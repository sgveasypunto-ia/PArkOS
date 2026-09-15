"""HU-F1.15 / KD-LOGIN-01 + KD-LOGIN-02 -- ``repo/login_historico.py``.

Read-only SELECT helpers consumed by
:mod:`parkos_core.api.v1.usuarios_login`. The single async helper
(:func:`listar_intentos_paginado`) executes exactly one SELECT against
``prod.login`` and returns ORM rows. The two cursor wrappers
(:func:`encode_next_cursor`, :func:`decode_cursor_or_none`) are pure
math (base64 JSON encoding/decoding of ``(timestamp_evento, uuid)``
pairs) and never touch the DB.

KD-LOGIN-01 (SELECT-only invariant): the helpers' bodies contain
ONLY ``await session.execute(select(...))`` calls. No write path is
reachable from this module. NO ``await session.commit()``.

KD-LOGIN-02 (read-only AST walk): ``tests/static/test_login_historico_read_only.py``
asserts that ``api/v1/usuarios_login.py::get_login_historico`` does
NOT contain ``update(Login)``, ``delete(Login)``,
``text("UPDATE prod.login")``, ``text("DELETE FROM prod.login")``,
or ``await session.commit()`` in the handler body.

DEC-LOGIN-01..10 reference: the design decisions are recorded in
``openspec/changes/hu-f1-15-login-historico/design.md``.

Helpers:

* :func:`listar_intentos_paginado` -- ``SELECT Login ... WHERE
  uuid_usuario = :u ORDER BY timestamp_evento DESC, uuid ASC LIMIT
  :limit + 1`` -> ``list[Login]``. Layer 2 tenant filter is applied
  at SQL layer when ``tenant_ctx.issuer_prefix == "operador-"``
  (DEC-LOGIN-03.A -- own-branch only; admin bypasses).
* :func:`encode_next_cursor` -- pure math. If ``len(items) <= limit``
  returns ``None`` (last page); otherwise encodes the last item's
  ``(timestamp_evento.isoformat(), str(uuid))`` pair as base64 JSON.
* :func:`decode_cursor_or_none` -- thin wrapper around
  :func:`parkos_core.repo.pagination.decode`. Returns ``None`` when
  the input cursor is ``None``; raises :class:`InvalidCursorError`
  on malformed base64/JSON/missing keys.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.tenancy import TenantContext
from ..models.L_S.login import Login
from .pagination import Cursor, InvalidCursorError
from .pagination import decode as cursor_decode
from .pagination import encode as cursor_encode

# Hard ceiling for pagination (DEC-LOGIN-04 + design §10.1 Step 4).
# The handler clamps to this ceiling before invoking the helper;
# re-clamping here is defense in depth.
_LIMIT_CEILING: int = 100


async def listar_intentos_paginado(
    session: AsyncSession,
    *,
    uuid_usuario: uuid_lib.UUID,
    cursor: str | None,
    limit: int,
    tenant_ctx: TenantContext,
) -> list[Login]:
    """Return one page of ``prod.login`` rows for the given user.

    KD-LOGIN-01: SELECT-only. NO UPDATE/DELETE/INSERT. NO commit.
    KD-LOGIN-02 + DEC-LOGIN-04: cursor pagination via
    ``(timestamp_evento DESC, uuid ASC)`` -- composite key supports
    stable cursor at page boundaries (secondary ``uuid`` tie-breaker
    prevents skip/repeat on identical ``timestamp_evento``).

    Layer 2 (DEC-LOGIN-03.A): when ``tenant_ctx.issuer_prefix ==
    "operador-"`` AND ``tenant_ctx.sucursal_uuid is not None`` the
    helper adds ``WHERE login.uuid_sucursal = ctx.sucursal_uuid`` at
    SQL layer so operador NEVER sees cross-branch data. ``admin-``
    bypasses (cross-branch audit). ``sync-agent-`` is not a valid
    issuer for this endpoint (KD-3 issuer chain at handler layer
    restricts to ``operador-`` + ``admin-``).

    Args:
        session: Async SQLAlchemy session.
        uuid_usuario: User UUID (path param, validated upstream).
        cursor: Opaque base64 cursor, or ``None`` for first page.
        limit: Page size (1..100). Helper fetches ``limit + 1`` rows
            so the handler can detect EOF + emit ``next_cursor``.
        tenant_ctx: Per-request tenant scope (DI-resolved upstream).

    Returns:
        Up to ``limit + 1`` ORM rows ordered by
        ``(timestamp_evento DESC, uuid ASC)``. Caller slices to
        ``[:limit]`` before serializing.
    """
    # Decode the cursor (or accept ``None``) before building the WHERE
    # so the typed exception bubbles up unchanged.
    decoded: Cursor | None = None
    if cursor is not None:
        decoded = cursor_decode(cursor)

    # Clamp limit (defense in depth; Pydantic already enforces 1..100).
    eff_limit: int = max(1, min(int(limit), _LIMIT_CEILING))

    stmt = (
        select(Login)
        .where(Login.uuid_usuario == uuid_usuario)
        # F1.15 T6 mypy clean-up (D3 deviation fix). The ORM column
        # types are nullable (timestamp_evento: datetime | None,
        # estado: str | None) but the [L-S] lifecycle always stamps
        # both values -- the schema contract (LoginIntentoItem) and
        # the audit invariant guarantee these are NEVER null in
        # production rows. Filter at SQL layer so the rows returned
        # have known-non-null types (mypy --strict happy) AND so the
        # handler never serializes an incomplete audit row.
        .where(
            Login.timestamp_evento.is_not(None),
            Login.estado.is_not(None),
        )
        .order_by(Login.timestamp_evento.desc(), Login.uuid.asc())
        .limit(eff_limit + 1)
    )

    # Layer 2 (DEC-LOGIN-03.A): operador- issuer filters by own-branch.
    if (
        tenant_ctx.issuer_prefix == "operador-"
        and tenant_ctx.sucursal_uuid is not None
    ):
        stmt = stmt.where(Login.uuid_sucursal == tenant_ctx.sucursal_uuid)
    # admin- bypasses (no filter added) -- cross-branch audit.

    if decoded is not None:
        cursor_ts = decoded.created_at or decoded.vigente_desde
        if cursor_ts is None:
            raise InvalidCursorError(
                "cursor missing both vigente_desde and created_at"
            )
        stmt = stmt.where(
            or_(
                Login.timestamp_evento < cursor_ts,
                # SQL tie-break: equal timestamp_evento + greater uuid.
                (Login.timestamp_evento == cursor_ts) & (Login.uuid > uuid_lib.UUID(decoded.uuid)),
            )
        )

    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    return rows


def encode_next_cursor(items: list[Login], limit: int) -> str | None:
    """Return the ``next_cursor`` opaque string for the page, or ``None`` at EOF.

    Pure math (no DB, no IO). If ``len(items) <= limit`` the current
    page is the last page and ``None`` is returned. Otherwise the
    ``(timestamp_evento, uuid)`` of the last item on the page (after
    slicing) is base64-JSON encoded as the cursor for the next page.

    DEC-LOGIN-04: stable cursor pagination. The composite
    ``(timestamp_evento DESC, uuid ASC)`` order means the last item
    on the current page IS the first item to skip on the next page.
    """
    if len(items) <= limit:
        return None
    last = items[limit - 1]
    ts = last.timestamp_evento
    if ts is None:
        # Defensive: the migration 0001 column allows NULL timestamps;
        # a NULL-bearing row at the page boundary would produce a
        # non-decodable cursor. Surface a typed error.
        raise InvalidCursorError(
            "cannot encode next_cursor: row has NULL timestamp_evento"
        )
    return cursor_encode(
        Cursor(
            vigente_desde=ts.isoformat(),
            created_at=None,
            uuid=str(last.uuid),
        )
    )


def decode_cursor_or_none(cursor: str | None) -> str | None:
    """Validate-and-passthrough cursor wrapper.

    Returns ``None`` when ``cursor`` is ``None`` (first page).
    Returns ``cursor`` unchanged on a valid cursor (caller can
    round-trip through :func:`encode_next_cursor`).

    Raises :class:`InvalidCursorError` on malformed base64/JSON/missing
    keys -- the handler converts this to HTTP 400 with error code
    ``cursor_invalid``.
    """
    if cursor is None:
        return None
    cursor_decode(cursor)  # raises on malformed
    return cursor


__all__ = [
    "decode_cursor_or_none",
    "encode_next_cursor",
    "listar_intentos_paginado",
]
