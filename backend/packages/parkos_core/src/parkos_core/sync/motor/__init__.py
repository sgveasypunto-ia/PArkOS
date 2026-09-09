"""sync/motor — the sync application engine (PR4+).

PR3 ships only :mod:`motor.dependency_orderer` (D18, T-PR3-006) — the
in-batch topological ordering step. ``SyncMotor``, ``apply_row``,
``verify_chain``, ``resolve_conflict`` and the rest of
design.md §3's Module Structure land starting PR4; this package exists now
so ``dependency_orderer.py`` has a stable import path ahead of them.
"""
from __future__ import annotations

from .dependency_orderer import order_batch

__all__ = ["order_batch"]
