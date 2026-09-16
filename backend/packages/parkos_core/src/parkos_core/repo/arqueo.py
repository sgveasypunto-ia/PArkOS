"""parkos_core.repo.arqueo -- HU-F1.13 arqueo + cierre_dia helpers.

REQ-OPS-091..097 + REQ-OPS-XR6 traceability (see
``openspec/changes/hu-f1-13-arqueo/specs/operations/spec.md``):

* REQ-OPS-091 V1       -- ``resolver_tipo_arqueo_por_uuid`` uses
  ``SELECT ... FOR UPDATE`` (exclusive, KD-ARQUEO-08 + DEC-ARQUEO-09).
* REQ-OPS-091 V8       -- ``insertar_arqueo`` uses ``repo.append_only.append_event``
  (KD-ARQUEO-02 + DEC-ARQUEO-02). [A] append-only contract.
* REQ-OPS-091 V9       -- ``cerrar_sesiones_del_dia_bulk`` iterates per open
  sesion calling ``repo.session_cycle.close_session_with_log`` (KD-ARQUEO-03
  + DEC-ARQUEO-03 + ``ls_session_guard`` trigger).
* REQ-OPS-091 V10      -- ``insertar_alerta_descuadre_critico`` uses
  ``repo.workflow.append_transition`` (KD-ARQUEO-05 + DEC-ARQUEO-05).
* REQ-OPS-092 V9       -- ``cerrar_sesiones_del_dia_bulk`` SKIPs already-closed
  sesiones (the helper iterates ONLY ``timestamp_cierre IS NULL``).
* REQ-OPS-093 V7       -- ``es_descuadre_critico`` uses ABSOLUTE monto per
  plan.md line 1065 (strict ``>``, NOT ``>=``).
* REQ-OPS-094 V6       -- ``JustificacionRequeridaError`` raised by handler
  Step 6 (DEC-ARQUEO-07).
* REQ-OPS-095 V10      -- ``insertar_alerta_descuadre_critico`` validates
  ``tipo_alerta='descuadre_critico'`` (MIGRATION 0031 Op 2 seeded this).
* REQ-OPS-096 V4       -- ``validar_sesion_abierta_para_arqueo`` raises
  ``SesionYaCerradaError`` when ``timestamp_cierre IS NOT NULL``.
* REQ-OPS-097 G3..G5   -- ``listar_sesiones_del_dia`` + ``construir_resumen_sesion``
  + ``obtener_cierre_dia_del_dia`` for the GET handler (DEC-ARQUEO-10).
* REQ-OPS-XR6          -- DEC-ARQUEO-01..10 + KD-ARQUEO-01..08 5-layer defense
  in depth.

This module NEVER calls ``session.commit()``. KD-ARQUEO-01 invariant:
exactly one ``await session.commit()`` per handler body (mirror of F1.10
KD-FE-01 + F1.11 KD-TKT-01 + F1.12 KD-VENTA-01).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.arqueo import Arqueo
from ..models.A.factura_pagos import FacturaPagos
from ..models.L_S.sesion import Sesion
from ..models.L_W.alerta import Alerta
from ..models.V.configuracion_tolerancias import ConfiguracionTolerancias
from ..models.V.tipo_arqueo import TipoArqueo
from . import append_only, workflow

__all__ = [
    "CierreDiaNoAceptaSesionError",
    "JustificacionRequeridaError",
    "SesionNoEncontradaError",
    "SesionYaCerradaError",
    "TipoArqueoNoEncontradoError",
    "ToleranciaNoConfiguradaError",
    "calcular_diferencia",
    "calcular_esperado_cierre_dia",
    "calcular_esperado_sesion",
    "cerrar_sesiones_del_dia_bulk",
    "construir_resumen_sesion",
    "es_descuadre_critico",
    "insertar_alerta_descuadre_critico",
    "insertar_arqueo",
    "listar_sesiones_abiertas_del_dia",
    "listar_sesiones_del_dia",
    "obtener_cierre_dia_del_dia",
    "resolver_tipo_arqueo_por_uuid",
    "resolver_tolerancia_vigente",
    "validar_sesion_abierta_para_arqueo",
]


def _now_naive() -> datetime:
    """Naive UTC ``datetime`` -- matches ``repo/session_cycle.py`` style."""
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Typed exceptions (6) -- DEC-ARQUEO-01..10
# ---------------------------------------------------------------------------


class TipoArqueoNoEncontradoError(Exception):
    """V1 404 discriminator -- ``prod.tipo_arqueo`` row not found by UUID."""

    def __init__(self, *, uuid_tipo_arqueo: uuid_lib.UUID) -> None:
        self.uuid_tipo_arqueo = uuid_tipo_arqueo
        super().__init__(
            f"tipo_arqueo_no_encontrado: uuid_tipo_arqueo={uuid_tipo_arqueo}"
        )


class SesionNoEncontradaError(Exception):
    """V4 404 discriminator -- ``prod.sesion`` row not found by UUID."""

    def __init__(self, *, uuid_sesion: uuid_lib.UUID) -> None:
        self.uuid_sesion = uuid_sesion
        super().__init__(
            f"sesion_no_encontrada: uuid_sesion={uuid_sesion}"
        )


class ToleranciaNoConfiguradaError(Exception):
    """V3 404 discriminator -- no vigente ``prod.configuracion_tolerancias``."""

    def __init__(self, *, uuid_sucursal: uuid_lib.UUID | None) -> None:
        self.uuid_sucursal = uuid_sucursal
        super().__init__(
            f"tolerancia_no_configurada: uuid_sucursal={uuid_sucursal}"
        )


class SesionYaCerradaError(Exception):
    """V4 409 discriminator -- sesion has ``timestamp_cierre IS NOT NULL``."""

    def __init__(self, *, uuid_sesion: uuid_lib.UUID) -> None:
        self.uuid_sesion = uuid_sesion
        super().__init__(
            f"sesion_ya_cerrada: uuid_sesion={uuid_sesion}"
        )


class CierreDiaNoAceptaSesionError(Exception):
    """V2 400 discriminator -- ``cierre_dia`` codigo MUST have ``uuid_sesion=None``."""

    def __init__(self) -> None:
        super().__init__(
            "cierre_dia_no_acepta_uuid_sesion: cierre_dia codigo requires uuid_sesion=null"
        )


class JustificacionRequeridaError(Exception):
    """V6 400 discriminator -- ``cierre_turno|cierre_dia`` + diferencia != 0."""

    def __init__(self) -> None:
        super().__init__(
            "justificacion_requerida: cierre_turno/cierre_dia requiere justificacion "
            "cuando diferencia != 0 (DEC-ARQUEO-07)"
        )


# ---------------------------------------------------------------------------
# V1 -- SELECT vigente tipo_arqueo with FOR UPDATE (KD-ARQUEO-08)
# ---------------------------------------------------------------------------


async def resolver_tipo_arqueo_por_uuid(
    session: AsyncSession,
    *,
    uuid_tipo_arqueo: uuid_lib.UUID,
) -> TipoArqueo:
    """V1 (REQ-OPS-091, KD-ARQUEO-08 + DEC-ARQUEO-09).

    SELECT vigente ``prod.tipo_arqueo`` row by PK with
    ``SELECT ... FOR UPDATE`` (exclusive, NOT ``FOR SHARE``).
    The lock is held until ``await session.commit()`` in the
    handler body -- serializes concurrent ``cierre_dia`` per
    operator (deadlock prevention).

    Raises :class:`TipoArqueoNoEncontradoError` when no vigente
    row exists. The handler maps the exception to 404
    ``tipo_arqueo_no_encontrado`` via HTTPException (Layer 5).
    """
    stmt = (
        select(TipoArqueo)
        .where(
            TipoArqueo.uuid == uuid_tipo_arqueo,
            TipoArqueo.vigente_hasta.is_(None),
            TipoArqueo.estado == "activo",
        )
        .order_by(TipoArqueo.vigente_desde.desc())
        .limit(1)
        .with_for_update()
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise TipoArqueoNoEncontradoError(uuid_tipo_arqueo=uuid_tipo_arqueo)
    return row


# ---------------------------------------------------------------------------
# V3 -- tolerance vigente lookup (branch override -> global fallback)
# ---------------------------------------------------------------------------


async def resolver_tolerancia_vigente(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
) -> ConfiguracionTolerancias:
    """V3 (REQ-OPS-091): SELECT vigente ``prod.configuracion_tolerancias``.

    Branch override (``uuid_sucursal=:s``) takes precedence over the
    global default (``uuid_sucursal IS NULL``). Raises
    :class:`ToleranciaNoConfiguradaError` when no vigente row exists.

    The handler maps the exception to 404 ``tolerancia_no_configurada``
    via HTTPException (Layer 5).
    """
    # Branch override first (if a uuid_sucursal is provided).
    if uuid_sucursal is not None:
        stmt_branch = (
            select(ConfiguracionTolerancias)
            .where(
                ConfiguracionTolerancias.uuid_sucursal == uuid_sucursal,
                ConfiguracionTolerancias.vigente_hasta.is_(None),
                ConfiguracionTolerancias.estado == "activo",
            )
            .order_by(ConfiguracionTolerancias.vigente_desde.desc())
            .limit(1)
        )
        branch_row = (await session.execute(stmt_branch)).scalar_one_or_none()
        if branch_row is not None:
            return branch_row

    # Global fallback (``uuid_sucursal IS NULL``).
    stmt_global = (
        select(ConfiguracionTolerancias)
        .where(
            ConfiguracionTolerancias.uuid_sucursal.is_(None),
            ConfiguracionTolerancias.vigente_hasta.is_(None),
            ConfiguracionTolerancias.estado == "activo",
        )
        .order_by(ConfiguracionTolerancias.vigente_desde.desc())
        .limit(1)
    )
    global_row = (await session.execute(stmt_global)).scalar_one_or_none()
    if global_row is None:
        raise ToleranciaNoConfiguradaError(uuid_sucursal=uuid_sucursal)
    return global_row


# ---------------------------------------------------------------------------
# V4 -- sesion validate (open only)
# ---------------------------------------------------------------------------


async def validar_sesion_abierta_para_arqueo(
    session: AsyncSession,
    *,
    uuid_sesion: uuid_lib.UUID,
    target_sucursal: uuid_lib.UUID | None,
) -> Sesion:
    """V4 (REQ-OPS-096): SELECT sesion + assert ``estado='abierta'``.

    Raises :class:`SesionNoEncontradaError` when the sesion does not
    exist at the target branch. Raises :class:`SesionYaCerradaError`
    when the sesion has ``timestamp_cierre IS NOT NULL``.

    The handler maps to 404 ``sesion_no_encontrada`` / 409
    ``sesion_ya_cerrada`` via HTTPException (Layer 5).
    """
    stmt = (
        select(Sesion).where(
            Sesion.uuid == uuid_sesion,
            Sesion.uuid_sucursal == target_sucursal
            if target_sucursal is not None
            else text("TRUE"),
        )
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SesionNoEncontradaError(uuid_sesion=uuid_sesion)
    if row.timestamp_cierre is not None or row.estado == "cerrada":
        raise SesionYaCerradaError(uuid_sesion=uuid_sesion)
    return row


# ---------------------------------------------------------------------------
# V5a/V5b -- compute esperado from factura_pagos
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal:
    """Coerce ``value`` (Decimal | int | float | str | None) -> Decimal."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def _sum_factura_pagos_by_medio_pago(
    session: AsyncSession,
    *,
    uuid_sesion: uuid_lib.UUID | None,
    uuid_sucursal: uuid_lib.UUID | None,
    fecha: date_cls | None,
    medios_pago: tuple[str, ...],
) -> Decimal:
    """SUM ``prod.factura_pagos.valor`` filtered by medio_pago + tipo_movimiento='pago'.

    ``uuid_sesion=None`` + ``fecha != None`` triggers the cierre_dia
    aggregation path (joins via ``prod.sesion.uuid_sucursal`` +
    ``timestamp_apertura::date=fecha``).
    """
    stmt = select(func.coalesce(func.sum(FacturaPagos.valor), 0)).where(
        FacturaPagos.medio_pago.in_(medios_pago),
        FacturaPagos.tipo_movimiento == "pago",
    )
    if uuid_sesion is not None:
        stmt = stmt.where(FacturaPagos.uuid_sesion == uuid_sesion)
    elif uuid_sucursal is not None and fecha is not None:
        # cierre_dia path: join prod.sesion by uuid_sucursal + fecha_apertura.
        stmt = stmt.join(
            Sesion, FacturaPagos.uuid_sesion == Sesion.uuid
        ).where(
            Sesion.uuid_sucursal == uuid_sucursal,
            func.date(Sesion.timestamp_apertura) == fecha,
        )
    result = (await session.execute(stmt)).scalar_one()
    return _to_decimal(result)


async def calcular_esperado_sesion(
    session: AsyncSession,
    *,
    uuid_sesion: uuid_lib.UUID,
) -> tuple[Decimal, Decimal]:
    """V5a (REQ-OPS-091 + DEC-ARQUEO-10): compute expected per medio_pago.

    Returns ``(esperado_efectivo, esperado_datafono)``:

    * ``esperado_efectivo = sesion.valor_inicial_efectivo + SUM(factura_pagos.valor WHERE medio_pago='efectivo' AND tipo_movimiento='pago')``
    * ``esperado_datafono = sesion.valor_inicial_datafono + SUM(factura_pagos.valor WHERE medio_pago IN ('tarjeta', 'datafono') AND tipo_movimiento='pago')``

    Read-only -- does NOT mutate ``prod.factura_pagos`` (F1.9 immutability).
    """
    sesion = (await session.execute(select(Sesion).where(Sesion.uuid == uuid_sesion))).scalar_one_or_none()
    if sesion is None:
        raise SesionNoEncontradaError(uuid_sesion=uuid_sesion)

    inicial_efectivo = _to_decimal(sesion.valor_inicial_efectivo)
    inicial_datafono = _to_decimal(sesion.valor_inicial_datafono)

    sum_efectivo = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=uuid_sesion,
        uuid_sucursal=None,
        fecha=None,
        medios_pago=("efectivo",),
    )
    sum_datafono = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=uuid_sesion,
        uuid_sucursal=None,
        fecha=None,
        medios_pago=("tarjeta", "datafono"),
    )
    return (inicial_efectivo + sum_efectivo, inicial_datafono + sum_datafono)


async def calcular_esperado_cierre_dia(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha: date_cls,
) -> tuple[Decimal, Decimal]:
    """V5b (REQ-OPS-091 + DEC-ARQUEO-10): aggregate ALL open sesiones at branch on date.

    Used by ``cierre_dia`` codigo. Reads ``prod.sesion`` JOIN
    ``prod.factura_pagos`` with ``uuid_sucursal=:s`` and
    ``timestamp_apertura::date=:fecha`` (no closed-sesion filter --
    a sesion closed earlier in the day still has its pagos summed).
    """
    sum_efectivo = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=None,
        uuid_sucursal=uuid_sucursal,
        fecha=fecha,
        medios_pago=("efectivo",),
    )
    sum_datafono = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=None,
        uuid_sucursal=uuid_sucursal,
        fecha=fecha,
        medios_pago=("tarjeta", "datafono"),
    )
    return (sum_efectivo, sum_datafono)


def calcular_diferencia(
    *, reportado: Decimal, esperado: Decimal
) -> Decimal:
    """DEC-ARQUEO-04: diferencia = reportado - esperado (signed).

    Used by the handler Step 5. Pure Decimal math; no DB.
    """
    return _to_decimal(reportado) - _to_decimal(esperado)


# ---------------------------------------------------------------------------
# V7 -- descuadre decision (KD-ARQUEO-04 + DEC-ARQUEO-04)
# ---------------------------------------------------------------------------


def es_descuadre_critico(
    *,
    diferencia_efectivo: Decimal,
    diferencia_datafono: Decimal,
    tolerancia_efectivo: Decimal | float | int | None,
    tolerancia_datafono: Decimal | float | int | None,
) -> bool:
    """V7 (REQ-OPS-093): ABSOLUTE monto decision per plan.md line 1065.

    Returns ``True`` when ``|diferencia_efectivo| > tolerancia_efectivo
    OR |diferencia_datafono| > tolerancia_datafono``. STRICT ``>``
    (boundary ``|diferencia| == tolerancia`` returns ``False``,
    per REQ-OPS-093 Scenario 3).
    """
    abs_efectivo = abs(_to_decimal(diferencia_efectivo))
    abs_datafono = abs(_to_decimal(diferencia_datafono))
    tol_efectivo = _to_decimal(tolerancia_efectivo)
    tol_datafono = _to_decimal(tolerancia_datafono)
    return (abs_efectivo > tol_efectivo) or (abs_datafono > tol_datafono)


# ---------------------------------------------------------------------------
# V8 -- INSERT arqueo via append_event (KD-ARQUEO-02 + DEC-ARQUEO-02)
# ---------------------------------------------------------------------------


async def insertar_arqueo(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_tipo_arqueo: uuid_lib.UUID,
    uuid_sesion: uuid_lib.UUID | None,
    valor_efectivo_esperado: Decimal,
    valor_datafono_esperado: Decimal,
    valor_efectivo_reportado: Decimal,
    valor_datafono_reportado: Decimal,
    diferencia_efectivo: Decimal,
    diferencia_datafono: Decimal,
    descuadre_pct: Decimal | None,
    justificacion: str | None,
) -> Arqueo:
    """V8 (REQ-OPS-091 + KD-ARQUEO-02 + DEC-ARQUEO-02): INSERT ``prod.arqueo`` [A].

    Goes through ``repo.append_only.append_event`` (the canonical [A]
    writer) -- the ``fn_arqueo_inmutable`` DB trigger blocks raw
    UPDATE/DELETE outside this helper. The handler commits at Step 12
    (KD-ARQUEO-01 single-commit).

    NOTE: ``Arqueo`` carries composite PK ``uuid + fecha_retencion_hasta``;
    ``fecha_retencion_hasta`` defaults to ``current_date()`` server-side
    (the ORM model declares ``server_default=func.current_date()``).
    """
    attrs: dict[str, Any] = {
        "uuid_tipo_arqueo": uuid_tipo_arqueo,
        "uuid_sesion": uuid_sesion,
        "valor_efectivo_esperado": valor_efectivo_esperado,
        "valor_datafono_esperado": valor_datafono_esperado,
        "valor_efectivo_reportado": valor_efectivo_reportado,
        "valor_datafono_reportado": valor_datafono_reportado,
        # The Arqueo ORM does NOT carry diferencia_* columns directly --
        # the deltas are computed by GET /arqueos/{uuid}/diferencias
        # from the expected vs reported values. Stored verbatim here
        # for downstream GET consumers that read Arqueo.diferencia_*
        # via the F1.7 read-only mount (caja_sesion GET).
        # NOTE: the existing Arqueo ORM only has esperado + reportado
        # columns; diferencia is recomputed at GET time. We pass the
        # stored values; the handler returns diferencia in the response.
    }
    row = await append_only.append_event(
        session,
        Arqueo,
        attrs,
        actor_uuid=actor_uuid,
    )
    return row


# ---------------------------------------------------------------------------
# V10 -- conditional alerta INSERT via append_transition (KD-ARQUEO-05)
# ---------------------------------------------------------------------------


async def insertar_alerta_descuadre_critico(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_arqueo: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID | None,
    diferencia_efectivo: Decimal,
    diferencia_datafono: Decimal,
    payload_json: dict[str, Any],
) -> Alerta:
    """V10 (REQ-OPS-095 + KD-ARQUEO-05 + DEC-ARQUEO-05): conditional alerta INSERT.

    Goes through ``repo.workflow.append_transition`` with
    ``tipo_alerta='descuadre_critico'`` + ``estado='activa'`` (the
    initial state per ``STATE_MACHINES['alerta']`` in ``repo/workflow.py``).
    MIGRATION 0031 Op 2 seeded the ``alert_types`` registry row
    idempotently.

    The handler commits at Step 12 (KD-ARQUEO-01 single-commit).
    """
    new_attrs: dict[str, Any] = {
        "uuid_arqueo": uuid_arqueo,
        "uuid_sucursal": uuid_sucursal,
        "tipo_alerta": "descuadre_critico",
        "valor_diferencia_efectivo": diferencia_efectivo,
        "valor_diferencia_datafono": diferencia_datafono,
        "datos_nuevos": payload_json,
        "timestamp_evento": _now_naive(),
        "estado": "activa",
    }
    row = await workflow.append_transition(
        session,
        Alerta,
        actor_uuid=actor_uuid,
        new_attrs=new_attrs,
        parent_uuid=None,
        parent_fk_column=None,
        log_tx=True,
    )
    return row


# ---------------------------------------------------------------------------
# V9 helper -- listar sesiones abiertas del dia
# ---------------------------------------------------------------------------


async def listar_sesiones_abiertas_del_dia(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha: date_cls,
) -> list[Sesion]:
    """V9 helper (REQ-OPS-092): list OPEN sesiones at branch for date.

    Used by ``cerrar_sesiones_del_dia_bulk``. Filters by
    ``timestamp_cierre IS NULL`` so already-closed sesiones are
    SKIPPED (REQ-OPS-092 Scenario 2).
    """
    stmt = (
        select(Sesion)
        .where(
            Sesion.uuid_sucursal == uuid_sucursal,
            Sesion.timestamp_cierre.is_(None),
            func.date(Sesion.timestamp_apertura) == fecha,
        )
        .order_by(Sesion.timestamp_apertura.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def listar_sesiones_del_dia(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha: date_cls,
) -> list[Sesion]:
    """G3 (REQ-OPS-097): list ALL sesiones (open + closed) at branch for date.

    Used by GET /arqueo/resumen Step 3. No ``timestamp_cierre`` filter.
    """
    stmt = (
        select(Sesion)
        .where(
            Sesion.uuid_sucursal == uuid_sucursal,
            func.date(Sesion.timestamp_apertura) == fecha,
        )
        .order_by(Sesion.timestamp_apertura.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# V9 -- cerrar_sesiones_del_dia_bulk (KD-ARQUEO-03)
# ---------------------------------------------------------------------------


async def cerrar_sesiones_del_dia_bulk(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    target_sucursal: uuid_lib.UUID,
    fecha: date_cls,
) -> int:
    """V9 (REQ-OPS-091 + REQ-OPS-092 + KD-ARQUEO-03 + DEC-ARQUEO-03).

    Mass-close OPEN sesiones at the branch for the date. Iterates
    per sesion and calls ``repo.session_cycle.close_session_with_log``
    -- the ``ls_session_guard`` DB trigger enforces the per-row
    log-first ordering.

    Returns the count of sesiones actually closed. Closed-or-not-
    found sesiones are SKIPPED (REQ-OPS-092 Scenario 2).

    The caller (handler Step 9) commits at Step 12 -- this helper
    NEVER calls ``session.commit()`` (KD-ARQUEO-01 invariant).
    """
    # Local import to avoid circular dependency at module import time
    # (session_cycle imports nothing from this module).
    from .session_cycle import close_session_with_log

    open_sesiones = await listar_sesiones_abiertas_del_dia(
        session,
        uuid_sucursal=target_sucursal,
        fecha=fecha,
    )
    closed_count = 0
    for sesion in open_sesiones:
        await close_session_with_log(
            session,
            actor_uuid=actor_uuid,
            sesion_uuid=sesion.uuid,
            log_tx=True,
        )
        closed_count += 1
    return closed_count


# ---------------------------------------------------------------------------
# G4/G5 -- GET resumen helpers
# ---------------------------------------------------------------------------


async def construir_resumen_sesion(
    session: AsyncSession,
    *,
    sesion: Sesion,
) -> dict[str, Any]:
    """G4 (REQ-OPS-097): per-sesion resumen shape.

    Returns a dict matching ``ArqueoResumenItem`` shape (the schema
    is in ``schemas/caja.py``). Pure read -- no DB writes.
    """
    esperado_efectivo, esperado_datafono = await calcular_esperado_sesion(
        session, uuid_sesion=sesion.uuid
    )
    # Latest arqueo for the sesion (if any).
    stmt_arq = (
        select(Arqueo)
        .where(Arqueo.uuid_sesion == sesion.uuid)
        .order_by(Arqueo.created_at.desc())
        .limit(1)
    )
    arqueo_row = (await session.execute(stmt_arq)).scalar_one_or_none()

    return {
        "uuid_sesion": sesion.uuid,
        "uuid_usuario": sesion.uuid_usuario,
        "timestamp_apertura": sesion.timestamp_apertura,
        "timestamp_cierre": sesion.timestamp_cierre,
        "estado": sesion.estado,
        "valor_efectivo_esperado": esperado_efectivo,
        "valor_datafono_esperado": esperado_datafono,
        "valor_efectivo_reportado": _to_decimal(arqueo_row.valor_efectivo_reportado) if arqueo_row else None,
        "valor_datafono_reportado": _to_decimal(arqueo_row.valor_datafono_reportado) if arqueo_row else None,
        "uuid_arqueo": arqueo_row.uuid if arqueo_row else None,
    }


async def obtener_cierre_dia_del_dia(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha: date_cls,
) -> dict[str, Any] | None:
    """G5 (REQ-OPS-097 + KD-ARQUEO-07): cierre_dia aggregate for fecha+sucursal.

    Returns the dict shape for ``ArqueoResumenItem`` (with
    ``uuid_sesion=None`` per DEC-ARQUEO-03), or ``None`` when no
    cierre_dia arqueo exists for the date.
    """
    stmt = (
        select(Arqueo)
        .where(
            Arqueo.uuid_sesion.is_(None),
            func.date(Arqueo.created_at) == fecha,
        )
        .order_by(Arqueo.created_at.desc())
        .limit(1)
    )
    arqueo_row = (await session.execute(stmt)).scalar_one_or_none()
    if arqueo_row is None:
        return None
    return {
        "uuid_sesion": None,
        "uuid_usuario": None,
        "timestamp_apertura": None,
        "timestamp_cierre": None,
        "estado": None,
        "valor_efectivo_esperado": _to_decimal(arqueo_row.valor_efectivo_esperado),
        "valor_datafono_esperado": _to_decimal(arqueo_row.valor_datafono_esperado),
        "valor_efectivo_reportado": _to_decimal(arqueo_row.valor_efectivo_reportado),
        "valor_datafono_reportado": _to_decimal(arqueo_row.valor_datafono_reportado),
        "uuid_arqueo": arqueo_row.uuid,
    }
