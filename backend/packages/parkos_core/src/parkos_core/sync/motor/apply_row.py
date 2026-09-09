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

**PR5 additions (T-PR5-005, T-PR5-010, D17, REQ-HOOK-006):**
``hook_pre_insert`` can now short-circuit ``apply_row`` in two additional
ways, both evaluated strictly BEFORE the repo call (same "prevent, don't
observe" posture as ``hook_validate_parent``):

  - ``HookResult(proceed=False, ...)`` -> ``ApplyResult(status=CONFLICT,
    reason="illegal_state_transition")`` — ``SubscriptionLifecycle``
    rejecting an illegal ``subscripcion_vehiculos`` transition or a
    vehicle-capacity overrun (REQ-HOOK-006). The hook itself writes the
    informational ``sync_conflict`` row before returning.
  - ``HookResult(reconciliation="noop", ...)`` -> ``ApplyResult(
    status=APPLIED, row_uuid=<open_version's uuid>)`` without ever calling
    the repo — ``IdentityReconciler`` detecting the arriving row is
    business-identical to the currently-open version (D17, REQ-HOOK-010).
    This is what prevents version-chain inflation on re-delivery.
"""
from __future__ import annotations

import datetime as dt_lib
import inspect
import uuid as uuid_lib
from typing import Any

from sqlalchemy import Date, DateTime
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from ...repo import append_only, event, session_cycle, versioned, workflow
from ..catalog.schema import SyncCatalogEntry
from ..hooks import registry
from ..hooks.base import HookContext, HookResult
from .apply_result import ApplyResult


class ApplyRowError(Exception):
    """Raised for a catalog entry with an unknown/unset ``apply_strategy``."""


def _coerce_wire_payload(model_cls: type, payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce JSON-wire string values back to the native types asyncpg
    requires for binding (found wiring the post-PR14 full-catalog-sync
    closing exercise's real ``POST /sync/events`` round trip — every prior
    test either stubbed ``SyncMotor`` or built its payload dict in-process,
    never crossing an actual JSON boundary).

    ``prod.sync_queue.datos`` is JSONB (populated by ``to_jsonb(NEW)`` in
    the DB trigger) and the ``/sync/events`` wire contract is a plain JSON
    body (``_CatalogPushEvent.payload: dict[str, Any]``, ``sync_router.py``)
    — a ``Date``/``DateTime`` column therefore arrives here as an ISO-8601
    string, not a ``datetime.date``/``datetime.datetime`` instance.
    asyncpg's binary protocol requires the real instance for a
    DATE/TIMESTAMP bind parameter and raises
    ``asyncpg.exceptions.DataError`` on a bare string — unlike a UUID
    column, which Postgres accepts via the ``::uuid`` text cast SQLAlchemy
    already emits, so no equivalent failure ever surfaced for those columns.

    Only touches keys that are real mapped columns on ``model_cls``; every
    other key (the reserved dispatch keys ``current_uuid``/``parent_uuid``,
    or any genuinely unrecognized key) passes through UNCHANGED — this
    function coerces types, it never drops or filters keys. An earlier
    version of this fix also silently dropped any key absent from
    ``model_cls``'s mapped columns, reasoning it defended against ORM/DB
    mapping drift (``models/L_E/factura_electronica.py`` was really
    missing a ``fecha_retencion_hasta`` mapped attribute the DB's own
    ``0001_initial_schema.py::_retention_column()`` call already creates
    physically — see that model's own docstring for the real fix, now
    applied there instead). That drop-anything-unmapped behavior was too
    broad: it also silently defeated
    ``tests/integration/test_sync_cloud_catalog_driven.py::
    test_apply_loop_isolates_one_poisoned_row_via_per_row_fallback``'s
    entire purpose (an intentionally-invalid extra payload key MUST still
    raise, proving the per-row fallback isolates a genuinely poisoned row
    from its batch siblings). Fixing the ONE real drift at its actual
    source (the ORM model) instead of papering over ALL possible drift
    generically here is the correct scope for this function.
    """
    mapper = sa_inspect(model_cls)
    mapped_columns = {column.name: column for column in mapper.columns}
    coerced: dict[str, Any] = {}
    for key, value in payload.items():
        column = mapped_columns.get(key)
        if column is not None and isinstance(value, str):
            # DateTime must be checked before Date — DateTime does not
            # subclass Date in SQLAlchemy; the two branches are independent.
            col_type = column.type
            if isinstance(col_type, DateTime):
                value = dt_lib.datetime.fromisoformat(value)
            elif isinstance(col_type, Date):
                value = dt_lib.date.fromisoformat(value)
        coerced[key] = value
    return coerced


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
      - ``session_cycle``: dispatches on ``spec.name`` — ``login`` uses
        ``record_login``/``close_login_with_log`` (``payload["estado"] ==
        "cerrado"`` selects the close path, ``payload["uuid"]`` names the
        login row); ``sesion`` uses ``open_session``/``close_session_with_log``
        (``payload["timestamp_cierre"]`` set selects the close path,
        ``payload["uuid"]`` names the sesion row). Both ``[L-S]`` catalog
        entries (``entries/sync_entries_ls.py``) declare
        ``apply_strategy="session_cycle"`` — dispatching on ``spec.name`` is
        REQUIRED here, otherwise a ``sesion`` row is misrouted into
        ``session_cycle.record_login`` and silently inserted into
        ``prod.login`` instead of ``prod.sesion`` (found wiring the
        post-PR14 full-catalog-sync closing exercise: ``payload["uuid_usuario"]``/
        ``payload["uuid_sucursal"]`` happen to exist on BOTH tables, so the
        misrouted call never raised — it just landed the wrong row).
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
        if spec.name == "sesion":
            if payload.get("timestamp_cierre") is not None:
                return await session_cycle.close_session_with_log(
                    session,
                    actor_uuid=actor_uuid,
                    sesion_uuid=payload["uuid"],
                    valor_final_efectivo=payload.get("valor_final_efectivo"),
                    valor_final_datafono=payload.get("valor_final_datafono"),
                )
            return await session_cycle.open_session(
                session,
                actor_uuid=actor_uuid,
                uuid_sucursal=payload["uuid_sucursal"],
                valor_inicial_efectivo=payload["valor_inicial_efectivo"],
                valor_inicial_datafono=payload["valor_inicial_datafono"],
                uuid_usuario=payload["uuid_usuario"],
                # Preserve the origin's identity — see open_session's own
                # docstring ("uuid" arg) for why this is required, not
                # optional, once any FK-carrying child (arqueo,
                # factura_pagos) syncs alongside its sesion parent.
                uuid=payload.get("uuid"),
            )
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
            # Preserve the origin's identity — see record_login's own
            # docstring ("uuid" arg) / open_session's fuller explanation.
            uuid=payload.get("uuid"),
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
    # Coerce JSON-wire string values ONCE, here, before ANY hook or the repo
    # dispatch sees ``payload`` — found wiring the post-PR14 full-catalog-
    # sync closing exercise's real POST /sync/events round trip. Coercing
    # only inside ``_dispatch_repo_call`` (an earlier version of this fix)
    # left every hook (``hook_validate_parent``, ``hook_pre_insert``,
    # ``hook_post_insert``, ``hook_chain_extend``) reading the ORIGINAL,
    # uncoerced ``payload`` parameter — Python rebinds a reassigned
    # parameter only inside the callee's own local scope, so
    # ``_dispatch_repo_call``'s ``payload = _coerce_wire_payload(...)``
    # never affected this function's own ``payload`` variable. See
    # ``_coerce_wire_payload``'s own docstring for the full "why" (ISO
    # string dates/datetimes from JSONB/JSON crossing the wire; asyncpg
    # requires the real instance for a DATE/TIMESTAMP bind).
    payload = _coerce_wire_payload(spec.model_cls, payload)

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

        # T-PR5-010 (REQ-HOOK-006): a pre_insert hook rejecting the row
        # (illegal lifecycle transition, capacity exceeded, ...) aborts
        # BEFORE the repo call — same "never observe, always prevent"
        # posture as hook_validate_parent's parent_missing short-circuit
        # above. The hook itself is responsible for writing the
        # informational ``sync_conflict`` row (it has ``ctx.session``);
        # this module only maps the rejection to the ApplyResult contract.
        if not result.proceed:
            return ApplyResult(
                status="CONFLICT",
                row_uuid=None,
                reason="illegal_state_transition",
                metrics=metrics,
            )

        # T-PR5-005 (REQ-HOOK-010, D17): IdentityReconciler's "noop" case —
        # the arriving row is business-identical to the currently-open
        # version. The repo call MUST NOT run (this is what prevents
        # version-chain inflation on every re-delivery of the same fact),
        # but the outcome is still APPLIED, not a rejection.
        if result.reconciliation == "noop":
            noop_uuid = open_version.get("uuid") if open_version else None
            return ApplyResult(
                status="APPLIED",
                row_uuid=noop_uuid,
                reason=None,
                metrics=metrics,
            )

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
            open_version=open_version,
            row_uuid=row_uuid,
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
    #
    #    Skipped when ``strategy == "append_event"`` — that branch of step
    #    3 above ALREADY passes ``chain_hash=spec.hash_chain`` into
    #    ``repo.append_only.append_event``, which (when ``chain_hash=True``)
    #    delegates the ENTIRE insert to ``repo.hash_chain.append`` itself —
    #    the row is already chain-extended and already persisted by the
    #    time step 5 would run. Both catalog entries this applies to today
    #    (``log_transaccional``, ``revocacion_factura`` — REQ-CAT-009's
    #    "only two ``hash_chain=True`` entries in the whole catalog", both
    #    ``apply_strategy="append_event"``) also declare a
    #    ``hook_chain_extend`` (``log_transaccional_chain`` /
    #    ``revocacion_factura_chain``) for the DIAN-provider-dispatcher call
    #    site (``dian/cloud/dispatcher.py``), which calls that hook
    #    DIRECTLY, outside ``apply_row`` — not for this path. Without this
    #    guard, EVERY catalog-driven sync of either table inserted the row
    #    TWICE per incoming event (found wiring the post-PR14 full-catalog-
    #    sync closing exercise's real ``revocacion_factura`` push: the
    #    second, redundant ``hash_chain.append`` call also crashed outright,
    #    since it read ``ctx.payload`` — the pre-coercion copy, see this
    #    function's own payload-coercion comment above — but the duplicate
    #    INSERT itself is the real defect, independent of that crash).
    if (
        spec.hash_chain
        and spec.hook_chain_extend is not None
        and spec.apply_strategy != "append_event"
    ):
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
