"""HU-F1.5: materialized view ``prod.mv_ocupacion_diaria`` + UNIQUE INDEX for
REFRESH CONCURRENTLY + per-sucursal breakdown for GET /operacion/ocupacion.

Revision ID: 0024_mv_ocupacion_diaria
Revises: 0023_unique_active_sesion_per_user (F1.3 chain head)
Create Date: 2026-09-14

The view encapsulates the "ingreso activo" predicate as a single source
of truth: ``prod.ingreso`` rows minus ``prod.salidas`` rows minus
``prod.anulaciones`` (``tipo_anulable IN ('ingreso','salida')`` and
``estado='ejecutada'``), grouped by
``(uuid_sucursal, uuid_tipo_vehiculo)``.

The UNIQUE INDEX on the natural composite
``(uuid_sucursal, uuid_tipo_vehiculo)`` is mandatory for
``REFRESH MATERIALIZED VIEW CONCURRENTLY``; without it, plain
``REFRESH`` takes an ``AccessExclusiveLock`` that blocks the 10s
polling of N operadores.

Pre-flight (KD-7) reports row counts on ``prod.ingreso`` +
``prod.anulaciones`` and aborts with ``RAISE EXCEPTION`` if
``prod.ingreso`` exceeds the 50M row threshold (R5 mitigation; full
table scan on first refresh would otherwise take minutes and risk
statement timeout on managed Postgres).

KEPT IN SYNC WITH: ``specs/operations/spec.md`` REQ-OPS-032 (RFC 2119
MUST: pre-flight; CONCURRENTLY; natural composite UNIQUE INDEX;
downgrade).
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0024_mv_ocupacion_diaria"
down_revision = "0023_unique_active_sesion_per_user"  # F1.3 chain
branch_labels = None
depends_on = None


# KD-7: 10M is informational (RAISE NOTICE), 50M is hard abort (RAISE EXCEPTION).
_PREFLIGHT_THRESHOLD_INFO = 10_000_000
_PREFLIGHT_THRESHOLD_ABORT = 50_000_000


def upgrade() -> None:
    # 1) Pre-flight: report row counts on prod.ingreso and prod.anulaciones.
    #    The first REFRESH after CREATE MATERIALIZED VIEW executes the
    #    SELECT once to populate the table; on a > 10M-row ingreso table
    #    the SELECT takes minutes. Emit NOTICE so the operator sees the
    #    ETA in the alembic log; abort only if > 50M (R5 mitigation).
    op.execute(
        f"""
        DO $$
        DECLARE
            _n_ingreso bigint;
            _n_anul    bigint;
            _n_salidas bigint;
        BEGIN
            SELECT count(*) INTO _n_ingreso FROM prod.ingreso;
            SELECT count(*) INTO _n_anul    FROM prod.anulaciones;
            SELECT count(*) INTO _n_salidas FROM prod.salidas;
            RAISE NOTICE
                'mv_ocupacion_diaria_preflight: prod.ingreso=% filas, '
                'prod.salidas=% filas, prod.anulaciones=% filas. '
                'El primer REFRESH puede tardar segundos a minutos.',
                _n_ingreso, _n_salidas, _n_anul;
            IF _n_ingreso > {_PREFLIGHT_THRESHOLD_ABORT} THEN
                RAISE EXCEPTION
                    'mv_ocupacion_diaria_preflight_abort: prod.ingreso '
                    'tiene % filas (umbral {_PREFLIGHT_THRESHOLD_ABORT}). '
                    'Aplique indice (uuid_sucursal, uuid_tipo_vehiculo) '
                    'en prod.ingreso antes de continuar.',
                    _n_ingreso;
            END IF;
        END $$;
        """
    )

    # 2) CREATE the materialized view. Initial population is lazy --
    #    rows are computed on first SELECT after CREATE. The first
    #    cycle of RefreshMvOcupacionWorker will materialize the rows;
    #    until then GET /operacion/ocupacion returns the breakdown for
    #    the rows that exist (initially zero). KEEP the SELECT
    #    identical to the repo helper's underlying predicate.
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS prod.mv_ocupacion_diaria AS
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
    )

    # 3) UNIQUE INDEX mandatory for REFRESH MATERIALIZED VIEW CONCURRENTLY
    #    (KD-2). CONCURRENTLY cannot run inside a transaction; Alembic's
    #    op.execute uses autocommit per statement, satisfying the rule.
    #    IF NOT EXISTS makes this migration idempotent against retries.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
                uq_mv_ocupacion_diaria_sucursal_tipo
            ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
            """
        )

    # 4) Grant SELECT to the application role. The ``parkos_app`` role
    #    already has SELECT on prod.ingreso / salidas / anulaciones /
    #    cvs / tv; this GRANT is for the new MV only.
    op.execute(
        "GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app;"
    )


def downgrade() -> None:
    # DROP MATERIALIZED VIEW drops its indexes too (including the
    # UNIQUE INDEX); explicit DROP INDEX is not required. CONCURRENTLY
    # has no analog for DROP (acquires AccessExclusive regardless);
    # operators should schedule the rollback off-peak.
    op.execute(
        "DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria;"
    )


__all__ = ["downgrade", "upgrade"]
