"""ORM model for ``prod.factura_electronica`` (DIAN invoice [L-E], PR6; branch-local numbering since T-PR9-002, D1-rev).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 875-891).

**D1-rev correction (T-PR9-002).** The BRANCH is the authoring side: it
inserts this row locally (``repo.event.record_event``, via
``repo.resolucion_facturacion.assign_consecutivo`` for the ``consecutivo``
allocation), offline-capable, then it replicates ``branch_to_cloud``
through the ordinary sync catalog entry (``sync/catalog/entries/
sync_entries_le.py``). The cloud only VALIDATES the received
``consecutivo`` falls inside the resolution's authorized range
(``dian/cloud/dispatcher.py::validate_consecutivo_range``, T-PR9-003) and
forwards to the DIAN provider \u2014 it never assigns the number.

This supersedes the prior (D1-original) claim that only ``api_admin``
writes here via ``dian/cloud_router.py``'s ``SELECT ... FOR UPDATE`` +
atomic ``consecutivo++`` (``dian/cloud/atomic_next_consecutivo.py``).
That cloud-side endpoint still exists and is still live (out of PR9's
scope to remove \u2014 see the PR9 apply report), but it is NOT the branch's
numbering path; the two do not share the same call path.

The UK ``(uuid_resolucion_facturacion, consecutivo)`` enforces uniqueness
inside a ``resolucion_facturacion``'s range \u2014 the DIAN ``numero_oficial``
invariant, now enforced on INSERT (the UK) rather than relied upon solely
via the allocator's own MAX()+1 read.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import BigInteger, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import LifecycleEventBase


class FacturaElectronica(LifecycleEventBase):
    """[L-E] DIAN official invoice event (cloud-only, REQ-30, REQ-34, REQ-35)."""

    __tablename__ = "factura_electronica"

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_factura: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_resolucion_facturacion: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    prefijo: Mapped[str | None] = mapped_column(String, nullable=True)
    consecutivo: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    descuento: Mapped[float | None] = mapped_column(Numeric(precision=18, scale=4), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "uuid_resolucion_facturacion",
            "consecutivo",
            name="factura_electronica_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["FacturaElectronica"]