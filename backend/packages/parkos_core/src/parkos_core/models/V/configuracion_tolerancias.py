"""ORM model for ``prod.configuracion_tolerancias`` ([V] table, PR4).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 387-399).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 3 business columns mirror the ER ``configuracion_tolerancias`` block
exactly: ``uuid_sucursal`` (PG_UUID, nullable — NULL means global default),
``tolerancia_efectivo`` and ``tolerancia_datafono`` (Numeric(18,4)).

Override resolution pattern (REQ-OP-12 + SC-OP-06): ``uuid_sucursal IS NULL``
row is the global default; a non-null row is the per-branch override. The
custom ``GET /configuracion-tolerancias/efectiva`` route in T-PR4-04 picks
the override if present, otherwise falls back to the global default.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class ConfiguracionTolerancias(VersionedBase):
    """[V] Cash-counting tolerances; global default + per-branch override."""

    __tablename__ = "configuracion_tolerancias"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tolerancia_efectivo: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    tolerancia_datafono: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "uuid_sucursal",
            "vigente_desde",
            name="configuracion_tolerancias_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["ConfiguracionTolerancias"]