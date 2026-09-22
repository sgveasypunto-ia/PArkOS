"""ORM model for ``prod.ingreso_consecutivo_contador`` (REQ-OPS-193, design §3.1).

51st ``[A]``-class table. Per-``(uuid_sucursal, uuid_tipo_vehiculo)`` monotonic
counter for ``prod.ingreso.consecutivo`` (the parking-lot identifier for
ingresos sin placa -- bicicleta, patineta). Defense in depth via:

  * ``REVOKE UPDATE, DELETE`` from ``rol_app`` -- migration 0042.
  * ``BEFORE UPDATE OR DELETE`` trigger carve-out that only permits UPDATE
    on ``(ultimo_consecutivo, last_event_uuid, sync_status, sync_timestamp,
    sync_attempts)`` -- all other columns are byte-identical to OLD on
    UPDATE; DELETE is unconditionally rejected.

Bi-temporal UK mirrors the [V] convention: ``(uuid_sucursal,
uuid_tipo_vehiculo, vigente_desde)`` -- version is part of identity.
Closing a version requires close-then-insert (AGENTS.md §2). An UPDATE
on the vigente row is the operational carve-out path (advancing the
counter) and is permitted by the trigger.

Counter rows are local-only per branch. No ``fn_enqueue_sync`` trigger is
attached at the DB layer -- the counter is operational state, never
replicated to the cloud.

NOT partitioned: counters are bounded at ``O(branches x tipos) ~ 100s``.
``pg_partman`` would add overhead for no gain.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class IngresoConsecutivoContador(AppendOnlyBase):
    """[A] Per-``(uuid_sucursal, uuid_tipo_vehiculo)`` ``ingreso.consecutivo`` counter."""

    __tablename__ = "ingreso_consecutivo_contador"

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    uuid_tipo_vehiculo: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )
    ultimo_consecutivo: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    last_event_uuid: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        # CHECK constraint is declared here so SQLAlchemy-aware tools
        # (e.g. ``alembic check``) can introspect it. The bi-temporal UK
        # ``UNIQUE (uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)``
        # lives at the DB layer (migration 0042) -- declared there, not
        # here, because declarative ``UniqueConstraint`` referring to the
        # ``vigente_desde`` mixin column triggers an "unknown column"
        # error during mapper configuration (mixin columns are visible
        # only AFTER the declarative machinery has finished assembling the
        # table). The same precedent is followed by other [A] subclasses
        # like ``idempotency_keys``: UKs are migration-side.
        CheckConstraint(
            "ultimo_consecutivo >= 0 AND ultimo_consecutivo < 1000000",
            name="ck_ingreso_consecutivo_contador_range",
        ),
        {"schema": "prod", "extend_existing": True},
    )


__all__ = ["IngresoConsecutivoContador"]