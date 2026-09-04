"""Per-class conflict resolution for the sync layer (T-PR9-03).

``ConflictResolver.apply_pushed_row`` decides what happens when a row
arrives from the cloud-side ``/sync/push`` (or the branch-side
``/sync/pull``). The policy mirrors the audit-first data architecture
(``AGENTS.md`` §1-§3) — once a row lands, it can never be deleted or
rewritten physically:

- ``[V]`` versioned rows: each incoming row is a NEW version of the
  logical entity; the resolver inserts it. If the per-row monotonic
  ``seq`` is BELOW what the local DB already has for the same
  ``uuid_registro``, the incoming row loses; the caller records the loss
  in ``sync_conflict`` and we return :class:`ApplyOutcome.CONFLICT_V`.
- ``[L-E]`` / ``[L-W]`` / ``[A]`` append-only: conflict is impossible
  (an event log has no overwrite semantics). Returns
  :class:`ApplyOutcome.APPLIED` and the worker calls the appropriate
  repo helper.
- ``[L-S]`` sessions: grace window (``JWT_OVERLAP_HOURS`` = 24h)
  during which both sides may legitimately write a ``close_session``
  for the same ``uuid_sesion``. After the grace expires, cloud-wins
  per §21.10.

Seq-mismatch vs INVALID-seq contract: a missing/non-int ``seq`` is
treated as :class:`ApplyOutcome.ERROR` so the caller can retry. A
strictly-lower-than-local ``seq`` is :class:`ApplyOutcome.CONFLICT_V`
(caller writes ``sync_conflict``). These two are deliberately distinct:
``ERROR`` means "I couldn't decide" (transient); ``CONFLICT_V`` means
"we have a real conflict; please record it".

Cites design §21.10 (conflict resolution), REQ-X9 (chain tie-break via
the per-row monotonic seq).

Per-row seq lookup — design intent and PR9b ownership:
The per-row monotonic ``seq`` lives in the destination table itself
(not in ``prod.sync_log``, which is a worker-cycle diagnostic record
without per-row content). The default implementation of
:meth:`ConflictResolver._read_local_seq` therefore returns ``None`` —
the resolver treats the absence as "no conflict possible" and accepts
the incoming row. PR9b's worker wires the concrete lookup against
the actual destination [V] tables; this helper stays table-class
agnostic so adding new [V] tables does not require touching this
module.
"""
from __future__ import annotations

import enum
import uuid as uuid_lib

from sqlalchemy.ext.asyncio import AsyncSession


class ApplyOutcome(enum.StrEnum):
    """Result of applying a single pushed row."""

    APPLIED = "applied"
    CONFLICT_V = "conflict_v"
    CONFLICT_LS = "conflict_ls"
    ERROR = "error"


# Import the concrete exception types we explicitly swallow so ruff's
# blind-exception check (``BLE001``) is satisfied. Anything else
# propagates so genuine bugs (e.g. DB-driver programming errors)
# surface during the sync worker's structured-logging error path.
from sqlalchemy.exc import SQLAlchemyError

# Tables classified as append-only ([A]) — no conflict ever.
APPEND_ONLY_TABLES: frozenset[str] = frozenset({
    "sync_queue",
    "sync_log",
    "sync_conflict",
    "log_transaccional",
    "factura_detalle",
    "factura_impuestos",
    "factura_otros_cobros",
    "factura_pagos",
    "revocacion_factura",
    "caja",
    "arqueo",
    "pairing_tokens",
    "revoked_sync_jwts",
    "idempotency_keys",
    "salidas",
})

# Tables classified as lifecycle events [L-E] — append-only (no conflict).
LIFECYCLE_EVENT_TABLES: frozenset[str] = frozenset({
    "ingreso",
    "facturas",
    "factura_electronica",
})

# Tables classified as workflows [L-W] — append-only (no conflict).
WORKFLOW_TABLES: frozenset[str] = frozenset({
    "anulaciones",
    "reclamos",
    "alerta",
    "reimpresion_ticket",
    "envio_dian",
    "validacion_evento",
})

# Tables classified as sessions [L-S] — grace-window conflict possible.
SESSION_TABLES: frozenset[str] = frozenset({
    "login",
    "sesion",
})


def _coerce_seq(datos: dict | None) -> int | None:
    """Return the per-row ``seq`` from ``datos`` (or ``None`` if missing/invalid).

    The ``seq`` lives in the ``datos->>'seq'`` projection (Postgres JSONB
    accessor on the wire); here we accept it from the already-parsed
    ``datos`` dict. Non-int values yield ``None`` so the caller can
    distinguish "missing" from "lower than local" — the former is
    :class:`ApplyOutcome.ERROR`, the latter is :class:`ApplyOutcome.CONFLICT_V`.
    """
    if not isinstance(datos, dict):
        return None
    raw = datos.get("seq")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class ConflictResolver:
    """Apply pushed rows from a branch sync to the local DB.

    Args:
        jwt_overlap_hours: Length of the [L-S] grace window during
            which both sides may legitimately write a session close.
            Default 24h per §21.10.
    """

    def __init__(self, *, jwt_overlap_hours: int = 24) -> None:
        if jwt_overlap_hours < 0:
            raise ValueError("jwt_overlap_hours must be >= 0")
        self.jwt_overlap_hours = jwt_overlap_hours

    async def apply_pushed_row(
        self, session: AsyncSession, row: dict
    ) -> ApplyOutcome:
        """Apply a pushed row from the branch to the local DB.

        Args:
            session: Active ``AsyncSession`` (caller commits).
            row: Pushed row with shape ``{tabla, uuid_registro, datos,
                uuid_sucursal, timestamp_evento, seq, actor_uuid}``.

        Returns:
            :class:`ApplyOutcome` — one of ``APPLIED``, ``CONFLICT_V``,
            ``CONFLICT_LS``, ``ERROR``. The caller is responsible for
            translating outcomes into repo writes (``sync_conflict`` for
            conflicts) and into the next-batch decision (``ERROR`` →
            retry the whole batch).
        """
        tabla = row.get("tabla")
        uuid_registro = row.get("uuid_registro")
        datos = row.get("datos") or {}

        if not isinstance(tabla, str) or not tabla:
            return ApplyOutcome.ERROR
        if not isinstance(uuid_registro, (str, uuid_lib.UUID)):
            return ApplyOutcome.ERROR

        # Coerce the per-row seq; missing/invalid → caller retries.
        incoming_seq = _coerce_seq(datos)
        if incoming_seq is None or incoming_seq < 0:
            return ApplyOutcome.ERROR

        # Append-only classes — accept unconditionally.
        if (
            tabla in APPEND_ONLY_TABLES
            or tabla in LIFECYCLE_EVENT_TABLES
            or tabla in WORKFLOW_TABLES
        ):
            return ApplyOutcome.APPLIED

        # [L-S] sessions — grace-window logic (happy path returns APPLIED).
        # Future PR may branch on ``self.jwt_overlap_hours`` + ``row.timestamp_evento``
        # to detect out-of-grace-window closes; for PR9a the helper returns
        # APPLIED so the worker proceeds with the write.
        if tabla in SESSION_TABLES:
            return ApplyOutcome.APPLIED

        # Default: [V] (versioned). Check the per-row seq before
        # admitting the row as a new version. The default
        # :meth:`_read_local_seq` returns ``None`` (no conflict possible);
        # PR9b's worker wires the concrete lookup per destination table.
        try:
            existing = await self._read_local_seq(session, tabla, uuid_registro)
        except SQLAlchemyError:
            # Driver / connection failure — caller retries the batch.
            return ApplyOutcome.ERROR
        if existing is not None and existing > incoming_seq:
            return ApplyOutcome.CONFLICT_V
        return ApplyOutcome.APPLIED

    async def _read_local_seq(
        self,
        session: AsyncSession,
        tabla: str,
        uuid_registro: str | uuid_lib.UUID,
    ) -> int | None:
        """Return the highest locally-known ``seq`` for ``(tabla, uuid_registro)``.

        Default implementation returns ``None`` — the per-row monotonic
        ``seq`` lives in the destination table itself (varies by table),
        so this helper stays table-class agnostic. PR9b's worker wraps
        or subclasses :class:`ConflictResolver` to provide the concrete
        lookup per [V] destination table.
        """
        return None


__all__ = [
    "APPEND_ONLY_TABLES",
    "LIFECYCLE_EVENT_TABLES",
    "SESSION_TABLES",
    "WORKFLOW_TABLES",
    "ApplyOutcome",
    "ConflictResolver",
]
