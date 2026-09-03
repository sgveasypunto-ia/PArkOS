"""Sucursal HTTP routes (PR4 minimal — pairing token mint, REQ-OP-15).

The pairing-token endpoint is cloud-only (issuer ``admin-``). Branch
operators cannot issue pairing tokens. The token is a single-use,
24-hour JWT that the branch operator exchanges for a long-lived
``sync-agent-`` JWT via ``POST /sync/pair`` (PR8 territory).

NO DELETE endpoint — defense in depth (design §3, AGENTS.md §3).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict

from ...api.deps import get_tenant_ctx, requires_issuer
from ...auth.tenancy import TenantContext
from ...auth.tokens import issue_token
from ...models.V.sucursal import Sucursal  # noqa: F401  (kept for type/extension surface)

router = APIRouter(prefix="/sucursal", tags=["sucursal"])

_pairing_issuer_dep = requires_issuer("admin-")


class PairingTokenResponse(BaseModel):
    """Pairing token mint response (REQ-OP-15)."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    token: str
    expires_at: datetime
    sucursal_uuid: uuid_lib.UUID


@router.get(
    "/{uuid}/pairing-token",
    response_model=PairingTokenResponse,
    summary="Mint a 24h single-use pairing token for a branch (cloud-only, REQ-OP-15)",
)
async def pairing_token(
    uuid: uuid_lib.UUID = Path(...),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_pairing_issuer_dep),
) -> PairingTokenResponse:
    """Mint a 24h single-use pairing token.

    The branch operator redeems this token at ``POST /sync/pair`` (PR8) for a
    long-lived ``sync-agent-`` JWT. Single-use enforcement lives in the
    consume endpoint (PR8 — verifies the token has not been seen before and
    writes a ``revoked_sync_jwts`` row in the same TX).
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    expires_at = now + timedelta(seconds=86400)  # 24 hours

    token = issue_token(
        subject_uuid=uuid,
        issuer="admin-cloud-pairing",
        claims={
            "purpose": "pairing",
            "single_use": True,
            "uuid_sucursal": str(uuid),
        },
        expires_in=86400,
    )

    return PairingTokenResponse(
        token=token,
        expires_at=expires_at,
        sucursal_uuid=uuid,
    )


__all__ = ["router"]
