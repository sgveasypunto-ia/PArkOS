"""Tests for the ``prod.resolucion_facturacion`` DIAN boundary (REQ-01, REQ-X3).

The ``resolucion-facturacion`` router is cloud-only:
``issuer_required="admin-"`` + ``permission_required="admin_resolucion_facturacion"``
(see ``api/v1/empresa.py::_ROUTER_CONFIG``). Branch operators (``operador-``
issuer) MUST NOT be able to write it.

Per the PR4 acceptance:

    curl -X POST .../resolucion-facturacion -H 'Bearer $ADMIN_JWT'    -> 201
    curl -X POST .../resolucion-facturacion -H 'Bearer $OPERADOR_JWT' -> denied

NOTE on the status code: the acceptance text says 403, but the shipped
``requires_issuer`` guard (``auth/jwt_issuer_guard.py``, PR1b) raises
``CrossIssuerError``, which is **401** (``{"error": "wrong_issuer"}``). 403 is
what the *permission* dependency raises. These tests assert the real, shipped
behaviour of the issuer guard — the cross-issuer write is denied at the 401
layer before permissions are ever evaluated.

Per the PR3/PR4 plan this ships schema-only + dependency tests (no DB). The
end-to-end HTTP test against a live server lands once testcontainers is wired
into CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from typing import Any, cast

import pytest
from fastapi import HTTPException
from parkos_core.api.deps import requires_issuer
from parkos_core.auth.tokens import issue_token
from parkos_core.schemas.empresa import (
    ResolucionFacturacionCreate,
    ResolucionFacturacionRead,
    ResolucionFacturacionUpdate,
)
from pydantic import ValidationError
from starlette.requests import Request

SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-00000000000c")
NOW = datetime(2026, 1, 1)


def _issue(issuer_prefix: str) -> str:
    """Mint a valid HS256 dev token for the given issuer prefix."""
    return issue_token(
        subject_uuid=uuid_lib.uuid4(),
        issuer=f"{issuer_prefix}cloud-001",
        claims={"rol": "test"},
        expires_in=3600,
    )


def _detail(exc: HTTPException) -> dict[str, Any]:
    """The guard's ``detail`` payload is always a ``{"error", "detail"}`` dict."""
    return cast("dict[str, Any]", exc.detail)


def _request_with(token: str | None) -> Request:
    """Build a minimal ASGI ``Request`` carrying the bearer token."""
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/empresa/resolucion-facturacion",
            "raw_path": b"/api/v1/empresa/resolucion-facturacion",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {},
        }
    )


class TestIssuerGuard:
    """``requires_issuer('admin-')`` MUST reject ``operador-`` tokens (REQ-X3)."""

    async def test_admin_token_passes(self) -> None:
        """Admin issuer passes the cloud-only guard and gets its claims back."""
        dep = requires_issuer("admin-")
        claims = await dep(_request_with(_issue("admin-")))
        assert claims["iss"].startswith("admin-")

    async def test_operador_token_rejected(self) -> None:
        """Operador issuer is denied on the DIAN cloud-only resource."""
        dep = requires_issuer("admin-")
        with pytest.raises(HTTPException) as exc_info:
            await dep(_request_with(_issue("operador-")))
        assert exc_info.value.status_code == 401
        detail = _detail(exc_info.value)
        assert detail["error"] == "wrong_issuer"
        assert "operador-" in detail["detail"]

    async def test_sync_agent_token_rejected(self) -> None:
        """Sync-agent issuer is also denied on cloud-only endpoints."""
        dep = requires_issuer("admin-")
        with pytest.raises(HTTPException) as exc_info:
            await dep(_request_with(_issue("sync-agent-")))
        assert exc_info.value.status_code == 401
        assert _detail(exc_info.value)["error"] == "wrong_issuer"

    async def test_missing_token_rejected(self) -> None:
        """No Authorization header at all is an invalid token (401)."""
        dep = requires_issuer("admin-")
        with pytest.raises(HTTPException) as exc_info:
            await dep(_request_with(None))
        assert exc_info.value.status_code == 401
        assert _detail(exc_info.value)["error"] == "invalid_token"

    async def test_admin_or_operador_accepts_both(self) -> None:
        """``requires_issuer('admin-', 'operador-')`` (the replicated-table config)."""
        dep = requires_issuer("admin-", "operador-")
        admin_claims = await dep(_request_with(_issue("admin-")))
        op_claims = await dep(_request_with(_issue("operador-")))
        assert admin_claims["iss"].startswith("admin-")
        assert op_claims["iss"].startswith("operador-")

    async def test_admin_or_operador_still_rejects_sync_agent(self) -> None:
        """``requires_issuer('admin-', 'operador-')`` still denies sync-agent."""
        dep = requires_issuer("admin-", "operador-")
        with pytest.raises(HTTPException) as exc_info:
            await dep(_request_with(_issue("sync-agent-")))
        assert exc_info.value.status_code == 401


class TestRouterConfigIsCloudOnly:
    """The router table itself pins the DIAN boundary (REQ-X3)."""

    def test_resolucion_facturacion_is_admin_only(self) -> None:
        from parkos_core.api.v1.empresa import _ROUTER_CONFIG

        issuer, perm = _ROUTER_CONFIG["resolucion-facturacion"]
        assert issuer == "admin-"
        assert perm == "admin_resolucion_facturacion"

    def test_replicated_tables_allow_operador(self) -> None:
        """Contrast: replicated tables DO allow the branch operator issuer."""
        from parkos_core.api.v1.empresa import _ROUTER_CONFIG

        issuer, _ = _ROUTER_CONFIG["tarifas-sucursal"]
        assert "operador-" in issuer


class TestCreateSchemaEnforcesDIANBoundary:
    """``ResolucionFacturacionCreate`` MUST reject client-supplied server fields."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("prefijo", "SETP"),
            ("rango_desde", 1),
            ("rango_hasta", 1000),
        ],
    )
    def test_create_rejects_server_assigned_field(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            ResolucionFacturacionCreate(
                uuid_sucursal=SUCURSAL_UUID,
                numero_resolucion="1876",
                fecha_resolucion=date(2026, 1, 1),
                fecha_inicio_vigencia=date(2026, 1, 1),
                fecha_fin_vigencia=date(2027, 1, 1),
                **{field: value},
            )

    def test_create_accepts_valid_payload(self) -> None:
        c = ResolucionFacturacionCreate(
            uuid_sucursal=SUCURSAL_UUID,
            numero_resolucion="1876",
            fecha_resolucion=date(2026, 1, 1),
            fecha_inicio_vigencia=date(2026, 1, 1),
            fecha_fin_vigencia=date(2027, 1, 1),
        )
        assert c.numero_resolucion == "1876"
        assert c.fecha_inicio_vigencia == date(2026, 1, 1)
        assert not hasattr(c, "prefijo")

    def test_create_coerces_iso_date_strings(self) -> None:
        """ISO-8601 strings coerce to ``datetime.date`` (JSON bodies)."""
        c = ResolucionFacturacionCreate(
            uuid_sucursal=SUCURSAL_UUID,
            numero_resolucion="1876",
            fecha_resolucion="2026-01-01",
            fecha_inicio_vigencia="2026-01-01",
            fecha_fin_vigencia="2027-01-01",
        )
        assert c.fecha_resolucion == date(2026, 1, 1)
        assert c.fecha_fin_vigencia == date(2027, 1, 1)

    @pytest.mark.parametrize("bad", ["not-a-date", 12345, ""])
    def test_create_rejects_bad_date(self, bad: object) -> None:
        with pytest.raises(ValidationError):
            ResolucionFacturacionCreate(
                uuid_sucursal=SUCURSAL_UUID,
                numero_resolucion="1876",
                fecha_resolucion=bad,
                fecha_inicio_vigencia=date(2026, 1, 1),
                fecha_fin_vigencia=date(2027, 1, 1),
            )

    def test_create_requires_uuid_sucursal(self) -> None:
        with pytest.raises(ValidationError):
            ResolucionFacturacionCreate(
                numero_resolucion="1876",
                fecha_resolucion=date(2026, 1, 1),
                fecha_inicio_vigencia=date(2026, 1, 1),
                fecha_fin_vigencia=date(2027, 1, 1),
            )


class TestReadSchemaIncludesServerAssignedFields:
    """``ResolucionFacturacionRead`` returns the server-assigned DIAN fields."""

    def test_read_includes_prefijo_and_range(self) -> None:
        r = ResolucionFacturacionRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000099"),
            uuid_sucursal=SUCURSAL_UUID,
            numero_resolucion="1876",
            prefijo="SETP",
            rango_desde=1,
            rango_hasta=1000,
            fecha_resolucion=date(2026, 1, 1),
            fecha_inicio_vigencia=date(2026, 1, 1),
            fecha_fin_vigencia=date(2027, 1, 1),
            vigente_desde=NOW,
            vigente_hasta=None,
            estado="activo",
            created_at=NOW,
            created_by=None,
            sync_status=None,
        )
        assert r.prefijo == "SETP"
        assert r.rango_desde == 1
        assert r.rango_hasta == 1000
        assert r.vigente_hasta is None
        assert r.estado == "activo"


class TestUpdateSchemaIsSymmetric:
    """The DIAN boundary applies on PUT too (REQ-04-V-ACTUALIZACION)."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("prefijo", "SETP"),
            ("rango_desde", 1),
            ("rango_hasta", 1000),
        ],
    )
    def test_update_rejects_server_assigned_field(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            ResolucionFacturacionUpdate(
                uuid_sucursal=SUCURSAL_UUID,
                numero_resolucion="1876",
                fecha_resolucion=date(2026, 1, 1),
                fecha_inicio_vigencia=date(2026, 1, 1),
                fecha_fin_vigencia=date(2027, 1, 1),
                **{field: value},
            )

    def test_update_accepts_valid_payload(self) -> None:
        u = ResolucionFacturacionUpdate(
            uuid_sucursal=SUCURSAL_UUID,
            numero_resolucion="1877",
            fecha_resolucion=date(2026, 6, 1),
            fecha_inicio_vigencia=date(2026, 6, 1),
            fecha_fin_vigencia=date(2027, 6, 1),
        )
        assert u.numero_resolucion == "1877"


class TestNumeroResolucionLength:
    """``numero_resolucion`` (part of UK01) MUST be 1-64 chars."""

    @pytest.mark.parametrize("bad", ["", "x" * 65])
    def test_create_rejects_bad_numero(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            ResolucionFacturacionCreate(
                uuid_sucursal=SUCURSAL_UUID,
                numero_resolucion=bad,
                fecha_resolucion=date(2026, 1, 1),
                fecha_inicio_vigencia=date(2026, 1, 1),
                fecha_fin_vigencia=date(2027, 1, 1),
            )

    def test_create_accepts_max_numero(self) -> None:
        c = ResolucionFacturacionCreate(
            uuid_sucursal=SUCURSAL_UUID,
            numero_resolucion="x" * 64,
            fecha_resolucion=date(2026, 1, 1),
            fecha_inicio_vigencia=date(2026, 1, 1),
            fecha_fin_vigencia=date(2027, 1, 1),
        )
        assert len(c.numero_resolucion) == 64
