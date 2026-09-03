"""Re-export the declarative base from :mod:`parkos_core.models.base`.

Splitting this re-export into its own module keeps ``db/`` self-contained —
``engine.py`` and ``tenancy.py`` import from here rather than reaching into
``models/``, which would otherwise force circular imports during the
``models/*`` package's own initialization.
"""
from __future__ import annotations

from ..models.base import Base

__all__ = ["Base"]