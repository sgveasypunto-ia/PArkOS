"""tests/migrations/conftest.py — guarantees migrations are applied before
any test in this package runs.

Every test module here touches ``prod.*`` tables directly (raw ``psycopg``
against ``pg_dsn``, or SQLAlchemy against ``pg_engine``) without requesting
the ``alembic_upgrade`` fixture itself. Historically that worked by
accident: some other, earlier-collected test elsewhere in the session
happened to request ``alembic_upgrade`` first, and since it (and the
underlying ``postgres_container``) are session-scoped, the migration
stayed applied for the rest of the run. Run this package in isolation, or
reorder collection, and every test here fails with
``psycopg.errors.UndefinedTable`` because the schema was never created.

This autouse fixture makes the dependency explicit and local instead of
relying on collection order across unrelated files.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _migrations_applied(alembic_upgrade: None) -> None:
    """Force ``alembic upgrade head`` before any test in this package runs."""
