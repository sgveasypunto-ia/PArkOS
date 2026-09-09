"""parkos_core.sync.guards — deploy-role boot-import guards (T-PR1-010, R-D4, R6).

Public surface:

- :mod:`parkos_core.sync.guards.role_guard` — :func:`assert_role`, the
  boot-import guard a role-scoped catalog entry module calls at import
  time.
"""

from __future__ import annotations

__all__: list[str] = []
