"""Pydantic v2 schemas for the sync-infrastructure ``[A]`` tables
(REQ-14-A-SYNC-FACADE, REQ-14-A-SYNC-LOG, REQ-14-A-SYNC-CONFLICT,
REQ-16, REQ-X4).

Five tables covered, all ``[A]`` (append-only) per AGENTS.md §1 + §3:

  - ``prod.sync_queue``     — carved-out [A] table; ``rol_app`` keeps
                              UPDATE/DELETE grants so the workers can
                              flip ``estado`` + ``intentos``. Only the
                              four whitelisted columns
                              (``estado``, ``intentos``, ``next_retry_at``,
                              ``ultimo_error``) are mutable from Python;
                              the column whitelist is enforced
                              client-side by
                              :mod:`parkos_core.repo.sync_queue`.
  - ``prod.sync_log``       — diagnostic counters written by the sync
                              workers (sent/succeeded/failed/conflicts,
                              per-batch duration).
  - ``prod.sync_conflict``  — snapshot of a disagreement between cloud
                              and branch (preserves ``datos_local`` +
                              ``datos_cloud`` for offline review).
  - ``prod.log_transaccional`` — the audit log; carries the SHA-256
                              hash chain (``hash_anterior`` +
                              ``hash_actual``) extended by
                              :func:`parkos_core.repo.hash_chain.append`.
  - ``prod.revocacion_factura`` — DIAN revocation events; also
                              carries the SHA-256 chain (the second of
                              only two chain carriers).

Per the bi-temporal canon AGENTS.md §3 the API exposes **Consulta,
Inserción** only — there is no ``Update`` shape for any of these
``[A]`` tables. ``SyncQueue`` is the carve-out that allows UPDATE on
four whitelisted columns, but that mutation is mediated by
:mod:`parkos_core.repo.sync_queue` (``mark_dispatched``,
``mark_failed``, ``mark_in_progress``) and never goes through a
Pydantic ``Update`` schema.

All schemas inherit :class:`_Base` from :mod:`.common`
(``extra='forbid'``, ``from_attributes=True``).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from ..repo.sync_queue import Operacion
from .common import _Base
from pydantic import Field

# `Operacion` is re-exported below in __all__ so callers can write
# `from parkos_core.schemas.sync_infra import Operacion` and get the
# SAME literal the repo helpers use. Keeping a single source of truth
# prevents drift between the Pydantic validator and the SQL helpers.

# ---------------------------------------------------------------------------
# SyncQueue (carved-out [A], REQ-14-A-SYNC-FACADE, design §12)
# ---------------------------------------------------------------------------


class SyncQueueRead(_Base):
    """Full read-back for ``prod.sync_queue`` (composite PK, carved-out [A]).

    Mirrors the ORM 1:1. Includes the four whitelisted columns
    (``estado``, ``intentos``, ``next_retry_at``, ``ultimo_error``)
    because the canonical mutation path is via
    :mod:`parkos_core.repo.sync_queue` helpers, not via Pydantic.
    Operators reading the row directly via the admin tooling need to
    see these values to interpret worker progress.
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    operacion: str | None
    tabla: str | None
    uuid_registro: uuid_lib.UUID | None
    datos: dict | None
    prioridad: int | None
    estado: str | None
    intentos: int | None
    next_retry_at: datetime | None
    ultimo_error: str | None


class SyncQueueCreate(_Base):
    """Create shape for ``prod.sync_queue``.

    Excludes server-computed columns:

    - ``uuid`` + ``fecha_retencion_hasta`` — composite PK; both server-
      defaulted (``gen_random_uuid()`` + ``current_date``).
    - ``created_at`` + ``created_by`` — audit mixin; server-set.
    - ``sync_status`` + ``sync_timestamp`` + ``sync_attempts`` — sync
      bookkeeping; server-set when the sync engine claims the row.
    - ``estado`` + ``intentos`` + ``next_retry_at`` + ``ultimo_error`` —
      the four whitelisted worker mutation columns. These are
      populated by :mod:`parkos_core.repo.sync_queue` helpers
      (``mark_dispatched`` / ``mark_failed`` / ``mark_in_progress``),
      not by the API caller.

    Required business columns:
    - ``operacion`` — one of ``"insert"``, ``"update"``, ``"delete"``,
      ``"compensate"``. Same :data:`Operacion` literal as
      :mod:`parkos_core.repo.sync_queue`.
    - ``tabla`` — source table name (e.g. ``"factura_pagos"``).
    - ``uuid_registro`` — UUID of the row being synced.
    - ``datos`` — payload to forward.

    Optional:
    - ``uuid_sucursal`` — tenant scope. ``None`` for cloud-global rows.
    - ``prioridad`` — override the default priority
      (``10`` for ``insert``, ``0`` for everything else).
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    operacion: Operacion
    tabla: str
    uuid_registro: uuid_lib.UUID
    datos: dict
    prioridad: int | None = None


# ---------------------------------------------------------------------------
# SyncLog (REQ-14-A-SYNC-LOG)
# ---------------------------------------------------------------------------


class SyncLogRead(_Base):
    """Full read-back for ``prod.sync_log`` (composite PK, [A]).

    The diagnostic record written by ``job_sync_sucursal`` and
    ``job_sync_cloud`` after each batch. Operators inspect this to
    detect stalled workers and size the ``sync_batch_size`` knob.
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    operaciones_enviadas: int | None
    operaciones_exitosas: int | None
    operaciones_fallidas: int | None
    conflictos: int | None
    duracion_ms: int | None


class SyncLogCreate(_Base):
    """Create shape for ``prod.sync_log``.

    Excludes server-computed columns (composite PK + audit + sync
    bookkeeping). The metric columns + ``timestamp_evento`` are
    worker-supplied — that's the whole point of the row.

    ``timestamp_evento`` defaults to ``NOW()`` at the DB layer; the
    worker MAY supply an explicit value if it batched the metrics
    after a clock-skew correction.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    timestamp_evento: datetime | None = None
    operaciones_enviadas: int | None = None
    operaciones_exitosas: int | None = None
    operaciones_fallidas: int | None = None
    conflictos: int | None = None
    duracion_ms: int | None = None


# ---------------------------------------------------------------------------
# SyncConflict (REQ-14-A-SYNC-CONFLICT)
# ---------------------------------------------------------------------------


class SyncConflictRead(_Base):
    """Full read-back for ``prod.sync_conflict`` (single PK, [A]).

    Records a sync-time disagreement between cloud and branch. Both
    sides preserve their own snapshot (``datos_local``,
    ``datos_cloud``) for offline review. The ``alerta`` workflow (PR6)
    escalates unresolved conflicts.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date | None
    uuid_sucursal: uuid_lib.UUID | None
    tabla: str | None
    uuid_registro: uuid_lib.UUID | None
    datos_local: dict | None
    datos_cloud: dict | None
    politica: str | None
    resolucion: str | None
    timestamp_evento: datetime | None


class SyncConflictCreate(_Base):
    """Create shape for ``prod.sync_conflict``.

    Excludes server-computed columns (single PK + audit + sync
    bookkeeping + retention). The conflict payload (``datos_local``,
    ``datos_cloud``, ``politica``, ``resolucion``) is worker-supplied.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    tabla: str | None = None
    uuid_registro: uuid_lib.UUID | None = None
    datos_local: dict | None = None
    datos_cloud: dict | None = None
    politica: str | None = None
    resolucion: str | None = None
    timestamp_evento: datetime | None = None


# ---------------------------------------------------------------------------
# LogTransaccional (audit log + SHA-256 chain, REQ-16, REQ-X4)
# ---------------------------------------------------------------------------


class LogTransaccionalRead(_Base):
    """Full read-back for ``prod.log_transaccional`` (composite PK, [A]).

    The audit log written by every API state-changing operation.
    Carries the SHA-256 chain columns (``hash_anterior``,
    ``hash_actual``) — :class:`_Base` exposes them so the read shape
    can power the cloud-side chain verifier (PR10) and the admin
    audit dashboard. Callers that surface this row to the public API
    MUST strip the hash columns client-side (same defense-in-depth
    pattern as :class:`PairingTokenRead` for ``pairing_token_hash``).
    """

    uuid: uuid_lib.UUID
    fecha_retencion_hasta: date
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_usuario: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID | None
    accion: str | None
    tabla_afectada: str | None
    uuid_registro_afectado: uuid_lib.UUID | None
    uuid_referencia: uuid_lib.UUID | None
    datos_anteriores: dict | None
    datos_nuevos: dict | None
    timestamp_evento: datetime | None
    hash_anterior: str | None
    hash_actual: str | None


class LogTransaccionalCreate(_Base):
    """Create shape for ``prod.log_transaccional``.

    Excludes server-computed columns:

    - ``uuid`` + ``fecha_retencion_hasta`` — composite PK; both server-
      defaulted (``gen_random_uuid()`` + ``current_date``).
    - ``created_at`` + ``created_by`` — audit mixin; server-set.
    - ``sync_status`` + ``sync_timestamp`` + ``sync_attempts`` — sync
      bookkeeping; server-set when the sync engine claims the row.
    - ``hash_anterior`` + ``hash_actual`` — the SHA-256 chain columns
      are computed by :func:`parkos_core.repo.hash_chain.append`,
      NOT by the API caller. Pydantic rejects any attempt to set
      these (defense in depth, design §11 step 4).

    **Required**: ``uuid_sucursal`` — every audit row is anchored to a
    tenant; the SHA-256 chain is per-tenant (the genesis hash is
    ``sha256("genesis:" + uuid_sucursal_bytes)``).
    """

    uuid_usuario: uuid_lib.UUID | None = None
    uuid_sucursal: uuid_lib.UUID
    accion: str | None = None
    tabla_afectada: str | None = None
    uuid_registro_afectado: uuid_lib.UUID | None = None
    uuid_referencia: uuid_lib.UUID | None = None
    datos_anteriores: dict | None = None
    datos_nuevos: dict | None = None
    timestamp_evento: datetime | None = None


# ---------------------------------------------------------------------------
# RevocacionFactura (DIAN revocation + SHA-256 chain, REQ-16, REQ-X4)
# ---------------------------------------------------------------------------


class RevocacionFacturaRead(_Base):
    """Full read-back for ``prod.revocacion_factura`` (single PK, [A]).

    DIAN revocation event; the second of only two tables that carry
    the SHA-256 chain (``log_transaccional`` is the other). The cloud-
    side verifier (PR10) walks the chain and raises
    :class:`parkos_core.repo.hash_chain.HashChainIntegrityViolation`
    on a break.

    The hash chain columns are exposed here for the same reason as
    :class:`LogTransaccionalRead` — internal tooling (chain verifier,
    admin audit dashboard) needs them. Public-API serialization MUST
    drop them.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_factura_electronica: uuid_lib.UUID | None
    uuid_factura_electronica_reemplazo: uuid_lib.UUID | None
    motivo: str | None
    timestamp_evento: datetime | None
    hash_anterior: str | None
    hash_actual: str | None


class RevocacionFacturaCreate(_Base):
    """Create shape for ``prod.revocacion_factura``.

    Excludes server-computed columns:

    - ``uuid`` — single PK; server-defaulted.
    - ``created_at`` + ``created_by`` — audit mixin; server-set.
    - ``sync_status`` + ``sync_timestamp`` + ``sync_attempts`` — sync
      bookkeeping; server-set when the sync engine claims the row.
    - ``fecha_retencion_hasta`` — DIAN retention; server-set by the
      retention worker (PR10).
    - ``hash_anterior`` + ``hash_actual`` — the SHA-256 chain columns
      are computed by :func:`parkos_core.repo.hash_chain.append`.

    All identity / business fields are accepted: ``uuid_sucursal``
    anchors the chain tenant; ``uuid_factura_electronica`` and the
    optional ``uuid_factura_electronica_reemplazo`` link the
    revocation to its parent factura; ``motivo`` carries the DIAN-
    required reason text.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_factura_electronica: uuid_lib.UUID | None = None
    uuid_factura_electronica_reemplazo: uuid_lib.UUID | None = None
    motivo: str | None = None
    timestamp_evento: datetime | None = None


__all__ = [
    "LogTransaccionalCreate",
    "LogTransaccionalRead",
    "Operacion",
    "RevocacionFacturaCreate",
    "RevocacionFacturaRead",
    "SyncConflictCreate",
    "SyncConflictRead",
    "SyncEstadoQueryParams",
    "SyncEstadoRead",
    "SyncLogCreate",
    "SyncLogRead",
    "SyncQueueCreate",
    "SyncQueueRead",
]


# ---------------------------------------------------------------------------
# SyncEstadoRead + SyncEstadoQueryParams (HU-F1.14)
# ---------------------------------------------------------------------------


class SyncEstadoQueryParams(_Base):
    """Query params for ``GET /api/v1/sync/estado``.

    Layer 4 defense: inherits ``extra='forbid'`` from :class:`_Base`,
    so a client smuggling an unknown field (e.g. ``actor_uuid``,
    ``computed_at``, ``cache_key``) triggers ``ValidationError`` and
    FastAPI returns ``422``.

    The branch identifier is required (``uuid_sucursal: UUID``) -- the
    Pydantic UUID validator rejects malformed values (R9 LOW, design
    §12). ``administrador`` cross-branch queries carry the operator's
    session UUID here directly; ``operador`` queries carry their own
    pinned branch (Layer 2 tenant scope checks ``ctx.sucursal_uuid``).
    """

    uuid_sucursal: uuid_lib.UUID


class SyncEstadoRead(_Base):
    """Response shape for ``GET /api/v1/sync/estado``.

    Mirrors the contract per design §10.4 + spec REQ-OPS-100:

    * ``uuid_sucursal`` -- the branch the snapshot describes.
    * ``ultima_sync_at`` -- ``datetime | None``. ``None`` means the
      branch has never synced (DEC-SYNC-08).
    * ``lag_seg`` -- ``int | None``. ``None`` when ``ultima_sync_at`` is
      ``None``; otherwise ``int((NOW() - ultima_sync_at).total_seconds())``
      with ``>= 0`` (DEC-SYNC-08). SyncBanner renders this as
      NEVER SYNCED / VERDE / AMARILLO / ROJO per plan.md lines
      2275-2291.
    * ``pendientes`` -- ``int >= 0`` (DEC-SYNC-09). ``count(*)``
      semantics: NEVER null, ALWAYS non-negative. SyncBanner renders
      a high-pile alert badge when ``pendientes >= 100``.

    Layer 4: ``extra='forbid'`` blocks unknown response fields.
    """

    uuid_sucursal: uuid_lib.UUID
    ultima_sync_at: datetime | None
    lag_seg: int | None
    pendientes: int = Field(ge=0)
