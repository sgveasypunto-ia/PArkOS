"""parkos_core.runtime.renovacion -- pure date rules for subscription renewal (PT-3).

No database, no I/O: everything here is a function of dates, so the edge
cases (end of month, leap year, Bogota midnight) are unit-testable with an
injected ``hoy``.

Conventions (decided once, here):

* ``fecha_vencimiento`` is the LAST COVERED DAY, inclusive (a plan of N days
  starting on day D expires on ``D + N - 1``). The validity predicates used
  across the backend are ``fecha_vencimiento >= hoy``.
* ``dias_restantes`` counts the covered days that are still left INCLUDING
  today: ``(fecha_vencimiento - hoy) + 1``. On the last covered day it is 1;
  the day after it is 0 (expired); older expirations are negative.
  (``reporteria`` exposes ``dias_para_vencer = fecha_vencimiento - hoy``,
  which is 0 on the last day -- always exactly ``dias_restantes - 1``.)
* "Today" is the Bogota calendar date (``runtime.tiempo.hoy_bogota``).
"""
from __future__ import annotations

from datetime import date, timedelta

from .tiempo import hoy_bogota

__all__ = [
    "RENOVACION_URGENTE_DIAS",
    "calcular_inicio_renovacion",
    "dias_restantes",
    "renovacion_anticipada",
    "renovacion_permitida",
]

# A subscription can be renewed at ANY time before (or after) it expires:
# there is no anticipation window and no cap. This constant only bounds the
# "renovables" feed (subscriptions worth surfacing as urgent: this many days
# or fewer left). It is NOT a renewal gate.
# Independent of ``subscripciones_cliente.dias_alerta_pre_vencimiento``
# (the per-subscription *warning* window, default 7).
RENOVACION_URGENTE_DIAS: int = 10


def dias_restantes(fecha_vencimiento: date | None, *, hoy: date | None = None) -> int | None:
    """Covered days left including today (``None`` when there is no due date)."""
    if fecha_vencimiento is None:
        return None
    referencia = hoy if hoy is not None else hoy_bogota()
    return (fecha_vencimiento - referencia).days + 1


def renovacion_permitida(restantes: int | None) -> bool:
    """Single decision point for "can this subscription be renewed now?".

    Allowed whenever the subscription has a due date: no anticipation window
    and no cap (the new period stacks on top of the remaining validity).
    Expired subscriptions (``restantes <= 0``) are included. Only a missing
    due date (``None``) blocks it.
    """
    return restantes is not None


def renovacion_anticipada(fecha_vencimiento: date, *, hoy: date | None = None) -> bool:
    """True when the current period still covers today (``vencimiento >= hoy``).

    The due date itself is still covered (inclusive predicate), so renewing
    ON the due date is an early renewal: the new period starts tomorrow, with
    no gap and no day paid twice.
    """
    referencia = hoy if hoy is not None else hoy_bogota()
    return fecha_vencimiento >= referencia


def calcular_inicio_renovacion(fecha_vencimiento_anterior: date, *, hoy: date | None = None) -> date:
    """``max(vencimiento_anterior + 1, hoy)``.

    Early renewal extends from the day after the previous due date; late
    renewal starts today (Bogota). The two coincide when the previous period
    expired yesterday.
    """
    referencia = hoy if hoy is not None else hoy_bogota()
    return max(fecha_vencimiento_anterior + timedelta(days=1), referencia)
