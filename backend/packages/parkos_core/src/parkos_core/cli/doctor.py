"""Diagnostic CLI (T-PR8-18, design §21.12 risk #23, §21.7).

Prints structured JSON to stdout summarizing the runtime's health:

    {
      "env_status": "ok" | "missing:<var>",
      "db_connectivity": "ok" | "error:<msg>",
      "jwt_key_path_exists": bool,
      "sync_jwt_path_readable": bool,
      "cloud_api_url_reachable": "ok" | "error:<code>"
    }

Exit 0 when all checks pass; exit 1 on any error.

Reuses ``runtime.env.load_config()`` for the env validation. The
``db_connectivity`` check executes ``SELECT 1`` against the DB; the
``cloud_api_url_reachable`` check does a HEAD with httpx + 5s timeout.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime

import httpx


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _check_db() -> str:
    """``SELECT 1`` against the configured DB. Returns 'ok' or 'error:<msg>'."""
    db_url = os.environ.get("PARKOS_DB_URL", "")
    if not db_url:
        return "error:PARKOS_DB_URL_unset"
    import psycopg

    # Normalize asyncpg SQLAlchemy URL → plain psycopg v3 DSN.
    conn_str = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn_str = conn_str.replace("postgresql+psycopg2://", "postgresql://", 1)
    conn_str = conn_str.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with (
            psycopg.connect(conn_str, connect_timeout=3) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT 1")
            cur.fetchone()
    except (psycopg.Error, OSError) as e:
        return f"error:{type(e).__name__}:{e}"
    return "ok"


async def _check_cloud(url: str | None) -> str:
    """HEAD against ``url`` with 5s timeout. Returns 'ok' or 'error:<code>'."""
    if not url:
        return "error:PARKOS_CLOUD_API_URL_unset"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.head(url)
    except (httpx.HTTPError, httpx.RequestError) as e:
        return f"error:{type(e).__name__}"
    if resp.status_code < 400:
        return "ok"
    return f"error:http_{resp.status_code}"


async def _async_main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m parkos_core.cli.doctor",
        description="Print structured diagnostic report for the parkos runtime.",
    )
    parser.parse_args()

    # --- env_status ---
    env_status = "ok"
    try:
        from parkos_core.runtime.env import load_config

        load_config()
    except ImportError as e:
        env_status = f"missing:{type(e).__name__}"

    # --- jwt_key_path_exists (sync check; pathlib is fine outside async I/O) ---
    jwt_key_path = os.environ.get("PARKOS_JWT_KEY_PATH", "")
    jwt_key_exists = bool(jwt_key_path) and os.path.isfile(jwt_key_path)  # noqa: ASYNC240

    # --- sync_jwt_path_readable ---
    sync_jwt_path = os.environ.get("PARKOS_SYNC_JWT_PATH", "")
    sync_jwt_readable = bool(sync_jwt_path) and os.path.isfile(sync_jwt_path)  # noqa: ASYNC240

    # --- db_connectivity (only if env_status ok to avoid noisy errors) ---
    db_connectivity = await _check_db() if env_status == "ok" else "error:env_invalid"

    # --- cloud_api_url_reachable ---
    cloud_url = os.environ.get("PARKOS_CLOUD_API_URL")
    cloud_reachable = await _check_cloud(cloud_url)

    report = {
        "env_status": env_status,
        "db_connectivity": db_connectivity,
        "jwt_key_path_exists": jwt_key_exists,
        "sync_jwt_path_readable": sync_jwt_readable,
        "cloud_api_url_reachable": cloud_reachable,
        "timestamp": _now_naive().isoformat(),
        "deploy": os.environ.get("PARKOS_DEPLOY", "unknown"),
    }

    sys.stdout.write(json.dumps(report) + "\n")

    # Exit 0 iff every check is OK. ``str.startswith('ok')`` covers
    # both 'ok' and 'ok:...' variants (none today, but the pattern is
    # future-proof).
    all_ok = (
        env_status == "ok"
        and db_connectivity.startswith("ok")
        and jwt_key_exists
        and sync_jwt_readable
        and cloud_reachable.startswith("ok")
    )
    return 0 if all_ok else 1


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main"]