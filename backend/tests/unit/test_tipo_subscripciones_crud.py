"""Schema-only tests for ``prod.tipo_subscripciones`` Pydantic schemas (PR3).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration tests
against a real Postgres land in a later PR once we wire testcontainers in CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from parkos_core.schemas.tipo_subscripciones import (
    TipoSubscripcionesCreate,
    TipoSubscripcionesFilter,
    TipoSubscripcionesRead,
    TipoSubscripcionesReadList,
    TipoSubscripcionesUpdate,
)
from pydantic import ValidationError


class TestConfigForbid:
    """``extra='forbid'`` rejects unknown fields (C-3)."""

    def test_create_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoSubscripcionesCreate(tipo="plan-mensual", rogue_field="evil")

    def test_update_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoSubscripcionesUpdate(tipo="plan-mensual", rogue_field="evil")


class TestVersioningColumnsExcluded:
    """``Create``/``Update`` MUST NOT accept versioning columns (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoSubscripcionesCreate(tipo="plan-mensual", **{forbidden: "x"})

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoSubscripcionesUpdate(tipo="plan-mensual", **{forbidden: "x"})


class TestTipoLength:
    """``tipo`` MUST be 1-64 chars."""

    @pytest.mark.parametrize("bad", ["", "x" * 65])
    def test_create_rejects_bad_length(self, bad):
        with pytest.raises(ValidationError):
            TipoSubscripcionesCreate(tipo=bad)

    def test_create_accepts_min_length(self):
        c = TipoSubscripcionesCreate(tipo="x")
        assert c.tipo == "x"

    def test_create_accepts_max_length(self):
        c = TipoSubscripcionesCreate(tipo="x" * 64)
        assert len(c.tipo) == 64


class TestOptionalFields:
    """All non-UK fields are optional on Create/Update."""

    def test_create_minimal_only_tipo(self):
        c = TipoSubscripcionesCreate(tipo="plan-basico")
        assert c.tipo == "plan-basico"
        assert c.valor is None
        assert c.duracion_dias is None
        assert c.cantidad_maxima_vehiculos is None
        assert c.mismo_tipo_vehiculo is None
        assert c.tipo_cliente_permitido is None

    def test_create_full(self):
        c = TipoSubscripcionesCreate(
            tipo="plan-b2b",
            valor=Decimal("150000.00"),
            duracion_dias=30,
            cantidad_maxima_vehiculos=5,
            mismo_tipo_vehiculo=False,
            tipo_cliente_permitido="juridica",
        )
        assert c.valor == Decimal("150000.00")
        assert c.duracion_dias == 30
        assert c.cantidad_maxima_vehiculos == 5
        assert c.mismo_tipo_vehiculo is False
        assert c.tipo_cliente_permitido == "juridica"


class TestFilterAllOptional:
    def test_empty_filter(self):
        f = TipoSubscripcionesFilter()
        assert f.estado is None
        assert f.vigente_desde__gte is None
        assert f.duracion_dias__gte is None

    def test_populated_filter(self):
        f = TipoSubscripcionesFilter(
            estado="activo",
            duracion_dias__gte=1,
            duracion_dias__lte=365,
        )
        assert f.estado == "activo"
        assert f.duracion_dias__gte == 1
        assert f.duracion_dias__lte == 365


class TestReadFromAttributes:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_read_from_dict(self):
        r = TipoSubscripcionesRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000010"),
            tipo="plan-mensual",
            valor=Decimal("50000.00"),
            duracion_dias=30,
            cantidad_maxima_vehiculos=2,
            mismo_tipo_vehiculo=True,
            tipo_cliente_permitido="natural",
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.tipo == "plan-mensual"
        assert r.valor == Decimal("50000.00")


class TestReadList:
    def test_empty_list(self):
        rl = TipoSubscripcionesReadList(items=[], next_cursor=None)
        assert rl.items == []
        assert rl.next_cursor is None

    def test_with_cursor(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        r = TipoSubscripcionesRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000011"),
            tipo="plan-anual",
            valor=Decimal("500000.00"),
            duracion_dias=365,
            cantidad_maxima_vehiculos=10,
            mismo_tipo_vehiculo=False,
            tipo_cliente_permitido=None,
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = TipoSubscripcionesReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"
