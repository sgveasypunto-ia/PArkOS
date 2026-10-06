# ruff: noqa: F811, PT018
"""test_sync_pull_rls.py -- the database-level safety net of ``POST /sync/pull`` (ADR-005).

Property under test: connected as ``rol_sync_pull`` with the branch GUC set, a plain
``SELECT`` on ANY pull table (no predicate at all) returns exactly the rows the SQL
scope predicate (``build_scope_predicate``) delivers -- never another branch's
exclusive rows and never FEWER than the predicate (a narrower policy would hide
rows the pull legitimately owes). With the GUC unset, scoped tables return nothing.

The ``PARKOS_PULL_RLS`` switch is pinned too: ``off`` is exactly the pre-RLS
behaviour (no role switch), ``on`` runs the reads as ``rol_sync_pull``.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest
from sqlalchemy import select, text

# Fixtures reused from the scope matrix (imported by pytest module name).
from test_sync_pull_scope_matrix import World, _keys, _pull, retire, world  # noqa: F401

from tests.pull_scope_expected import ALL_BRANCHES_ALLOWLIST, EXPECTED_SCOPE

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

PULL_TABLES = sorted(EXPECTED_SCOPE)
SCOPED_TABLES = sorted(t for t in EXPECTED_SCOPE if t not in ALL_BRANCHES_ALLOWLIST)


def _spec(name: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[name]


async def _visible_as_pull_role(
    engine, table: str, branch: uuid_lib.UUID | None
) -> set[uuid_lib.UUID]:
    """``SELECT uuid`` from the table as ``rol_sync_pull`` -- NO scope predicate."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL ROLE rol_sync_pull"))
            if branch is not None:
                await conn.execute(
                    text("SELECT set_config('parkos.pull_sucursal', :b, true)"), {"b": str(branch)}
                )
            rows = (await conn.execute(text(f"SELECT uuid FROM prod.{table}"))).scalars().all()
        finally:
            await trans.rollback()
    return set(rows)


async def _predicate_ids(engine, name: str, branch: uuid_lib.UUID) -> set[uuid_lib.UUID]:
    from parkos_core.sync.motor.pull_scope import build_scope_predicate
    from sqlalchemy.ext.asyncio import async_sessionmaker

    spec = _spec(name)
    model = spec.model_cls
    stmt = select(model.uuid)
    predicate = build_scope_predicate(spec, branch)
    if predicate is not None:
        stmt = stmt.where(predicate)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        return set((await s.execute(stmt)).scalars().all())


@pytest.mark.parametrize("name", PULL_TABLES)
@pytest.mark.parametrize("who", ["a", "b"])
async def test_rls_alone_equals_the_scope_predicate(
    world: World, pg_engine, name: str, who: str, app
) -> None:
    branch = world.suc_a if who == "a" else world.suc_b
    table = _spec(name).model_cls.__table__.name
    rls = await _visible_as_pull_role(pg_engine, table, branch)
    predicate = await _predicate_ids(pg_engine, name, branch)

    assert predicate <= rls, f"{name}: RLS is NARROWER than the pull predicate (rows would vanish)"
    assert rls <= predicate, f"{name}: RLS lets through rows the predicate excludes"

    other = "b" if who == "a" else "a"
    exclusive = world.ids.get((name, other))
    if exclusive is not None and name not in ALL_BRANCHES_ALLOWLIST:
        assert exclusive not in rls, f"{name}: branch {who} can read branch {other}'s exclusive row"
    own = world.ids.get((name, who))
    if own is not None:
        assert own in rls, f"{name}: branch {who} cannot read its own row"


@pytest.mark.parametrize("name", SCOPED_TABLES)
async def test_unset_branch_fails_closed(world: World, pg_engine, name: str, app) -> None:
    table = _spec(name).model_cls.__table__.name
    assert await _visible_as_pull_role(pg_engine, table, None) == set(), f"{name}: not fail-closed"


@pytest.mark.parametrize("name", sorted(ALL_BRANCHES_ALLOWLIST))
async def test_reference_catalogs_stay_readable_without_a_branch(
    world: World, pg_engine, name: str, app
) -> None:
    table = _spec(name).model_cls.__table__.name
    assert await _visible_as_pull_role(pg_engine, table, None)


async def test_pull_role_is_read_only(world: World, pg_engine, app) -> None:
    from sqlalchemy.exc import DBAPIError

    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL ROLE rol_sync_pull"))
            with pytest.raises(DBAPIError):
                await conn.execute(text("UPDATE prod.sucursal SET nombre = nombre"))
        finally:
            await trans.rollback()
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL ROLE rol_sync_pull"))
            with pytest.raises(DBAPIError):
                await conn.execute(text("SELECT 1 FROM prod.sync_log LIMIT 1"))
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------
# Application wiring: PARKOS_PULL_RLS switch
# ---------------------------------------------------------------------------


async def test_scope_context_switches_role_and_restores_it(
    world: World, pg_engine, monkeypatch, app
) -> None:
    from parkos_core.api.v1 import sync_router
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.delenv("PARKOS_PULL_RLS", raising=False)
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
        outer = (await s.execute(text("SELECT current_user"))).scalar_one()
        async with sync_router._pull_rls_scope(s, world.suc_a):
            inside = (await s.execute(text("SELECT current_user"))).scalar_one()
            guc = (
                await s.execute(text("SELECT current_setting('parkos.pull_sucursal', true)"))
            ).scalar_one()
            # a deliberately UNSCOPED query (the bug the net exists for)
            from parkos_core.models.V.usuarios import Usuarios

            leaked = set((await s.execute(select(Usuarios.uuid))).scalars().all())
        after = (await s.execute(text("SELECT current_user"))).scalar_one()
        await s.rollback()

    assert inside == "rol_sync_pull" and after == outer
    assert guc == str(world.suc_a)
    assert world.ids[("usuarios", "a")] in leaked
    assert world.ids[("usuarios", "b")] not in leaked


async def test_switch_off_keeps_the_old_behaviour(
    world: World, pg_engine, monkeypatch, app
) -> None:
    from parkos_core.api.v1 import sync_router
    from sqlalchemy.ext.asyncio import async_sessionmaker

    monkeypatch.setenv("PARKOS_PULL_RLS", "off")
    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
        outer = (await s.execute(text("SELECT current_user"))).scalar_one()
        async with sync_router._pull_rls_scope(s, world.suc_a):
            inside = (await s.execute(text("SELECT current_user"))).scalar_one()
            guc = (
                await s.execute(text("SELECT current_setting('parkos.pull_sucursal', true)"))
            ).scalar_one()
        await s.rollback()
    assert inside == outer
    assert guc in (None, "")


async def test_endpoint_result_is_identical_with_rls_on_and_off(
    world: World, client, mint_sync_agent_jwt, monkeypatch, app
) -> None:
    from parkos_core.api.v1 import sync_router

    seen: list[str] = []
    original = sync_router._fetch_pull_rows

    async def spy(session, **kw):
        seen.append((await session.execute(text("SELECT current_user"))).scalar_one())
        return await original(session, **kw)

    monkeypatch.setattr(sync_router, "_fetch_pull_rows", spy)
    results: dict[str, set] = {}
    for mode in ("on", "off"):
        monkeypatch.setenv("PARKOS_PULL_RLS", mode)
        token = mint_sync_agent_jwt(scope="branch", sucursal_uuid=world.suc_a)
        resp = await _pull(client, token, 0)
        assert resp.status_code == 200, resp.text
        results[mode] = _keys(resp.json())

    assert seen[0] == "rol_sync_pull" and seen[1] != "rol_sync_pull"
    assert results["on"] == results["off"]
    assert results["on"], "the world must deliver rows"


async def test_rol_app_still_sees_every_row_of_every_rls_table(
    world: World, pg_engine, app
) -> None:
    """Regression guard: RLS ON must not deny the API login role (permissive policy).

    The superuser bypasses RLS and gives the true count; ``rol_app`` (the group role
    ``parkos_app`` inherits) must see exactly the same, with and without a branch GUC.
    """
    async with pg_engine.connect() as conn:
        tables = (
            (
                await conn.execute(
                    text(
                        "SELECT relname FROM pg_class WHERE relrowsecurity "
                        "AND relnamespace = 'prod'::regnamespace ORDER BY 1"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tables) == 17
        for table in tables:
            total = (await conn.execute(text(f"SELECT count(*) FROM prod.{table}"))).scalar_one()
            trans = await conn.begin_nested()
            await conn.execute(text("SET LOCAL ROLE rol_app"))
            as_app = (await conn.execute(text(f"SELECT count(*) FROM prod.{table}"))).scalar_one()
            await trans.rollback()
            assert as_app == total, f"{table}: rol_app sees {as_app} of {total} rows"
