"""parkos-api-admin FastAPI app.

Layer 2 of the DIAN-only boundary (design §10): the cloud router is
lazily imported when ``PARKOS_DEPLOY=cloud``. Branch images never reach
this branch because the entrypoint is cloud-only.

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
    """Build the cloud admin FastAPI app.

    The DIAN-only boundary is enforced inside ``parkos_core.api.v1`` via a
    lazy import of ``dian.cloud_router`` (gated on ``PARKOS_DEPLOY=cloud``).

    Note on T-PR8-02: ``load_config()`` is called in :func:`main`
    (the uvicorn entrypoint), NOT here. ``create_app`` is called by
    tests that want to inspect the FastAPI app object without booting
    the full runtime stack; running the env validator here would mean
    every test (incl. ``tests/static/test_no_delete_routes.py``) must
    set valid ``PARKOS_*`` env vars or skip. Keeping the validator at
    :func:`main` preserves "fail-fast before the socket binds" without
    hampering the test surface.
    """
    app = FastAPI(
        title="parkos-api-admin",
        version="0.1.0",
        description="Cloud admin API — multi-tenant, three-issuer JWT, DIAN-aware.",
    )

    # CORS — dev: allow all origins. Tighten in PR7 with the production allowlist.
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
            "service": "parkos-api-admin",
            "deploy": os.environ.get("PARKOS_DEPLOY", "cloud"),
        }

    # Mount the v1 routers
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
        sys.stderr.write("env validation failed for api_admin:\n")
        for err in exc.errors:
            sys.stderr.write(f"  - {err}\n")
        sys.exit(2)

    import uvicorn

    uvicorn.run(
        "api_admin_main.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=bool(os.environ.get("RELOAD", "")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()


__all__ = ["app", "create_app", "main"]