"""test_dispatcher_hash_chain_branch_not_cloud.py — T-PR11-12, REQ-X4.

Per design §21.11 step 3 + AGENTS.md `Hash chain` section: the SHA-256
``log_transaccional`` chain extends PER SUCURSAL. Two different branches
must NEVER share a chain head.

ACTUAL FLOW (verified against ``repo/event.py::record_event``,
``repo/hash_chain.py::_read_prior_hash``):

  1. ``record_event(log_tx=True)`` does NOT call
     :func:`repo.hash_chain.append`. It directly constructs the
     ``LogTransaccional`` row with
     ``uuid_sucursal=new_attrs.get("uuid_sucursal")`` — the **branch**
     UUID passed by the cloud-router handler.
  2. The hash chain columns (``hash_anterior`` / ``hash_actual``) are
     NOT populated by ``record_event``; they are filled only when the
     writer goes through :func:`repo.append_only.append_event` with
     ``chain_hash=True`` (or :func:`repo.hash_chain.append` directly,
     as ``dispatch_revocacion`` does on ``aceptado`` per §21.11 step 2).
  3. :func:`repo.hash_chain._read_prior_hash` queries prior chain head
     by ``model_cls.uuid_sucursal == uuid_sucursal`` — different
     branches therefore have different chain heads.

This test verifies both halves of the contract end-to-end on the
cloud-router flow. No real DB — all session interactions are mocked.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.repo.event import record_event
from parkos_core.repo.hash_chain import _genesis_hash, _read_prior_hash


async def test_record_event_stamps_branch_uuid_and_chain_is_per_sucursal() -> None:
    """T-PR11-12 — log_transaccional stamped with branch.uuid, chain is per-sucursal."""
    branch_uuid = uuid_lib.UUID("11111111-1111-1111-1111-111111111111")
    cloud_uuid = uuid_lib.UUID("22222222-2222-2222-2222-222222222222")
    actor_uuid = uuid_lib.UUID("33333333-3333-3333-3333-333333333333")

    # --- Part 1: record_event stamps log_transaccional.uuid_sucursal = branch.uuid ---
    session = MagicMock(name="AsyncSession")
    added: list = []
    session.add = MagicMock(side_effect=added.append)

    async def _empty_exec(*_a: object, **_k: object) -> MagicMock:
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=None)
        return r

    session.execute = AsyncMock(side_effect=_empty_exec)

    await record_event(
        session,
        FacturaElectronica,
        actor_uuid=actor_uuid,
        new_attrs={
            "uuid_sucursal": branch_uuid,
            "uuid_factura": uuid_lib.uuid4(),
            "uuid_cliente": uuid_lib.uuid4(),
            "uuid_resolucion_facturacion": uuid_lib.uuid4(),
            "prefijo": "SETP",
            "consecutivo": 1,
            "descuento": 0,
        },
        log_tx=True,
    )

    fact_rows = [o for o in added if isinstance(o, FacturaElectronica)]
    log_rows = [o for o in added if isinstance(o, LogTransaccional)]
    assert len(fact_rows) == 1, f"expected 1 FacturaElectronica, got {len(fact_rows)}"
    assert len(log_rows) == 1, f"expected 1 LogTransaccional, got {len(log_rows)}"

    log_row = log_rows[0]
    assert log_row.uuid_sucursal == branch_uuid, (
        f"log_transaccional.uuid_sucursal={log_row.uuid_sucursal}, "
        f"expected branch.uuid={branch_uuid}"
    )
    assert log_row.uuid_sucursal != cloud_uuid, (
        "log_transaccional.uuid_sucursal must be per-branch, not cloud-global"
    )
    assert log_row.tabla_afectada == "factura_electronica"
    assert log_row.uuid_registro_afectado == fact_rows[0].uuid
    assert log_row.uuid_usuario == actor_uuid

    # --- Part 2: _read_prior_hash returns the BRANCH's prior hash_actual ---
    branch_prior_hash = "a" * 64  # valid 64-char hex
    branch_prior_row = MagicMock(name="branch_prior_log")
    branch_prior_row.uuid_sucursal = branch_uuid
    branch_prior_row.hash_actual = branch_prior_hash
    branch_prior_row.timestamp_evento = datetime(2026, 1, 1, tzinfo=UTC).replace(
        tzinfo=None
    )

    branch_session = MagicMock()

    async def _return_branch_prior(*_a: object, **_k: object) -> MagicMock:
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=branch_prior_row)
        return r

    branch_session.execute = AsyncMock(side_effect=_return_branch_prior)

    prior_hash_for_branch = await _read_prior_hash(
        branch_session, LogTransaccional, branch_uuid
    )
    assert prior_hash_for_branch == branch_prior_hash, (
        f"hash_chain should read prior hash from the BRANCH's chain; "
        f"got {prior_hash_for_branch!r}, expected {branch_prior_hash!r}"
    )

    # --- Part 3: a DIFFERENT sucursal gets a DIFFERENT chain head ---
    cloud_session = MagicMock()

    async def _return_cloud_prior(*_a: object, **_k: object) -> MagicMock:
        r = MagicMock()
        # No prior row for cloud → helper returns the genesis anchor for cloud.
        r.scalar_one_or_none = MagicMock(return_value=None)
        return r

    cloud_session.execute = AsyncMock(side_effect=_return_cloud_prior)

    prior_hash_for_cloud = await _read_prior_hash(
        cloud_session, LogTransaccional, cloud_uuid
    )
    assert prior_hash_for_cloud == _genesis_hash(cloud_uuid), (
        f"cloud's prior hash should be its genesis anchor, not the branch's; "
        f"got {prior_hash_for_cloud!r}"
    )
    assert prior_hash_for_cloud != prior_hash_for_branch, (
        "cloud's chain head MUST differ from the branch's — "
        "otherwise the per-sucursal guarantee is broken"
    )
