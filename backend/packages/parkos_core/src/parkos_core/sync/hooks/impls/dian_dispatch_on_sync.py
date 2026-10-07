"""hooks/impls/dian_dispatch_on_sync.py — wire the DIAN dispatcher to the
cloud-side catalog-driven sync apply path (CU-05 critical fix #2).

The cloud-side catalog-driven apply loop
(``jobs/sync_cloud.py::_apply_pending_batch_once``, T-PR11-001) drains
``prod.sync_queue`` and applies every row through
:meth:`motor.apply_row.apply_row`. For three DIAN-bound catalog entries
(``factura_electronica``, ``revocacion_factura``, and
``envio_dian(estado='pendiente')``) a successful apply was leaving the
row in the cloud DB forever without ever being forwarded to the DIAN
provider — ``dian/cloud_router.py`` calls
:func:`dian.cloud.dispatcher.dispatch_factura_electronica_with_backoff`
on its direct admin POST endpoint, but the same call site was MISSING
on the sync apply path (the catalog entries declared
``apply_strategy="record_event"`` /
``apply_strategy="append_transition"`` /
``apply_strategy="append_event"`` with no ``hook_post_insert``).

This module closes that gap by binding one ``hook_post_insert`` callable
per affected catalog entry. Each hook delegates to the EXACT SAME
``dian.cloud.dispatcher.dispatch_*_with_backoff`` API the cloud-router
already calls (REQ-34, REQ-35, REQ-X3), reusing the same
``dian/backoff.py::DIAN_BACKOFF_SCHEDULE`` retry budget — no new curve,
no fork. The hooks are catalog-imported (not just registered) so the
catalog entry's dataclass field binds the actual callable at construction
time (``registry`` is the discovery surface; the direct import is what
``apply_row``'s step-4 ``spec.hook_post_insert`` actually invokes).

**Cloud-only.** Lazy-imports ``dian.cloud.dispatcher`` from inside each
hook so the import-time ``PARKOS_DEPLOY=branch`` guard
(``dian/cloud/dispatcher.py`` lines 80-84, REQ-X3, design §10 Layer 2)
never fires when the shared catalog module loads on a branch image. The
DIAN-PROVIDER-URL / DIAN-PROVIDER-TOKEN env reads also happen at HOOK
CALL time (not module load), so a test that monkeypatches those env
vars sees the patched values without having to reload this module.

**Known duplication hazard (out of scope for this PR).** The branch
typically creates both a ``factura_electronica`` and its initial
``envio_dian(pendiente)`` and replicates both via sync — both hooks
fire on apply, each kicking off its OWN ``dispatch_*_with_backoff``
chain. This produces two parallel envio_dian chains (the FE hook's
chain + the envio_dian(pendiente) hook's chain) instead of one chain
extending the branch's pendiente envio_dian via ``uuid_envio_padre``.
Closing that requires either deduplication on the cloud (a lookup
before dispatch) or chaining ``dispatch_*`` (single-attempt, with
``parent_envio_uuid``) instead of ``dispatch_*_with_backoff`` — both
are documented, explicitly out-of-scope follow-ups for whichever PR
next touches the FE/dispatcher wire-up.
"""
from __future__ import annotations

import asyncio
import os
import uuid as uuid_lib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import event

from parkos_core.runtime.log_safe import sanitize_error

from .. import registry
from ..base import HookContext, HookResult

# DIAN provider connection — module-level env reads (matches
# ``dian/cloud_router.py``'s own module-load reads). Read at IMPORT time
# so a test can ``monkeypatch.setenv`` and reimport the module if it
# needs to drive a different provider URL.
_DIAN_PROVIDER_URL: str = os.environ.get(
    "PARKOS_DIAN_PROVIDER_URL", "http://localhost:8080"
)
_DIAN_TOKEN_PATH: Path = Path(
    os.environ.get("PARKOS_DIAN_PROVIDER_TOKEN_PATH", "/dev/null")
)

_log = structlog.get_logger(__name__)

#: ``Session.info`` key holding the dispatches queued by the current
#: transaction (defect D5: they used to run INLINE inside the sync apply
#: transaction; a slow/unreachable provider left it ``idle in transaction``
#: holding locks and blocked ``/sync/push`` for every other branch).
_PENDING_KEY = "parkos_dian_deferred_dispatches"

DeferredDispatch = Callable[[Any], Awaitable[Any]]
#: ``("fe" | "rev", document uuid)`` - identity of the document a dispatch is for.
DispatchKey = tuple[str, uuid_lib.UUID]

#: Safety net only (the ordering is the real fix, see ``_on_after_commit``):
#: pause before re-trying a dispatch whose source row was not visible yet.
_NOT_VISIBLE_RETRY_DELAYS_S: tuple[float, ...] = (0.5, 2.0, 5.0)

# Strong refs: the loop only keeps weak refs to tasks.
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
#: Documents with a dispatch task alive in THIS process (same-process dedupe;
#: cross-process dedupe is the advisory lock + chain check in the dispatcher).
_INFLIGHT: set[DispatchKey] = set()


@dataclass(eq=False)
class _Queued:
    make: DeferredDispatch
    key: DispatchKey | None
    #: Innermost SessionTransaction (SAVEPOINT or root) the hook ran in.
    txn: Any


def _inside(txn: Any, ancestor: Any) -> bool:
    while txn is not None:
        if txn is ancestor:
            return True
        txn = txn.parent
    return False


async def _alert_failure(key: DispatchKey) -> None:
    """Best effort: a failed dispatch must be visible, never silent."""
    try:
        from ....db.engine import SessionLocal
        from ....dian.cloud.dispatcher import record_dispatch_failure

        async with SessionLocal() as session:
            await record_dispatch_failure(session, uuid_documento=key[1], kind=key[0])
    except Exception as exc:  # noqa: BLE001 - the alert must never mask the original failure
        _log.warning(
            "dian_dispatch.failure_alert_failed",
            error_class=type(exc).__name__,
            error=sanitize_error(exc),
        )


async def _run_deferred(make: DeferredDispatch, key: DispatchKey | None = None) -> None:
    """Run one queued dispatch in its OWN session, after the apply committed."""
    try:
        from ....db.engine import SessionLocal

        attempt = 0
        while True:
            try:
                async with SessionLocal() as session:
                    await make(session)
                return
            except Exception as exc:  # noqa: BLE001
                if getattr(exc, "not_visible", False) and attempt < len(
                    _NOT_VISIBLE_RETRY_DELAYS_S
                ):
                    await asyncio.sleep(_NOT_VISIBLE_RETRY_DELAYS_S[attempt])
                    attempt += 1
                    continue
                raise
    except Exception as exc:  # noqa: BLE001 - background; the envio_dian chain keeps the state
        if type(exc).__name__ == "DispatchAlreadyHandledError":
            _log.info("dian_dispatch.already_handled", documento=str(key[1]) if key else None)
            return
        # structlog is not configured to render ``exc_info`` here, so the
        # warning used to carry no cause. Class + sanitized message (URL
        # credentials masked, truncated) make it diagnosable; never the token.
        _log.warning(
            "dian_dispatch.deferred_failed",
            error_class=type(exc).__name__,
            error=sanitize_error(exc),
            exc_info=True,
        )
        if key is not None:
            await _alert_failure(key)


async def _run_and_release(make: DeferredDispatch, key: DispatchKey | None) -> None:
    try:
        await _run_deferred(make, key)
    finally:
        if key is not None:
            _INFLIGHT.discard(key)


def _spawn(queued: list[_Queued]) -> None:
    """Start one detached task per distinct document (needs a running loop)."""
    loop = asyncio.get_running_loop()
    for item in queued:
        if item.key is not None:
            if item.key in _INFLIGHT:
                continue  # FE hook + envio_dian hook for the same document
            _INFLIGHT.add(item.key)
        task = loop.create_task(_run_and_release(item.make, item.key), name="dian_dispatch")
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)


def _on_after_commit(sync_session: Any) -> None:
    # SQLAlchemy fires ``after_commit`` for the release of a SAVEPOINT as
    # well, and the sync push applies EVERY row inside ``begin_nested()``.
    # Spawning there started the dispatch before the request-level commit,
    # so its own session could not see the just-inserted
    # ``factura_electronica`` ("not found") and every envio_dian stayed
    # 'pendiente' (defect DD1). Only the outermost commit makes the rows
    # visible to other sessions.
    if sync_session.in_nested_transaction():
        return
    pending: list[_Queued] = sync_session.info.get(_PENDING_KEY) or []
    if not pending:
        return
    queued = list(pending)
    pending.clear()
    _spawn(queued)


def _on_after_soft_rollback(sync_session: Any, previous_transaction: Any) -> None:
    """Drop only the dispatches queued inside the transaction that rolled back.

    A SAVEPOINT rollback (one poison row) must not erase the dispatches of the
    rows that already succeeded in the same batch, and the rolled-back row's
    own document never existed. A root rollback drops everything.
    """
    pending = sync_session.info.get(_PENDING_KEY)
    if pending:
        pending[:] = [q for q in pending if not _inside(q.txn, previous_transaction)]


def defer_dispatch(
    session: Any, make: DeferredDispatch, *, key: DispatchKey | None = None
) -> None:
    """Queue ``make(fresh_session)`` to run AFTER the OUTERMOST commit.

    Never runs the provider call inside the caller's transaction. A rollback
    drops what was queued inside the rolled-back (sub)transaction.
    """
    sync_session = session.sync_session
    pending = sync_session.info.get(_PENDING_KEY)
    if pending is None:
        sync_session.info[_PENDING_KEY] = pending = []
        event.listen(sync_session, "after_commit", _on_after_commit)
        event.listen(sync_session, "after_soft_rollback", _on_after_soft_rollback)
    pending.append(
        _Queued(
            make=make,
            key=key,
            txn=sync_session.get_nested_transaction() or sync_session.get_transaction(),
        )
    )


def resume_factura_dispatch(
    uuid_factura_electronica: uuid_lib.UUID, actor_uuid: uuid_lib.UUID | None = None
) -> bool:
    """Start the deferred dispatch of an already-committed FE (periodic sweep).

    Same detached task, same advisory-lock/chain guard as the post-commit hook,
    so a document is never sent twice. Returns False when this process already
    has a dispatch alive for the document.
    """
    from ....dian.cloud.dispatcher import dispatch_factura_electronica_with_backoff

    key: DispatchKey = ("fe", uuid_factura_electronica)
    if key in _INFLIGHT:
        return False
    actor = actor_uuid or uuid_lib.uuid4()
    _spawn(
        [
            _Queued(
                make=lambda session: dispatch_factura_electronica_with_backoff(
                    session,
                    uuid_factura_electronica=uuid_factura_electronica,
                    actor_uuid=actor,
                    dian_provider_url=_DIAN_PROVIDER_URL,
                    dian_token_path=_DIAN_TOKEN_PATH,
                    skip_if_dispatched=True,
                ),
                key=key,
                txn=None,
            )
        ]
    )
    return True


# ``envio_dian`` workflow state-machine initial state (D1-rev: branch is
# the author of the envio_dian chain, initial transition is ``pendiente``).
_ESTADO_PENDIENTE = "pendiente"


async def dian_factura_electronica_dispatch_hook(ctx: HookContext) -> HookResult:
    """``hook_post_insert`` for ``factura_electronica`` (CU-05 fix #2 leg 1).

    Fires AFTER the repo's ``record_event`` write commits the new
    ``prod.factura_electronica`` row (apply_row step 3 flushes before
    step 4) — ``ctx.row_uuid`` is the just-written row's uuid.
    Delegates straight to
    :func:`dian.cloud.dispatcher.dispatch_factura_electronica_with_backoff`
    with the DIAN retry budget the dispatcher already owns (no new
    backoff curve, no fork).

    Returns ``HookResult(proceed=True)`` — the motor's step-5
    ``hook_chain_extend`` runs after this for any entry that also
    declares one, but no FE entry declares a ``hook_chain_extend`` so
    nothing more fires in this leg.
    """
    if ctx.row_uuid is None:
        # Defensive — apply_row always populates row_uuid for
        # hook_post_insert when the repo call returns a row with a uuid
        # column, but a regression there should not crash the worker
        # loop; an ApplyResult without dispatch is still a valid apply.
        return HookResult(proceed=True)

    # Lazy import — see module docstring's "Cloud-only" note.
    from ....dian.cloud.dispatcher import (
        dispatch_factura_electronica_with_backoff,
    )

    row_uuid = ctx.row_uuid
    actor_uuid = ctx.actor_uuid

    defer_dispatch(
        ctx.session,
        lambda session: dispatch_factura_electronica_with_backoff(
            session,
            uuid_factura_electronica=row_uuid,
            actor_uuid=actor_uuid,
            dian_provider_url=_DIAN_PROVIDER_URL,
            dian_token_path=_DIAN_TOKEN_PATH,
            skip_if_dispatched=True,
        ),
        key=("fe", row_uuid),
    )
    return HookResult(proceed=True)


async def dian_revocacion_factura_dispatch_hook(ctx: HookContext) -> HookResult:
    """``hook_post_insert`` for ``revocacion_factura`` (CU-05 fix #2 leg 2).

    Mirrors :func:`dian_factura_electronica_dispatch_hook` for the
    revocation half of the DIAN pipeline — calls
    :func:`dian.cloud.dispatcher.dispatch_revocacion_with_backoff`
    (T-PR11-02, design §21.11 step 2), which on ``aceptado`` extends
    the ``prod.revocacion_factura`` SHA-256 chain with motivo=
    ``'dian_confirmada'`` (REQ-16, REQ-X4) via the existing
    ``hook_chain_extend`` slot already bound on this entry.
    """
    if ctx.row_uuid is None:
        return HookResult(proceed=True)

    from ....dian.cloud.dispatcher import dispatch_revocacion_with_backoff

    row_uuid = ctx.row_uuid
    actor_uuid = ctx.actor_uuid

    defer_dispatch(
        ctx.session,
        lambda session: dispatch_revocacion_with_backoff(
            session,
            uuid_revocacion_factura=row_uuid,
            actor_uuid=actor_uuid,
            dian_provider_url=_DIAN_PROVIDER_URL,
            dian_token_path=_DIAN_TOKEN_PATH,
            skip_if_dispatched=True,
        ),
        key=("rev", row_uuid),
    )
    return HookResult(proceed=True)


async def envio_dian_resume_hook(ctx: HookContext) -> HookResult:
    """``hook_post_insert`` for ``envio_dian(estado='pendiente')`` (CU-05 fix #2 leg 3).

    Branch-originated envio_dian rows in the ``pendiente`` state arrive
    at the cloud via sync — without this hook every pendiente envio_dian
    sits in the cloud DB forever without ever being forwarded to Factus.
    Inspects ``ctx.payload`` to decide which underlying row drives the
    dispatch:

      - ``payload["uuid_factura_electronica"]`` set
        -> dispatch via
        :func:`dian.cloud.dispatcher.dispatch_factura_electronica_with_backoff`.
      - ``payload["payload"]["uuid_revocacion_factura"]`` set (the JSONB
        nested case — the dispatcher's own serialize writes it inside
        ``payload`` for revocation-linked envios, not as a top-level
        column)
        -> dispatch via
        :func:`dian.cloud.dispatcher.dispatch_revocacion_with_backoff`.

    Rows in any non-``pendiente`` state (``enviado``, ``aceptado``,
    ``rechazado``) are skipped — they're cloud-side transitions on the
    envio_dian chain (see ``dian/cloud_router.py`` +
    ``dispatcher._finalize_revocacion``'s chain-extension write) and
    re-dispatching them would create duplicate Factus submissions.
    """
    payload = ctx.payload if isinstance(ctx.payload, dict) else {}
    estado = payload.get("estado")
    if estado != _ESTADO_PENDIENTE:
        return HookResult(proceed=True)

    uuid_factura_electronica = payload.get("uuid_factura_electronica")
    nested_raw = payload.get("payload")
    nested_payload = nested_raw if isinstance(nested_raw, dict) else {}
    uuid_revocacion_factura = nested_payload.get("uuid_revocacion_factura")

    if uuid_factura_electronica is not None:
        from ....dian.cloud.dispatcher import (
            dispatch_factura_electronica_with_backoff,
        )

        defer_dispatch(
            ctx.session,
            lambda session: dispatch_factura_electronica_with_backoff(
                session,
                uuid_factura_electronica=uuid_factura_electronica,
                actor_uuid=ctx.actor_uuid,
                dian_provider_url=_DIAN_PROVIDER_URL,
                dian_token_path=_DIAN_TOKEN_PATH,
                skip_if_dispatched=True,
            ),
            key=("fe", uuid_lib.UUID(str(uuid_factura_electronica))),
        )
    elif uuid_revocacion_factura is not None:
        from ....dian.cloud.dispatcher import dispatch_revocacion_with_backoff

        defer_dispatch(
            ctx.session,
            lambda session: dispatch_revocacion_with_backoff(
                session,
                uuid_revocacion_factura=uuid_revocacion_factura,
                actor_uuid=ctx.actor_uuid,
                dian_provider_url=_DIAN_PROVIDER_URL,
                dian_token_path=_DIAN_TOKEN_PATH,
                skip_if_dispatched=True,
            ),
            key=("rev", uuid_lib.UUID(str(uuid_revocacion_factura))),
        )

    return HookResult(proceed=True)


registry.register(
    "dian_factura_electronica_dispatch",
    dian_factura_electronica_dispatch_hook,
)
registry.register(
    "dian_revocacion_factura_dispatch",
    dian_revocacion_factura_dispatch_hook,
)
registry.register(
    "envio_dian_resume",
    envio_dian_resume_hook,
)


__all__ = [
    "defer_dispatch",
    "dian_factura_electronica_dispatch_hook",
    "dian_revocacion_factura_dispatch_hook",
    "envio_dian_resume_hook",
    "resume_factura_dispatch",
]