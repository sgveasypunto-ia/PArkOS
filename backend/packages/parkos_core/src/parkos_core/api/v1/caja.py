"""Operations HTTP routes — caja + arqueo (PR7, REQ-10-A-INSERCION).

``caja`` and ``arqueo`` are ``[A]`` (append-only) tables — NO UPDATE/DELETE
via the router. Write endpoints land in a follow-up PR that calls
``repo.append_only.append_event``.
"""
from __future__ import annotations

from fastapi import APIRouter

from ...models.A.arqueo import Arqueo
from ...models.A.caja import Caja
from ...schemas.caja import (
    ArqueoCreate,
    ArqueoRead,
    ArqueoReadList,
    ArqueoUpdate,
    CajaCreate,
    CajaRead,
    CajaReadList,
    CajaUpdate,
)
from ..router_factory import make_router

router = APIRouter(prefix="/caja", tags=["caja"])


def _mount_caja(
    *,
    resource: str,
    model_cls: type,
    read_schema: type,
    read_list_schema: type,
    create_schema: type,
    update_schema: type,
) -> None:
    """Mount one caja C+Q+U router under ``/caja/{resource}``.

    ``write_enabled=False`` per PR7 rationale (above). Corrections on
    ``[A]`` tables are expressed as compensating rows via the
    ``repo.append_only.append_event`` helper (REQ-10-A-INSERCION).
    """
    router.include_router(
        make_router(
            resource=resource,
            model_cls=model_cls,
            read_schema=read_schema,
            read_list_schema=read_list_schema,
            create_schema=create_schema,
            update_schema=update_schema,
            repo_kind="versioned",
            issuer_required="operador-,admin-",
            permission_required="emitir_factura",
            write_enabled=False,  # PR7 is read-only; writes via custom endpoints (PR11)
        )
    )


_mount_caja(
    resource="caja",
    model_cls=Caja,
    read_schema=CajaRead,
    read_list_schema=CajaReadList,
    create_schema=CajaCreate,
    update_schema=CajaUpdate,
)
_mount_caja(
    resource="arqueo",
    model_cls=Arqueo,
    read_schema=ArqueoRead,
    read_list_schema=ArqueoReadList,
    create_schema=ArqueoCreate,
    update_schema=ArqueoUpdate,
)


__all__ = ["router"]