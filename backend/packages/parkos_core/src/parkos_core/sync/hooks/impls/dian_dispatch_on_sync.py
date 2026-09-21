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

import os
import uuid as uuid_lib
from pathlib import Path

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

    await dispatch_factura_electronica_with_backoff(
        ctx.session,
        uuid_factura_electronica=ctx.row_uuid,
        actor_uuid=ctx.actor_uuid,
        dian_provider_url=_DIAN_PROVIDER_URL,
        dian_token_path=_DIAN_TOKEN_PATH,
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

    await dispatch_revocacion_with_backoff(
        ctx.session,
        uuid_revocacion_factura=ctx.row_uuid,
        actor_uuid=ctx.actor_uuid,
        dian_provider_url=_DIAN_PROVIDER_URL,
        dian_token_path=_DIAN_TOKEN_PATH,
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

        await dispatch_factura_electronica_with_backoff(
            ctx.session,
            uuid_factura_electronica=uuid_factura_electronica,
            actor_uuid=ctx.actor_uuid,
            dian_provider_url=_DIAN_PROVIDER_URL,
            dian_token_path=_DIAN_TOKEN_PATH,
        )
    elif uuid_revocacion_factura is not None:
        from ....dian.cloud.dispatcher import dispatch_revocacion_with_backoff

        await dispatch_revocacion_with_backoff(
            ctx.session,
            uuid_revocacion_factura=uuid_revocacion_factura,
            actor_uuid=ctx.actor_uuid,
            dian_provider_url=_DIAN_PROVIDER_URL,
            dian_token_path=_DIAN_TOKEN_PATH,
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
    "dian_factura_electronica_dispatch_hook",
    "dian_revocacion_factura_dispatch_hook",
    "envio_dian_resume_hook",
]