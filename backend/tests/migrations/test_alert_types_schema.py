"""test_alert_types_schema.py — T-PR8-002 acceptance for migration
``0013_add_alert_types.py`` (design.md §2 Issue #6).

Verifies the table, REVOKE, inmutable trigger, CHECK constraint, and the
idempotent seed all exist/behave correctly after ``alembic upgrade head``.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

_EXPECTED_TIPOS = frozenset(
    {
        "hash_chain_anomaly",
        "dian_rechazada",
        "dian_timeout",
        "dian_error",
        "branch_offline_reauth_required",
        "orphan_workflow_chain",
        "fe_provider_error",
        "fe_numbering_exhausted",
    }
)


async def test_alert_types_table_exists(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'prod' AND table_name = 'alert_types'"
                )
            )
        ).scalars().all()
    assert rows == ["alert_types"]


async def test_alert_types_seed_has_exactly_8_rows(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        result = await conn.execute(text("SELECT tipo_alerta FROM prod.alert_types"))
        rows = result.scalars().all()
    assert set(rows) == _EXPECTED_TIPOS
    assert len(rows) == 8


async def test_alert_types_severity_values(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT tipo_alerta, severity FROM prod.alert_types"))
        ).all()
    by_tipo = dict(rows)
    assert by_tipo["hash_chain_anomaly"] == "critical"
    assert by_tipo["dian_rechazada"] == "warning"
    assert by_tipo["fe_provider_error"] == "critical"
    assert by_tipo["fe_numbering_exhausted"] == "critical"
    assert all(v in {"info", "warning", "critical"} for v in by_tipo.values())


async def test_alert_types_severity_check_constraint(pg_dsn: str, alembic_upgrade) -> None:
    """An invalid ``severity`` value must be rejected by the CHECK constraint."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            await cur.execute(
                "INSERT INTO prod.alert_types (tipo_alerta, severity) VALUES (%s, %s)",
                ("__test_invalid_severity__", "not_a_real_severity"),
            )
        await conn.rollback()


async def test_alert_types_revoked(pg_dsn: str, alembic_upgrade) -> None:
    """``rol_app`` must NOT have UPDATE/DELETE on ``alert_types``."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        await cur.execute("SELECT has_table_privilege('rol_app', 'prod.alert_types', 'UPDATE')")
        can_update = (await cur.fetchone())[0]
        await cur.execute("SELECT has_table_privilege('rol_app', 'prod.alert_types', 'DELETE')")
        can_delete = (await cur.fetchone())[0]
    assert can_update is False
    assert can_delete is False


async def test_alert_types_inmutable_trigger(pg_dsn: str, alembic_upgrade) -> None:
    """UPDATE and DELETE both raise ``ALERT_TYPES_INMUTABLE``."""
    import psycopg

    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="ALERT_TYPES_INMUTABLE"):
            await cur.execute(
                "UPDATE prod.alert_types SET descripcion = 'x' WHERE tipo_alerta = 'dian_error'"
            )
        await conn.rollback()

        with pytest.raises(psycopg.errors.InsufficientPrivilege, match="ALERT_TYPES_INMUTABLE"):
            await cur.execute("DELETE FROM prod.alert_types WHERE tipo_alerta = 'dian_error'")
        await conn.rollback()


async def test_alert_types_reseed_is_idempotent(pg_engine, alembic_upgrade) -> None:
    """Re-running the same idempotent INSERT is a no-op (T-PR8-002 acceptance)."""
    async with pg_engine.begin() as conn:
        before = (await conn.execute(text("SELECT count(*) FROM prod.alert_types"))).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity) "
                "VALUES ('dian_error', 'duplicate insert attempt', 'warning') "
                "ON CONFLICT (tipo_alerta) DO NOTHING"
            )
        )
        after = (await conn.execute(text("SELECT count(*) FROM prod.alert_types"))).scalar_one()
    assert before == after == 8
