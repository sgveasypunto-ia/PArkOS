"""HU-F9.2 realineada -- gestión de cupos de suscripción (Sheet de sucursal).

Dedicated router (mirror de ``clientes_venta.py`` -- DEC-VENTA-05 pattern):
4 endpoints que NO puede servir el CRUD genérico de ``router_factory``
porque tienen invariantes de negocio reales (cupo máximo, mismo tipo de
vehículo) o necesitan un JOIN que el CRUD genérico no arma (cliente +
plan + conteo de inscritos).

  1. ``GET /clientes/subscripciones-activas`` -- paso 1 del Sheet:
     listado de suscripciones activas de la sucursal actual.
  2. ``GET /clientes/subscripciones-cliente/buscar`` -- paso 2: busca la
     suscripción activa de un cliente por ``numero_identificacion``.
  3. ``POST /clientes/subscripcion-vehiculos/agregar`` -- paso 3: agrega
     un vehículo, validando V5 (``mismo_tipo_vehiculo``) + V6
     (``cantidad_maxima_vehiculos``) ANTES del INSERT (reutiliza los
     validadores de ``repo.venta_suscripcion``).
  4. ``PUT /clientes/subscripcion-vehiculos/{uuid}/quitar`` -- paso 3:
     da de baja un vehículo inscrito (``close_and_insert`` bi-temporal
     con ``estado='inactivo'`` -- nunca DELETE). El PUT genérico de
     ``router_factory`` NO sirve para esto: ``SubscripcionVehiculosUpdate``
     no expone ``estado`` como campo (ver schemas/clientes.py), así que
     nunca podría viajar la transición en el payload.

Cada handler mantiene el invariante de un solo ``await session.commit()``
(mismo KD-VENTA-01 que ``clientes_venta.py``).
"""

from __future__ import annotations

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.tenancy import TenantContext, get_tenant_ctx
from ...db.engine import get_session
from ...repo import cupos_subscripcion as repo_cupos
from ...repo import venta_suscripcion as repo_venta
from ...repo.versioned import RowNotFoundError
from ...schemas.clientes import (
    AgregarVehiculoCupoRequest,
    ClienteResumen,
    PlanResumen,
    SubscripcionActivaItem,
    SubscripcionCupoDetalle,
    SubscripcionesActivasResponse,
    VehiculoInscrito,
)
from ..deps import requires_issuer
from . import _helpers

# NO "/clientes" prefix here -- api/v1/clientes.py includes this router
# into its OWN router (which already carries prefix="/clientes") via a
# bare ``router.include_router(...)`` with no prefix arg. A prefix here
# would double every path to ``/api/v1/clientes/clientes/...`` (real bug
# found live on ``clientes_venta.py`` while wiring this router -- see
# that file's ``router = APIRouter(...)`` comment for the full story).
router = APIRouter(tags=["clientes"])

_cupos_issuer_dep = requires_issuer("operador-", "admin-")


def _to_cliente_resumen(cliente) -> ClienteResumen:
    return ClienteResumen(
        uuid=cliente.uuid,
        nombre=cliente.nombre,
        apellido=cliente.apellido,
        numero_identificacion=cliente.numero_identificacion,
    )


def _to_plan_resumen(plan) -> PlanResumen:
    return PlanResumen(
        uuid=plan.uuid,
        tipo=plan.tipo,
        valor=plan.valor,
        cantidad_maxima_vehiculos=plan.cantidad_maxima_vehiculos,
        mismo_tipo_vehiculo=plan.mismo_tipo_vehiculo,
    )


def _to_cupo_detalle(row: repo_cupos.SubscripcionConVehiculos) -> SubscripcionCupoDetalle:
    inscritos = len(row.vehiculos)
    cupo_maximo = row.plan.cantidad_maxima_vehiculos
    cupo_disponible = max(cupo_maximo - inscritos, 0) if cupo_maximo is not None else None
    return SubscripcionCupoDetalle(
        uuid=row.subscripcion.uuid,
        cliente=_to_cliente_resumen(row.cliente),
        plan=_to_plan_resumen(row.plan),
        fecha_inicio_cobertura=row.subscripcion.fecha_inicio_cobertura,
        fecha_vencimiento=row.subscripcion.fecha_vencimiento,
        cupo_maximo=cupo_maximo,
        cupo_disponible=cupo_disponible,
        vehiculos=[
            VehiculoInscrito(
                uuid=v.uuid_subscripcion_vehiculo,
                uuid_vehiculo=v.vehiculo.uuid,
                placa=v.vehiculo.placa,
            )
            for v in row.vehiculos
        ],
    )


@router.get(
    "/subscripciones-activas",
    response_model=SubscripcionesActivasResponse,
)
async def listar_subscripciones_activas(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_cupos_issuer_dep),
) -> SubscripcionesActivasResponse:
    """Paso 1 del Sheet: listado de suscripciones activas de la sucursal actual."""
    rows = await repo_cupos.listar_subscripciones_activas(session)
    items = [
        SubscripcionActivaItem(
            uuid=r.subscripcion.uuid,
            cliente=_to_cliente_resumen(r.cliente),
            plan=_to_plan_resumen(r.plan),
            fecha_inicio_cobertura=r.subscripcion.fecha_inicio_cobertura,
            fecha_vencimiento=r.subscripcion.fecha_vencimiento,
            cupo_maximo=r.plan.cantidad_maxima_vehiculos,
            vehiculos_inscritos=r.vehiculos_inscritos,
        )
        for r in rows
    ]
    return SubscripcionesActivasResponse(items=items)


@router.get(
    "/subscripciones-activas/buscar",
    response_model=SubscripcionCupoDetalle | None,
    responses={200: {"description": "null cuando no hay suscripción activa para ese cliente"}},
)
async def buscar_subscripcion_por_identificacion(
    numero_identificacion: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_cupos_issuer_dep),
) -> SubscripcionCupoDetalle | None:
    """Paso 2 del Sheet: busca la suscripción activa de un cliente por su
    número de identificación. ``None`` (200) cuando no hay resultado --
    es un estado vacío legítimo, no un error."""
    row = await repo_cupos.buscar_subscripcion_activa_por_identificacion(
        session, numero_identificacion=numero_identificacion
    )
    if row is None:
        return None
    return _to_cupo_detalle(row)


@router.post(
    "/subscripcion-vehiculos/agregar",
    response_model=SubscripcionCupoDetalle,
    status_code=201,
    responses={
        404: {"description": "subscripcion_no_encontrada"},
        409: {"description": "vehiculo_ya_inscrito"},
        422: {"description": "cantidad_maxima_excedida / tipo_vehiculo_incompatible"},
    },
)
async def agregar_vehiculo(
    response: Response,
    payload: AgregarVehiculoCupoRequest,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_cupos_issuer_dep),
) -> SubscripcionCupoDetalle:
    """Paso 3 del Sheet: agrega un vehículo a una suscripción existente,
    validando cupo (V6) y mismo-tipo (V5) ANTES de tocar la base."""
    no_store = _helpers.no_store_headers()

    try:
        detalle = await repo_cupos.buscar_subscripcion_con_vehiculos_por_uuid(
            session, uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente
        )
    except repo_cupos.SubscripcionNoEncontradaError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "subscripcion_no_encontrada"},
            headers=no_store,
        ) from exc

    nuevo_vehiculo, _was_created = await repo_venta.buscar_o_crear_vehiculo_por_placa(
        session, placa=payload.placa, actor_uuid=ctx.actor_uuid
    )

    try:
        repo_venta.validar_placas_mismo_tipo_vehiculo(
            plan=detalle.plan,
            vehiculos=[v.vehiculo for v in detalle.vehiculos] + [nuevo_vehiculo],
        )
    except repo_venta.TipoVehiculoIncompatibleError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "tipo_vehiculo_incompatible",
                "tipos_encontrados": exc.tipos_encontrados,
            },
            headers=no_store,
        ) from exc

    try:
        repo_venta.validar_cantidad_maxima_vehiculos(
            plan=detalle.plan, n_placas=len(detalle.vehiculos) + 1
        )
    except repo_venta.CantidadMaximaExcedidaError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "cantidad_maxima_excedida",
                "cantidad_maxima_vehiculos": exc.cantidad_maxima_vehiculos,
                "placas_proporcionadas": exc.placas_proporcionadas,
            },
            headers=no_store,
        ) from exc

    try:
        await repo_cupos.agregar_vehiculo_a_subscripcion(
            session,
            uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente,
            placa=payload.placa,
            actor_uuid=ctx.actor_uuid,
        )
    except repo_cupos.VehiculoYaInscritoError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "vehiculo_ya_inscrito", "placa": exc.placa},
            headers=no_store,
        ) from exc

    await session.commit()

    actualizado = await repo_cupos.buscar_subscripcion_con_vehiculos_por_uuid(
        session, uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente
    )
    _helpers.apply_no_store_header(response)
    return _to_cupo_detalle(actualizado)


@router.put(
    "/subscripcion-vehiculos/{uuid}/quitar",
    response_model=SubscripcionCupoDetalle,
    responses={404: {"description": "vehiculo_inscrito_no_encontrado"}},
)
async def quitar_vehiculo(
    response: Response,
    uuid: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_cupos_issuer_dep),
) -> SubscripcionCupoDetalle:
    """Paso 3 del Sheet: da de baja un vehículo inscrito (bi-temporal,
    nunca DELETE) y devuelve el detalle de cupos ya actualizado."""
    no_store = _helpers.no_store_headers()

    try:
        cerrado = await repo_cupos.quitar_vehiculo_de_subscripcion(
            session, uuid_subscripcion_vehiculo=uuid, actor_uuid=ctx.actor_uuid
        )
    except RowNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": "vehiculo_inscrito_no_encontrado"},
            headers=no_store,
        ) from exc

    await session.commit()

    actualizado = await repo_cupos.buscar_subscripcion_con_vehiculos_por_uuid(
        session, uuid_subscripcion_cliente=cerrado.uuid_subscripcion_cliente
    )
    _helpers.apply_no_store_header(response)
    return _to_cupo_detalle(actualizado)


__all__ = ["router"]
