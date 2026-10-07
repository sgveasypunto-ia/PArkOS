"""Contract pin: ``GET /workflows/alerta?estado=`` vocabulary (defect L1).

A stale sucursal renderer polled ``estado=activa`` and every call answered
422. The API is the source of truth: the vocabulary is
abierta | en_revision | resuelta; ``activa``/``activo`` were never valid.
"""

from __future__ import annotations

from fastapi import FastAPI
from parkos_core.api.v1.workflows_alerta import router


def _estado_schema() -> dict:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    spec = app.openapi()
    params = spec["paths"]["/api/v1/workflows/alerta"]["get"]["parameters"]
    param = next(p for p in params if p["name"] == "estado")
    schema = param["schema"]
    if "anyOf" in schema:
        schema = next(s for s in schema["anyOf"] if "enum" in s)
    return schema


def test_estado_query_accepts_exactly_the_alerta_vocabulary() -> None:
    assert set(_estado_schema()["enum"]) == {"abierta", "en_revision", "resuelta"}


def test_estado_query_rejects_activa_and_activo() -> None:
    enum = _estado_schema()["enum"]
    assert "activa" not in enum
    assert "activo" not in enum
