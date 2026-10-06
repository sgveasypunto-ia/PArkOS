"""HU-F1.13 / T2.5 -- Pydantic schemas for caja arqueo.

Pure Pydantic v2 validation tests, no HTTP, no DB. The schemas inherit
``extra='forbid'`` from :class:`schemas.common._Base` (Layer 4 defense).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


def _uuid() -> uuid_lib.UUID:
    return uuid_lib.uuid4()


# ---------------------------------------------------------------------------
# ArqueoCreateV2 -- POST /api/v1/caja/arqueo payload
# ---------------------------------------------------------------------------


def test_arqueo_create_v2_accepts_valid_payload_with_sesion() -> None:
    """T2.5: valid payload with uuid_sesion + Decimal amounts + justificacion."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    payload = ArqueoCreateV2(
        uuid_tipo_arqueo=_uuid(),
        uuid_sesion=_uuid(),
        valor_efectivo_reportado=Decimal("148000"),
        valor_datafono_reportado=Decimal("320000"),
        justificacion="OK",
    )
    assert payload.valor_efectivo_reportado == Decimal("148000")
    assert payload.uuid_sesion is not None


def test_arqueo_create_v2_accepts_null_datafono() -> None:
    """REQ-OPS-191 Scenario 2: legacy client omits the field (None default applied)."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    payload = ArqueoCreateV2(
        uuid_tipo_arqueo=_uuid(),
        uuid_sesion=_uuid(),
        valor_efectivo_reportado=Decimal("148000"),
        # valor_datafono_reportado omitted entirely
    )
    assert payload.valor_datafono_reportado is None


def test_arqueo_create_v2_accepts_explicit_null_datafono() -> None:
    """REQ-OPS-191 Scenario 3: legacy client sends ``null`` -- accepted."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    payload = ArqueoCreateV2(
        uuid_tipo_arqueo=_uuid(),
        uuid_sesion=_uuid(),
        valor_efectivo_reportado=Decimal("148000"),
        valor_datafono_reportado=None,
    )
    assert payload.valor_datafono_reportado is None


def test_arqueo_create_v2_accepts_legacy_datafono_decimal() -> None:
    """REQ-OPS-191 Scenario 1: legacy client sends ``Decimal`` -- accepted (handler ignores)."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    payload = ArqueoCreateV2(
        uuid_tipo_arqueo=_uuid(),
        uuid_sesion=_uuid(),
        valor_efectivo_reportado=Decimal("148000"),
        valor_datafono_reportado=Decimal("320000"),  # legacy kiosk compat
    )
    assert payload.valor_datafono_reportado == Decimal("320000")


def test_arqueo_create_v2_accepts_uuid_sesion_null_for_cierre_dia() -> None:
    """T2.5: valid payload with uuid_sesion=None (cierre_dia codigo)."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    payload = ArqueoCreateV2(
        uuid_tipo_arqueo=_uuid(),
        uuid_sesion=None,
        valor_efectivo_reportado=Decimal("500000"),
        valor_datafono_reportado=Decimal("800000"),
    )
    assert payload.uuid_sesion is None


def test_arqueo_create_v2_rejects_uuid_usuario_injection() -> None:
    """Layer 4: ``extra='forbid'`` blocks client smuggling of uuid_usuario."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    with pytest.raises(Exception) as exc_info:
        ArqueoCreateV2(
            uuid_tipo_arqueo=_uuid(),
            uuid_sesion=_uuid(),
            valor_efectivo_reportado=Decimal("148000"),
            valor_datafono_reportado=Decimal("320000"),
            uuid_usuario=_uuid(),  # NOT in the schema
        )
    assert "uuid_usuario" in str(exc_info.value) or "extra" in str(exc_info.value).lower()


def test_arqueo_create_v2_rejects_alerta_generada_injection() -> None:
    """Layer 4: ``extra='forbid'`` blocks client smuggling of alerta_generada."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    with pytest.raises(Exception) as exc_info:
        ArqueoCreateV2(
            uuid_tipo_arqueo=_uuid(),
            uuid_sesion=_uuid(),
            valor_efectivo_reportado=Decimal("148000"),
            valor_datafono_reportado=Decimal("320000"),
            alerta_generada=True,  # NOT in the schema
        )
    assert "alerta_generada" in str(exc_info.value) or "extra" in str(exc_info.value).lower()


def test_arqueo_create_v2_rejects_created_at_injection() -> None:
    """Layer 4: ``extra='forbid'`` blocks created_at smuggling."""
    from parkos_core.schemas.caja import ArqueoCreateV2

    with pytest.raises(Exception) as exc_info:
        ArqueoCreateV2(
            uuid_tipo_arqueo=_uuid(),
            uuid_sesion=_uuid(),
            valor_efectivo_reportado=Decimal("148000"),
            valor_datafono_reportado=Decimal("320000"),
            created_at="2026-09-15T12:00:00",  # server-side only
        )
    assert "created_at" in str(exc_info.value) or "extra" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# ArqueoReadForHandler -- POST response (REQ-OPS-192: datafono fields REMOVED)
# ---------------------------------------------------------------------------


def test_arqueo_read_for_handler_accepts_alerta_generada_true() -> None:
    """REQ-OPS-192: datafono fields are REMOVED from the response shape."""
    from parkos_core.schemas.caja import ArqueoReadForHandler

    resp = ArqueoReadForHandler(
        uuid=_uuid(),
        uuid_tipo_arqueo=_uuid(),
        codigo_tipo_arqueo="cierre_turno",
        uuid_sesion=_uuid(),
        valor_efectivo_esperado=Decimal("148000"),
        valor_efectivo_reportado=Decimal("148150"),
        diferencia_efectivo=Decimal("150"),
        descuadre_pct=Decimal("0.03"),
        alerta_generada=True,
        alerta_uuid=_uuid(),
    )
    assert resp.alerta_generada is True
    assert resp.codigo_tipo_arqueo == "cierre_turno"


def test_arqueo_read_for_handler_alerta_uuid_can_be_null() -> None:
    """REQ-OPS-192: datafono fields absent from the response (auditoria path)."""
    from parkos_core.schemas.caja import ArqueoReadForHandler

    resp = ArqueoReadForHandler(
        uuid=_uuid(),
        uuid_tipo_arqueo=_uuid(),
        codigo_tipo_arqueo="auditoria",
        uuid_sesion=_uuid(),
        valor_efectivo_esperado=Decimal("100"),
        valor_efectivo_reportado=Decimal("100"),
        diferencia_efectivo=Decimal("0"),
        descuadre_pct=None,
        alerta_generada=False,
        alerta_uuid=None,
    )
    assert resp.alerta_generada is False
    assert resp.alerta_uuid is None


def test_arqueo_read_for_handler_excludes_datafono_fields() -> None:
    """REQ-OPS-192 / D3 regression guard: passing datafono kwargs MUST
    raise ValidationError (the fields are REMOVED, not nullable)."""
    from parkos_core.schemas.caja import ArqueoReadForHandler
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ArqueoReadForHandler(
            uuid=_uuid(),
            uuid_tipo_arqueo=_uuid(),
            codigo_tipo_arqueo="cierre_turno",
            uuid_sesion=_uuid(),
            valor_efectivo_esperado=Decimal("148000"),
            valor_efectivo_reportado=Decimal("148150"),
            diferencia_efectivo=Decimal("150"),
            # REMOVED fields -- ``extra='forbid'`` rejects them.
            valor_datafono_esperado=Decimal("0"),  # type: ignore[call-arg]
            valor_datafono_reportado=Decimal("0"),  # type: ignore[call-arg]
            diferencia_datafono=Decimal("0"),  # type: ignore[call-arg]
            alerta_generada=False,
            alerta_uuid=None,
        )


# ---------------------------------------------------------------------------
# ArqueoResumenRead + CierreDiarioQueryParams
# ---------------------------------------------------------------------------


def test_arqueo_resumen_read_has_sesiones_and_cierre_dia_fields() -> None:
    from parkos_core.schemas.caja import ArqueoResumenRead

    r = ArqueoResumenRead(
        fecha=date(2026, 9, 15),
        uuid_sucursal=_uuid(),
        sesiones=[],
        cierre_dia=None,
    )
    assert r.sesiones == []
    assert r.cierre_dia is None


def test_cierre_diario_query_params_requires_uuid_sucursal_and_fecha() -> None:
    """Both fields required; missing either raises ValidationError."""
    from parkos_core.schemas.caja import CierreDiarioQueryParams

    with pytest.raises(Exception):
        CierreDiarioQueryParams(fecha=date(2026, 9, 15))  # missing uuid_sucursal

    with pytest.raises(Exception):
        CierreDiarioQueryParams(uuid_sucursal=_uuid())  # missing fecha

    # Both present succeeds.
    ok = CierreDiarioQueryParams(uuid_sucursal=_uuid(), fecha=date(2026, 9, 15))
    assert ok.fecha == date(2026, 9, 15)


def test_cierre_diario_query_params_rejects_extra_fields() -> None:
    from parkos_core.schemas.caja import CierreDiarioQueryParams

    with pytest.raises(Exception):
        CierreDiarioQueryParams(
            uuid_sucursal=_uuid(),
            fecha=date(2026, 9, 15),
            uuid_usuario=_uuid(),  # forbidden
        )


# ---------------------------------------------------------------------------
# Typed error schemas
# ---------------------------------------------------------------------------


def test_typed_error_tipo_arqueo_no_encontrado_carries_uuid() -> None:
    from parkos_core.schemas.caja import TipoArqueoNoEncontradoErrorRead

    u = _uuid()
    err = TipoArqueoNoEncontradoErrorRead(
        uuid_tipo_arqueo=u,
    )
    assert err.error == "tipo_arqueo_no_encontrado"
    assert err.uuid_tipo_arqueo == u


def test_typed_error_sesion_ya_cerrada_carries_uuid() -> None:
    from parkos_core.schemas.caja import SesionYaCerradaErrorRead

    u = _uuid()
    err = SesionYaCerradaErrorRead(uuid_sesion=u)
    assert err.error == "sesion_ya_cerrada"


def test_typed_error_justificacion_requerida_carries_no_context() -> None:
    from parkos_core.schemas.caja import JustificacionRequeridaErrorRead

    err = JustificacionRequeridaErrorRead()
    assert err.error == "justificacion_requerida"


# ---------------------------------------------------------------------------
# ArqueoDiferenciasResponse -- GET /arqueos/{uuid}/diferencias (REQ-OPS-192)
# ---------------------------------------------------------------------------


def test_arqueo_diferencias_response_excludes_datafono() -> None:
    """REQ-OPS-192: datafono fields are REMOVED from the diferencias response."""
    from parkos_core.api.v1.caja_sesion import ArqueoDiferenciasResponse
    from pydantic import ValidationError

    # Valid construction (no datafono fields).
    resp = ArqueoDiferenciasResponse(
        uuid_arqueo=_uuid(),
        valor_efectivo_esperado=148000.0,
        valor_efectivo_reportado=148050.0,
        diferencia_efectivo=50.0,
    )
    assert resp.diferencia_efectivo == 50.0

    # REMOVED fields -- ``extra='forbid'`` rejects them.
    with pytest.raises(ValidationError):
        ArqueoDiferenciasResponse(
            uuid_arqueo=_uuid(),
            valor_efectivo_esperado=148000.0,
            valor_efectivo_reportado=148050.0,
            diferencia_efectivo=50.0,
            valor_datafono_esperado=0.0,  # type: ignore[call-arg]
            valor_datafono_reportado=0.0,  # type: ignore[call-arg]
            diferencia_datafono=0.0,  # type: ignore[call-arg]
        )
