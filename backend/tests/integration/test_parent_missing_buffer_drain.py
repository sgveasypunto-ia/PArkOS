"""test_parent_missing_buffer_drain.py — T-PR8-006/007 (design.md §2 Issue #8,
ADR-003 Part 2).

A child (``factura_detalle``) arriving before its declared parent
(``facturas``) is buffered; the sender's outbox row reaches
``estado='exitoso'`` with ``intentos`` UNCHANGED; the child applies once the
parent lands; the buffer row reaches ``estado='aplicado'`` (T-PR8-006/PR8
acceptance).

No real ``ValidateParentChain`` hook implementation exists anywhere across
this change's PR1-PR14 plan (documented gap, ``tasks.md`` T-PR7-006's own
"documented gap, out of PR7 scope" note) — this test forces the
``parent_missing`` condition via the SAME test-injection precedent
(``make_spec(name, hook_validate_parent=lambda ctx: HookResult(parent_valid
=False))``, REQ-HOOK-015) that T-PR7-006 already established for the same
reason.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.models.A.factura_detalle import FacturaDetalle
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.models.A.sync_queue_lw_buffer import SyncQueueLwBuffer
from parkos_core.repo import sync_queue as sync_queue_repo
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.hooks.base import HookResult
from parkos_core.sync.motor import dependency_buffer
from parkos_core.sync.motor.apply_row import apply_row
from sqlalchemy import select


@pytest.mark.usefixtures("alembic_upgrade")
async def test_parent_missing_buffer_drain(
    pg_session, make_spec, seeded_sucursal_uuid
) -> None:
    actor_uuid = uuid_lib.uuid4()
    facturas_uuid = uuid_lib.uuid4()
    child_uuid = uuid_lib.uuid4()

    # --- 1. Simulate the sender's outbox row for the child. ---
    child_payload = {
        "uuid": child_uuid,
        "uuid_sucursal": seeded_sucursal_uuid,
        "uuid_factura": facturas_uuid,
        "concepto": "parqueo",
        "cantidad": 1,
        "valor_unitario": 5000,
        "subtotal": 5000,
    }
    # ``sync_queue.enqueue``'s ``datos`` is a JSONB column and (per its own
    # docstring) is normally fed a ``to_jsonb(NEW)`` DB-trigger snapshot —
    # already JSON-safe. A hand-built Python payload with raw ``UUID``
    # values (as this test constructs) is NOT auto-serializable, so we pass
    # a stringified copy here — same convention ``apply_row``'s payload
    # would arrive in over the wire in production.
    sq_row = await sync_queue_repo.enqueue(
        pg_session,
        "insert",
        "factura_detalle",
        child_uuid,
        {k: (str(v) if isinstance(v, uuid_lib.UUID) else v) for k, v in child_payload.items()},
        seeded_sucursal_uuid,
    )
    await pg_session.flush()
    sq_uuid = sq_row.uuid
    assert sq_row.intentos == 0

    # --- 2. Receiver attempts to apply the child; its declared parent
    #        ("facturas") is missing (forced via test injection — see
    #        module docstring). ---
    forced_spec = make_spec(
        "factura_detalle",
        hook_validate_parent=lambda ctx: HookResult(parent_valid=False),
    )
    result = await apply_row(
        pg_session,
        forced_spec,
        dict(child_payload),
        actor_uuid=actor_uuid,
        branch_uuid=seeded_sucursal_uuid,
    )
    assert result.status == "RETRY"
    assert result.reason == "parent_missing"

    # --- 3. The receiver buffers the row; the SENDER marks its outbox row
    #        delivered (mark_dispatched -> estado='exitoso'), intentos
    #        UNCHANGED — a dependency wait is not a transport failure (D18).
    await dependency_buffer.handle_parent_missing(
        pg_session,
        forced_spec,
        dict(child_payload),
        uuid_registro=child_uuid,
        tabla_padre="facturas",
        uuid_padre=facturas_uuid,
        uuid_sucursal=seeded_sucursal_uuid,
    )
    await sync_queue_repo.mark_dispatched(pg_session, sq_uuid)
    await pg_session.flush()

    refreshed_sq = (
        await pg_session.execute(select(SyncQueue).where(SyncQueue.uuid == sq_uuid))
    ).scalar_one()
    assert refreshed_sq.estado == "exitoso"
    assert refreshed_sq.intentos == 0

    buffered = (
        await pg_session.execute(
            select(SyncQueueLwBuffer).where(SyncQueueLwBuffer.uuid_registro == child_uuid)
        )
    ).scalar_one()
    assert buffered.estado == "pendiente"
    assert buffered.tabla_padre == "facturas"
    assert buffered.uuid_padre == facturas_uuid

    # --- 4. The parent (facturas) lands. ---
    facturas_spec = SYNC_CATALOG_BY_NAME["facturas"]
    facturas_payload = {
        "uuid": facturas_uuid,
        "uuid_sucursal": seeded_sucursal_uuid,
        "subtotal": 5000,
        "descuento": 0,
        "total": 5000,
    }
    parent_result = await apply_row(
        pg_session,
        facturas_spec,
        facturas_payload,
        actor_uuid=actor_uuid,
        branch_uuid=seeded_sucursal_uuid,
    )
    assert parent_result.status == "APPLIED"

    # --- 5. Drain — the child applies (bounded iterative work queue, see
    #        motor/dependency_buffer.py's module docstring). ---
    applied_count = await dependency_buffer.drain_dependency_buffer(
        pg_session,
        tabla_padre="facturas",
        uuid_padre=facturas_uuid,
        actor_uuid=actor_uuid,
        branch_uuid=seeded_sucursal_uuid,
    )
    assert applied_count == 1

    await pg_session.refresh(buffered)
    assert buffered.estado == "aplicado"

    child_row = (
        await pg_session.execute(select(FacturaDetalle).where(FacturaDetalle.uuid == child_uuid))
    ).scalar_one()
    assert child_row.uuid_factura == facturas_uuid
    assert child_row.concepto == "parqueo"
