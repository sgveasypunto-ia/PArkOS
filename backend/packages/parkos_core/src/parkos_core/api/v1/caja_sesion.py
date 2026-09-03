"""Operations HTTP routes — sesion + custom endpoints (PR7, REQ-40, REQ-41).

``Sesion`` is ``[L-S]`` (session lifecycle). NO UPDATE/DELETE via the
canonical router — the lifecycle goes through custom endpoints:

- ``POST /sesiones`` calls ``open_session()``.
- ``PUT /sesion/{uuid}/cerrar`` calls ``close_session_with_log()``.

Also adds ``GET /arqueos/{uuid}/diferencias`` reading the Arqueo row and
computing expected vs reported deltas (SC-40-S-FULL-SHIFT — full-shift
difference calculation).
"""
from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.L_S.sesion import Sesion
from ...repo.session_cycle import close_session_with_log, open_session
from ...schemas.caja import (
    SesionCreate,
    SesionRead,
    SesionReadList,
    SesionUpdate,
)
from ..deps import TenantContext, get_session, get_tenant_ctx, requires_issuer
from ..router_factory import make_router

router = APIRouter(prefix="/caja-sesion", tags=["caja-sesion"])

_sesion_issuer_dep = requires_issuer("operador-", "admin-")


class SesionCerrarRequest(BaseModel):
    """PUT /sesion/{uuid}/cerrar body — final cash values for shift close.

    The ``valor_final_*`` values are recorded in the ``log_transaccional``
    row's ``datos_nuevos`` JSONB — the Sesion table only stores the
    initial values (REQ-41).
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    valor_final_efectivo: float | None = None
    valor_final_datafono: float | None = None


class ArqueoDiferenciasResponse(BaseModel):
    """GET /arqueos/{uuid}/diferencias response (SC-40-S-FULL-SHIFT).

    Reads the Arqueo row directly and computes the expected-vs-reported
    deltas. Returns ``None`` for differences when no Arqueo row exists.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    uuid_arqueo: uuid_lib.UUID
    valor_efectivo_esperado: float | None
    valor_datafono_esperado: float | None
    valor_efectivo_reportado: float | None
    valor_datafono_reportado: float | None
    diferencia_efectivo: float | None
    diferencia_datafono: float | None


@router.post(
    "/sesiones",
    response_model=SesionRead,
    status_code=201,
    summary="Open a cash session (REQ-40-S-OPEN)",
)
async def open_sesion(
    payload: SesionCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_sesion_issuer_dep),
):
    """Insert a new Sesion row + log_transaccional (REQ-40)."""
    if payload.uuid_sucursal is None or payload.uuid_usuario is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_required_field",
                "fields": [
                    f
                    for f, v in (
                        ("uuid_sucursal", payload.uuid_sucursal),
                        ("uuid_usuario", payload.uuid_usuario),
                    )
                    if v is None
                ],
            },
        )

    valor_efectivo = float(payload.valor_inicial_efectivo or 0)
    valor_datafono = float(payload.valor_inicial_datafono or 0)

    new_row = await open_session(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=payload.uuid_sucursal,
        valor_inicial_efectivo=valor_efectivo,
        valor_inicial_datafono=valor_datafono,
        uuid_usuario=payload.uuid_usuario,
        log_tx=True,
    )
    await session.commit()
    await session.refresh(new_row)
    return SesionRead.model_validate(new_row)


@router.put(
    "/sesion/{uuid}/cerrar",
    response_model=SesionRead,
    summary="Close a cash session (REQ-41, SC-42 — log-first)",
)
async def cerrar_sesion(
    payload: SesionCerrarRequest,
    uuid: uuid_lib.UUID = Path(...),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_sesion_issuer_dep),
):
    """Close the Sesion row + write log_transaccional FIRST.

    The DB trigger ``ls_session_guard`` validates the log exists in the
    same TX. If not, the trigger RAISES (REQ-41, SC-42).
    """
    updated = await close_session_with_log(
        session,
        actor_uuid=ctx.actor_uuid,
        sesion_uuid=uuid,
        valor_final_efectivo=payload.valor_final_efectivo,
        valor_final_datafono=payload.valor_final_datafono,
        log_tx=True,
    )
    await session.commit()
    return SesionRead.model_validate(updated)


@router.get(
    "/arqueos/{uuid}/diferencias",
    response_model=ArqueoDiferenciasResponse,
    summary="Derived arqueo differences (SC-40-S-FULL-SHIFT)",
)
async def arqueo_diferencias(
    uuid: uuid_lib.UUID = Path(...),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_sesion_issuer_dep),
):
    """Read the Arqueo row + compute expected-vs-reported deltas.

    Returns 404 if no Arqueo row exists for the given ``uuid``. The
    derived view ``V_ARQUEO_DIFERENCIAS`` is computed on demand here
    rather than read from the view to keep the path independent of the
    view's existence at boot.
    """
    row = (
        await session.execute(
            text(
                "SELECT valor_efectivo_esperado, valor_datafono_esperado, "
                "valor_efectivo_reportado, valor_datafono_reportado "
                "FROM prod.arqueo WHERE uuid = :uuid"
            ),
            {"uuid": str(uuid)},
        )
    ).first()

    if row is None:
        raise HTTPException(status_code=404, detail={"error": "arqueo_not_found"})

    esperado_e = float(row[0]) if row[0] is not None else 0
    esperado_d = float(row[1]) if row[1] is not None else 0
    reportado_e = float(row[2]) if row[2] is not None else 0
    reportado_d = float(row[3]) if row[3] is not None else 0

    return ArqueoDiferenciasResponse(
        uuid_arqueo=uuid,
        valor_efectivo_esperado=esperado_e,
        valor_datafono_esperado=esperado_d,
        valor_efectivo_reportado=reportado_e,
        valor_datafono_reportado=reportado_d,
        diferencia_efectivo=reportado_e - esperado_e,
        diferencia_datafono=reportado_d - esperado_d,
    )


# Read-only mounts of sesion for GET endpoints (no write via router)
router.include_router(
    make_router(
        resource="sesion",
        model_cls=Sesion,
        read_schema=SesionRead,
        read_list_schema=SesionReadList,
        create_schema=SesionCreate,
        update_schema=SesionUpdate,
        repo_kind="versioned",
        issuer_required="operador-,admin-",
        permission_required="emitir_factura",
        write_enabled=False,
    )
)


__all__ = ["router"]