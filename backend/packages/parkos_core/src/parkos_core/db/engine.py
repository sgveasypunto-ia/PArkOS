"""Async SQLAlchemy engine + session factory (design §3 environment).

Reads ``DATABASE_URL`` from the environment. The URL is resolved lazily
so importing this module does NOT require ``DATABASE_URL`` to be set
(useful for unit tests that exercise schemas/repos without a live DB).

Production startup (uvicorn entrypoint) MUST set ``DATABASE_URL`` before
the first request lands; the lazy resolver raises ``RuntimeError`` at
that point.
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any as _Any

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def _resolve_url() -> str:
    """Return the async URL for the application runtime."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL env var is required for parkos_core application "
            "runtime (e.g. postgresql+asyncpg://parkos:parkos@db:5432/parkos)."
        )
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


# Lazy engine — created on first access. Lets the package import without
# DATABASE_URL while still failing loudly at runtime if the URL is missing.
_engine = None
_sessionmaker: _Any = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _resolve_url(),
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
    return _engine


def _get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            _get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


# Compatibility shims — the type annotations point at the lazy creators.
# Existing callers (router code, deps, etc.) reference these names directly.
class _LazyEngine:
    """Proxy that defers engine creation to first attribute access."""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)


class _LazySessionmaker:
    """Proxy that defers sessionmaker creation to first call."""

    def __call__(self, *args, **kwargs):
        return _get_sessionmaker()(*args, **kwargs)


engine = _LazyEngine()
sessionmaker = _LazySessionmaker()
# Alias used by the sync workers (PR9b — sync_cloud.py / sync_sucursal.py
# expect ``SessionLocal`` to mirror the SQLAlchemy sessionmaker pattern).
SessionLocal = _LazySessionmaker()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields a fresh :class:`AsyncSession` per request."""
    sm = _get_sessionmaker()
    async with sm() as session:
        yield session


__all__ = ["engine", "sessionmaker", "get_session"]