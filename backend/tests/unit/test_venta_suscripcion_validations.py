"""HU-F1.12 / T4: validation + prorrateo + INSERT unit tests.

Pure logic + mock-based tests for V4 + V5 + V6 + V7 + V9a + V9b.

* V5 ``validar_placas_mismo_tipo_vehiculo``: in-process same-tipo check.
* V6 ``validar_cantidad_maxima_vehiculos``: in-process count check.
* V7 ``calcular_monto_suscripcion`` / ``calcular_fecha_vencimiento`` (PT-3, no proration).
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
from datetime import date, timedelta
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
# V7 -- calcular_monto_suscripcion / calcular_fecha_vencimiento (PT-3)
# ---------------------------------------------------------------------------


def _make_plan_for_monto(*, valor: float, duracion_dias: int | None) -> MagicMock:
    plan = MagicMock()
    plan.valor = valor
    plan.duracion_dias = duracion_dias
    return plan


@pytest.mark.parametrize(("valor", "duracion"), [(60000, 30), (220000, 60), (320000, 90)])
def test_calcular_monto_suscripcion_always_full_plan_value(valor: int, duracion: int) -> None:
    """PT-3: the charge is the full plan price; it takes no start date at all.

    The old proration charged $0 on the last day of a month and a fraction
    after day 15; the signature (plan only) now rules that out.
    """
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_monto(valor=valor, duracion_dias=duracion)
    assert repo_venta.calcular_monto_suscripcion(plan=plan) == Decimal(f"{valor}.00")
    assert not hasattr(repo_venta, "calcular_prorrateo")


@pytest.mark.parametrize("duracion", [None, 0, -5])
def test_calcular_monto_suscripcion_invalid_duracion_raises(duracion: int | None) -> None:
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_monto(valor=30000, duracion_dias=duracion)
    with pytest.raises(repo_venta.PlanDuracionDiasInvalidoError) as excinfo:
        repo_venta.calcular_monto_suscripcion(plan=plan)
    assert "plan_duracion_dias_invalido" in str(excinfo.value)


@pytest.mark.parametrize(
    ("inicio", "duracion", "esperado"),
    [
        (date(2026, 9, 1), 30, date(2026, 9, 30)),  # 30 days from day 1 -> day 30
        (date(2026, 9, 20), 30, date(2026, 10, 19)),
        (date(2026, 9, 20), 60, date(2026, 11, 18)),
        (date(2026, 9, 20), 90, date(2026, 12, 18)),
        (date(2026, 9, 30), 30, date(2026, 10, 29)),  # last day of month
        (date(2026, 1, 31), 1, date(2026, 1, 31)),  # 1-day plan covers only the start day
        (date(2028, 1, 31), 30, date(2028, 2, 29)),  # leap year: Jan 31 + 29 = Feb 29
        (date(2028, 2, 1), 29, date(2028, 2, 29)),  # lands exactly on Feb 29
        (date(2028, 2, 29), 30, date(2028, 3, 29)),  # start on leap day
        (date(2027, 1, 31), 30, date(2027, 3, 1)),  # non-leap: Feb has 28 days
        (date(2026, 12, 31), 60, date(2027, 2, 28)),  # year rollover
    ],
)
def test_calcular_fecha_vencimiento_is_start_plus_duration_minus_one(
    inicio: date, duracion: int, esperado: date
) -> None:
    """PD-01: cycle = fecha_inicio_cobertura + duracion_dias - 1 (inclusive last day)."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_monto(valor=1, duracion_dias=duracion)
    assert (
        repo_venta.calcular_fecha_vencimiento(plan=plan, fecha_inicio_cobertura=inicio)
        == esperado
    )


def test_calcular_fecha_vencimiento_invalid_duracion_raises() -> None:
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_monto(valor=1, duracion_dias=0)
    with pytest.raises(repo_venta.PlanDuracionDiasInvalidoError):
        repo_venta.calcular_fecha_vencimiento(
            plan=plan, fecha_inicio_cobertura=date(2026, 9, 20)
        )


@pytest.mark.parametrize("duracion", [30, 60, 90])
@pytest.mark.parametrize("inicio", [date(2026, 9, 1), date(2026, 9, 30), date(2028, 2, 29)])
def test_vencimiento_semantics_covers_exactly_duration_calendar_days(
    inicio: date, duracion: int
) -> None:
    """PD-01: a plan of N days is valid for EXACTLY N calendar days.

    ``fecha_vencimiento`` is the last covered day and the validity predicates
    use ``fecha_vencimiento >= hoy`` (subscripcion_activa.py): counting the
    days from the start for which that predicate holds yields N.
    """
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan_for_monto(valor=1, duracion_dias=duracion)
    venc = repo_venta.calcular_fecha_vencimiento(plan=plan, fecha_inicio_cobertura=inicio)
    cubiertos = [
        d
        for d in (inicio + timedelta(days=i) for i in range(duracion + 10))
        if venc >= d
    ]
    assert len(cubiertos) == duracion
    assert venc + timedelta(days=1) not in cubiertos


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


# ---------------------------------------------------------------------------
# HU-F20.2 BR3/E1 (NEW) -- validar_vehiculo_sin_suscripcion_vigente_distinta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validar_vehiculo_sin_suscripcion_vigente_distinta_raises_when_found() -> None:
    """Another ACTIVE subscripcion already covers this vehiculo -> raise."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = uuid_lib.uuid4()  # a matching row uuid
    session.execute = AsyncMock(return_value=result)

    uuid_vehiculo = uuid_lib.uuid4()
    with pytest.raises(repo_venta.PlacaConSuscripcionVigenteError) as excinfo:
        await repo_venta.validar_vehiculo_sin_suscripcion_vigente_distinta(
            session,
            uuid_vehiculo=uuid_vehiculo,
            excluir_uuid_subscripcion_cliente=uuid_lib.uuid4(),
        )
    assert excinfo.value.uuid_vehiculo == uuid_vehiculo
    assert "placa_con_suscripcion_vigente" in str(excinfo.value)


@pytest.mark.asyncio
async def test_validar_vehiculo_sin_suscripcion_vigente_distinta_ok_when_none_found() -> None:
    """No OTHER active subscripcion covers this vehiculo -> no raise."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    await repo_venta.validar_vehiculo_sin_suscripcion_vigente_distinta(
        session,
        uuid_vehiculo=uuid_lib.uuid4(),
        excluir_uuid_subscripcion_cliente=uuid_lib.uuid4(),
    )


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
