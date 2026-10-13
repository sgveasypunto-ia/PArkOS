"""#12/#14: GET catalogos/tipo-subscripciones filters (tipo de vehiculo + estado + tipo de cliente).

The SQL emitted by the global catalog list handler is captured with a fake
session and compiled against the PostgreSQL dialect (no live DB needed).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402


class _EmptyScalars:
    def all(self) -> list:
        return []


class _EmptyResult:
    def scalars(self) -> _EmptyScalars:
        return _EmptyScalars()


class _CapturingSession:
    def __init__(self) -> None:
        self.stmts: list[Any] = []

    async def execute(self, stmt: Any) -> Any:
        self.stmts.append(stmt)
        return _EmptyResult()


@pytest.fixture
def app_and_session(monkeypatch: pytest.MonkeyPatch):
    from fastapi import FastAPI
    from parkos_core.api.v1.catalogos import router as catalogos_router
    from parkos_core.db.engine import get_session

    async def fake_verify_jwt(request: Any) -> dict[str, Any]:
        return {
            "iss": "admin-test",
            "sub": str(uuid_lib.uuid4()),
            "rol": "admin",
            "sucursales_permitidas": [],
        }

    session = _CapturingSession()

    async def fake_get_session() -> Any:
        return session

    app = FastAPI()
    app.include_router(catalogos_router, prefix="/api/v1")
    app.dependency_overrides[get_session] = fake_get_session

    import parkos_core.auth.jwt_issuer_guard as _gj
    import parkos_core.auth.permissions as _pj
    import parkos_core.auth.tenancy as _tj

    for mod in (_gj, _pj, _tj):
        monkeypatch.setattr(mod, "verify_jwt", fake_verify_jwt)
    return app, session


def _sql(stmt: Any) -> tuple[str, dict[str, Any]]:
    from sqlalchemy.dialects import postgresql

    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


async def _get(app: Any, path: str):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_listado_tipo_subscripciones_filtra_solo_activos(app_and_session) -> None:
    """#12: a closed/inactive plan never shows up in the list."""
    app, session = app_and_session
    moto = uuid_lib.uuid4()
    r = await _get(app, f"/api/v1/catalogos/tipo-subscripciones?uuid_tipo_vehiculo={moto}")
    assert r.status_code == 200, r.text
    sql, params = _sql(session.stmts[0])
    assert "tipo_subscripciones.estado =" in sql
    assert "activo" in params.values()
    # moto plans + typeless plans (e.g. MENSUAL_EMPRESA with NULL type)
    assert "tipo_subscripciones.uuid_tipo_vehiculo IS NULL" in sql
    assert moto in params.values()


@pytest.mark.asyncio
async def test_listado_con_tipo_cliente_natural_excluye_planes_juridica(
    app_and_session,
) -> None:
    """#14: tipo_cliente=natural -> permitido = 'natural' OR permitido IS NULL."""
    app, session = app_and_session
    r = await _get(app, "/api/v1/catalogos/tipo-subscripciones?tipo_cliente=natural")
    assert r.status_code == 200, r.text
    sql, params = _sql(session.stmts[0])
    assert "tipo_subscripciones.tipo_cliente_permitido =" in sql
    assert "tipo_subscripciones.tipo_cliente_permitido IS NULL" in sql
    assert "natural" in params.values()
    assert "juridica" not in params.values()


@pytest.mark.asyncio
async def test_listado_sin_tipo_cliente_no_filtra_por_cliente(app_and_session) -> None:
    app, session = app_and_session
    r = await _get(app, "/api/v1/catalogos/tipo-subscripciones")
    assert r.status_code == 200, r.text
    sql, _ = _sql(session.stmts[0])
    assert "tipo_cliente_permitido =" not in sql
    assert "tipo_cliente_permitido IS NULL" not in sql


@pytest.mark.asyncio
async def test_tipo_cliente_invalido_422(app_and_session) -> None:
    app, _ = app_and_session
    r = await _get(app, "/api/v1/catalogos/tipo-subscripciones?tipo_cliente=otro")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tipo_cliente_en_otro_catalogo_422(app_and_session) -> None:
    app, _ = app_and_session
    r = await _get(app, "/api/v1/catalogos/tipos-vehiculo?tipo_cliente=natural")
    assert r.status_code == 422
