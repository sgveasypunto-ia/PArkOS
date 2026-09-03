"""parkos branch API entrypoint (FastAPI app + uvicorn runner).

Mounts the shared ``parkos_core.api.v1`` routers under ``/api/v1``. On
branch images the DIAN-only boundary short-circuits — ``dian.cloud_router``
is not on disk (Docker .dockerignore excludes it) and the lazy import
guard in :mod:`parkos_core.api.v1` raises a clear error if it ever runs.
"""

__all__: list[str] = []