"""parkos_core.repo.venta_suscripcion -- HU-F1.12 sale-at-the-counter helpers.

REQ-OPS-083..090 + REQ-OPS-XR5 traceability (see
``openspec/changes/hu-f1-12-venta-suscripcion/specs/operations/spec.md``):

* REQ-OPS-083 V1+V2+V3+V4+V5+V6+V7+V8+V9 -- the 9 typed helpers
  (``buscar_cliente_por_uuid_o_crear`` + ``buscar_tipo_subscripcion_vigente_por_uuid``
  + ``buscar_o_crear_vehiculo_por_placa`` + ``validar_placas_mismo_tipo_vehiculo``
  + ``validar_cantidad_maxima_vehiculos`` + ``validar_placa_duplicada_subscripcion``
  + ``calcular_prorrateo`` + ``crear_subscripcion_cliente`` +
  ``crear_subscripcion_vehiculos_bulk``) all stay commit-free. The
  single ``await session.commit()`` is owned by the API handler at
  Step 10 of the 10-step chain (KD-VENTA-01).
* REQ-OPS-084 V2          -- ``buscar_tipo_subscripcion_vigente_por_uuid``
  uses ``SELECT ... FOR UPDATE`` (exclusive, NOT ``FOR SHARE`` -- DEC-VENTA-04).
* REQ-OPS-086 V7          -- ``calcular_prorrateo`` implements A-09 prorrateo
  (no ``monto_prorrateado`` column on ``prod.subscripciones_cliente``).
* REQ-OPS-087 V5          -- ``validar_placas_mismo_tipo_vehiculo`` raises
  ``TipoVehiculoIncompatibleError`` BEFORE any INSERT.
* REQ-OPS-088 V6          -- ``validar_cantidad_maxima_vehiculos`` raises
  ``CantidadMaximaExcedidaError`` BEFORE any INSERT.
* REQ-OPS-089 V4          -- ``validar_placa_duplicada_subscripcion`` reuses
  ``repo.subscripcion_activa.resolve_active_subscription_for_exit`` (F1.7).
* REQ-OPS-090 V1          -- ``buscar_cliente_por_uuid_o_crear`` discards
  ``dv`` (DEC-VENTA-07 -- validated by Pydantic, not persisted).
* REQ-OPS-XR5             -- DEC-VENTA-01 + DEC-VENTA-02 + KD-VENTA-01 +
  KD-VENTA-02 5-layer defense in depth.

This module NEVER calls ``session.commit()``. KD-VENTA-01 invariant:
exactly one ``await session.commit()`` per handler body (mirror of F1.10
KD-FE-01 + F1.11 KD-TKT-01).

DEC-VENTA-08 WITHDRAWN: all 5 [V] sync catalog entries pre-exist at
``sync/catalog/entries/sync_entries_v.py`` lines 133, 451, 483, 511, 525
(pre-flight verified 2026-09-15).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date as date_cls
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.clientes import Clientes
from ..models.V.tipo_subscripciones import TipoSubscripciones
from ..models.V.vehiculos import Vehiculos
from . import placa as repo_placa
from . import versioned

__all__ = [
    "CantidadMaximaExcedidaError",
    "ClienteNoEncontradoError",
    "PlanDuracionDiasInvalidoError",
    "SubscripcionDuplicadaPlacaError",
    "TipoSubscripcionNoEncontradoError",
    "TipoSubscripcionNoVigenteError",
    "TipoVehiculoIncompatibleError",
    "buscar_cliente_por_uuid_o_crear",
    "buscar_cliente_por_uuid_o_crear_existente",
    "buscar_cliente_por_uuid_o_crear_nuevo",
    "buscar_o_crear_vehiculo_por_placa",
    "buscar_tipo_subscripcion_vigente_por_uuid",
    "calcular_prorrateo",
    "crear_subscripcion_cliente",
    "crear_subscripcion_vehiculos_bulk",
    "validar_cantidad_maxima_vehiculos",
    "validar_placa_duplicada_subscripcion",
    "validar_placas_mismo_tipo_vehiculo",
]


# ---------------------------------------------------------------------------
# Typed exceptions (7) -- DEC-VENTA-01..07
# ---------------------------------------------------------------------------


class ClienteNoEncontradoError(Exception):
    """V1 404 discriminator -- ``prod.clientes`` row not found by PK.

    Raised by ``buscar_cliente_por_uuid_o_crear_existente`` when the
    caller supplied ``uuid_cliente`` but no vigente row exists at the
    operator's branch.
    """

    def __init__(self, *, uuid_cliente: uuid_lib.UUID) -> None:
        self.uuid_cliente = uuid_cliente
        super().__init__(f"cliente_no_encontrado: uuid_cliente={uuid_cliente}")


class TipoSubscripcionNoEncontradoError(Exception):
    """V2 404 discriminator -- no vigente ``prod.tipo_subscripciones`` for UUID."""

    def __init__(self, *, uuid_tipo_subscripcion: uuid_lib.UUID) -> None:
        self.uuid_tipo_subscripcion = uuid_tipo_subscripcion
        super().__init__(
            f"tipo_subscripcion_no_encontrado: uuid_tipo_subscripcion={uuid_tipo_subscripcion}"
        )


class TipoSubscripcionNoVigenteError(Exception):
    """V2 409 discriminator -- ``prod.tipo_subscripciones`` row exists but is closed."""

    def __init__(self, *, uuid_tipo_subscripcion: uuid_lib.UUID) -> None:
        self.uuid_tipo_subscripcion = uuid_tipo_subscripcion
        super().__init__(
            f"tipo_subscripcion_no_vigente: uuid_tipo_subscripcion={uuid_tipo_subscripcion}"
        )


class SubscripcionDuplicadaPlacaError(Exception):
    """V4 422 discriminator -- placa already has an active subscription at this branch."""

    def __init__(self, *, placa: str, uuid_sucursal: uuid_lib.UUID) -> None:
        self.placa = placa
        self.uuid_sucursal = uuid_sucursal
        super().__init__(
            f"suscripcion_duplicada_placa: placa={placa}, uuid_sucursal={uuid_sucursal}"
        )


class TipoVehiculoIncompatibleError(Exception):
    """V5 422 discriminator -- ``mismo_tipo_vehiculo`` plan + mixed tipos in placas."""

    def __init__(self, *, tipos_encontrados: list[str]) -> None:
        self.tipos_encontrados = tipos_encontrados
        super().__init__(
            f"tipo_vehiculo_incompatible: tipos_encontrados={tipos_encontrados}"
        )


class CantidadMaximaExcedidaError(Exception):
    """V6 422 discriminator -- ``cantidad_maxima_vehiculos`` exceeded by ``len(placas)``."""

    def __init__(
        self, *, cantidad_maxima_vehiculos: int, placas_proporcionadas: int
    ) -> None:
        self.cantidad_maxima_vehiculos = cantidad_maxima_vehiculos
        self.placas_proporcionadas = placas_proporcionadas
        super().__init__(
            f"cantidad_maxima_excedida: cantidad_maxima_vehiculos="
            f"{cantidad_maxima_vehiculos}, placas_proporcionadas={placas_proporcionadas}"
        )


class PlanDuracionDiasInvalidoError(Exception):
    """V7 422 edge -- ``plan.duracion_dias <= 0`` (ZeroDivisionError catch)."""

    def __init__(self) -> None:
        super().__init__("plan_duracion_dias_invalido: duracion_dias must be > 0")


# ---------------------------------------------------------------------------
# V1..V9 helpers -- T3 fills in cliente (V1) + plan (V2) + vehiculo (V3);
# T4 fills in validations (V4 + V5 + V6) + prorrateo (V7) + INSERTs (V9).
# ---------------------------------------------------------------------------


async def buscar_tipo_subscripcion_vigente_por_uuid(
    session: AsyncSession, *, uuid_tipo_subscripcion: uuid_lib.UUID
) -> TipoSubscripciones | None:
    """V2 (REQ-OPS-084): SELECT vigente ``prod.tipo_subscripciones`` row.

    Uses ``SELECT ... FOR UPDATE`` (exclusive, NOT ``FOR SHARE`` per
    DEC-VENTA-04) on the most-recent vigente row. The lock is held
    until ``await session.commit()`` in the handler body. The lock
    closes the concurrent-update race: two TXs that both read the
    plan at the same time serialize on this row, so a concurrent plan
    edit (out-of-scope for F1.12) cannot race with the sale.

    Returns the ORM row or ``None`` -- the handler maps ``None`` to
    404 ``tipo_subscripcion_no_encontrado`` via HTTPException (Layer 5).
    """
    stmt = (
        select(TipoSubscripciones)
        .where(
            TipoSubscripciones.uuid == uuid_tipo_subscripcion,
            TipoSubscripciones.vigente_hasta.is_(None),
            TipoSubscripciones.estado == "activo",
        )
        .order_by(TipoSubscripciones.vigente_desde.desc())
        .limit(1)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def buscar_cliente_por_uuid_o_crear_existente(
    session: AsyncSession, *, uuid_cliente: uuid_lib.UUID
) -> Clientes:
    """V1 EXISTING branch: SELECT vigente ``prod.clientes`` row by PK.

    Raises :class:`ClienteNoEncontradoError` if no vigente row exists
    at the operator's branch. The handler maps the exception to 404
    ``cliente_no_encontrado`` via HTTPException (Layer 5).
    """
    row = await session.get(Clientes, uuid_cliente)
    if row is None:
        raise ClienteNoEncontradoError(uuid_cliente=uuid_cliente)
    return row


async def buscar_cliente_por_uuid_o_crear_nuevo(
    session: AsyncSession,
    *,
    datos_cliente: dict[str, Any],
    actor_uuid: uuid_lib.UUID,
) -> Clientes:
    """V1 NEW branch: INSERT new cliente via ``close_and_insert(current_uuid=None)``.

    DEC-VENTA-07: ``dv`` (if present) is Pydantic-validated upstream
    by ``ClientesCreate._validar_nit_dv`` but NOT a column on
    ``prod.clientes``. The helper filters ``dv`` out of ``new_attrs``
    before calling ``close_and_insert`` -- only business columns
    (``tipo_identificador``, ``numero_identificacion``, ``nombre``,
    ``apellido``, ``telefono``, ``email``, ``uuid_tipo_persona``,
    ``registro``) are persisted.

    Returns the new ORM row (caller commits at Step 10 of the handler).
    """
    new_attrs = {k: v for k, v in datos_cliente.items() if k != "dv"}
    return await versioned.close_and_insert(
        session,
        Clientes,
        current_uuid=None,
        new_attrs=new_attrs,
        actor_uuid=actor_uuid,
    )


async def buscar_cliente_por_uuid_o_crear(
    session: AsyncSession,
    *,
    uuid_cliente: uuid_lib.UUID | None,
    datos_cliente: dict[str, Any] | None,
    actor_uuid: uuid_lib.UUID,
) -> Clientes:
    """V1 facade: dispatch NEW (``datos_cliente``) vs EXISTING (``uuid_cliente``).

    The XOR invariant is enforced by ``VentaSuscripcionCreate._check_cliente_xor_uuid``
    at the Pydantic layer (Layer 4). This helper is the API-side dispatch.

    DEC-VENTA-02 lock ordering: EXISTING branch acquires the
    ``SELECT FOR UPDATE`` on the cliente row before any INSERT in V3,
    so a concurrent new-cliente race cannot create duplicate
    (tipo_identificador, numero_identificacion) UK hits.
    """
    if uuid_cliente is not None:
        return await buscar_cliente_por_uuid_o_crear_existente(
            session, uuid_cliente=uuid_cliente
        )
    if datos_cliente is not None:
        return await buscar_cliente_por_uuid_o_crear_nuevo(
            session, datos_cliente=datos_cliente, actor_uuid=actor_uuid
        )
    # XOR is already validated at the Pydantic layer; this branch is
    # reachable only if the caller bypassed the schema (unit-test path).
    raise ValueError(
        "buscar_cliente_por_uuid_o_crear requires exactly one of "
        "uuid_cliente or datos_cliente"
    )


async def buscar_o_crear_vehiculo_por_placa(
    session: AsyncSession, *, placa: str, actor_uuid: uuid_lib.UUID
) -> tuple[Vehiculos, bool]:
    """V3 (REQ-OPS-086): per-placa SELECT-or-INSERT ``prod.vehiculos``.

    SELECT-OR-INSERT: looks up the vigente row for ``placa``
    (``vigente_hasta IS NULL AND estado='activo'``). On hit returns
    the row + ``was_created=False``. On miss, calls
    :func:`repo.placa.detectar_tipo_vehiculo` to infer
    ``uuid_tipo_vehiculo`` from the placa regex (F1.7 reuse) and
    calls ``close_and_insert(current_uuid=None)`` to INSERT the new
    vehicle. Returns ``(vehiculo_orm, was_created=True)``.

    KD-VENTA-02 lock ordering: this helper runs AFTER V1 (cliente)
    and BEFORE V4 (duplicate placa check). The plan row is already
    locked via ``buscar_tipo_subscripcion_vigente_por_uuid`` so two
    concurrent sales cannot double-create the same vehicle.

    Caller commits at Step 10 of the handler (KD-VENTA-01).
    """
    stmt = (
        select(Vehiculos)
        .where(
            Vehiculos.placa == placa,
            Vehiculos.vigente_hasta.is_(None),
            Vehiculos.estado == "activo",
        )
        .order_by(Vehiculos.vigente_desde.desc())
        .limit(1)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing, False

    uuid_tipo_vehiculo = await repo_placa.detectar_tipo_vehiculo(placa)
    nuevo = await versioned.close_and_insert(
        session,
        Vehiculos,
        current_uuid=None,
        new_attrs={"placa": placa, "uuid_tipo_vehiculo": uuid_tipo_vehiculo},
        actor_uuid=actor_uuid,
    )
    return nuevo, True


# ---------------------------------------------------------------------------
# T4 stubs (placeholders -- bodies added in T4)
# ---------------------------------------------------------------------------


def validar_placas_mismo_tipo_vehiculo(
    *, plan: Any, vehiculos: list[Any]
) -> None:
    """V5 (REQ-OPS-087): same-tipo validation when ``plan.mismo_tipo_vehiculo``.

    Raises ``TipoVehiculoIncompatibleError`` BEFORE any INSERT. Pure
    in-process comparison of ``vehiculo.uuid_tipo_vehiculo``. Body
    lands in T4.
    """
    raise NotImplementedError("V5 body added in T4 (HU-F1.12)")


def validar_cantidad_maxima_vehiculos(
    *, plan: Any, n_placas: int
) -> None:
    """V6 (REQ-OPS-088): ``len(placas) <= plan.cantidad_maxima_vehiculos``.

    Raises ``CantidadMaximaExcedidaError`` BEFORE any INSERT. Pure
    in-process count. Body lands in T4.
    """
    raise NotImplementedError("V6 body added in T4 (HU-F1.12)")


async def validar_placa_duplicada_subscripcion(
    session: AsyncSession,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    fecha_inicio_cobertura: date_cls,
) -> None:
    """V4 (REQ-OPS-089): per-placa reverse-direction active-sub lookup.

    Reuses ``repo.subscripcion_activa.resolve_active_subscription_for_exit``
    (F1.7). Raises ``SubscripcionDuplicadaPlacaError`` on hit. Body
    lands in T4.
    """
    raise NotImplementedError("V4 body added in T4 (HU-F1.12)")


def calcular_prorrateo(*, plan: Any, fecha_inicio_cobertura: date_cls) -> Any:
    """V7 (REQ-OPS-090 / A-09): ``valor_dia * dias_restantes_mes`` after day-15.

    Returns the prorrateo ``Decimal`` (or ``None`` if before day 16).
    Raises ``PlanDuracionDiasInvalidoError`` on ``ZeroDivisionError``.
    Body lands in T4.
    """
    raise NotImplementedError("V7 body added in T4 (HU-F1.12)")


async def crear_subscripcion_cliente(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_cliente: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_subscripcion: uuid_lib.UUID,
    fecha_inicio_cobertura: date_cls,
    fecha_vencimiento: date_cls,
) -> Any:
    """V9a: INSERT ``prod.subscripciones_cliente`` row (no close -- first version).

    Body lands in T4.
    """
    raise NotImplementedError("V9a body added in T4 (HU-F1.12)")


async def crear_subscripcion_vehiculos_bulk(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_subscripcion_cliente: uuid_lib.UUID,
    uuid_vehiculos: list[uuid_lib.UUID],
) -> list[Any]:
    """V9b: ``pg_advisory_xact_lock`` + bulk INSERT ``prod.subscripcion_vehiculos``.

    Body lands in T4.
    """
    raise NotImplementedError("V9b body added in T4 (HU-F1.12)")
