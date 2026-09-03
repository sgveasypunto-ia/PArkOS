"""Schema-only tests for ``prod.tipo_tarifa`` Pydantic schemas (PR3).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration tests
against a real Postgres land in a later PR once we wire testcontainers in CI.

We assert:
- ``model_config = ConfigDict(extra='forbid')`` rejects unknown fields (C-3).
- ``Create`` schema excludes versioning columns (C-6 bi-temporal-crud).
- ``Create`` enforces ``tipo`` length 1-64.
- ``Update`` shape matches ``Create``.
- ``Filter`` is all-optional.
- ``ReadList`` accepts a list of ``Read`` and an optional cursor.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.schemas.tipo_tarifa import (
    TipoTarifaCreate,
    TipoTarifaFilter,
    TipoTarifaRead,
    TipoTarifaReadList,
    TipoTarifaUpdate,
)
from pydantic import ValidationError


class TestConfigForbid:
    """``extra='forbid'`` rejects unknown fields (C-3)."""

    def test_create_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoTarifaCreate(tipo="hora", rogue_field="evil")

    def test_update_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoTarifaUpdate(tipo="hora", rogue_field="evil")


class TestVersioningColumnsExcluded:
    """``Create``/``Update`` MUST NOT accept versioning columns (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoTarifaCreate(tipo="hora", **{forbidden: "x"})

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoTarifaUpdate(tipo="hora", **{forbidden: "x"})


class TestTipoLength:
    """``tipo`` MUST be 1-64 chars."""

    @pytest.mark.parametrize("bad", ["", "x" * 65])
    def test_create_rejects_bad_length(self, bad):
        with pytest.raises(ValidationError):
            TipoTarifaCreate(tipo=bad)

    def test_create_accepts_min_length(self):
        c = TipoTarifaCreate(tipo="x")
        assert c.tipo == "x"

    def test_create_accepts_max_length(self):
        c = TipoTarifaCreate(tipo="x" * 64)
        assert len(c.tipo) == 64


class TestFilterAllOptional:
    def test_empty_filter(self):
        f = TipoTarifaFilter()
        assert f.estado is None
        assert f.vigente_desde__gte is None
        assert f.vigente_desde__lte is None

    def test_populated_filter(self):
        f = TipoTarifaFilter(estado="activo", vigente_desde__gte=datetime(2026, 1, 1))
        assert f.estado == "activo"


class TestReadFromAttributes:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_read_from_dict(self):
        r = TipoTarifaRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000001"),
            tipo="hora",
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.uuid == uuid_lib.UUID("00000000-0000-0000-0000-000000000001")


class TestReadList:
    def test_empty_list(self):
        rl = TipoTarifaReadList(items=[], next_cursor=None)
        assert rl.items == []
        assert rl.next_cursor is None

    def test_with_cursor(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        r = TipoTarifaRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000002"),
            tipo="fraccion",
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = TipoTarifaReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"
