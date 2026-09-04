"""Unit tests for ``sync.conflict_resolver`` (PR9a, T-PR9-03).

Pins the per-class conflict policy at the helper boundary — the worker
bodies (PR9b) translate each :class:`ApplyOutcome` into a repo write
(``sync_conflict`` for conflicts, the appropriate append-only or
versioned repo for applies, retry for ``ERROR``).

Coverage:

- ``[A]`` append-only → always :class:`ApplyOutcome.APPLIED` (no
  conflict possible — ``sync_queue``, ``log_transaccional``, etc.).
- ``[L-E]`` lifecycle events → always :class:`ApplyOutcome.APPLIED`
  (``ingreso``, ``facturas``, ``factura_electronica``).
- ``[L-W]`` workflows → always :class:`ApplyOutcome.APPLIED``
  (``anulaciones``, ``reclamos``, ``alerta``, etc.).
- ``[L-S]`` sessions → :class:`ApplyOutcome.APPLIED` in the happy path
  (grace-window logic is owned by PR9b's worker).
- ``[V]`` (default fallback) → :class:`ApplyOutcome.APPLIED` on first
  write when no local seq exists.
- Missing/non-int ``seq`` → :class:`ApplyOutcome.ERROR` (caller
  retries).
- ``_read_local_seq`` stub returns ``None`` (no conflict possible).
- Constructor rejects negative ``jwt_overlap_hours``.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.sync.conflict_resolver import (
    APPEND_ONLY_TABLES,
    LIFECYCLE_EVENT_TABLES,
    SESSION_TABLES,
    WORKFLOW_TABLES,
    ApplyOutcome,
    ConflictResolver,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(tabla: str, *, seq: int = 1, uuid: str | None = None) -> dict:
    """Build a minimal pushed-row dict for the resolver."""
    return {
        "tabla": tabla,
        "uuid_registro": uuid or str(uuid_lib.uuid4()),
        "datos": {"seq": seq},
        "uuid_sucursal": str(uuid_lib.uuid4()),
        "timestamp_evento": "2026-01-01T00:00:00",
        "actor_uuid": str(uuid_lib.uuid4()),
    }


# ---------------------------------------------------------------------------
# Append-only table classes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tabla",
    sorted(APPEND_ONLY_TABLES | LIFECYCLE_EVENT_TABLES | WORKFLOW_TABLES),
)
@pytest.mark.asyncio
async def test_append_only_tables_always_apply(tabla: str) -> None:
    """``[A]``/``[L-E]``/``[L-W]`` → APPLIED unconditionally."""
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, _row(tabla))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.APPLIED


# ---------------------------------------------------------------------------
# Session tables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tabla", sorted(SESSION_TABLES))
@pytest.mark.asyncio
async def test_session_tables_apply_within_grace_window(tabla: str) -> None:
    """``[L-S]`` happy path → APPLIED (grace window allows overlap)."""
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, _row(tabla))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.APPLIED


# ---------------------------------------------------------------------------
# Versioned ([V]) default fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_versioned_table_default_apply_when_no_local_seq() -> None:
    """``[V]`` table with no local seq → APPLIED (new version)."""
    resolver = ConflictResolver()
    # A table that isn't in any of the explicit classes falls through
    # to the [V] default path; with the stub ``_read_local_seq``
    # returning ``None``, the incoming row is admitted.
    outcome = await resolver.apply_pushed_row(None, _row("empresa"))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.APPLIED


@pytest.mark.asyncio
async def test_versioned_table_rejects_lower_seq() -> None:
    """``[V]`` table with local seq higher than incoming → CONFLICT_V."""
    resolver = ConflictResolver()

    async def _fake_read_local_seq(
        session, tabla: str, uuid_registro
    ) -> int | None:
        # Local DB has already admitted a higher seq for this row.
        return 100

    resolver._read_local_seq = _fake_read_local_seq  # type: ignore[method-assign]
    outcome = await resolver.apply_pushed_row(None, _row("empresa", seq=5))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.CONFLICT_V


@pytest.mark.asyncio
async def test_versioned_table_accepts_higher_seq() -> None:
    """``[V]`` table with local seq lower than incoming → APPLIED."""
    resolver = ConflictResolver()

    async def _fake_read_local_seq(
        session, tabla: str, uuid_registro
    ) -> int | None:
        return 5

    resolver._read_local_seq = _fake_read_local_seq  # type: ignore[method-assign]
    outcome = await resolver.apply_pushed_row(None, _row("empresa", seq=100))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.APPLIED


# ---------------------------------------------------------------------------
# Error / malformed inputs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_tabla_returns_error() -> None:
    """Row with no ``tabla`` → ERROR."""
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, {"datos": {"seq": 1}})  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


@pytest.mark.asyncio
async def test_missing_uuid_registro_returns_error() -> None:
    """Row with no ``uuid_registro`` → ERROR."""
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, {"tabla": "sesion", "datos": {"seq": 1}})  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


@pytest.mark.asyncio
async def test_non_int_seq_returns_error() -> None:
    """Row with non-int ``seq`` → ERROR."""
    resolver = ConflictResolver()
    row = {
        "tabla": "sesion",
        "uuid_registro": str(uuid_lib.uuid4()),
        "datos": {"seq": "not-a-number"},
        "uuid_sucursal": str(uuid_lib.uuid4()),
        "timestamp_evento": "2026-01-01T00:00:00",
        "actor_uuid": str(uuid_lib.uuid4()),
    }
    outcome = await resolver.apply_pushed_row(None, row)  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


@pytest.mark.asyncio
async def test_missing_seq_returns_error() -> None:
    """Row with ``datos.seq`` missing → ERROR."""
    resolver = ConflictResolver()
    row = {
        "tabla": "sesion",
        "uuid_registro": str(uuid_lib.uuid4()),
        "datos": {},
        "uuid_sucursal": str(uuid_lib.uuid4()),
        "timestamp_evento": "2026-01-01T00:00:00",
        "actor_uuid": str(uuid_lib.uuid4()),
    }
    outcome = await resolver.apply_pushed_row(None, row)  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


@pytest.mark.asyncio
async def test_negative_seq_returns_error() -> None:
    """Row with ``seq < 0`` → ERROR (invalid format)."""
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, _row("sesion", seq=-1))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


@pytest.mark.asyncio
async def test_db_failure_returns_error() -> None:
    """DB exception in ``_read_local_seq`` → ERROR (caller retries)."""
    from sqlalchemy.exc import SQLAlchemyError

    resolver = ConflictResolver()

    async def _boom(session, tabla: str, uuid_registro):
        raise SQLAlchemyError("simulated driver failure")

    resolver._read_local_seq = _boom  # type: ignore[method-assign]
    outcome = await resolver.apply_pushed_row(None, _row("empresa", seq=5))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_constructor_rejects_negative_grace_window() -> None:
    """``jwt_overlap_hours`` must be >= 0 (grace window can't be negative)."""
    with pytest.raises(ValueError, match="jwt_overlap_hours"):
        ConflictResolver(jwt_overlap_hours=-1)


def test_default_grace_window_is_24h() -> None:
    """Default ``jwt_overlap_hours`` matches spec §21.10 (24h)."""
    resolver = ConflictResolver()
    assert resolver.jwt_overlap_hours == 24


# ---------------------------------------------------------------------------
# Stub _read_local_seq
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_read_local_seq_returns_none() -> None:
    """The default ``_read_local_seq`` stub returns ``None``.

    PR9b's worker overrides this with the concrete per-destination-table
    lookup; the default keeps the helper table-class agnostic.
    """
    resolver = ConflictResolver()
    result = await resolver._read_local_seq(None, "empresa", str(uuid_lib.uuid4()))  # type: ignore[arg-type]
    assert result is None
