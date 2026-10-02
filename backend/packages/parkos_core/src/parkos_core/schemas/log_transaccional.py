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
from datetime import date, datetime
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


# ============================================================================
# HU-F20.4 — Bitácora: cross-branch read, hash-chain verification, typeahead
# ============================================================================
#
# New read-only surface under ``api/v1/auditoria.py`` (``GET
# /admin/log-transaccional`` + ``.../verify-chain`` + ``.../buscar``),
# deliberately NOT mounted on ``audit.py`` (IT-12's single/ambient-tenant
# endpoint, which stays untouched). ``AuditLogItem`` already mirrors
# ``log_transaccional``'s full business-column shape 1:1, so the list
# endpoint reuses it (and ``AuditLogListResponse``) directly rather than
# declaring a near-duplicate Pydantic model.


class LogTransaccionalListQueryParams(_Base):
    """Query params for ``GET /admin/log-transaccional`` (HU-F20.4).

    Unlike IT-12's ``AuditLogQueryParams``, there is no "at least one
    selector required" rule here: omitting ``uuid_sucursal`` means
    "every branch the admin is permitted to see" (cross-branch sweep,
    mirrors ``admin_views.sync_log_list``'s convention), not "reject the
    request". ``uuid_sucursal`` narrows to exactly one branch and the
    route 403s ``unauthorized_sucursal_context`` when it is not in the
    admin's permitted set.
    """

    tabla: str | None = Field(
        default=None,
        max_length=64,
        description="Optional table filter, maps to tabla_afectada.",
    )
    uuid_registro: uuid_lib.UUID | None = Field(
        default=None,
        description="Optional affected-record uuid filter, maps to uuid_registro_afectado.",
    )
    uuid_sucursal: uuid_lib.UUID | None = Field(
        default=None,
        description=(
            "Optional single-branch selector. Must be one of the admin's "
            "permitted branches (extract_sucursales_permitidas_fresh); "
            "omitted, the query scopes to every permitted branch."
        ),
    )
    uuid_usuario: uuid_lib.UUID | None = Field(
        default=None,
        description="Optional acting-user uuid filter.",
    )
    desde: date | None = Field(
        default=None,
        description="Inclusive start date, filtered on timestamp_evento.",
    )
    hasta: date | None = Field(
        default=None,
        description="Inclusive end date, filtered on timestamp_evento.",
    )
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ChainAnomalyItem(_Base):
    """One ``ChainAnomaly`` (``sync.motor.verify_chain``), wire shape.

    1:1 field mirror of ``parkos_core.sync.motor.verify_chain.ChainAnomaly``
    -- see that module for the detection semantics.
    """

    tabla: str
    uuid_sucursal: uuid_lib.UUID | None
    uuid: uuid_lib.UUID
    expected: str
    actual: str | None
    seq: int | None
    reason: str


class VerifyChainResponse(_Base):
    """``GET /admin/log-transaccional/verify-chain`` response envelope."""

    ok: bool
    anomalias: list[ChainAnomalyItem]


class BuscarPrefijoItem(_Base):
    """One typeahead match (``GET /admin/log-transaccional/buscar``).

    Deliberately thinner than ``AuditLogItem`` -- just enough for a
    typeahead to disambiguate candidates (table + affected record +
    branch + when), not the full audit payload diff.
    """

    uuid: uuid_lib.UUID
    tabla_afectada: str | None
    uuid_registro_afectado: uuid_lib.UUID | None
    uuid_sucursal: uuid_lib.UUID | None
    timestamp_evento: datetime


class BuscarPrefijoResponse(_Base):
    """``GET /admin/log-transaccional/buscar`` response envelope. No cursor."""

    items: list[BuscarPrefijoItem]
