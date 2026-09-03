"""Catalog-domain HTTP routes (REQ-OP-13, REQ-02-V-CONSULTA).

PR1b smoke-mounts ``tipo-persona`` only — the full catalog (9 tables) ships
in PR3. The smoke mount proves the router factory works end-to-end before
PR3 fans out the same pattern across ``tipos-vehiculo``, ``tipo-tarifa``,
``impuestos``, etc.
"""
from __future__ import annotations

from fastapi import APIRouter

from ...models.V.tipo_persona import TipoPersona
from ...schemas import catalogos as catalogos_schemas
from ..router_factory import make_router

router = APIRouter(prefix="/catalogos", tags=["catalogos"])

# Smoke mount — PR3 adds: tipos-vehiculo, tipo-subscripciones, tipo-tarifa,
# tipo-sucursal, tipo-arqueo, impuestos, otros-cobros, costos-servicios.
router.include_router(
    make_router(
        resource="tipo-persona",
        model_cls=TipoPersona,
        read_schema=catalogos_schemas.TipoPersonaRead,
        read_list_schema=catalogos_schemas.TipoPersonaReadList,
        create_schema=catalogos_schemas.TipoPersonaCreate,
        update_schema=catalogos_schemas.TipoPersonaUpdate,
        repo_kind="versioned",
        issuer_required="admin-,operador-",
        permission_required="config_catalogo",
    )
)

__all__ = ["router"]