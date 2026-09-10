"""test_identity_reconciliation_real_http.py — regression coverage for the
most critical defect confirmed this session (2026-09-10, manual QA against
live Docker containers, section 4.6.a exercised via REAL HTTP, not by
calling ``apply_row`` directly like ``test_identity_invariant.py`` does):

``SyncMotor.apply_row`` — the ONLY caller of the catalog applier reachable
from any real production path (``api/v1/sync_router.py::sync_events``,
``jobs/sync_cloud.py::_apply_pending_batch_once``,
``jobs/sync_sucursal.py::_pull_and_apply_catalog``) — never resolved
``open_version`` before invoking ``identity_reconciler``. Confirmed live:
creating the same natural key on cloud and branch (real HTTP POSTs, real
Docker) with divergent phone numbers, then letting a real push+pull cycle
run, left CLOUD with 2 simultaneously-open rows and BRANCH with 3, for the
identical natural key — with zero ``sync_conflict`` rows recorded.

This test exercises the SAME real code path (``POST /api/v1/sync/events``,
real FastAPI routing + auth + ``SyncMotor.apply_row``) a branch's push
actually goes through — not ``apply_row.apply_row`` directly like
``test_identity_invariant.py``, which resolves ``open_version`` itself and
therefore never exercised this gap.
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
async def test_divergent_cliente_push_reconciles_to_one_open_row_real_http(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory
) -> None:
    """A cliente already open on this node (representing cloud's own
    version) receives a divergent push (representing a branch's
    independently-created version of the SAME natural key) via the REAL
    ``POST /api/v1/sync/events`` endpoint. Must converge to exactly ONE
    open row, with an informational ``sync_conflict`` recorded — never a
    hard block, never two open rows."""
    from parkos_core.models.A.sync_conflict import SyncConflict
    from parkos_core.models.V.clientes import Clientes
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    numero_identificacion = f"DIV{uuid_lib.uuid4().hex[:10]}"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        local_open = v_fixture_factory.build(
            Clientes,
            tipo_identificador="CC",
            numero_identificacion=numero_identificacion,
            nombre="Cloud",
            apellido="Version",
            telefono="3001111111",
        )
        session.add(local_open)
        await session.commit()
        await session.refresh(local_open)

    # A branch, independently, created its OWN version of the same person
    # (same natural key) with a DIFFERENT phone — exactly the manual Docker
    # repro. Pushed via the real /sync/events wire shape.
    token = mint_sync_agent_jwt(scope="branch")
    remote_uuid = uuid_lib.uuid4()
    resp = await client.post(
        "/api/v1/sync/events",
        json={
            "events": [
                {
                    "event_type": "row_push",
                    "tabla": "clientes",
                    "uuid_registro": str(remote_uuid),
                    "payload": {
                        "uuid": str(remote_uuid),
                        "tipo_identificador": "CC",
                        "numero_identificacion": numero_identificacion,
                        "nombre": "Cloud",
                        "apellido": "Version",
                        "telefono": "3009999999",
                    },
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 207), resp.text
    result_status = resp.json()["results"][0]["status"]
    assert result_status in ("applied", "conflict"), (
        f"expected the push to be accepted (never a hard block), got {result_status!r}: {resp.text}"
    )

    async with Session() as session:
        open_count = (
            await session.execute(
                select(func.count())
                .select_from(Clientes)
                .where(
                    Clientes.tipo_identificador == "CC",
                    func.regexp_replace(Clientes.numero_identificacion, "[^0-9A-Za-z]", "", "g")
                    == numero_identificacion,
                    Clientes.vigente_hasta.is_(None),
                )
            )
        ).scalar_one()
        assert open_count == 1, (
            f"R17 violation: {open_count} open rows for the same natural key after a "
            "real divergent HTTP push — expected exactly 1"
        )

        # Scoped to THIS test's own cliente row — the shared session-scoped
        # DB (conftest.py::pg_engine) legitimately carries other tests' own
        # "clientes" identity_divergence conflicts (e.g.
        # test_identity_invariant.py's own forward-divergence case), which
        # an unscoped count over the whole table would (incorrectly) count
        # too. Confirmed real running the full suite together (2026-09-10).
        conflict_count = (
            await session.execute(
                select(func.count())
                .select_from(SyncConflict)
                .where(
                    SyncConflict.tabla == "clientes",
                    SyncConflict.politica == "identity_divergence",
                    SyncConflict.uuid_registro == local_open.uuid,
                )
            )
        ).scalar_one()
        assert conflict_count == 1, (
            f"expected exactly 1 informational sync_conflict row for the divergent "
            f"business data, got {conflict_count}"
        )
