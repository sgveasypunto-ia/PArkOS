"""test_motor_apply_batch.py — T-PR4-009 acceptance for
``motor/sync_motor.py::SyncMotor.apply_batch``.

Given a batch containing a row whose own ``hook_validate_parent`` reports a
missing parent (``RETRY(parent_missing)``), when ``apply_batch`` processes
the batch, then every other row in the same batch whose declared
``depends_on`` names the buffered row's table is ALSO buffered — never
attempted, never failed (REQ-MOT-015, design.md Issue #8).

NOTE (PR4 stub): the real persistent dependency buffer
(``motor/dependency_buffer.py``, writing ``prod.sync_queue_lw_buffer`` keyed
on the exact ``(tabla_padre, uuid_padre)``) lands in PR8. This test exercises
``SyncMotor.apply_batch``'s own per-call, in-memory bookkeeping
(``BatchResult.buffered``) — coarser than the real buffer (table-name-level,
not per-uuid) but sufficient to prove the "children of a buffered row are
never attempted" contract this PR ships. ``xfail`` is deliberately NOT used
here — per tasks.md T-PR4-009, the stub genuinely satisfies the contract
this test exercises.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock, patch

from parkos_core.runtime.engine_flag import EngineMode
from parkos_core.sync.hooks.base import HookResult
from parkos_core.sync.motor.sync_motor import SyncMotor

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


async def test_retry_parent_missing_buffers_children_in_batch(make_spec) -> None:
    """A missing-parent row buffers itself AND every same-batch child.

    ``facturas`` is forced to report a missing parent via an overridden
    ``hook_validate_parent`` (its real dependencies are not seeded here —
    this test is pure mock, no DB). ``factura_impuestos`` declares
    ``facturas`` in its own ``depends_on``, so once ``facturas`` is
    buffered, ``factura_impuestos`` must be buffered too — WITHOUT
    ``apply_row`` (and therefore its repo call) ever running on it.
    """
    facturas_spec = make_spec(
        "facturas",
        hook_validate_parent=lambda ctx: HookResult(proceed=True, parent_valid=False),
    )
    factura_impuestos_spec = make_spec("factura_impuestos")

    # Batch fed in a dependency-naive order — order_batch (invoked inside
    # apply_batch) is what puts facturas ahead of factura_impuestos.
    rows = [
        (
            factura_impuestos_spec,
            {"uuid_sucursal": None, "uuid_factura": None, "uuid_impuesto": None},
        ),
        (facturas_spec, {"uuid_sucursal": None}),
    ]

    motor = SyncMotor(engine=EngineMode.CATALOG)
    session = MagicMock(name="session")
    session.flush = AsyncMock()

    with (
        patch("parkos_core.repo.event.record_event", new=AsyncMock()) as record_mock,
        patch("parkos_core.repo.append_only.append_event", new=AsyncMock()) as append_mock,
    ):
        result = await motor.apply_batch(session, rows, actor_uuid=ACTOR_UUID)

    # Neither row's repo call ever ran — facturas short-circuited on its own
    # hook_validate_parent; factura_impuestos was buffered by apply_batch
    # BEFORE apply_row (and therefore its repo call) was ever invoked.
    record_mock.assert_not_called()
    append_mock.assert_not_called()

    buffered_names = {spec.name for spec, _ in result.buffered}
    assert buffered_names == {"facturas", "factura_impuestos"}
    assert result.applied == []
