"""Schema-only tests for ``prod.costos_servicios`` Pydantic schemas (PR3).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration tests
against a real Postgres land in a later PR once we wire testcontainers in CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from parkos_core.schemas.costos_servicios import (
    CostosServiciosCreate,
    CostosServiciosFilter,
    CostosServiciosRead,
    CostosServiciosReadList,
    CostosServiciosUpdate,
)
from pydantic import ValidationError


class TestConfigForbid:
    """``extra='forbid'`` rejects unknown fields (C-3)."""

    def test_create_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            CostosServiciosCreate(concepto="Reimpresión", rogue_field="evil")

    def test_update_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            CostosServiciosUpdate(concepto="Reimpresión", rogue_field="evil")


class TestVersioningColumnsExcluded:
    """``Create``/``Update`` MUST NOT accept versioning columns (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            CostosServiciosCreate(concepto="Reimpresión", **{forbidden: "x"})

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            CostosServiciosUpdate(concepto="Reimpresión", **{forbidden: "x"})


class TestConceptoLength:
    """``concepto`` MUST be 1-255 chars (UK01)."""

    @pytest.mark.parametrize("bad", ["", "x" * 256])
    def test_create_rejects_bad_concepto(self, bad):
        with pytest.raises(ValidationError):
            CostosServiciosCreate(concepto=bad)

    def test_create_accepts_max_concepto(self):
        c = CostosServiciosCreate(concepto="x" * 255)
        assert len(c.concepto) == 255


class TestOptionalFields:
    """``costo``, ``tipo_calculo`` are optional (only ``concepto`` is mandatory)."""

    def test_create_minimal_only_concepto(self):
        c = CostosServiciosCreate(concepto="Reimpresión de ticket")
        assert c.concepto == "Reimpresión de ticket"
        assert c.costo is None
        assert c.tipo_calculo is None

    def test_create_full(self):
        c = CostosServiciosCreate(
            concepto="Reimpresión de ticket",
            costo=Decimal("2000.00"),
            tipo_calculo="fijo",
        )
        assert c.costo == Decimal("2000.00")
        assert c.tipo_calculo == "fijo"


class TestFilterAllOptional:
    def test_empty_filter(self):
        f = CostosServiciosFilter()
        assert f.estado is None
        assert f.concepto is None
        assert f.tipo_calculo is None

    def test_populated_filter(self):
        f = CostosServiciosFilter(estado="activo", concepto="Reimpresión", tipo_calculo="fijo")
        assert f.concepto == "Reimpresión"
        assert f.tipo_calculo == "fijo"


class TestReadFromAttributes:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_read_from_dict(self):
        r = CostosServiciosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000050"),
            concepto="Reimpresión de ticket",
            costo=Decimal("2000.00"),
            tipo_calculo="fijo",
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.concepto == "Reimpresión de ticket"
        assert r.costo == Decimal("2000.00")


class TestReadList:
    def test_empty_list(self):
        rl = CostosServiciosReadList(items=[], next_cursor=None)
        assert rl.items == []

    def test_with_cursor(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        r = CostosServiciosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000051"),
            concepto="Copia de factura",
            costo=Decimal("3500.00"),
            tipo_calculo="fijo",
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = CostosServiciosReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"
