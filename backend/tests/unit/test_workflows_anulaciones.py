"""HU-F20.3 — POST /api/v1/workflows/anulaciones (+ /{uuid}/transicion) tests.

Mock-everything pattern (no DB), mirrors ``test_workflows_alerta_descartar.py``
/ ``test_reimpresion_ticket_create_handler.py``. Asserts:

  - Root creation: permission gate (``anular_ingreso_salida``), INSERT via
    ``append_transition`` with ``estado='iniciada'``, single commit,
    ``Cache-Control: no-store``.
  - Transition: V1 chain-tip via ``read_chain_tip``; ``ChainNotFoundError``
    -> 404. Tenant scope post-V1 (403 operador cross-branch). Permission
    gate resolved from the tip's CURRENT estado (``aprobar_anulacion`` from
    ``iniciada``, ``ejecutar_anulacion`` from ``autorizada``) -> 403 if
    missing, INCLUDING the "has the other step's permission but not this
    one" case the HU calls out explicitly. ``IllegalTransitionError`` from
    ``append_transition`` -> 409.
  - Pydantic schema: ``motivo`` mandatory/non-blank, polymorphic
    tipo_anulable/uuid_ingreso/uuid_salida cross-field guard, extra='forbid'.

Real STATE_MACHINES names are used throughout (``iniciada`` / ``autorizada``
/ ``ejecutada`` / ``rechazada`` — see ``workflows_anulaciones.py`` module
docstring for the drift vs plan.md's prose).
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
    AnulacionesSolicitarEndpoint,
    AnulacionesTransicionEndpoint,
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
    uuid_anulacion_padre: uuid_lib.UUID | None = None,
    tipo_anulable: str = "ingreso",
    uuid_ingreso: uuid_lib.UUID | None = None,
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid or uuid_lib.uuid4()
    row.fecha_retencion_hasta = _now().date()
    row.created_at = _now()
    row.created_by = uuid_lib.uuid4()
    row.sync_status = None
    row.sync_timestamp = None
    row.sync_attempts = None
    row.uuid_sucursal = uuid_sucursal
    row.tipo_anulable = tipo_anulable
    row.uuid_ingreso = uuid_ingreso or uuid_lib.uuid4()
    row.uuid_salida = None
    row.uuid_usuario = uuid_lib.uuid4()
    row.motivo = "motivo de prueba"
    row.uuid_anulacion_padre = uuid_anulacion_padre
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
        AnulacionesSolicitarEndpoint(
            tipo_anulable="ingreso", uuid_ingreso=uuid_lib.uuid4(), motivo=""
        )


def test_solicitar_endpoint_rejects_whitespace_only_motivo() -> None:
    with pytest.raises(ValidationError):
        AnulacionesSolicitarEndpoint(
            tipo_anulable="ingreso", uuid_ingreso=uuid_lib.uuid4(), motivo="   "
        )


def test_solicitar_endpoint_rejects_mismatched_tipo_anulable() -> None:
    """tipo_anulable='ingreso' but only uuid_salida supplied -> 422."""
    with pytest.raises(ValidationError):
        AnulacionesSolicitarEndpoint(
            tipo_anulable="ingreso", uuid_salida=uuid_lib.uuid4(), motivo="ok"
        )


def test_solicitar_endpoint_rejects_both_uuid_ingreso_and_salida() -> None:
    with pytest.raises(ValidationError):
        AnulacionesSolicitarEndpoint(
            tipo_anulable="ingreso",
            uuid_ingreso=uuid_lib.uuid4(),
            uuid_salida=uuid_lib.uuid4(),
            motivo="ok",
        )


def test_solicitar_endpoint_accepts_valid_payload() -> None:
    payload = AnulacionesSolicitarEndpoint(
        tipo_anulable="salida", uuid_salida=uuid_lib.uuid4(), motivo="Cliente desistio"
    )
    assert payload.motivo == "Cliente desistio"


def test_solicitar_endpoint_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AnulacionesSolicitarEndpoint(
            tipo_anulable="ingreso",
            uuid_ingreso=uuid_lib.uuid4(),
            motivo="ok",
            estado="iniciada",
        )


def test_transicion_endpoint_rejects_blank_motivo() -> None:
    with pytest.raises(ValidationError):
        AnulacionesTransicionEndpoint(estado="autorizada", motivo="")


def test_transicion_endpoint_rejects_unknown_estado() -> None:
    with pytest.raises(ValidationError):
        AnulacionesTransicionEndpoint(estado="iniciada", motivo="ok")  # not a valid destination


# ---------------------------------------------------------------------------
# solicitar_anulacion handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_solicitar_anulacion_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import parkos_core.api.v1.workflows_anulaciones as mod

    uuid_sucursal = uuid_lib.uuid4()
    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    response = _new_response()
    new_row = _make_row(uuid_sucursal=uuid_sucursal, estado="iniciada")

    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock(return_value=new_row))

    payload = AnulacionesSolicitarEndpoint(
        tipo_anulable="ingreso", uuid_ingreso=new_row.uuid_ingreso, motivo="Cliente desistio"
    )
    result = await mod.solicitar_anulacion(response, payload, session, ctx, None)

    assert result.estado == "iniciada"
    assert response.headers.get("Cache-Control") == "no-store"
    assert session.commit.await_count == 1

    append_kwargs = mod.repo_workflow.append_transition.call_args.kwargs
    assert append_kwargs["parent_uuid"] is None
    assert append_kwargs["parent_fk_column"] == "uuid_anulacion_padre"
    assert append_kwargs["new_attrs"]["estado"] == "iniciada"
    assert append_kwargs["new_attrs"]["uuid_usuario"] == ctx.actor_uuid


@pytest.mark.asyncio
async def test_solicitar_anulacion_returns_403_without_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_anulaciones as mod

    ctx = _make_ctx()
    session = AsyncMock()
    response = _new_response()

    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=False))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = AnulacionesSolicitarEndpoint(
        tipo_anulable="ingreso", uuid_ingreso=uuid_lib.uuid4(), motivo="ok"
    )
    with pytest.raises(HTTPException) as exc_info:
        await mod.solicitar_anulacion(response, payload, session, ctx, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["detail"] == "anular_ingreso_salida"
    mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


# ---------------------------------------------------------------------------
# transicionar_anulacion handler
# ---------------------------------------------------------------------------


def _patch_tip(monkeypatch, mod, *, uuid_root, tip_row, estado):
    async def _read_chain_tip(session, model_cls, *, root_uuid, parent_fk_column):
        assert root_uuid == uuid_root
        assert parent_fk_column == "uuid_anulacion_padre"
        return {
            "uuid_root": uuid_root,
            "uuid_actual": tip_row.uuid,
            "estado": estado,
            "timestamp_evento": _now(),
            "chain_length": 1,
        }

    monkeypatch.setattr(mod.repo_workflow, "read_chain_tip", _read_chain_tip)


@pytest.mark.asyncio
async def test_transicionar_anulacion_happy_path_iniciada_to_autorizada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_anulaciones as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="iniciada")
    new_row = _make_row(
        uuid_sucursal=uuid_sucursal, estado="autorizada", uuid_anulacion_padre=uuid_root
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="iniciada")
    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock(return_value=new_row))

    payload = AnulacionesTransicionEndpoint(estado="autorizada", motivo="Revisado por admin")
    result = await mod.transicionar_anulacion(response, uuid_root, payload, session, ctx, None)

    assert result.estado == "autorizada"
    assert session.commit.await_count == 1
    perm_call = mod.actor_has_permission.call_args.kwargs
    assert perm_call["codigo"] == "aprobar_anulacion"


@pytest.mark.asyncio
async def test_transicionar_anulacion_happy_path_autorizada_to_ejecutada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_anulaciones as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="autorizada")
    new_row = _make_row(
        uuid_sucursal=uuid_sucursal, estado="ejecutada", uuid_anulacion_padre=uuid_root
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal, issuer_prefix="admin-")
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="autorizada")
    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock(return_value=new_row))

    payload = AnulacionesTransicionEndpoint(estado="ejecutada", motivo="Anulacion ejecutada")
    result = await mod.transicionar_anulacion(response, uuid_root, payload, session, ctx, None)

    assert result.estado == "ejecutada"
    perm_call = mod.actor_has_permission.call_args.kwargs
    assert perm_call["codigo"] == "ejecutar_anulacion"


@pytest.mark.asyncio
async def test_transicionar_anulacion_returns_403_has_aprobar_but_not_ejecutar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HU's explicit example: actor holds 'aprobar_anulacion' but the tip is
    already 'autorizada' (needs 'ejecutar_anulacion') -> 403, no INSERT."""
    import parkos_core.api.v1.workflows_anulaciones as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="autorizada")

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="autorizada")

    async def _actor_has_permission(session, *, actor_uuid, codigo):
        # Actor holds ONLY 'aprobar_anulacion', not 'ejecutar_anulacion'.
        return codigo == "aprobar_anulacion"

    monkeypatch.setattr(mod, "actor_has_permission", _actor_has_permission)
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = AnulacionesTransicionEndpoint(estado="ejecutada", motivo="Intento no autorizado")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_anulacion(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["detail"] == "ejecutar_anulacion"
    mod.repo_workflow.append_transition.assert_not_called()
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_transicionar_anulacion_returns_409_illegal_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tip is 'iniciada', client requests 'ejecutada' directly -> IllegalTransitionError -> 409."""
    import parkos_core.api.v1.workflows_anulaciones as mod
    from parkos_core.repo import workflow as repo_workflow_mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="iniciada")

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="iniciada")
    monkeypatch.setattr(mod, "actor_has_permission", AsyncMock(return_value=True))

    async def _append_transition_raises(*args, **kwargs):
        raise repo_workflow_mod.IllegalTransitionError(
            "Illegal transition for anulaciones: 'iniciada' -> 'ejecutada'."
        )

    monkeypatch.setattr(mod.repo_workflow, "append_transition", _append_transition_raises)

    payload = AnulacionesTransicionEndpoint(estado="ejecutada", motivo="Salto invalido")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_anulacion(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "illegal_transition"
    assert exc_info.value.detail["estado_actual"] == "iniciada"
    assert exc_info.value.detail["estado_solicitado"] == "ejecutada"
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_transicionar_anulacion_returns_404_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_anulaciones as mod
    from parkos_core.repo import workflow as repo_workflow_mod

    uuid_root = uuid_lib.uuid4()
    ctx = _make_ctx()
    session = AsyncMock()
    response = _new_response()

    async def _read_chain_tip_raises(session, model_cls, *, root_uuid, parent_fk_column):
        raise repo_workflow_mod.ChainNotFoundError(f"root row {root_uuid} not found")

    monkeypatch.setattr(mod.repo_workflow, "read_chain_tip", _read_chain_tip_raises)
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = AnulacionesTransicionEndpoint(estado="autorizada", motivo="No existe")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_anulacion(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "anulacion_not_found"
    mod.repo_workflow.append_transition.assert_not_called()


@pytest.mark.asyncio
async def test_transicionar_anulacion_returns_403_tenant_scope_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_anulaciones as mod

    uuid_root = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    other_sucursal = uuid_lib.uuid4()
    tip_row = _make_row(uuid=uuid_root, uuid_sucursal=uuid_sucursal, estado="iniciada")

    ctx = _make_ctx(sucursal_uuid=other_sucursal, issuer_prefix="operador-")
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=tip_row))
    )
    response = _new_response()

    _patch_tip(monkeypatch, mod, uuid_root=uuid_root, tip_row=tip_row, estado="iniciada")
    monkeypatch.setattr(mod.repo_workflow, "append_transition", AsyncMock())

    payload = AnulacionesTransicionEndpoint(estado="autorizada", motivo="Cruce de sucursal")
    with pytest.raises(HTTPException) as exc_info:
        await mod.transicionar_anulacion(response, uuid_root, payload, session, ctx, None)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    mod.repo_workflow.append_transition.assert_not_called()
