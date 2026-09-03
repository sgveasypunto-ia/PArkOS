"""test_dian_boundary_branch.py — REQ-X3 / SC-X6 (DIAN boundary, belt-and-suspenders).

Verifies the import-level guard in ``parkos_core.dian.cloud_router``
raises ``ImportError`` when ``PARKOS_DEPLOY=branch``. The cloud_router
module is the single writer for:

- ``POST /api/v1/factura-electronica`` (REQ-34/35, atomic consecutivo++)
- ``POST /api/v1/envio-dian`` (REQ-25-W-CLOUD-ONLY)
- ``POST /api/v1/validacion-evento`` (REQ-25)
- ``POST /api/v1/revocacion-factura-webhook`` (REQ-X3 hash chain extension)

The defense is at TWO layers (design §10):
1. **Image-level**: branch images physically lack the file.
2. **Import-level**: this test verifies the runtime guard.

If a branch image ever tries to ``import parkos_core.dian.cloud_router``,
the guard fires immediately.
"""
from __future__ import annotations

import os
import sys

import pytest


def _force_branch_env(monkeypatch_module) -> None:
    """Set PARKOS_DEPLOY=branch for the duration of one import attempt.

    Uses ``os.environ`` direct manipulation since monkeypatch isn't in the
    static test directory by default.
    """
    _prev = os.environ.get("PARKOS_DEPLOY")
    os.environ["PARKOS_DEPLOY"] = "branch"
    # Stash for restoration
    monkeypatch_module._prev_deploy = _prev


def _restore_env(monkeypatch_module) -> None:
    if monkeypatch_module._prev_deploy is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = monkeypatch_module._prev_deploy


def test_dian_cloud_router_unavailable_on_branch() -> None:
    """``from parkos_core.dian.cloud_router import router`` raises ImportError on branch."""
    _prev = os.environ.get("PARKOS_DEPLOY")
    os.environ["PARKOS_DEPLOY"] = "branch"

    # Clear any cached module so the guard re-runs in the new env
    sys.modules.pop("parkos_core.dian.cloud_router", None)
    sys.modules.pop("parkos_core.dian", None)

    try:
        with pytest.raises(ImportError) as exc_info:
            from parkos_core.dian import cloud_router  # noqa: F401
        assert "branch deploys" in str(exc_info.value) or "DIAN" in str(exc_info.value), (
            f"ImportError message should mention branch deploys / DIAN; got {exc_info.value!r}"
        )
    finally:
        # Restore env
        if _prev is None:
            os.environ.pop("PARKOS_DEPLOY", None)
        else:
            os.environ["PARKOS_DEPLOY"] = _prev


def test_dian_cloud_router_alt_import_path() -> None:
    """``from parkos_core.dian.cloud_router import router`` (alt path) also raises."""
    _prev = os.environ.get("PARKOS_DEPLOY")
    os.environ["PARKOS_DEPLOY"] = "branch"

    sys.modules.pop("parkos_core.dian.cloud_router", None)
    sys.modules.pop("parkos_core.dian", None)

    try:
        with pytest.raises(ImportError):
            from parkos_core.dian.cloud_router import router  # noqa: F401
    finally:
        if _prev is None:
            os.environ.pop("PARKOS_DEPLOY", None)
        else:
            os.environ["PARKOS_DEPLOY"] = _prev


def test_dian_cloud_router_loads_on_cloud_deploy() -> None:
    """On default (cloud) deploy, the import succeeds."""
    import os
    # tests/static/conftest.py defaults to PARKOS_DEPLOY=branch; this test
    # needs cloud deploy. Override explicitly.
    _prev = os.environ.get("PARKOS_DEPLOY")
    os.environ["PARKOS_DEPLOY"] = "cloud"

    sys.modules.pop("parkos_core.dian.cloud_router", None)
    sys.modules.pop("parkos_core.dian", None)
    try:
        from parkos_core.dian import cloud_router  # noqa: F401
        # If we got here, the import succeeded — assertion passes.
        assert hasattr(cloud_router, "router")
    except ImportError as e:
        # If the import failed on cloud deploy, that's a bug.
        raise AssertionError(
            f"Importing cloud_router on default (cloud) deploy MUST succeed; got {e!r}"
        ) from e
    finally:
        # Restore for subsequent tests
        if _prev is None:
            os.environ.pop("PARKOS_DEPLOY", None)
        else:
            os.environ["PARKOS_DEPLOY"] = _prev
