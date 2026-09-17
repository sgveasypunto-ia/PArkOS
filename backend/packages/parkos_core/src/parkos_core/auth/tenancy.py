"""Tenant scoping via ``X-Sucursal-Context`` (REQ-X1, REQ-X2, SC-X1).

Three branches per issuer:
- ``admin-`` — requires the ``X-Sucursal-Context`` header; validates the
  uuid against ``claims["sucursales_permitidas"]``.
- ``operador-`` — JWT pins a single branch (``claims["sucursal"]``); the
  header is OPTIONAL and, if present, MUST match the JWT claim.
- ``sync-agent-`` — JWT ``scope`` claim: ``branch`` pins one branch,
  ``cloud`` returns ``sucursal_uuid=None`` (no tenant filter on cloud sync
  receivers).

The resolved ``TenantContext`` is also bound to the SQLAlchemy event listener
via ``db.tenancy.set_tenant_context`` so every downstream SELECT/UPDATE/
DELETE on tables carrying ``uuid_sucursal`` is auto-filtered.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException, Request

from ..db.tenancy import set_tenant_context
from .jwt_issuer_guard import verify_jwt


@dataclass(frozen=True)
class TenantContext:
    """Per-request tenant scope + actor identity.

    ``uuid_sesion`` is the active ``prod.sesion`` uuid when the request is made
    inside an open operator turno (F3.3 / F8.1 caller convention). It is sourced
    from the JWT ``sesion`` claim for ``operador-`` issuers; ``admin-`` and
    ``sync-agent-`` carry ``uuid_sesion=None`` because they don't operate a
    turno. ``None`` is also the value when the operator is authenticated but
    has no active ``prod.sesion`` (e.g., login mid-shift before opening turno).

    Closing the pre-existing F1.9 gap (``facturacion.py:376,466`` referenced
    ``ctx.uuid_sesion`` which would ``AttributeError``); V8 in F1.12 was the
    first caller that needed this field for real (``prod.factura_pagos`` FK).
    """

    actor_uuid: uuid_lib.UUID
    actor_rol: str
    issuer_prefix: str  # 'admin-' | 'operador-' | 'sync-agent-'
    sucursal_uuid: uuid_lib.UUID | None  # operador- pins; admin- reads from header
    uuid_sesion: uuid_lib.UUID | None = None  # operador- active turno session, if any


class MissingSucursalContextError(HTTPException):
    """400: ``admin-`` token used without the ``X-Sucursal-Context`` header."""

    def __init__(self) -> None:
        super().__init__(
            status_code=400,
            detail={"error": "missing_sucursal_context"},
        )


class UnauthorizedSucursalContextError(HTTPException):
    """403: header uuid not in admin's ``sucursales_permitidas`` claim."""

    def __init__(self) -> None:
        super().__init__(
            status_code=403,
            detail={"error": "unauthorized_sucursal_context"},
        )


class TenantScopeViolationError(HTTPException):
    """403: cross-tenant query attempt."""

    def __init__(self) -> None:
        super().__init__(
            status_code=403,
            detail={"error": "tenant_scope_violation"},
        )


async def get_tenant_ctx(
    request: Request,
    x_sucursal_context: str | None = Header(None, alias="X-Sucursal-Context"),
) -> TenantContext:
    """FastAPI dependency: returns the per-request ``TenantContext``.

    Reads the JWT (via :func:`verify_jwt`), enforces the issuer-specific
    tenant rule, and binds the resolved ``sucursal_uuid`` to the SQLAlchemy
    event listener for downstream query auto-filtering.
    """
    claims: dict[str, Any] = await verify_jwt(request)
    iss = claims.get("iss", "")
    issuer_prefix = iss.split("-")[0] + "-" if "-" in iss else ""
    actor_uuid = uuid_lib.UUID(claims["sub"])
    actor_rol = claims.get("rol", "operador" if issuer_prefix == "operador-" else "admin")

    if issuer_prefix == "operador-":
        # operador- is pinned to a single sucursal
        sucursal_str = claims.get("sucursal")
        if not sucursal_str:
            raise HTTPException(
                status_code=401,
                detail={"error": "missing_sucursal_in_jwt", "detail": "operador tokens require 'sucursal' claim"},
            )
        try:
            sucursal_uuid = uuid_lib.UUID(sucursal_str)
        except (ValueError, TypeError) as e:
            raise HTTPException(
                status_code=401,
                detail={"error": "malformed_sucursal_in_jwt", "detail": str(e)},
            )
        # uuid_sesion sourced from JWT ``sesion`` claim (F3.3 sets it on
        # ``POST /caja-sesion/sesiones`` -> ``uuid_sesion`` is the active
        # ``prod.sesion.uuid``). ``None`` when the operator has no active
        # turno (login before abrir-turno). ``None`` is also the value when
        # the claim is malformed; we do not raise 401 on a missing claim
        # because that would lock out operators mid-shift who happen to be
        # outside a turno (a valid business state).
        sesion_str = claims.get("sesion")
        uuid_sesion_ctx: uuid_lib.UUID | None = None
        if sesion_str:
            try:
                uuid_sesion_ctx = uuid_lib.UUID(sesion_str)
            except (ValueError, TypeError):
                uuid_sesion_ctx = None
        # X-Sucursal-Context header is OPTIONAL; if present, MUST match
        if x_sucursal_context is not None:
            try:
                header_uuid = uuid_lib.UUID(x_sucursal_context)
            except ValueError as e:
                raise UnauthorizedSucursalContextError() from e
            if header_uuid != sucursal_uuid:
                raise UnauthorizedSucursalContextError()
        set_tenant_context(sucursal_uuid)
        return TenantContext(
            actor_uuid=actor_uuid,
            actor_rol=actor_rol,
            issuer_prefix=issuer_prefix,
            sucursal_uuid=sucursal_uuid,
            uuid_sesion=uuid_sesion_ctx,
        )

    if issuer_prefix == "admin-":
        if x_sucursal_context is None:
            raise MissingSucursalContextError()
        try:
            header_uuid = uuid_lib.UUID(x_sucursal_context)
        except ValueError as e:
            raise UnauthorizedSucursalContextError() from e
        permitidas = claims.get("sucursales_permitidas", []) or []
        if str(header_uuid) not in {str(u) for u in permitidas}:
            raise UnauthorizedSucursalContextError()
        set_tenant_context(header_uuid)
        return TenantContext(
            actor_uuid=actor_uuid,
            actor_rol=actor_rol,
            issuer_prefix=issuer_prefix,
            sucursal_uuid=header_uuid,
            # ``admin-`` does not operate a turno; uuid_sesion always None.
            uuid_sesion=None,
        )

    if issuer_prefix == "sync-agent-":
        scope = claims.get("scope", "branch")
        if scope == "branch":
            sucursal_str = claims.get("sucursal")
            try:
                sucursal_uuid = uuid_lib.UUID(sucursal_str) if sucursal_str else None
            except (ValueError, TypeError):
                sucursal_uuid = None
        else:
            sucursal_uuid = None  # cloud scope — no tenant filter
        if sucursal_uuid is not None:
            set_tenant_context(sucursal_uuid)
        return TenantContext(
            actor_uuid=actor_uuid,
            actor_rol="sync-agent",
            issuer_prefix=issuer_prefix,
            sucursal_uuid=sucursal_uuid,
            # ``sync-agent-`` does not operate a turno; uuid_sesion always None.
            uuid_sesion=None,
        )

    raise HTTPException(
        status_code=401,
        detail={"error": "unknown_issuer", "detail": issuer_prefix},
    )


__all__ = [
    "TenantContext",
    "TenantScopeViolationError",
    "MissingSucursalContextError",
    "UnauthorizedSucursalContextError",
    "get_tenant_ctx",
]