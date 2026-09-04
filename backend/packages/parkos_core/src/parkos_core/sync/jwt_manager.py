"""Branch-side JWT lifecycle manager (T-PR9-04).

``JwtManager`` is consumed by the branch-side ``job_sync_sucursal``
worker. It owns the long-lived JWT file (``PARKOS_SYNC_JWT_PATH``) and
the per-cycle 401 handling:

- ``rotate``: ``POST /api/v1/sync/rotate-jwt`` → new JWT + ``grace_until``.
  Persists the new JWT to disk with mode ``0600`` so a co-located
  process cannot read it. The old JWT remains valid until
  ``grace_until`` (default 24h grace per the spec §21.3).
- ``on_401_response``: parses the JSON error body. ``sync_jwt_revoked``
  → ``sys.exit(1)`` so the orchestrator's restart-loop surfaces the
  issue (the worker emits a ``branch_offline_reauth_required`` marker
  so the supervisor / next boot can flag the operator). ``sync_jwt_expired``
  or ``sync_jwt_invalid`` → :class:`JwtAction.RETRY_NEW_JWT` so the
  caller calls :meth:`rotate` then retries. Anything else → ``HALT_REVOKED``
  (defensive default for unknown 401s).

Why the marker file instead of a direct INSERT into ``alerta``: the
branch worker runs without a live DB session in some failure modes
(e.g. on boot when the JWT file is missing). The marker is process-local
and atomic (``Path.touch(exist_ok=True)``); the next supervisor boot
reads it and surfaces the alerta via the regular branch API path
(``POST /alertas``), which goes through the RBAC + audit chain.

Cites §21.3 (JWT specifics), §21.7 (401 handling + exit codes),
§21.9 (``/sync/rotate-jwt``).
"""
from __future__ import annotations

import enum
import json
import os
import sys
from pathlib import Path

import httpx
import structlog

# Default branch-offline-reauth-required marker filename. Lives in the
# same directory as the JWT file so a co-mounted secret volume keeps
# them together (and the supervisor can wipe both at re-pair time).
BRANCH_OFFLINE_MARKER_NAME = ".branch_offline_reauth_required"


class JwtAction(enum.StrEnum):
    """Action the sync worker should take after a 401."""

    RETRY_NEW_JWT = "retry_new_jwt"
    HALT_REVOKED = "halt_revoked"
    HALT_EXPIRED = "halt_expired"


class JwtManager:
    """Branch-side JWT lifecycle (rotate + 401 handling).

    Args:
        jwt_path: Path to the long-lived ``sync-agent-`` JWT file
            (``PARKOS_SYNC_JWT_PATH``).
        base_url: Cloud API base URL (``PARKOS_CLOUD_API_URL``). Falls
            back to ``PARKOS_CLOUD_API_URL`` from the environment, then
            to ``http://localhost:8000`` (matches the docker-compose
            cloud service name resolution default).
        client_factory: Optional injection seam for tests (returns an
            ``httpx.AsyncClient``). Production uses the default
            ``httpx.AsyncClient(timeout=30.0)``.
        logger: Optional structlog ``BoundLogger``; defaults to the
            ``parkos.sync.jwt_manager`` logger.
    """

    def __init__(
        self,
        jwt_path: Path,
        *,
        base_url: str | None = None,
        client_factory: type[httpx.AsyncClient] | None = None,
        logger: structlog.stdlib.BoundLogger | None = None,
    ) -> None:
        self.jwt_path = Path(jwt_path)
        self.base_url = (base_url or os.environ.get("PARKOS_CLOUD_API_URL", "http://localhost:8000")).rstrip(
            "/"
        )
        self._client_factory = client_factory or httpx.AsyncClient
        self.log = logger or structlog.get_logger("parkos.sync.jwt_manager")

    def get_current_jwt(self) -> str:
        """Read the current JWT from disk.

        Raises:
            FileNotFoundError: ``jwt_path`` is missing — the branch has
                not paired yet, or the supervisor wiped the secret
                volume at re-pair time.
        """
        return self.jwt_path.read_text(encoding="utf-8").strip()

    async def rotate(self) -> str:
        """``POST /api/v1/sync/rotate-jwt`` → persist the new JWT.

        The old JWT (in the ``Authorization`` header) is verified by
        the cloud against its current public key; on success the cloud
        returns ``{"jwt": ..., "expires_at": ..., "grace_until": ...}``
        (the grace window keeps the old JWT valid for ``grace_until``
        so concurrent in-flight requests don't break).

        The new JWT is written with mode ``0600`` on POSIX (best-effort
        on Windows where ``os.chmod`` is partially supported — the
        worker still runs, but the secret is not as tightly contained).
        Returns the new JWT string.

        Raises:
            httpx.HTTPStatusError: cloud rejected the rotate call
                (``401`` for revoked/expired, ``4xx`` for malformed
                inputs, ``5xx`` for transient cloud failures).
        """
        current = self.get_current_jwt()
        async with self._client_factory(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/sync/rotate-jwt",
                headers={"Authorization": f"Bearer {current}"},
            )
        response.raise_for_status()
        body = response.json()
        new_jwt = body["jwt"]

        # Persist with 0600 perms where supported. ``os.open`` with
        # ``O_CREAT | O_TRUNC | O_WRONLY`` gives us atomic-ish
        # replacement; ``os.chmod`` after ``os.close`` is the most
        # portable "set mode" call.
        fd = os.open(
            str(self.jwt_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            os.write(fd, new_jwt.encode("utf-8"))
        finally:
            os.close(fd)
        try:
            os.chmod(self.jwt_path, 0o600)
        except OSError:
            # Windows / filesystems without POSIX mode bits — log and
            # continue. The supervisor still has the secret contained
            # at the docker-volume boundary.
            self.log.warning("jwt_chmod_unsupported", path=str(self.jwt_path))

        self.log.info("jwt_rotated", path=str(self.jwt_path))
        return new_jwt

    async def on_401_response(self, response: httpx.Response) -> JwtAction:
        """Inspect a 401 from the cloud and return the worker action.

        Behaviour by error body:

        - ``sync_jwt_revoked`` → emit a ``branch_offline_reauth_required``
          marker file + ``sys.exit(1)``. The orchestrator restart-loop
          surfaces the issue; an operator must re-pair the branch.
        - ``sync_jwt_expired`` / ``sync_jwt_invalid`` → return
          :class:`JwtAction.RETRY_NEW_JWT` so the caller calls
          :meth:`rotate` then retries the original call.
        - Anything else → :class:`JwtAction.HALT_REVOKED` (defensive
          default; we don't know what the cloud is signalling, so we
          halt rather than retry indefinitely).

        The ``sys.exit(1)`` for the revoked case is intentional: the
        worker has no way to recover (re-pairing requires an admin
        action with the admin JWT) and the orchestrator's restart-loop
        catches the exit, logs the marker, and surfaces the alert to
        the operator via the regular branch API on the next boot.
        """
        error = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                error = str(body.get("error", ""))
        except (ValueError, json.JSONDecodeError):
            # Body not JSON — leave ``error`` empty; falls through to the
            # defensive default (HALT_REVOKED).
            error = ""

        if error == "sync_jwt_revoked":
            self._emit_branch_offline_alerta()
            self.log.error(
                "jwt_revoked_halting",
                status=response.status_code,
                error=error,
            )
            sys.exit(1)
        if error in ("sync_jwt_expired", "sync_jwt_invalid"):
            self.log.warning(
                "jwt_retry_required",
                status=response.status_code,
                error=error,
            )
            return JwtAction.RETRY_NEW_JWT
        # Unknown 401 — treat as revoked (defensive). We don't want the
        # worker spinning forever on a malformed token.
        self.log.error(
            "jwt_unknown_401_halting",
            status=response.status_code,
            error=error,
        )
        return JwtAction.HALT_REVOKED

    def _emit_branch_offline_alerta(self) -> None:
        """Write the ``branch_offline_reauth_required`` marker.

        The marker is a 0-byte file in the JWT directory. The supervisor
        reads it on the next boot and POSTs an ``alerta
        tipo_alerta='branch_offline_reauth_required'`` to the branch
        API, which propagates through the regular RBAC + audit chain.
        Direct DB write is intentionally avoided: the worker may be
        running without a live DB session in this failure mode, and the
        marker is process-local + atomic.
        """
        marker = self.jwt_path.parent / BRANCH_OFFLINE_MARKER_NAME
        marker.touch(exist_ok=True)


__all__ = [
    "BRANCH_OFFLINE_MARKER_NAME",
    "JwtAction",
    "JwtManager",
]
