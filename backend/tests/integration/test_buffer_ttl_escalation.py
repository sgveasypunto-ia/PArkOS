"""test_buffer_ttl_escalation.py — T-PR8-008/009 (design.md §2 Issue #8's
"Escalation").

An unresolved parent past the 24h TTL emits exactly ONE
``alerta tipo_alerta='orphan_workflow_chain'`` and produces ZERO
``sync_queue`` re-enqueues; the buffered row lands ``estado='fallido'``,
``ultimo_error='parent_missing_timeout'``, never deleted (T-PR8-008/PR8
acceptance).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.models.A.sync_queue_lw_buffer import SyncQueueLwBuffer
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.sync.motor import dependency_buffer
from sqlalchemy import select


@pytest.mark.usefixtures("alembic_upgrade")
async def test_buffer_ttl_escalation_emits_one_alert_no_requeue(
    pg_session, seeded_sucursal_uuid
) -> None:
    child_uuid = uuid_lib.uuid4()
    facturas_uuid = uuid_lib.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    # ``ttl_hours=-1`` yields an ``expires_at`` already in the past — set
    # AT INSERT TIME, never via a post-insert UPDATE: ``[A]`` tables are
    # append-only (REVOKE + inmutable trigger), so mutating ``expires_at``
    # after the fact would itself raise ``SYNC_QUEUE_LW_BUFFER_INMUTABLE``.
    buffered = await dependency_buffer.buffer_row(
        pg_session,
        uuid_sucursal=seeded_sucursal_uuid,
        tabla="factura_detalle",
        uuid_registro=child_uuid,
        tabla_padre="facturas",
        uuid_padre=facturas_uuid,
        datos={"uuid": str(child_uuid)},
        ttl_hours=-1,
    )
    await pg_session.flush()

    pre_existing_alerts = (
        await pg_session.execute(
            select(Alerta).where(
                Alerta.tipo_alerta == "orphan_workflow_chain",
                Alerta.uuid_sucursal == seeded_sucursal_uuid,
            )
        )
    ).scalars().all()
    assert pre_existing_alerts == []

    expired_count = await dependency_buffer._lw_buffer_sweep(pg_session, now=now)
    assert expired_count == 1

    await pg_session.refresh(buffered)
    assert buffered.estado == "fallido"
    assert buffered.ultimo_error == "parent_missing_timeout"

    alerts = (
        await pg_session.execute(
            select(Alerta).where(
                Alerta.tipo_alerta == "orphan_workflow_chain",
                Alerta.uuid_sucursal == seeded_sucursal_uuid,
            )
        )
    ).scalars().all()
    assert len(alerts) == 1

    # Zero sync_queue re-enqueues — a dependency-wait timeout is not a
    # transport failure (D18); intentos/next_retry_at are never touched
    # for this reason.
    sq_rows = (
        await pg_session.execute(select(SyncQueue).where(SyncQueue.uuid_registro == child_uuid))
    ).scalars().all()
    assert sq_rows == []

    # Never deleted — the buffer row still exists (append-only contract).
    still_there = (
        await pg_session.execute(
            select(SyncQueueLwBuffer).where(SyncQueueLwBuffer.uuid_registro == child_uuid)
        )
    ).scalar_one_or_none()
    assert still_there is not None
    assert still_there.estado == "fallido"


@pytest.mark.usefixtures("alembic_upgrade")
async def test_buffer_ttl_sweep_ignores_non_expired_rows(pg_session, seeded_sucursal_uuid) -> None:
    """A row still within its TTL window is untouched by the sweep."""
    child_uuid = uuid_lib.uuid4()
    facturas_uuid = uuid_lib.uuid4()

    await dependency_buffer.buffer_row(
        pg_session,
        uuid_sucursal=seeded_sucursal_uuid,
        tabla="factura_detalle",
        uuid_registro=child_uuid,
        tabla_padre="facturas",
        uuid_padre=facturas_uuid,
        datos={"uuid": str(child_uuid)},
        ttl_hours=24,
    )
    await pg_session.flush()

    expired_count = await dependency_buffer._lw_buffer_sweep(pg_session)
    assert expired_count == 0

    row = (
        await pg_session.execute(
            select(SyncQueueLwBuffer).where(SyncQueueLwBuffer.uuid_registro == child_uuid)
        )
    ).scalar_one()
    assert row.estado == "pendiente"
