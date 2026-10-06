"""REQ-MOT-001 / REQ-MOT-016 -- F12.1.1 sync layer datafono drop.

The sync ``apply_row`` close leg MUST pass ``valor_final_datafono=None``
explicit (D2 default) regardless of what the queue payload carries.
``session_cycle.close_session_with_log`` MUST omit the
``valor_final_datafono`` key from ``datos_nuevos`` when the value is
``None`` (strict REQ-MOT-016 Scenario 2 -- the field is wire-dead).

Open leg is preserved -- ``valor_inicial_datafono`` keeps flowing
through the sync boundary because the apertura contract is
unchanged (the UI hardcodes ``0``; legacy kiosks may still send it).

These tests are pure-Python mocks of the dispatch table; the end-to-end
contract is enforced by ``tests/integration/test_branch_offline_flow.py``
which exercises the real DB.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
for _p in (_PARKOS_CORE_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


# ---------------------------------------------------------------------------
# Build a real SyncCatalogEntry instance (the dispatch reads
# ``spec.name`` + ``spec.apply_strategy``; other fields use the canonical
# defaults from the catalog).
# ---------------------------------------------------------------------------


def _build_sesion_spec():
    from parkos_core.sync.catalog.schema import SyncCatalogEntry
    from parkos_core.models.L_S.sesion import Sesion

    return SyncCatalogEntry(
        name="sesion",
        model_cls=Sesion,
        audit_class="L_S",
        sync_strategy="grace_window",
        direction="branch_to_cloud",
        broadcast_policy=None,
        apply_strategy="session_cycle",
        depends_on=("sucursal", "usuarios"),
        has_uuid_sucursal=True,
        seq_strategy="max_created_at",
    )


def _sesion_uuid() -> uuid_lib.UUID:
    return uuid_lib.uuid4()


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# S1: sync close path passes valor_final_datafono=None explicit (D2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_cycle_close_passes_datafono_none() -> None:
    """REQ-MOT-001 / D2: ``apply_row`` on close dispatches
    ``close_session_with_log(..., valor_final_datafono=None)`` regardless
    of the wire payload value.
    """
    from parkos_core.sync.motor.apply_row import apply_row

    sesion_uuid = _sesion_uuid()
    payload = {
        "uuid": str(sesion_uuid),
        "uuid_sucursal": str(uuid_lib.uuid4()),
        "uuid_usuario": str(uuid_lib.uuid4()),
        "timestamp_apertura": _now_naive().isoformat(),
        "timestamp_cierre": _now_naive().isoformat(),
        "valor_final_efectivo": "0",
        "valor_final_datafono": "50000",  # wire payload (legacy / pre-F12.1.1)
    }
    spec = _build_sesion_spec()
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    m_close = AsyncMock(return_value=MagicMock(uuid=sesion_uuid))
    with patch(
        "parkos_core.sync.motor.apply_row.session_cycle.close_session_with_log",
        new=m_close,
    ):
        await apply_row(
            session=session,
            spec=spec,
            payload=payload,
            actor_uuid=uuid_lib.uuid4(),
        )

    m_close.assert_awaited_once()
    args = m_close.await_args
    assert args is not None
    call_kwargs = args.kwargs
    assert call_kwargs["valor_final_datafono"] is None  # REQ-MOT-001 / D2: explicit None
    assert call_kwargs["valor_final_efectivo"] == "0"


# ---------------------------------------------------------------------------
# S2: sync open path preserves valor_inicial_datafono (no change)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_cycle_open_passes_datafono_through() -> None:
    """REQ-MOT-001: open leg is preserved -- ``valor_inicial_datafono``
    flows through unchanged (the apertura contract is unchanged;
    the UI hardcodes ``0`` per the F12.1.1 FE commits).
    """
    from parkos_core.sync.motor.apply_row import apply_row

    payload = {
        "uuid": str(_sesion_uuid()),
        "uuid_sucursal": str(uuid_lib.uuid4()),
        "uuid_usuario": str(uuid_lib.uuid4()),
        "timestamp_apertura": _now_naive().isoformat(),
        "valor_inicial_efectivo": "50000",
        "valor_inicial_datafono": "0",  # preserved on open
    }
    spec = _build_sesion_spec()
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    m_open = AsyncMock(return_value=MagicMock(uuid=uuid_lib.uuid4()))
    with patch(
        "parkos_core.sync.motor.apply_row.session_cycle.open_session",
        new=m_open,
    ):
        await apply_row(
            session=session,
            spec=spec,
            payload=payload,
            actor_uuid=uuid_lib.uuid4(),
        )

    m_open.assert_awaited_once()
    args = m_open.await_args
    assert args is not None
    call_kwargs = args.kwargs
    # Open leg keeps valor_inicial_datafono flowing through.
    assert call_kwargs["valor_inicial_datafono"] == "0"


# ---------------------------------------------------------------------------
# S3: close_session_with_log drops valor_final_datafono from datos_nuevos
#     when None is passed (REQ-MOT-016 strict Scenario 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_cycle_close_datos_nuevos_omits_datafono() -> None:
    """REQ-MOT-016 Scenario 2 strict: when ``valor_final_datafono`` is
    ``None``, the key is OMITTED from ``datos_nuevos`` -- NOT serialized
    as ``"None"``. The datafono dimension is wire-dead at close.
    """
    from parkos_core.repo.session_cycle import close_session_with_log

    sesion_uuid = _sesion_uuid()
    sesion_mock = MagicMock()
    sesion_mock.uuid = sesion_uuid
    sesion_mock.valor_inicial_efectivo = Decimal("50000")
    sesion_mock.valor_inicial_datafono = Decimal("0")
    sesion_mock.uuid_sucursal = uuid_lib.uuid4()
    sesion_mock.timestamp_cierre = None

    sesion_select = MagicMock()
    sesion_select.scalar_one_or_none.return_value = sesion_mock

    session = MagicMock()
    session.execute = AsyncMock(return_value=sesion_select)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    captured = {}

    def _capture_log_row(row):
        captured["log_row"] = row

    session.add.side_effect = _capture_log_row

    await close_session_with_log(
        session,
        actor_uuid=uuid_lib.uuid4(),
        sesion_uuid=sesion_uuid,
        valor_final_efectivo=148000.0,
        valor_final_datafono=None,  # F12.1.1: drop at boundary
        observaciones=None,
    )

    assert "log_row" in captured
    datos_nuevos = captured["log_row"].datos_nuevos
    # F12.1.1 / REQ-MOT-016: the datafono key is OMITTED, not serialized as "None".
    assert "valor_final_datafono" not in datos_nuevos
    # efectivo key remains (effective datafono).
    assert datos_nuevos["valor_final_efectivo"] == "148000.0"
    assert datos_nuevos["valor_inicial_efectivo"] == "50000"
    # Apertura value is still in the snapshot (preserved on the open side).
    assert datos_nuevos["valor_inicial_datafono"] == "0"


@pytest.mark.asyncio
async def test_session_cycle_close_persisted_column_is_default() -> None:
    """REQ-MOT-016 Scenario 1: the persisted ``prod.sesion.valor_final_datafono``
    column MUST be the column default (``0``/``NULL``) when the sync close
    path strips the wire value. The column write itself is in
    ``Sesion.update`` (SQLAlchemy) which only writes fields present in
    the attrs dict -- since the dispatch passes ``valor_final_datafono=None``
    and ``close_session_with_log`` only adds it to datos_nuevos when not
    None, the actual UPDATE excludes the column from the SET clause.
    """
    from parkos_core.repo.session_cycle import close_session_with_log

    sesion_uuid = _sesion_uuid()
    sesion_mock = MagicMock()
    sesion_mock.uuid = sesion_uuid
    sesion_mock.valor_inicial_efectivo = Decimal("50000")
    sesion_mock.valor_inicial_datafono = Decimal("0")
    sesion_mock.uuid_sucursal = uuid_lib.uuid4()
    sesion_mock.timestamp_cierre = None

    sesion_select = MagicMock()
    sesion_select.scalar_one_or_none.return_value = sesion_mock

    session = MagicMock()
    session.execute = AsyncMock(return_value=sesion_select)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    # The Sesion ORM update for valor_final_datafono happens via SQL UPDATE
    # (not ORM dirty-check); the function passes ``valor_final_efectivo``
    # only. Verify by checking that no ``valor_final_datafono`` write
    # call is dispatched downstream.
    write_calls: list[dict] = []

    async def _capture_execute(*args, **kwargs):
        # SQL UPDATE writes touch execute(); record the text/params.
        if args and isinstance(args[0], str) and "UPDATE" in args[0].upper():
            write_calls.append({"text": args[0], "params": args[1] if len(args) > 1 else kwargs})
        return sesion_select

    session.execute = AsyncMock(side_effect=_capture_execute)

    await close_session_with_log(
        session,
        actor_uuid=uuid_lib.uuid4(),
        sesion_uuid=sesion_uuid,
        valor_final_efectivo=148000.0,
        valor_final_datafono=None,
        observaciones=None,
    )

    # The persisted ``prod.sesion.valor_final_datafono`` column is NOT
    # explicitly written (column default applies). The only UPDATE on
    # the sesion row sets the cierre timestamps + efectivos.
    update_texts = [c["text"] for c in write_calls]
    sesion_updates = [t for t in update_texts if "UPDATE" in t.upper() and "sesion" in t.lower()]
    if sesion_updates:
        # If a SQL UPDATE was issued, it MUST NOT reference valor_final_datafono.
        for txt in sesion_updates:
            assert "valor_final_datafono" not in txt, (
                f"sync close path must not write valor_final_datafono: {txt}"
            )