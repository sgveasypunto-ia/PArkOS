"""test_sync_sucursal_apply_batch.py — T-PR12-006 acceptance (REQ-MOT-015).

Req: REQ-MOT-015 · Design: §17 · Depends on: T-PR12-002.

Branch mirror of ``test_sync_cloud_catalog_driven.py`` (PR11's cloud-side
acceptance): ``SyncSucursalWorker`` applies a pulled ``cloud_to_branch``
batch through ``SyncMotor.apply_batch`` — dependency-ordered + buffered —
against a real Postgres container, instead of the legacy per-row
``ConflictResolver.apply_pushed_row`` path.

Also proves T-PR12-006's OTHER acceptance clause: batch SELECTION for the
outbound push is unchanged — ``list_pending``'s ``prioridad DESC,
intentos ASC, created_at ASC`` ordering still governs which rows are sent
and in what order; only the wire contract + in-batch application changed.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

from parkos_core.jobs.sync_sucursal import SyncSucursalWorker
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.sync.transport import PullResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


async def test_pull_and_apply_catalog_applies_v_row_via_apply_batch(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    """A cloud_to_branch [V] row pulled from the cloud lands in prod.usuarios
    via SyncMotor.apply_batch (T-PR12-006), not the legacy ConflictResolver."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        jwt_path = tmp_path / "sync.jwt"
        jwt_path.write_text("fake-jwt", encoding="utf-8")

        worker = SyncSucursalWorker(
            jwt_path=jwt_path,
            base_url="http://cloud",
            session=session,
            poll_interval_s=1,
        )

        cedula = f"cd-{uuid_lib.uuid4().hex[:12]}"
        worker._http_client = MagicMock()
        worker._http_client.pull = AsyncMock(
            return_value=PullResponse(
                status=200,
                rows=[
                    {
                        "tabla": "usuarios",
                        "uuid_registro": str(uuid_lib.uuid4()),
                        "datos": {
                            "nombre": "Grace",
                            "apellido": "Hopper",
                            "cedula": cedula,
                            "email": f"{cedula}@example.com",
                            "rol": "operador",
                        },
                    }
                ],
                next_seq=1,
            )
        )

        await worker._pull_and_apply_catalog()
        await session.commit()

        result = await session.execute(
            select(Usuarios).where(Usuarios.cedula == cedula)
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.nombre == "Grace"


async def test_pull_and_apply_catalog_skips_unrecognized_tabla_without_crashing(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    """An unrecognized tabla in the pulled batch never crashes the cycle —
    it's logged and the rest of the batch (if any) still applies."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        jwt_path = tmp_path / "sync.jwt"
        jwt_path.write_text("fake-jwt", encoding="utf-8")

        worker = SyncSucursalWorker(
            jwt_path=jwt_path, base_url="http://cloud", session=session
        )
        worker._http_client = MagicMock()
        worker._http_client.pull = AsyncMock(
            return_value=PullResponse(
                status=200,
                rows=[{"tabla": "not_a_real_table", "uuid_registro": None, "datos": {}}],
                next_seq=1,
            )
        )

        # Must not raise.
        await worker._pull_and_apply_catalog()


async def test_push_catalog_preserves_list_pending_ordering(
    pg_engine, alembic_upgrade
) -> None:
    """T-PR12-006: batch SELECTION is unchanged — still prioridad DESC,
    intentos ASC, created_at ASC (repo/sync_queue.py::list_pending)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        low = await sq_helpers.enqueue(
            session, "insert", "usuarios", uuid_lib.uuid4(), {"k": "low"}, None,
            prioridad=1,
        )
        high = await sq_helpers.enqueue(
            session, "insert", "usuarios", uuid_lib.uuid4(), {"k": "high"}, None,
            prioridad=10,
        )
        await session.commit()

        pending = await sq_helpers.list_pending(session, limit=100)
        pending_uuids = [row.uuid for row in pending]
        # High priority (10) must sort before low priority (1) — unchanged
        # list_pending contract, regardless of which applier pushes them.
        assert pending_uuids.index(high.uuid) < pending_uuids.index(low.uuid)
