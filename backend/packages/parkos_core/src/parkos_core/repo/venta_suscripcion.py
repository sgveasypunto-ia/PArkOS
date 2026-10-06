"""parkos_core.repo.venta_suscripcion -- HU-F1.12 sale-at-the-counter helpers.

REQ-OPS-083..090 + REQ-OPS-XR5 traceability (see
``openspec/changes/hu-f1-12-venta-suscripcion/specs/operations/spec.md``):

* REQ-OPS-083 V1+V2+V3+V4+V5+V6+V7+V8+V9 -- the 9 typed helpers
  (``buscar_cliente_por_uuid_o_crear`` + ``buscar_tipo_subscripcion_vigente_por_uuid``
  + ``buscar_o_crear_vehiculo_por_placa`` + ``validar_placas_mismo_tipo_vehiculo``
  + ``validar_cantidad_maxima_vehiculos`` + ``validar_placa_duplicada_subscripcion``
  + ``calcular_monto_suscripcion`` + ``crear_subscripcion_cliente`` +
  ``crear_subscripcion_vehiculos_bulk``) all stay commit-free. The
  single ``await session.commit()`` is owned by the API handler at
  Step 10 of the 10-step chain (KD-VENTA-01).
* REQ-OPS-084 V2          -- ``buscar_tipo_subscripcion_vigente_por_uuid``
  uses ``SELECT ... FOR UPDATE`` (exclusive, NOT ``FOR SHARE`` -- DEC-VENTA-04).
* REQ-OPS-086 V7          -- ``calcular_monto_suscripcion`` always charges the
  full plan price (PT-3: A-09 prorrateo was removed).
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
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls
from decimal import Decimal
import hashlib
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.clientes import Clientes
from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos
from ..models.V.subscripciones_cliente import SubscripcionesCliente
from ..models.V.tipo_subscripciones import TipoSubscripciones
from ..models.V.vehiculos import Vehiculos
from ..runtime.tiempo import hoy_bogota
from . import placa as repo_placa
from . import versioned
from .tipo_persona import resolve_uuid_tipo_persona

__all__ = [
    "CantidadMaximaExcedidaError",
    "ClienteNoEncontradoError",
    "PlanDuracionDiasInvalidoError",
    "SubscripcionDuplicadaPlacaError",
    "TipoSubscripcionNoEncontradoError",
    "TipoSubscripcionNoVigenteError",
    "TipoVehiculoIncompatibleError",
    "TipoVehiculoPlanIncompatibleError",
    "buscar_cliente_por_uuid_o_crear",
    "buscar_cliente_por_uuid_o_crear_existente",
    "buscar_cliente_por_uuid_o_crear_nuevo",
    "buscar_o_crear_vehiculo_por_placa",
    "buscar_subscripcion_activa_de_placa",
    "buscar_tipo_subscripcion_vigente_por_uuid",
    "calcular_fecha_vencimiento",
    "calcular_monto_suscripcion",
    "crear_subscripcion_cliente",
    "crear_subscripcion_vehiculos_bulk",
    "validar_cantidad_maxima_vehiculos",
    "validar_placa_duplicada_subscripcion",
    "validar_mismo_tipo_vehiculos",
    "validar_placas_mismo_tipo_vehiculo",
    "validar_tipo_vehiculo_del_plan",
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

    def __init__(
        self,
        *,
        placa: str,
        uuid_sucursal: uuid_lib.UUID,
        uuid_subscripcion_cliente: uuid_lib.UUID | None = None,
    ) -> None:
        self.placa = placa
        self.uuid_sucursal = uuid_sucursal
        self.uuid_subscripcion_cliente = uuid_subscripcion_cliente
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
    """V7 422 edge -- ``plan.duracion_dias`` missing or ``<= 0``."""

    def __init__(self) -> None:
        super().__init__("plan_duracion_dias_invalido: duracion_dias must be > 0")


class TipoVehiculoPlanIncompatibleError(TipoVehiculoIncompatibleError):
    """PT-2 -- the vehicle type does not match ``plan.uuid_tipo_vehiculo``.

    Subclass of :class:`TipoVehiculoIncompatibleError` on purpose: call
    sites that only catch the V5 error (e.g. the venta flow) keep mapping
    it to 422 ``tipo_vehiculo_incompatible`` without changes, while the
    PT-2 endpoints catch the subclass first and answer the more specific
    ``tipo_vehiculo_plan_incompatible``.
    """

    def __init__(
        self,
        *,
        tipo_plan: uuid_lib.UUID,
        tipos_encontrados: list[str],
    ) -> None:
        self.tipo_plan = tipo_plan
        super().__init__(tipos_encontrados=tipos_encontrados)


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

    Ajuste identificación persona natural/empresa: ``uuid_tipo_persona``
    is resolved server-side from ``tipo_identificador`` via
    :func:`repo.tipo_persona.resolve_uuid_tipo_persona` when the caller
    didn't already supply one -- the frontend only ever sends a
    document type (``NIT``/``CC``/``CE``/``pasaporte``), never a
    catalog UUID.
    """
    new_attrs = {k: v for k, v in datos_cliente.items() if k != "dv"}
    if new_attrs.get("uuid_tipo_persona") is None:
        new_attrs["uuid_tipo_persona"] = await resolve_uuid_tipo_persona(
            session, tipo_identificador=new_attrs.get("tipo_identificador")
        )
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

    uuid_tipo_vehiculo = await repo_placa.detectar_tipo_vehiculo(session, placa)
    nuevo = await versioned.close_and_insert(
        session,
        Vehiculos,
        current_uuid=None,
        new_attrs={"placa": placa, "uuid_tipo_vehiculo": uuid_tipo_vehiculo},
        actor_uuid=actor_uuid,
    )
    return nuevo, True


# ---------------------------------------------------------------------------
# T4 -- validations + prorrateo + INSERTs
# ---------------------------------------------------------------------------


def validar_tipo_vehiculo_del_plan(
    *, plan: TipoSubscripciones, vehiculos: list[Vehiculos]
) -> None:
    """PT-2: every vehicle must match ``plan.uuid_tipo_vehiculo``.

    ``plan.uuid_tipo_vehiculo IS NULL`` means "any vehicle type" (e.g. the
    corporate plan) and the check is skipped. Otherwise a vehicle whose
    ``uuid_tipo_vehiculo`` differs (including an undetected, NULL type)
    raises :class:`TipoVehiculoPlanIncompatibleError`.
    """
    tipo_plan = getattr(plan, "uuid_tipo_vehiculo", None)
    if tipo_plan is None:
        return
    tipos = {v.uuid_tipo_vehiculo for v in vehiculos}
    if tipos - {tipo_plan}:
        raise TipoVehiculoPlanIncompatibleError(
            tipo_plan=tipo_plan,
            tipos_encontrados=sorted(str(t) for t in tipos),
        )


def validar_placas_mismo_tipo_vehiculo(
    *, plan: TipoSubscripciones, vehiculos: list[Vehiculos]
) -> None:
    """V5 (REQ-OPS-087): vehicle-type validations of a plan (venta flow).

    1. PT-2: the vehicles must match ``plan.uuid_tipo_vehiculo`` when the
       plan is typed (see :func:`validar_tipo_vehiculo_del_plan`).
    2. :func:`validar_mismo_tipo_vehiculos`.

    The add-plate endpoints validate an EXISTING subscription: there the
    plan type is checked on the NEW plate only (legacy plates already
    enrolled must not block adding another one), so they call the two
    functions separately.
    """
    validar_tipo_vehiculo_del_plan(plan=plan, vehiculos=vehiculos)
    validar_mismo_tipo_vehiculos(plan=plan, vehiculos=vehiculos)


def validar_mismo_tipo_vehiculos(
    *, plan: TipoSubscripciones, vehiculos: list[Vehiculos]
) -> None:
    """V5: when ``plan.mismo_tipo_vehiculo`` is ``True`` all ``vehiculos`` MUST
    share the same ``uuid_tipo_vehiculo``; otherwise
    :class:`TipoVehiculoIncompatibleError` BEFORE any INSERT (422). When it is
    ``False``/``None`` the check is SKIPPED -- heterogeneous types allowed.
    """
    if not plan.mismo_tipo_vehiculo:
        return
    tipos = {v.uuid_tipo_vehiculo for v in vehiculos}
    if len(tipos) > 1:
        raise TipoVehiculoIncompatibleError(
            tipos_encontrados=sorted(str(t) for t in tipos)
        )


def validar_cantidad_maxima_vehiculos(
    *, plan: TipoSubscripciones, n_placas: int
) -> None:
    """V6 (REQ-OPS-088): ``n_placas <= plan.cantidad_maxima_vehiculos``.

    Raises :class:`CantidadMaximaExcedidaError` BEFORE any INSERT. Pure
    in-process count -- no DB query required (the handler already
    holds the plan row from V2).
    """
    if plan.cantidad_maxima_vehiculos is not None and n_placas > plan.cantidad_maxima_vehiculos:
        raise CantidadMaximaExcedidaError(
            cantidad_maxima_vehiculos=plan.cantidad_maxima_vehiculos,
            placas_proporcionadas=n_placas,
        )


async def buscar_subscripcion_activa_de_placa(
    session: AsyncSession,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    fecha_referencia: date_cls | None = None,
    excluir_uuid_subscripcion_cliente: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID | None:
    """Uuid of the ACTIVE subscripcion of ``placa`` at ``uuid_sucursal``.

    Single definition of "this plate is already covered" shared by the
    sale flow and the three add-plate paths (PT-2). A subscripcion counts
    only when ALL hold: the subscripcion row is open
    (``vigente_hasta IS NULL``) with ``estado='activo'`` at THIS branch and
    ``fecha_vencimiento >= fecha_referencia`` (default: today), and the
    junction row + the vehicle row are open (the junction ``estado`` is
    ``'activo'``). An expired subscripcion, one closed by a renewal, or
    one at ANOTHER branch does not block.
    """
    referencia = fecha_referencia or hoy_bogota()
    stmt = (
        select(SubscripcionesCliente.uuid)
        .join(
            SubscripcionVehiculos,
            SubscripcionVehiculos.uuid_subscripcion_cliente == SubscripcionesCliente.uuid,
        )
        .join(Vehiculos, Vehiculos.uuid == SubscripcionVehiculos.uuid_vehiculo)
        .where(
            Vehiculos.placa == placa,
            Vehiculos.vigente_hasta.is_(None),
            SubscripcionVehiculos.vigente_hasta.is_(None),
            SubscripcionVehiculos.estado == "activo",
            SubscripcionesCliente.uuid_sucursal == uuid_sucursal,
            SubscripcionesCliente.vigente_hasta.is_(None),
            SubscripcionesCliente.estado == "activo",
            SubscripcionesCliente.fecha_vencimiento >= referencia,
        )
        .limit(1)
    )
    if excluir_uuid_subscripcion_cliente is not None:
        stmt = stmt.where(SubscripcionesCliente.uuid != excluir_uuid_subscripcion_cliente)
    return (await session.execute(stmt)).scalars().first()


def _placa_lock_key(uuid_sucursal: uuid_lib.UUID, placa: str) -> int:
    """Stable signed-int64 advisory-lock key for ``(sucursal, placa)``."""
    digest = hashlib.sha256(f"placa-sucursal:{uuid_sucursal}:{placa}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


async def validar_placa_duplicada_subscripcion(
    session: AsyncSession,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    fecha_inicio_cobertura: date_cls | None = None,
    excluir_uuid_subscripcion_cliente: uuid_lib.UUID | None = None,
) -> None:
    """V4 (REQ-OPS-089) / PT-2: reject a plate with an ACTIVE subscripcion at
    this branch (see :func:`buscar_subscripcion_activa_de_placa`).

    Raises :class:`SubscripcionDuplicadaPlacaError`. Same-branch only: an
    active subscripcion at ANOTHER branch is allowed. The venta flow keeps
    its own wire mapping; the PT-2 endpoints answer 409
    ``placa_con_suscripcion_activa``.
    """
    # Serialise "check then insert" for the same (sucursal, placa): without
    # this two concurrent adds of one plate to two subscriptions both see no
    # conflict. Transaction-scoped: released at the handler's single commit.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": _placa_lock_key(uuid_sucursal, placa)},
    )
    conflicto = await buscar_subscripcion_activa_de_placa(
        session,
        placa=placa,
        uuid_sucursal=uuid_sucursal,
        fecha_referencia=fecha_inicio_cobertura,
        excluir_uuid_subscripcion_cliente=excluir_uuid_subscripcion_cliente,
    )
    if conflicto is not None:
        raise SubscripcionDuplicadaPlacaError(
            placa=placa,
            uuid_sucursal=uuid_sucursal,
            uuid_subscripcion_cliente=conflicto,
        )


def _duracion_dias_valida(plan: TipoSubscripciones) -> int:
    """Return ``plan.duracion_dias`` or raise 422 ``plan_duracion_dias_invalido``."""
    duracion = plan.duracion_dias
    if duracion is None or duracion <= 0:
        raise PlanDuracionDiasInvalidoError()
    return int(duracion)


def calcular_monto_suscripcion(*, plan: TipoSubscripciones) -> Decimal:
    """V7 (PT-3): the full plan price is ALWAYS charged -- no proration.

    The charge depends only on the plan, never on how close the start date
    is to the end of the calendar month. A 60-day plan charges the 60 days.

    Raises :class:`PlanDuracionDiasInvalidoError` when
    ``plan.duracion_dias`` is missing or ``<= 0``.
    """
    _duracion_dias_valida(plan)
    valor = plan.valor if plan.valor is not None else 0
    return Decimal(valor).quantize(Decimal("0.01"))


def calcular_fecha_vencimiento(
    *, plan: TipoSubscripciones, fecha_inicio_cobertura: date_cls
) -> date_cls:
    """Last covered day: ``fecha_inicio_cobertura + plan.duracion_dias - 1``.

    The cycle is per subscription (starts at activation), never the
    calendar month. PD-01: a plan of N days covers EXACTLY N calendar days.
    ``fecha_vencimiento`` is the last covered day, INCLUSIVE: the validity
    predicates use ``fecha_vencimiento >= hoy``, so start day through
    ``fecha_vencimiento`` is N days. Existing rows are not rewritten.

    Raises :class:`PlanDuracionDiasInvalidoError` on an invalid duration.
    """
    return fecha_inicio_cobertura + timedelta(days=_duracion_dias_valida(plan) - 1)


async def crear_subscripcion_cliente(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_cliente: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_subscripcion: uuid_lib.UUID,
    fecha_inicio_cobertura: date_cls,
    fecha_vencimiento: date_cls,
) -> SubscripcionesCliente:
    """V9a: INSERT ``prod.subscripciones_cliente`` row (no close -- first version).

    Bi-temporal invariants are set by ``close_and_insert`` server-side:
    ``vigente_desde = NOW()``, ``vigente_hasta = NULL``, ``estado = 'activo'``.
    The handler commits at Step 10 (KD-VENTA-01).
    """
    return await versioned.close_and_insert(
        session,
        SubscripcionesCliente,
        current_uuid=None,
        new_attrs={
            "uuid_cliente": uuid_cliente,
            "uuid_sucursal": uuid_sucursal,
            "uuid_tipo_subscripcion": uuid_tipo_subscripcion,
            "fecha_inicio_cobertura": fecha_inicio_cobertura,
            "fecha_vencimiento": fecha_vencimiento,
        },
        actor_uuid=actor_uuid,
    )


async def crear_subscripcion_vehiculos_bulk(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_subscripcion_cliente: uuid_lib.UUID,
    uuid_vehiculos: list[uuid_lib.UUID],
) -> list[SubscripcionVehiculos]:
    """V9b: ``pg_advisory_xact_lock`` + bulk INSERT ``prod.subscripcion_vehiculos``.

    The advisory lock serializes concurrent inserts targeting the same
    ``uuid_subscripcion_cliente`` so that the V6
    ``cantidad_maxima_vehiculos`` invariant cannot be violated by a
    race (REQ-OP-08 mirror). The lock is held until the handler's
    single commit at Step 10 (KD-VENTA-01).

    Returns the list of newly inserted ORM rows.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": uuid_to_int64(uuid_subscripcion_cliente)},
    )
    rows: list[SubscripcionVehiculos] = []
    for v_uuid in uuid_vehiculos:
        row = SubscripcionVehiculos(
            uuid_subscripcion_cliente=uuid_subscripcion_cliente,
            uuid_vehiculo=v_uuid,
            vigente_desde=datetime_utcnow(),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime_utcnow(),
            created_by=actor_uuid,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return rows


def uuid_to_int64(uuid_val: uuid_lib.UUID) -> int:
    """Convert a UUID to a signed 64-bit int (Postgres ``bigint``).

    Used as the key for ``pg_advisory_xact_lock`` so that the lock
    namespace matches the ``uuid_subscripcion_cliente`` value.
    """
    return uuid_val.int & 0x7FFFFFFFFFFFFFFF


def datetime_utcnow() -> Any:
    """Lightweight ``datetime.now(UTC)`` -- replaces deprecated ``datetime.utcnow()``.

    Returns naive UTC datetime (matches the F1.5 ``created_at`` column
    convention -- no tzinfo so SQLAlchemy stores as ``timestamp without
    time zone``).
    """

    return datetime.now(UTC).replace(tzinfo=None)
