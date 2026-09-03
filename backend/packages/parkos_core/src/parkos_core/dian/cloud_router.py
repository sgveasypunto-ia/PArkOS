"""DIAN cloud-only FastAPI router (T-PR6-09, REQ-X3, design §10 Layer 2).

Belt-and-suspenders DIAN boundary at TWO layers:

1. **Image-level** (Layer 1, design §10): the ``Dockerfile`` for branch
   images physically excludes the ``parkos_core/dian/`` directory.
2. **Import-level** (Layer 2, this module): the top-level guard below
   raises ``ImportError`` if ``PARKOS_DEPLOY=branch``. Anyone trying to
   ``from parkos_core.dian.cloud_router import router`` on a branch
   image fails immediately at import time — the process never reaches
   the endpoint registration phase.

Endpoints (all cloud-only, REQ-X3):

- ``POST /factura-electronica`` — REQ-34 / REQ-35. Atomic
  ``SELECT FOR UPDATE`` on ``prod.resolucion_facturacion`` row +
  ``consecutivo++`` + INSERT into ``prod.factura_electronica`` via
  :func:`repo.event.record_event` (append-only, co-transactional
  ``log_transaccional``).
- ``POST /envio-dian`` — REQ-25-W-CLOUD-ONLY. Workflow transition for
  DIAN send/ack via :func:`repo.workflow.append_transition` (state
  machine: ``pendiente -> enviado -> ack|error``).
- ``POST /validacion-evento`` — REQ-25. Admin validation of received
  events via :func:`repo.workflow.append_transition` (state machine:
  ``pendiente -> validado|rechazado``).
- ``POST /revocacion-factura-webhook`` — REQ-X3. Receives DIAN
  revocation, inserts ``prod.revocacion_factura`` row extending the
  per-tenant SHA-256 hash chain (the second of only two chain carriers
  per design §11).

Issuer: ``admin-,operador-`` (admin writes; branch operator triggers
DIAN flows on behalf of the branch via an admin token from the cloud
admin app). The branch cannot reach these endpoints because the import
guard prevents them from loading.
"""
from __future__ import annotations

import logging
import os
import uuid as uuid_lib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Cloud-only enforcement guard (REQ-X3, design §10 Layer 2).
# This MUST stay as the very first non-stdlib code so the ImportError
# fires before any app-specific imports — branch deploys bail out at
# module load.
if os.environ.get("PARKOS_DEPLOY", "cloud").lower() == "branch":
    raise ImportError(
        "parkos_core.dian.cloud_router is unavailable on branch deploys "
        "(REQ-X3, design §10 belt-and-suspenders)."
    )

from ..api.deps import get_tenant_ctx, requires_issuer
from ..auth.tenancy import TenantContext
from ..db.engine import get_session
from ..models.A.revocacion_factura import RevocacionFactura
from ..models.L_E.factura_electronica import FacturaElectronica
from ..models.L_W.envio_dian import EnvioDian
from ..models.L_W.validacion_evento import ValidacionEvento
from ..models.V.resolucion_facturacion import ResolucionFacturacion
from ..repo.append_only import append_event
from ..repo.event import record_event
from ..repo.workflow import append_transition
from ..schemas.dian import EnvioDianCreate, ValidacionEventoCreate
from ..schemas.facturacion import FacturaElectronicaCreate

logger = logging.getLogger(__name__)

# No prefix here — the v1 root ``APIRouter(prefix="/api/v1")`` owns that.
# Nested prefixes would produce ``/api/v1/api/v1/<endpoint>``. Each
# endpoint below declares its full sub-path.
router = APIRouter(tags=["dian"])

_cloud_issuer_dep = requires_issuer("admin-", "operador-")


# ---------------------------------------------------------------------------
# Inline webhook payload schema
# ---------------------------------------------------------------------------
# T-PR6-09 ships this endpoint in PR6; the dedicated
# ``schemas.revocacion_factura`` module lands in PR6b per
# ``schemas/dian.py`` line 26-28 (this module must not create a new file
# outside the deliverable scope defined by T-PR6-09/10/11). Defining the
# payload here keeps the cloud-only boundary self-contained: one file,
# one module-level guard, one router, four endpoints.


class RevocacionFacturaWebhookPayload(BaseModel):
    """Inbound webhook payload for ``POST /revocacion-factura-webhook``.

    DIAN POSTs this when an electronic invoice is annulled. The webhook
    is **not** JWT-authenticated at the application layer — DIAN
    authenticates via signed HTTP requests (out of scope here). The
    endpoint's issuer guard additionally accepts admin tokens; production
    webhook callers present an admin token via the cloud admin app.

    The DIAN-controlled ``timestamp_evento`` is preserved as-is so the
    audit trail reflects DIAN's clock instead of our server clock.
    """

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    uuid_sucursal: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID
    uuid_factura_electronica_reemplazo: uuid_lib.UUID | None = None
    motivo: str | None = None
    timestamp_evento: uuid_lib.UUID | str | int | float | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/factura-electronica",
    status_code=201,
    summary="Atomic SELECT FOR UPDATE on resolucion + consecutivo++ + INSERT (REQ-34, REQ-35)",
)
async def create_factura_electronica(
    payload: FacturaElectronicaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_cloud_issuer_dep),
) -> dict[str, Any]:
    """Atomically assign prefijo + consecutivo + insert ``factura_electronica``.

    REQ-34 / REQ-35:

    1. ``SELECT FOR UPDATE`` on ``prod.resolucion_facturacion`` row —
       the row lock holds until commit so concurrent inserts do not race
       for the same ``consecutivo``.
    2. Compute ``consecutivo = MAX(consecutivo)+1`` scoped to the
       resolution. The UK
       ``(uuid_resolucion_facturacion, consecutivo)`` enforces DIAN's
       ``numero_oficial`` uniqueness invariant inside the range.
    3. ``record_event`` the new row (append-only ``[L-E]``, with a
       co-transactional ``log_transaccional`` audit row).

    Returns:
        ``{uuid, prefijo, consecutivo}`` — the server-assigned trio.
    """
    # 1. SELECT FOR UPDATE the resolucion_facturacion row (cloud admin).
    resolucion_uuid = payload.uuid_resolucion_facturacion
    row = (
        await session.execute(
            select(ResolucionFacturacion)
            .where(ResolucionFacturacion.uuid == resolucion_uuid)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "resolucion_not_found", "uuid": str(resolucion_uuid)},
        )

    # 2. Read prefijo + compute next consecutivo from rango_desde.
    prefijo = row.prefijo
    if prefijo is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "resolucion_sin_prefijo"},
        )
    max_consecutivo = (
        await session.execute(
            text(
                "SELECT COALESCE(MAX(consecutivo), :start) "
                "FROM prod.factura_electronica "
                "WHERE uuid_resolucion_facturacion = :uuid"
            ),
            {"start": row.rango_desde or 0, "uuid": str(resolucion_uuid)},
        )
    ).scalar()
    consecutivo = int(max_consecutivo) + 1

    # 3. INSERT via record_event (append-only [L-E]).
    new_row = await record_event(
        session,
        FacturaElectronica,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": payload.uuid_sucursal,
            "uuid_factura": payload.uuid_factura,
            "uuid_cliente": payload.uuid_cliente,
            "uuid_resolucion_facturacion": resolucion_uuid,
            "prefijo": prefijo,
            "consecutivo": consecutivo,
            "descuento": payload.descuento,
        },
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return {"uuid": new_row.uuid, "prefijo": prefijo, "consecutivo": consecutivo}


@router.post(
    "/envio-dian",
    status_code=201,
    summary="Workflow transition for DIAN send/ack (REQ-25-W-CLOUD-ONLY)",
)
async def create_envio_dian(
    payload: EnvioDianCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_cloud_issuer_dep),
) -> dict[str, Any]:
    """Record a workflow transition for DIAN envio (send/ack).

    Cloud-only — branch deploys cannot load this module. Validates
    ``parent.estado -> new_attrs['estado']`` against
    :data:`repo.workflow.STATE_MACHINES['envio_dian']` via
    :func:`repo.workflow.append_transition` (REQ-21). For root
    insertions (``parent_uuid=None``) the new row starts at
    ``pendiente``.

    Returns:
        ``{"uuid": new_row.uuid}``.
    """
    parent_uuid = getattr(payload, "uuid_envio_padre", None)
    new_attrs = payload.model_dump(exclude_none=True)
    if "estado" not in new_attrs:
        new_attrs["estado"] = "pendiente" if parent_uuid is None else "enviado"

    new_row = await append_transition(
        session,
        EnvioDian,
        actor_uuid=ctx.actor_uuid,
        new_attrs=new_attrs,
        parent_uuid=parent_uuid,
        parent_fk_column="uuid_envio_padre",
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return {"uuid": new_row.uuid}


@router.post(
    "/validacion-evento",
    status_code=201,
    summary="Admin validation of a received event (REQ-25)",
)
async def create_validacion_evento(
    payload: ValidacionEventoCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_cloud_issuer_dep),
) -> dict[str, Any]:
    """Record a validation event for an admin-verified received event.

    Cloud-only. State machine
    (``repo.workflow.STATE_MACHINES['validacion_evento']``):
    ``pendiente -> validado|rechazado``. Root insertions default to
    ``pendiente``.

    Returns:
        ``{"uuid": new_row.uuid}``.
    """
    parent_uuid = getattr(payload, "uuid_validacion_padre", None)
    new_attrs = payload.model_dump(exclude_none=True)
    if "estado" not in new_attrs:
        new_attrs["estado"] = "pendiente" if parent_uuid is None else "validado"

    new_row = await append_transition(
        session,
        ValidacionEvento,
        actor_uuid=ctx.actor_uuid,
        new_attrs=new_attrs,
        parent_uuid=parent_uuid,
        parent_fk_column="uuid_validacion_padre",
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return {"uuid": new_row.uuid}


@router.post(
    "/revocacion-factura-webhook",
    status_code=201,
    summary="Receive DIAN revocation webhook, extend SHA-256 hash chain (REQ-X3)",
)
async def revocacion_factura_webhook(
    payload: RevocacionFacturaWebhookPayload,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _claims: None = Depends(_cloud_issuer_dep),
) -> dict[str, Any]:
    """Insert a ``revocacion_factura`` row extending the hash chain.

    DIAN POSTs a signed webhook when an electronic invoice is annulled.
    The row is ``[A]`` (append-only) + carries the second of only two
    hash chains (REQ-16, REQ-X4). :func:`repo.append_only.append_event`
    with ``chain_hash=True`` extends the per-``uuid_sucursal`` SHA-256
    chain atomically with the INSERT — the DB trigger
    ``prod.fn_extend_hash_chain()`` re-verifies the Python-computed hash
    on commit and raises ``HASH_CHAIN_MISMATCH`` if they diverge.

    The webhook is unauthenticated at the JWT layer; the endpoint
    additionally accepts admin- tokens. ``actor_uuid=None`` is
    intentional — DIAN is not a JWT subject.

    Returns:
        ``{"uuid": new_row.uuid}``.
    """
    new_row = await append_event(
        session,
        RevocacionFactura,
        payload.model_dump(exclude_none=True),
        actor_uuid=None,  # webhook — DIAN is not a JWT subject
        chain_hash=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return {"uuid": new_row.uuid}


__all__ = ["RevocacionFacturaWebhookPayload", "router"]
