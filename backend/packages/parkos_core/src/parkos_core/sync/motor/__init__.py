"""sync/motor — the sync application engine (PR4+).

PR3 shipped only :mod:`motor.dependency_orderer` (D18, T-PR3-006) — the
in-batch topological ordering step. PR4 adds the ``apply_row`` dispatch +
hook lifecycle skeleton (``apply_result.py``, ``apply_row.py``) and the
``SyncMotor`` class itself (``sync_motor.py``). PR6 adds the hash chain
walker (``verify_chain.py``). PR7 adds the seq-lookup dispatcher
(``read_local_seq.py``, D4) and ``resolve_conflict`` (per-audit-class
conflict policy). ``dependency_buffer`` (PR8) lands later.
"""
from __future__ import annotations

from .apply_result import ApplyResult, ApplyStatus
from .apply_row import ApplyRowError, apply_row
from .dependency_orderer import order_batch
from .read_local_seq import DEFAULT_CACHE_TTL_SECONDS, ReadLocalSeq, ReadLocalSeqError
from .resolve_conflict import ConflictResolution, ConflictStatus, resolve_conflict
from .sync_motor import BatchResult, SyncMotor
from .verify_chain import ChainAnomaly, verify_chain, verify_chain_for_spec

__all__ = [
    "DEFAULT_CACHE_TTL_SECONDS",
    "ApplyResult",
    "ApplyRowError",
    "ApplyStatus",
    "BatchResult",
    "ChainAnomaly",
    "ConflictResolution",
    "ConflictStatus",
    "ReadLocalSeq",
    "ReadLocalSeqError",
    "SyncMotor",
    "apply_row",
    "order_batch",
    "resolve_conflict",
    "verify_chain",
    "verify_chain_for_spec",
]
