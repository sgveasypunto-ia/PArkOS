"""test_subscripcion_vehiculos_open_version_fallback.py — regression for the
one ``[V]`` table needing hook COMPOSITION, not a bare ``identity_reconciler``
swap, in the 2026-09-10 identity-reconciliation generalization.

``subscripcion_vehiculos`` is ``bidirectional`` with a real ER-declared
natural key (UK01 ``(uuid_subscripcion_cliente, uuid_vehiculo,
vigente_desde)``) but already carries its own ``hook_pre_insert``
(``subscription_lifecycle`` — REQ-HOOK-006 lifecycle/capacity validation),
so it could not simply be pointed at ``identity_reconciler`` like the other
20 tables (a ``SyncCatalogEntry`` has exactly one ``hook_pre_insert`` slot).

Before this fix, ``subscription_lifecycle`` only ever read
``payload.get("current_uuid")`` — populated by the LOCAL
``plate_change_cascade`` caller (same node, same transaction, already knows
the row it's closing), but NEVER present on a REPLICATED row (the wire
payload is just ``to_jsonb(NEW)`` of the origin's new row; ``current_uuid``
is not a real column). A replicated lifecycle change therefore always
looked like "no prior version" on the receiving node: the old open junction
row was never closed, leaving 2 simultaneously-open rows for the same
(cliente-subscripcion, vehiculo) pair — the exact hazard this whole
generalization closes for every other table.

The fix: ``subscripcion_vehiculos`` now declares ``natural_key``, so
``SyncMotor.apply_row`` resolves ``ctx.open_version`` before calling
``subscription_lifecycle`` — which now falls back to
``open_version["uuid"]``/``open_version["estado"]`` when the wire payload
carries no explicit ``current_uuid``, and returns a ``payload_override`` so
the eventual ``close_and_insert`` closes the RIGHT local row.

Exercised via the REAL ``POST /api/v1/sync/events`` HTTP path — never by
calling ``apply_row``/``subscription_lifecycle`` directly.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from parkos_core.runtime import engine_flag


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_replicated_lifecycle_change_closes_old_junction_row(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory
) -> None:
    """A legal lifecycle transition (activa -> suspendida) arrives with NO
    explicit ``current_uuid`` (simulating a real cross-node replication,
    not the local plate-change-cascade path) — must still converge to
    exactly 1 open row for the natural key, not 2."""
    from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
    from parkos_core.models.V.vehiculos import Vehiculos
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # subscripcion_vehiculos DOES carry real DB-level FK constraints to
        # both parents (fk_subscripcion_vehiculos_uuid_subscripcion_cliente),
        # unlike subscripciones_cliente/vehiculos' own FKs (application-
        # enforced only per their own docstrings) — real parent rows needed.
        subscripcion_row = v_fixture_factory.build(SubscripcionesCliente)
        vehiculo_row = v_fixture_factory.build(Vehiculos, placa=f"PLC{uuid_lib.uuid4().hex[:6]}")
        session.add_all([subscripcion_row, vehiculo_row])
        await session.commit()
        uuid_subscripcion_cliente = subscripcion_row.uuid
        uuid_vehiculo = vehiculo_row.uuid

        local_open = v_fixture_factory.build(
            SubscripcionVehiculos,
            uuid_subscripcion_cliente=uuid_subscripcion_cliente,
            uuid_vehiculo=uuid_vehiculo,
            estado="activa",
        )
        session.add(local_open)
        await session.commit()

    token = mint_sync_agent_jwt(scope="branch")
    new_uuid = uuid_lib.uuid4()
    resp = await client.post(
        "/api/v1/sync/events",
        json={
            "events": [
                {
                    "event_type": "row_push",
                    "tabla": "subscripcion_vehiculos",
                    "uuid_registro": str(new_uuid),
                    "payload": {
                        "uuid": str(new_uuid),
                        "uuid_subscripcion_cliente": str(uuid_subscripcion_cliente),
                        "uuid_vehiculo": str(uuid_vehiculo),
                        "estado": "suspendida",
                        # Deliberately NO "current_uuid" key — this is what
                        # the real to_jsonb(NEW)-sourced wire payload looks
                        # like; only the LOCAL plate_change_cascade caller
                        # ever sets this explicitly.
                    },
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 207), resp.text
    assert resp.json()["results"][0]["status"] == "applied", resp.text

    async with Session() as session:
        open_rows = (
            (
                await session.execute(
                    select(SubscripcionVehiculos).where(
                        SubscripcionVehiculos.uuid_subscripcion_cliente
                        == uuid_subscripcion_cliente,
                        SubscripcionVehiculos.uuid_vehiculo == uuid_vehiculo,
                        SubscripcionVehiculos.vigente_hasta.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(open_rows) == 1, (
            f"R17-equivalent violation: {len(open_rows)} open subscripcion_vehiculos rows "
            "for the same (subscripcion, vehiculo) pair after a real replicated lifecycle "
            "push — expected exactly 1"
        )
        assert open_rows[0].uuid == new_uuid
        assert open_rows[0].estado == "suspendida"
