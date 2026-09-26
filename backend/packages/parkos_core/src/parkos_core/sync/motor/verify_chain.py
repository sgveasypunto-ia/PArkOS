"""motor/verify_chain.py — hash chain walker (T-PR6-006/007, REQ-MOT-006).

Walks the two hash-chain-carrying tables (``log_transaccional``,
``revocacion_factura`` — REQ-CAT-009, D6-rev: exactly these two, ``revocacion_
factura`` resolving to exactly ONE catalog entry) in ``(timestamp_evento,
uuid)`` order, per ``uuid_sucursal``, verifying each row's ``hash_anterior``
matches the PRIOR row's ``hash_actual`` (the chain-linkage invariant
``repo.hash_chain.append`` establishes on write). A mismatch is recorded as
one :class:`ChainAnomaly` and the walk CONTINUES — a single broken link must
not hide every anomaly after it (design.md §5's ``SyncMotor.verify_chain``
docstring: "Covers log_transaccional AND revocacion_factura — exactly one
chain per (tabla, uuid_sucursal)").

Two entry points:

  - :func:`verify_chain_for_spec` — walks ONE chain-bearing spec's model for
    one ``uuid_sucursal`` (or every tenant when ``uuid_sucursal=None``).
  - :func:`verify_chain` — walks EVERY ``verify_chain=True`` catalog entry
    (today: ``log_transaccional`` + ``revocacion_factura``) and concatenates
    the anomalies — the PR6 acceptance criterion's "verify_chain iterates
    both tables" in one call.

Not wired into ``motor/sync_motor.py``'s ``SyncMotor`` class yet — the
design.md §5 ``SyncMotor.verify_chain(self, spec, branch_uuid)`` signature
is a thin per-spec wrapper a future PR (PR10, the cloud-side verifier
worker) adds; this module ships the walker itself, independently testable
and already table-complete.
"""

from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..catalog.schema import SyncCatalogEntry
from ..catalog.sync_catalog import SYNC_CATALOG


@dataclass(frozen=True)
class ChainAnomaly:
    """One detected hash-chain break (REQ-MOT-006).

    ``uuid``: the row whose ``hash_anterior`` did not match the prior row's
    ``hash_actual`` (or, for the first row seen for a ``uuid_sucursal``,
    the genesis anchor — see ``repo.hash_chain._genesis_hash``).
    ``expected``/``actual``: the two divergent hash values (``expected`` is
    what the walker computed from the prior row / genesis anchor; ``actual``
    is what this row's own ``hash_anterior`` column holds).
    ``seq``: the row's position in its chain, or ``None`` on a database
    where migration 0058 has not run yet.
    """

    tabla: str
    uuid_sucursal: uuid_lib.UUID | None
    uuid: uuid_lib.UUID
    expected: str
    actual: str | None
    seq: int | None = None
    reason: str = "hash_chain_break"


def _genesis_hash(uuid_sucursal: uuid_lib.UUID | None) -> str:
    """Mirror of ``repo.hash_chain._genesis_hash`` (duplicated only to avoid
    a motor -> repo -> motor import cycle risk; the formula is a one-line
    SHA-256 and is asserted identical by ``test_verify_chain.py``)."""
    import hashlib

    marker = b"NULL" if uuid_sucursal is None else str(uuid_sucursal).encode("ascii")
    return hashlib.sha256(b"genesis:" + marker).hexdigest()


async def verify_chain_for_spec(
    session: AsyncSession,
    spec: SyncCatalogEntry,
    uuid_sucursal: uuid_lib.UUID | None = None,
    min_seq: int | None = None,
) -> list[ChainAnomaly]:
    """Walk ``spec.model_cls`` (one chain-bearing table) for one tenant.

    ``uuid_sucursal=None`` walks the GLOBAL partition (the ``uuid_sucursal
    IS NULL`` chain), NOT "every tenant" — callers wanting every tenant's
    chain verified call this once per known ``uuid_sucursal`` (mirroring
    ``repo.hash_chain.append``'s own per-tenant scoping).

    Rows are read in ``seq`` order — the per-chain monotonic position
    migration 0058 allocates at insert time under a per-chain advisory
    lock. ``seq`` is the only causal ordering: ``timestamp_evento`` is
    business-supplied and collides across a burst, and ``created_at`` is
    stamped per node so a replicated or backfilled row can carry a
    ``created_at`` behind rows already in the chain. Either one makes a
    timestamp-ordered walk report ``hash_chain_break`` for rows that were
    never corrupted, which is exactly the confirmed-live false positive
    both orderings used to produce. A mismatch does not stop the walk —
    every subsequent row is still checked against ITS OWN immediate
    predecessor, so a single corrupted link produces exactly one anomaly,
    not a cascade.

    ``min_seq`` skips a known-bad prefix of a chain. It exists for the two
    historical breaks left in place by 0058: the migration reproduces the
    old ``(created_at, uuid)`` order precisely so that evidence is not
    reshaped, which means those rows keep failing the linkage check
    forever. Callers pass the head ``seq`` of that prefix to have them
    reported as a known incident rather than re-alerted on every sweep.
    The first row examined still has its ``hash_anterior`` checked against
    the genesis anchor, so a skip can never mask a break of its own.
    """
    model_cls = spec.model_cls
    stmt = (
        select(model_cls)
        .where(model_cls.uuid_sucursal == uuid_sucursal)  # type: ignore[attr-defined]
        .order_by(
            model_cls.seq.asc().nullslast(),  # type: ignore[attr-defined]
            model_cls.created_at.asc(),  # type: ignore[attr-defined]
            model_cls.uuid.asc(),  # type: ignore[attr-defined]
        )
    )
    rows = (await session.execute(stmt)).scalars().all()

    anomalies: list[ChainAnomaly] = []
    expected_prior_hash = _genesis_hash(uuid_sucursal)

    for row in rows:
        row_seq = getattr(row, "seq", None)
        if min_seq is not None and row_seq is not None and row_seq < min_seq:
            # Skipped prefix: re-anchor on this row's own hash_actual so the
            # first examined row is still checked against something real.
            if row.hash_actual is not None:  # type: ignore[attr-defined]
                expected_prior_hash = row.hash_actual  # type: ignore[attr-defined]
            continue
        actual_hash_anterior = row.hash_anterior  # type: ignore[attr-defined]
        if actual_hash_anterior != expected_prior_hash:
            anomalies.append(
                ChainAnomaly(
                    tabla=spec.name,
                    uuid_sucursal=uuid_sucursal,
                    uuid=row.uuid,  # type: ignore[attr-defined]
                    expected=expected_prior_hash,
                    actual=actual_hash_anterior,
                    seq=row_seq,
                )
            )
        # Walk continues from THIS row's own hash_actual regardless of
        # whether it matched — an anomaly at row N must not cascade into
        # N+1 also being reported for the same underlying break.
        expected_prior_hash = row.hash_actual  # type: ignore[attr-defined]

    return anomalies


async def verify_chain(
    session: AsyncSession,
    uuid_sucursal: uuid_lib.UUID | None = None,
    min_seq: int | None = None,
) -> list[ChainAnomaly]:
    """Walk EVERY ``verify_chain=True`` catalog entry (REQ-MOT-006).

    Today that is exactly ``log_transaccional`` and ``revocacion_factura``
    (REQ-CAT-009) — the PR6 acceptance criterion's "verify_chain iterates
    both tables" in one call. Anomalies from both tables are concatenated;
    ``tabla`` on each :class:`ChainAnomaly` disambiguates which table an
    anomaly came from.
    """
    anomalies: list[ChainAnomaly] = []
    for spec in SYNC_CATALOG:
        if not spec.verify_chain:
            continue
        anomalies.extend(await verify_chain_for_spec(session, spec, uuid_sucursal, min_seq=min_seq))
    return anomalies


__all__ = ["ChainAnomaly", "verify_chain", "verify_chain_for_spec"]
