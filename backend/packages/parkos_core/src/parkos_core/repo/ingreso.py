"""HU-F1.6 -- repo surface for ``POST /operacion/ingresos`` validation chain.

Encapsulates the 8-step validation + ``crear_ingreso_evento`` write path
so the handler can stay thin (REQ-OPS-034..041, D-HU-F1.6-11 precedence
rules). KD-FORZADO-01 prefix contract lives here as
:data:`FORZADO_PREFIX` + :data:`FORZADO_MIN_MOTIVO_CHARS`.

R-A5 mitigation: this module RE-EXPORTS every validator from the other
``repo/*.py`` modules so the handler imports the full chain from a
single import surface (``parkos_core.repo.ingreso``).
"""
from __future__ import annotations

import uuid as uuid_lib
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.ingreso import Ingreso
from ..models.V.tipos_vehiculo import TiposVehiculo
from .alerta import insertar_alerta_forzado
from .event import record_event
from .ocupacion import validar_cupo_disponible
from .subscripcion_activa import validar_subscripcion_vigente
from .tarifas_vigencia import validar_tarifa_vigente

# Public constants (exported in __all__). KD-FORZADO-01 prefix + min motivo.
FORZADO_PREFIX = "[FORZADO: "
FORZADO_MIN_MOTIVO_CHARS = 10


async def validar_tipo_vehiculo_vigente(
    session: AsyncSession,
    *,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    forzado: bool = False,
) -> bool:
    """V4 (REQ-OPS-038): is ``uuid_tipo_vehiculo`` vigente at the DB?

    KD-V3: a forced ingreso NEVER bypasses catalog defects -- the tipo
    must be vigente in ``prod.tipos_vehiculo`` regardless of prefix.
    """
    stmt = (
        select(TiposVehiculo.uuid)
        .where(
            TiposVehiculo.uuid == uuid_tipo_vehiculo,
            TiposVehiculo.vigente_hasta.is_(None),
            TiposVehiculo.estado == "activo",
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row is not None


async def existe_ingreso_activo(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    placa: str,
) -> uuid_lib.UUID | None:
    """V8 (REQ-OPS-040): is there an active ingreso for ``(sucursal, placa)``?

    An ingreso is ACTIVE if it has no matching ``salidas`` row and no
    matching ``anulaciones`` row. KD-V4 / D-HU-F1.6-3 forbids pessimistic
    locks (`FOR UPDATE/SHARE`) from the endpoint -- we read with a
    plain ``EXISTS`` and rely on the unique partial index pre-F1.5 to
    keep the race surface narrow.
    """
    stmt = text(
        """
        SELECT EXISTS(
          SELECT 1
          FROM prod.ingreso i
          WHERE i.uuid_sucursal = :uuid_sucursal
            AND i.placa = :placa
            AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid)
            AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_ingreso = i.uuid)
        ) AS exists
        """
    )
    row = (
        await session.execute(
            stmt, {"uuid_sucursal": str(uuid_sucursal), "placa": placa}
        )
    ).first()
    if row is None or not row.exists:
        return None
    # Return the prior UUID so the caller can populate
    # ``uuid_ingreso_existente``. The EXISTS subquery loses identity;
    # re-select with a plain SELECT id to surface it.
    id_stmt = text(
        """
        SELECT i.uuid
        FROM prod.ingreso i
        WHERE i.uuid_sucursal = :uuid_sucursal
          AND i.placa = :placa
          AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid)
          AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_ingreso = i.uuid)
        LIMIT 1
        """
    )
    id_row = (
        await session.execute(
            id_stmt, {"uuid_sucursal": str(uuid_sucursal), "placa": placa}
        )
    ).first()
    return uuid_lib.UUID(id_row.uuid) if id_row is not None else None


def validar_kd_forzado(observaciones: str | None, forzado: bool) -> str | None:
    """KD-FORZADO-01: parse ``[FORZADO: <motivo>]`` from ``observaciones``.

    Three discriminators raise 422 HTTPException with a typed error:

    - ``forzado_contradiccion`` -- ``forzado=False`` but the prefix is
      present (the prefix alone is enough; ``forzado`` just toggles
      whether we extract or reject it).
    - ``motivo_forzado_requerido`` -- ``forzado=True`` but no prefix.
    - ``motivo_forzado_insuficiente`` -- motivo shorter than
      :data:`FORZADO_MIN_MOTIVO_CHARS`.

    Returns the stripped motivo (``>=10`` chars) on success, or ``None``
    if the prefix is absent and ``forzado=False``.
    """
    has_prefix = (
        observaciones is not None
        and FORZADO_PREFIX in observaciones
        and observaciones.rstrip().endswith("]")
    )
    if forzado and not has_prefix:
        raise HTTPException(
            status_code=422,
            detail={"error": "motivo_forzado_requerido"},
        )
    if not forzado and has_prefix:
        raise HTTPException(
            status_code=422,
            detail={"error": "forzado_contradiccion"},
        )
    if not has_prefix:
        return None
    # Extract motivo between prefix and trailing "]".
    start = observaciones.index(FORZADO_PREFIX) + len(FORZADO_PREFIX)
    end = observaciones.rindex("]")
    motivo = observaciones[start:end].strip()
    if len(motivo) < FORZADO_MIN_MOTIVO_CHARS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "motivo_forzado_insuficiente",
                "min_chars": FORZADO_MIN_MOTIVO_CHARS,
            },
        )
    return motivo


async def crear_ingreso_evento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict[str, Any],
) -> Ingreso:
    """Thin wrapper around :func:`repo.event.record_event` for ``Ingreso``.

    KD-V4 / REQ-30 / REQ-33: the ONLY allowed write path on the [L-E]
    ``ingreso`` table. The AST walk
    ``tests/static/test_no_write_after_insert.py`` (T6.1) rejects any
    ``UPDATE|DELETE|TRUNCATE|MERGE|FOR UPDATE|FOR SHARE`` literal in
    this module (defense in depth, R-A3 mitigation).
    """
    return await record_event(
        session,
        Ingreso,
        actor_uuid=actor_uuid,
        new_attrs=new_attrs,
        log_tx=True,
    )


__all__ = [
    "FORZADO_MIN_MOTIVO_CHARS",
    "FORZADO_PREFIX",
    "crear_ingreso_evento",
    "existe_ingreso_activo",
    "insertar_alerta_forzado",
    "validar_cupo_disponible",
    "validar_kd_forzado",
    "validar_subscripcion_vigente",
    "validar_tarifa_vigente",
    "validar_tipo_vehiculo_vigente",
]
