"""ORM model for ``prod.factura_otros_cobros`` (billing [A] surcharges, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 672-686).

``AppendOnlyBase`` \u2014 write-only via ``repo.append_only.append_event``.
Other charges (recargos, propinas, ajustes) are append-only by design \u2014
corrections flow as new rows that point to the original via
``uuid_otro_cobro`` (the FK to the master catalog) and the parent
``uuid_factura``.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class FacturaOtrosCobros(AppendOnlyBase):
    """[A] Surcharge line on a ``factura`` (recargo, propina, ajuste)."""

    __tablename__ = "factura_otros_cobros"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_otro_cobro: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    base_calculo: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    valor_aplicado: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    valor: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["FacturaOtrosCobros"]