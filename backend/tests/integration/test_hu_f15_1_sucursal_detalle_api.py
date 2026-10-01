"""test_hu_f15_1_sucursal_detalle_api.py — HU-F15.1 backend surface (T3/T5).

Covers the two backend deliverables of HU-F15.1's atomic task T3:

  1. BR4 — the ``vigente_en`` bi-temporal filter added to
     ``GET /empresa/cantidad-vehiculos-sucursal`` and
     ``GET /empresa/resolucion-facturacion`` (``tarifas-sucursal`` already
     had it since HU-F1.4 and is NOT re-tested here).
  2. BR2/BR3 — the new ``POST /empresa/sucursal/{uuid}/deshabilitar`` guard:
     404 unknown branch, 409 ``sucursal_con_ocupacion``, 409
     ``sucursal_con_suscripciones_vigentes``, and the 204 happy path.

Layout mirrors ``test_pr_c_api_e2e.py`` (shared seed helpers duplicated
locally per that file's own precedent — see e.g.
``test_tarifas_tipo_required.py``'s ``_grant_permission`` docstring: "Mirror
of the helper in ...") plus ``test_mv_ocupacion_diaria_db.py`` /
``test_pr_c_api_e2e.py`` for the MV-backed occupancy seed.

Tests run via real ASGI + testcontainers Postgres (``client``/``app``
fixtures, ``conftest.py``), same as every other integration test in this
suite. ``resolucion-facturacion`` is DIAN-root / cloud-only (REQ-X3): its
tests use ``app="admin"`` because the branch (``sucursal``) deploy excludes
the resource entirely (``api/v1/__init__.py::_CLOUD_ONLY_EMPRESA_RESOURCES``).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta

import pytest

_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["sucursal"], indirect=True)
_ADMIN_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["admin"], indirect=True)


def _now_naive() -> datetime:
    """Naive UTC datetime matching the DB ``DateTime(timezone=False)`` column."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _ensure_permiso(pg_engine, *, perm_code: str) -> uuid_lib.UUID:
    """Idempotent permiso row (SELECT-or-INSERT). Mirror of
    ``test_pr_c_api_e2e.py::_ensure_permiso``."""
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


async def _grant_permission(pg_engine, *, actor_uuid: uuid_lib.UUID, perm_code: str) -> None:
    """Idempotent permisos_usuario grant. Mirror of
    ``test_pr_c_api_e2e.py::_grant_permission``."""
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


async def _assign_admin_to_sucursal(
    pg_engine, *, actor_uuid: uuid_lib.UUID, uuid_sucursal: uuid_lib.UUID
) -> None:
    """Grant an admin actor an open ``usuarios_sucursal`` row for a branch.

    Required ONLY for handlers behind ``requires_sucursal``/``get_tenant_ctx``
    that receive an ``X-Sucursal-Context`` header for an ``admin-`` token:
    ``auth.tenancy.get_tenant_ctx`` validates that header against
    ``extract_sucursales_permitidas_fresh`` (a live ``usuarios_sucursal``
    read), NOT the JWT's ``sucursales_permitidas`` claim -- without this row
    the request 403s with ``unauthorized_sucursal_context`` before the
    handler body ever runs. ``usuarios_sucursal.uuid_usuario`` carries a real
    DB-level FK to ``prod.usuarios``, so a bare ``Usuarios`` row is seeded
    too (mirrors ``test_tarifas_tipo_required.py``'s ``_grant_permission``
    minimal-user shape)."""
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Admin",
                apellido="HU-F15.1",
                email=f"{actor_uuid}@example.com",
                password_hash="test-hash",
                rol="admin",
            )
        )
        session.add(
            UsuariosSucursal(uuid_sucursal=uuid_sucursal, uuid_usuario=actor_uuid)
        )
        await session.commit()


async def _seed_sucursal(pg_engine, uuid_sucursal: uuid_lib.UUID) -> None:
    """Insert a real Empresa + Sucursal. Mirror of
    ``test_pr_c_api_e2e.py::_seed_sucursal``."""
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa HU-F15.1",
                nit=f"905{empresa_uuid.hex[:6]}",
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
                nombre=f"Sucursal HU-F15.1 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"F{uuid_sucursal.hex[:6]}",
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


async def _seed_tipo_vehiculo(pg_engine, *, uuid_tipo: uuid_lib.UUID, tipo: str) -> None:
    """Insert one vigente ``tipos_vehiculo`` row. Mirror of
    ``test_pr_c_api_e2e.py::_seed_tipo_vehiculo``."""
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
    """Insert one active ``prod.ingreso`` row (no matching salida/anulacion).
    Mirror of ``test_pr_c_api_e2e.py::_seed_ingreso_activo``."""
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
                placa=f"F15{ingreso_uuid.hex[:6]}",
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
    """Force-refresh ``prod.mv_ocupacion_diaria``. Mirror of
    ``test_pr_c_api_e2e.py::_refresh_mv_ocupacion`` (the real refresh runs on
    a worker; tests cannot wait on it)."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria;")
        conn.commit()


async def _seed_cantidad_vehiculos_sucursal(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    vigente_desde: datetime,
    cantidad: int = 10,
) -> uuid_lib.UUID:
    """Insert one ``cantidad_vehiculos_sucursal`` row at a specific
    ``vigente_desde`` (BR4 test needs control over the exact valid-time
    boundary, independent of ``now()``)."""
    from parkos_core.models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    row_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid=row_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                cantidad=cantidad,
                vigente_desde=vigente_desde,
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
    return row_uuid


async def _seed_resolucion_facturacion(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    vigente_desde: datetime,
) -> uuid_lib.UUID:
    """Insert one ``resolucion_facturacion`` row at a specific
    ``vigente_desde`` (same BR4 control need as the cantidad helper)."""
    from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
    from sqlalchemy.ext.asyncio import async_sessionmaker

    row_uuid = uuid_lib.uuid4()
    hoy = date.today()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            ResolucionFacturacion(
                uuid=row_uuid,
                uuid_sucursal=uuid_sucursal,
                numero_resolucion=f"RES-{row_uuid.hex[:8]}",
                prefijo="FE",
                rango_desde=1,
                rango_hasta=5000,
                fecha_resolucion=hoy,
                fecha_inicio_vigencia=hoy,
                fecha_fin_vigencia=hoy + timedelta(days=365),
                vigente_desde=vigente_desde,
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
    return row_uuid


async def _seed_subscripcion_cliente_vigente(
    pg_engine, *, uuid_sucursal: uuid_lib.UUID
) -> uuid_lib.UUID:
    """Insert one vigente ``subscripciones_cliente`` row referencing a branch
    (BR3: blocks ``deshabilitar`` while any such row is open). No real
    ``clientes`` / ``tipo_subscripciones`` parent rows are needed -- neither
    FK is enforced at the SQL level (app-enforced only, per this table's own
    model docstring)."""
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
    from sqlalchemy.ext.asyncio import async_sessionmaker

    row_uuid = uuid_lib.uuid4()
    hoy = date.today()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            SubscripcionesCliente(
                uuid=row_uuid,
                uuid_cliente=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_subscripcion=uuid_lib.uuid4(),
                fecha_inicio_cobertura=hoy,
                fecha_vencimiento=hoy + timedelta(days=30),
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
    return row_uuid


# ---------------------------------------------------------------------------
# BR4 — ``vigente_en`` on GET /empresa/cantidad-vehiculos-sucursal
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_br4_cantidad_vigente_en_excluye_version_futura(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """A ``cantidad_vehiculos_sucursal`` row whose ``vigente_desde`` is in
    the future is excluded when ``vigente_en`` is a point in time BEFORE it,
    and included once ``vigente_en`` reaches/crosses that boundary."""
    branch_uuid = uuid_lib.uuid4()
    tipo_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=tipo_uuid, tipo="carro")
    await _assign_admin_to_sucursal(pg_engine, actor_uuid=actor_uuid, uuid_sucursal=branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    boundary = _now_naive() + timedelta(days=10)
    await _seed_cantidad_vehiculos_sucursal(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_uuid,
        vigente_desde=boundary,
    )

    before = await client.get(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        params={"vigente_en": (boundary - timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert before.status_code == 200, before.text
    assert before.json()["items"] == []

    after = await client.get(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        params={"vigente_en": (boundary + timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert after.status_code == 200, after.text
    uuids = {item["uuid_sucursal"] for item in after.json()["items"]}
    assert str(branch_uuid) in uuids


# ---------------------------------------------------------------------------
# BR4 — ``vigente_en`` on GET /empresa/resolucion-facturacion (admin/cloud)
# ---------------------------------------------------------------------------


@_ADMIN_HTTP_PYTESTMARK
async def test_br4_resolucion_facturacion_vigente_en_excluye_version_futura(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """Same bi-temporal contract as the cantidad test, for
    ``resolucion-facturacion`` -- the DIAN-root / cloud-only resource, hence
    ``app="admin"`` (``api_sucursal`` excludes this resource entirely)."""
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _assign_admin_to_sucursal(pg_engine, actor_uuid=actor_uuid, uuid_sucursal=branch_uuid)
    await _grant_permission(
        pg_engine, actor_uuid=actor_uuid, perm_code="admin_resolucion_facturacion"
    )
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }

    boundary = _now_naive() + timedelta(days=10)
    await _seed_resolucion_facturacion(
        pg_engine, uuid_sucursal=branch_uuid, vigente_desde=boundary
    )

    before = await client.get(
        "/api/v1/empresa/resolucion-facturacion",
        params={"vigente_en": (boundary - timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert before.status_code == 200, before.text
    assert before.json()["items"] == []

    after = await client.get(
        "/api/v1/empresa/resolucion-facturacion",
        params={"vigente_en": (boundary + timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert after.status_code == 200, after.text
    uuids = {item["uuid_sucursal"] for item in after.json()["items"]}
    assert str(branch_uuid) in uuids


# ---------------------------------------------------------------------------
# BR2/BR3 — POST /empresa/sucursal/{uuid}/deshabilitar
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_deshabilitar_404_sucursal_no_encontrada(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """An unknown (or already-closed) branch uuid 404s before any guard runs."""
    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_sucursal")
    token = mint_admin_jwt(actor_uuid=actor_uuid)

    resp = await client.post(
        f"/api/v1/empresa/sucursal/{uuid_lib.uuid4()}/deshabilitar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["error"] == "sucursal_no_encontrada"


@_HTTP_PYTESTMARK
async def test_deshabilitar_409_sucursal_con_ocupacion(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    """BR3: refuses to disable a branch with an active (open) ``ingreso``."""
    branch_uuid = uuid_lib.uuid4()
    tipo_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(pg_engine, uuid_tipo=tipo_uuid, tipo="carro")
    await _seed_ingreso_activo(pg_engine, uuid_sucursal=branch_uuid, uuid_tipo_vehiculo=tipo_uuid)
    await _refresh_mv_ocupacion(pg_dsn)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_sucursal")
    token = mint_admin_jwt(actor_uuid=actor_uuid)

    resp = await client.post(
        f"/api/v1/empresa/sucursal/{branch_uuid}/deshabilitar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "sucursal_con_ocupacion"
    assert detail["activos"] >= 1


@_HTTP_PYTESTMARK
async def test_deshabilitar_409_sucursal_con_suscripciones_vigentes(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """BR3: refuses to disable a branch with a vigente subscription, even
    with zero active ingresos."""
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_subscripcion_cliente_vigente(pg_engine, uuid_sucursal=branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_sucursal")
    token = mint_admin_jwt(actor_uuid=actor_uuid)

    resp = await client.post(
        f"/api/v1/empresa/sucursal/{branch_uuid}/deshabilitar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "sucursal_con_suscripciones_vigentes"
    assert detail["suscripciones_vigentes"] >= 1


@_HTTP_PYTESTMARK
async def test_deshabilitar_204_happy_path_cierra_sin_reemplazo(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """With no blockers, the branch closes (204). Asserted directly against
    the DB (not a follow-up GET): the dedicated global-reads router that
    answers ``GET /empresa/sucursal/{uuid}`` bounds its result to the
    caller's OWN ``usuarios_sucursal`` assignments (``_permitted_sucursal_
    uuids``), which this test's actor was never granted -- that would 404
    regardless of whether the close happened, so it cannot tell the two
    cases apart. The DB read proves exactly BR2's "close-only, no
    replacement version" contract: same ``uuid``, ``vigente_hasta`` now set,
    and no second row for this branch exists."""
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_sucursal")
    token = mint_admin_jwt(actor_uuid=actor_uuid)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/empresa/sucursal/{branch_uuid}/deshabilitar",
        headers=headers,
    )
    assert resp.status_code == 204, resp.text

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        rows = (
            (await session.execute(select(Sucursal).where(Sucursal.uuid == branch_uuid)))
            .scalars()
            .all()
        )
    assert len(rows) == 1, "close_only must not insert a replacement version"
    assert rows[0].vigente_hasta is not None
    assert rows[0].estado == "inactivo"
