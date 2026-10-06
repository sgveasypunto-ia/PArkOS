"""test_sync_pull_query_budget.py — SQL statement budget for ``POST /sync/pull``.

Today ``_fetch_pull_rows`` loads each catalog table whole and calls
``resolve_broadcast_targets`` once per row; for ``all_branches`` entries that
resolver runs ``discover_active_branches`` (no ``branch_cache`` is passed),
so a pull costs N+1 statements: ~200 rows in one ``all_branches`` table
means 200+ extra queries. The budget below (K=60) fits one SELECT per
catalog entry plus auth overhead, and fails until the filter is pushed to
SQL / the branch lookup is cached per request.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

ROWS = 200
QUERY_BUDGET = 60


async def test_pull_with_many_all_branches_rows_stays_within_query_budget(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory, app
) -> None:
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy import event, update
    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import async_sessionmaker

    since_seq = int(datetime.now(UTC).timestamp() * 1000) - 2
    tag = uuid_lib.uuid4().hex[:8]
    rows = [v_fixture_factory.build(TiposVehiculo, tipo=f"qb-{tag}-{i}") for i in range(ROWS)]
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
        s.add_all(rows)
        await s.commit()

    token = mint_sync_agent_jwt(scope="branch")
    statements: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", _count)
    try:
        resp = await client.post(
            "/api/v1/sync/pull",
            json={"since_seq": since_seq},
            headers={"Authorization": f"Bearer {token}", "X-Request-Id": uuid_lib.uuid4().hex},
        )
    finally:
        event.remove(Engine, "before_cursor_execute", _count)
        # Close the rows logically so later since_seq=0 pulls stay under the cap.
        async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
            await s.execute(
                update(TiposVehiculo)
                .where(TiposVehiculo.uuid.in_([r.uuid for r in rows]))
                .values(vigente_hasta=datetime.now(UTC).replace(tzinfo=None), estado="inactivo")
            )
            await s.commit()

    assert resp.status_code == 200, resp.text
    delivered = [r for r in resp.json()["rows"] if r["tabla"] == "tipos_vehiculo"]
    assert len(delivered) >= ROWS, "the pull must still deliver every all_branches row"
    assert len(statements) <= QUERY_BUDGET, (
        f"pull issued {len(statements)} SQL statements for {ROWS} rows "
        f"(budget {QUERY_BUDGET}); N+1 via discover_active_branches per row"
    )
