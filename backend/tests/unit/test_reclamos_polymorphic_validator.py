"""Tests for ``ReclamosCreate`` Pydantic validator + ``polymorphic_row_exists``.

REQ-OP-08 + REQ-23-W-POLYMORPHIC-FK. Two test surfaces:

1. **Pydantic edge validation** (``ReclamosCreate`` / ``ReclamosUpdate``) —
   ``tipo_reclamable`` MUST be one of ``Literal["ingreso", "salida", "factura"]``;
   ``uuid_reclamable`` MUST be a UUID. Unknown discriminator values return
   ``422`` BEFORE any DB hit.

2. **DB existence check** (``polymorphic_row_exists``) — validates
   ``(tipo_reclamable, uuid_reclamable)`` against the right polymorphic
   target table. Unknown ``tipo_reclamable`` raises
   :class:`UnknownPolymorphicTypeError`; missing rows return ``False``.
"""

from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.repo.workflow import (
    UnknownPolymorphicTypeError,
    polymorphic_row_exists,
)
from parkos_core.schemas.workflows import ReclamosCreate, ReclamosUpdate
from pydantic import ValidationError

UUID_A = uuid_lib.UUID("00000000-0000-0000-0000-00000000000a")
UUID_B = uuid_lib.UUID("00000000-0000-0000-0000-00000000000b")
UUID_C = uuid_lib.UUID("00000000-0000-0000-0000-00000000000c")


# ---------------------------------------------------------------------------
# Pydantic schema tests (no DB, no mock session)
# ---------------------------------------------------------------------------


class TestReclamosCreatePydantic:
    """``ReclamosCreate`` enforces the polymorphic FK discriminator at the API edge."""

    def test_create_accepts_tipo_ingreso(self):
        c = ReclamosCreate(tipo_reclamable="ingreso", uuid_reclamable=UUID_A)
        assert c.tipo_reclamable == "ingreso"
        assert c.uuid_reclamable == UUID_A

    def test_create_accepts_tipo_salida(self):
        c = ReclamosCreate(tipo_reclamable="salida", uuid_reclamable=UUID_B)
        assert c.tipo_reclamable == "salida"
        assert c.uuid_reclamable == UUID_B

    def test_create_accepts_tipo_factura(self):
        c = ReclamosCreate(tipo_reclamable="factura", uuid_reclamable=UUID_C)
        assert c.tipo_reclamable == "factura"
        assert c.uuid_reclamable == UUID_C

    def test_create_accepts_optional_motivo_and_sucursal(self):
        """Optional fields don't block creation; ``motivo`` is bounded to 1000 chars."""
        c = ReclamosCreate(
            tipo_reclamable="ingreso",
            uuid_reclamable=UUID_A,
            uuid_sucursal=UUID_B,
            motivo="customer complaint about parking duration",
        )
        assert c.motivo == "customer complaint about parking duration"
        assert c.uuid_sucursal == UUID_B

    def test_create_rejects_unknown_tipo(self):
        """Unknown ``tipo_reclamable`` raises ValidationError (422)."""
        with pytest.raises(ValidationError) as exc_info:
            ReclamosCreate(tipo_reclamable="otro", uuid_reclamable=UUID_A)
        # Pydantic v2 surfaces a literal_error on the discriminator.
        assert any(err["type"] == "literal_error" for err in exc_info.value.errors())

    def test_create_requires_uuid_reclamable(self):
        """Missing ``uuid_reclamable`` is rejected (REQ-23-W-POLYMORPHIC-FK)."""
        with pytest.raises(ValidationError) as exc_info:
            ReclamosCreate(tipo_reclamable="ingreso")  # type: ignore[call-arg]
        assert any(err["loc"] == ("uuid_reclamable",) for err in exc_info.value.errors())

    def test_create_rejects_non_uuid_reclamable(self):
        """``uuid_reclamable`` MUST be a valid UUID — strings that aren't UUID-shaped fail."""
        with pytest.raises(ValidationError):
            ReclamosCreate(tipo_reclamable="ingreso", uuid_reclamable="not-a-uuid")

    def test_create_forbids_extra_fields(self):
        """``extra='forbid'`` blocks unknown fields (defense in depth)."""
        with pytest.raises(ValidationError) as exc_info:
            ReclamosCreate(
                tipo_reclamable="ingreso",
                uuid_reclamable=UUID_A,
                estado="recibido",  # server-set; not allowed from the client
            )
        assert any(err["type"] == "extra_forbidden" for err in exc_info.value.errors())

    def test_update_accepts_optional_fields(self):
        """``ReclamosUpdate`` makes every field optional; empty payload is valid."""
        u = ReclamosUpdate()
        assert u.tipo_reclamable is None
        assert u.uuid_reclamable is None
        assert u.motivo is None

    def test_update_rejects_unknown_tipo(self):
        """Unknown discriminator on Update path also raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ReclamosUpdate(tipo_reclamable="vehiculo")
        assert any(err["type"] == "literal_error" for err in exc_info.value.errors())

    def test_update_accepts_known_tipo(self):
        u = ReclamosUpdate(tipo_reclamable="salida", motivo="investigation update")
        assert u.tipo_reclamable == "salida"
        assert u.motivo == "investigation update"


# ---------------------------------------------------------------------------
# polymorphic_row_exists tests (mock AsyncSession, no real DB)
# ---------------------------------------------------------------------------


def _result_scalar(row) -> MagicMock:
    """Wrap a row in a ``Result``-shaped mock with ``scalar_one_or_none``."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    return result


def _make_session_with_row(row) -> AsyncMock:
    """Mock AsyncSession whose ``execute().scalar_one_or_none()`` returns ``row``."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_result_scalar(row))
    return session


def _make_model_row() -> MagicMock:
    """Build a generic mock row — no ``spec`` so it matches any target ORM class."""
    row = MagicMock()
    row.uuid = UUID_A
    return row


class TestPolymorphicRowExists:
    """``polymorphic_row_exists`` resolves ``tipo_reclamable`` to the right table."""

    @pytest.mark.asyncio
    async def test_ingreso_exists_returns_true(self):
        """Mock session returns a row from ``Ingreso`` → ``True``."""
        session = _make_session_with_row(_make_model_row())

        found = await polymorphic_row_exists(
            session,
            tipo_reclamable="ingreso",
            uuid_reclamable=UUID_A,
        )
        assert found is True

    @pytest.mark.asyncio
    async def test_salida_exists_returns_true(self):
        """Mock session returns a row from ``Salidas`` → ``True``."""
        session = _make_session_with_row(_make_model_row())

        found = await polymorphic_row_exists(
            session,
            tipo_reclamable="salida",
            uuid_reclamable=UUID_B,
        )
        assert found is True

    @pytest.mark.asyncio
    async def test_factura_exists_returns_true(self):
        """Mock session returns a row from ``Facturas`` → ``True``."""
        session = _make_session_with_row(_make_model_row())

        found = await polymorphic_row_exists(
            session,
            tipo_reclamable="factura",
            uuid_reclamable=UUID_C,
        )
        assert found is True

    @pytest.mark.asyncio
    async def test_not_found_returns_false(self):
        """Mock session returns ``None`` → ``False`` (target row missing)."""
        session = _make_session_with_row(None)

        found = await polymorphic_row_exists(
            session,
            tipo_reclamable="ingreso",
            uuid_reclamable=UUID_A,
        )
        assert found is False

    @pytest.mark.asyncio
    async def test_unknown_tipo_raises(self):
        """``tipo_reclamable='otro'`` raises :class:`UnknownPolymorphicTypeError`."""
        session = _make_session_with_row(_make_model_row())

        with pytest.raises(UnknownPolymorphicTypeError, match="otro"):
            await polymorphic_row_exists(
                session,
                tipo_reclamable="otro",
                uuid_reclamable=UUID_A,
            )
        # Session MUST NOT be touched when the tipo is unknown (fast-fail).
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_execute_called_once_per_lookup(self):
        """Each ``polymorphic_row_exists`` call hits the DB exactly once."""
        session = _make_session_with_row(_make_model_row())

        await polymorphic_row_exists(
            session,
            tipo_reclamable="ingreso",
            uuid_reclamable=UUID_A,
        )
        session.execute.assert_awaited_once()
