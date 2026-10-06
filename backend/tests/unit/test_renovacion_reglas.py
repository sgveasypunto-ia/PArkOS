"""PT-3 -- pure date rules for subscription renewal (no DB).

Covers the window (11/10/1/0/expired), the start date (before / after / on
the due date), month end, leap year, plans of 30/60/90 days and the Bogota
midnight boundary.
"""
from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

_PARKOS_CORE_SRC = Path(__file__).resolve().parents[2] / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402

from parkos_core.repo.venta_suscripcion import (  # noqa: E402
    calcular_fecha_vencimiento,
    calcular_monto_suscripcion,
)
from parkos_core.runtime.renovacion import (  # noqa: E402
    RENOVACION_VENTANA_DIAS,
    calcular_inicio_renovacion,
    dias_restantes,
    renovacion_anticipada,
    renovacion_permitida,
)
from parkos_core.runtime.tiempo import hoy_bogota  # noqa: E402
from parkos_core.schemas.clientes import SubscripcionCupoDetalle  # noqa: E402
from parkos_core.schemas.renovacion import ConRenovacion  # noqa: E402

HOY = date(2026, 10, 6)


def _plan(dias: int, valor: str = "30000") -> SimpleNamespace:
    return SimpleNamespace(duracion_dias=dias, valor=Decimal(valor))


def test_ventana_es_diez_dias() -> None:
    assert RENOVACION_VENTANA_DIAS == 10


# ---------------------------------------------------------------- window ---


@pytest.mark.parametrize(
    ("dias_hasta_vencimiento", "restantes", "permitida"),
    [
        (10, 11, False),  # 11 days left -> rejected
        (9, 10, True),  # 10 days left -> allowed (exact edge)
        (8, 9, True),
        (0, 1, True),  # due date = last covered day -> 1 day left
        (-1, 0, True),  # expired yesterday -> 0 left, can renew
        (-30, -29, True),  # long expired -> can renew
    ],
)
def test_ventana_de_renovacion_bordes(
    dias_hasta_vencimiento: int, restantes: int, permitida: bool
) -> None:
    vencimiento = HOY + timedelta(days=dias_hasta_vencimiento)
    assert dias_restantes(vencimiento, hoy=HOY) == restantes
    assert renovacion_permitida(restantes) is permitida


def test_sin_fecha_de_vencimiento_no_se_puede_renovar() -> None:
    assert dias_restantes(None, hoy=HOY) is None
    assert renovacion_permitida(None) is False


def test_plan_de_n_dias_recien_activado_tiene_n_dias_restantes() -> None:
    inicio = HOY
    vencimiento = calcular_fecha_vencimiento(plan=_plan(30), fecha_inicio_cobertura=inicio)
    assert dias_restantes(vencimiento, hoy=inicio) == 30
    # the last covered day counts as 1 and is still valid (>= hoy)
    assert dias_restantes(vencimiento, hoy=vencimiento) == 1
    assert dias_restantes(vencimiento, hoy=vencimiento + timedelta(days=1)) == 0


# ------------------------------------------------------------ start date ---


def test_renovacion_antes_del_vencimiento_inicia_el_dia_siguiente() -> None:
    vencimiento = HOY + timedelta(days=5)
    assert renovacion_anticipada(vencimiento, hoy=HOY) is True
    assert calcular_inicio_renovacion(vencimiento, hoy=HOY) == vencimiento + timedelta(days=1)


def test_renovacion_el_dia_exacto_del_vencimiento_es_anticipada() -> None:
    """``vencimiento >= hoy`` is the validity predicate, so the due date is
    still covered: the renewal is early and starts TOMORROW (no day paid
    twice, no gap)."""
    assert renovacion_anticipada(HOY, hoy=HOY) is True
    assert calcular_inicio_renovacion(HOY, hoy=HOY) == HOY + timedelta(days=1)


def test_renovacion_vencida_ayer_inicia_hoy() -> None:
    vencimiento = HOY - timedelta(days=1)
    assert renovacion_anticipada(vencimiento, hoy=HOY) is False
    assert calcular_inicio_renovacion(vencimiento, hoy=HOY) == HOY


def test_renovacion_muy_vencida_inicia_hoy_no_en_el_pasado() -> None:
    vencimiento = HOY - timedelta(days=40)
    assert calcular_inicio_renovacion(vencimiento, hoy=HOY) == HOY


# ------------------------------------------------------ plans / calendar ---


@pytest.mark.parametrize("dias", [30, 60, 90])
def test_renovacion_cubre_exactamente_n_dias_sin_prorrateo(dias: int) -> None:
    plan = _plan(dias, valor="45000")
    anterior = HOY + timedelta(days=3)
    inicio = calcular_inicio_renovacion(anterior, hoy=HOY)
    vencimiento = calcular_fecha_vencimiento(plan=plan, fecha_inicio_cobertura=inicio)
    assert (vencimiento - inicio).days + 1 == dias
    assert inicio == anterior + timedelta(days=1)
    assert calcular_monto_suscripcion(plan=plan) == Decimal("45000.00")


def test_ultimo_dia_del_mes_no_prorratea_ni_se_corta_al_mes() -> None:
    plan = _plan(30)
    anterior = date(2026, 1, 31)
    inicio = calcular_inicio_renovacion(anterior, hoy=date(2026, 1, 29))
    assert inicio == date(2026, 2, 1)
    assert calcular_fecha_vencimiento(plan=plan, fecha_inicio_cobertura=inicio) == date(2026, 3, 2)
    assert calcular_monto_suscripcion(plan=plan) == Decimal("30000.00")


def test_anio_bisiesto_29_de_febrero() -> None:
    plan = _plan(30)
    # 2028 is a leap year: the previous period ends on Feb 28, the 29th exists.
    anterior = date(2028, 2, 28)
    inicio = calcular_inicio_renovacion(anterior, hoy=date(2028, 2, 25))
    assert inicio == date(2028, 2, 29)
    assert calcular_fecha_vencimiento(plan=plan, fecha_inicio_cobertura=inicio) == date(2028, 3, 29)


def test_anio_no_bisiesto_28_de_febrero() -> None:
    plan = _plan(30)
    anterior = date(2027, 2, 28)
    inicio = calcular_inicio_renovacion(anterior, hoy=date(2027, 2, 25))
    assert inicio == date(2027, 3, 1)
    assert calcular_fecha_vencimiento(plan=plan, fecha_inicio_cobertura=inicio) == date(2027, 3, 30)


def test_ventana_cruza_fin_de_mes_y_de_anio() -> None:
    vencimiento = date(2027, 1, 5)
    # Dec 26 -> 11 days left (outside), Dec 27 -> 10 (inside)
    assert renovacion_permitida(dias_restantes(vencimiento, hoy=date(2026, 12, 26))) is False
    assert renovacion_permitida(dias_restantes(vencimiento, hoy=date(2026, 12, 27))) is True


def test_ventana_en_bisiesto() -> None:
    vencimiento = date(2028, 3, 5)  # Feb has 29 days in 2028
    assert dias_restantes(vencimiento, hoy=date(2028, 2, 24)) == 11
    assert dias_restantes(vencimiento, hoy=date(2028, 2, 25)) == 10
    # the same dates in a common year are one day apart in the other direction
    assert dias_restantes(date(2027, 3, 5), hoy=date(2027, 2, 24)) == 10


# ------------------------------------------------------- Bogota midnight ---


def test_medianoche_bogota_no_es_medianoche_utc() -> None:
    """02:00 UTC of Oct 7 is still Oct 6 in Bogota (UTC-5): the renewal
    window/start must follow the Bogota day, not the UTC one."""
    now = datetime(2026, 10, 7, 2, 0, tzinfo=UTC)
    hoy = hoy_bogota(now)
    assert hoy == date(2026, 10, 6)
    vencimiento = date(2026, 10, 6)
    assert dias_restantes(vencimiento, hoy=hoy) == 1  # last covered day, still valid
    assert calcular_inicio_renovacion(vencimiento, hoy=hoy) == date(2026, 10, 7)


def test_cruce_de_medianoche_bogota_cambia_el_dia() -> None:
    antes = hoy_bogota(datetime(2026, 10, 7, 4, 59, 59, tzinfo=UTC))  # 23:59:59 Bogota
    despues = hoy_bogota(datetime(2026, 10, 7, 5, 0, 0, tzinfo=UTC))  # 00:00:00 Bogota
    assert antes == date(2026, 10, 6)
    assert despues == date(2026, 10, 7)
    vencimiento = date(2026, 10, 6)
    assert dias_restantes(vencimiento, hoy=antes) == 1
    assert dias_restantes(vencimiento, hoy=despues) == 0  # expired at Bogota midnight
    assert calcular_inicio_renovacion(vencimiento, hoy=antes) == date(2026, 10, 7)
    assert calcular_inicio_renovacion(vencimiento, hoy=despues) == date(2026, 10, 7)


# --------------------------------------------- read-model computed fields ---


def test_campos_calculados_en_lectura_usan_la_fecha_de_bogota() -> None:
    class _Lectura(ConRenovacion):
        pass

    hoy = hoy_bogota()
    fuera = _Lectura(fecha_vencimiento=hoy + timedelta(days=RENOVACION_VENTANA_DIAS))  # 11 left
    dentro = _Lectura(fecha_vencimiento=hoy + timedelta(days=RENOVACION_VENTANA_DIAS - 1))  # 10
    vencida = _Lectura(fecha_vencimiento=hoy - timedelta(days=3))
    sin_fecha = _Lectura(fecha_vencimiento=None)

    assert (fuera.dias_restantes, fuera.puede_renovar) == (11, False)
    assert (dentro.dias_restantes, dentro.puede_renovar) == (10, True)
    assert vencida.dias_restantes == -2
    assert vencida.puede_renovar is True
    assert (sin_fecha.dias_restantes, sin_fecha.puede_renovar) == (None, False)
    assert dentro.model_dump()["puede_renovar"] is True  # serialized for the UI


def test_detalle_de_cupos_expone_campos_calculados() -> None:
    assert "dias_restantes" in SubscripcionCupoDetalle.model_computed_fields
    assert "puede_renovar" in SubscripcionCupoDetalle.model_computed_fields
