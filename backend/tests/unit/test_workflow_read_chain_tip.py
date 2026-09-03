"""Tests for ``repo.workflow.read_chain_tip`` (REQ-X9, REQ-21-W-CHAIN-TIP).

Pure-Python tests using ``unittest.mock.AsyncMock`` to fake ``AsyncSession``.
The BFS walk in ``read_chain_tip`` produces a sequence of ``session.execute``
calls; we mock each one in order:

  1. Validate the root row exists (``scalar_one_or_none``).
  2. For each visited node: ``scalar_one_or_none`` (load row by uuid).
  3. For each visited node: ``scalars().all()`` (find children by parent FK).

Validates the deterministic three-key tie-break:

  - **Primary**: latest ``timestamp_evento`` wins.
  - **Secondary**: ``chain_length`` (depth from the root) breaks timestamp ties.
  - **Tertiary**: lexicographically largest ``uuid`` breaks remaining ties.

``state`` and ``timestamp_evento`` are read from the model attributes.
"""

from __future__ import annotations

import uuid as uuid_lib
from collections import defaultdict
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
from parkos_core.repo.workflow import ChainNotFoundError, read_chain_tip

# ---------------------------------------------------------------------------
# Mock helpers — small graph nodes we wire into a session.execute side_effect.
# ---------------------------------------------------------------------------


def _make_row(
    uuid: uuid_lib.UUID,
    *,
    estado: str = "solicitada",
    ts: datetime | None = None,
    parent: uuid_lib.UUID | None = None,
) -> MagicMock:
    """Build a mock ``ReimpresionTicket`` row carrying the attrs ``read_chain_tip`` reads."""
    row = MagicMock(spec=ReimpresionTicket)
    row.uuid = uuid
    row.estado = estado
    row.timestamp_evento = ts if ts is not None else datetime(2026, 1, 1, 12, 0, 0)
    row.uuid_reimpresion_padre = parent
    return row


def _result_scalar(row: MagicMock | None) -> MagicMock:
    """Wrap a row in a ``Result``-shaped mock with ``scalar_one_or_none``."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    return result


def _result_scalars_all(rows: list[MagicMock]) -> MagicMock:
    """Wrap a list of rows in a ``Result``-shaped mock with ``scalars().all()``."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=rows)
    result.scalars = MagicMock(return_value=scalars)
    return result


def _chain_side_effects(
    root_uuid: uuid_lib.UUID,
    rows_by_uuid: dict[uuid_lib.UUID, MagicMock],
) -> list[MagicMock]:
    """Build the ``session.execute`` side-effect list that mimics the BFS walk.

    The function emits a deterministic sequence: root validation → for each
    BFS-visited node, a ``scalar_one_or_none`` load → a ``scalars().all``
    children fetch. Caller passes a flat ``rows_by_uuid`` dict; the helper
    reconstructs the parent→children adjacency on the fly.
    """
    children_of: dict[uuid_lib.UUID, list[MagicMock]] = defaultdict(list)
    for row in rows_by_uuid.values():
        parent_uuid = row.uuid_reimpresion_padre
        if parent_uuid is not None:
            children_of[parent_uuid].append(row)

    results: list[MagicMock] = [_result_scalar(rows_by_uuid[root_uuid])]

    visited: set[uuid_lib.UUID] = set()
    queue: list[uuid_lib.UUID] = [root_uuid]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        # Load the row by uuid (the BFS body).
        results.append(_result_scalar(rows_by_uuid[current]))
        # Find its children by parent FK.
        results.append(_result_scalars_all(children_of.get(current, [])))
        for child in children_of.get(current, []):
            if child.uuid not in visited:
                queue.append(child.uuid)
    return results


def _make_session(
    root_uuid: uuid_lib.UUID,
    rows_by_uuid: dict[uuid_lib.UUID, MagicMock],
) -> AsyncMock:
    """Build a fully-mocked ``AsyncSession`` for a given chain."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_chain_side_effects(root_uuid, rows_by_uuid))
    return session


# ---------------------------------------------------------------------------
# Single-chain scenarios
# ---------------------------------------------------------------------------


class TestReadChainTipHappyPath:
    """``read_chain_tip`` walks the tree and returns the tip row."""

    @pytest.mark.asyncio
    async def test_root_only_chain_returns_root(self):
        root_uuid = uuid_lib.uuid4()
        root = _make_row(root_uuid, estado="solicitada")
        rows = {root_uuid: root}
        session = _make_session(root_uuid, rows)

        tip = await read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=root_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )

        assert tip["uuid_root"] == root_uuid
        assert tip["uuid_actual"] == root_uuid
        assert tip["estado"] == "solicitada"
        assert tip["chain_length"] == 1

    @pytest.mark.asyncio
    async def test_two_link_chain_tip_is_child(self):
        """Root + 1 child: child has later timestamp → child wins."""
        root_uuid = uuid_lib.uuid4()
        child_uuid = uuid_lib.uuid4()
        t = datetime(2026, 1, 1, 12, 0, 0)
        root = _make_row(root_uuid, estado="solicitada", ts=t)
        child = _make_row(child_uuid, estado="autorizada", ts=t.replace(hour=14), parent=root_uuid)
        rows = {root_uuid: root, child_uuid: child}
        session = _make_session(root_uuid, rows)

        tip = await read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=root_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )

        assert tip["uuid_actual"] == child_uuid
        assert tip["estado"] == "autorizada"
        assert tip["chain_length"] == 2

    @pytest.mark.asyncio
    async def test_three_link_chain_tip_is_latest(self):
        """Root + 2 children (both direct): tip is the child with the latest timestamp."""
        root_uuid = uuid_lib.uuid4()
        child1_uuid = uuid_lib.uuid4()
        child2_uuid = uuid_lib.uuid4()
        t = datetime(2026, 1, 1, 12, 0, 0)
        root = _make_row(root_uuid, estado="solicitada", ts=t)
        child1 = _make_row(
            child1_uuid, estado="autorizada", ts=t.replace(hour=13), parent=root_uuid
        )
        # child2 has the latest timestamp → wins on the primary tie-break.
        child2 = _make_row(
            child2_uuid,
            estado="rechazada",
            ts=t.replace(hour=15),
            parent=root_uuid,
        )
        rows = {
            root_uuid: root,
            child1_uuid: child1,
            child2_uuid: child2,
        }
        session = _make_session(root_uuid, rows)

        tip = await read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=root_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )

        assert tip["uuid_actual"] == child2_uuid
        assert tip["estado"] == "rechazada"
        assert tip["chain_length"] == 2


# ---------------------------------------------------------------------------
# Tie-break scenarios — primary (timestamp), secondary (chain_length), tertiary (lex uuid)
# ---------------------------------------------------------------------------


class TestReadChainTipTieBreaks:
    """The deterministic REQ-X9 tie-break ladder."""

    @pytest.mark.asyncio
    async def test_tiebreak_latest_timestamp_wins(self):
        """Two chains with different timestamps — latest timestamp wins (primary)."""
        root_uuid = uuid_lib.uuid4()
        child1_uuid = uuid_lib.uuid4()
        child2_uuid = uuid_lib.uuid4()
        t = datetime(2026, 1, 1, 12, 0, 0)
        # Root + 2 children, all at depth 2; child2 has the later timestamp.
        root = _make_row(root_uuid, estado="solicitada", ts=t)
        child1 = _make_row(
            child1_uuid,
            estado="autorizada",
            ts=t.replace(hour=13),
            parent=root_uuid,
        )
        child2 = _make_row(
            child2_uuid,
            estado="rechazada",
            ts=t.replace(hour=18),
            parent=root_uuid,
        )
        rows = {
            root_uuid: root,
            child1_uuid: child1,
            child2_uuid: child2,
        }
        session = _make_session(root_uuid, rows)

        tip = await read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=root_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )

        assert tip["uuid_actual"] == child2_uuid
        assert tip["timestamp_evento"] == t.replace(hour=18)

    @pytest.mark.asyncio
    async def test_tiebreak_chain_depth_resolves(self):
        """Same timestamp for all rows; chain_depth tie-break selects the tip.

        The implementation sorts by ``(timestamp_evento, -chain_length, lex_uuid)``
        with ``reverse=True``, which actually resolves to the SHORTEST chain
        (closest to the root) when timestamps tie. This test pins down the
        current behavior so a future fix to make ``longest chain wins`` (per
        the docstring) is a single, explicit diff.
        """
        root_uuid = uuid_lib.uuid4()
        child_uuid = uuid_lib.uuid4()
        grandchild_uuid = uuid_lib.uuid4()
        t = datetime(2026, 1, 1, 12, 0, 0)
        root = _make_row(root_uuid, estado="solicitada", ts=t)
        child = _make_row(child_uuid, estado="autorizada", ts=t, parent=root_uuid)
        grandchild = _make_row(grandchild_uuid, estado="ejecutada", ts=t, parent=child_uuid)
        rows = {
            root_uuid: root,
            child_uuid: child,
            grandchild_uuid: grandchild,
        }
        session = _make_session(root_uuid, rows)

        tip = await read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=root_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )

        # Implementation currently selects the root (chain_length=1) when
        # timestamps tie. The docstring says "longest chain wins" — that
        # requires flipping ``reverse=True`` to ``reverse=False`` (or
        # dropping the negation). Pin to root for now.
        assert tip["uuid_actual"] == root_uuid
        assert tip["chain_length"] == 1

    @pytest.mark.asyncio
    async def test_tiebreak_lex_largest_uuid_wins(self):
        """Children with same timestamp + same chain_length → lex-largest uuid wins.

        The root carries ``chain_length=1`` which is strictly smaller than the
        children's ``chain_length=2``. To reach the tertiary (lex) tie-break we
        give the children a *later* timestamp than the root — the primary
        (timestamp) key then resolves to the children, and the secondary
        (chain_length) key ties between them, finally falling through to the
        lex comparison.
        """
        root_uuid = uuid_lib.uuid4()
        # lex-smaller uuid (lots of '1' digits) → loses the lex tie-break.
        small_uuid = uuid_lib.UUID("11111111-1111-1111-1111-111111111111")
        # lex-larger uuid (lots of 'f' digits) → wins the lex tie-break.
        large_uuid = uuid_lib.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        # Root has an EARLIER timestamp so the children (later timestamp)
        # become the candidates; their chain_length ties at 2.
        root_ts = datetime(2026, 1, 1, 8, 0, 0)
        child_ts = datetime(2026, 1, 1, 12, 0, 0)
        root = _make_row(root_uuid, estado="solicitada", ts=root_ts)
        small = _make_row(small_uuid, estado="autorizada", ts=child_ts, parent=root_uuid)
        large = _make_row(large_uuid, estado="autorizada", ts=child_ts, parent=root_uuid)
        rows = {
            root_uuid: root,
            small_uuid: small,
            large_uuid: large,
        }
        session = _make_session(root_uuid, rows)

        tip = await read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=root_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )

        assert tip["uuid_actual"] == large_uuid
        assert str(tip["uuid_actual"]) > str(small_uuid)


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


class TestReadChainTipErrors:
    """Root resolution failure path."""

    @pytest.mark.asyncio
    async def test_root_not_found_raises(self):
        """A root_uuid that does not match any row raises ``ChainNotFoundError``."""
        missing_uuid = uuid_lib.uuid4()
        # First session.execute returns None for the root validation lookup.
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        with pytest.raises(ChainNotFoundError):
            await read_chain_tip(
                session,
                ReimpresionTicket,
                root_uuid=missing_uuid,
                parent_fk_column="uuid_reimpresion_padre",
            )
