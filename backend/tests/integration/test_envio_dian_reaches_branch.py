"""test_envio_dian_reaches_branch.py — T-PR9-009.

``envio_dian`` reaching the branch is an ordinary ``cloud_to_branch``
catalog apply: ``repo.workflow.append_transition`` (already shipped in
PR4). This test exercises that apply directly against a REAL Postgres
database and asserts the two invariants T-PR9-009 cares about:

  1. ``factura_electronica``'s own columns are byte-identical before and
     after the ``envio_dian`` apply — it is NEVER updated (design.md §2
     Issue #1's "No-UPDATE consequence").
  2. ``cufe``/``estado`` are readable through the derived view
     ``prod.v_factura_electronica_acuse`` (migration 0009, T-PR5-008) —
     not by re-reading ``factura_electronica`` itself.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime

import pytest
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.L_W.envio_dian import EnvioDian
from parkos_core.models.V.clientes import Clientes
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.repo.workflow import append_transition
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _snapshot(row: FacturaElectronica) -> dict[str, object]:
    """Every mapped column's current value, keyed by column name."""
    mapper = sa_inspect(FacturaElectronica)
    return {col.name: getattr(row, col.name) for col in mapper.columns}


@pytest.mark.asyncio
async def test_envio_dian_apply_never_updates_factura_electronica_and_cufe_readable_via_view(
    pg_engine: AsyncEngine, seeded_sucursal_uuid: uuid_lib.UUID
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        resolucion = ResolucionFacturacion(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            numero_resolucion=f"RES-{uuid_lib.uuid4().hex[:8]}",
            prefijo="SETP",
            rango_desde=1,
            rango_hasta=999999999,
            fecha_resolucion=date.today(),
            fecha_inicio_vigencia=date.today(),
            fecha_fin_vigencia=None,
            vigente_desde=_now(),
            vigente_hasta=None,
            estado="activo",
            created_at=_now(),
            created_by=None,
            sync_status="pendiente",
            sync_timestamp=None,
            sync_attempts=0,
        )
        factura_comercial = Facturas(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            subtotal=10000,
            descuento=0,
            total=10000,
            uuid_ingreso=None,
            uuid_salida=None,
            created_at=_now(),
            created_by=None,
        )
        cliente = Clientes(
            uuid=uuid_lib.uuid4(),
            tipo_identificador="CC",
            numero_identificacion=str(uuid_lib.uuid4().int)[:10],
            nombre="Cliente",
            apellido="Branch Apply",
            vigente_desde=_now(),
            vigente_hasta=None,
            estado="activo",
            created_at=_now(),
            created_by=None,
            sync_status="pendiente",
            sync_timestamp=None,
            sync_attempts=0,
        )
        session.add_all([resolucion, factura_comercial, cliente])
        await session.commit()

        factura_electronica = FacturaElectronica(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=seeded_sucursal_uuid,
            uuid_factura=factura_comercial.uuid,
            uuid_cliente=cliente.uuid,
            uuid_resolucion_facturacion=resolucion.uuid,
            prefijo="SETP",
            consecutivo=1,
            descuento=0,
            created_at=_now(),
            created_by=None,
        )
        session.add(factura_electronica)
        await session.commit()
        factura_uuid = factura_electronica.uuid

    # Snapshot BEFORE the envio_dian apply.
    async with Session() as session:
        before = (
            await session.execute(
                select(FacturaElectronica).where(FacturaElectronica.uuid == factura_uuid)
            )
        ).scalar_one()
        before_snapshot = _snapshot(before)

    # Apply envio_dian at the branch — an ordinary cloud_to_branch catalog
    # apply (apply_strategy="append_transition", PR4). Root insertion:
    # STATE_MACHINES validation is a no-op for parent_uuid=None (only
    # validated on a chained transition), matching dispatcher.py's own
    # root-envio construction.
    actor_uuid = uuid_lib.uuid4()
    async with Session() as session:
        envio = await append_transition(
            session,
            EnvioDian,
            actor_uuid=actor_uuid,
            new_attrs={
                "uuid_sucursal": seeded_sucursal_uuid,
                "uuid_factura_electronica": factura_uuid,
                "uuid_resolucion_facturacion": resolucion.uuid,
                "cufe": "cufe-branch-reach-001",
                "estado": "aceptado",
                "timestamp_evento": _now(),
            },
            parent_uuid=None,
            parent_fk_column="uuid_envio_padre",
            log_tx=False,
        )
        await session.commit()
        envio_uuid = envio.uuid

    # Snapshot AFTER — factura_electronica must be byte-identical.
    async with Session() as session:
        after = (
            await session.execute(
                select(FacturaElectronica).where(FacturaElectronica.uuid == factura_uuid)
            )
        ).scalar_one()
        after_snapshot = _snapshot(after)

    assert after_snapshot == before_snapshot, (
        "factura_electronica's own columns changed after an envio_dian apply "
        "— it must NEVER be updated (design.md §2 Issue #1)"
    )

    # cufe/estado are readable through the derived view, not by re-reading
    # factura_electronica.
    async with Session() as session:
        acuse = (
            await session.execute(
                text(
                    "SELECT cufe, estado FROM prod.v_factura_electronica_acuse "
                    "WHERE uuid_factura_electronica = :uuid"
                ),
                {"uuid": str(factura_uuid)},
            )
        ).one()

    assert acuse.cufe == "cufe-branch-reach-001"
    assert acuse.estado == "aceptado"

    # Sanity: the view's row really is keyed off the envio we just applied.
    async with Session() as session:
        applied = (
            await session.execute(select(EnvioDian).where(EnvioDian.uuid == envio_uuid))
        ).scalar_one()
    assert applied.cufe == "cufe-branch-reach-001"


def test_snapshot_helper_covers_every_mapped_column() -> None:
    """Defensive: :func:`_snapshot` covers every mapped column, not a
    hand-picked subset — otherwise a future new column could silently
    escape the byte-identity check above."""
    mapper = sa_inspect(FacturaElectronica)
    column_names = {c.name for c in mapper.columns}
    assert {"uuid", "prefijo", "consecutivo", "uuid_resolucion_facturacion"} <= column_names

    dummy = FacturaElectronica()
    assert set(_snapshot(dummy).keys()) == column_names
