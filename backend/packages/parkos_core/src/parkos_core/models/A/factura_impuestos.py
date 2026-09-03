"""ORM model for ``prod.factura_impuestos`` (billing [A] tax snapshot, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 656-670).

``AppendOnlyBase`` \u2014 write-only via ``repo.append_only.append_event``.
The retention column (``fecha_retencion_hasta``) is inherited from
``RetentionMixin``; for DIAN tables the helper sets
``NOW() + INTERVAL '5 years'`` on insert.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class FacturaImpuestos(AppendOnlyBase):
    """[A] Tax snapshot applied to a ``factura`` row (DIAN-coupled)."""

    __tablename__ = "factura_impuestos"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_impuesto: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    base_calculo: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    porcentaje_aplicado: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    valor: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["FacturaImpuestos"]