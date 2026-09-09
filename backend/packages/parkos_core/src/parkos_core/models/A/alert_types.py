"""ORM model for ``prod.alert_types`` (T-PR8-002, design §2 Issue #6).

Deploy-seeded registry of valid ``tipo_alerta`` identifiers — out-of-catalog
(``catalog/out_of_catalog.py::OUT_OF_CATALOG``), never enters the sync
pipeline. Business-key PK (``tipo_alerta``), not a ``uuid`` surrogate — this
is the first table in the schema shaped this way: ``alert_types`` members
are referenced by identifier in Python source, so a new one already ships
with a deploy (design.md §2 Issue #6), unlike an operator-editable catalog
that needs a surrogate key to reach the branch without one.

:func:`parkos_core.repo.alert_types.validate` is the read-side guard; the
seed (idempotent, both cloud and branch) ships in this table's own
migration (``0013_add_alert_types.py``) plus the standalone
``infra/scripts/seed_alert_types.py`` operational script.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class AlertTypes(Base):
    """Registry row — one valid ``tipo_alerta`` identifier + its severity.

    Composes ``AuditMixin``/``SyncMixin``-equivalent columns directly
    (rather than inheriting :class:`AppendOnlyBase`) because that base's
    :class:`IdMixin` forces a ``uuid`` primary key, which this table does
    not have (see module docstring).
    """

    __tablename__ = "alert_types"

    tipo_alerta: Mapped[str] = mapped_column(String, primary_key=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(length=16), nullable=False)

    # --- Audit + sync columns (AGENTS.md: "every model has created_at,
    # created_by, ..., sync_status/sync_timestamp/sync_attempts") ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("NOW()"),
    )
    created_by: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    sync_status: Mapped[str | None] = mapped_column(
        String(length=16),
        nullable=True,
        server_default="pendiente",
    )
    sync_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    sync_attempts: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        server_default="0",
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="alert_types_severity_check",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["AlertTypes"]
