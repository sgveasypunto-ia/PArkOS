"""test_dual_protocol.py — T-PR11-003 acceptance (REQ-CUT-003, REQ-CUT-004).

Covers both the pure response builder
(``sync.cutover.dual_protocol.build_sync_hello_response``) and the
``GET /sync/hello`` endpoint end to end (no DB, no auth — matches the
endpoint's own no-session, no-JWT signature).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from parkos_core.api.v1.sync_router import router as sync_router_obj
from parkos_core.runtime import engine_flag
from parkos_core.sync.cutover.dual_protocol import (
    BRANCH_CACHE_TTL_SECONDS,
    DEFAULT_MIN_BRANCH_VERSION,
    GRACE_PERIOD_DAYS,
    build_sync_hello_response,
)


class TestBuildSyncHelloResponse:
    def test_legacy_engine_reports_legacy_with_null_grace_until(self) -> None:
        result = build_sync_hello_response(engine=engine_flag.EngineMode.LEGACY)
        assert result.protocol_version == "legacy"
        assert result.grace_until is None

    @pytest.mark.parametrize(
        "mode",
        [engine_flag.EngineMode.CATALOG_ADMIN, engine_flag.EngineMode.CATALOG_DIAN],
    )
    def test_cloud_internal_staging_modes_still_report_legacy_to_branches(
        self, mode: engine_flag.EngineMode
    ) -> None:
        """Stages 1-2 (catalog_admin/catalog_dian) are cloud-internal — a
        branch still sees 'legacy' until stage 3 (REQ-CUT-006)."""
        result = build_sync_hello_response(engine=mode)
        assert result.protocol_version == "legacy"
        assert result.grace_until is None

    @pytest.mark.parametrize(
        "mode",
        [engine_flag.EngineMode.CATALOG, engine_flag.EngineMode.CATALOG_BRANCH],
    )
    def test_catalog_engine_reports_catalog_with_14_day_grace(
        self, mode: engine_flag.EngineMode
    ) -> None:
        now = datetime(2026, 9, 24, 0, 0, 0, tzinfo=UTC)
        result = build_sync_hello_response(engine=mode, now=now)
        assert result.protocol_version == "catalog"
        expected = (now + timedelta(days=GRACE_PERIOD_DAYS)).isoformat()
        assert result.grace_until == expected
        assert GRACE_PERIOD_DAYS == 14

    def test_min_branch_version_defaults_and_overrides(self) -> None:
        default_result = build_sync_hello_response(engine=engine_flag.EngineMode.CATALOG)
        assert default_result.min_branch_version == DEFAULT_MIN_BRANCH_VERSION

        overridden = build_sync_hello_response(
            engine=engine_flag.EngineMode.CATALOG, min_branch_version="2.0.0"
        )
        assert overridden.min_branch_version == "2.0.0"

    def test_catalog_revision_reads_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PARKOS_CATALOG_REVISION", "abc1234")
        result = build_sync_hello_response(engine=engine_flag.EngineMode.LEGACY)
        assert result.catalog_revision == "abc1234"

    def test_catalog_revision_defaults_to_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PARKOS_CATALOG_REVISION", raising=False)
        result = build_sync_hello_response(engine=engine_flag.EngineMode.LEGACY)
        assert result.catalog_revision == "unknown"

    def test_branch_cache_ttl_is_300s(self) -> None:
        assert BRANCH_CACHE_TTL_SECONDS == 300


class TestSyncHelloEndpoint:
    @pytest.fixture
    def app(self) -> FastAPI:
        application = FastAPI()
        application.include_router(sync_router_obj)
        return application

    def test_hello_requires_no_auth_and_matches_shape(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-CUT-004: response shape exactly
        {protocol_version, min_branch_version, grace_until, catalog_revision}."""
        monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
        engine_flag._reset_cache_for_tests()

        c = TestClient(app)
        resp = c.get("/sync/hello")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == {
            "protocol_version",
            "min_branch_version",
            "grace_until",
            "catalog_revision",
        }
        assert body["protocol_version"] == "catalog"
        assert body["grace_until"] is not None

    def test_hello_reports_null_grace_until_on_legacy(
        self, app: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PARKOS_SYNC_ENGINE", "legacy")
        engine_flag._reset_cache_for_tests()

        c = TestClient(app)
        resp = c.get("/sync/hello")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["protocol_version"] == "legacy"
        assert body["grace_until"] is None
