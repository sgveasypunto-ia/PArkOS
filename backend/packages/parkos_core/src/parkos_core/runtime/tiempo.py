"""parkos_core.runtime.tiempo -- reference clock for the business day.

The branch operates in Colombia (``America/Bogota``, UTC-5, no DST). A
"today" computed from UTC flips five hours early (at 19:00 Bogota), so
validations that compare against a calendar date (subscription validity,
duplicate-plate checks) must use the Bogota date instead.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = ["BOGOTA_TZ", "dia_bogota_rango_utc", "hoy_bogota"]


def _load_bogota_tz() -> tzinfo:
    try:
        return ZoneInfo("America/Bogota")
    except ZoneInfoNotFoundError:  # slim images without tzdata
        # Colombia has had a fixed UTC-5 offset (no DST) since 1993.
        return timezone(timedelta(hours=-5), "America/Bogota")


BOGOTA_TZ: tzinfo = _load_bogota_tz()


def hoy_bogota(now: datetime | None = None) -> date:
    """Return the current calendar date in Bogota.

    ``now`` is injectable for tests; naive values are treated as UTC.
    """
    moment = now if now is not None else datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(BOGOTA_TZ).date()


def dia_bogota_rango_utc(fecha: date) -> tuple[datetime, datetime]:
    """Return ``[inicio, fin)`` of the Bogota calendar day ``fecha`` as
    naive UTC datetimes.

    The DB stores ``timestamp without time zone`` in UTC, so
    ``timestamp::date = fecha`` compares the UTC date: a session opened at
    20:00 Bogota (01:00Z next day) falls on the wrong date. Filtering with
    this half-open range matches the business day instead.
    """
    inicio_local = datetime(fecha.year, fecha.month, fecha.day, tzinfo=BOGOTA_TZ)
    inicio = inicio_local.astimezone(UTC).replace(tzinfo=None)
    return inicio, inicio + timedelta(days=1)
