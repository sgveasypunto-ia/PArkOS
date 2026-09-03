"""Schema-only tests for ``prod.otros_cobros`` Pydantic schemas (PR3).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration tests
against a real Postgres land in a later PR once we wire testcontainers in CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from parkos_core.schemas.otros_cobros import (
    OtrosCobrosCreate,
    OtrosCobrosFilter,
    OtrosCobrosRead,
    OtrosCobrosReadList,
    OtrosCobrosUpdate,
)
from pydantic import ValidationError


class TestConfigForbid:
    """``extra='forbid'`` rejects unknown fields (C-3)."""

    def test_create_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            OtrosCobrosCreate(nombre="Seguro", rogue_field="evil")

    def test_update_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            OtrosCobrosUpdate(nombre="Seguro", rogue_field="evil")


class TestVersioningColumnsExcluded:
    """``Create``/``Update`` MUST NOT accept versioning columns (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            OtrosCobrosCreate(nombre="Seguro", **{forbidden: "x"})

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            OtrosCobrosUpdate(nombre="Seguro", **{forbidden: "x"})


class TestNombreLength:
    """``nombre`` MUST be 1-255 chars (UK01)."""

    @pytest.mark.parametrize("bad", ["", "x" * 256])
    def test_create_rejects_bad_nombre(self, bad):
        with pytest.raises(ValidationError):
            OtrosCobrosCreate(nombre=bad)

    def test_create_accepts_max_nombre(self):
        c = OtrosCobrosCreate(nombre="x" * 255)
        assert len(c.nombre) == 255


class TestOptionalFields:
    """``costo``, ``tipo_calculo``, ``base_calculo`` are all optional."""

    def test_create_minimal_only_nombre(self):
        c = OtrosCobrosCreate(nombre="Seguro voluntario")
        assert c.nombre == "Seguro voluntario"
        assert c.costo is None
        assert c.tipo_calculo is None
        assert c.base_calculo is None

    def test_create_full(self):
        c = OtrosCobrosCreate(
            nombre="Seguro voluntario",
            costo=Decimal("5000.00"),
            tipo_calculo="fijo",
            base_calculo=None,
        )
        assert c.costo == Decimal("5000.00")
        assert c.tipo_calculo == "fijo"
        assert c.base_calculo is None


class TestFilterAllOptional:
    def test_empty_filter(self):
        f = OtrosCobrosFilter()
        assert f.estado is None
        assert f.nombre is None
        assert f.tipo_calculo is None

    def test_populated_filter(self):
        f = OtrosCobrosFilter(estado="activo", nombre="Seguro", tipo_calculo="fijo")
        assert f.nombre == "Seguro"
        assert f.tipo_calculo == "fijo"


class TestReadFromAttributes:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_read_from_dict(self):
        r = OtrosCobrosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000040"),
            nombre="Seguro voluntario",
            costo=Decimal("5000.00"),
            tipo_calculo="fijo",
            base_calculo=None,
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.nombre == "Seguro voluntario"
        assert r.costo == Decimal("5000.00")


class TestReadList:
    def test_empty_list(self):
        rl = OtrosCobrosReadList(items=[], next_cursor=None)
        assert rl.items == []

    def test_with_cursor(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        r = OtrosCobrosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000041"),
            nombre="Lavado exterior",
            costo=Decimal("15000.00"),
            tipo_calculo="fijo",
            base_calculo=None,
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = OtrosCobrosReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"