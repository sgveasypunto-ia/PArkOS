"""
check_drain.py — stage-4 drain gate (T-PR11-004, REQ-OPS-013, REQ-CUT-002).

Before the cutover advances from stage 3 ("job_sync_cloud") to stage 4
("branch cutover"), `prod.sync_queue` MUST have zero rows still
`estado='pendiente'` — otherwise a branch could switch appliers mid-flight
while the cloud still has undelivered legacy-path work outstanding.

  SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente';

  - count == 0  -> exit 0
  - count != 0  -> exit 1, printing the count + the elapsed seconds since
    the cutover attempt started (``--since``/``PARKOS_CUTOVER_ATTEMPT_STARTED_AT``,
    both optional; 0.0s when neither is supplied — this script has no
    built-in memory of "when the operator started this attempt", per
    REQ-CUT-002's own note that a non-zero count MUST halt the cutover and
    surface a structured alert, which is the operator's/deploy-pipeline's
    job, not this script's)

Usage:
  python openspec/scripts/check_drain.py [--database-url URL] [--since ISO8601]

  --database-url defaults to the DATABASE_URL env var.
  --since defaults to the PARKOS_CUTOVER_ATTEMPT_STARTED_AT env var, or is
  omitted entirely (elapsed reported as 0.0s).

Exit codes:
  0 = drained (count == 0)
  1 = not drained (count != 0) — cutover MUST halt (REQ-CUT-002)
  2 = usage/connection error (missing DSN, DB unreachable)

Actual CI/stage-gate automation wiring (invoking this script from a real
deploy pipeline) is explicitly out of scope here — a deploy-pipeline
concern, not this script's (mirrors T-PR11-004's own tasks.md note).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg (v3) required. Install with `uv add psycopg[binary]`.", file=sys.stderr)
    sys.exit(2)


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        print(f"ERROR: --since / PARKOS_CUTOVER_ATTEMPT_STARTED_AT is not a valid "
              f"ISO-8601 datetime: {raw!r}", file=sys.stderr)
        sys.exit(2)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def count_pending(conn: psycopg.Connection) -> int:
    """Return ``count(*)`` of ``prod.sync_queue`` rows with ``estado='pendiente'``."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'")
        row = cur.fetchone()
        return int(row[0]) if row is not None else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Stage-4 drain gate: prod.sync_queue must have 0 pending rows."
    )
    parser.add_argument(
        "--database-url", default=None,
        help="Postgres DSN. If omitted, reads the DATABASE_URL env var.",
    )
    parser.add_argument(
        "--since", default=None,
        help="ISO-8601 timestamp the cutover attempt started. If omitted, reads "
             "PARKOS_CUTOVER_ATTEMPT_STARTED_AT; elapsed is reported as 0.0s if neither is set.",
    )
    args = parser.parse_args(argv)

    dsn = args.database_url or os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: --database-url or DATABASE_URL env var required", file=sys.stderr)
        return 2

    since = _parse_since(args.since or os.environ.get("PARKOS_CUTOVER_ATTEMPT_STARTED_AT"))

    try:
        with psycopg.connect(dsn) as conn:
            pending = count_pending(conn)
    except psycopg.OperationalError as e:
        print(f"ERROR: DB connection failed: {e}", file=sys.stderr)
        return 2

    if pending == 0:
        print("OK: prod.sync_queue drained (0 pending rows).")
        return 0

    elapsed_seconds = (datetime.now(UTC) - since).total_seconds() if since is not None else 0.0
    print(
        f"FAIL: prod.sync_queue has {pending} pending row(s); "
        f"elapsed={elapsed_seconds:.1f}s since cutover attempt started. "
        "Cutover MUST halt (REQ-CUT-002)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
