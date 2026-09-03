"""[A] Append-only ORM models — hash chain + retention + REVOKE + triggers.

PR1b ships ``log_transaccional`` (the only [A] table that must exist for
``repo/versioned.close_and_insert`` to write its log row in the same TX).
PR2 ships the rest of the [A] infrastructure (``sync_queue``, ``sync_log``,
``sync_conflict``, ``caja``, ``arqueo``, ``revocacion_factura``). PR7 ships
``idempotency_keys``.
"""
from __future__ import annotations

from .log_transaccional import LogTransaccional

__all__ = ["LogTransaccional"]