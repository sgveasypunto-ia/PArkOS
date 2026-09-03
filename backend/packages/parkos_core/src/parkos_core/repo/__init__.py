"""parkos_core repository helpers — the SOLE writer layer for state changes.

Defense in depth (AGENTS.md §3, design §4):
- API routers MUST NOT call ``session.add(...)`` or ``session.execute(...)``
  for INSERT/UPDATE/DELETE on ``[V]/[L-E]/[L-W]/[L-S]/[A]`` tables.
- All state changes go through helpers in this package.
- AST tests in ``tests/static/`` reject violations.

PR1b ships only the auth-domain helpers:
- :mod:`.versioned` — close+insert for [V] tables
- :mod:`.session_cycle` — login lifecycle (skeleton; full in PR7)
- :mod:`.pagination` — opaque cursor encode/decode (REQ-OP-01)

Subsequent PRs add ``append_only``, ``event``, ``workflow``, ``hash_chain``,
``idempotency``, ``sync_outbox``, ``factura_pagos``.
"""
from __future__ import annotations

from .pagination import Cursor, InvalidCursorError, decode, encode

__all__ = ["Cursor", "InvalidCursorError", "encode", "decode"]