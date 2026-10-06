"""PT-3: Bogota reference clock for subscription validity checks."""
from __future__ import annotations

from datetime import UTC, date, datetime

from parkos_core.runtime.tiempo import hoy_bogota


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
