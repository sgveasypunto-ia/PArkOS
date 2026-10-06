"""Pure logic of ``scripts/report_pull_scope_overdelivery.py`` (no database)."""

from __future__ import annotations

import importlib.util
import sys
import uuid as uuid_lib
from pathlib import Path
from types import ModuleType

from sqlalchemy.dialects import postgresql

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "report_pull_scope_overdelivery.py"
BRANCH = uuid_lib.UUID("11111111-1111-1111-1111-111111111111")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("report_pull_scope_overdelivery", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


report = _load()


def _sql(stmt: object) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


def test_audited_tables_are_the_overdelivered_ones() -> None:
    assert report.AUDITED_TABLES == (
        "usuarios",
        "permisos_usuario",
        "clientes",
        "clientes_b2b",
        "vehiculos",
        "empresa",
    )


def test_statements_only_count_and_negate_the_pull_predicate() -> None:
    for table in report.AUDITED_TABLES:
        stmts = report.build_count_statements(table, BRANCH)
        assert set(stmts) == {"total", "vigente", "outside_vigente", "outside_total"}
        for sql in map(_sql, stmts.values()):
            assert sql.startswith("SELECT count(*)")  # counts only, never row data
        outside = _sql(stmts["outside_total"])
        assert "NOT coalesce(" in outside  # a NULL predicate is NOT delivered


def test_usuarios_outside_scope_reuses_the_membership_subselect() -> None:
    sql = _sql(report.build_count_statements("usuarios", BRANCH)["outside_total"])
    assert "usuarios_sucursal" in sql
    assert "vigente_hasta IS NULL" in sql


def test_branch_uuid_is_bound_not_inlined() -> None:
    stmt = report.build_count_statements("clientes", BRANCH)["outside_total"]
    assert str(BRANCH) not in _sql(stmt)
    assert BRANCH in stmt.compile().params.values()


def test_cloud_statement_is_the_vigente_pull_scope() -> None:
    sql = _sql(report.build_cloud_in_scope_statement("usuarios", BRANCH))
    assert sql.startswith("SELECT count(*)")
    assert "usuarios_sucursal" in sql


def test_format_report_is_counts_only() -> None:
    counts = [
        report.TableCounts("usuarios", 10, 9, 4, 5, cloud_in_scope=3),
        report.TableCounts("empresa", 1, 1, 0, 0, cloud_in_scope=None),
    ]
    text = report.format_report(BRANCH, counts, with_cloud=True)
    for expected in ("usuarios", "outside_vigente", "cloud_in_scope"):
        assert expected in text
    assert "owner's decision" in text
    lines = {
        ln.split()[0]: ln.split()
        for ln in text.splitlines()
        if ln.startswith(("usuarios", "empresa"))
    }
    assert lines["usuarios"][1:] == ["10", "9", "4", "5", "3"]
    assert lines["empresa"][-1] == "-"


def test_format_report_without_cloud_has_no_cloud_column() -> None:
    text = report.format_report(
        BRANCH, [report.TableCounts("usuarios", 1, 1, 0, 0)], with_cloud=False
    )
    assert "cloud_in_scope" not in text
