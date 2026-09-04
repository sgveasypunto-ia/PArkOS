"""Compensating payment reversal for ``prod.factura_pagos`` (REQ-OP-09, SC-11).

A reversal is a NEW ``[A]`` row with ``tipo_movimiento='reverso'`` linking
back to the original via ``uuid_pago_revertido``. The original row is
NEVER mutated — per the ``[A]`` inmutability contract
(``REVOKE UPDATE, DELETE`` + ``BEFORE UPDATE OR DELETE`` trigger) the
``factura_pagos`` table is append-only; the derived view
``V_FACTURA_PAGOS_NETOS`` subtracts reversos from pagos for net reporting.

The partial unique index
``CREATE UNIQUE INDEX uq_factura_pagos_reverso
   ON prod.factura_pagos (uuid_pago_revertido)
   WHERE tipo_movimiento = 'reverso' AND uuid_pago_revertido IS NOT NULL``
(lands in T-PR6-06 migration ``0004_add_factura_pagos_reverso_index.py``)
enforces at the DB layer that a given payment can be reversed at most
once. ``reverse_payment`` raises :class:`DuplicateReversoError` when the
DB rejects the second insert via ``UniqueViolation``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.factura_pagos import FacturaPagos
from ..models.A.log_transaccional import LogTransaccional


class FacturaPagosError(Exception):
    """Base class for ``factura_pagos`` operation failures."""


class PagoNotFoundError(FacturaPagosError):
    """Raised when ``original_pago_uuid`` does not match any row."""


class DuplicateReversoError(FacturaPagosError):
    """Raised when a reverso row already exists for the given payment.

    Maps to HTTP 409 in router code. The DB enforces this via the partial
    unique index ``uq_factura_pagos_reverso`` (PR6-T06 migration); this
    is the Python-side mirror that translates psycopg's
    ``UniqueViolation`` into a domain exception.
    """


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` — matches ``repo/append_only.py`` style."""
    return datetime.now(UTC).replace(tzinfo=None)


async def reverse_payment(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    original_pago_uuid: uuid_lib.UUID,
    motivo: str | None = None,
    log_tx: bool = True,
) -> FacturaPagos:
    """Insert a compensating ``factura_pagos`` row with ``tipo_movimiento='reverso'``.

    Reads the original row (raises :class:`PagoNotFoundError` if missing),
    then inserts a NEW row mirroring the original's business attributes
    (``uuid_factura``, ``uuid_sucursal``, ``uuid_sesion``, ``medio_pago``,
    ``valor``, ``referencia``) and stamping the reverso discriminator:

    - ``tipo_movimiento='reverso'``
    - ``uuid_pago_revertido=original_pago_uuid``
    - ``timestamp_evento=now``
    - ``fecha_retencion_hasta=NOW() + 5 years`` (DIAN retention)

    A co-transactional ``log_transaccional`` row is appended when
    ``log_tx=True`` (default).

    The session is flushed so the DB raises ``UniqueViolation`` (from
    ``uq_factura_pagos_reverso``) at flush time rather than at commit
    time. This keeps the exception scoped to the helper's surface so the
    router can map it to a 409 cleanly.

    Args:
        session: Active ``AsyncSession`` (caller commits).
        actor_uuid: JWT subject of the operator requesting the reversal.
        original_pago_uuid: UUID of the original ``factura_pagos`` row to
            reverse.
        motivo: Optional human-readable reason recorded on the
            ``log_transaccional`` row's ``datos_nuevos`` payload.
        log_tx: Whether to append a ``log_transaccional`` row in the
            same TX (default ``True``).

    Returns:
        The newly inserted compensating :class:`FacturaPagos` row (not
        yet committed by this helper).

    Raises:
        PagoNotFoundError: ``original_pago_uuid`` does not match any
            ``factura_pagos`` row.
        DuplicateReversoError: A ``reverso`` row for this payment already
            exists (partial unique index
            ``uq_factura_pagos_reverso`` violated).
    """
    # 1. Read the original payment row.
    original = (
        await session.execute(
            select(FacturaPagos).where(FacturaPagos.uuid == original_pago_uuid)
        )
    ).scalar_one_or_none()
    if original is None:
        raise PagoNotFoundError(
            f"No factura_pagos row with uuid={original_pago_uuid}"
        )

    now = _now_naive()
    # DIAN 5-year retention — matches the migration's `Date` column type.
    fecha_retencion_hasta = (now + timedelta(days=5 * 365)).date()

    # 2. Build the compensating row (mirror original attrs + reverso flags).
    new_row = FacturaPagos(
        uuid_sucursal=original.uuid_sucursal,
        uuid_factura=original.uuid_factura,
        uuid_sesion=original.uuid_sesion,
        medio_pago=original.medio_pago,
        valor=original.valor,
        referencia=original.referencia,
        tipo_movimiento="reverso",
        uuid_pago_revertido=original_pago_uuid,
        timestamp_evento=now,
        fecha_retencion_hasta=fecha_retencion_hasta,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(new_row)

    if log_tx:
        log_row = LogTransaccional(
            uuid_usuario=actor_uuid,
            uuid_sucursal=original.uuid_sucursal,
            accion="compensar",
            tabla_afectada="factura_pagos",
            uuid_registro_afectado=getattr(new_row, "uuid", None),
            uuid_referencia=original_pago_uuid,
            timestamp_evento=now,
            datos_nuevos={"motivo": motivo, "tipo_movimiento": "reverso"},
        )
        session.add(log_row)

    # 3. Flush so the DB raises UniqueViolation NOW (not at commit time).
    try:
        await session.flush()
    except IntegrityError as e:
        # psycopg raises UniqueViolation; SQLAlchemy wraps it as
        # IntegrityError. The BEFORE INSERT trigger raises
        # ``factura_pagos reverso uniqueness violation: uuid_pago_revertido=...
        # already has a reverso row`` (see 0004_add_factura_pagos_reverso_trigger.py:48).
        if (
            "reverso uniqueness" in str(e.orig)
            or "duplicate key" in str(e.orig).lower()
        ):
            raise DuplicateReversoError(
                f"Payment {original_pago_uuid} has already been reversed"
            ) from e
        raise

    return new_row


__all__ = [
    "DuplicateReversoError",
    "FacturaPagosError",
    "PagoNotFoundError",
    "reverse_payment",
]
