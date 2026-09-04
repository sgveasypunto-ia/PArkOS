"""Unit tests for ``sync.jwt_manager`` (PR9a, T-PR9-04).

Covers the JWT rotation path (via ``httpx.MockTransport``) + the 401
response classifier:

- ``rotate`` happy path: writes the new JWT to ``jwt_path`` with mode
  ``0600`` (POSIX-only enforcement — Windows is best-effort per
  ``os.chmod`` semantics).
- ``rotate`` raises on HTTP error (cloud rejected).
- ``on_401_response`` classifier:
  - ``{"error": "sync_jwt_revoked"}`` → emits the marker file + raises
    ``SystemExit(1)`` (orchestrator restart-loop surfaces the issue).
  - ``{"error": "sync_jwt_expired"}`` → ``JwtAction.RETRY_NEW_JWT``
    (caller calls ``rotate`` then retries).
  - ``{"error": "sync_jwt_invalid"}`` → ``JwtAction.RETRY_NEW_JWT``.
  - Non-JSON body → ``JwtAction.HALT_REVOKED`` (defensive default).
- ``get_current_jwt`` reads from disk; missing file → ``FileNotFoundError``.
- Marker file naming is consistent so the supervisor can locate it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from parkos_core.sync.jwt_manager import (
    BRANCH_OFFLINE_MARKER_NAME,
    JwtAction,
    JwtManager,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client_factory(transport: httpx.MockTransport) -> type[httpx.AsyncClient]:
    """Return an ``httpx.AsyncClient`` factory bound to the given transport.

    Production ``JwtManager.rotate`` does
    ``async with self._client_factory(...) as client`` — the factory
    must accept the same kwargs (``timeout=...``). We wrap the
    MockTransport into a class so the ``async with`` context-manager
    protocol resolves cleanly.
    """

    def _factory(*args, **kwargs):
        # Inject the MockTransport — httpx.AsyncClient honors ``transport=``
        # directly so we don't need a custom HTTPConnectionPool.
        kwargs.setdefault("transport", transport)
        return httpx.AsyncClient(*args, **kwargs)

    # Bind at instance-creation time (callable returning the AsyncClient).
    return _factory  # type: ignore[return-value]


@pytest.fixture
def jwt_file(tmp_path: Path) -> Path:
    """Write a fake JWT to a temp file."""
    p = tmp_path / "sync.jwt"
    p.write_text("old-jwt", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# get_current_jwt
# ---------------------------------------------------------------------------


class TestGetCurrentJwt:
    """``JwtManager.get_current_jwt`` — disk read."""

    def test_reads_jwt_from_disk(self, jwt_file: Path) -> None:
        manager = JwtManager(jwt_file)
        assert manager.get_current_jwt() == "old-jwt"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        p = tmp_path / "sync.jwt"
        p.write_text("  new-jwt\n", encoding="utf-8")
        manager = JwtManager(p)
        assert manager.get_current_jwt() == "new-jwt"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        manager = JwtManager(tmp_path / "missing.jwt")
        with pytest.raises(FileNotFoundError):
            manager.get_current_jwt()


# ---------------------------------------------------------------------------
# rotate
# ---------------------------------------------------------------------------


class TestRotate:
    """``JwtManager.rotate`` — POST /sync/rotate-jwt + persist."""

    @pytest.mark.asyncio
    async def test_rotate_writes_new_jwt_to_disk(self, jwt_file: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"jwt": "new-jwt"})

        manager = JwtManager(
            jwt_file,
            base_url="http://test",
            client_factory=_mock_client_factory(httpx.MockTransport(handler)),
        )
        new_jwt = await manager.rotate()
        assert new_jwt == "new-jwt"
        assert jwt_file.read_text(encoding="utf-8") == "new-jwt"  # noqa: ASYNC240

    @pytest.mark.asyncio
    async def test_rotate_preserves_old_jwt_when_called_again(
        self, jwt_file: Path
    ) -> None:
        """Verify the manager reads the latest JWT from disk on each call.

        (Production behaviour: ``get_current_jwt`` reads from disk every
        time, so a rotated JWT takes effect immediately on the next
        ``rotate`` call without re-instantiating the manager.)
        """

        def handler(request: httpx.Request) -> httpx.Response:
            # The handler always returns ``rotated-jwt-N`` based on the
            # current ``Authorization`` header (proves we read fresh).
            auth = request.headers.get("Authorization", "")
            if auth == "Bearer old-jwt":
                return httpx.Response(200, json={"jwt": "rotated-1"})
            if auth == "Bearer rotated-1":
                return httpx.Response(200, json={"jwt": "rotated-2"})
            raise AssertionError(f"unexpected auth header: {auth!r}")

        manager = JwtManager(
            jwt_file,
            base_url="http://test",
            client_factory=_mock_client_factory(httpx.MockTransport(handler)),
        )
        await manager.rotate()
        assert jwt_file.read_text(encoding="utf-8") == "rotated-1"  # noqa: ASYNC240
        await manager.rotate()
        assert jwt_file.read_text(encoding="utf-8") == "rotated-2"  # noqa: ASYNC240

    @pytest.mark.asyncio
    async def test_rotate_raises_on_4xx(self, jwt_file: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "sync_jwt_revoked"})

        manager = JwtManager(
            jwt_file,
            base_url="http://test",
            client_factory=_mock_client_factory(httpx.MockTransport(handler)),
        )
        with pytest.raises(httpx.HTTPStatusError):
            await manager.rotate()
        # Original JWT unchanged on failure.
        assert jwt_file.read_text(encoding="utf-8") == "old-jwt"  # noqa: ASYNC240

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        sys.platform.startswith("win"), reason="POSIX 0600 mode not enforced"
    )
    async def test_rotate_sets_file_mode_0600_on_posix(self, jwt_file: Path) -> None:
        """``rotate`` writes the new JWT with mode ``0600`` on POSIX."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"jwt": "new-jwt"})

        manager = JwtManager(
            jwt_file,
            base_url="http://test",
            client_factory=_mock_client_factory(httpx.MockTransport(handler)),
        )
        await manager.rotate()
        mode = jwt_file.stat().st_mode & 0o777  # noqa: ASYNC240
        assert mode == 0o600


# ---------------------------------------------------------------------------
# on_401_response
# ---------------------------------------------------------------------------


class TestOn401Response:
    """``JwtManager.on_401_response`` — JSON error classifier."""

    @pytest.mark.asyncio
    async def test_sync_jwt_revoked_halts(
        self, jwt_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``sync_jwt_revoked`` → marker file + ``sys.exit(1)``."""

        def fake_exit(code: int) -> None:
            raise SystemExit(code)

        monkeypatch.setattr("parkos_core.sync.jwt_manager.sys.exit", fake_exit)

        manager = JwtManager(jwt_file)
        response = httpx.Response(401, json={"error": "sync_jwt_revoked"})
        with pytest.raises(SystemExit):
            await manager.on_401_response(response)

        # Marker file written.
        marker = jwt_file.parent / BRANCH_OFFLINE_MARKER_NAME
        assert marker.exists()

    @pytest.mark.asyncio
    async def test_sync_jwt_expired_returns_retry_action(
        self, jwt_file: Path
    ) -> None:
        """``sync_jwt_expired`` → ``JwtAction.RETRY_NEW_JWT``."""
        manager = JwtManager(jwt_file)
        response = httpx.Response(401, json={"error": "sync_jwt_expired"})
        action = await manager.on_401_response(response)
        assert action == JwtAction.RETRY_NEW_JWT
        # No marker for the retry case.
        marker = jwt_file.parent / BRANCH_OFFLINE_MARKER_NAME
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_sync_jwt_invalid_returns_retry_action(
        self, jwt_file: Path
    ) -> None:
        """``sync_jwt_invalid`` → ``JwtAction.RETRY_NEW_JWT`` (defensive)."""
        manager = JwtManager(jwt_file)
        response = httpx.Response(401, json={"error": "sync_jwt_invalid"})
        action = await manager.on_401_response(response)
        assert action == JwtAction.RETRY_NEW_JWT

    @pytest.mark.asyncio
    async def test_unknown_error_halts(self, jwt_file: Path) -> None:
        """Unknown 401 error code → ``JwtAction.HALT_REVOKED`` (defensive)."""
        manager = JwtManager(jwt_file)
        response = httpx.Response(401, json={"error": "something_else"})
        action = await manager.on_401_response(response)
        assert action == JwtAction.HALT_REVOKED

    @pytest.mark.asyncio
    async def test_non_json_body_halts(self, jwt_file: Path) -> None:
        """Non-JSON body → ``JwtAction.HALT_REVOKED`` (defensive default)."""
        manager = JwtManager(jwt_file)
        response = httpx.Response(401, text="not json")
        action = await manager.on_401_response(response)
        assert action == JwtAction.HALT_REVOKED


# ---------------------------------------------------------------------------
# Marker file
# ---------------------------------------------------------------------------


def test_marker_filename_is_stable() -> None:
    """The marker filename is part of the supervisor contract."""
    assert BRANCH_OFFLINE_MARKER_NAME == ".branch_offline_reauth_required"


# ---------------------------------------------------------------------------
# Constructor + base URL normalization
# ---------------------------------------------------------------------------


def test_base_url_trailing_slash_stripped(jwt_file: Path) -> None:
    """``base_url`` normalization: ``http://cloud/`` → ``http://cloud``."""
    manager = JwtManager(jwt_file, base_url="http://cloud/")
    assert manager.base_url == "http://cloud"


def test_base_url_falls_back_to_env(
    jwt_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no ``base_url`` is passed, the manager reads ``PARKOS_CLOUD_API_URL``."""
    monkeypatch.setenv("PARKOS_CLOUD_API_URL", "http://cloud-from-env")
    manager = JwtManager(jwt_file)
    assert manager.base_url == "http://cloud-from-env"


def test_jwt_path_is_coerced_to_path(jwt_file: Path) -> None:
    """``jwt_path`` accepts strings or Path objects (defensive)."""
    manager = JwtManager(str(jwt_file))  # type: ignore[arg-type]
    assert isinstance(manager.jwt_path, Path)
    assert manager.jwt_path == jwt_file


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_jwt_action_values_are_strings() -> None:
    """``JwtAction`` members serialize as plain strings."""
    assert JwtAction.RETRY_NEW_JWT == "retry_new_jwt"
    assert JwtAction.HALT_REVOKED == "halt_revoked"
    assert JwtAction.HALT_EXPIRED == "halt_expired"
