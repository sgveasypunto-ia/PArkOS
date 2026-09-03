"""DIAN cloud-only FastAPI router (T-PR6-09, T-PR11-05/06, REQ-X3, design §10 Layer 2).

Belt-and-suspenders DIAN boundary at TWO layers:

1. **Image-level** (Layer 1, design §10): the ``Dockerfile`` for branch
   images physically excludes the ``parkos_core/dian/`` directory.
2. **Import-level** (Layer 2, this module + the ``cloud/`` submodules):
   the top-level guards raise ``ImportError`` if
   ``PARKOS_DEPLOY=branch``. Anyone trying to
   ``from parkos_core.dian.cloud_router import router`` on a branch
   image fails immediately at import time.

Endpoints (all cloud-only, REQ-X3):

- ``POST /factura-electronica`` — REQ-34 / REQ-35. Atomic
  ``SELECT FOR UPDATE`` on the resolution row + ``consecutivo++``
  (T-PR11-05 helper) + INSERT via :func:`repo.event.record_event`;
  T-PR11-06 then fires the DIAN dispatcher.
- ``POST /envio-dian`` — REQ-25-W-CLOUD-ONLY. Workflow transition for
  DIAN send/ack via :func:`repo.workflow.append_transition`.
- ``POST /validacion-evento`` — REQ-25. Admin validation of received
  events via :func:`repo.workflow.append_transition`.
- ``POST /revocacion-factura-webhook`` — REQ-X3. Receives DIAN
  revocation, inserts ``prod.revocacion_factura`` extending the
  per-tenant SHA-256 chain; T-PR11-06 fires the dispatcher which
  extends the chain AGAIN with the confirmation row.

Issuer: ``admin-,operador-`` (admin writes; branch operator triggers
DIAN flows via an admin token from the cloud admin app).
"""
from __future__ import annotations

import logging
import os
import uuid as uuid_lib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
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
from ..repo.append_only import append_event
from ..repo.event import record_event
from ..repo.workflow import append_transition
from ..schemas.dian import EnvioDianCreate, ValidacionEventoCreate
from ..schemas.facturacion import FacturaElectronicaCreate
from .cloud.atomic_next_consecutivo import (
    PrefijoMissingError,
    ResolucionNotFoundError,
    next_consecutivo,
)
from .cloud.dispatcher import dispatch_factura_electronica, dispatch_revocacion

logger = logging.getLogger(__name__)

# T-PR11-06 — DIAN provider connection (cloud-only). Read once at
# module load so all calls share the same endpoint/token.
DIAN_PROVIDER_URL = os.environ.get(
    "PARKOS_DIAN_PROVIDER_URL", "http://localhost:8080"
)
DIAN_TOKEN_PATH = Path(
    os.environ.get("PARKOS_DIAN_PROVIDER_TOKEN_PATH", "/dev/null")
)

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
    """Atomically assign prefijo + consecutivo + insert + dispatch (REQ-34, REQ-35).

    1. :func:`atomic_next_consecutivo.next_consecutivo` runs
       ``SELECT FOR UPDATE`` on the resolution row + computes the next
       ``consecutivo`` (lock holds until the INSERT commits).
    2. ``record_event`` writes the ``[L-E]`` row + co-transactional
       ``log_transaccional`` audit row.
    3. T-PR11-06 fires the DIAN dispatcher; the terminal outcome
       (``aceptado`` | ``rechazado`` | ``timeout``) lands in
       ``envio_dian.respuesta_proveedor.estado_dian``.

    Returns:
        ``{uuid, prefijo, consecutivo, uuid_envio_dian}``.
    """
    # 1. Atomic next-consecutivo (T-PR11-05). The lock is held by the
    # transaction until the INSERT commits below — concurrent inserts
    # on the same resolution serialize cleanly.
    resolucion_uuid = payload.uuid_resolucion_facturacion
    try:
        prefijo, consecutivo = await next_consecutivo(
            session, uuid_resolucion_facturacion=resolucion_uuid
        )
    except ResolucionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "resolucion_not_found", "uuid": str(resolucion_uuid)},
        ) from exc
    except PrefijoMissingError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "resolucion_sin_prefijo"},
        ) from exc

    # 2. INSERT via record_event (append-only [L-E]).
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

    # 3. T-PR11-06 — fire the DIAN dispatcher; envio_dian row carries
    # the terminal outcome.
    envio = await dispatch_factura_electronica(
        session,
        uuid_factura_electronica=new_row.uuid,
        actor_uuid=ctx.actor_uuid,
        dian_provider_url=DIAN_PROVIDER_URL,
        dian_token_path=DIAN_TOKEN_PATH,
    )

    return {
        "uuid": new_row.uuid,
        "prefijo": prefijo,
        "consecutivo": consecutivo,
        "uuid_envio_dian": envio.uuid,
    }


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
    """Insert a ``revocacion_factura`` row + fire the DIAN dispatcher.

    DIAN POSTs a signed webhook when an electronic invoice is annulled.
    The row is ``[A]`` (append-only) + carries the second of only two
    hash chains (REQ-16, REQ-X4). :func:`repo.append_only.append_event`
    with ``chain_hash=True`` extends the per-``uuid_sucursal`` SHA-256
    chain atomically with the INSERT — the DB trigger
    ``prod.fn_extend_hash_chain()`` re-verifies the Python-computed hash
    on commit and raises ``HASH_CHAIN_MISMATCH`` if they diverge.

    Per design §21.11 step 2 (T-PR11-02 / T-PR11-06), the dispatcher
    fires after the inbound row is committed. On ``aceptado`` the
    dispatcher extends the chain AGAIN with a confirmation row
    (``motivo='dian_confirmada'``) — the inbound + confirmed are TWO
    distinct events in the chain by design.

    The webhook is unauthenticated at the JWT layer; the endpoint
    additionally accepts admin- tokens. ``actor_uuid=None`` is
    intentional — DIAN is not a JWT subject.

    Returns:
        ``{"uuid": new_row.uuid, "uuid_envio_dian": envio.uuid}``.
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

    # T-PR11-06 — fire the DIAN dispatcher; on ``aceptado`` it
    # extends the SHA-256 chain with motivo='dian_confirmada'.
    envio = await dispatch_revocacion(
        session,
        uuid_revocacion_factura=new_row.uuid,
        actor_uuid=None,  # webhook — DIAN is not a JWT subject
        dian_provider_url=DIAN_PROVIDER_URL,
        dian_token_path=DIAN_TOKEN_PATH,
    )

    return {"uuid": new_row.uuid, "uuid_envio_dian": envio.uuid}


__all__ = ["RevocacionFacturaWebhookPayload", "router"]
