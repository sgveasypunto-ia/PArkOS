"""ORM model for ``prod.factura_pagos`` (billing [A] payment events, PR6).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 688-717).

Range-partitioned monthly by ``fecha_retencion_hasta`` (DIAN 5+ year
retention, pg_partman parent). Composite PK on
``(uuid, fecha_retencion_hasta)``.

The ``tipo_movimiento`` discriminator (``pago`` | ``reverso``) + the
``uuid_pago_revertido`` pointer are guarded by the partial unique index
created in T-PR6-06:
``CREATE UNIQUE INDEX uq_factura_pagos_reverso
   ON prod.factura_pagos (uuid_pago_revertido)
   WHERE tipo_movimiento = 'reverso' AND uuid_pago_revertido IS NOT NULL``.
This is the DB-layer enforcement of ``reverse_payment()``'s at-most-once
invariant (REQ-OP-09, SC-11) \u2014 a second reversal raises
``UniqueViolation`` and surfaces as ``DuplicateReversoError`` (409).

Additionally, F1.9 / MIGRATION 0027 Op 3 installs the BEFORE INSERT
trigger ``fn_factura_pagos_init_pago_uniqueness`` on this table,
rejecting a second ``pago``/``ajuste`` row for the same ``uuid_factura``.
This is the only DB-layer defense against duplicate init-pago rows
because ``prod.factura_pagos`` is range-partitioned by
``fecha_retencion_hasta`` (partial unique index infeasible across
partitions). Violations surface as ``PagoDuplicadoError`` (409) in
``repo.factura.crear_factura_pago``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class FacturaPagos(AppendOnlyBase):
    """[A] Payment event against a ``factura`` (or its reversal)."""

    __tablename__ = "factura_pagos"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
    fecha_retencion_hasta: Mapped[date] = mapped_column(  # type: ignore[override]
        Date,
        nullable=False,
        server_default=func.current_date(),
    )

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_sesion: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    medio_pago: Mapped[str | None] = mapped_column(String, nullable=True)
    valor: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)
    referencia: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo_movimiento: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_pago_revertido: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    timestamp_evento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="factura_pagos_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["FacturaPagos"]