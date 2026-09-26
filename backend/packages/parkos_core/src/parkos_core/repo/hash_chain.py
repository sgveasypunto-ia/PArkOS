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

The DB trigger ``prod.fn_extend_hash_chain()`` (added by 0001, attached only
to ``log_transaccional``) does the same calculation server-side as a safety
net — if the Python chain somehow diverges from the DB chain, the trigger
raises ``HASH_CHAIN_MISMATCH`` at INSERT time. That same trigger has an
escape valve for the very FIRST row of a ``uuid_sucursal``: a row with
``accion='inicialización'`` AND ``hash_anterior = hash_actual`` (both equal
to the per-``uuid_sucursal`` genesis anchor) passes without requiring a
prior row to exist. Every OTHER row raises
``HASH_CHAIN_INTEGRITY_VIOLATION: no genesis row for uuid_sucursal=%`` when
no prior row is found for that tenant.

**Genesis-row bootstrap (PR6, REQ-16 + REQ-X4).** ``0001_initial_schema.py``
documents (see its "Hash-chain genesis (runtime)" comment) that the genesis
row is deliberately NOT inserted at migration time — it is meant to be
created by the application the first time a chain is extended for a given
``uuid_sucursal``. Before PR6, nothing actually did this: :func:`append`
computed the genesis anchor for use as the FIRST real row's
``hash_anterior``, but never persisted an actual genesis row, so the DB
trigger's "no genesis row" branch fired on that very first INSERT.
:func:`_ensure_genesis_row` closes this gap — see its docstring.

The cloud-side verifier (PR10 worker) walks the chain on every sync
batch and raises :class:`HashChainIntegrityViolation` on a break. PR2
ships the helper + unit tests; PR10 owns the worker.
"""

from __future__ import annotations

import hashlib
import json
import uuid as uuid_lib
from datetime import UTC, date, datetime
from typing import Any, TypeVar

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import AppendOnlyBase

T = TypeVar("T", bound=AppendOnlyBase)

GENESIS_PREFIX = b"genesis:"

# The ``accion`` that marks a chain's genesis row. The DB trigger
# (``fn_extend_hash_chain``) branches on the same literal, so this constant
# exists to keep the Python side from drifting away from the SQL side — the
# ``d4c7fc74`` incident was a genesis row landing on a live chain, and a
# one-character drift here would silently reopen it.
GENESIS_ACCION = "inicialización"


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
    """``json.dumps`` default hook — serialise common ORM scalars to strings.

    ``date`` handling added wiring the post-PR14 full-catalog-sync closing
    exercise: ``log_transaccional``/``revocacion_factura`` both carry a real
    ``fecha_retencion_hasta`` ``Date`` column (DIAN retention,
    ``RetentionMixin``/``_retention_column()``), populated by a DB
    ``server_default`` the instant either row is inserted — a hash-chain
    payload for either table can therefore legitimately carry a plain
    ``datetime.date`` value (never just ``datetime.datetime``), and this
    hook previously raised ``TypeError: Cannot JSON-serialize date`` on the
    very first one it ever saw (``datetime.date`` is NOT a ``datetime.
    datetime`` instance — ``isinstance(obj, datetime)`` is ``False`` for a
    bare ``date``, so the existing branch never matched it). Checked AFTER
    ``datetime`` — ``datetime.datetime`` is itself a subclass of
    ``datetime.date``, so ``date`` must be the second, narrower check or it
    would incorrectly swallow real datetimes first.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
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


# Sentinel ``timestamp_evento`` stamped on a bootstrapped genesis row. It
# sorts before any real business event for the same ``uuid_sucursal`` so a
# query that orders by ``timestamp_evento`` still sees the genesis row
# first. It is no longer load-bearing for chain order — migration 0058
# walks by ``seq`` — but it is kept so existing reads that order by
# ``timestamp_evento`` keep behaving as before.
_GENESIS_TIMESTAMP = datetime(1970, 1, 1, tzinfo=UTC).replace(tzinfo=None)


async def _ensure_genesis_row(
    session: AsyncSession,
    model_cls: type[AppendOnlyBase],
    uuid_sucursal: uuid_lib.UUID | None,
    genesis_hash: str | None = None,
) -> None:
    """Idempotently bootstrap the real genesis row for ``uuid_sucursal``.

    ``prod.fn_extend_hash_chain()`` (0001_initial_schema.py, attached only to
    ``log_transaccional``) rejects the FIRST INSERT for a ``uuid_sucursal``
    with ``HASH_CHAIN_INTEGRITY_VIOLATION: no genesis row`` unless an
    explicit escape-valve row already exists: ``accion='inicialización'``
    AND ``hash_anterior = hash_actual`` (both the per-``uuid_sucursal``
    genesis anchor). The migration deliberately does NOT insert that row —
    see its "Hash-chain genesis (runtime)" comment — the application is
    responsible for creating it on first use. This function IS that runtime
    bootstrap: called from :func:`_read_head` exactly when no prior
    row exists yet for ``uuid_sucursal`` (which is also the only moment a
    genesis row is legitimately missing), so a second call for the same
    ``uuid_sucursal`` never happens — the genesis row it inserts here
    immediately becomes the "prior row" every subsequent
    :func:`_read_head` call for this tenant finds instead.

    Works for both hash-chain carriers via ``hasattr`` rather than
    branching on ``model_cls`` by name: ``log_transaccional`` has an
    ``accion`` / ``tabla_afectada`` discriminator pair the DB trigger's
    escape valve keys off of; ``revocacion_factura`` has neither column (and
    no DB trigger is even attached to it — only ``log_transaccional_hash_
    chain`` exists in 0001), so those two fields are simply omitted for it.
    Every other column on both models is nullable, so the minimal row below
    satisfies every NOT NULL constraint.

    ``timestamp_evento`` is stamped with the far-past :data:`_GENESIS_TIMESTAMP`
    sentinel rather than left ``NULL`` — Postgres sorts ``NULL`` FIRST on a
    ``DESC`` order by default, which would make an untimestamped genesis row
    outrank every real row forever and permanently short-circuit the chain.
    """
    anchor = genesis_hash if genesis_hash is not None else _genesis_hash(uuid_sucursal)
    genesis_attrs: dict[str, Any] = {
        "uuid_sucursal": uuid_sucursal,
        "timestamp_evento": _GENESIS_TIMESTAMP,
        "hash_anterior": anchor,
        "hash_actual": anchor,
        # The genesis row is position 1 of its chain; 0058 makes that
        # explicit and NOT NULL.
        "seq": 1,
        "created_at": datetime.now(UTC).replace(tzinfo=None),
        "created_by": None,
    }
    if hasattr(model_cls, "accion"):
        genesis_attrs["accion"] = GENESIS_ACCION
    if hasattr(model_cls, "tabla_afectada"):
        genesis_attrs["tabla_afectada"] = model_cls.__tablename__

    genesis_row = model_cls(**genesis_attrs)
    session.add(genesis_row)
    # Flush NOW (not just add) — the real row this bootstrap unblocks is
    # about to be added to the SAME session and MUST see this genesis row
    # already physically INSERTed (same transaction, read-your-own-writes)
    # before its own INSERT statement reaches the DB trigger.
    await session.flush()


async def _chain_lock(session: AsyncSession, uuid_sucursal: uuid_lib.UUID | None) -> None:
    """Take the per-chain advisory lock ``prod.fn_extend_hash_chain`` uses.

    The trigger allocates ``seq`` under this lock, so anything that reads the
    head and then inserts must hold the same lock, or two concurrent
    ``append`` calls would both read head N, both stamp
    ``hash_anterior = head_N``, and the second would be rejected by the
    trigger's linkage check with an error that has nothing to do with
    corruption.

    The key is derived by Postgres from the same expression the trigger
    uses, rather than reimplemented here, so the two can never drift.
    """
    key = "GLOBAL" if uuid_sucursal is None else str(uuid_sucursal)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(('x' || substr(md5(:k), 1, 16))::bit(64)::bigint)"),
        {"k": key},
    )


async def _read_head(
    session: AsyncSession,
    model_cls: type[AppendOnlyBase],
    uuid_sucursal: uuid_lib.UUID | None,
) -> tuple[int, str]:
    """Return ``(next_seq, head_hash_actual)`` for ``uuid_sucursal``.

    Reads the highest ``seq`` — the per-chain monotonic position migration
    0058 introduced — and returns the position the NEXT row must occupy.
    ``seq`` is the only causal ordering available: it records append order,
    so a row that arrives late with a backdated ``created_at`` still lands
    at the head instead of appearing mid-chain and making its successor
    look broken.

    ``seq DESC NULLS LAST`` with the old ``(created_at DESC, uuid DESC)``
    as a tie-break keeps this readable on a database where 0058 has not run
    (every ``seq`` NULL) instead of failing outright.

    An empty chain bootstraps its genesis row and reports ``(2, anchor)``:
    the genesis row itself is ``seq`` 1.

    History: this used to order by ``created_at``, and before that by
    ``timestamp_evento``. Neither is causal — ``timestamp_evento`` is
    business-supplied and collides across a burst of events, and
    ``created_at`` is stamped per node and can be replicated backwards.
    Both produced real ``hash_chain_break`` alerts for rows that were never
    corrupted, which is what 0058 removes at the source.
    """
    stmt = (
        select(model_cls)
        .where(model_cls.uuid_sucursal == uuid_sucursal)
        .order_by(
            model_cls.seq.desc().nullslast(),  # type: ignore[attr-defined]
            model_cls.created_at.desc(),  # type: ignore[attr-defined]
            model_cls.uuid.desc(),  # type: ignore[attr-defined]
        )
        .limit(1)
    )

    result = await session.execute(stmt)
    prior = result.scalar_one_or_none()
    if prior is None:
        genesis = _genesis_hash(uuid_sucursal)
        await _ensure_genesis_row(session, model_cls, uuid_sucursal, genesis)
        return 2, genesis
    prior_seq = getattr(prior, "seq", None)
    return (prior_seq + 1 if prior_seq is not None else 2), prior.hash_actual  # type: ignore[attr-defined]


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
    # Serialize read-head + INSERT against every other appender on this
    # chain AND against the trigger's own seq allocation. Without this, two
    # concurrent calls both stamp the same hash_anterior and the second is
    # rejected by the trigger's linkage check.
    await _chain_lock(session, uuid_sucursal)
    next_seq, prior_hash = await _read_head(session, model_cls, uuid_sucursal)

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
    # ``seq`` is stamped here as well as by the trigger. On
    # ``log_transaccional`` the trigger recomputes the identical value (it
    # holds the same advisory lock), so this is a mirror. On
    # ``revocacion_factura``, which has never had a DB trigger, this IS the
    # only allocator -- without it the 0058 NOT NULL constraint rejects
    # every insert.
    payload_with_audit["seq"] = next_seq

    new_row = model_cls(**payload_with_audit)
    session.add(new_row)
    return new_row


__all__ = [
    "GENESIS_ACCION",
    "GENESIS_PREFIX",
    "HashChainIntegrityViolation",
    "_canonical_json",
    "_ensure_genesis_row",
    "_genesis_hash",
    "append",
]
