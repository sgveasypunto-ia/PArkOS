"""Integration tests for HU-F20.4 (``api/v1/auditoria.py``).

Real Postgres + real handlers, same harness shape as
``test_admin_sync_hu_f19_1.py`` (ad hoc router-only app, issuer dep
overridden, ``get_session`` bound to the real ``pg_engine``). The
``audit_read`` permission dependency is ALSO overridden here -- same
reasoning: these tests exercise the cross-branch bitácora business logic
(real hash chains, real ``extract_sucursales_permitidas_fresh`` reads),
not ``require_permission``'s own DB-grant check (covered in isolation by
``tests/unit/test_permissions_dependency.py``).

Covers:

  - ``GET /admin/log-transaccional/verify-chain``, Scenario A (clean chain
    -> ``{"ok": true, "anomalias": []}``) and Scenario B (one row's
    ``hash_anterior`` corrupted via a raw UPDATE that bypasses the
    ``LOG_TRANSACCIONAL_INMUTABLE`` trigger -> the anomaly names the
    EXACT corrupted row).
  - ``GET /admin/log-transaccional`` cross-branch listing + the new
    filters (``tabla``, ``uuid_registro``, ``desde``/``hasta``).
  - ``GET /admin/log-transaccional/buscar`` typeahead.

Skips cleanly (via the ``alembic_upgrade`` fixture chain in
``conftest.py``) when the local Postgres image lacks ``pg_partman`` --
documented, expected limitation, not a regression to chase here (see the
HU-F20.4 task brief).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
for _p in (_PARKOS_CORE_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import parkos_core.api.v1.auditoria as _auditoria_module  # noqa: E402
from parkos_core.api.v1.auditoria import router as auditoria_router_obj  # noqa: E402
from parkos_core.models.A.log_transaccional import LogTransaccional  # noqa: E402
from parkos_core.models.V.empresa import Empresa  # noqa: E402
from parkos_core.models.V.sucursal import Sucursal  # noqa: E402
from parkos_core.repo.hash_chain import append as hash_chain_append  # noqa: E402

ACTOR_UUID_FOR_CHAIN = uuid_lib.UUID("00000000-0000-0000-0000-0000000000f2")


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_sucursal(pg_engine) -> uuid_lib.UUID:
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Bitacora SA",
                nit=f"905{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hola",
                mensaje_salida="bye",
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
        sucursal_uuid = uuid_lib.uuid4()
        session.add(
            Sucursal(
                uuid=sucursal_uuid,
                uuid_empresa=empresa_uuid,
                uuid_tipo_sucursal=None,
                nombre=f"Suc Bitacora {sucursal_uuid.hex[:8]}",
                prefijo_nombre=f"B{sucursal_uuid.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Bitacora",
                telefono="+575555",
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
        return sucursal_uuid


async def _assign_admin(
    pg_engine, *, actor_uuid: uuid_lib.UUID, sucursales: list[uuid_lib.UUID]
) -> None:
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Usuarios(
                uuid=actor_uuid,
                nombre="Bitacora",
                apellido="Admin",
                cedula=f"A{actor_uuid.hex[:10]}",
                email=f"bitacora-{actor_uuid.hex[:8]}@parkos.local",
                password_hash="$2b$12$not-a-real-hash-for-jwt-only-tests",
                rol="admin",
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
        for sucursal in sucursales:
            session.add(
                UsuariosSucursal(
                    uuid_sucursal=sucursal,
                    uuid_usuario=actor_uuid,
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


def _build_app(pg_engine) -> tuple[FastAPI, Any]:
    """Mount ``auditoria.router`` with overrides; return (app, set_claims)."""
    from parkos_core.db.engine import get_session

    app = FastAPI()
    outer = APIRouter(prefix="/api/v1")
    outer.include_router(auditoria_router_obj)
    app.include_router(outer)

    captured: dict = {"value": None}

    def _override_claims() -> dict:
        if captured["value"] is None:
            raise RuntimeError("set_claims() before request")
        return captured["value"]

    app.dependency_overrides[_auditoria_module._admin_issuer_dep] = _override_claims
    app.dependency_overrides[_auditoria_module._audit_perm_dep] = lambda: None

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async def _session_override() -> Any:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    return app, lambda c: captured.__setitem__("value", c)


async def _get(fastapi_app: FastAPI, url: str) -> httpx.Response:
    transport = ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.get(url)


async def _setup_one_branch_admin(pg_engine) -> tuple[uuid_lib.UUID, uuid_lib.UUID, FastAPI, Any]:
    branch = await _seed_sucursal(pg_engine)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch])
    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims({"sub": str(admin_actor), "iss": "admin-test", "rol": "admin"})
    return branch, admin_actor, fastapi_app, set_claims


async def _seed_clean_chain(
    pg_engine, *, uuid_sucursal: uuid_lib.UUID, count: int
) -> list[uuid_lib.UUID]:
    """Genesis (auto) + ``count`` correctly-linked rows, via the real
    ``repo.hash_chain.append`` helper (never hand-rolled hashing)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    row_uuids: list[uuid_lib.UUID] = []
    async with Session() as session:
        for i in range(count):
            row = await hash_chain_append(
                session,
                LogTransaccional,
                {
                    "uuid_sucursal": uuid_sucursal,
                    "accion": "crear",
                    "tabla_afectada": "ingreso",
                    "uuid_registro_afectado": uuid_lib.uuid4(),
                    "timestamp_evento": datetime(2026, 1, 1, 12, i, 0),
                },
                actor_uuid=ACTOR_UUID_FOR_CHAIN,
            )
            await session.commit()
            row_uuids.append(row.uuid)
    return row_uuids


async def _corrupt_hash_anterior(
    pg_engine, *, row_uuid: uuid_lib.UUID, new_hash_anterior: str
) -> None:
    """Deliberately break the chain link for ``row_uuid`` via a raw UPDATE.

    ``prod.log_transaccional`` is [A] (append-only): the BEFORE UPDATE OR
    DELETE trigger raises ``LOG_TRANSACCIONAL_INMUTABLE`` on any ordinary
    UPDATE. ``session_replication_role = replica`` disables triggers for
    this ONE statement -- same established pattern
    ``test_verify_chain.py::_insert_bypassing_chain_trigger`` uses to
    construct its own corrupted fixture (that one bypasses the trigger for
    an INSERT; this one bypasses it for an UPDATE). The DB trigger is a
    real production safety net; this test intentionally defeats it to
    prove the WALKER (``verify_chain_for_spec``, exercised here through the
    real HTTP endpoint) also detects the break, not just the trigger.
    """
    from sqlalchemy import text

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(text("SET session_replication_role = replica"))
        await session.execute(
            text("UPDATE prod.log_transaccional SET hash_anterior = :h WHERE uuid = :u"),
            {"h": new_hash_anterior, "u": row_uuid},
        )
        await session.execute(text("SET session_replication_role = origin"))
        await session.commit()


# ---------------------------------------------------------------------------
# verify-chain: Scenario A (clean) / Scenario B (corrupted)
# ---------------------------------------------------------------------------


async def test_verify_chain_clean_chain_returns_ok_true(
    pg_engine, alembic_upgrade
) -> None:
    """Scenario A: a clean, valid hash chain verifies with zero anomalies."""
    branch, _actor, fastapi_app, _set_claims = await _setup_one_branch_admin(pg_engine)
    await _seed_clean_chain(pg_engine, uuid_sucursal=branch, count=3)

    resp = await _get(
        fastapi_app, f"/api/v1/admin/log-transaccional/verify-chain?uuid_sucursal={branch}"
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "anomalias": []}


async def test_verify_chain_corrupted_row_is_named_in_anomalias(
    pg_engine, alembic_upgrade
) -> None:
    """Scenario B: a corrupted ``hash_anterior`` surfaces as >=1 anomaly
    naming the EXACT corrupted row's uuid."""
    branch, _actor, fastapi_app, _set_claims = await _setup_one_branch_admin(pg_engine)
    row_uuids = await _seed_clean_chain(pg_engine, uuid_sucursal=branch, count=3)
    corrupted_uuid = row_uuids[1]
    await _corrupt_hash_anterior(pg_engine, row_uuid=corrupted_uuid, new_hash_anterior="0" * 64)

    resp = await _get(
        fastapi_app, f"/api/v1/admin/log-transaccional/verify-chain?uuid_sucursal={branch}"
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert len(body["anomalias"]) >= 1
    anomaly_uuids = {a["uuid"] for a in body["anomalias"]}
    assert str(corrupted_uuid) in anomaly_uuids
    corrupted_entry = next(a for a in body["anomalias"] if a["uuid"] == str(corrupted_uuid))
    assert corrupted_entry["actual"] == "0" * 64
    assert corrupted_entry["tabla"] == "log_transaccional"


async def test_verify_chain_omitted_branch_sweeps_every_permitted_branch(
    pg_engine, alembic_upgrade
) -> None:
    """Omitting ``uuid_sucursal`` verifies EVERY permitted branch, not just
    the near-empty global (``uuid_sucursal IS NULL``) partition."""
    branch_a = await _seed_sucursal(pg_engine)
    branch_b = await _seed_sucursal(pg_engine)
    admin_actor = uuid_lib.uuid4()
    await _assign_admin(pg_engine, actor_uuid=admin_actor, sucursales=[branch_a, branch_b])
    fastapi_app, set_claims = _build_app(pg_engine)
    set_claims({"sub": str(admin_actor), "iss": "admin-test", "rol": "admin"})

    await _seed_clean_chain(pg_engine, uuid_sucursal=branch_a, count=2)
    row_uuids_b = await _seed_clean_chain(pg_engine, uuid_sucursal=branch_b, count=2)
    await _corrupt_hash_anterior(pg_engine, row_uuid=row_uuids_b[0], new_hash_anterior="9" * 64)

    resp = await _get(fastapi_app, "/api/v1/admin/log-transaccional/verify-chain")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    anomaly_uuids = {a["uuid"] for a in body["anomalias"]}
    assert str(row_uuids_b[0]) in anomaly_uuids


async def test_verify_chain_unpermitted_branch_returns_403(
    pg_engine, alembic_upgrade
) -> None:
    _branch, _actor, fastapi_app, _set_claims = await _setup_one_branch_admin(pg_engine)
    other_branch = uuid_lib.uuid4()

    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/log-transaccional/verify-chain?uuid_sucursal={other_branch}",
    )

    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "unauthorized_sucursal_context"


async def test_verify_chain_unknown_table_returns_422(
    pg_engine, alembic_upgrade
) -> None:
    _branch, _actor, fastapi_app, _set_claims = await _setup_one_branch_admin(pg_engine)

    resp = await _get(
        fastapi_app, "/api/v1/admin/log-transaccional/verify-chain?tabla=not_a_real_table"
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "tabla_no_verificable"


# ---------------------------------------------------------------------------
# Cross-branch listing + filters
# ---------------------------------------------------------------------------


async def test_list_log_transaccional_filters_by_tabla_and_date_range(
    pg_engine, alembic_upgrade
) -> None:
    branch, _actor, fastapi_app, _set_claims = await _setup_one_branch_admin(pg_engine)
    await _seed_clean_chain(pg_engine, uuid_sucursal=branch, count=2)

    resp = await _get(
        fastapi_app,
        f"/api/v1/admin/log-transaccional?uuid_sucursal={branch}&tabla=ingreso"
        f"&desde=2026-01-01&hasta=2026-01-01",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 2
    assert all(item["tabla_afectada"] == "ingreso" for item in body["items"])


async def test_list_log_transaccional_rango_fecha_invalido_returns_422(
    pg_engine, alembic_upgrade
) -> None:
    _branch, _actor, fastapi_app, _set_claims = await _setup_one_branch_admin(pg_engine)

    resp = await _get(
        fastapi_app,
        "/api/v1/admin/log-transaccional?desde=2026-02-01&hasta=2026-01-01",
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "rango_fecha_invalido"


# ---------------------------------------------------------------------------
# Typeahead
# ---------------------------------------------------------------------------


async def test_buscar_matches_prefix_scoped_to_permitted_branch(
    pg_engine, alembic_upgrade
) -> None:
    branch, _actor, fastapi_app, _set_claims = await _setup_one_branch_admin(pg_engine)
    await _seed_clean_chain(pg_engine, uuid_sucursal=branch, count=1)

    resp = await _get(fastapi_app, "/api/v1/admin/log-transaccional/buscar?prefijo=ingr")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) >= 1
    assert all(item["tabla_afectada"].startswith("ingr") for item in body["items"])


__all__ = [
    "test_buscar_matches_prefix_scoped_to_permitted_branch",
    "test_list_log_transaccional_filters_by_tabla_and_date_range",
    "test_list_log_transaccional_rango_fecha_invalido_returns_422",
    "test_verify_chain_clean_chain_returns_ok_true",
    "test_verify_chain_corrupted_row_is_named_in_anomalias",
    "test_verify_chain_omitted_branch_sweeps_every_permitted_branch",
    "test_verify_chain_unknown_table_returns_422",
    "test_verify_chain_unpermitted_branch_returns_403",
]
