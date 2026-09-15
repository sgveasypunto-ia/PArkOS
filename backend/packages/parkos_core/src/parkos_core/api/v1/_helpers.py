"""Shared HTTP helpers for the ``api/v1`` routers.

**R-A6 mitigation (HU-F1.6).** The F1.5/F1.8 endpoints repeat
``headers={"Cache-Control": "no-store"}`` inline on every
``HTTPException(...)`` raise. To keep the chain consistent across the
operator-facing routes (create_ingreso F1.6, cotizar F1.8, get_ocupacion
F1.5) without leaking that pattern, both successes and errors route
through :func:`no_store_headers` + :func:`apply_no_store_header`.

The helper is intentionally trivial -- no logging, no Request-state
mutation -- so it can be unit-tested without a session.
"""
from __future__ import annotations

from fastapi import Response


def no_store_headers() -> dict[str, str]:
    """Return the ``Cache-Control: no-store`` header dict (R-A6).

    Every response from operator-facing mutating endpoints (``POST
    /operacion/ingresos``, ``GET /operacion/cotizar``) MUST carry this
    header regardless of status code. A proxy that serves a stale quote
    or a stale ingreso-write would silently accept out-of-date state.
    """
    return {"Cache-Control": "no-store"}


def apply_no_store_header(response: Response) -> None:
    """Attach ``Cache-Control: no-store`` to a 2xx response (R-A6)."""
    response.headers["Cache-Control"] = "no-store"


__all__ = ["apply_no_store_header", "no_store_headers"]
