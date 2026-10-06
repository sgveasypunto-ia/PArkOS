"""Migration 0083: indexes backing the SQL-scoped ``POST /sync/pull``."""
from __future__ import annotations

import pytest
from sqlalchemy import text

_EXPECTED = {
    "ix_tarifas_sucursal_sucursal_created_at": ("tarifas_sucursal", "uuid_sucursal, created_at"),
    "ix_documentos_sucursal_created_at": ("documentos", "uuid_sucursal, created_at"),
    "ix_cantidad_vehiculos_sucursal_sucursal_created_at": (
        "cantidad_vehiculos_sucursal",
        "uuid_sucursal, created_at",
    ),
    "ix_resolucion_facturacion_sucursal_created_at": (
        "resolucion_facturacion",
        "uuid_sucursal, created_at",
    ),
    "ix_configuracion_tolerancias_sucursal_created_at": (
        "configuracion_tolerancias",
        "uuid_sucursal, created_at",
    ),
    "ix_configuracion_seguridad_sucursal_created_at": (
        "configuracion_seguridad",
        "uuid_sucursal, created_at",
    ),
    "ix_usuarios_sucursal_sucursal_created_at": ("usuarios_sucursal", "uuid_sucursal, created_at"),
    "ix_subscripciones_cliente_sucursal_created_at": (
        "subscripciones_cliente",
        "uuid_sucursal, created_at",
    ),
    "ix_subscripciones_cliente_sucursal_cliente": (
        "subscripciones_cliente",
        "uuid_sucursal, uuid_cliente",
    ),
    "ix_factura_electronica_sucursal_cliente": (
        "factura_electronica",
        "uuid_sucursal, uuid_cliente",
    ),
}


@pytest.mark.parametrize("name", sorted(_EXPECTED))
async def test_pull_scope_index_exists_with_expected_columns(
    name: str, pg_engine, alembic_upgrade
) -> None:
    table, columns = _EXPECTED[name]
    async with pg_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT tablename, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'prod' AND indexname = :n"
                ),
                {"n": name},
            )
        ).one()

    assert row.tablename == table
    assert f"({columns})" in row.indexdef
    assert "WHERE" not in row.indexdef  # plain, not partial
