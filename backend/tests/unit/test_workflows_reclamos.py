"""HU-F20.3 — POST /api/v1/workflows/reclamos (+ /{uuid}/transicion) tests.

Mock-everything pattern (no DB), mirrors ``test_workflows_anulaciones.py`` /
``test_workflows_alerta_descartar.py``. Asserts:

  - Root creation: permission gate (``registrar_reclamo``), INSERT via
    ``append_transition`` with ``estado='recibido'``, single commit,
    ``Cache-Control: no-store``.
  - Transition: V1 chain-tip via ``read_chain_tip``; ``ChainNotFoundError``
    -> 404. Tenant scope post-V1 (403 operador cross-branch). Permission
    gate: ``resolver_reclamo`` -> 403 if missing (SAME code for both
    ``recibido -> en_investigacion`` and ``en_investigacion -> {resuelto,
    rechazado}``, unlike anulaciones' per-step split).
    ``IllegalTransitionError`` from ``append_transition`` -> 409.
  - Pydantic schema: ``motivo`` mandatory/non-blank, extra='forbid'.

Real STATE_MACHINES names are used throughout (``recibido`` /
``en_investigacion`` / ``resuelto`` / ``rechazado`` — see
``workflows_reclamos.py`` module docstring for the drift vs plan.md's prose).
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
from parkos_core.schemas.workflows import (  # noqa: E402
    ReclamosSolicitarEndpoint,
    ReclamosTransicionEndpoint,
)
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


def _make_row(
    *,
    uuid: uuid_lib.UUID | None = None,
    uuid_sucursal: uuid_lib.UUID,
    estado: str,
    uuid_reclamo_padre: uuid_lib.UUID | None = None,
    tipo_reclamable: str = "ingreso",
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid or uuid_lib.uuid4()
    row.created_at = _now()
    row.created_by = uuid_lib.uuid4()
    row.sync_status = None
    row.sync_timestamp = None
    row.sync_attempts = None
    row.uuid_sucursal = uuid_sucursal
    row.tipo_reclamable = tipo_reclamable
    row.uuid_reclamable = uuid_lib.uuid4()
    row.motivo = "motivo de prueba"
    row.uuid_reclamo_padre = uuid_reclamo_padre
    row.timestamp_evento = _now()
    row.vigente_desde = _now()
    row.vigente_hasta = None
    row.estado = estado
    return row


# ---------------------------------------------------------------------------
# Schema-level validation
# ---------------------------------------------------------------------------


def test_solicitar_endpoint_rejects_blank_motivo() -> None:
    with pytest.raises(ValidationError):
        ReclamosSolicitarEndpoint(
            tipo_reclamable="ingreso", uuid_reclamable=uuid_lib.uuid4(), motivo=""
        )


def test_solicitar_endpoint_rejects_whitespace_only_motivo() -> None:
    with pytest.raises(ValidationError):
        ReclamosSolicitarEndpoint(
            tipo_reclamable="ingreso", uuid_reclamable=uuid_lib.uuid4(), motivo="   "
        )


def test_solicitar_endpoint_rejects_unknown_tipo_reclamable() -> None:
    with pytest.raises(ValidationError):
        ReclamosSolicitarEndpoint(
            tipo_reclamable="otro", uuid_reclamable=uuid_lib.uuid4(), motivo="ok"
        )


def test_solicitar_endpoint_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ReclamosSolicitarEndpoint(
            tipo_reclamable="ingreso",
            uuid_reclamable=uuid_lib.uuid4(),
            motivo="ok",
            estado="recibido",
        )


def test_transicion_endpoint_rejects_blank_motivo() -> None:
    with pytest.raises(ValidationError):
        ReclamosTransicionEndpoint(estado="en_investigacion", motivo="")


def test_transicion_endpoint_rejects_unknown_estado() -> None:
    with pytest.raises(ValidationError):
        ReclamosTransicionEndpoint(estado="recibido", motivo="ok")  # not a valid destination


# ---------------------------------------------------------------------------
# solicitar_reclamo handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_solicitar_reclamo_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import parkos_core.api.v1.workflows_reclamos as mod

    uuid_sucursal = uuid_lib.uuid4()
    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()
    new_row = _make_row(uuid_sucursal=uuid_sucursal, estado="recibido")

    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock(return_value=new_row))

    payload = ReclamosSolicitarEndpoint(
        tipo_reclamable="ingreso", uuid_reclamable=new_row.uuid_reclamable, motivo="Cobro doble"
    )
    result = await mod.solicitar_reclamo(response, payload, session, ctx, None)

    assert result.estado == "recibido"
    assert response.headers.get("Cache-Control") == "no-store"
    assert session.commit.await_count == 1

    append_kwargs = mod.repo_workflow.append_transition.call_args.kwargs
    assert append_kwargs["parent_uuid"] is None
    assert append_kwargs["parent_fk_column"] == "uuid_reclamo_padre"
    assert append_kwargs["new_attrs"]["estado"] == "recibido"


@pytest.mark.asyncio
async def test_solicitar_reclamo_returns_403_without_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_reclamos as mod

    ctx = _make_ctx()
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=False))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = ReclamosSolicitarEndpoint(
        tipo_reclamable="ingreso", uuid_reclamable=uuid_lib.uuid4(), motivo="ok"
    )
    with pytest.raises(HTTPException) as exc_info:
        await mod.solicitar_reclamo(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["detail"] == "registrar_reclamo"
    mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


# ---------------------------------------------------------------------------
# transicionar_reclamo handler
# ---------------------------------------------------------------------------


def _patch_tip(monkeypatch, mod, *, uuid_root, tip_row, estado):
    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        assert root_uuid == uuid_root
        assert parent_fk_column == "uuid_reclamo_padre"
        return {
            "uuid_root": uuid_root,
            "uuid_actual": tip_row.uuid,
            "estado": estado,
            "timestamp_evento": _now(),
            "chain_length": 1,
        }

    monkeypatch.setattr(mod.repo_workflow, "read_chain_tip", _read_chain_tip)


@pytest.mark.asyncio
async def test_transicionar_reclamo_happy_path_recibido_to_en_investigacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_reclamos as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="recibido")
    new_row = _make_row(
        uuid_sucursal=uuid_sucursal, estado="en_investigacion", uuid_reclamo_padre=uuid_root
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal, issuer_prefix="admin-")
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="recibido")
    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock(return_value=new_row))

    payload = ReclamosTransicionEndpoint(estado="en_investigacion", motivo="Tomado en revision")
    result = await mod.transicionar_reclamo(response, uuid_root, payload, session, ctx, None)

    assert result.estado == "en_investigacion"
    perm_call = mod.actor_has_permission.call_args.kwargs
    assert perm_call["codigo"] == "resolver_reclamo"


@pytest.mark.asyncio
async def test_transicionar_reclamo_happy_path_en_investigacion_to_resuelto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_reclamos as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="en_investigacion")
    new_row = _make_row(
        uuid_sucursal=uuid_sucursal, estado="resuelto", uuid_reclamo_padre=uuid_root
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal, issuer_prefix="admin-")
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="en_investigacion")
    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock(return_value=new_row))

    payload = ReclamosTransicionEndpoint(estado="resuelto", motivo="Reembolso aplicado")
    result = await mod.transicionar_reclamo(response, uuid_root, payload, session, ctx, None)

    assert result.estado == "resuelto"


@pytest.mark.asyncio
async def test_transicionar_reclamo_returns_403_without_resolver_reclamo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_reclamos as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="recibido")

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="recibido")
    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=False))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = ReclamosTransicionEndpoint(estado="en_investigacion", motivo="Sin permiso")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_reclamo(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["detail"] == "resolver_reclamo"
    mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_transicionar_reclamo_returns_409_illegal_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tip is 'recibido', client requests 'resuelto' directly (skipping
    'en_investigacion') -> IllegalTransitionError -> 409."""
    import parkos_core.api.v1.workflows_reclamos as mod
    from parkos_core.repo import workflow as repo_workflow_mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="recibido")

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="recibido")
    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))

    async def _append_transition_raises(*args, **kwargs):
        raise repo_workflow_mod.IllegalTransitionError(
            "Illegal transition for reclamos: 'recibido' -> 'resuelto'."
        )

    monkeypatch.setattr(mod.repo_workflow, "append_transition", _append_transition_raises)

    payload = ReclamosTransicionEndpoint(estado="resuelto", motivo="Salto invalido")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_reclamo(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "illegal_transition"
    assert exc_info.value.detail["estado_actual"] == "recibido"
    assert exc_info.value.detail["estado_solicitado"] == "resuelto"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_transicionar_reclamo_returns_404_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_reclamos as mod
    from parkos_core.repo import workflow as repo_workflow_mod

    uuid_root = uuid_lib.uuid4()
    ctx = _make_ctx()
    session = AsyncMock()
    response = _new_response()

    async def _read_chain_tip_raises(session, model_cls, *, root_uuid, parent_fk_column):
        raise repo_workflow_mod.ChainNotFoundError(f"root row {root_uuid} not found")

    monkeypatch.setattr(mod.repo_workflow, "read_chain_tip", _read_chain_tip_raises)
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = ReclamosTransicionEndpoint(estado="en_investigacion", motivo="No existe")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_reclamo(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "reclamo_not_found"
    mod.repo_workflow.append_transition.assert_not_called()


@pytest.mark.asyncio
async def test_transicionar_reclamo_returns_403_tenant_scope_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_reclamos as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    other_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="recibido")

    ctx = _make_ctx(sucursal_uuid=other_sucursal, issuer_prefix="operador-")
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="recibido")
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = ReclamosTransicionEndpoint(estado="en_investigacion", motivo="Cruce de sucursal")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_reclamo(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    mod.repo_workflow.append_transition.assert_not_called()
