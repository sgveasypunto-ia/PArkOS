"""test_tarifas_vigente_en.py — HU-F1.4 / REQ-OPS-017..021.

TDD RED → GREEN for the dedicated ``GET /empresa/tarifas-sucursal``
handler that adds the optional ``vigente_en`` query param. The handler
applies the canonical bi-temporal predicate
``vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta
> :vigente_en) AND estado = 'activo'`` and MUST coexist with the factory
(``router_factory.make_router``) registered for the other resources.

These are integration-style tests under ``tests/unit/`` because they need
a real ``pg_engine`` and a real ASGI ``httpx.AsyncClient`` (the
``extra='forbid'`` on ``TarifasSucursalFilter``, the cursor pagination
and the bi-temporal predicate are all behaviour that only Postgres can
pin — SQLite would silently accept any predicate shape and let the bug
go unnoticed). Same precedent as
``tests/unit/test_router_factory_no_vigente_desde.py`` (HU-F1.1
GAP-BE-02): unit-test folder, integration-test body.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import pytest
from parkos_core.models.V.tarifas_sucursal import TarifasSucursal

pytestmark = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive ``datetime`` matching the DB column ``DateTime(timezone=False)``."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _ensure_permiso(
    pg_engine,
    *,
    perm_code: str,
) -> uuid_lib.UUID:
    """Look up (or insert) one ``permisos`` row for ``perm_code``.

    Returns its ``uuid``. The factory wires ``"tarifas-sucursal"`` to
    ``"config_tarifas"`` (``empresa.py:64``) but the canonical seed
    migration (``0002_seed_permisos_canonicos.py``) does NOT include
    that code — pre-existing project inconsistency. Tests seed the
    permission locally so the dependency check resolves, without
    mutating the migration.
    """
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
    pg_engine,
    *,
    actor_uuid: uuid_lib.UUID,
    perm_code: str,
) -> None:
    """Seed one ``permisos_usuario`` row for ``actor_uuid`` and ``perm_code``.

    ``permisos_usuario.uuid_usuario`` has a real FK to ``prod.usuarios``.
    Auto-creates the ``permisos`` row when the canonical seed didn't
    include the code (e.g. ``config_tarifas``).
    """
    from parkos_core.models.V.permisos_usuario import PermisosUsuario
    from sqlalchemy.ext.asyncio import async_sessionmaker

    permiso_uuid = await _ensure_permiso(pg_engine, perm_code=perm_code)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(PermisosUsuario(uuid_usuario=actor_uuid, uuid_permiso=permiso_uuid))
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


async def _seed_sucursal(pg_engine, uuid_sucursal: uuid_lib.UUID) -> None:
    """Insert one real ``sucursal`` row for ``uuid_sucursal``.

    ``tarifas_sucursal.uuid_sucursal`` carries a real FK to
    ``prod.sucursal.uuid`` — tests that insert tarifas need a parent
    Sucursal first. The operator token's ``sucursal`` claim and the
    ``X-Sucursal-Context`` header are pinned to this same uuid so the
    branch context is consistent across all three.
    """
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa Test",
                nit=f"900{empresa_uuid.hex[:6]}",
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
                nombre=f"Sucursal Test {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"P{uuid_sucursal.hex[:6]}",
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
    """Truncate ``prod.tarifas_sucursal`` so each test sees a clean slate.

    The production tenant filter listener reads
    ``state.column_descriptions`` instead of ``state.statement``
    (``tests/conftest.py`` notes the bug at lines 177-195) — that bug
    lets one test see the seeded rows of a previous test. Mirroring
    the HU-F1.1 precedent: use the sync ``psycopg`` connection with the
    superuser DSN to truncate the table.
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE prod.tarifas_sucursal")
        conn.commit()


def _make_tarifa(
    *,
    uuid_sucursal: uuid_lib.UUID,
    vigente_desde: datetime,
    vigente_hasta: datetime | None,
    estado: str,
) -> TarifasSucursal:
    """Build (but do NOT persist) one ``TarifasSucursal`` row.

    The UK01 ``(uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa,
    vigente_desde)`` is satisfied by giving every fixture a unique
    ``vigente_desde``; ``uuid_tipo_vehiculo`` and ``uuid_tipo_tarifa``
    are NULL so the test does not need to seed the catalog parents
    (the FK columns are nullable in the schema and PostgreSQL skips
    the FK check when the value is NULL).
    """
    return TarifasSucursal(
        uuid=uuid_lib.uuid4(),
        uuid_sucursal=uuid_sucursal,
        uuid_tipo_vehiculo=None,
        uuid_tipo_tarifa=None,
        valor=100,
        valor_plena=100,
        vigente_desde=vigente_desde,
        vigente_hasta=vigente_hasta,
        estado=estado,
        created_at=_now_naive(),
        created_by=None,
        sync_status="pendiente",
        sync_timestamp=None,
        sync_attempts=0,
    )


async def _seed_three_versions(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    base: datetime,
) -> tuple[uuid_lib.UUID, uuid_lib.UUID, uuid_lib.UUID]:
    """Seed the three-version matrix used by Caso 1 and Caso 2.

    Each row uses a unique ``vigente_desde`` to satisfy UK01 — past /
    current / future get distinct days.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add_all([
            _make_tarifa(
                uuid_sucursal=uuid_sucursal,
                vigente_desde=base - timedelta(days=120),
                vigente_hasta=base - timedelta(days=60),
                estado="activo",
            ),
            _make_tarifa(
                uuid_sucursal=uuid_sucursal,
                vigente_desde=base - timedelta(days=60),
                vigente_hasta=None,
                estado="activo",
            ),
            _make_tarifa(
                uuid_sucursal=uuid_sucursal,
                vigente_desde=base + timedelta(days=30),
                vigente_hasta=None,
                estado="activo",
            ),
        ])
        await session.commit()

    # Re-query to capture the row uuids — the constructor generated
    # fresh ones; the assertions need them by ``vigente_desde``.
    from sqlalchemy import select

    async with Session() as session:
        rows = (
            await session.execute(
                select(TarifasSucursal).where(
                    TarifasSucursal.uuid_sucursal == uuid_sucursal
                )
            )
        ).scalars().all()
    by_vig = {row.vigente_desde: row.uuid for row in rows}
    past = by_vig[base - timedelta(days=120)]
    current = by_vig[base - timedelta(days=60)]
    future = by_vig[base + timedelta(days=30)]
    return past, current, future


# ---------------------------------------------------------------------------
# Caso 1 — sin vigente_en (default now(UTC)) → sólo la fila actual
# ---------------------------------------------------------------------------


async def test_list_sin_vigente_en_devuelve_vigentes_al_momento_actual(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """Sin query param ``vigente_en`` el endpoint debe devolver la fila
    cuya ventana cubre ``now(UTC)`` y NO las filas pasadas ni las futuras.

    Pre-HU-F1.4 el factory devolvía las filas con ``vigente_hasta IS
    NULL`` — equivalente al subconjunto de este predicado. El handler
    dedicado mantiene esa retrocompatibilidad para todas las filas
    activas vigentes; las filas inactivas con ``vigente_hasta IS NULL``
    dejan de devolverse sin que el caller lo pida (defensa en profundidad,
    alineado con ``resolve_active_subscription_for_exit``).
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    _, current_uuid, _ = await _seed_three_versions(
        pg_engine,
        uuid_sucursal=branch_uuid,
        base=base,
    )

    resp = await client.get(
        "/api/v1/empresa/tarifas-sucursal",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    uuids = [it["uuid"] for it in items]
    assert str(current_uuid) in uuids, (
        f"current version must be in the default-vigente_en response; got {uuids}"
    )
    # Only the current version should be returned; past and future are
    # outside the now(UTC) window.
    assert len(uuids) == 1, (
        f"exactly one row must match the default now(UTC) predicate; got {len(uuids)}: {uuids}"
    )


# ---------------------------------------------------------------------------
# Caso 2 — vigente_en pasado → la fila cuya ventana cubría ese instante
# ---------------------------------------------------------------------------


async def test_list_con_fecha_pasada_devuelve_tarifa_de_ese_momento(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """``?vigente_en=<fecha_pasada>`` debe devolver la fila cuya ventana
    cubre ese instante y NO las demás.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    past_uuid, _, _ = await _seed_three_versions(
        pg_engine,
        uuid_sucursal=branch_uuid,
        base=base,
    )

    # Pick a moment inside the past version's window.
    past_target = base - timedelta(days=90)

    resp = await client.get(
        "/api/v1/empresa/tarifas-sucursal",
        params={"vigente_en": past_target.isoformat()},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    uuids = [it["uuid"] for it in items]
    assert str(past_uuid) in uuids, (
        f"past version must be in the response for ?vigente_en={past_target}; got {uuids}"
    )
    assert len(uuids) == 1, (
        f"exactly one row must match the past vigente_en predicate; got {len(uuids)}: {uuids}"
    )


# ---------------------------------------------------------------------------
# Caso 3 — vigente_en futuro dentro de la ventana de una tarifa programada
# ---------------------------------------------------------------------------


async def test_list_con_fecha_futura_sobre_tarifa_programada(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """``?vigente_en=<fecha_futura>`` debe devolver la tarifa programada
    (cuyo ``vigente_desde`` es futuro) cuando ``vigente_en >= vigente_desde``
    y ``vigente_hasta IS NULL``. La fila ``current`` (abierta y vigente
    hasta el infinito) también satisface el predicado en ese instante.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    _, current_uuid, future_uuid = await _seed_three_versions(
        pg_engine,
        uuid_sucursal=branch_uuid,
        base=base,
    )

    future_target = base + timedelta(days=45)

    resp = await client.get(
        "/api/v1/empresa/tarifas-sucursal",
        params={"vigente_en": future_target.isoformat()},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    items = resp.json()["items"]
    uuids = [it["uuid"] for it in items]
    assert str(future_uuid) in uuids, (
        f"future-programmed version missing; got {uuids}"
    )
    assert str(current_uuid) in uuids, (
        f"current open version must still match the predicate; got {uuids}"
    )
    assert len(uuids) == 2, (
        f"current + future must both match the predicate; got {len(uuids)}: {uuids}"
    )


# ---------------------------------------------------------------------------
# Caso 4 — vigente_en fuera de toda ventana → lista vacía (anti-regresión)
# ---------------------------------------------------------------------------


async def test_list_con_fecha_fuera_de_toda_ventana_devuelve_lista_vacia(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """``?vigente_en=<fecha_fuera>`` debe devolver ``[]``: ninguna fila
    cumple el predicado. Anti-regresión: el handler dedicado no debe
    devolver filas cuyas ventanas NO cubran ``vigente_en``.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    await _seed_three_versions(
        pg_engine,
        uuid_sucursal=branch_uuid,
        base=base,
    )

    # A moment far in the past — well before the past version's window
    # closed and well before the current version's ``vigente_desde``.
    far_past = base - timedelta(days=365)

    resp = await client.get(
        "/api/v1/empresa/tarifas-sucursal",
        params={"vigente_en": far_past.isoformat()},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["items"] == [], (
        f"items must be empty for vigente_en outside all windows; got {body['items']!r}"
    )
    assert body["next_cursor"] is None


# ---------------------------------------------------------------------------
# Caso 5 — CU-02 (operador, 2026-09-22): ``GET /{uuid}`` devuelve el
# detalle completo de UNA tarifa. El handler lista por vigente_en;
# este endpoint dedicado complementa el flujo de cotizacion: el
# payload de ``/operacion/cotizar`` retorna ``tarifa_uuid`` (sin
# detalle) y el FE hace un lookup here para mostrar
# ``valor``/``valor_plena``/``vigente_desde``/``vigente_hasta`` en
# el panel de cotizacion.
# ---------------------------------------------------------------------------


async def test_get_by_uuid_devuelve_detalle_completo(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """``GET /api/v1/empresa/tarifas-sucursal/{uuid}`` retorna la fila
    completa (``TarifasSucursalRead``) — el FE la usa para mostrar el
    breakdown legible de la tarifa aplicada (no solo el UUID).

    Verifica que el shape es correcto: ``uuid`` matchea, ``valor`` y
    ``valor_plena`` se exponen como string (NUMERIC serializa a string
    JSON para preservar precision), ``vigente_desde`` es ISO-8601,
    ``estado`` es 'activo', ``vigente_hasta`` puede ser ``null`` (la
    fila es vigente sin fecha de cierre).
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    base = _now_naive()
    await _seed_three_versions(
        pg_engine,
        uuid_sucursal=branch_uuid,
        base=base,
    )

    # El seeder crea 3 versiones; la del medio (current_uuid) es la
    # que tiene ``vigente_desde`` reciente + ``vigente_hasta`` NULL
    # (vigente abierta). Buscamos esa para verificar el detalle
    # completo sin solapamiento.
    list_resp = await client.get(
        "/api/v1/empresa/tarifas-sucursal",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )
    assert list_resp.status_code == 200
    # Tomar la fila con vigente_hasta NULL (la "open" version del
    # seeder).
    current = next(
        it for it in list_resp.json()["items"] if it["vigente_hasta"] is None
    )
    uuid_target = current["uuid"]

    resp = await client.get(
        f"/api/v1/empresa/tarifas-sucursal/{uuid_target}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, (
        f"GET by uuid must return 200 with detalle completo; got "
        f"{resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["uuid"] == uuid_target, (
        f"uuid in response must match the path param; got {body['uuid']!r}"
    )
    assert body["uuid_sucursal"] == str(branch_uuid)
    assert body["estado"] == "activo"
    assert body["vigente_hasta"] is None, (
        f"open version (current_uuid) must have vigente_hasta=NULL; "
        f"got {body['vigente_hasta']!r}"
    )
    assert isinstance(body["vigente_desde"], str) and body["vigente_desde"]
    # valor + valor_plena son NUMERIC(18,4) → serializan como string
    # JSON para preservar precision (decisión de producto, ver PR-9).
    assert "valor" in body and isinstance(body["valor"], str)
    assert "valor_plena" in body and isinstance(body["valor_plena"], str)
    assert "created_at" in body


async def test_get_by_uuid_uuid_inexistente_devuelve_404(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """``GET /api/v1/empresa/tarifas-sucursal/{uuid}`` con uuid que no
    existe en ``prod.tarifas_sucursal`` debe retornar 404 con el
    detail ``{"error": "tarifa_no_encontrada", "uuid": "..."}``. El FE
    usa ese 404 como trigger de fallback en ``useTarifaByUuid``.
    """
    await _truncate_tarifas(pg_dsn)
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    await _seed_sucursal(pg_engine, branch_uuid)
    await _seed_usuario(pg_engine, actor_uuid)
    await _grant_permission(pg_engine, actor_uuid=actor_uuid, perm_code="config_tarifas")
    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    nonexistent_uuid = uuid_lib.uuid4()

    resp = await client.get(
        f"/api/v1/empresa/tarifas-sucursal/{nonexistent_uuid}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 404, (
        f"GET by uuid with nonexistent row must return 404; got "
        f"{resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("error") == "tarifa_no_encontrada", (
        f"detail.error must be 'tarifa_no_encontrada'; got {detail!r}"
    )
    assert detail.get("uuid") == str(nonexistent_uuid)


__all__ = [
    "test_get_by_uuid_devuelve_detalle_completo",
    "test_get_by_uuid_uuid_inexistente_devuelve_404",
    "test_list_con_fecha_fuera_de_toda_ventana_devuelve_lista_vacia",
    "test_list_con_fecha_futura_sobre_tarifa_programada",
    "test_list_con_fecha_pasada_devuelve_tarifa_de_ese_momento",
    "test_list_sin_vigente_en_devuelve_vigentes_al_momento_actual",
]
