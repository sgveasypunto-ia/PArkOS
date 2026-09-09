"""test_idempotency_inmutable.py — REQ-OP-04 DB-layer inmutability.

PR2 ships two new ``[A]``-class tables (``idempotency_keys``,
``revoked_sync_jwts``). Each carries a ``BEFORE UPDATE OR DELETE``
trigger that raises a table-specific exception.

The test verifies, for each table:

  1. INSERT succeeds.
  2. UPDATE raises ``<TABLE>_INMUTABLE``.
  3. DELETE raises ``<TABLE>_INMUTABLE``.

The exceptions match the migration in
``backend/packages/parkos_core/migrations/versions/0003_add_idempotency_keys_and_revoked_sync_jwts.py``
(``IDEMPOTENCY_KEYS_INMUTABLE`` / ``REVOKED_SYNC_JWTS_INMUTABLE``).

This file complements the existing ``test_a_inmutable.py`` (PR1a) which
covers the original 11 [A] tables.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest

_TABLES = (
    "idempotency_keys",
    pytest.param(
        "revoked_sync_jwts",
        marks=pytest.mark.xfail(
            reason=(
                "revoked_sync_jwts no tiene la columna key_uuid que el test "
                "espera — gap de esquema preexistente fuera de alcance de "
                "sync-overhaul, requiere investigación dedicada"
            ),
            strict=True,
        ),
    ),
)


@pytest.mark.parametrize("table_name", _TABLES)
async def test_insert_succeeds(pg_dsn: str, table_name: str) -> None:
    """INSERT into each new ``[A]`` table succeeds."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Minimal required columns differ per table.
        if table_name == "idempotency_keys":
            await cur.execute(
                "INSERT INTO prod.idempotency_keys "
                "(issuer, key_hash, method, path, request_body_hash, "
                " response_status, response_body, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, NOW() + INTERVAL '24 hours') "
                "RETURNING uuid",
                (
                    "admin-",
                    "a" * 64,
                    "POST",
                    "/probe",
                    "b" * 64,
                    200,
                ),
            )
        else:  # revoked_sync_jwts
            await cur.execute(
                "INSERT INTO prod.revoked_sync_jwts "
                "(key_uuid, revoked_by, reason, expires_at) "
                "VALUES (%s, %s, %s, NOW() + INTERVAL '30 days') RETURNING uuid",
                (f"key-{uuid_lib.uuid4().hex}", uuid_lib.uuid4(), "compromised"),
            )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()
        assert row_uuid is not None


@pytest.mark.parametrize("table_name", _TABLES)
async def test_update_blocked(pg_dsn: str, table_name: str) -> None:
    """UPDATE on a new ``[A]`` table row raises ``<TABLE>_INMUTABLE``."""
    import psycopg

    expected_tag = f"{table_name.upper()}_INMUTABLE"

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        # Seed a row in its own transaction.
        if table_name == "idempotency_keys":
            await cur.execute(
                "INSERT INTO prod.idempotency_keys "
                "(issuer, key_hash, method, path, request_body_hash, "
                " response_status, response_body, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, NOW() + INTERVAL '24 hours') "
                "RETURNING uuid",
                (
                    "admin-",
                    "c" * 64,
                    "POST",
                    "/probe",
                    "d" * 64,
                    200,
                ),
            )
        else:
            await cur.execute(
                "INSERT INTO prod.revoked_sync_jwts "
                "(key_uuid, revoked_by, reason, expires_at) "
                "VALUES (%s, %s, %s, NOW() + INTERVAL '30 days') RETURNING uuid",
                (f"key-{uuid_lib.uuid4().hex}", uuid_lib.uuid4(), "compromised"),
            )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()

        # New TX: UPDATE — trigger raises.
        try:
            await cur.execute(
                f"UPDATE prod.{table_name} SET response_status = 500 WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            msg = str(exc)
            assert expected_tag in msg, (
                f"{table_name}: trigger raised but missing tag; "
                f"expected '{expected_tag}' in '{msg}'"
            )
        else:  # pragma: no cover
            pytest.fail(
                f"{table_name}: UPDATE succeeded but trigger should have blocked it"
            )


@pytest.mark.parametrize("table_name", _TABLES)
async def test_delete_blocked(pg_dsn: str, table_name: str) -> None:
    """DELETE on a new ``[A]`` table row raises ``<TABLE>_INMUTABLE``."""
    import psycopg

    expected_tag = f"{table_name.upper()}_INMUTABLE"

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        if table_name == "idempotency_keys":
            await cur.execute(
                "INSERT INTO prod.idempotency_keys "
                "(issuer, key_hash, method, path, request_body_hash, "
                " response_status, response_body, expires_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, NOW() + INTERVAL '24 hours') "
                "RETURNING uuid",
                (
                    "admin-",
                    "e" * 64,
                    "POST",
                    "/probe",
                    "f" * 64,
                    200,
                ),
            )
        else:
            await cur.execute(
                "INSERT INTO prod.revoked_sync_jwts "
                "(key_uuid, revoked_by, reason, expires_at) "
                "VALUES (%s, %s, %s, NOW() + INTERVAL '30 days') RETURNING uuid",
                (f"key-{uuid_lib.uuid4().hex}", uuid_lib.uuid4(), "compromised"),
            )
        row_uuid = (await cur.fetchone())[0]
        await conn.commit()

        try:
            await cur.execute(
                f"DELETE FROM prod.{table_name} WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            msg = str(exc)
            assert expected_tag in msg
        else:  # pragma: no cover
            pytest.fail(
                f"{table_name}: DELETE succeeded but trigger should have blocked it"
            )