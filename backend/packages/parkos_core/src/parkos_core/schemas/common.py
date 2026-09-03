"""Shared Pydantic v2 base classes (design §6).

- :class:`_Base` — strict ORM mapper: ``from_attributes=True``, ``extra='forbid'``.
- :class:`FilterBase` — base for ``Filter`` query models (all fields optional).
- :class:`ReadListBase` — ``{items: list[T], next_cursor: str | None}`` shape,
  parameterized by ``T`` so each table's ``ReadList`` can narrow ``items``.

Convention: ``extra='forbid'`` so Pydantic rejects unknown fields at the
edge (C-3 in bi-temporal-crud.md). Clients cannot smuggle versioning columns
(``vigente_desde``, ``vigente_hasta``, ``estado``) — they aren't in the
``Create`` schema and the strict-extra would 422 if attempted.
"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


_T = TypeVar("_T")


class _Base(BaseModel):
    """Strict ORM mapper. ``from_attributes=True`` for ``model_validate(row)``.
    ``extra='forbid'`` rejects unknown fields at the API edge.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FilterBase(_Base):
    """All-optional filter model. Subclass per table to add fields."""

    pass


class ReadListBase(BaseModel, Generic[_T]):
    """Cursor-paginated list response. ``next_cursor=None`` means EOF."""

    items: list[_T]
    next_cursor: str | None = None


__all__ = ["_Base", "FilterBase", "ReadListBase"]