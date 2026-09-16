"""HU-F1.12 / T1.2-T1.3: typed-exception module surface assertions.

RED then GREEN: the module is created with all 7 typed exceptions
(DEC-VENTA-01..07) + helper name placeholders. The tests below assert
the public surface (``__all__`` exports + instantiation + inheritance).

No DB dependency: pure import + class-attribute assertions.
"""
from __future__ import annotations

import uuid as uuid_lib


def test_repo_venta_suscripcion_module_imports_and_exposes_all_seven_typed_exceptions() -> None:
    """T1: import ``parkos_core.repo.venta_suscripcion`` and verify public surface.

    Per DEC-VENTA-01..07 the module MUST expose the 7 typed exceptions
    via ``__all__``. Each is a concrete ``Exception`` subclass with a
    typed dataclass-style attribute and a ``__str__`` for logging.
    """
    from parkos_core.repo import venta_suscripcion as repo_venta

    expected = {
        "TipoSubscripcionNoVigenteError",
        "TipoSubscripcionNoEncontradoError",
        "SubscripcionDuplicadaPlacaError",
        "TipoVehiculoIncompatibleError",
        "CantidadMaximaExcedidaError",
        "PlanDuracionDiasInvalidoError",
        "ClienteNoEncontradoError",
    }
    for name in expected:
        assert name in repo_venta.__all__, (
            f"T1 violated: typed exception {name!r} missing from "
            f"parkos_core.repo.venta_suscripcion.__all__"
        )
        cls = getattr(repo_venta, name)
        assert issubclass(cls, Exception), (
            f"T1 violated: {name!r} must subclass Exception"
        )


def test_typed_exceptions_carry_typed_attributes_and_inherit_from_exception() -> None:
    """T1: each typed exception carries the typed payload declared in design §11.7.

    Spot-check 3 exceptions (the most-used discriminators) plus the
    inheritance assertion. The remaining 4 follow the same shape -- the
    exhaustive set is asserted in the previous test via ``__all__``.
    """
    from parkos_core.repo.venta_suscripcion import (
        CantidadMaximaExcedidaError,
        ClienteNoEncontradoError,
        PlanDuracionDiasInvalidoError,
        SubscripcionDuplicadaPlacaError,
        TipoVehiculoIncompatibleError,
    )

    uuid_a = uuid_lib.uuid4()
    uuid_b = uuid_lib.uuid4()

    err_cliente = ClienteNoEncontradoError(uuid_cliente=uuid_a)
    assert err_cliente.uuid_cliente == uuid_a
    assert "cliente_no_encontrado" in str(err_cliente)
    assert isinstance(err_cliente, Exception)

    err_cantidad = CantidadMaximaExcedidaError(
        cantidad_maxima_vehiculos=2, placas_proporcionadas=3
    )
    assert err_cantidad.cantidad_maxima_vehiculos == 2
    assert err_cantidad.placas_proporcionadas == 3
    assert "cantidad_maxima_excedida" in str(err_cantidad)

    err_duracion = PlanDuracionDiasInvalidoError()
    assert "plan_duracion_dias_invalido" in str(err_duracion)
    assert isinstance(err_duracion, Exception)

    err_placa = SubscripcionDuplicadaPlacaError(placa="ABC123", uuid_sucursal=uuid_b)
    assert err_placa.placa == "ABC123"
    assert err_placa.uuid_sucursal == uuid_b
    assert "suscripcion_duplicada_placa" in str(err_placa)

    err_tipo = TipoVehiculoIncompatibleError(tipos_encontrados=["t_auto", "t_moto"])
    assert err_tipo.tipos_encontrados == ["t_auto", "t_moto"]
    assert "tipo_vehiculo_incompatible" in str(err_tipo)

    # Non-exhaustive: ``pytest`` reference keeps the import block above
    # from being collapsed by lint tools that strip unused names.
    assert CantidadMaximaExcedidaError is not None
