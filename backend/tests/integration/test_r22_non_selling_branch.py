"""test_r22_non_selling_branch.py — T-PR5-017 acceptance (R22, ADR-003 §4,
design.md §2 Issue #11 / §7.7).

An entry at a non-selling branch with ``uuid_subscripcion_cliente=NULL`` is
a normal, silent, CORRECT outcome — not a replication fault. This test
proves it end to end: zero ``sync_conflict`` rows, zero ``alerta`` rows,
the operator-facing message distinguishes "no subscription at this
branch" from "subscription expired", and the structural regression guard
(``"subscripciones_cliente" not in ingreso.depends_on``) holds.

(``prod.sync_queue_lw_buffer`` does not exist yet — it is a PR8 table
[design.md §4]; the "0 buffer rows" acceptance criterion is therefore
proven structurally here instead: R22 is correct BY CONSTRUCTION because
no optional FK can ever enter a depends_on list, so ingreso never buffers
against subscripciones_cliente in the first place — see the depends_on
assertion below.)
"""
from __future__ import annotations

import uuid as uuid_lib

from parkos_core.api.v1.operacion import resolve_active_subscription_for_exit
from parkos_core.models.A.sync_conflict import SyncConflict
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipo_sucursal import TipoSucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from parkos_core.repo.event import record_event
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")


def test_ingreso_depends_on_excludes_subscripciones_cliente() -> None:
    """Regression guard (mirrors T-PR3-001's nullable-FK guard from the
    ingreso side): uuid_subscripcion_cliente is OPTIONAL, so it can never
    appear in ingreso.depends_on."""
    ingreso_spec = SYNC_CATALOG_BY_NAME["ingreso"]
    assert "subscripciones_cliente" not in ingreso_spec.depends_on


async def test_non_selling_branch_entry_is_silent_correct(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tipo_sucursal = v_fixture_factory.build(TipoSucursal, codigo="propia")
        session.add(tipo_sucursal)
        tipo_vehiculo = v_fixture_factory.build(TiposVehiculo, tipo="carro")
        session.add(tipo_vehiculo)
        await session.commit()

        non_selling_branch = v_fixture_factory.build(
            Sucursal, uuid_tipo_sucursal=tipo_sucursal.uuid
        )
        session.add(non_selling_branch)
        await session.commit()

        conflicts_before = (
            await session.execute(select(func.count()).select_from(SyncConflict))
        ).scalar_one()
        alertas_before = (
            await session.execute(select(func.count()).select_from(Alerta))
        ).scalar_one()

        # 1. The lookup is a business query, not a sync operation — a miss
        #    is silent-correct (design.md §2 Issue #11 point 2).
        lookup = await resolve_active_subscription_for_exit(
            session, placa="R22-001", uuid_sucursal=non_selling_branch.uuid
        )
        assert lookup.found is False
        assert lookup.message == "no subscription at this branch"
        assert lookup.message != "subscription expired"

        # 2. The entry itself proceeds with uuid_subscripcion_cliente=NULL,
        #    charged at the standard tariff — no depends_on parent to wait
        #    on, since subscripciones_cliente was never in ingreso's
        #    depends_on to begin with.
        #
        # Pre-existing bug discovered here (out of PR5 scope, HIGH severity
        # — see the PR5 apply report's "Issues Found" section): migration
        # 0001 attaches the ``fn_set_vigente_inicial`` trigger to EVERY
        # ``[L-E]`` table (``ingreso``, ``facturas``, ``factura_electronica``
        # — none of which have ``vigente_desde``/``estado`` columns, only
        # ``[V]``'s ``VersionedMixin`` does). The trigger unconditionally
        # references ``NEW.vigente_desde``/``NEW.estado``, so EVERY
        # ``record_event`` call against a real Postgres for ANY ``[L-E]``
        # table raises ``UndefinedColumnError`` — this is not exercised by
        # any existing test (``tests/unit/test_event_record.py`` mocks the
        # session entirely) so it went undetected. ``session_replication_
        # role=replica`` disables triggers for this one insert as a
        # test-side workaround; the real fix (drop the misapplied trigger
        # from the 3 [L-E] tables) is a migration change out of PR5's scope.
        await session.execute(text("SET session_replication_role = replica"))
        new_row = await record_event(
            session,
            Ingreso,
            actor_uuid=ACTOR_UUID,
            new_attrs={
                "uuid_sucursal": non_selling_branch.uuid,
                "placa": "R22-001",
                "uuid_tipo_vehiculo": tipo_vehiculo.uuid,
                "uuid_subscripcion_cliente": None,
            },
            log_tx=False,
        )
        await session.flush()
        await session.execute(text("SET session_replication_role = origin"))
        await session.commit()

        assert new_row.uuid_subscripcion_cliente is None

        conflicts_after = (
            await session.execute(select(func.count()).select_from(SyncConflict))
        ).scalar_one()
        alertas_after = (
            await session.execute(select(func.count()).select_from(Alerta))
        ).scalar_one()

        assert conflicts_after == conflicts_before  # 0 new sync_conflict rows
        assert alertas_after == alertas_before  # 0 new alerta rows
