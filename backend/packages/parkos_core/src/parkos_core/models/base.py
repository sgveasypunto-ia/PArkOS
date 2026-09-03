"""ORM abstract bases for parkos_core models (design §3.2 + §3.3).

Five abstract declarative bases, one per audit level:

- :class:`VersionedBase` — [V] bi-temporal close+insert
- :class:`LifecycleEventBase` — [L-E] insert-only lifecycle events
- :class:`WorkflowBase` — [L-W] state machine transitions
- :class:`SessionBase` — [L-S] session lifecycle
- :class:`AppendOnlyBase` — [A] hash chain + retention + append-only

Mixin composition (fixed per design):

- :class:`IdMixin` — PK ``uuid`` column (tables with composite PKs override)
- :class:`AuditMixin` — ``created_at``, ``created_by`` (mandatory, AGENTS.md §1)
- :class:`SyncMixin` — ``sync_status``, ``sync_timestamp``, ``sync_attempts``
- :class:`VersionedMixin` — ``vigente_desde``, ``vigente_hasta``, ``estado``
- :class:`RetentionMixin` — ``fecha_retencion_hasta`` (DIAN retention)
- :class:`HashChainMixin` — ``hash_anterior``, ``hash_actual`` (chain)

Each abstract base carries a class-level marker (``__close_and_insert_only__`` /
``__write_only__`` / ``__record_only__`` / ``__workflow_only__`` /
``__session_only__``) consumed by the AST scan in ``tests/static/``. The
markers carry zero runtime cost — they are pure metadata walked by ``__mro__``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import CHAR, Date, DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Top-level declarative base. All parkos ORM classes descend from this."""


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------


class IdMixin:
    """Primary-key ``uuid`` column.

    Concrete tables with composite primary keys (e.g. partitioned [A] tables
    keyed by ``(uuid, fecha_retencion_hasta)``) MUST re-declare ``uuid``
    with ``primary_key=False`` and override the PK via a ``PrimaryKeyConstraint``
    in ``__table_args__``. See ``models/A/log_transaccional.py`` for the pattern.
    """

    uuid: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        nullable=False,
    )


class AuditMixin:
    """``created_at`` + ``created_by`` — mandatory on every table (AGENTS.md §1).

    ``created_by`` is intentionally NOT a foreign key to ``usuarios``: users
    can be closed via bi-temporal versioning, but the audit trail must survive
    that closure. The audit layer holds a snapshot of the actor's ``uuid`` at
    write time.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("NOW()"),
    )
    created_by: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )


class SyncMixin:
    """Per-row sync bookkeeping on every replicated table."""

    sync_status: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        server_default="pendiente",
    )  # 'pendiente' | 'sincronizado' | 'error'
    sync_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    sync_attempts: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        server_default="0",
    )


class VersionedMixin:
    """[V] bi-temporal versioning columns."""

    vigente_desde: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        server_default=text("NOW()"),
    )
    vigente_hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )
    estado: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        server_default="activo",
    )  # 'activo' | 'inactivo'


class RetentionMixin:
    """[A] DIAN retention column (5+ years per DIAN).

    For DIAN tables the ``append_only.append_event`` helper sets
    ``NOW() + INTERVAL '5 years'`` on insert. Non-DIAN [A] tables leave this
    NULL by default.
    """

    fecha_retencion_hasta: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )


class HashChainMixin:
    """[A] SHA-256 hash chain columns — ONLY ``log_transaccional`` + ``revocacion_factura``.

    Server-computed by ``repo.hash_chain.append``. Pydantic schemas MUST NOT
    accept these columns from the client (defense in depth, design §11 step 4).
    """

    hash_anterior: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    hash_actual: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)


# ---------------------------------------------------------------------------
# Abstract bases (one per audit level)
# ---------------------------------------------------------------------------


class VersionedBase(Base, IdMixin, AuditMixin, SyncMixin, VersionedMixin):
    """[V] Bi-temporal close+insert (REQ-04, REQ-05)."""

    __abstract__ = True
    __close_and_insert_only__ = True


class LifecycleEventBase(Base, IdMixin, AuditMixin, SyncMixin):
    """[L-E] Insert-only lifecycle event."""

    __abstract__ = True
    __record_only__ = True


class WorkflowBase(Base, IdMixin, AuditMixin, SyncMixin):
    """[L-W] State machine transitions (REQ-X9, REQ-21-W-TRANSITION)."""

    __abstract__ = True
    __workflow_only__ = True


class SessionBase(Base, IdMixin, AuditMixin, SyncMixin):
    """[L-S] Session lifecycle (login + sesion tables)."""

    __abstract__ = True
    __session_only__ = True


class AppendOnlyBase(Base, IdMixin, AuditMixin, SyncMixin, RetentionMixin):
    """[A] Append-only with retention. [A] tables carry REVOKE UPDATE/DELETE.

    Defense in depth, AGENTS.md §1 + §3:
    - DB layer: REVOKE + ``BEFORE UPDATE OR DELETE`` trigger blocks mutation.
    - ORM layer: this marker tells AST tests ``session.execute(update/delete)``
      on a concrete subclass is a violation outside ``repo/append_only.py``.

    Note: ``Base`` MUST be the first parent in the MRO so SQLAlchemy 2.0
    registers the abstract base as a proper ``DeclarativeBase`` subclass.
    Without this, concrete subclasses fail with ``TypeError: __init__() got
    an unexpected keyword argument 'uuid'`` at instantiation time. This was
    a latent bug introduced in PR1b and caught by the PR2 sub-agent.
    """

    __abstract__ = True
    __write_only__ = True


__all__ = [
    "Base",
    "IdMixin",
    "AuditMixin",
    "SyncMixin",
    "VersionedMixin",
    "RetentionMixin",
    "HashChainMixin",
    "VersionedBase",
    "LifecycleEventBase",
    "WorkflowBase",
    "SessionBase",
    "AppendOnlyBase",
]