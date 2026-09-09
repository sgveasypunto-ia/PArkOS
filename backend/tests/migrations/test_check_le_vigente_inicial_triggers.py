"""test_check_le_vigente_inicial_triggers.py — T-PR6-000 acceptance for
migration ``0010_drop_le_vigente_inicial_triggers.py``.

Verifies the fix for a bug discovered during PR5: ``0001_initial_schema.py``
wrongly attaches ``fn_set_vigente_inicial()`` (a trigger that stamps
``NEW.vigente_desde``/``NEW.estado`` on a ``NULL``) to 3 ``[L-E]`` tables
(``ingreso``, ``facturas``, ``factura_electronica``) that carry NO
``_versioning_columns()`` — any real INSERT raised
``UndefinedColumnError: record "new" has no field "vigente_desde"``.

  (a) A minimal INSERT into each of the 3 previously-broken tables now
      succeeds (the migration 0010 fix).
  (b) The trigger still exists and still works for a real ``[V]`` table
      (``sucursal``) — the regression guard confirming 0010 did not touch
      ``fn_set_vigente_inicial()`` itself or any correctly-targeted trigger.
"""
from __future__ import annotations

import uuid as uuid_lib

from sqlalchemy import text


async def test_ingreso_insert_no_longer_raises_undefined_column(
    pg_engine, alembic_upgrade
) -> None:
    """A bare INSERT into ``prod.ingreso`` succeeds post-0010 (was UndefinedColumnError)."""
    async with pg_engine.connect() as conn:
        row_uuid = uuid_lib.uuid4()
        await conn.execute(
            text("INSERT INTO prod.ingreso (uuid) VALUES (:uuid)"),
            {"uuid": row_uuid},
        )
        await conn.commit()

        count = (
            await conn.execute(
                text("SELECT count(*) FROM prod.ingreso WHERE uuid = :uuid"),
                {"uuid": row_uuid},
            )
        ).scalar_one()
        assert count == 1


async def test_facturas_insert_no_longer_raises_undefined_column(
    pg_engine, alembic_upgrade
) -> None:
    """A bare INSERT into ``prod.facturas`` succeeds post-0010 (was UndefinedColumnError)."""
    async with pg_engine.connect() as conn:
        row_uuid = uuid_lib.uuid4()
        await conn.execute(
            text("INSERT INTO prod.facturas (uuid) VALUES (:uuid)"),
            {"uuid": row_uuid},
        )
        await conn.commit()

        count = (
            await conn.execute(
                text("SELECT count(*) FROM prod.facturas WHERE uuid = :uuid"),
                {"uuid": row_uuid},
            )
        ).scalar_one()
        assert count == 1


async def test_factura_electronica_insert_no_longer_raises_undefined_column(
    pg_engine, alembic_upgrade
) -> None:
    """A bare INSERT into ``prod.factura_electronica`` succeeds post-0010."""
    async with pg_engine.connect() as conn:
        row_uuid = uuid_lib.uuid4()
        await conn.execute(
            text("INSERT INTO prod.factura_electronica (uuid) VALUES (:uuid)"),
            {"uuid": row_uuid},
        )
        await conn.commit()

        count = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM prod.factura_electronica WHERE uuid = :uuid"
                ),
                {"uuid": row_uuid},
            )
        ).scalar_one()
        assert count == 1


async def test_le_triggers_are_gone(pg_engine, alembic_upgrade) -> None:
    """The 3 wrongly-attached triggers no longer exist after 0010."""
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger t "
                    "JOIN pg_class c ON t.tgrelid = c.oid "
                    "JOIN pg_namespace n ON c.relnamespace = n.oid "
                    "WHERE n.nspname = 'prod' AND t.tgname IN ("
                    "'ingreso_set_vigente_inicial', "
                    "'facturas_set_vigente_inicial', "
                    "'factura_electronica_set_vigente_inicial'"
                    ") AND NOT t.tgisinternal"
                )
            )
        ).scalars().all()
        assert rows == []


async def test_sucursal_vigente_inicial_trigger_still_works(
    pg_engine, alembic_upgrade
) -> None:
    """Regression guard: the trigger still fires for a real ``[V]`` table.

    ``sucursal`` correctly carries ``_versioning_columns()`` — a bare
    INSERT (no ``vigente_desde``/``estado`` supplied) must still be stamped
    by ``fn_set_vigente_inicial()`` exactly as before 0010.
    """
    async with pg_engine.connect() as conn:
        row_uuid = uuid_lib.uuid4()
        await conn.execute(
            text("INSERT INTO prod.sucursal (uuid, nombre) VALUES (:uuid, :nombre)"),
            {"uuid": row_uuid, "nombre": f"Sucursal T-PR6-000 {row_uuid.hex[:8]}"},
        )
        await conn.commit()

        row = (
            await conn.execute(
                text(
                    "SELECT vigente_desde, estado FROM prod.sucursal WHERE uuid = :uuid"
                ),
                {"uuid": row_uuid},
            )
        ).one()
        assert row.vigente_desde is not None
        assert row.estado == "activo"
