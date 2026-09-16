"""sync/cutover/backfill.py — topological, paginated initial backfill (R-D8).

Req: R-D8 · Design: §7.1, §3 · T-PR12-001/002.

A freshly paired branch starts with an empty catalog set (design.md §7.1).
:func:`run_backfill` walks every ``cloud_to_branch``/``bidirectional``
``SYNC_CATALOG`` entry in **topological level order** (D18,
``catalog/dependency_graph.py``), paginated, applying each page through
:meth:`SyncMotor.apply_batch` (T-PR12-002) — the SAME catalog-driven apply
path the steady-state cutover uses (D12: one apply path, not a bespoke
backfill-only one).

``usuarios``/``permisos``/``permisos_usuario`` need no special-casing to
land at the root of the walk (R9, offline login available as early as
possible) — they declare ``depends_on=()`` (or depend only on other root
entries), so the generic topological order already puts them at/near level
0.

``catalog_backfill_complete{uuid_sucursal}`` (T-PR12-008) reaches 1 only
when **every** level applied with **zero** unresolved (buffered) parents —
a single buffered row anywhere in the whole walk keeps the gauge at 0, even
if every other level applied cleanly.

**Transport-agnostic by design.** ``design.md``'s module structure lists
``cutover/backfill.py`` as a standalone module — no new/modified
``sync_router.py`` endpoint is named anywhere in ``tasks.md``'s PR12 file
list, and design.md never pins down a concrete wire shape for "paginated"
beyond that word. Inventing a new HTTP endpoint here would be scope creep
beyond the explicit PR12 file list (and this project's own rule against
adding endpoints as a test shortcut) — so this module accepts an injected
:data:`FetchPage` callable instead of hardcoding a transport. The concrete
production implementation (an HTTP client hitting the cloud's bulk-export
surface) is a **documented, deliberately out-of-scope** follow-up, the same
kind of carve-out already established for
``motor/dependency_buffer.py``'s ``ValidateParentChain`` gap or
``check_drain.py``'s CI-wiring note. ``jobs/sync_sucursal.py`` wires
whatever concrete :data:`FetchPage` a follow-up PR builds when one is
configured; this module is fully unit/integration-testable today with a
fake fetcher (see ``tests/integration/test_pairing_flow.py``).
"""

from __future__ import annotations

import uuid as uuid_lib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...runtime import engine_flag
from ..catalog.dependency_graph import topological_level
from ..catalog.schema import SyncCatalogEntry
from ..catalog.sync_catalog import SYNC_CATALOG
from ..motor import apply_guard
from ..motor.sync_motor import SyncMotor
from ..observability.metrics import catalog_backfill_complete

#: Directions a freshly-paired branch must backfill (R-D8). ``branch_to_
#: cloud``-only entries never appear here — the branch is their origin, not
#: their destination.
_BACKFILL_DIRECTIONS: frozenset[str] = frozenset({"cloud_to_branch", "bidirectional"})

DEFAULT_PAGE_SIZE = 100


@dataclass(frozen=True)
class BackfillPage:
    """One page of rows for a single catalog table.

    ``rows`` are raw business-attribute dicts (``apply_row``'s payload
    convention) — the caller pairs each with its own ``SyncCatalogEntry``,
    not this module.
    """

    rows: tuple[dict[str, Any], ...]
    next_cursor: str | None
    has_more: bool


#: ``fetch_page(tabla, cursor, limit) -> BackfillPage`` — one table, one
#: page. See the module docstring's "Transport-agnostic by design" note.
FetchPage = Callable[[str, str | None, int], Awaitable[BackfillPage]]


@dataclass
class BackfillResult:
    """Outcome of one :func:`run_backfill` call."""

    applied: int = 0
    buffered: int = 0
    levels_completed: list[int] = field(default_factory=list)
    complete: bool = False


def _backfill_entries(
    catalog: tuple[SyncCatalogEntry, ...] = SYNC_CATALOG,
) -> list[SyncCatalogEntry]:
    """Every entry a freshly-paired branch must backfill, ordered by
    topological level then name (stable tie-break, ADR-003 Part 1 / R12 —
    priority is only an intra-level FIFO concern elsewhere, never an
    ordering key here)."""
    entries = [e for e in catalog if e.direction in _BACKFILL_DIRECTIONS]
    return sorted(entries, key=lambda e: (topological_level(e.name), e.name))


async def run_backfill(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    fetch_page: FetchPage,
    actor_uuid: uuid_lib.UUID,
    motor: SyncMotor | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    catalog: tuple[SyncCatalogEntry, ...] = SYNC_CATALOG,
) -> BackfillResult:
    """Backfill every ``cloud_to_branch``/``bidirectional`` entry, one
    topological level at a time, paginated (R-D8, design.md §7.1).

    Args:
        session: Active branch ``AsyncSession`` (caller commits).
        uuid_sucursal: The freshly-paired branch — only used for the
            ``catalog_backfill_complete`` gauge's label.
        fetch_page: Table-scoped, paginated data source (see
            :data:`FetchPage`).
        actor_uuid: Forwarded to every ``apply_batch`` call.
        motor: Optional pre-built :class:`SyncMotor` (tests inject a stub);
            defaults to one built with ``engine_flag.get_engine()``.
        page_size: Rows requested per :data:`FetchPage` call.
        catalog: Override the entries walked (tests use a small fixture
            catalog instead of the real 46-entry one).

    Returns:
        :class:`BackfillResult`. ``complete=True`` iff every level applied
        with zero buffered rows.
    """
    entries = _backfill_entries(catalog)
    active_motor = motor if motor is not None else SyncMotor(engine=engine_flag.get_engine())

    # Explicit 0 up front — a concurrent reader (e.g. the stage-4 gate) must
    # never observe a stale 1 from a PRIOR run while this one is mid-flight.
    catalog_backfill_complete.labels(uuid_sucursal=str(uuid_sucursal)).set(0)

    result = BackfillResult()
    any_buffered = False

    # NOT wired to the echo-amplification fix (migration
    # 0016_add_sync_apply_guard / sync.motor.apply_guard) yet. This function
    # currently has NO production caller (see this module's own "Transport-
    # agnostic by design" docstring note — every real call site today is a
    # test with a fake ``fetch_page``/``session=object()``), so the confirmed
    # real-Docker echo bug (post-PR14 closing exercise, real defect #3)
    # cannot manifest through this path today. It WOULD apply the same way
    # it does for every other real apply call site (``jobs/sync_cloud.py``,
    # ``jobs/sync_sucursal.py``, ``api/v1/sync_router.py::sync_events``) once
    # a concrete production ``FetchPage`` transport is wired here — a
    # ``bidirectional`` entry (e.g. ``log_transaccional``) backfilled onto a
    # freshly-paired branch would re-trigger that branch's own
    # ``fn_enqueue_sync`` exactly like the steady-state loops did. Flagged
    # here as a documented follow-up for whichever PR wires that transport
    # (wire ``sync.motor.apply_guard.enable_echo_suppression(session)`` once,
    # here, before the level loop, mirroring the other 4 call sites) —
    # deliberately NOT added now: doing so would also require rebuilding
    # ``tests/unit/test_catalog_backfill_gauge.py``'s ``session=object()``
    # stubs (that suite's own documented contract: the gauge transition rule
    # is a pure function of ``BatchResult``, independent of what the DB
    # does), a real design tradeoff outside this fix's scope.

    levels: dict[int, list[SyncCatalogEntry]] = {}
    for entry in entries:
        levels.setdefault(topological_level(entry.name), []).append(entry)

    for level in sorted(levels):
        level_buffered = 0
        for entry in levels[level]:
            cursor: str | None = None
            while True:
                page = await fetch_page(entry.name, cursor, page_size)
                if page.rows:
                    # Real defect confirmed via manual QA (2026-09-10):
                    # once ``permisos``' uuids became deterministic across
                    # nodes (migration 0019, fixing the SAME class of
                    # cross-node duplication this guard already closes for
                    # the two REAL apply loops — see
                    # jobs/sync_cloud.py::_apply_pending_batch_once and
                    # jobs/sync_sucursal.py::_pull_and_apply_catalog), a
                    # fresh branch's own independently-seeded canonical
                    # permisos rows collide (PK violation, not a silent
                    # duplicate) with cloud's identical rows during initial
                    # backfill. This function has no production caller yet
                    # (see this module's own docstring), but skipping a
                    # row whose uuid already exists here too keeps it
                    # consistent with the two real call sites instead of
                    # leaving a THIRD, differently-behaved apply path.
                    fresh_rows = []
                    for row in page.rows:
                        row_dict = dict(row)
                        if await apply_guard.row_already_present(
                            session, entry.model_cls, row_dict.get("uuid")
                        ):
                            continue
                        fresh_rows.append(row_dict)
                    resolved = [(entry, row_dict) for row_dict in fresh_rows]
                    if resolved:
                        batch_result = await active_motor.apply_batch(
                            session, resolved, actor_uuid=actor_uuid
                        )
                        result.applied += len(batch_result.applied)
                        level_buffered += len(batch_result.buffered)
                cursor = page.next_cursor
                if not page.has_more:
                    break
        result.buffered += level_buffered
        result.levels_completed.append(level)
        if level_buffered:
            any_buffered = True

    result.complete = not any_buffered
    catalog_backfill_complete.labels(uuid_sucursal=str(uuid_sucursal)).set(
        1 if result.complete else 0
    )
    return result


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "BackfillPage",
    "BackfillResult",
    "FetchPage",
    "run_backfill",
]
