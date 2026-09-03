"""Schema-only tests for ``prod.tipo_sucursal`` Pydantic schemas (PR3).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration tests
against a real Postgres land in a later PR once we wire testcontainers in CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.schemas.tipo_sucursal import (
    TipoSucursalCreate,
    TipoSucursalFilter,
    TipoSucursalRead,
    TipoSucursalReadList,
    TipoSucursalUpdate,
)
from pydantic import ValidationError


class TestConfigForbid:
    """``extra='forbid'`` rejects unknown fields (C-3)."""

    def test_create_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoSucursalCreate(codigo="AUTO", rogue_field="evil")

    def test_update_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoSucursalUpdate(codigo="AUTO", rogue_field="evil")


class TestVersioningColumnsExcluded:
    """``Create``/``Update`` MUST NOT accept versioning columns (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoSucursalCreate(codigo="AUTO", **{forbidden: "x"})

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoSucursalUpdate(codigo="AUTO", **{forbidden: "x"})


class TestCodigoLength:
    """``codigo`` MUST be 1-64 chars."""

    @pytest.mark.parametrize("bad", ["", "x" * 65])
    def test_create_rejects_bad_codigo(self, bad):
        with pytest.raises(ValidationError):
            TipoSucursalCreate(codigo=bad)

    def test_create_accepts_max_codigo(self):
        c = TipoSucursalCreate(codigo="x" * 64)
        assert len(c.codigo) == 64


class TestOptionalFields:
    """``nombre``, ``descripcion``, ``caracteristicas`` are all optional."""

    def test_create_minimal_only_codigo(self):
        c = TipoSucursalCreate(codigo="AUTO")
        assert c.codigo == "AUTO"
        assert c.nombre is None
        assert c.descripcion is None
        assert c.caracteristicas is None

    def test_create_full(self):
        c = TipoSucursalCreate(
            codigo="AUTO",
            nombre="Autoservicio",
            descripcion="Punto sin operador, sólo lector de placas.",
            caracteristicas={"captura_placa_auto": True, "sin_operador": True},
        )
        assert c.nombre == "Autoservicio"
        assert c.descripcion.startswith("Punto sin operador")
        assert c.caracteristicas == {
            "captura_placa_auto": True,
            "sin_operador": True,
        }

    def test_caracteristicas_must_be_dict(self):
        # Schema allows dict[str, Any] | None; a string is invalid.
        with pytest.raises(ValidationError):
            TipoSucursalCreate(codigo="AUTO", caracteristicas="not-a-dict")


class TestFilterAllOptional:
    def test_empty_filter(self):
        f = TipoSucursalFilter()
        assert f.estado is None
        assert f.codigo is None
        assert f.vigente_desde__gte is None

    def test_populated_filter(self):
        f = TipoSucursalFilter(estado="activo", codigo="AUTO")
        assert f.codigo == "AUTO"


class TestReadFromAttributes:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_read_from_dict(self):
        r = TipoSucursalRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000020"),
            codigo="AUTO",
            nombre="Autoservicio",
            descripcion="Punto sin operador",
            caracteristicas={"sin_operador": True},
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.codigo == "AUTO"
        assert r.caracteristicas == {"sin_operador": True}


class TestReadList:
    def test_empty_list(self):
        rl = TipoSucursalReadList(items=[], next_cursor=None)
        assert rl.items == []

    def test_with_cursor(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        r = TipoSucursalRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000021"),
            codigo="MANUAL",
            nombre="Con operador",
            descripcion=None,
            caracteristicas=None,
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = TipoSucursalReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"
