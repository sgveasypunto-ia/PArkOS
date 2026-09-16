"""Migration test — pairing_tokens + revoked_sync_jwts BEFORE UPDATE/DELETE trigger + REVOKE.

Verifies (PR8a, T-PR8-23):

- ``prod.pairing_tokens``: INSERT succeeds; UPDATE raises
  ``PAIRING_TOKENS_INMUTABLE``; DELETE raises the same; rol_app has no
  UPDATE/DELETE; the BEFORE UPDATE OR DELETE trigger
  ``pairing_tokens_no_update_delete`` exists.

- ``prod.revoked_sync_jwts``: INSERT succeeds; UPDATE raises
  ``REVOKED_SYNC_JWTS_INMUTABLE``; DELETE raises the same; rol_app has
  no UPDATE/DELETE; the BEFORE UPDATE OR DELETE trigger
  ``revoked_sync_jwts_no_update_delete`` exists.

The trigger function + table + REVOKE are guaranteed by migration
``0006_*`` which ships all four pieces in the SAME script per
``openspec/config.yaml`` ``rules.tasks`` (defense in depth).

Requires a live Postgres (testcontainers). Skipped when the default
``postgres:16-alpine`` image is used because pg_partman is missing.
Override with ``TEST_PG_IMAGE=parkos-postgres:16-pgpartman`` on a
system where the project's custom image is available. The session-
level fixture ``alembic_upgrade`` in ``conftest.py`` calls
``pytest.skip(...)`` so the WHOLE session is skipped when the chain
fails to apply.

Mirrors ``test_idempotency_inmutable.py`` (PR2 test for the 50th [A]
table) and ``test_a_inmutable.py`` (PR1a test for the original 11 [A]
tables).
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest

# (table, trigger_function_name, trigger_name, expected_error_tag)
_TABLES: tuple[tuple[str, str, str, str], ...] = (
    (
        "pairing_tokens",
        "fn_pairing_tokens_inmutable",
        "pairing_tokens_no_update_delete",
        "PAIRING_TOKENS_INMUTABLE",
    ),
    (
        "revoked_sync_jwts",
        "fn_revoked_sync_jwts_inmutable",
        "revoked_sync_jwts_no_update_delete",
        "REVOKED_SYNC_JWTS_INMUTABLE",
    ),
)


# ---------------------------------------------------------------------------
# CRUD block / unblock
# ---------------------------------------------------------------------------


# The partition gap this suite used to xfail against ("Gap preexistente de
# mantenimiento de partición partman en pairing_tokens") is fixed by
# migration 0018_add_default_partitions_pairing_revoked_jwts — both tables
# now carry a DEFAULT partition, so every real INSERT below succeeds.


@pytest.mark.parametrize(("table_name", "_fn", "_trig", "_tag"), _TABLES)
async def test_insert_succeeds(
    pg_dsn: str, table_name: str, _fn: str, _trig: str, _tag: str
) -> None:
    """INSERT into each new ``[A]`` table succeeds (rol_app has INSERT)."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Minimal column set per table — UUID + fecha_retencion_hasta +
        # the 4 NOT-NULL business fields per the migration DDL.
        if table_name == "pairing_tokens":
            await cur.execute(
                "INSERT INTO prod.pairing_tokens "
                "(uuid, fecha_retencion_hasta, pairing_token_hash, expires_at, used) "
                "VALUES (gen_random_uuid(), CURRENT_DATE, %s, NOW() + INTERVAL '24 hours', false) "
                "RETURNING uuid",
                ("a" * 64,),
            )
        else:  # revoked_sync_jwts
            await cur.execute(
                "INSERT INTO prod.revoked_sync_jwts "
                "(uuid, fecha_retencion_hasta, jwt_kid, jwt_uuid, expires_at, motivo) "
                "VALUES (gen_random_uuid(), CURRENT_DATE, %s, %s, NOW() + INTERVAL '30 days', %s) "
                "RETURNING uuid",
                (f"kid-{uuid_lib.uuid4().hex}", uuid_lib.uuid4().hex, "test"),
            )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()
        assert row_uuid is not None, f"INSERT into {table_name} returned no row"


@pytest.mark.parametrize(("table_name", "_fn", "_trig", "expected_tag"), _TABLES)
async def test_update_blocked(
    pg_dsn: str, table_name: str, _fn: str, _trig: str, expected_tag: str
) -> None:
    """UPDATE on each new ``[A]`` table row raises ``<TABLE>_INMUTABLE``."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Seed a row in its own transaction (commit so the next TX sees it).
        if table_name == "pairing_tokens":
            await cur.execute(
                "INSERT INTO prod.pairing_tokens "
                "(uuid, fecha_retencion_hasta, pairing_token_hash, expires_at, used) "
                "VALUES (gen_random_uuid(), CURRENT_DATE, %s, NOW() + INTERVAL '24 hours', false) "
                "RETURNING uuid",
                ("b" * 64,),
            )
        else:  # revoked_sync_jwts
            await cur.execute(
                "INSERT INTO prod.revoked_sync_jwts "
                "(uuid, fecha_retencion_hasta, jwt_kid, jwt_uuid, expires_at, motivo) "
                "VALUES (gen_random_uuid(), CURRENT_DATE, %s, %s, NOW() + INTERVAL '30 days', %s) "
                "RETURNING uuid",
                (f"kid-{uuid_lib.uuid4().hex}", uuid_lib.uuid4().hex, "test"),
            )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()

        # New TX: UPDATE — blocked by whichever defense layer this
        # connection's role hits first. ``rol_app`` has no UPDATE grant at
        # all (migration 0006's own REVOKE), so Postgres raises
        # ``InsufficientPrivilege`` before the BEFORE trigger ever runs;
        # a role that DOES hold the grant (e.g. table owner, an emergency
        # manual fix) reaches the trigger itself, which raises the
        # table-specific tagged ``RaiseException``. Both are a correctly
        # blocked mutation — only the tag assertion is meaningful when the
        # trigger is the one that actually fired.
        mutate_column = "used = true" if table_name == "pairing_tokens" else "motivo = 'mutated'"
        try:
            await cur.execute(
                f"UPDATE prod.{table_name} SET {mutate_column} WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.RaiseException as exc:
            msg = str(exc)
            assert expected_tag in msg, (
                f"{table_name}: trigger raised but missing tag; "
                f"expected '{expected_tag}' in '{msg}'"
            )
        except psycopg.errors.InsufficientPrivilege:
            pass  # blocked at the GRANT level before the trigger ran — also correct.
        else:  # pragma: no cover
            pytest.fail(f"{table_name}: UPDATE succeeded but should have been blocked")


@pytest.mark.parametrize(("table_name", "_fn", "_trig", "expected_tag"), _TABLES)
async def test_delete_blocked(
    pg_dsn: str, table_name: str, _fn: str, _trig: str, expected_tag: str
) -> None:
    """DELETE on each new ``[A]`` table row raises ``<TABLE>_INMUTABLE``."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        if table_name == "pairing_tokens":
            await cur.execute(
                "INSERT INTO prod.pairing_tokens "
                "(uuid, fecha_retencion_hasta, pairing_token_hash, expires_at, used) "
                "VALUES (gen_random_uuid(), CURRENT_DATE, %s, NOW() + INTERVAL '24 hours', false) "
                "RETURNING uuid",
                ("c" * 64,),
            )
        else:  # revoked_sync_jwts
            await cur.execute(
                "INSERT INTO prod.revoked_sync_jwts "
                "(uuid, fecha_retencion_hasta, jwt_kid, jwt_uuid, expires_at, motivo) "
                "VALUES (gen_random_uuid(), CURRENT_DATE, %s, %s, NOW() + INTERVAL '30 days', %s) "
                "RETURNING uuid",
                (f"kid-{uuid_lib.uuid4().hex}", uuid_lib.uuid4().hex, "test"),
            )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()

        # Same two valid defense layers as test_update_blocked above.
        try:
            await cur.execute(
                f"DELETE FROM prod.{table_name} WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.RaiseException as exc:
            msg = str(exc)
            assert expected_tag in msg, (
                f"{table_name}: trigger raised but missing tag; "
                f"expected '{expected_tag}' in '{msg}'"
            )
        except psycopg.errors.InsufficientPrivilege:
            pass  # blocked at the GRANT level before the trigger ran — also correct.
        else:  # pragma: no cover
            pytest.fail(f"{table_name}: DELETE succeeded but should have been blocked")


# ---------------------------------------------------------------------------
# REVOKE verification — same predicate the canonical
# tests/migrations/check_schema_match.py uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table_name", [t[0] for t in _TABLES])
async def test_rol_app_cannot_update_table(pg_dsn: str, table_name: str) -> None:
    """``rol_app`` MUST NOT have UPDATE privilege on the new ``[A]`` table."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT has_table_privilege('rol_app', %s, 'UPDATE')",
            (f"prod.{table_name}",),
        )
        can_update = (await cur.fetchone())[0]
        assert can_update is False, (
            f"{table_name}: REVOKE failed — rol_app still has UPDATE privilege"
        )


@pytest.mark.parametrize("table_name", [t[0] for t in _TABLES])
async def test_rol_app_cannot_delete_table(pg_dsn: str, table_name: str) -> None:
    """``rol_app`` MUST NOT have DELETE privilege on the new ``[A]`` table."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT has_table_privilege('rol_app', %s, 'DELETE')",
            (f"prod.{table_name}",),
        )
        can_delete = (await cur.fetchone())[0]
        assert can_delete is False, (
            f"{table_name}: REVOKE failed — rol_app still has DELETE privilege"
        )


# ---------------------------------------------------------------------------
# Trigger existence — one ``<table>_no_update_delete`` trigger per [A] table.
# Mirrors SC-10-A-INMUTABLE-DB which counts the trigger count by name.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trigger_name", [t[2] for t in _TABLES])
async def test_inmutable_trigger_exists(pg_dsn: str, trigger_name: str) -> None:
    """``pg_trigger`` MUST have exactly one row for the trigger name ON THE
    PARTITIONED PARENT TABLE (``relkind = 'p'``).

    Since migration 0018 attached a real ``DEFAULT`` partition to both
    tables, Postgres itself clones each parent trigger onto the partition
    (same ``tgname``, different ``tgrelid`` — expected, correct behavior:
    the immutability guarantee must hold on the partition that physically
    stores the rows too). Filtering to the parent's own ``relkind='p'`` row
    is the precise re-statement of this test's original intent ("the
    trigger is declared exactly once") without being tripped up by that
    expected per-partition clone.
    """
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute(
            """
            SELECT count(*)
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            WHERE t.tgname = %s AND c.relkind = 'p'
            """,
            (trigger_name,),
        )
        count = (await cur.fetchone())[0]
        assert count == 1, (
            f"{trigger_name}: expected exactly 1 pg_trigger row on the "
            f"partitioned parent table, got {count}"
        )
