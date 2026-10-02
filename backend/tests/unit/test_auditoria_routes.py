"""Unit tests for ``api/v1/auditoria.py`` (HU-F20.4).

Mirrors the dependency-override pattern used throughout this suite
(``test_admin_sync_hu_f19_1.py``'s ad hoc router-only app,
``test_audit_log_endpoint.py``'s issuer-dep override) but goes one step
further and ALSO overrides the ``audit_read`` permission dependency --
per the task brief, these are unit tests of the HANDLERS, not of
``requires_issuer``/``require_permission`` themselves (those are covered by
``test_jwt_issuer_guard.py`` / ``test_permissions_dependency.py``). The
business-logic dependencies the handlers call directly
(``extract_sucursales_permitidas_fresh``, ``repo.log_transaccional.*``,
``verify_chain_for_spec``) are monkeypatched so every test runs with NO
real Postgres connection -- fast, deterministic, no testcontainers.

The real end-to-end behaviour (real hash chains, real cross-branch auth)
is covered by ``tests/integration/test_bitacora_hu_f20_4.py``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import parkos_core.api.v1.auditoria as auditoria_module
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from parkos_core.api.deps import get_session
from parkos_core.sync.motor.verify_chain import ChainAnomaly

ACTOR_UUID = uuid_lib.uuid4()


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _build_app() -> FastAPI:
    """Mount ONLY ``auditoria.router``, auth deps bypassed."""
    app = FastAPI()
    app.include_router(auditoria_module.router, prefix="/api/v1")

    app.dependency_overrides[auditoria_module._admin_issuer_dep] = lambda: {
        "sub": str(ACTOR_UUID),
        "iss": "admin-test",
    }
    app.dependency_overrides[auditoria_module._audit_perm_dep] = lambda: None
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    return app


async def _get(app: FastAPI, url: str) -> httpx.Response:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(url)


def _row(
    *,
    uuid: uuid_lib.UUID | None = None,
    uuid_sucursal: uuid_lib.UUID | None = None,
    tabla_afectada: str | None = "ingreso",
    uuid_registro_afectado: uuid_lib.UUID | None = None,
) -> object:
    from unittest.mock import MagicMock

    row = MagicMock()
    row.uuid = uuid or uuid_lib.uuid4()
    row.timestamp_evento = _now_naive()
    row.uuid_usuario = uuid_lib.uuid4()
    row.uuid_sucursal = uuid_sucursal or uuid_lib.uuid4()
    row.uuid_referencia = None
    row.accion = "crear"
    row.tabla_afectada = tabla_afectada
    row.uuid_registro_afectado = uuid_registro_afectado or uuid_lib.uuid4()
    row.datos_anteriores = None
    row.datos_nuevos = {"x": 1}
    row.hash_anterior = "a" * 64
    row.hash_actual = "b" * 64
    return row


# ---------------------------------------------------------------------------
# GET /admin/log-transaccional
# ---------------------------------------------------------------------------


class TestListLogTransaccional:
    async def test_cross_branch_default_scopes_to_every_permitted_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        permitidas = [uuid_lib.uuid4(), uuid_lib.uuid4()]
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=permitidas),
        )
        captured: dict = {}

        async def _fake_listar(session, **kwargs):
            captured.update(kwargs)
            return [_row()]

        monkeypatch.setattr(auditoria_module.repo_audit, "listar_eventos_paginados", _fake_listar)

        app = _build_app()
        resp = await _get(app, "/api/v1/admin/log-transaccional")

        assert resp.status_code == 200, resp.text
        assert sorted(captured["uuid_sucursales"], key=str) == sorted(permitidas, key=str)
        assert captured["uuid_sucursal"] is None
        body = resp.json()
        assert len(body["items"]) == 1

    async def test_single_branch_narrows_when_permitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        branch = uuid_lib.uuid4()
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[branch, uuid_lib.uuid4()]),
        )
        captured: dict = {}

        async def _fake_listar(session, **kwargs):
            captured.update(kwargs)
            return []

        monkeypatch.setattr(auditoria_module.repo_audit, "listar_eventos_paginados", _fake_listar)

        app = _build_app()
        resp = await _get(app, f"/api/v1/admin/log-transaccional?uuid_sucursal={branch}")

        assert resp.status_code == 200, resp.text
        assert captured["uuid_sucursales"] == [branch]

    async def test_unpermitted_branch_returns_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        other_branch = uuid_lib.uuid4()
        resp = await _get(app, f"/api/v1/admin/log-transaccional?uuid_sucursal={other_branch}")

        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "unauthorized_sucursal_context"

    async def test_empty_permitidas_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[]),
        )
        app = _build_app()
        resp = await _get(app, "/api/v1/admin/log-transaccional")

        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "missing_sucursal_context"

    async def test_desde_after_hasta_returns_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        resp = await _get(
            app,
            "/api/v1/admin/log-transaccional?desde=2026-02-01&hasta=2026-01-01",
        )

        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "rango_fecha_invalido"

    async def test_invalid_cursor_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        resp = await _get(
            app, "/api/v1/admin/log-transaccional?cursor=!!!not-base64!!!"
        )

        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_cursor"


# ---------------------------------------------------------------------------
# GET /admin/log-transaccional/verify-chain
# ---------------------------------------------------------------------------


class TestVerifyChainEndpoint:
    async def test_unknown_table_returns_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        resp = await _get(
            app, "/api/v1/admin/log-transaccional/verify-chain?tabla=not_a_real_table"
        )

        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "tabla_no_verificable"

    async def test_non_verify_chain_table_returns_422(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real catalog entry that does NOT carry ``verify_chain=True``
        (e.g. ``sucursal``, a [V] table) must still 422 -- the gate is on
        the ``verify_chain`` flag, not merely "does the name resolve"."""
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        resp = await _get(
            app, "/api/v1/admin/log-transaccional/verify-chain?tabla=sucursal"
        )

        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "tabla_no_verificable"

    async def test_single_branch_calls_verify_chain_for_spec_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        branch = uuid_lib.uuid4()
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[branch]),
        )
        calls: list = []

        async def _fake_verify(session, entry, uuid_sucursal=None, min_seq=None):
            calls.append(uuid_sucursal)
            return []

        monkeypatch.setattr(auditoria_module, "verify_chain_for_spec", _fake_verify)

        app = _build_app()
        resp = await _get(
            app, f"/api/v1/admin/log-transaccional/verify-chain?uuid_sucursal={branch}"
        )

        assert resp.status_code == 200, resp.text
        assert calls == [branch]
        assert resp.json() == {"ok": True, "anomalias": []}

    async def test_omitted_branch_sweeps_every_permitted_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        branches = [uuid_lib.uuid4(), uuid_lib.uuid4(), uuid_lib.uuid4()]
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=branches),
        )
        calls: list = []

        async def _fake_verify(session, entry, uuid_sucursal=None, min_seq=None):
            calls.append(uuid_sucursal)
            return []

        monkeypatch.setattr(auditoria_module, "verify_chain_for_spec", _fake_verify)

        app = _build_app()
        resp = await _get(app, "/api/v1/admin/log-transaccional/verify-chain")

        assert resp.status_code == 200, resp.text
        # One call PER permitted branch -- never a single uuid_sucursal=None call.
        assert sorted(calls, key=str) == sorted(branches, key=str)
        assert None not in calls

    async def test_anomaly_surfaces_as_ok_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        branch = uuid_lib.uuid4()
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[branch]),
        )
        broken_uuid = uuid_lib.uuid4()
        anomaly = ChainAnomaly(
            tabla="log_transaccional",
            uuid_sucursal=branch,
            uuid=broken_uuid,
            expected="a" * 64,
            actual="0" * 64,
            seq=3,
        )

        async def _fake_verify(session, entry, uuid_sucursal=None, min_seq=None):
            return [anomaly]

        monkeypatch.setattr(auditoria_module, "verify_chain_for_spec", _fake_verify)

        app = _build_app()
        resp = await _get(
            app, f"/api/v1/admin/log-transaccional/verify-chain?uuid_sucursal={branch}"
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is False
        assert len(body["anomalias"]) == 1
        assert body["anomalias"][0]["uuid"] == str(broken_uuid)
        assert body["anomalias"][0]["actual"] == "0" * 64

    async def test_unpermitted_branch_returns_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        other_branch = uuid_lib.uuid4()
        resp = await _get(
            app, f"/api/v1/admin/log-transaccional/verify-chain?uuid_sucursal={other_branch}"
        )

        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "unauthorized_sucursal_context"


# ---------------------------------------------------------------------------
# GET /admin/log-transaccional/buscar
# ---------------------------------------------------------------------------


class TestBuscarEndpoint:
    async def test_happy_path_returns_items_scoped_to_permitidas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        permitidas = [uuid_lib.uuid4()]
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=permitidas),
        )
        captured: dict = {}

        async def _fake_buscar(session, **kwargs):
            captured.update(kwargs)
            return [_row(tabla_afectada="ingreso")]

        monkeypatch.setattr(auditoria_module.repo_audit, "buscar_prefijo", _fake_buscar)

        app = _build_app()
        resp = await _get(app, "/api/v1/admin/log-transaccional/buscar?prefijo=ing")

        assert resp.status_code == 200, resp.text
        assert captured["prefijo"] == "ing"
        assert captured["uuid_sucursales"] == permitidas
        assert captured["limit"] == 10
        assert len(resp.json()["items"]) == 1

    async def test_empty_prefijo_returns_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        resp = await _get(app, "/api/v1/admin/log-transaccional/buscar?prefijo=")

        assert resp.status_code == 422

    async def test_limit_over_ten_returns_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[uuid_lib.uuid4()]),
        )
        app = _build_app()
        resp = await _get(
            app, "/api/v1/admin/log-transaccional/buscar?prefijo=ing&limit=11"
        )

        assert resp.status_code == 422

    async def test_empty_permitidas_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            auditoria_module,
            "extract_sucursales_permitidas_fresh",
            AsyncMock(return_value=[]),
        )
        app = _build_app()
        resp = await _get(app, "/api/v1/admin/log-transaccional/buscar?prefijo=ing")

        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "missing_sucursal_context"
