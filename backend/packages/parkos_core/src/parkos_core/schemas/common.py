"""Shared Pydantic v2 base classes (design §6).

- :class:`_Base` — strict ORM mapper: ``from_attributes=True``, ``extra='forbid'``.
  Adds a model-level UTC datetime serializer so every ``datetime`` field
  in every read model that inherits from ``_Base`` is emitted with the
  ``Z`` suffix (or its existing offset, if the column is already
  ``TIMESTAMPTZ``). This makes the AGENTS.md §Sync "Naive-UTC convention"
  explicit on the wire and prevents the operator-reported
  ``new Date(naiveString).getTime()`` ECMAScript local-parse bug that
  bit ``/cupos`` on 2026-10-11.
- :class:`FilterBase` — base for ``Filter`` query models (all fields optional).
- :class:`ReadListBase` — ``{items: list[T], next_cursor: str | None}`` shape,
  parameterized by ``T`` so each table's ``ReadList`` can narrow ``items``.

Convention: ``extra='forbid'`` so Pydantic rejects unknown fields at the
edge (C-3 in bi-temporal-crud.md). Clients cannot smuggle versioning columns
(``vigente_desde``, ``vigente_hasta``, ``estado``) — they aren't in the
``Create`` schema and the strict-extra would 422 if attempted.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_serializer


_T = TypeVar("_T")


def _serialize_utc(value: datetime) -> str:
    """Project-wide datetime serializer.

    Naive datetimes (the case for every ``DateTime(timezone=False)``
    column in the schema) get a trailing ``Z`` so the consumer knows
    "this is UTC, not local". Aware datetimes keep whatever offset
    they carry — we never normalize to UTC server-side because the
    column shape already encodes the convention. Returning ``str``
    (not ``datetime``) is what the JSON wire format expects anyway,
    so the consumer is now defensible against the
    ``new Date(naiveString).getTime()`` ECMAScript local-parse bug
    that bit the operator on 2026-10-11 in
    :file:`web_admin/src/lib/datetimeTz.ts`.
    """
    if value.tzinfo is None:
        return value.isoformat(timespec="seconds") + "Z"
    return value.isoformat(timespec="seconds")


class _Base(BaseModel):
    """Strict ORM mapper. ``from_attributes=True`` for ``model_validate(row)``.
    ``extra='forbid'`` rejects unknown fields at the API edge.

    The :meth:`_serialize_with_utc` hook below is the single place
    the wire contract ``UTC suffix on every datetime`` is enforced —
    no per-schema work needed. The hook walks the model's
    ``__dict__`` (raw Python attributes, BEFORE Pydantic's default
    serialization turns them into ISO strings) and converts every
    ``datetime`` to the canonical UTC form, then delegates the
    rest of the dump to Pydantic's defaults. ``mode='plain'`` is
    required because ``mode='wrap'`` would call ``handler(self)``
    first — at that point the datetimes are already strings, so
    ``isinstance(value, datetime)`` would never be true and the
    suffix would silently be dropped.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @model_serializer(mode="wrap")
    def _serialize_with_utc(
        self, handler: Any
    ) -> dict[str, Any]:  # type: ignore[override]
        # ``mode='wrap'`` lets us call Pydantic's default serializer
        # (which still emits naive datetimes as bare ISO strings) and
        # post-process the result. We then walk ``self.__dict__`` (the
        # raw Python attribute values, BEFORE Pydantic turned them
        # into strings) to find every naive datetime and append the
        # canonical ``Z`` suffix on the corresponding string. The
        # advantage over ``mode='plain'`` is that we keep
        # ``@computed_field`` and any future Pydantic-driven
        # serializations (enums, ``Decimal`` stringification, etc.)
        # without having to re-implement them in this hook.
        data = handler(self)
        for key, raw_value in self.__dict__.items():
            if (
                isinstance(raw_value, datetime)
                and raw_value.tzinfo is None
            ):
                serialized = data.get(key)
                if isinstance(serialized, str):
                    data[key] = serialized + "Z"
        return data


class FilterBase(_Base):
    """All-optional filter model. Subclass per table to add fields."""

    pass


class ReadListBase(BaseModel, Generic[_T]):
    """Cursor-paginated list response. ``next_cursor=None`` means EOF."""

    items: list[_T]
    next_cursor: str | None = None


__all__ = ["_Base", "FilterBase", "ReadListBase"]