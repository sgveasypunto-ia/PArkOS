"""HU-F1.6 / REQ-OPS-041.C — alerta INSERT for ``capacidad_agotada_forzado``.

Encapsulates the JSON payload shape for the alerta INSERT that fires
when a cupo-bypass is granted (KD-FORZADO-01 + bypass_reason ==
"cupo_agotado"). The motivo and ``uuid_ingreso`` are stored in the
dedicated ``datos_nuevos`` JSONB column added by migration 0025
(R-A2 mitigation).

Caller commits (same TX as the ingreso INSERT, R5 mitigation). The
helper calls ``await session.flush()`` so ``alerta.uuid`` (a DB-side
default) is populated before the caller continues.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_W.alerta import Alerta


async def insertar_alerta_forzado(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    motivo: str,
) -> Alerta:
    """Insert ``prod.alerta`` row with ``tipo_alerta='capacidad_agotada_forzado'``.

    Same TX as the ingreso INSERT (caller commits, R5 mitigation).
    The motivo is stored in the JSONB ``datos_nuevos`` column
    (added in migration 0025).

    Returns:
        The newly constructed ``Alerta`` row (not yet committed).
        The caller is responsible for ``await session.commit()`` so the
        alerta commits atomically with the ingreso INSERT.
    """
    alerta = Alerta(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=actor_uuid,
        tipo_alerta="capacidad_agotada_forzado",
        estado="abierta",
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
        uuid_arqueo=None,
        datos_nuevos={"motivo": motivo, "uuid_ingreso": str(uuid_ingreso)},
    )
    session.add(alerta)
    await session.flush()  # so uuid is populated before the caller continues
    return alerta


__all__ = ["insertar_alerta_forzado"]