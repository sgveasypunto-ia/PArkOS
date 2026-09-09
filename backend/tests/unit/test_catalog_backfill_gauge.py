"""Unit tests — ``observability/metrics.py::catalog_backfill_complete`` gauge.

T-PR12-008. Req: REQ-OPS-006 · Design: §9 · Depends on: T-PR12-002.

Exercises the gauge purely through ``cutover.backfill.run_backfill`` with a
FAKE ``SyncMotor`` (an ``apply_batch`` stub returning a chosen
``BatchResult``) — no real Postgres needed; the gauge's transition rule is a
pure function of "did any level buffer a row", independent of what the DB
actually does.
"""
from __future__ import annotations

import uuid as uuid_lib
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.cutover.backfill import BackfillPage, run_backfill
from parkos_core.sync.motor.apply_result import ApplyResult
from parkos_core.sync.motor.sync_motor import BatchResult
from parkos_core.sync.observability.metrics import catalog_backfill_complete


def _gauge_value(uuid_sucursal: uuid_lib.UUID) -> float:
    """Read the current gauge value (test-only escape hatch — prometheus_
    client deliberately has no public "read back" API since it's built for
    scraping, not introspection)."""
    return catalog_backfill_complete.labels(uuid_sucursal=str(uuid_sucursal))._value.get()


def _fake_fetch_page(
    pages_by_table: dict[str, BackfillPage],
) -> Callable[[str, str | None, int], Awaitable[BackfillPage]]:
    async def _fetch(tabla: str, cursor: str | None, limit: int) -> BackfillPage:
        return pages_by_table[tabla]

    return _fetch


class _FakeMotor:
    """Stub ``SyncMotor`` — returns a pre-baked ``BatchResult`` per table."""

    def __init__(self, results_by_table: dict[str, BatchResult]) -> None:
        self._results_by_table = results_by_table

    async def apply_batch(
        self, session: Any, rows: list[tuple[Any, dict[str, Any]]], *, actor_uuid: Any
    ) -> BatchResult:
        tabla = rows[0][0].name
        return self._results_by_table[tabla]


@pytest.mark.asyncio
async def test_gauge_stays_zero_while_any_level_has_unresolved_parent() -> None:
    usuarios = SYNC_CATALOG_BY_NAME["usuarios"]  # level 0, depends_on=()
    permisos_usuario = SYNC_CATALOG_BY_NAME["permisos_usuario"]  # depends on usuarios+permisos

    fetch_page = _fake_fetch_page(
        {
            "usuarios": BackfillPage(rows=({"nombre": "a"},), next_cursor=None, has_more=False),
            "permisos_usuario": BackfillPage(rows=({"x": 1},), next_cursor=None, has_more=False),
        }
    )
    motor = _FakeMotor(
        {
            "usuarios": BatchResult(
                applied=[ApplyResult(status="APPLIED", row_uuid=uuid_lib.uuid4())]
            ),
            "permisos_usuario": BatchResult(buffered=[(permisos_usuario, {"x": 1})]),
        }
    )

    branch = uuid_lib.uuid4()
    result = await run_backfill(
        session=object(),
        uuid_sucursal=branch,
        fetch_page=fetch_page,
        actor_uuid=uuid_lib.uuid4(),
        motor=motor,
        catalog=(usuarios, permisos_usuario),
    )

    assert result.complete is False
    assert result.buffered == 1
    assert _gauge_value(branch) == 0


@pytest.mark.asyncio
async def test_gauge_reaches_one_when_every_level_applies_with_zero_unresolved() -> None:
    usuarios = SYNC_CATALOG_BY_NAME["usuarios"]
    permisos = SYNC_CATALOG_BY_NAME["permisos"]

    fetch_page = _fake_fetch_page(
        {
            "usuarios": BackfillPage(rows=({"nombre": "a"},), next_cursor=None, has_more=False),
            "permisos": BackfillPage(rows=(), next_cursor=None, has_more=False),
        }
    )
    motor = _FakeMotor(
        {
            "usuarios": BatchResult(
                applied=[ApplyResult(status="APPLIED", row_uuid=uuid_lib.uuid4())]
            ),
        }
    )

    branch = uuid_lib.uuid4()
    result = await run_backfill(
        session=object(),
        uuid_sucursal=branch,
        fetch_page=fetch_page,
        actor_uuid=uuid_lib.uuid4(),
        motor=motor,
        catalog=(usuarios, permisos),
    )

    assert result.complete is True
    assert _gauge_value(branch) == 1


@pytest.mark.asyncio
async def test_gauge_reset_to_zero_at_the_start_of_every_run() -> None:
    """A concurrent reader must never see a stale 1 from a PRIOR run while a
    fresh one is mid-flight — run_backfill sets 0 up front, unconditionally."""
    usuarios = SYNC_CATALOG_BY_NAME["usuarios"]
    branch = uuid_lib.uuid4()

    # First run: completes cleanly, gauge -> 1.
    clean_fetch = _fake_fetch_page(
        {"usuarios": BackfillPage(rows=({"nombre": "a"},), next_cursor=None, has_more=False)}
    )
    clean_motor = _FakeMotor(
        {
            "usuarios": BatchResult(
                applied=[ApplyResult(status="APPLIED", row_uuid=uuid_lib.uuid4())]
            )
        }
    )
    await run_backfill(
        session=object(),
        uuid_sucursal=branch,
        fetch_page=clean_fetch,
        actor_uuid=uuid_lib.uuid4(),
        motor=clean_motor,
        catalog=(usuarios,),
    )
    assert _gauge_value(branch) == 1

    # Second run (e.g. re-pairing after a reset) buffers — gauge must drop
    # back to 0, not stay stuck at the prior run's 1.
    buffered_fetch = _fake_fetch_page(
        {"usuarios": BackfillPage(rows=({"nombre": "a"},), next_cursor=None, has_more=False)}
    )
    buffered_motor = _FakeMotor({"usuarios": BatchResult(buffered=[(usuarios, {"nombre": "a"})])})
    result = await run_backfill(
        session=object(),
        uuid_sucursal=branch,
        fetch_page=buffered_fetch,
        actor_uuid=uuid_lib.uuid4(),
        motor=buffered_motor,
        catalog=(usuarios,),
    )
    assert result.complete is False
    assert _gauge_value(branch) == 0
