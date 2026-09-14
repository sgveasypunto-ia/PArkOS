"""hooks/impls/subscription_lifecycle.py — ``SubscriptionLifecycle`` (T-PR5-012).

REQ-HOOK-006: ``hook_pre_insert`` bound to ``subscripcion_vehiculos``.
Validates two independent things before the motor is allowed to persist an
arriving row, both mapped by ``motor/apply_row.py`` to the SAME outcome —
``ApplyResult(status=CONFLICT, reason="illegal_state_transition")`` plus an
informational ``sync_conflict`` row (``politica="illegal_lifecycle"``),
written directly by this hook (it holds ``ctx.session``):

1. **Lifecycle transition.** ``estado`` (repurposing ``VersionedMixin``'s
   generic bi-temporal column to carry the subscription's own business
   state — ``activa`` | ``suspendida`` | ``cancelada``, not the generic
   ``activo``/``inactivo``) must move along a legal edge:

   | From | Allowed to |
   |---|---|
   | ``activa`` | ``suspendida``, ``cancelada`` |
   | ``suspendida`` | ``activa``, ``cancelada`` |
   | ``cancelada`` | (terminal — no outgoing transition) |

   A same-state transition (``activa`` -> ``activa``) is always legal — an
   idempotent continuation, not a transition. This is what lets
   ``PlateChangeCascade`` (``hook_post_insert`` on ``vehiculos``,
   T-PR5-014) close and re-insert a junction row that PRESERVES its
   current lifecycle state without tripping this validator: the cascade
   payload carries the row's own current ``estado`` forward unchanged.
   A row with no prior version (``current_uuid`` absent/``None``) has no
   transition to validate — a brand-new association is always legal on
   this axis.

2. **Vehicle-capacity** (only when the row is a genuinely NEW association
   — ``current_uuid`` absent/``None``, not a version-close/replace like the
   plate-change cascade uses): the resulting open-row count for
   ``uuid_subscripcion_cliente`` must not exceed the parent plan's
   ``cantidad_maxima_vehiculos`` (resolved through the already-validated
   ``depends_on`` parent — ``subscripciones_cliente.uuid_tipo_subscripcion``
   -> ``tipo_subscripciones.cantidad_maxima_vehiculos``). FK values here are
   snapshot pointers to a specific version (design's no-FK-rewriting rule),
   so both parent lookups are plain ``uuid ==`` reads, no "currently open"
   filter needed.

**2026-09-10 extension — ``current_uuid`` fallback via ``ctx.open_version``.**
``payload.get("current_uuid")`` is only ever populated by a LOCAL caller
that already knows the row it is closing — ``PlateChangeCascade`` (its own
query, same node, same transaction). A row arriving from REPLICATION
(real ``/sync/events`` push or ``/sync/pull``) carries none of that: the
wire payload is just ``to_jsonb(NEW)`` of the origin's newly-inserted row,
which has no ``current_uuid`` column. Without a fallback, every replicated
lifecycle change on this table looked like "no prior version" on the
receiving node — the SAME universal defect ``identity_lookup.py`` closes
for every other ``[V]`` table, just reachable here too because this table
keeps its own ``hook_pre_insert`` instead of ``identity_reconciler``.
``subscripcion_vehiculos`` now declares ``natural_key=
(uuid_subscripcion_cliente, uuid_vehiculo)`` (``entries/sync_entries_v.py``),
so ``SyncMotor.apply_row`` resolves ``ctx.open_version`` before calling this
hook exactly as it does for ``identity_reconciler``-driven tables. When
``payload`` carries no explicit ``current_uuid``, this hook now falls back
to ``ctx.open_version["uuid"]`` (and reads ``old_state`` straight off
``ctx.open_version`` instead of re-querying) and returns a
``payload_override`` so the eventual ``close_and_insert`` closes the RIGHT
local row instead of leaving it open forever. An explicit
``payload["current_uuid"]`` (the local-cascade case) always wins — this
fallback only fires when the wire payload didn't already say.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from .. import registry
from ..base import HookContext, HookResult

_LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "activa": frozenset({"suspendida", "cancelada"}),
    "suspendida": frozenset({"activa", "cancelada"}),
    "cancelada": frozenset(),  # terminal
}


async def _write_illegal_lifecycle_conflict(
    ctx: HookContext, *, uuid_registro: Any, reason: str
) -> None:
    from ....models.A.sync_conflict import SyncConflict

    now = datetime.now(UTC).replace(tzinfo=None)
    conflict = SyncConflict(
        uuid_sucursal=ctx.branch_uuid,
        tabla=ctx.spec.name,
        uuid_registro=uuid_registro,
        datos_local=None,
        datos_cloud={"estado_solicitado": ctx.payload.get("estado"), "motivo": reason},
        politica="illegal_lifecycle",
        resolucion=None,
        timestamp_evento=now,
    )
    ctx.session.add(conflict)


def _is_legal_transition(old_state: str | None, new_state: str | None) -> bool:
    if old_state is None:
        # No prior version — brand-new association, nothing to transition
        # from.
        return True
    if new_state == old_state:
        # Idempotent continuation (e.g. PlateChangeCascade re-inserting the
        # SAME lifecycle state under a new vehiculos version) — never a
        # transition, always legal.
        return True
    return new_state in _LEGAL_TRANSITIONS.get(old_state, frozenset())


async def subscription_lifecycle(ctx: HookContext) -> HookResult:
    """``hook_pre_insert`` — REQ-HOOK-006 lifecycle + capacity validation."""
    from ....models.V.subscripcion_vehiculos import SubscripcionVehiculos
    from ....models.V.subscripciones_cliente import SubscripcionesCliente
    from ....models.V.tipo_subscripciones import TipoSubscripciones

    payload = ctx.payload
    open_version = ctx.open_version
    explicit_current_uuid = payload.get("current_uuid")
    # Fallback for a REPLICATED row (see module docstring's 2026-09-10
    # extension) — the wire payload never carries current_uuid, but
    # SyncMotor.apply_row already resolved the locally-open row for this
    # natural key via identity_lookup.resolve_open_version.
    resolved_via_open_version = explicit_current_uuid is None and open_version is not None
    current_uuid = (
        explicit_current_uuid
        if explicit_current_uuid is not None
        else (open_version.get("uuid") if open_version is not None else None)
    )
    new_state = payload.get("estado")

    old_state: str | None = None
    if current_uuid is not None:
        if resolved_via_open_version and open_version is not None:
            # Already have the full row (open_version) — no need to
            # re-query for its estado. The redundant `open_version is not
            # None` check is implied by `resolved_via_open_version`'s own
            # definition above (mypy can't narrow across the boolean, so
            # this spells it out for it).
            old_state = open_version.get("estado")
        else:
            current_row = (
                await ctx.session.execute(
                    select(SubscripcionVehiculos).where(SubscripcionVehiculos.uuid == current_uuid)
                )
            ).scalar_one_or_none()
            old_state = current_row.estado if current_row is not None else None

    if not _is_legal_transition(old_state, new_state):
        await _write_illegal_lifecycle_conflict(
            ctx,
            uuid_registro=current_uuid,
            reason=f"illegal transition {old_state!r} -> {new_state!r}",
        )
        return HookResult(proceed=False)

    # Vehicle-capacity check — only for a genuinely NEW association.
    if current_uuid is None:
        uuid_subscripcion_cliente = payload.get("uuid_subscripcion_cliente")
        subscripcion = (
            await ctx.session.execute(
                select(SubscripcionesCliente).where(
                    SubscripcionesCliente.uuid == uuid_subscripcion_cliente
                )
            )
        ).scalar_one_or_none()

        cantidad_maxima: int | None = None
        if subscripcion is not None and subscripcion.uuid_tipo_subscripcion is not None:
            tipo = (
                await ctx.session.execute(
                    select(TipoSubscripciones).where(
                        TipoSubscripciones.uuid == subscripcion.uuid_tipo_subscripcion
                    )
                )
            ).scalar_one_or_none()
            cantidad_maxima = tipo.cantidad_maxima_vehiculos if tipo is not None else None

        if cantidad_maxima is not None:
            open_count = (
                await ctx.session.execute(
                    select(func.count()).where(
                        SubscripcionVehiculos.uuid_subscripcion_cliente
                        == uuid_subscripcion_cliente,
                        SubscripcionVehiculos.vigente_hasta.is_(None),
                    )
                )
            ).scalar_one()
            if open_count + 1 > cantidad_maxima:
                await _write_illegal_lifecycle_conflict(
                    ctx,
                    uuid_registro=uuid_subscripcion_cliente,
                    reason=(f"vehicle capacity exceeded: {open_count + 1} > {cantidad_maxima}"),
                )
                return HookResult(proceed=False)

    if resolved_via_open_version:
        override = {k: v for k, v in payload.items() if k != "current_uuid"}
        override["current_uuid"] = current_uuid
        return HookResult(proceed=True, payload_override=override)

    return HookResult(proceed=True)


registry.register("subscription_lifecycle", subscription_lifecycle)

__all__ = ["subscription_lifecycle"]
