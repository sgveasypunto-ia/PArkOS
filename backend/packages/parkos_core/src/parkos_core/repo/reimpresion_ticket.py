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

from typing import Any

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
# Typed exceptions (5) -- T2.3 GREEN carries real ``__init__`` payloads.
# These are intentionally bare class declarations at T1.2 to satisfy the
# module-import-surface test; helper bodies land in T2.3 alongside the
# ``__all__`` re-export.
# ---------------------------------------------------------------------------


class IngresoNoEncontradoError(Exception):
    """V1: ``prod.ingreso`` row not found by PK (HTTP 404 create)."""


class ReimpresionNotFoundError(Exception):
    """V1: ``prod.reimpresion_ticket`` row not found by PK (HTTP 404 anular)."""


class ReimpresionAlreadyPendingError(Exception):
    """V2: chain-tip guard already finds an 'autorizada' row (HTTP 409)."""


class AnulacionNoPermitidaError(Exception):
    """V2: chain-tip already terminal (HTTP 409 anulacion terminal)."""


class CostoServicioNoConfiguradoError(Exception):
    """DEC-TKT-05 runtime defensive check (HTTP 409 create)."""


# ---------------------------------------------------------------------------
# Helpers (stubs at T1.2 -- real bodies land in T2.3 / T2.4)
# ---------------------------------------------------------------------------


async def buscar_ingreso_por_uuid(session: Any, *, uuid_ingreso: Any) -> Any:
    """V1: lookup ``prod.ingreso`` by PK -- T2.3 GREEN carries the body."""


async def buscar_reimpresion_por_uuid(session: Any, *, uuid: Any) -> Any:
    """V1/V2: lookup ``prod.reimpresion_ticket`` by PK -- T2.3 GREEN body."""


async def buscar_reimpresion_activa_por_ingreso(
    session: Any, *, uuid_ingreso: Any
) -> Any:
    """V2 KD-TKT-02: chain-tip guard via ``SELECT ... FOR UPDATE`` -- T2.3 body."""


async def buscar_factura_por_uuid(session: Any, *, uuid_factura: Any) -> Any:
    """V3 DEC-TKT-04: lookup ``prod.facturas`` by PK -- T2.3 GREEN body."""


async def buscar_costo_servicio_vigente_por_concepto(
    session: Any, *, concepto: Any
) -> Any:
    """DEC-TKT-05: vigente ``prod.costos_servicios`` lookup -- T2.4 body."""


async def check_idempotency_key(
    session: Any, *, idempotency_key: Any, endpoint: Any
) -> Any:
    """DEC-IDEM-01: thin ``prod.idempotency_keys`` wrapper -- T2.4 body."""
