"""Admin scope filtering tests (T-PR10-06).

Verifies that admin-issuer queries are scoped to ``claims.sucursales_permitidas``
via the ``apply_admin_scope`` helper (T-PR10-04, REQ-X2), plus the response
shapes of the three PR10 admin endpoints.

Pydantic/SQL-composition level tests — no live DB required.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import ClassVar

import pytest
from parkos_core.api.v1.admin_views import (
    AdminMeResponse,
    SucursalDashboard,
    SucursalItem,
    SucursalListItem,
    SucursalListResponse,
    SucursalSyncStatus,
)
from parkos_core.db.tenancy import apply_admin_scope, extract_sucursales_permitidas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.sucursal import Sucursal
from pydantic import ValidationError
from sqlalchemy import select

SUCURSAL_A = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")
SUCURSAL_B = uuid_lib.UUID("00000000-0000-0000-0000-0000000000b1")
ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c1")


class TestSucursalListItemSchema:
    def test_read_basic(self):
        item = SucursalListItem(
            uuid=SUCURSAL_A,
            nombre="Sucursal Centro",
            ciudad="Bogota",
            uuid_tipo_sucursal=uuid_lib.uuid4(),
        )
        assert item.nombre == "Sucursal Centro"


class TestSucursalSyncStatusSchema:
    def test_nullable_fields(self):
        s = SucursalSyncStatus(
            last_sync_at=None,
            last_error=None,
            last_heartbeat_at=None,
        )
        assert s.last_sync_at is None


class TestSucursalItemSchema:
    def test_full_item(self):
        item = SucursalItem(
            uuid=SUCURSAL_A,
            nombre="Sucursal A",
            ciudad="Bogota",
            uuid_tipo_sucursal=uuid_lib.uuid4(),
            sync_status=SucursalSyncStatus(
                last_sync_at=datetime(2026, 1, 1),
                last_error=None,
                last_heartbeat_at=datetime(2026, 1, 1),
            ),
            open_alerts_count=2,
            last_pairing_at=datetime(2026, 1, 1),
        )
        assert item.open_alerts_count == 2


class TestSucursalListResponseSchema:
    def test_empty_response(self):
        r = SucursalListResponse(items=[], next_cursor=None)
        assert r.items == []


class TestSucursalDashboardSchema:
    def test_full_dashboard(self):
        d = SucursalDashboard(
            uuid_sucursal=SUCURSAL_A,
            fecha=datetime(2026, 1, 1),
            ingresos_count=10,
            ingresos_monto_total=100000.0,
            facturas_emitidas_count=5,
            facturas_electronicas_count=3,
            open_alertas_count=2,
            sync_health={
                "last_sync_at": datetime(2026, 1, 1),
                "lag_seconds": 60,
                "queue_depth": 0,
            },
        )
        assert d.ingresos_count == 10
        assert d.facturas_electronicas_count == 3

    def test_extras_forbidden(self):
        with pytest.raises(ValidationError):
            SucursalDashboard(
                uuid_sucursal=SUCURSAL_A,
                fecha=datetime(2026, 1, 1),
                ingresos_count=10,
                ingresos_monto_total=0.0,
                facturas_emitidas_count=0,
                facturas_electronicas_count=0,
                open_alertas_count=0,
                sync_health={
                    "last_sync_at": None,
                    "lag_seconds": None,
                    "queue_depth": 0,
                },
                rogue_field="evil",
            )


class TestAdminMeResponseSchema:
    def test_full_response(self):
        r = AdminMeResponse(
            actor_uuid=ACTOR_UUID,
            email="admin@example.com",
            rol="admin",
            sucursales_permitidas=[SUCURSAL_A, SUCURSAL_B],
            permissions=["config_catalogo", "gestionar_dian"],
        )
        assert len(r.sucursales_permitidas) == 2
        assert "config_catalogo" in r.permissions

    def test_empty_permissions(self):
        r = AdminMeResponse(
            actor_uuid=ACTOR_UUID,
            email=None,
            rol=None,
            sucursales_permitidas=[],
            permissions=[],
        )
        assert r.permissions == []


class TestExtractSucursalesPermitidas:
    def test_from_claims_dict_with_strings(self):
        claims = {"sucursales_permitidas": [str(SUCURSAL_A), str(SUCURSAL_B)]}
        assert extract_sucursales_permitidas(claims) == [SUCURSAL_A, SUCURSAL_B]

    def test_missing_key_is_empty(self):
        assert extract_sucursales_permitidas({}) == []

    def test_malformed_entries_are_dropped_not_widened(self):
        claims = {"sucursales_permitidas": [str(SUCURSAL_A), "not-a-uuid", None]}
        assert extract_sucursales_permitidas(claims) == [SUCURSAL_A]

    def test_accepts_object_with_attribute(self):
        class _Ctx:
            sucursales_permitidas: ClassVar[list[uuid_lib.UUID]] = [SUCURSAL_A]

        assert extract_sucursales_permitidas(_Ctx()) == [SUCURSAL_A]


class TestApplyAdminScopeHelper:
    def test_apply_admin_scope_is_callable(self):
        assert callable(apply_admin_scope)

    def test_scope_filters_sucursal_by_own_uuid(self):
        claims = {"sucursales_permitidas": [str(SUCURSAL_A)]}
        stmt = apply_admin_scope(None, select(Sucursal), claims)
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "prod.sucursal.uuid IN" in sql

    def test_scope_filters_tenant_table_by_uuid_sucursal(self):
        claims = {"sucursales_permitidas": [str(SUCURSAL_A)]}
        stmt = apply_admin_scope(None, select(Ingreso), claims)
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "prod.ingreso.uuid_sucursal IN" in sql

    def test_permitted_uuids_are_bound_to_the_filter(self):
        claims = {"sucursales_permitidas": [str(SUCURSAL_A)]}
        stmt = apply_admin_scope(None, select(Sucursal), claims)
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        # The default dialect renders PG_UUID literals as bare hex.
        rendered = str(compiled)
        assert SUCURSAL_A.hex in rendered
        assert SUCURSAL_B.hex not in rendered

    def test_empty_permitidas_fails_closed(self):
        stmt = apply_admin_scope(None, select(Sucursal), {"sucursales_permitidas": []})
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "FALSE" in sql
        assert "IN" not in sql.split("WHERE", 1)[1]

    def test_missing_claim_fails_closed(self):
        stmt = apply_admin_scope(None, select(Sucursal), {})
        assert "FALSE" in str(stmt.compile(compile_kwargs={"literal_binds": True}))

    def test_existing_where_is_preserved(self):
        claims = {"sucursales_permitidas": [str(SUCURSAL_A)]}
        base = select(Sucursal).where(Sucursal.vigente_hasta.is_(None))
        stmt = apply_admin_scope(None, base, claims)
        sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "vigente_hasta IS NULL" in sql
        assert "prod.sucursal.uuid IN" in sql


class TestAdminViewsRouter:
    def test_router_exposes_three_get_routes(self):
        from parkos_core.api.v1.admin_views import router

        paths = {r.path for r in router.routes}
        assert "/sucursales" in paths
        assert "/admin/sucursales/{uuid}/dashboard" in paths
        assert "/admin/me" in paths

    def test_no_delete_routes(self):
        from parkos_core.api.v1.admin_views import router

        methods: set[str] = set()
        for route in router.routes:
            methods |= set(getattr(route, "methods", set()))
        assert "DELETE" not in methods
        assert methods == {"GET"}
