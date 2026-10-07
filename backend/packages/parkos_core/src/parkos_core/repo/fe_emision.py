"""Always-on electronic-invoice (FE) emission after a payment.

Business rule: EVERY charge flow (salida, servicio/ingreso, subscription sale
and renewal) ends with an electronic invoice. If the payer gave no customer
data the document is issued to the standard customer
(:data:`parkos_core.constants.CLIENTE_ESTANDAR_UUID`). The document is final at
emission; only the DIAN acknowledgement stays pending (``envio_dian``).

Public surface (reusable by any charge flow, e.g. renewals):

* :func:`emitir_fe_para_pago` -- best-effort emission AFTER the payment commit.
  Never raises for business errors and never undoes the payment.
* :class:`FeRetryScheduler` + :func:`reintentar_pendientes` -- bounded
  automatic retry driven by the branch sync worker.

Failure model
-------------
If the emission fails (no resolution, range exhausted, no prefix, ...):

1. The payment/factura stay committed (this helper runs after that commit).
2. The invoice is left "pending": it has NO ``factura_electronica`` row yet,
   and an informational ``fe_emision_pendiente`` alerta (already ``resuelta``,
   so it does not clutter the admin queue) records what a retry needs
   (``uuid_factura``, ``uuid_cliente``, extra payload). Pending invoices are
   exactly the markers whose factura has no FE row.
3. The worker retries with backoff (:data:`BACKOFF_S`, at most
   :data:`MAX_REINTENTOS` retries, and never beyond :data:`MAX_EDAD`).
4. If it is still failing after that, ONE ``fe_emision_fallida`` (warning)
   alerta is raised for the administrator.

Deployment awareness (cloud vs branch)
--------------------------------------
Invoice numbering is BRANCH-LOCAL (AGENTS.md): ``consecutivo`` is assigned by
the branch inside its own ``resolucion_facturacion`` range, and the FE is
emitted there. A charge that originates in the CLOUD (``PARKOS_DEPLOY=cloud``:
admin renewal, any sale from web_admin) therefore must NOT number nor emit:
if both nodes numbered from the same resolution they would mint the same
``(uuid_resolucion_facturacion, consecutivo)`` and the branch->cloud push would
fail forever on ``factura_electronica_uk01``. In the cloud this function only
leaves the SAME ``fe_emision_pendiente`` marker the branch retry uses, tagged
``origen='nube'`` (the factura/pago are already committed by the caller); it
returns ``pendiente=True`` with no error and never calls ``assign_consecutivo``.
In a branch deployment nothing changes.

The branch is meant to pick the marker up through :func:`reintentar_pendientes`
and number with its own resolution. NOTE: ``facturas`` / ``alerta`` are
``branch_to_cloud`` in the sync catalog, so a cloud-created marker does not
reach the branch yet; the replication that closes that last hop needs a
pull-RLS migration and is reported separately ([POR DEFINIR]).

Idempotency: a consecutivo is only consumed when the FE row is inserted in the
same transaction as the numbering (``assign_consecutivo`` reads
``MAX(consecutivo)``; it never reserves). A failed attempt therefore burns
nothing, a retry of an invoice that already has an FE returns it untouched,
and the DB keeps ``one_fe_per_factura`` + UK ``(resolucion, consecutivo)``.

Privacy: no customer data is logged or written to alerts -- only UUIDs and
error codes.
"""
from __future__ import annotations

import os
import time
import uuid as uuid_lib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import CLIENTE_ESTANDAR_UUID
from ..models.L_E.facturas import Facturas
from ..models.L_W.alerta import Alerta
from . import factura_electronica as repo_fe
from . import resolucion_facturacion as repo_resolucion

log = structlog.get_logger("parkos.repo.fe_emision")

ALERTA_PENDIENTE = "fe_emision_pendiente"
ALERTA_FALLIDA = "fe_emision_fallida"

# Seconds to wait after the Nth failed retry before the next one.
BACKOFF_S: tuple[int, ...] = (60, 300, 900, 1800, 3600)
MAX_REINTENTOS = len(BACKOFF_S)
# Hard cap on how long a pending invoice is retried (covers worker restarts,
# which reset the in-memory attempt counters).
MAX_EDAD = timedelta(hours=24)
# Minimum seconds between two scans of the pending markers.
SCAN_INTERVAL_S = 30

# Stable error codes (superset of the ones the sale endpoint already exposed).
ERR_SIN_SUCURSAL = "missing_sucursal_context"
ERR_SIN_RESOLUCION = "resolucion_facturacion_no_encontrada"
ERR_NUMERACION_AGOTADA = "numeracion_agotada"
ERR_SIN_PREFIJO = "resolucion_sin_prefijo"
ERR_FACTURA_NO_ENCONTRADA = "factura_no_encontrada"
ERR_INESPERADO = "fe_error_inesperado"
# Marker reason for a charge originated in the cloud: numbering/emission is
# delegated to the branch (not a failure).
MOTIVO_EMISION_EN_SUCURSAL = "emision_en_sucursal"
ORIGEN_NUBE = "nube"


def es_despliegue_nube() -> bool:
    """True when this process is the cloud deployment (``PARKOS_DEPLOY=cloud``).

    Read at call time (like ``api/app_factory.py``). Unset or ``branch`` keep
    the branch behaviour, so tests and the branch API are unaffected.
    """
    return os.environ.get("PARKOS_DEPLOY", "").strip().lower() == "cloud"


@dataclass(frozen=True)
class FeEmisionResultado:
    """Outcome of one emission attempt.

    Exactly one of ``uuid_factura_electronica`` / ``error`` is set.
    ``pendiente`` is True when the failure left the invoice queued for the
    automatic retry.
    """

    uuid_factura_electronica: uuid_lib.UUID | None = None
    uuid_envio_dian: uuid_lib.UUID | None = None
    error: str | None = None
    pendiente: bool = False

    @property
    def emitida(self) -> bool:
        return self.uuid_factura_electronica is not None


async def _buscar_factura(
    session: AsyncSession, uuid_factura: uuid_lib.UUID
) -> Facturas | None:
    """Load a factura by uuid. ``prod.facturas`` is partitioned (composite PK
    ``(uuid, fecha_retencion_hasta)``), so ``session.get`` cannot be used."""
    stmt = select(Facturas).where(Facturas.uuid == uuid_factura).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _rollback_seguro(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001 - best effort, the marker insert reports its own failure
        log.warning("fe_emision.rollback_fallo")


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def emitir_fe_para_pago(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID | None,
    uuid_factura: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID | None = None,
    uuid_cliente: uuid_lib.UUID | None = None,
    payload_extra: dict[str, str] | None = None,
    registrar_pendiente: bool = True,
) -> FeEmisionResultado:
    """Emit the FE for an already-committed payment (best-effort, own commit).

    Args:
        session: session of the charge flow; the payment MUST already be
            committed. This function commits on every path (success: FE +
            envio atomically; failure: releases the numbering lock and
            persists the pending marker) and never raises for business
            errors.
        actor_uuid: ``created_by`` of the FE/envio rows.
        uuid_factura: the paid ``prod.facturas`` row.
        uuid_sucursal: defaults to the factura's own branch.
        uuid_cliente: customer the payer asked to invoice. ``None`` means the
            standard customer.
        payload_extra: extra UUID-only context copied into the envio payload.
        registrar_pendiente: write the retry marker on failure (the retry
            job passes False: the marker already exists).
    """
    extra = dict(payload_extra or {})
    cliente = uuid_cliente or CLIENTE_ESTANDAR_UUID
    en_savepoint = False
    try:
        existente = await repo_fe.buscar_factura_electronica_por_factura(
            session, uuid_factura=uuid_factura
        )
        if existente is not None:  # idempotent: already emitted
            return FeEmisionResultado(uuid_factura_electronica=existente.uuid)

        factura = await _buscar_factura(session, uuid_factura)
        if factura is None:
            await session.commit()
            return FeEmisionResultado(error=ERR_FACTURA_NO_ENCONTRADA)
        sucursal = uuid_sucursal or factura.uuid_sucursal
        if es_despliegue_nube():
            # Cloud-originated charge: the branch numbers and emits. Only
            # leave the marker (never assign_consecutivo here).
            await session.commit()  # close the read transaction first
            pendiente = True
            if registrar_pendiente:
                pendiente = await _registrar_pendiente(
                    session,
                    actor_uuid=actor_uuid,
                    uuid_sucursal=sucursal,
                    uuid_factura=uuid_factura,
                    uuid_cliente=cliente,
                    payload_extra=extra,
                    motivo=MOTIVO_EMISION_EN_SUCURSAL,
                    origen=ORIGEN_NUBE,
                )
            return FeEmisionResultado(pendiente=pendiente)
        descuento = Decimal(str(factura.descuento or 0))

        # SAVEPOINT: an unexpected DB fault rolls back only the FE inserts and
        # leaves the caller's already-loaded ORM objects (factura, detalles)
        # usable for the response, instead of expiring the whole session.
        en_savepoint = True
        async with session.begin_nested():
            error, fe_uuid, envio_uuid = await _emitir(
                session,
                actor_uuid=actor_uuid,
                uuid_sucursal=sucursal,
                uuid_factura=uuid_factura,
                uuid_cliente=cliente,
                descuento=descuento,
                payload_extra=extra,
            )
        en_savepoint = False
        if error is None:
            await session.commit()
            return FeEmisionResultado(
                uuid_factura_electronica=fe_uuid, uuid_envio_dian=envio_uuid
            )
        # Business failure: nothing was written; commit releases the
        # SELECT ... FOR UPDATE lock taken by assign_consecutivo.
        await session.commit()
    except repo_fe.FacturaElectronicaYaExisteError:
        # Concurrent emission won the partial UK (the repo already rolled the
        # session back); reuse the winner's row.
        existente = await repo_fe.buscar_factura_electronica_por_factura(
            session, uuid_factura=uuid_factura
        )
        if existente is not None:
            return FeEmisionResultado(uuid_factura_electronica=existente.uuid)
        error, sucursal = ERR_INESPERADO, uuid_sucursal
    except Exception as exc:  # noqa: BLE001 - the payment must survive any FE fault
        if not en_savepoint:
            # Fault in a plain query/commit (outside the savepoint): the
            # transaction may be aborted, so clear it or the pending marker
            # could not be written either. The savepoint case needs no
            # rollback (it already discarded the partial FE writes).
            await _rollback_seguro(session)
        log.warning(
            "fe_emision.error_inesperado",
            error_type=type(exc).__name__,
            uuid_factura=str(uuid_factura),
        )
        error, sucursal = ERR_INESPERADO, uuid_sucursal

    pendiente = False
    if registrar_pendiente:
        pendiente = await _registrar_pendiente(
            session,
            actor_uuid=actor_uuid,
            uuid_sucursal=sucursal,
            uuid_factura=uuid_factura,
            uuid_cliente=cliente,
            payload_extra=extra,
            motivo=error,
        )
    return FeEmisionResultado(error=error, pendiente=pendiente)


async def _emitir(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID | None,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_factura: uuid_lib.UUID,
    uuid_cliente: uuid_lib.UUID,
    descuento: Decimal,
    payload_extra: dict[str, str],
) -> tuple[str | None, uuid_lib.UUID | None, uuid_lib.UUID | None]:
    """Numbering + FE + envio inserts (flushed, NOT committed)."""
    if uuid_sucursal is None:
        return ERR_SIN_SUCURSAL, None, None
    resolucion = await repo_resolucion.buscar_resolucion_vigente_por_sucursal(
        session, uuid_sucursal=uuid_sucursal
    )
    if resolucion is None:
        return ERR_SIN_RESOLUCION, None, None
    if not resolucion.prefijo:
        return ERR_SIN_PREFIJO, None, None
    try:
        consecutivo = await repo_resolucion.assign_consecutivo(
            session,
            resolucion_uuid=resolucion.uuid,
            source_event_uuid=uuid_factura,
        )
    except repo_resolucion.ConsecutivoRangeExhaustedError:
        return ERR_NUMERACION_AGOTADA, None, None

    fe_row = await repo_fe.crear_factura_electronica_inicial(
        session,
        actor_uuid=actor_uuid,  # type: ignore[arg-type]
        uuid_sucursal=uuid_sucursal,
        uuid_factura=uuid_factura,
        uuid_resolucion_facturacion=resolucion.uuid,
        prefijo=resolucion.prefijo,
        consecutivo=consecutivo,
        descuento=descuento,
        uuid_cliente=uuid_cliente,
    )
    envio = await repo_fe.crear_envio_dian_inicial(
        session,
        actor_uuid=actor_uuid,  # type: ignore[arg-type]
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=fe_row.uuid,
        uuid_resolucion_facturacion=resolucion.uuid,
        payload={
            "prefijo": resolucion.prefijo,
            "consecutivo": consecutivo,
            "uuid_factura": str(uuid_factura),
            **payload_extra,
        },
    )
    return None, fe_row.uuid, envio.uuid


# ---------------------------------------------------------------------------
# Pending marker + alerts
# ---------------------------------------------------------------------------


async def _registrar_pendiente(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID | None,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_factura: uuid_lib.UUID,
    uuid_cliente: uuid_lib.UUID,
    payload_extra: dict[str, str],
    motivo: str,
    origen: str | None = None,
) -> bool:
    """Persist the retry marker (once per factura). Returns True if queued."""
    datos: dict[str, Any] = {
        "motivo": motivo,
        "uuid_factura": str(uuid_factura),
        "uuid_cliente": str(uuid_cliente),
        "actor_uuid": str(actor_uuid) if actor_uuid else None,
        "payload_extra": payload_extra,
    }
    if origen:
        datos["origen"] = origen
    # First try with the operator on the alerta; if that FK cannot be
    # satisfied on this node, fall back to NULL (the actor still travels in
    # ``datos_nuevos`` for the retry).
    for usuario in (actor_uuid, None):
        try:
            # SAVEPOINT: a FK failure discards only the marker insert and
            # leaves the caller's ORM objects usable (no full rollback).
            async with session.begin_nested():
                ya = (
                    await session.execute(
                        text(
                            "SELECT 1 FROM prod.alerta WHERE tipo_alerta = :t "
                            "AND datos_nuevos->>'uuid_factura' = :f LIMIT 1"
                        ),
                        {"t": ALERTA_PENDIENTE, "f": str(uuid_factura)},
                    )
                ).first()
                if ya is None:
                    session.add(
                        Alerta(
                            uuid_sucursal=uuid_sucursal,
                            uuid_usuario=usuario,
                            tipo_alerta=ALERTA_PENDIENTE,
                            estado="resuelta",  # informational, no admin action
                            timestamp_evento=_now_naive(),
                            uuid_arqueo=None,
                            datos_nuevos=datos,
                        )
                    )
                    await session.flush()
            await session.commit()
            return True
        except Exception as exc:  # noqa: BLE001 - never mask the payment outcome
            log.error(
                "fe_emision.marcador_pendiente_fallo",
                error_type=type(exc).__name__,
                uuid_factura=str(uuid_factura),
            )
            if usuario is None:
                break
    return False


async def _alertar_fallida(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    uuid_factura: str,
    motivo: str,
    intentos: int,
) -> None:
    """Raise the administrator alert (once per factura: dedupe by factura)."""
    ya = (
        await session.execute(
            text(
                "SELECT 1 FROM prod.alerta WHERE tipo_alerta = :t "
                "AND datos_nuevos->>'uuid_factura' = :f LIMIT 1"
            ),
            {"t": ALERTA_FALLIDA, "f": uuid_factura},
        )
    ).first()
    if ya is None:
        session.add(
            Alerta(
                uuid_sucursal=uuid_sucursal,
                uuid_usuario=None,  # system alert: must never fail on a user FK
                tipo_alerta=ALERTA_FALLIDA,
                estado="abierta",
                timestamp_evento=_now_naive(),
                uuid_arqueo=None,
                datos_nuevos={
                    "motivo": motivo,
                    "uuid_factura": uuid_factura,
                    "intentos": intentos,
                },
            )
        )
        await session.flush()
    await session.commit()


# ---------------------------------------------------------------------------
# Automatic retry (driven by the branch sync worker)
# ---------------------------------------------------------------------------


@dataclass
class FeRetryScheduler:
    """In-memory backoff state for pending invoices (one per worker)."""

    clock: Any = time.monotonic
    _estado: dict[str, tuple[int, float]] = field(default_factory=dict)
    _proximo_scan: float = 0.0

    def scan_due(self) -> bool:
        ahora = self.clock()
        if ahora < self._proximo_scan:
            return False
        self._proximo_scan = ahora + SCAN_INTERVAL_S
        return True

    def due(self, uuid_factura: str) -> bool:
        _, siguiente = self._estado.get(uuid_factura, (0, 0.0))
        return self.clock() >= siguiente

    def intentos(self, uuid_factura: str) -> int:
        return self._estado.get(uuid_factura, (0, 0.0))[0]

    def fallo(self, uuid_factura: str) -> int:
        """Record a failed retry; returns the number of retries so far."""
        n = self.intentos(uuid_factura) + 1
        delay = BACKOFF_S[min(n - 1, len(BACKOFF_S) - 1)]
        self._estado[uuid_factura] = (n, self.clock() + delay)
        return n

    def olvidar(self, uuid_factura: str) -> None:
        self._estado.pop(uuid_factura, None)


async def reintentar_pendientes(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    scheduler: FeRetryScheduler,
    limit: int = 20,
    now: datetime | None = None,
) -> dict[str, int]:
    """Retry pending invoices of this branch; alert the admin when exhausted.

    Returns counters ``{"emitidas", "fallidas", "alertas"}`` (for logs/tests).
    """
    contadores = {"emitidas": 0, "fallidas": 0, "alertas": 0}
    if not scheduler.scan_due():
        return contadores
    ahora = now or _now_naive()
    filas = (
        await session.execute(
            text(
                """
                SELECT a.uuid_usuario, a.timestamp_evento, a.datos_nuevos
                FROM prod.alerta a
                WHERE a.tipo_alerta = :pend
                  AND a.uuid_sucursal = :suc
                  AND a.timestamp_evento > :desde
                  AND NOT EXISTS (
                      SELECT 1 FROM prod.factura_electronica fe
                      WHERE fe.uuid_factura =
                            CAST(a.datos_nuevos->>'uuid_factura' AS uuid))
                  AND NOT EXISTS (
                      SELECT 1 FROM prod.alerta f
                      WHERE f.tipo_alerta = :fall
                        AND f.datos_nuevos->>'uuid_factura'
                            = a.datos_nuevos->>'uuid_factura')
                ORDER BY a.timestamp_evento
                LIMIT :lim
                """
            ),
            {
                "pend": ALERTA_PENDIENTE,
                "fall": ALERTA_FALLIDA,
                "suc": str(uuid_sucursal),
                "desde": ahora - timedelta(days=7),
                "lim": limit,
            },
        )
    ).all()
    # The SELECT opened a transaction; release it before the per-invoice work.
    await session.commit()

    vistas: set[str] = set()
    for actor_alerta, ts, datos in filas:
        datos = datos or {}
        if datos.get("uuid_factura") in vistas:
            continue  # duplicate marker (concurrent failures): handle once
        vistas.add(str(datos.get("uuid_factura")))
        actor = (
            uuid_lib.UUID(datos["actor_uuid"]) if datos.get("actor_uuid") else actor_alerta
        )
        factura_txt = datos.get("uuid_factura")
        if not factura_txt:
            continue
        expirada = ts is not None and (ahora - ts) > MAX_EDAD
        motivo = str(datos.get("motivo") or ERR_INESPERADO)
        if not expirada:
            if not scheduler.due(factura_txt):
                continue
            extra = {
                str(k): str(v) for k, v in (datos.get("payload_extra") or {}).items()
            }
            resultado = await emitir_fe_para_pago(
                session,
                actor_uuid=actor,
                uuid_factura=uuid_lib.UUID(factura_txt),
                uuid_sucursal=uuid_sucursal,
                uuid_cliente=uuid_lib.UUID(datos["uuid_cliente"])
                if datos.get("uuid_cliente")
                else None,
                payload_extra=extra,
                registrar_pendiente=False,
            )
            if resultado.emitida:
                scheduler.olvidar(factura_txt)
                contadores["emitidas"] += 1
                continue
            contadores["fallidas"] += 1
            motivo = resultado.error or motivo
            if scheduler.fallo(factura_txt) < MAX_REINTENTOS:
                continue
        await _alertar_fallida(
            session,
            uuid_sucursal=uuid_sucursal,
            uuid_factura=factura_txt,
            motivo=motivo,
            intentos=scheduler.intentos(factura_txt),
        )
        scheduler.olvidar(factura_txt)
        contadores["alertas"] += 1
    return contadores


__all__ = [
    "ALERTA_FALLIDA",
    "ALERTA_PENDIENTE",
    "BACKOFF_S",
    "MAX_EDAD",
    "MAX_REINTENTOS",
    "FeEmisionResultado",
    "FeRetryScheduler",
    "emitir_fe_para_pago",
    "reintentar_pendientes",
]
