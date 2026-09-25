"""Pydantic v2 schemas for the Caja domain (PR7, T-PR7-08).

Covers 3 tables in ``prod``:

- :class:`Caja` — ``[A]`` cash-drawer snapshot (composite PK
  ``uuid + fecha_retencion_hasta``, monthly ``pg_partman`` partition).
- :class:`Arqueo` — ``[A]`` cash-count event (composite PK
  ``uuid + fecha_retencion_hasta``, monthly ``pg_partman`` partition).
- :class:`Sesion` — ``[L-S]`` cash session, NO versioning columns.
  Open on shift start, close on shift end. Writes MUST go through
  ``repo.session_cycle.open_session`` / ``close_session_with_log``
  (REQ-40, REQ-41); the ``ls_session_guard`` trigger blocks any UPDATE
  without a co-transactional ``log_transaccional`` row (SC-40, SC-42).

Append-only at write time (design §4.5, §4.7): every table here is
either ``[A]`` (REVOKE UPDATE/DELETE + BEFORE UPDATE OR DELETE trigger)
or ``[L-S]`` (UPDATE allowed only via the session-cycle helpers). The
``Update`` schemas exist to satisfy the
``Read / Create / Update / Filter / ReadList`` quintet per T-PR7-08; the
router layer does NOT expose PATCH routes for ``caja`` / ``arqueo``
and only mounts ``PUT /sesion/{uuid}/cerrar`` for :class:`SesionUpdate`.

``SesionUpdate`` narrows the writable surface to the four fields the
``close_session_with_log`` helper mutates:

- ``valor_inicial_efectivo``, ``valor_inicial_datafono`` (corrections to
  the initial drawer counts recorded at open time)
- ``timestamp_cierre``, ``uuid_usuario_cierre`` (set atomically at close)

Server-assigned ``uuid_sucursal`` / ``uuid_usuario`` /
``timestamp_apertura`` are intentionally excluded from ``Update`` —
they are fixed at ``open_session`` time and never change afterwards.
``extra='forbid'`` (from :class:`_Base`) is the T-PR4-08-style
fast-fail assertion: any attempt to PATCH those fields returns
``ValidationError`` (HTTP 422) before the request hits the router.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from .common import FilterBase, ReadListBase, _Base

# ---------------------------------------------------------------------------
# Caja ([A] cash-drawer snapshot, REQ-26-A-CAJA)
# ---------------------------------------------------------------------------


class CajaRead(_Base):
    """Read-back for ``prod.caja`` (composite PK; monthly partitioned).

    The cash + datafono balances are recorded at sesion close; the
    reverso pattern (insert a compensating ``caja`` row with negative
    deltas) handles corrections. There is no UPDATE path on this table.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    valor_efectivo: Decimal | None
    valor_datafono: Decimal | None


class CajaCreate(_Base):
    """INSERT payload for ``prod.caja``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    valor_efectivo: Decimal | None = None
    valor_datafono: Decimal | None = None


class CajaUpdate(_Base):
    """[A] UPDATE payload — append-only, REVOKE UPDATE on the DB.

    Defined for quintet completeness; no route mounts it. Corrections
    are expressed as new ``caja`` rows with opposite deltas.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    valor_efectivo: Decimal | None = None
    valor_datafono: Decimal | None = None


class CajaFilter(FilterBase):
    """Query filter for ``prod.caja``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    created_at__gte: datetime | None = None
    created_at__lte: datetime | None = None


class CajaReadList(ReadListBase[CajaRead]):
    """Cursor-paginated list of :class:`CajaRead` items."""


# ---------------------------------------------------------------------------
# Arqueo ([A] cash-count event, REQ-26-A-ARQUEO)
# ---------------------------------------------------------------------------


class ArqueoRead(_Base):
    """Read-back for ``prod.arqueo`` (composite PK; monthly partitioned).

    Expected vs reported balances per payment method (cash + datafono).
    Corrections are compensating rows; no UPDATE path on this table.
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    fecha_retencion_hasta: date
    uuid_sucursal: uuid_lib.UUID | None
    uuid_tipo_arqueo: uuid_lib.UUID | None
    uuid_sesion: uuid_lib.UUID | None
    valor_efectivo_esperado: Decimal | None
    valor_datafono_esperado: Decimal | None
    valor_efectivo_reportado: Decimal | None
    valor_datafono_reportado: Decimal | None


class ArqueoCreate(_Base):
    """INSERT payload for ``prod.arqueo``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_arqueo: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    valor_efectivo_esperado: Decimal | None = None
    valor_datafono_esperado: Decimal | None = None
    valor_efectivo_reportado: Decimal | None = None
    valor_datafono_reportado: Decimal | None = None


class ArqueoUpdate(_Base):
    """[A] UPDATE payload — append-only, REVOKE UPDATE on the DB.

    Defined for quintet completeness; no route mounts it.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_arqueo: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    valor_efectivo_esperado: Decimal | None = None
    valor_datafono_esperado: Decimal | None = None
    valor_efectivo_reportado: Decimal | None = None
    valor_datafono_reportado: Decimal | None = None


class ArqueoFilter(FilterBase):
    """Query filter for ``prod.arqueo``."""

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_tipo_arqueo: uuid_lib.UUID | None = None
    uuid_sesion: uuid_lib.UUID | None = None
    created_at__gte: datetime | None = None
    created_at__lte: datetime | None = None


class ArqueoReadList(ReadListBase[ArqueoRead]):
    """Cursor-paginated list of :class:`ArqueoRead` items."""


# ---------------------------------------------------------------------------
# Sesion ([L-S] cash session, REQ-40 / REQ-41 / SC-40 / SC-42)
# ---------------------------------------------------------------------------


class SesionRead(_Base):
    """Read-back for ``prod.sesion`` (single PK, [L-S], NO versioning).

    The ``open_session`` helper INSERTs with ``timestamp_apertura`` +
    initial cash; ``close_session_with_log`` UPDATEs with
    ``timestamp_cierre`` + ``uuid_usuario_cierre`` in the SAME
    transaction as a ``log_transaccional`` row (the
    ``ls_session_guard`` trigger enforces this, SC-40).
    """

    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    valor_inicial_efectivo: Decimal | None
    valor_inicial_datafono: Decimal | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    timestamp_apertura: datetime | None
    timestamp_cierre: datetime | None
    uuid_usuario_cierre: uuid_lib.UUID | None


class SesionOpenResponse(SesionRead):
    """Response for ``POST /caja-sesion/sesiones`` (open) and ``PUT
    /caja-sesion/sesion/{uuid}/cerrar`` (close).

    BUGFIX (2026-09-25): the access/refresh token the operator was
    holding at open/close time never carried the ``sesion`` claim (see
    ``auth/tenancy.py::TenantContext`` docstring, which claimed this
    endpoint already set it -- it never did). ``ctx.uuid_sesion`` was
    ALWAYS ``None`` for every operator, which silently broke every
    feature keyed on it (e.g. ``prod.factura_pagos.uuid_sesion``, used
    by the arqueo "esperado" calculation to sum cobros for the turno --
    reimpresiones and ventas de suscripción were being charged for
    real but never counted in arqueo).

    Reissuing a fresh token pair here (with ``sesion`` set on open,
    absent on close) is the only point where the backend knows the
    operator's session identity changed; the frontend MUST replace its
    stored tokens with these on both calls.
    """

    access_token: str
    refresh_token: str
    expires_in: int


class SesionCreate(_Base):
    """INSERT payload for ``prod.sesion`` (REQ-40-S-OPEN).

    Server-assigned ``timestamp_apertura`` is filled by
    ``open_session()`` — clients SHOULD NOT send it. ``extra='forbid'``
    blocks smuggling it; the helper ignores any client value.

    REQ-OPS-135 (Bug 5 of qa-2026-09-17): ``observaciones`` is the
    free-text notes the operator may attach to a sesion open
    (typically the reason for opening, e.g. ``"Apertura turno
    mañana"``). Capped at 500 chars (F3.3 cap). When omitted, the
    column is ``NULL`` and the field is not surfaced into
    ``prod.log_transaccional.datos_nuevos``.
    """

    valor_inicial_efectivo: Decimal | None = None
    valor_inicial_datafono: Decimal | None = None
    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    timestamp_apertura: datetime | None = None
    timestamp_cierre: datetime | None = None
    uuid_usuario_cierre: uuid_lib.UUID | None = None
    observaciones: str | None = Field(default=None, max_length=500)


class SesionUpdate(_Base):
    """[L-S] UPDATE payload — close-time fields only.

    Intentionally NARROW: only the four fields ``close_session_with_log``
    is allowed to mutate are exposed here:

    - ``valor_inicial_efectivo`` / ``valor_inicial_datafono`` — late
      corrections to the initial drawer counts recorded at open time.
    - ``timestamp_cierre`` / ``uuid_usuario_cierre`` — set atomically
      at sesion close.

    Server-fixed fields (``uuid_sucursal``, ``uuid_usuario``,
    ``timestamp_apertura``) are EXCLUDED so a PATCH cannot rewrite the
    identity of an opened sesion. ``extra='forbid'`` makes any attempt
    a 422 at the API edge.
    """

    valor_inicial_efectivo: Decimal | None = None
    valor_inicial_datafono: Decimal | None = None
    timestamp_cierre: datetime | None = None
    uuid_usuario_cierre: uuid_lib.UUID | None = None


class SesionFilter(FilterBase):
    """Query filter for ``prod.sesion``.

    ``timestamp_apertura__gte/lte`` is the natural range for shift
    reports (open sesions in a date window); the ``uuid_usuario_cierre
    IS NULL`` open-sesions case is encoded by the ``abierta`` flag
    computed in the router.
    """

    uuid_sucursal: uuid_lib.UUID | None = None
    uuid_usuario: uuid_lib.UUID | None = None
    timestamp_apertura__gte: datetime | None = None
    timestamp_apertura__lte: datetime | None = None


class SesionReadList(ReadListBase[SesionRead]):
    """Cursor-paginated list of :class:`SesionRead` items."""


# ---------------------------------------------------------------------------
# HU-F1.13 -- V2 endpoints (REQ-OPS-091..097 + REQ-OPS-XR6)
# ---------------------------------------------------------------------------


class ArqueoCreateV2(_Base):
    """HU-F1.13 / REQ-OPS-091: POST /api/v1/caja/arqueo payload (V2).

    Server-derived fields (``uuid_sucursal``, ``uuid_usuario``, ``alerta_uuid``,
    ``alerta_generada``, ``descuadre_pct``, ``created_at``, ``created_by``)
    are NOT exposed here -- the handler computes them. ``extra='forbid'``
    (inherited from :class:`_Base`) blocks client smuggling of those
    columns. The handler enforces ``justificacion`` REQUIRED when
    ``tipo_arqueo.codigo in ('cierre_turno', 'cierre_dia')`` AND
    diferencia != 0 (DEC-ARQUEO-07).
    """

    uuid_tipo_arqueo: uuid_lib.UUID
    uuid_sesion: uuid_lib.UUID | None = None  # None when cierre_dia (DEC-ARQUEO-03)
    valor_efectivo_reportado: Decimal
    valor_datafono_reportado: Decimal
    justificacion: str | None = None  # required for cierre_turno/cierre_dia + diferencia != 0


class ArqueoReadForHandler(_Base):
    """HU-F1.13 / REQ-OPS-091 Scenario 1: POST handler response shape.

    Includes ``alerta_generada`` + ``alerta_uuid`` (Step 10 result) +
    ``descuadre_pct`` (informational only, DEC-ARQUEO-04).
    """

    uuid: uuid_lib.UUID
    uuid_tipo_arqueo: uuid_lib.UUID
    codigo_tipo_arqueo: str
    uuid_sesion: uuid_lib.UUID | None
    valor_efectivo_esperado: Decimal
    valor_datafono_esperado: Decimal
    valor_efectivo_reportado: Decimal
    valor_datafono_reportado: Decimal
    diferencia_efectivo: Decimal
    diferencia_datafono: Decimal
    descuadre_pct: Decimal | None = None
    alerta_generada: bool = False
    alerta_uuid: uuid_lib.UUID | None = None


class ArqueoResumenItem(_Base):
    """HU-F1.13 / REQ-OPS-097: per-sesion row in GET /arqueo/resumen.

    For ``cierre_dia`` aggregate items, ``uuid_sesion`` is ``None``
    (DEC-ARQUEO-03).
    """

    uuid_sesion: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    timestamp_apertura: datetime | None
    timestamp_cierre: datetime | None
    estado: str | None
    valor_efectivo_esperado: Decimal | None
    valor_datafono_esperado: Decimal | None
    valor_efectivo_reportado: Decimal | None
    valor_datafono_reportado: Decimal | None
    uuid_arqueo: uuid_lib.UUID | None


class ArqueoResumenRead(_Base):
    """HU-F1.13 / REQ-OPS-097: GET /arqueo/resumen response.

    ``cierre_dia`` is ``None`` when no cierre_dia arqueo exists for
    the (uuid_sucursal, fecha) pair. ``sesiones`` is ``[]`` for empty
    days (REQ-OPS-097 Scenario 3).
    """

    fecha: date
    uuid_sucursal: uuid_lib.UUID
    sesiones: list[ArqueoResumenItem]
    cierre_dia: ArqueoResumenItem | None = None


class CierreDiarioQueryParams(_Base):
    """HU-F1.13 / REQ-OPS-097: GET /arqueo/resumen query params.

    Both fields are required (the endpoint returns 422 via Pydantic
    when missing). ``extra='forbid'`` blocks client smuggling.
    """

    uuid_sucursal: uuid_lib.UUID
    fecha: date


# ---------------------------------------------------------------------------
# Typed error schemas (Layer 5 -- mapped via HTTPException)
# ---------------------------------------------------------------------------


class TipoArqueoNoEncontradoErrorRead(_Base):
    """V1 404 -- ``prod.tipo_arqueo`` row missing for UUID."""

    error: str = "tipo_arqueo_no_encontrado"
    uuid_tipo_arqueo: uuid_lib.UUID


class SesionNoEncontradaErrorRead(_Base):
    """V4 404 -- ``prod.sesion`` row missing for UUID."""

    error: str = "sesion_no_encontrada"
    uuid_sesion: uuid_lib.UUID


class ToleranciaNoConfiguradaErrorRead(_Base):
    """V3 404 -- no vigente ``prod.configuracion_tolerancias``."""

    error: str = "tolerancia_no_configurada"
    uuid_sucursal: uuid_lib.UUID | None


class SesionYaCerradaErrorRead(_Base):
    """V4 409 -- ``prod.sesion`` has ``timestamp_cierre IS NOT NULL``."""

    error: str = "sesion_ya_cerrada"
    uuid_sesion: uuid_lib.UUID


class CierreDiaNoAceptaSesionErrorRead(_Base):
    """V2 400 -- ``cierre_dia`` codigo requires ``uuid_sesion=null``."""

    error: str = "cierre_dia_no_acepta_uuid_sesion"


class JustificacionRequeridaErrorRead(_Base):
    """V6 400 -- cierre_turno/cierre_dia + diferencia != 0 + sin justificacion."""

    error: str = "justificacion_requerida"


__all__ = [
    "ArqueoCreate",
    "ArqueoCreateV2",
    "ArqueoFilter",
    "ArqueoRead",
    "ArqueoReadForHandler",
    "ArqueoReadList",
    "ArqueoResumenItem",
    "ArqueoResumenRead",
    "ArqueoUpdate",
    "CajaCreate",
    "CajaFilter",
    "CajaRead",
    "CajaReadList",
    "CajaUpdate",
    "CierreDiaNoAceptaSesionErrorRead",
    "CierreDiarioQueryParams",
    "JustificacionRequeridaErrorRead",
    "SesionCreate",
    "SesionFilter",
    "SesionNoEncontradaErrorRead",
    "SesionRead",
    "SesionReadList",
    "SesionUpdate",
    "SesionYaCerradaErrorRead",
    "TipoArqueoNoEncontradoErrorRead",
    "ToleranciaNoConfiguradaErrorRead",
]
