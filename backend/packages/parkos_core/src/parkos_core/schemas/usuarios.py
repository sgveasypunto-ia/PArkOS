"""Pydantic v2 schemas for HU-F1.15 ``GET /api/v1/usuarios/{uuid}/login``.

Three schemas:

* :class:`LoginHistoricoQueryParams` -- path + query params for the
  handler. Inherits ``extra='forbid'`` from :class:`_Base`
  (Layer 4 defense, blocks client smuggling of ``actor_uuid``,
  ``computed_at``, ``cache_key``, ``activo``).
* :class:`LoginIntentoItem` -- single login attempt row in the
  response. Mirrors the relevant ``prod.login`` columns (5 business
  columns per ``models/L_S/login.py:33-74``). ``estado`` is a
  :data:`Literal["exitoso", "fallido", "cerrado"]` (DEC-LOGIN-10 --
  REAL [L-S] lifecycle value, NEVER synthetic boolean ``activo``).
* :class:`LoginHistoricoListResponse` -- ``{items, next_cursor}``
  envelope per ``api/router_factory.py:227`` (DEC-LOGIN-07). Forward-
  compatible with Parte 2 (HU-F16.1/F16.5): no ``activo``, no
  ``count``, no ``total``, no ``has_more``.

Layer 4: ``extra='forbid'`` blocks unknown response fields so the
client cannot inject synthetic columns server-side.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import _Base

# DEC-LOGIN-10: REAL [L-S] lifecycle value, NEVER synthetic boolean ``activo``.
# The 3 values mirror ``auth.py:239-246`` (fallido), ``auth.py:260-266``
# (exitoso), ``auth.py:352-393`` (cerrado).
ESTADO_LOGIN_LITERAL: tuple[str, ...] = ("exitoso", "fallido", "cerrado")
EstadoLogin = Literal["exitoso", "fallido", "cerrado"]


class LoginHistoricoQueryParams(_Base):
    """Query params for ``GET /api/v1/usuarios/{uuid}/login``.

    The ``uuid`` is the path param (validated by FastAPI ``uuid``
    converter + Pydantic UUID type). ``limit`` is bounded to
    ``1..100`` per DEC-LOGIN-04 (default 10). ``cursor`` is the
    opaque base64 JSON cursor from a previous page (``None`` for
    first page).

    Layer 4 (extra='forbid'): a client smuggling an unknown field
    (e.g. ``actor_uuid``, ``computed_at``, ``cache_key``, ``activo``)
    triggers ``ValidationError`` and FastAPI returns ``422``.
    """

    uuid: uuid_lib.UUID
    limit: int = Field(default=10, ge=1, le=100)
    cursor: str | None = None


class LoginIntentoItem(_Base):
    """Single login attempt row in the ``LoginHistoricoListResponse``.

    Mirrors 5 business columns of ``prod.login`` (per
    ``models/L_S/login.py:33-74``):

    * ``uuid`` -- composite PK with ``fecha_retencion_hasta`` (server-
      defaulted, omitted from response).
    * ``timestamp_evento`` -- naive UTC, NOT nullable (the [L-S]
      session lifecycle stamps every row).
    * ``timestamp_cierre`` -- naive UTC, nullable for OPEN sessions.
    * ``estado`` -- ``Literal["exitoso", "fallido", "cerrado"]``
      (DEC-LOGIN-10). NEVER null (the lifecycle always stamps a value).
    * ``uuid_sucursal`` -- FK ``prod.sucursal.uuid``, nullable.

    Layer 4 (extra='forbid'): blocks client smuggling of unknown
    response fields.
    """

    uuid: uuid_lib.UUID
    timestamp_evento: datetime
    timestamp_cierre: datetime | None
    estado: EstadoLogin
    uuid_sucursal: uuid_lib.UUID | None


class LoginHistoricoListResponse(_Base):
    """Cursor-paginated list response per DEC-LOGIN-07.

    Envelope: ``{items: list[LoginIntentoItem], next_cursor: str | None}``.
    Forward-compatible with Parte 2 (HU-F16.1/F16.5): no ``activo``,
    no ``count``, no ``total``, no ``has_more`` -- Parte 2 may
    extend the dedicated router without breaking this contract.
    """

    items: list[LoginIntentoItem]
    next_cursor: str | None = None


__all__ = [
    "ESTADO_LOGIN_LITERAL",
    "EstadoLogin",
    "LoginHistoricoListResponse",
    "LoginHistoricoQueryParams",
    "LoginIntentoItem",
]
