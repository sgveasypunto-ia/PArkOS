"""HU-F1.10 / T1.1 — Pydantic v2 schema validation tests.

Pure Pydantic validation tests, no DB, no HTTP. The ``_Base`` ancestor
of all ``FacturaElectronica*`` / ``EnvioDian*`` / typed error schemas
sets ``extra='forbid'`` (F1.9 precedent); the tests below pin that
contract (DEC-FE-05 — server-assigns ``prefijo``/``consecutivo``; the
client must NOT be able to smuggle them in the request body).

REQ-OPS-064 (server-assigns prefijo+consecutivo) +
REQ-OPS-067 (one FE per factura) are the load-bearing requirements.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.schemas.facturacion import (
    EnvioDianRead,
    FacturaElectronicaCreate,
    FacturaElectronicaRead,
    NumeracionAgotadaError,
)
from pydantic import ValidationError


def test_fe_create_rejects_prefijo_injection() -> None:
    """T1: ``extra='forbid'`` rejects ``prefijo`` smuggling (DEC-FE-05)."""
    payload = {
        "uuid_factura": str(uuid_lib.uuid4()),
        "prefijo": "SETP",
    }
    with pytest.raises(ValidationError):
        FacturaElectronicaCreate.model_validate(payload)


def test_fe_create_rejects_consecutivo_injection() -> None:
    """T2: ``extra='forbid'`` rejects ``consecutivo`` smuggling (DEC-FE-05)."""
    payload = {
        "uuid_factura": str(uuid_lib.uuid4()),
        "consecutivo": 4521,
    }
    with pytest.raises(ValidationError):
        FacturaElectronicaCreate.model_validate(payload)


def test_fe_create_rejects_uuid_resolucion_injection() -> None:
    """T3: ``extra='forbid'`` rejects ``uuid_resolucion_facturacion`` (4NF)."""
    payload = {
        "uuid_factura": str(uuid_lib.uuid4()),
        "uuid_resolucion_facturacion": str(uuid_lib.uuid4()),
    }
    with pytest.raises(ValidationError):
        FacturaElectronicaCreate.model_validate(payload)


def test_fe_create_requires_uuid_factura() -> None:
    """T4: missing ``uuid_factura`` raises ValidationError."""
    with pytest.raises(ValidationError):
        FacturaElectronicaCreate.model_validate({})


def test_fe_create_accepts_uuid_factura_only() -> None:
    """T5: the minimum valid payload is ``{"uuid_factura": <uuid>}``."""
    uuid_factura = uuid_lib.uuid4()
    payload = FacturaElectronicaCreate(uuid_factura=uuid_factura)
    assert payload.uuid_factura == uuid_factura


def test_envio_dian_read_estado_literal_enforced() -> None:
    """T6: ``estado`` is a strict ``Literal[...]`` (no fabrication)."""
    base = {
        "uuid": str(uuid_lib.uuid4()),
        "uuid_factura_electronica": str(uuid_lib.uuid4()),
        "timestamp_evento": "2026-09-14T10:00:00",
    }
    # Valid values
    for estado in ("pendiente", "enviado", "aceptado", "rechazado"):
        EnvioDianRead.model_validate({**base, "estado": estado})
    # Invalid value
    with pytest.raises(ValidationError):
        EnvioDianRead.model_validate({**base, "estado": "reportado"})


def test_factura_electronica_read_requires_canonical_fields() -> None:
    """T7: ``FacturaElectronicaRead`` requires prefijo + consecutivo + envio_actual."""
    fe_uuid = uuid_lib.uuid4()
    envio_uuid = uuid_lib.uuid4()
    payload = FacturaElectronicaRead(
        uuid=fe_uuid,
        prefijo="SETP",
        consecutivo=42,
        uuid_factura=uuid_lib.uuid4(),
        uuid_resolucion_facturacion=uuid_lib.uuid4(),
        created_at="2026-09-14T10:00:00",
        envio_actual=EnvioDianRead(
            uuid=envio_uuid,
            uuid_factura_electronica=fe_uuid,
            estado="pendiente",
            timestamp_evento="2026-09-14T10:00:00",
        ),
    )
    assert payload.prefijo == "SETP"
    assert payload.consecutivo == 42
    assert payload.envio_actual.estado == "pendiente"


def test_numeracion_agotada_error_schema_typed() -> None:
    """T8: ``NumeracionAgotadaError`` schema matches contract (DEC-FE-03)."""
    resolucion_uuid = uuid_lib.uuid4()
    payload = NumeracionAgotadaError(
        error="numeracion_agotada",
        uuid_resolucion_facturacion=resolucion_uuid,
        rango_hasta=5000,
        prefijo="SETP",
    )
    assert payload.error == "numeracion_agotada"
    assert payload.uuid_resolucion_facturacion == resolucion_uuid
    assert payload.rango_hasta == 5000
    assert payload.prefijo == "SETP"


def test_numeracion_agotada_error_wrong_discriminator_rejected() -> None:
    """T9: error discriminator is strictly Literal['numeracion_agotada']."""
    payload = {
        "error": "otro_error",
        "uuid_resolucion_facturacion": str(uuid_lib.uuid4()),
        "rango_hasta": 5000,
        "prefijo": "SETP",
    }
    with pytest.raises(ValidationError):
        NumeracionAgotadaError.model_validate(payload)
