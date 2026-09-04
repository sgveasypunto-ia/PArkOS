"""parkos-api-sucursal FastAPI app.

Branch-pinned entrypoint: only ``operador-`` + ``sync-agent-`` tokens are
accepted on the mounted routes. ``admin-`` tokens are rejected by the JWT
guard (``requires_issuer("operador-,sync-agent-")``) — cross-audience
tokens return 401.

The DIAN-only boundary (design §10) is enforced at image level: branch
images physically lack ``parkos_core/dian/cloud_router.py``. The lazy
import guard in :mod:`parkos_core.api.v1` is belt-and-suspenders.

Layer ``runtime/env`` is wired FIRST (T-PR8-02): ``load_config()`` runs
before any DB or network connection so misconfiguration fails fast
with exit code ``2`` rather than surfacing as a confusing
``RuntimeError`` deep inside a third-party driver (design §21.2).
"""
from __future__ import annotations

import logging
import os
import sys
import uuid as uuid_lib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# T-PR8-02: env validator is the first parkos_core import so a misconfig
# stops the process BEFORE we open a DB pool, a DIAN HTTP client, or a
# uvicorn socket. The validator prints the offending var name(s) on
# ``MissingEnvError``; we additionally ``sys.exit(2)`` to honor the
# orchestrator exit-code contract (§21.2).
from parkos_core.runtime.env import MissingEnvError, load_config
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

    Note on T-PR8-02: ``load_config()`` is called in :func:`main`
    (the uvicorn entrypoint), NOT here. ``create_app`` is called by
    tests that want to inspect the FastAPI app object without booting
    the full runtime stack. Branch deploys additionally require
    ``PARKOS_SUCURSAL_UUID`` (UUIDv4) + ``PARKOS_CLOUD_API_URL`` +
    ``PARKOS_SYNC_JWT_PATH`` — all surfaced as a single
    ``MissingEnvError`` so the operator fixes everything in one pass.
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
    """uvicorn entrypoint.

    T-PR8-02: validate runtime env FIRST. ``load_config()`` raises
    ``MissingEnvError`` with a list of offending var names; we surface
    the error to stderr and exit ``2`` so the orchestrator (Docker,
    Kubernetes) marks the boot as a hard failure rather than a
    crash-loop soft failure.

    Placing the validator here (not in :func:`create_app`) means
    production boots fail fast WITHOUT blocking ``create_app`` from
    tests that want to introspect the FastAPI app object without
    setting valid runtime env.
    """
    try:
        load_config()
    except MissingEnvError as exc:
        sys.stderr.write("env validation failed for api_sucursal:\n")
        for err in exc.errors:
            sys.stderr.write(f"  - {err}\n")
        sys.exit(2)

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