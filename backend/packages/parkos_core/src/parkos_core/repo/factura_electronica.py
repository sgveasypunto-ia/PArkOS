"""HU-F1.10 / REQ-OPS-064..074 — FE numbering + estado DIAN + retry.

Helpers for ``POST /api/v1/facturacion/factura-electronica``:

- :func:`buscar_factura_por_uuid` (V1) — checks ``prod.facturas.uuid`` exists.
- :func:`buscar_factura_electronica_por_factura` (V2) — existing FE for uuid_factura.
- :func:`buscar_factura_electronica_por_uuid` (V1) — FE row by uuid.
- :func:`crear_factura_electronica_inicial` (Step 7 INSERT [L-E]).
- :func:`crear_envio_dian_inicial` (Step 8 INSERT [L-W] initial).
- :func:`crear_envio_dian_reintento` (Step 5 INSERT [L-W] retry with uuid_envio_padre).
- :func:`buscar_envio_dian_chain_tip` (V2 chain-tip via ``timestamp_evento DESC LIMIT 1``).
- :func:`leer_factura_electronica_con_envio_via_view` (GET JOIN to view).
- :func:`validar_uuid_factura_y_sucursal` (V1 + tenant scope data).

8 typed exceptions:

- :class:`FacturaNoEncontradaElectronicaError` (V1 404).
- :class:`FacturaElectronicaNoEncontradaError` (GET + /reintentar V1 404).
- :class:`FacturaElectronicaYaExisteError` (V2 409 + partial UK race).
- :class:`ReintentoNoPermitidoError` (V2 409 on ``aceptado``).
- :class:`EnvioDianAlreadyPendingError` (V2 409 on ``pendiente``).
- :class:`NumeracionDuplicadaError` (UK01 race on (resolucion, consecutivo)).
- :class:`ResolucionNoVigenteError` (V3 409).
- :class:`ConsecutivoRangeExhaustedError` (V4 409, RE-EXPORTED from
  :mod:`parkos_core.repo.resolucion_facturacion` for callers).

DEC-FE-01: envio_dian writes are branch-initiated.
DEC-FE-02: retry chain via NEW row + uuid_envio_padre (NEVER UPDATE).
DEC-FE-05: assign_consecutivo reused as-is, NO modification.
KD-FE-01: handler commits ONCE; this module does NOT commit.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.factura_electronica import FacturaElectronica
from ..models.L_E.facturas import Facturas
from ..models.L_W.envio_dian import EnvioDian

# Re-export for callers (DEC-FE-03 + DEC-FE-05 + REQ-OPS-066).
from .resolucion_facturacion import ConsecutivoRangeExhaustedError  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Typed exceptions (handler 12-step chain discriminators)
# ---------------------------------------------------------------------------


class FacturaNoEncontradaElectronicaError(Exception):
    """V1 404 discriminator — ``prod.facturas.uuid`` not found."""

    def __init__(self, *, uuid_factura: uuid_lib.UUID) -> None:
        self.uuid_factura = uuid_factura
        super().__init__(f"factura_no_encontrada: uuid_factura={uuid_factura}")


class FacturaElectronicaNoEncontradaError(Exception):
    """GET + /reintentar V1 404 discriminator — ``prod.factura_electronica.uuid`` not found."""

    def __init__(self, *, uuid_factura_electronica: uuid_lib.UUID) -> None:
        self.uuid_factura_electronica = uuid_factura_electronica
        super().__init__(
            f"factura_electronica_no_encontrada: uuid_factura_electronica={uuid_factura_electronica}"
        )


class FacturaElectronicaYaExisteError(Exception):
    """V2 409 discriminator — existing FE row for uuid_factura OR partial UK race."""

    def __init__(self, *, uuid_factura: uuid_lib.UUID) -> None:
        self.uuid_factura = uuid_factura
        super().__init__(f"factura_electronica_ya_existe: uuid_factura={uuid_factura}")


class ReintentoNoPermitidoError(Exception):
    """V2 409 discriminator — chain tip state is ``aceptado`` (DEC-FE-04)."""

    def __init__(
        self, *, uuid_factura_electronica: uuid_lib.UUID, estado_actual: str | None
    ) -> None:
        self.uuid_factura_electronica = uuid_factura_electronica
        self.estado_actual = estado_actual
        super().__init__(
            f"reintento_no_permitido: uuid_factura_electronica={uuid_factura_electronica}, "
            f"estado_actual={estado_actual}"
        )


class EnvioDianAlreadyPendingError(Exception):
    """V2 409 discriminator — chain tip state is ``pendiente`` (rapid-retry guard)."""

    def __init__(
        self, *, uuid_factura_electronica: uuid_lib.UUID, uuid_envio_pendiente: uuid_lib.UUID
    ) -> None:
        self.uuid_factura_electronica = uuid_factura_electronica
        self.uuid_envio_pendiente = uuid_envio_pendiente
        super().__init__(
            f"envio_dian_already_pending: uuid_factura_electronica={uuid_factura_electronica}, "
            f"uuid_envio_pendiente={uuid_envio_pendiente}"
        )


class NumeracionDuplicadaError(Exception):
    """UK01 race — pgcode 23505 on ``factura_electronica_uk01 (uuid_resolucion_facturacion, consecutivo)``."""

    def __init__(self, *, uuid_resolucion_facturacion: uuid_lib.UUID, consecutivo: int) -> None:
        self.uuid_resolucion_facturacion = uuid_resolucion_facturacion
        self.consecutivo = consecutivo
        super().__init__(
            f"numeracion_duplicada: uuid_resolucion_facturacion={uuid_resolucion_facturacion}, "
            f"consecutivo={consecutivo}"
        )


class ResolucionNoVigenteError(Exception):
    """V3 409 discriminator — no vigente resolution for uuid_sucursal."""

    def __init__(self, *, uuid_sucursal: uuid_lib.UUID) -> None:
        self.uuid_sucursal = uuid_sucursal
        super().__init__(f"resolucion_no_vigente: uuid_sucursal={uuid_sucursal}")


# ---------------------------------------------------------------------------
# V1: prod.facturas.uuid exists
# ---------------------------------------------------------------------------


async def buscar_factura_por_uuid(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> Facturas | None:
    """V1: SELECT ``prod.facturas`` row by PK."""
    return await session.get(Facturas, uuid_factura)


# ---------------------------------------------------------------------------
# V2 (create handler): existing FE row for uuid_factura
# ---------------------------------------------------------------------------


async def buscar_factura_electronica_por_factura(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> FacturaElectronica | None:
    """V2: SELECT current ``prod.factura_electronica`` row for ``uuid_factura``.

    The partial UK ``one_fe_per_factura`` (MIGRATION 0028 Op 2) guarantees
    at most one row per uuid_factura (NOT NULL).
    """
    stmt = select(FacturaElectronica).where(
        FacturaElectronica.uuid_factura == uuid_factura
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# V1 (GET + /reintentar): FE row exists by uuid
# ---------------------------------------------------------------------------


async def buscar_factura_electronica_por_uuid(
    session: AsyncSession, *, uuid: uuid_lib.UUID
) -> FacturaElectronica | None:
    """V1 (GET + /reintentar): SELECT current ``prod.factura_electronica`` row by uuid."""
    return await session.get(FacturaElectronica, uuid)


# ---------------------------------------------------------------------------
# Step 7 INSERT prod.factura_electronica [L-E]
# ---------------------------------------------------------------------------


async def crear_factura_electronica_inicial(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    prefijo: str | None,
    consecutivo: int,
) -> FacturaElectronica:
    """Step 7 INSERT: single ``prod.factura_electronica`` row.

    The ``prefijo`` is snapshotted from the vigente
    ``prod.resolucion_facturacion`` row returned by V3 (REQ-OPS-074).
    The ``consecutivo`` is from ``assign_consecutivo``. ``descuento=Decimal(0)``
    (MVP). Sets ``fecha_retencion_hasta = date.today() + timedelta(days=5*365)``
    (DIAN 5-year retention).

    Catches ``IntegrityError`` on partial UK ``one_fe_per_factura`` (pgcode 23505)
    and raises :class:`FacturaElectronicaYaExisteError`.

    NOTE (zero-bug-policy, 2026-09-23): ``prefijo`` is nullable to match
    the ORM (``Mapped[str | None]``, see
    ``models/V/resolucion_facturacion.py:39``). The previous typing was
    a typing-time lie: callers passed ``resolucion.prefijo`` (which IS
    nullable at the DB level), causing the LSP error at the call site
    ``api/v1/facturacion.py:707``.
    """
    fecha_retencion_hasta = date.today()  # see factura_detalle.py NOTE part 2
    fe_row = FacturaElectronica(
        uuid=uuid_lib.uuid4(),
        fecha_retencion_hasta=fecha_retencion_hasta,
        uuid_sucursal=uuid_sucursal,
        uuid_factura=uuid_factura,
        uuid_resolucion_facturacion=uuid_resolucion_facturacion,
        prefijo=prefijo,
        consecutivo=consecutivo,
        descuento=Decimal(0),
        created_by=actor_uuid,
    )
    session.add(fe_row)
    try:
        await session.flush()
    except IntegrityError as exc:
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        if pgcode == "23505":
            await session.rollback()
            raise FacturaElectronicaYaExisteError(uuid_factura=uuid_factura) from exc
        raise
    return fe_row


# ---------------------------------------------------------------------------
# Step 8 INSERT initial prod.envio_dian [L-W]
# ---------------------------------------------------------------------------


async def crear_envio_dian_inicial(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura_electronica: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    payload: dict[str, Any],
) -> EnvioDian:
    """Step 8 INSERT: initial ``prod.envio_dian`` row.

    Sets ``estado='pendiente'``, ``uuid_envio_padre=NULL``, ``cufe=NULL``,
    ``respuesta_proveedor=NULL``, ``timestamp_evento=now()``.

    The ``payload`` JSONB includes ``prefijo`` + ``consecutivo`` +
    ``uuid_factura`` (denormalized snapshot for cloud dispatcher).
    """
    fecha_retencion_hasta = date.today() + timedelta(days=5 * 365)
    envio_row = EnvioDian(
        uuid=uuid_lib.uuid4(),
        fecha_retencion_hasta=fecha_retencion_hasta,
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=uuid_factura_electronica,
        uuid_resolucion_facturacion=uuid_resolucion_facturacion,
        payload=payload,
        respuesta_proveedor=None,
        cufe=None,
        uuid_envio_padre=None,
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
        estado="pendiente",
        vigente_desde=datetime.now(UTC).replace(tzinfo=None),
        vigente_hasta=None,
        created_by=actor_uuid,
    )
    session.add(envio_row)
    await session.flush()
    return envio_row


# ---------------------------------------------------------------------------
# V2 chain tip lookup (chain tip via ORDER BY timestamp_evento DESC LIMIT 1)
# ---------------------------------------------------------------------------


async def buscar_envio_dian_chain_tip(
    session: AsyncSession, *, uuid_factura_electronica: uuid_lib.UUID
) -> EnvioDian | None:
    """V2 chain-tip lookup (Step 4 of /reintentar).

    Returns the LATEST ``prod.envio_dian`` row for the FE by
    ``timestamp_evento DESC LIMIT 1``. Mirrors the
    ``v_factura_electronica_acuse`` view's ``DISTINCT ON`` semantic.
    """
    stmt = (
        select(EnvioDian)
        .where(EnvioDian.uuid_factura_electronica == uuid_factura_electronica)
        .order_by(EnvioDian.timestamp_evento.desc(), EnvioDian.uuid.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Step 5 INSERT retry prod.envio_dian [L-W]
# ---------------------------------------------------------------------------


async def crear_envio_dian_reintento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_factura_electronica: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    payload: dict[str, Any],
    uuid_envio_padre: uuid_lib.UUID,
) -> EnvioDian:
    """Step 5 INSERT (DEC-FE-02 + DEC-FE-07): NEW ``prod.envio_dian`` retry row.

    Sets ``uuid_envio_padre=<tip.uuid>``, ``estado='pendiente'``, ``cufe=NULL``.

    The chain IS the audit trail. NEVER UPDATE on existing envio rows.

    NOTE (zero-bug-policy, 2026-09-23): ``uuid_sucursal`` is nullable
    to match the underlying :class:`EnvioDian` ORM column
    (``Mapped[uuid_lib.UUID | None]``, see
    ``models/L_W/envio_dian.py:31``). The previous typing was a lie —
    callers passed ``fe_row.uuid_sucursal`` (nullable at the DB
    level), causing the LSP error at the call site
    ``api/v1/facturacion.py:1007``.
    """
    fecha_retencion_hasta = date.today()  # see factura_detalle.py NOTE part 2
    envio_row = EnvioDian(
        uuid=uuid_lib.uuid4(),
        fecha_retencion_hasta=fecha_retencion_hasta,
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=uuid_factura_electronica,
        uuid_resolucion_facturacion=uuid_resolucion_facturacion,
        payload=payload,
        respuesta_proveedor=None,
        cufe=None,
        uuid_envio_padre=uuid_envio_padre,
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
        estado="pendiente",
        vigente_desde=datetime.now(UTC).replace(tzinfo=None),
        vigente_hasta=None,
        created_by=actor_uuid,
    )
    session.add(envio_row)
    await session.flush()
    return envio_row


# ---------------------------------------------------------------------------
# GET JOIN to v_factura_electronica_acuse
# ---------------------------------------------------------------------------


async def leer_factura_electronica_con_envio_via_view(
    session: AsyncSession, *, uuid: uuid_lib.UUID
) -> tuple[FacturaElectronica | None, dict[str, Any] | None]:
    """Step 3 of GET (REQ-OPS-068): JOIN ``prod.v_factura_electronica_acuse``.

    Returns ``(fe_row, ack_row_or_None)`` where ``ack_row_or_None`` is the
    view row as a dict (``uuid``, ``estado``, ``cufe``, ``timestamp_evento``,
    ``motivo_rechazo``) or ``None`` if the FE has zero envio rows
    (defensive null mapping per REQ-OPS-068 Scenario 2). Returns
    ``(None, None)`` if the FE itself does not exist.
    """
    fe_row = await session.get(FacturaElectronica, uuid)
    if fe_row is None:
        return None, None
    ack_row = (
        await session.execute(
            text(
                "SELECT uuid, estado, cufe, timestamp_evento, motivo_rechazo "
                "FROM prod.v_factura_electronica_acuse "
                "WHERE uuid_factura_electronica = :uuid"
            ),
            {"uuid": str(uuid)},
        )
    ).first()
    if ack_row is None:
        return fe_row, None
    return fe_row, {
        "uuid": ack_row.uuid,
        "estado": ack_row.estado,
        "cufe": ack_row.cufe,
        "timestamp_evento": ack_row.timestamp_evento,
        "motivo_rechazo": ack_row.motivo_rechazo,
    }


# ---------------------------------------------------------------------------
# V1 + tenant scope helper (combined for DRY)
# ---------------------------------------------------------------------------


async def validar_uuid_factura_y_sucursal(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> tuple[Facturas, uuid_lib.UUID]:
    """V1 + tenant scope data extraction.

    Returns ``(factura_row, target_sucursal_uuid)`` if found, else raises
    :class:`FacturaNoEncontradaElectronicaError` (handler maps to 404).
    """
    factura = await session.get(Facturas, uuid_factura)
    if factura is None:
        raise FacturaNoEncontradaElectronicaError(uuid_factura=uuid_factura)
    return factura, factura.uuid_sucursal  # type: ignore[return-value]


__all__ = [
    # Typed exceptions
    "ConsecutivoRangeExhaustedError",
    "EnvioDianAlreadyPendingError",
    "FacturaElectronicaNoEncontradaError",
    "FacturaElectronicaYaExisteError",
    "FacturaNoEncontradaElectronicaError",
    "NumeracionDuplicadaError",
    "ReintentoNoPermitidoError",
    "ResolucionNoVigenteError",
    # Helpers
    "buscar_envio_dian_chain_tip",
    "buscar_factura_electronica_por_factura",
    "buscar_factura_electronica_por_uuid",
    "buscar_factura_por_uuid",
    "crear_envio_dian_inicial",
    "crear_envio_dian_reintento",
    "crear_factura_electronica_inicial",
    "leer_factura_electronica_con_envio_via_view",
    "validar_uuid_factura_y_sucursal",
]
