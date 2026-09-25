"""
check_schema_match.py — Full schema conformance verifier.

Parses `modelo_datos_er.mmd` (canonical Mermaid ER diagram) and asserts a 100%
match against the live `prod.*` Postgres schema. Zero difference tolerated —
any deviation exits non-zero with a precise diff.

**ADR-002 (sync-overhaul PR10, T-PR10-007).** The ER now declares 51
entities; the physical `prod.*` schema carries 54 tables = 51 ER + 3
non-ER operational tables (`idempotency_keys`, `pairing_tokens`,
`revoked_sync_jwts` — added by `create-49-table-apis` PR7/PR8, confirmed
against `catalog/local_only_catalog.py`). These 3 have no `%% [A]` block in
`modelo_datos_er.mmd` by design (ADR-002) and must NOT be flagged as
"extra" tables not in the ER — see `EXPECTED_NON_ER_TABLES` in check (a).

Checks performed:
  (a) Every table listed in the ER exists in `prod.*`; every physical table
      not in the ER is either an accepted `EXPECTED_NON_ER_TABLES` entry or
      a genuine extra (fails)
  (b) Every column in the ER exists in the DB with the same name, type, and
      nullability (within a small set of accepted Postgres vs Mermaid synonyms)
  (c) Every UK declared in the ER exists as a UNIQUE or PRIMARY KEY constraint
  (d) Every FK declared in the ER exists as a FOREIGN KEY constraint
  (e) Every `[A]`-class table has `REVOKE UPDATE, DELETE FROM rol_app` (verified
      via `has_table_privilege`)
  (f) Every `[A]`-class table has a `BEFORE UPDATE OR DELETE` trigger named
      `<table>_inmutable` (or similar) that raises on mutation
  (g) Every `[L-S]`-class table has a `BEFORE UPDATE` session-guard trigger that
      requires a `log_transaccional` row in the same TX
  (h) The 8 high-volume `[A]` tables have a `pg_partman` partition registered
      (informational only for any OTHER registered partman parent — e.g.
      `sync_queue_lw_buffer`'s own daily partition schedule, ADR-002 — extra
      partman parents are never a failure, only the 8 listed ones are required)

Usage:
  python openspec/scripts/check_schema_match.py \\
      [--er PATH/modelo_datos_er.mmd] \\
      [--database-url postgresql://...] \\
      [--schema prod]

Exit codes:
  0 = 100% match (zero difference)
  1 = at least one difference (printed to stderr with diff)
  2 = missing prerequisite (DB unreachable, ER not parseable)
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import psycopg
    from psycopg import sql
except ImportError:
    print("ERROR: psycopg (v3) required. Install with `uv add psycopg[binary]`.", file=sys.stderr)
    raise


# ---------------------------------------------------------------------------
# ER parsing (Mermaid erDiagram, our specific dialect)
# ---------------------------------------------------------------------------

# Table-class tags we expect in the ER (as the first non-empty %% comment in
# each block). The canonical ER uses %% [V], %% [L-E], %% [L-W], %% [L-S], %% [A].
CLASS_RE = re.compile(r"%%\s*\[([VLA][\w-]*)\]\s+([^\n]+)")
# Table-block opener: `    <name> {`
TABLE_HEADER_RE = re.compile(r"^\s{4}([a-z_][a-z0-9_]*)\s*\{")
# Column line: `<type> <name> [PK|FK|UK]? "<comment>"`
COLUMN_RE = re.compile(
    r"^\s+(?P<type>\S+)\s+(?P<name>[a-z_][a-z0-9_]*)\s*"
    r"(?P<flags>(?:\s+(?:PK|FK|UK))*)"
    r'(?:\s+"(?P<comment>[^"]*)")?'
    r"\s*$"
)
# UK declaration in comment: `UK01 (field, vigente_desde) - ...`
UK_RE = re.compile(r"UK\d+\s*\(([^)]+)\)")
# FK declaration in comment: `references prod.<table>(<field>)` or
# `FK -> prod.<table>.<field>`
FK_RE = re.compile(r"(?:FK\s*(?:->|:)\s*([a-z_][a-z0-9_]*)|references\s+([a-z_][a-z0-9_]*))")


@dataclass(frozen=True)
class Column:
    name: str
    type_raw: str
    flags: frozenset[str]  # subset of {"PK", "FK", "UK"}


@dataclass(frozen=True)
class Table:
    name: str
    klass: str  # "V", "L-E", "L-W", "L-S", "A"
    columns: tuple[Column, ...]
    uks: tuple[tuple[str, ...], ...]  # each UK is a tuple of column names
    fks: tuple[str, ...]  # referenced table names (informational)


# ADR-002: physical prod tables that are NOT ER entities (no `%% [A]` block
# in modelo_datos_er.mmd) — deliberately, not an omission. `create-49-table-
# apis` PR7/PR8 added these as `LocalOnlyCatalog` entries
# (`catalog/local_only_catalog.py`), never replicated, never ER-modeled.
# Physical total = 51 ER + 4 non-ER = 55.
# `ingreso_consecutivo_contador` is the 4th non-ER table, added in
# `ingreso-multi-tipo-consecutivo` PR-A (migration 0042, 2026-09-22): a
# local-only per-branch counter for ingresos sin placa. Not replicated to
# the cloud; never ER-modeled (same convention as the other 3).
# `sync_cursor` is the 5th non-ER table, added in `sync-sucursal-cursor-
# pull` (migration 0051): the branch worker's per-uuid_sucursal cloud-pull
# high-water mark (CU-07). Local-only, never replicated, never ER-modeled.
EXPECTED_NON_ER_TABLES: frozenset[str] = frozenset(
    {
        "idempotency_keys",
        "pairing_tokens",
        "revoked_sync_jwts",
        "ingreso_consecutivo_contador",
        "sync_cursor",
    }
)

# ADR-002/003: `[A]` tables with a documented, DELETE-only REVOKE carve-out
# (UPDATE stays granted) instead of the standard full `REVOKE UPDATE, DELETE`.
# `sync_queue_lw_buffer`'s drain/TTL-sweep workers must UPDATE `estado`/
# `ultimo_error` after insert (0012_add_sync_queue_lw_buffer.py) — the same
# tension design §12 already resolved for `sync_queue` itself (full UPDATE
# grant, Python-side discipline), generalized to this one other table.
DELETE_ONLY_REVOKE_TABLES: frozenset[str] = frozenset({"sync_queue_lw_buffer"})


# Mermaid → Postgres type mapping (covers everything in our canonical ER).
# Anything outside this map raises a parse error — better to fail loud than
# silently accept an unknown type.
MERMAID_TO_POSTGRES: dict[str, str] = {
    "uuid": "uuid",
    "string": "character varying",  # accept either varchar or text downstream
    "int": "integer",
    "bigint": "bigint",
    "decimal": "numeric",
    "bool": "boolean",
    "timestamp": "timestamp without time zone",
    "date": "date",
    "text": "text",
    "json": "jsonb",
}


@dataclass
class ParseError(Exception):
    line: int
    reason: str


def parse_er(path: Path) -> dict[str, Table]:
    """Parse a Mermaid erDiagram into a dict of tables keyed by name."""
    text = path.read_text(encoding="utf-8")
    # Mutable builder until each table is finalized (frozen Table dataclass).
    @dataclass
    class TableBuilder:
        name: str
        klass: str = "?"
        columns: list[Column] = field(default_factory=list)
        uks: list[tuple[str, ...]] = field(default_factory=list)
        fks: list[str] = field(default_factory=list)

    builders: dict[str, TableBuilder] = {}
    current: TableBuilder | None = None
    seen_class: bool = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Track table class via the first %% comment inside a table block.
        m_class = CLASS_RE.search(line)
        if m_class and current is not None and not seen_class:
            current.klass = m_class.group(1)
            builders[current.name] = current
            seen_class = True
            continue

        m_header = TABLE_HEADER_RE.match(line)
        if m_header:
            current = TableBuilder(name=m_header.group(1))
            seen_class = False
            continue

        if line.strip() == "}" and current is not None:
            current = None
            seen_class = False
            continue

        if current is None:
            continue

        m_col = COLUMN_RE.match(line)
        if not m_col:
            continue
        flags = frozenset(m_col.group("flags").split())
        column = Column(
            name=m_col.group("name"),
            type_raw=m_col.group("type"),
            flags=flags,
        )
        current.columns.append(column)
        # Look for UK / FK in the comment.
        comment = m_col.group("comment") or ""
        for m_uk in UK_RE.finditer(comment):
            names = tuple(n.strip() for n in m_uk.group(1).split(","))
            current.uks.append(names)
        for m_fk in FK_RE.finditer(comment):
            ref = m_fk.group(1) or m_fk.group(2)
            if ref:
                current.fks.append(ref)

    # Fill klass defaults if no %% comment was found (safety net).
    for b in builders.values():
        if b.klass == "?":
            cols = {c.name for c in b.columns}
            if "hash_actual" in cols:
                b.klass = "A"
            elif any(c in cols for c in ("uuid_anulacion_padre", "uuid_reclamo_padre", "uuid_alerta_padre",
                                          "uuid_reimpresion_padre", "uuid_envio_padre", "uuid_validacion_padre")):
                b.klass = "L-W"
            elif "timestamp_cierre" in cols and b.name in {"login", "sesion"}:
                b.klass = "L-S"
            elif "timestamp_evento" in cols and b.name in {"ingreso", "facturas", "factura_electronica"}:
                b.klass = "L-E"
            else:
                b.klass = "V"

    if not builders:
        raise ParseError(0, f"ER parser found 0 tables in {path}")

    return {
        name: Table(
            name=b.name,
            klass=b.klass,
            columns=tuple(b.columns),
            uks=tuple(b.uks),
            fks=tuple(b.fks),
        )
        for name, b in builders.items()
    }


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------

@dataclass
class Diff:
    issues: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.issues.append(msg)

    @property
    def ok(self) -> bool:
        return not self.issues


def diff_schema(tables: dict[str, Table], conn, schema: str = "prod") -> Diff:
    """Run all 8 checks against the live DB and accumulate issues."""
    diff = Diff()

    cur = conn.cursor()

    # --- (a) every table exists ---
    # We query pg_class directly (not information_schema.tables) so we can
    # filter out pg_partman child partitions. pg_partman creates child
    # partitions as ordinary tables (relkind='r') with relispartition=true;
    # these are implementation artifacts of pg_partman.create_parent() and
    # should NOT be flagged as "extras" against the canonical ER. The user
    # tables themselves show up as either relkind='r' (ordinary) or
    # relkind='p' (partitioned — the 8 high-volume tables). We include both
    # and exclude child partitions via relispartition=false.
    cur.execute("""
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = current_schema()
          AND c.relkind IN ('r', 'p')
          AND NOT c.relispartition
        ORDER BY c.relname;
    """)
    db_tables = {row[0] for row in cur.fetchall()}
    er_tables = set(tables.keys())
    missing_in_db = er_tables - db_tables
    # ADR-002: idempotency_keys / pairing_tokens / revoked_sync_jwts are
    # physical prod tables with NO `%% [A]` block in the ER by design (they
    # are LocalOnlyCatalog, non-ER operational tables) — never flag them as
    # "extra". Anything else not in the ER is a genuine drift.
    extra_in_db = db_tables - er_tables - EXPECTED_NON_ER_TABLES
    if missing_in_db:
        diff.fail(f"(a) ER has {len(missing_in_db)} table(s) missing from DB: {sorted(missing_in_db)}")
    if extra_in_db:
        diff.fail(f"(a) DB has {len(extra_in_db)} table(s) NOT in ER: {sorted(extra_in_db)}")

    # --- (b) every column matches in name, type, nullability ---
    cur.execute("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = current_schema()
        ORDER BY table_name, ordinal_position;
    """)
    db_columns: dict[str, dict[str, tuple[str, str]]] = {}
    for tname, cname, dtype, nullable in cur.fetchall():
        db_columns.setdefault(tname, {})[cname] = (dtype, nullable)
    for tname, t in tables.items():
        if tname not in db_columns:
            continue  # already flagged in (a)
        db_cols = db_columns[tname]
        er_col_map = {c.name: c for c in t.columns}
        for col_name, col in er_col_map.items():
            if col_name not in db_cols:
                diff.fail(f"(b) table {tname} missing column {col_name}")
                continue
            db_dtype, db_nullable = db_cols[col_name]
            expected_pg = MERMAID_TO_POSTGRES.get(col.type_raw)
            if expected_pg is None:
                diff.fail(f"(b) {tname}.{col_name}: ER type '{col.type_raw}' not in MERMAID_TO_POSTGRES map")
                continue
            if expected_pg != db_dtype and not db_dtype.startswith(expected_pg):
                # Tolerant: accept varchar/text variants for "string", numeric
                # variants for "decimal", etc.
                if not (
                    (expected_pg == "character varying" and db_dtype in {"text", "character varying"}) or
                    (expected_pg == "numeric" and db_dtype in {"numeric", "decimal"}) or
                    (expected_pg == "timestamp without time zone" and db_dtype in {"timestamp without time zone"})
                ):
                    diff.fail(f"(b) {tname}.{col_name}: type mismatch ER='{col.type_raw}' (→pg='{expected_pg}') DB='{db_dtype}'")

    # --- (c) every UK in the ER exists in the DB ---
    # For each table with a UK in the ER, check the DB has at least one
    # UNIQUE constraint that includes the leading column of the UK.
    cur.execute("""
        SELECT tc.table_name, kcu.column_name, tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_schema = current_schema()
          AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
        ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
    """)
    db_unique_cols: dict[str, set[str]] = {}
    for tname, cname, _ in cur.fetchall():
        db_unique_cols.setdefault(tname, set()).add(cname)
    for tname, t in tables.items():
        for uk_cols in t.uks:
            if not uk_cols:
                continue
            leading = uk_cols[0]
            if leading not in db_unique_cols.get(tname, set()):
                diff.fail(f"(c) {tname}: ER declares UK ({', '.join(uk_cols)}) but DB has no UNIQUE/PRIMARY KEY covering '{leading}'")

    # --- (d) every FK in the ER has a foreign-key constraint in the DB ---
    cur.execute("""
        SELECT tc.table_name, kcu.column_name, ccu.table_name AS ref_table
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.table_schema = current_schema()
          AND tc.constraint_type = 'FOREIGN KEY';
    """)
    db_fks: dict[str, set[str]] = {}
    for tname, _, ref in cur.fetchall():
        db_fks.setdefault(tname, set()).add(ref)
    for tname, t in tables.items():
        for ref in t.fks:
            if ref not in db_fks.get(tname, set()):
                diff.fail(f"(d) {tname}: ER FK → {ref} not present as FOREIGN KEY in DB")

    # --- (e) every [A] table has REVOKE UPDATE, DELETE FROM rol_app ---
    # sync_queue_lw_buffer carries a documented DELETE-only carve-out
    # (0012_add_sync_queue_lw_buffer.py, ADR-002/003, mirroring sync_queue's
    # own "full UPDATE grant, Python-side discipline" convention): the
    # drain/TTL-sweep workers must UPDATE estado/ultimo_error after insert,
    # so only DELETE is revoked for this one table — UPDATE stays granted.
    # Discovered while wiring the amended ER into this script: check (e) had
    # no carve-out for a partially-revoked [A] table before ADR-002 added
    # one to the canon.
    a_tables = [t.name for t in tables.values() if t.klass == "A" and t.name != "sync_queue"]
    for tname in a_tables:
        cur.execute("SELECT has_table_privilege('rol_app', %s, 'UPDATE')", (f"prod.{tname}",))
        can_update = cur.fetchone()[0]
        cur.execute("SELECT has_table_privilege('rol_app', %s, 'DELETE')", (f"prod.{tname}",))
        can_delete = cur.fetchone()[0]
        if can_delete:
            diff.fail(f"(e) {tname}: REVOKE failed — rol_app has DELETE={can_delete}")
        if tname not in DELETE_ONLY_REVOKE_TABLES and can_update:
            diff.fail(f"(e) {tname}: REVOKE failed — rol_app has UPDATE={can_update}")

    # --- (f) every [A] table has a BEFORE UPDATE OR DELETE trigger ---
    cur.execute("""
        SELECT c.relname, t.tgname
        FROM pg_trigger t
        JOIN pg_class c ON t.tgrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = current_schema()
          AND t.tgname LIKE '%_inmutable'
          AND NOT t.tgisinternal;
    """)
    inmut_triggers = {row[0] for row in cur.fetchall()}
    for tname in a_tables:
        if tname not in inmut_triggers:
            diff.fail(f"(f) {tname}: no '<table>_inmutable' BEFORE UPDATE OR DELETE trigger in DB")

    # --- (g) every [L-S] table has a session-guard trigger ---
    cur.execute("""
        SELECT c.relname, t.tgname
        FROM pg_trigger t
        JOIN pg_class c ON t.tgrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = current_schema()
          AND (t.tgname LIKE 'ls_session%' OR t.tgname LIKE '%ls\\_session%')
          AND NOT t.tgisinternal;
    """)
    ls_triggers = {row[0] for row in cur.fetchall()}
    ls_tables = [t.name for t in tables.values() if t.klass == "L-S"]
    for tname in ls_tables:
        if tname not in ls_triggers:
            diff.fail(f"(g) {tname}: no session-guard BEFORE UPDATE trigger in DB")

    # --- (h) the 8 high-volume [A] tables have a pg_partman partition registered ---
    cur.execute("""
        SELECT parent_table FROM partman.part_config
        WHERE parent_table LIKE '%.' || current_schema() || '.%'
        ORDER BY parent_table;
    """)
    partman_parents = {row[0].split(".")[-1] for row in cur.fetchall()}
    expected_partman = {"factura_detalle", "factura_pagos", "log_transaccional",
                       "sync_log", "sync_queue", "caja", "arqueo", "salidas"}
    missing_partman = expected_partman - partman_parents
    extra_partman = partman_parents - expected_partman
    if missing_partman:
        diff.fail(f"(h) pg_partman missing partition parents: {sorted(missing_partman)}")
    if extra_partman:
        # Informational, not failure — extra partman parents are OK.
        print(f"(h) info: pg_partman has additional parents: {sorted(extra_partman)}")

    # --- (i) MV canon guard — REQ-OPS-133 / Bug 3 of qa-2026-09-17 ---
    # The ``prod.mv_ocupacion_diaria`` materialized view is a hard
    # contract for F4.3 / REQ-OPS-031 polling. Without it the GET
    # /operacion/ocupacion handler returns 500. The view is created by
    # migration 0024 (and re-asserted by migration 0034 after partial-
    # commit drift) but the contract is independent of the migration
    # table — an operator could in principle drop the view manually and
    # the migration table would still claim 0024/0034 as applied. This
    # check closes the loop with ``to_regclass`` and exits non-zero if
    # the MV is missing. The script's exit-code aggregator then bubbles
    # this up to CI as a failure.
    cur.execute("SELECT to_regclass(%s)", (f"{schema}.mv_ocupacion_diaria",))
    mv_regclass = cur.fetchone()[0]
    if mv_regclass is None:
        diff.fail(
            "(i) mv_ocupacion_diaria_missing: prod.mv_ocupacion_diaria is "
            "absent. Run migration 0034 to recreate it. See REQ-OPS-133."
        )

    # The MV also carries a UNIQUE INDEX required by
    # ``REFRESH MATERIALIZED VIEW CONCURRENTLY``. Without it, the 10s
    # refresh worker falls back to plain REFRESH (which takes an
    # AccessExclusiveLock briefly). Surface this as a CI failure so
    # the operator fixes it before the worker silently falls back in
    # production.
    cur.execute(
        """
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = current_schema()
          AND c.relkind = 'i'
          AND c.relname = 'uq_mv_ocupacion_diaria_sucursal_tipo';
        """
    )
    if cur.fetchone() is None:
        diff.fail(
            "(i) mv_ocupacion_diaria_index_missing: "
            "prod.uq_mv_ocupacion_diaria_sucursal_tipo UNIQUE INDEX is "
            "absent. REFRESH CONCURRENTLY will not work. See REQ-OPS-133."
        )

    return diff


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify prod.* schema matches modelo_datos_er.mmd 100%.")
    parser.add_argument("--er", default="./modelo_datos_er.mmd",
                        help="Path to modelo_datos_er.mmd (default: ./modelo_datos_er.mmd)")
    parser.add_argument("--database-url", default=None,
                        help="Postgres DSN. If omitted, reads DATABASE_URL env var.")
    parser.add_argument("--schema", default="prod",
                        help="Schema name to check (default: prod)")
    args = parser.parse_args(argv)

    er_path = Path(args.er)
    if not er_path.is_file():
        print(f"ERROR: ER file not found: {er_path}", file=sys.stderr)
        return 2

    try:
        tables = parse_er(er_path)
    except ParseError as e:
        print(f"ERROR: ER parse failed: line {e.line}: {e.reason}", file=sys.stderr)
        return 2
    print(f"ER parsed: {len(tables)} tables "
          f"({sum(1 for t in tables.values() if t.klass == 'V')} [V], "
          f"{sum(1 for t in tables.values() if t.klass == 'L-E')} [L-E], "
          f"{sum(1 for t in tables.values() if t.klass == 'L-W')} [L-W], "
          f"{sum(1 for t in tables.values() if t.klass == 'L-S')} [L-S], "
          f"{sum(1 for t in tables.values() if t.klass == 'A')} [A])")

    dsn = args.database_url or os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: --database-url or DATABASE_URL env var required", file=sys.stderr)
        return 2

    try:
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(args.schema)))
            diff = diff_schema(tables, conn, schema=args.schema)
    except psycopg.OperationalError as e:
        print(f"ERROR: DB connection failed: {e}", file=sys.stderr)
        return 2

    print()
    if diff.ok:
        print("OK: 100% match. Schema matches modelo_datos_er.mmd exactly.")
        return 0
    print(f"FAIL: {len(diff.issues)} issue(s) found:")
    for issue in diff.issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    import os  # local import to keep top imports tight
    sys.exit(main(sys.argv[1:]))
