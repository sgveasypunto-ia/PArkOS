"""Tests for ``repo.workflow.append_transition`` (REQ-21, SC-20).

Pure-Python tests using ``unittest.mock.AsyncMock`` to fake ``AsyncSession``.
Validates the [L-W] state-machine writer:

- ``append_transition`` writes a new chain row + a co-transactional
  ``log_transaccional`` row.
- The transition ``parent.estado -> new_attrs['estado']`` MUST be legal
  per :data:`STATE_MACHINES`; illegal transitions raise
  :class:`IllegalTransitionError`.
- ``model_cls`` MUST be a :class:`WorkflowBase` subclass and carry a
  :data:`STATE_MACHINES` entry; non-[L-W] classes raise
  :class:`WorkflowError`.
- ``new_attrs`` MUST contain ``estado``; missing key raises
  :class:`WorkflowError`.
- ``parent_uuid`` MUST resolve to an existing row; missing parent raises
  :class:`ChainNotFoundError`.
- :data:`STATE_MACHINES` covers all 6 [L-W] tables, and terminal
  states map to ``[]``.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.models.L_W.anulaciones import Anulaciones
from parkos_core.models.L_W.reclamos import Reclamos
from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
from parkos_core.models.V.tipo_persona import TipoPersona
from parkos_core.repo.workflow import (
    STATE_MACHINES,
    ChainNotFoundError,
    IllegalTransitionError,
    WorkflowError,
    append_transition,
)

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000bb")


def _make_session(parent_row=None) -> AsyncMock:
    """Mock ``AsyncSession`` — ``add()`` is sync, ``execute()`` is async.

    ``append_transition`` only calls ``session.execute`` when ``parent_uuid``
    is provided (to load the parent row); ``session.add`` is called once for
    the workflow row and once for the co-transactional log row.
    """
    session = AsyncMock()
    session.add = MagicMock()

    # Always wire ``session.execute`` (when parent_uuid is provided) so the
    # parent-lookup branch is mocked; pass ``None`` for missing parent rows.
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=parent_row)
    session.execute = AsyncMock(return_value=result)

    return session


def _make_reimpresion_row(uuid: uuid_lib.UUID, estado: str = "solicitada") -> MagicMock:
    """Build a mock ``ReimpresionTicket`` row for parent lookup."""
    row = MagicMock(spec=ReimpresionTicket)
    row.uuid = uuid
    row.estado = estado
    row.timestamp_evento = datetime(2026, 1, 1, 12, 0, 0)
    row.uuid_reimpresion_padre = None
    return row


class TestAppendTransitionRootRow:
    """Root row case (``parent_uuid=None``) — first transition in a chain."""

    @pytest.mark.asyncio
    async def test_session_add_called_twice_for_root_and_log(self):
        session = _make_session(parent_row=None)
        attrs = {
            "estado": "solicitada",
            "uuid_sucursal": SUCURSAL_UUID,
            "motivo": "first reprint",
        }
        await append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
            parent_uuid=None,
        )
        # Two adds: ReimpresionTicket row + LogTransaccional row.
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_root_row_carries_server_side_fields(self):
        session = _make_session(parent_row=None)
        attrs = {
            "estado": "solicitada",
            "uuid_sucursal": SUCURSAL_UUID,
            "motivo": "first reprint",
        }
        await append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
        )
        # First add call is the ReimpresionTicket row.
        new_row = session.add.call_args_list[0].args[0]
        assert isinstance(new_row, ReimpresionTicket)
        assert new_row.created_by == ACTOR_UUID
        assert new_row.created_at is not None
        # No parent FK set — root rows have uuid_reimpresion_padre=None.
        assert new_row.uuid_reimpresion_padre is None
        # Business attrs propagated.
        assert new_row.estado == "solicitada"
        assert new_row.uuid_sucursal == SUCURSAL_UUID
        assert new_row.motivo == "first reprint"

    @pytest.mark.asyncio
    async def test_log_transaccional_row_carries_correct_fields(self):
        session = _make_session(parent_row=None)
        attrs = {"estado": "solicitada", "uuid_sucursal": SUCURSAL_UUID}
        await append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
        )
        # Lazy import mirrors append_transition's pattern to avoid module-load circulars.
        from parkos_core.models.A.log_transaccional import LogTransaccional

        log_row = session.add.call_args_list[1].args[0]
        assert isinstance(log_row, LogTransaccional)
        assert log_row.uuid_usuario == ACTOR_UUID
        assert log_row.uuid_sucursal == SUCURSAL_UUID
        assert log_row.accion == "crear"
        assert log_row.tabla_afectada == "reimpresion_ticket"
        assert log_row.timestamp_evento is not None

    @pytest.mark.asyncio
    async def test_log_tx_false_skips_log_row(self):
        """``log_tx=False`` writes only the workflow row (1 add, not 2)."""
        session = _make_session(parent_row=None)
        attrs = {"estado": "solicitada"}
        await append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
            log_tx=False,
        )
        assert session.add.call_count == 1


class TestAppendTransitionLegalTransition:
    """Legal transition case (``parent_uuid=<existing>``)."""

    @pytest.mark.asyncio
    async def test_legal_solicitada_to_autorizada(self):
        parent_uuid = uuid_lib.uuid4()
        parent_row = _make_reimpresion_row(parent_uuid, estado="solicitada")
        session = _make_session(parent_row=parent_row)

        attrs = {"estado": "autorizada", "uuid_sucursal": SUCURSAL_UUID}
        await append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
            parent_uuid=parent_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )
        # Two adds: child ReimpresionTicket + log_transaccional.
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_parent_fk_wired_to_parent_uuid(self):
        """The new row's self-FK column points at the parent_uuid."""
        parent_uuid = uuid_lib.uuid4()
        parent_row = _make_reimpresion_row(parent_uuid, estado="solicitada")
        session = _make_session(parent_row=parent_row)

        attrs = {"estado": "autorizada"}
        await append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
            parent_uuid=parent_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )
        child_row = session.add.call_args_list[0].args[0]
        assert isinstance(child_row, ReimpresionTicket)
        assert child_row.uuid_reimpresion_padre == parent_uuid

    @pytest.mark.asyncio
    async def test_parent_lookup_executes_select(self):
        """``session.execute`` is called once to load the parent row."""
        parent_uuid = uuid_lib.uuid4()
        parent_row = _make_reimpresion_row(parent_uuid, estado="autorizada")
        session = _make_session(parent_row=parent_row)

        attrs = {"estado": "ejecutada"}
        await append_transition(
            session,
            ReimpresionTicket,
            actor_uuid=ACTOR_UUID,
            new_attrs=attrs,
            parent_uuid=parent_uuid,
            parent_fk_column="uuid_reimpresion_padre",
        )
        session.execute.assert_awaited_once()


class TestAppendTransitionIllegalTransition:
    """Illegal transitions raise :class:`IllegalTransitionError`."""

    @pytest.mark.asyncio
    async def test_ejecutada_is_terminal(self):
        """``ejecutada`` is terminal — transition to ``autorizada`` is illegal."""
        parent_uuid = uuid_lib.uuid4()
        parent_row = _make_reimpresion_row(parent_uuid, estado="ejecutada")
        session = _make_session(parent_row=parent_row)

        attrs = {"estado": "autorizada"}
        with pytest.raises(IllegalTransitionError, match="ejecutada"):
            await append_transition(
                session,
                ReimpresionTicket,
                actor_uuid=ACTOR_UUID,
                new_attrs=attrs,
                parent_uuid=parent_uuid,
                parent_fk_column="uuid_reimpresion_padre",
            )
        # No row added when transition is illegal.
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_rechazada_is_terminal(self):
        """``rechazada`` is terminal — transition to ``solicitada`` is illegal."""
        parent_uuid = uuid_lib.uuid4()
        parent_row = _make_reimpresion_row(parent_uuid, estado="rechazada")
        session = _make_session(parent_row=parent_row)

        attrs = {"estado": "solicitada"}
        with pytest.raises(IllegalTransitionError):
            await append_transition(
                session,
                ReimpresionTicket,
                actor_uuid=ACTOR_UUID,
                new_attrs=attrs,
                parent_uuid=parent_uuid,
                parent_fk_column="uuid_reimpresion_padre",
            )

    @pytest.mark.asyncio
    async def test_skips_intermediate_state(self):
        """``solicitada -> ejecutada`` skips ``autorizada`` — illegal."""
        parent_uuid = uuid_lib.uuid4()
        parent_row = _make_reimpresion_row(parent_uuid, estado="solicitada")
        session = _make_session(parent_row=parent_row)

        attrs = {"estado": "ejecutada"}
        with pytest.raises(IllegalTransitionError):
            await append_transition(
                session,
                ReimpresionTicket,
                actor_uuid=ACTOR_UUID,
                new_attrs=attrs,
                parent_uuid=parent_uuid,
                parent_fk_column="uuid_reimpresion_padre",
            )


class TestAppendTransitionTypeGuards:
    """Type guards and preconditions on the helper (REQ-21)."""

    @pytest.mark.asyncio
    async def test_rejects_v_model(self):
        """``[V]`` classes are NOT [L-W] — WorkflowError is raised."""
        session = _make_session(parent_row=None)
        with pytest.raises(WorkflowError, match="WorkflowBase"):
            await append_transition(
                session,
                TipoPersona,
                actor_uuid=ACTOR_UUID,
                new_attrs={"estado": "natural"},
            )
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_string(self):
        session = _make_session(parent_row=None)
        with pytest.raises(WorkflowError):
            await append_transition(
                session,
                "ReimpresionTicket",  # type: ignore[arg-type]
                actor_uuid=ACTOR_UUID,
                new_attrs={"estado": "solicitada"},
            )

    @pytest.mark.asyncio
    async def test_missing_estado_raises(self):
        """``new_attrs`` without ``estado`` raises WorkflowError."""
        session = _make_session(parent_row=None)
        with pytest.raises(WorkflowError, match="estado"):
            await append_transition(
                session,
                ReimpresionTicket,
                actor_uuid=ACTOR_UUID,
                new_attrs={"uuid_sucursal": SUCURSAL_UUID},
            )
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_parent_uuid_without_fk_column_raises(self):
        """``parent_uuid`` requires ``parent_fk_column``."""
        parent_uuid = uuid_lib.uuid4()
        session = _make_session(parent_row=None)
        with pytest.raises(WorkflowError, match="parent_fk_column"):
            await append_transition(
                session,
                ReimpresionTicket,
                actor_uuid=ACTOR_UUID,
                new_attrs={"estado": "autorizada"},
                parent_uuid=parent_uuid,
                parent_fk_column=None,
            )


class TestAppendTransitionParentNotFound:
    """``parent_uuid`` that does not match any row → :class:`ChainNotFoundError`."""

    @pytest.mark.asyncio
    async def test_missing_parent_raises(self):
        session = _make_session(parent_row=None)  # scalar_one_or_none returns None

        with pytest.raises(ChainNotFoundError):
            await append_transition(
                session,
                ReimpresionTicket,
                actor_uuid=ACTOR_UUID,
                new_attrs={"estado": "autorizada"},
                parent_uuid=uuid_lib.uuid4(),
                parent_fk_column="uuid_reimpresion_padre",
            )
        session.add.assert_not_called()


class TestStateMachines:
    """Validate :data:`STATE_MACHINES` shape and contents."""

    def test_state_machines_covers_six_lw_tables(self):
        """All 6 [L-W] tables have a STATE_MACHINES entry."""
        assert len(STATE_MACHINES) == 6
        assert set(STATE_MACHINES.keys()) == {
            "reimpresion_ticket",
            "anulaciones",
            "reclamos",
            "alerta",
            "envio_dian",
            "validacion_evento",
        }

    def test_terminal_states_have_empty_allowed(self):
        """For each table, states whose ``allowed == []`` are the terminal ones."""
        terminal_states = {
            "reimpresion_ticket": {"ejecutada", "rechazada"},
            "anulaciones": {"ejecutada", "rechazada"},
            "reclamos": {"resuelto", "rechazado"},
            "alerta": {"resuelta"},
            "envio_dian": {"ack", "error"},
            "validacion_evento": {"validado", "rechazado"},
        }
        for table, terminals in terminal_states.items():
            machine = STATE_MACHINES[table]
            actual_terminals = {state for state, allowed in machine.items() if allowed == []}
            assert actual_terminals == terminals, (
                f"{table}: terminal states mismatch. Expected {terminals}, got {actual_terminals}"
            )

    def test_all_tables_reference_real_orm_classes(self):
        """Every ``STATE_MACHINES`` key matches an ORM ``__tablename__``."""
        expected = {
            ReimpresionTicket.__tablename__,
            Anulaciones.__tablename__,
            Reclamos.__tablename__,
            Alerta.__tablename__,
        }
        # envio_dian + validacion_evento are cloud-only; their ORM classes
        # also exist in the workspace but we don't import them here to keep
        # the test lightweight.
        assert expected.issubset(set(STATE_MACHINES.keys()))
