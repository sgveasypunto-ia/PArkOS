"""SS1: re-delivering a row that already exists is an idempotent APPLIED, in
EVERY engine mode and for every audit class except ``sucursal`` (UPDATE in
place) and ``sesion`` (its closing UPDATE is applied idempotently by the
``session_cycle`` dispatch).

The cloud runs ``PARKOS_SYNC_ENGINE=legacy`` and the dedup used to sit AFTER the
legacy dispatch, so a re-sent seed row (``permisos``, ``clientes``) or an
already-applied ``[A]``/``[L-*]`` row hit ``duplicate key ... _pkey`` on every
retry: ``apply_error`` forever, branch queue never drained.
"""

from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, patch

import pytest
from parkos_core.runtime import engine_flag
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor import sync_motor
from parkos_core.sync.motor.sync_motor import SyncMotor

ROW = uuid_lib.uuid4()


@pytest.mark.parametrize("engine", [engine_flag.EngineMode.LEGACY, engine_flag.EngineMode.CATALOG])
@pytest.mark.parametrize("tabla", ["permisos", "clientes", "factura_electronica", "envio_dian"])
async def test_row_already_present_is_applied_without_touching_the_write_path(
    engine: engine_flag.EngineMode, tabla: str
) -> None:
    spec = SYNC_CATALOG_BY_NAME[tabla]
    write = AsyncMock()
    with (
        patch.object(sync_motor.apply_guard, "row_already_present", AsyncMock(return_value=True)),
        patch.object(sync_motor, "_catalog_apply_row", write),
        patch.object(sync_motor, "remap_payload_with_aliases", AsyncMock(side_effect=lambda s, sp, p: p)),
        patch.object(sync_motor.ConflictResolver, "apply_pushed_row", write),
    ):
        result = await SyncMotor(engine=engine).apply_row(
            AsyncMock(), spec, {"uuid": str(ROW)}, actor_uuid=uuid_lib.uuid4()
        )
    assert result.status == "APPLIED"
    write.assert_not_awaited()


async def test_sesion_is_never_short_circuited_by_the_dedup() -> None:
    """Its closing event carries the uuid of an EXISTING row on purpose."""
    spec = SYNC_CATALOG_BY_NAME["sesion"]
    probe = AsyncMock(return_value=True)
    write = AsyncMock(return_value="written")
    with (
        patch.object(sync_motor.apply_guard, "row_already_present", probe),
        patch.object(sync_motor, "_catalog_apply_row", write),
        patch.object(sync_motor, "remap_payload_with_aliases", AsyncMock(side_effect=lambda s, sp, p: p)),
    ):
        out = await SyncMotor(engine=engine_flag.EngineMode.CATALOG).apply_row(
            AsyncMock(), spec, {"uuid": str(ROW)}, actor_uuid=uuid_lib.uuid4()
        )
    assert out == "written"
    probe.assert_not_awaited()
