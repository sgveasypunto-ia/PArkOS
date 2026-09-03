"""Directory-scoped conftest for ``tests/static/``.

Sets ``PARKOS_DEPLOY=branch`` BEFORE any test in this directory imports
``api_sucursal_main.app``. The v1 router's lazy-import of
``dian.cloud_router`` reads the env var at import time, so the test
fixtures must mirror the branch image-level exclusion.

PR6 introduced ``dian/cloud_router.py`` (which raises ``ImportError`` on
``PARKOS_DEPLOY=branch``). Without this conftest, the default
``PARKOS_DEPLOY="cloud"`` causes the cloud_router to load into the
"branch" app at test time — breaking the
``test_openapi_branch_excludes_cloud`` static test.

This is a NEW file (not a modification of PR1c's ``tests/conftest.py``).
"""
from __future__ import annotations

import os

# Default to branch for ALL tests under tests/static/. The static tests
# validate DIAN boundary + schema-only contracts; they never need cloud
# mounts. Tests that explicitly need cloud deploy can override via
# monkeypatch.
os.environ.setdefault("PARKOS_DEPLOY", "branch")