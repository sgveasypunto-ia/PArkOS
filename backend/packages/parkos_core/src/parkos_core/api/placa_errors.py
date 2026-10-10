"""422 mapping for placas rejected at the request-validation edge.

Schemas typed with :data:`parkos_core.schemas._placa.PlacaVehiculo` raise
:class:`PlacaFormatoInvalidoError` inside Pydantic. By default FastAPI would
answer ``{"detail": [{"loc", "msg", "type"}]}``; the project's other 422s are
``{"detail": {"error", "message", "placa"}}`` (e.g. ``placa_duplicada_en_venta``).
This handler makes placa failures use the project shape on every endpoint that
accepts a placa -- including the generic CRUD routers -- and leaves every other
validation error to FastAPI's default handler.

Register it once per app (``api_sucursal_main`` and ``api_admin_main``).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..repo.placa_formato import FORMATOS_ACEPTADOS, PlacaFormatoInvalidoError


_MAX_ECO = 32


def _placa_error(exc: RequestValidationError) -> PlacaFormatoInvalidoError | None:
    for err in exc.errors():
        cause = (err.get("ctx") or {}).get("error")
        if isinstance(cause, PlacaFormatoInvalidoError):
            return cause
    return None


async def placa_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    cause = _placa_error(exc)
    if cause is None:
        return await request_validation_exception_handler(request, exc)
    # Cap the echoed input: the 422 must not reflect an arbitrarily large body.
    placa = str(cause.placa)[:_MAX_ECO]
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "error": "placa_formato_invalido",
                "placa": placa,
                "message": (
                    f"La placa {placa!r} no tiene un formato valido; "
                    f"use {FORMATOS_ACEPTADOS[0]} (carro) o "
                    f"{FORMATOS_ACEPTADOS[1]} (moto)."
                ),
                "formatos_aceptados": list(FORMATOS_ACEPTADOS),
            }
        },
        headers={"Cache-Control": "no-store"},
    )


def register_placa_validation_handler(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, placa_validation_handler)


__all__ = ["placa_validation_handler", "register_placa_validation_handler"]
