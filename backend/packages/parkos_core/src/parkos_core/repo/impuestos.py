"""HU-F1.7 -- inline-seed helper for ``prod.impuestos`` (KD-IVA resolver).

Provides read access to the canonical IVA tax row (codigo='IVA',
porcentaje=0.19). The row itself is inserted by migration 0026 via
``INSERT ... ON CONFLICT (codigo, vigente_desde) DO NOTHING``.

This module is a thin wrapper -- the PL/pgSQL function
``prod.calcular_cotizacion`` reads ``prod.impuestos`` directly without
going through Python. The helper exists for:
- HU-F1.9 (facturacion) snapshot validation.
- HU-F14.2 audit (verify IVA seeded post-deploy).
- Test fixtures (mock the read).

Idempotent on re-apply. ``validar_iva_configurado`` returns True iff the
IVA row exists and is vigente at NOW(); the contract is the same as
F1.8's PL/pgSQL predicate. ``obtener_iva_vigente`` is the value-returning
variant used by ``api/v1/facturacion.py::create_factura`` Step 8 to
avoid hardcoded tax constants (DEC-FACT-03).
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.impuestos import Impuestos


async def validar_iva_configurado(session: AsyncSession) -> bool:
    """Return True iff ``prod.impuestos`` has a vigente row with codigo='IVA'.

    Predicate (bi-temporal [V]):
        codigo = 'IVA'
        AND vigente_hasta IS NULL
        AND estado = 'activo'
        AND vigente_desde <= NOW()
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    stmt = select(Impuestos).where(
        Impuestos.codigo == "IVA",
        Impuestos.vigente_hasta.is_(None),
        Impuestos.estado == "activo",
        Impuestos.vigente_desde <= now,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row is not None


async def obtener_iva_vigente(session: AsyncSession) -> Decimal | None:
    """Return the active IVA ``porcentaje`` as ``Decimal`` (DEC-FACT-03).

    DEC-FACT-03 forbids hardcoded tax constants in the billing hot path.
    The handler MUST source the IVA rate from ``prod.impuestos`` so that
    a regulatory change to the rate is automatically reflected in both
    ``compute_total`` (Step 8) and ``crear_factura_impuesto_iva``
    (Step 10b). This helper reads the vigente row's ``porcentaje``.

    Bi-temporal [V] predicate (mirrors ``validar_iva_configurado``):
        codigo = 'IVA'
        AND vigente_hasta IS NULL
        AND estado = 'activo'
        AND vigente_desde <= NOW()

    Returns ``None`` when no vigente row exists. Handler maps this to
    HTTP 500 ``iva_no_configurado``.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    # ``order_by(... desc) + limit(1)`` so a corrupt DB with multiple
    # vigente rows deterministically picks the most recent one (the
    # versioned catalog normally has at most one open row at any time,
    # but this keeps the helper defensive).
    stmt = (
        select(Impuestos.porcentaje)
        .where(
            Impuestos.codigo == "IVA",
            Impuestos.vigente_hasta.is_(None),
            Impuestos.estado == "activo",
            Impuestos.vigente_desde <= now,
        )
        .order_by(Impuestos.vigente_desde.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row


__all__ = ["obtener_iva_vigente", "validar_iva_configurado"]
