"""hooks/registry.py — factory by name -> callable (T-PR4-004).

REQ-HOOK-015 / REQ-OPS-009: every one of the 4 hook slots on a
``SyncCatalogEntry`` (``hook_pre_insert``, ``hook_post_insert``,
``hook_chain_extend``, ``hook_validate_parent``) defaults to the no-op
``lambda ctx: HookResult(proceed=True)`` when unset, so ``apply_row`` never
has to special-case "no hook configured" and a test that does not care about
hooks does not have to set them up.

PR4 ships the contract + the no-op default only. Concrete implementations
(``IdentityReconciler``, ``PlateChangeCascade``, ``SubscriptionLifecycle``,
``BiTemporalCompensation``, ``LogTransaccionalChain``,
``RevocacionFacturaChain``, ``ValidateParentChain``, ``AlertEmitter``) land
under ``hooks/impls/`` starting PR5/PR6 and self-register here via
:func:`register` at import time.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from .base import HookContext, HookResult

# Hooks may be plain sync callables (the REQ-HOOK-015 test-injection
# precedent: ``lambda ctx: HookResult(proceed=True)``) or ``async def``
# (every real PR5+ implementation, since they read the DB). ``apply_row``'s
# ``_invoke_hook`` awaits the result only if it is actually awaitable, so
# both shapes satisfy this one alias.
HookFn = Callable[[HookContext], HookResult | Awaitable[HookResult]]


def _default_hook(ctx: HookContext) -> HookResult:
    """The no-op default every unset hook slot resolves to (T-PR4-004)."""
    return HookResult(proceed=True)


# name -> hook implementation. Empty in PR4 — populated by PR5/PR6's
# ``hooks/impls/*`` modules via :func:`register`.
_REGISTRY: dict[str, HookFn] = {}


def register(name: str, hook: HookFn) -> None:
    """Register a named hook implementation (used by ``hooks/impls/*``, PR5+)."""
    _REGISTRY[name] = hook


def get_hook(name: str) -> HookFn:
    """Look up a registered hook implementation by name.

    Raises:
        KeyError: ``name`` is not registered. Callers that need a safe
            fallback should use :func:`resolve` instead.
    """
    return _REGISTRY[name]


def resolve(hook: HookFn | None) -> HookFn:
    """Return ``hook`` if set, else the no-op default (T-PR4-004)."""
    return hook if hook is not None else _default_hook


__all__ = ["HookFn", "get_hook", "register", "resolve"]
