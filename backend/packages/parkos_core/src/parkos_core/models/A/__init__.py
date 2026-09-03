"""[A] Append-only ORM models — hash chain + retention + REVOKE + triggers.

PR2 ships the full [A] infrastructure (8 ORM classes):

  - :class:`LogTransaccional` — audit log; SHA-256 chain carrier (REQ-16, REQ-X4)
  - :class:`SyncQueue`        — outbox carved-out from [A] inmutability (REQ-14)
  - :class:`SyncLog`          — sync-worker diagnostic log
  - :class:`SyncConflict`     — cloud/branch disagreement snapshot
  - :class:`Caja`             — cash-drawer snapshot
  - :class:`Arqueo`           — cash-count event
  - :class:`RevocacionFactura` — DIAN revocation; second hash-chain carrier
  - :class:`IdempotencyKeys`  — Idempotency-Key response cache (REQ-OP-04)
  - :class:`RevokedSyncJwts`  — JWT revocation registry (REQ-OP-04)

All classes descend from :class:`AppendOnlyBase`; the inmutability contract
(``REVOKE UPDATE, DELETE`` + ``BEFORE UPDATE OR DELETE`` trigger) is
enforced at the DB layer for every table here. ``SyncQueue`` is the
carve-out (design §12) — it keeps ``UPDATE`` / ``DELETE`` grants so the
sync workers can flip ``estado`` + ``intentos``, but the column whitelist
is enforced in :mod:`parkos_core.repo.sync_queue` (Python side).
"""
from __future__ import annotations

from .arqueo import Arqueo
from .caja import Caja
from .idempotency_keys import IdempotencyKeys
from .log_transaccional import LogTransaccional
from .revocacion_factura import RevocacionFactura
from .revoked_sync_jwts import RevokedSyncJwts
from .sync_conflict import SyncConflict
from .sync_log import SyncLog
from .sync_queue import SyncQueue

__all__ = [
    "Arqueo",
    "Caja",
    "IdempotencyKeys",
    "LogTransaccional",
    "RevocacionFactura",
    "RevokedSyncJwts",
    "SyncConflict",
    "SyncLog",
    "SyncQueue",
]