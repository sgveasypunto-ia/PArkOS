"""HU-F1.11 / T4.1 — POST /api/v1/workflows/reimpresion-ticket handler tests.

F1.10 mock-everything pattern (no DB): mock repo helpers with
``unittest.mock.MagicMock`` + ``AsyncMock`` and drive the handler chain
end-to-end. Asserts:

  - State machine correctness across V1..V5 validations
  - KD-TKT-01 single-commit on the happy path
  - DEC-TKT-06 Cache-Control: no-store header on 201 + 4xx responses
  - Tenant scope post-V1 (KD-S2 analog from F1.7)
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from parkos_core.schemas.workflows import ReimpresionTicketCreateEndpoint  # noqa: E402


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_ctx(
    *,
    sucursal_uuid: uuid_lib.UUID | None = None,
    actor_uuid: uuid_lib.UUID | None = None,
    issuer_prefix: str = "operador-",
) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = actor_uuid or uuid_lib.uuid4()
    ctx.issuer_prefix = issuer_prefix
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _make_ingreso_orm(
    *,
    uuid_ingreso: uuid_lib.UUID | None = None,
    uuid_sucursal: uuid_lib.UUID | None = None,
) -> MagicMock:
    ingreso = MagicMock()
    ingreso.uuid = uuid_ingreso or uuid_lib.uuid4()
    ingreso.uuid_sucursal = uuid_sucursal or uuid_lib.uuid4()
    return ingreso


def _make_reimpresion_orm(
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    motivo: str = "Cliente solicita reimpresion por deterioro",
    uuid_factura: uuid_lib.UUID | None = None,
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.created_at = _now()
    row.created_by = uuid_lib.uuid4()
    row.sync_status = None
    row.sync_timestamp = None
    row.sync_attempts = None
    row.uuid_sucursal = uuid_sucursal
    row.uuid_ingreso = uuid_ingreso
    row.uuid_usuario = uuid_lib.uuid4()
    row.uuid_costo_servicio = None
    row.costo_aplicado = None
    row.uuid_factura = uuid_factura
    row.motivo = motivo
    row.uuid_reimpresion_padre = None
    row.timestamp_evento = _now()
    row.vigente_desde = _now()
    row.vigente_hasta = None
    row.estado = "activo"
    return row


# ---------------------------------------------------------------------------
# T4.1 — happy path + V1..V5 error paths (mocked, no DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_reimpresion_happy_path_uuid_ingreso_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.1: 201 + workflow_estado='autorizada' + KD-TKT-01 single commit.

    No ``uuid_factura`` → V3 skipped (DEC-TKT-04). Result carries
    ``Cache-Control: no-store`` header on the response.
    """
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_ingreso = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    ingreso = _make_ingreso_orm(
        uuid_ingreso=uuid_ingreso, uuid_sucursal=uuid_sucursal
    )
    new_reim = _make_reimpresion_orm(
        uuid_sucursal=uuid_sucursal, uuid_ingreso=uuid_ingreso
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_ingreso_por_uuid",
        AsyncMock(return_value=ingreso),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_activa_por_ingreso",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=new_reim),
    )

    payload = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion por deterioro del original",
        uuid_ingreso=uuid_ingreso,
        uuid_factura=None,
    )
    result = await workflows_reimpresion_mod.create_reimpresion_ticket(
        response, payload, session, ctx, None
    )

    assert result.uuid == new_reim.uuid
    assert result.workflow_estado == "autorizada"
    assert result.uuid_reimpresion_padre is None  # chain root
    assert result.uuid_factura is None
    assert response.headers.get("Cache-Control") == "no-store"
    # KD-TKT-01 single-commit invariant.
    assert session.commit.await_count == 1
    # V3 must be skipped when uuid_factura is None.
    workflows_reimpresion_mod.repo_reimpresion.buscar_factura_por_uuid.assert_not_called()


@pytest.mark.asyncio
async def test_create_reimpresion_happy_path_with_uuid_factura_populated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.1: 201 + uuid_factura populated when factura exists (DEC-TKT-04)."""
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_ingreso = uuid_lib.uuid4()
    uuid_factura = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    ingreso = _make_ingreso_orm(
        uuid_ingreso=uuid_ingreso, uuid_sucursal=uuid_sucursal
    )
    factura = MagicMock()
    factura.uuid = uuid_factura
    new_reim = _make_reimpresion_orm(
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
        uuid_factura=uuid_factura,
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_ingreso_por_uuid",
        AsyncMock(return_value=ingreso),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_activa_por_ingreso",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=factura),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=new_reim),
    )

    payload = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion con factura vinculada",
        uuid_ingreso=uuid_ingreso,
        uuid_factura=uuid_factura,
    )
    result = await workflows_reimpresion_mod.create_reimpresion_ticket(
        response, payload, session, ctx, None
    )

    assert result.uuid_factura == uuid_factura
    assert result.workflow_estado == "autorizada"
    assert response.headers.get("Cache-Control") == "no-store"
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_create_reimpresion_returns_404_ingreso_no_encontrado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V1 404: prod.ingreso.uuid absent → 404 ingreso_no_encontrado."""
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_ingreso = uuid_lib.uuid4()
    ctx = _make_ctx()
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_ingreso_por_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_activa_por_ingreso",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion por error administrativo",
        uuid_ingreso=uuid_ingreso,
        uuid_factura=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.create_reimpresion_ticket(
            response, payload, session, ctx, None
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "ingreso_no_encontrado"
    assert exc_info.value.detail["uuid_ingreso"] == str(uuid_ingreso)
    # DEC-TKT-06: error responses carry Cache-Control: no-store.
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    # V2/V4 must NOT have been reached.
    workflows_reimpresion_mod.repo_reimpresion.buscar_reimpresion_activa_por_ingreso.assert_not_called()
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_create_reimpresion_returns_409_reimpresion_already_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V2 409: chain tip exists for uuid_ingreso → 409 reimpresion_already_pending."""
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_ingreso = uuid_lib.uuid4()
    existing_reim_uuid = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    ingreso = _make_ingreso_orm(
        uuid_ingreso=uuid_ingreso, uuid_sucursal=uuid_sucursal
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_ingreso_por_uuid",
        AsyncMock(return_value=ingreso),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_activa_por_ingreso",
        AsyncMock(return_value={"uuid": existing_reim_uuid, "workflow_estado": "autorizada"}),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion por error administrativo",
        uuid_ingreso=uuid_ingreso,
        uuid_factura=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.create_reimpresion_ticket(
            response, payload, session, ctx, None
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "reimpresion_already_pending"
    assert exc_info.value.detail["uuid_ingreso"] == str(uuid_ingreso)
    assert exc_info.value.detail["uuid_reimpresion"] == str(existing_reim_uuid)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    # V3 + INSERT must NOT have been reached; no commit.
    workflows_reimpresion_mod.repo_reimpresion.buscar_factura_por_uuid.assert_not_called()
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_create_reimpresion_returns_404_factura_no_encontrada_when_uuid_factura_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V3 404: prod.facturas.uuid absent (when supplied) → 404 factura_no_encontrada."""
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_ingreso = uuid_lib.uuid4()
    uuid_factura = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    ingreso = _make_ingreso_orm(
        uuid_ingreso=uuid_ingreso, uuid_sucursal=uuid_sucursal
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_ingreso_por_uuid",
        AsyncMock(return_value=ingreso),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_activa_por_ingreso",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion con factura inexistente",
        uuid_ingreso=uuid_ingreso,
        uuid_factura=uuid_factura,
    )
    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.create_reimpresion_ticket(
            response, payload, session, ctx, None
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "factura_no_encontrada"
    assert exc_info.value.detail["uuid_factura"] == str(uuid_factura)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_create_reimpresion_returns_403_tenant_scope_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant scope (KD-S2 analog from F1.7): operador cross-branch → 403.

    The ctx sucursal_uuid differs from the ingreso's uuid_sucursal; the
    handler MUST raise 403 AFTER V1 succeeds (post-V1, DEC-TKT-06).
    """
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_ingreso = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    other_sucursal = uuid_lib.uuid4()
    ingreso = _make_ingreso_orm(
        uuid_ingreso=uuid_ingreso, uuid_sucursal=uuid_sucursal
    )

    ctx = _make_ctx(sucursal_uuid=other_sucursal, issuer_prefix="operador-")
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_ingreso_por_uuid",
        AsyncMock(return_value=ingreso),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_activa_por_ingreso",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion cross-branch",
        uuid_ingreso=uuid_ingreso,
        uuid_factura=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.create_reimpresion_ticket(
            response, payload, session, ctx, None
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    # V2 + V3 + INSERT must NOT have been reached.
    workflows_reimpresion_mod.repo_reimpresion.buscar_reimpresion_activa_por_ingreso.assert_not_called()
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0