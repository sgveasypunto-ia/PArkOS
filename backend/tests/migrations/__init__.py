"""Migration-level DB tests (PR1c).

Each module here runs against the testcontainers Postgres with the full
``0001_initial_schema`` already applied by the ``alembic_upgrade`` fixture
in ``tests/conftest.py``. Tests use raw psycopg (v3) SQL to exercise the
DB-layer enforcement directly — the ORM models for most [A] / [L-S]
tables are not yet shipped (PR2+), so going through SQL keeps the suite
robust against future ORM additions.
"""