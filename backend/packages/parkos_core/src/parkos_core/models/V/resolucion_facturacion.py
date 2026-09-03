"""ORM model for ``prod.resolucion_facturacion`` ([V] table, PR4).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 416-433).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 8 business columns mirror the ER ``resolucion_facturacion`` block exactly:
``uuid_sucursal`` (PG_UUID), ``numero_resolucion`` (UK), ``prefijo`` (String),
``rango_desde`` / ``rango_hasta`` (BigInteger), ``fecha_resolucion`` /
``fecha_inicio_vigencia`` / ``fecha_fin_vigencia`` (Date).

This is the DIAN root table (REQ-X3): cloud-only writes. The Pydantic
``Create`` schema (``schemas/empresa.py::ResolucionFacturacionCreate`` in
T-PR4-02) server-assigns ``prefijo`` and the ``rango_desde`` / ``rango_hasta``
range — clients never supply them.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date

from sqlalchemy import BigInteger, Date, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class ResolucionFacturacion(VersionedBase):
    """[V] DIAN billing resolution per branch; cloud-only writes."""

    __tablename__ = "resolucion_facturacion"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    numero_resolucion: Mapped[str | None] = mapped_column(String, nullable=True)
    prefijo: Mapped[str | None] = mapped_column(String, nullable=True)
    rango_desde: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rango_hasta: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fecha_resolucion: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_inicio_vigencia: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin_vigencia: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "numero_resolucion",
            "vigente_desde",
            name="resolucion_facturacion_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["ResolucionFacturacion"]