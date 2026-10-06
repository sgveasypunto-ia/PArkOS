"""Migrations 0086 / 0087 against a real Postgres (testcontainers via ``alembic_upgrade``)."""
from __future__ import annotations

from sqlalchemy import text


async def test_alert_types_seeded_as_info(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT tipo_alerta, severity FROM prod.alert_types "
                    "WHERE tipo_alerta LIKE 'suscripcion_placa_%'"
                )
            )
        ).all()
    assert dict(rows) == {
        "suscripcion_placa_agregada": "info",
        "suscripcion_placa_quitada": "info",
    }


async def test_permission_seeded_once_with_deterministic_uuid(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT uuid::text FROM prod.permisos "
                    "WHERE permiso = 'gestionar_placas_suscripcion' AND vigente_hasta IS NULL"
                )
            )
        ).scalars().all()
    assert rows == ["3cfef8c2-7f34-5eed-b7a0-4ca169343d5d"]


async def test_tipo_subscripciones_column_and_fk(pg_engine, alembic_upgrade) -> None:
    async with pg_engine.connect() as conn:
        nullable = (
            await conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns WHERE table_schema='prod' "
                    "AND table_name='tipo_subscripciones' AND column_name='uuid_tipo_vehiculo'"
                )
            )
        ).scalar_one()
        fk = (
            await conn.execute(
                text(
                    "SELECT confrelid::regclass::text FROM pg_constraint "
                    "WHERE conname='fk_tipo_subscripciones_uuid_tipo_vehiculo'"
                )
            )
        ).scalar_one()
    assert nullable == "YES"
    assert fk == "prod.tipos_vehiculo"
