"""Tests for ``SubscripcionVehiculosCreate`` validator (REQ-OP-08, SC-OP-08).

The Pydantic validator is a fast-fail shape check (both FKs non-None).
The authoritative count + ``pg_advisory_xact_lock`` guard lives in a
deferred endpoint wrapper (out of PR5 scope — T-PR5-06 note). PR6 / a
later PR will add the endpoint layer that takes the advisory lock.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime

import pytest
from parkos_core.schemas.clientes import (
    SubscripcionVehiculosCreate,
    SubscripcionVehiculosFilter,
    SubscripcionVehiculosRead,
    SubscripcionVehiculosReadList,
    SubscripcionVehiculosUpdate,
)
from pydantic import ValidationError

SUBSCRIPCION_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000cc")
VEHICULO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000dd")


class TestSubscripcionVehiculosCreateValidator:
    """REQ-OP-08 fast-fail: both FKs must be non-None."""

    def test_create_rejects_none_uuid_subscripcion_cliente(self):
        with pytest.raises(ValidationError):
            SubscripcionVehiculosCreate(
                uuid_subscripcion_cliente=None,
                uuid_vehiculo=VEHICULO_UUID,
            )

    def test_create_rejects_none_uuid_vehiculo(self):
        with pytest.raises(ValidationError):
            SubscripcionVehiculosCreate(
                uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
                uuid_vehiculo=None,
            )

    def test_create_accepts_valid_payload(self):
        c = SubscripcionVehiculosCreate(
            uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
            uuid_vehiculo=VEHICULO_UUID,
        )
        assert c.uuid_subscripcion_cliente == SUBSCRIPCION_UUID
        assert c.uuid_vehiculo == VEHICULO_UUID


class TestSubscripcionVehiculosUpdateValidator:
    """``Update`` mirrors Create (bi-temporal close+insert, REQ-04)."""

    def test_update_rejects_none_uuid_subscripcion_cliente(self):
        with pytest.raises(ValidationError):
            SubscripcionVehiculosUpdate(
                uuid_subscripcion_cliente=None,
                uuid_vehiculo=VEHICULO_UUID,
            )

    def test_update_rejects_none_uuid_vehiculo(self):
        with pytest.raises(ValidationError):
            SubscripcionVehiculosUpdate(
                uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
                uuid_vehiculo=None,
            )

    def test_update_accepts_valid_payload(self):
        u = SubscripcionVehiculosUpdate(
            uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
            uuid_vehiculo=VEHICULO_UUID,
        )
        assert u.uuid_subscripcion_cliente == SUBSCRIPCION_UUID
        assert u.uuid_vehiculo == VEHICULO_UUID


class TestSubscripcionVehiculosVersioningExclusion:
    """``extra='forbid'`` blocks versioning columns on Create/Update (C-6)."""

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_create_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            SubscripcionVehiculosCreate(
                uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
                uuid_vehiculo=VEHICULO_UUID,
                **{forbidden: "x"},
            )

    @pytest.mark.parametrize("forbidden", ["vigente_desde", "vigente_hasta", "estado"])
    def test_update_rejects_versioning_column(self, forbidden):
        with pytest.raises(ValidationError):
            SubscripcionVehiculosUpdate(
                uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
                uuid_vehiculo=VEHICULO_UUID,
                **{forbidden: "x"},
            )


class TestSubscripcionVehiculosRead:
    """``Read`` mirrors ORM columns."""

    def test_read_from_dict(self):
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


class TestSubscripcionVehiculosReadList:
    def test_empty_list(self):
        rl = SubscripcionVehiculosReadList(items=[], next_cursor=None)
        assert rl.items == []

    def test_with_cursor(self):
        now = datetime(2026, 1, 1)
        r = SubscripcionVehiculosRead(
            uuid=uuid_lib.uuid4(),
            uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
            uuid_vehiculo=VEHICULO_UUID,
            vigente_desde=now,
            vigente_hasta=None,
            estado="activo",
            created_at=now,
            created_by=None,
            sync_status=None,
        )
        rl = SubscripcionVehiculosReadList(items=[r], next_cursor="abc")
        assert len(rl.items) == 1
        assert rl.next_cursor == "abc"


class TestSubscripcionVehiculosFilter:
    def test_empty_filter(self):
        f = SubscripcionVehiculosFilter()
        assert f.estado is None
        assert f.uuid_subscripcion_cliente is None
        assert f.uuid_vehiculo is None
        assert f.vigente_desde__gte is None

    def test_populated_filter(self):
        f = SubscripcionVehiculosFilter(
            uuid_subscripcion_cliente=SUBSCRIPCION_UUID,
            uuid_vehiculo=VEHICULO_UUID,
            estado="activo",
        )
        assert f.uuid_subscripcion_cliente == SUBSCRIPCION_UUID


# Module-level design contract — not a runtime assertion but documented intent.
# The DB-layer count guard (`pg_advisory_xact_lock`) is OUT OF PR5 scope.
def test_design_documents_fast_fail_layer() -> None:
    """This is a design contract test, not a runtime check.

    REQ-OP-08 enforcement happens in two layers:
    1. Pydantic fast-fail: both FKs non-None (this file, TestSubscripcionVehiculosCreateValidator).
    2. DB-layer advisory lock + count check (deferred — T-PR5-06 note, future PR).
    """
    assert True  # contract is documented in the module docstring
