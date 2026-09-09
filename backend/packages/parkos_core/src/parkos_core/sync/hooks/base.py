"""hooks/base.py — ``HookContext`` / ``HookResult`` (T-PR4-003).

REQ-HOOK-001 / REQ-HOOK-002: the two data contracts every hook callable
(``Callable[[HookContext], HookResult | Awaitable[HookResult]]``, see
``registry.py::HookFn``) receives and returns. ``HookContext`` is mutable
(``payload`` may be adjusted by ``hook_pre_insert``); ``HookResult`` is
frozen — a hook communicates its outcome by returning a new value, never by
mutating the context it received.

``spec`` is typed against ``catalog.schema.SyncCatalogEntry`` only under
``TYPE_CHECKING`` — importing it at runtime would create an import cycle
(``catalog/schema.py`` -> ... -> ``sync/hooks/base.py`` -> back to
``catalog/schema.py``), which does not exist today but is worth avoiding on
principle for a module every hook implementation imports. ``from __future__
import annotations`` (PEP 563) makes this safe: annotations are strings at
runtime, so mypy/pyright still resolve the real type while nothing is
actually imported until interpretation time.
"""
from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from ..catalog.schema import SyncCatalogEntry

ReconciliationKind = Literal["noop", "forward", "historical"]


@dataclass
class HookContext:
    """Per-invocation context passed to every hook callable (REQ-HOOK-001).

    ``chain_head`` is set for ``hook_chain_extend``; ``parent_local`` is set
    for ``hook_validate_parent``; ``open_version`` is set for
    ``natural_key`` specs (D17) so ``IdentityReconciler`` does not have to
    re-query the currently-open version.
    """

    spec: SyncCatalogEntry
    payload: dict[str, Any]
    session: AsyncSession
    actor_uuid: uuid_lib.UUID
    chain_head: bytes | None = None
    parent_local: dict[str, Any] | None = None
    open_version: dict[str, Any] | None = None
    branch_uuid: uuid_lib.UUID | None = None


@dataclass(frozen=True)
class HookResult:
    """Frozen outcome returned by every hook callable (REQ-HOOK-002).

    ``proceed=False`` aborts ``apply_row`` (illegal-transition style
    rejection); ``parent_valid=False`` (used only by ``hook_validate_parent``)
    short-circuits to ``ApplyResult(status=RETRY, reason="parent_missing")``
    instead. ``cascade_rows`` are ``(table_name, payload)`` pairs the motor
    applies through itself (recursively, via ``apply_row``) in the same
    transaction — e.g. ``PlateChangeCascade``'s closed/reopened
    ``subscripcion_vehiculos`` rows.
    """

    proceed: bool = True
    payload_override: dict[str, Any] | None = None
    chain_extension: tuple[bytes, bytes] | None = None
    parent_valid: bool = True
    reconciliation: ReconciliationKind | None = None
    cascade_rows: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


__all__ = ["HookContext", "HookResult", "ReconciliationKind"]
