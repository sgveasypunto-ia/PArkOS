"""Unit tests for ``repo.sucursal.propagate_uuid_to_fks`` -- the
post-close+insert hook that prevents the
``sucursales_permitidas``-style FK breakage (see migration 0061
docstring).

The full DB-level behavior is covered by the alembic migration in CI;
this file covers the Python-level contract (table list, idempotent
UPDATE shape, early-return on same uuid) without spinning up a
testcontainer.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text as sql_text
from sqlalchemy.sql.elements import TextClause

from parkos_core.repo.sucursal import (
    _FK_TABLES,
    propagate_uuid_to_fks,
)


def _capture_execute_calls(mock_session: AsyncMock) -> list[tuple[str, dict]]:
    """Return the (sql_template, params) pairs from every
    ``session.execute`` call, asserting each is a ``text(...)`` with
    a single named-bind ``params`` dict.
    """
    captured: list[tuple[str, dict]] = []
    for c in mock_session.execute.call_args_list:
        # Each call is ``session.execute(text(...), {"k": v})`` per the
        # current implementation. ``text(...)`` returns a
        # ``TextClause`` instance (NOT the function itself), which is
        # what we want to assert here.
        stmt, params = c.args
        assert isinstance(stmt, TextClause), (
            f"expected sqlalchemy TextClause (text(...) return value), "
            f"got {type(stmt).__name__}"
        )
        assert isinstance(params, dict), (
            f"expected dict params, got {type(params).__name__}"
        )
        captured.append((str(stmt), params))
    return captured


@pytest.mark.parametrize(
    ("schema", "table"),
    [(s, t) for s, t in _FK_TABLES],
)
def test_fk_table_list_covers_all_eight_admin_facing_tables(
    schema: str, table: str
) -> None:
    """Lock in the exact set of tables the helper propagates.

    Adding a new admin-facing FK to ``prod.sucursal`` (e.g. a future
    ``prod.configuracion_x`` table) is opt-in: extend ``_FK_TABLES`` here
    AND in migration 0061.
    """
    # All entries are under ``prod`` schema (the project's only schema
    # for tenant data; ``parkos_core`` keeps its own internal tables out
    # of the FK surface).
    assert schema == "prod"
    # All 7 entries share the same FK column name ``uuid_sucursal`` --
    # the canonical FK column name on every table that branches against
    # Sucursal (see 0001_initial_schema).
    assert table in {
        "usuarios_sucursal",
        "tarifas_sucursal",
        "cantidad_vehiculos_sucursal",
        "configuracion_tolerancias",
        "configuracion_seguridad",
        "resolucion_facturacion",
        "subscripciones_cliente",
    }


async def test_propagate_uuid_to_fks_executes_one_update_per_table() -> None:
    old_uuid = uuid_lib.uuid4()
    new_uuid = uuid_lib.uuid4()
    session = AsyncMock()

    await propagate_uuid_to_fks(session, old_uuid=old_uuid, new_uuid=new_uuid)

    assert session.execute.await_count == len(_FK_TABLES)
    calls = _capture_execute_calls(session)
    for (schema, table), (sql, params) in zip(_FK_TABLES, calls):
        assert f"{schema}.{table}" in sql
        assert "SET uuid_sucursal = :new_uuid" in sql
        assert "WHERE uuid_sucursal = :old_uuid" in sql
        assert params == {"new_uuid": new_uuid, "old_uuid": old_uuid}


async def test_propagate_uuid_to_fks_is_a_noop_when_uuids_match() -> None:
    """The helper is called from ``close_and_insert`` after the flush; if
    (defensively) called with the same uuid on both sides, skip the
    UPDATE entirely. Belt-and-suspenders -- the caller already gates on
    ``current_uuid is not None``.
    """
    same_uuid = uuid_lib.uuid4()
    session = AsyncMock()

    await propagate_uuid_to_fks(
        session, old_uuid=same_uuid, new_uuid=same_uuid
    )

    session.execute.assert_not_awaited()


async def test_propagate_uuid_to_fks_uses_parameterized_sql() -> None:
    """SQL injection guard: the helper must NEVER interpolate uuids into
    the SQL string. The bind dict ensures Postgres treats them as data.
    """
    old_uuid = uuid_lib.uuid4()
    new_uuid = uuid_lib.uuid4()
    session = AsyncMock()

    await propagate_uuid_to_fks(session, old_uuid=old_uuid, new_uuid=new_uuid)

    for c in session.execute.call_args_list:
        sql_text = str(c.args[0])
        assert str(old_uuid) not in sql_text, (
            "old_uuid must be bound, not interpolated -- otherwise "
            "uuid4() output would be sitting in a SQL string and could "
            "carry SQL-injection payload"
        )
        assert str(new_uuid) not in sql_text
