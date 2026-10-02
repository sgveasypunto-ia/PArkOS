"""HU-F19.4 — POST /api/v1/workflows/alerta/{uuid}/descartar tests.

Mock-everything pattern (no DB), mirrors
``test_reimpresion_ticket_anular_handler.py`` (HU-F1.11 / DEC-TKT-06
precedent for a custom ``[L-W]`` transition endpoint). Asserts:

  - V1 chain-tip via ``read_chain_tip``; ``ChainNotFoundError`` -> 404
  - Tenant scope post-V1 (403 operador cross-branch)
  - V2 terminal-state guard (409 ``alerta_ya_resuelta`` if already 'resuelta')
  - INSERT NEW row via ``append_transition`` (NEVER UPDATE on tip)
  - single-commit on the happy path
  - ``Cache-Control: no-store`` header on every response
  - ``observaciones`` persisted into ``datos_nuevos`` (no dedicated column)
  - Pydantic schema rejects blank/whitespace-only ``observaciones`` (422)
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
from parkos_core.schemas.workflows import AlertaDescartarEndpoint  # noqa: E402
from pydantic import ValidationError  # noqa: E402


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


def _make_tip_row(
    *,
    uuid_tip: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    tipo_alerta: str = "descuadre_critico",
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_tip
    row.uuid_sucursal = uuid_sucursal
    row.uuid_usuario = uuid_lib.uuid4()
    row.uuid_arqueo = uuid_lib.uuid4()
    row.tipo_alerta = tipo_alerta
    row.valor_diferencia_efectivo = None
    row.valor_diferencia_datafono = None
    row.uuid_alerta_padre = None
    row.timestamp_evento = _now()
    row.datos_nuevos = None
    row.vigente_desde = _now()
    row.vigente_hasta = None
    row.estado = "abierta"
    return row


def _make_new_resuelta_row(
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_alerta_padre: uuid_lib.UUID,
    observaciones: str,
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.fecha_retencion_hasta = _now().date()
    row.created_at = _now()
    row.created_by = uuid_lib.uuid4()
    row.sync_status = None
    row.sync_timestamp = None
    row.sync_attempts = None
    row.uuid_sucursal = uuid_sucursal
    row.uuid_usuario = uuid_lib.uuid4()
    row.uuid_arqueo = uuid_lib.uuid4()
    row.tipo_alerta = "descuadre_critico"
    row.valor_diferencia_efectivo = None
    row.valor_diferencia_datafono = None
    row.uuid_alerta_padre = uuid_alerta_padre
    row.timestamp_evento = _now()
    row.datos_nuevos = {"observaciones": observaciones}
    row.vigente_desde = _now()
    row.vigente_hasta = None
    row.estado = "resuelta"
    return row


# ---------------------------------------------------------------------------
# Schema-level validation — observaciones mandatory and non-blank
# ---------------------------------------------------------------------------


def test_descartar_endpoint_rejects_blank_observaciones() -> None:
    with pytest.raises(ValidationError):
        AlertaDescartarEndpoint(observaciones="")


def test_descartar_endpoint_rejects_whitespace_only_observaciones() -> None:
    with pytest.raises(ValidationError):
        AlertaDescartarEndpoint(observaciones="   ")


def test_descartar_endpoint_accepts_non_blank_observaciones() -> None:
    payload = AlertaDescartarEndpoint(observaciones="Conteo verificado manualmente")
    assert payload.observaciones == "Conteo verificado manualmente"


def test_descartar_endpoint_rejects_extra_fields() -> None:
    """extra='forbid' (inherited from _Base) rejects smuggled estado/padre."""
    with pytest.raises(ValidationError):
        AlertaDescartarEndpoint(observaciones="ok", estado="resuelta")


# ---------------------------------------------------------------------------
# Handler — happy path + V1..V2 error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_descartar_alerta_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: chain tip 'abierta' -> INSERT NEW 'resuelta' row.

    Asserts:
      - response.estado == 'resuelta'
      - response uuid_alerta_padre == tip.uuid (chain link)
      - session.commit() called exactly once
      - Cache-Control: no-store header
      - append_transition new_attrs carries observaciones via datos_nuevos
    """
    import parkos_core.api.v1.workflows_alerta as workflows_alerta_mod

    uuid_root = uuid_lib.uuid4()
    uuid_tip = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_tip_row(uuid_tip=uuid_tip, uuid_sucursal=uuid_sucursal)
    observaciones = "Conteo verificado manualmente, diferencia justificada"
    new_row = _make_new_resuelta_row(
        uuid_sucursal=uuid_sucursal,
        uuid_alerta_padre=uuid_tip,
        observaciones=observaciones,
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        assert root_uuid == uuid_root
        assert parent_fk_column == "uuid_alerta_padre"
        return {
            "uuid_root": uuid_root,
            "uuid_actual": uuid_tip,
            "estado": "abierta",
            "timestamp_evento": _now(),
            "chain_length": 1,
        }

    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow, "read_chain_tip", _read_chain_tip
    )
    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=new_row),
    )

    payload = AlertaDescartarEndpoint(observaciones=observaciones)
    result = await workflows_alerta_mod.descartar_alerta(
        response, uuid_root, payload, session, ctx, None, None
    )

    assert result.uuid == new_row.uuid
    assert result.estado == "resuelta"
    assert result.uuid_alerta_padre == uuid_tip
    assert response.headers.get("Cache-Control") == "no-store"
    assert session.commit.await_count == 1

    append_kwargs = workflows_alerta_mod.repo_workflow.append_transition.call_args.kwargs
    assert append_kwargs["parent_uuid"] == uuid_tip
    assert append_kwargs["parent_fk_column"] == "uuid_alerta_padre"
    assert append_kwargs["new_attrs"]["estado"] == "resuelta"
    assert append_kwargs["new_attrs"]["datos_nuevos"] == {"observaciones": observaciones}
    assert append_kwargs["new_attrs"]["uuid_usuario"] == ctx.actor_uuid


@pytest.mark.asyncio
async def test_descartar_alerta_returns_409_ya_resuelta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V2 409: chain tip 'resuelta' (terminal) -> 409 alerta_ya_resuelta.

    Asserts no INSERT, no commit.
    """
    import parkos_core.api.v1.workflows_alerta as workflows_alerta_mod

    uuid_root = uuid_lib.uuid4()
    uuid_tip = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_tip_row(uuid_tip=uuid_tip, uuid_sucursal=uuid_sucursal)
    tip_row.estado = "resuelta"

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        return {
            "uuid_root": uuid_root,
            "uuid_actual": uuid_tip,
            "estado": "resuelta",  # terminal
            "timestamp_evento": _now(),
            "chain_length": 2,
        }

    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow, "read_chain_tip", _read_chain_tip
    )
    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = AlertaDescartarEndpoint(observaciones="Intento repetido")
    with pytest.raises(HTTPException) as exc_info:
        await workflows_alerta_mod.descartar_alerta(
            response, uuid_root, payload, session, ctx, None, None
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "alerta_ya_resuelta"
    assert exc_info.value.detail["uuid"] == str(uuid_root)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    workflows_alerta_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_descartar_alerta_returns_404_alerta_no_encontrada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V1 404: ChainNotFoundError -> 404 alerta_not_found."""
    import parkos_core.api.v1.workflows_alerta as workflows_alerta_mod
    from parkos_core.repo import workflow as repo_workflow_mod

    uuid_root = uuid_lib.uuid4()
    ctx = _make_ctx()
    session = AsyncMock()
    response = _new_response()

    async def _read_chain_tip_raises(session, model_cls, *, root_uuid, parent_fk_column):
        raise repo_workflow_mod.ChainNotFoundError(
            f"root row {root_uuid} not found in alerta"
        )

    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow, "read_chain_tip", _read_chain_tip_raises
    )
    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = AlertaDescartarEndpoint(observaciones="No existe")
    with pytest.raises(HTTPException) as exc_info:
        await workflows_alerta_mod.descartar_alerta(
            response, uuid_root, payload, session, ctx, None, None
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "alerta_not_found"
    assert exc_info.value.detail["uuid"] == str(uuid_root)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    workflows_alerta_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_descartar_alerta_returns_403_tenant_scope_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tenant scope: operador cross-branch -> 403."""
    import parkos_core.api.v1.workflows_alerta as workflows_alerta_mod

    uuid_root = uuid_lib.uuid4()
    uuid_tip = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    other_sucursal = uuid_lib.uuid4()
    tip_row = _make_tip_row(uuid_tip=uuid_tip, uuid_sucursal=uuid_sucursal)

    ctx = _make_ctx(sucursal_uuid=other_sucursal, issuer_prefix="operador-")
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        return {
            "uuid_root": uuid_root,
            "uuid_actual": uuid_tip,
            "estado": "abierta",
            "timestamp_evento": _now(),
            "chain_length": 1,
        }

    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow, "read_chain_tip", _read_chain_tip
    )
    monkeypatch.setattr(
        workflows_alerta_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=None),
    )

    payload = AlertaDescartarEndpoint(observaciones="Cruce de sucursal")
    with pytest.raises(HTTPException) as exc_info:
        await workflows_alerta_mod.descartar_alerta(
            response, uuid_root, payload, session, ctx, None, None
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    workflows_alerta_mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0
