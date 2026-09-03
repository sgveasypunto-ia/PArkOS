"""Tests for ``repo.factura_pagos.reverse_payment`` (REQ-OP-09, SC-11).

Pure-Python tests using ``unittest.mock.AsyncMock`` to fake ``AsyncSession``.
Validates the compensating-payment flow:

- ``reverse_payment`` reads the original ``factura_pagos`` row, builds a
  NEW row with ``tipo_movimiento='reverso'`` and
  ``uuid_pago_revertido=<original.uuid>``, and writes a co-transactional
  ``log_transaccional`` row.
- A missing ``original_pago_uuid`` raises :class:`PagoNotFoundError`.
- A second reversal attempt on the same payment raises
  :class:`DuplicateReversoError` (HTTP 409) — the DB-layer partial unique
  index ``uq_factura_pagos_reverso`` is mocked as an
  :class:`sqlalchemy.exc.IntegrityError` whose ``orig`` message carries
  the index name or ``"duplicate key"`` token.
- ``IntegrityError`` from a different constraint propagates unchanged
  (not wrapped as :class:`DuplicateReversoError`).
"""

from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.models.A.factura_pagos import FacturaPagos
from parkos_core.repo.factura_pagos import (
    DuplicateReversoError,
    PagoNotFoundError,
    reverse_payment,
)
from sqlalchemy.exc import IntegrityError

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")
ORIGINAL_PAGO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-000000000001")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000bb")
FACTURA_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000cc")
SESION_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000dd")


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_original_pago_row(
    *,
    valor: float = 150.0,
    medio_pago: str = "efectivo",
    referencia: str | None = "REF-001",
) -> MagicMock:
    """Build a mock ``FacturaPagos`` original-row (the pago being reversed)."""
    row = MagicMock(spec=FacturaPagos)
    row.uuid = ORIGINAL_PAGO_UUID
    row.uuid_sucursal = SUCURSAL_UUID
    row.uuid_factura = FACTURA_UUID
    row.uuid_sesion = SESION_UUID
    row.medio_pago = medio_pago
    row.valor = valor
    row.referencia = referencia
    row.tipo_movimiento = "pago"
    row.uuid_pago_revertido = None
    row.timestamp_evento = None
    row.fecha_retencion_hasta = None
    return row


def _make_session_with_original(
    original_row: MagicMock | None,
    *,
    flush_side_effect: Exception | None = None,
) -> AsyncMock:
    """Build a mock ``AsyncSession`` with controlled SELECT + flush behaviour.

    The ``session.execute`` returns the original row (or ``None``); the
    optional ``flush_side_effect`` lets tests raise from the flush call to
    simulate the partial unique index violation.
    """
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=original_row)
    session.execute = AsyncMock(return_value=result)
    if flush_side_effect is not None:
        session.flush = AsyncMock(side_effect=flush_side_effect)
    else:
        session.flush = AsyncMock()
    return session


class _IntegrityOrig:
    """Mimics a psycopg ``orig`` whose ``str()`` carries the constraint name."""

    def __init__(self, message: str) -> None:
        self._message = message

    def __str__(self) -> str:
        return self._message


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestReversePaymentHappyPath:
    """``reverse_payment`` happy path — original row found, no constraint violation."""

    @pytest.mark.asyncio
    async def test_session_add_called_twice_for_reverso_and_log(self):
        original = _make_original_pago_row()
        session = _make_session_with_original(original)

        await reverse_payment(
            session,
            actor_uuid=ACTOR_UUID,
            original_pago_uuid=ORIGINAL_PAGO_UUID,
        )
        # Two adds: compensating reverso row + log_transaccional row.
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_reverso_row_carries_reverso_discriminator(self):
        original = _make_original_pago_row(valor=200.0)
        session = _make_session_with_original(original)

        result_row = await reverse_payment(
            session,
            actor_uuid=ACTOR_UUID,
            original_pago_uuid=ORIGINAL_PAGO_UUID,
        )
        assert isinstance(result_row, FacturaPagos)
        # Server-set discriminator flags.
        assert result_row.tipo_movimiento == "reverso"
        assert result_row.uuid_pago_revertido == ORIGINAL_PAGO_UUID
        # Mirrored business attributes.
        assert result_row.valor == 200.0
        assert result_row.uuid_sucursal == SUCURSAL_UUID
        assert result_row.uuid_factura == FACTURA_UUID
        assert result_row.medio_pago == "efectivo"
        # Server-set audit + DIAN retention.
        assert result_row.created_at is not None
        assert result_row.created_by == ACTOR_UUID
        assert result_row.timestamp_evento is not None
        assert result_row.fecha_retencion_hasta is not None

    @pytest.mark.asyncio
    async def test_log_transaccional_row_carries_motivo(self):
        original = _make_original_pago_row()
        session = _make_session_with_original(original)

        await reverse_payment(
            session,
            actor_uuid=ACTOR_UUID,
            original_pago_uuid=ORIGINAL_PAGO_UUID,
            motivo="customer complaint",
        )
        from parkos_core.models.A.log_transaccional import LogTransaccional

        log_row = session.add.call_args_list[1].args[0]
        assert isinstance(log_row, LogTransaccional)
        assert log_row.uuid_usuario == ACTOR_UUID
        assert log_row.uuid_sucursal == SUCURSAL_UUID
        assert log_row.accion == "compensar"
        assert log_row.tabla_afectada == "factura_pagos"
        assert log_row.uuid_referencia == ORIGINAL_PAGO_UUID
        assert log_row.datos_nuevos["motivo"] == "customer complaint"
        assert log_row.datos_nuevos["tipo_movimiento"] == "reverso"

    @pytest.mark.asyncio
    async def test_log_tx_false_skips_log_row(self):
        original = _make_original_pago_row()
        session = _make_session_with_original(original)

        await reverse_payment(
            session,
            actor_uuid=ACTOR_UUID,
            original_pago_uuid=ORIGINAL_PAGO_UUID,
            log_tx=False,
        )
        # Only the reverso row; no log_transaccional.
        assert session.add.call_count == 1
        added = session.add.call_args_list[0].args[0]
        assert isinstance(added, FacturaPagos)
        from parkos_core.models.A.log_transaccional import LogTransaccional

        assert not isinstance(added, LogTransaccional)

    @pytest.mark.asyncio
    async def test_flush_is_called(self):
        """``reverse_payment`` MUST call ``session.flush()`` to surface the
        partial unique index violation at the helper's boundary (not at commit)."""
        original = _make_original_pago_row()
        session = _make_session_with_original(original)

        await reverse_payment(
            session,
            actor_uuid=ACTOR_UUID,
            original_pago_uuid=ORIGINAL_PAGO_UUID,
        )
        session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# PagoNotFoundError path
# ---------------------------------------------------------------------------


class TestReversePaymentPagoNotFound:
    """Original uuid that does not match any row → :class:`PagoNotFoundError`."""

    @pytest.mark.asyncio
    async def test_missing_original_raises(self):
        session = _make_session_with_original(original_row=None)

        with pytest.raises(PagoNotFoundError):
            await reverse_payment(
                session,
                actor_uuid=ACTOR_UUID,
                original_pago_uuid=ORIGINAL_PAGO_UUID,
            )
        # No row added when the original is missing.
        session.add.assert_not_called()
        session.flush.assert_not_called()


# ---------------------------------------------------------------------------
# DuplicateReversoError path — partial unique index violation
# ---------------------------------------------------------------------------


class TestReversePaymentDuplicate:
    """Partial unique index ``uq_factura_pagos_reverso`` blocks a second reversal."""

    @pytest.mark.asyncio
    async def test_duplicate_via_index_name_message(self):
        """``e.orig`` carries the partial unique index name → DuplicateReversoError."""
        original = _make_original_pago_row()
        orig = _IntegrityOrig(
            'duplicate key value violates unique constraint "uq_factura_pagos_reverso"'
        )
        err = IntegrityError("INSERT INTO factura_pagos ...", None, orig)
        session = _make_session_with_original(original, flush_side_effect=err)

        with pytest.raises(DuplicateReversoError, match="already been reversed"):
            await reverse_payment(
                session,
                actor_uuid=ACTOR_UUID,
                original_pago_uuid=ORIGINAL_PAGO_UUID,
            )

    @pytest.mark.asyncio
    async def test_duplicate_via_duplicate_key_token(self):
        """``e.orig`` carries ``"duplicate key"`` → DuplicateReversoError (defensive)."""
        original = _make_original_pago_row()
        orig = _IntegrityOrig('duplicate key value violates unique constraint "some_other_idx"')
        err = IntegrityError("INSERT INTO factura_pagos ...", None, orig)
        session = _make_session_with_original(original, flush_side_effect=err)

        with pytest.raises(DuplicateReversoError):
            await reverse_payment(
                session,
                actor_uuid=ACTOR_UUID,
                original_pago_uuid=ORIGINAL_PAGO_UUID,
            )


# ---------------------------------------------------------------------------
# Other IntegrityError propagation — defense in depth
# ---------------------------------------------------------------------------


class TestReversePaymentIntegrityErrorPropagation:
    """``IntegrityError`` from a non-duplicate constraint MUST propagate unchanged."""

    @pytest.mark.asyncio
    async def test_other_constraint_error_propagates(self):
        original = _make_original_pago_row()
        orig = _IntegrityOrig(
            'insert or update on table "factura_pagos" violates foreign key '
            'constraint "fk_factura_pagos_factura"'
        )
        err = IntegrityError("INSERT INTO factura_pagos ...", None, orig)
        session = _make_session_with_original(original, flush_side_effect=err)

        with pytest.raises(IntegrityError) as exc_info:
            await reverse_payment(
                session,
                actor_uuid=ACTOR_UUID,
                original_pago_uuid=ORIGINAL_PAGO_UUID,
            )
        # Must NOT be wrapped as DuplicateReversoError.
        assert not isinstance(exc_info.value, DuplicateReversoError)
        assert "fk_factura_pagos_factura" in str(exc_info.value.orig)
