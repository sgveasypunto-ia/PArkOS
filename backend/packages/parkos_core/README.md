# parkos-core

Shared library for the Parkos multi-tenant parking-lot management system.

This package provides:

- SQLAlchemy 2.0 ORM models for the 49 canonical tables
- Alembic migrations (currently `0001_initial_schema.py`)
- Pydantic v2 schemas for API I/O
- Authentication helpers (3-issuer JWT, bcrypt password hashing)
- Sync + DIAN infrastructure

## Layout

```
parkos_core/
├── pyproject.toml
├── src/parkos_core/
│   └── __init__.py
└── migrations/
    ├── env.py
    ├── script.py.mako
    ├── versions/
    │   ├── 0001_initial_schema.py  # the canonical 49-table schema
    │   └── README.md
    └── ...
```

## Quickstart

```bash
# Install (from the workspace root: backend/)
uv sync

# Run migrations against a local Postgres
export DATABASE_URL=postgresql://parkos:parkos@localhost:5432/parkos
uv run python -m alembic upgrade head

# Or apply via the apply script (uses testcontainers Postgres)
uv run python backend/scripts/apply_migration.py
```

## Constraints

- Python 3.13+
- PostgreSQL 16+
- No physical DELETE at any layer (API, ORM, DB) — corrections are
  expressed as new rows via close+insert (`[V]`) or compensating workflow
  rows (`[A]`).
- Hash chain on `log_transaccional` and `revocacion_factura` is
  per-`uuid_sucursal`; preserve on sync.

See `openspec/changes/create-49-table-apis/` for the canonical spec,
design, and tasks.