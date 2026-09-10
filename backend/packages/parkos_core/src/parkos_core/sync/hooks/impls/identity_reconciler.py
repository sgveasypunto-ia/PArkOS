"""hooks/impls/identity_reconciler.py — ``IdentityReconciler`` (T-PR5-005, D17).

REQ-HOOK-010: ``hook_pre_insert`` bound to the three ``bidirectional``
identity masters — ``clientes``, ``clientes_b2b``, ``vehiculos`` (each
declaring a non-empty ``natural_key``, T-PR2-006). Classifies an arriving
row against ``HookContext.open_version`` (the currently-open local version
for the SAME normalized natural key, resolved by the caller — see
``hooks/base.py``'s ``HookContext`` docstring) into exactly one of three
``ReconciliationKind`` values:

  - ``noop``    — business columns identical to the open version. The
    motor (``motor/apply_row.py``) skips the repo call entirely; this is
    what prevents version-chain inflation on re-delivery of the same fact.
  - ``forward``  — arriving ``vigente_desde`` is later. Ordinary
    ``close_and_insert``: this hook only supplies ``current_uuid`` (the
    open version's uuid) via ``payload_override`` so the motor closes the
    RIGHT local row.
  - ``historical`` — arriving ``vigente_desde`` is earlier. Inserted as an
    ALREADY-CLOSED version (``vigente_hasta`` = the open version's
    ``vigente_desde``); ``current_uuid=None`` so the currently-open row is
    never touched — no UPDATE, ever.

**Never blocking, never MANUAL.** ``HookResult.proceed`` is always ``True``
here — a blocking resolution would stop a client registration, which stops
the invoice at the counter (Q3's ratified default). When ``forward``/
``historical`` also differs on a **material** column (any business column
other than the natural key itself — natural-key formatting variance alone,
e.g. ``"1020"`` vs. ``"10-20"``, is normal data variance, not a conflict),
an informational ``sync_conflict`` (``politica="identity_divergence"``) is
written directly by this hook (it holds ``ctx.session``) — the apply still
succeeds.

**Never rewrites an existing FK.** This hook only ever INSERTs a new
version or leaves the open version untouched; it never issues an UPDATE
against any FK-holding row. Current-identity resolution for readers happens
by natural key at read time (``prod.v_clientes_actual`` /
``prod.v_vehiculos_actual``, migration ``0009_add_derived_read_views.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from .. import registry
from ..base import HookContext, HookResult

# Columns every [V] row carries that are NEVER part of the "business
# columns identical" comparison — technical/audit/bi-temporal metadata, not
# entity data. ``current_uuid`` is the apply_row.py reserved payload key
# (not a real column) and is excluded for the same reason.
_TECHNICAL_COLUMNS: frozenset[str] = frozenset(
    {
        "uuid",
        "created_at",
        "created_by",
        "sync_status",
        "sync_timestamp",
        "sync_attempts",
        "vigente_desde",
        "vigente_hasta",
        "estado",
        "current_uuid",
    }
)


def _business_columns(payload: dict[str, Any], open_version: dict[str, Any]) -> set[str]:
    """Every column present on either side, minus technical/bi-temporal metadata."""
    return (set(payload) | set(open_version)) - _TECHNICAL_COLUMNS


def _differs(payload: dict[str, Any], open_version: dict[str, Any], columns: set[str]) -> bool:
    return any(payload.get(column) != open_version.get(column) for column in columns)


def _json_safe(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Coerce ``UUID``/``datetime``/``Decimal`` leaf values so the dict is
    JSONB-storable.

    ``sync_conflict.datos_local`` / ``datos_cloud`` are JSONB columns;
    ``asyncpg`` does not auto-serialize ``uuid.UUID``, ``datetime``, or
    ``decimal.Decimal`` values embedded in a plain ``dict``, so this hook
    stringifies/floats them the same way ``repo.hash_chain._json_default``
    does for canonical hashing. ``Decimal`` was never exercised by the 3
    original identity masters (none has a ``Numeric`` business column) —
    found live (``TypeError: Object of type Decimal is not JSON
    serializable``) generalizing identity reconciliation to
    ``Numeric``-carrying tables (``impuestos.porcentaje``,
    ``configuracion_tolerancias.tolerancia_efectivo``, 2026-09-10).
    """
    if value is None:
        return None
    safe: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, UUID):
            safe[key] = str(item)
        elif isinstance(item, datetime):
            safe[key] = item.isoformat()
        elif isinstance(item, Decimal):
            safe[key] = float(item)
        else:
            safe[key] = item
    return safe


async def _write_divergence_conflict(ctx: HookContext, open_version: dict[str, Any]) -> None:
    """Write the informational ``sync_conflict`` row for a divergent arrival.

    Lazily imported to avoid a module-load-time circular between
    ``sync/hooks/impls/*`` and ``models/A/*`` (none exists today, but every
    other hook module in this package follows the same lazy-import
    convention as ``motor/apply_row.py``'s cascade dispatch, see that
    module's ``hook_post_insert`` step).
    """
    from ....models.A.sync_conflict import SyncConflict

    now = datetime.now(UTC).replace(tzinfo=None)
    conflict = SyncConflict(
        uuid_sucursal=ctx.branch_uuid,
        tabla=ctx.spec.name,
        uuid_registro=open_version.get("uuid"),
        datos_local=_json_safe(open_version),
        datos_cloud=_json_safe(ctx.payload),
        politica="identity_divergence",
        resolucion=None,
        timestamp_evento=now,
    )
    ctx.session.add(conflict)


async def identity_reconciler(ctx: HookContext) -> HookResult:
    """``hook_pre_insert`` — D17 natural-key reconciliation (REQ-HOOK-010)."""
    open_version = ctx.open_version
    if not open_version:
        # No currently-open version for this normalized natural key exists
        # locally — nothing to reconcile against, ordinary first insert.
        return HookResult(proceed=True)

    payload = ctx.payload
    business_columns = _business_columns(payload, open_version)

    if not _differs(payload, open_version, business_columns):
        return HookResult(proceed=True, reconciliation="noop")

    arriving_desde = payload.get("vigente_desde")
    open_desde = open_version.get("vigente_desde")
    # Equal timestamps are not spelled out by design.md's case table (only
    # "later" / "earlier" are). Ties resolve to "forward" (ordinary
    # close_and_insert) — the least surprising default, since it matches
    # every other apply's un-reconciled behavior.
    is_forward = arriving_desde is None or open_desde is None or arriving_desde >= open_desde

    # "Material" columns exclude the natural key itself — a raw-formatting
    # difference in the natural key (e.g. "1020" vs "10-20") is expected
    # data variance across independently-registering branches, not a
    # genuine data conflict.
    material_columns = business_columns - set(ctx.spec.natural_key)
    if _differs(payload, open_version, material_columns):
        await _write_divergence_conflict(ctx, open_version)

    if is_forward:
        override = {
            key: value
            for key, value in payload.items()
            if key not in ("vigente_desde", "vigente_hasta", "estado", "current_uuid")
        }
        override["current_uuid"] = open_version.get("uuid")
        return HookResult(proceed=True, reconciliation="forward", payload_override=override)

    # historical — insert as an already-closed version; current_uuid=None
    # so the currently-open row is NEVER touched (no UPDATE, ever).
    override = {key: value for key, value in payload.items() if key != "current_uuid"}
    override["current_uuid"] = None
    override["vigente_hasta"] = open_desde
    override["estado"] = "inactivo"
    return HookResult(proceed=True, reconciliation="historical", payload_override=override)


registry.register("identity_reconciler", identity_reconciler)

__all__ = ["identity_reconciler"]
