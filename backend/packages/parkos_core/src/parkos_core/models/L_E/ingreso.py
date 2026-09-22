"""ORM model for ``prod.ingreso`` (operation [L-E] lifecycle event, PR5).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 542-555).

``LifecycleEventBase`` — insert-only event. NO versioning columns. Writes
MUST go through ``repo.event.record_event`` (REQ-30, REQ-33), and the
AST scan in ``tests/static/test_no_raw_dml_on_le_tables.py`` rejects any
``session.execute(update/delete)`` against this table outside that helper.

Current state (``abierto`` | ``cerrado`` | ``anulada``) is DERIVED via the
``V_INGRESO_ESTADO`` view by joining with ``salidas`` and ``anulaciones``
(PR6 mounts those). The view materializes the state on read — we never
store it on the row itself, in keeping with the bi-temporal contract
(state belongs to the workflow, not to the event).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import LifecycleEventBase


class Ingreso(LifecycleEventBase):
    """[L-E] Vehicle entry event — append-only at write time."""

    __tablename__ = "ingreso"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    placa: Mapped[str | None] = mapped_column(String, nullable=True)
    uuid_tipo_vehiculo: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_subscripcion_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    fecha_ingreso: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    # REQ-OPS-192: nullable parking-lot identifier for ingresos sin placa
    # (bicicleta, patineta). Format ``<TIPO>-NNNNNN-<uuid8>`` -- assigned
    # by ``repo.ingreso_consecutivo.assign_ingreso_consecutivo``. NULL for
    # legacy carro/moto rows (backward compat). Defense in depth: partial UK
    # ``uq_ingreso_consecutivo_partial`` on (sucursal, tipo, consecutivo)
    # WHERE consecutivo IS NOT NULL.
    consecutivo: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Ingreso"]
