"""Tests for ``repo.factura.crear_factura_pago``'s ``uuid_sucursal`` column.

Live QA defect (Reportería financiera "Pagos" tab, 2026-10-02):
``crear_factura_pago`` never populated ``prod.factura_pagos.uuid_sucursal``
on INSERT. The global ``do_orm_execute`` tenant listener
(``db/tenancy.py``) injects ``WHERE uuid_sucursal = :ctx`` on ANY ORM read
of an entity carrying that column, so a NULL value silently dropped every
row from every admin-scoped read (``GET /reporteria/pagos`` returned
``items: []`` despite real payments existing for the branch/range).

Pure-Python tests using ``unittest.mock.AsyncMock`` to fake ``AsyncSession``
— same style as ``test_factura_pagos_reverse.py``.
"""

from __future__ import annotations

import inspect
import uuid as uuid_lib
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.models.A.factura_pagos import FacturaPagos
from parkos_core.repo.factura import crear_factura_pago

FACTURA_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000cc1")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000bb1")


@pytest.mark.asyncio
async def test_crear_factura_pago_sets_uuid_sucursal_on_the_new_row() -> None:
    """GREEN: the inserted ``FacturaPagos`` row carries the real branch."""
    session = AsyncMock()
    session.add = MagicMock()

    new_row = await crear_factura_pago(
        session,
        uuid_factura=FACTURA_UUID,
        uuid_sucursal=SUCURSAL_UUID,
        medio_pago="efectivo",
        valor=Decimal("500"),
    )

    assert isinstance(new_row, FacturaPagos)
    assert new_row.uuid_sucursal == SUCURSAL_UUID
    assert new_row.uuid_factura == FACTURA_UUID
    session.add.assert_called_once_with(new_row)
    session.flush.assert_awaited_once()


def test_crear_factura_pago_requires_uuid_sucursal() -> None:
    """RED-turned-GREEN: ``uuid_sucursal`` is a mandatory keyword-only arg.

    Regression guard against silently reintroducing the nullable/optional
    gap this fix closes -- a caller MUST supply the branch explicitly.
    """
    sig = inspect.signature(crear_factura_pago)
    param = sig.parameters["uuid_sucursal"]
    assert param.default is inspect.Parameter.empty
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
