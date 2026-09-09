"""hooks/impls/log_transaccional_chain.py — ``LogTransaccionalChain`` (T-PR6-001/002).

REQ-HOOK-008: ``hook_chain_extend`` bound to ``log_transaccional``. Every
event extends the per-``uuid_sucursal`` SHA-256 hash chain — the same
primitive :func:`bi_temporal_compensation`'s ``hook_post_insert`` already
wraps for its OWN compensating row (``repo.hash_chain.append``, PR2). This
module is the CANONICAL, catalog-registered implementation that slot exists
for (design.md §6): given ``ctx.payload`` (the business attributes for one
``log_transaccional`` event), it invokes :func:`repo.hash_chain.append`,
which:

  1. Reads the prior chain head for ``payload['uuid_sucursal']`` — or
     bootstraps the real genesis row on first use (PR6, ``repo/hash_chain.
     py::_ensure_genesis_row``).
  2. Computes ``hash_actual = sha256(canonical(payload_with_audit) +
     bytes.fromhex(hash_anterior))``.
  3. Stamps and INSERTs the row.

Not wired into ``motor/apply_row.py``'s own ``_LOG_TRANSACCIONAL`` spec
dispatch today: ``apply_strategy="append_event"`` combined with
``spec.hash_chain=True`` already extends the chain at the repo-call step
(step 3) for any ``apply_row(_LOG_TRANSACCIONAL_spec, ...)`` invocation —
nothing in the current codebase makes that call directly (``log_
transaccional`` rows are always created as a SIDE EFFECT of another spec's
apply — ``repo.event.record_event``, ``repo.versioned.close_and_insert``,
``BiTemporalCompensation`` — never as a top-level push). This hook exists
as the catalog-registered, directly-callable, testable unit the design's
hook contract requires; a future PR wiring actual cross-node replication of
``log_transaccional`` rows through ``apply_row`` directly will need to
address the double-extension interaction with step 3's own ``chain_hash``
dispatch at that time (not pre-empted here — see the PR6 apply report's
"Deviations" section).
"""
from __future__ import annotations

from .. import registry
from ..base import HookContext, HookResult


async def log_transaccional_chain(ctx: HookContext) -> HookResult:
    """``hook_chain_extend`` — REQ-HOOK-008 chain extension for ``log_transaccional``."""
    from ....models.A.log_transaccional import LogTransaccional
    from ....repo import hash_chain

    new_row = await hash_chain.append(
        ctx.session,
        LogTransaccional,
        ctx.payload,
        actor_uuid=ctx.actor_uuid,
    )

    return HookResult(
        proceed=True,
        chain_extension=(
            new_row.hash_anterior.encode("ascii"),
            new_row.hash_actual.encode("ascii"),
        ),
    )


registry.register("log_transaccional_chain", log_transaccional_chain)

__all__ = ["log_transaccional_chain"]
