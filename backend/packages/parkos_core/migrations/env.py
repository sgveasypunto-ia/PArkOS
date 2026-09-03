"""Alembic env.py — async + sync fallback for parkos-core migrations.

Reads ``DATABASE_URL`` from the environment. The migration runtime uses the
sync driver (``psycopg2``) for Alembic's offline/online modes; the
application runtime uses ``asyncpg`` (``postgresql+asyncpg``).

Multi-schema aware: ``include_schemas=True`` is REQUIRED because every
parkos table lives under ``prod.*``.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the package is importable for env.py consumers (autogenerate).
SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Configure logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Parkos does NOT use SQLAlchemy declarative metadata for autogenerate;
# the canonical schema is hand-built in 0001_initial_schema.py to match
# ``modelo_datos_er.mmd`` exactly. We declare ``target_metadata = None``
# to prevent any drift-induced autogenerate from polluting the schema.
target_metadata = None


def _resolve_url() -> str:
    """Read DATABASE_URL from env. Translate ``postgresql+asyncpg`` to
    ``postgresql+psycopg2`` for Alembic's sync runtime."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL env var is required for Alembic "
            "(e.g. postgresql://parkos:parkos@localhost:5432/parkos)."
        )
    # Alembic is sync-only — translate any asyncpg URLs to psycopg2.
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]
    elif url.startswith("postgresql+psycopg://"):
        url = "postgresql+psycopg2://" + url[len("postgresql+psycopg://"):]
    elif not url.startswith(("postgresql://", "postgresql+psycopg2://")):
        # Try plain postgresql:// as a passthrough; otherwise raise.
        if not url.startswith("postgres://"):
            raise RuntimeError(
                f"DATABASE_URL must use postgresql:// or postgresql+psycopg2:// "
                f"(got: {url[:40]}...)."
            )
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout/file."""
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the live database."""
    # Override sqlalchemy.url from the env so secrets never leak into alembic.ini.
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _resolve_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            render_as_batch=False,  # PostgreSQL only — DO NOT use SQLite batch mode.
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()