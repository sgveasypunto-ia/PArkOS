"""HU-F1.11 / T4.3 — POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular tests.

F1.10 mock-everything pattern (no DB). Asserts:
  - V1 chain-tip via ``read_chain_tip`` (F1.5 PR5-016 reuse)
  - Tenant scope post-V1 (KD-S2)
  - V2 chain tip state guard (409 anulacion_no_permitida if rechazada)
  - DEC-TKT-03: INSERT NEW row via append_transition (NEVER UPDATE on tip)
  - KD-TKT-01 single-commit on the happy path
  - DEC-TKT-06 Cache-Control: no-store header on every response
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
from parkos_core.schemas.workflows import ReimpresionTicketAnularEndpoint  # noqa: E402


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


def _make_tip_orm(
    *,
    uuid_tip: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    estado_bitemporal: str = "activo",
    motivo: str = "Reimpresion autorizada previa",
) -> MagicMock:
    tip = MagicMock()
    tip.uuid = uuid_tip
    tip.uuid_sucursal = uuid_sucursal
    tip.uuid_ingreso = uuid_ingreso
    tip.uuid_usuario = uuid_lib.uuid4()
    tip.uuid_costo_servicio = None
    tip.costo_aplicado = None
    tip.uuid_factura = None
    tip.motivo = motivo
    tip.uuid_reimpresion_padre = None
    tip.timestamp_evento = _now()
    tip.vigente_desde = _now()
    tip.vigente_hasta = None
    tip.estado = estado_bitemporal
    tip.motivo_anulacion = None
    return tip


def _make_new_rechazada_orm(
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    uuid_reimpresion_padre: uuid_lib.UUID,
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
    row.uuid_factura = None
    row.motivo = "Cliente solicito anulacion por error administrativo"
    row.motivo_anulacion = "Cliente solicito anulacion por error administrativo"
    row.uuid_reimpresion_padre = uuid_reimpresion_padre
    row.timestamp_evento = _now()
    row.vigente_desde = _now()
    row.vigente_hasta = None
    row.estado = "activo"
    return row


# ---------------------------------------------------------------------------
# T4.3 — happy path + V1..V3 error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anular_reimpresion_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: chain tip 'autorizada' → INSERT NEW 'rechazada' row.

    Asserts:
      - response.workflow_estado == 'rechazada'
      - response.uuid_reimpresion_padre == tip.uuid (chain link)
      - session.commit() called exactly once (KD-TKT-01)
      - Cache-Control: no-store header
    """
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_root = uuid_lib.uuid4()
    uuid_tip = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    uuid_ingreso = uuid_lib.uuid4()
    tip = _make_tip_orm(
        uuid_tip=uuid_tip,
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
    )
    new_row = _make_new_rechazada_orm(
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
        uuid_reimpresion_padre=uuid_tip,
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()

    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        assert root_uuid == uuid_root
        assert parent_fk_column == "uuid_reimpresion_padre"
        return {
            "uuid_root": uuid_root,
            "uuid_actual": uuid_tip,
            # BUGFIX (2026-09-25): `read_chain_tip` (repo/workflow.py) has
            # NO `workflow_estado` key -- its real shape is `{uuid_root,
            # uuid_actual, estado, timestamp_evento, chain_length}`, and
            # for `reimpresion_ticket` the per-table `estado` cycle IS
            # 'autorizada'/'rechazada' (not the generic 'activo'/
            # 'inactivo'). This fake previously encoded the same
            # misreading the handler had (`tip["workflow_estado"]`),
            # which masked the real `KeyError: 'workflow_estado'` 500.
            "estado": "autorizada",
            "timestamp_evento": _now(),
            "chain_length": 1,
        }

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "read_chain_tip",
        _read_chain_tip,
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_por_uuid",
        AsyncMock(return_value=tip),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=new_row),
    )

    payload = ReimpresionTicketAnularEndpoint(
        motivo_anulacion="Cliente solicito anulacion por error administrativo",
    )
    result = await workflows_reimpresion_mod.anular_reimpresion_ticket(
        response, uuid_root, payload, session, ctx, None
    )

    assert result.uuid == new_row.uuid
    assert result.workflow_estado == "rechazada"
    assert result.uuid_reimpresion_padre == uuid_tip
    assert result.motivo_anulacion == "Cliente solicito anulacion por error administrativo"
    assert response.headers.get("Cache-Control") == "no-store"
    # KD-TKT-01 single-commit invariant.
    assert session.commit.await_count == 1
    # DEC-TKT-03: append_transition called with parent_uuid=tip.uuid.
    append_kwargs = workflows_reimpresion_mod.repo_workflow.append_transition.call_args.kwargs
    assert append_kwargs["parent_uuid"] == uuid_tip
    assert append_kwargs["parent_fk_column"] == "uuid_reimpresion_padre"


@pytest.mark.asyncio
async def test_anular_reimpresion_returns_409_anulacion_no_permitida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V2 409: chain tip 'rechazada' → 409 anulacion_no_permitida.

    Asserts:
      - 409 status_code + discriminator
      - NO INSERT, NO commit
    """
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_root = uuid_lib.uuid4()
    uuid_tip = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    uuid_ingreso = uuid_lib.uuid4()
    tip = _make_tip_orm(
        uuid_tip=uuid_tip,
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()

    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        return {
            "uuid_root": uuid_root,
            "uuid_actual": uuid_tip,
            "estado": "rechazada",  # terminal
            "timestamp_evento": _now(),
            "chain_length": 1,
        }

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "read_chain_tip",
        _read_chain_tip,
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_por_uuid",
        AsyncMock(return_value=tip),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = ReimpresionTicketAnularEndpoint(
        motivo_anulacion="Cliente solicito anulacion por error administrativo",
    )
    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.anular_reimpresion_ticket(
            response, uuid_root, payload, session, ctx, None
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "anulacion_no_permitida"
    assert exc_info.value.detail["estado_actual"] == "rechazada"
    assert exc_info.value.detail["uuid_reimpresion"] == str(uuid_root)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_anular_reimpresion_returns_404_reimpresion_no_encontrada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V1 404: ChainNotFoundError → 404 reimpresion_not_found."""
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod
    from parkos_core.repo import workflow as repo_workflow_mod

    uuid_root = uuid_lib.uuid4()
    ctx = _make_ctx()
    session = AsyncMock()
    response = _new_response()

    async def _read_chain_tip_raises(session, model_cls, *, root_uuid, parent_fk_column):
        raise repo_workflow_mod.ChainNotFoundError(
            f"root row {root_uuid} not found in reimpresion_ticket"
        )

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "read_chain_tip",
        _read_chain_tip_raises,
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_por_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = ReimpresionTicketAnularEndpoint(
        motivo_anulacion="Cliente solicito anulacion por error administrativo",
    )
    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.anular_reimpresion_ticket(
            response, uuid_root, payload, session, ctx, None
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "reimpresion_not_found"
    assert exc_info.value.detail["uuid_reimpresion"] == str(uuid_root)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    workflows_reimpresion_mod.repo_reimpresion.buscar_reimpresion_por_uuid.assert_not_called()
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_anular_reimpresion_returns_403_tenant_scope_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant scope (KD-S2): operador cross-branch → 403.

    ctx.sucursal_uuid differs from the chain tip's uuid_sucursal.
    """
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod

    uuid_root = uuid_lib.uuid4()
    uuid_tip = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    other_sucursal = uuid_lib.uuid4()
    uuid_ingreso = uuid_lib.uuid4()
    tip = _make_tip_orm(
        uuid_tip=uuid_tip,
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
    )

    ctx = _make_ctx(sucursal_uuid=other_sucursal, issuer_prefix="operador-")
    session = AsyncMock()
    response = _new_response()

    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        return {
            "uuid_root": uuid_root,
            "uuid_actual": uuid_tip,
            "estado": "autorizada",
            "timestamp_evento": _now(),
            "chain_length": 1,
        }

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "read_chain_tip",
        _read_chain_tip,
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_por_uuid",
        AsyncMock(return_value=tip),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = ReimpresionTicketAnularEndpoint(
        motivo_anulacion="Cliente solicito anulacion por error administrativo",
    )
    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.anular_reimpresion_ticket(
            response, uuid_root, payload, session, ctx, None
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0