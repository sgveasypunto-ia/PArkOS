"""test_cantidad_vehiculos_sucursal_e2e.py — PR-C end-to-end coverage of the
write paths that ``make_router`` mounts for ``cantidad_vehiculos_sucursal``.

What this file pins
-------------------
``backend/.../api/empresa.py::_mount_empresa`` mounts the same five-route
factory surface (``GET list``, ``GET /{uuid}``, ``GET /{uuid}/history``,
``POST``, ``PUT /{uuid}``) that ``test_tarifas_sucursal_e2e.py`` covers
for ``tarifas_sucursal``. The contract is identical; the schema differs
in two ways:

  * three business columns (sucursal, tipo_vehiculo, ``cantidad INTEGER``)
    instead of five; ``cantidad`` is the only ``Numeric``/``Integer``
    payload field this resource exposes;
  * UK01 is ``(uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)`` — one
    fewer column than ``tarifas_sucursal``.

The same gap surfaced in T3 of the tarifas file applies here too: PUT
issues a fresh UUID on close+insert, and the factory's ``GET /{uuid}/
history`` does NOT walk the version chain by business identity. PR-C
pins the same shape.

What the four cases pin
-----------------------
* C1 POST 201 creates a row with ``cantidad=N``.
* C2 POST without ``config_cupos`` → 403 (lock-in of 0059).
* C3 PUT closes the current row and inserts a new version with ``cantidad=N+1``.
  ``GET /{old_uuid}`` → 404; ``GET /{new_uuid}`` → 200 with the new
  ``cantidad``; ``GET /{old_uuid}/history`` → list of one closed version.
* C4 Schema UK01 invariant: two INSERTs with the same business key +
  same ``vigente_desde`` raise ``UniqueViolation``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest

# Module-level parametrize would force every test (including the UK01 ones
# that don't touch the HTTP client) to depend on the ``app`` fixture.
# Only the three HTTP-driven cases pin the ``sucursal`` app — apply the
# parametrize on each of those individually.
_HTTP_PYTESTMARK = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Local helpers — kept local so this file does not couple with the tarifas
# file's helpers through a shared conftest mutation.
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _ensure_permiso(pg_engine, *, perm_code: str) -> uuid_lib.UUID:
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
        from parkos_core.models.V.permisos import Permisos as _P

        row = _P(
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
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa PR-C Cupos",
                nit=f"902{empresa_uuid.hex[:6]}",
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
                nombre=f"Sucursal Cupos {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"D{uuid_sucursal.hex[:6]}",
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


async def _truncate_cupos(pg_dsn: str) -> None:
    """Truncate ``prod.cantidad_vehiculos_sucursal``."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.cantidad_vehiculos_sucursal")
        conn.commit()


def _payload(*, uuid_sucursal: uuid_lib.UUID, cantidad: int = 50) -> dict[str, object]:
    """Minimal valid POST payload.

    ``uuid_tipo_vehiculo`` is nullable in the schema and the FK check is
    skipped when NULL — the test does not need to seed catalog parents
    (mirrors HU-F1.4's choice).
    """
    return {
        "uuid_sucursal": str(uuid_sucursal),
        "uuid_tipo_vehiculo": None,
        "cantidad": cantidad,
    }


# ---------------------------------------------------------------------------
# C1 — POST 201 creates a row with cantidad=N, vigente_hasta IS NULL
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_post_cantidad_crea_fila_vigente(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    await _truncate_cupos(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_cupos")
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_payload(uuid_sucursal=branch_uuid, cantidad=50),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["vigente_hasta"] is None, "POST must open a row (vigente_hasta IS NULL)"
    assert body["estado"] == "activo"
    assert body["uuid_sucursal"] == str(branch_uuid)
    assert body["cantidad"] == 50


# ---------------------------------------------------------------------------
# C2 — auth gate: admin WITHOUT ``config_cupos`` → 403
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_post_cantidad_sin_permiso_devuelve_403(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    await _truncate_cupos(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    # Deliberately NO _grant_permission call.
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    resp = await client.post(
        "/api/v1/empresa/cantidad-vehiculos-sucursal",
        json=_payload(uuid_sucursal=branch_uuid),
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp.status_code == 403, f"got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# C3 — PUT closes the current row and inserts a new version with cantidad=N+1
# ---------------------------------------------------------------------------


@_HTTP_PYTESTMARK
async def test_put_cantidad_cierra_version_y_abre_nueva(
    pg_engine, alembic_upgrade, mint_admin_jwt, client, pg_dsn
) -> None:
    await _truncate_cupos(pg_dsn)
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
        json=_payload(uuid_sucursal=branch_uuid, cantidad=50),
        headers=headers,
    )
    assert post.status_code == 201
    original_uuid = post.json()["uuid"]

    # PUT bumps cantidad 50 → 75. Close+insert, not in-place update.
    new_payload = _payload(uuid_sucursal=branch_uuid, cantidad=75)
    put = await client.put(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{original_uuid}",
        json=new_payload,
        headers=headers,
    )
    assert put.status_code == 200, f"got {put.status_code}: {put.text}"
    new_uuid = put.json()["uuid"]
    assert new_uuid != original_uuid, "PUT must close+insert, NOT mutate the row in place"

    # Old UUID is closed → 404 via ``current_version`` (vigente_hasta IS
    # NULL filter excludes it).
    closed_get = await client.get(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{original_uuid}",
        headers=headers,
    )
    assert closed_get.status_code == 404, (
        f"GET on a closed uuid must return 404; got {closed_get.status_code}: {closed_get.text}"
    )

    # New UUID is open → 200 with the new cantidad.
    open_get = await client.get(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{new_uuid}",
        headers=headers,
    )
    assert open_get.status_code == 200, f"got {open_get.status_code}: {open_get.text}"
    assert open_get.json()["cantidad"] == 75
    assert open_get.json()["vigente_hasta"] is None
    assert open_get.json()["estado"] == "activo"

    # History of the old uuid lists ONLY the closed version.
    history = await client.get(
        f"/api/v1/empresa/cantidad-vehiculos-sucursal/{original_uuid}/history",
        headers=headers,
    )
    assert history.status_code == 200, f"got {history.status_code}: {history.text}"
    versions = history.json()
    assert len(versions) == 1, (
        f"history of the closed uuid must list 1 version; got {len(versions)}"
    )
    assert versions[0]["cantidad"] == 50
    assert versions[0]["vigente_hasta"] is not None
    assert versions[0]["estado"] == "inactivo"


# ---------------------------------------------------------------------------
# C4 — Schema UK01 invariant
# ---------------------------------------------------------------------------


async def test_uk01_rechaza_dos_filas_con_mismo_vigente_desde(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """Two INSERTs with identical UK01 columns must violate the constraint.

    UK01 is ``(uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)``. Mirrors
    ``test_tarifas_sucursal_e2e.py::test_uk01_rechaza_...`` for the other
    resource.
    """
    await _truncate_cupos(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    fixed_vigente_desde = _now_naive()

    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO prod.cantidad_vehiculos_sucursal "
            "(uuid, uuid_sucursal, uuid_tipo_vehiculo, cantidad, "
            " vigente_desde, vigente_hasta, estado, "
            " created_at, created_by, sync_status, sync_attempts) "
            "VALUES (gen_random_uuid(), %s, NULL, 50, "
            "        %s, NULL, 'activo', %s, NULL, 'sincronizado', 0)",
            (branch_uuid, fixed_vigente_desde, _now_naive()),
        )
        conn.commit()

        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO prod.cantidad_vehiculos_sucursal "
                "(uuid, uuid_sucursal, uuid_tipo_vehiculo, cantidad, "
                " vigente_desde, vigente_hasta, estado, "
                " created_at, created_by, sync_status, sync_attempts) "
                "VALUES (gen_random_uuid(), %s, NULL, 75, "
                "        %s, NULL, 'activo', %s, NULL, 'sincronizado', 0)",
                (branch_uuid, fixed_vigente_desde, _now_naive()),
            )
        conn.rollback()
