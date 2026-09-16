"""HU-F1.9 / T7.1 -- OpenAPI spec contract for ``apps/facturacion``.

The F1.9 surface is exposed via a static OpenAPI YAML document at
``apps/facturacion/openapi.yaml`` (the contract for the F1.11 React app).
This module gates:

- The YAML file exists.
- The YAML contains paths ``/api/v1/facturacion/factura`` and
  ``/api/v1/facturacion/factura-pagos``.
- The YAML components.schemas include the 4 typed error schemas
  (``NitInvalidoErrorSchema``, ``ClienteNoEncontradoErrorSchema``,
  ``DetalleInvalidoErrorSchema``, ``TotalNoCoherenteErrorSchema``).

DB-free: pure file existence + YAML parse.
"""
from __future__ import annotations

from pathlib import Path

OPENAPI_PATH = Path("apps/facturacion/openapi.yaml")


def test_openapi_facturacion_yaml_existe() -> None:
    """RED: YAML file MUST exist before this test passes."""
    assert OPENAPI_PATH.is_file(), (
        f"OpenAPI spec missing at {OPENAPI_PATH}. "
        "Author it with paths /api/v1/facturacion/factura + "
        "/api/v1/facturacion/factura-pagos."
    )


def test_openapi_facturacion_contiene_paths_factura_y_factura_pagos() -> None:
    """RED: YAML MUST declare both POST paths."""
    import yaml  # PyYAML

    data = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    assert "/api/v1/facturacion/factura" in paths, (
        f"path /api/v1/facturacion/factura missing from {OPENAPI_PATH}. "
        f"Found paths: {sorted(paths.keys())}"
    )
    assert "/api/v1/facturacion/factura-pagos" in paths, (
        "path /api/v1/facturacion/factura-pagos missing."
    )


def test_openapi_facturacion_contiene_typed_error_schemas() -> None:
    """RED: YAML components.schemas MUST list the 4 typed error schemas.

    These discriminators drive the 4xx error contract for the
    facturacion surface (D-HU-F1.9-19).
    """
    import yaml

    data = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = data.get("components", {}).get("schemas", {})
    required_schemas = [
        "NitInvalidoErrorSchema",
        "ClienteNoEncontradoErrorSchema",
        "DetalleInvalidoErrorSchema",
        "TotalNoCoherenteErrorSchema",
    ]
    for schema_name in required_schemas:
        assert schema_name in schemas, (
            f"components.schemas.{schema_name} missing from {OPENAPI_PATH}. "
            f"Found: {sorted(schemas.keys())}"
        )
