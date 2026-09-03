"""ORM model for ``prod.documentos`` ([V] table, PR4).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 343-355).
Bi-temporal close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

The 4 business columns mirror the ER ``documentos`` block exactly:
``uuid_sucursal`` (PG_UUID), ``tipo`` (String), ``formato`` (String),
``documento_b64`` (Text). The 1MB cap on ``documento_b64`` is enforced at the
Pydantic boundary (``schemas/empresa.py::DocumentosCreate`` in T-PR4-02), not
in the ORM layer. No UK constraint — the table has no uniqueness invariant
beyond PK.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class Documentos(VersionedBase):
    """[V] Administrative files of a branch (logos, templates) inlined as base64."""

    __tablename__ = "documentos"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    formato: Mapped[str | None] = mapped_column(String, nullable=True)
    documento_b64: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Documentos"]