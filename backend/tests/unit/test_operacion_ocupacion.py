"""test_operacion_ocupacion.py -- HU-F1.5 / REQ-OPS-030..031.

TDD RED -> GREEN coverage for the new ``GET /api/v1/operacion/ocupacion``
handler introduced by HU-F1.5. The endpoint exposes a thin adapter over
the materialized view ``prod.mv_ocupacion_diaria`` (refreshed every 10s
by ``parkos_core.jobs.refresh_mv_ocupacion``) plus the LEFT JOIN to
``cantidad_vehiculos_sucursal`` for the ``cupo_maximo`` field.

Pattern: mirrors the HU-F1.8 / HU-F1.4 precedent in
``tests/unit/test_calcular_cotizacion.py`` and
``tests/unit/test_caja_sesion_me.py`` -- real ``pg_engine`` plus an
``httpx.AsyncClient`` bound to the FastAPI app via ``ASGITransport``.

Four scenarios from ``openspec/changes/hu-f1-5-mv-ocupacion-diaria/
design.md §11 File 1``:

  1. operador-self   -- happy path: operador- pinned to ``X``,
     ``GET ?uuid_sucursal=X`` returns 200 + ``OcupacionResponse`` with
     the per-tipo breakdown (REQs REQ-OPS-030).
  2. operador-cross  -- cross-tenant attempt from ``X`` to ``Y``
     returns 403 ``tenant_scope_violation`` (REQ-OPS-031 KD-3).
  3. admin-allowed   -- admin- with ``X-Sucursal-Context`` + matching
     ``sucursales_permitidas`` returns 200 (REQ-OPS-031 KD-3 admin).
  4. admin-no-context -- admin- without ``X-Sucursal-Context`` AND no
     claim-pinned sucursal returns 400 ``missing_sucursal_context``
     (REQ-OPS-031 KD-3 missing).

All responses carry the ``Cache-Control: no-store`` header (R8
consistency with F1.3 / F1.8).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


def _now_naive() -> datetime:
    """Naive ``datetime`` matching ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate_ocupacion_tables(pg_dsn: str) -> None:
    """Truncate the tables the endpoint JOINs.

    ``prod.mv_ocupacion_diaria`` is a MATERIALIZED VIEW, not a table,
    so we cannot TRUNCATE it; we rely on the per-test refresh + the
    source-table TRUNCATE CASCADE to invalidate it. The next
    ``REFRESH MATERIALIZED VIEW`` (triggered by the test's seed
    helper) repopulates the rows.
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.ingreso, prod.salidas, prod.anulaciones, "
            "prod.cantidad_vehiculos_sucursal, prod.tipos_vehiculo, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _seed_empresa_sucursal(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> None:
    """Insert ``empresa`` + ``sucursal`` to satisfy FK chains."""
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa Ocup Test",
                nit=f"900{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="Hola",
                mensaje_salida="Adios",
                regimen="comun",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa_uuid,
                uuid_tipo_sucursal=None,
                nombre=f"Sucursal Ocup {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"O{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Ocup 1",
                telefono="+571234567",
                horario="24/7",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _seed_tipo_y_cantidad(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    tipo: str,
    cupo_maximo: int,
) -> None:
    """Insert ``tipos_vehiculo`` + a vigente ``cantidad_vehiculos_sucursal``
    row with the given cupo.

    Splits the inserts into two commits because the
    ``fk_cantidad_vehiculos_sucursal_uuid_tipo_vehiculo`` constraint is
    evaluated per-statement on Postgres when both rows live in the
    same unit-of-work -- flushing the cantidad row before the
    tipos_vehiculo row hits a violation. Issuing the tipos_vehiculo
    INSERT + COMMIT in its own transaction first makes the row
    visible to the subsequent INSERT.
    """
    from parkos_core.models.V.cantidad_vehiculos_sucursal import (
        CantidadVehiculosSucursal,
    )

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo_vehiculo,
                tipo=tipo,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                cantidad=cupo_maximo,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _seed_ingreso(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
) -> uuid_lib.UUID:
    """Insert one ingreso row and refresh the MV."""
    now = _now_naive()
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                placa=f"Ocup{ingreso_uuid.hex[:6]}",
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now,
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
        # The MV may have been dropped by a co-located integration
        # test. Create it idempotently before refreshing -- the repo
        # test setup (F1.5) is independent from the migration chain.
        await _ensure_mv_exists(pg_engine)
        await session.execute(
            text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")
        )
        await session.commit()
    return ingreso_uuid


async def _ensure_mv_exists(pg_engine) -> None:
    """Idempotent CREATE of ``prod.mv_ocupacion_diaria`` + UNIQUE INDEX.

    The view + index belong to migration 0024; co-running this unit
    test with the integration suite can leave the DB in a state where
    the integration tests dropped the MV. Defense in depth: rebuild
    if missing.

    The DSN is derived from the SQLAlchemy engine URL converted back
    to ``postgresql://`` syntax (asyncpg uses ``postgresql+asyncpg://``).
    """
    import psycopg

    dsn_async = pg_engine.url.render_as_string(hide_password=False)
    # asyncpg URL -> psycopg (sync) URL
    dsn_sync = dsn_async.replace("postgresql+asyncpg://", "postgresql://")

    mv_sql = """
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
    idx_sql = """
    CREATE UNIQUE INDEX IF NOT EXISTS
        uq_mv_ocupacion_diaria_sucursal_tipo
    ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
    """

    with psycopg.connect(dsn_sync) as conn, conn.cursor() as cur:
        cur.execute(mv_sql)
        conn.commit()
    with psycopg.connect(dsn_sync, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(idx_sql)


# ---------------------------------------------------------------------------
# Caso 1 -- operador self -> 200
# ---------------------------------------------------------------------------


async def test_operador_self_returns_200_with_ocupacion_response(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """operador- pinned to ``X`` requesting ``?uuid_sucursal=X`` returns
    200 + ``OcupacionResponse`` containing the per-tipo breakdown."""
    await _truncate_ocupacion_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()
    tipo_moto = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_uuid)
    await _seed_tipo_y_cantidad(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_auto,
        tipo="carro",
        cupo_maximo=50,
    )
    await _seed_tipo_y_cantidad(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_moto,
        tipo="moto",
        cupo_maximo=20,
    )
    await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_auto,
    )

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    resp = await client.get(
        "/api/v1/operacion/ocupacion",
        params={"uuid_sucursal": str(branch_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert resp.headers.get("Cache-Control") == "no-store", (
        f"Cache-Control: no-store missing on happy-path response; "
        f"got {resp.headers.get('Cache-Control')!r}"
    )
    body = resp.json()
    assert body["uuid_sucursal"] == str(branch_uuid)
    assert isinstance(body["items"], list)
    assert len(body["items"]) >= 1, (
        f"breakdown MUST contain at least one item (the seeded Auto row); "
        f"got {body['items']!r}"
    )
    auto_item = next(
        (it for it in body["items"] if it["uuid_tipo_vehiculo"] == str(tipo_auto)),
        None,
    )
    assert auto_item is not None, (
        f"breakdown MUST include the seeded Auto tipo; got {body['items']!r}"
    )
    assert auto_item["tipo"] == "Auto"
    assert auto_item["cupo_maximo"] == 50
    assert auto_item["activos"] == 1
    assert auto_item["disponible"] == 49
    # Items are ORDER BY tv.tipo; "Auto" precedes "Moto".
    tipos_in_order = [it["tipo"] for it in body["items"]]
    assert tipos_in_order == sorted(tipos_in_order), (
        f"items MUST be ordered by tipo (KD-4); got {tipos_in_order!r}"
    )


# ---------------------------------------------------------------------------
# Caso 2 -- operador cross-tenant -> 403 tenant_scope_violation
# ---------------------------------------------------------------------------


async def test_operador_cross_tenant_returns_403_tenant_scope_violation(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """operador- pinned to ``X`` requesting ``?uuid_sucursal=Y`` returns
    403 ``tenant_scope_violation`` (REQ-OPS-031 KD-3)."""
    await _truncate_ocupacion_tables(pg_dsn)

    branch_x = uuid_lib.uuid4()
    branch_y = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_x)
    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_y)

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_x)

    resp = await client.get(
        "/api/v1/operacion/ocupacion",
        params={"uuid_sucursal": str(branch_y)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_x),
        },
    )

    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    # FastAPI wraps HTTPException(detail={...}) under ``detail``.
    detail = body.get("detail") or {}
    assert detail.get("error") == "tenant_scope_violation", (
        f"error discriminator MUST be 'tenant_scope_violation' (REQ-OPS-031 KD-3); "
        f"got {body!r}"
    )
    # Defense in depth: NEVER leak pgcode / driver strings / the target UUID.
    body_str = str(body)
    for leak in ("pgcode", "psycopg", "asyncpg", str(branch_y)):
        assert leak not in body_str, (
            f"403 body MUST NOT leak pgcode / driver strings / target UUID; "
            f"got {body_str!r}"
        )


# ---------------------------------------------------------------------------
# Caso 3 -- admin- with valid X-Sucursal-Context -> 200
# ---------------------------------------------------------------------------


async def test_admin_allowed_branch_returns_200(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """admin- with ``X-Sucursal-Context`` matching
    ``claims['sucursales_permitidas']`` returns 200 (REQ-OPS-031 KD-3)."""
    await _truncate_ocupacion_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_uuid)
    await _seed_tipo_y_cantidad(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_auto,
        tipo="carro",
        cupo_maximo=30,
    )

    token = mint_admin_jwt(
        actor_uuid=actor_uuid,
        sucursales_permitidas=[branch_uuid],
    )

    resp = await client.get(
        "/api/v1/operacion/ocupacion",
        params={"uuid_sucursal": str(branch_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert resp.headers.get("Cache-Control") == "no-store"
    body = resp.json()
    assert body["uuid_sucursal"] == str(branch_uuid)
    assert isinstance(body["items"], list)
    # The seed inserted one tipo; the breakdown returns one row.
    assert len(body["items"]) == 1
    assert body["items"][0]["cupo_maximo"] == 30
    assert body["items"][0]["activos"] == 0


# ---------------------------------------------------------------------------
# Caso 4 -- admin- no X-Sucursal-Context and no query -> 400 missing_sucursal_context
# ---------------------------------------------------------------------------


async def test_admin_no_context_returns_400_missing_sucursal_context(
    pg_engine, mint_admin_jwt, client, pg_dsn
) -> None:
    """admin- with no ``X-Sucursal-Context`` header AND no ``?uuid_sucursal=``
    query param returns 400 ``missing_sucursal_context`` (REQ-OPS-031 KD-3
    missing)."""
    await _truncate_ocupacion_tables(pg_dsn)

    actor_uuid = uuid_lib.uuid4()
    # ``mint_admin_jwt`` requires ``X-Sucursal-Context`` for ANY admin-
    # token validation through ``get_tenant_ctx`` -- so the cleanest way
    # to trigger the handler-level 400 (rather than the dependency-level
    # one) is to pass a header that fails the per-tenant check. The
    # handler raises 400 ``missing_sucursal_context`` ONLY when neither
    # the query param nor ``ctx.sucursal_uuid`` resolves a target.
    #
    # The dependency chain enforces ``X-Sucursal-Context`` first; if the
    # dependency raises 400 ``missing_sucursal_context``, that satisfies
    # the same contract (same error code, same status). This test
    # therefore asserts the dependency-level outcome, which is the
    # canonical ``400 missing_sucursal_context`` path for admin-.

    # Use a token that has NO allowed sucursales -- but issue_token
    # needs at least one. We pass a dummy UUID; since the request has
    # no header, the dependency's 400 fires BEFORE the handler runs.
    bogus_branch = uuid_lib.uuid4()
    token = mint_admin_jwt(
        actor_uuid=actor_uuid,
        sucursales_permitidas=[bogus_branch],
    )

    resp = await client.get(
        "/api/v1/operacion/ocupacion",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 400, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    detail = body.get("detail") or {}
    assert detail.get("error") == "missing_sucursal_context", (
        f"error discriminator MUST be 'missing_sucursal_context' "
        f"(REQ-OPS-031 KD-3); got {body!r}"
    )
    # Defense in depth: NEVER leak pgcode / driver strings.
    body_str = str(body)
    for leak in ("pgcode", "psycopg", "asyncpg"):
        assert leak not in body_str


__all__ = [
    "test_admin_allowed_branch_returns_200",
    "test_admin_no_context_returns_400_missing_sucursal_context",
    "test_operador_cross_tenant_returns_403_tenant_scope_violation",
    "test_operador_self_returns_200_with_ocupacion_response",
]
