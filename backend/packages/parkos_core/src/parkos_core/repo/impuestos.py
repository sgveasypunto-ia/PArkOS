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
F1.8's PL/pgSQL predicate.
"""
from __future__ import annotations

from datetime import UTC, datetime

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


__all__ = ["validar_iva_configurado"]
