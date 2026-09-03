"""parkos_core Pydantic schemas — domain-grouped (design §2 + §6).

Per table the convention is ``Read``, ``Create``, ``Update``, ``Filter``,
``ReadList``. Field names mirror ORM column names 1:1 so ``model_validate(row)``
is the only mapping (no aliases; C-3 in bi-temporal-crud).

PR1b ships the auth-domain schemas (5 V + 1 L_S) plus a smoke-mount set
for the catalog router. Subsequent PRs add the rest of catalog,
empresa/sucursal, operacion, facturacion, workflows domains.
"""
from __future__ import annotations

# Domain submodules re-export their symbols through __all__ at the bottom of
# each file. Top-level __init__ does NOT eagerly import them to keep the
# package import-time minimal — schemas are pulled in by routers only.
from . import auth as auth
from . import catalogos as catalogos
from . import common as common

__all__ = ["auth", "catalogos", "common"]