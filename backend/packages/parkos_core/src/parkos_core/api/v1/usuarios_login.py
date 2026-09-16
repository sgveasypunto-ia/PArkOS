"""HU-F1.15 / REQ-OPS-102..105 + REQ-OPS-XR6 -- ``GET /api/v1/usuarios/{uuid}/login``.

Dedicated ``APIRouter`` mounted at FastAPI app-level (DEC-LOGIN-01.A --
sibling of :mod:`auth`, NOT in :mod:`caja`). Single read-only handler:

* ``get_login_historico`` -- 8-step chain on
  ``GET /api/v1/usuarios/{uuid}/login?limit=10&cursor=...``. KD-LOGIN-01
  SELECT-only + KD-LOGIN-02 read-only AST walk invariant.

Defense in depth (REQ-OPS-XR6 cross-cutting from F1.13, ``openspec/
specs/operations/spec.md:3951``):

  * Layer 1: KD-3 issuer chain ``requires_issuer("operador-",
    "admin-")`` + permission gate ``audit_read`` (DEC-LOGIN-02 +
    DEC-LOGIN-09.B, pre-seeded at ``0002_seed_permisos_canonicos.py
    :48``).
  * Layer 2: tenant scope post-V1 (KD-S2 F1.7 analog). Operador own-
    branch SQL filter applied at :func:`listar_intentos_paginado`;
    admin bypasses (cross-branch audit).
  * Layer 3: KD-LOGIN-01 SELECT-only + KD-LOGIN-02 read-only AST walk.
  * Layer 4: Pydantic ``extra='forbid'`` (``LoginHistoricoQueryParams``
    + ``LoginIntentoItem`` + ``LoginHistoricoListResponse`` inherit
    from ``_Base``).
  * Layer 5: handler 200/400/403/422 mapping + ``Cache-Control: no-store``
    on every response (DEC-LOGIN-05).

KD-LOGIN-01 SELECT-only invariant (AST walk enforced): the handler
executes exactly one SELECT (via :func:`repo.login_historico
.listar_intentos_paginado`). NO UPDATE/DELETE on ``prod.login``. NO
``await session.commit()``. The handler is purely read-only --
``prod.log_operaciones`` is never written.

DEC-LOGIN-01..10 reference: the design decisions are recorded in
``openspec/changes/hu-f1-15-login-historico/design.md``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...repo import login_historico as repo_login_historico
from ...schemas.usuarios import (
    EstadoLogin,
    LoginHistoricoListResponse,
    LoginHistoricoQueryParams,
    LoginIntentoItem,
)
from ..deps import requires_issuer
from . import _helpers

# Dedicated router -- mounted via ``router.include_router`` from
# ``api/v1/__init__.py`` (DEC-LOGIN-01.A -- sibling of ``auth.py``,
# POST-mutating-only invariant preserved per ``auth.py:69`` rationale).
# NOT via the ``make_router`` factory because the read endpoint has a
# path-param UUID + a typed permission gate (``audit_read``) that the
# factory cannot model.
router = APIRouter(prefix="/usuarios", tags=["usuarios"])

# KD-3 issuer chain + ``audit_read`` permission gate (DEC-LOGIN-02 +
# DEC-LOGIN-09.B). Single dep reused for the GET handler.
_login_historico_issuer_dep = requires_issuer("operador-", "admin-")


@router.get(
    "/{uuid}/login",
    response_model=LoginHistoricoListResponse,
    status_code=200,
)
async def get_login_historico(
    response: Response,
    uuid: uuid_lib.UUID,
    params: LoginHistoricoQueryParams = Depends(),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_login_historico_issuer_dep),
) -> LoginHistoricoListResponse:
    """``GET /api/v1/usuarios/{uuid}/login`` -- 8-step read chain.

    Step chain:
        1. Layer 1 issuer dep + permission gate ``audit_read``
           (DI-resolved via ``_login_historico_issuer_dep``). The dep
           already enforced KD-3 issuer + permission gate; ``ctx``
           carries the resolved claims.
        2. Layer 2 tenant scope post-V1 (KD-S2 F1.7 analog). The
           filter is applied at SQL layer (Step 4) -- no need to
           short-circuit here. Operador own-branch; admin bypasses.
        3. Layer 4 Pydantic UUID + limit + cursor validation (FastAPI
           Depends). Malformed values are rejected by FastAPI with
           422 before the handler body runs.
        4. KD-LOGIN-01 + KD-LOGIN-02: READ-ONLY via 1 typed SELECT
           helper :func:`repo.login_historico.listar_intentos_paginado`.
           NO UPDATE/DELETE/INSERT in this body. NO
           ``await session.commit()``.
        5. Build ``next_cursor`` via :func:`repo.login_historico
           .encode_next_cursor` (pure math, ``None`` at EOF).
        6. Layer 5: ``apply_no_store_header(response)`` (DEC-LOGIN-05,
           XR6 Layer 5 mirror from F1.10/F1.11/F1.12/F1.13/F1.14).
        7. Layer 4 + Layer 5: build ``LoginHistoricoListResponse``
           envelope ``{items, next_cursor}`` (DEC-LOGIN-07 forward-
           compatible Parte 2 shape).
        8. KD-LOGIN-01 reaffirmed -- no writes, no commits, no log rows.

    Empty branch contract (DEC-LOGIN-08): zero ``prod.login`` rows for
    the user returns ``items=[]`` + ``next_cursor=None`` with HTTP 200
    (NEVER 404, NEVER 403). The Pydantic UUID validator at the path
    layer raises 422 if the UUID is malformed (Layer 4).
    """
    # --- Step 4 (KD-LOGIN-01 + KD-LOGIN-02): SELECT via 1 typed helper ---
    # NO UPDATE/DELETE/INSERT in this body (AST walk enforces).
    # NO await session.commit() -- GET is naturally idempotent.
    rows = await repo_login_historico.listar_intentos_paginado(
        session,
        uuid_usuario=uuid,
        cursor=params.cursor,
        limit=params.limit,
        tenant_ctx=ctx,  # Layer 2 filter (DEC-LOGIN-03.A)
    )

    # --- Step 5: build next_cursor (pure math) ---
    next_cursor = repo_login_historico.encode_next_cursor(rows, params.limit)

    # --- Step 6 (Layer 5): no-store header on success ---
    _helpers.apply_no_store_header(response)

    # --- Step 7: build {items, next_cursor} envelope (DEC-LOGIN-07) ---
    # Slicing rows[:params.limit] ensures we never serialize the
    # ``limit + 1`` probe row used to detect EOF. ``LoginIntentoItem``
    # instances (not dict literals) preserve mypy --strict typing.
    #
    # F1.15 T6 mypy clean-up (D3 deviation fix). The ORM types
    # ``Login.timestamp_evento: datetime | None`` and
    # ``Login.estado: str | None`` are nullable but the repo helper
    # applies ``WHERE timestamp_evento IS NOT NULL AND estado IS NOT
    # NULL`` -- the [L-S] lifecycle always stamps both values per the
    # audit invariant and ``LoginIntentoItem`` schema contract. The
    # ``cast()`` calls bridge the SQL-level type narrowing to Python
    # types so mypy --strict is satisfied without losing runtime
    # safety (Pydantic's ``LoginIntentoItem`` + ``LoginHistoricoListResponse``
    # at the envelope level enforces the non-null contract via
    # Layer 4 extra='forbid').
    items = [
        LoginIntentoItem(
            uuid=row.uuid,
            timestamp_evento=cast(datetime, row.timestamp_evento),
            timestamp_cierre=row.timestamp_cierre,
            estado=cast(EstadoLogin, row.estado),
            uuid_sucursal=row.uuid_sucursal,
        )
        for row in rows[: params.limit]
    ]
    return LoginHistoricoListResponse(items=items, next_cursor=next_cursor)

    # --- Step 8: KD-LOGIN-01 reaffirmed -- no writes, no commits, no log rows ---


__all__ = ["router"]
