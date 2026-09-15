"""HU-F1.14 / T2.1+T2.3+T2.4 -- ``repo/sync_estado.py`` tests.

Three typed SELECT helpers + module-import guard. The handlers consume
these helpers via ``await repo_sync_estado.<helper>(session, ...)``.

* ``get_ultima_sync_at(session, *, uuid_sucursal)`` -> ``datetime | None``.
* ``calcular_lag_seg(ultima_sync_at, now)`` -> ``int | None`` (pure math).
* ``count_pendientes_sync_queue(session, *, uuid_sucursal)`` -> ``int``.

KD-SYNC-01 invariant: the helpers NEVER call ``await session.commit()``
or any UPDATE/DELETE. SELECT-only.

T2.1 RED: the module must import + expose the 3 helper names via
``__all__`` (pre-implementation raises ``ModuleNotFoundError``).
T2.3 RED+GREEN: helper body tests (empty returns None / populated
returns MAX / count empty=0 / count populated=N + pure math for
calcular_lag_seg).
T2.4 REFACTOR: commit-free contract smoke test.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# ---------------------------------------------------------------------------
# T2.1 -- module import + __all__ contract
# ---------------------------------------------------------------------------


def test_repo_sync_estado_module_imports() -> None:
    """T2.1: module imports + ``__all__`` exposes all 3 helper names."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    public = set(repo_sync_estado.__all__)
    expected_helpers = {
        "get_ultima_sync_at",
        "calcular_lag_seg",
        "count_pendientes_sync_queue",
    }
    missing = expected_helpers - public
    assert not missing, f"missing from __all__: {sorted(missing)}"


# ---------------------------------------------------------------------------
# T2.3 -- get_ultima_sync_at (mocked AsyncSession)
# ---------------------------------------------------------------------------


def test_get_ultima_sync_at_empty_returns_none() -> None:
    """T2.3: empty prod.sync_log for uuid_sucursal -> ``None`` (DEC-SYNC-08)."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    uuid_sucursal = uuid_lib.uuid4()
    result = asyncio_run(repo_sync_estado.get_ultima_sync_at(session, uuid_sucursal=uuid_sucursal))

    assert result is None, f"expected None for empty sync_log, got {result!r}"
    # KD-SYNC-01: helper MUST NOT call session.commit().
    session.commit.assert_not_called()


def test_get_ultima_sync_at_populated_returns_max() -> None:
    """T2.3: populated prod.sync_log for uuid_sucursal -> MAX(timestamp_evento)."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    expected_max = datetime(2026, 9, 15, 12, 0, 0)
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=expected_max))
    )

    uuid_sucursal = uuid_lib.uuid4()
    result = asyncio_run(repo_sync_estado.get_ultima_sync_at(session, uuid_sucursal=uuid_sucursal))

    assert result == expected_max, f"expected {expected_max!r}, got {result!r}"
    # KD-SYNC-01: helper MUST NOT call session.commit().
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# T2.3 -- calcular_lag_seg (pure math)
# ---------------------------------------------------------------------------


def test_calcular_lag_seg_null_returns_none() -> None:
    """T2.3: ``calcular_lag_seg(None, now)`` -> ``None`` (DEC-SYNC-08)."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    now = datetime(2026, 9, 15, 12, 0, 0)
    assert repo_sync_estado.calcular_lag_seg(None, now) is None


def test_calcular_lag_seg_positive_returns_int() -> None:
    """T2.3: ``calcular_lag_seg(now-120s, now)`` -> 120 (exact positive int)."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    now = datetime(2026, 9, 15, 12, 0, 0)
    ultima = now - timedelta(seconds=120)
    assert repo_sync_estado.calcular_lag_seg(ultima, now) == 120


def test_calcular_lag_seg_zero_returns_zero() -> None:
    """T2.3: ``calcular_lag_seg(now, now)`` -> 0 (boundary, integer)."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    now = datetime(2026, 9, 15, 12, 0, 0)
    assert repo_sync_estado.calcular_lag_seg(now, now) == 0


def test_calcular_lag_seg_pure_function_no_side_effects() -> None:
    """T2.4 REFACTOR: ``calcular_lag_seg`` is a pure function (deterministic)."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    now = datetime(2026, 9, 15, 12, 0, 0)
    ultima = now - timedelta(seconds=300)
    first = repo_sync_estado.calcular_lag_seg(ultima, now)
    second = repo_sync_estado.calcular_lag_seg(ultima, now)
    third = repo_sync_estado.calcular_lag_seg(ultima, now)
    assert first == second == third == 300, (
        "calcular_lag_seg must be deterministic (pure function, no side effects)"
    )


# ---------------------------------------------------------------------------
# T2.3 -- count_pendientes_sync_queue (mocked AsyncSession)
# ---------------------------------------------------------------------------


def test_count_pendientes_sync_queue_zero_returns_zero() -> None:
    """T2.3: empty prod.sync_queue -> 0 (DEC-SYNC-09: ALWAYS int >= 0)."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one=MagicMock(return_value=0))
    )

    uuid_sucursal = uuid_lib.uuid4()
    result = asyncio_run(
        repo_sync_estado.count_pendientes_sync_queue(session, uuid_sucursal=uuid_sucursal)
    )

    assert result == 0, f"expected 0 for empty sync_queue, got {result!r}"
    assert isinstance(result, int), f"pendientes must be int, got {type(result)}"
    # KD-SYNC-01: helper MUST NOT call session.commit().
    session.commit.assert_not_called()


def test_count_pendientes_sync_queue_positive_returns_count() -> None:
    """T2.3: populated prod.sync_queue with N pendientes -> N."""
    from parkos_core.repo import sync_estado as repo_sync_estado

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one=MagicMock(return_value=12))
    )

    uuid_sucursal = uuid_lib.uuid4()
    result = asyncio_run(
        repo_sync_estado.count_pendientes_sync_queue(session, uuid_sucursal=uuid_sucursal)
    )

    assert result == 12, f"expected 12, got {result!r}"
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# async test helper (the AsyncMock pattern uses asyncio.run to execute)
# ---------------------------------------------------------------------------


def asyncio_run(coro):
    """Synchronously run a single coroutine for the mocked AsyncSession helpers."""
    import asyncio

    return asyncio.run(coro)
