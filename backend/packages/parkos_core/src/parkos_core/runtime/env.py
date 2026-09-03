"""Runtime env validator (T-PR8-01).

Single source of truth for runtime-required env vars. Called via
``parkos_core.runtime.env.load_config()`` at the FIRST import in each
entrypoint (admin/branch/runner) — fail-fast before any DB or network
connection (REQ: bootstrap's existing ``entrypoint.sh`` env pre-flight stays
for the 49-schema migration + Alembic REVOKE/trigger verification; this
validator focuses on runtime-required env).

Validates:

- ``PARKOS_DEPLOY ∈ {cloud, branch}`` (REQUIRED)
- ``PARKOS_SUCURSAL_UUID`` is UUIDv4 on branch (REQUIRED on branch, OPTIONAL on cloud)
- ``PARKOS_DB_URL`` (REQUIRED on both)
- ``PARKOS_CLOUD_API_URL`` (REQUIRED on branch — branch needs to know the cloud endpoint)
- ``PARKOS_JWT_KEY_PATH`` (REQUIRED on both)
- ``PARKOS_SYNC_JWT_PATH`` (REQUIRED on branch)
- ``PARKOS_DIAN_PROVIDER_URL`` + ``PARKOS_DIAN_PROVIDER_TOKEN_PATH`` (REQUIRED on cloud)

Optional ints (with defaults): ``PARKOS_SYNC_POLL_INTERVAL_S=10``,
``PARKOS_SYNC_BATCH_SIZE=100``, ``PARKOS_SYNC_HEARTBEAT_S=60``,
``PARKOS_DIAN_TIMEOUT_S=30``, ``PARKOS_DIAN_RETRY_MAX=3``,
``PARKOS_SYNC_VERIFY_INTERVAL_S=3600``.

Cites design §21.2 (env validator).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID


class MissingEnvError(Exception):
    """Raised when required env vars are unset or malformed.

    Carry the offending var names + reason so callers (entrypoints) can
    format a clean stderr + exit code 2.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            "Missing/malformed env vars: " + ", ".join(errors)
        )


def _require_str(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise MissingEnvError([f"{name}=<unset>"])
    return val


def _require_uuid(name: str, *, v4_only: bool = False) -> UUID:
    raw = _require_str(name)
    try:
        u = UUID(raw)
    except ValueError as e:
        raise MissingEnvError([f"{name}={raw!r} is not a UUID: {e}"]) from e
    if v4_only and u.version != 4:
        raise MissingEnvError([f"{name}={raw!r} is not UUIDv4 (got v{u.version})"])
    return u


def _require_path(name: str) -> Path:
    raw = _require_str(name)
    p = Path(raw)
    parent = p.parent
    # ``is_dir()`` is False for both "parent missing" and "parent is a file" —
    # either way the env var points at an unusable location, so reject early.
    if not parent.is_dir():
        raise MissingEnvError(
            [f"{name}={raw!r} parent dir missing or not a directory: {parent}"]
        )
    return p


def _optional_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        # Malformed → fall back to default + warn (per spec §21.2 acceptance #11)
        import warnings

        warnings.warn(
            f"{name}={raw!r} is not a valid int; using default {default}",
            stacklevel=2,
        )
        return default


@dataclass(frozen=True)
class BranchConfig:
    """Branch runtime config (PARKOS_DEPLOY=branch)."""

    deploy: str = "branch"
    uuid_sucursal: UUID = field(default=None)  # type: ignore[assignment]
    db_url: str = ""
    cloud_api_url: str = ""
    jwt_key_path: Path = field(default=None)  # type: ignore[assignment]
    sync_jwt_path: Path = field(default=None)  # type: ignore[assignment]

    sync_poll_interval_s: int = 10
    sync_batch_size: int = 100
    sync_heartbeat_s: int = 60
    sync_verify_interval_s: int = 3600


@dataclass(frozen=True)
class CloudConfig:
    """Cloud runtime config (PARKOS_DEPLOY=cloud)."""

    deploy: str = "cloud"
    db_url: str = ""
    jwt_key_path: Path = field(default=None)  # type: ignore[assignment]

    dian_provider_url: str = ""
    dian_provider_token_path: Path = field(default=None)  # type: ignore[assignment]

    dian_timeout_s: int = 30
    dian_retry_max: int = 3


def load_config() -> BranchConfig | CloudConfig:
    """Load + validate runtime env. Returns BranchConfig or CloudConfig.

    Collects ALL offending vars before raising so the caller can render a
    single, actionable stderr message (rather than fixing one var at a
    time across multiple invocations).

    Raises:
        MissingEnvError: with a list of all offending var names + reasons.
    """
    errors: list[str] = []

    deploy = os.environ.get("PARKOS_DEPLOY")
    if deploy not in ("cloud", "branch"):
        errors.append(f"PARKOS_DEPLOY={deploy!r} (must be 'cloud' or 'branch')")

    db_url = os.environ.get("PARKOS_DB_URL", "")
    if not db_url:
        errors.append("PARKOS_DB_URL=<unset>")

    try:
        jwt_key_path = _require_path("PARKOS_JWT_KEY_PATH")
    except MissingEnvError as e:
        errors.extend(e.errors)
        jwt_key_path = None  # type: ignore[assignment]  # placeholder

    if deploy == "branch":
        try:
            uuid_sucursal = _require_uuid("PARKOS_SUCURSAL_UUID", v4_only=True)
        except MissingEnvError as e:
            errors.extend(e.errors)
            uuid_sucursal = None  # type: ignore[assignment]  # placeholder

        cloud_api_url = os.environ.get("PARKOS_CLOUD_API_URL", "")
        if not cloud_api_url:
            errors.append("PARKOS_CLOUD_API_URL=<unset>")

        try:
            sync_jwt_path = _require_path("PARKOS_SYNC_JWT_PATH")
        except MissingEnvError as e:
            errors.extend(e.errors)
            sync_jwt_path = None  # type: ignore[assignment]  # placeholder

        # Fail-fast: if any branch-required var is missing, surface ALL the
        # collected errors in a single MissingEnvError — never return a
        # partially-populated config.
        if errors:
            raise MissingEnvError(errors)

        return BranchConfig(
            deploy="branch",
            uuid_sucursal=uuid_sucursal,  # type: ignore[arg-type]
            db_url=db_url,
            cloud_api_url=cloud_api_url,
            jwt_key_path=jwt_key_path,  # type: ignore[arg-type]
            sync_jwt_path=sync_jwt_path,  # type: ignore[arg-type]
            sync_poll_interval_s=_optional_int("PARKOS_SYNC_POLL_INTERVAL_S", 10),
            sync_batch_size=_optional_int("PARKOS_SYNC_BATCH_SIZE", 100),
            sync_heartbeat_s=_optional_int("PARKOS_SYNC_HEARTBEAT_S", 60),
            sync_verify_interval_s=_optional_int("PARKOS_SYNC_VERIFY_INTERVAL_S", 3600),
        )

    if deploy == "cloud":
        dian_provider_url = os.environ.get("PARKOS_DIAN_PROVIDER_URL", "")
        if not dian_provider_url:
            errors.append("PARKOS_DIAN_PROVIDER_URL=<unset>")

        try:
            dian_provider_token_path = _require_path("PARKOS_DIAN_PROVIDER_TOKEN_PATH")
        except MissingEnvError as e:
            errors.extend(e.errors)
            dian_provider_token_path = None  # type: ignore[assignment]  # placeholder

        if errors:
            raise MissingEnvError(errors)

        return CloudConfig(
            deploy="cloud",
            db_url=db_url,
            jwt_key_path=jwt_key_path,  # type: ignore[arg-type]
            dian_provider_url=dian_provider_url,
            dian_provider_token_path=dian_provider_token_path,  # type: ignore[arg-type]
            dian_timeout_s=_optional_int("PARKOS_DIAN_TIMEOUT_S", 30),
            dian_retry_max=_optional_int("PARKOS_DIAN_RETRY_MAX", 3),
        )

    # deploy was missing or invalid; ``errors`` carries at least the
    # ``PARKOS_DEPLOY`` line, possibly more (DB URL / JWT path).
    raise MissingEnvError(errors)


def main() -> int:
    """CLI entrypoint: validate env and exit 0 on ok, 2 on failure.

    Used by ``parkos_cli_doctor`` (T-PR8-18) and called directly from
    container entrypoints for fail-fast diagnostics.
    """
    try:
        cfg = load_config()
    except MissingEnvError as e:
        sys.stderr.write("env validation failed:\n")
        for err in e.errors:
            sys.stderr.write(f"  - {err}\n")
        return 2
    print(f"env ok: deploy={cfg.deploy}")
    if isinstance(cfg, BranchConfig):
        # isinstance narrows the union for every type checker; runtime
        # deploy string would also work but is fragile under refactoring.
        print(f"  uuid_sucursal={cfg.uuid_sucursal}")
        print(f"  cloud_api_url={cfg.cloud_api_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "BranchConfig",
    "CloudConfig",
    "MissingEnvError",
    "load_config",
    "main",
]