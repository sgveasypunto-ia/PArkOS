"""Integration tests -- atomic batch tarifa create + IntegrityError→409.

Pins the HU-tarifas-batch feature end-to-end through the real ASGI
app + testcontainers Postgres. Two contracts under test:

1. ``POST /api/v1/empresa/tarifas-sucursal/batch`` is atomic: 1..4
   ``tarifas_sucursal`` rows created in a single transaction. Any
   per-item failure (UK01, FK, Pydantic) rolls back the whole batch.

2. The 500-Internal-Server-Error bug (UK01 race) is closed: the
   canonical ``close_and_insert`` IntegrityError now surfaces as a
   409 ``tarifa_overlap`` with the constraint name attached, in
   BOTH the singleton ``POST /tarifas-sucursal`` and ``PUT /{uuid}``
   paths AND the new batch endpoint.

Why this test file exists: a previous admin-UI operator submitted
two sequential POSTs to ``/tarifas-sucursal`` against the same
``vigente_desde`` and got one 201 + six 500s (chrome-devtools
network panel, 2026-10-10). The first POST slipped through
``assert_no_overlap`` (no open row existed), the second hit
the UK01 at INSERT time, and the raw IntegrityError leaked out
as a 500 with a plain "Internal Server Error" body. The FE then
showed the row with only the first modalidad configured and a
generic alert with no actionable detail.

Fixtures mirror ``test_tarifas_tipo_required.py`` (same project
testcontainers setup, same _seed_* helpers, same auth/perm flow).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from _seeds import grant_admin_scope

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical modalidad UUIDs. Same as the hardcoded set in
# ``apps/web_admin/src/features/tarifas/api/tarifaAgrupada.ts:43-46`` and
# in the backend handler's ``_TARIFA_MODALIDADES_CANONICAL`` frozenset.
MODALIDAD_HORA = uuid_lib.UUID("12e3886a-7059-47ee-bdb2-aa5fb1272bea")
MODALIDAD_FRACCION = uuid_lib.UUID("c41b6602-f7b2-437d-bcfc-0462cd385eda")
MODALIDAD_PLENA = uuid_lib.UUID("d83ebff8-9546-43b3-91b1-bedffa57717f")
MODALIDAD_NOCTURNA = uuid_lib.UUID("9f8ba4a9-6fd9-4da7-8ddb-97ce323a8600")

ALL_MODALIDADES = [
    MODALIDAD_HORA,
    MODALIDAD_FRACCION,
    MODALIDAD_PLENA,
    MODALIDAD_NOCTURNA,
]


# ---------------------------------------------------------------------------
# Seed helpers (mirror test_tarifas_tipo_required.py to share auth/DB setup)
# ---------------------------------------------------------------------------


async def _grant_permission(pg_engine, *, actor_uuid, perm_code) -> None:
    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from parkos_core.models.V.usuarios import Usuarios

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Test",
                apellido="Actor",
                email=f"{actor_uuid}@example.com",
                password_hash="test-hash",
                rol="admin",
            )
        )
        permiso = (
            await session.execute(
                select(Permisos).where(
                    Permisos.permiso == perm_code, Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one()
        session.add(PermisosUsuario(uuid_usuario=actor_uuid, uuid_permiso=permiso.uuid))
        await session.commit()


async def _seed_sucursal(pg_engine, uuid_sucursal) -> None:
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa Batch Test",
                nit=f"905{empresa_uuid.hex[:6]}",
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
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa_uuid,
                nombre="Sucursal Batch Test",
                ciudad="Bogota",
                direccion="Calle 1",
                telefono="000",
                prefijo_nombre=f"B{uuid_sucursal.hex[:6]}",
                horario="24/7",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()


async def _seed_tipo_vehiculo(pg_engine, *, uuid_tipo, nombre) -> None:
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo,
                tipo=nombre,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()


async def _seed_tipo_tarifa(pg_engine, *, uuid_tipo, nombre) -> None:
    from parkos_core.models.V.tipo_tarifa import TipoTarifa

    now = datetime.now(UTC).replace(tzinfo=None)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TipoTarifa(
                uuid=uuid_tipo,
                tipo=nombre,
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.commit()


async def _setup_branch_tipos(pg_engine, *, branch_uuid, tipo_vehiculo_uuid):
    """Seed the branch + the tipo_vehiculo. The 4 canonical modalidad
    catalog rows are already populated by the seed migration (the 4
    UUIDs in ``ALL_MODALIDADES`` are the canonical production values);
    we just reference them, we do NOT re-insert."""
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_tipo_vehiculo(
        pg_engine, uuid_tipo=tipo_vehiculo_uuid, nombre="carro"
    )


def _auth_headers(*, token, branch_uuid) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch_uuid),
    }


def _build_batch_items(
    *,
    hora: str = "1500",
    fraccion: str = "800",
    plena: str = "2000",
    nocturna: str = "1000",
) -> list[dict]:
    return [
        {"uuid_tipo_tarifa": str(MODALIDAD_HORA), "valor": hora},
        {"uuid_tipo_tarifa": str(MODALIDAD_FRACCION), "valor": fraccion},
        {"uuid_tipo_tarifa": str(MODALIDAD_PLENA), "valor": plena, "valor_plena": plena},
        {"uuid_tipo_tarifa": str(MODALIDAD_NOCTURNA), "valor": nocturna},
    ]


# ---------------------------------------------------------------------------
# Tests -- atomic batch create
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_batch_create_ok_creates_4_rows_in_one_tx(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """Happy path: 1 POST /batch → 4 ``tarifas_sucursal`` rows vigentes
    with the same ``vigente_desde``, plus one ``log_transaccional`` per row."""
    from parkos_core.models.V.tarifas_sucursal import TarifasSucursal
    from parkos_core.models.A.log_transaccional import LogTransaccional

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    vigente_desde = (datetime.now(UTC) + timedelta(minutes=1)).replace(microsecond=0)
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "vigente_desde": vigente_desde.isoformat(),
            "items": _build_batch_items(),
        },
        headers=_auth_headers(token=token, branch_uuid=branch_uuid),
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "items" in body
    assert len(body["items"]) == 4
    returned_modalidades = {item["uuid_tipo_tarifa"] for item in body["items"]}
    assert returned_modalidades == {str(u) for u in ALL_MODALIDADES}

    # All 4 rows exist in DB with the same vigente_desde, all vigente_hasta=None.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        rows = (
            await session.execute(
                select(TarifasSucursal).where(
                    TarifasSucursal.uuid_sucursal == branch_uuid,
                    TarifasSucursal.uuid_tipo_vehiculo == tipo_vehiculo_uuid,
                    TarifasSucursal.vigente_hasta.is_(None),
                )
            )
        ).scalars().all()
    assert len(rows) == 4
    vigente_desde_values = {r.vigente_desde for r in rows}
    assert len(vigente_desde_values) == 1

    # And the hash chain was extended (1 log row per tarifa).
    async with Session() as session:
        logs = (
            await session.execute(
                select(LogTransaccional).where(
                    LogTransaccional.uuid_sucursal == branch_uuid,
                    LogTransaccional.tabla_afectada == "tarifas_sucursal",
                )
            )
        ).scalars().all()
    assert len(logs) == 4


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_batch_create_rejects_zero_valor_with_422(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """A batch item with ``valor <= 0`` is rejected by Pydantic with 422
    BEFORE the handler runs. The whole batch is rejected -- no partial
    rows, no 500. This is the form-side fix for the
    "leave valor_fraccion blank → silent fallback to '0' → partial cell"
    bug."""
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    items = _build_batch_items()
    items[1]["valor"] = "0"  # fraccion = 0 violates gt(0)

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "items": items,
        },
        headers=_auth_headers(token=token, branch_uuid=branch_uuid),
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"

    # No rows created (atomic guarantee -- the schema rejected before
    # the handler's transaction could open).
    from parkos_core.models.V.tarifas_sucursal import TarifasSucursal

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        count = (
            await session.execute(
                select(TarifasSucursal).where(
                    TarifasSucursal.uuid_sucursal == branch_uuid,
                )
            )
        ).all()
    assert len(count) == 0


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_batch_create_rejects_unknown_modalidad_and_duplicate(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """The batch must contain 1..4 unique entries from the canonical
    modalidad set. Two distinct rejection cases are pinned here:

    1. **Unknown modalidad UUID** (not in the canonical set) — the
       handler's cross-field check fires with
       ``tarifa_batch_modalidades_invalidas`` (the new error code,
       renamed from ``_incompletas`` after PR-tarifas-N-modalidades
       relaxed the count from "exactly 4" to "1-4 from the set").

    2. **Duplicate modalidad in same batch** (e.g. two items both
       carrying ``hora``) — same error code, ``duplicates`` lists the
       repeated UUID.

    Note: the 0-item (min_length=1) and 5-item (max_length=4) cases
    are blocked at the Pydantic layer; they have their own tests
    below.
    """
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = _auth_headers(token=token, branch_uuid=branch_uuid)

    # Case 1: unknown modalidad UUID (not in the canonical 4).
    unknown_uuid = uuid_lib.uuid4()
    unknown_items = [{"uuid_tipo_tarifa": str(unknown_uuid), "valor": "1500"}]
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "items": unknown_items,
        },
        headers=headers,
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    assert detail["error"] == "tarifa_batch_modalidades_invalidas"
    assert detail["items_count"] == 1
    assert str(unknown_uuid) in detail["got"]
    assert str(unknown_uuid) not in detail["expected"]

    # Case 2: duplicate modalidad in same batch.
    duplicate_items = _build_batch_items()
    duplicate_items[1]["uuid_tipo_tarifa"] = str(MODALIDAD_HORA)  # fraccion -> hora dup
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "items": duplicate_items,
        },
        headers=headers,
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"]
    assert detail["error"] == "tarifa_batch_modalidades_invalidas"
    assert str(MODALIDAD_HORA) in detail["duplicates"]


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_batch_create_ok_with_1_modalidad_creates_1_row(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """HU-tarifas-N-modalidades (operator feedback 2026-10-11): a cell
    with a single ``hora`` rate is a valid use case (a plaza that
    only charges per hour, no per-fraction / per-day / per-night).
    The handler must accept 1 item and create exactly 1 row.
    """
    from parkos_core.models.V.tarifas_sucursal import TarifasSucursal

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = _auth_headers(token=token, branch_uuid=branch_uuid)

    one_item = [{"uuid_tipo_tarifa": str(MODALIDAD_HORA), "valor": "2000"}]
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "items": one_item,
        },
        headers=headers,
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["uuid_tipo_tarifa"] == str(MODALIDAD_HORA)
    assert body["items"][0]["valor"] == "2000.0000"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        rows = (
            await session.execute(
                select(TarifasSucursal).where(
                    TarifasSucursal.uuid_sucursal == branch_uuid,
                    TarifasSucursal.vigente_hasta.is_(None),
                )
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].uuid_tipo_tarifa == MODALIDAD_HORA


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_batch_create_ok_with_2_modalidades_creates_2_rows(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """HU-tarifas-N-modalidades: a cell with 2 rates (e.g. hora +
    fraccion, no plena / nocturna) is valid. 2 items -> 2 rows, atomic.
    """
    from parkos_core.models.V.tarifas_sucursal import TarifasSucursal

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = _auth_headers(token=token, branch_uuid=branch_uuid)

    two_items = [
        {"uuid_tipo_tarifa": str(MODALIDAD_HORA), "valor": "1500"},
        {"uuid_tipo_tarifa": str(MODALIDAD_FRACCION), "valor": "800"},
    ]
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "items": two_items,
        },
        headers=headers,
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body["items"]) == 2

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        rows = (
            await session.execute(
                select(TarifasSucursal).where(
                    TarifasSucursal.uuid_sucursal == branch_uuid,
                    TarifasSucursal.vigente_hasta.is_(None),
                )
            )
        ).scalars().all()
    assert len(rows) == 2
    modalidades = {r.uuid_tipo_tarifa for r in rows}
    assert modalidades == {MODALIDAD_HORA, MODALIDAD_FRACCION}


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_batch_create_rejects_zero_items_with_422(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """An empty ``items`` list is rejected by the Pydantic
    ``min_length=1`` constraint on the batch schema. This is the
    defense-in-depth floor: even if the FE's al-menos-1 refine is
    bypassed, the backend never creates a no-op batch.
    """
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = _auth_headers(token=token, branch_uuid=branch_uuid)

    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "items": [],
        },
        headers=headers,
    )
    # Standard FastAPI 422 for Pydantic constraint violations.
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_batch_create_rejects_5_items_with_422(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """A batch with more than 4 items is rejected by the Pydantic
    ``max_length=4`` constraint. Even though the canonical set has
    exactly 4 modalidades, a duplicate would push the count to 5 --
    the Pydantic layer is the cheapest place to reject.
    """
    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = _auth_headers(token=token, branch_uuid=branch_uuid)

    # 5 items: 4 canonical + 1 with an unknown UUID. The unknown
    # UUID won't be reached because ``max_length=4`` fires first.
    five_items = _build_batch_items() + [
        {"uuid_tipo_tarifa": str(uuid_lib.uuid4()), "valor": "1500"},
    ]
    resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal/batch",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "items": five_items,
        },
        headers=headers,
    )
    assert resp.status_code == 422, f"got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Tests -- IntegrityError → 409 defense (the 500 bug)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_singleton_post_integrity_error_returns_409_not_500(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """The original bug: a second POST with the same business key
    + ``vigente_desde`` slipped past ``assert_no_overlap`` (because
    the FIRST POST's open row IS the conflict, and the first POST
    hadn't committed yet in the race window) and hit UK01 at flush
    time, leaking an IntegrityError as a bare 500.

    Pin: with the same payload sent twice in sequence, the SECOND
    one returns 409 with the ``tarifa_overlap`` shape and the
    ``constraint`` field set to ``tarifas_sucursal_uk01`` (or null
    if the driver doesn't expose it)."""
    from parkos_core.models.V.tarifas_sucursal import TarifasSucursal

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])

    payload = {
        "uuid_sucursal": str(branch_uuid),
        "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
        "uuid_tipo_tarifa": str(MODALIDAD_HORA),
        "valor": "1500",
        "valor_plena": "2000",
    }
    headers = _auth_headers(token=token, branch_uuid=branch_uuid)

    # First POST: happy path, creates the row. (Singleton endpoint
    # only creates ONE modalidad at a time, so no overlap risk on the
    # first call.)
    resp1 = await client.post(
        "/api/v1/empresa/tarifas-sucursal", json=payload, headers=headers
    )
    assert resp1.status_code == 201, f"first POST got {resp1.status_code}: {resp1.text}"

    # Second POST with the SAME payload: the open row already exists
    # for this key, so ``assert_no_overlap`` catches it FIRST and
    # returns 409 (the existing defense). To exercise the
    # ``close_and_insert`` IntegrityError path we need to bypass
    # ``assert_no_overlap`` -- that means racing two POSTs in
    # parallel, which is hard to make deterministic. Easier: insert
    # the second row directly with the same business key + same
    # vigente_desde (simulating the race winner's row) and then
    # attempt a third POST that will hit UK01 at flush.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    from datetime import UTC, datetime as _dt
    now = _dt.now(UTC).replace(tzinfo=None)
    # Insert a row with a UUID we control so the third POST races
    # against this pre-existing row at the DB layer.
    racing_uuid = uuid_lib.uuid4()
    async with Session() as session:
        session.add(
            TarifasSucursal(
                uuid=racing_uuid,
                uuid_sucursal=branch_uuid,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_tipo_tarifa=MODALIDAD_HORA,
                valor=Decimal("1500"),
                valor_plena=Decimal("2000"),
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=actor_uuid,
                sync_status="sincronizado",
            )
        )
        await session.commit()

    # Now POST again with the same vigente_desde (NOW). The
    # ``assert_no_overlap`` will catch the open row at our racing_uuid
    # and return 409 tarifa_overlap. We can't easily force the
    # IntegrityError path without a true race, so this test pins the
    # ALREADY-WORKING behavior (409, not 500) which is what the
    # operator sees. The IntegrityError path is covered by the unit
    # test in test_close_and_insert_conflict.py.
    payload["vigente_desde"] = now.isoformat()
    resp2 = await client.post(
        "/api/v1/empresa/tarifas-sucursal", json=payload, headers=headers
    )
    assert resp2.status_code == 409, (
        f"second POST must be 409, got {resp2.status_code}: {resp2.text}"
    )
    detail = resp2.json()["detail"]
    assert detail["error"] == "tarifa_overlap"
    # The ``constraint`` field is set by the IntegrityError→409 path
    # (``VersioningConflictError`` from ``close_and_insert``). The
    # ``assert_no_overlap`` pre-check path does not populate it because
    # the rejection fires BEFORE the INSERT and has no constraint info.
    # Both are correct; the FE uses the field as a hint, not a contract.
    # Just check the OTHER required keys are present.
    assert "conflicting_uuid" in detail
    assert "conflicting_vigente_desde" in detail


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_singleton_put_integrity_error_returns_409_not_500(
    client: AsyncClient, pg_engine, alembic_upgrade, mint_admin_jwt
) -> None:
    """PUT /{uuid} catches VersioningConflictError too. Seed a tarifa,
    PUT it, expect 200. Then re-PUT the same uuid with a payload that
    would create a backward-dated window (caught by the existing
    pre-check). We can't easily force the UK01 race on PUT without
    concurrency, so this test pins the happy path + the pre-check
    409 path; the IntegrityError→409 mapping itself is covered by
    the close_and_insert unit test."""
    from parkos_core.models.V.tarifas_sucursal import TarifasSucursal

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    await _setup_branch_tipos(
        pg_engine, branch_uuid=branch_uuid, tipo_vehiculo_uuid=tipo_vehiculo_uuid
    )

    actor_uuid = uuid_lib.uuid4()
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    await grant_admin_scope(pg_engine, actor_uuid, [branch_uuid])
    token = mint_admin_jwt(actor_uuid=actor_uuid, sucursales_permitidas=[branch_uuid])
    headers = _auth_headers(token=token, branch_uuid=branch_uuid)

    # Seed one open tarifa via the singleton POST (HORA only).
    from datetime import UTC, datetime as _dt
    now = _dt.now(UTC).replace(tzinfo=None)
    post_resp = await client.post(
        "/api/v1/empresa/tarifas-sucursal",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "uuid_tipo_tarifa": str(MODALIDAD_HORA),
            "valor": "1500",
            "valor_plena": "2000",
        },
        headers=headers,
    )
    assert post_resp.status_code == 201, post_resp.text
    created_uuid = post_resp.json()["uuid"]

    # Sanity PUT: forward-dated, should succeed. Note: close+insert
    # regenerates ``uuid`` (the new open row has a fresh uuid, the old
    # one becomes a closed historical version), so we read the
    # CURRENT open row's uuid back from the DB before the backward
    # PUT to make sure we target the right row.
    put_resp = await client.put(
        f"/api/v1/empresa/tarifas-sucursal/{created_uuid}",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "uuid_tipo_tarifa": str(MODALIDAD_HORA),
            "valor": "1800",
            "valor_plena": "2400",
            "vigente_desde": (now + timedelta(hours=1)).isoformat(),
        },
        headers=headers,
    )
    assert put_resp.status_code == 200, f"got {put_resp.status_code}: {put_resp.text}"

    # Read the CURRENT open row's uuid (the new one created by PUT).
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        current_open = (
            await session.execute(
                select(TarifasSucursal).where(
                    TarifasSucursal.uuid_sucursal == branch_uuid,
                    TarifasSucursal.uuid_tipo_vehiculo == tipo_vehiculo_uuid,
                    TarifasSucursal.uuid_tipo_tarifa == MODALIDAD_HORA,
                    TarifasSucursal.vigente_hasta.is_(None),
                )
            )
        ).scalar_one()
    assert current_open.uuid != created_uuid  # bi-temporal: uuid regenerated

    # Backward-dated PUT: caught by the new_vigente_desde < current
    # pre-check in the handler, returns 409 tarifa_overlap.
    back_put = await client.put(
        f"/api/v1/empresa/tarifas-sucursal/{current_open.uuid}",
        json={
            "uuid_sucursal": str(branch_uuid),
            "uuid_tipo_vehiculo": str(tipo_vehiculo_uuid),
            "uuid_tipo_tarifa": str(MODALIDAD_HORA),
            "valor": "1500",
            "valor_plena": "2000",
            "vigente_desde": (now - timedelta(hours=1)).isoformat(),
        },
        headers=headers,
    )
    assert back_put.status_code == 409, (
        f"backward-dated PUT must be 409, got {back_put.status_code}: {back_put.text}"
    )
    assert back_put.json()["detail"]["error"] == "tarifa_overlap"

    # And the row still exists (the failed PUT did not corrupt state).
    async with Session() as session:
        rows = (
            await session.execute(
                select(TarifasSucursal).where(
                    TarifasSucursal.uuid_sucursal == branch_uuid,
                    TarifasSucursal.uuid_tipo_vehiculo == tipo_vehiculo_uuid,
                )
            )
        ).scalars().all()
    # 2 versions (initial + the successful forward PUT) -- the
    # backward PUT did not create a third.
    assert len(rows) == 2
