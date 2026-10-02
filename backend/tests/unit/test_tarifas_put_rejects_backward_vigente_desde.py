"""Regression test -- ``PUT /empresa/tarifas-sucursal/{uuid}`` must reject
a ``vigente_desde`` that goes backward before the row being replaced's own
``vigente_desde`` (QA batch tarifas/cupos, 2026-10-02).

BUGFIX: ``assert_no_overlap`` (``repo/overlap.py``) only queries rows
where ``vigente_hasta IS NULL`` (the one currently-open row per business
key) and the PUT handler passes ``exclude_uuid=uuid`` -- the row being
edited IS that one open row, so after excluding it there is NEVER an
"other" open row left to conflict with. The overlap guard can therefore
never fire on PUT, no matter how far back ``vigente_desde`` is dated --
confirmed live: ``PUT`` with ``vigente_desde`` inside an already-CLOSED
historical window (``[17:16, 17:17)``) returned 200, silently creating
two overlapping bi-temporal windows for the same business key.

Fix: reject (409 ``tarifa_overlap``) directly in the handler when the
payload's ``vigente_desde`` is before the CURRENT row's own
``vigente_desde`` -- the chain's windows are constructed to be
monotonically increasing, so this single comparison is sufficient to
block going backward into any prior window, open or closed.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import datetime
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
TIPO_VEHICULO_UUID = uuid_lib.UUID("fa8eb664-2566-4b5f-953b-d0a38289d95c")
TIPO_TARIFA_UUID = uuid_lib.UUID("12e3886a-7059-47ee-bdb2-aa5fb1272bea")
TARGET_UUID = uuid_lib.uuid4()


def _make_current_row():
    row = MagicMock(name="current_tarifa_row")
    row.uuid = TARGET_UUID
    row.uuid_sucursal = SUCURSAL_UUID
    row.uuid_tipo_vehiculo = TIPO_VEHICULO_UUID
    row.uuid_tipo_tarifa = TIPO_TARIFA_UUID
    row.valor = "3500.0000"
    row.valor_plena = None
    row.vigente_desde = datetime(2026, 10, 2, 17, 17, 0)
    row.vigente_hasta = None
    row.estado = "activo"
    row.created_at = datetime(2026, 10, 2, 17, 17, 0)
    row.created_by = None
    row.sync_status = None
    return row


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from parkos_core.api.v1 import _build_empresa_router

    app = FastAPI()
    app.include_router(_build_empresa_router(), prefix="/api/v1")

    async def _session_override():
        session = MagicMock(name="AsyncSession")
        session.commit = AsyncMock(return_value=None)
        session.refresh = AsyncMock(return_value=None)
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
    app.dependency_overrides[empresa_module._tarifas_pr_c_perm_dep] = lambda: None

    monkeypatch.setattr(
        empresa_module, "current_version", AsyncMock(return_value=_make_current_row())
    )
    monkeypatch.setattr(empresa_module, "assert_no_overlap", AsyncMock(return_value=None))
    new_row = _make_current_row()
    monkeypatch.setattr(
        empresa_module, "close_and_insert", AsyncMock(return_value=new_row)
    )

    return TestClient(app)


def _put(client: TestClient, vigente_desde_iso: str):
    return client.put(
        f"/api/v1/empresa/tarifas-sucursal/{TARGET_UUID}",
        json={
            "uuid_sucursal": str(SUCURSAL_UUID),
            "uuid_tipo_vehiculo": str(TIPO_VEHICULO_UUID),
            "uuid_tipo_tarifa": str(TIPO_TARIFA_UUID),
            "valor": "3500.0000",
            "valor_plena": None,
            "vigente_desde": vigente_desde_iso,
        },
    )


def test_put_rejects_vigente_desde_before_current_own_vigente_desde(
    client: TestClient,
) -> None:
    """``vigente_desde`` inside an already-closed historical window (here,
    before the row's OWN current ``vigente_desde``) must 409, not 200 --
    the overlap guard alone cannot catch this on PUT (see module docstring)."""
    resp = _put(client, "2026-10-02T17:16:30")
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["error"] == "tarifa_overlap"


def test_put_accepts_vigente_desde_at_or_after_current_own_vigente_desde(
    client: TestClient,
) -> None:
    """The fix must not regress forward-dated (or same-instant) edits."""
    resp = _put(client, "2026-10-02T17:45:00")
    assert resp.status_code == 200, resp.text
