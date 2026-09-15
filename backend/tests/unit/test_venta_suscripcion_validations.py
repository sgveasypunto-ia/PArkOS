"""HU-F1.12 / T4: validation + prorrateo + INSERT unit tests.

Pure logic + mock-based tests for V4 + V5 + V6 + V7 + V9a + V9b.

* V5 ``validar_placas_mismo_tipo_vehiculo``: in-process same-tipo check.
* V6 ``validar_cantidad_maxima_vehiculos``: in-process count check.
* V7 ``calcular_prorrateo``: pure Decimal math + ZeroDivisionError catch.
* V4 ``validar_placa_duplicada_subscripcion``: reuses F1.7
  ``resolve_active_subscription_for_exit`` (mocked).
* V9a ``crear_subscripcion_cliente``: delegates to close_and_insert with
  the right new_attrs.
* V9b ``crear_subscripcion_vehiculos_bulk``: emits pg_advisory_xact_lock
  + adds one SubscripcionVehiculos row per UUID.

Pattern: F1.10 + F1.11 mock-everything (no live DB required).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402,I001


# ---------------------------------------------------------------------------
# V5 -- validar_placas_mismo_tipo_vehiculo
# ---------------------------------------------------------------------------


def _make_plan(*, mismo_tipo_vehiculo: bool) -> MagicMock:
    plan = MagicMock()
    plan.mismo_tipo_vehiculo = mismo_tipo_vehiculo
    return plan


def _make_vehiculo(*, uuid_tipo_vehiculo: uuid_lib.UUID) -> MagicMock:
    v = MagicMock()
    v.uuid_tipo_vehiculo = uuid_tipo_vehiculo
    return v


def test_validar_placas_mismo_tipo_vehiculo_ok_same_tipo() -> None:
    """V5 T1: plan.mismo_tipo_vehiculo=True, all vehiculos same tipo -> OK."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan(mismo_tipo_vehiculo=True)
    tipo = uuid_lib.uuid4()
    vehiculos = [_make_vehiculo(uuid_tipo_vehiculo=tipo), _make_vehiculo(uuid_tipo_vehiculo=tipo)]

    repo_venta.validar_placas_mismo_tipo_vehiculo(plan=plan, vehiculos=vehiculos)


def test_validar_placas_mismo_tipo_vehiculo_rechaza_distintos_tipos() -> None:
    """V5 T2: plan.mismo_tipo_vehiculo=True, mixed tipos -> raise 422."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan(mismo_tipo_vehiculo=True)
    tipo_a = uuid_lib.uuid4()
    tipo_b = uuid_lib.uuid4()
    vehiculos = [
        _make_vehiculo(uuid_tipo_vehiculo=tipo_a),
        _make_vehiculo(uuid_tipo_vehiculo=tipo_b),
    ]

    with pytest.raises(repo_venta.TipoVehiculoIncompatibleError) as excinfo:
        repo_venta.validar_placas_mismo_tipo_vehiculo(plan=plan, vehiculos=vehiculos)
    # DEC-VENTA-05: tipos_encontrados is a sorted list of strings
    assert excinfo.value.tipos_encontrados == sorted([str(tipo_a), str(tipo_b)])
    assert "tipo_vehiculo_incompatible" in str(excinfo.value)


def test_validar_placas_mismo_tipo_vehiculo_skipped_when_plan_mismo_tipo_false() -> None:
    """V5 T3: plan.mismo_tipo_vehiculo=False -> SKIPPED (heterogeneous OK)."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan(mismo_tipo_vehiculo=False)
    vehiculos = [
        _make_vehiculo(uuid_tipo_vehiculo=uuid_lib.uuid4()),
        _make_vehiculo(uuid_tipo_vehiculo=uuid_lib.uuid4()),
    ]
    # Should not raise even though tipos differ.
    repo_venta.validar_placas_mismo_tipo_vehiculo(plan=plan, vehiculos=vehiculos)


# ---------------------------------------------------------------------------
# V6 -- validar_cantidad_maxima_vehiculos
# ---------------------------------------------------------------------------


def test_validar_cantidad_maxima_vehiculos_ok_when_within_limit() -> None:
    """V6 T1: plan allows 2, n_placas=2 -> OK."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = MagicMock()
    plan.cantidad_maxima_vehiculos = 2
    repo_venta.validar_cantidad_maxima_vehiculos(plan=plan, n_placas=2)


def test_validar_cantidad_maxima_vehiculos_raises_when_exceeded() -> None:
    """V6 T2: plan allows 1, n_placas=2 -> raises CantidadMaximaExcedidaError."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = MagicMock()
    plan.cantidad_maxima_vehiculos = 1

    with pytest.raises(repo_venta.CantidadMaximaExcedidaError) as excinfo:
        repo_venta.validar_cantidad_maxima_vehiculos(plan=plan, n_placas=2)
    assert excinfo.value.cantidad_maxima_vehiculos == 1
    assert excinfo.value.placas_proporcionadas == 2
    assert "cantidad_maxima_excedida" in str(excinfo.value)


def test_validar_cantidad_maxima_vehiculos_ok_when_limit_none() -> None:
    """V6 edge: plan.cantidad_maxima_vehiculos=None (unbounded) -> OK."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = MagicMock()
    plan.cantidad_maxima_vehiculos = None
    repo_venta.validar_cantidad_maxima_vehiculos(plan=plan, n_placas=10)


# ---------------------------------------------------------------------------
# V7 -- calcular_prorrateo (pure Decimal math)
# ---------------------------------------------------------------------------


def _make_plan_for_prorrateo(*, valor: float, duracion_dias: int) -> MagicMock:
    plan = MagicMock()
    plan.valor = valor
    plan.duracion_dias = duracion_dias
    return plan


def test_calcular_prorrateo_after_day_15_returns_proportional() -> None:
    """V7 T1: day > 15 -> (valor/duracion) * (dias_en_mes - day)."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_prorrateo(valor=30000, duracion_dias=30)
    fecha = date(2026, 9, 20)  # day=20; September has 30 days; dias_restantes=10
    # 30000 / 30 * 10 = 10000.00
    result = repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=fecha)
    assert result == Decimal("10000.00")


def test_calcular_prorrateo_before_day_15_returns_full_value() -> None:
    """V7 T2: day <= 15 -> full plan.valor."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_prorrateo(valor=30000, duracion_dias=30)
    fecha = date(2026, 9, 10)  # day=10 -> full
    result = repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=fecha)
    assert result == Decimal("30000.00")


def test_calcular_prorrateo_zero_duracion_raises() -> None:
    """V7 T3: plan.duracion_dias=0 -> ZeroDivisionError -> PlanDuracionDiasInvalidoError."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_prorrateo(valor=30000, duracion_dias=0)
    with pytest.raises(repo_venta.PlanDuracionDiasInvalidoError) as excinfo:
        repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=date(2026, 9, 20))
    assert "plan_duracion_dias_invalido" in str(excinfo.value)


def test_calcular_prorrateo_boundary_day_15_returns_full() -> None:
    """V7 edge: day == 15 boundary (inclusive) returns full."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_prorrateo(valor=30000, duracion_dias=30)
    fecha = date(2026, 9, 15)
    result = repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=fecha)
    assert result == Decimal("30000.00")


# ---------------------------------------------------------------------------
# V4 -- validar_placa_duplicada_subscripcion (reuses F1.7 helper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validar_placa_duplicada_subscripcion_raises_when_active_found() -> None:
    """V4 T1: existing active sub for placa -> raises SubscripcionDuplicadaPlacaError."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()

    class _FakeResult:
        found = True

    async def fake_resolve(*_args: object, **_kwargs: object) -> _FakeResult:
        return _FakeResult()

    # Patch the SOURCE module -- the import is inside the function so
    # the helper module's binding is updated by the patch.
    with patch(
        "parkos_core.repo.subscripcion_activa.resolve_active_subscription_for_exit",
        new=fake_resolve,
    ):
        with pytest.raises(repo_venta.SubscripcionDuplicadaPlacaError) as excinfo:
            await repo_venta.validar_placa_duplicada_subscripcion(
                session,
                placa="ABC123",
                uuid_sucursal=uuid_lib.uuid4(),
                fecha_inicio_cobertura=date(2026, 9, 20),
            )
        assert excinfo.value.placa == "ABC123"
        assert "suscripcion_duplicada_placa" in str(excinfo.value)


@pytest.mark.asyncio
async def test_validar_placa_duplicada_subscripcion_ok_when_no_active() -> None:
    """V4 edge: no active sub -> no raise."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()

    class _FakeResult:
        found = False

    async def fake_resolve(*_args: object, **_kwargs: object) -> _FakeResult:
        return _FakeResult()

    with patch(
        "parkos_core.repo.subscripcion_activa.resolve_active_subscription_for_exit",
        new=fake_resolve,
    ):
        # Should NOT raise.
        await repo_venta.validar_placa_duplicada_subscripcion(
            session,
            placa="XYZ999",
            uuid_sucursal=uuid_lib.uuid4(),
            fecha_inicio_cobertura=date(2026, 9, 20),
        )


# ---------------------------------------------------------------------------
# V9a -- crear_subscripcion_cliente (delegates to close_and_insert)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crear_subscripcion_cliente_delegates_to_close_and_insert() -> None:
    """V9a: helper delegates to versioned.close_and_insert with the right new_attrs."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    new_row = MagicMock()
    actor = uuid_lib.uuid4()
    uuid_cliente = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    uuid_tipo = uuid_lib.uuid4()

    with patch.object(
        repo_venta.versioned, "close_and_insert", new=AsyncMock(return_value=new_row)
    ) as mock_cai:
        result = await repo_venta.crear_subscripcion_cliente(
            session,
            actor_uuid=actor,
            uuid_cliente=uuid_cliente,
            uuid_sucursal=uuid_sucursal,
            uuid_tipo_subscripcion=uuid_tipo,
            fecha_inicio_cobertura=date(2026, 9, 20),
            fecha_vencimiento=date(2026, 10, 20),
        )
    assert result is new_row
    args, kwargs = mock_cai.call_args
    assert args[0] is session
    assert args[1] is repo_venta.SubscripcionesCliente
    assert kwargs["current_uuid"] is None
    assert kwargs["actor_uuid"] == actor
    assert kwargs["new_attrs"]["uuid_cliente"] == uuid_cliente
    assert kwargs["new_attrs"]["uuid_sucursal"] == uuid_sucursal
    assert kwargs["new_attrs"]["uuid_tipo_subscripcion"] == uuid_tipo
    assert kwargs["new_attrs"]["fecha_inicio_cobertura"] == date(2026, 9, 20)
    assert kwargs["new_attrs"]["fecha_vencimiento"] == date(2026, 10, 20)


# ---------------------------------------------------------------------------
# V9b -- crear_subscripcion_vehiculos_bulk (advisory lock + bulk INSERT)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculos_bulk_advisory_lock_and_bulk_insert() -> None:
    """V9b: pg_advisory_xact_lock emitted + one SubscripcionVehiculos row per UUID."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # ``session.execute`` must be AsyncMock so ``await session.execute(...)`` works.
    session.execute = AsyncMock()

    actor = uuid_lib.uuid4()
    uuid_sub = uuid_lib.uuid4()
    v1 = uuid_lib.uuid4()
    v2 = uuid_lib.uuid4()

    rows = await repo_venta.crear_subscripcion_vehiculos_bulk(
        session,
        actor_uuid=actor,
        uuid_subscripcion_cliente=uuid_sub,
        uuid_vehiculos=[v1, v2],
    )

    # First call: pg_advisory_xact_lock(text(...), {"k": ...}) -> positional
    # text + dict-of-bind-params; kwargs is empty.
    assert session.execute.await_count == 1
    args, _kwargs = session.execute.await_args
    assert len(args) >= 2
    assert "pg_advisory_xact_lock" in str(args[0])
    bind_params = args[1]
    assert bind_params["k"] == repo_venta.uuid_to_int64(uuid_sub)

    # session.add called twice (one per vehiculo)
    assert session.add.call_count == 2
    assert session.flush.await_count == 1
    assert len(rows) == 2
    assert rows[0].uuid_subscripcion_cliente == uuid_sub
    assert rows[0].uuid_vehiculo == v1
    assert rows[1].uuid_vehiculo == v2
    assert rows[0].estado == "activo"
    assert rows[0].vigente_hasta is None
