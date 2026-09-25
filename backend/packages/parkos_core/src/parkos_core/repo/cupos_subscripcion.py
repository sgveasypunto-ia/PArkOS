"""parkos_core.repo.cupos_subscripcion -- HU-F9.2 realineada (gestión de
cupos de una suscripción ya vendida, dentro del Sheet de sucursal).

Distinto de :mod:`repo.venta_suscripcion` (que cubre la VENTA atómica de
una suscripción nueva): este módulo cubre el ciclo de vida DESPUÉS de la
venta -- listar activas, buscar por identificación del cliente, y
agregar/quitar vehículos inscritos uno a la vez. Reutiliza los
validadores V5/V6 (``mismo_tipo_vehiculo`` / ``cantidad_maxima_vehiculos``)
y el helper de lookup-or-create de vehículo de ``repo.venta_suscripcion``
en vez de duplicarlos.

Tenant scoping: ``prod.subscripciones_cliente`` tiene ``uuid_sucursal`` y
por lo tanto queda auto-filtrada por sucursal vía el listener de
``db/tenancy.py`` (``ContextVar`` seteado en ``get_tenant_ctx``) -- estas
queries NO agregan un ``WHERE uuid_sucursal`` manual porque ya está
aplicado a nivel de sesión. ``prod.clientes`` NO tiene ``uuid_sucursal``
(catálogo global) -- la búsqueda por ``numero_identificacion`` es
correctamente branch-agnostic; lo que SÍ queda scoped a la sucursal
actual es la suscripción activa de ese cliente.

Este módulo NUNCA llama ``session.commit()`` (mismo invariante KD-VENTA-01
que ``repo.venta_suscripcion`` -- el handler es el único punto de commit).
"""

from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.clientes import Clientes
from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ..models.V.subscripciones_cliente import SubscripcionesCliente
from ..models.V.tipo_subscripciones import TipoSubscripciones
from ..models.V.vehiculos import Vehiculos
from . import versioned

__all__ = [
    "SubscripcionActivaRow",
    "SubscripcionConVehiculos",
    "SubscripcionNoEncontradaError",
    "VehiculoInscritoRow",
    "VehiculoYaInscritoError",
    "agregar_vehiculo_a_subscripcion",
    "buscar_subscripcion_activa_por_identificacion",
    "buscar_subscripcion_con_vehiculos_por_uuid",
    "listar_subscripciones_activas",
    "quitar_vehiculo_de_subscripcion",
]


class SubscripcionNoEncontradaError(Exception):
    """404 discriminator -- no vigente+activa ``subscripciones_cliente`` en esta sucursal."""

    def __init__(self, *, detalle: str) -> None:
        self.detalle = detalle
        super().__init__(f"subscripcion_no_encontrada: {detalle}")


class VehiculoYaInscritoError(Exception):
    """409 discriminator -- la placa ya está inscrita (vigente) en esta suscripción."""

    def __init__(self, *, placa: str) -> None:
        self.placa = placa
        super().__init__(f"vehiculo_ya_inscrito: placa={placa}")


@dataclass(frozen=True)
class SubscripcionActivaRow:
    """Una fila del listado de suscripciones activas + su conteo de inscritos."""

    subscripcion: SubscripcionesCliente
    cliente: Clientes
    plan: TipoSubscripciones
    vehiculos_inscritos: int


@dataclass(frozen=True)
class VehiculoInscritoRow:
    """Un vehículo inscrito vigente, con el uuid de la fila-junction."""

    uuid_subscripcion_vehiculo: uuid_lib.UUID
    vehiculo: Vehiculos


@dataclass(frozen=True)
class SubscripcionConVehiculos:
    """Detalle completo de una suscripción + sus vehículos inscritos vigentes."""

    subscripcion: SubscripcionesCliente
    cliente: Clientes
    plan: TipoSubscripciones
    vehiculos: list[VehiculoInscritoRow]


def _cupo_disponible(*, cupo_maximo: int | None, inscritos: int) -> int | None:
    if cupo_maximo is None:
        return None
    return max(cupo_maximo - inscritos, 0)


async def listar_subscripciones_activas(
    session: AsyncSession,
) -> list[SubscripcionActivaRow]:
    """Listado branch-scoped de suscripciones activas (paso 1 del Sheet).

    Predicado bi-temporal (mismo criterio que
    ``repo.subscripcion_activa.validar_subscripcion_vigente``):
    ``vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >= hoy``.
    El tenant scoping de ``uuid_sucursal`` lo aplica automáticamente el
    listener de ``db/tenancy.py`` -- no se filtra a mano acá.
    """
    hoy = datetime.now(UTC).date()

    conteo_subq = (
        select(
            SubscripcionVehiculos.uuid_subscripcion_cliente.label("uuid_subscripcion"),
            func.count(SubscripcionVehiculos.uuid).label("n_inscritos"),
        )
        .where(
            SubscripcionVehiculos.vigente_hasta.is_(None),
            SubscripcionVehiculos.estado == "activo",
        )
        .group_by(SubscripcionVehiculos.uuid_subscripcion_cliente)
        .subquery()
    )

    stmt = (
        select(SubscripcionesCliente, Clientes, TipoSubscripciones, conteo_subq.c.n_inscritos)
        .join(Clientes, Clientes.uuid == SubscripcionesCliente.uuid_cliente)
        .join(
            TipoSubscripciones,
            TipoSubscripciones.uuid == SubscripcionesCliente.uuid_tipo_subscripcion,
        )
        .outerjoin(
            conteo_subq,
            conteo_subq.c.uuid_subscripcion == SubscripcionesCliente.uuid,
        )
        .where(
            SubscripcionesCliente.vigente_hasta.is_(None),
            SubscripcionesCliente.estado == "activo",
            SubscripcionesCliente.fecha_vencimiento >= hoy,
            Clientes.vigente_hasta.is_(None),
            TipoSubscripciones.vigente_hasta.is_(None),
        )
        .order_by(SubscripcionesCliente.fecha_vencimiento.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        SubscripcionActivaRow(
            subscripcion=subscripcion,
            cliente=cliente,
            plan=plan,
            vehiculos_inscritos=n_inscritos or 0,
        )
        for subscripcion, cliente, plan, n_inscritos in rows
    ]


async def _vehiculos_inscritos_de(
    session: AsyncSession, *, uuid_subscripcion_cliente: uuid_lib.UUID
) -> list[VehiculoInscritoRow]:
    stmt = (
        select(SubscripcionVehiculos, Vehiculos)
        .join(Vehiculos, Vehiculos.uuid == SubscripcionVehiculos.uuid_vehiculo)
        .where(
            SubscripcionVehiculos.uuid_subscripcion_cliente == uuid_subscripcion_cliente,
            SubscripcionVehiculos.vigente_hasta.is_(None),
            SubscripcionVehiculos.estado == "activo",
            Vehiculos.vigente_hasta.is_(None),
        )
        .order_by(Vehiculos.placa.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [VehiculoInscritoRow(uuid_subscripcion_vehiculo=sv.uuid, vehiculo=v) for sv, v in rows]


async def buscar_subscripcion_activa_por_identificacion(
    session: AsyncSession, *, numero_identificacion: str
) -> SubscripcionConVehiculos | None:
    """Busca la suscripción activa (en esta sucursal) del cliente con ese
    número de identificación. ``None`` si el cliente no existe o no tiene
    una suscripción activa en la sucursal actual (estado vacío, no error).
    """
    hoy = datetime.now(UTC).date()
    stmt = (
        select(SubscripcionesCliente, Clientes, TipoSubscripciones)
        .join(Clientes, Clientes.uuid == SubscripcionesCliente.uuid_cliente)
        .join(
            TipoSubscripciones,
            TipoSubscripciones.uuid == SubscripcionesCliente.uuid_tipo_subscripcion,
        )
        .where(
            Clientes.numero_identificacion == numero_identificacion,
            Clientes.vigente_hasta.is_(None),
            SubscripcionesCliente.vigente_hasta.is_(None),
            SubscripcionesCliente.estado == "activo",
            SubscripcionesCliente.fecha_vencimiento >= hoy,
            TipoSubscripciones.vigente_hasta.is_(None),
        )
        .order_by(SubscripcionesCliente.vigente_desde.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    subscripcion, cliente, plan = row
    vehiculos = await _vehiculos_inscritos_de(session, uuid_subscripcion_cliente=subscripcion.uuid)
    return SubscripcionConVehiculos(
        subscripcion=subscripcion, cliente=cliente, plan=plan, vehiculos=vehiculos
    )


async def buscar_subscripcion_con_vehiculos_por_uuid(
    session: AsyncSession, *, uuid_subscripcion_cliente: uuid_lib.UUID
) -> SubscripcionConVehiculos:
    """Variante por uuid (usada tras agregar/quitar, para refrescar el detalle).

    Raises :class:`SubscripcionNoEncontradaError` si no hay una fila
    vigente+activa con ese uuid en la sucursal actual (branch-scoped por
    el listener de tenancy).
    """
    stmt = (
        select(SubscripcionesCliente, Clientes, TipoSubscripciones)
        .join(Clientes, Clientes.uuid == SubscripcionesCliente.uuid_cliente)
        .join(
            TipoSubscripciones,
            TipoSubscripciones.uuid == SubscripcionesCliente.uuid_tipo_subscripcion,
        )
        .where(
            SubscripcionesCliente.uuid == uuid_subscripcion_cliente,
            SubscripcionesCliente.vigente_hasta.is_(None),
            TipoSubscripciones.vigente_hasta.is_(None),
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise SubscripcionNoEncontradaError(
            detalle=f"uuid_subscripcion_cliente={uuid_subscripcion_cliente}"
        )
    subscripcion, cliente, plan = row
    vehiculos = await _vehiculos_inscritos_de(session, uuid_subscripcion_cliente=subscripcion.uuid)
    return SubscripcionConVehiculos(
        subscripcion=subscripcion, cliente=cliente, plan=plan, vehiculos=vehiculos
    )


async def agregar_vehiculo_a_subscripcion(
    session: AsyncSession,
    *,
    uuid_subscripcion_cliente: uuid_lib.UUID,
    placa: str,
    actor_uuid: uuid_lib.UUID,
) -> SubscripcionVehiculos:
    """Inscribe un vehículo nuevo en una suscripción existente.

    Caller (el handler) es responsable de correr ANTES las validaciones
    V5 (``validar_placas_mismo_tipo_vehiculo``) y V6
    (``validar_cantidad_maxima_vehiculos``) de ``repo.venta_suscripcion``
    -- este helper asume que ya pasaron y solo hace el INSERT bajo el
    mismo ``pg_advisory_xact_lock`` que la venta atómica (REQ-OP-08).

    Raises :class:`VehiculoYaInscritoError` si la placa ya está inscrita
    (vigente) en esta misma suscripción.
    """
    from . import venta_suscripcion as repo_venta

    vehiculo, _was_created = await repo_venta.buscar_o_crear_vehiculo_por_placa(
        session, placa=placa, actor_uuid=actor_uuid
    )

    ya_inscrito_stmt = select(SubscripcionVehiculos).where(
        SubscripcionVehiculos.uuid_subscripcion_cliente == uuid_subscripcion_cliente,
        SubscripcionVehiculos.uuid_vehiculo == vehiculo.uuid,
        SubscripcionVehiculos.vigente_hasta.is_(None),
        SubscripcionVehiculos.estado == "activo",
    )
    ya_inscrito = (await session.execute(ya_inscrito_stmt)).scalar_one_or_none()
    if ya_inscrito is not None:
        raise VehiculoYaInscritoError(placa=placa)

    nuevas = await repo_venta.crear_subscripcion_vehiculos_bulk(
        session,
        actor_uuid=actor_uuid,
        uuid_subscripcion_cliente=uuid_subscripcion_cliente,
        uuid_vehiculos=[vehiculo.uuid],
    )
    return nuevas[0]


async def quitar_vehiculo_de_subscripcion(
    session: AsyncSession,
    *,
    uuid_subscripcion_vehiculo: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
) -> SubscripcionVehiculos:
    """Da de baja un vehículo inscrito -- ``close_and_insert`` bi-temporal
    con ``estado='inactivo'`` (nunca DELETE).

    Solo pasa ``new_attrs={"estado": "inactivo"}`` -- ``close_and_insert``
    carga el resto de columnas (``uuid_subscripcion_cliente``,
    ``uuid_vehiculo``) desde la fila vigente que cierra (ver
    ``repo/versioned.py``), así que no hace falta resenviarlas.

    Propaga ``versioned.RowNotFoundError`` si ``uuid_subscripcion_vehiculo``
    no matchea ninguna fila vigente (el handler la mapea a 404).
    """
    return await versioned.close_and_insert(
        session,
        SubscripcionVehiculos,
        current_uuid=uuid_subscripcion_vehiculo,
        new_attrs={"estado": "inactivo"},
        actor_uuid=actor_uuid,
    )
