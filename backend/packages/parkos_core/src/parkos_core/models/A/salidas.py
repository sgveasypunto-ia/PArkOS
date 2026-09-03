"""ORM model for ``prod.salidas`` (vehicle exit [A] event, PR6-T05a).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 557-580).
The table was created in PR1a but the ORM class was deferred to PR6 — it
is the missing polymorphic target referenced from
``repo/workflow.py::polymorphic_row_exists`` (REQ-OP-08, REQ-23-W-POLYMORPHIC-FK).

Range-partitioned monthly by ``fecha_retencion_hasta`` (DIAN 5+ year
retention, pg_partman parent). Composite PK on
``(uuid, fecha_retencion_hasta)`` overrides ``IdMixin``'s single-column PK.

``[A]`` inmutability is enforced at the DB layer by the
``REVOKE UPDATE, DELETE`` from ``rol_app`` + the
``BEFORE UPDATE OR DELETE`` trigger installed in migration ``0001``. The
ORM marker ``__write_only__`` (inherited from :class:`AppendOnlyBase`) is
read by ``tests/static/test_no_raw_dml_on_a_tables.py`` to reject any
``session.execute(update/delete)`` against ``salidas`` outside
``repo/append_only.py``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import Date, DateTime, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class Salidas(AppendOnlyBase):
    """[A] Append-only vehicle exit event.

    Written via :func:`repo.append_only.append_event` (single INSERT
    helper, REQ-10-A-INSERCION). Never updated or deleted: the original
    exit record is permanent; corrections are expressed as new
    compensating ``[L-W]`` rows (e.g. ``anulaciones``) and never as a
    mutation of this row.
    """

    __tablename__ = "salidas"

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
    uuid_ingreso: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    fecha_salida: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="salidas_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["Salidas"]
