"""Idempotently seed ``prod.alert_types`` (T-PR8-003, design.md §2 Issue #6).

Standalone operational script — direct Postgres connection (via ``psycopg``),
NOT the admin HTTP API (unlike ``seed_catalogs.py``): ``alert_types`` is
out-of-catalog deploy-time reference data, not an operator-editable catalog,
so there is no ``/api/v1/catalogos/*`` endpoint for it. Idempotency shape
mirrors ``seed_catalogs.py``'s general convention (``ON CONFLICT DO
NOTHING``, safe to re-run); the actual literal precedent for this exact
``psycopg`` + ``ON CONFLICT`` pattern is
``backend/scripts/replicate_catalogs_to_branch.py`` /
``0002_seed_permisos_canonicos.py``, since ``seed_catalogs.py`` itself goes
through the HTTP admin API and shows no ``ON CONFLICT`` clause directly.

Run identically against BOTH the cloud DB and every branch DB — there is no
role/deploy-target distinction (design.md §2 Issue #6: "seeded idempotently
on both cloud and branch"). The same 8 rows also ship inline in this
table's own migration (``0013_add_alert_types.py``); this script exists for
operational re-seeding outside the alembic path (e.g. a branch DB
provisioned from a snapshot that predates this migration).

Usage:
    uv run python infra/scripts/seed_alert_types.py \\
        --dsn postgresql://parkos:parkos@localhost:5432/parkos
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg

# (tipo_alerta, descripcion, severity) — MUST stay identical to
# ``0013_add_alert_types.py``'s ``_SEED_ROWS``. No row names the
# third-party DIAN provider (addendum #5, REQ-OPS-016,
# ``tests/unit/test_alert_types_seed.py``).
SEED_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "hash_chain_anomaly",
        "Hash chain integrity break detected by the chain verifier",
        "critical",
    ),
    (
        "dian_rechazada",
        "DIAN provider rejected the submitted electronic-invoicing document",
        "warning",
    ),
    (
        "dian_timeout",
        "DIAN provider request timed out",
        "critical",
    ),
    (
        "dian_error",
        "Generic DIAN provider error on a terminal poll outcome",
        "warning",
    ),
    (
        "branch_offline_reauth_required",
        "Branch JWT requires re-authentication after an extended offline period",
        "warning",
    ),
    (
        "orphan_workflow_chain",
        "Dependency-buffer TTL sweep found an unresolved parent wait",
        "warning",
    ),
    (
        "fe_provider_error",
        "DIAN provider exchange exhausted its retry budget",
        "critical",
    ),
    (
        "fe_numbering_exhausted",
        "Authorized invoice numbering range (resolucion_facturacion) exhausted",
        "critical",
    ),
)


def seed_alert_types(dsn: str) -> int:
    """INSERT every row in :data:`SEED_ROWS`, idempotently. Returns rows seen."""
    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for tipo_alerta, descripcion, severity in SEED_ROWS:
                cur.execute(
                    """
                    INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tipo_alerta) DO NOTHING
                    """,
                    (tipo_alerta, descripcion, severity),
                )
            cur.execute("SELECT count(*) FROM prod.alert_types")
            return cur.fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL", "postgresql://parkos:parkos@localhost:5432/parkos"),
        help="Postgres DSN (default: $DATABASE_URL or the local dev default).",
    )
    args = parser.parse_args()

    print(f"== Seeding {len(SEED_ROWS)} prod.alert_types rows ==")
    total = seed_alert_types(args.dsn)
    print(f"Total rows in prod.alert_types: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
