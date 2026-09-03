"""Schema-only tests for ``prod.impuestos`` Pydantic schemas (PR3).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration tests
against a real Postgres land in a later PR once we wire testcontainers in CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from parkos_core.schemas.impuestos import (
    ImpuestosCreate,
    ImpuestosFilter,
    ImpuestosRead,
    ImpuestosReadList,
    ImpuestosUpdate,
)
from pydantic import ValidationError


class TestConfigForbid:
    """``extra='forbid'`` rejects unknown fields (C-3)."""

    def test_create_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            ImpuestosCreate(codigo="IVA-19", rogue_field="evil")

    def test_update_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            ImpuestosUpdate(codigo="IVA-19", rogue_field="evil")


class TestVersioningColumnsExcluded:
    """``Create``/``Update`` MUST NOT accept versioning columns (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            ImpuestosCreate(codigo="IVA-19", **{forbidden: "x"})

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            ImpuestosUpdate(codigo="IVA-19", **{forbidden: "x"})


class TestCodigoLength:
    """``codigo`` MUST be 1-64 chars."""

    @pytest.mark.parametrize("bad", ["", "x" * 65])
    def test_create_rejects_bad_codigo(self, bad):
        with pytest.raises(ValidationError):
            ImpuestosCreate(codigo=bad)

    def test_create_accepts_min_codigo(self):
        c = ImpuestosCreate(codigo="x")
        assert c.codigo == "x"


class TestOptionalFields:
    """``nombre``, ``porcentaje``, ``tipo_calculo``, ``base_calculo`` are all optional."""

    def test_create_minimal_only_codigo(self):
        c = ImpuestosCreate(codigo="IVA-19")
        assert c.codigo == "IVA-19"
        assert c.nombre is None
        assert c.porcentaje is None
        assert c.tipo_calculo is None
        assert c.base_calculo is None

    def test_create_full(self):
        c = ImpuestosCreate(
            nombre="IVA 19%",
            codigo="IVA-19",
            porcentaje=Decimal("19.0000"),
            tipo_calculo="porcentual",
            base_calculo="subtotal",
        )
        assert c.nombre == "IVA 19%"
        assert c.porcentaje == Decimal("19.0000")
        assert c.tipo_calculo == "porcentual"
        assert c.base_calculo == "subtotal"

    def test_porcentaje_accepts_decimal_string(self):
        # Pydantic v2 coerces string to Decimal for Decimal fields
        c = ImpuestosCreate(codigo="IVA-19", porcentaje="19.0000")
        assert c.porcentaje == Decimal("19.0000")


class TestFilterAllOptional:
    def test_empty_filter(self):
        f = ImpuestosFilter()
        assert f.estado is None
        assert f.codigo is None
        assert f.tipo_calculo is None
        assert f.vigente_desde__gte is None

    def test_populated_filter(self):
        f = ImpuestosFilter(estado="activo", codigo="IVA-19", tipo_calculo="porcentual")
        assert f.codigo == "IVA-19"
        assert f.tipo_calculo == "porcentual"


class TestReadFromAttributes:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_read_from_dict(self):
        r = ImpuestosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000030"),
            nombre="IVA 19%",
            codigo="IVA-19",
            porcentaje=Decimal("19.0000"),
            tipo_calculo="porcentual",
            base_calculo="subtotal",
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.codigo == "IVA-19"
        assert r.porcentaje == Decimal("19.0000")


class TestReadList:
    def test_empty_list(self):
        rl = ImpuestosReadList(items=[], next_cursor=None)
        assert rl.items == []

    def test_with_cursor(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        r = ImpuestosRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000031"),
            nombre="INC",
            codigo="INC-2026",
            porcentaje=Decimal("0.8000"),
            tipo_calculo="porcentual",
            base_calculo="subtotal",
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = ImpuestosReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"
