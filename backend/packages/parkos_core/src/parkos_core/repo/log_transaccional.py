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
from datetime import datetime
from typing import cast

from sqlalchemy import and_, or_, select
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
    uuid_sucursal: uuid_lib.UUID,
    cursor: AuditCursor | None,
    limit: int,
) -> list[LogTransaccional]:
    """Return one page of ``prod.log_transaccional`` rows for a branch.

    KD-MOT-AUDIT-01: SELECT-only. NO UPDATE/DELETE/INSERT. NO commit.

    Pagination (DEC-AUDIT-01):
      - ORDER BY ``(timestamp_evento DESC, uuid ASC)``.
      - Stable cursor: ``(timestamp_evento < cursor_ts) OR (timestamp_evento =
        cursor_ts AND uuid < cursor_uuid)`` -- excludes the cursor row and
        everything that sorts strictly after it in the DESC stream.

    Returns the rows in DESCENDING timestamp order (newest first).
    """
    limit = min(limit, _LIMIT_CEILING)

    stmt = (
        select(LogTransaccional)
        .where(LogTransaccional.uuid_sucursal == uuid_sucursal)
        .order_by(
            LogTransaccional.timestamp_evento.desc(),
            LogTransaccional.uuid.asc(),
        )
        .limit(limit + 1)
    )
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

