"""motor/apply_row.py — dispatch on ``spec.apply_strategy`` + hook lifecycle
(T-PR4-005, T-PR4-006, T-PR4-007).

REQ-MOT-001..004, REQ-HOOK-003: applies one row from a remote push. Never
writes to the DB directly — every ``apply_strategy`` branch delegates to a
``repo/*`` helper (``repo.versioned``, ``repo.event``, ``repo.append_only``,
``repo.workflow``, ``repo.session_cycle``) so audit-first invariants
(bi-temporal close+insert for ``[V]``, append-only for ``[A]``/``[L-E]``,
state-machine validation for ``[L-W]``) stay enforced in exactly one place —
not duplicated here.

Hook lifecycle order (REQ-HOOK-003, D18):

    hook_validate_parent -> hook_pre_insert -> repo call
        -> hook_post_insert -> hook_chain_extend

``hook_validate_parent`` runs — and can short-circuit to
``ApplyResult(status=RETRY, reason="parent_missing")`` — strictly BEFORE the
repo call, so a missing declared parent never reaches persistence (the
defect D18 fixes: the prior design ran parent validation *after* the write,
which could only observe an FK violation, not prevent it).

``spec.snapshot_columns`` (D20, REQ-CAT-020) travel inside ``payload``
unmodified all the way to the repo call — this module never reads a live
catalog table (``impuestos``, ``otros_cobros``) to recompute them; see
``test_snapshot_columns_never_recomputed`` (T-PR4-007).
"""
from __future__ import annotations

import inspect
import uuid as uuid_lib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...repo import append_only, event, session_cycle, versioned, workflow
from ..catalog.schema import SyncCatalogEntry
from ..hooks import registry
from ..hooks.base import HookContext, HookResult
from .apply_result import ApplyResult


class ApplyRowError(Exception):
    """Raised for a catalog entry with an unknown/unset ``apply_strategy``."""


async def _invoke_hook(hook: registry.HookFn, ctx: HookContext) -> HookResult:
    """Call ``hook``, awaiting the result only if it is actually awaitable.

    REQ-HOOK-015's test-injection precedent is a plain sync lambda
    (``lambda ctx: HookResult(proceed=True)``); real PR5/PR6 hook
    implementations are ``async def`` because they read the DB
    (``IdentityReconciler``, ``ValidateParentChain``, ...). Both shapes call
    through this one path.
    """
    result = hook(ctx)
    if inspect.isawaitable(result):
        result = await result
    return result


async def _dispatch_repo_call(
    session: AsyncSession,
    spec: SyncCatalogEntry,
    payload: dict[str, Any],
    *,
    actor_uuid: uuid_lib.UUID,
    log_tx: bool,
) -> Any:
    """The one ``apply_strategy`` -> ``repo/*`` dispatch table (REQ-MOT-001).

    Payload conventions (this module's contract, not re-derived elsewhere):

      - ``close_and_insert``: an optional reserved ``current_uuid`` key
        names the local row to close (``None``/absent for a first insert);
        every other key is a business attribute for the new version.
      - ``append_transition``: an optional reserved ``parent_uuid`` key
        names the previous row in the ``[L-W]`` chain (``None``/absent for
        the chain's root row); every other key is a business attribute.
      - ``record_event`` / ``append_event``: ``payload`` is passed through
        as the event's business attributes verbatim.
      - ``session_cycle``: ``payload["estado"] == "cerrado"`` dispatches to
        ``close_login_with_log`` (``payload["uuid"]`` names the login row);
        anything else dispatches to ``record_login``.
    """
    strategy = spec.apply_strategy

    if strategy == "close_and_insert":
        current_uuid = payload.get("current_uuid")
        new_attrs = {k: v for k, v in payload.items() if k != "current_uuid"}
        return await versioned.close_and_insert(
            session,
            spec.model_cls,
            current_uuid=current_uuid,
            new_attrs=new_attrs,
            actor_uuid=actor_uuid,
            log_tx=log_tx,
        )

    if strategy == "record_event":
        return await event.record_event(
            session,
            spec.model_cls,
            actor_uuid=actor_uuid,
            new_attrs=payload,
            log_tx=log_tx,
        )

    if strategy == "append_event":
        return await append_only.append_event(
            session,
            spec.model_cls,
            payload,
            actor_uuid=actor_uuid,
            chain_hash=spec.hash_chain,
        )

    if strategy == "append_transition":
        parent_uuid = payload.get("parent_uuid")
        new_attrs = {k: v for k, v in payload.items() if k != "parent_uuid"}
        return await workflow.append_transition(
            session,
            spec.model_cls,
            actor_uuid=actor_uuid,
            new_attrs=new_attrs,
            parent_uuid=parent_uuid,
            parent_fk_column=spec.parent_fk_column,
            log_tx=log_tx,
        )

    if strategy == "session_cycle":
        if payload.get("estado") == "cerrado":
            return await session_cycle.close_login_with_log(
                session,
                login_uuid=payload["uuid"],
                actor_uuid=actor_uuid,
            )
        return await session_cycle.record_login(
            session,
            usuario_uuid=payload["uuid_usuario"],
            sucursal_uuid=payload["uuid_sucursal"],
            actor_uuid=actor_uuid,
            success=payload.get("estado") != "fallido",
            motivo=payload.get("motivo"),
        )

    raise ApplyRowError(f"{spec.name}: unknown or unset apply_strategy: {strategy!r}")


async def apply_row(
    session: AsyncSession,
    spec: SyncCatalogEntry,
    payload: dict[str, Any],
    *,
    actor_uuid: uuid_lib.UUID,
    log_tx: bool = True,
    branch_uuid: uuid_lib.UUID | None = None,
    parent_local: dict[str, Any] | None = None,
    open_version: dict[str, Any] | None = None,
    chain_head: bytes | None = None,
) -> ApplyResult:
    """Apply one row from a remote push (REQ-MOT-001..005, REQ-HOOK-003).

    Args:
        session: Active ``AsyncSession`` (caller commits).
        spec: The catalog entry describing this table's sync policy.
        payload: Business attributes for the row (see
            :func:`_dispatch_repo_call` for the per-strategy convention).
        actor_uuid: JWT subject (audit actor).
        log_tx: Forwarded to the ``repo/*`` helper.
        branch_uuid, parent_local, open_version, chain_head: Forwarded into
            :class:`HookContext` for the hooks that use them.

    Returns:
        :class:`ApplyResult` — ``APPLIED`` on success, ``RETRY`` with
        ``reason="parent_missing"`` when ``hook_validate_parent`` rejects a
        declared parent.
    """
    metrics: dict[str, bool] = {
        "hook_validate_parent": False,
        "hook_pre_insert": False,
        "hook_post_insert": False,
        "hook_chain_extend": False,
    }

    # 1. hook_validate_parent — only for specs with a declared dependency
    #    (REQ-HOOK-003 step 1, D18). Runs BEFORE any write is attempted.
    if spec.depends_on:
        hook = registry.resolve(spec.hook_validate_parent)
        ctx = HookContext(
            spec=spec,
            payload=payload,
            session=session,
            actor_uuid=actor_uuid,
            parent_local=parent_local,
            branch_uuid=branch_uuid,
        )
        result = await _invoke_hook(hook, ctx)
        metrics["hook_validate_parent"] = True
        if not result.parent_valid:
            return ApplyResult(
                status="RETRY",
                row_uuid=None,
                reason="parent_missing",
                metrics=metrics,
            )

    # 2. hook_pre_insert (if set on the spec) — identity reconciliation
    #    (D17) or payload adjustment (REQ-HOOK-003 step 2).
    if spec.hook_pre_insert is not None:
        ctx = HookContext(
            spec=spec,
            payload=payload,
            session=session,
            actor_uuid=actor_uuid,
            open_version=open_version,
            branch_uuid=branch_uuid,
        )
        result = await _invoke_hook(spec.hook_pre_insert, ctx)
        metrics["hook_pre_insert"] = True
        if result.payload_override is not None:
            payload = result.payload_override

    # 3. Repo call — dispatches per spec.apply_strategy (REQ-MOT-001..004).
    #    snapshot_columns (D20) travel inside `payload` verbatim; nothing
    #    above or below this line re-reads a live catalog to recompute them.
    new_row = await _dispatch_repo_call(
        session, spec, payload, actor_uuid=actor_uuid, log_tx=log_tx
    )
    # repo/* helpers deliberately do not flush/refresh (they stay composable
    # inside a larger caller-owned TX — see repo/versioned.py's docstring).
    # A flush (NOT a commit — the caller still owns the transaction) is
    # required here so `new_row.uuid` (server_default=gen_random_uuid()) is
    # actually populated before this function reads it and before any
    # downstream hook_post_insert/hook_chain_extend needs it.
    await session.flush()
    row_uuid = getattr(new_row, "uuid", None)

    # 4. hook_post_insert (if set) — telemetry (D10) + cascade_rows, applied
    #    through the motor (recursively) so cascades honor the same
    #    invariants as primary rows (REQ-HOOK-003 step 4, REQ-HOOK-005).
    if spec.hook_post_insert is not None:
        ctx = HookContext(
            spec=spec,
            payload=payload,
            session=session,
            actor_uuid=actor_uuid,
            branch_uuid=branch_uuid,
        )
        result = await _invoke_hook(spec.hook_post_insert, ctx)
        metrics["hook_post_insert"] = True
        for cascade_table, cascade_payload in result.cascade_rows:
            # Lazy import — avoids a module-load-time circular between
            # motor/apply_row.py and catalog/sync_catalog.py.
            from ..catalog.sync_catalog import SYNC_CATALOG_BY_NAME

            cascade_spec = SYNC_CATALOG_BY_NAME[cascade_table]
            await apply_row(
                session,
                cascade_spec,
                cascade_payload,
                actor_uuid=actor_uuid,
                log_tx=log_tx,
                branch_uuid=branch_uuid,
            )

    # 5. hook_chain_extend (if hash_chain=True and set) — extends the
    #    SHA-256 chain (REQ-MOT-004, REQ-HOOK-003 step 5).
    if spec.hash_chain and spec.hook_chain_extend is not None:
        ctx = HookContext(
            spec=spec,
            payload=payload,
            session=session,
            actor_uuid=actor_uuid,
            chain_head=chain_head,
            branch_uuid=branch_uuid,
        )
        await _invoke_hook(spec.hook_chain_extend, ctx)
        metrics["hook_chain_extend"] = True

    return ApplyResult(status="APPLIED", row_uuid=row_uuid, reason=None, metrics=metrics)


__all__ = ["ApplyRowError", "apply_row"]
