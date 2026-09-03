"""parkos cloud admin API entrypoint (FastAPI app + uvicorn runner).

Mounts the shared ``parkos_core.api.v1`` routers under ``/api/v1``. On cloud
images (``PARKOS_DEPLOY=cloud``) the DIAN-only router is lazily imported;
on branch images the import guard in :mod:`parkos_core.api.v1` short-circuits.
"""

__all__: list[str] = []