"""Regression test -- ``GET /empresa/tarifas-sucursal/by-key`` route-ordering
bug (QA batch tarifas/cupos, 2026-10-02).

BUGFIX: ``api/v1/empresa.py``'s reorder block (search ``_reordered``) lists
``"tarifas-sucursal__dedicated_hu_f1_4"`` (owns the catch-all
``GET /tarifas-sucursal/{uuid}``) BEFORE
``"tarifas-sucursal__dedicated_pr_c"`` (owns the literal
``GET /tarifas-sucursal/by-key``). Starlette/FastAPI match routes in
registration order, so ANY request to ``/tarifas-sucursal/<anything>`` --
including the literal ``by-key`` -- matched the catch-all ``{uuid}`` path
param first. Pydantic then rejected ``"by-key"`` as an invalid UUID,
producing a permanent 422 (``uuid_parsing``) and making the "ver
histórico" feature unreachable over real HTTP (confirmed live via
chrome-devtools against the running admin UI: clicking "Ver histórico"
on ``/tarifas`` always rendered "Sin versiones registradas.").

Exact same bug class as
``test_caja_arqueo_router_ordering.py`` (``/caja/arqueo/resumen`` shadowed
by the generic ``/caja/arqueo/{uuid}`` factory mount, 2026-09-25) --
mirrors its pattern: drive the REAL aggregated empresa router (the one
``api/v1/__init__.py`` actually mounts, built from the real, reordered
``_SUB_ROUTERS``) through an actual ``TestClient`` HTTP request, so a
registration-order regression fails here instead of only being visible
live in the browser.
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
from parkos_core.api.v1 import empresa as empresa_module  # noqa: E402
from parkos_core.auth.tenancy import TenantContext, get_tenant_ctx  # noqa: E402
from parkos_core.db.engine import get_session  # noqa: E402

SUCURSAL_UUID = uuid_lib.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Real ``_build_empresa_router()`` output (same builder ``api/v1/__init__.py``
    uses for the live app, real ``_SUB_ROUTERS`` registration order)."""
    from parkos_core.api.v1 import _build_empresa_router  # local import: side-effect order

    app = FastAPI()
    app.include_router(_build_empresa_router(), prefix="/api/v1")

    async def _session_override():
        session = MagicMock(name="AsyncSession")
        result = MagicMock(name="Result")
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)
        yield session

    def _tenant_override() -> TenantContext:
        return TenantContext(
            actor_uuid=uuid_lib.uuid4(),
            actor_rol="admin",
            issuer_prefix="admin-",
            sucursal_uuid=SUCURSAL_UUID,
            uuid_sesion=None,
        )

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_tenant_ctx] = _tenant_override
    app.dependency_overrides[empresa_module._tarifas_pr_c_issuer_dep] = lambda: None
    app.dependency_overrides[empresa_module._tarifas_issuer_dep] = lambda: None

    return TestClient(app)


def test_tarifas_by_key_route_not_shadowed_by_dedicated_uuid_mount(
    client: TestClient,
) -> None:
    """``/tarifas-sucursal/by-key`` must dispatch to
    ``get_tarifa_by_key_history_pr_c``, never to the dedicated HU-F1.4
    ``GET /tarifas-sucursal/{uuid}`` single-item read (registration-order
    regression)."""
    resp = client.get(
        "/api/v1/empresa/tarifas-sucursal/by-key",
        params={"sucursal": str(SUCURSAL_UUID)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_tarifas_read_by_real_uuid_still_reaches_dedicated_mount(
    client: TestClient,
) -> None:
    """The dedicated ``GET /tarifas-sucursal/{uuid}`` read-by-id route must
    still work for an actual UUID once ``/by-key`` is registered first --
    the fix must not regress the single-item read."""
    random_uuid = uuid_lib.uuid4()
    resp = client.get(f"/api/v1/empresa/tarifas-sucursal/{random_uuid}")
    # No row exists (session mock returns no scalar) -- what matters is
    # that Starlette dispatched to the uuid-param handler at all (a real
    # 404 from the handler body) rather than the "by-key" literal route.
    assert resp.status_code == 404, resp.text
    assert "tarifa_no_encontrada" in resp.text
