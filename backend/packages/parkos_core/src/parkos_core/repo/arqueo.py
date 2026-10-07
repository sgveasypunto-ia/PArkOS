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

import base64
import json
import uuid as uuid_lib
from datetime import UTC, datetime
from datetime import date as date_cls
from decimal import Decimal
from typing import Any, Dict

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.arqueo import Arqueo
from ..models.A.factura_pagos import FacturaPagos
from ..models.L_S.sesion import Sesion
from ..models.L_W.alerta import Alerta
from ..models.V.configuracion_tolerancias import ConfiguracionTolerancias
from ..models.V.sucursal import Sucursal
from ..models.V.tipo_arqueo import TipoArqueo
from ..runtime.tiempo import dia_bogota_rango_utc
from . import append_only, workflow


def _inicio_dia(fecha: date_cls) -> datetime:
    """Start (naive UTC) of the Bogota business day ``fecha`` (H9)."""
    return dia_bogota_rango_utc(fecha)[0]


def _fin_dia(fecha: date_cls) -> datetime:
    """Exclusive end (naive UTC) of the Bogota business day ``fecha`` (H9)."""
    return dia_bogota_rango_utc(fecha)[1]

__all__ = [
    "CierreDiaNoAceptaSesionError",
    "InvalidArqueoCursorError",
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
    "decode_arqueo_cursor",
    "encode_arqueo_cursor",
    "es_descuadre_critico",
    "insertar_alerta_descuadre_critico",
    "insertar_arqueo",
    "listar_arqueos_admin",
    "listar_sucursales_vigentes",
    "listar_sesiones_abiertas_del_dia",
    "listar_sesiones_del_dia",
    "obtener_cierre_dia_del_dia",
    "resumen_admin_del_dia",
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
    # F11.3 follow-up -- Sesion has NO ``estado`` column (state is
    # encoded via ``timestamp_cierre IS NULL`` -- bi-temporal close).
    # The previous check ``row.estado == "cerrada"`` raised
    # AttributeError on every arqueo POST. State discrimination:
    #   timestamp_cierre IS NULL  -> open
    #   timestamp_cierre NOT NULL -> closed
    if row.timestamp_cierre is not None:
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
            Sesion.timestamp_apertura >= _inicio_dia(fecha),
            Sesion.timestamp_apertura < _fin_dia(fecha),
        )
    result = (await session.execute(stmt)).scalar_one()
    return _to_decimal(result)


async def calcular_esperado_sesion(
    session: AsyncSession,
    *,
    uuid_sesion: uuid_lib.UUID,
) -> Decimal:
    """V5a (REQ-OPS-194): compute expected efectivo for one sesion.

    Returns ``esperado_efectivo`` (single Decimal, NOT a tuple) as:

    * ``esperado_efectivo = sesion.valor_inicial_efectivo + SUM(factura_pagos.valor WHERE medio_pago='efectivo' AND tipo_movimiento='pago')``

    The datafono dimension is excluded from the result per the F12.1.1
    backend-ignore-datafono change: the datafono column is preserved in
    the schema (compliance) but no longer participates in the expected
    calculation. (D4 default; previously returned a ``(esperado_efectivo,
    esperado_datafono)`` tuple -- call sites updated.)

    Read-only -- does NOT mutate ``prod.factura_pagos`` (F1.9 immutability).
    """
    sesion = (await session.execute(select(Sesion).where(Sesion.uuid == uuid_sesion))).scalar_one_or_none()
    if sesion is None:
        raise SesionNoEncontradaError(uuid_sesion=uuid_sesion)

    inicial_efectivo = _to_decimal(sesion.valor_inicial_efectivo)

    sum_efectivo = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=uuid_sesion,
        uuid_sucursal=None,
        fecha=None,
        medios_pago=("efectivo",),
    )
    return inicial_efectivo + sum_efectivo


async def calcular_esperado_cierre_dia(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fecha: date_cls,
) -> Decimal:
    """V5b (REQ-OPS-194): aggregate ALL sesiones at branch on date (efectivo only).

    Used by ``cierre_dia`` codigo. Reads ``prod.sesion`` JOIN
    ``prod.factura_pagos`` with ``uuid_sucursal=:s`` and
    ``timestamp_apertura::date=:fecha`` (no closed-sesion filter --
    a sesion closed earlier in the day still has its pagos summed).
    The datafono dimension is excluded from the aggregate per F12.1.1.
    """
    sum_efectivo = await _sum_factura_pagos_by_medio_pago(
        session,
        uuid_sesion=None,
        uuid_sucursal=uuid_sucursal,
        fecha=fecha,
        medios_pago=("efectivo",),
    )
    return sum_efectivo


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
    diferencia_efectivo: Decimal | float,
    tolerancia_efectivo: Decimal | float | int | None,
) -> bool:
    """V7 (REQ-OPS-195): ABSOLUTE monto decision on effective only.

    Returns ``True`` when ``|diferencia_efectivo| > tolerancia_efectivo``.
    STRICT ``>`` (boundary ``|diferencia| == tolerancia`` returns
    ``False``, per REQ-OPS-093 Scenario 3 / REQ-OPS-195).

    The datafono dimension is REMOVED from this decision per F12.1.1
    (D5 default): the datafono column is preserved in the schema but no
    longer drives an alerta. A ``TypeError`` at the call site is the
    intentional failure mode if a caller still passes the legacy
    ``diferencia_datafono`` / ``tolerancia_datafono`` kwargs.
    """
    abs_efectivo = abs(_to_decimal(diferencia_efectivo))
    tol_efectivo = _to_decimal(tolerancia_efectivo)
    return abs_efectivo > tol_efectivo


# ---------------------------------------------------------------------------
# V8 -- INSERT arqueo via append_event (KD-ARQUEO-02 + DEC-ARQUEO-02)
# ---------------------------------------------------------------------------


async def insertar_arqueo(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_tipo_arqueo: uuid_lib.UUID,
    uuid_sesion: uuid_lib.UUID | None,
    valor_efectivo_esperado: Decimal,
    valor_efectivo_reportado: Decimal,
    diferencia_efectivo: Decimal,
    descuadre_pct: Decimal | None,
    justificacion: str | None,
) -> Arqueo:
    """V8 (REQ-OPS-091 + KD-ARQUEO-02 + DEC-ARQUEO-02): INSERT ``prod.arqueo`` [A].

    Goes through ``repo.append_only.append_event`` (the canonical [A]
    writer) -- the ``fn_arqueo_inmutable`` DB trigger blocks raw
    UPDATE/DELETE outside this helper. The handler commits at Step 12
    (KD-ARQUEO-01 single-commit).

    F12.1.1 (REQ-OPS-091 modified): the datafono columns are NO LONGER
    populated by the handler. The DB columns
    (``valor_datafono_esperado``, ``valor_datafono_reportado``,
    ``diferencia_datafono``) are preserved for historical rows
    (compliance + D3 bitácora) but receive the column default (server /
    arithmetic, ``NULL`` or ``0``) for new rows. The handler computes only
    the effective difference.

    NOTE: ``Arqueo`` carries composite PK ``uuid + fecha_retencion_hasta``;
    ``fecha_retencion_hasta`` defaults to ``current_date()`` server-side
    (the ORM model declares ``server_default=func.current_date()``).

    QA batch Arqueos (2026-10-02): ``uuid_sucursal`` used to be left out of
    ``attrs`` entirely -- same bug class as ``factura_pagos`` (migration
    0073): the global tenant listener (``db/tenancy.py``) only auto-filters
    SELECT/UPDATE/DELETE, never INSERT, so a write path that forgets the
    column leaves it permanently NULL. Every ``prod.arqueo`` row ever
    created (both ``admin-`` and ``operador-`` issuers -- this one is not
    issuer-specific) silently dropped out of ANY branch-scoped read
    (``GET /api/v1/caja/arqueo?uuid_sucursal=...``, the admin list in
    ``/arqueos``). The handler already computes ``target_sucursal`` at
    Step 2a; it is now threaded through to this INSERT.
    """
    attrs: dict[str, Any] = {
        "uuid_sucursal": uuid_sucursal,
        "uuid_tipo_arqueo": uuid_tipo_arqueo,
        "uuid_sesion": uuid_sesion,
        "valor_efectivo_esperado": valor_efectivo_esperado,
        "valor_efectivo_reportado": valor_efectivo_reportado,
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
    # F11.3 follow-up -- ``append_event`` calls ``session.add(new_row)``
    # but does NOT flush, so the server-side ``gen_random_uuid()``
    # default on the primary key is still None until commit. The
    # handler reads ``.uuid`` IMMEDIATELY (line 273) to pass to the
    # alerta INSERT chain and the response shape; without an
    # explicit flush here both downstream operations crash on
    # ``UUID input should be a string, bytes or UUID object``.
    # Single-commit invariant (KD-ARQUEO-01) is preserved -- the
    # explicit flush only emits the INSERT statement, the COMMIT
    # still happens once at handler Step 12.
    await session.flush()
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
    payload_json: dict[str, Any],
) -> Alerta:
    """V10 (REQ-OPS-095 + KD-ARQUEO-05 + DEC-ARQUEO-05): conditional alerta INSERT.

    Goes through ``repo.workflow.append_transition`` with
    ``tipo_alerta='descuadre_critico'`` + ``estado='abierta'`` (the
    initial state per ``STATE_MACHINES['alerta']`` in ``repo/workflow.py``).
    MIGRATION 0031 Op 2 seeded the ``alert_types`` registry row
    idempotently.

    F12.1.1 (REQ-OPS-094 modified / REQ-OPS-196): the alerta payload
    no longer carries ``diferencia_datafono`` (the datafono dimension
    is excluded from the alerta decision). The DB column
    ``prod.alerta.valor_diferencia_datafono`` is preserved + nullable
    for the historical bitácora (D3 drill-down); new alertas
    materialize it as ``NULL``.

    The handler commits at Step 12 (KD-ARQUEO-01 single-commit).
    """
    new_attrs: dict[str, Any] = {
        "uuid_arqueo": uuid_arqueo,
        "uuid_sucursal": uuid_sucursal,
        "tipo_alerta": "descuadre_critico",
        "valor_diferencia_efectivo": diferencia_efectivo,
        "datos_nuevos": payload_json,
        "timestamp_evento": _now_naive(),
        "estado": "abierta",
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
    # F11.3 follow-up -- ``append_transition`` calls ``session.add(new_row)``
    # but does NOT flush, so the server-side ``gen_random_uuid()`` default
    # on the Alerta primary key is still ``None`` until the handler's
    # Step 12 commit. The handler reads ``.uuid`` IMMEDIATELY to surface
    # it in the response (alerta_uuid field). Without an explicit flush
    # the response always returns ``alerta_uuid: null`` even though the
    # row IS created (verified by GET /workflows/alerta showing 13+
    # descuadre_critico rows accumulating per arqueo POST). Same fix
    # pattern as insertar_arqueo -- single-commit invariant preserved.
    await session.flush()
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
            Sesion.timestamp_apertura >= _inicio_dia(fecha),
            Sesion.timestamp_apertura < _fin_dia(fecha),
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
            Sesion.timestamp_apertura >= _inicio_dia(fecha),
            Sesion.timestamp_apertura < _fin_dia(fecha),
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
    esperado_efectivo = await calcular_esperado_sesion(
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

    # F11.3 follow-up -- Sesion has NO ``estado`` column. State is
    # derived from ``timestamp_cierre`` (bi-temporal close):
    #   timestamp_cierre IS NULL  -> 'abierta'
    #   timestamp_cierre NOT NULL -> 'cerrada'
    # The downstream F10.3 ``useArqueoResumenPorSesion`` schema expects
    # ``estado: z.string().nullable()`` so the FE can render the
    # session row status badge.
    estado_derivado = "cerrada" if sesion.timestamp_cierre is not None else "abierta"
    return {
        "uuid_sesion": sesion.uuid,
        "uuid_usuario": sesion.uuid_usuario,
        "timestamp_apertura": sesion.timestamp_apertura,
        "timestamp_cierre": sesion.timestamp_cierre,
        "estado": estado_derivado,
        "valor_efectivo_esperado": esperado_efectivo,
        "valor_efectivo_reportado": _to_decimal(arqueo_row.valor_efectivo_reportado) if arqueo_row else None,
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
        "valor_efectivo_reportado": _to_decimal(arqueo_row.valor_efectivo_reportado),
        "uuid_arqueo": arqueo_row.uuid,
    }


# ---------------------------------------------------------------------------
# HU-F18.1 admin list (REQ-X2 cross-branch arqueo visibility)
# ---------------------------------------------------------------------------


class InvalidArqueoCursorError(Exception):
    """Raised when the base64 cursor payload is malformed.

    Mapped to ``400 invalid_cursor`` by the route handler. Mirrors the
    ``repo.log_transaccional.InvalidAuditCursorError`` shape so the
    cursor contract is uniform across audit and arqueo listings.
    """


def encode_arqueo_cursor(items: list[Arqueo], limit: int) -> str | None:
    """Opaque base64 ``(timestamp_evento_iso, uuid_str)`` cursor.

    Returns ``None`` at EOF (when the SQL returned no more rows than
    the page asked for). When the EOF probe (``limit + 1``) returns
    more, the cursor is the LAST SHIPPED row's key
    (``items[limit - 1]``) -- same convention as the audit cursor.
    """
    if len(items) <= limit:
        return None
    last = items[limit - 1]
    payload = json.dumps(
        {
            "ts": last.created_at.isoformat(),
            "uuid": str(last.uuid),
        },
        separators=(",", ":"),
    )
    return base64.b64encode(payload.encode("ascii")).decode("ascii")


def decode_arqueo_cursor(cursor: str | None) -> tuple[datetime, uuid_lib.UUID] | None:
    """Decode the opaque cursor back into ``(timestamp_evento, uuid)``.

    Returns ``None`` for the first page (no cursor). Raises
    :class:`InvalidArqueoCursorError` on malformed base64 / JSON / missing
    keys -- the route handler maps that to ``400 invalid_cursor``.
    """
    if cursor is None:
        return None
    try:
        decoded = base64.b64decode(cursor.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidArqueoCursorError(f"invalid base64: {exc}") from exc
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise InvalidArqueoCursorError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or "ts" not in data or "uuid" not in data:
        raise InvalidArqueoCursorError(
            "missing required keys (ts, uuid) in cursor payload"
        )
    try:
        return (datetime.fromisoformat(data["ts"]), uuid_lib.UUID(data["uuid"]))
    except (ValueError, TypeError) as exc:
        raise InvalidArqueoCursorError(f"invalid cursor field: {exc}") from exc


async def listar_arqueos_admin(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID | None = None,
    fecha_desde: date_cls | None = None,
    fecha_hasta: date_cls | None = None,
    uuid_tipo_arqueo: uuid_lib.UUID | None = None,
    cursor: tuple[datetime, uuid_lib.UUID] | None,
    limit: int,
) -> list[Arqueo]:
    """HU-F18.1 (REQ-OPS-152): cursor-paginated admin-side arqueo listing.

    All four WHERE predicates are OPTIONAL. Composed with AND. The
    endpoint is admin-only; the ``admin-`` issuer dep at the route
    handler gatekeeps it (no operador- access).

    Parameters:

    - ``uuid_sucursal``: scope to a single branch. The admin sees every
      branch by default; UI-driven filtering by ``<BranchSelector />``.
    - ``fecha_desde`` / ``fecha_hasta``: inclusive date filter applied on
      ``created_at::date``. Both independent (``fecha_desde`` alone
      returns "from that date to now", ``fecha_hasta`` alone returns
      "everything up to that date"). Both ``None`` means "no
      date filter".
    - ``uuid_tipo_arqueo``: scope to a single arqueo-type code. The
      two seed codes are ``auditoria`` and ``cierre_turno`` (one
      per ``prod.caja`` row per migration 0026).

    Pagination mirrors the audit listing pattern: ORDER BY
    ``(created_at DESC, uuid ASC)``; the stable cursor excludes the
    cursor row and everything that sorts strictly after it in the DESC
    stream. Read-only -- does NOT mutate ``prod.arqueo`` (the [A]
    append-only contract from migration 0023 is preserved).
    """
    limit = min(limit, 100)

    stmt = select(Arqueo)
    if uuid_sucursal is not None:
        stmt = stmt.where(Arqueo.uuid_sucursal == uuid_sucursal)
    if fecha_desde is not None:
        stmt = stmt.where(func.date(Arqueo.created_at) >= fecha_desde)
    if fecha_hasta is not None:
        stmt = stmt.where(func.date(Arqueo.created_at) <= fecha_hasta)
    if uuid_tipo_arqueo is not None:
        stmt = stmt.where(Arqueo.uuid_tipo_arqueo == uuid_tipo_arqueo)

    if cursor is not None:
        cursor_ts, cursor_uuid = cursor
        cursor_clause = or_(
            Arqueo.created_at < cursor_ts,
            and_(
                Arqueo.created_at == cursor_ts,
                Arqueo.uuid > cursor_uuid,
            ),
        )
        stmt = stmt.where(cursor_clause)

    stmt = stmt.order_by(Arqueo.created_at.desc(), Arqueo.uuid.asc()).limit(limit + 1)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_alerta_uuids_for_arqueos(
    session: AsyncSession,
    uuid_arqueos: list[uuid_lib.UUID],
) -> dict[uuid_lib.UUID, uuid_lib.UUID]:
    """Batched ``uuid_arqueo`` -> ``alerta.uuid`` lookup for the admin list.

    QA backlog cleanup (2026-10-02, AlertaLink): ``GET /api/v1/caja/arqueo``
    (the admin Listado tab) never surfaced ``alerta_uuid`` per row -- only
    the POST handler's response (Step 10, same transaction the alerta was
    created in) did. Revisiting an arqueo later in the Listado tab had no
    way to recover its alerta's uuid, so ``<AlertaLink>`` always received
    ``null``. One ``uuid_arqueo IN (...)`` query per page (<= ``limit+1``
    rows) is batched here instead of N+1 per-row lookups.

    At most one ``descuadre_critico`` alerta exists per arqueo
    (``insertar_alerta_descuadre_critico`` fires once, in the same POST
    transaction that created the arqueo); an empty input list short-circuits
    to avoid an always-false ``IN ()`` round-trip.
    """
    if not uuid_arqueos:
        return {}
    # Ordered oldest -> newest so the dict comprehension below keeps the
    # LAST (most recent) row per ``uuid_arqueo`` -- if the alerta was ever
    # transitioned (``append_transition`` with a ``parent_uuid``, e.g. an
    # admin moving it to ``en_revision``), that inserts an ADDITIONAL row
    # rather than closing the original (workflow tables chain via
    # ``uuid_alerta_padre`` self-FK, unlike ``[V]``'s vigente_hasta
    # close+insert), so more than one row can share the same
    # ``uuid_arqueo``. The admin should land on the current head of the
    # chain, not the stale root.
    stmt = (
        select(Alerta.uuid_arqueo, Alerta.uuid)
        .where(Alerta.uuid_arqueo.in_(uuid_arqueos))
        .order_by(Alerta.created_at.asc())
    )
    result = await session.execute(stmt)
    return {row.uuid_arqueo: row.uuid for row in result if row.uuid_arqueo is not None}


# ---------------------------------------------------------------------------
# HU-F18.3 admin cross-branch resumen (REQ-OPS-153)
# ---------------------------------------------------------------------------


async def listar_sucursales_vigentes(
    session: AsyncSession,
) -> list[Sucursal]:
    """Return the vigente (vigente_hasta IS NULL) ``prod.sucursal`` rows.

    Used by the admin cross-branch resumen (F18.3) to enumerate every
    branch the admin sees today. Admin's tenant scope (KD-S2) bypasses
    the per-branch filter the operador- issuer would apply.
    """
    stmt = (
        select(Sucursal)
        .where(Sucursal.vigente_hasta.is_(None))
        .order_by(Sucursal.nombre.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def resumen_admin_del_dia(
    session: AsyncSession,
    *,
    fecha: date_cls,
) -> list[Dict[str, Any]]:
    """Cross-branch per-day resumen for the admin (HU-F18.3, REQ-OPS-153).

    Returns one dict per vigente ``prod.sucursal`` with the day's
    expected totals (``calcular_esperado_cierre_dia``), the cierre_dia
    arqueo if one exists, and a total of regular arqueos for the date.

    Used by ``GET /api/v1/admin/caja/arqueo/resumen?fecha=YYYY-MM-DD``
    which mirrors the operator-side ``/caja/arqueo/resumen`` but across
    every branch in one round trip. No tenant scope (``admin-``
    issuer; F18.1 already uses the same split).

    Empty case (``date`` with zero arqueos anywhere) returns ``[]``
    with HTTP 200 -- a day with no activity is a valid response, not
    a 404.
    """
    out: list[Dict[str, Any]] = []
    sucursales = await listar_sucursales_vigentes(session)
    for s in sucursales:
        esperado_e = await calcular_esperado_cierre_dia(
            session,
            uuid_sucursal=s.uuid,
            fecha=fecha,
        )
        # Latest cierre_dia for the date (uuid_sesion IS NULL per DEC-ARQUEO-03).
        stmt_cd = (
            select(Arqueo)
            .where(
                Arqueo.uuid_sucursal == s.uuid,
                Arqueo.uuid_sesion.is_(None),
                func.date(Arqueo.created_at) == fecha,
            )
            .order_by(Arqueo.created_at.desc())
            .limit(1)
        )
        cd_row = (await session.execute(stmt_cd)).scalar_one_or_none()
        # Total regular arqueos at the branch for the date (excludes
        # cierre_dia which has uuid_sesion IS NULL).
        stmt_total = select(func.count(Arqueo.uuid)).where(
            Arqueo.uuid_sucursal == s.uuid,
            func.date(Arqueo.created_at) == fecha,
            Arqueo.uuid_sesion.is_not(None),
        )
        total = int((await session.execute(stmt_total)).scalar_one() or 0)
        cierre_dia_dict = (
            _to_resumen_item(cd_row) if cd_row is not None else None
        )
        out.append(
            {
                "uuid_sucursal": s.uuid,
                "nombre": s.nombre,
                "esperado_efectivo": esperado_e,
                "cierre_dia": cierre_dia_dict,
                "total_arqueos": total,
            }
        )
    return out


def _to_resumen_item(arq: Arqueo) -> Dict[str, Any]:
    """Convert an ``Arqueo`` row to the wire-shape ``ArqueoResumenItem`` dict.

    Mirrors ``construir_resumen_sesion`` but for a single Arqueo
    (cierre_dia has ``uuid_sesion IS NULL`` per DEC-ARQUEO-03). The
    summary caller maps the dict to the Pydantic schema on the way
    out.
    """
    return {
        "uuid": arq.uuid,
        "uuid_tipo_arqueo": arq.uuid_tipo_arqueo,
        "codigo_tipo_arqueo": None,
        "uuid_sesion": arq.uuid_sesion,
        "valor_efectivo_esperado": _to_decimal(arq.valor_efectivo_esperado),
        "valor_datafono_esperado": _to_decimal(arq.valor_datafono_esperado),
        "valor_efectivo_reportado": _to_decimal(arq.valor_efectivo_reportado),
        "valor_datafono_reportado": _to_decimal(arq.valor_datafono_reportado),
        "diferencia_efectivo": _to_decimal(arq.valor_efectivo_reportado)
        - _to_decimal(arq.valor_efectivo_esperado),
        "diferencia_datafono": _to_decimal(arq.valor_datafono_reportado)
        - _to_decimal(arq.valor_datafono_esperado),
        "descuadre_pct": None,
        "alerta_generada": None,
        "alerta_uuid": None,
    }
