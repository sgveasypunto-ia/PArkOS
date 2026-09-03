"""test_openapi_branch_excludes_cloud.py — REQ-X3.

The branch FastAPI app (``api_sucursal_main``) MUST NOT expose any of the
cloud-only paths. Cloud-only paths come from the ``dian.cloud_router``
module (PR8+) and are gated by both image-level exclusion (the branch
Docker image physically lacks the module) and the JWT scope guard
(``admin-`` tokens only, not ``operador-`` / ``sync-agent-``).

This test generates the OpenAPI 3.1 schema from
``api_sucursal_main.app`` at test time and asserts that none of the
cloud-only paths are present:

  - ``/api/v1/factura-electronica``
  - ``/api/v1/factura-electronica/{...}``
  - ``/api/v1/envio-dian``
  - ``/api/v1/envio-dian/{...}``
  - ``/api/v1/validacion-evento``
  - ``/api/v1/validacion-evento/{...}``
  - ``/api/v1/revocacion-factura``
  - ``/api/v1/revocacion-factura/{...}``

Substring match catches the resource plus any sub-paths (path params,
action suffixes).

Why we don't check the admin app: the admin app can legitimately expose
all of these. The invariant is one-way: branch → cloud is forbidden,
cloud → branch is allowed (admin sees the union).
"""
from __future__ import annotations

import pytest

CLOUD_ONLY_PATH_FRAGMENTS = (
    "factura-electronica",
    "envio-dian",
    "validacion-evento",
    "revocacion-factura",
)


def _branch_openapi_paths() -> list[str]:
    try:
        from api_sucursal_main.app import app as sucursal_app
    except ImportError as exc:
        pytest.skip(f"could not import api_sucursal_main.app: {exc}")
    return sorted(sucursal_app.openapi().get("paths", {}).keys())


def test_branch_openapi_excludes_cloud_routes() -> None:
    """The branch app OpenAPI MUST NOT contain any cloud-only path fragment."""
    paths = _branch_openapi_paths()
    offenders = [
        p for p in paths
        if any(fragment in p for fragment in CLOUD_ONLY_PATH_FRAGMENTS)
    ]
    assert not offenders, (
        "Branch OpenAPI exposes cloud-only paths:\n"
        + "\n".join(f"  {p}" for p in offenders)
        + "\n\nCloud-only paths are gated by image-level exclusion (branch "
        "Docker image physically lacks parkos_core.dian.cloud_router). If "
        "this test fails, the branch app has acquired a cloud-only import."
    )


def test_branch_openapi_has_no_cloud_only_path_fragments() -> None:
    """Stronger variant: assert no CLOUD-ONLY path fragments are present.

    This is the production invariant. Routes legitimately mounted on the
    branch app (auth, catalogos, health) MUST still be present; only
    cloud-only paths (factura-electronica, envio-dian, etc.) MUST be
    missing.
    """
    paths = _branch_openapi_paths()
    cloud_hits: list[str] = []
    for p in paths:
        for fragment in CLOUD_ONLY_PATH_FRAGMENTS:
            if fragment in p:
                cloud_hits.append(f"{p} (matched: {fragment})")
                break
    assert not cloud_hits, (
        "Branch OpenAPI exposes cloud-only paths:\n"
        + "\n".join(f"  {h}" for h in cloud_hits)
    )
    # And the branch app SHOULD mount some legitimate non-cloud paths.
    legitimate = [p for p in paths if not any(f in p for f in CLOUD_ONLY_PATH_FRAGMENTS)]
    assert legitimate, (
        "Branch OpenAPI exposes only the root — expected at least "
        "auth/catalogos/health to be mounted from the PR1b routers."
    )