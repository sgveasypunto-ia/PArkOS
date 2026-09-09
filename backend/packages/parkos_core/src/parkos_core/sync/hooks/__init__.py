"""sync/hooks — the per-table hook contract (PR4+).

Re-exports the hook data contracts (:class:`HookContext`, :class:`HookResult`,
design.md §6 / specs/hooks.md REQ-HOOK-001/002) and the name->callable
:mod:`registry`. Concrete hook implementations (``IdentityReconciler``,
``PlateChangeCascade``, ``SubscriptionLifecycle``, ``BiTemporalCompensation``,
``LogTransaccionalChain``, ``RevocacionFacturaChain``, ``ValidateParentChain``,
``AlertEmitter``) land under ``hooks/impls/`` starting PR5/PR6; PR4 only ships
the contract + the no-op default every unset hook slot resolves to.
"""
from __future__ import annotations

from .base import HookContext, HookResult
from .registry import get_hook, register, resolve

__all__ = ["HookContext", "HookResult", "get_hook", "register", "resolve"]
