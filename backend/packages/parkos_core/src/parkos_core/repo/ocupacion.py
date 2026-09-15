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
    "CupoValidationResult",
    "OcupacionItemRow",
    "get_ocupacion_puros_activos",
    "validar_cupo_disponible",
]


# ---------------------------------------------------------------------------
# HU-F1.6 -- V1+V2 validation (REQ-OPS-034/035) on top of the F1.5 MV.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CupoValidationResult:
    """Outcome of :func:`validar_cupo_disponible`.

    Discriminators:

    - ``cupo_no_configurado=True`` (V1): the branch has no
      ``cantidad_vehiculos_sucursal`` row for ``uuid_tipo_vehiculo``
      (``cupo_maximo=0``) -- 422 ``cupo_no_configurado`` (bypass permitted).
    - ``cupo_agotado=True`` (V2): ``activos >= cupo_maximo`` AND
      ``forzado=False`` -- 422 ``motivo_forzado_requerido``.
    - Both flags ``False``: cup available (proceed).
    """

    cupo_no_configurado: bool
    cupo_agotado: bool
    cupo_maximo: int
    activos: int

    @classmethod
    def ok(cls, *, cupo_maximo: int, activos: int) -> CupoValidationResult:
        return cls(
            cupo_no_configurado=False,
            cupo_agotado=False,
            cupo_maximo=cupo_maximo,
            activos=activos,
        )


async def validar_cupo_disponible(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    forzado: bool = False,
) -> CupoValidationResult:
    """V1+V2 (REQ-OPS-034/035): enough cup to accept a new ingreso?

    Reads :func:`get_ocupacion_puros_activos` (F1.5) and narrows to
    the row matching ``uuid_tipo_vehiculo``. KD-V4 (RIESCO-SUC-02):
    eventual consistency via MV; lag <= 10s accepted as live risk.

    KD-V8: KD-FORZADO chain may BYPASS a V2 agotado; the helper returns
    ``cupo_agotado=False`` in that case so the handler proceeds to
    INSERT. Caller is responsible for raising the alerta INSERT.
    """
    items = await get_ocupacion_puros_activos(session, uuid_sucursal=uuid_sucursal)
    match: OcupacionItemRow | None = next(
        (it for it in items if it.uuid_tipo_vehiculo == uuid_tipo_vehiculo),
        None,
    )
    if match is None:
        # No tipo registered at all -- treat as V1 (no config).
        return CupoValidationResult(
            cupo_no_configurado=True,
            cupo_agotado=False,
            cupo_maximo=0,
            activos=0,
        )
    if match.cupo_maximo == 0:
        return CupoValidationResult(
            cupo_no_configurado=True,
            cupo_agotado=False,
            cupo_maximo=0,
            activos=match.activos,
        )
    if match.activos >= match.cupo_maximo and not forzado:
        return CupoValidationResult(
            cupo_no_configurado=False,
            cupo_agotado=True,
            cupo_maximo=match.cupo_maximo,
            activos=match.activos,
        )
    return CupoValidationResult.ok(
        cupo_maximo=match.cupo_maximo,
        activos=match.activos,
    )
