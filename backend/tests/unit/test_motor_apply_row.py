"""test_motor_apply_row.py — T-PR4-001/006/007 acceptance for motor/apply_row.py.

Given a ``SyncCatalogEntry`` and a payload, when ``apply_row`` dispatches it,
then:

  - ``test_dispatch_per_apply_strategy_*``: each of the 5 ``apply_strategy``
    values calls the exact ``repo/*`` helper design.md §5 / REQ-MOT-001
    names (``session_cycle`` covers both its ``record_login`` and
    ``close_login_with_log`` branches) — pure mock-based, no DB.
  - ``test_parent_validation_precedes_persistence``: a spec whose
    ``hook_validate_parent`` returns ``parent_valid=False`` short-circuits to
    ``ApplyResult(status=RETRY, reason="parent_missing")`` **before** the
    repo call runs (REQ-HOOK-003 step 1, D18) — pure mock-based, no DB.
  - ``test_snapshot_columns_never_recomputed``: mutating the live
    ``impuestos`` catalog after a ``factura_impuestos`` row was authored does
    not change the persisted snapshot columns on apply (D20, REQ-CAT-020) —
    DB-backed (``pg_engine``/``alembic_upgrade``), the one test in this file
    that needs a real Postgres to prove nothing here recomputes from the
    live catalog.
"""
from __future__ import annotations

import uuid as uuid_lib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from parkos_core.models.A.salidas import Salidas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket
from parkos_core.models.V.usuarios import Usuarios
from parkos_core.sync.hooks.base import HookResult
from parkos_core.sync.motor.apply_row import apply_row
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000bb")
USUARIO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000cc")
LOGIN_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000dd")


def _fake_session() -> MagicMock:
    """Minimal session stand-in — every repo call these tests exercise is
    mocked, so the session only needs to be forwardable, never touched.

    ``flush`` must be awaitable: ``apply_row`` flushes after the repo call
    so a server_default-generated ``uuid`` (e.g. ``gen_random_uuid()``) is
    populated before it reads ``new_row.uuid``.
    """
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    return session


def _fake_row(row_uuid: uuid_lib.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(uuid=row_uuid or uuid_lib.uuid4())


# ---------------------------------------------------------------------------
# T-PR4-001 / T-PR4-005 — the 5-strategy mapping table
# ---------------------------------------------------------------------------


async def test_dispatch_per_apply_strategy_close_and_insert(make_spec) -> None:
    """``close_and_insert`` -> ``repo.versioned.close_and_insert``."""
    spec = make_spec("usuarios")
    session = _fake_session()

    with patch(
        "parkos_core.repo.versioned.close_and_insert",
        new=AsyncMock(return_value=_fake_row()),
    ) as mocked:
        result = await apply_row(
            session, spec, {"current_uuid": None, "nombre": "Ana"}, actor_uuid=ACTOR_UUID
        )

    mocked.assert_awaited_once_with(
        session,
        Usuarios,
        current_uuid=None,
        new_attrs={"nombre": "Ana"},
        actor_uuid=ACTOR_UUID,
        log_tx=True,
    )
    assert result.status == "APPLIED"


async def test_dispatch_per_apply_strategy_record_event(make_spec) -> None:
    """``record_event`` -> ``repo.event.record_event``."""
    spec = make_spec("ingreso")
    session = _fake_session()
    payload = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}

    with patch(
        "parkos_core.repo.event.record_event",
        new=AsyncMock(return_value=_fake_row()),
    ) as mocked:
        result = await apply_row(session, spec, dict(payload), actor_uuid=ACTOR_UUID)

    mocked.assert_awaited_once_with(
        session, Ingreso, actor_uuid=ACTOR_UUID, new_attrs=payload, log_tx=True
    )
    assert result.status == "APPLIED"


async def test_dispatch_per_apply_strategy_append_event(make_spec) -> None:
    """``append_event`` -> ``repo.append_only.append_event(chain_hash=spec.hash_chain)``."""
    spec = make_spec("salidas")
    assert spec.hash_chain is False  # precondition for this test's assertion below
    session = _fake_session()
    payload = {"uuid_sucursal": SUCURSAL_UUID}

    with patch(
        "parkos_core.repo.append_only.append_event",
        new=AsyncMock(return_value=_fake_row()),
    ) as mocked:
        result = await apply_row(session, spec, dict(payload), actor_uuid=ACTOR_UUID)

    mocked.assert_awaited_once_with(
        session, Salidas, payload, actor_uuid=ACTOR_UUID, chain_hash=False
    )
    assert result.status == "APPLIED"


async def test_dispatch_per_apply_strategy_append_transition(make_spec) -> None:
    """``append_transition`` -> ``repo.workflow.append_transition``."""
    spec = make_spec("reimpresion_ticket")
    session = _fake_session()
    payload = {"parent_uuid": None, "estado": "solicitada", "uuid_sucursal": SUCURSAL_UUID}

    with patch(
        "parkos_core.repo.workflow.append_transition",
        new=AsyncMock(return_value=_fake_row()),
    ) as mocked:
        result = await apply_row(session, spec, dict(payload), actor_uuid=ACTOR_UUID)

    mocked.assert_awaited_once_with(
        session,
        ReimpresionTicket,
        actor_uuid=ACTOR_UUID,
        new_attrs={"estado": "solicitada", "uuid_sucursal": SUCURSAL_UUID},
        parent_uuid=None,
        parent_fk_column="uuid_reimpresion_padre",
        log_tx=True,
    )
    assert result.status == "APPLIED"


async def test_dispatch_per_apply_strategy_session_cycle_insert(make_spec) -> None:
    """``session_cycle`` (insert branch) -> ``repo.session_cycle.record_login``."""
    spec = make_spec("login")
    session = _fake_session()
    payload = {"uuid_usuario": USUARIO_UUID, "uuid_sucursal": SUCURSAL_UUID, "estado": "exitoso"}

    with (
        patch(
            "parkos_core.repo.session_cycle.record_login",
            new=AsyncMock(return_value=_fake_row()),
        ) as record_mock,
        patch(
            "parkos_core.repo.session_cycle.close_login_with_log", new=AsyncMock()
        ) as close_mock,
    ):
        result = await apply_row(session, spec, dict(payload), actor_uuid=ACTOR_UUID)

    record_mock.assert_awaited_once_with(
        session,
        usuario_uuid=USUARIO_UUID,
        sucursal_uuid=SUCURSAL_UUID,
        actor_uuid=ACTOR_UUID,
        success=True,
        motivo=None,
        # uuid=None here (not omitted) — apply_row now forwards
        # payload.get("uuid") to record_login so a synced login row
        # preserves the origin's identity (found wiring the post-PR14
        # full-catalog-sync closing exercise; see record_login's own
        # docstring). This payload carries no "uuid" key, so None.
        uuid=None,
    )
    close_mock.assert_not_called()
    assert result.status == "APPLIED"


async def test_dispatch_per_apply_strategy_session_cycle_close(make_spec) -> None:
    """``session_cycle`` (close branch) -> ``repo.session_cycle.close_login_with_log``."""
    spec = make_spec("login")
    session = _fake_session()
    payload = {"uuid": LOGIN_UUID, "estado": "cerrado"}

    with (
        patch(
            "parkos_core.repo.session_cycle.close_login_with_log",
            new=AsyncMock(return_value=_fake_row(LOGIN_UUID)),
        ) as close_mock,
        patch("parkos_core.repo.session_cycle.record_login", new=AsyncMock()) as record_mock,
    ):
        result = await apply_row(session, spec, dict(payload), actor_uuid=ACTOR_UUID)

    close_mock.assert_awaited_once_with(session, login_uuid=LOGIN_UUID, actor_uuid=ACTOR_UUID)
    record_mock.assert_not_called()
    assert result.status == "APPLIED"


async def test_dispatch_per_apply_strategy_session_cycle_insert_sesion(make_spec) -> None:
    """``session_cycle`` for ``sesion`` (open branch) -> ``repo.session_cycle.open_session``.

    Regression test for a real bug found wiring the post-PR14 full-
    catalog-sync closing exercise: both ``login`` AND ``sesion`` declare
    ``apply_strategy="session_cycle"`` (``entries/sync_entries_ls.py``),
    but the dispatch used to call ``session_cycle.record_login``/
    ``close_login_with_log`` UNCONDITIONALLY — a synced ``sesion`` row was
    silently misrouted into ``prod.login`` instead of ``prod.sesion``.
    Fixed by dispatching on ``spec.name`` (see ``apply_row.py``'s own
    ``_dispatch_repo_call`` docstring for the full note).
    """
    spec = make_spec("sesion")
    session = _fake_session()
    payload = {
        "uuid": LOGIN_UUID,
        "uuid_sucursal": SUCURSAL_UUID,
        "uuid_usuario": USUARIO_UUID,
        "valor_inicial_efectivo": 100000,
        "valor_inicial_datafono": 0,
    }

    with (
        patch(
            "parkos_core.repo.session_cycle.open_session",
            new=AsyncMock(return_value=_fake_row(LOGIN_UUID)),
        ) as open_mock,
        patch(
            "parkos_core.repo.session_cycle.close_session_with_log", new=AsyncMock()
        ) as close_mock,
        patch("parkos_core.repo.session_cycle.record_login", new=AsyncMock()) as record_mock,
    ):
        result = await apply_row(session, spec, dict(payload), actor_uuid=ACTOR_UUID)

    open_mock.assert_awaited_once_with(
        session,
        actor_uuid=ACTOR_UUID,
        uuid_sucursal=SUCURSAL_UUID,
        valor_inicial_efectivo=100000,
        valor_inicial_datafono=0,
        uuid_usuario=USUARIO_UUID,
        # Preserves the origin's identity (see open_session's own
        # docstring) — required once any FK-carrying child (arqueo,
        # factura_pagos) syncs alongside its sesion parent.
        uuid=LOGIN_UUID,
    )
    close_mock.assert_not_called()
    record_mock.assert_not_called()
    assert result.status == "APPLIED"


async def test_dispatch_per_apply_strategy_session_cycle_close_sesion(make_spec) -> None:
    """``session_cycle`` for ``sesion`` (close branch) -> ``close_session_with_log``."""
    spec = make_spec("sesion")
    session = _fake_session()
    payload = {"uuid": LOGIN_UUID, "timestamp_cierre": "2026-09-09T00:00:00"}

    with (
        patch(
            "parkos_core.repo.session_cycle.close_session_with_log",
            new=AsyncMock(return_value=_fake_row(LOGIN_UUID)),
        ) as close_mock,
        patch("parkos_core.repo.session_cycle.open_session", new=AsyncMock()) as open_mock,
    ):
        result = await apply_row(session, spec, dict(payload), actor_uuid=ACTOR_UUID)

    close_mock.assert_awaited_once_with(
        session,
        actor_uuid=ACTOR_UUID,
        sesion_uuid=LOGIN_UUID,
        valor_final_efectivo=None,
        valor_final_datafono=None,
    )
    open_mock.assert_not_called()
    assert result.status == "APPLIED"


# ---------------------------------------------------------------------------
# T-PR4-006 — parent validation precedes persistence
# ---------------------------------------------------------------------------


async def test_parent_validation_precedes_persistence(make_spec) -> None:
    """``hook_validate_parent`` rejecting a row cuts it off before any repo write.

    ``ingreso`` has a non-empty ``depends_on`` (``sucursal``,
    ``tipos_vehiculo``), so ``hook_validate_parent`` runs (REQ-HOOK-003 step
    1). Overriding it to return ``parent_valid=False`` must short-circuit to
    ``RETRY(parent_missing)`` — the mocked ``repo.event.record_event`` must
    see ZERO calls.
    """
    spec = make_spec(
        "ingreso",
        hook_validate_parent=lambda ctx: HookResult(proceed=True, parent_valid=False),
    )
    session = _fake_session()
    payload = {"uuid_sucursal": SUCURSAL_UUID, "placa": "ABC123"}

    with patch("parkos_core.repo.event.record_event", new=AsyncMock()) as mocked:
        result = await apply_row(session, spec, payload, actor_uuid=ACTOR_UUID)

    mocked.assert_not_called()
    assert result.status == "RETRY"
    assert result.reason == "parent_missing"
    assert result.row_uuid is None
    assert result.metrics["hook_validate_parent"] is True
    assert result.metrics["hook_pre_insert"] is False
    assert result.metrics["hook_post_insert"] is False
    assert result.metrics["hook_chain_extend"] is False


# ---------------------------------------------------------------------------
# T-PR4-007 — snapshot columns never recomputed (D20)
# ---------------------------------------------------------------------------


async def test_snapshot_columns_never_recomputed(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """Mutating the live ``impuestos`` catalog after issuance must not leak
    into an already-authored ``factura_impuestos`` row's persisted snapshot
    (D20, REQ-CAT-020, design.md Issue #12).

    Real Postgres, not mocks: this is a regression guard against
    ``apply_row`` (or anything it calls) ever re-reading ``impuestos`` at
    apply time, which the pure-mock tests above cannot observe.
    """
    from parkos_core.models.A.factura_impuestos import FacturaImpuestos
    from parkos_core.models.V.impuestos import Impuestos
    from parkos_core.repo import versioned
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        # 1. Seed the impuestos version IN FORCE when the invoice was issued.
        original = v_fixture_factory.build(
            Impuestos, codigo="IVA-T-PR4-007", porcentaje=19.0
        )
        session.add(original)
        await session.commit()
        original_uuid = original.uuid

        # 2. Mutate the local impuestos catalog — a new tax-rate version —
        #    exactly the hazard D20 exists to prevent from leaking into an
        #    already-issued invoice's snapshot.
        await versioned.close_and_insert(
            session,
            Impuestos,
            current_uuid=original_uuid,
            new_attrs={"codigo": "IVA-T-PR4-007", "porcentaje": 5.0},
            actor_uuid=ACTOR_UUID,
            log_tx=False,
        )
        await session.commit()

        # 3. Apply a factura_impuestos row snapshotting the ORIGINAL rate —
        #    the rate actually in force when the invoice was issued.
        spec = SYNC_CATALOG_BY_NAME["factura_impuestos"]
        payload = {
            "uuid_impuesto": original_uuid,
            "base_calculo": 100000,
            "porcentaje_aplicado": 19.0,
            "valor": 19000,
        }
        result = await apply_row(session, spec, payload, actor_uuid=ACTOR_UUID)
        await session.commit()

        assert result.status == "APPLIED"
        assert result.row_uuid is not None

        persisted = (
            await session.execute(
                select(FacturaImpuestos).where(FacturaImpuestos.uuid == result.row_uuid)
            )
        ).scalar_one()

    # Persisted values match the payload verbatim — NOT the mutated catalog
    # (which now holds porcentaje=5.0 for this codigo).
    assert float(persisted.porcentaje_aplicado) == 19.0
    assert float(persisted.base_calculo) == 100000
    assert float(persisted.valor) == 19000
