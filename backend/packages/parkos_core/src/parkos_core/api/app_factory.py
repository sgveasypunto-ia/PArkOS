"""app_factory.py — unified FastAPI app factory for cloud and branch deploys.

Selects the right app module based on PARKOS_DEPLOY. Lets docker-compose
override the CMD to `parkos_core.api.app_factory:create_app` and have
the same Dockerfile serve both api-admin and api-sucursal entrypoints.

Usage:
    uvicorn parkos_core.api.app_factory:create_app --factory \
        --host 0.0.0.0 --port 8000

Or via Python:
    from parkos_core.api.app_factory import create_app
    app = create_app()

The factory reads PARKOS_DEPLOY at call time (not import time) so a
single image can serve both cloud and branch contexts via docker-compose
``command:`` override.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def create_app():
    """Build the FastAPI app for the current PARKOS_DEPLOY.

    Returns:
        FastAPI: The cloud or branch app instance.
    """
    deploy = os.environ.get("PARKOS_DEPLOY", "cloud").lower()

    if deploy == "branch":
        from api_sucursal_main.app import app
        logger.info("app_factory: loaded api_sucursal_main.app (PARKOS_DEPLOY=branch)")
        return app
    if deploy == "cloud":
        from api_admin_main.app import app
        logger.info("app_factory: loaded api_admin_main.app (PARKOS_DEPLOY=cloud)")
        return app

    raise ValueError(
        f"PARKOS_DEPLOY={deploy!r} is not 'cloud' or 'branch'. "
        "Set PARKOS_DEPLOY in the container environment."
    )


__all__ = ["create_app"]
