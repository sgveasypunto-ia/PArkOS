"""parkos_core.repo.reimpresion_ticket -- reimpresion de tiquete helpers.

REQ-OPS-075..080 + REQ-OPS-XR4 traceability (see
``openspec/changes/hu-f1-11-reimpresion-tiquete/specs/operations/spec.md``):

* REQ-OPS-075 V1+V2+V5  -- ``buscar_ingreso_por_uuid`` +
  ``buscar_reimpresion_activa_por_ingreso`` (KD-TKT-02 chain-tip
  ``SELECT ... FOR UPDATE``) + ``buscar_reimpresion_por_uuid``.
* REQ-OPS-077 V1        -- ``buscar_reimpresion_por_uuid`` reused for
  anulacion lookup.
* REQ-OPS-079           -- ``buscar_costo_servicio_vigente_por_concepto``
  defensive lookup (DEC-TKT-05 siembra comes from MIGRATION 0029 Op 1).
* REQ-OPS-080 V3        -- ``buscar_factura_por_uuid`` (DEC-TKT-04
  ``uuid_factura`` optional on create).
* REQ-OPS-XR4           -- ``check_idempotency_key`` thin wrapper around
  ``prod.idempotency_keys`` (DEC-IDEM-01 F1.6 reuse).

Defense in depth (KD-TKT-01): this module NEVER calls
``session.commit()``. The single commit is owned by the API handler
(``api/v1/workflows_reimpresion.py``) per the F1.10 single-commit
invariant.

DEC-TKT-02 INSERT-only invariant: every state change funnels through
``repo.workflow.append_transition`` (F1.5 PR5-016). The AST walks in
``tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py``
re-enforce that NO ``UPDATE`` or ``DELETE`` on
``prod.reimpresion_ticket`` is ever emitted by an F1.11 handler.
"""
from __future__ import annotations

import uuid as uuid_lib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.facturas import Facturas
from ..models.L_E.ingreso import Ingreso
from ..models.L_W.reimpresion_ticket import ReimpresionTicket
from ..models.V.costos_servicios import CostosServicios

__all__ = [
    # Typed exceptions (5)
    "AnulacionNoPermitidaError",
    "CostoServicioNoConfiguradoError",
    "IngresoNoEncontradoError",
    "ReimpresionAlreadyPendingError",
    "ReimpresionNotFoundError",
    # V1 helpers + V2 chain-tip guard + siembra + idempotency wrappers
    "buscar_costo_servicio_vigente_por_concepto",
    "buscar_factura_por_uuid",
    "buscar_ingreso_por_uuid",
    "buscar_reimpresion_activa_por_ingreso",
    "buscar_reimpresion_por_uuid",
    "check_idempotency_key",
]


# ---------------------------------------------------------------------------
# Typed exceptions (5)
# ---------------------------------------------------------------------------


class IngresoNoEncontradoError(Exception):
    """V1 404 discriminator — ``prod.ingreso`` row not found by PK."""

    def __init__(self, *, uuid_ingreso: uuid_lib.UUID) -> None:
        self.uuid_ingreso = uuid_ingreso
        super().__init__(f"ingreso_no_encontrado: uuid_ingreso={uuid_ingreso}")


class ReimpresionNotFoundError(Exception):
    """V1 404 discriminator — ``prod.reimpresion_ticket`` row not in chain."""

    def __init__(self, *, uuid_reimpresion: uuid_lib.UUID) -> None:
        self.uuid_reimpresion = uuid_reimpresion
        super().__init__(
            f"reimpresion_not_found: uuid_reimpresion={uuid_reimpresion}"
        )


class ReimpresionAlreadyPendingError(Exception):
    """V2 409 discriminator — recent active reimpresion for uuid_ingreso."""

    def __init__(
        self,
        *,
        uuid_ingreso: uuid_lib.UUID,
        uuid_reimpresion: uuid_lib.UUID,
    ) -> None:
        self.uuid_ingreso = uuid_ingreso
        self.uuid_reimpresion = uuid_reimpresion
        super().__init__(
            f"reimpresion_already_pending: uuid_ingreso={uuid_ingreso}, "
            f"uuid_reimpresion={uuid_reimpresion}"
        )


class AnulacionNoPermitidaError(Exception):
    """V2 409 discriminator — chain-tip already terminal ``rechazada``."""

    def __init__(self, *, uuid_reimpresion: uuid_lib.UUID) -> None:
        self.uuid_reimpresion = uuid_reimpresion
        super().__init__(
            f"anulacion_no_permitida: uuid_reimpresion={uuid_reimpresion}"
        )


class CostoServicioNoConfiguradoError(Exception):
    """DEC-TKT-05 runtime defensive check (HTTP 409 create)."""

    def __init__(self, *, concepto: str) -> None:
        self.concepto = concepto
        super().__init__(f"costo_servicio_no_configurado: concepto={concepto}")


# ---------------------------------------------------------------------------
# V1 helpers
# ---------------------------------------------------------------------------


async def buscar_ingreso_por_uuid(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> Ingreso | None:
    """V1: SELECT ``prod.ingreso`` row by PK.

    Returns the ORM row if found, else ``None``. The handler raises the
    404 via HTTPException (DEC-TKT-06 layer-5 mapping).
    """
    return await session.get(Ingreso, uuid_ingreso)


async def buscar_reimpresion_por_uuid(
    session: AsyncSession, *, uuid: uuid_lib.UUID
) -> ReimpresionTicket | None:
    """V1/V2: SELECT ``prod.reimpresion_ticket`` row by PK.

    Returns the ORM row if found, else ``None``. Used by the anulacion
    endpoint after ``read_chain_tip`` resolves the chain tip uuid, and
    directly by the tenant-scope check to fetch ``uuid_sucursal``.
    """
    return await session.get(ReimpresionTicket, uuid)


async def buscar_factura_por_uuid(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> Facturas | None:
    """V3 (DEC-TKT-04, optional): SELECT ``prod.facturas`` row by PK.

    Returns the ORM row if found, else ``None``. The handler raises the
    404 only IF the payload supplied ``uuid_factura``.
    """
    return await session.get(Facturas, uuid_factura)


# ---------------------------------------------------------------------------
# V2 chain-tip guard (DEC-TKT-02 + KD-TKT-02 SELECT ... FOR UPDATE)
# ---------------------------------------------------------------------------


async def buscar_reimpresion_activa_por_ingreso(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> dict[str, Any] | None:
    """V2 chain-tip guard (DEC-TKT-02 + KD-TKT-02 ``SELECT ... FOR UPDATE``).

    Returns ``{uuid, timestamp_evento, workflow_estado}`` of the
    most-recent active ``prod.reimpresion_ticket`` row for the given
    ``uuid_ingreso``, or ``None`` if no recent active row exists.

    The lookup uses ``SELECT ... FOR UPDATE`` on the most-recent active
    row to close the concurrent-create race (KD-TKT-02, mirror of F1.10
    KD-FE-02). The row lock is held until ``await session.commit()`` in
    the handler body. Two concurrent TXs attempting to create
    reimpresions for the same ``uuid_ingreso`` serialize: the FIRST
    acquires the lock and inserts; the SECOND blocks at SELECT FOR
    UPDATE until the FIRST commits, then proceeds with the V2 check
    (which now finds the recent row and returns 409
    ``reimpresion_already_pending``).

    Tie-break mirrors F1.5 PR5-016 REQ-X9:
    ``(max(timestamp_evento DESC), lex(uuid DESC))`` — deterministic.
    ``workflow_estado`` is synthesized as ``"autorizada"`` for MVP; the
    full state machine derivation is F2.x (when manual authorization
    reintroduces ``solicitada`` / ``ejecutada`` per DEC-TKT-02 §5.1.1).
    """
    stmt = (
        select(ReimpresionTicket)
        .where(
            ReimpresionTicket.uuid_ingreso == uuid_ingreso,
            ReimpresionTicket.vigente_hasta.is_(None),
            ReimpresionTicket.estado == "activo",
        )
        .order_by(
            ReimpresionTicket.timestamp_evento.desc(),
            ReimpresionTicket.uuid.desc(),
        )
        .limit(1)
        .with_for_update()
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return {
        "uuid": row.uuid,
        "timestamp_evento": row.timestamp_evento,
        "workflow_estado": "autorizada",
    }


# ---------------------------------------------------------------------------
# DEC-TKT-05 defensive siembra lookup
# ---------------------------------------------------------------------------


async def buscar_costo_servicio_vigente_por_concepto(
    session: AsyncSession, *, concepto: str
) -> CostosServicios | None:
    """DEC-TKT-05: SELECT vigente ``prod.costos_servicios`` row for ``concepto``.

    Returns the ORM row if a vigente (``vigente_hasta IS NULL``,
    ``estado='activo'``) row exists, else ``None``. The handler maps
    ``None`` to 409 ``costo_servicio_no_configurado`` (defensive check
    after MIGRATION 0029 Op 1 siembra; the cost is informational and
    NOT snapshotted on the reimpresion row per DEC-TKT-04).

    The handler calls this helper as the final guard before the
    ``append_transition`` write so a missed siembra surfaces as a typed
    409 rather than a downstream FK or trigger failure.
    """
    stmt = (
        select(CostosServicios)
        .where(
            CostosServicios.concepto == concepto,
            CostosServicios.vigente_hasta.is_(None),
            CostosServicios.estado == "activo",
        )
        .order_by(CostosServicios.vigente_desde.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# DEC-IDEM-01 idempotency-key cache wrapper (F1.6 reuse)
# ---------------------------------------------------------------------------


async def check_idempotency_key(
    session: AsyncSession,
    *,
    idempotency_key: str,
    endpoint: str,
) -> dict[str, Any] | None:
    """DEC-IDEM-01 thin wrapper around ``prod.idempotency_keys`` cache.

    The actual cache lookup + short-circuit is performed by the F1.6
    ``Idempotency-Key`` middleware (``api/middleware.py::idempotency_mw``)
    which keys on ``(key, endpoint, actor_uuid)`` with a 7-day TTL.
    F1.11 inherits that middleware verbatim — this helper exists for:

      * testability — RED tests can drive the cache layer in isolation
        without spinning up the full FastAPI app;
      * explicit documentation — pinpoints the DEC-IDEM-01 reuse contract
        at the reimpresion-repo layer so a future grep finds it.

    Returns ``None`` (cache miss) in this environment because the
    middleware owns the authoritative lookup. A real Postgres-backed
    implementation would query ``prod.idempotency_keys`` with the same
    key contract — out of scope for F1.11.
    """
    return None
