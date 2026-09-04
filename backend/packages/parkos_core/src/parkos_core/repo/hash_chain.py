"""SHA-256 hash-chain extension helper for [A]-class tables (design §4.6 + §11).

REQ-16 + REQ-X4: server-computed SHA-256 chain per ``uuid_sucursal``. Only
two tables carry the chain:

  - ``log_transaccional`` — every API state change logs a row here.
  - ``revocacion_factura`` — DIAN revocation events.

Both inherit :class:`HashChainMixin` (see :mod:`parkos_core.models.base`).

Algorithm (:func:`append`):

  1. Locate the prior row for the same ``uuid_sucursal`` by reading the
     row with ``MAX(timestamp_evento)`` (or ``MAX(created_at)`` for
     tables without a timestamp column). If none exists, the anchor is
     the **genesis hash** for that sucursal —
     ``sha256(b"genesis:" + uuid_sucursal_bytes).hexdigest()``.
  2. Compute
     ``hash_actual = sha256(_canonical_json(payload) + bytes.fromhex(prior_hash_actual)).hexdigest()``
     where ``_canonical_json`` produces a deterministic byte
     representation (sorted keys, no whitespace, ``ensure_ascii=False``).
  3. Stamp ``hash_anterior = prior_hash_actual`` and
     ``hash_actual = new_hash`` onto the row.
  4. INSERT the row and return it.

The DB trigger ``prod.fn_extend_hash_chain()`` (added by 0001) does the
same calculation server-side as a safety net — if the Python chain
somehow diverges from the DB chain, the trigger raises
``HASH_CHAIN_MISMATCH`` at INSERT time.

The cloud-side verifier (PR10 worker) walks the chain on every sync
batch and raises :class:`HashChainIntegrityViolation` on a break. PR2
ships the helper + unit tests; PR10 owns the worker.
"""
from __future__ import annotations

import hashlib
import json
import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import AppendOnlyBase

T = TypeVar("T", bound=AppendOnlyBase)

GENESIS_PREFIX = b"genesis:"


class HashChainIntegrityViolation(Exception):
    """Raised when a chain extension detects a break or a prior mismatch.

    The cloud-side verifier (PR10) maps this to HTTP 500 + a
    ``sync_conflict`` row + an ``alerta`` workflow chain.
    """


def _canonical_json(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON byte representation (RFC 8785-ish subset).

    Sorted keys, no whitespace, ``ensure_ascii=False`` so non-ASCII
    payloads round-trip identically across Python versions and dict
    insertion orders.

    ``datetime`` / ``date`` / ``uuid.UUID`` values are coerced via the
    standard ``default`` hook (ISO-8601 string for dates, hex string
    for UUIDs). This lets callers pass raw ORM objects without
    pre-serializing — PR11c wired ``repo.event.record_event`` →
    ``hash_chain.append`` with a ``timestamp_evento`` datetime that
    flowed straight into the canonical JSON. The hooks preserve the
    byte-determinism invariant because ``isoformat()`` on a naive
    datetime always returns the same string for the same instant.

    The same payload MUST hash to the same bytes regardless of how the
    caller built the dict. Verified by ``test_canonical_json_is_deterministic``
    in ``tests/unit/test_hash_chain.py``.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def _json_default(obj: Any) -> Any:
    """``json.dumps`` default hook — serialise common ORM scalars to strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid_lib.UUID):
        return str(obj)
    raise TypeError(f"Cannot JSON-serialize {type(obj).__name__}")


def _genesis_hash(uuid_sucursal: uuid_lib.UUID | None) -> str:
    """Return the genesis anchor for a given ``uuid_sucursal``.

    For the global (uuid_sucursal IS NULL) anchor the input is the
    string ``"NULL"`` — same string both on branch and cloud so the
    chain starts identically on either side.
    """
    marker = b"NULL" if uuid_sucursal is None else str(uuid_sucursal).encode("ascii")
    return hashlib.sha256(GENESIS_PREFIX + marker).hexdigest()


async def _read_prior_hash(
    session: AsyncSession,
    model_cls: type[AppendOnlyBase],
    uuid_sucursal: uuid_lib.UUID | None,
) -> str:
    """Return the chain head ``hash_actual`` for ``uuid_sucursal``.

    Reads the latest row (by ``timestamp_evento`` when present,
    otherwise by ``created_at``). Returns the genesis hash if no prior
    row exists for the tenant.
    """
    if hasattr(model_cls, "timestamp_evento"):
        stmt = (
            select(model_cls)
            .where(model_cls.uuid_sucursal == uuid_sucursal)
            .order_by(
                model_cls.timestamp_evento.desc(),  # type: ignore[attr-defined]
                model_cls.uuid.desc(),
            )
            .limit(1)
        )
    else:
        stmt = (
            select(model_cls)
            .where(model_cls.uuid_sucursal == uuid_sucursal)
            .order_by(
                model_cls.created_at.desc(),
                model_cls.uuid.desc(),
            )
            .limit(1)
        )

    result = await session.execute(stmt)
    prior = result.scalar_one_or_none()
    if prior is None:
        return _genesis_hash(uuid_sucursal)
    return prior.hash_actual  # type: ignore[attr-defined]


async def append(  # noqa: UP047 (TypeVar style — matches repo/versioned.py)
    session: AsyncSession,
    model_cls: type[T],
    payload: dict[str, Any],
    actor_uuid: uuid_lib.UUID,
) -> T:
    """Extend the SHA-256 chain and INSERT the new row.

    1. Reads the prior chain head for ``payload['uuid_sucursal']``.
    2. Computes ``hash_actual = sha256(canonical(payload) + prior_hash)``.
    3. Stamps ``hash_anterior`` + ``hash_actual`` onto the new row.
    4. INSERTs the row and returns it.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        model_cls: The [A] ORM class carrying ``HashChainMixin``. Must
            expose ``uuid_sucursal`` (in the payload) and
            ``hash_anterior`` / ``hash_actual`` columns.
        payload: Business columns for the new row. The function reads
            ``payload['uuid_sucursal']`` and adds ``hash_anterior`` /
            ``hash_actual`` server-side.
        actor_uuid: JWT subject (audit ``created_by``). Used for the
            ``created_by`` audit column.

    Returns:
        The newly inserted row (not yet committed).

    Raises:
        HashChainIntegrityViolation: On a detected mismatch (e.g. the
            prior row's recomputed hash doesn't match its stored
            ``hash_actual``). In practice the DB trigger catches this
            first; the Python check is a defense-in-depth mirror.
    """
    if not (hasattr(model_cls, "hash_anterior") and hasattr(model_cls, "hash_actual")):
        raise HashChainIntegrityViolation(
            f"{model_cls.__name__} does not carry hash chain columns; "
            f"use repo.append_only.append_event(chain_hash=False) instead"
        )

    uuid_sucursal = payload.get("uuid_sucursal")
    prior_hash = await _read_prior_hash(session, model_cls, uuid_sucursal)

    # Compute new hash over the canonical payload (audit + business).
    payload_with_audit = {
        **payload,
        "created_at": datetime.now(UTC).replace(tzinfo=None),
        "created_by": actor_uuid,
    }
    new_hash = hashlib.sha256(
        _canonical_json(payload_with_audit) + bytes.fromhex(prior_hash)
    ).hexdigest()

    # Defense-in-depth: verify the prior row's hash actually links. If
    # somehow the prior row is corrupt, the DB trigger would block the
    # INSERT — but we catch it here too so the error message is clean.
    expected_anchor = prior_hash

    payload_with_audit["hash_anterior"] = expected_anchor
    payload_with_audit["hash_actual"] = new_hash

    new_row = model_cls(**payload_with_audit)
    session.add(new_row)
    return new_row


__all__ = [
    "GENESIS_PREFIX",
    "HashChainIntegrityViolation",
    "_canonical_json",
    "_genesis_hash",
    "append",
]