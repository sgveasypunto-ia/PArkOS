"""Thin Python wrapper around ``prod.calcular_cotizacion(p_uuid_ingreso uuid)``.

Implements REQ-OPS-022..024 from the HU-F1.8 spec: thin async adapter
that calls the PL/pgSQL function via ``session.execute(text(...))``,
unwraps the jsonb envelope, and maps the typed errors to custom
exceptions so the FastAPI handler (``api/v1/operacion.py``) can convert
them to ``HTTPException`` with the right status codes.

**All pricing logic lives in PL/pgSQL** — this module deliberately
contains ZERO formula code. The whole reason the function exists
server-side is transactional atomicity between ``cotizar`` and
HU-F1.7 ``POST /operacion/salidas`` (KD-1 ``SELECT ... FOR SHARE`` on
``tarifas_sucursal``); duplicating any of that in Python would defeat
the lock.

**Precedence (REQ-OPS-024).** The PL/pgSQL function short-circuits in
the order ``ingreso_no_encontrado > tarifa_no_vigente > iva_no_
configurado``. This module maps the jsonb ``error`` key to typed
exceptions — same precedence, no reordering.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class CotizacionError(Exception):
    """Base class for every typed error the quotation primitive can raise.

    The handler in ``api/v1/operacion.py`` catches this base to attach
    ``Cache-Control: no-store`` to every error response (R8). Concrete
    subclasses carry the specific error code the client sees.
    """

    error_code: str = "cotizacion_error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.error_code)
        self.message = message or self.error_code


class IngresoNoEncontrado(CotizacionError):
    """404 — the ``uuid_ingreso`` does not exist or already has a non-anulada salida."""

    error_code = "ingreso_no_encontrado"


class TarifaNoVigente(CotizacionError):
    """404 — ingreso OK but no vigente ``tarifas_sucursal`` row for the combination (KD-3)."""

    error_code = "tarifa_no_vigente"


class IVANoConfigurado(CotizacionError):
    """500 — no ``impuestos`` row with ``nombre='IVA'`` vigente at ``NOW()`` (KD-IVA)."""

    error_code = "iva_no_configurado"


# Mapping from the jsonb ``error`` key returned by the PL/pgSQL to the
# concrete exception class the handler raises. Order is irrelevant — the
# function only ever returns ONE error key per call (first-match
# short-circuit, REQ-OPS-024).
_ERROR_TO_EXCEPTION: dict[str, type[CotizacionError]] = {
    "ingreso_no_encontrado": IngresoNoEncontrado,
    "tarifa_no_vigente": TarifaNoVigente,
    "iva_no_configurado": IVANoConfigurado,
}


async def cotizar_ingreso(
    session: AsyncSession,
    *,
    uuid_ingreso: UUID,
) -> dict[str, Any]:
    """Invoke ``prod.calcular_cotizacion(:uuid)`` and return its jsonb payload.

    On a typed error (jsonb ``{"error": "<code>"}`` envelope), raise the
    matching :class:`CotizacionError` subclass. On a successful payload
    (``{"cobrar": true|false, ...}``) return the dict unchanged so the
    caller can build the Pydantic response.

    The function does NOT commit or rollback the session — the handler
    controls the transaction boundary. The PL/pgSQL function holds a
    ``SELECT ... FOR SHARE`` lock for the whole transaction, so the
    handler MUST commit (or the lock leaks until the connection is
    returned to the pool).
    """
    payload = (
        await session.execute(
            text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
            {"uuid": str(uuid_ingreso)},
        )
    ).scalar_one()

    # The function is declared STABLE and the contract guarantees the
    # payload is a jsonb dict; defensive type check in case a future
    # migration accidentally changes the return type.
    if not isinstance(payload, dict):
        raise CotizacionError(
            f"calcular_cotizacion returned unexpected type "
            f"{type(payload).__name__}; expected jsonb dict"
        )

    error_code = payload.get("error")
    if isinstance(error_code, str):
        exception_cls = _ERROR_TO_EXCEPTION.get(error_code)
        if exception_cls is not None:
            raise exception_cls()
        # Unknown error code from the function — surface it as the base
        # exception so the handler can still respond with 500 + the
        # code, but never silently swallow it.
        raise CotizacionError(f"unknown_error_code={error_code!r}")

    return payload


__all__ = [
    "CotizacionError",
    "IVANoConfigurado",
    "IngresoNoEncontrado",
    "TarifaNoVigente",
    "cotizar_ingreso",
]
