"""test_reverse_dry_run.py — T-PR14-002 acceptance for
``openspec/scripts/reverse_sync_overhaul.py`` (D12).

  - ``--dry-run`` exits 0 on a clean run.
  - ``--dry-run`` exits non-zero when ``check_catalog_drift.py`` fails.
  - The ``fn_enqueue_sync_catalog`` triggers (0014, the migration
    ``tasks.md``'s PR14 section calls "0011" after the now-superseded
    renumbering) are asserted NOT removed, in both ``--dry-run`` and a real
    (non-dry-run) invocation.
  - Step 3 reuses ``motor.dependency_buffer.drain_dependency_buffer``
    (PR8) rather than reimplementing the drain: a buffered row whose
    parent already landed gets applied by a real (non-dry-run) run.

Assertions about the OVERALL report (``report.ok``) are scoped to
``--dry-run`` only — dry-run never touches ``prod.sync_queue``'s real
backlog (step 2 always reports without checking it), so it is unaffected
by whatever OTHER tests sharing this session-scoped container leave
behind. A real (non-dry-run) run's step 2 (drain-wait) legitimately
depends on the ACTUAL current backlog across the whole shared test
container, so those tests assert the SPECIFIC step outcome they exercise
(step 3's drain, or the trigger count) rather than the full report's
aggregate ``.ok``.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _REPO_ROOT / "openspec" / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import reverse_sync_overhaul  # noqa: E402

_CATALOG_TRIGGER_NAMES = (
    "usuarios_enqueue_sync_catalog",
    "sucursal_enqueue_sync_catalog",
    "clientes_enqueue_sync_catalog",
)


async def _trigger_count(pg_engine: AsyncEngine, names: tuple[str, ...]) -> int:
    async with pg_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT count(*) FROM information_schema.triggers "
                "WHERE trigger_schema = 'prod' AND trigger_name = ANY(:names)"
            ),
            {"names": list(names)},
        )
        return result.scalar_one()


def _trigger_count_sync(pg_dsn: str, names: tuple[str, ...]) -> int:
    """Plain-psycopg trigger count (mirrors ``check_drain.py``'s own sync style).

    Used by the tests that call ``reverse_sync_overhaul.main()`` directly —
    ``main()`` runs its own ``asyncio.run()`` internally, which cannot be
    invoked from inside pytest-asyncio's already-running event loop, so
    those tests are plain (non-async) functions and need a plain-sync DB
    check alongside them.
    """
    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.triggers "
            "WHERE trigger_schema = 'prod' AND trigger_name = ANY(%s)",
            (list(names),),
        )
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0


def _step(report: reverse_sync_overhaul.ReverseMigrationReport, step: int):
    return next(s for s in report.steps if s.step == step)


@pytest.mark.usefixtures("alembic_upgrade")
def test_dry_run_exits_0_on_clean_run(pg_async_dsn: str, pg_dsn: str) -> None:
    """Plain (non-async) test — ``main()`` runs its own ``asyncio.run()`` and
    cannot be called from within pytest-asyncio's already-running loop."""
    before = _trigger_count_sync(pg_dsn, _CATALOG_TRIGGER_NAMES)
    assert before == len(_CATALOG_TRIGGER_NAMES)

    exit_code = reverse_sync_overhaul.main(["--dry-run", "--database-url", pg_async_dsn])
    assert exit_code == 0

    after = _trigger_count_sync(pg_dsn, _CATALOG_TRIGGER_NAMES)
    assert after == before, "dry-run must never mutate state, including trigger definitions"


@pytest.mark.usefixtures("alembic_upgrade")
def test_dry_run_via_plain_psycopg_style_dsn(pg_dsn: str) -> None:
    """The DSN normalizer accepts a plain ``postgresql://`` DSN, not only ``+asyncpg``."""
    exit_code = reverse_sync_overhaul.main(["--dry-run", "--database-url", pg_dsn])
    assert exit_code == 0


@pytest.mark.usefixtures("alembic_upgrade")
async def test_dry_run_exits_nonzero_when_catalog_drift_check_fails(
    pg_async_dsn: str, tmp_path: Path
) -> None:
    failing_script = tmp_path / "always_fail.py"
    failing_script.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")

    report = await reverse_sync_overhaul.run(
        dry_run=True,
        database_url=pg_async_dsn,
        src_root=reverse_sync_overhaul.DEFAULT_SRC_ROOT,
        catalog_drift_script=failing_script,
    )
    assert report.ok is False
    assert _step(report, 6).ok is False


@pytest.mark.usefixtures("alembic_upgrade")
async def test_fn_enqueue_sync_catalog_triggers_not_removed_on_real_run(
    pg_async_dsn: str, pg_engine: AsyncEngine
) -> None:
    """A real (non-dry-run) invocation never drops the 0014 catalog triggers (D12, §12 amended)."""
    before = await _trigger_count(pg_engine, _CATALOG_TRIGGER_NAMES)

    report = await reverse_sync_overhaul.run(
        dry_run=False,
        database_url=pg_async_dsn,
        src_root=reverse_sync_overhaul.DEFAULT_SRC_ROOT,
    )

    after = await _trigger_count(pg_engine, _CATALOG_TRIGGER_NAMES)
    assert after == before
    # Step 6 (chain verifier + catalog drift) is independent of prod.sync_queue's
    # backlog and must be green regardless of what other tests leave behind.
    assert _step(report, 6).ok is True


@pytest.mark.usefixtures("alembic_upgrade")
async def test_step3_drains_buffer_via_dependency_buffer_reuse(
    pg_session, pg_async_dsn: str, seeded_sucursal_uuid
) -> None:
    """Non-dry-run step 3 reuses PR8's ``drain_dependency_buffer`` — a buffered
    row whose parent already landed gets applied, never reimplemented."""
    from parkos_core.models.A.sync_queue_lw_buffer import SyncQueueLwBuffer
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
    from parkos_core.sync.motor.apply_row import apply_row

    actor_uuid = uuid_lib.uuid4()
    facturas_uuid = uuid_lib.uuid4()
    child_uuid = uuid_lib.uuid4()

    # Seed the parent FIRST (already landed) — the rollback scenario where,
    # by the time this step runs, the parent has since arrived.
    facturas_spec = SYNC_CATALOG_BY_NAME["facturas"]
    parent_result = await apply_row(
        pg_session,
        facturas_spec,
        {
            "uuid": facturas_uuid,
            "uuid_sucursal": seeded_sucursal_uuid,
            "subtotal": 5000,
            "descuento": 0,
            "total": 5000,
        },
        actor_uuid=actor_uuid,
        branch_uuid=seeded_sucursal_uuid,
    )
    assert parent_result.status == "APPLIED"

    now = datetime.now(UTC).replace(tzinfo=None)
    buffered = SyncQueueLwBuffer(
        uuid_sucursal=seeded_sucursal_uuid,
        tabla="factura_detalle",
        uuid_registro=child_uuid,
        tabla_padre="facturas",
        uuid_padre=facturas_uuid,
        datos={
            "uuid": str(child_uuid),
            "uuid_sucursal": str(seeded_sucursal_uuid),
            "uuid_factura": str(facturas_uuid),
            "concepto": "parqueo",
            "cantidad": 1,
            "valor_unitario": 5000,
            "subtotal": 5000,
        },
        estado="pendiente",
        buffered_at=now,
        expires_at=now + timedelta(hours=24),
    )
    pg_session.add(buffered)
    # A real commit (not just flush) — reverse_sync_overhaul.run() opens its
    # OWN session/connection, so the seeded row must actually be persisted
    # to be visible to it.
    await pg_session.commit()

    report = await reverse_sync_overhaul.run(
        dry_run=False,
        database_url=pg_async_dsn,
        src_root=reverse_sync_overhaul.DEFAULT_SRC_ROOT,
    )
    assert _step(report, 3).ok is True

    await pg_session.refresh(buffered)
    assert buffered.estado == "aplicado"
