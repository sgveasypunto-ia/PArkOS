"""Tests for ``repo.event.record_event`` (REQ-30, REQ-33).

Pure-Python tests using ``unittest.mock.AsyncMock`` to fake ``AsyncSession``.
Validates:

- ``LifecycleEventWriteError`` raised for non-``[L-E]`` model classes.
- ``session.add`` called twice (event row + ``LogTransaccional`` row) by default.
- Server-side ``created_at`` + ``created_by`` set on the new event row.
- ``log_tx=False`` skips the ``LogTransaccional`` row.
- ``record_event`` does NOT commit (caller's responsibility).
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.repo.event import (
    LIFECYCLE_EVENT_FORBIDDEN_MSG,
    LifecycleEventWriteError,
    record_event,
)

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000bb")


def _make_session() -> AsyncMock:
    """Mock ``AsyncSession`` — ``add()`` is sync, ``flush()`` / ``execute()`` are async.

    After PR11c wired ``record_event(log_tx=True)`` →
    ``hash_chain.append`` → ``session.execute(stmt)`` to read the prior
    chain head, the mock must stub ``execute()`` too. We return a
    Result-like whose ``scalar_one_or_none()`` is a FAKE PRIOR ROW (not
    ``None``) — PR6's genesis-row auto-bootstrap
    (``repo.hash_chain._ensure_genesis_row``) only activates on the "no
    prior row" branch, and it ``session.add()``s + ``session.flush()``es a
    genesis row when it does. This file's assertions are about
    ``record_event``'s OWN dispatch logic (exactly 2 adds: the event row +
    its log row; never flushing — that stays the caller's responsibility),
    an orthogonal concern to hash-chain genesis bootstrapping (covered by
    ``tests/unit/test_hash_chain.py`` / ``test_log_transaccional_chain.py``
    instead) — simulating an EXISTING chain here keeps those assertions
    decoupled from that unrelated first-call-only behavior.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    fake_prior_row = MagicMock()
    fake_prior_row.hash_actual = "a" * 64
    fake_result = MagicMock()
    fake_result.scalar_one_or_none = MagicMock(return_value=fake_prior_row)
    session.execute = AsyncMock(return_value=fake_result)
    return session


class TestRecordEventHappyPath:
    """``record_event`` happy path with valid ``Ingreso`` + attrs."""

    @pytest.mark.asyncio
    async def test_session_add_called_twice_by_default(self):
        session = _make_session()
        attrs = {
            "uuid_sucursal": SUCURSAL_UUID,
            "placa": "ABC123",
            "uuid_tipo_vehiculo": uuid_lib.uuid4(),
            "fecha_ingreso": "2026-01-01T08:00:00",
            "observaciones": "PR5 test",
        }
        await record_event(session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs)
        # Two adds: Ingreso row + LogTransaccional row
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_new_ingreso_row_has_server_side_fields(self):
        session = _make_session()
        attrs = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}
        await record_event(session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs)
        # First add call is the Ingreso row
        ingreso_row = session.add.call_args_list[0].args[0]
        assert isinstance(ingreso_row, Ingreso)
        assert ingreso_row.created_by == ACTOR_UUID
        assert ingreso_row.created_at is not None
        # Propagated business attrs
        assert ingreso_row.placa == "ABC123"
        assert ingreso_row.uuid_sucursal == SUCURSAL_UUID

    @pytest.mark.asyncio
    async def test_log_transaccional_row_carries_correct_fields(self):
        session = _make_session()
        attrs = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}
        await record_event(session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs)
        # Second add call is the LogTransaccional row
        # Lazy import mirrors record_event's own pattern to avoid module-load circulars.
        from parkos_core.models.A.log_transaccional import LogTransaccional

        log_row = session.add.call_args_list[1].args[0]
        assert isinstance(log_row, LogTransaccional)
        assert log_row.uuid_usuario == ACTOR_UUID
        assert log_row.uuid_sucursal == SUCURSAL_UUID
        assert log_row.accion == "crear"
        assert log_row.tabla_afectada == "ingreso"
        assert log_row.timestamp_evento is not None

    @pytest.mark.asyncio
    async def test_propagates_extra_attrs_to_row(self):
        """All keys in ``new_attrs`` end up on the new Ingreso row."""
        session = _make_session()
        uuid_tipo_vehiculo = uuid_lib.uuid4()
        uuid_subscripcion = uuid_lib.uuid4()
        fecha_ingreso = "2026-02-15T09:30:00"
        attrs = {
            "uuid_sucursal": SUCURSAL_UUID,
            "placa": "XYZ789",
            "uuid_tipo_vehiculo": uuid_tipo_vehiculo,
            "uuid_subscripcion_cliente": uuid_subscripcion,
            "fecha_ingreso": fecha_ingreso,
            "observaciones": "monthly subscriber",
        }
        await record_event(session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs)
        ingreso_row = session.add.call_args_list[0].args[0]
        assert ingreso_row.placa == "XYZ789"
        assert ingreso_row.uuid_tipo_vehiculo == uuid_tipo_vehiculo
        assert ingreso_row.uuid_subscripcion_cliente == uuid_subscripcion
        assert ingreso_row.observaciones == "monthly subscriber"
        # ``fecha_ingreso`` was passed as ISO string — accepted by SQLAlchemy
        # column coercion; the ORM stores it as the value passed in
        # (no session.flush happened).
        assert ingreso_row.fecha_ingreso == fecha_ingreso

    @pytest.mark.asyncio
    async def test_returns_new_ingreso_instance(self):
        session = _make_session()
        attrs = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}
        result = await record_event(session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs)
        assert isinstance(result, Ingreso)
        assert result.placa == "ABC123"


class TestRecordEventLogTxFalse:
    """``log_tx=False`` skips the ``LogTransaccional`` row."""

    @pytest.mark.asyncio
    async def test_only_one_session_add_call(self):
        session = _make_session()
        attrs = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}
        await record_event(
            session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs, log_tx=False
        )
        assert session.add.call_count == 1
        # First (and only) add is the Ingreso row, NOT a LogTransaccional
        from parkos_core.models.A.log_transaccional import LogTransaccional

        added = session.add.call_args_list[0].args[0]
        assert isinstance(added, Ingreso)
        assert not isinstance(added, LogTransaccional)


class TestRecordEventTypeGuard:
    """``record_event`` rejects non-``[L-E]`` model classes (REQ-30)."""

    @pytest.mark.asyncio
    async def test_rejects_v_model(self):
        session = _make_session()
        with pytest.raises(LifecycleEventWriteError):
            await record_event(
                session,
                TipoPersona,  # [V], NOT [L-E]
                actor_uuid=ACTOR_UUID,
                new_attrs={"tipo": "natural"},
            )

    @pytest.mark.asyncio
    async def test_rejects_string(self):
        session = _make_session()
        with pytest.raises(LifecycleEventWriteError):
            await record_event(
                session,
                "Ingreso",  # type: ignore[arg-type]
                actor_uuid=ACTOR_UUID,
                new_attrs={},
            )

    @pytest.mark.asyncio
    async def test_rejects_none(self):
        session = _make_session()
        with pytest.raises(LifecycleEventWriteError):
            await record_event(
                session,
                None,  # type: ignore[arg-type]
                actor_uuid=ACTOR_UUID,
                new_attrs={},
            )

    @pytest.mark.asyncio
    async def test_rejects_int(self):
        """Non-class primitives also fail the ``isinstance(model_cls, type)`` guard."""
        session = _make_session()
        with pytest.raises(LifecycleEventWriteError):
            await record_event(
                session,
                42,  # type: ignore[arg-type]
                actor_uuid=ACTOR_UUID,
                new_attrs={},
            )


class TestRecordEventActorUuid:
    """``actor_uuid`` flows into ``created_by`` on the new row."""

    @pytest.mark.asyncio
    async def test_created_by_matches_actor_uuid(self):
        session = _make_session()
        other_actor = uuid_lib.UUID("00000000-0000-0000-0000-0000000000ff")
        attrs = {"uuid_sucursal": SUCURSAL_UUID, "placa": "AAA111"}
        await record_event(session, Ingreso, actor_uuid=other_actor, new_attrs=attrs)
        ingreso_row = session.add.call_args_list[0].args[0]
        assert ingreso_row.created_by == other_actor
        assert ingreso_row.created_by != ACTOR_UUID


class TestRecordEventNoCommit:
    """``record_event`` MUST NOT call ``session.commit()`` (caller's responsibility)."""

    @pytest.mark.asyncio
    async def test_does_not_call_session_commit(self):
        session = _make_session()
        attrs = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}
        await record_event(session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs)
        # ``commit`` MUST NOT have been called — record_event only adds rows.
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_call_session_flush(self):
        session = _make_session()
        attrs = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}
        await record_event(session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=attrs)
        session.flush.assert_not_called()


def test_lifecycle_event_forbidden_msg_is_string():
    """Marker string is exported (AST test in T-PR5-13 scans for it)."""
    assert isinstance(LIFECYCLE_EVENT_FORBIDDEN_MSG, str)
    assert "[L-E]" in LIFECYCLE_EVENT_FORBIDDEN_MSG
    assert "record_event" in LIFECYCLE_EVENT_FORBIDDEN_MSG