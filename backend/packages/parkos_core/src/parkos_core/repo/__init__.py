"""parkos_core repository helpers — the SOLE writer layer for state changes.

Defense in depth (AGENTS.md §3, design §4):

  - API routers MUST NOT call ``session.add(...)`` or
    ``session.execute(...)`` for INSERT/UPDATE/DELETE on
    ``[V]/[L-E]/[L-W]/[L-S]/[A]`` tables.
  - All state changes go through helpers in this package.
  - AST tests in ``tests/static/`` reject violations.

Module map (PR2 adds the [A] infrastructure; previous PRs ship
auth-domain + pagination helpers):

  - :mod:`.versioned`       — close+insert for [V] tables (REQ-04, REQ-05)
  - :mod:`.session_cycle`   — login lifecycle ([L-S] skeleton in PR1b; full in PR7)
  - :mod:`.pagination`      — opaque cursor encode/decode (REQ-OP-01)
  - :mod:`.append_only`     — :func:`append_event` + :func:`compensate`
                              for [A] tables (REQ-10, REQ-15)
  - :mod:`.hash_chain`      — :func:`append` extends the SHA-256 chain on
                              ``log_transaccional`` + ``revocacion_factura``
                              (REQ-16, REQ-X4)
  - :mod:`.sync_queue`      — worker-side CRUD on the carved-out
                              ``sync_queue`` table (REQ-14, SC-13)
  - :mod:`.sync_outbox`     — no-op facade documenting that the DB
                              trigger ``prod.fn_enqueue_sync()`` owns
                              the canonical sync enqueue path (REQ-X6)

Subsequent PRs add ``event`` (PR5), ``workflow`` + ``factura_pagos``
(PR6), ``idempotency`` + full session_cycle (PR7).
"""
from __future__ import annotations

from .pagination import Cursor, InvalidCursorError, decode, encode

__all__ = ["Cursor", "InvalidCursorError", "decode", "encode"]