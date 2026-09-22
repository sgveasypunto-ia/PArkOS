"""HU-F11.x (REQ-OPS-200) — tipos_vehiculo subset para ingreso con override.

Filtra ``prod.tipos_vehiculo`` a las filas cuyo ``tipo`` aparece como
sufijo de al menos un ``prod.tipo_subscripciones`` vigente. El operador
usa este subset como dropdown para override del tipo detectado por regex
en :class:`IngresoPanel`.

No hay FK directo entre ``tipo_subscripciones`` y ``tipos_vehiculo`` en
el modelo (verificado en ``modelo_datos_er.mmd``: ``tipo_subscripciones``
solo FK-a ``subscripciones_cliente``). El link es IMPLÍCITO por
convención del string ``tipo_subscripciones.tipo``:
  - MENSUAL_AUTO / BIMESTRAL_AUTO / TRIMESTRAL_AUTO → 'AUTO' → 'carro'
  - MENSUAL_MOTO → 'MOTO' → 'moto'
  - MENSUAL_EMPRESA → 'EMPRESA' → mixed (ignorar, no es un vehicle type)

PRAGMÁTICO. Si en el futuro se agrega un FK ``uuid_tipo_vehiculo`` a
``tipo_subscripciones`` (o junction table), esta función debería
preferir el FK y caer al parseo solo cuando el FK es NULL.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.tipo_subscripciones import TipoSubscripciones
from ..models.V.tipos_vehiculo import TiposVehiculo


def _suffix_to_tipo_vehiculo(suffix: str) -> str | None:
    """Map ``tipo_subscripciones.tipo`` suffix → ``tipos_vehiculo.tipo``.

    Returns ``None`` for suffixes that don't correspond to a vehicle type
    (e.g. ``EMPRESA``, ``DAILY``). Case-insensitive: 'AUTO' y 'auto'
    ambos → 'carro'.
    """
    suffix_lower = suffix.strip().lower()
    # Convention table — keep narrow. Future FK override should bypass.
    if suffix_lower == "auto":
        return "carro"
    if suffix_lower == "moto":
        return "moto"
    # bicicleta / patineta no tienen plans en el seed actual.
    return None


async def get_tipos_vehiculo_con_subscripcion(
    session: AsyncSession,
) -> list[TiposVehiculo]:
    """Vigentes ``prod.tipos_vehiculo`` cuyo ``tipo`` está cubierto por al
    menos un ``prod.tipo_subscripciones`` vigente (parsing del sufijo del
    string ``tipo`` del plan).

    Devuelve las filas completas de ``TiposVehiculo`` (uuid + tipo +
    vigente_desde + ...) ordenadas por el orden natural del catálogo.
    NO devuelve [] cuando no hay subscripciones — devuelve lo que haya
    en el catálogo (defensa contra operador offline / catálogo sin sync).
    """
    # 1) Fetch vigente subscription plans (no per-sucursal: tipo_subscripciones
    # es catálogo global, no tiene uuid_sucursal).
    plan_stmt = select(TipoSubscripciones.tipo).where(
        TipoSubscripciones.vigente_hasta.is_(None),
        TipoSubscripciones.estado == "activo",
        TipoSubscripciones.tipo.is_not(None),
    )
    plan_rows = (await session.execute(plan_stmt)).scalars().all()

    # 2) Derive the set of vehicle-tipos covered by those plans.
    covered_tipos: set[str] = set()
    for plan_tipo in plan_rows:
        if plan_tipo is None:
            continue
        # Convention: <PERIOD>_<VEHICLE_TYPE>. Take last segment after '_'.
        last_segment = plan_tipo.rsplit("_", 1)[-1]
        mapped = _suffix_to_tipo_vehiculo(last_segment)
        if mapped is not None:
            covered_tipos.add(mapped)

    if not covered_tipos:
        # Fallback defensivo: si no hay plans parseables (catálogo
        # corrupto / branch sin sync), devolvemos el catálogo vigente
        # completo. El operador puede overridear — el server igual
        # rechaza con 422 si el tipo no tiene cupo/tarifa.
        fallback_stmt = select(TiposVehiculo).where(
            TiposVehiculo.vigente_hasta.is_(None),
            TiposVehiculo.estado == "activo",
        )
        rows = (await session.execute(fallback_stmt)).scalars().all()
        return list(rows)

    # 3) Query the canonical tipos_vehiculo for those tipos.
    stmt = (
        select(TiposVehiculo)
        .where(
            TiposVehiculo.tipo.in_(covered_tipos),
            TiposVehiculo.vigente_hasta.is_(None),
            TiposVehiculo.estado == "activo",
        )
        .order_by(TiposVehiculo.tipo)
    )
    return list((await session.execute(stmt)).scalars().all())


__all__ = ["get_tipos_vehiculo_con_subscripcion"]