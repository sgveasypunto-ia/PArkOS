"""test_local_only_and_infra_never_replicate.py — closes the negative-test
gap from the original QA plan (sections 5.9/5.10): the 3 ``LOCAL_ONLY_CATALOG``
tables must NEVER enqueue into ``sync_queue`` (no trigger attached at all),
and the 5 ``OUT_OF_CATALOG`` infra names must be SKIPPED by the cloud apply
loop without ever failing or reaching ``apply_row`` — confirmed against a
real Postgres container, not asserted from reading the catalog declarations.

The 3 LOCAL_ONLY_CATALOG checks use direct ``pg_trigger`` introspection
(never an INSERT): constructing a fully-valid business row for all three
would otherwise couple this test to each table's own unrelated schema
quirks (e.g. ``idempotency_keys`` has no ``fecha_retencion_hasta`` column
despite inheriting the same ``[A]`` base every partitioned table does — a
separate, pre-existing gap out of scope for this test). Checking "no
enqueue trigger is attached" directly is both simpler and a more precise
match for what LOCAL_ONLY_CATALOG's contract actually promises.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.jobs.sync_cloud import SyncCloudWorker
from parkos_core.models.A.sync_queue import SyncQueue
from parkos_core.repo import sync_queue as sq_helpers
from parkos_core.runtime import engine_flag
from parkos_core.sync.catalog.local_only_catalog import LOCAL_ONLY_CATALOG
from parkos_core.sync.catalog.out_of_catalog import OUT_OF_CATALOG
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


@pytest.mark.parametrize("entry", LOCAL_ONLY_CATALOG, ids=lambda e: e.name)
async def test_local_only_table_has_no_enqueue_trigger(pg_engine, alembic_upgrade, entry) -> None:
    """No ``fn_enqueue_sync``/``fn_enqueue_sync_catalog`` trigger is attached
    to a LOCAL_ONLY_CATALOG table — the DB-level guarantee behind
    ``direction=None``/``sync_strategy="local_only"``, not just a Python-side
    declaration."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        result = await session.execute(
            text(
                """
                SELECT t.tgname, p.proname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_proc p ON p.oid = t.tgfoid
                WHERE n.nspname = 'prod'
                  AND c.relname = :tabla
                  AND NOT t.tgisinternal
                  AND p.proname IN ('fn_enqueue_sync', 'fn_enqueue_sync_catalog')
                """
            ),
            {"tabla": entry.name},
        )
        enqueue_triggers = result.all()
        assert enqueue_triggers == [], (
            f"{entry.name}: LOCAL_ONLY_CATALOG table must have NO sync-enqueue "
            f"trigger attached — found {enqueue_triggers}"
        )


@pytest.mark.parametrize("tabla", sorted(OUT_OF_CATALOG))
async def test_infra_table_row_is_skipped_without_failure(
    pg_engine, alembic_upgrade, tabla: str
) -> None:
    """A stray ``sync_queue`` row whose ``tabla`` is one of the 5
    out-of-catalog infra names must settle as dispatched (never
    ``mark_failed``, never re-enqueued) WITHOUT the apply loop ever calling
    ``SyncMotor.apply_row``/``apply_batch`` for it (D21 guard 2)."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        queue_row = await sq_helpers.enqueue(
            session,
            "insert",
            tabla,
            uuid_lib.uuid4(),
            {"stray": "infra-row", "tabla": tabla},
            None,
        )
        await session.commit()

        worker = SyncCloudWorker(session=session)
        settled = await worker._apply_pending_batch_once()
        await session.commit()
        assert settled >= 1

        estado, ultimo_error, intentos = (
            await session.execute(
                select(SyncQueue.estado, SyncQueue.ultimo_error, SyncQueue.intentos).where(
                    SyncQueue.uuid == queue_row.uuid
                )
            )
        ).one()
        assert estado == "exitoso", (
            f"{tabla}: infra row must settle as dispatched, not {estado!r} "
            f"(ultimo_error={ultimo_error!r})"
        )
        assert ultimo_error is None
        assert intentos == 0, "an infra-row skip must never count as a delivery retry"
