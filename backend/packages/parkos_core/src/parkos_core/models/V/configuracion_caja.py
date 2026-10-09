"""ORM model for ``prod.configuracion_caja`` ([V] table, HU-F13.3).

Maps 1:1 to the migration in ``0066_add_configuracion_caja.py``. Bi-temporal
close+insert (REQ-04, REQ-05): writes go through
``repo.versioned.close_and_insert``.

Explicit ER exception (DEC-ADM-12), same shape as its two siblings
``ConfiguracionTolerancias`` / ``ConfiguracionSeguridad``:
``uuid_sucursal`` (PG_UUID, nullable — NULL means global default),
``base_inicial_sugerida`` (Numeric(18,4)), ``redondeo`` (string enum
validated at the Pydantic edge, not here), ``denominaciones_permitidas``
(JSONB array of ints, UI-validated).

``base_inicial_sugerida`` is the base de caja every shift of the branch opens
with (the operator does not type it). ``POST /caja-sesion/sesiones`` resolves it
server-side (branch override, then global default) and records it in
``sesion.valor_inicial_efectivo`` -- the column stays the source of truth for
each shift, so changing the parameter never alters a shift already open. The
row is cloud-authored and travels ``cloud_to_branch`` through the sync catalog
(migration 0099). ``valor_inicial_datafono`` always starts at 0.

BR2: the descuadre alert threshold already lives in
``configuracion_tolerancias.tolerancia_efectivo`` / ``tolerancia_datafono``
— not duplicated here.

Override resolution pattern (REQ-OP-12 + SC-OP-06): ``uuid_sucursal IS NULL``
row is the global default; a non-null row is the per-branch override. The
custom ``GET /configuracion-caja/efectiva`` route picks the override if
present, otherwise falls back to the global default.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import VersionedBase


class ConfiguracionCaja(VersionedBase):
    """[V] Cash-box config (base inicial sugerida, redondeo, denominaciones);
    global default + per-branch override."""

    __tablename__ = "configuracion_caja"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    base_inicial_sugerida: Mapped[float | None] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    redondeo: Mapped[str | None] = mapped_column(
        String(length=16),
        nullable=True,
    )
    denominaciones_permitidas: Mapped[list[int] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "uuid_sucursal",
            "vigente_desde",
            name="configuracion_caja_uk01",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["ConfiguracionCaja"]
