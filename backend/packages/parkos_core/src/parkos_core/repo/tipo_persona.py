"""HU-F9.1/F8.1 (Ajuste identificación persona natural/empresa) --
shared resolver mapping ``clientes.tipo_identificador`` to the vigente
``tipo_persona`` catalog row.

DIAN document types map deterministically to persona type: ``NIT`` is
always a persona jurídica; ``CC``/``CE``/``pasaporte`` are always a
persona natural (``.mmd`` ``clientes.apellido``: "vacío para persona
jurídica" confirms the same split). Centralized here so every cliente
creation path (venta de suscripción today; factura con datos propios
once it starts auto-creando clientes) resolves the same way instead of
re-deriving the mapping inline.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.tipo_persona import TipoPersona

_TIPO_JURIDICA = "juridica"
_TIPO_NATURAL = "natural"


def _tipo_persona_catalogo(tipo_identificador: str | None) -> str:
    """Maps a ``tipo_identificador`` value to its ``tipo_persona.tipo`` string."""
    return _TIPO_JURIDICA if tipo_identificador == "NIT" else _TIPO_NATURAL


async def resolve_uuid_tipo_persona(
    session: AsyncSession, *, tipo_identificador: str | None
) -> object | None:
    """Looks up the vigente ``tipo_persona`` row uuid for a ``tipo_identificador``.

    Returns ``None`` when ``tipo_identificador`` is falsy, or when the
    catalog has no vigente/activo row for the resolved ``tipo`` string
    (e.g. an environment where the catalog hasn't been seeded yet) --
    callers treat ``None`` the same as "not provided", never as an error.
    """
    if not tipo_identificador:
        return None

    tipo = _tipo_persona_catalogo(tipo_identificador)
    stmt = (
        select(TipoPersona.uuid)
        .where(
            TipoPersona.tipo == tipo,
            TipoPersona.vigente_hasta.is_(None),
            TipoPersona.estado == "activo",
        )
        .order_by(TipoPersona.vigente_desde.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = ["resolve_uuid_tipo_persona"]
