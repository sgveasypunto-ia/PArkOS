"""parkos_core CLI entrypoints.

Each CLI is a standalone module invokable via ``python -m``:

- ``parkos_core.cli.pair`` (T-PR8-17) — branch-side one-shot pairing.
- ``parkos_core.cli.doctor`` (T-PR8-18, §21.12 risk #23) — diagnostic
  report covering env + DB + JWT key + cloud API reachability.

The CLIs are intentionally thin wrappers over the library API. They
do not duplicate the env validation, JWT mint, or DB session logic —
those live in ``runtime.env``, ``auth.tokens``, ``db.engine``, etc.
"""
from __future__ import annotations

__all__: list[str] = []