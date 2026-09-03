"""parkos-api-sucursal FastAPI app.

Branch-pinned entrypoint: only ``operador-`` + ``sync-agent-`` tokens are
accepted on the mounted routes. ``admin-`` tokens are rejected by the JWT
guard (``requires_issuer("operador-,sync-agent-")``) — cross-audience
tokens return 401.

The DIAN-only boundary (design §10) is enforced at image level: branch
images physically lack ``parkos_core/dian/cloud_router.py``. The lazy
import guard in :mod:`parkos_core.api.v1` is belt-and-suspenders.
"""
from __future__ import annotations

import logging
import os
import uuid as uuid_lib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a stable ``X-Request-ID`` to every request for log correlation."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid_lib.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def create_app() -> FastAPI:
    """Build the branch FastAPI app.

    Branch-pinned routes only (operador + sync-agent). The DIAN router is
    NOT mounted (design §10): branch images physically lack the module.
    """
    app = FastAPI(
        title="parkos-api-sucursal",
        version="0.1.0",
        description="Branch API — operador + sync-agent only, offline-first.",
    )

    # CORS — dev: allow all origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)

    # Idempotency-Key passthrough (REQ-OP-04, design §8).
    from parkos_core.api.middleware import IdempotencyKeyMiddleware
    app.add_middleware(IdempotencyKeyMiddleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "parkos-api-sucursal",
            "deploy": os.environ.get("PARKOS_DEPLOY", "branch"),
        }

    # Mount the v1 routers (the v1 module skips the cloud_router import on
    # branch deploy — no error path).
    from parkos_core.api.v1 import router as v1_router
    app.include_router(v1_router)

    return app


app = create_app()


def main() -> None:
    """uvicorn entrypoint."""
    import uvicorn

    uvicorn.run(
        "api_sucursal_main.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8001")),
        reload=bool(os.environ.get("RELOAD", "")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()


__all__ = ["app", "create_app", "main"]