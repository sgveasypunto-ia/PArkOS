"""test_pr_c_api_e2e.py — PR-C end-to-end coverage of the extended
``tarifas-sucursal`` + ``cantidad-vehiculos-sucursal`` API surface.

This file covers the four behaviours added on top of the factory:

  1. ``vigente_desde`` opcional — schedule a future rate / capacity.
  2. Overlap guard — 409 ``tarifa_overlap`` / ``cantidad_overlap``
     when a new window would intersect an existing open row.
  3. ``sucursal_inmutable`` guard — 422 on PUT that changes the row's
     branch.
  4. ``capacidad_insuficiente`` guard (BR2, HU-F14.4) — 422 on PUT that
     lowers capacity below the count of currently-active ``ingreso``
     rows for the same ``(uuid_sucursal, uuid_tipo_vehiculo)``.
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
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None,
    vigente_desde: datetime | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "uuid_sucursal": str(uuid_sucursal),
        "uuid_tipo_vehiculo": str(uuid_tipo_vehiculo) if uuid_tipo_vehiculo else None,
        "cantidad": cantidad,
    }
    if vigente_desde is not None:
        body["vigente_desde"] = vigente_desde.isoformat()
    return body


async def _seed_tipo_vehiculo(pg_engine, *, uuid_tipo: uuid_lib.UUID, tipo: str) -> None:
    """Insert one vigente ``tipos_vehiculo`` row (mirror of
    ``test_mv_ocupacion_diaria_db.py::_seed_tipo_vehiculo``)."""
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo,
                tipo=tipo,
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


async def _seed_ingreso_activo(
    pg_engine, *, uuid_sucursal: uuid_lib.UUID, uuid_tipo_vehiculo: uuid_lib.UUID
) -> uuid_lib.UUID:
    """Insert one active ``prod.ingreso`` row (no matching salida/anulacion),
    the same minimal shape ``test_mv_ocupacion_diaria_db.py::_seed_ingreso``
    uses. Return its uuid."""
    from parkos_core.models.L_E.ingreso import Ingreso
    from sqlalchemy.ext.asyncio import async_sessionmaker

    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                placa=f"PRC{ingreso_uuid.hex[:6]}",
                uuid_subscripcion_cliente=None,
                fecha_ingreso=_now_naive(),
                observaciones=None,
                created_at=_now_naive(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


async def _refresh_mv_ocupacion(pg_dsn: str) -> None:
    """Force-refresh ``prod.mv_ocupacion_diaria`` so the guard's read
    sees ingresos seeded in this test (the real refresh runs on a
    worker; tests cannot wait on it, see C2/C9/C10 below)."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria;")
        conn.commit()


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
    """BR2 (HU-F14.4): the operator cannot lower ``cantidad`` below the
    count of currently-active ``ingreso`` rows for the same
    ``(uuid_sucursal, uuid_tipo_vehiculo)``. The guard reuses
    ``repo.ocupacion.get_ocupacion_puros_activos`` (the HU-F1.5
    ``mv_ocupacion_diaria`` breakdown, catalog-driven by
    ``tipos_vehiculo``).

    A REAL ``uuid_tipo_vehiculo`` (not the NULL "blanket" cell the
    other C-series tests use) is required here: the MV's breakdown
    join is driven by the ``tipos_vehiculo`` catalog, so a NULL-typed
    cupos row never matches a breakdown row and the guard would never
    fire for it (by design — see the PR-C PUT handler docstring).
    """
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    tipo_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=tipo_uuid, tipo="moto")
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    # Seed an open cantidad with capacidad 50 for the real tipo.
    post = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(
            uuid_sucursal=branch_uuid, cantidad=50, uuid_tipo_vehiculo=tipo_uuid
        ),
        headers=headers,
    )
    assert post.status_code == 201, post.text
    cupos_uuid = post.json()["uuid"]

    # Seed 2 active ingreso rows (ORM insert — the model does not
    # require cliente/vehiculo FKs) and refresh the MV so the guard
    # observes ``ocupado_actual == 2``.
    await _seed_ingreso_activo(pg_engine, uuid_sucursal=branch_uuid, uuid_tipo_vehiculo=tipo_uuid)
    await _seed_ingreso_activo(pg_engine, uuid_sucursal=branch_uuid, uuid_tipo_vehiculo=tipo_uuid)
    await _refresh_mv_ocupacion(pg_dsn)

    # PUT lower cantidad to 1 (< 2 active ingresos) → 422.
    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{cupos_uuid}",
        json=_cantidad_payload(
            uuid_sucursal=branch_uuid, cantidad=1, uuid_tipo_vehiculo=tipo_uuid
        ),
        headers=headers,
    )
    assert put.status_code == 422, f"got {put.status_code}: {put.text}"
    detail = put.json()["detail"]
    assert detail["error"] == "capacidad_insuficiente"
    assert detail["tipo"] == "moto"
    assert detail["ocupado_actual"] == 2
    assert detail["solicitado"] == 1


@_HTTP_PYTESTMARK
async def test_c8_put_cantidad_aumenta_capacidad_ok(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """BR2: increasing ``cantidad`` for a tipo always succeeds (200),
    regardless of current occupancy — the guard only fires on a
    reduction below ``ocupado_actual``."""
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    tipo_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=tipo_uuid, tipo="carro")
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    post = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(
            uuid_sucursal=branch_uuid, cantidad=10, uuid_tipo_vehiculo=tipo_uuid
        ),
        headers=headers,
    )
    assert post.status_code == 201, post.text
    cupos_uuid = post.json()["uuid"]

    await _seed_ingreso_activo(pg_engine, uuid_sucursal=branch_uuid, uuid_tipo_vehiculo=tipo_uuid)
    await _refresh_mv_ocupacion(pg_dsn)

    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{cupos_uuid}",
        json=_cantidad_payload(
            uuid_sucursal=branch_uuid, cantidad=20, uuid_tipo_vehiculo=tipo_uuid
        ),
        headers=headers,
    )
    assert put.status_code == 200, f"got {put.status_code}: {put.text}"
    assert put.json()["cantidad"] == 20


@_HTTP_PYTESTMARK
async def test_c9_put_cantidad_reduce_por_encima_de_ocupado_ok(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """BR2: reducing ``cantidad`` is allowed as long as the new total
    stays at or above ``ocupado_actual`` (200)."""
    await _truncate_cantidad(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    tipo_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=tipo_uuid, tipo="carro")
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    post = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_cantidad_payload(
            uuid_sucursal=branch_uuid, cantidad=10, uuid_tipo_vehiculo=tipo_uuid
        ),
        headers=headers,
    )
    assert post.status_code == 201, post.text
    cupos_uuid = post.json()["uuid"]

    # 2 active ingresos — reducing to 5 (> 2) must still succeed.
    await _seed_ingreso_activo(pg_engine, uuid_sucursal=branch_uuid, uuid_tipo_vehiculo=tipo_uuid)
    await _seed_ingreso_activo(pg_engine, uuid_sucursal=branch_uuid, uuid_tipo_vehiculo=tipo_uuid)
    await _refresh_mv_ocupacion(pg_dsn)

    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{cupos_uuid}",
        json=_cantidad_payload(
            uuid_sucursal=branch_uuid, cantidad=5, uuid_tipo_vehiculo=tipo_uuid
        ),
        headers=headers,
    )
    assert put.status_code == 200, f"got {put.status_code}: {put.text}"
    assert put.json()["cantidad"] == 5


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
