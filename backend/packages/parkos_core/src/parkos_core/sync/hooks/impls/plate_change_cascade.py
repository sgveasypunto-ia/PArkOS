"""hooks/impls/plate_change_cascade.py — ``PlateChangeCascade`` (T-PR5-014).

REQ-HOOK-005: ``hook_post_insert`` bound to ``vehiculos`` (re-targeted from
``hook_pre_insert`` + a ``reclamos`` row — see the module docstring's
"Superseded" note in ``specs/hooks.md`` REQ-HOOK-005: ``reclamos`` has no
vehicle-reclamable shape, so that original design was not storable).

``vehiculos.uuid`` identifies a *version* (bi-temporal close+insert), so an
ordinary plate edit (``close_and_insert(current_uuid=<old>, new_attrs=
{"placa": "NEW123", ...})``) mints a NEW version while every existing
``subscripcion_vehiculos`` row still points at the OLD one — the
subscription would silently keep covering the previous plate. This hook
closes those junction rows and inserts replacements pointing at the new
version, via ``cascade_rows`` the motor applies recursively through itself
(``motor/apply_row.py``'s ``hook_post_insert`` step, REQ-HOOK-003 step 4) —
so the cascade honors the exact same invariants (``SubscriptionLifecycle``,
audit logging) as any primary row.

**No plate change to cascade** (a brand-new ``vehiculos`` insert, no prior
``current_uuid``) -> no-op, empty ``cascade_rows``.

**Audit trail is ``log_transaccional``** — the SAME mechanism as every
other bi-temporal transition (``repo.versioned.close_and_insert`` always
writes one), never a ``reclamos`` row (there is no vehicle-reclamable
shape: ``reclamos.tipo_reclamable in {ingreso, salida, factura,
subscripcion}``).

**The ``vehiculos`` write itself always proceeds regardless of this hook's
outcome** — ``hook_post_insert`` runs strictly AFTER the repo call (see
``motor/apply_row.py``'s lifecycle order), so there is nothing left to
abort by this point; this hook only ever returns ``proceed=True``.
"""
from __future__ import annotations

from sqlalchemy import select

from .. import registry
from ..base import HookContext, HookResult


async def plate_change_cascade(ctx: HookContext) -> HookResult:
    """``hook_post_insert`` — REQ-HOOK-005 junction-row cascade."""
    from ....models.V.subscripcion_vehiculos import SubscripcionVehiculos

    old_uuid = ctx.payload.get("current_uuid")
    if old_uuid is None:
        # Brand-new vehiculos row — no prior version, nothing to cascade.
        return HookResult(proceed=True)

    new_uuid = ctx.row_uuid or ctx.payload.get("uuid")
    if new_uuid is None:
        # Defensive — should not happen (the repo call always yields a
        # uuid, either server-generated or carried in the payload).
        return HookResult(proceed=True)

    open_junctions = (
        await ctx.session.execute(
            select(SubscripcionVehiculos).where(
                SubscripcionVehiculos.uuid_vehiculo == old_uuid,
                SubscripcionVehiculos.vigente_hasta.is_(None),
            )
        )
    ).scalars().all()

    cascade_rows = [
        (
            "subscripcion_vehiculos",
            {
                "current_uuid": row.uuid,
                "uuid_subscripcion_cliente": row.uuid_subscripcion_cliente,
                "uuid_vehiculo": new_uuid,
                # Preserve the lifecycle state as-is — this is a re-target,
                # not a lifecycle transition. SubscriptionLifecycle treats
                # a same-state arrival as always legal (T-PR5-012).
                "estado": row.estado,
            },
        )
        for row in open_junctions
    ]

    return HookResult(proceed=True, cascade_rows=cascade_rows)


registry.register("plate_change_cascade", plate_change_cascade)

__all__ = ["plate_change_cascade"]
