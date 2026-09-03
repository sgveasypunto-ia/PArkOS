"""Schema-only tests for ``prod.tipo_arqueo`` Pydantic schemas (PR3).

Per the PR3 plan, this PR ships schema-only tests (no DB). Integration tests
against a real Postgres land in a later PR once we wire testcontainers in CI.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.schemas.tipo_arqueo import (
    TipoArqueoCreate,
    TipoArqueoFilter,
    TipoArqueoRead,
    TipoArqueoReadList,
    TipoArqueoUpdate,
)
from pydantic import ValidationError


class TestConfigForbid:
    """``extra='forbid'`` rejects unknown fields (C-3)."""

    def test_create_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoArqueoCreate(codigo="cierre_turno", rogue_field="evil")

    def test_update_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            TipoArqueoUpdate(codigo="cierre_turno", rogue_field="evil")


class TestVersioningColumnsExcluded:
    """``Create``/``Update`` MUST NOT accept versioning columns (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoArqueoCreate(codigo="cierre_turno", **{forbidden: "x"})

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            TipoArqueoUpdate(codigo="cierre_turno", **{forbidden: "x"})


class TestCodigoLength:
    """``codigo`` MUST be 1-64 chars."""

    @pytest.mark.parametrize("bad", ["", "x" * 65])
    def test_create_rejects_bad_codigo(self, bad):
        with pytest.raises(ValidationError):
            TipoArqueoCreate(codigo=bad)

    def test_create_accepts_max_codigo(self):
        c = TipoArqueoCreate(codigo="x" * 64)
        assert len(c.codigo) == 64


class TestOptionalFields:
    """``nombre`` and ``descripcion`` are both optional."""

    def test_create_minimal_only_codigo(self):
        c = TipoArqueoCreate(codigo="cierre_turno")
        assert c.codigo == "cierre_turno"
        assert c.nombre is None
        assert c.descripcion is None

    def test_create_full(self):
        c = TipoArqueoCreate(
            codigo="cierre_turno",
            nombre="Cierre de turno",
            descripcion="Arqueo ejecutado al cierre del turno del operador.",
        )
        assert c.nombre == "Cierre de turno"
        assert c.descripcion.startswith("Arqueo ejecutado")


class TestFilterAllOptional:
    def test_empty_filter(self):
        f = TipoArqueoFilter()
        assert f.estado is None
        assert f.codigo is None
        assert f.vigente_desde__gte is None

    def test_populated_filter(self):
        f = TipoArqueoFilter(estado="activo", codigo="cierre_turno")
        assert f.codigo == "cierre_turno"


class TestReadFromAttributes:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_read_from_dict(self):
        r = TipoArqueoRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000030"),
            codigo="cierre_turno",
            nombre="Cierre de turno",
            descripcion="Arqueo ejecutado al cierre del turno del operador.",
            vigente_desde=datetime(2026, 1, 1),
            vigente_hasta=None,
            estado="activo",
            created_at=datetime(2026, 1, 1),
            created_by=None,
            sync_status=None,
        )
        assert r.codigo == "cierre_turno"
        assert r.nombre == "Cierre de turno"


class TestReadList:
    def test_empty_list(self):
        rl = TipoArqueoReadList(items=[], next_cursor=None)
        assert rl.items == []

    def test_with_cursor(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        r = TipoArqueoRead(
            uuid=uuid_lib.UUID("00000000-0000-0000-0000-000000000031"),
            codigo="auditoria",
            nombre="Auditoría sorpresiva",
            descripcion=None,
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = TipoArqueoReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"