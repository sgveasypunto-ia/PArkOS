"""
reverse_sync_overhaul.py — idempotent reverse migration (D12, T-PR14-002).

Six steps, matching design.md §12 / proposal §9.8 exactly:

  1. Set ``PARKOS_SYNC_ENGINE=legacy`` on all workers (D12 kill switch).
  2. Wait for ``prod.sync_queue.pendiente == 0`` (drain check, §9.4).
  3. Drain ``prod.sync_queue_lw_buffer`` — buffered rows re-enter the legacy
     path. Reuses ``parkos_core.sync.motor.dependency_buffer
     .drain_dependency_buffer`` for every distinct ``(tabla_padre,
     uuid_padre)`` pending group — the SAME bounded-iterative drain PR8
     ships, never reimplemented here.
  4. Disable the new endpoints.
  5. Restore the legacy push/pull paths.
  6. Verify the chain verifier is still green (reuses PR6's
     ``motor.verify_chain``) AND that ``check_catalog_drift.py`` still
     exits 0.

**Steps 1, 4, and 5 are infra/deploy-pipeline actions this script has no
authority over** (mirrors ``check_drain.py``'s own "actual CI/stage-gate
automation wiring is out of scope" carve-out, and ``cutover/dual_protocol
.py``'s ``PARKOS_CATALOG_REVISION`` carve-out) — there is no live worker
fleet or router process reachable from a one-shot CLI invocation. Every
mode (dry-run AND real) prints the exact operator/deploy-pipeline action
required; neither mode pretends to have flipped infra it cannot reach.
Steps 2, 3, and 6 are real DB operations against ``DATABASE_URL`` — in
``--dry-run`` they are READ-ONLY (report what WOULD happen); without
``--dry-run`` step 3 actually drains the buffer and step 6 actually re-verifies.

**The new ``fn_enqueue_sync_catalog`` triggers (0014, i.e. the catalog
triggers migration tasks.md's PR14 section calls "0011" after the
now-superseded numbering) are NEVER touched by this script** — there is no
code path here that runs Alembic or issues a ``DROP TRIGGER``/``DROP
FUNCTION`` statement. Removing them would re-open the missing-catalog gap
D8-rev exists to close; the legacy applier tolerates the extra
``sync_queue`` rows they still produce (design.md §12, amended).

Idempotent: every step is safe to re-run — step 2/3/6 are pure reads (or a
best-effort apply that only ever moves ``'pendiente'`` rows to
``'aplicado'``, never destructively).

Usage:
  python openspec/scripts/reverse_sync_overhaul.py --dry-run
      [--database-url URL] [--src-root PATH]

  --database-url defaults to the DATABASE_URL env var.
  --src-root defaults to backend/packages/parkos_core/src.

Exit codes:
  0 = every step's real/derivable criteria passed
  1 = at least one real/derivable criterion failed (chain anomaly found,
      check_catalog_drift.py exited non-zero, drain check failed, ...)
  2 = usage/connection error (missing DSN, DB unreachable, backend package
      not importable from --src-root)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import uuid as uuid_lib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC_ROOT = REPO_ROOT / "backend" / "packages" / "parkos_core" / "src"
DEFAULT_CHECK_CATALOG_DRIFT_SCRIPT = Path(__file__).resolve().parent / "check_catalog_drift.py"

# A dedicated, documented "system" actor for automated rollback re-application
# of buffered rows (T-PR14-002 step 3). Nil UUID — no `usuarios` row backs
# it; every drained apply_row call needs SOME actor_uuid to stamp `created_by`
# on cascade rows, and this rollback path runs unattended (no human operator
# JWT available), so a fixed, greppable sentinel is clearer than a random one.
ROLLBACK_SYSTEM_ACTOR_UUID = uuid_lib.UUID(int=0)


def _normalize_to_asyncpg_url(raw: str) -> str:
    """Rewrite a testcontainers/psycopg-style DSN into the asyncpg URL SQLAlchemy async expects.

    Mirrors ``backend/tests/conftest.py``'s own
    ``_testcontainers_url_to_asyncpg`` — duplicated (not imported) because
    this script must run standalone, outside pytest.
    """
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + raw[len("postgresql+psycopg://"):]
    if raw.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://"):]
    if raw.startswith("postgres://"):
        return "postgresql+asyncpg://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw:
        return "postgresql+asyncpg://" + raw[len("postgresql://"):]
    return raw


@dataclass
class StepOutcome:
    step: int
    name: str
    ok: bool
    mutated: bool
    detail: str


@dataclass
class ReverseMigrationReport:
    dry_run: bool
    steps: list[StepOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)

    def record(self, step: int, name: str, *, ok: bool, mutated: bool, detail: str) -> None:
        if self.dry_run and mutated:
            print(f"[DRY-RUN] would {detail}")
        elif ok:
            print(f"OK: step {step} ({name}): {detail}")
        else:
            print(f"FAIL: step {step} ({name}): {detail}")
        self.steps.append(StepOutcome(step, name, ok, mutated, detail))


# ---------------------------------------------------------------------------
# Step 1 — set legacy (advisory: no live worker fleet reachable from here)
# ---------------------------------------------------------------------------


def step1_set_legacy(report: ReverseMigrationReport) -> None:
    report.record(
        1,
        "set_legacy",
        ok=True,
        mutated=True,
        detail=(
            "set PARKOS_SYNC_ENGINE=legacy on all workers (D12 kill switch) — this is a "
            "deploy-pipeline/infra action (compose env, k8s secret, ...) outside this "
            "script's reach; workers re-read the flag every 60s, no restart needed"
        ),
    )


# ---------------------------------------------------------------------------
# Step 2 — wait for sync_queue drain
# ---------------------------------------------------------------------------


async def _count_pending_sync_queue(session) -> int:
    from parkos_core.models.A.sync_queue import SyncQueue
    from sqlalchemy import func, select

    stmt = select(func.count()).select_from(SyncQueue).where(SyncQueue.estado == "pendiente")
    return int((await session.execute(stmt)).scalar_one())


async def step2_wait_for_drain(
    session,
    report: ReverseMigrationReport,
    *,
    dry_run: bool,
    max_attempts: int,
    poll_interval_s: float,
) -> bool:
    pending = await _count_pending_sync_queue(session)
    if dry_run:
        report.record(
            2, "wait_for_drain", ok=True, mutated=True,
            detail=f"wait for prod.sync_queue.pendiente == 0 (currently {pending})",
        )
        return True

    for attempt in range(max_attempts):
        pending = await _count_pending_sync_queue(session)
        if pending == 0:
            report.record(
                2, "wait_for_drain", ok=True, mutated=False,
                detail="prod.sync_queue drained (0 pending rows)",
            )
            return True
        if attempt < max_attempts - 1:
            await asyncio.sleep(poll_interval_s)

    report.record(
        2, "wait_for_drain", ok=False, mutated=False,
        detail=f"prod.sync_queue still has {pending} pending row(s) after {max_attempts} poll(s)",
    )
    return False


# ---------------------------------------------------------------------------
# Step 3 — drain the dependency buffer (reuses PR8's dependency_buffer.py)
# ---------------------------------------------------------------------------


async def _select_distinct_pending_buffer_parents(
    session,
) -> list[tuple[str, uuid_lib.UUID, uuid_lib.UUID | None]]:
    """Every distinct ``(tabla_padre, uuid_padre)`` a 'pendiente' buffer row waits on.

    Read-only — never writes to ``sync_queue_lw_buffer`` directly. Only
    ``parkos_core.sync.motor.dependency_buffer`` is allowed to write to that
    table (its own module docstring's "carve-out" contract); this script
    only ever calls :func:`drain_dependency_buffer` to do so.
    """
    from parkos_core.models.A.sync_queue_lw_buffer import SyncQueueLwBuffer
    from sqlalchemy import select

    stmt = (
        select(
            SyncQueueLwBuffer.tabla_padre,
            SyncQueueLwBuffer.uuid_padre,
            SyncQueueLwBuffer.uuid_sucursal,
        )
        .where(SyncQueueLwBuffer.estado == "pendiente")
        .distinct()
    )
    rows = (await session.execute(stmt)).all()
    return [(r.tabla_padre, r.uuid_padre, r.uuid_sucursal) for r in rows]


async def _count_pending_buffer_rows(session) -> int:
    from parkos_core.models.A.sync_queue_lw_buffer import SyncQueueLwBuffer
    from sqlalchemy import func, select

    stmt = (
        select(func.count())
        .select_from(SyncQueueLwBuffer)
        .where(SyncQueueLwBuffer.estado == "pendiente")
    )
    return int((await session.execute(stmt)).scalar_one())


async def step3_drain_dependency_buffer(
    session, report: ReverseMigrationReport, *, dry_run: bool, actor_uuid: uuid_lib.UUID
) -> None:
    groups = await _select_distinct_pending_buffer_parents(session)
    total_pending = await _count_pending_buffer_rows(session)

    if dry_run:
        report.record(
            3, "drain_dependency_buffer", ok=True, mutated=True,
            detail=(
                f"drain prod.sync_queue_lw_buffer via motor.dependency_buffer"
                f".drain_dependency_buffer for {len(groups)} distinct parent-key "
                f"group(s), {total_pending} pending row(s) total (buffered rows re-enter "
                "the legacy path)"
            ),
        )
        return

    from parkos_core.sync.motor.dependency_buffer import drain_dependency_buffer

    applied_total = 0
    for tabla_padre, uuid_padre, uuid_sucursal in groups:
        applied_total += await drain_dependency_buffer(
            session,
            tabla_padre=tabla_padre,
            uuid_padre=uuid_padre,
            actor_uuid=actor_uuid,
            branch_uuid=uuid_sucursal,
        )
    await session.commit()
    remaining = await _count_pending_buffer_rows(session)
    report.record(
        3, "drain_dependency_buffer", ok=True, mutated=False,
        detail=(
            f"drained {applied_total} buffered row(s); {remaining} still pending "
            "(owned by the existing TTL sweep, unchanged — no new state invented here)"
        ),
    )


# ---------------------------------------------------------------------------
# Steps 4/5 — disable new endpoints / restore legacy paths (advisory)
# ---------------------------------------------------------------------------


def step4_disable_new_endpoints(report: ReverseMigrationReport) -> None:
    report.record(
        4, "disable_new_endpoints", ok=True, mutated=True,
        detail=(
            "disable the new catalog-driven sync endpoints — a router/deploy-config action "
            "outside this script's reach; see AGENTS.md's docker/compose section for where "
            "routing is configured"
        ),
    )


def step5_restore_legacy_paths(report: ReverseMigrationReport) -> None:
    report.record(
        5, "restore_legacy_paths", ok=True, mutated=True,
        detail=(
            "restore the legacy push/pull paths — a deploy-config action outside this "
            "script's reach; the legacy applier itself was never removed from the codebase "
            "(dual-protocol, D11), so restoring it is a routing/flag change, not a code change"
        ),
    )


# ---------------------------------------------------------------------------
# Step 6 — verify chain verifier green + catalog drift green
# ---------------------------------------------------------------------------


async def _known_branch_uuids(session) -> tuple[uuid_lib.UUID, ...]:
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy import select

    rows = (await session.execute(select(Sucursal.uuid))).scalars().all()
    return tuple(rows)


async def step6_verify_green(
    session,
    report: ReverseMigrationReport,
    *,
    dry_run: bool,
    src_root: Path,
    catalog_drift_script: Path,
) -> bool:
    from parkos_core.sync.motor.verify_chain import verify_chain

    branches = await _known_branch_uuids(session)
    anomalies = 0
    for branch in (*branches, None):
        anomalies += len(await verify_chain(session, uuid_sucursal=branch))
    chain_ok = anomalies == 0

    # asyncio.to_thread — subprocess.run is blocking; running it directly
    # here would stall the event loop for every other coroutine.
    drift_proc = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, str(catalog_drift_script), str(src_root)],
        capture_output=True,
        text=True,
    )
    drift_ok = drift_proc.returncode == 0
    ok = chain_ok and drift_ok

    detail = (
        f"chain_anomalies={anomalies}, check_catalog_drift.py exit={drift_proc.returncode}"
    )
    if not drift_ok:
        detail += f"\n--- check_catalog_drift.py output ---\n{drift_proc.stdout}{drift_proc.stderr}"

    report.record(
        6, "verify_green", ok=ok, mutated=dry_run,
        detail=(
            f"verify the chain verifier is green (0 anomalies) and check_catalog_drift.py "
            f"exits 0 — {detail}"
        ) if dry_run else detail,
    )
    return ok


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run(
    *,
    dry_run: bool,
    database_url: str,
    src_root: Path,
    catalog_drift_script: Path = DEFAULT_CHECK_CATALOG_DRIFT_SCRIPT,
    actor_uuid: uuid_lib.UUID = ROLLBACK_SYSTEM_ACTOR_UUID,
    max_drain_attempts: int = 3,
    drain_poll_interval_s: float = 2.0,
) -> ReverseMigrationReport:
    report = ReverseMigrationReport(dry_run=dry_run)

    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    step1_set_legacy(report)

    os.environ["DATABASE_URL"] = _normalize_to_asyncpg_url(database_url)

    # NOTE: ``import parkos_core.db.engine as _engine_mod`` is UNSAFE here —
    # ``parkos_core/db/__init__.py`` does ``from .engine import ... engine``,
    # which REBINDS the package attribute ``parkos_core.db.engine`` to the
    # ``_LazyEngine()`` INSTANCE (shadowing the submodule of the same name).
    # A dotted ``import ... as`` walks attributes from the top-level package
    # object, so it would silently resolve to that instance instead of the
    # real module (confirmed: the instance has no ``.sessionmaker``, and its
    # own ``__getattr__`` proxies to a real ``AsyncEngine``, which doesn't
    # either — an ``AttributeError`` two layers deep). ``importlib`` reads
    # straight from ``sys.modules``, bypassing the shadowed attribute.
    import importlib

    _engine_mod = importlib.import_module("parkos_core.db.engine")

    # Force a fresh engine/sessionmaker bound to THIS invocation's DATABASE_URL
    # (a prior import in the same process — e.g. a test — may have cached one
    # bound to a different DSN; mirrors backend/tests/conftest.py's own reset,
    # which shares this same latent import-shadowing gotcha — see this PR's
    # apply report).
    _engine_mod._engine = None
    _engine_mod._sessionmaker = None
    sessionmaker = _engine_mod.sessionmaker

    async with sessionmaker() as session:
        await step2_wait_for_drain(
            session, report, dry_run=dry_run,
            max_attempts=max_drain_attempts, poll_interval_s=drain_poll_interval_s,
        )
        await step3_drain_dependency_buffer(session, report, dry_run=dry_run, actor_uuid=actor_uuid)

    step4_disable_new_endpoints(report)
    step5_restore_legacy_paths(report)

    async with sessionmaker() as session:
        await step6_verify_green(
            session, report, dry_run=dry_run, src_root=src_root,
            catalog_drift_script=catalog_drift_script,
        )

    await _engine_mod._get_engine().dispose()
    # Leave no trace: reset the module-level singleton pointers so any OTHER
    # consumer sharing this process (e.g. a later test in the same pytest
    # session) lazily rebuilds its OWN fresh engine against whatever
    # DATABASE_URL is current at ITS time of use, rather than touching this
    # now-disposed engine object.
    _engine_mod._engine = None
    _engine_mod._sessionmaker = None
    return report


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent reverse migration for sync-overhaul (D12, T-PR14-002)."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Record actions without mutating state."
    )
    parser.add_argument(
        "--database-url", default=None,
        help="Postgres DSN. If omitted, reads the DATABASE_URL env var.",
    )
    parser.add_argument(
        "--src-root", default=None,
        help="parkos_core src root. Defaults to backend/packages/parkos_core/src.",
    )
    args = parser.parse_args(argv)

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: --database-url or DATABASE_URL env var required", file=sys.stderr)
        return 2

    src_root = Path(args.src_root) if args.src_root else DEFAULT_SRC_ROOT
    if not src_root.is_dir():
        print(f"ERROR: source root not found: {src_root}", file=sys.stderr)
        return 2

    try:
        report = asyncio.run(
            run(dry_run=args.dry_run, database_url=database_url, src_root=src_root)
        )
    except ImportError as exc:
        print(f"ERROR: could not import parkos_core: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: DB connection failed: {exc}", file=sys.stderr)
        return 2

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
