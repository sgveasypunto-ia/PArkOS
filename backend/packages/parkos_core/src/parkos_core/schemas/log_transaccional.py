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

- ``uuid_sucursal``: OPTIONAL branch selector. Required by the original
  branch-scoped dashboard (HU-F15.2 Empresa singleton uses the
  optional ``tabla_afectada`` filter instead). The SQL would have to
  scan the whole table without any selector (the partition key is
  ``fecha_retencion_hasta``, not ``uuid_sucursal``), so at least ONE of
  ``uuid_sucursal`` and ``tabla_afectada`` MUST be present (model
  validator raises 422 otherwise). The admin issuer can scope by branch
  (``uuid_sucursal``), by singleton table (``tabla_afectada='empresa'``,
  HU-F15.2 Empresa bitácora), or both (AND).

- ``tabla_afectada``: NEW (HU-F15.2). Optional singleton-table filter.
  When provided without ``uuid_sucursal`` the response carries every
  row whose ``tabla_afectada`` column matches (Empresa is a singleton
  and the dashboard needs every edit, not just one branch's).

  Note on the "at least one selector" rule: the model_validator that
  enforced this in earlier drafts returned ``pydantic_core.ValidationError``
  which FastAPI's default exception handler does NOT translate into
  422 when raised inside ``Depends()`` -- it surfaced as a 500. We
  validate the same rule in the route handler instead
  (``api/v1/audit.py`` step 3) so the operator sees the correct
  ``missing_selector`` 422 with the same shape as the Layer-4
  violations.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Any

from pydantic import Field

from .common import ReadListBase, _Base


class AuditLogQueryParams(_Base):
    """Query params for ``GET /api/v1/admin/audit/log``.

    The handler at ``api/v1/audit.py`` requires at least ONE of
    ``uuid_sucursal`` and ``tabla_afectada`` and raises
    ``missing_selector`` 422 otherwise. Both fields are typed
    ``Optional[...]`` here so Pydantic does not reject the empty
    case at the Depends() boundary; the handler runs the check
    explicitly so FastAPI emits the right 422 shape.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    tabla_afectada: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Optional singleton-table filter. HU-F15.2 EmpresaBitacoraTab "
            "queries by ``tabla_afectada='empresa'`` to retrieve every "
            "audit row for the Empresa singleton (Empresa has no branch)."
        ),
    )
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
