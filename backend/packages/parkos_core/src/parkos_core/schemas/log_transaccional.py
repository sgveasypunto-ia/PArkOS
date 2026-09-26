"""Pydantic schemas for the admin audit-log read endpoint (IT-12).

Read-only edge schema for ``GET /api/v1/admin/audit/log``. Mirrors the
business columns of ``prod.log_transaccional`` (HU-F1.10 audit
contract) and adds a ``datos_nuevos`` / ``datos_anteriores`` payload
shape so the renderer can render the change diff inline without a
second round-trip.

``extra='forbid'`` from :class:`_Base` (Layer 4): a client smuggling
unknown fields (``actor_uuid``, ``cache_key``, ``computed_at``,
``vigente_desde``, ``vigente_hasta``) is rejected with 422.

Filter + pagination:

- ``limit``: 1..100, default 20. Mirrors the F1.15 precedent
  (``DEC-LOGIN-04`` -- the dashboard's natural page is "the last 20
  mutations across the branch", not "the whole history").

- ``cursor``: opaque base64 JSON ``(timestamp_evento_iso, uuid)`` from
  the previous page; ``None`` for the first page.

- ``uuid_sucursal``: required query param. Without it the SQL would have
  to scan the whole table (the partition key is ``fecha_retencion_hasta``,
  not ``uuid_sucursal``). The admin endpoint requires the operator to
  pick a branch from the ``<BranchSelector />`` first.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Any

from pydantic import Field

from .common import ReadListBase, _Base


class AuditLogQueryParams(_Base):
    """Query params for ``GET /api/v1/admin/audit/log``.

    The ``uuid_sucursal`` selector is REQUIRED -- without it the SQL
    would have to scan the whole partition range (the table is
    partitioned by ``fecha_retencion_hasta``, not by branch). The
    renderer reads the branch from the active
    ``<BranchSelector />`` selection and passes it on every request.
    """

    uuid_sucursal: uuid_lib.UUID
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class AuditLogItem(_Base):
    """One row in the ``AuditLogListResponse``.

    Mirrors 10 business columns of ``prod.log_transaccional``:

    - ``uuid`` (composite PK with ``fecha_retencion_hasta``; server-
      defaulted date omitted from the wire payload).
    - ``timestamp_evento`` -- naive UTC, NOT nullable per the [L-S]
      audit invariant (``append_only.append_event`` always stamps it).
    - ``uuid_usuario``, ``uuid_sucursal``, ``uuid_referencia`` --
      nullable FKs.
    - ``accion``, ``tabla_afectada`` -- short strings, both nullable in
      the [A] table but in practice always stamped by the audit log.
    - ``datos_anteriores``, ``datos_nuevos`` -- JSONB diff payload
      (nullable). The renderer renders these as a side-by-side diff.
    - ``hash_anterior``, ``hash_actual`` -- SHA-256 hex strings (nullable
      on the genesis row only; all subsequent rows carry them). The
      renderer's integrity badge shows ``hash_anterior -> hash_actual``
      per row.
    """

    uuid: uuid_lib.UUID
    timestamp_evento: datetime
    uuid_usuario: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_referencia: uuid_lib.UUID | None
    accion: str | None
    tabla_afectada: str | None
    datos_anteriores: dict[str, Any] | None
    datos_nuevos: dict[str, Any] | None
    hash_anterior: str | None
    hash_actual: str | None


class AuditLogListResponse(ReadListBase[AuditLogItem]):
    """Cursor-paginated list envelope (mirror of F1.15 DEC-LOGIN-07)."""
