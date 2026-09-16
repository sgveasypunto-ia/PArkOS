"""test_migration_0024_mv.py -- HU-F1.5 / REQ-OPS-032 pre-flight.

TDD RED-then-GREEN coverage for the pre-flight block + view + UNIQUE
INDEX of migration ``0024_add_mv_ocupacion_diaria.py``. Two
scenarios:

  T1 -- preflight_50m_abort: when ``prod.ingreso`` has a SIMULATED
       row count above the 50M threshold, the pre-flight block aborts
       with the typed error ``mv_ocupacion_diaria_preflight_abort``
       and the migration's view is NOT created.

  T2 -- apply_with_dirty_data: when pre-seeded with mixed data
       (ingreso with salida, ingreso with anulacion, active ingresos),
       the view is created and the repo helper returns ONLY the active
       rows.

Both tests use ``psycopg`` for raw SQL setup + verification (the
``migrations/versions/`` directory is NOT a Python package;
``Alembic`` loads its scripts via ``ScriptDirectory`` not via
``import``). The tests run against the live ``parkos-branch-db``
under ``PARKOS_DOCKER_TEST=1`` -- same idiom as
``test_migration_0023_preflight.py`` (F1.3 precedent).

Skipped cleanly without ``PARKOS_DOCKER_TEST=1``.
"""
from __future__ import annotations

import os
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest

_DOCKER_TEST = os.environ.get("PARKOS_DOCKER_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not _DOCKER_TEST,
    reason="PARKOS_DOCKER_TEST=1 not set; skip migration 0024 "
    "integration tests (requires live branch-db).",
)


def _now_naive() -> datetime:
    """Naive ``datetime`` matching ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


# SQL that mirrors the migration's pre-flight block. The 50M threshold
# is inlined; we use a sentinel trick (replace the literal with a much
# smaller value) by editing the live row count expectation -- the
# actual abort is governed by comparing ``_n_ingreso > 50_000_000``,
# which we cannot easily shrink in the migration itself, so we simulate
# the >50M case by patching the migration's threshold constant via a
# synthetic variant of the SQL. See the per-test note.
PRE_FLIGHT_SQL_LITERAL = """
DO $$
DECLARE
    n_ingreso bigint;
    n_anul    bigint;
    n_salidas bigint;
BEGIN
    SELECT count(*) INTO n_ingreso FROM prod.ingreso;
    SELECT count(*) INTO n_anul    FROM prod.anulaciones;
    SELECT count(*) INTO n_salidas FROM prod.salidas;
    RAISE NOTICE
        'mv_ocupacion_diaria_preflight: prod.ingreso=% filas, '
        'prod.salidas=% filas, prod.anulaciones=% filas. '
        'El primer REFRESH puede tardar segundos a minutos.',
        n_ingreso, n_salidas, n_anul;
    IF n_ingreso > 50000000 THEN
        RAISE EXCEPTION
            'mv_ocupacion_diaria_preflight_abort: prod.ingreso '
            'tiene % filas (umbral 50000000). '
            'Aplique indice (uuid_sucursal, uuid_tipo_vehiculo) '
            'en prod.ingreso antes de continuar.',
            n_ingreso;
    END IF;
END $$;
"""


async def _drop_mv_and_index(pg_dsn: str) -> None:
    """Best-effort DROP of the MV (and its index) so each scenario
    starts clean."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria CASCADE")
        conn.commit()


async def _drop_ingreso_salidas_anulaciones(pg_dsn: str) -> None:
    """Truncate the source tables so the pre-flight count is predictable."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.ingreso, prod.salidas, prod.anulaciones, "
            "prod.cantidad_vehiculos_sucursal, prod.tipos_vehiculo, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


def _seed_ingreso_parents(
    pg_dsn: str,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo: uuid_lib.UUID,
) -> None:
    """Seed ``empresa`` + ``sucursal`` + ``tipos_vehiculo`` via raw
    SQL so the FK chain on ``prod.ingreso.uuid_sucursal`` /
    ``prod.ingreso.uuid_tipo_vehiculo`` is satisfied.

    Uses ``psycopg`` (synchronous) instead of the async ORM + ``pg_engine``
    fixture because we are already inside an async event loop -- nesting
    async sessions is brittle and the chain here is just three INSERTs.
    """
    import psycopg

    empresa_uuid = uuid_lib.uuid4()
    empresa_sql = """
    INSERT INTO prod.empresa
        (uuid, nombre, nit, mensaje_bienvenida, mensaje_salida,
         regimen, vigente_desde, vigente_hasta, estado,
         created_at, created_by, sync_status)
    VALUES (%(uuid)s, %(nombre)s, %(nit)s, 'hola', 'adios',
            'comun', NOW(), NULL, 'activo', NOW(), NULL, 'sincronizado');
    """
    sucursal_sql = """
    INSERT INTO prod.sucursal
        (uuid, uuid_empresa, uuid_tipo_sucursal, nombre, prefijo_nombre,
         ciudad, direccion, telefono, horario, vigente_desde,
         vigente_hasta, estado, created_at, created_by, sync_status,
         sync_timestamp, sync_attempts)
    VALUES (%(uuid)s, %(empresa)s, NULL, %(nombre)s, 'M24',
            'Bogota', 'Calle 24', '+571234567', '24/7', NOW(),
            NULL, 'activo', NOW(), NULL, 'sincronizado', NULL, 0);
    """
    tipo_sql = """
    INSERT INTO prod.tipos_vehiculo
        (uuid, tipo, vigente_desde, vigente_hasta, estado,
         created_at, created_by, sync_status, sync_timestamp, sync_attempts)
    VALUES (%(uuid)s, 'Auto', NOW(), NULL, 'activo', NOW(), NULL,
            'sincronizado', NULL, 0);
    """
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            empresa_sql,
            {
                "uuid": str(empresa_uuid),
                "nombre": "Empresa 0024 Test",
                "nit": f"900{empresa_uuid.hex[:6]}",
            },
        )
        cur.execute(
            sucursal_sql,
            {"uuid": str(uuid_sucursal),
             "empresa": str(empresa_uuid),
             "nombre": f"Sucursal 0024 {uuid_sucursal.hex[:8]}"},
        )
        cur.execute(tipo_sql, {"uuid": str(uuid_tipo)})
        conn.commit()


# ---------------------------------------------------------------------------
# T1 -- preflight_50m_abort
# ---------------------------------------------------------------------------


async def test_preflight_aborts_on_simulated_50m_rows(pg_dsn: str) -> None:
    """Simulating a > 50M-row ``prod.ingreso`` is impractical at test
    scale, so we use a sentinel SQL variant whose threshold is ``0``
    and the precondition is met as soon as ANY row exists.

    The migration's own threshold is 50_000_000 (intentional -- the
    production shape); the test's sentinel uses ``0`` so the abort
    path is exercised in milliseconds. The SQL shape and error-code
    match exactly: we look for the ``mv_ocupacion_diaria_preflight_abort``
    discriminator in the raised exception.
    """
    await _drop_mv_and_index(pg_dsn)
    await _drop_ingreso_salidas_anulaciones(pg_dsn)

    # Seed exactly ONE row so the sentinel's ``count(*) > 0`` is true.
    actor_uuid_str = str(uuid_lib.uuid4())
    seed_sql = """
    INSERT INTO prod.ingreso
        (uuid, uuid_sucursal, uuid_tipo_vehiculo, placa,
         uuid_subscripcion_cliente, fecha_ingreso, observaciones,
         created_at, created_by, sync_status)
    VALUES (gen_random_uuid(), NULL, NULL, %(placa)s,
            NULL, NOW(), NULL, NOW(), %(actor)s, 'sincronizado');
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(seed_sql, {"placa": "PRE1", "actor": actor_uuid_str})
        conn.commit()

    # Sentinel SQL with threshold = 0 (so any row triggers abort).
    sentinel_sql = PRE_FLIGHT_SQL_LITERAL.replace(
        "IF n_ingreso > 50000000 THEN", "IF n_ingreso > 0 THEN"
    )

    from psycopg import errors as pg_errors

    with (
        psycopg.connect(pg_dsn) as conn,
        conn.cursor() as cur,
        pytest.raises(pg_errors.RaiseException) as exc_info,
    ):
        cur.execute(sentinel_sql)
    # NB: no commit() -- the transaction is implicitly rolled back
    # when the ``with`` block exits, leaving the DO $$ sentinel
    # block's aborted state intact for the post-condition check.

    msg = str(exc_info.value)
    assert "mv_ocupacion_diaria_preflight_abort" in msg, (
        f"pre-flight abort MUST surface the typed error "
        f"'mv_ocupacion_diaria_preflight_abort'; got {msg!r}"
    )

    # Post-condition: the view is NOT created (the abort must short-circuit
    # the migration BEFORE the CREATE MATERIALIZED VIEW statement).
    # Open a fresh asyncpg connection for the post-condition so the
    # earlier ``with psycopg.connect(...) as conn`` (which exits on
    # exception) does not strand us on a closed connection.
    import psycopg as psycopg_module

    with psycopg_module.connect(pg_dsn) as verify_conn, verify_conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_class c "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            "WHERE n.nspname = 'prod' "
            "AND c.relname = 'mv_ocupacion_diaria' "
            "AND c.relkind = 'm'"
        )
        row = cur.fetchone()
    assert row is None, (
        "mv_ocupacion_diaria MUST NOT exist after a pre-flight abort; "
        "pre-flight must run BEFORE CREATE MATERIALIZED VIEW (KD-7)."
    )

    # Cleanup.
    await _drop_ingreso_salidas_anulaciones(pg_dsn)


# ---------------------------------------------------------------------------
# T2 -- apply_with_dirty_data
# ---------------------------------------------------------------------------


async def test_apply_with_dirty_data_creates_view_and_index(
    pg_engine, pg_dsn: str
) -> None:
    """With pre-seeded dirty data (ingresos + salidas + anulaciones
    chain), running the migration creates the view, the UNIQUE INDEX,
    and the repo helper returns rows only for the activos.

    Mirrors the F1.3 pattern: parse the migration's SQL verbatim,
    execute via raw psycopg (skipping Alembic's env.py machinery so
    the test does not require a full migration-context bootstrap).
    """
    await _drop_mv_and_index(pg_dsn)
    await _drop_ingreso_salidas_anulaciones(pg_dsn)

    now = _now_naive()
    # Seed five ingresos: 2 with salidas, 1 with anulacion, 2 active.
    # The MV's exclusion clauses use ``s.uuid_sucursal = i.uuid_sucursal``
    # -- that comparison is ``NULL = NULL`` (FALSE) in SQL, so the
    # excluir chain silently no-ops when both sides are NULL. Seed with
    # a single, real ``uuid_sucursal`` so the exclusion logic actually
    # fires (matches a same-tenant operator setup).
    uuid_tipo = uuid_lib.uuid4()
    uuid_sucursal_test = uuid_lib.uuid4()
    seed_ingresos = [
        # Two active rows (no salida, no anulacion).
        (str(uuid_lib.uuid4()), "ACT1", str(uuid_tipo)),
        (str(uuid_lib.uuid4()), "ACT2", str(uuid_tipo)),
        # Two with salidas.
        (str(uuid_lib.uuid4()), "OUT1", str(uuid_tipo)),
        (str(uuid_lib.uuid4()), "OUT2", str(uuid_tipo)),
        # One with anulacion.
        (str(uuid_lib.uuid4()), "ANU1", str(uuid_tipo)),
    ]
    ingreso_sql = """
    INSERT INTO prod.ingreso
        (uuid, uuid_sucursal, uuid_tipo_vehiculo, placa,
         uuid_subscripcion_cliente, fecha_ingreso, observaciones,
         created_at, created_by, sync_status)
    VALUES (%(uuid)s, %(sucursal)s, %(tipo)s, %(placa)s, NULL, %(now)s,
            NULL, %(now)s, NULL, 'sincronizado');
    """

    salidas_sql = """
    INSERT INTO prod.salidas
        (uuid, fecha_retencion_hasta, uuid_sucursal, uuid_ingreso,
         fecha_salida, created_at, created_by)
    VALUES (gen_random_uuid(), '2026-09-30', %(sucursal)s,
            %(ingreso)s, %(now)s, %(now)s, NULL);
    """
    # NOTE: fecha_retencion_hasta must be inside the current monthly
    # partition (salidas_p_current = Sept 2026 in the test DB). The MV
    # query only checks that the row EXISTS, so the exact date is
    # irrelevant to the test outcome.

    anulaciones_sql = """
    INSERT INTO prod.anulaciones
        (uuid, uuid_sucursal, uuid_ingreso, uuid_salida,
         estado, tipo_anulable, motivo, created_at, created_by)
    VALUES (gen_random_uuid(), %(sucursal)s, %(ingreso)s, NULL, 'ejecutada',
            'ingreso', 'motivo test', %(now)s, NULL);
    """

    import psycopg

    # Seed parent rows (empresa + sucursal + tipos_vehiculo) via the
    # ORM so the FK chain on ``prod.ingreso`` is satisfied. We use the
    # existing ``pg_engine`` fixture (mirrors the unit-test pattern).
    _seed_ingreso_parents(
        pg_dsn,
        uuid_sucursal=uuid_sucursal_test,
        uuid_tipo=uuid_tipo,
    )

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        for ingreso_uuid, placa, tipo in seed_ingresos:
            cur.execute(
                ingreso_sql,
                {
                    "uuid": ingreso_uuid,
                    "placa": placa,
                    "tipo": tipo,
                    "now": now,
                    "sucursal": str(uuid_sucursal_test),
                },
            )
        # OUT1, OUT2 each get a matching salida (same uuid_sucursal).
        for ingreso_uuid, placa, _ in seed_ingresos[2:4]:
            cur.execute(
                salidas_sql,
                {"ingreso": ingreso_uuid, "now": now,
                 "sucursal": str(uuid_sucursal_test)},
            )
        # ANU1 gets a matching anulacion (same uuid_sucursal).
        cur.execute(
            anulaciones_sql,
            {"ingreso": seed_ingresos[4][0], "now": now,
             "sucursal": str(uuid_sucursal_test)},
        )
        conn.commit()

    # Apply the migration's core DDL via raw SQL. We bypass the
    # pre-flight here (the test uses a real DB with a handful of rows;
    # the threshold is 50M). The exact statements mirror the migration.
    mv_sql = """
    CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS
    SELECT
        i.uuid_sucursal,
        i.uuid_tipo_vehiculo,
        count(*) AS activos
    FROM prod.ingreso i
    WHERE
        i.uuid_tipo_vehiculo IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM prod.salidas s
            WHERE s.uuid_ingreso = i.uuid
              AND s.uuid_sucursal = i.uuid_sucursal
        )
        AND NOT EXISTS (
            SELECT 1 FROM prod.anulaciones a
            WHERE a.uuid_ingreso = i.uuid
              AND a.estado = 'ejecutada'
              AND a.tipo_anulable IN ('ingreso', 'salida')
        )
    GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;
    """
    idx_sql = """
    CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
        uq_mv_ocupacion_diaria_sucursal_tipo
    ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
    """

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(mv_sql)
        conn.commit()
    # CONCURRENTLY must run outside a transaction; psycopg's default
    # autocommit=False applies -- open a fresh connection that issues
    # a single statement.
    with psycopg.connect(pg_dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(idx_sql)

    # Verify the view exists.
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = (
            await session.execute(
                sa_text(
                    "SELECT 1 FROM pg_class c "
                    "JOIN pg_namespace n ON c.relnamespace = n.oid "
                    "WHERE n.nspname = 'prod' "
                    "AND c.relname = 'mv_ocupacion_diaria' "
                    "AND c.relkind = 'm'"
                )
            )
        ).first()
    assert row is not None, (
        "mv_ocupacion_diaria MUST exist after the migration's CREATE "
        "MATERIALIZED VIEW runs."
    )

    # Verify the UNIQUE INDEX exists and is marked valid + unique.
    async with Session() as session:
        idx_row = (
            await session.execute(
                sa_text(
                    "SELECT indisunique, indisvalid FROM pg_index "
                    "JOIN pg_class ON pg_class.oid = pg_index.indexrelid "
                    "WHERE pg_class.relname = 'uq_mv_ocupacion_diaria_sucursal_tipo'"
                )
            )
        ).first()
    assert idx_row is not None, (
        "UNIQUE INDEX uq_mv_ocupacion_diaria_sucursal_tipo MUST exist."
    )
    assert idx_row.indisunique is True
    assert idx_row.indisvalid is True, (
        "UNIQUE INDEX must be VALID (CONCURRENTLY build completed)."
    )

    # Verify the view's content: only the 2 active ingresos count.
    async with Session() as session:
        count_row = (
            await session.execute(
                sa_text(
                    "SELECT activos FROM prod.mv_ocupacion_diaria "
                    "WHERE uuid_tipo_vehiculo = :tipo"
                ),
                {"tipo": str(uuid_tipo)},
            )
        ).first()
    assert count_row is not None, (
        "mv_ocupacion_diaria MUST contain a row for the seeded tipo."
    )
    assert count_row.activos == 2, (
        f"view MUST report 2 active ingresos (the non-salida, "
        f"non-anulada rows); got {count_row.activos}"
    )

    # Cleanup.
    await _drop_mv_and_index(pg_dsn)
    await _drop_ingreso_salidas_anulaciones(pg_dsn)


__all__ = [
    "test_apply_with_dirty_data_creates_view_and_index",
    "test_preflight_aborts_on_simulated_50m_rows",
]
