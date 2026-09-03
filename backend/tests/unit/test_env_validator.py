"""Tests for ``parkos_core.runtime.env`` (T-PR8-04, design §21.2 acceptance #21-23).

12 fixtures, one per spec line in T-PR8-04:

  1. ``PARKOS_DEPLOY`` unset → ``MissingEnvError``.
  2. ``PARKOS_DEPLOY=cloud`` → ok, returns ``CloudConfig``.
  3. ``PARKOS_DEPLOY=branch`` on a context without branch-required vars →
     ``MissingEnvError`` + ``main()`` exits ``2``.
  4. ``PARKOS_SUCURSAL_UUID`` empty → ``MissingEnvError``.
  5. ``PARKOS_SUCURSAL_UUID`` malformed → ``MissingEnvError``.
  6. ``PARKOS_SUCURSAL_UUID`` is UUIDv3 (not v4) → ``MissingEnvError``.
  7. ``PARKOS_DB_URL`` unset on cloud → ``MissingEnvError``.
  8. ``PARKOS_CLOUD_API_URL`` unset on branch → ``MissingEnvError``.
  9. ``PARKOS_SYNC_JWT_PATH`` missing parent dir → ``MissingEnvError``.
 10. ``PARKOS_DIAN_PROVIDER_URL`` unset on cloud → ``MissingEnvError``.
 11. Optional int malformed → falls back to default + ``warnings.warn``.
 12. Happy path: full valid env loads the right ``BranchConfig`` and
     ``main()`` exits 0 (the same env probe ``parkos_cli_doctor`` runs).

The validator is pure stdlib — no DB, no network, no pytest plugins.
Each fixture clears every ``PARKOS_*`` env var it knows about so test
order cannot leak state across the suite.
"""
from __future__ import annotations

import uuid as uuid_lib
import warnings
from pathlib import Path

import pytest
from parkos_core.runtime.env import (
    BranchConfig,
    CloudConfig,
    MissingEnvError,
    load_config,
    main,
)

# Stable UUIDv4 (version nibble = 4) — ``uuid4()`` would also work but a
# fixed string makes the test diff friendly and the ``.version == 4``
# assertion explicit by construction.
V4_UUID = uuid_lib.UUID("11111111-2222-4322-8333-444444444444")
# Stable UUIDv3 — the version nibble is what fixture #6 checks.
V3_UUID = uuid_lib.UUID("11111111-2222-3322-8333-444444444444")

# Every PARKOS_* var the validator reads. Tests clear them all before
# setting the ones they care about — guards against env-var leakage from
# the host shell into the test (e.g. CI runners leaking PARKOS_DEPLOY).
_ALL_PARKOS_VARS: tuple[str, ...] = (
    "PARKOS_DEPLOY",
    "PARKOS_DB_URL",
    "PARKOS_JWT_KEY_PATH",
    "PARKOS_SUCURSAL_UUID",
    "PARKOS_CLOUD_API_URL",
    "PARKOS_SYNC_JWT_PATH",
    "PARKOS_DIAN_PROVIDER_URL",
    "PARKOS_DIAN_PROVIDER_TOKEN_PATH",
    "PARKOS_SYNC_POLL_INTERVAL_S",
    "PARKOS_SYNC_BATCH_SIZE",
    "PARKOS_SYNC_HEARTBEAT_S",
    "PARKOS_SYNC_VERIFY_INTERVAL_S",
    "PARKOS_DIAN_TIMEOUT_S",
    "PARKOS_DIAN_RETRY_MAX",
)


def _clear_parkos_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset every PARKOS_* var the validator reads."""
    for name in _ALL_PARKOS_VARS:
        monkeypatch.delenv(name, raising=False)


def _valid_cloud_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Minimum env for a successful cloud config."""
    _clear_parkos_env(monkeypatch)
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    monkeypatch.setenv("PARKOS_DB_URL", "postgresql+asyncpg://u:p@db:5432/parkos")
    monkeypatch.setenv("PARKOS_JWT_KEY_PATH", str(tmp_path / "jwt.key"))
    monkeypatch.setenv("PARKOS_DIAN_PROVIDER_URL", "https://dian.example.com/api")
    monkeypatch.setenv(
        "PARKOS_DIAN_PROVIDER_TOKEN_PATH", str(tmp_path / "dian.tok")
    )


def _valid_branch_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Minimum env for a successful branch config."""
    _clear_parkos_env(monkeypatch)
    monkeypatch.setenv("PARKOS_DEPLOY", "branch")
    monkeypatch.setenv("PARKOS_DB_URL", "postgresql+asyncpg://u:p@db:5432/parkos")
    monkeypatch.setenv("PARKOS_JWT_KEY_PATH", str(tmp_path / "jwt.key"))
    monkeypatch.setenv("PARKOS_SUCURSAL_UUID", str(V4_UUID))
    monkeypatch.setenv("PARKOS_CLOUD_API_URL", "https://cloud.example.com")
    monkeypatch.setenv("PARKOS_SYNC_JWT_PATH", str(tmp_path / "sync.jwt"))


# ---------------------------------------------------------------------------
# Fixture 1 — PARKOS_DEPLOY unset → MissingEnvError
# ---------------------------------------------------------------------------


def test_deploy_unset_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(1) No ``PARKOS_DEPLOY`` env var → ``MissingEnvError`` naming the var."""
    _clear_parkos_env(monkeypatch)
    # Set the rest so the only failure is PARKOS_DEPLOY itself.
    monkeypatch.setenv("PARKOS_DB_URL", "postgresql+asyncpg://u:p@db:5432/parkos")
    monkeypatch.setenv("PARKOS_JWT_KEY_PATH", str(tmp_path / "jwt.key"))

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    assert any("PARKOS_DEPLOY" in e for e in excinfo.value.errors)


# ---------------------------------------------------------------------------
# Fixture 2 — PARKOS_DEPLOY=cloud → CloudConfig
# ---------------------------------------------------------------------------


def test_deploy_cloud_returns_cloud_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(2) Valid cloud env → ``CloudConfig`` with all required fields populated."""
    _valid_cloud_env(monkeypatch, tmp_path)

    cfg = load_config()

    assert isinstance(cfg, CloudConfig)
    assert cfg.deploy == "cloud"
    assert cfg.db_url == "postgresql+asyncpg://u:p@db:5432/parkos"
    assert cfg.jwt_key_path == tmp_path / "jwt.key"
    assert cfg.dian_provider_url == "https://dian.example.com/api"
    assert cfg.dian_provider_token_path == tmp_path / "dian.tok"
    # Defaults for the two cloud-only optional ints.
    assert cfg.dian_timeout_s == 30
    assert cfg.dian_retry_max == 3


# ---------------------------------------------------------------------------
# Fixture 3 — PARKOS_DEPLOY=branch on a context missing branch vars
# ---------------------------------------------------------------------------


def test_branch_deploy_without_branch_vars_raises_and_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """(3) Selecting branch deploy on a context that only has shared vars →
    ``MissingEnvError`` listing every missing branch-required var, and
    ``main()`` exits ``2`` with the same error names on stderr.
    """
    _clear_parkos_env(monkeypatch)
    monkeypatch.setenv("PARKOS_DEPLOY", "branch")
    # Only the shared (always-required) vars are set; branch-required vars
    # (SUCURSAL_UUID, CLOUD_API_URL, SYNC_JWT_PATH) are all absent.
    monkeypatch.setenv("PARKOS_DB_URL", "postgresql+asyncpg://u:p@db:5432/parkos")
    monkeypatch.setenv("PARKOS_JWT_KEY_PATH", str(tmp_path / "jwt.key"))

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    msg = "; ".join(excinfo.value.errors)
    assert "PARKOS_SUCURSAL_UUID" in msg
    assert "PARKOS_CLOUD_API_URL" in msg
    assert "PARKOS_SYNC_JWT_PATH" in msg

    # Same scenario via the CLI entrypoint — exit code 2 + stderr names the
    # offending vars (this is the path an entrypoint hits at container boot).
    assert main() == 2
    captured = capsys.readouterr()
    assert "env validation failed" in captured.err
    assert "PARKOS_SUCURSAL_UUID" in captured.err


# ---------------------------------------------------------------------------
# Fixture 4 — PARKOS_SUCURSAL_UUID empty
# ---------------------------------------------------------------------------


def test_sucursal_uuid_empty_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(4) ``PARKOS_SUCURSAL_UUID=''`` → ``MissingEnvError`` (treated as unset)."""
    _valid_branch_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PARKOS_SUCURSAL_UUID", "")

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    assert any("PARKOS_SUCURSAL_UUID" in e for e in excinfo.value.errors)


# ---------------------------------------------------------------------------
# Fixture 5 — PARKOS_SUCURSAL_UUID malformed
# ---------------------------------------------------------------------------


def test_sucursal_uuid_malformed_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(5) ``PARKOS_SUCURSAL_UUID='not-a-uuid'`` → ``MissingEnvError`` naming the cause."""
    _valid_branch_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PARKOS_SUCURSAL_UUID", "not-a-uuid")

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    msg = "; ".join(excinfo.value.errors)
    assert "PARKOS_SUCURSAL_UUID" in msg
    assert "not a UUID" in msg


# ---------------------------------------------------------------------------
# Fixture 6 — PARKOS_SUCURSAL_UUID is UUIDv3 (not v4)
# ---------------------------------------------------------------------------


def test_sucursal_uuid_v3_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(6) ``PARKOS_SUCURSAL_UUID`` parses as UUID but is v3 → ``MissingEnvError``
    with an explicit ``UUIDv4`` mention in the message.
    """
    _valid_branch_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PARKOS_SUCURSAL_UUID", str(V3_UUID))

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    msg = "; ".join(excinfo.value.errors)
    assert "PARKOS_SUCURSAL_UUID" in msg
    assert "UUIDv4" in msg


# ---------------------------------------------------------------------------
# Fixture 7 — PARKOS_DB_URL unset on cloud
# ---------------------------------------------------------------------------


def test_db_url_unset_on_cloud_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(7) ``PARKOS_DB_URL`` missing on a cloud deploy → ``MissingEnvError``."""
    _clear_parkos_env(monkeypatch)
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    monkeypatch.setenv("PARKOS_JWT_KEY_PATH", str(tmp_path / "jwt.key"))
    monkeypatch.setenv("PARKOS_DIAN_PROVIDER_URL", "https://dian.example.com/api")
    monkeypatch.setenv(
        "PARKOS_DIAN_PROVIDER_TOKEN_PATH", str(tmp_path / "dian.tok")
    )
    # Deliberately omit PARKOS_DB_URL.

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    assert any("PARKOS_DB_URL" in e for e in excinfo.value.errors)


# ---------------------------------------------------------------------------
# Fixture 8 — PARKOS_CLOUD_API_URL unset on branch
# ---------------------------------------------------------------------------


def test_cloud_api_url_unset_on_branch_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(8) Branch deploy without ``PARKOS_CLOUD_API_URL`` → ``MissingEnvError``."""
    _clear_parkos_env(monkeypatch)
    monkeypatch.setenv("PARKOS_DEPLOY", "branch")
    monkeypatch.setenv("PARKOS_DB_URL", "postgresql+asyncpg://u:p@db:5432/parkos")
    monkeypatch.setenv("PARKOS_JWT_KEY_PATH", str(tmp_path / "jwt.key"))
    monkeypatch.setenv("PARKOS_SUCURSAL_UUID", str(V4_UUID))
    monkeypatch.setenv("PARKOS_SYNC_JWT_PATH", str(tmp_path / "sync.jwt"))
    # Deliberately omit PARKOS_CLOUD_API_URL.

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    assert any("PARKOS_CLOUD_API_URL" in e for e in excinfo.value.errors)


# ---------------------------------------------------------------------------
# Fixture 9 — PARKOS_SYNC_JWT_PATH missing parent dir
# ---------------------------------------------------------------------------


def test_sync_jwt_path_missing_parent_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(9) ``PARKOS_SYNC_JWT_PATH`` points under a directory that doesn't
    exist → ``MissingEnvError`` (the validator rejects the env var before
    any I/O attempt, so the entrypoint fails fast).
    """
    _valid_branch_env(monkeypatch, tmp_path)
    missing_dir = tmp_path / "does_not_exist" / "sync.jwt"
    monkeypatch.setenv("PARKOS_SYNC_JWT_PATH", str(missing_dir))

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    msg = "; ".join(excinfo.value.errors)
    assert "PARKOS_SYNC_JWT_PATH" in msg
    assert "parent dir" in msg


# ---------------------------------------------------------------------------
# Fixture 10 — PARKOS_DIAN_PROVIDER_URL unset on cloud
# ---------------------------------------------------------------------------


def test_dian_provider_url_unset_on_cloud_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(10) Cloud deploy without ``PARKOS_DIAN_PROVIDER_URL`` → ``MissingEnvError``."""
    _clear_parkos_env(monkeypatch)
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    monkeypatch.setenv("PARKOS_DB_URL", "postgresql+asyncpg://u:p@db:5432/parkos")
    monkeypatch.setenv("PARKOS_JWT_KEY_PATH", str(tmp_path / "jwt.key"))
    monkeypatch.setenv(
        "PARKOS_DIAN_PROVIDER_TOKEN_PATH", str(tmp_path / "dian.tok")
    )
    # Deliberately omit PARKOS_DIAN_PROVIDER_URL.

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    assert any("PARKOS_DIAN_PROVIDER_URL" in e for e in excinfo.value.errors)


# ---------------------------------------------------------------------------
# Fixture 11 — optional int malformed → falls back to default + warn
# ---------------------------------------------------------------------------


def test_optional_int_malformed_falls_back_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """(11) Two malformed optional ints → each falls back to its default
    AND emits a ``UserWarning`` naming the offending var (per spec §21.2
    acceptance #11 — never crash on a malformed tuning value).
    """
    _valid_cloud_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PARKOS_DIAN_TIMEOUT_S", "not-a-number")
    monkeypatch.setenv("PARKOS_DIAN_RETRY_MAX", "still-not-a-number")

    with warnings.catch_warnings(record=True) as caught:
        # Make sure the warning is actually recorded (the validator calls
        # ``warnings.warn`` which honours the current filter).
        warnings.simplefilter("always")
        cfg = load_config()

    # Defaults applied.
    assert cfg.dian_timeout_s == 30
    assert cfg.dian_retry_max == 3

    # One warning per malformed int, each naming the var.
    relevant = [
        w
        for w in caught
        if "PARKOS_DIAN_TIMEOUT_S" in str(w.message)
        or "PARKOS_DIAN_RETRY_MAX" in str(w.message)
    ]
    assert len(relevant) == 2, (
        f"expected 2 warnings (one per malformed int); got {len(relevant)}: "
        f"{[str(w.message) for w in caught]}"
    )


# ---------------------------------------------------------------------------
# Fixture 12 — happy path: full env loads correctly + main() exits 0
# ---------------------------------------------------------------------------


def test_branch_happy_path_full_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """(12) Doctor happy path: every required + optional var set → returns
    a fully-populated ``BranchConfig`` and ``main()`` exits ``0`` with the
    diagnostic summary on stdout (what ``parkos_cli_doctor`` reads to set
    its ``env_status`` field).
    """
    _valid_branch_env(monkeypatch, tmp_path)
    # Override every optional int so we also prove they're honored.
    monkeypatch.setenv("PARKOS_SYNC_POLL_INTERVAL_S", "5")
    monkeypatch.setenv("PARKOS_SYNC_BATCH_SIZE", "250")
    monkeypatch.setenv("PARKOS_SYNC_HEARTBEAT_S", "30")
    monkeypatch.setenv("PARKOS_SYNC_VERIFY_INTERVAL_S", "1800")

    cfg = load_config()

    # Type + identity-critical fields.
    assert isinstance(cfg, BranchConfig)
    assert cfg.deploy == "branch"
    assert cfg.uuid_sucursal == V4_UUID
    assert cfg.db_url == "postgresql+asyncpg://u:p@db:5432/parkos"
    assert cfg.cloud_api_url == "https://cloud.example.com"
    assert cfg.jwt_key_path == tmp_path / "jwt.key"
    assert cfg.sync_jwt_path == tmp_path / "sync.jwt"
    # Optional ints honored (not the defaults).
    assert cfg.sync_poll_interval_s == 5
    assert cfg.sync_batch_size == 250
    assert cfg.sync_heartbeat_s == 30
    assert cfg.sync_verify_interval_s == 1800

    # CLI entrypoint succeeds and prints the same env probe.
    assert main() == 0
    captured = capsys.readouterr()
    assert "env ok" in captured.out
    assert f"uuid_sucursal={V4_UUID}" in captured.out
    assert captured.err == ""


# ---------------------------------------------------------------------------
# Defensive: ``MissingEnvError.errors`` carries every offender at once.
# ---------------------------------------------------------------------------


def test_missing_env_error_lists_all_offenders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When several vars are missing the validator must surface ALL of them
    in ``MissingEnvError.errors`` (collect-don't-fail-fast semantics) so
    the operator only has to fix the env once.
    """
    _clear_parkos_env(monkeypatch)
    # Only deploy is set; PARKOS_DB_URL, PARKOS_JWT_KEY_PATH, and the
    # cloud-only DIAN_PROVIDER_URL are all missing simultaneously.
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")

    with pytest.raises(MissingEnvError) as excinfo:
        load_config()

    errors = excinfo.value.errors
    assert any("PARKOS_DB_URL" in e for e in errors)
    assert any("PARKOS_JWT_KEY_PATH" in e for e in errors)
    assert any("PARKOS_DIAN_PROVIDER_URL" in e for e in errors)
    # At least the three missing vars, possibly more (parent-dir check
    # could add a fourth if it ran — it does run via _require_path, so
    # we expect 3+ entries).
    assert len(errors) >= 3