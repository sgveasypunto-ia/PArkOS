# ruff: noqa: PT018, E501
"""Migration 0085: database-level safety net for ``POST /sync/pull`` (ADR-005).

Covers the schema contract (role, grants, RLS, policies, helper functions), the
idempotent upgrade / clean downgrade, and the static gate: every pull-eligible
catalog entry is readable by ``rol_sync_pull`` and every non-reference one is
guarded by an RLS policy, so a table cannot join the pull without a decision.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests.pull_scope_expected import ALL_BRANCHES_ALLOWLIST, EXPECTED_SCOPE

ROLE = "rol_sync_pull"
MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "packages/parkos_core/migrations/versions/0085_pull_rls.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0085", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_envio_dian_migration():
    """0096 puts ``envio_dian`` under the same barrier; a 0085 round trip must undo it first."""
    path = MIGRATION.with_name("0096_pull_rls_envio_dian.py")
    spec = importlib.util.spec_from_file_location("migration_0096", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_configuracion_caja_migration():
    """0099 puts ``configuracion_caja`` under the same barrier; undo it before 0085."""
    path = MIGRATION.with_name("0099_sync_configuracion_caja.py")
    spec = importlib.util.spec_from_file_location("migration_0099", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pull_tables() -> dict[str, str]:
    """entry name -> physical table name for every pull-eligible catalog entry."""
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG

    return {
        s.name: s.model_cls.__table__.name
        for s in SYNC_CATALOG
        if s.direction in {"cloud_to_branch", "bidirectional"} and s.broadcast_policy is not None
    }


async def _scalar(engine, sql: str, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


async def test_role_is_read_only_nologin_without_bypass(pg_engine) -> None:
    async with pg_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT rolcanlogin, rolbypassrls, rolsuper FROM pg_roles WHERE rolname = :r"),
                {"r": ROLE},
            )
        ).one()
    assert tuple(row) == (False, False, False)
    assert await _scalar(pg_engine, "SELECT pg_has_role('rol_app', :r, 'MEMBER')", r=ROLE)


async def test_role_has_select_only_on_every_pull_table(pg_engine) -> None:
    async with pg_engine.connect() as conn:
        for table in _pull_tables().values():
            privs = {
                p: (
                    await conn.execute(
                        text("SELECT has_table_privilege(:r, :t, :p)"),
                        {"r": ROLE, "t": f"prod.{table}", "p": p},
                    )
                ).scalar_one()
                for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
            assert privs == {"SELECT": True, "INSERT": False, "UPDATE": False, "DELETE": False}, (
                table
            )


async def test_role_cannot_read_bridge_only_or_unrelated_tables(pg_engine) -> None:
    async with pg_engine.connect() as conn:
        for table in ("sync_log", "pairing_tokens", "log_transaccional"):
            allowed = (
                await conn.execute(
                    text("SELECT has_table_privilege(:r, :t, 'SELECT')"),
                    {"r": ROLE, "t": f"prod.{table}"},
                )
            ).scalar_one()
            assert allowed is False, table


async def test_every_non_reference_pull_table_has_rls_and_both_policies(pg_engine) -> None:
    """Static gate (e): a new pull table without a policy fails here."""
    tables = _pull_tables()
    assert set(tables) == set(EXPECTED_SCOPE)
    async with pg_engine.connect() as conn:
        for name, table in tables.items():
            rls, force = (
                await conn.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                        "WHERE oid = to_regclass(:t)"
                    ),
                    {"t": f"prod.{table}"},
                )
            ).one()
            policies = {
                (r.policyname, r.cmd, tuple(r.roles))
                for r in (
                    await conn.execute(
                        text(
                            "SELECT policyname, cmd, roles FROM pg_policies "
                            "WHERE schemaname = 'prod' AND tablename = :t"
                        ),
                        {"t": table},
                    )
                ).all()
            }
            if name in ALL_BRANCHES_ALLOWLIST:
                assert rls is False, f"{name}: reference catalog must not carry RLS"
                continue
            assert rls is True and force is False, f"{name}: RLS on, never FORCE"
            assert (f"pull_rls_{table}", "SELECT", (ROLE,)) in policies, name
            assert (f"pull_rls_app_{table}", "ALL", ("rol_app",)) in policies, name
            assert len(policies) == 2, f"{name}: unexpected extra policies {policies}"


async def test_bridge_table_is_guarded_and_select_only(pg_engine) -> None:
    """``factura_electronica`` is read by the clientes predicate: own-branch rows only."""
    async with pg_engine.connect() as conn:
        rls = (
            await conn.execute(
                text(
                    "SELECT relrowsecurity FROM pg_class WHERE oid = 'prod.factura_electronica'::regclass"
                )
            )
        ).scalar_one()
        privs = [
            (
                await conn.execute(
                    text("SELECT has_table_privilege(:r, 'prod.factura_electronica', :p)"),
                    {"r": ROLE, "p": p},
                )
            ).scalar_one()
            for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
        ]
    assert rls is True
    assert privs == [True, False, False, False]


async def test_helpers_are_hardened_definers(pg_engine) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT p.proname, p.prosecdef, p.provolatile, p.proconfig, "
                    "has_function_privilege('public', p.oid, 'EXECUTE') AS pub, "
                    "has_function_privilege(:r, p.oid, 'EXECUTE') AS role_ok "
                    "FROM pg_proc p WHERE p.pronamespace = 'prod'::regnamespace "
                    "AND p.proname LIKE 'fn\\_pull\\_%'"
                ),
                {"r": ROLE},
            )
        ).all()
    by_name = {r.proname: r for r in rows}
    assert len(by_name) == 7
    for name, r in by_name.items():
        assert r.provolatile in ("s", b"s"), name
        assert r.pub is False and r.role_ok is True, name
        assert any(c.startswith("search_path=") for c in r.proconfig), name
        assert r.prosecdef is (name != "fn_pull_branch"), name


async def test_upgrade_is_idempotent_and_downgrade_is_clean(pg_engine) -> None:
    """Run downgrade, re-upgrade and upgrade twice inside one rolled-back transaction."""
    module = _load_migration()
    later = _load_envio_dian_migration()
    latest = _load_configuracion_caja_migration()
    tables = set(_pull_tables().values())

    def exercise(sync_conn) -> dict[str, int]:
        ctx = MigrationContext.configure(sync_conn)
        seen: dict[str, int] = {}

        def count(sql: str) -> int:
            return sync_conn.execute(text(sql)).scalar_one()

        with Operations.context(ctx):
            latest.downgrade()
            later.downgrade()
            module.downgrade()
            seen["policies_after_down"] = count("SELECT count(*) FROM pg_policies")
            seen["rls_after_down"] = count(
                "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relnamespace = 'prod'::regnamespace"
            )
            seen["funcs_after_down"] = count(
                "SELECT count(*) FROM pg_proc WHERE proname LIKE 'fn\\_pull\\_%'"
            )
            seen["role_after_down"] = count(
                f"SELECT count(*) FROM pg_roles WHERE rolname = '{ROLE}'"
            )
            module.upgrade()
            module.upgrade()
            later.upgrade()
            latest.upgrade()
            latest.upgrade()  # idempotent
            seen["policies_after_up"] = count("SELECT count(*) FROM pg_policies")
            seen["rls_after_up"] = count(
                "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relnamespace = 'prod'::regnamespace"
            )
            seen["role_after_up"] = count(f"SELECT count(*) FROM pg_roles WHERE rolname = '{ROLE}'")
        return seen

    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            seen = await conn.run_sync(exercise)
        finally:
            await trans.rollback()

    assert seen["policies_after_down"] == 0
    assert seen["rls_after_down"] == 0
    assert seen["funcs_after_down"] == 0
    assert seen["role_after_down"] == 0
    assert seen["role_after_up"] == 1
    scoped = len(tables) - len(ALL_BRANCHES_ALLOWLIST) + 1  # + factura_electronica bridge
    assert seen["rls_after_up"] == scoped
    assert seen["policies_after_up"] == 2 * scoped
    # the real DB was left untouched by the rolled-back round trip
    assert await _scalar(pg_engine, "SELECT count(*) FROM pg_policies") == 2 * scoped


@pytest.mark.parametrize("revision", ["0085_pull_rls"])
def test_migration_chain_head(revision: str) -> None:
    module = _load_migration()
    assert module.revision == revision
    assert module.down_revision == "0084_clientes_nk_all_index"
