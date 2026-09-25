"""Display projection helper for ``POST /facturacion/factura``.

HU-F8.4 — Mostrar factura post-pago con desglose (MVP).

The `<FacturaDisplayModal />` in ``apps/electron-sucursal`` shows the
breakdown after a successful pago. To avoid forcing the FE into a
second round-trip, the BE response of ``POST /api/v1/facturacion/
factura`` carries the display projection inline.

``build_display_factura`` queries the joined rows the handler just
inserted (or already loaded):

* ``prod.factura_pagos`` for the init pago's ``medio_pago`` (just
  committed in the handler via ``repo_factura.crear_factura_pago``)
* ``prod.factura_impuestos`` joined with ``prod.impuestos`` for the
  snapshot percentage AND the catalog ``nombre``
* ``prod.salidas`` + ``prod.ingreso`` for placa, fecha_ingreso,
  fecha_salida, and ``minutos`` (computed wall-clock)
* ``prod.sucursal`` + ``prod.empresa`` for datos_sucursal display
* ``prod.clientes`` by uuid_cliente for cliente display (NULL when
  consumidor final)
* COUNT(facturas) for the local ``numero_recibo`` derivation

All reads happen AFTER the KD-FACT-01 single-commit atomic write. The
helper runs in the same ``AsyncSession`` (no new TX). KD-S7 lock has
already been released at this point.

**MVP scope** (HU-F8.4-PR1): the helper covers the operator's
explicit request — minutos, segregación de valores (subtotal + total
+ items + impuestos), datos sucursal/cliente/vehiculo. Deferred for
later PRs: ``pagos[]`` array (FE can derive from `medio_pago` +
form), ``factura_electronica`` (cloud-only, NULL at branch emission
time 99% of the time), ``vuelto_cents`` / ``monto_recibido_cents``
(FE computes client-side from PagoModal state), ``voucher`` (FE has
it in the form).

The helper is intentionally not in ``repo/`` because it composes data
from 4 tables for a single consumer (the FE display); it is not a
persistence operation. Tests live in
``tests/api/test_factura_display_projection.py``.
"""
from __future__ import annotations

import math
import uuid as uuid_lib
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.A.factura_detalle import FacturaDetalle
from ...models.A.factura_impuestos import FacturaImpuestos
from ...models.A.factura_pagos import FacturaPagos
from ...models.L_E.facturas import Facturas
from ...models.L_E.ingreso import Ingreso
from ...models.V.clientes import Clientes
from ...models.V.empresa import Empresa
from ...models.V.impuestos import Impuestos
from ...models.V.sucursal import Sucursal
from ...schemas.facturacion import (
    FacturaCreate,
    FacturaDisplayCliente,
    FacturaDisplayImpuesto,
    FacturaDisplaySucursal,
    FacturaDisplayVehiculo,
    FacturaItemRead,
    FacturaRead,
    FacturaServicioCreate,
)


def _to_decimal(value: float | int | Decimal | None) -> Decimal | None:
    """Coerce a SQLAlchemy Numeric (Python float) or int to Decimal.

    The ORM maps Numeric(18,4) to Python ``float`` for convenience;
    the Pydantic schemas (``FacturaRead``, ``FacturaDisplayImpuesto``)
    declare ``Decimal``. This helper centralizes the conversion so
    every display projection site is consistent.
    """
    if value is None:
        return None
    return Decimal(str(value))


async def build_display_factura(
    session: AsyncSession,
    *,
    new_factura: Facturas,
    detalles_creados: list[FacturaDetalle],
    payload: FacturaCreate | FacturaServicioCreate,
    total_server: Decimal,
    cliente_uuid: uuid_lib.UUID | None,
) -> FacturaRead:
    """Assemble the enriched :class:`FacturaRead` for the post-pago response.

    Caller MUST have already called ``session.commit()`` (KD-FACT-01)
    before invoking this helper. No new transactions, no new locks —
    this is read-only composition on the just-committed state.

    Parameters
    ----------
    session
        The same ``AsyncSession`` used by ``create_factura``. The
        helper runs queries against this session's connection — no
        second connection / no second pool borrow.
    new_factura
        The just-committed ``prod.facturas`` row, already ``refresh()``ed.
    detalles_creados
        The list of ``prod.factura_detalle`` rows inserted in Step 10.
        Used to build the ``items: list[FacturaItemRead]`` field.
    payload
        The original POST payload — carries ``medio_pago``,
        ``referencia``, ``fe_con_datos``, ``fe_datos_cliente``. The
        helper reads ``medio_pago`` from the init ``factura_pagos`` row
        (canonical source, not the payload).
    total_server
        The server-recomputed total (KD-FACT-01 invariant).
    cliente_uuid
        ``uuid_cliente`` after V2 lookup (DEC-FACT-06 derivado).
        ``None`` when consumidor final (no ``prod.clientes`` row).

    Returns
    -------
    FacturaRead
        The enriched shape the FE consumes.
    """
    # ---- 1) Init pago from the row just inserted in Step 10 ----
    # The init pago row carries ``medio_pago`` (canonical source). This
    # is the discriminator the FE uses to choose post-pago behavior.
    init_pago_row = (
        await session.execute(
            select(FacturaPagos)
            .where(FacturaPagos.uuid_factura == new_factura.uuid)
            .where(FacturaPagos.tipo_movimiento == "pago")
            .order_by(FacturaPagos.timestamp_evento.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    medio_pago: str = (
        init_pago_row.medio_pago
        if init_pago_row is not None and init_pago_row.medio_pago is not None
        else payload.medio_pago
    )

    # ---- 2) Impuestos snapshot + nombre from prod.impuestos ----
    # DEC-SUC-24 segregation: the display must show the breakdown
    # (base + porcentaje snapshot + valor) so the operator sees what
    # was applied, NOT just the total. ``porcentaje_aplicado`` is the
    # historical snapshot (preserved on factura_impuestos even when
    # the catalog version closes).
    impuestos_rows = (
        await session.execute(
            select(FacturaImpuestos, Impuestos)
            .join(Impuestos, FacturaImpuestos.uuid_impuesto == Impuestos.uuid, isouter=True)
            .where(FacturaImpuestos.uuid_factura == new_factura.uuid)
        )
    ).all()
    impuestos_display = [
        FacturaDisplayImpuesto(
            uuid=imp.uuid,
            uuid_impuesto=imp.uuid_impuesto,
            nombre_impuesto=cat.nombre if cat else None,
            codigo_impuesto=cat.codigo if cat else None,
            base_calculo=_to_decimal(imp.base_calculo),
            porcentaje_aplicado=_to_decimal(imp.porcentaje_aplicado),
            valor=_to_decimal(imp.valor),
        )
        for imp, cat in impuestos_rows
    ]

    # ---- 3) Datos sucursal (sucursal JOIN empresa) ----
    # The current row of the bi-temporal table (vigente_hasta IS NULL).
    sucursal_row = (
        await session.execute(
            select(Sucursal, Empresa)
            .join(Empresa, Sucursal.uuid_empresa == Empresa.uuid, isouter=True)
            .where(Sucursal.uuid == new_factura.uuid_sucursal)
            .where(Sucursal.vigente_hasta.is_(None))
        )
    ).first()
    if sucursal_row is None:
        # Defensive: a sucursal row MUST exist by the time a factura
        # is created (tenant scoping). Surface a server-side error
        # rather than silently swallowing.
        raise RuntimeError(
            f"sucursal row not found for uuid_sucursal={new_factura.uuid_sucursal}"
        )
    suc, emp = sucursal_row
    datos_sucursal = FacturaDisplaySucursal(
        razon_social=suc.nombre,
        nit=emp.nit if emp else None,
        direccion=suc.direccion,
        ciudad=suc.ciudad,
        telefono=suc.telefono,
        horario=suc.horario,
        regimen=emp.regimen if emp else None,
    )

    # ---- 4) Datos vehiculo (ingreso JOIN salidas + minutos) ----
    # ``salidas`` doesn't have a ``cotizacion_snapshot`` column in the
    # DB; we derive the time parked from
    # ``(salidas.fecha_salida - ingreso.fecha_ingreso)``. DEC-SUC-24
    # states the display mirrors the time that was billed = wall-clock
    # time for rotación at standard tarifa.
    ingreso_row = (
        await session.execute(
            select(Ingreso)
            .where(Ingreso.uuid == new_factura.uuid_ingreso)
        )
    ).scalar_one_or_none()
    salida_row = (
        await session.execute(
            select(FacturaPagos)  # placeholder; we need Salidas but import is tricky
            .where(FacturaPagos.uuid_factura == new_factura.uuid)
            .limit(0)
        )
    ).all()  # noqa: E501
    # Actually, query Salidas properly:
    from ...models.A.salidas import Salidas  # local import to avoid path issues

    salida_row = (
        await session.execute(
            select(Salidas)
            .where(Salidas.uuid == new_factura.uuid_salida)
        )
    ).scalar_one_or_none()
    datos_vehiculo: FacturaDisplayVehiculo | None = None
    if ingreso_row is not None and salida_row is not None:
        minutos: int | None = None
        if ingreso_row.fecha_ingreso is not None and salida_row.fecha_salida is not None:
            delta = salida_row.fecha_salida - ingreso_row.fecha_ingreso
            # Per directive "no salga decimales si no que lo aproxime al
            # siguiente numero" (operator 2026-09-23): CEIL the duration
            # so the operator charges the FULL minute the vehiculo
            # spent in the patio. Sub-second estancias → 1 minute.
            minutos = math.ceil(delta.total_seconds() / 60)
        datos_vehiculo = FacturaDisplayVehiculo(
            placa=ingreso_row.placa,
            uuid_tipo_vehiculo=ingreso_row.uuid_tipo_vehiculo,
            fecha_ingreso=ingreso_row.fecha_ingreso,
            fecha_salida=salida_row.fecha_salida,
            minutos=minutos,
        )

    # ---- 5) Cliente display (NULL for consumidor final) ----
    cliente_display: FacturaDisplayCliente | None = None
    if cliente_uuid is not None:
        cliente_row = (
            await session.execute(
                select(Clientes)
                .where(Clientes.uuid == cliente_uuid)
            )
        ).scalar_one_or_none()
        if cliente_row is not None:
            cliente_display = FacturaDisplayCliente(
                nit=cliente_row.numero_identificacion,
                dv=None,  # DV is on fe_datos_cliente (request), not persisted
                nombre=cliente_row.nombre,
                apellido=cliente_row.apellido,
                email=cliente_row.email,
                telefono=cliente_row.telefono,
            )

    # ---- 6) numero_recibo (sucursal-YYYYMMDD-NNNNNN, derived per-day) ----
    # Per plan.md:473 — local receipt numbering, no relation to FE
    # consecutivo. Derived server-side from a COUNT query at emission
    # time. O(N) per factura but acceptable for MVP; consider column
    # promotion if throughput becomes an issue (post-MVP).
    count_today = (
        await session.execute(
            select(func.count())
            .select_from(Facturas)
            .where(Facturas.uuid_sucursal == new_factura.uuid_sucursal)
            .where(func.date(Facturas.created_at) == date.today())
        )
    ).scalar_one()
    numero_recibo = (
        f"{(new_factura.uuid_sucursal or uuid_lib.uuid4()).hex[:8]}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
        f"{int(count_today):06d}"
    )

    # ---- 7) Assemble FacturaRead ----
    return FacturaRead(
        # --- Base (HU-F1.9) ---
        uuid=new_factura.uuid,
        created_at=new_factura.created_at,
        uuid_sucursal=new_factura.uuid_sucursal,  # type: ignore[arg-type]
        uuid_ingreso=new_factura.uuid_ingreso,
        uuid_salida=new_factura.uuid_salida,
        subtotal=_to_decimal(new_factura.subtotal) or Decimal(0),
        descuento=_to_decimal(new_factura.descuento) or Decimal(0),
        total=_to_decimal(new_factura.total) or Decimal(0),
        uuid_cliente=cliente_uuid,
        items=[
            # NOTE: ``prod.factura_detalle`` does NOT have a ``tipo``
            # column in the DB (verified via \d+ on the table). The
            # create_factura_detalle_bulk repo passes
            # ``tipo=item.tipo`` to the ORM but the kwarg is silently
            # dropped. The ``FacturaItemRead.tipo: str`` is required,
            # so we hard-code "servicio" for every line — acceptable
            # for a parking lot where every line is essentially a
            # service. If the operator ever needs to differentiate
            # servicio vs producto, a migration to add the column
            # would be required (NOT in MVP scope).
            FacturaItemRead(
                uuid=item.uuid,
                tipo="servicio",
                concepto=item.concepto or "",
                cantidad=item.cantidad or 0,
                valor_unitario=_to_decimal(item.valor_unitario) or Decimal(0),
                subtotal=_to_decimal(item.subtotal) or Decimal(0),
            )
            for item in detalles_creados
        ],
        estado="emitida",
        # --- HU-F8.4 display enrichment (MVP) ---
        medio_pago=medio_pago,  # type: ignore[arg-type]
        monto_recibido_cents=None,  # FE computes client-side from PagoModal
        vuelto_cents=None,  # FE computes client-side from PagoModal
        voucher=None,  # FE has it in the form
        numero_recibo=numero_recibo,
        cliente=cliente_display,
        datos_sucursal=datos_sucursal,
        datos_vehiculo=datos_vehiculo,
        impuestos=impuestos_display,
        pagos=[],  # MVP: empty; FE reads medio_pago + form values for vueltos/voucher
        factura_electronica=None,  # MVP: NULL (cloud-only, numbers async)
    )


__all__ = ["build_display_factura"]