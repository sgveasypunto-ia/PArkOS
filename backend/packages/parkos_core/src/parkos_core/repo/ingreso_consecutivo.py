"""Per-``(uuid_sucursal, uuid_tipo_vehiculo)`` ``consecutivo`` assignment
(REQ-OPS-191..193, HU-INGRESO-SIN-PLACA, design §4).

Mirrors :func:`repo.resolucion_facturacion.assign_consecutivo` (T-PR9-002)
verbatim where possible -- the idempotency-then-``SELECT FOR UPDATE``-then-
``UPDATE`` pattern is the project's proven recipe for monotonic counter
allocation under concurrent POSTs from multiple kioskos at the same
branch.

The returned string is the parking-lot identifier for ``ingreso`` rows
without a placa (``bicicleta``, ``patineta``), formatted as
``<TIPO>-NNNNNN-<uuid8>`` -- e.g. ``BICI-000001-3f8a1b2c``. The
``<uuid8>`` suffix is the first 8 hex chars of the caller-supplied
``source_event_uuid`` (which MUST equal the new ``ingreso.uuid`` once
the handler commits) -- making retries byte-identical.

``No side effect outside the caller's transaction.`` This helper only
reads + takes a row lock + may INSERT/UPDATE one counter row. The caller
is expected to INSERT the new ``ingreso`` row (``record_event``) using
the returned string and commit together, in the SAME transaction. If
that transaction rolls back, the counter row's mutation is rolled back
too, so the next call recomputes from the same committed state and hands
out the same number again.

``[A]`` audit class: ``REVOKE UPDATE, DELETE`` on ``rol_app`` and a
``BEFORE UPDATE OR DELETE`` trigger in migration 0042 enforce this at
the DB layer; the trigger carve-out allows UPDATE only on the
``(ultimo_consecutivo, last_event_uuid, sync_status, sync_timestamp,
sync_attempts)`` columns -- exactly what this helper mutates.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.ingreso_consecutivo_contador import IngresoConsecutivoContador
from ..models.V.tipos_vehiculo import TiposVehiculo


class TipoVehiculoNotFoundError(RuntimeError):
    """Raised when ``uuid_tipo_vehiculo`` matches no vigente
    ``prod.tipos_vehiculo`` row at the catalog layer.

    Distinct from ``prod.tipos_vehiculo.uuid`` simply being unknown --
    the catalog layer itself might be missing the row (e.g. mid-sync
    during a cloud-to-branch sync outage). Maps to HTTP 422 at the
    handler with ``error='tipo_vehiculo_invalido'``.
    """


class ConsecutivoExhaustedError(RuntimeError):
    """Raised when ``ultimo_consecutivo`` would exceed ``999999``.

    The CHECK constraint on the column enforces ``ultimo_consecutivo <
    1000000`` at the DB layer. Realistic single-branch scale never
    approaches this (a 999,999-counter overflow means 1 million ingresos
    sin placa on one branch), but if it happens the next
    ``assign_ingreso_consecutivo`` raises. Handler maps to HTTP 503
    ``consecutivo_ingreso_exhausted`` -- operational alert flow
    (DEC-INCOME-04) deferred per ``exploration.md`` Q1.
    """


async def assign_ingreso_consecutivo(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    source_event_uuid: uuid_lib.UUID,
) -> str:
    """Return the next ``consecutivo`` in format ``<TIPO>-NNNNNN-<uuid8>``.

    Idempotent per ``source_event_uuid`` (REQ-OPS-191): looks up FIRST
    whether a counter row already has ``last_event_uuid == source_event_uuid``
    in this namespace; if so, reuses the stored ``ultimo_consecutivo``
    verbatim. A retry of the SAME emitting event reuses the same number
    instead of leaking a gap or handing out a second one.

    Args:
        session: Active ``AsyncSession`` -- caller commits together with
            the ``ingreso`` INSERT that consumes the returned string.
        uuid_sucursal: Branch scope (multi-tenant isolation: two branches
            can both have ``BICI-000001-...`` without collision).
        uuid_tipo_vehiculo: The catalog tipo UUID (``bicicleta`` /
            ``patineta`` for the no-placa flow; the function does NOT
            itself check the tipo matches a no-placa one -- that's the
            handler's responsibility).
        source_event_uuid: Idempotency anchor. The handler pre-generates
            ``new_uuid = uuid.uuid4()`` BEFORE calling this helper so the
            ``<uuid8>`` suffix is deterministic across retries; the
            handler then INSERTs ``ingreso.uuid = new_uuid`` in the same
            TX. Same UUID in -> same suffix -> same byte-identical string.

    Returns:
        Formatted string ``<TIPO>-NNNNNN-<source_event_uuid.hex[:8]>``,
        e.g. ``"BICI-000001-3f8a1b2c"``.

    Raises:
        TipoVehiculoNotFoundError: catalog has no vigente row for
            ``uuid_tipo_vehiculo``.
        ConsecutivoExhaustedError: counter at 999999 (would overflow
            the CHECK constraint).
    """
    # 0. Resolve TIPO uppercase from the catalog (one round-trip).
    tipo_row = (
        await session.execute(
            select(TiposVehiculo.tipo).where(
                TiposVehiculo.uuid == uuid_tipo_vehiculo,
                TiposVehiculo.vigente_hasta.is_(None),
                TiposVehiculo.estado == "activo",
            )
        )
    ).first()
    if tipo_row is None:
        raise TipoVehiculoNotFoundError(
            f"uuid_tipo_vehiculo={uuid_tipo_vehiculo} not vigente in "
            f"prod.tipos_vehiculo"
        )
    tipo_upper = (tipo_row.tipo or "").upper()  # 'BICI' | 'PATIN' | etc.

    # 1. IDEMPOTENCY CHECK -- mirror assign_consecutivo step 1.
    existing = (
        await session.execute(
            select(IngresoConsecutivoContador).where(
                IngresoConsecutivoContador.uuid_sucursal == uuid_sucursal,
                IngresoConsecutivoContador.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
                IngresoConsecutivoContador.last_event_uuid == source_event_uuid,
                IngresoConsecutivoContador.vigente_hasta.is_(None),  # type: ignore[attr-defined]
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _format_consecutivo(
            tipo_upper, existing.ultimo_consecutivo, source_event_uuid
        )

    # 2. SELECT FOR UPDATE on the vigente counter row.
    counter = (
        await session.execute(
            select(IngresoConsecutivoContador)
            .where(
                IngresoConsecutivoContador.uuid_sucursal == uuid_sucursal,
                IngresoConsecutivoContador.uuid_tipo_vehiculo == uuid_tipo_vehiculo,
                IngresoConsecutivoContador.vigente_hasta.is_(None),  # type: ignore[attr-defined]
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if counter is None:
        # 3a. FIRST INGRESO for this namespace -- INSERT counter row 1.
        # Lazy import mirrors api/v1/operacion.py:384 -- dateutil may not
        # be available at module-load time in some test environments.
        from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

        new_counter = IngresoConsecutivoContador(
            uuid_sucursal=uuid_sucursal,
            uuid_tipo_vehiculo=uuid_tipo_vehiculo,
            ultimo_consecutivo=1,
            last_event_uuid=source_event_uuid,
            vigente_desde=datetime.now(UTC).replace(tzinfo=None),
            # DIAN retention: 5 years from creation (AGENTS.md §1).
            fecha_retencion_hasta=datetime.now(UTC).date() + relativedelta(years=5),
        )
        session.add(new_counter)
        await session.flush()
        return _format_consecutivo(tipo_upper, 1, source_event_uuid)

    # 3b. SUBSEQUENT INGRESO -- UPDATE counter (carve-out allows this).
    next_n = counter.ultimo_consecutivo + 1
    if next_n >= 1000000:
        raise ConsecutivoExhaustedError(
            f"counter overflow at namespace (sucursal={uuid_sucursal}, "
            f"tipo={uuid_tipo_vehiculo}): next consecutivo {next_n} would "
            f"exceed the 6-digit format"
        )
    counter.ultimo_consecutivo = next_n
    counter.last_event_uuid = source_event_uuid
    # SQLAlchemy ORM-level mutation; on flush() the carve-out trigger
    # allows the UPDATE because only (ultimo_consecutivo, last_event_uuid)
    # changed.
    return _format_consecutivo(tipo_upper, next_n, source_event_uuid)


def _format_consecutivo(
    tipo_upper: str, n: int, source_uuid: uuid_lib.UUID
) -> str:
    """Format ``<TIPO>-{n:06d}-{source_uuid.hex[:8]}`` (REQ-OPS-191).

    The 6-digit zero-padded ``n`` handles up to 999,999 consecutivos per
    ``(sucursal, tipo)`` namespace -- well beyond any realistic
    single-branch scale. The 8-hex suffix is the first 8 chars of the
    Ingreso UUID, which makes retries byte-identical.
    """
    return f"{tipo_upper}-{n:06d}-{source_uuid.hex[:8]}"


__all__ = [
    "ConsecutivoExhaustedError",
    "TipoVehiculoNotFoundError",
    "assign_ingreso_consecutivo",
]