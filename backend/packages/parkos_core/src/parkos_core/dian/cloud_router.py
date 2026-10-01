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
- ``GET /envio-dian`` / ``GET /validacion-evento`` — HU-F13.4.
  Cursor-paginated read-only listings for these 2 cloud-only
  ``[L-W]`` tables (``workflows.py`` explicitly must not mount them
  — see that module's docstring). Same ``{items, next_cursor}``
  contract as the rest of the system (:mod:`repo.pagination`).

Issuer: ``admin-,operador-`` (admin writes; branch operator triggers
DIAN flows via an admin token from the cloud admin app).
"""
from __future__ import annotations

import logging
import os
import uuid as uuid_lib
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
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
from ..repo.pagination import Cursor, InvalidCursorError
from ..repo.pagination import decode as cursor_decode
from ..repo.pagination import encode as cursor_encode
from ..repo.workflow import STATE_MACHINES, append_transition
from ..schemas.dian import (
    EnvioDianCreate,
    EnvioDianRead,
    EnvioDianReadList,
    ValidacionEventoCreate,
    ValidacionEventoRead,
    ValidacionEventoReadList,
)
from ..schemas.facturacion import CloudFacturaElectronicaCreate
from .cloud.atomic_next_consecutivo import (
    PrefijoMissingError,
    ResolucionNotFoundError,
    next_consecutivo,
)
from .cloud.dispatcher import (
    ESTADO_ACEPTADO,
    ESTADO_EN_PROCESO,
    ESTADO_ERROR,
    ESTADO_RECHAZADO,
    ESTADO_TIMEOUT,
    dispatch_factura_electronica,
    dispatch_revocacion,
)

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
    payload: CloudFacturaElectronicaCreate,
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


# ---------------------------------------------------------------------------
# HU-F13.4 — read-only cursor-paginated listings (REQ-25 / REQ-25-W-CLOUD-ONLY)
# ---------------------------------------------------------------------------
#
# BR1: reads only — same ``{items, next_cursor}`` contract as the rest of
# the system (``repo.pagination``), no new writes. BR3: mounted on THIS
# router so the module-level ``PARKOS_DEPLOY=branch`` guard at the top of
# the file covers them too.
#
# ``estado`` 422-validation sets, below, are NOT the 4 values plan.md's
# HU-F13.4 BR2 names (``pendiente|enviado|aceptado|rechazado`` for
# envio_dian; ``recibido|validado|observado|rechazado`` for
# validacion_evento) — those 4 values are drift: they mirror
# ``schemas.facturacion.FacturaDisplayFE.estado_dian``, a DERIVED FE-display
# projection that collapses the raw column into a simplified enum, not the
# raw table's own domain (confirmed against every writer in the codebase):
#
# - ``envio_dian.estado`` has TWO independent writers: (a) the
#   ``POST /envio-dian`` transition endpoint above, validated against
#   :data:`repo.workflow.STATE_MACHINES['envio_dian']`
#   (``pendiente|enviado|ack|error``); and (b) ``dian.cloud.dispatcher``'s
#   ``dispatch_factura_electronica`` / ``*_with_backoff``, which mutates
#   ``envio.estado`` DIRECTLY (bypassing STATE_MACHINES) with its own
#   ``ESTADO_*`` constants (``aceptado|rechazado|timeout|en_proceso|error``).
#   The real domain is the UNION of both.
# - ``validacion_evento.estado`` has exactly ONE writer (the
#   ``POST /validacion-evento`` transition endpoint above), so its real
#   domain is exactly :data:`repo.workflow.STATE_MACHINES['validacion_evento']`
#   (``pendiente|validado|rechazado`` — neither ``recibido`` nor
#   ``observado`` is ever written; ``recibido`` is actually a ``reclamos``
#   state in the same ``STATE_MACHINES`` dict, a likely copy/paste source
#   of the plan.md drift).
_ENVIO_DIAN_ESTADOS: frozenset[str] = frozenset(STATE_MACHINES["envio_dian"]) | {
    ESTADO_ACEPTADO,
    ESTADO_RECHAZADO,
    ESTADO_TIMEOUT,
    ESTADO_EN_PROCESO,
    ESTADO_ERROR,
}
_VALIDACION_EVENTO_ESTADOS: frozenset[str] = frozenset(STATE_MACHINES["validacion_evento"])


def _parse_cursor_timestamp(value: str) -> datetime:
    """Parse the cursor's ISO-8601 ``vigente_desde`` into a naive ``datetime``.

    Mirrors ``api.router_factory._parse_cursor_timestamp`` (not imported —
    that helper is module-private, and this cloud-only module stays
    self-contained per the ``RevocacionFacturaWebhookPayload`` precedent
    above). asyncpg needs a naive ``datetime`` bound against a
    ``DateTime(timezone=False)`` column; Postgres refuses the implicit
    cast from a tz-aware value otherwise.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


async def _list_workflow_rows(
    session: AsyncSession,
    *,
    model_cls: Any,
    estado_values: frozenset[str],
    estado: str | None,
    cursor: str | None,
    limit: int,
    extra_where: list[Any] | None = None,
) -> tuple[list[Any], str | None]:
    """Shared cursor-paginated SELECT for ``envio_dian`` / ``validacion_evento``.

    Mirrors ``api.router_factory.make_router``'s generic ``list_endpoint``
    for ``[L-W]`` tables that declare ``vigente_desde`` (same ordering,
    same cursor shape via ``repo.pagination``) — these two cloud-only
    tables share that exact shape with their branch-originated siblings
    (``alerta``/``reclamos``/``anulaciones``/``reimpresion_ticket``,
    mounted via that factory in ``api/v1/workflows.py``), just read here
    instead because ``workflows.py`` must not mount them (REQ-X3).

    Raises:
        HTTPException: 422 ``invalid_estado`` when ``estado`` is not in
            ``estado_values``; 400 ``invalid_cursor`` on a malformed or
            wrong-shape cursor (mirrors ``repo.pagination.InvalidCursorError``
            — same contract as the rest of the system).
    """
    if estado is not None and estado not in estado_values:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_estado",
                "estado": estado,
                "allowed": sorted(estado_values),
            },
        )

    try:
        decoded = cursor_decode(cursor) if cursor else None
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_cursor", "detail": str(exc)},
        ) from exc

    cursor_tuple: tuple[datetime, uuid_lib.UUID] | None = None
    if decoded is not None:
        if decoded.vigente_desde is None:
            # Decodes cleanly (exactly one of vigente_desde/created_at was
            # present) but carries the WRONG key for an [L-W] table cursor —
            # e.g. copy-pasted from an [A]/[L-E] listing's cursor.
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_cursor",
                    "detail": "cursor missing vigente_desde (required for this [L-W] table)",
                },
            )
        cursor_tuple = (
            _parse_cursor_timestamp(decoded.vigente_desde),
            uuid_lib.UUID(decoded.uuid),
        )

    stmt = select(model_cls).where(model_cls.vigente_hasta.is_(None))
    if estado is not None:
        stmt = stmt.where(model_cls.estado == estado)
    for clause in extra_where or []:
        stmt = stmt.where(clause)
    stmt = stmt.order_by(model_cls.vigente_desde.desc(), model_cls.uuid.asc())
    if cursor_tuple is not None:
        cursor_ts, cursor_uuid = cursor_tuple
        stmt = stmt.where(
            (model_cls.vigente_desde < cursor_ts)
            | ((model_cls.vigente_desde == cursor_ts) & (model_cls.uuid > cursor_uuid))
        )
    stmt = stmt.limit(limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = cursor_encode(
            Cursor(vigente_desde=last.vigente_desde.isoformat(), uuid=str(last.uuid))
        )
    return rows, next_cursor


@router.get(
    "/envio-dian",
    response_model=EnvioDianReadList,
    status_code=200,
    summary="HU-F13.4: cursor-paginated read of envio_dian (REQ-25-W-CLOUD-ONLY)",
)
async def list_envio_dian(
    uuid_sucursal: uuid_lib.UUID | None = Query(default=None),  # noqa: B008
    estado: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _claims: None = Depends(_cloud_issuer_dep),
) -> EnvioDianReadList:
    """``GET /api/v1/envio-dian`` — cursor-paginated read-only listing.

    Filters (both optional, composed with AND): ``uuid_sucursal`` and
    ``estado`` (422 ``invalid_estado`` if not a real value — see the
    module-level comment above ``_ENVIO_DIAN_ESTADOS`` for the full
    drift-vs-plan.md rationale). Orders by
    ``(vigente_desde DESC, uuid ASC)`` — same convention as every other
    ``[L-W]`` table with ``vigente_desde`` (``api.router_factory``).
    """
    extra_where: list[Any] = []
    if uuid_sucursal is not None:
        extra_where.append(EnvioDian.uuid_sucursal == uuid_sucursal)

    rows, next_cursor = await _list_workflow_rows(
        session,
        model_cls=EnvioDian,
        estado_values=_ENVIO_DIAN_ESTADOS,
        estado=estado,
        cursor=cursor,
        limit=limit,
        extra_where=extra_where,
    )
    items = [EnvioDianRead.model_validate(row) for row in rows]
    return EnvioDianReadList(items=items, next_cursor=next_cursor)


@router.get(
    "/validacion-evento",
    response_model=ValidacionEventoReadList,
    status_code=200,
    summary="HU-F13.4: cursor-paginated read of validacion_evento (REQ-25)",
)
async def list_validacion_evento(
    uuid_sucursal: uuid_lib.UUID | None = Query(default=None),  # noqa: B008
    estado: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _claims: None = Depends(_cloud_issuer_dep),
) -> ValidacionEventoReadList:
    """``GET /api/v1/validacion-evento`` — cursor-paginated read-only listing.

    Filters (both optional, composed with AND): ``uuid_sucursal`` and
    ``estado`` (422 ``invalid_estado`` if not a real value — see the
    module-level comment above ``_VALIDACION_EVENTO_ESTADOS``). Orders by
    ``(vigente_desde DESC, uuid ASC)``, same as :func:`list_envio_dian`.
    """
    extra_where: list[Any] = []
    if uuid_sucursal is not None:
        extra_where.append(ValidacionEvento.uuid_sucursal == uuid_sucursal)

    rows, next_cursor = await _list_workflow_rows(
        session,
        model_cls=ValidacionEvento,
        estado_values=_VALIDACION_EVENTO_ESTADOS,
        estado=estado,
        cursor=cursor,
        limit=limit,
        extra_where=extra_where,
    )
    items = [ValidacionEventoRead.model_validate(row) for row in rows]
    return ValidacionEventoReadList(items=items, next_cursor=next_cursor)


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
