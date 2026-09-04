"""test_openapi_no_delete_operations.py — SC-04 hard gate.

Scans the two committed OpenAPI artifacts (``backend/packages/api_admin/
openapi.json`` + ``backend/packages/api_sucursal/openapi.json``) for any
HTTP method ``delete`` exposed by any path. AGENTS.md §3 forbids DELETE
endpoints at every layer — the API surface must therefore produce zero
DELETE operations under the OpenAPI 3.1 schema.

This is a stronger guarantee than the AST + ``app.openapi()`` scan in
``test_no_delete_routes.py``: that test inspects the live module graph at
test time, while this one inspects the committed artifact that downstream
tooling (CD pipelines, SDK generators, partner docs) actually consumes.
A divergence between the live OpenAPI and the committed artifact is itself
a defect — and would let a DELETE operation slip through if the artifact is
stale.

Failure mode: if either ``openapi.json`` contains a path whose methods
dict has a ``delete`` key, the test fails with the list of offenders so
the diff is actionable.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# Resolve from the test file's location: tests/static/<file>.py -> 2 levels up
# reaches ``backend/``. Both artifacts live at ``backend/packages/<pkg>/``.
_OPENAPI_ADMIN = (
    Path(__file__).resolve().parents[2] / "packages" / "api_admin" / "openapi.json"
)
_OPENAPI_BRANCH = (
    Path(__file__).resolve().parents[2] / "packages" / "api_sucursal" / "openapi.json"
)


def _load_or_skip(path: Path) -> dict | None:
    """Load a JSON file as an OpenAPI spec, or skip if the artifact is absent.

    Tests under ``tests/static/`` must NOT depend on a build step; if a
    reviewer runs the suite locally without the committed artifacts, the
    test skips with a clear pointer rather than erroring.
    """
    if not path.exists():
        pytest.skip(f"OpenAPI artifact not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"OpenAPI artifact is not valid JSON: {path} ({exc})")


def _delete_operations(spec: dict) -> list[str]:
    """Return ``"<path> (delete)"`` for every DELETE entry in ``spec.paths``."""
    offenders: list[str] = []
    for path, ops in (spec.get("paths") or {}).items():
        if not isinstance(ops, dict):
            continue
        if "delete" in ops:
            offenders.append(f"{path} (delete)")
    return offenders


def test_admin_openapi_has_no_delete_operations() -> None:
    """``packages/api_admin/openapi.json`` MUST contain zero DELETE operations."""
    spec = _load_or_skip(_OPENAPI_ADMIN)
    assert spec is not None, "spec loader skipped via pytest.skip"
    bad = _delete_operations(spec)
    assert bad == [], (
        "admin OpenAPI contains DELETE operations (violates SC-04 / AGENTS.md §3):\n"
        + "\n".join(f"  {entry}" for entry in bad)
    )


def test_branch_openapi_has_no_delete_operations() -> None:
    """``packages/api_sucursal/openapi.json`` MUST contain zero DELETE operations."""
    spec = _load_or_skip(_OPENAPI_BRANCH)
    assert spec is not None, "spec loader skipped via pytest.skip"
    bad = _delete_operations(spec)
    assert bad == [], (
        "branch OpenAPI contains DELETE operations (violates SC-04 / AGENTS.md §3):\n"
        + "\n".join(f"  {entry}" for entry in bad)
    )
