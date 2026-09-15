"""HU-F1.12 / T2.1 + T2.3: Pydantic schema tests for VentaSuscripcionCreate + Response.

11 tests covering:
* ``extra='forbid'`` blocks ``vigente_desde`` / ``estado`` / ``created_by`` /
  ``uuid_sucursal`` injection (4 tests, T2.1).
* ``model_validator`` XOR: both provided (1 test, T2.1).
* ``model_validator`` XOR: both absent (1 test, T2.1).
* ``placas`` 1-2 range: 0 rejected, 3 rejected, 1 OK, 2 OK (4 tests, T2.3).
* ``monto_prorrateado`` nullable when cobrar_ahora=False, Decimal OK
  when cobrar_ahora=True (2 tests, T2.3 + DEC-VENTA-03).

No DB dependency. Pure Pydantic v2 validation.

Pattern: F1.11 ``test_reimpresion_ticket_schemas.py`` -- direct schema
instantiation + ``pytest.raises(ValidationError)`` assertions.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError


def _build_cliente() -> dict:
    """Helper: minimal valid ``ClientesCreate`` for ``cliente`` XOR field."""
    return {
        "tipo_identificador": "CC",
        "numero_identificacion": "1234567890",
        "nombre": "Juan",
        "apellido": "Perez",
    }


def _minimal_create_kwargs(**overrides: object) -> dict:
    """Build a minimal valid ``VentaSuscripcionCreate`` kwargs dict.

    Defaults: ``uuid_cliente`` branch (no embedded ``cliente``) +
    1 placa + plan UUID + fecha_inicio_cobertura + cobrar_ahora=False.
    """
    base: dict = {
        "uuid_cliente": uuid_lib.uuid4(),
        "placas": ["ABC123"],
        "uuid_tipo_subscripcion": uuid_lib.uuid4(),
        "fecha_inicio_cobertura": date(2026, 9, 20),
        "cobrar_ahora": False,
        "emitir_factura_electronica": False,
        "medio_pago": "efectivo",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# T2.1 -- extra='forbid' blocks versioning + smuggling fields (4 tests)
# ---------------------------------------------------------------------------


def test_create_endpoint_rejects_vigente_desde_injection() -> None:
    """T2.1 T1: ``vigente_desde`` smuggling blocked by ``extra='forbid'``."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(
            **_minimal_create_kwargs(vigente_desde="2026-09-01")  # type: ignore[arg-type]
        )
    assert "vigente_desde" in str(excinfo.value)


def test_create_endpoint_rejects_estado_injection() -> None:
    """T2.1 T2: ``estado`` smuggling blocked."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(
            **_minimal_create_kwargs(estado="activo")  # type: ignore[arg-type]
        )
    assert "estado" in str(excinfo.value)


def test_create_endpoint_rejects_created_by_injection() -> None:
    """T2.1 T3: ``created_by`` smuggling blocked."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(
            **_minimal_create_kwargs(created_by=str(uuid_lib.uuid4()))  # type: ignore[arg-type]
        )
    assert "created_by" in str(excinfo.value)


def test_create_endpoint_rejects_uuid_sucursal_injection() -> None:
    """T2.1 T4: ``uuid_sucursal`` smuggling blocked (server-set per TenantContext)."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(
            **_minimal_create_kwargs(uuid_sucursal=str(uuid_lib.uuid4()))  # type: ignore[arg-type]
        )
    assert "uuid_sucursal" in str(excinfo.value)


# ---------------------------------------------------------------------------
# T2.1 -- model_validator XOR (2 tests)
# ---------------------------------------------------------------------------


def test_create_endpoint_rejects_cliente_and_uuid_cliente_both_provided() -> None:
    """T2.1 T5: both ``cliente`` and ``uuid_cliente`` populated -> ValidationError."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(
            **_minimal_create_kwargs(
                cliente=_build_cliente(),  # type: ignore[arg-type]
                uuid_cliente=uuid_lib.uuid4(),
            )
        )
    assert "exactly one of cliente or uuid_cliente" in str(excinfo.value)


def test_create_endpoint_rejects_cliente_and_uuid_cliente_both_absent() -> None:
    """T2.1 T6: both ``cliente`` and ``uuid_cliente`` None -> ValidationError."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(
            **_minimal_create_kwargs(
                uuid_cliente=None,  # type: ignore[arg-type]
            )
        )
    assert "exactly one of cliente or uuid_cliente" in str(excinfo.value)


# ---------------------------------------------------------------------------
# T2.3 -- placas list 1-2 range (3 tests)
# ---------------------------------------------------------------------------


def test_create_endpoint_rejects_placas_count_0() -> None:
    """T2.3 T1: ``placas=[]`` rejected by ``min_length=1``."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(**_minimal_create_kwargs(placas=[]))
    assert "placas" in str(excinfo.value).lower() or "list" in str(excinfo.value).lower()


def test_create_endpoint_rejects_placas_count_3() -> None:
    """T2.3 T2: ``placas=[3 items]`` rejected by ``max_length=2``."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError) as excinfo:
        VentaSuscripcionCreate(
            **_minimal_create_kwargs(placas=["ABC123", "DEF456", "GHI789"])
        )
    assert "placas" in str(excinfo.value).lower() or "list" in str(excinfo.value).lower()


def test_create_endpoint_accepts_placas_count_1_and_2() -> None:
    """T2.3 T3: 1 placa and 2 placas both valid (boundary check)."""
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    one = VentaSuscripcionCreate(**_minimal_create_kwargs(placas=["ABC123"]))
    assert one.placas == ["ABC123"]

    two = VentaSuscripcionCreate(
        **_minimal_create_kwargs(placas=["ABC123", "DEF456"])
    )
    assert two.placas == ["ABC123", "DEF456"]


# ---------------------------------------------------------------------------
# T2.3 -- Response schema (DEC-VENTA-03: monto_prorrateado nullable)
# ---------------------------------------------------------------------------


def test_response_monto_prorrateado_null_when_cobrar_ahora_false() -> None:
    """T2.3 T4: VentaSuscripcionResponse accepts ``monto_prorrateado=None`` (DEC-VENTA-03)."""
    from parkos_core.schemas.clientes import VentaSuscripcionResponse

    resp = VentaSuscripcionResponse(
        uuid_cliente=uuid_lib.uuid4(),
        uuid_subscripcion=uuid_lib.uuid4(),
        uuid_vehiculos=[uuid_lib.uuid4()],
        uuid_sucursal=uuid_lib.uuid4(),
        fecha_inicio_cobertura=date(2026, 9, 20),
        fecha_vencimiento=date(2026, 10, 20),
        valor_total_plan=Decimal("30000.00"),
        monto_prorrateado=None,
    )
    assert resp.monto_prorrateado is None
    assert resp.uuid_factura is None
    assert resp.uuid_factura_electronica is None
    assert resp.uuid_envio_dian is None


def test_response_monto_prorrateado_decimal_when_cobrar_ahora_true() -> None:
    """T2.3 T5: VentaSuscripcionResponse accepts Decimal monto_prorrateado."""
    from parkos_core.schemas.clientes import VentaSuscripcionResponse

    uuid_fact = uuid_lib.uuid4()
    resp = VentaSuscripcionResponse(
        uuid_cliente=uuid_lib.uuid4(),
        uuid_subscripcion=uuid_lib.uuid4(),
        uuid_vehiculos=[uuid_lib.uuid4(), uuid_lib.uuid4()],
        uuid_sucursal=uuid_lib.uuid4(),
        fecha_inicio_cobertura=date(2026, 9, 20),
        fecha_vencimiento=date(2026, 10, 20),
        valor_total_plan=Decimal("30000.00"),
        monto_prorrateado=Decimal("10000.00"),
        uuid_factura=uuid_fact,
    )
    assert resp.monto_prorrateado == Decimal("10000.00")
    assert resp.uuid_factura == uuid_fact
    assert len(resp.uuid_vehiculos) == 2
