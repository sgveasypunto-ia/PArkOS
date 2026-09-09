"""[A] Append-only ORM models — hash chain + retention + REVOKE + triggers.

PR2 ships the base [A] infrastructure; PR6 adds the [L-W] workflows;
PR8a adds:

  - :class:`PairingToken`    — admin-issued short-lived (24h) pairing
    tokens (REQ-OP-04, design §21.3)
  - :class:`RevokedSyncJwt`  — JWT revocation registry, normalized to
    ``jwt_kid`` + ``jwt_uuid`` with bi-temporal UK (PR8a replaces the
    PR2-shipped ``RevokedSyncJwts`` whose columns did not match the
    revocation-by-kid+jti pattern)

  Other [A] tables living here:

  - :class:`LogTransaccional` — audit log; SHA-256 chain carrier (REQ-16, REQ-X4)
  - :class:`SyncQueue`        — outbox carved-out from [A] inmutability (REQ-14)
  - :class:`SyncLog`          — sync-worker diagnostic log
  - :class:`SyncConflict`     — cloud/branch disagreement snapshot
  - :class:`Caja`             — cash-drawer snapshot
  - :class:`Arqueo`           — cash-count event
  - :class:`RevocacionFactura` — DIAN revocation; second hash-chain carrier
  - :class:`IdempotencyKeys`  — Idempotency-Key response cache (REQ-OP-04)

PR8 adds:

  - :class:`SyncQueueLwBuffer` — dependency buffer (design §2 Issue #2/#8);
    keyed on ``(tabla_padre, uuid_padre)``, drained by
    :mod:`parkos_core.sync.motor.dependency_buffer`
  - :class:`AlertTypes`        — deploy-seeded ``tipo_alerta`` registry
    (design §2 Issue #6); the ONE exception here — it descends directly
    from :class:`Base`, not :class:`AppendOnlyBase`, since its PK is the
    business key ``tipo_alerta``, not a ``uuid`` (see its own docstring)

Every OTHER class descends from :class:`AppendOnlyBase`; the inmutability
contract (``REVOKE UPDATE, DELETE`` + ``BEFORE UPDATE OR DELETE`` trigger) is
enforced at the DB layer for every table here. ``SyncQueue`` is the
carve-out (design §12) — it keeps ``UPDATE`` / ``DELETE`` grants so the
sync workers can flip ``estado`` + ``intentos``, but the column whitelist
is enforced in :mod:`parkos_core.repo.sync_queue` (Python side).
"""
from __future__ import annotations

from .alert_types import AlertTypes
from .arqueo import Arqueo
from .caja import Caja
from .idempotency_keys import IdempotencyKeys
from .log_transaccional import LogTransaccional
from .pairing_tokens import PairingToken
from .revocacion_factura import RevocacionFactura
from .revoked_sync_jwts import RevokedSyncJwt
from .sync_conflict import SyncConflict
from .sync_log import SyncLog
from .sync_queue import SyncQueue
from .sync_queue_lw_buffer import SyncQueueLwBuffer

__all__ = [
    "AlertTypes",
    "Arqueo",
    "Caja",
    "IdempotencyKeys",
    "LogTransaccional",
    "PairingToken",
    "RevocacionFactura",
    "RevokedSyncJwt",
    "SyncConflict",
    "SyncLog",
    "SyncQueue",
    "SyncQueueLwBuffer",
]