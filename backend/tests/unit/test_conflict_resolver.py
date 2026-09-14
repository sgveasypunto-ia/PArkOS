"""Unit tests for ``sync.conflict_resolver`` — thin shim (T-PR7-004).

**Rewritten in PR7.** The PR9a-era version of this file pinned the 4
hardcoded ``frozenset`` constants (``APPEND_ONLY_TABLES``,
``LIFECYCLE_EVENT_TABLES``, ``WORKFLOW_TABLES``, ``SESSION_TABLES``) and the
permanent-``None`` ``_read_local_seq`` stub — both removed by T-PR7-004
(the decision now lives in ``motor/resolve_conflict.py``, reached via
``SyncMotor.resolve_conflict``). This file now pins the SHIM boundary only:
input validation the shim itself still owns (``tabla``/``uuid_registro``
presence and format), the catalog lookup, and the
``ConflictResolution.status`` -> ``ApplyOutcome`` mapping. The actual
per-audit-class POLICY is covered by ``test_resolve_conflict.py``.

Coverage:

- Malformed input (missing/invalid ``tabla``/``uuid_registro``) -> ``ERROR``,
  still validated at the shim boundary (moved earlier than before: this
  now happens BEFORE any catalog lookup or DB access).
- An out-of-catalog ``tabla`` -> ``APPLIED`` (no conflict possible outside
  the catalog).
- ``[A]``/``[L-E]``/``[L-W]`` -> ``APPLIED`` (no concrete
  ``ValidateParentChain`` hook wired yet — see
  ``motor/resolve_conflict.py``'s docstring).
- ``[L-S]`` happy path -> ``APPLIED`` (grace-window logic, REQ-MOT-013).
- ``[V]`` (default fallback, e.g. ``documentos`` — one of the 2 ``[V]``
  entries the ER model itself declares no natural key for) -> ``APPLIED``
  on first write
  when no local seq exists, ``CONFLICT_V`` on a stale/equal remote seq
  (now DB-backed, via the real ``ReadLocalSeq`` — no more monkey-patching
  a removed ``_read_local_seq`` method).
- DB failure during resolution -> ``ERROR`` (caller retries).
- Constructor rejects negative ``jwt_overlap_hours``; default is 24h.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import pytest
from parkos_core.models.V.documentos import Documentos
from parkos_core.sync.conflict_resolver import ApplyOutcome, ConflictResolver

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(tabla: str, *, uuid: str | None = None, timestamp_evento: datetime | None = None) -> dict:
    """Build a minimal pushed-row dict for the resolver.

    ``timestamp_evento`` is a real ``datetime`` (not an ISO string) — real
    callers (``api/v1/sync_router.py``) assemble this row with an
    already-parsed ``datetime`` value, never a wire-format string.
    """
    return {
        "tabla": tabla,
        "uuid_registro": uuid or str(uuid_lib.uuid4()),
        "datos": {},
        "uuid_sucursal": None,
        "timestamp_evento": timestamp_evento or datetime(2026, 1, 1),
        "actor_uuid": str(uuid_lib.uuid4()),
    }


# ---------------------------------------------------------------------------
# Append-only / lifecycle / workflow classes — no concrete parent-validation
# hook wired yet, so the registry no-op default resolves APPLIED (documented
# in motor/resolve_conflict.py's docstring — not a regression PR7 introduces).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tabla", ["salidas", "caja", "arqueo"])
async def test_append_only_tables_apply(tabla: str) -> None:
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, _row(tabla))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.APPLIED


@pytest.mark.parametrize("tabla", ["ingreso", "facturas"])
async def test_lifecycle_event_tables_apply(tabla: str) -> None:
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, _row(tabla))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.APPLIED


@pytest.mark.parametrize("tabla", ["anulaciones", "reclamos", "alerta"])
async def test_workflow_tables_apply(tabla: str) -> None:
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, _row(tabla))  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.APPLIED


# ---------------------------------------------------------------------------
# Session tables
# ---------------------------------------------------------------------------


async def test_session_table_applies_within_grace_window() -> None:
    """``[L-S]`` happy path -> APPLIED (recent timestamp_evento, REQ-MOT-013)."""
    resolver = ConflictResolver()
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    outcome = await resolver.apply_pushed_row(
        None,
        _row("login", timestamp_evento=recent),  # type: ignore[arg-type]
    )
    assert outcome == ApplyOutcome.APPLIED


async def test_session_table_conflict_ls_past_grace_window() -> None:
    """``[L-S]`` outside the grace window -> CONFLICT_LS."""
    resolver = ConflictResolver()
    stale = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=30)
    outcome = await resolver.apply_pushed_row(
        None,
        _row("login", timestamp_evento=stale),  # type: ignore[arg-type]
    )
    assert outcome == ApplyOutcome.CONFLICT_LS


# ---------------------------------------------------------------------------
# Versioned ([V]) default fallback — now DB-backed via the real ReadLocalSeq
# ---------------------------------------------------------------------------


async def test_versioned_table_default_apply_when_no_local_seq(pg_session) -> None:
    """``[V]`` table with no locally-known row -> APPLIED (new version)."""
    resolver = ConflictResolver()
    row = _row("documentos")
    row["datos"] = {"created_at": datetime.now(UTC).replace(tzinfo=None)}
    outcome = await resolver.apply_pushed_row(pg_session, row)
    assert outcome == ApplyOutcome.APPLIED


async def test_versioned_table_rejects_stale_seq(pg_session) -> None:
    """``[V]`` table where the local row is at least as new -> CONFLICT_V."""
    resolver = ConflictResolver()
    row_uuid = uuid_lib.uuid4()
    local_created = datetime(2026, 1, 1)
    pg_session.add(Documentos(uuid=row_uuid, created_at=local_created))
    await pg_session.flush()

    row = _row("documentos", uuid=str(row_uuid))
    row["datos"] = {"created_at": local_created}  # equal, not strictly newer
    outcome = await resolver.apply_pushed_row(pg_session, row)
    assert outcome == ApplyOutcome.CONFLICT_V


async def test_versioned_table_accepts_newer_seq(pg_session) -> None:
    """``[V]`` table where the remote row is strictly newer -> APPLIED."""
    resolver = ConflictResolver()
    row_uuid = uuid_lib.uuid4()
    local_created = datetime(2026, 1, 1)
    pg_session.add(Documentos(uuid=row_uuid, created_at=local_created))
    await pg_session.flush()

    row = _row("documentos", uuid=str(row_uuid))
    row["datos"] = {"created_at": local_created + timedelta(days=1)}
    outcome = await resolver.apply_pushed_row(pg_session, row)
    assert outcome == ApplyOutcome.APPLIED


# ---------------------------------------------------------------------------
# Error / malformed inputs
# ---------------------------------------------------------------------------


async def test_missing_tabla_returns_error() -> None:
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(None, {"datos": {}})  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


async def test_missing_uuid_registro_returns_error() -> None:
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(
        None,
        {"tabla": "sesion", "datos": {}},  # type: ignore[arg-type]
    )
    assert outcome == ApplyOutcome.ERROR


async def test_malformed_uuid_registro_returns_error() -> None:
    resolver = ConflictResolver()
    row = _row("sesion")
    row["uuid_registro"] = "not-a-uuid"
    outcome = await resolver.apply_pushed_row(None, row)  # type: ignore[arg-type]
    assert outcome == ApplyOutcome.ERROR


async def test_out_of_catalog_table_applies_unconditionally() -> None:
    """A table outside SYNC_CATALOG (e.g. sync-infra itself) -> APPLIED."""
    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(
        None,
        _row("sync_queue"),  # type: ignore[arg-type]
    )
    assert outcome == ApplyOutcome.APPLIED


async def test_db_failure_returns_error(pg_session, monkeypatch) -> None:
    """A DB-layer exception during resolution -> ERROR (caller retries)."""
    from parkos_core.sync.motor import sync_motor as sync_motor_module
    from sqlalchemy.exc import SQLAlchemyError

    async def _boom(self, session, spec, **kwargs):
        raise SQLAlchemyError("simulated driver failure")

    monkeypatch.setattr(sync_motor_module.SyncMotor, "resolve_conflict", _boom)

    resolver = ConflictResolver()
    outcome = await resolver.apply_pushed_row(pg_session, _row("documentos"))
    assert outcome == ApplyOutcome.ERROR


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_constructor_rejects_negative_grace_window() -> None:
    with pytest.raises(ValueError, match="jwt_overlap_hours"):
        ConflictResolver(jwt_overlap_hours=-1)


def test_default_grace_window_is_24h() -> None:
    resolver = ConflictResolver()
    assert resolver.jwt_overlap_hours == 24
