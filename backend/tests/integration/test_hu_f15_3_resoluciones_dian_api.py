"""test_hu_f15_3_resoluciones_dian_api.py — HU-F15.3 backend surface (T3/T5).

Covers ``GET /empresa/resolucion-facturacion/{uuid}/consecutivo-actual``
(BR1/BR2): a read-only projection of the current consecutivo (derived as
``COALESCE(MAX(factura_electronica.consecutivo), rango_desde - 1) + 1``,
mirroring ``dian.cloud.atomic_next_consecutivo.next_consecutivo`` WITHOUT its
``SELECT ... FOR UPDATE`` lock) plus the "agotandose" banner flag (fewer than
100 numbers left before ``rango_hasta``).

Seed helpers are duplicated locally, same precedent as
``test_hu_f15_1_sucursal_detalle_api.py`` (its own module docstring explains
why: "shared seed helpers duplicated locally per that file's own precedent").
``resolucion-facturacion`` is DIAN-root / cloud-only (REQ-X3): tests use
``app="admin"`` because the branch (``sucursal``) deploy excludes the
resource entirely (``api/v1/__init__.py::_CLOUD_ONLY_EMPRESA_RESOURCES``).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta

import pytest

_ADMIN_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["admin"], indirect=True)


def _now_naive() -> datetime:
    """Naive UTC datetime matching the DB ``DateTime(timezone=False)`` column."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _ensure_permiso(pg_engine, *, perm_code: str) -> uuid_lib.UUID:
    """Idempotent permiso row (SELECT-or-INSERT). Mirror of
    ``test_hu_f15_1_sucursal_detalle_api.py::_ensure_permiso``."""
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
    ``test_hu_f15_1_sucursal_detalle_api.py::_grant_permission``."""
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
    Mirror of ``test_hu_f15_1_sucursal_detalle_api.py::_assign_admin_to_sucursal``."""
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Admin",
                apellido="HU-F15.3",
                email=f"{actor_uuid}@example.com",
                password_hash="test-hash",
                rol="admin",
            )
        )
        session.add(UsuariosSucursal(uuid_sucursal=uuid_sucursal, uuid_usuario=actor_uuid))
        await session.commit()


async def _seed_sucursal(pg_engine, uuid_sucursal: uuid_lib.UUID) -> None:
    """Insert a real Empresa + Sucursal. Mirror of
    ``test_hu_f15_1_sucursal_detalle_api.py::_seed_sucursal``."""
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa HU-F15.3",
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
                nombre=f"Sucursal HU-F15.3 {uuid_sucursal.hex[:8]}",
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


async def _seed_resolucion_facturacion(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    rango_desde: int,
    rango_hasta: int,
) -> uuid_lib.UUID:
    """Insert one ``resolucion_facturacion`` row with a known range. Mirror
    of ``test_hu_f15_1_sucursal_detalle_api.py::_seed_resolucion_facturacion``,
    parametrized on the range instead of ``vigente_desde`` (HU-F15.3 needs
    control over the range, not the bi-temporal boundary)."""
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
                rango_desde=rango_desde,
                rango_hasta=rango_hasta,
                fecha_resolucion=hoy,
                fecha_inicio_vigencia=hoy,
                fecha_fin_vigencia=hoy + timedelta(days=365),
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


async def _seed_factura_electronica(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    consecutivo: int,
) -> uuid_lib.UUID:
    """Insert one ``factura_electronica`` row pinned to a consecutivo. Mirror
    of ``test_dian_round_trip.py::_seed_factura_electronica``, minus the
    ``facturas``/``clientes`` parents (neither FK is enforced at the SQL
    level for this table)."""
    from parkos_core.models.L_E.factura_electronica import FacturaElectronica
    from sqlalchemy.ext.asyncio import async_sessionmaker

    row_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            FacturaElectronica(
                uuid=row_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_factura=None,
                uuid_cliente=None,
                uuid_resolucion_facturacion=uuid_resolucion_facturacion,
                prefijo="FE",
                consecutivo=consecutivo,
                descuento=0,
                created_at=_now_naive(),
                created_by=None,
            )
        )
        await session.commit()
    return row_uuid


async def _actor_headers(pg_engine, mint_admin_jwt, *, branch_uuid: uuid_lib.UUID) -> dict:
    actor_uuid = uuid_lib.uuid4()
    await _assign_admin_to_sucursal(pg_engine, actor_uuid=actor_uuid, uuid_sucursal=branch_uuid)
    await _grant_permission(
        pg_engine, actor_uuid=actor_uuid, perm_code="admin_resolucion_facturacion"
    )
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    return {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }


# ---------------------------------------------------------------------------
# BR1 — consecutivo_actual derivation (COALESCE(MAX(consecutivo), rango_desde - 1) + 1)
# ---------------------------------------------------------------------------


@_ADMIN_HTTP_PYTESTMARK
async def test_consecutivo_actual_sin_facturas_previas_arranca_en_rango_desde(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """No ``factura_electronica`` rows yet -> the first consecutivo lands on
    ``rango_desde`` (matches ``atomic_next_consecutivo.next_consecutivo``'s
    own ``start = rango_desde - 1`` when there is no existing MAX)."""
    branch_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch_uuid)
    resolucion_uuid = await _seed_resolucion_facturacion(
        pg_engine, uuid_sucursal=branch_uuid, rango_desde=1, rango_hasta=5000
    )

    resp = await client.get(
        f"/api/v1/empresa/resolucion-facturacion/{resolucion_uuid}/consecutivo-actual",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["consecutivo_actual"] == 1
    assert body["rango_hasta"] == 5000
    assert body["restantes"] == 4999
    assert body["agotandose"] is False


@_ADMIN_HTTP_PYTESTMARK
async def test_consecutivo_actual_con_facturas_previas_lee_max_mas_uno(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """With 2 existing ``factura_electronica`` rows (consecutivo 1 and 2),
    the next one is 3 -- same MAX()+1 read the real allocator uses, just
    without the write-path lock."""
    branch_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch_uuid)
    resolucion_uuid = await _seed_resolucion_facturacion(
        pg_engine, uuid_sucursal=branch_uuid, rango_desde=1, rango_hasta=5000
    )
    await _seed_factura_electronica(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_resolucion_facturacion=resolucion_uuid,
        consecutivo=1,
    )
    await _seed_factura_electronica(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_resolucion_facturacion=resolucion_uuid,
        consecutivo=2,
    )

    resp = await client.get(
        f"/api/v1/empresa/resolucion-facturacion/{resolucion_uuid}/consecutivo-actual",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["consecutivo_actual"] == 3
    assert body["restantes"] == 4997


@_ADMIN_HTTP_PYTESTMARK
async def test_consecutivo_actual_404_resolucion_no_encontrada(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    branch_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch_uuid)

    resp = await client.get(
        f"/api/v1/empresa/resolucion-facturacion/{uuid_lib.uuid4()}/consecutivo-actual",
        headers=headers,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["error"] == "resolucion_no_encontrada"


# ---------------------------------------------------------------------------
# BR2 — "agotandose" banner flag (< 100 numbers remaining before rango_hasta)
# ---------------------------------------------------------------------------


@_ADMIN_HTTP_PYTESTMARK
async def test_consecutivo_actual_agotandose_true_bajo_100_restantes(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """``rango_hasta - consecutivo_actual < 100`` -> ``agotandose: true``
    (BR2), computed server-side."""
    branch_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch_uuid)
    resolucion_uuid = await _seed_resolucion_facturacion(
        pg_engine, uuid_sucursal=branch_uuid, rango_desde=1, rango_hasta=50
    )

    resp = await client.get(
        f"/api/v1/empresa/resolucion-facturacion/{resolucion_uuid}/consecutivo-actual",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["consecutivo_actual"] == 1
    assert body["restantes"] == 49
    assert body["agotandose"] is True


@_ADMIN_HTTP_PYTESTMARK
async def test_consecutivo_actual_agotandose_false_en_exactamente_100_restantes(
    pg_engine, alembic_upgrade, mint_admin_jwt, client
) -> None:
    """Exactly at the BR2 boundary (100 restantes) -> still NOT agotandose
    (the rule is "fewer than 100", i.e. strictly less than)."""
    branch_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    headers = await _actor_headers(pg_engine, mint_admin_jwt, branch_uuid=branch_uuid)
    resolucion_uuid = await _seed_resolucion_facturacion(
        pg_engine, uuid_sucursal=branch_uuid, rango_desde=1, rango_hasta=101
    )

    resp = await client.get(
        f"/api/v1/empresa/resolucion-facturacion/{resolucion_uuid}/consecutivo-actual",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["consecutivo_actual"] == 1
    assert body["restantes"] == 100
    assert body["agotandose"] is False
