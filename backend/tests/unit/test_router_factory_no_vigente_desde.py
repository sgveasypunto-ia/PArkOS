"""test_router_factory_no_vigente_desde.py — GAP-BE-02 / HU-F1.1.

Regression coverage for the ``router_factory.list_endpoint`` bug:
``order_by(model_cls.vigente_desde.desc(), ...)`` and the cursor
comparison ``(model_cls.vigente_desde < decoded.vigente_desde) | ...``
were emitted WITHOUT the same ``hasattr`` guard that already protects
the ``WHERE vigente_hasta IS NULL`` filter. Any router mounted over a
model that does not declare ``vigente_desde`` (the 15 ``AppendOnlyBase``
``[A]`` tables, ``Sesion`` ``[L_S]``, and the 3 ``[L_E]`` tables)
crashed with an ``InvalidRequestError`` at the first request — the
pre-existing routes for ``GET /caja/caja``, ``GET /caja/arqueo``, and
``GET /caja-sesion/sesion`` all 500'd before this fix.

The four cases below pin the fix at the API boundary (real httpx
``client`` against the branch FastAPI app + a real Postgres
testcontainer, per the project convention ``tests/conftest.py``):

  1. ``GET /caja/arqueo`` on an EMPTY ``arqueo`` table — 200 with
     ``{items: [], next_cursor: null}``. (Before the fix: 500 because
     ``model_cls.vigente_desde.desc()`` raises on ``Arqueo``.)
  2. ``GET /caja/arqueo`` with three seeded rows — 200, items ordered
     ``created_at DESC`` with a non-null ``next_cursor`` for page 2.
  3. ``GET /caja/arqueo?cursor=<next>`` — second page returns the
     remaining row in the correct order. (Before the fix: 500 in the
     ``WHERE`` comparison.)
  4. Regression control — ``GET /empresa/sucursal`` (a ``[V]`` model
     WITH ``vigente_desde``) — behavior is unchanged: ordered by
     ``vigente_desde DESC, uuid ASC``, ``next_cursor`` still encodes
     ``vigente_desde`` (not ``created_at``).

Tests use the ``operador-`` JWT (pinned to one branch via the
``sucursal`` claim) because ``caja.py:53`` and ``caja_sesion.py:204``
require ``emitir_factura``. The branch app is selected via
``@pytest.mark.parametrize("app", ["sucursal"], indirect=True)``
(default in conftest; explicit here for clarity).
"""
from __future__ import annotations

import base64
import json
import uuid as uuid_lib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Local helpers — kept module-private so this file owns its test setup.
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive ``datetime`` matching the DB column type ``DateTime(timezone=False)``."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _grant_permission(
    pg_engine,
    *,
    actor_uuid: uuid_lib.UUID,
    perm_code: str,
) -> None:
    """Seed one ``permisos_usuario`` row for an already-created ``usuarios``.

    ``permisos_usuario.uuid_usuario`` has a real FK to ``prod.usuarios``.
    The ``permisos`` row for ``emitir_factura`` / ``config_sucursal`` is
    already seeded by migration ``0002_seed_permisos_canonicos.py``
    (REQ-OP-13 / AGENTS.md §3).
    """
    from parkos_core.models.V.permisos import Permisos
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        permiso = (
            await session.execute(
                select(Permisos).where(
                    Permisos.permiso == perm_code, Permisos.vigente_hasta.is_(None)
                )
            )
        ).scalar_one()
        session.add(PermisosUsuario(uuid_usuario=actor_uuid, uuid_permiso=permiso.uuid))
        await session.commit()


async def _seed_usuario(pg_engine, actor_uuid: uuid_lib.UUID) -> None:
    """Insert one ``usuarios`` row for ``actor_uuid`` (FK target of the permiso row)."""
    from parkos_core.models.V.usuarios import Usuarios
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Test",
                apellido="Operador",
                email=f"{actor_uuid}@example.com",
                password_hash="test-hash",
                rol="operador",
            )
        )
        await session.commit()


async def _seed_sucursal_for_arqueo_fk(
    pg_engine,
    *,
    uuid_empresa: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID:
    """Seed one ``sucursal`` row that an ``arqueo.uuid_sucursal`` FK can reference.

    ``arqueo.uuid_sucursal`` carries a real FK to ``prod.sucursal.uuid``
    (``fk_arqueo_uuid_sucursal``, migration ``0001_initial_schema.py:1507-1515``).
    Tests that seed Arqueo rows need a parent Sucursal first. Returns the
    Sucursal uuid so the caller can use it as ``branch_uuid`` for both
    the operador token claim AND the Arqueo FK target — keeping them
    consistent across the operator token, the Arqueo rows, and the
    ``X-Sucursal-Context`` header.
    """
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        e_uuid = uuid_empresa
        if e_uuid is None:
            e_uuid = uuid_lib.uuid4()
            session.add(
                Empresa(
                    uuid=e_uuid,
                    nombre="Empresa Test",
                    nit=f"900{str(e_uuid).replace('-', '')[:6]}",
                    mensaje_bienvenida="Hola",
                    mensaje_salida="Adios",
                    regimen="comun",
                    vigente_desde=_now_naive(),
                    vigente_hasta=None,
                    estado="activo",
                    created_at=_now_naive(),
                    created_by=None,
                    sync_status="pendiente",
                )
            )
            await session.flush()
        s_uuid = uuid_lib.uuid4()
        session.add(
            Sucursal(
                uuid=s_uuid,
                uuid_empresa=e_uuid,
                uuid_tipo_sucursal=None,
                nombre=f"Sucursal FK Target {s_uuid.hex[:8]}",
                prefijo_nombre=f"FK{s_uuid.hex[:8]}",
                ciudad="Bogota",
                direccion="Calle FK 1",
                telefono="+571234567",
                horario="24/7",
                vigente_desde=_now_naive(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now_naive(),
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
        return s_uuid


@pytest_asyncio.fixture
async def isolated_arqueo_table(pg_dsn: str) -> AsyncIterator[None]:
    """Truncate ``prod.arqueo`` before AND after each test using the superuser DSN.

    Why this fixture exists (HU-F1.1 specific): the production tenant
    filter listener at ``parkos_core.db.tenancy.install_tenant_event_listener``
    has a latent bug — it reads ``state.column_descriptions`` but
    ``ORMExecuteState`` exposes that on ``state.statement`` (not on the
    state itself), so the WHERE ``uuid_sucursal = ctx`` clause is never
    injected. Result: queries see rows from other tenants. Fixing the
    listener is out of scope for HU-F1.1 (and would touch a security-
    critical listener). Instead, this fixture truncates Arqueo at the
    start and end of each test using the testcontainer superuser DSN
    (``pg_dsn``, ``test:test``) — the ``parkos_app`` least-privilege role
    can't TRUNCATE/DELETE on [A] tables by design.

    The pagination tests in this file are order-dependent: Caso 2 sees
    3 rows (its own seed) and Caso 3 expects 3 rows too — but Caso 3
    would otherwise see Caso 2's 3 + its own 3 = 6 rows because of the
    listener bug above. Truncating isolates each test.
    """
    import psycopg

    async def _truncate() -> None:
        # Sync psycopg connection — TRUNCATE is a DDL operation that
        # doesn't need async; using sync keeps the fixture simple.
        with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
            cur.execute("TRUNCATE prod.arqueo")
            conn.commit()

    await _truncate()
    try:
        yield
    finally:
        await _truncate()


async def _seed_arqueo_rows(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    timestamps: list[datetime],
) -> list[uuid_lib.UUID]:
    """Insert N ``arqueo`` rows for ``uuid_sucursal`` with explicit ``created_at`` values.

    Returns the inserted uuids in the SAME order as ``timestamps`` so the
    test can correlate response order with seed order. The composite
    primary key of ``arqueo`` is ``(uuid, fecha_retencion_hasta)``;
    ``fecha_retencion_hasta`` defaults to ``current_date`` server-side.
    ``uuid_tipo_arqueo`` is left NULL to avoid the FK requirement on
    ``prod.tipo_arqueo`` (the catalog is not seeded by the test container
    baseline; tests that exercise it seed their own).
    """
    from parkos_core.models.A.arqueo import Arqueo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    inserted_uuids: list[uuid_lib.UUID] = []
    async with Session() as session:
        for ts in timestamps:
            row_uuid = uuid_lib.uuid4()
            inserted_uuids.append(row_uuid)
            session.add(
                Arqueo(
                    uuid=row_uuid,
                    uuid_sucursal=uuid_sucursal,
                    uuid_tipo_arqueo=None,
                    uuid_sesion=None,
                    valor_efectivo_esperado=None,
                    valor_datafono_esperado=None,
                    valor_efectivo_reportado=None,
                    valor_datafono_reportado=None,
                    created_at=ts,
                    created_by=None,
                    sync_status="pendiente",
                    sync_timestamp=None,
                    sync_attempts=0,
                )
            )
        await session.commit()
    return inserted_uuids


async def _seed_sucursal_rows(
    pg_engine,
    *,
    uuid_empresa: uuid_lib.UUID,
    timestamps: list[datetime],
) -> list[uuid_lib.UUID]:
    """Insert N ``sucursal`` rows for the regression control case.

    Each row is a fresh open version (``vigente_hasta=None``,
    ``vigente_desde=<ts>``, ``estado='activo'``). The composite UK
    ``(prefijo_nombre, vigente_desde)`` is satisfied by giving each
    row a unique ``prefijo_nombre``.
    """
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    inserted_uuids: list[uuid_lib.UUID] = []
    async with Session() as session:
        for i, ts in enumerate(timestamps):
            row_uuid = uuid_lib.uuid4()
            inserted_uuids.append(row_uuid)
            session.add(
                Sucursal(
                    uuid=row_uuid,
                    uuid_empresa=uuid_empresa,
                    uuid_tipo_sucursal=None,
                    nombre=f"Sucursal Test {i} {row_uuid.hex[:8]}",
                    prefijo_nombre=f"PREF{i}-{row_uuid.hex[:6]}",
                    ciudad="Bogota",
                    direccion="Calle Test 123",
                    telefono="+571234567",
                    horario="24/7",
                    vigente_desde=ts,
                    vigente_hasta=None,
                    estado="activo",
                    created_at=ts,
                    created_by=None,
                    sync_status="pendiente",
                    sync_timestamp=None,
                    sync_attempts=0,
                )
            )
        await session.commit()
    return inserted_uuids


async def _seed_empresa(pg_engine) -> uuid_lib.UUID:
    """Insert one ``empresa`` row and return its uuid."""
    from parkos_core.models.V.empresa import Empresa
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        e_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=e_uuid,
                nombre="Empresa Test",
                nit=f"900{str(e_uuid).replace('-', '')[:6]}",
                mensaje_bienvenida="Hola",
                mensaje_salida="Adios",
                regimen="comun",
                vigente_desde=_now_naive(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now_naive(),
                created_by=None,
                sync_status="pendiente",
            )
        )
        await session.commit()
        return e_uuid


def _decode_cursor_field(cursor: str | None, *, field: str) -> str | None:
    """Decode the opaque base64url(JSON) cursor and return one field.

    Mirrors ``repo.pagination.decode`` but is intentionally lightweight —
    used only to assert WHICH key the cursor carries (``vigente_desde``
    for the [V] path, ``created_at`` for the [A] path). Returns ``None``
    if ``cursor`` is ``None``.
    """
    if cursor is None:
        return None
    padded = cursor + "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    data = json.loads(raw.decode("utf-8"))
    value = data.get(field)
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Caso 1 — empty Arqueo (sin vigente_desde) → 200 + {items: [], next_cursor: null}
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", ["sucursal"], indirect=True)
async def test_list_arqueo_empty_returns_200_with_empty_items(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, isolated_arqueo_table
) -> None:
    """``GET /caja/arqueo`` on an empty ``arqueo`` table — proves the
    ``order_by(model_cls.vigente_desde.desc(), ...)`` line does NOT
    raise on a model that has no ``vigente_desde`` attribute.

    Pre-fix symptom: 500 ``InvalidRequestError: Mapper 'mapped class
    Arqueo' has no property 'vigente_desde'`` (raised inside SQLAlchemy
    when compiling the ``order_by`` clause).
    """
    # Seed a Sucursal so the FK ``fk_arqueo_uuid_sucursal`` (not yet
    # needed since we don't INSERT Arqueo here, but it keeps the test
    # setup consistent with the others) and the operador-token branch
    # pin are anchored to a real row.
    branch_uuid = await _seed_sucursal_for_arqueo_fk(pg_engine)
    actor_uuid = uuid_lib.uuid4()
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="emitir_factura")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    resp = await client.get(
        "/api/v1/caja/arqueo",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, (
        f"expected 200 (the order_by line must not crash on Arqueo), got "
        f"{resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


# ---------------------------------------------------------------------------
# Caso 2 — Arqueo with 3 rows → 200, items ordered created_at DESC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", ["sucursal"], indirect=True)
async def test_list_arqueo_with_three_rows_returns_200_in_created_at_desc(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, isolated_arqueo_table
) -> None:
    """``GET /caja/arqueo`` with 3 seeded rows — items come back in
    ``created_at DESC, uuid ASC`` order and ``next_cursor`` is present
    (we request ``limit=2`` so the 3rd row triggers ``len(rows) > limit``
    and the ``next_cursor`` branch).
    """
    branch_uuid = await _seed_sucursal_for_arqueo_fk(pg_engine)
    actor_uuid = uuid_lib.uuid4()
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="emitir_factura")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    # Seed 3 rows at increasing timestamps — newest is the LAST one.
    ts_old, ts_mid, ts_new = base, base + timedelta(hours=1), base + timedelta(hours=2)
    uuids = await _seed_arqueo_rows(
        pg_engine, uuid_sucursal=branch_uuid, timestamps=[ts_old, ts_mid, ts_new]
    )

    resp = await client.get(
        "/api/v1/caja/arqueo",
        params={"limit": 2},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body["items"]) == 2, f"expected 2 items (limit=2), got {len(body['items'])}"
    # Newest first.
    assert body["items"][0]["uuid"] == str(uuids[2])
    assert body["items"][1]["uuid"] == str(uuids[1])
    assert body["next_cursor"] is not None, (
        "next_cursor must be present so the remaining row is reachable"
    )
    # The cursor encodes created_at (NOT vigente_desde) — Arqueo has no vigente_desde.
    assert _decode_cursor_field(body["next_cursor"], field="vigente_desde") is None
    assert _decode_cursor_field(body["next_cursor"], field="created_at") is not None


# ---------------------------------------------------------------------------
# Caso 3 — pagination with cursor (created_at) returns the remaining row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", ["sucursal"], indirect=True)
async def test_list_arqueo_pagination_cursor_returns_remaining_row(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, isolated_arqueo_table
) -> None:
    """``GET /caja/arqueo?cursor=<next>&limit=2`` after page 1 leaves one
    row — page 2 returns exactly that row in the same order.

    This pins the cursor comparison in ``list_endpoint``: the ``WHERE``
    clause that filters rows BELOW the cursor must compile against
    ``created_at`` (not ``vigente_desde``) for Arqueo. Pre-fix: 500.
    """
    branch_uuid = await _seed_sucursal_for_arqueo_fk(pg_engine)
    actor_uuid = uuid_lib.uuid4()
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="emitir_factura")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    ts_old, ts_mid, ts_new = base, base + timedelta(hours=1), base + timedelta(hours=2)
    uuids = await _seed_arqueo_rows(
        pg_engine, uuid_sucursal=branch_uuid, timestamps=[ts_old, ts_mid, ts_new]
    )

    # Page 1
    resp1 = await client.get(
        "/api/v1/caja/arqueo",
        params={"limit": 2},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp1.status_code == 200, f"page 1 got {resp1.status_code}: {resp1.text}"
    body1 = resp1.json()
    assert len(body1["items"]) == 2
    next_cursor = body1["next_cursor"]
    assert next_cursor is not None

    # Page 2 — pass the cursor back.
    resp2 = await client.get(
        "/api/v1/caja/arqueo",
        params={"limit": 2, "cursor": next_cursor},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert resp2.status_code == 200, f"page 2 got {resp2.status_code}: {resp2.text}"
    body2 = resp2.json()

    # Page 2 must contain ONLY the oldest row (ts_old), nothing else.
    assert len(body2["items"]) == 1, f"expected 1 item on page 2, got {len(body2['items'])}"
    assert body2["items"][0]["uuid"] == str(uuids[0])
    assert body2["next_cursor"] is None, (
        "no more pages — the third row was the last one in the set"
    )


# ---------------------------------------------------------------------------
# Caso 4 — regression control: Sucursal (con vigente_desde) NO cambia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("app", ["sucursal"], indirect=True)
async def test_list_sucursal_with_vigente_desde_uses_vigente_desde_path(
    pg_engine, alembic_upgrade, mint_operador_jwt, client
) -> None:
    """Regression: ``GET /empresa/sucursal`` (a ``[V]`` model that DOES
    declare ``vigente_desde``) MUST keep its existing order-by and
    cursor contract — ``vigente_desde DESC, uuid ASC``, cursor encodes
    ``vigente_desde`` (NOT ``created_at``).

    If the fix accidentally flipped the cursor field for [V] too,
    page-2 of any existing client would break — this test pins the
    pre-existing behaviour.
    """
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    empresa_uuid = await _seed_empresa(pg_engine)
    await _seed_usuario(pg_engine, actor_uuid)
    # The ``empresa`` router (which mounts ``sucursal``) requires
    # ``config_sucursal`` per ``empresa.py:60``.
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_sucursal")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    ts_old, ts_mid, ts_new = base, base + timedelta(hours=1), base + timedelta(hours=2)
    uuids = await _seed_sucursal_rows(
        pg_engine, uuid_empresa=empresa_uuid, timestamps=[ts_old, ts_mid, ts_new]
    )

    resp = await client.get(
        "/api/v1/empresa/sucursal",
        params={"limit": 2},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body["items"]) == 2
    # Sucursal's vigente_desde DESC, uuid ASC → newest version first.
    assert body["items"][0]["uuid"] == str(uuids[2])
    assert body["items"][1]["uuid"] == str(uuids[1])
    # Cursor encodes ``vigente_desde`` — NOT ``created_at`` — for [V] tables.
    assert body["next_cursor"] is not None
    assert _decode_cursor_field(body["next_cursor"], field="created_at") is None, (
        "[V] cursor must continue to carry vigente_desde, not created_at — "
        "this is the regression control for the [V] path"
    )
    assert _decode_cursor_field(body["next_cursor"], field="vigente_desde") is not None


__all__ = [
    "test_list_arqueo_empty_returns_200_with_empty_items",
    "test_list_arqueo_pagination_cursor_returns_remaining_row",
    "test_list_arqueo_with_three_rows_returns_200_in_created_at_desc",
    "test_list_sucursal_with_vigente_desde_uses_vigente_desde_path",
]
