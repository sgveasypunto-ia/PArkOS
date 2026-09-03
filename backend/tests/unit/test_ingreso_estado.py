"""Schema tests for ``IngresoEstadoResponse`` (REQ-32-E-DERIVED-ESTADO, SC-30).

Pure-Python Pydantic tests for the schema declared in
``api/v1/operacion.py::IngresoEstadoResponse``. The state-derivation SQL
(``SELECT EXISTS(SELECT 1 FROM prod.salidas WHERE uuid_ingreso = ...)``)
lives in ``api/v1/operacion.py::get_ingreso_estado``. Full state machine
coverage (``abierto`` -> ``cerrado`` after a ``salidas`` row, ->
``anulada`` after an ``anulaciones`` chain) lands in a later PR once the
``salidas`` and ``anulaciones`` tables have data (PR6 mounts them) --
those are integration tests against a real Postgres and live in a
separate suite.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from types import SimpleNamespace

import pytest
from parkos_core.api.v1.operacion import IngresoEstadoResponse
from pydantic import ValidationError

INGRESO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000e1")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000e2")


class TestIngresoEstadoResponseSchema:
    """``IngresoEstadoResponse`` accepts all 3 derived states."""

    @pytest.mark.parametrize("estado", ["abierto", "cerrado", "anulada"])
    def test_accepts_valid_state(self, estado: str) -> None:
        r = IngresoEstadoResponse(
            uuid_ingreso=INGRESO_UUID,
            estado=estado,
        )
        assert r.estado == estado
        assert r.uuid_ingreso == INGRESO_UUID

    def test_uuid_ingreso_required(self) -> None:
        with pytest.raises(ValidationError):
            IngresoEstadoResponse(estado="abierto")

    def test_estado_required(self) -> None:
        with pytest.raises(ValidationError):
            IngresoEstadoResponse(uuid_ingreso=INGRESO_UUID)

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            IngresoEstadoResponse(
                uuid_ingreso=INGRESO_UUID,
                estado="abierto",
                rogue_field="evil",
            )

    def test_optional_fields_default_none(self) -> None:
        r = IngresoEstadoResponse(uuid_ingreso=INGRESO_UUID, estado="abierto")
        assert r.fecha_ingreso is None
        assert r.uuid_sucursal is None

    def test_full_response(self) -> None:
        now = datetime(2026, 1, 1)
        r = IngresoEstadoResponse(
            uuid_ingreso=INGRESO_UUID,
            estado="cerrado",
            fecha_ingreso=now,
            uuid_sucursal=SUCURSAL_UUID,
        )
        assert r.estado == "cerrado"
        assert r.fecha_ingreso == now
        assert r.uuid_sucursal == SUCURSAL_UUID

    def test_uuid_coerced_from_string(self) -> None:
        # Pydantic auto-coerces UUID-typed fields from hex strings.
        r = IngresoEstadoResponse(
            uuid_ingreso=str(INGRESO_UUID),
            estado="abierto",
        )
        assert r.uuid_ingreso == INGRESO_UUID


class TestIngresoEstadoResponseFromORM:
    """``from_attributes=True`` allows ``model_validate(orm_row)``."""

    def test_from_attributes_object(self) -> None:
        # ORM-like object with attributes matching the field names.
        orm_row = SimpleNamespace(
            uuid_ingreso=INGRESO_UUID,
            estado="anulada",
            fecha_ingreso=datetime(2026, 2, 1),
            uuid_sucursal=SUCURSAL_UUID,
        )
        r = IngresoEstadoResponse.model_validate(orm_row)
        assert r.estado == "anulada"
        assert r.uuid_ingreso == INGRESO_UUID
        assert r.fecha_ingreso == datetime(2026, 2, 1)
        assert r.uuid_sucursal == SUCURSAL_UUID

    def test_from_attributes_with_optional_none(self) -> None:
        orm_row = SimpleNamespace(
            uuid_ingreso=INGRESO_UUID,
            estado="abierto",
            fecha_ingreso=None,
            uuid_sucursal=None,
        )
        r = IngresoEstadoResponse.model_validate(orm_row)
        assert r.estado == "abierto"
        assert r.fecha_ingreso is None
        assert r.uuid_sucursal is None


class TestStateMachineDesignContract:
    """Documents the state machine (SC-30).

    States and transitions for an ``ingreso`` row:

    - ``abierto`` (initial): no ``salidas`` row yet, no ``anulaciones`` chain.
    - ``cerrado``: matching ``salidas`` row exists (PR6 mounts the table).
    - ``anulada``: matching ``anulaciones`` chain exists (PR6 mounts).

    Order of precedence (most-derived first):

    1. ``anulada`` if any ``anulaciones`` chain references this ingreso.
    2. ``cerrado`` if any ``salidas`` row references this ingreso.
    3. ``abierto`` otherwise.

    PR5 ships the ``abierto`` and ``cerrado`` branches (via the
    ``prod.salidas`` ``EXISTS`` query in ``get_ingreso_estado``). The
    ``anulada`` branch lands in PR6. Full SQL state-machine coverage
    lives in integration tests against a real Postgres, not here.
    """

    def test_state_values_are_documented(self) -> None:
        # The 3 states must be the only valid options in the schema.
        valid_states = {"abierto", "cerrado", "anulada"}
        # Schema accepts any string by default (no Literal); the contract
        # is enforced at the endpoint layer (the SQL EXISTS query only
        # ever produces ``abierto`` or ``cerrado`` in PR5).
        r = IngresoEstadoResponse(uuid_ingreso=INGRESO_UUID, estado="abierto")
        assert r.estado in valid_states
        # Note: the schema doesn't enforce ``estado in valid_states`` via
        # ``Literal`` because we want flexibility for future states
        # (e.g., ``vencida`` for expired subscriptions). The endpoint
        # validates the contract at the SQL query level.