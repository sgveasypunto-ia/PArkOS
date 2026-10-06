"""The scope-entry query of the incremental pull does not re-evaluate the scope.

The entry predicate of every derived rule is, by construction, the scope rule with a
window on the bridge rows (a subset of the scope), so ANDing the full scope into the
entry query only costs a second evaluation of the same sub-selects. ``empresa`` is the
exception (its entry is "the branch row is new", which does not name the empresa) and
must stay self-sufficient. Pure compile-time coverage, no database.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Any

import pytest
from parkos_core.api.v1 import sync_router
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.pull_scope import build_scope_entry_predicate, build_scope_predicate
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

BRANCH = uuid_lib.UUID("00000000-0000-0000-0000-0000000000a1")
_DERIVED = ["usuarios", "permisos_usuario", "clientes", "clientes_b2b", "vehiculos", "empresa"]


def _literal(stmt: Any) -> str:
    compiled = stmt.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split())


class _Result:
    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return []


class _RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, stmt: Any) -> _Result:
        self.statements.append(stmt)
        return _Result()


async def _entry_statements() -> dict[str, str]:
    """Compiled entry statements (the ones without LIMIT) keyed by table."""
    session = _RecordingSession()
    await sync_router._fetch_pull_rows(session, uuid_sucursal=BRANCH, since_seq=1_000)  # type: ignore[arg-type]
    by_table: dict[str, str] = {}
    for stmt in session.statements:
        if stmt._limit_clause is not None:
            continue
        table = stmt.column_descriptions[0]["entity"].__tablename__
        by_table[table] = _literal(stmt)
    return by_table


@pytest.mark.parametrize("table", _DERIVED)
async def test_entry_query_is_exactly_the_entry_predicate(table: str) -> None:
    spec = SYNC_CATALOG_BY_NAME[table]
    model: Any = spec.model_cls
    floor = sync_router._created_at_floor_for_seq(1_000)
    assert isinstance(floor, datetime)
    entry = build_scope_entry_predicate(spec, BRANCH, floor, None)
    expected = select(model).where(entry)
    if spec.audit_class == "V":
        expected = expected.where(model.vigente_hasta.is_(None))
    expected = expected.order_by(model.created_at.asc(), model.uuid.asc())

    assert (await _entry_statements())[spec.model_cls.__tablename__] == _literal(expected)


@pytest.mark.parametrize("table", [t for t in _DERIVED if t != "empresa"])
def test_entry_predicate_is_contained_in_the_scope_rule(table: str) -> None:
    """Containment witness: the entry is the scope rule with extra bridge-row
    conditions only, so every bridge relation it reads is a relation the scope reads."""
    spec = SYNC_CATALOG_BY_NAME[table]
    floor = datetime(2026, 10, 5, 12, 0, 0)
    entry = _literal(select(spec.model_cls.uuid).where(build_scope_entry_predicate(spec, BRANCH, floor)))
    scope = _literal(select(spec.model_cls.uuid).where(build_scope_predicate(spec, BRANCH)))
    for bridge in ("usuarios_sucursal", "subscripciones_cliente", "factura_electronica", "subscripcion_vehiculos"):
        if f"prod.{bridge}" in entry:
            assert f"prod.{bridge}" in scope


def test_empresa_entry_still_names_the_empresa_of_the_branch() -> None:
    """Not a subset of the scope on its own: without the scope rule it would return every empresa."""
    spec = SYNC_CATALOG_BY_NAME["empresa"]
    floor = datetime(2026, 10, 5, 12, 0, 0)
    sql = _literal(select(spec.model_cls.uuid).where(build_scope_entry_predicate(spec, BRANCH, floor)))

    assert "prod.sucursal.created_at >= '2026-10-05 12:00:00'" in sql
    assert "prod.empresa.nit IN" in sql  # the scope rule is part of the entry predicate
