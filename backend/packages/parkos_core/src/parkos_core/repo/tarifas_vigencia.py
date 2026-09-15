"""HU-F1.4 — Bi-temporal helper for ``GET /empresa/tarifas-sucursal``.

This module exists so the dedicated handler in ``api/v1/empresa.py`` can
apply the canonical bi-temporal predicate
``vigente_desde <= :v AND (vigente_hasta IS NULL OR vigente_hasta > :v) AND
estado = 'activo'`` without duplicating cursor / order / tz-normalization
logic. The helper is SELECT-only — no INSERT/UPDATE/DELETE, no side effects,
no cache, no lock.

Why a new helper instead of extending :func:`router_factory.make_router`:
HU-F1.1 (``f7cb37a``) stabilized the factory. Touching it would re-open the
blast radius over the 30+ resources the factory mounts. HU-F1.4 keeps the
factory intact and adds this targeted helper for the one resource that
needs the bi-temporal filter (``tarifas-sucursal``).

The predicate lives at module level as :data:`BITEMPORAL_VIGENTE_PREDICATE`
so the unit tests can reference it without re-encoding the SQL.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.router_factory import _order_key, _parse_cursor_timestamp
from ..models.V.tarifas_sucursal import TarifasSucursal
from ..repo.pagination import Cursor
from ..repo.pagination import decode as cursor_decode
from ..repo.pagination import encode as cursor_encode
from ..schemas.empresa import TarifasSucursalFilter

# Module-level alias for the column type used by the helper. Lets tests
# reference the SAME expression the handler uses without re-typing it.
BITEMPORAL_VIGENTE_PREDICATE_TEMPLATE = (
    "vigente_desde <= :vigente_en "
    "AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en) "
    "AND estado = 'activo'"
)


def bitemporal_vigente_predicate(model_cls: type, v_utc: datetime) -> ColumnElement[bool]:
    """Return the canonical bi-temporal predicate bound to ``v_utc``.

    Used by the dedicated ``GET /empresa/tarifas-sucursal`` handler so
    tests can assert the SAME predicate the handler uses without
    re-encoding the SQL.
    """
    # ``model_cls`` is typed as ``type`` (generic) but the helper only
    # accepts classes declaring ``estado`` / ``vigente_desde`` /
    # ``vigente_hasta`` — mirror the factory's ``# type: ignore`` to
    # tell mypy the runtime check is already done.
    return and_(
        model_cls.estado == "activo",  # type: ignore[attr-defined]
        model_cls.vigente_desde <= v_utc,  # type: ignore[attr-defined]
        or_(
            model_cls.vigente_hasta.is_(None),  # type: ignore[attr-defined]
            model_cls.vigente_hasta > v_utc,  # type: ignore[attr-defined]
        ),
    )


def _to_utc_naive(value: datetime) -> datetime:
    """Normalize ``value`` to a naive UTC ``datetime`` suitable for binding.

    The DB column ``tarifas_sucursal.vigente_desde`` / ``vigente_hasta``
    is ``DateTime(timezone=False)``; asyncpg rejects ``timestamp with time
    zone`` implicit casts in a ``WHERE`` (see the bug note in
    :func:`router_factory._parse_cursor_timestamp`). Naive input is
    interpreted as UTC — same convention as the cursor decoder.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(tzinfo=None)


async def list_tarifas_vigentes(
    session: AsyncSession,
    *,
    vigente_en: datetime,
    filter: TarifasSucursalFilter,
    cursor: str | None,
    limit: int,
) -> tuple[list[TarifasSucursal], str | None]:
    """Return ``(rows, next_cursor)`` for the bi-temporal filter.

    Identical ordering / cursor contract to the factory's
    ``list_endpoint`` — ``(vigente_desde DESC, uuid ASC)``, cursor
    encodes ``vigente_desde`` — so cursors emitted by the factory
    remain decodable after the deploy.

    Args:
        session: Async SQLAlchemy session.
        vigente_en: Point in time for the predicate. Naive is treated as UTC.
        filter: Pre-validated filter schema (currently only carries
            ``vigente_en`` and the legacy fields — the helper ignores the
            legacy ones; the handler can re-apply them when callers pass
            them via ``TarifasSucursalFilter``).
        cursor: Opaque base64url cursor, or ``None`` for the first page.
        limit: Page size (1..200).
    """
    v_utc = _to_utc_naive(vigente_en)

    # Decode the cursor (or accept ``None``) before building the WHERE so
    # the typed exception bubbles up unchanged. ``InvalidCursorError`` is
    # converted to HTTP 400 by the handler layer.
    decoded = None
    if cursor is not None:
        decoded = cursor_decode(cursor)

    order_col, cursor_field = _order_key(TarifasSucursal)

    stmt = select(TarifasSucursal).where(bitemporal_vigente_predicate(TarifasSucursal, v_utc))

    # Optional additional filters from the schema (uuid_sucursal,
    # uuid_tipo_vehiculo, uuid_tipo_tarifa). Apply them when set so the
    # handler can pass a richer filter without the helper caring.
    if filter.uuid_sucursal is not None:
        stmt = stmt.where(TarifasSucursal.uuid_sucursal == filter.uuid_sucursal)
    if filter.uuid_tipo_vehiculo is not None:
        stmt = stmt.where(TarifasSucursal.uuid_tipo_vehiculo == filter.uuid_tipo_vehiculo)
    if filter.uuid_tipo_tarifa is not None:
        stmt = stmt.where(TarifasSucursal.uuid_tipo_tarifa == filter.uuid_tipo_tarifa)

    stmt = stmt.order_by(order_col, TarifasSucursal.uuid.asc())

    if decoded is not None:
        cursor_ts = _parse_cursor_timestamp(getattr(decoded, cursor_field))
        stmt = stmt.where(
            (order_col.element < cursor_ts)
            | (
                (order_col.element == cursor_ts)
                & (TarifasSucursal.uuid > uuid_lib.UUID(decoded.uuid))
            )
        )

    stmt = stmt.limit(limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        last_vigente_desde: datetime | None = getattr(last, "vigente_desde", None)
        next_cursor = cursor_encode(
            Cursor(
                vigente_desde=(
                    last_vigente_desde.isoformat()
                    if cursor_field == "vigente_desde" and last_vigente_desde is not None
                    else None
                ),
                created_at=None,
                uuid=str(last.uuid),
            )
        )

    _ = filter  # silence unused-arg when no extras are present (helper is reusable)
    return rows, next_cursor


__all__ = [
    "BITEMPORAL_VIGENTE_PREDICATE_TEMPLATE",
    "TarifaValidationResult",
    "bitemporal_vigente_predicate",
    "list_tarifas_vigentes",
    "validar_tarifa_vigente",
]


# ---------------------------------------------------------------------------
# HU-F1.6 -- V3 (REQ-OPS-036) thin wrapper on F1.4 bi-temporal predicate.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TarifaValidationResult:
    """Outcome of :func:`validar_tarifa_vigente`."""

    vigente: bool
    tarifa: TarifasSucursal | None = None


async def validar_tarifa_vigente(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    at: datetime,
    forzado: bool = False,
) -> TarifaValidationResult:
    """V3 (REQ-OPS-036): is there a vigente ``tarifas_sucursal`` row?

    Reuses :data:`bitemporal_vigente_predicate` verbatim from F1.4
    (``vigente_desde <= :v AND (vigente_hasta IS NULL OR vigente_hasta
    > :v) AND estado = 'activo'``). KD-FORZADO does NOT bypass V3 -- a
    forced ingreso still requires a vigente tariff to bill against.
    The ``forzado`` param is accepted for symmetry with the other
    validators but ignored.
    """
    v_utc = _to_utc_naive(at)
    stmt = (
        select(TarifasSucursal)
        .where(
            TarifasSucursal.uuid_sucursal == uuid_sucursal,
            TarifasSucursal.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
        )
        .where(bitemporal_vigente_predicate(TarifasSucursal, v_utc))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is not None:
        return TarifaValidationResult(vigente=True, tarifa=row)
    return TarifaValidationResult(vigente=False, tarifa=None)
