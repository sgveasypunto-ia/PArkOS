"""catalog/schema.py — ``SyncCatalogEntry`` declarative schema (T-PR2-001).

REQ-CAT-001: the frozen dataclass every catalog entry (``SYNC_CATALOG``,
``LOCAL_ONLY_CATALOG``) is built from. This module declares the schema only
— it does not populate any catalog (see ``entries/sync_entries_*.py``,
``local_only_catalog.py``, ``out_of_catalog.py``).

**Fields removed by this amendment** (D1-rev, D5-rev, D14-rev): ``cloud_only``
(replaced by the ``role_required``/``originating_role`` pair — distinguishes
"may not exist here" from "is not authored here but is legitimately
present"), ``sync_back_event`` (the branch numbers ``factura_electronica``
locally; ``envio_dian`` is the ordinary return channel), ``direction_proposed``
(direction is ratified in this change, not deferred).

**Fields added**: ``depends_on``, ``parent_fk_column``, ``self_chain`` (D18);
``natural_key``, ``natural_key_normalizer`` (D17); ``originating_role``;
``snapshot_columns`` (D20); ``justification``; ``backoff_schedule``,
``max_retries``, ``on_exhaustion`` (T-PR9-005, design.md §2 Issue #9 —
per-entry override for the DIAN critical path).

**HookFn is intentionally loose here.** ``hooks/base.py::HookContext`` /
``HookResult`` ship in PR4 (design.md §3 Module Structure). PR2 only
*declares* the four hook slots on the schema — hook *implementations* land in
PR4/PR5/PR6. Tightening ``HookFn`` to the real ``HookContext``/``HookResult``
types is PR4's job, not PR2's; importing a not-yet-existing module here would
break every PR2 entry file.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy.orm import DeclarativeBase

# Loose hook-callable alias — see the module docstring's "HookFn" note.
HookFn = Callable[[Any], Awaitable[Any]]

AuditClass = Literal["V", "L_E", "L_W", "L_S", "A"]

SyncStrategy = Literal[
    "append",
    "manual",
    "grace_window",
    "never_propagated",
    "local_only",
    "is_sync_outbox",
]

Direction = Literal["cloud_to_branch", "branch_to_cloud", "bidirectional"]

BroadcastPolicy = Literal[
    "single_branch",
    "all_branches",
    "all_branches_with_override",
    "subscription",
]

ApplyStrategy = Literal[
    "close_and_insert",
    "record_event",
    "append_event",
    "append_transition",
    "session_cycle",
]

SeqStrategy = Literal[
    "seq_via_datos",
    "max_timestamp_evento",
    "max_created_at",
    "none",
]

RoleRequired = Literal["cloud", "branch", "both"]

# REQ-CAT-001 last bullet: ``broadcast_policy`` MUST NEVER receive a
# ``direction`` value — CI asserts the two enums are disjoint sets of
# string literals. Asserted once at import time (fast, no fixture needed);
# ``test_catalog_schema.py`` re-asserts this behaviorally.
_DIRECTION_VALUES: frozenset[str] = frozenset(
    {"cloud_to_branch", "branch_to_cloud", "bidirectional"}
)
_BROADCAST_POLICY_VALUES: frozenset[str] = frozenset(
    {"single_branch", "all_branches", "all_branches_with_override", "subscription"}
)
assert _DIRECTION_VALUES.isdisjoint(_BROADCAST_POLICY_VALUES), (
    "direction and broadcast_policy enums must stay disjoint string-literal sets"
)


class SyncCatalogEntrySchemaError(ValueError):
    """Raised by :meth:`SyncCatalogEntry.__post_init__` on an invalid entry."""


@dataclass(frozen=True)
class SyncCatalogEntry:
    """Declarative sync policy for one ``prod.*`` table (REQ-CAT-001).

    Frozen (immutable at runtime) so a catalog entry can never drift after
    import — mutating any field raises ``dataclasses.FrozenInstanceError``.
    """

    # --- Identity -----------------------------------------------------
    name: str
    model_cls: type[DeclarativeBase]
    audit_class: AuditClass

    # --- Policy (D5-rev, D8-rev, D14-rev) ------------------------------
    sync_strategy: SyncStrategy
    direction: Direction | None  # None iff sync_strategy == "never_propagated"
    broadcast_policy: BroadcastPolicy | None = "single_branch"

    # --- Apply ----------------------------------------------------------
    apply_strategy: ApplyStrategy | None = None

    # --- Dependency ordering (D18) --------------------------------------
    depends_on: tuple[str, ...] = ()
    parent_fk_column: str | None = None
    self_chain: bool = False

    # --- Sequence ---------------------------------------------------------
    has_uuid_sucursal: bool = False
    seq_strategy: SeqStrategy | None = None

    # --- Identity reconciliation (D17) -------------------------------------
    natural_key: tuple[str, ...] = ()
    natural_key_normalizer: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    # --- Hash chain -----------------------------------------------------
    hash_chain: bool = False
    verify_chain: bool = False

    # --- Role / scope -----------------------------------------------------
    role_required: RoleRequired = "both"
    originating_role: RoleRequired = "branch"

    # --- Snapshot immutability (D20) ---------------------------------------
    snapshot_columns: frozenset[str] | None = None

    # --- Hooks (per-table callable, four slots — §6 of design.md) -----------
    hook_pre_insert: HookFn | None = None
    hook_post_insert: HookFn | None = None
    hook_chain_extend: HookFn | None = None
    hook_validate_parent: HookFn | None = None

    # --- Operational --------------------------------------------------------
    is_sync_outbox: bool = False
    state_mutable_columns: frozenset[str] | None = None

    # --- Per-entry backoff override (T-PR9-005, design.md §2 Issue #9) -------
    # ``None`` on every entry except ``factura_electronica`` /
    # ``revocacion_factura`` (the DIAN critical path — ``dian/backoff.py::
    # DIAN_BACKOFF_SCHEDULE``, imported, never re-declared here). Passed
    # straight into ``repo/sync_queue.py::mark_failed`` as an override; a
    # ``None`` value means "use the general curve" (unchanged semantics).
    backoff_schedule: tuple[timedelta, ...] | None = None
    max_retries: int | None = None
    on_exhaustion: str | None = None

    # --- Metadata -------------------------------------------------------------
    justification: str | None = None
    priority: int = 1
    chain_priority: int = 0

    def __post_init__(self) -> None:
        if self.sync_strategy == "never_propagated":
            if self.direction is not None:
                raise SyncCatalogEntrySchemaError(
                    f"{self.name}: sync_strategy='never_propagated' requires direction=None, "
                    f"got {self.direction!r}"
                )
            if not self.justification:
                raise SyncCatalogEntrySchemaError(
                    f"{self.name}: sync_strategy='never_propagated' requires a non-empty "
                    "justification"
                )
        elif self.sync_strategy != "local_only" and self.direction is None:
            raise SyncCatalogEntrySchemaError(
                f"{self.name}: direction=None is only valid when "
                "sync_strategy='never_propagated' or 'local_only'"
            )

        tablename = getattr(self.model_cls, "__tablename__", None)
        if tablename != self.name:
            raise SyncCatalogEntrySchemaError(
                f"{self.name}: model_cls.__tablename__={tablename!r} does not match entry name"
            )

        if self.self_chain and not self.parent_fk_column:
            raise SyncCatalogEntrySchemaError(
                f"{self.name}: self_chain=True requires a non-empty parent_fk_column"
            )


__all__ = [
    "ApplyStrategy",
    "AuditClass",
    "BroadcastPolicy",
    "Direction",
    "HookFn",
    "RoleRequired",
    "SeqStrategy",
    "SyncCatalogEntry",
    "SyncCatalogEntrySchemaError",
    "SyncStrategy",
]
