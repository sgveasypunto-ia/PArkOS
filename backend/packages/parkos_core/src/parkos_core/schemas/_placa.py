"""Reusable Pydantic types for request bodies that carry a placa.

``PlacaVehiculo`` normalizes (trim + upper + no whitespace) and enforces the
same format as the branch frontend (see :mod:`parkos_core.repo.placa_formato`).
On failure it raises :class:`PlacaFormatoInvalidoError` (a ``ValueError``);
:func:`parkos_core.api.placa_errors.register_placa_validation_handler` turns
it into the project-standard 422 ``{error, message, placa}``.

Use it ONLY on inputs (Create/Update/request schemas). Never on Read schemas
or filters: historical rows may hold placas that predate the rule.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator

from ..repo.placa_formato import validar_placa

PlacaVehiculo = Annotated[str, BeforeValidator(validar_placa)]
"""Required placa, canonicalized. ``PlacaVehiculo | None`` for optional ones."""

__all__ = ["PlacaVehiculo"]
