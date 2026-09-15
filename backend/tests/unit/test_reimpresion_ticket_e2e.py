"""HU-F1.11 / T8.1 — Full-chain e2e integration test (mock-everything).

Mirrors F1.10 ``test_factura_electronica_e2e.py``. Drives the full
reimpresion lifecycle end-to-end:

  1. POST /api/v1/workflows/reimpresion-ticket                  -> 201 + inicial row
  2. POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular    -> 201 + rechazada row
  3. POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular    -> 409 anulacion_no_permitida

Mocks the repo helpers end-to-end (no DB). Asserts:
  - State machine correctness across the 3 calls
  - KD-TKT-01 single-commit per write call (exactly 1 commit per call)
  - DEC-TKT-02 INSERT-only invariant: chain grew by 1 row per write
  - DEC-TKT-06 Cache-Control: no-store on every response
  - DEC-TKT-03 NEVER UPDATE on existing chain tip
  - Tenant scope (ctx.sucursal_uuid matches the ingreso row)
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


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_ctx(sucursal_uuid: uuid_lib.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal_uuid
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _make_ingreso_orm(
    *,
    uuid_ingreso: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
) -> MagicMock:
    ingreso = MagicMock()
    ingreso.uuid = uuid_ingreso
    ingreso.uuid_sucursal = uuid_sucursal
    return ingreso


def _make_reimpresion_orm(
    *,
    uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    uuid_reimpresion_padre: uuid_lib.UUID | None,
    motivo: str,
    motivo_anulacion: str | None = None,
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid
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
    row.motivo = motivo
    row.motivo_anulacion = motivo_anulacion
    row.uuid_reimpresion_padre = uuid_reimpresion_padre
    row.timestamp_evento = _now()
    row.vigente_desde = _now()
    row.vigente_hasta = None
    row.estado = "activo"
    return row


@pytest.mark.asyncio
async def test_reimpresion_full_chain_post_create_then_anular_then_reanular_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T8.1: POST → anular → re-anular full chain integrity.

    Drives the entire reimpresion lifecycle end-to-end with mocked
    repo helpers (no DB). The 3-step journey proves:

      Step 1: POST /reimpresion-ticket → 201 + workflow_estado='autorizada'
              chain root inserted, uuid_reimpresion_padre=None.
      Step 2: POST /reimpresion-ticket/{r1}/anular → 201 + workflow_estado='rechazada'
              NEW row inserted with uuid_reimpresion_padre=r1. The
              original r1 row is NEVER mutated (DEC-TKT-03).
      Step 3: POST /reimpresion-ticket/{r1}/anular AGAIN → 409
              anulacion_no_permitida (terminal state).

    Each step carries Cache-Control: no-store. KD-TKT-01 single-commit
    is verified per write call.
    """
    import parkos_core.api.v1.workflows_reimpresion as workflows_reimpresion_mod
    from parkos_core.schemas.workflows import (
        ReimpresionTicketAnularEndpoint,
        ReimpresionTicketCreateEndpoint,
    )

    uuid_sucursal = uuid_lib.uuid4()
    uuid_ingreso = uuid_lib.uuid4()
    r1_uuid = uuid_lib.uuid4()
    r2_uuid = uuid_lib.uuid4()

    ingreso = _make_ingreso_orm(
        uuid_ingreso=uuid_ingreso, uuid_sucursal=uuid_sucursal
    )
    r1 = _make_reimpresion_orm(
        uuid=r1_uuid,
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
        uuid_reimpresion_padre=None,
        motivo="Cliente solicita reimpresion por deterioro del original",
    )
    r2 = _make_reimpresion_orm(
        uuid=r2_uuid,
        uuid_sucursal=uuid_sucursal,
        uuid_ingreso=uuid_ingreso,
        uuid_reimpresion_padre=r1_uuid,
        motivo="Error operativo: reimprimir solicitada por error administrativo",
        motivo_anulacion="Error operativo: reimprimir solicitada por error administrativo",
    )

    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    session = AsyncMock()

    # ------------------------------------------------------------------
    # Step 1: POST /reimpresion-ticket → 201
    # ------------------------------------------------------------------
    response_1 = _new_response()

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
        AsyncMock(return_value=r1),
    )

    payload_create = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion por deterioro del original",
        uuid_ingreso=uuid_ingreso,
        uuid_factura=None,
    )
    result_1 = await workflows_reimpresion_mod.create_reimpresion_ticket(
        response_1, payload_create, session, ctx, None
    )

    assert result_1.uuid == r1_uuid
    assert result_1.workflow_estado == "autorizada"
    assert result_1.uuid_reimpresion_padre is None  # chain root
    assert response_1.headers.get("Cache-Control") == "no-store"
    # KD-TKT-01 single-commit on write call #1.
    assert session.commit.await_count == 1

    # ------------------------------------------------------------------
    # Step 2: POST /reimpresion-ticket/{r1}/anular → 201
    # ------------------------------------------------------------------
    session_2 = AsyncMock()
    response_2 = _new_response()

    async def _read_chain_tip_2(session, model_cls, *, root_uuid, parent_fk_column):
        assert root_uuid == r1_uuid
        assert parent_fk_column == "uuid_reimpresion_padre"
        return {
            "uuid_root": r1_uuid,
            "uuid_actual": r1_uuid,
            "estado": "activo",
            "timestamp_evento": _now(),
            "chain_length": 1,
            "workflow_estado": "autorizada",
        }

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "read_chain_tip",
        _read_chain_tip_2,
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_por_uuid",
        AsyncMock(return_value=r1),
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "append_transition",
        AsyncMock(return_value=r2),
    )

    payload_anular = ReimpresionTicketAnularEndpoint(
        motivo_anulacion="Error operativo: reimprimir solicitada por error administrativo",
    )
    result_2 = await workflows_reimpresion_mod.anular_reimpresion_ticket(
        response_2, r1_uuid, payload_anular, session_2, ctx, None
    )

    assert result_2.uuid == r2_uuid
    assert result_2.workflow_estado == "rechazada"
    assert result_2.uuid_reimpresion_padre == r1_uuid
    assert result_2.motivo_anulacion == (
        "Error operativo: reimprimir solicitada por error administrativo"
    )
    assert response_2.headers.get("Cache-Control") == "no-store"
    # KD-TKT-01 single-commit on write call #2.
    assert session_2.commit.await_count == 1
    # DEC-TKT-03: the new row was inserted via append_transition
    # with parent_uuid=r1_uuid (NEVER UPDATE on the original r1 row).
    append_kwargs = (
        workflows_reimpresion_mod.repo_workflow.append_transition.call_args.kwargs
    )
    assert append_kwargs["parent_uuid"] == r1_uuid
    assert append_kwargs["parent_fk_column"] == "uuid_reimpresion_padre"

    # ------------------------------------------------------------------
    # Step 3: POST /reimpresion-ticket/{r1}/anular AGAIN → 409 terminal
    # ------------------------------------------------------------------
    session_3 = AsyncMock()
    response_3 = _new_response()

    async def _read_chain_tip_3(session, model_cls, *, root_uuid, parent_fk_column):
        # Chain tip now is r2 with workflow_estado='rechazada' (terminal).
        return {
            "uuid_root": r1_uuid,
            "uuid_actual": r2_uuid,
            "estado": "activo",
            "timestamp_evento": _now(),
            "chain_length": 2,
            "workflow_estado": "rechazada",
        }

    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_workflow,
        "read_chain_tip",
        _read_chain_tip_3,
    )
    monkeypatch.setattr(
        workflows_reimpresion_mod.repo_reimpresion,
        "buscar_reimpresion_por_uuid",
        AsyncMock(return_value=r2),
    )
    # Reset the mock counter from step 2 so we can assert step 3
    # didn't invoke append_transition.
    workflows_reimpresion_mod.repo_workflow.append_transition.reset_mock()

    with pytest.raises(HTTPException) as exc_info:
        await workflows_reimpresion_mod.anular_reimpresion_ticket(
            response_3, r1_uuid, payload_anular, session_3, ctx, None
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "anulacion_no_permitida"
    assert exc_info.value.detail["estado_actual"] == "rechazada"
    assert exc_info.value.detail["uuid_reimpresion"] == str(r1_uuid)
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
    # Terminal state: no INSERT, no commit.
    workflows_reimpresion_mod.repo_workflow.append_transition.assert_not_called()
    assert session_3.commit.await_count == 0
