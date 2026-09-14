"""test_apply_pending_no_self_duplicate.py — regression coverage for a real
defect confirmed in Docker (qa-e2e session, 2026-09-09): granting
``permisos_usuario`` to a bootstrap admin via the real service layer
(``repo.versioned.close_and_insert``, the same primitive
``router_factory.create_endpoint`` uses) produced TWO active rows per grant,
~1.14s apart — with only ONE ``sync_queue`` entry per grant, proving the
second row came from ``SyncCloudWorker._apply_pending_batch_once`` silently
re-applying its own freshly-enqueued row, not from a double call.

Root cause: every ``[V]`` catalog table's real ``INSERT`` fires
``fn_enqueue_sync_catalog()`` (migration 0014) unconditionally, including
cloud-authored writes for ``direction="cloud_to_branch"`` tables that were
ALREADY correctly applied by virtue of being written directly. T-PR11-001's
``_business_payload_for_apply`` strips the source row's own ``uuid`` (to
avoid a PK-collision crash — see that function's block comment), but the
stripped-uuid payload then flows into ``close_and_insert(current_uuid=None,
...)`` unchanged, which happily INSERTs a second row with a freshly
generated uuid — turning a would-be crash into a silent duplicate instead.

This is distinct from ``test_sync_apply_echo_guard.py``, which proves the
motor's OWN write during apply does not RE-ENQUEUE (migration 0016) — it
never exercises a REAL trigger-fired queue entry whose payload is the
already-live source row's own ``to_jsonb(NEW)`` dump, which is exactly what
happens for every genuine cloud-authored write.

Tables with an ``identity_reconciler`` hook (``clientes``, ``vehiculos``)
never hit this: the reconciler recognizes the natural key already exists
and converges instead of blindly inserting. Flat catalogs like
``impuestos`` have no such hook, so nothing stopped the duplicate.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.jobs.sync_cloud import SyncCloudWorker
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.models.V.impuestos import Impuestos
from parkos_core.repo.versioned import close_and_insert
from parkos_core.runtime import engine_flag
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


async def test_apply_pending_batch_once_does_not_duplicate_self_originated_row(
    pg_engine, alembic_upgrade
) -> None:
    """A real, service-layer-created ``impuestos`` row (no identity_reconciler,
    ``direction=cloud_to_branch``) must remain a SINGLE active row after
    ``_apply_pending_batch_once`` drains the real trigger-fired queue entry
    its own INSERT produced."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        codigo = f"iva-{uuid_lib.uuid4().hex[:8]}"
        actor = uuid_lib.uuid4()

        # Real service-layer creation — the SAME primitive
        # router_factory.create_endpoint uses for POST /catalogos/impuestos.
        # This is what fires fn_enqueue_sync_catalog() for real, with a
        # genuine to_jsonb(NEW) payload (unlike the manually-crafted
        # sq_helpers.enqueue() calls the echo-guard tests use).
        row = await close_and_insert(
            session,
            Impuestos,
            current_uuid=None,
            new_attrs={
                "nombre": "IVA",
                "codigo": codigo,
                "porcentaje": "19.0000",
                "tipo_calculo": "porcentaje",
                "base_calculo": "subtotal",
            },
            actor_uuid=actor,
        )
        await session.commit()

        queued = (
            await session.execute(
                select(func.count())
                .select_from(SyncQueue)
                .where(SyncQueue.uuid_registro == row.uuid)
            )
        ).scalar_one()
        assert queued == 1, "sanity: the real trigger must enqueue exactly once"

        worker = SyncCloudWorker(session=session)
        settled = await worker._apply_pending_batch_once()
        await session.commit()
        assert settled >= 1

        active_count = (
            await session.execute(
                select(func.count())
                .select_from(Impuestos)
                .where(Impuestos.codigo == codigo, Impuestos.vigente_hasta.is_(None))
            )
        ).scalar_one()
        assert active_count == 1, (
            "the apply loop must not silently duplicate a cloud-originated "
            f"row whose own uuid already exists — found {active_count} "
            f"active rows for codigo={codigo}"
        )

        dispatched_estado = (
            await session.execute(
                select(SyncQueue.estado).where(SyncQueue.uuid_registro == row.uuid)
            )
        ).scalar_one()
        assert dispatched_estado == "exitoso", (
            "the queue entry must still settle as dispatched — skipping the "
            "re-apply must not leave it stuck pending/failed"
        )
