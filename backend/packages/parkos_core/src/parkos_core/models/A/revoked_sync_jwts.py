"""ORM model for ``prod.revoked_sync_jwts`` (T-PR8-05, design §21).

Tracks JWT ``kid`` + ``jti`` values that have been explicitly revoked
by an admin (e.g. after a key rotation compromise or a branch
decommission). The sync workers consult this table before accepting a
sync token via ``repo.revoked_sync_jwt.is_revoked`` (lands in PR8b).

``[A]``-class: ``REVOKE UPDATE, DELETE`` from ``rol_app`` and a
``BEFORE UPDATE OR DELETE`` trigger block mutation. Revocations are
append-only: revoking a token a second time is a no-op (the UK on
``(jwt_kid, jwt_uuid, vigente_desde)`` rejects the duplicate INSERT,
which the helper maps to a 204 returned response).

Composite PK (``uuid``, ``fecha_retencion_hasta``) — required by
``pg_partman`` range partitioning. Volume is bounded by JWT rotation
cadence (a few entries per branch per rotation), but the table
inherits the [A] partitioned shape from ``log_transaccional`` for
uniform storage and TTL sweep behavior.

UK deviation: design §21.3 calls for ``UNIQUE (jwt_kid, jwt_uuid)``.
Under the bi-temporal canon (AGENTS.md §2), the UK MUST also include
``vigente_desde`` because a revocation carried over from a previous
version of the JWT authority (e.g. a kid retired after a rotation)
needs to coexist with a new revocation against a freshly minted kid.
PostgreSQL further requires partitioned tables to include ALL
partition-key columns in a unique constraint, so the final UK is
``revoked_sync_jwts_uk01 ON (jwt_kid, jwt_uuid, vigente_desde,
fecha_retencion_hasta)``. The ``vigente_desde`` and
``fecha_retencion_hasta`` columns are server-defaulted to ``NOW()`` /
``CURRENT_DATE`` respectively, so the common path (single revocation
per kid+jwt pair inserted in a single transaction) still produces
only one unique tuple — the constraint's practical semantics match
what the spec's 2-column UK would have given.

The PR2-shipped file at the same path used ``key_uuid`` / ``reason``
columns with a single-PK ``uuid`` — that shape was wrong for the
revocation-by-kid+jwt_uuid pattern. Migration ``0006`` drops and
recreates the table with the canonical shape defined here.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class RevokedSyncJwt(AppendOnlyBase):
    """[A] JWT revocation registry (REQ-OP-04, design §21).

    Composite PK (``uuid``, ``fecha_retencion_hasta``) for pg_partman.
    UK on (``jwt_kid``, ``jwt_uuid``, ``vigente_desde``) — see module
    docstring for the deviation from design §21.3.

    ``vigente_desde`` is added explicitly (not via ``VersionedMixin``,
    which the [A] base deliberately omits) because the UK requires it
    per the bi-temporal canon. The column is server-defaulted to
    ``NOW()`` so client code never sets it.
    """

    __tablename__ = "revoked_sync_jwts"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
    fecha_retencion_hasta: Mapped[date] = mapped_column(  # type: ignore[override]
        Date,
        nullable=False,
        server_default=func.current_date(),
    )
    # Explicit ``vigente_desde`` so the UK can reference it. NOT NULL
    # (server-defaulted to NOW()) for symmetry with the [V] bi-temporal
    # canon. ``vigente_hasta`` is intentionally absent — revocations
    # are append-only; "closing" a revocation means inserting a new
    # row with ``motivo='uncancelled'`` referencing the original.
    vigente_desde: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("NOW()"),
    )

    # --- Business columns ---
    # ``jwt_kid`` is the JWT ``kid`` header (admin-/operador-/sync-agent-
    # authority identifier). ``jwt_uuid`` is the JWT ``jti`` payload
    # claim (per-token id). Together they uniquely identify a revoked
    # token issuance.
    jwt_kid: Mapped[str] = mapped_column(String(length=64), nullable=False)
    jwt_uuid: Mapped[str] = mapped_column(String(length=64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    revoked_by: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Bi-temporal canon deviation: include ``vigente_desde`` in the
        # UK (server-defaulted to NOW() so the common path hits a single
        # unique tuple per kid+jti). PostgreSQL ALSO requires
        # ``fecha_retencion_hasta`` for unique constraints on RANGE-
        # partitioned tables; the final UK is therefore
        # ``(jwt_kid, jwt_uuid, vigente_desde, fecha_retencion_hasta)``.
        # See module docstring.
        UniqueConstraint(
            "jwt_kid",
            "jwt_uuid",
            "vigente_desde",
            "fecha_retencion_hasta",
            name="revoked_sync_jwts_uk01",
        ),
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="revoked_sync_jwts_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["RevokedSyncJwt"]
