"""Branch-side pairing CLI (T-PR8-17, design §21.3, REQ-OP-15).

Reads ``PARKOS_PAIRING_TOKEN`` + ``PARKOS_CLOUD_API_URL`` +
``PARKOS_SYNC_JWT_PATH`` + ``PARKOS_SUCURSAL_UUID`` from env, POSTs to
``{PARKOS_CLOUD_API_URL}/api/v1/sync/pair`` with the token + branch
metadata, writes the returned JWT to ``PARKOS_SYNC_JWT_PATH`` mode
``0o600`` (Unix perms; Windows best-effort), deletes the
``PARKOS_PAIRING_TOKEN`` env var, writes a ``log_transaccional`` row
with ``accion='pair_completed'``, exits 0.

Subsequent boots (no ``PARKOS_PAIRING_TOKEN``) exit 0 silently — the
branch is already paired, the persisted JWT on disk is used by the
sync worker.

Cites design §21.13 ("pairing CLI is env-var driven, not interactive"),
§21.12 risk #23 (operator typo on ``PARKOS_SUCURSAL_UUID`` is caught
by ``doctor``, not by ``pair`` — pair assumes the operator already
validated via doctor).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import socket
import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


def _now_naive() -> datetime:
    """Naive UTC matching the DB ``timestamp without time zone`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _post_pair_request(
    cloud_api_url: str,
    pairing_token: str,
    uuid_sucursal: uuid_lib.UUID,
    branch_info: dict[str, str],
) -> dict[str, object]:
    """POST to the cloud's ``/api/v1/sync/pair`` endpoint.

    Returns the parsed JSON body. Raises ``httpx.HTTPStatusError`` on
    non-2xx and ``httpx.RequestError`` on transport failures — the
    CLI surfaces both as exit code 3 (per the §21.7 exit-code contract
    for transport errors).
    """
    url = f"{cloud_api_url.rstrip('/')}/api/v1/sync/pair"
    payload = {
        "pairing_token": pairing_token,
        "uuid_sucursal": str(uuid_sucursal),
        "branch_info": branch_info,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def _write_log_transaccional(
    *,
    actor_uuid: uuid_lib.UUID | None,
    uuid_sucursal: uuid_lib.UUID,
) -> None:
    """INSERT a ``log_transaccional`` row recording ``pair_completed``.

    Best-effort: if the DB is unreachable, the CLI logs a warning but
    doesn't fail the pair (the JWT is already on disk; ops can replay
    the log row manually).
    """
    try:
        from parkos_core.db.engine import sessionmaker
        from parkos_core.models.A.log_transaccional import LogTransaccional
        from parkos_core.repo.append_only import append_event
    except ImportError as e:
        logger.warning("could not import log_transaccional helpers: %s", e)
        return

    try:
        async with sessionmaker() as session:
            await append_event(
                session,
                LogTransaccional,
                {
                    "uuid_sucursal": uuid_sucursal,
                    "accion": "pair_completed",
                    "tabla_afectada": "sync_agent_jwts",
                    "uuid_registro_afectado": uuid_sucursal,
                    "datos_anteriores": None,
                    "datos_nuevos": {"pair_completed_at": _now_naive().isoformat()},
                },
                actor_uuid=actor_uuid,
            )
            await session.commit()
    except (OSError, RuntimeError) as e:
        logger.warning("could not write log_transaccional row: %s", e)


def _branch_info() -> dict[str, str]:
    """Return the branch bootstrap metadata that the cloud records at consume time."""
    return {
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "version": os.environ.get("PARKOS_VERSION", "0.1.0"),
    }


def _persist_jwt(path: Path, jwt: str) -> None:
    """Write the JWT to ``path`` with restrictive perms (Unix mode 0o600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(jwt, encoding="utf-8")
    # Mode 0o600 — owner read/write, no group/other. On Windows this
    # silently fails (no POSIX mode bits); the file inherits the
    # process's umask which is fine for the branch-host trust model.
    try:
        os.chmod(path, 0o600)
    except OSError as e:
        logger.warning("could not chmod %s to 0o600: %s", path, e)


async def _async_main() -> int:
    """Async entrypoint — exit code 0 on success, 3 on transport failure."""
    parser = argparse.ArgumentParser(
        prog="python -m parkos_core.cli.pair",
        description="Branch-side pairing: consume PARKOS_PAIRING_TOKEN, "
        "exchange for sync-agent- JWT, persist to PARKOS_SYNC_JWT_PATH.",
    )
    parser.parse_args()  # no flags today; reserve for future use

    pairing_token = os.environ.get("PARKOS_PAIRING_TOKEN")
    cloud_api_url = os.environ.get("PARKOS_CLOUD_API_URL")
    sync_jwt_path = os.environ.get("PARKOS_SYNC_JWT_PATH")
    sucursal_uuid_raw = os.environ.get("PARKOS_SUCURSAL_UUID")

    # Subsequent boot: silently exit 0. The branch is already paired.
    if not pairing_token:
        logger.debug("PARKOS_PAIRING_TOKEN unset; branch already paired")
        return 0

    # Validate the rest of the env. Failures map to exit 2 (the §21.7
    # boundary-error contract), surfacing the offending var name.
    missing: list[str] = []
    if not cloud_api_url:
        missing.append("PARKOS_CLOUD_API_URL")
    if not sync_jwt_path:
        missing.append("PARKOS_SYNC_JWT_PATH")
    if not sucursal_uuid_raw:
        missing.append("PARKOS_SUCURSAL_UUID")
    if missing:
        sys.stderr.write("pair: missing env vars: " + ", ".join(missing) + "\n")
        return 2

    try:
        sucursal_uuid = uuid_lib.UUID(sucursal_uuid_raw)
    except ValueError as e:
        sys.stderr.write(f"pair: PARKOS_SUCURSAL_UUID is not a UUID: {e}\n")
        return 2

    # POST to cloud + persist JWT.
    try:
        body = await _post_pair_request(
            cloud_api_url=cloud_api_url,  # type: ignore[arg-type]
            pairing_token=pairing_token,
            uuid_sucursal=sucursal_uuid,
            branch_info=_branch_info(),
        )
    except httpx.HTTPStatusError as e:
        sys.stderr.write(
            f"pair: cloud returned {e.response.status_code}: "
            f"{e.response.text[:200]}\n"
        )
        return 3
    except httpx.RequestError as e:
        sys.stderr.write(f"pair: cloud unreachable: {e}\n")
        return 3

    jwt = body.get("sync_jwt")
    if not isinstance(jwt, str) or not jwt:
        sys.stderr.write("pair: cloud response missing 'sync_jwt'\n")
        return 3

    _persist_jwt(Path(sync_jwt_path), jwt)  # type: ignore[arg-type]

    # Best-effort log row.
    await _write_log_transaccional(
        actor_uuid=None,  # branch's sync-agent has no actor_uuid at pair time
        uuid_sucursal=sucursal_uuid,
    )

    # Clear the token from the env so subsequent processes don't see it.
    os.environ.pop("PARKOS_PAIRING_TOKEN", None)

    sys.stdout.write(
        json.dumps(
            {
                "status": "ok",
                "uuid_sucursal": str(sucursal_uuid),
                "sync_jwt_path": sync_jwt_path,
            }
        )
        + "\n"
    )
    return 0


def main() -> int:
    """Synchronous wrapper for ``python -m parkos_core.cli.pair``."""
    logging.basicConfig(level=os.environ.get("PARKOS_LOG_LEVEL", "INFO"))
    return asyncio.run(_async_main())


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main"]