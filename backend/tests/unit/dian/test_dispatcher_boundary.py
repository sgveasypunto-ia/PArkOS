"""Boundary guard test for parkos_core.dian.cloud.dispatcher (T-PR11-11, REQ-X3).

The dispatcher module has a module-level guard that raises ImportError
when PARKOS_DEPLOY=branch (DIAN cloud is cloud-only). This test
verifies the guard fires on branch deploy.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest


def test_dispatcher_unavailable_on_branch_deploy() -> None:
    """``from parkos_core.dian.cloud.dispatcher`` raises ImportError on PARKOS_DEPLOY=branch."""
    original = os.environ.get("PARKOS_DEPLOY", "cloud")
    os.environ["PARKOS_DEPLOY"] = "branch"

    # Purge any cached import of the dispatcher module (or its parents)
    # so the guard fires fresh on this import.
    for mod_name in (
        "parkos_core.dian.cloud.dispatcher",
        "parkos_core.dian.cloud",
        "parkos_core.dian",
    ):
        sys.modules.pop(mod_name, None)

    try:
        with pytest.raises(ImportError) as exc_info:
            # Use importlib to ensure fresh import (the test_..._import_alias
            # pattern from static test_dian_boundary_branch.py).
            importlib.import_module("parkos_core.dian.cloud.dispatcher")
        assert "branch" in str(exc_info.value).lower() or "dian" in str(exc_info.value).lower(), (
            f"ImportError message should mention branch / DIAN; got {exc_info.value!r}"
        )
    finally:
        os.environ["PARKOS_DEPLOY"] = original
        # Purge again so subsequent tests can import normally.
        for mod_name in (
            "parkos_core.dian.cloud.dispatcher",
            "parkos_core.dian.cloud",
            "parkos_core.dian",
        ):
            sys.modules.pop(mod_name, None)
