"""HU-F1.9 / REQ-OPS-053..063 -- transactional billing repo helpers.

Single-PR atomicity contract:

- :func:`crear_factura_evento` (Step 9) inserts the ``prod.facturas`` row.
- :func:`crear_factura_impuesto_iva` (Step 10b) inserts the IVA snapshot.
- :func:`crear_factura_pago` (Step 10c) inserts the initial pago.
- All four (including the bulk detalle INSERT in
  :mod:`repo.factura_detalle`) commit ONCE in the caller's session
  (KD-FACT-01 invariant).

KD-FACT-02: :func:`lock_tarifas_sucursal_para_items` acquires
``SELECT ... FOR SHARE`` per-row on ``prod.tarifas_sucursal`` for every
referenced ``uuid_tarifa_sucursal``. The lock is held until
``session.commit()``.

DEC-FACT-01: writes are append-only INSERTs on the four target tables.
NO UPDATE, NO DELETE.

Typed exceptions are exposed in :data:`__all__` for handler discrimination.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.factura_detalle import FacturaDetalle
from ..models.A.factura_impuestos import FacturaImpuestos
from ..models.A.factura_pagos import FacturaPagos
from ..models.L_E.facturas import Facturas
from ..schemas.facturacion import FacturaItemCreate

# ---------------------------------------------------------------------------
# Typed exceptions (handler 12-step chain discriminator)
# ---------------------------------------------------------------------------


class SalidaNoFacturableError(Exception):
    """404 V1 — salida does not exist OR is not facturable.

    Returns ``None`` when the lookup misses; raised by handler with
    ``detail={"error": "salida_no_facturable", "uuid_salida": ...}``.
    """


class ClienteNoEncontradoFacturaError(Exception):
    """404 V2 — cliente does not exist (when ``fe_con_datos=true``)."""


class NitInvalidoError(Exception):
    """422 V5 — NIT módulo 11 mismatch.

    Pydantic v2 ``@model_validator`` already raises this in 99% of
    cases; this typed exception is the server-side defense-in-depth.
    """


class TotalNoCoherenteError(Exception):
    """422 V6 — server-recomputed ``total`` differs from payload by >0.01 COP."""


class VoucherRequeridoError(Exception):
    """400 V7 — ``medio_pago='datafono'`` requires non-empty ``referencia``."""


class FacturaDuplicadaError(Exception):
    """409 — partial unique index ``one_factura_per_salida`` violated.

    Source: MIGRATION 0027 Op 2. Maps from
    ``IntegrityError("one_factura_per_salida")`` during INSERT.
    """


class PagoDuplicadoError(Exception):
    """409 — BEFORE INSERT trigger ``fn_factura_pagos_init_pago_uniqueness``.

    Source: MIGRATION 0027 Op 3. Maps from RAISES EXCEPTION via
    ``ERRCODE=unique_violation``.
    """

    def __init__(self, *, uuid_factura: uuid_lib.UUID) -> None:
        self.uuid_factura = uuid_factura
        super().__init__(f"pago_duplicado: uuid_factura={uuid_factura}")


# ---------------------------------------------------------------------------
# V1: buscar salida facturable
# ---------------------------------------------------------------------------


async def buscar_salida_facturable(
    session: AsyncSession, *, uuid_salida: uuid_lib.UUID
) -> Salidas | None:
    """V1 — read ``prod.salidas`` row by uuid.

    Used by handler Step 2 (V1) to verify the salida is facturable.
    A salida is facturable iff (per DEC-FACT-02):

    - It exists in ``prod.salidas`` (this helper confirms row presence).
    - It has not been previously facturada (enforced by the
      ``one_factura_per_salida`` partial unique index, MIGRATION 0027 Op 2).
    - It belongs to the requester's sucursal (enforced at handler
      Step 3 tenant scope, NOT here).

    Returns the :class:`Salidas` row when present, ``None`` otherwise.
    Handler maps ``None`` to 404 ``salida_no_encontrada``.
    """
    from ..models.A.salidas import Salidas  # local import to avoid cycles

    stmt = select(Salidas).where(Salidas.uuid == uuid_salida)
    return (await session.execute(stmt)).scalar_one_or_none()


async def buscar_o_crear_cliente_por_nit(
    session: AsyncSession,
    *,
    numero_identificacion: str,
    datos: Any,
) -> Any | None:
    """V2 — lookup ``prod.clientes`` by ``numero_identificacion``.

    For MVP (F1.9): returns ``None`` when not found (handler maps to 404).
    Auto-creación is Fase 2 (per design).
    """
    from ..models.V.clientes import Clientes  # local import to avoid cycles

    stmt = select(Clientes).where(Clientes.numero_identificacion == numero_identificacion)
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row


# ---------------------------------------------------------------------------
# V4: validar items
# ---------------------------------------------------------------------------


def validar_items(items: list[FacturaItemCreate]) -> list[FacturaItemCreate]:
    """V4 — defense-in-depth re-check of items.

    Pydantic already enforces ``min_length=1``, ``gt(0)``,
    ``Literal[tipo]``. This function is a defense-in-depth re-check;
    returns the same list on success, raises
    :class:`TotalNoCoherenteError`-equivalents (here we just return)
    if any invariant violated.

    For F1.9 MVP, the items pass through if Pydantic accepted them.
    Future HUs may add per-item invariants (e.g., unique concepts).
    """
    if not items:
        return []
    return items


# ---------------------------------------------------------------------------
# KD-FACT-02: lock FOR SHARE per-row
# ---------------------------------------------------------------------------


async def lock_tarifas_sucursal_para_items(
    session: AsyncSession, *, items: list[FacturaItemCreate]
) -> None:
    """KD-FACT-02: ``SELECT FOR SHARE`` per-row on ``prod.tarifas_sucursal``.

    For every unique ``uuid_tarifa_sucursal`` referenced. Lock held until
    caller's ``session.commit()``. If no items reference
    ``uuid_tarifa_sucursal``, this is a no-op.
    """
    tarifs_uuids = {
        item.uuid_tarifa_sucursal
        for item in items
        if item.uuid_tarifa_sucursal is not None
    }
    if not tarifs_uuids:
        return

    from ..models.V.tarifas_sucursal import TarifasSucursal

    stmt = (
        select(TarifasSucursal)
        .where(TarifasSucursal.uuid.in_(tarifs_uuids))
        .with_for_update(read=True)  # psycopg2/asyncpg: FOR SHARE
    )
    result = await session.execute(stmt)
    # Materialize the lock: iterate so the SELECT FOR SHARE actually
    # acquires the lock, not just builds the query.
    list(result.scalars())


# ---------------------------------------------------------------------------
# V6: compute_total
# ---------------------------------------------------------------------------


def compute_total(
    *,
    items: list[FacturaItemCreate],
    iva: Decimal,
    retencion: Decimal = Decimal(0),
) -> Decimal:
    """V6: server-side recompute of ``total = subtotal_items + iva - retencion``.

    ``subtotal_items = sum(item.cantidad * item.valor_unitario)``.

    ``iva = subtotal_items * iva_rate`` (the Decimal from caller).

    ``retencion = Decimal('0')`` in MVP (DEC-FACT-04, Fase 4 deferred).
    """
    subtotal_items = sum(
        (item.cantidad * item.valor_unitario for item in items),
        Decimal(0),
    )
    iva_monto = (subtotal_items * iva).quantize(Decimal("0.01"))
    total = subtotal_items + iva_monto - retencion
    return total.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Step 9: INSERT prod.facturas [L-E]
# ---------------------------------------------------------------------------


async def crear_factura_evento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict[str, Any],
) -> Facturas:
    """Step 9: INSERT ``prod.facturas`` [L-E] (bi-temporal).

    DEC-FACT-01 amended: F1.9 only INSERTs, never UPDATEs. State
    transitions happen via NEW rows with later
    ``fecha_retencion_hasta`` per bi-temporal versioning. The
    single-commit invariant (KD-FACT-01) materializes the INSERT
    atomically with the other 3 tables.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    new_row = Facturas(**new_attrs, created_at=now, created_by=actor_uuid)
    session.add(new_row)
    try:
        await session.flush()
    except IntegrityError as err:
        # Partial unique index ``one_factura_per_salida`` (MIGRATION 0027
        # Op 2) rejects a second factura for the same uuid_salida.
        if "one_factura_per_salida" in str(err.orig):
            raise FacturaDuplicadaError() from err
        raise
    return new_row


# ---------------------------------------------------------------------------
# Step 10b: INSERT prod.factura_impuestos (IVA snapshot)
# ---------------------------------------------------------------------------


async def crear_factura_impuesto_iva(
    session: AsyncSession,
    *,
    uuid_factura: uuid_lib.UUID,
    base: Decimal,
    iva: Decimal,
) -> FacturaImpuestos:
    """Step 10b: INSERT one IVA snapshot row in ``prod.factura_impuestos``.

    Looks up ``uuid_impuesto`` (IVA) from ``prod.impuestos`` and
    accepts the ``iva`` percentage (already validated by Step 5 via
    :func:`repo.impuestos.obtener_iva_vigente`) from the caller.
    Snapshots both ``uuid_impuesto`` and ``porcentaje_aplicado`` so
    historical reports remain valid even if IVA changes.

    DEC-FACT-03: the percentage is NOT hardcoded; it MUST come from
    the caller (which sources it from ``prod.impuestos``). If a
    regulatory change raises IVA from 0.19 to 0.20, the same value
    is used for ``compute_total`` (Step 8) and the IVA snapshot
    (this function) — no drift between total and snapshot.

    KD-FACT-01: caller commits ONCE.
    """
    from ..models.V.impuestos import Impuestos  # local import to avoid cycles

    iva_row = (
        await session.execute(
            select(Impuestos).where(
                Impuestos.codigo == "IVA",
                Impuestos.vigente_hasta.is_(None),
                Impuestos.estado == "activo",
            )
        )
    ).scalar_one()

    iva_monto = (base * iva).quantize(Decimal("0.01"))
    new_row = FacturaImpuestos(
        uuid_factura=uuid_factura,
        uuid_impuesto=iva_row.uuid,
        base_calculo=base,
        porcentaje_aplicado=iva,
        valor=iva_monto,
        fecha_retencion_hasta=date.today() + timedelta(days=5 * 365),
    )
    session.add(new_row)
    await session.flush()
    return new_row


# ---------------------------------------------------------------------------
# Step 10c: INSERT prod.factura_pagos (initial pago)
# ---------------------------------------------------------------------------


async def crear_factura_pago(
    session: AsyncSession,
    *,
    uuid_factura: uuid_lib.UUID,
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"],
    valor: Decimal,
    referencia: str | None = None,
    uuid_sesion: uuid_lib.UUID | None = None,
) -> FacturaPagos:
    """Step 10c: INSERT one pago row in ``prod.factura_pagos``.

    ``tipo_movimiento='pago'`` is the initial payment. Reversos are
    INSERT-only compensating movements (handled by F1.13 via
    :func:`repo.factura_pagos.reverse_payment`, REUSED VERBATIM).

    Defense-in-depth: BEFORE INSERT trigger
    ``fn_factura_pagos_init_pago_uniqueness`` (MIGRATION 0027 Op 3)
    rejects a second pago row for the same ``uuid_factura``.
    """
    new_row = FacturaPagos(
        uuid_factura=uuid_factura,
        medio_pago=medio_pago,
        valor=valor,
        referencia=referencia,
        uuid_sesion=uuid_sesion,
        tipo_movimiento="pago",
        fecha_retencion_hasta=date.today() + timedelta(days=5 * 365),
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(new_row)
    try:
        await session.flush()
    except IntegrityError as err:
        # BEFORE INSERT trigger RAISES EXCEPTION via
        # ``ERRCODE='unique_violation'`` → psycopg2/asyncpg raises
        # ``IntegrityError``.
        if "factura_pagos_init_pago_uniqueness" in str(err.orig):
            raise PagoDuplicadoError(uuid_factura=uuid_factura) from err
        raise
    return new_row


__all__ = [
    "ClienteNoEncontradoFacturaError",
    "FacturaDuplicadaError",
    "NitInvalidoError",
    "PagoDuplicadoError",
    "SalidaNoFacturableError",
    "TotalNoCoherenteError",
    "VoucherRequeridoError",
    "buscar_o_crear_cliente_por_nit",
    "buscar_salida_facturable",
    "compute_total",
    "crear_factura_evento",
    "crear_factura_impuesto_iva",
    "crear_factura_pago",
    "lock_tarifas_sucursal_para_items",
    "validar_items",
]
