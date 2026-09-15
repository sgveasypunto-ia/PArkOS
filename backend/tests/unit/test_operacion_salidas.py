"""HU-F1.7 / REQ-OPS-042..052 -- schemas unit tests for the salida payload
and response shapes.

Pattern: pure Pydantic v2 validation, no HTTP, no DB. Mirrors the F1.6
``test_schemas_ingreso.py`` precedent (DEC-SUC-21-NEW + DEC-FORZADO-01
defense in depth).
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from pydantic import ValidationError
from parkos_core.schemas.operacion import (
    IngresoNoEncontradoError,
    PlacaNoCoincideConIngresoError,
    SalidaCreateForzado,
    SalidaDuplicadaError,
    SalidaReadForzado,
    TarifaVigenteNoEncontradaSalidaError,
)


def test_salida_create_forzado_acepta_uuid_ingreso_minimo() -> None:
    """T1 (GREEN): minimal payload is accepted."""
    payload = SalidaCreateForzado(uuid_ingreso=uuid_lib.uuid4())
    assert payload.uuid_ingreso is not None
    assert payload.placa is None
    assert payload.observaciones is None
    assert payload.forzado is False


def test_salida_create_forzado_rechaza_tipo_salida_injection() -> None:
    """T2 (RED -> GREEN): extra='forbid' rejects ``tipo_salida`` injection.

    DEC-SUC-21-NEW: ``tipo_salida`` is a server-derived value (NEVER a
    column in ``prod.salidas``). A client attempting to inject the
    field must be rejected with ``ValidationError`` BEFORE the handler
    runs.
    """
    with pytest.raises(ValidationError) as ei:
        SalidaCreateForzado.model_validate(
            {"uuid_ingreso": str(uuid_lib.uuid4()), "tipo_salida": "ROTACION"}
        )
    assert "tipo_salida" in str(ei.value)


def test_salida_create_forzado_rechaza_cotizacion_snapshot_injection() -> None:
    """T3 (RED -> GREEN): extra='forbid' rejects ``cotizacion_snapshot``
    injection (DEC-SUC-23 + DEC-SUC-21-NEW defense).
    """
    with pytest.raises(ValidationError) as ei:
        SalidaCreateForzado.model_validate(
            {
                "uuid_ingreso": str(uuid_lib.uuid4()),
                "cotizacion_snapshot": {"cobrar": True},
            }
        )
    assert "cotizacion_snapshot" in str(ei.value)


def test_salida_read_forzado_default_fields() -> None:
    """T4 (GREEN): minimal read accepts defaults for F1.7 new fields."""
    uuid = uuid_lib.uuid4()
    payload = SalidaReadForzado.model_validate(
        {
            "uuid": str(uuid),
            "created_at": "2026-09-14T12:00:00",
            "created_by": None,
            "sync_status": None,
            "sync_timestamp": None,
            "sync_attempts": None,
            "uuid_sucursal": None,
            "uuid_ingreso": str(uuid_lib.uuid4()),
            "fecha_salida": "2026-09-14T12:00:00",
            "tipo_salida": "ROTACION",
            # Defaults: forzado_en_creacion=False, motivo_forzado=None,
            # cotizacion_snapshot=None
        }
    )
    assert payload.tipo_salida == "ROTACION"
    assert payload.forzado_en_creacion is False
    assert payload.motivo_forzado is None
    assert payload.cotizacion_snapshot is None


def test_salida_read_forzado_tipo_salida_literal_validation() -> None:
    """T5 (RED -> GREEN): ``tipo_salida`` Literal discriminator rejects
    unknown values (Pydantic v2 typed contract).
    """
    with pytest.raises(ValidationError):
        SalidaReadForzado.model_validate(
            {
                "uuid": str(uuid_lib.uuid4()),
                "created_at": "2026-09-14T12:00:00",
                "uuid_ingreso": str(uuid_lib.uuid4()),
                "fecha_salida": "2026-09-14T12:00:00",
                "tipo_salida": "INVALID",
            }
        )


def test_ingreso_no_encontrado_error_discriminator() -> None:
    """T6: V1 404 discriminator typed shape."""
    uuid = uuid_lib.uuid4()
    err = IngresoNoEncontradoError(uuid_ingreso=uuid)
    assert err.error == "ingreso_no_encontrado"
    assert err.uuid_ingreso == uuid


def test_salida_duplicada_error_discriminator() -> None:
    """T7: 409 partial unique index discriminator typed shape."""
    uuid = uuid_lib.uuid4()
    err = SalidaDuplicadaError(uuid_ingreso=uuid)
    assert err.error == "salida_duplicada"
    assert err.uuid_ingreso == uuid


def test_placa_no_coincide_error_discriminator() -> None:
    """T8: V3 422 discriminator typed shape."""
    err = PlacaNoCoincideConIngresoError(
        placa_request="ABC12D", placa_ingreso="ABC123"
    )
    assert err.error == "placa_no_coincide_con_ingreso"
    assert err.placa_request == "ABC12D"
    assert err.placa_ingreso == "ABC123"


def test_tarifa_vigente_no_encontrada_error_discriminator() -> None:
    """T9: V5 422 discriminator typed shape."""
    err = TarifaVigenteNoEncontradaSalidaError()
    assert err.error == "tarifa_vigente_no_encontrada"


def test_typed_error_rejects_wrong_literal() -> None:
    """T10: Literal discriminator enforcement on typed errors."""
    with pytest.raises(ValidationError):
        IngresoNoEncontradoError.model_validate(
            {"error": "wrong_value", "uuid_ingreso": str(uuid_lib.uuid4())}
        )


__all__ = [
    "test_salida_create_forzado_acepta_uuid_ingreso_minimo",
    "test_salida_create_forzado_rechaza_tipo_salida_injection",
    "test_salida_create_forzado_rechaza_cotizacion_snapshot_injection",
    "test_salida_read_forzado_default_fields",
    "test_salida_read_forzado_tipo_salida_literal_validation",
    "test_ingreso_no_encontrado_error_discriminator",
    "test_salida_duplicada_error_discriminator",
    "test_placa_no_coincide_error_discriminator",
    "test_tarifa_vigente_no_encontrada_error_discriminator",
    "test_typed_error_rejects_wrong_literal",
]
