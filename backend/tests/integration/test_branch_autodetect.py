"""test_branch_autodetect.py — T-PR12-007 acceptance (REQ-CUT-005).

Req: REQ-CUT-005 · Design: §8 · Depends on: T-PR11-003.

Exercises all 4 rows of REQ-CUT-005's condition table
(``openspec/changes/sync-overhaul/specs/cutover-migration.md``):

| Condition | Applier |
|---|---|
| ``protocol_version == "legacy"`` | Legacy applier |
| catalog + ``branch_version >= min_branch_version`` | Catalog (``SyncMotor``) |
| catalog + ``branch_version < min_branch_version`` | Legacy + ``WARN catalog_too_new`` |
| HTTP error / timeout | Legacy (fail-safe) |

Uses a real Postgres container only because ``SyncSucursalWorker``'s
constructor requires a session; ``/sync/hello`` itself is mocked at the
``SyncHttpClient`` boundary (no real cloud process in this test).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
from parkos_core.jobs.sync_sucursal import ApplierMode, SyncSucursalWorker
from parkos_core.sync.transport import HelloResponse
from sqlalchemy.ext.asyncio import async_sessionmaker


def _worker(session, tmp_path, *, branch_version: str = "1.5.0") -> SyncSucursalWorker:
    jwt_path = tmp_path / "sync.jwt"
    jwt_path.write_text("fake-jwt", encoding="utf-8")
    return SyncSucursalWorker(
        jwt_path=jwt_path,
        base_url="http://cloud",
        session=session,
        branch_version=branch_version,
    )


async def test_row1_legacy_protocol_selects_legacy_applier(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        worker = _worker(session, tmp_path)
        worker._http_client = MagicMock()
        worker._http_client.hello = AsyncMock(
            return_value=HelloResponse(
                status=200,
                protocol_version="legacy",
                min_branch_version="1.5.0",
                grace_until=None,
                catalog_revision="abc123",
            )
        )

        mode = await worker._detect_applier_mode()
        assert mode is ApplierMode.LEGACY


async def test_row2_catalog_protocol_with_sufficient_version_selects_catalog(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        worker = _worker(session, tmp_path, branch_version="1.6.0")
        worker._http_client = MagicMock()
        worker._http_client.hello = AsyncMock(
            return_value=HelloResponse(
                status=200,
                protocol_version="catalog",
                min_branch_version="1.5.0",
                grace_until="2099-01-01T00:00:00+00:00",
                catalog_revision="abc123",
            )
        )

        mode = await worker._detect_applier_mode()
        assert mode is ApplierMode.CATALOG


async def test_row3_catalog_protocol_with_stale_version_falls_back_to_legacy(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        worker = _worker(session, tmp_path, branch_version="1.4.0")
        worker._http_client = MagicMock()
        worker._http_client.hello = AsyncMock(
            return_value=HelloResponse(
                status=200,
                protocol_version="catalog",
                min_branch_version="1.5.0",
                grace_until="2099-01-01T00:00:00+00:00",
                catalog_revision="abc123",
            )
        )

        mode = await worker._detect_applier_mode()
        assert mode is ApplierMode.LEGACY


async def test_row4_http_error_fails_safe_to_legacy(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        worker = _worker(session, tmp_path)
        worker._http_client = MagicMock()
        worker._http_client.hello = AsyncMock(side_effect=httpx.ConnectTimeout("timed out"))

        mode = await worker._detect_applier_mode()
        assert mode is ApplierMode.LEGACY


async def test_row4_transport_os_error_fails_safe_to_legacy(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        worker = _worker(session, tmp_path)
        worker._http_client = MagicMock()
        worker._http_client.hello = AsyncMock(side_effect=OSError("dns blew up"))

        mode = await worker._detect_applier_mode()
        assert mode is ApplierMode.LEGACY


async def test_decision_is_cached_for_the_ttl_window(
    pg_engine, alembic_upgrade, tmp_path
) -> None:
    """A second call within the TTL window must NOT call /sync/hello again."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        worker = _worker(session, tmp_path)
        worker._http_client = MagicMock()
        worker._http_client.hello = AsyncMock(
            return_value=HelloResponse(
                status=200,
                protocol_version="legacy",
                min_branch_version="1.5.0",
                grace_until=None,
                catalog_revision="abc123",
            )
        )

        first = await worker._detect_applier_mode()
        second = await worker._detect_applier_mode()
        assert first is ApplierMode.LEGACY
        assert second is ApplierMode.LEGACY
        worker._http_client.hello.assert_awaited_once()
