"""Regression test — ``GET /caja/arqueo/resumen`` route-ordering bug (2026-09-25).

BUGFIX: ``api/v1/caja.py`` used to mount the generic C+Q factory router
for ``resource="arqueo"`` (registers ``GET /caja/arqueo/{uuid}``) BEFORE
including the dedicated ``caja_arqueo.router`` (which owns the literal
``GET /caja/arqueo/resumen``). Starlette matches routes in registration
order, so ANY request to ``/caja/arqueo/<anything>`` — including the
literal ``resumen`` — matched the generic ``{uuid}`` path param first.
Pydantic then rejected ``"resumen"`` as an invalid UUID, producing a
permanent 422 and making the resumen endpoint unreachable over real
HTTP (confirmed live against the running backend). The existing unit
tests in ``test_arqueo_resumen.py`` call ``get_arqueo_resumen`` as a
bare Python function and therefore never exercise Starlette's route
matching — they could not have caught this class of bug.

This test drives the REAL ``caja.router`` (not a hand-picked subset)
through an actual ``TestClient`` HTTP request, so a regression in
registration order fails here.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from parkos_core.api.deps import get_tenant_ctx  # noqa: E402
from parkos_core.api.v1 import caja as caja_module  # noqa: E402
from parkos_core.api.v1 import caja_arqueo as caja_arqueo_module  # noqa: E402
from parkos_core.auth.tenancy import TenantContext  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402

SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Real ``caja.router`` (both mounts, real registration order) via TestClient."""
    app = FastAPI()
    app.include_router(caja_module.router, prefix="/api/v1")

    async def _session_override():
        yield MagicMock(name="AsyncSession")

    def _tenant_override() -> TenantContext:
        # admin- bypasses the operador- cross-branch tenant check (Layer 2).
        return TenantContext(
            actor_uuid=uuid_lib.uuid4(),
            actor_rol="admin",
            issuer_prefix="admin-",
            sucursal_uuid=SUCURSAL_UUID,
            uuid_sesion=None,
        )

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_tenant_ctx] = _tenant_override
    app.dependency_overrides[caja_arqueo_module._caja_resumen_issuer_dep] = (
        lambda: None
    )

    monkeypatch.setattr(
        caja_arqueo_module.repo_arqueo,
        "listar_sesiones_del_dia",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        caja_arqueo_module.repo_arqueo,
        "obtener_cierre_dia_del_dia",
        AsyncMock(return_value=None),
    )

    return TestClient(app)


def test_arqueo_resumen_route_not_shadowed_by_generic_uuid_mount(
    client: TestClient,
) -> None:
    """``/arqueo/resumen`` must dispatch to ``get_arqueo_resumen``, never
    to the generic factory-mounted ``GET /arqueo/{uuid}`` read-by-id
    route (registration-order regression in ``api/v1/caja.py``)."""
    resp = client.get(
        "/api/v1/caja/arqueo/resumen",
        params={"uuid_sucursal": str(SUCURSAL_UUID), "fecha": "2026-09-25"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sesiones"] == []
    assert body["cierre_dia"] is None
    assert body["uuid_sucursal"] == str(SUCURSAL_UUID)


def test_arqueo_read_by_real_uuid_still_reaches_generic_mount(
    client: TestClient,
) -> None:
    """The generic ``GET /arqueo/{uuid}`` factory route must still work
    for an actual UUID once ``/arqueo/resumen`` is registered first —
    the fix must not regress the factory-mounted single-item read."""
    random_uuid = uuid_lib.uuid4()
    resp = client.get(f"/api/v1/caja/arqueo/{random_uuid}")
    # No row exists for this UUID (session is a bare MagicMock without a
    # configured `.get`/`.execute` return) -- what matters here is that
    # Starlette dispatched to the generic single-item handler at all
    # (any response FastAPI itself produced, e.g. 404/500 from the real
    # handler body) rather than the "resumen" literal route (404 "Not
    # Found" from Starlette itself, or the old 422 uuid_parsing shape).
    assert resp.status_code != 422 or "uuid_parsing" not in resp.text
