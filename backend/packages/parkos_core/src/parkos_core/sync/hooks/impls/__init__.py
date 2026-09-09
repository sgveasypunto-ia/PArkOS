"""hooks/impls/ — concrete ``HookFn`` implementations (PR5 + PR6).

Each module self-registers under a stable name via
``sync.hooks.registry.register`` at import time AND is imported directly by
the catalog entry that binds it (``catalog/entries/sync_entries_{v,a}.py``)
— the registry is the discovery/introspection surface (e.g. for tests that
resolve a hook by name), the direct import is what actually wires
``hook_pre_insert``/``hook_post_insert``/``hook_chain_extend`` onto a
``SyncCatalogEntry`` at catalog-construction time.
"""
from __future__ import annotations

__all__: list[str] = []
