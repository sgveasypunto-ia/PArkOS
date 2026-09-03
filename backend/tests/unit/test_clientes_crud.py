"""Schema-only tests for the 5 commercial tables (REQ-01..04).

Per PR3 plan, PR5 ships pure-Pydantic tests (no DB). Integration tests
against a real Postgres land in a later PR.

The router config (``api/v1/clientes.py``) allows BOTH ``operador-`` and
``admin-`` issuers (operator writes locally, admin reads cross-branch).
This file validates the Pydantic contracts for the 5 tables:
``clientes``, ``clientes-b2b``, ``subscripciones-cliente``, ``vehiculos``,
``subscripcion-vehiculos``.

The ``SubscripcionVehiculosCreate`` /
``SubscripcionVehiculosUpdate`` validators are most-tested in
``test_subscripcion_vehiculos_validator.py`` (T-PR5-10) — here we only
cover basic shape.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

import pytest
from parkos_core.api.v1.clientes import _ROUTER_CONFIG
from parkos_core.schemas.clientes import (
    ClientesB2BCreate,
    ClientesB2BFilter,
    ClientesB2BRead,
    ClientesB2BReadList,
    ClientesB2BUpdate,
    ClientesCreate,
    ClientesFilter,
    ClientesRead,
    ClientesReadList,
    ClientesUpdate,
    SubscripcionesClienteCreate,
    SubscripcionesClienteFilter,
    SubscripcionesClienteRead,
    SubscripcionesClienteReadList,
    SubscripcionesClienteUpdate,
    SubscripcionVehiculosCreate,
    SubscripcionVehiculosFilter,
    SubscripcionVehiculosRead,
    SubscripcionVehiculosReadList,
    SubscripcionVehiculosUpdate,
    VehiculosCreate,
    VehiculosFilter,
    VehiculosRead,
    VehiculosReadList,
    VehiculosUpdate,
)
from pydantic import ValidationError

CLIENTE_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c1")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c2")
TIPO_PERSONA_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c3")
TIPO_VEHICULO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c4")
TIPO_SUBSCRIPCION_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c5")
VEHICULO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c6")
SUBSCRIPCION_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000c7")


# ============================================================================
# Router issuer policy (REQ-01: operador writes locally, admin reads cross-branch)
# ============================================================================


class TestRouterIssuerPolicy:
    """All 5 commercial routers MUST accept ``operador-,admin-`` issuers."""

    @pytest.mark.parametrize(
        "resource",
        [
            "clientes",
            "clientes-b2b",
            "subscripciones-cliente",
            "vehiculos",
            "subscripcion-vehiculos",
        ],
    )
    def test_router_accepts_operador_and_admin(self, resource: str) -> None:
        issuer, perm = _ROUTER_CONFIG[resource]
        assert issuer == "operador-,admin-", (
            f"Router {resource} must accept operador-,admin-; got {issuer!r}"
        )
        assert perm.startswith("admin_"), (
            f"Router {resource} permission must start with admin_; got {perm!r}"
        )

    def test_all_5_resources_configured(self) -> None:
        assert len(_ROUTER_CONFIG) == 5
        expected = {
            "clientes",
            "clientes-b2b",
            "subscripciones-cliente",
            "vehiculos",
            "subscripcion-vehiculos",
        }
        assert set(_ROUTER_CONFIG.keys()) == expected


# ============================================================================
# clientes
# ============================================================================


class TestClientes:
    def test_read_from_dict(self) -> None:
        r = ClientesRead(
            uuid=CLIENTE_UUID,
            tipo_identificador="CC",
            numero_identificacion="1234567890",
            nombre="Juan",
            apellido="Pérez",
            telefono="+573001234567",
            email="juan@example.com",
            uuid_tipo_persona=TIPO_PERSONA_UUID,
            registro={"direccion": "Calle 1 #2-3"},
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.numero_identificacion == "1234567890"
        assert r.registro == {"direccion": "Calle 1 #2-3"}

    def test_read_projects_from_orm_dict(self) -> None:
        """``from_attributes=True`` lets us project a dict that mirrors ORM attrs."""
        orm_row = {
            "uuid": CLIENTE_UUID,
            "tipo_identificador": "CE",
            "numero_identificacion": "987654",
            "nombre": "Ana",
            "apellido": "Gómez",
            "telefono": None,
            "email": None,
            "uuid_tipo_persona": None,
            "registro": None,
            "vigente_desde": datetime(2026, 2, 1),
            "vigente_hasta": None,
            "estado": "activo",
            "created_at": datetime(2026, 2, 1),
            "created_by": None,
            "sync_status": None,
        }
        r = ClientesRead.model_validate(orm_row)
        assert r.nombre == "Ana"

    def test_create_minimal(self) -> None:
        c = ClientesCreate(
            tipo_identificador="CC",
            numero_identificacion="1234567890",
        )
        assert c.nombre is None
        assert c.registro is None

    def test_create_full(self) -> None:
        c = ClientesCreate(
            tipo_identificador="CC",
            numero_identificacion="1234567890",
            nombre="Juan",
            apellido="Pérez",
            telefono="+573001234567",
            email="juan@example.com",
            uuid_tipo_persona=TIPO_PERSONA_UUID,
            registro={"direccion": "Calle 1"},
        )
        assert c.nombre == "Juan"
        assert c.uuid_tipo_persona == TIPO_PERSONA_UUID

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning(self, forbidden: str) -> None:
        with pytest.raises(ValidationError):
            ClientesCreate(
                tipo_identificador="CC",
                numero_identificacion="1234567890",
                **{forbidden: "x"},
            )

    def test_update_validates(self) -> None:
        u = ClientesUpdate(
            tipo_identificador="NIT",
            numero_identificacion="900123456",
            nombre="Empresa SA",
        )
        assert u.tipo_identificador == "NIT"
        assert u.apellido is None

    def test_filter_defaults(self) -> None:
        f = ClientesFilter()
        assert f.estado is None
        assert f.vigente_desde__gte is None
        assert f.vigente_desde__lte is None
        assert f.uuid_tipo_persona is None

    def test_read_list_shape(self) -> None:
        rl = ClientesReadList(items=[], next_cursor=None)
        assert rl.items == []
        assert rl.next_cursor is None


# ============================================================================
# clientes_b2b
# ============================================================================


class TestClientesB2B:
    def test_read_from_dict(self) -> None:
        r = ClientesB2BRead(
            uuid=uuid_lib.uuid4(),
            uuid_cliente=CLIENTE_UUID,
            cantidad=10,
            registro={"convenio_tipo": "premium"},
            fecha_inicio_convenio=date(2026, 1, 1),
            fecha_vencimiento=date(2027, 1, 1),
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.cantidad == 10
        assert r.fecha_vencimiento == date(2027, 1, 1)
        assert r.uuid_cliente == CLIENTE_UUID

    def test_create_minimal(self) -> None:
        c = ClientesB2BCreate(uuid_cliente=CLIENTE_UUID)
        assert c.cantidad is None
        assert c.fecha_inicio_convenio is None
        assert c.fecha_vencimiento is None
        assert c.registro is None

    def test_create_full(self) -> None:
        c = ClientesB2BCreate(
            uuid_cliente=CLIENTE_UUID,
            cantidad=5,
            registro={"convenio_tipo": "standard"},
            fecha_inicio_convenio=date(2026, 1, 1),
            fecha_vencimiento=date(2027, 1, 1),
        )
        assert c.cantidad == 5
        assert c.registro == {"convenio_tipo": "standard"}

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning(self, forbidden: str) -> None:
        with pytest.raises(ValidationError):
            ClientesB2BCreate(uuid_cliente=CLIENTE_UUID, **{forbidden: "x"})

    def test_update_validates(self) -> None:
        u = ClientesB2BUpdate(
            uuid_cliente=CLIENTE_UUID,
            cantidad=20,
            fecha_vencimiento=date(2028, 6, 1),
        )
        assert u.cantidad == 20
        assert u.uuid_cliente == CLIENTE_UUID

    def test_filter_defaults(self) -> None:
        f = ClientesB2BFilter()
        assert f.estado is None
        assert f.vigente_desde__gte is None
        assert f.uuid_cliente is None

    def test_read_list_shape(self) -> None:
        rl = ClientesB2BReadList(items=[], next_cursor=None)
        assert rl.items == []


# ============================================================================
# subscripciones_cliente
# ============================================================================


class TestSubscripcionesCliente:
    def test_read_from_dict(self) -> None:
        r = SubscripcionesClienteRead(
            uuid=uuid_lib.uuid4(),
            uuid_cliente=CLIENTE_UUID,
            uuid_sucursal=SUCURSAL_UUID,
            uuid_tipo_subscripcion=TIPO_SUBSCRIPCION_UUID,
            fecha_inicio_cobertura=date(2026, 1, 1),
            fecha_vencimiento=date(2027, 1, 1),
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.uuid_tipo_subscripcion == TIPO_SUBSCRIPCION_UUID
        assert r.fecha_inicio_cobertura == date(2026, 1, 1)

    def test_create_minimal(self) -> None:
        c = SubscripcionesClienteCreate(
            uuid_cliente=CLIENTE_UUID,
            uuid_sucursal=SUCURSAL_UUID,
            uuid_tipo_subscripcion=TIPO_SUBSCRIPCION_UUID,
        )
        assert c.fecha_inicio_cobertura is None
        assert c.fecha_vencimiento is None

    def test_create_full(self) -> None:
        c = SubscripcionesClienteCreate(
            uuid_cliente=CLIENTE_UUID,
            uuid_sucursal=SUCURSAL_UUID,
            uuid_tipo_subscripcion=TIPO_SUBSCRIPCION_UUID,
            fecha_inicio_cobertura=date(2026, 1, 1),
            fecha_vencimiento=date(2027, 1, 1),
        )
        assert c.fecha_vencimiento == date(2027, 1, 1)

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning(self, forbidden: str) -> None:
        with pytest.raises(ValidationError):
            SubscripcionesClienteCreate(
                uuid_cliente=CLIENTE_UUID,
                uuid_sucursal=SUCURSAL_UUID,
                uuid_tipo_subscripcion=TIPO_SUBSCRIPCION_UUID,
                **{forbidden: "x"},
            )

    def test_update_validates(self) -> None:
        u = SubscripcionesClienteUpdate(
            uuid_cliente=CLIENTE_UUID,
            uuid_sucursal=SUCURSAL_UUID,
            uuid_tipo_subscripcion=TIPO_SUBSCRIPCION_UUID,
            fecha_vencimiento=date(2028, 1, 1),
        )
        assert u.fecha_vencimiento == date(2028, 1, 1)

    def test_filter_defaults(self) -> None:
        f = SubscripcionesClienteFilter()
        assert f.estado is None
        assert f.uuid_cliente is None
        assert f.uuid_sucursal is None
        assert f.uuid_tipo_subscripcion is None

    def test_read_list_shape(self) -> None:
        rl = SubscripcionesClienteReadList(items=[], next_cursor=None)
        assert rl.items == []


# ============================================================================
# vehiculos
# ============================================================================


class TestVehiculos:
    def test_read_from_dict(self) -> None:
        r = VehiculosRead(
            uuid=uuid_lib.uuid4(),
            placa="ABC123",
            uuid_tipo_vehiculo=TIPO_VEHICULO_UUID,
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.placa == "ABC123"
        assert r.uuid_tipo_vehiculo == TIPO_VEHICULO_UUID

    def test_create_minimal(self) -> None:
        c = VehiculosCreate(placa="ABC123", uuid_tipo_vehiculo=TIPO_VEHICULO_UUID)
        assert c.placa == "ABC123"
        assert c.uuid_tipo_vehiculo == TIPO_VEHICULO_UUID

    def test_create_max_length_placa(self) -> None:
        """REQ-OP-06: international plates up to 16 chars."""
        placa = "A" * 16
        c = VehiculosCreate(placa=placa, uuid_tipo_vehiculo=TIPO_VEHICULO_UUID)
        assert len(c.placa) == 16

    def test_create_rejects_empty_placa(self) -> None:
        with pytest.raises(ValidationError):
            VehiculosCreate(placa="", uuid_tipo_vehiculo=TIPO_VEHICULO_UUID)

    def test_create_rejects_long_placa(self) -> None:
        """REQ-OP-06: 17+ chars must fail (max_length=16)."""
        with pytest.raises(ValidationError):
            VehiculosCreate(placa="X" * 17, uuid_tipo_vehiculo=TIPO_VEHICULO_UUID)

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning(self, forbidden: str) -> None:
        with pytest.raises(ValidationError):
            VehiculosCreate(
                placa="ABC123",
                uuid_tipo_vehiculo=TIPO_VEHICULO_UUID,
                **{forbidden: "x"},
            )

    def test_update_validates(self) -> None:
        u = VehiculosUpdate(placa="XYZ789", uuid_tipo_vehiculo=TIPO_VEHICULO_UUID)
        assert u.placa == "XYZ789"

    def test_update_rejects_long_placa(self) -> None:
        """Update shape carries the same constraint."""
        with pytest.raises(ValidationError):
            VehiculosUpdate(placa="X" * 17, uuid_tipo_vehiculo=TIPO_VEHICULO_UUID)

    def test_filter_defaults(self) -> None:
        f = VehiculosFilter()
        assert f.estado is None
        assert f.placa is None
        assert f.uuid_tipo_vehiculo is None

    def test_read_list_shape(self) -> None:
        rl = VehiculosReadList(items=[], next_cursor=None)
        assert rl.items == []


# ============================================================================
# subscripcion_vehiculos (basic shape; deep validator tests in T-PR5-10)
# ============================================================================


class TestSubscripcionVehiculosBasic:
    def test_read_from_dict(self) -> None:
        r = SubscripcionVehiculosRead(
            uuid=uuid_lib.uuid4(),
            uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
            uuid_vehiculo=VEHICULO_UUID,
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.uuid_subscripcion_cliente == SUBSCRIPCION_UUID
        assert r.uuid_vehiculo == VEHICULO_UUID

    def test_create_basic(self) -> None:
        c = SubscripcionVehiculosCreate(
            uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
            uuid_vehiculo=VEHICULO_UUID,
        )
        assert c.uuid_subscripcion_cliente == SUBSCRIPCION_UUID
        assert c.uuid_vehiculo == VEHICULO_UUID

    def test_create_rejects_missing_subscripcion(self) -> None:
        """REQ-OP-08 fast-fail: both FK UUIDs are required."""
        with pytest.raises(ValidationError):
            SubscripcionVehiculosCreate(
                uuid_subscripcion_cliente=None,
                uuid_vehiculo=VEHICULO_UUID,
            )

    def test_create_rejects_missing_vehiculo(self) -> None:
        with pytest.raises(ValidationError):
            SubscripcionVehiculosCreate(
                uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
                uuid_vehiculo=None,
            )

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning(self, forbidden: str) -> None:
        with pytest.raises(ValidationError):
            SubscripcionVehiculosCreate(
                uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
                uuid_vehiculo=VEHICULO_UUID,
                **{forbidden: "x"},
            )

    def test_update_validates(self) -> None:
        u = SubscripcionVehiculosUpdate(
            uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
            uuid_vehiculo=VEHICULO_UUID,
        )
        assert u.uuid_vehiculo == VEHICULO_UUID

    def test_filter_defaults(self) -> None:
        f = SubscripcionVehiculosFilter()
        assert f.estado is None
        assert f.uuid_subscripcion_cliente is None
        assert f.uuid_vehiculo is None

    def test_read_list_shape(self) -> None:
        rl = SubscripcionVehiculosReadList(items=[], next_cursor=None)
        assert rl.items == []