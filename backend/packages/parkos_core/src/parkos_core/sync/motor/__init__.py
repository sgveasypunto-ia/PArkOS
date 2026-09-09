"""sync/motor — the sync application engine (PR4+).

PR3 shipped only :mod:`motor.dependency_orderer` (D18, T-PR3-006) — the
in-batch topological ordering step. PR4 adds the ``apply_row`` dispatch +
hook lifecycle skeleton (``apply_result.py``, ``apply_row.py``) and the
``SyncMotor`` class itself (``sync_motor.py``). ``verify_chain`` (PR6),
``resolve_conflict`` (PR7), and ``dependency_buffer`` (PR8) land later.
"""
from __future__ import annotations

from .apply_result import ApplyResult, ApplyStatus
from .apply_row import ApplyRowError, apply_row
from .dependency_orderer import order_batch
from .sync_motor import BatchResult, SyncMotor

__all__ = [
    "ApplyResult",
    "ApplyRowError",
    "ApplyStatus",
    "BatchResult",
    "SyncMotor",
    "apply_row",
    "order_batch",
]
