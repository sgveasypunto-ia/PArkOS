"""repo/subscripcion_vinculos.py -- keep plate links with the live subscription version.

``subscripciones_cliente.uuid`` identifies a *version*: a generic update
(``PUT /subscripciones-cliente/{uuid}``) is a bi-temporal close+insert that mints
a NEW uuid, while the ``subscripcion_vehiculos`` links ([V]) keep pointing at the
CLOSED version. The active version would then show no plates: renewal answers
``suscripcion_sin_vehiculos``, vehicle counts drop and the plate lookup / duplicate
checks stop seeing the plates.

:func:`trasladar_vinculos_abiertos` re-creates the open links on the new version
(close old link, insert new one, same vehicle and state) in the caller's
transaction -- the same pattern ``repo.renovacion`` uses. It is deliberately
NOT inside ``versioned.close_and_insert``: that helper also applies remote sync
rows, and the origin node already replicates its own link close/insert rows, so
moving links there as well would double-apply them.
"""

from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ..models.V.subscripciones_cliente import SubscripcionesCliente


async def trasladar_vinculos_abiertos(
    session: AsyncSession,
    *,
    old_uuid: uuid_lib.UUID,
    new_row: SubscripcionesCliente,
    actor_uuid: uuid_lib.UUID,
) -> list[SubscripcionVehiculos]:
    """Move the open links of ``old_uuid`` to ``new_row.uuid`` (no physical DELETE)."""
    new_uuid = new_row.uuid
    if new_uuid == old_uuid:
        return []
    abiertos = (
        (
            await session.execute(
                select(SubscripcionVehiculos)
                .where(
                    SubscripcionVehiculos.uuid_subscripcion_cliente == old_uuid,
                    SubscripcionVehiculos.vigente_hasta.is_(None),
                )
                .order_by(SubscripcionVehiculos.created_at.asc())
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if not abiertos:
        return []

    # Same boundary as the new subscription version: closed links end where the new ones open.
    ahora = new_row.vigente_desde
    snapshot = [(link.uuid, link.uuid_vehiculo, link.estado) for link in abiertos]
    for link_uuid, _veh, _estado in snapshot:
        await session.execute(
            update(SubscripcionVehiculos)
            .where(
                SubscripcionVehiculos.uuid == link_uuid,
                SubscripcionVehiculos.vigente_hasta.is_(None),
            )
            .values(vigente_hasta=ahora, estado="inactivo")
        )
    nuevos: list[SubscripcionVehiculos] = []
    for _link_uuid, uuid_vehiculo, estado in snapshot:
        nuevo = SubscripcionVehiculos(
            uuid_subscripcion_cliente=new_uuid,
            uuid_vehiculo=uuid_vehiculo,
            vigente_desde=ahora,
            vigente_hasta=None,
            estado=estado,
            created_at=new_row.created_at,
            created_by=actor_uuid,
        )
        session.add(nuevo)
        nuevos.append(nuevo)
    await session.flush()
    return nuevos


async def after_update_subscripcion(
    session: AsyncSession,
    *,
    old_uuid: uuid_lib.UUID,
    new_row: SubscripcionesCliente,
    actor_uuid: uuid_lib.UUID,
) -> None:
    """``make_router(after_update=...)`` adapter for ``subscripciones-cliente``."""
    await trasladar_vinculos_abiertos(
        session, old_uuid=old_uuid, new_row=new_row, actor_uuid=actor_uuid
    )


__all__ = ["after_update_subscripcion", "trasladar_vinculos_abiertos"]
