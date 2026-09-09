"""motor/broadcast_resolver.py — ``broadcast_policy`` dispatch (T-PR12-003).

REQ-MOT-014, REQ-MOT-016 (design.md §3, D5-rev, D19, §16 Q1). Resolves which
branch(es) a ``cloud_to_branch``/``bidirectional`` catalog row targets:

  - ``single_branch``     — the payload's own ``uuid_sucursal`` (or, for an
                             entry with ``has_uuid_sucursal=False`` whose row
                             IS the branch identity, e.g. ``sucursal`` itself,
                             the row's own ``uuid``).
  - ``all_branches``       — every currently-active branch
                             (:func:`parkos_core.sync.auto_discovery.
                             discover_active_branches`).
  - ``all_branches_with_override`` (D19) — a ``NULL`` ``uuid_sucursal`` row is
                             the global default (targets every branch); a
                             non-``NULL`` row overrides for exactly that one
                             branch.
  - ``subscription``       (§16 Q1) — a subscription is honored only at the
                             branch that sold it: the row's own
                             ``uuid_sucursal`` when the entry carries one
                             (``subscripciones_cliente``), or — for an entry
                             that doesn't (``subscripcion_vehiculos``,
                             REQ-CAT-017) — transitively via its
                             ``depends_on`` parent's ``uuid_sucursal``.
                             **Never** falls back to ``all_branches``: an
                             unresolvable subscription scope is a caller bug,
                             raised loudly (:class:`BroadcastPolicyError`),
                             not silently broadcast everywhere.

**Never a second query (design.md §3 module docstring).** The transitive
``subscription`` case accepts an optional ``parent_local`` — the SAME parent
row data ``hook_validate_parent`` already fetched (via
:class:`~parkos_core.sync.hooks.base.HookContext.parent_local`) to validate
the declared ``depends_on`` dependency exists — so this resolver contributes
**zero** additional queries when the caller supplies it. When it is not
supplied (e.g. a caller resolving broadcast scope independently of an
``apply_row`` call), this module falls back to exactly **one** scalar SELECT
for the parent's ``uuid_sucursal`` column — never a second query on top of
that (e.g. it never ALSO re-validates the parent exists, or looks up the
branch row itself just to confirm it — the caller's ``depends_on``
validation already owns that).
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auto_discovery import BranchCache, discover_active_branches
from ..catalog.schema import SyncCatalogEntry

# Entry name -> (fk_column_on_own_payload, parent_catalog_entry_name) for a
# "subscription"-policy entry whose OWN payload carries no ``uuid_sucursal``
# (``has_uuid_sucursal=False``) and must resolve its owning branch
# transitively through a declared ``depends_on`` parent (REQ-CAT-017).
# Single source of truth for this specific mapping — SYNC_CATALOG's own
# ``depends_on`` already names ``subscripciones_cliente`` as a parent of
# ``subscripcion_vehiculos``; this table only pins WHICH parent carries the
# scope-defining ``uuid_sucursal`` (a subscription's OTHER declared parent,
# ``vehiculos``, does not).
_TRANSITIVE_SUBSCRIPTION_PARENT: dict[str, tuple[str, str]] = {
    "subscripcion_vehiculos": ("uuid_subscripcion_cliente", "subscripciones_cliente"),
}


class BroadcastPolicyError(Exception):
    """Raised when a broadcast target cannot be resolved.

    Covers: ``broadcast_policy=None`` (no broadcast scope — single
    destination, cloud; never call this resolver for it), a
    ``single_branch``/``subscription`` payload missing the field it needs, an
    unregistered transitive-parent mapping, or a parent row with no
    ``uuid_sucursal``. Never silently falls back to ``all_branches``.
    """


@dataclass(frozen=True)
class BroadcastTargets:
    """The resolved fan-out scope for one row.

    ``all_branches=True`` means "every currently-active branch" — the
    concrete list is resolved eagerly into ``branch_uuids`` so callers never
    need a second round-trip to enumerate them.
    """

    all_branches: bool
    branch_uuids: tuple[uuid_lib.UUID, ...] = ()


async def _resolve_all_branches(
    session: AsyncSession, *, branch_cache: BranchCache | None
) -> BroadcastTargets:
    if branch_cache is not None:
        endpoints = await branch_cache.get(session)
    else:
        endpoints = await discover_active_branches(session)
    return BroadcastTargets(
        all_branches=True,
        branch_uuids=tuple(e.uuid_sucursal for e in endpoints),
    )


async def _fetch_parent_uuid_sucursal(
    session: AsyncSession,
    *,
    parent_table: str,
    parent_uuid: uuid_lib.UUID,
) -> uuid_lib.UUID | None:
    """The ONE fallback query when the caller supplies no ``parent_local``.

    A single scalar SELECT — never a second query on top of it (no
    re-validation of the parent's existence, no separate branch-row lookup).
    """
    # Lazy import — avoids a module-load-time circular between
    # motor/broadcast_resolver.py and catalog/sync_catalog.py (same
    # reasoning as apply_row.py's own cascade_rows lookup).
    from ..catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    parent_spec = SYNC_CATALOG_BY_NAME[parent_table]
    column = parent_spec.model_cls.uuid_sucursal
    pk_column = parent_spec.model_cls.uuid
    stmt = select(column).where(pk_column == parent_uuid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def resolve_broadcast_targets(
    session: AsyncSession,
    spec: SyncCatalogEntry,
    payload: dict[str, Any],
    *,
    parent_local: dict[str, Any] | None = None,
    branch_cache: BranchCache | None = None,
) -> BroadcastTargets:
    """Resolve which branch(es) ``payload`` (a ``spec``-shaped row) targets.

    Args:
        session: Active ``AsyncSession`` — only touched for ``all_branches``
            enumeration or the ``subscription`` fallback query.
        spec: The row's catalog entry (reads ``broadcast_policy`` +
            ``has_uuid_sucursal``).
        payload: The row's business attributes (``apply_row``'s convention).
        parent_local: The already-validated ``depends_on`` parent's data
            (design.md §3's "never a second query" — reuse, don't re-fetch).
        branch_cache: Optional :class:`BranchCache` for ``all_branches``/
            ``all_branches_with_override`` enumeration; falls back to a
            fresh :func:`discover_active_branches` call when omitted.

    Returns:
        :class:`BroadcastTargets`.

    Raises:
        BroadcastPolicyError: unresolvable scope (see the class docstring).
    """
    policy = spec.broadcast_policy

    if policy is None:
        raise BroadcastPolicyError(
            f"{spec.name}: broadcast_policy=None has no broadcast scope (single "
            "destination is the cloud) — never call resolve_broadcast_targets for it"
        )

    if policy == "all_branches":
        return await _resolve_all_branches(session, branch_cache=branch_cache)

    if policy == "all_branches_with_override":
        override = payload.get("uuid_sucursal")
        if override is None:
            return await _resolve_all_branches(session, branch_cache=branch_cache)
        return BroadcastTargets(all_branches=False, branch_uuids=(override,))

    if policy == "single_branch":
        target = payload.get("uuid_sucursal") if spec.has_uuid_sucursal else payload.get("uuid")
        if target is None:
            raise BroadcastPolicyError(
                f"{spec.name}: single_branch broadcast_policy requires a resolvable "
                "branch uuid in the payload"
            )
        return BroadcastTargets(all_branches=False, branch_uuids=(target,))

    if policy == "subscription":
        if spec.has_uuid_sucursal:
            target = payload.get("uuid_sucursal")
            if target is None:
                raise BroadcastPolicyError(
                    f"{spec.name}: subscription broadcast_policy requires uuid_sucursal "
                    "in the payload"
                )
            return BroadcastTargets(all_branches=False, branch_uuids=(target,))

        # Transitive resolution (REQ-CAT-017) — e.g. subscripcion_vehiculos.
        if parent_local is not None and parent_local.get("uuid_sucursal") is not None:
            # Already-validated parent — NEVER a second query.
            return BroadcastTargets(
                all_branches=False, branch_uuids=(parent_local["uuid_sucursal"],)
            )

        mapping = _TRANSITIVE_SUBSCRIPTION_PARENT.get(spec.name)
        if mapping is None:
            raise BroadcastPolicyError(
                f"{spec.name}: subscription broadcast_policy with has_uuid_sucursal=False "
                "has no registered transitive-parent mapping — never falls back to "
                "all_branches"
            )
        fk_column, parent_table = mapping
        parent_uuid = payload.get(fk_column)
        if parent_uuid is None:
            raise BroadcastPolicyError(
                f"{spec.name}: payload is missing {fk_column!r}, needed to resolve the "
                "subscription's owning branch transitively"
            )
        # The ONE fallback query — no parent_local was supplied.
        uuid_sucursal = await _fetch_parent_uuid_sucursal(
            session, parent_table=parent_table, parent_uuid=parent_uuid
        )
        if uuid_sucursal is None:
            raise BroadcastPolicyError(
                f"{spec.name}: parent {parent_table} {parent_uuid} has no uuid_sucursal — "
                "cannot resolve subscription broadcast scope; never falls back to "
                "all_branches"
            )
        return BroadcastTargets(all_branches=False, branch_uuids=(uuid_sucursal,))

    raise BroadcastPolicyError(f"{spec.name}: unrecognized broadcast_policy {policy!r}")


__all__ = [
    "BroadcastPolicyError",
    "BroadcastTargets",
    "resolve_broadcast_targets",
]
