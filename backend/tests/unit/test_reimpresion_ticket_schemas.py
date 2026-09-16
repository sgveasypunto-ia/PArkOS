"""HU-F1.11 / T3.1 + T3.3 — Pydantic v2 schema validation.

Pure-Pydantic tests (no DB, no HTTP). Verifies:

* T3.1 — ``ReimpresionTicketCreateEndpoint`` + ``ReimpresionTicketAnularEndpoint``
  enforce ``motivo`` / ``motivo_anulacion`` length contract
  (``min_length=10, max_length=500`` per DEC-TKT-06) and reject extra
  fields via ``extra='forbid'`` (inherited from ``_Base``).

* T3.3 — 5 typed error schemas (``ReimpresionAlreadyPendingError``,
  ``AnulacionNoPermitidaError``, ``ReimpresionNotFoundError``,
  ``IngresoNoEncontradoError``, ``FacturaNoEncontradaReimpresionError``)
  pin the discriminator ``Literal`` values that the API handlers map
  to HTTP status codes.

These tests are pure-Python and run without any DB / Docker fixture;
they exercise the Layer-1 (Pydantic) defense in front of the handlers.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path

import pytest
from pydantic import ValidationError

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# ---------------------------------------------------------------------------
# T3.1 — endpoint payload schemas
# ---------------------------------------------------------------------------


def test_create_endpoint_rejects_motivo_below_10_chars() -> None:
    """Pydantic ``min_length=10`` rejects motivo shorter than 10 chars."""
    from parkos_core.schemas.workflows import ReimpresionTicketCreateEndpoint

    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketCreateEndpoint(
            motivo="abc",  # 3 chars
            uuid_ingreso=uuid_lib.uuid4(),
        )
    # The rejected field is motivo
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("motivo",) for e in errors), (
        f"expected ValidationError on motivo, got: {errors}"
    )


def test_create_endpoint_accepts_motivo_at_min_length_10() -> None:
    """Pydantic accepts motivo at exactly the 10-char boundary."""
    from parkos_core.schemas.workflows import ReimpresionTicketCreateEndpoint

    payload = ReimpresionTicketCreateEndpoint(
        motivo="1234567890",  # exactly 10 chars
        uuid_ingreso=uuid_lib.uuid4(),
    )
    assert payload.motivo == "1234567890"
    assert isinstance(payload.uuid_ingreso, uuid_lib.UUID)


def test_create_endpoint_rejects_estado_injection_via_extra_forbid() -> None:
    """``extra='forbid'`` rejects client smuggling of server-set fields."""
    from parkos_core.schemas.workflows import ReimpresionTicketCreateEndpoint

    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketCreateEndpoint(
            motivo="Cliente solicita reimpresion por deterioro",
            uuid_ingreso=uuid_lib.uuid4(),
            uuid_factura=None,
            estado="autorizada",  # client smuggling attempt
        )
    errors = exc_info.value.errors()
    assert any("estado" in (e["loc"] or ()) for e in errors), (
        f"expected ValidationError on 'estado' extra field, got: {errors}"
    )


def test_create_endpoint_accepts_uuid_factura_null() -> None:
    """DEC-TKT-04: ``uuid_factura: null`` is valid (DEC-TKT-04 optional)."""
    from parkos_core.schemas.workflows import ReimpresionTicketCreateEndpoint

    payload = ReimpresionTicketCreateEndpoint(
        motivo="Cliente solicita reimpresion sin factura",
        uuid_ingreso=uuid_lib.uuid4(),
        uuid_factura=None,
    )
    assert payload.uuid_factura is None


def test_create_endpoint_rejects_motivo_above_500_chars() -> None:
    """``max_length=500`` rejects motivo longer than 500 chars (audit cap)."""
    from parkos_core.schemas.workflows import ReimpresionTicketCreateEndpoint

    too_long = "x" * 501
    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketCreateEndpoint(
            motivo=too_long,
            uuid_ingreso=uuid_lib.uuid4(),
        )
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("motivo",) for e in errors), (
        f"expected ValidationError on motivo length, got: {errors}"
    )


def test_anular_endpoint_rejects_motivo_anulacion_below_10_chars() -> None:
    """Pydantic ``min_length=10`` rejects motivo_anulacion < 10 chars."""
    from parkos_core.schemas.workflows import ReimpresionTicketAnularEndpoint

    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketAnularEndpoint(motivo_anulacion="abc")
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("motivo_anulacion",) for e in errors), (
        f"expected ValidationError on motivo_anulacion, got: {errors}"
    )


def test_anular_endpoint_rejects_state_injection_via_extra_forbid() -> None:
    """``extra='forbid'`` rejects estado / uuid_reimpresion_padre smuggling."""
    from parkos_core.schemas.workflows import ReimpresionTicketAnularEndpoint

    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketAnularEndpoint(
            motivo_anulacion="Error operativo: reimprimir solicitada por error administrativo",
            estado="rechazada",  # server-set, must not be client-supplied
        )
    errors = exc_info.value.errors()
    assert any("estado" in (e["loc"] or ()) for e in errors), (
        f"expected ValidationError on 'estado' extra field, got: {errors}"
    )


def test_anular_endpoint_accepts_motivo_anulacion_at_min_length() -> None:
    """Pydantic accepts motivo_anulacion at exactly 10 chars."""
    from parkos_core.schemas.workflows import ReimpresionTicketAnularEndpoint

    payload = ReimpresionTicketAnularEndpoint(motivo_anulacion="1234567890")
    assert payload.motivo_anulacion == "1234567890"


# ---------------------------------------------------------------------------
# T3.3 — typed error schemas
# ---------------------------------------------------------------------------


def test_reimpresion_already_pending_error_discriminator_literal() -> None:
    """REQ-OPS-077 V2: error discriminator is the closed Literal."""
    from parkos_core.schemas.workflows import ReimpresionAlreadyPendingError

    err = ReimpresionAlreadyPendingError.model_validate(
        {
            "error": "reimpresion_already_pending",
            "uuid_ingreso": str(uuid_lib.uuid4()),
            "uuid_reimpresion": str(uuid_lib.uuid4()),
        }
    )
    assert err.error == "reimpresion_already_pending"


def test_reimpresion_already_pending_error_rejects_wrong_discriminator() -> None:
    """The closed Literal rejects any other discriminator string."""
    from parkos_core.schemas.workflows import ReimpresionAlreadyPendingError

    with pytest.raises(ValidationError):
        ReimpresionAlreadyPendingError.model_validate(
            {
                "error": "wrong_discriminator",
                "uuid_ingreso": str(uuid_lib.uuid4()),
                "uuid_reimpresion": str(uuid_lib.uuid4()),
            }
        )


def test_anulacion_no_permitida_error_estado_actual_literal() -> None:
    """estado_actual is the closed Literal["rechazada"]."""
    from parkos_core.schemas.workflows import AnulacionNoPermitidaError

    err = AnulacionNoPermitidaError.model_validate(
        {
            "error": "anulacion_no_permitida",
            "uuid_reimpresion": str(uuid_lib.uuid4()),
            "estado_actual": "rechazada",
        }
    )
    assert err.estado_actual == "rechazada"


def test_anulacion_no_permitida_error_rejects_other_estado_actual() -> None:
    """estado_actual MUST be Literal["rechazada"], nothing else."""
    from parkos_core.schemas.workflows import AnulacionNoPermitidaError

    with pytest.raises(ValidationError):
        AnulacionNoPermitidaError.model_validate(
            {
                "error": "anulacion_no_permitida",
                "uuid_reimpresion": str(uuid_lib.uuid4()),
                "estado_actual": "autorizada",  # not allowed
            }
        )


def test_reimpresion_not_found_error_minimal() -> None:
    """Only ``error`` + ``uuid_reimpresion`` are required."""
    from parkos_core.schemas.workflows import ReimpresionNotFoundError

    err = ReimpresionNotFoundError.model_validate(
        {"error": "reimpresion_not_found", "uuid_reimpresion": str(uuid_lib.uuid4())}
    )
    assert err.error == "reimpresion_not_found"


def test_ingreso_no_encontrado_error_minimal() -> None:
    """Only ``error`` + ``uuid_ingreso`` are required."""
    from parkos_core.schemas.workflows import IngresoNoEncontradoError

    err = IngresoNoEncontradoError.model_validate(
        {"error": "ingreso_no_encontrado", "uuid_ingreso": str(uuid_lib.uuid4())}
    )
    assert err.error == "ingreso_no_encontrado"


def test_factura_no_encontrada_reimpresion_error_minimal() -> None:
    """Only ``error`` + ``uuid_factura`` are required."""
    from parkos_core.schemas.workflows import FacturaNoEncontradaReimpresionError

    err = FacturaNoEncontradaReimpresionError.model_validate(
        {"error": "factura_no_encontrada", "uuid_factura": str(uuid_lib.uuid4())}
    )
    assert err.error == "factura_no_encontrada"


def test_read_schema_extends_with_motivo_anulacion_and_workflow_estado() -> None:
    """DEC-TKT-04: ``ReimpresionTicketRead`` exposes motivo_anulacion +
    workflow_estado (server-derived)."""
    from parkos_core.schemas.workflows import ReimpresionTicketRead

    # Confirm both fields are declared on the schema
    assert "motivo_anulacion" in ReimpresionTicketRead.model_fields
    assert "workflow_estado" in ReimpresionTicketRead.model_fields
