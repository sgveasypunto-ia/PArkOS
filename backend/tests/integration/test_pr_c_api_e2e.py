"""test_pr_c_api_e2e.py — PR-C end-to-end coverage of the extended
``tarifas-sucursal`` + ``cantidad-vehiculos-sucursal`` API surface.

This file covers the four behaviours added on top of the factory:

  1. ``vigente_desde`` opcional — schedule a future rate / capacity.
  2. Overlap guard — 409 ``tarifa_overlap`` / ``cantidad_overlap``
     when a new window would intersect an existing open row.
  3. ``sucursal_inmutable`` guard — 422 on PUT that changes the row's
     branch.
  4. ``cantidad_bajo_ingresos_activos`` guard — 422 on PUT that lowers
     capacity below the count of currently-active ``ingreso`` rows.
  5. ``by-key / history`` endpoint — walks the bi-temporal version
     chain by business identity (UK01 columns) instead of by uuid.

The basic C/Q+U surface (T1..T5 / C1..C4 of PR-C v1) is implicitly
covered: the 0059 lock-in was already pinned by
``test_migration_0059_router_permissions.py`` at the migration level,
and the factory's GET list / GET /{uuid} / GET /{uuid}/history still
work unchanged. We focus the e2e tests on what PR-C actually changed.

Layout:

  * Helpers — shared ``_seed_sucursal``, ``_grant_permission``,
    ``_truncate_*``, ``_payload_*``.
  * Tarifas tests T1..T5.
  * Cantidad tests C1..C5.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

# Only the HTTP-driven tests parametrize ``app``. The UK01 invariant
# tests (no HTTP) skip it. Pattern documented in PR-C.
_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive UTC datetime matching the DB ``DateTime(timezone=False)`` column."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _ensure_permiso(pg_engine, *, perm_code: str) -> uuid_lib.UUID:
    """Idempotent permiso row (SELECT-or-INSERT) — mirrors HU-F1.4 helper."""
    from parkos_core.models.V.permisos import Permisos
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        existing = (
            await session.execute(
                select(Permisos).where(
                    Permisos.permiso == perm_code, Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.uuid
        row = Permisos(
            uuid=uuid_lib.uuid4(),
            permiso=perm_code,
            vigente_desde=_now_naive(),
            vigente_hasta=None,
            estado="activo",
            created_at=_now_naive(),
            created_by=None,
            sync_status="sincronizado",
            sync_timestamp=_now_naive(),
            sync_attempts=0,
        )
        session.add(row)
        await session.commit()
        return row.uuid


async def _grant_permission(
    pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str
) -> None:
    """Idempotent permisos_usuario grant."""
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    permiso_uuid = await _ensure_permiso(pg_engine, perm_code=perm_code)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        already = (
            await session.execute(
                select(PermisosUsuario).where(
                    PermisosUsuario.uuid_usuario == actor_uuid,
                    PermisosUsuario.uuid_permiso == permiso_uuid,
                    PermisosUsuario.vigente_hasta.is_(None),
                )
            )
        ).scalar_one_or_none()
        if already is not None:
            return
        session.add(PermisosUsuario(uuid_usuario=actor_uuid, uuid_permiso=permiso_uuid))
        await session.commit()


async def _seed_sucursal(pg_engine, uuid_sucursal: uuid_lib.UUID) -> None:
    """Insert a real Empresa + Sucursal so the FK from tarifas / cantidad resolves."""
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa PR-C v2",
                nit=f"903{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="Hola",
                mensaje_salida="Adios",
                regimen="comun",
                vigente_desde=_now_naive(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now_naive(),
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
                nombre=f"Sucursal PR-C v2 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"E{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Test 1",
                telefono="+571234567",
                horario="24/7",
                vigente_desde=_now_naive(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now_naive(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()


async def _truncate_tarifas(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.tarifas_sucursal")
        conn.commit()


async def _truncate_cantidad(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.cantidad_vehiculos_sucursal")
        conn.commit()


def _tarifa_payload(
    *,
    uuid_sucursal: uuid_lib.UUID,
    valor: str = "1500.00",
    valor_plena: str = "2000.00",
    vigente_desde: datetime | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "uuid_sucursal": str(uuid_sucursal),
        "uuid_tipo_vehiculo": None,
        "uuid_tipo_tarifa": None,
        "valor": valor,
        "valor_plena": valor_plena,
    }
    if vigente_desde is not None:
        body["vigente_desde"] = vigente_desde.isoformat()
    return body


def _cantidad_payload(
    *,
    uuid_sucursal: uuid_lib.UUID,
    cantidad: int = 50,
    vigente_desde: datetime | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "uuid_sucursal": str(uuid_sucursal),
        "uuid_tipo_vehiculo": None,
        "cantidad": cantidad,
    }
    if vigente_desde is not None:
        body["vigente_desde"] = vigente_desde.isoformat()
    return body


# ---------------------------------------------------------------------------
# T1 — vigente_desde opcional del cliente (programar tarifa futura)
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_t1_tarifa_vigente_desde_futuro(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """POST with ``vigente_desde`` in the future schedules a tariff that
    is NOT vigente at ``now()`` but IS vigente at the scheduled instant.

    The handler accepts the future date and the row opens at that
    boundary. The factory's GET list filters by
    ``vigente_hasta IS NULL`` (open rows), so the new row IS in the
    list (it has not closed yet). The dedicated HU-F1.4 listing
    handler filters by the bi-temporal predicate with
    ``vigente_en=now`` — the row is excluded because
    ``vigente_desde > now``.

    The cotizador therefore charges the OLD rate at ``now`` (no
    vigente tarifa with the new ``vigente_desde``) and would switch
    to the new rate starting at the scheduled boundary. PR-C's
    ability to schedule without a separate "scheduled change" feature
    is what the operator asked for.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    futura = _now_naive() + timedelta(days=30)
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_tarifa_payload(uuid_sucursal=branch_uuid, vigente_desde=futura),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["vigente_hasta"] is None
    assert datetime.fromisoformat(body["vigente_desde"]) == futura

    # GET by-key/history lists the future version.
    by_key = await client.get(
        "/api/v1/empresa/tarifas-sucursal/by-key",
        params={"sucursal": str(branch_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert by_key.status_code == 200, f"got {by_key.status_code}: {by_key.text}"
    items = by_key.json()
    assert len(items) == 1
    assert datetime.fromisoformat(items[0]["vigente_desde"]) == futura


# ---------------------------------------------------------------------------
# T2 — overlap guard: 409 tarifa_overlap
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_t2_put_tarifa_overlap_devuelve_409(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """A second POST that opens a window strictly inside an existing
    open row's window must be rejected with 409 ``tarifa_overlap``.

    The seed is open-ended. The new candidate at a strictly later
    ``vigente_desde`` overlaps because the seed never closes. The
    handler surfaces the conflict with the offending row's uuid +
    vigente_desde in the detail.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    first = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_tarifa_payload(uuid_sucursal=branch_uuid),
        headers=headers,
    )
    assert first.status_code == 201, first.text
    seed_uuid = first.json()["uuid"]

    # Wait a tick so the second POST's clock_timestamp() is strictly
    # after the first one's. The first was at _now_naive() at POST
    # time; ``time.sleep(0.01)`` is overkill for Postgres'
    # ``clock_timestamp()`` precision but it's the simplest way to make
    # the test deterministic.
    import asyncio

    await asyncio.sleep(0.01)

    second = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_tarifa_payload(uuid_sucursal=branch_uuid, valor="9999.00"),
        headers=headers,
    )
    assert second.status_code == 409, (
        f"strict overlap with open row must return 409; got {second.status_code}: "
        f"{second.text}"
    )
    detail = second.json()["detail"]
    assert detail["error"] == "tarifa_overlap"
    assert detail["conflicting_uuid"] == seed_uuid


# ---------------------------------------------------------------------------
# T3 — sucursal_inmutable: 422 on PUT that changes uuid_sucursal
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_t3_put_tarifa_cambia_sucursal_devuelve_422(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """A PUT that tries to move the tarifa to a different branch is
    rejected with 422 ``sucursal_inmutable``. The tarifa belongs to
    the branch that created it; the operator must create a new
    version on the destination branch instead."""
    await _truncate_tarifas(pg_dsn)
    branch_a = uuid_lib.uuid4()
    branch_b = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_a)
    await _seed_sucursal(pg_engine, branch_b)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_a, branch_b])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_a),
    }

    post = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_tarifa_payload(uuid_sucursal=branch_a),
        headers=headers,
    )
    assert post.status_code == 201, post.text
    tarifa_uuid = post.json()["uuid"]

    # PUT trying to move to branch_b.
    put = await client.put(
        f"/api/v1/empresa/tarifas-sucursal/{tarifa_uuid}",
        json=_tarifa_payload(uuid_sucursal=branch_b, valor="3000.00"),
        headers=headers,
    )
    assert put.status_code == 422, f"got {put.status_code}: {put.text}"
    detail = put.json()["detail"]
    assert detail["error"] == "sucursal_inmutable"
    assert detail["existing_sucursal"] == str(branch_a)
    assert detail["attempted_sucursal"] == str(branch_b)


# ---------------------------------------------------------------------------
# T4 — valor <= 0 es rechazado por Pydantic antes de tocar la DB
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_t4_post_tarifa_valor_negativo_devuelve_422(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """``valor <= 0`` is rejected at the API edge (Pydantic
    ``Field(gt=0)``) with 422. The DB is never touched."""
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_tarifa_payload(uuid_sucursal=branch_uuid, valor="-1.00"),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# T5 — by-key/history recorre toda la cadena bi-temporal
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_t5_by_key_history_recorre_versiones_post_close(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """PUT issues a fresh UUID on close+insert. The factory's
    ``GET /{uuid}/history`` filters by uuid and only returns the
    closed original. ``GET /by-key`` walks the chain by business
    identity (UK01 columns) and returns BOTH versions DESC by
    ``vigente_desde``.

    This is the gap that the PR-C v1 docstring flagged as a
    follow-up. PR-C v2 closes it.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    post = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json=_tarifa_payload(uuid_sucursal=branch_uuid),
        headers=headers,
    )
    assert post.status_code == 201
    original_uuid = post.json()["uuid"]

    import asyncio

    await asyncio.sleep(0.01)

    put = await client.put(
        f"/api/v1/empresa/tarifas-sucursal/{original_uuid}",
        json=_tarifa_payload(uuid_sucursal=branch_uuid, valor="3000.00"),
        headers=headers,
    )
    assert put.status_code == 200, put.text

    # by-key walks the full chain.
    by_key = await client.get(
        "/api/v1/empresa/tarifas-sucursal/by-key",
        params={"sucursal": str(branch_uuid)},
        headers=headers,
    )
    assert by_key.status_code == 200, by_key.text
    versions = by_key.json()
    assert len(versions) == 2, (
        f"close+insert must produce 2 versions visible by-key; got {len(versions)}"
    )
    # DESC by vigente_desde.
    assert Decimal(str(versions[0]["valor"])) == Decimal("3000.00")
    assert versions[0]["vigente_hasta"] is None
    assert versions[0]["estado"] == "activo"
    assert Decimal(str(versions[1]["valor"])) == Decimal("1500.00")
    assert versions[1]["vigente_hasta"] is not None
    assert versions[1]["estado"] == "inactivo"


# ---------------------------------------------------------------------------
# C1 — POST cupos con vigente_desde futuro
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_c1_post_cantidad_vigente_desde_futuro(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """Mirror of T1 for cantidad."""
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    futura = _now_naive() + timedelta(days=15)
    resp = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=42, vigente_desde=futura),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["cantidad"] == 42
    assert datetime.fromisoformat(body["vigente_desde"]) == futura


# ---------------------------------------------------------------------------
# C2 — PUT que baja cantidad bajo ingresos activos: 422
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_c2_put_cantidad_bajo_ingresos_activos_devuelve_422(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """The operator cannot lower ``cantidad`` below the count of
    currently-active ``ingreso`` rows for the same
    ``(uuid_sucursal, uuid_tipo_vehiculo)``. The guard reads from
    ``mv_ocupacion_diaria`` via ``validar_cantidad_vigente``.

    We do NOT seed an active ``ingreso`` row directly (the test would
    need the full ingreso flow); we seed a fake "activos" via the MV
    by inserting an ingreso with the right shape. With the MV lag
    (<=10s) accepted as live risk, we ``time.sleep`` only if needed;
    a 422 on ``activos=1 > solicitada=0`` is enough to pin the guard.

    To pin the GUARD without seeding ingreso rows, we POST
    ``cantidad=50`` and then PUT ``cantidad=0``. Without an active
    ingreso the MV returns activos=0, which is NOT greater than 0,
    so the guard does NOT fire and the PUT succeeds. To force the
    guard to fire we need activos > solicitada. The simplest
    deterministic way is to seed an ingreso row directly via psycopg
    — but that requires the ingreso FK chain (cliente, vehiculo,
    tipo_vehiculo). We accept the cost: a focused integration test
    is worth the seed.

    Alternative approach (chosen here): seed the ingresos indirectly
    via a direct INSERT into ``prod.ingreso`` with the minimum column
    set the MV reads. This pins the guard's reactivity to MV state.
    """
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    # Seed an open cantidad with capacidad 50.
    post = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=50),
        headers=headers,
    )
    assert post.status_code == 201, post.text
    cupos_uuid = post.json()["uuid"]

    # Seed an active ingreso row so the MV reports activos >= 1. We
    # bypass the API (which would require the full ingreso contract)
    # and INSERT directly via psycopg. The MV refresh is async; we
    # wait up to 12s for it to pick up the row.
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        # The ingreso table requires a cliente + vehiculo + tipo_vehiculo
        # (FK chain). We seed a minimal valid row. The full FK
        # validation in tests is heavy; for this test we only need
        # the MV to see an open ingreso at our (sucursal, tipo_vehiculo).
        # We use a NULL uuid_tipo_vehiculo so the row matches the
        # NULL-cell cupos (the cell ``ingreso.uuid_tipo_vehiculo IS NULL``).
        cur.execute(
            """
            INSERT INTO prod.ingreso (
                uuid, uuid_sucursal, uuid_tipo_vehiculo, uuid_cliente,
                uuid_vehiculo, consecutivo, placa, fecha_ingreso,
                estado, vigente_desde, vigente_hasta, created_at,
                created_by, sync_status, sync_attempts
            ) VALUES (
                gen_random_uuid(), %s, NULL,
                (SELECT uuid FROM prod.clientes LIMIT 1),
                (SELECT uuid FROM prod.vehiculos LIMIT 1),
                9001, 'PRCCAPO',
                clock_timestamp(), 'activo', clock_timestamp(),
                NULL, clock_timestamp(), NULL, 'sincronizado', 0
            )
            """,
            (branch_uuid,),
        )
        conn.commit()

    # Refresh the MV (its refresh is on a worker; for the test we
    # force a refresh via psycopg so we do not depend on ``psql`` on
    # PATH). CONCURRENTLY requires the MV to have a unique index
    # (which it does — see ``0024_add_mv_ocupacion_diaria``), and
    # permits reads to continue during the refresh.
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria;")
        conn.commit()

    # PUT lower cantidad to 0 with 1+ active ingreso → 422.
    import asyncio

    await asyncio.sleep(0.01)

    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{cupos_uuid}",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=0),
        headers=headers,
    )
    assert put.status_code == 422, f"got {put.status_code}: {put.text}"
    detail = put.json()["detail"]
    assert detail["error"] == "cantidad_bajo_ingresos_activos"
    assert detail["activos"] >= 1
    assert detail["solicitada"] == 0


# ---------------------------------------------------------------------------
# C3 — PUT sin ingresos activos puede bajar cantidad libremente
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_c3_put_cantidad_baja_sin_ingresos_activos_ok(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """Without active ingreso, the guard does NOT fire. PUT that
    lowers ``cantidad`` succeeds (200) and creates a new version."""
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    post = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=50),
        headers=headers,
    )
    assert post.status_code == 201, post.text
    cupos_uuid = post.json()["uuid"]

    import asyncio

    await asyncio.sleep(0.01)

    # Lower from 50 to 10 — no active ingreso, guard does not fire.
    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{cupos_uuid}",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=10),
        headers=headers,
    )
    assert put.status_code == 200, f"got {put.status_code}: {put.text}"
    assert put.json()["cantidad"] == 10

    # by-key shows both versions.
    by_key = await client.get(
        "/api/v1/empresa/cantidad-vehiculos-sucursal/by-key",
        params={"sucursal": str(branch_uuid)},
        headers=headers,
    )
    assert by_key.status_code == 200, by_key.text
    assert len(by_key.json()) == 2


# ---------------------------------------------------------------------------
# C4 — overlap guard: 409 cantidad_overlap
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_c4_post_cantidad_overlap_devuelve_409(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """Mirror of T2 for cantidad: a second POST inside an existing
    open row's window returns 409 ``cantidad_overlap``."""
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    first = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=50),
        headers=headers,
    )
    assert first.status_code == 201, first.text
    seed_uuid = first.json()["uuid"]

    import asyncio

    await asyncio.sleep(0.01)

    second = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=20),
        headers=headers,
    )
    assert second.status_code == 409, (
        f"strict overlap with open cantidad must return 409; got "
        f"{second.status_code}: {second.text}"
    )
    detail = second.json()["detail"]
    assert detail["error"] == "cantidad_overlap"
    assert detail["conflicting_uuid"] == seed_uuid


# ---------------------------------------------------------------------------
# C5 — sucursal_inmutable on PUT (mirror of T3 for cupos)
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_c5_put_cantidad_cambia_sucursal_devuelve_422(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """A PUT that tries to move the cupos to a different branch is
    rejected with 422 ``sucursal_inmutable``."""
    await _truncate_cantidad(pg_dsn)
    branch_a = uuid_lib.uuid4()
    branch_b = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_a)
    await _seed_sucursal(pg_engine, branch_b)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_a, branch_b])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_a),
    }

    post = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(uuid_sucursal=branch_a, cantidad=50),
        headers=headers,
    )
    assert post.status_code == 201, post.text
    cupos_uuid = post.json()["uuid"]

    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{cupos_uuid}",
        json=_cantidad_payload(uuid_sucursal=branch_b, cantidad=20),
        headers=headers,
    )
    assert put.status_code == 422, f"got {put.status_code}: {put.text}"
    detail = put.json()["detail"]
    assert detail["error"] == "sucursal_inmutable"
    assert detail["existing_sucursal"] == str(branch_a)
    assert detail["attempted_sucursal"] == str(branch_b)


# ---------------------------------------------------------------------------
# C6 — tz-aware ``vigente_desde`` no longer 500s
# ---------------------------------------------------------------------------
#
# Regression for the cupos POST/PUT 500 reproduced 2026-09-29: the
# admin ``<CupoForm>`` ``datetimeLocalToIso`` helper appends ``+00:00``
# to the datetime-local string, so the wire payload arrives tz-aware.
# Pydantic v2 keeps the tzinfo; ``assert_no_overlap`` binds it to a
# ``DateTime(timezone=False)`` column and asyncpg rejects with
# ``can't subtract offset-naive and offset-aware datetimes`` (DataError
# 500). The handler now normalizes the payload via ``_to_naive_utc``
# before binding. Same fix covers tarifas POST/PUT (latent).
#
# We hit POST and PUT with an explicit ``+00:00`` offset and assert
# 201/200, not 500.


@_HTTP_PYTESTMARK
async def test_c6_post_cantidad_vigente_desde_tz_aware_no_500(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """POST with a tz-aware ``vigente_desde`` must NOT 500."""
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    futura = _now_naive() + timedelta(days=10)
    # Wire payload mirrors the admin ``<CupoForm>`` format:
    # ``datetimeLocalToIso`` appends ``+00:00`` to the datetime-local.
    payload = {
        "uuid_sucursal": str(branch_uuid),
        "uuid_tipo_vehiculo": None,
        "cantidad": 25,
        "vigente_desde": futura.isoformat() + "+00:00",
    }
    resp = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["cantidad"] == 25
    # The response ``vigente_desde`` is naive (matches DB column).
    assert datetime.fromisoformat(body["vigente_desde"]) == futura


@_HTTP_PYTESTMARK
async def test_c7_put_cantidad_vigente_desde_tz_aware_no_500(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """PUT (edit) with a tz-aware ``vigente_desde`` must NOT 500."""
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    # Seed an open cupos.
    seed = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(uuid_sucursal=branch_uuid, cantidad=50),
        headers=headers,
    )
    assert seed.status_code == 201, seed.text
    cupos_uuid = seed.json()["uuid"]

    import asyncio

    await asyncio.sleep(0.01)

    # PUT with tz-aware vigente_desde. The handler must normalize and
    # succeed (not 500). The "overlap guard" sees nueva_desde ==
    # semilla.vigente_desde -> the new row opens at the same boundary
    # the existing row closed at (Carril B: ``exclude_uuid``).
    nueva = _now_naive() + timedelta(days=20)
    payload = {
        "uuid_sucursal": str(branch_uuid),
        "uuid_tipo_vehiculo": None,
        "cantidad": 75,
        "vigente_desde": nueva.isoformat() + "+00:00",
    }
    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{cupos_uuid}",
        json=payload,
        headers=headers,
    )
    assert put.status_code == 200, f"got {put.status_code}: {put.text}"
    assert put.json()["cantidad"] == 75
