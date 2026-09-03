"""parkos_core.sync — bidirectional sync HTTP transport + workers (PR9, T-PR9-02).

Public surface (PR9-scope):

- :mod:`parkos_core.sync.transport` — :class:`SyncHttpClient` for the
  HTTP transport (``push``, ``pull``, ``heartbeat``, ``rotate-jwt``).
"""
from __future__ import annotations

__all__: list[str] = []
