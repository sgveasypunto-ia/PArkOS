"""``repo/log_transaccional.py`` -- read-only helpers for the admin
audit-log dashboard (IT-12).

KD-MOT-AUDIT-01 invariant: the helpers' bodies contain ONLY
``SELECT`` statements. NO ``UPDATE``, ``DELETE``, ``INSERT``, NO
``await session.commit()``. The audit-log table ``log_transaccional``
is [A] (append-only) -- REVOKE UPDATE, DELETE FROM rol_app is
asserted by migration 0001 + a BEFORE UPDATE OR DELETE trigger that
raises ``LOG_TRANSACCIONAL_INMUTABLE``. This module honors that.

Cursor design (DEC-AUDIT-01, mirror of F1.15): base64-encoded JSON
``(timestamp_evento_iso, uuid)`` -- the SECONDARY ``uuid`` is the
tie-breaker that prevents skip/repeat when two rows share the same
``timestamp_evento`` (a real risk for batch inserts where the same
``now()`` produces identical timestamps at microsecond precision).

The pagination ORDER is ``(timestamp_evento DESC, uuid ASC)`` -- DESC
matches the dashboard's "newest first" UX and lets the operator spot
anomalies quickly (the first 20 rows are the most recent).

Why this is a separate module from ``repo/hash_chain.py``: the hash
chain verifier is about INTEGRITY (does the chain link?), this
module is about VISIBILITY (what did each row do?). They share the
underlying table but the consumer patterns are different -- the
verifier runs in ``job_sync_cloud`` with a watermark + retry
contract, the dashboard hits a read endpoint on demand.

Note: ``log_transaccional`` does NOT have a ``created_at`` column --
the only timestamp is ``timestamp_evento`` (server-set per audit
invariant, but nullable in the schema per the [A] ``AppendOnlyBase``
contract). This module therefore uses a local cursor format that
carries ``timestamp_evento_iso`` + ``uuid``, independent of the
generic ``Cursor`` dataclass in ``repo.pagination``.
"""
from __future__ import annotations

import base64
import json
import uuid as uuid_lib
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.log_transaccional import LogTransaccional

_LIMIT_CEILING: int = 100


@dataclass(frozen=True)
class AuditCursor:
    """Local opaque cursor for the audit-log dashboard.

    Carries ``(timestamp_evento, uuid)`` -- the unique key the
    pagination ORDER uses. Mirrors the F1.15 cursor shape
    (``(vigente_desde, uuid)``) but bound to the audit table's actual
    timestamp column.
    """

    ts: datetime
    uuid: uuid_lib.UUID


class InvalidAuditCursorError(ValueError):
    """Raised when an audit cursor cannot be decoded."""


def encode_audit_cursor(items: list[LogTransaccional], limit: int) -> str | None:
    """Base64-encoded JSON ``(timestamp_evento_iso, uuid_str)``.

    Returns ``None`` at EOF. If ``items`` contains more rows than the
    page asked for (``limit + 1`` is the EOF probe), the cursor is the
    SHIPPED row's key (the row at ``items[limit - 1]``).
    """
    if len(items) <= limit:
        return None
    last = items[limit - 1]
    # ``timestamp_evento`` is nullable in the ORM contract but in
    # practice always stamped by ``append_only.append_event`` (the
    # ``[A]`` audit invariant). The cast bridges SQL-level typing to
    # the Pydantic-validated non-null contract at the wire boundary.
    payload = json.dumps(
        {
            "ts": cast(datetime, last.timestamp_evento).isoformat(),
            "uuid": str(last.uuid),
        },
        separators=(",", ":"),
    )
    return base64.b64encode(payload.encode("ascii")).decode("ascii")


def decode_audit_cursor(cursor: str | None) -> AuditCursor | None:
    """Decode the opaque cursor back into ``AuditCursor``.

    Returns ``None`` when the cursor is ``None`` (first page). Raises
    :class:`InvalidAuditCursorError` on malformed base64/JSON/missing
    keys -- the handler maps that to HTTP 400.
    """
    if cursor is None:
        return None
    try:
        decoded = base64.b64decode(cursor.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidAuditCursorError(f"invalid base64: {exc}") from exc
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise InvalidAuditCursorError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or "ts" not in data or "uuid" not in data:
        raise InvalidAuditCursorError(
            "missing required keys (ts, uuid) in cursor payload"
        )
    try:
        ts = datetime.fromisoformat(data["ts"])
        uuid = uuid_lib.UUID(data["uuid"])
    except (ValueError, TypeError) as exc:
        raise InvalidAuditCursorError(f"invalid cursor field: {exc}") from exc
    return AuditCursor(ts=ts, uuid=uuid)


async def listar_eventos_paginados(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    tabla_afectada: str | None,
    cursor: AuditCursor | None,
    limit: int,
    # --- HU-F20.4: cross-branch bitácora filters (additive, keyword-only,
    # all defaulted so the IT-12 call sites above -- audit.py + the
    # pre-existing TestListarEventosPaginados tests -- keep compiling and
    # behaving unchanged). ---
    uuid_sucursales: list[uuid_lib.UUID] | None = None,
    uuid_registro_afectado: uuid_lib.UUID | None = None,
    uuid_usuario: uuid_lib.UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> list[LogTransaccional]:
    """Return one page of ``prod.log_transaccional`` rows.

    KD-MOT-2025-10-01 (HU-F15.2): the function now accepts BOTH a
    branch selector (``uuid_sucursal``) and a singleton-table filter
    (``tabla_afectada``). At least one must be provided -- the schema
    validator rejects the no-selector case with 422. Filters compose
    with AND.

    HU-F20.4 (bitácora cross-branch read + search): five additive filters,
    all optional and AND-composed with everything above:

      - ``uuid_sucursales``: an IN-clause over MULTIPLE branches, used by
        the new cross-branch ``GET /admin/log-transaccional`` endpoint
        INSTEAD of the singular ``uuid_sucursal`` equality filter. The two
        are mutually exclusive in practice -- when ``uuid_sucursales`` is
        given it takes precedence over ``uuid_sucursal`` (the legacy IT-12
        caller never passes the new kwarg, so this branch is dead code for
        ``audit.py``).
      - ``uuid_registro_afectado`` / ``uuid_usuario``: plain equality
        filters on the affected-record uuid and the acting user uuid.
      - ``desde`` / ``hasta``: inclusive date-range filter on
        ``timestamp_evento``, mirroring ``admin_views.sync_log_list``'s
        exact convention (``func.date(col) >= desde`` / ``<= hasta`` --
        naive UTC column, DATE-truncated comparison so a ``desde`` of
        "today" includes every row from 00:00:00 that day). The 422
        ``rango_fecha_invalido`` check for ``desde > hasta`` lives in the
        route handler (``api/v1/auditoria.py``), same split IT-12 already
        uses for ``missing_selector``.

    Pagination (DEC-AUDIT-01):
      - ORDER BY ``(timestamp_evento DESC, uuid ASC)``.
      - Stable cursor: ``(timestamp_evento < cursor_ts) OR (timestamp_evento =
        cursor_ts AND uuid < cursor_uuid)`` -- excludes the cursor row and
        everything that sorts strictly after it in the DESC stream.

    Returns the rows in DESCENDING timestamp order (newest first).
    """
    limit = min(limit, _LIMIT_CEILING)

    stmt = select(LogTransaccional)
    if uuid_sucursales is not None:
        stmt = stmt.where(LogTransaccional.uuid_sucursal.in_(uuid_sucursales))
    elif uuid_sucursal is not None:
        stmt = stmt.where(LogTransaccional.uuid_sucursal == uuid_sucursal)
    if tabla_afectada is not None:
        stmt = stmt.where(LogTransaccional.tabla_afectada == tabla_afectada)
    if uuid_registro_afectado is not None:
        stmt = stmt.where(LogTransaccional.uuid_registro_afectado == uuid_registro_afectado)
    if uuid_usuario is not None:
        stmt = stmt.where(LogTransaccional.uuid_usuario == uuid_usuario)
    if desde is not None:
        stmt = stmt.where(func.date(LogTransaccional.timestamp_evento) >= desde)
    if hasta is not None:
        stmt = stmt.where(func.date(LogTransaccional.timestamp_evento) <= hasta)
    stmt = stmt.order_by(
        LogTransaccional.timestamp_evento.desc(),
        LogTransaccional.uuid.asc(),
    ).limit(limit + 1)

    if cursor is not None:
        cursor_ts = cursor.ts
        cursor_uuid = cursor.uuid
        cursor_clause = or_(
            LogTransaccional.timestamp_evento < cursor_ts,
            and_(
                LogTransaccional.timestamp_evento == cursor_ts,
                LogTransaccional.uuid < cursor_uuid,
            ),
        )
        stmt = stmt.where(cursor_clause)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def buscar_prefijo(
    session: AsyncSession,
    *,
    prefijo: str,
    uuid_sucursales: list[uuid_lib.UUID] | None,
    limit: int,
) -> list[LogTransaccional]:
    """Typeahead search over ``prod.log_transaccional`` (HU-F20.4).

    Matches rows whose ``tabla_afectada`` OR ``uuid_registro_afectado``
    (cast to text) starts with ``prefijo`` (case-insensitive prefix match,
    ``ILIKE 'prefijo%'``). No cursor -- this is a bounded typeahead, not a
    paginated listing; the caller (``api/v1/auditoria.py``) caps ``limit``
    at 10 (literal spec: "límite 10 resultados").

    ``uuid_sucursales`` applies the SAME cross-branch tenant scoping as
    :func:`listar_eventos_paginados` -- a typeahead must not leak another
    tenant's ``tabla_afectada``/``uuid_registro_afectado`` combinations
    either, so an admin only ever searches within their own permitted
    branches. ``None`` means "no branch scoping" (not used by the route,
    which always resolves a concrete permitted-branch list first, but kept
    optional so the helper is independently testable/reusable).

    Ordering: ``timestamp_evento DESC`` (newest first) is a reasonable,
    documented tiebreak for a typeahead -- there is no natural ordering
    for "which of N matching rows to show first", and newest-first matches
    every other bitácora surface in this module.
    """
    pattern = f"{prefijo}%"
    stmt = select(LogTransaccional).where(
        or_(
            LogTransaccional.tabla_afectada.ilike(pattern),
            LogTransaccional.uuid_registro_afectado.cast(String).ilike(pattern),
        )
    )
    if uuid_sucursales is not None:
        stmt = stmt.where(LogTransaccional.uuid_sucursal.in_(uuid_sucursales))
    stmt = stmt.order_by(LogTransaccional.timestamp_evento.desc()).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())

