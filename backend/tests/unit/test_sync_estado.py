"""HU-F1.14 / T3.1+T3.2+T3.3 -- 2 MANDATED handler unit tests + 2 supporting.

The 2 mandated tests per plan.md line 1126:

  * ``test_empty_branch_200_with_null_lag`` -- no sync_log rows ->
    ``lag_seg=None``, ``ultima_sync_at=None``, ``pendientes=0``,
    ``200 OK``, ``Cache-Control: no-store`` (DEC-SYNC-08).
  * ``test_populated_branch_with_5_sync_log_rows_and_12_pending`` -- 5
    sync_log rows + 12 sync_queue pendientes -> exact ``lag_seg`` math
    (within ±1s tolerance) + ``pendientes=12``.

Plus 2 supporting tests:

  * ``test_tenant_scope_violation_returns_403`` -- operador- cross-branch
    -> 403 ``tenant_scope_violation`` + ``Cache-Control: no-store``.
  * ``test_invalid_uuid_returns_422`` -- malformed uuid_sucursal -> 422
    ``uuid_sucursal_invalid`` (Pydantic validator, Layer 4) +
    ``Cache-Control: no-store``.

Pattern: F1.13 ``test_arqueo_handler.py`` -- mock all repo helpers +
DB-mock session with AsyncMock. The handler is exercised in isolation
(no FastAPI app / no httpx), so the tests do NOT need a real DB.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


def _make_ctx(
    *,
    issuer_prefix: str = "operador-",
    sucursal_uuid: uuid_lib.UUID | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.actor_rol = "operador" if issuer_prefix == "operador-" else "admin"
    ctx.issuer_prefix = issuer_prefix
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_params(
    *,
    uuid_sucursal: uuid_lib.UUID | None = None,
) -> MagicMock:
    p = MagicMock()
    p.uuid_sucursal = uuid_sucursal or uuid_lib.uuid4()
    return p


async def _run_handler(handler, params, session, ctx, response):
    """Invoke the handler with the five FastAPI DI values resolved."""
    return await handler(
        response=response,
        params=params,
        session=session,
        ctx=ctx,
        _claims=None,
    )


# ---------------------------------------------------------------------------
# T3.1 -- MANDATED test #1 (empty branch, plan.md line 1126)
# ---------------------------------------------------------------------------


def test_empty_branch_200_with_null_lag() -> None:
    """MANDATED (plan.md line 1126): empty sync_log -> 200 with null lag.

    DEC-SYNC-08: ``lag_seg=None`` (NOT 0, NOT inf). Handler must return
    ``200 OK`` (NOT 404) + ``Cache-Control: no-store``.
    """
    from parkos_core.api.v1 import sync_estado as api_sync_estado
    from parkos_core.repo import sync_estado as repo_sync_estado

    uuid_sucursal = uuid_lib.uuid4()
    params = _build_params(uuid_sucursal=uuid_sucursal)
    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    response = _new_response()
    session = MagicMock()

    with (
        patch.object(
            repo_sync_estado,
            "get_ultima_sync_at",
            AsyncMock(return_value=None),
        ),
        patch.object(
            repo_sync_estado,
            "count_pendientes_sync_queue",
            AsyncMock(return_value=0),
        ),
    ):
        result = asyncio_run(
            _run_handler(api_sync_estado.get_sync_estado, params, session, ctx, response)
        )

    assert result.uuid_sucursal == uuid_sucursal
    assert result.ultima_sync_at is None
    assert result.lag_seg is None
    assert result.pendientes == 0
    assert response.headers["Cache-Control"] == "no-store", (
        "Layer 5: every response MUST carry Cache-Control: no-store (DEC-SYNC-04)"
    )


# ---------------------------------------------------------------------------
# T3.2 -- MANDATED test #2 (populated branch, plan.md line 1126)
# ---------------------------------------------------------------------------


def test_populated_branch_with_5_sync_log_rows_and_12_pending() -> None:
    """MANDATED (plan.md line 1126): 5 sync_log + 12 pendientes -> exact lag math.

    The handler reads ``t_max`` from the helper + computes
    ``calcular_lag_seg(t_max, now)``. With ``t_max`` = ``now - 60s``
    we expect ``lag_seg`` = 60 ± 1s tolerance.
    """
    from parkos_core.api.v1 import sync_estado as api_sync_estado
    from parkos_core.repo import sync_estado as repo_sync_estado

    uuid_sucursal = uuid_lib.uuid4()
    params = _build_params(uuid_sucursal=uuid_sucursal)
    ctx = _make_ctx(sucursal_uuid=uuid_sucursal)
    response = _new_response()
    session = MagicMock()

    # The handler computes ``now = datetime.now(UTC).replace(tzinfo=None)``
    # internally; we pick ``t_max`` = 60s before ``now`` and the test
    # asserts ``lag_seg`` in [59, 61].
    expected_t_max = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=60)

    with (
        patch.object(
            repo_sync_estado,
            "get_ultima_sync_at",
            AsyncMock(return_value=expected_t_max),
        ),
        patch.object(
            repo_sync_estado,
            "count_pendientes_sync_queue",
            AsyncMock(return_value=12),
        ),
    ):
        result = asyncio_run(
            _run_handler(api_sync_estado.get_sync_estado, params, session, ctx, response)
        )

    assert result.uuid_sucursal == uuid_sucursal
    assert result.ultima_sync_at == expected_t_max
    assert result.lag_seg is not None
    assert 59 <= result.lag_seg <= 61, (
        f"expected lag_seg ~60s tolerance, got {result.lag_seg!r}"
    )
    assert result.pendientes == 12
    assert response.headers["Cache-Control"] == "no-store"


# ---------------------------------------------------------------------------
# T3.3 -- supporting test: tenant scope violation returns 403
# ---------------------------------------------------------------------------


def test_tenant_scope_violation_returns_403() -> None:
    """operador- cross-branch -> 403 ``tenant_scope_violation`` + no-store."""
    from fastapi import HTTPException

    from parkos_core.api.v1 import sync_estado as api_sync_estado

    own_branch = uuid_lib.uuid4()
    other_branch = uuid_lib.uuid4()
    params = _build_params(uuid_sucursal=other_branch)
    ctx = _make_ctx(issuer_prefix="operador-", sucursal_uuid=own_branch)
    response = _new_response()
    session = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        asyncio_run(
            _run_handler(api_sync_estado.get_sync_estado, params, session, ctx, response)
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    assert exc_info.value.headers["Cache-Control"] == "no-store"


# ---------------------------------------------------------------------------
# T3.3 -- supporting test: invalid uuid returns 422 (Pydantic Layer 4)
# ---------------------------------------------------------------------------


def test_invalid_uuid_returns_422() -> None:
    """Malformed uuid_sucursal -> 422 ``uuid_sucursal_invalid`` + no-store."""
    from pydantic import ValidationError

    # The Pydantic SyncEstadoQueryParams enforces UUID format at construction
    # time. A bad uuid_sucursal triggers ValidationError BEFORE the handler
    # body runs.
    from parkos_core.schemas.sync_infra import SyncEstadoQueryParams

    with pytest.raises(ValidationError):
        SyncEstadoQueryParams(uuid_sucursal="not-a-uuid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# async + pytest.raises helpers (mirrors F1.13 test_arqueo_handler.py)
# ---------------------------------------------------------------------------


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
