"""HU-F1.5: thin async helper for ``prod.mv_ocupacion_diaria`` reads.

REQ-OPS-030: the single SQL JOIN that backs ``GET /operacion/ocupacion``.

Encapsulates:
  - the MV (``prod.mv_ocupacion_diaria``) -- count(*) by
    ``(uuid_sucursal, uuid_tipo_vehiculo)``;
  - the JOIN to ``prod.tipos_vehiculo`` for the human-readable
    ``tipo`` string;
  - the LEFT JOIN to ``prod.cantidad_vehiculos_sucursal`` for
    ``cupo_maximo`` (KD-6: may be NULL if admin has not configured
    capacity -- ``COALESCE`` resolves to 0, and ``disponible`` may be
    negative).

The encapsulation lets:
  - the test layer exercise the helper directly via DB fixtures
    without HTTP;
  - the endpoint (``api/v1/operacion.py::get_ocupacion``) stay thin
    (resolve ctx, call helper, wrap in ``OcupacionResponse``).

Bind params only (no string interpolation -- KD-1 SQL injection
hygiene). SQL is ``text(...)`` with SQLAlchemy parameter substitution.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class OcupacionItemRow:
    """Per-tipo row returned from the MV JOIN.

    Used internally by the repo helper; the endpoint wraps these into
    the pydantic ``schemas/operacion.OcupacionItem`` (no leakage of
    ORM types).
    """

    uuid_tipo_vehiculo: uuid_lib.UUID
    tipo: str
    cupo_maximo: int
    activos: int

    @property
    def disponible(self) -> int:
        """KD-6: ``cupo_maximo - activos``; may be negative when
        ``cantidad_vehiculos_sucursal`` is missing for the combo."""
        return self.cupo_maximo - self.activos


async def get_ocupacion_puros_activos(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> list[OcupacionItemRow]:
    """REQ-OPS-030: SELECT for the per-tipo breakdown.

    The endpoint MUST surface every ``tipos_vehiculo`` configured at
    the branch, even when no ``ingresos`` are active yet. The MV only
    emits rows when there is at least one active ingreso, so we
    LEFT JOIN the MV onto ``cantidad_vehiculos_sucursal`` (the
    configured-capacity table) — that table is the driver, the MV
    is optional.

    KD-6: ``cupo_maximo`` falls back to ``0`` when the branch has no
    ``cantidad_vehiculos_sucursal`` row for that tipo (admins might
    not have configured capacity yet), and ``disponible`` can be
    negative when ``activos > cupo_maximo``.

    KD-4: rows are ordered by ``tv.tipo`` for deterministic output
    across refreshes (the MV itself does not guarantee ordering).

    SQL (kept in sync with the migration's MV definition):

        SELECT
            tv.uuid                       AS uuid_tipo_vehiculo,
            tv.tipo                       AS tipo,
            COALESCE(cvs.cantidad, 0)     AS cupo_maximo,
            COALESCE(mv.activos, 0)       AS activos
        FROM prod.tipos_vehiculo tv
        LEFT JOIN prod.cantidad_vehiculos_sucursal cvs
          ON cvs.uuid_sucursal = :uuid_sucursal
         AND cvs.uuid_tipo_vehiculo = tv.uuid
         AND cvs.vigente_hasta IS NULL
        LEFT JOIN prod.mv_ocupacion_diaria mv
          ON mv.uuid_sucursal = :uuid_sucursal
         AND mv.uuid_tipo_vehiculo = tv.uuid
        WHERE tv.vigente_hasta IS NULL
        ORDER BY tv.tipo
    """
    stmt = text(
        """
        SELECT
            tv.uuid                       AS uuid_tipo_vehiculo,
            tv.tipo                       AS tipo,
            COALESCE(cvs.cantidad, 0)     AS cupo_maximo,
            COALESCE(mv.activos, 0)       AS activos
        FROM prod.tipos_vehiculo tv
        LEFT JOIN prod.cantidad_vehiculos_sucursal cvs
          ON cvs.uuid_sucursal = :uuid_sucursal
         AND cvs.uuid_tipo_vehiculo = tv.uuid
         AND cvs.vigente_hasta IS NULL
        LEFT JOIN prod.mv_ocupacion_diaria mv
          ON mv.uuid_sucursal = :uuid_sucursal
         AND mv.uuid_tipo_vehiculo = tv.uuid
        WHERE tv.vigente_hasta IS NULL
        ORDER BY tv.tipo
        """
    )
    rows = (await session.execute(stmt, {"uuid_sucursal": str(uuid_sucursal)})).all()
    return [
        OcupacionItemRow(
            uuid_tipo_vehiculo=r.uuid_tipo_vehiculo,
            tipo=r.tipo,
            cupo_maximo=r.cupo_maximo,
            activos=r.activos,
        )
        for r in rows
    ]


__all__ = [
    "OcupacionItemRow",
    "get_ocupacion_puros_activos",
]
