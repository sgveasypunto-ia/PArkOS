"""PT-3: Bogota reference clock for subscription validity checks."""
from __future__ import annotations

from datetime import UTC, date, datetime

from parkos_core.runtime.tiempo import dia_bogota_rango_utc, hoy_bogota


def test_hoy_bogota_late_evening_bogota_is_still_same_day() -> None:
    # 2026-09-30 23:30 Bogota == 2026-10-01 04:30 UTC: UTC "today" is a day ahead.
    now = datetime(2026, 10, 1, 4, 30, tzinfo=UTC)
    assert now.date() == date(2026, 10, 1)
    assert hoy_bogota(now) == date(2026, 9, 30)


def test_hoy_bogota_just_after_midnight_bogota() -> None:
    # 2026-10-01 00:05 Bogota == 05:05 UTC
    assert hoy_bogota(datetime(2026, 10, 1, 5, 5, tzinfo=UTC)) == date(2026, 10, 1)


def test_hoy_bogota_boundary_is_utc_minus_five() -> None:
    assert hoy_bogota(datetime(2026, 10, 1, 4, 59, tzinfo=UTC)) == date(2026, 9, 30)
    assert hoy_bogota(datetime(2026, 10, 1, 5, 0, tzinfo=UTC)) == date(2026, 10, 1)


def test_hoy_bogota_leap_day() -> None:
    assert hoy_bogota(datetime(2028, 3, 1, 3, 0, tzinfo=UTC)) == date(2028, 2, 29)


def test_hoy_bogota_naive_is_treated_as_utc() -> None:
    assert hoy_bogota(datetime(2026, 10, 1, 4, 30)) == date(2026, 9, 30)


def test_hoy_bogota_defaults_to_now() -> None:
    assert isinstance(hoy_bogota(), date)


def test_dia_bogota_rango_utc_is_utc_plus_five_naive() -> None:
    """A Bogota calendar day spans 05:00Z of that date to 05:00Z of the next
    (naive UTC, matching the ``timestamp without time zone`` columns)."""
    inicio, fin = dia_bogota_rango_utc(date(2026, 10, 7))
    assert inicio == datetime(2026, 10, 7, 5, 0)
    assert fin == datetime(2026, 10, 8, 5, 0)
    assert inicio.tzinfo is None and fin.tzinfo is None


def test_dia_bogota_rango_utc_contains_evening_session_opened_after_19h() -> None:
    """A session opened 20:00 Bogota (01:00Z next UTC day) belongs to the
    Bogota day, which a plain ``timestamp::date`` (UTC) comparison misses."""
    inicio, fin = dia_bogota_rango_utc(date(2026, 10, 7))
    apertura_utc = datetime(2026, 10, 8, 1, 0)  # 20:00 Bogota on the 7th
    assert inicio <= apertura_utc < fin
