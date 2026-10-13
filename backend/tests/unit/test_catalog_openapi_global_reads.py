"""OpenAPI must document the handlers that actually serve catalog reads.

The 9 catalogs with ``tenant_free_reads`` register their 3 GET routes on the
catalogos router BEFORE the factory sub-router, so FastAPI serves the
tenant-free handlers. The factory's duplicate GETs used to overwrite them in
``/openapi.json`` (same path + method), hiding ``tipo_cliente`` /
``uuid_tipo_vehiculo`` and wrongly advertising ``X-Sucursal-Context``.
"""
from __future__ import annotations

import pytest

_CATALOG_RESOURCES: tuple[str, ...] = (
    "tipo-persona",
    "tipos-vehiculo",
    "tipo-subscripciones",
    "tipo-tarifa",
    "tipo-sucursal",
    "tipo-arqueo",
    "impuestos",
    "otros-cobros",
    "costos-servicios",
)
_BASE = "/api/v1/catalogos"
_TENANT_HEADER = "X-Sucursal-Context"


@pytest.fixture(scope="module")
def spec() -> dict:
    from fastapi import FastAPI
    from parkos_core.api.v1.catalogos import router as catalogos_router

    app = FastAPI()
    app.include_router(catalogos_router, prefix="/api/v1")
    return app.openapi()


def _param_names(operation: dict) -> set[str]:
    return {p["name"] for p in operation.get("parameters", [])}


@pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
def test_list_get_documents_global_handler_params(spec: dict, resource: str) -> None:
    names = _param_names(spec["paths"][f"{_BASE}/{resource}"]["get"])
    assert _TENANT_HEADER not in names
    assert {"cursor", "limit", "uuid_tipo_vehiculo", "tipo_cliente"} <= names


@pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
def test_detail_and_history_get_do_not_require_tenant_header(
    spec: dict, resource: str
) -> None:
    for suffix in ("/{uuid}", "/{uuid}/history"):
        op = spec["paths"][f"{_BASE}/{resource}{suffix}"]["get"]
        assert _TENANT_HEADER not in _param_names(op), f"{resource}{suffix}"


@pytest.mark.parametrize("resource", _CATALOG_RESOURCES)
def test_writes_still_document_tenant_header(spec: dict, resource: str) -> None:
    item = spec["paths"][f"{_BASE}/{resource}"]
    assert _TENANT_HEADER in _param_names(item["post"])
    assert _TENANT_HEADER in _param_names(spec["paths"][f"{_BASE}/{resource}/{{uuid}}"]["put"])
