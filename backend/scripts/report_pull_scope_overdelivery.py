"""READ-ONLY diagnostic: rows a branch holds OUTSIDE the new ``/sync/pull`` scope.

Before the scope fix every branch received the full ``usuarios``, ``clientes``,
``vehiculos`` ... tables. This script counts, per affected table, how many local
rows fall outside what ``POST /sync/pull`` would deliver today to that branch.
It reuses the production predicates (``pull_scope.build_scope_predicate``) and
evaluates them against the BRANCH database, whose tables are the same ones.

Safety:
  - the session is read-only (``default_transaction_read_only=on`` at connect
    time, then ``SET TRANSACTION READ ONLY``) and the script only issues SELECT
    ``count(*)`` statements. It never writes, never DELETEs, never closes a
    vigencia.
  - the output is COUNTS ONLY: no names, cedulas, emails, hashes or uuids of rows.

Usage (from ``backend/``)::

    uv run python scripts/report_pull_scope_overdelivery.py \\
        --branch-url postgresql+psycopg://user:pwd@localhost:5433/parkos \\
        --sucursal <uuid_sucursal> [--cloud-url postgresql+psycopg://...]

``--cloud-url`` is optional context: the number of rows of each table the cloud
would deliver to that branch (so "local" can be compared with "expected").

The cleanup decision (leave the rows, or design a NON-propagating logical close)
belongs to the product owner. Do not close vigencias on the branch with the
regular ``close_and_insert`` path: ``clientes`` and ``vehiculos`` are
bidirectional, so the closing write is enqueued in ``sync_queue`` and pushed to
the cloud, where it would close the canonical row for every other branch.
"""

from __future__ import annotations

import argparse
import sys
import uuid as uuid_lib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.pull_scope import build_scope_predicate
from sqlalchemy import ColumnElement, Select, create_engine, false, func, select
from sqlalchemy.engine import Connection

# Tables that were over-delivered (``all_branches`` before the scope fix).
AUDITED_TABLES: tuple[str, ...] = (
    "usuarios",
    "permisos_usuario",
    "clientes",
    "clientes_b2b",
    "vehiculos",
    "empresa",
)


@dataclass(frozen=True)
class TableCounts:
    """Counts for one table. Vigente = ``vigente_hasta IS NULL`` (what a pull sends)."""

    table: str
    total: int
    vigente: int
    outside_vigente: int
    outside_total: int
    cloud_in_scope: int | None = None


def _model(table: str) -> Any:
    return SYNC_CATALOG_BY_NAME[table].model_cls


def _vigente(model: Any) -> ColumnElement[bool]:
    column = getattr(model, "vigente_hasta", None)
    return column.is_(None) if column is not None else ~false()


def _outside(table: str, uuid_sucursal: uuid_lib.UUID) -> ColumnElement[bool]:
    """``NOT COALESCE(<pull predicate>, false)``: a NULL predicate is NOT delivered."""
    predicate = build_scope_predicate(SYNC_CATALOG_BY_NAME[table], uuid_sucursal)
    if predicate is None:  # all_branches: nothing is ever outside
        return false()
    return ~func.coalesce(predicate, false())


def build_count_statements(
    table: str, uuid_sucursal: uuid_lib.UUID
) -> dict[str, Select[tuple[int]]]:
    """The four ``count(*)`` statements for ``table`` (pure: nothing is executed)."""
    model = _model(table)
    outside = _outside(table, uuid_sucursal)
    vigente = _vigente(model)

    def count(*where: ColumnElement[bool]) -> Select[tuple[int]]:
        stmt = select(func.count()).select_from(model)
        return stmt.where(*where) if where else stmt

    return {
        "total": count(),
        "vigente": count(vigente),
        "outside_vigente": count(vigente, outside),
        "outside_total": count(outside),
    }


def build_cloud_in_scope_statement(table: str, uuid_sucursal: uuid_lib.UUID) -> Select[tuple[int]]:
    """Vigente rows the pull would deliver to the branch (cloud-side context)."""
    model = _model(table)
    stmt = select(func.count()).select_from(model).where(_vigente(model))
    predicate = build_scope_predicate(SYNC_CATALOG_BY_NAME[table], uuid_sucursal)
    return stmt if predicate is None else stmt.where(predicate)


def format_report(
    uuid_sucursal: uuid_lib.UUID, counts: list[TableCounts], *, with_cloud: bool
) -> str:
    """Counts-only text report (no row data)."""
    header = ["table", "total", "vigente", "outside_vigente", "outside_total"]
    if with_cloud:
        header.append("cloud_in_scope")
    rows = [header]
    for c in counts:
        row = [c.table, str(c.total), str(c.vigente), str(c.outside_vigente), str(c.outside_total)]
        if with_cloud:
            row.append("-" if c.cloud_in_scope is None else str(c.cloud_in_scope))
        rows.append(row)
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = [f"pull scope over-delivery report (branch {uuid_sucursal}) -- READ ONLY, counts only"]
    for r in rows:
        lines.append(
            "  ".join(
                cell.rjust(widths[i]) if i else cell.ljust(widths[i]) for i, cell in enumerate(r)
            )
        )
    lines.append("")
    lines.append("outside_vigente = vigente local rows the pull would NOT deliver to this branch.")
    lines.append("No data was modified. Cleanup (leave vs non-propagating logical close) is the")
    lines.append("owner's decision: a regular local logical close on clientes/vehiculos")
    lines.append("(bidirectional) is enqueued and pushed to the cloud, closing the canonical")
    lines.append("row for the other branches.")
    return "\n".join(lines)


def _read_only_engine(url: str) -> Any:
    return create_engine(
        url,
        connect_args={"options": "-c default_transaction_read_only=on"},
        pool_pre_ping=False,
    )


def _scalar(conn: Connection, stmt: Select[tuple[int]]) -> int:
    return int(conn.execute(stmt).scalar_one())


def collect(
    branch_url: str,
    uuid_sucursal: uuid_lib.UUID,
    cloud_url: str | None = None,
) -> list[TableCounts]:
    cloud_counts: Mapping[str, int] = {}
    if cloud_url:
        cloud_engine = _read_only_engine(cloud_url)
        with cloud_engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            cloud_counts = {
                t: _scalar(conn, build_cloud_in_scope_statement(t, uuid_sucursal))
                for t in AUDITED_TABLES
            }
        cloud_engine.dispose()

    engine = _read_only_engine(branch_url)
    out: list[TableCounts] = []
    with engine.connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        for table in AUDITED_TABLES:
            stmts = build_count_statements(table, uuid_sucursal)
            values = {k: _scalar(conn, s) for k, s in stmts.items()}
            out.append(TableCounts(table=table, cloud_in_scope=cloud_counts.get(table), **values))
        conn.rollback()
    engine.dispose()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--branch-url", required=True, help="URL of the BRANCH database")
    parser.add_argument("--sucursal", required=True, type=uuid_lib.UUID, help="branch uuid")
    parser.add_argument("--cloud-url", default=None, help="optional cloud DB URL (context only)")
    args = parser.parse_args(argv)

    counts = collect(args.branch_url, args.sucursal, args.cloud_url)
    print(format_report(args.sucursal, counts, with_cloud=args.cloud_url is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
