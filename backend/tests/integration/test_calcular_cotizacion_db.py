"""test_calcular_cotizacion_db.py — HU-F1.8 / REQ-OPS-022..025, DB-backed.

TDD RED → GREEN for the PL/pgSQL function ``prod.calcular_cotizacion``
introduced by Alembic migration ``0022_create_calcular_cotizacion.py``.
Two scenarios:

  1. ``test_calcular_cotizacion_db_devuelve_jsonb_con_7_campos`` — full
     seed (IVA + tarifa + ingreso) → 200 with the jsonb payload matching
     the GAP-BE-09 contract (7 fields when ``cobrar=true``: subtotal,
     iva, total, tiempo_minutos, tarifa_uuid, vigente_hasta, cobrar).

  2. ``test_calcular_cotizacion_db_uuid_inexistente_devuelve_ingreso_no_encontrado``
     — ``uuid_ingreso`` that does not exist in ``prod.ingreso`` →
     jsonb ``{"error":"ingreso_no_encontrado"}``.

Both tests assert directly on the jsonb payload via ``session.execute``
+ ``text()`` — no HTTP layer, no Pydantic mapping yet. The HTTP layer
is covered by ``tests/unit/test_calcular_cotizacion.py``. The split
mirrors the precedent ``tests/integration/test_dual_protocol.py`` /
``tests/integration/test_branch_offline_flow.py``: DB-only invariants
stay out of the HTTP test folder.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.impuestos import Impuestos
from parkos_core.models.V.tarifas_sucursal import TarifasSucursal
from parkos_core.models.V.tipo_tarifa import TipoTarifa
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive ``datetime`` matching ``DateTime(timezone=False)`` columns."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate_tables(pg_dsn: str) -> None:
    """Truncate every table touched by these scenarios.

    ``CASCADE`` follows the FK from ``prod.salidas`` into
    ``prod.ingreso`` so a clean slate is guaranteed regardless of
    seed order; mirrors the same pattern in
    ``tests/unit/test_calcular_cotizacion.py``.
    """
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.ingreso, prod.tarifas_sucursal, "
            "prod.impuestos, prod.tipo_tarifa, prod.tipos_vehiculo, "
            "prod.subscripcion_vehiculos, prod.vehiculos, "
            "prod.subscripciones_cliente, prod.sucursal, prod.empresa "
            "CASCADE"
        )
        conn.commit()


async def _seed_minimal_happy_path(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    uuid_tipo_tarifa: uuid_lib.UUID,
    minutos_en_estacionamiento: int,
) -> uuid_lib.UUID:
    """Insert the minimum rows the PL/pgSQL needs to compute a quote:

      - ``empresa`` + ``sucursal``
      - ``tipos_vehiculo`` + ``tipo_tarifa``
      - ``tarifas_sucursal`` (``valor=100, valor_plena=200, tipo='hora'``)
      - ``impuestos`` (``nombre='IVA', porcentaje=0.19``)
      - ``ingreso`` (dated ``minutos_en_estacionamiento`` minutes ago)

    Returns the inserted ``ingreso.uuid``.
    """
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa Cotizar DB Test",
                nit=f"900{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="Hola",
                mensaje_salida="Adios",
                regimen="comun",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
            )
        )
        await session.flush()
        session.add(
            Sucursal(
                uuid=uuid_sucursal,
                uuid_empresa=empresa_uuid,
                uuid_tipo_sucursal=None,
                nombre=f"Sucursal DB {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"D{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle DB 1",
                telefono="+571234567",
                horario="24/7",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        # Flush Sucursal immediately so the downstream FKs
        # (``tarifas_sucursal.uuid_sucursal``, ``ingreso.uuid_sucursal``)
        # see it. Without this explicit flush, the whole batch is
        # committed at ``await session.commit()`` and SQLAlchemy's
        # FK-dependency topological sort still works *in theory*, but
        # a single typo / unique-violation on any sibling insert
        # (e.g. ``prefijo_nombre`` collision) rolls the entire
        # transaction back — including the Sucursal — leaving the
        # FK dangling for the next batch.
        await session.flush()
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo_vehiculo,
                tipo="carro",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        session.add(
            TipoTarifa(
                uuid=uuid_tipo_tarifa,
                tipo="hora",
                vigente_desde=now,
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.flush()
        session.add(
            TarifasSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                uuid_tipo_tarifa=uuid_tipo_tarifa,
                valor=Decimal("100"),
                valor_plena=Decimal("200"),
                vigente_desde=now - timedelta(seconds=1),
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        session.add(
            Impuestos(
                uuid=uuid_lib.uuid4(),
                nombre="IVA",
                codigo=f"IVA-{uuid_lib.uuid4().hex[:6]}",
                porcentaje=Decimal("0.19"),
                tipo_calculo="porcentaje",
                base_calculo="subtotal",
                vigente_desde=now - timedelta(seconds=1),
                vigente_hasta=None,
                estado="activo",
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.flush()
        ingreso_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                placa=None,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=minutos_en_estacionamiento),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


# ---------------------------------------------------------------------------
# Caso 1 — happy path devuelve jsonb con 7 campos (GAP-BE-09)
# ---------------------------------------------------------------------------


async def test_calcular_cotizacion_db_devuelve_jsonb_con_7_campos(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """Full seed → ``prod.calcular_cotizacion(:uuid)`` returns a jsonb
    payload with 7 fields (cobrar, subtotal, iva, total, tiempo_minutos,
    tarifa_uuid, vigente_hasta) and the exact decimal values from
    CU-02 AC7.

    Math sanity (``unidad_minutos=60`` for ``hora``):

      ``tiempo_tar_plena = (200/100) * 60 = 120`` minutes
      ``CEIL(89 + drift) = 90`` → ``total = 100 * 90 = 9000``
      ``iva = 9000 * 0.19 = 1710``
      ``subtotal = 9000 - 1710 = 7290``

    The seed uses 89 minutes (not 90) because the PL/pgSQL ``NOW()``
    evaluated at function-execution time is later than the
    ``fecha_ingreso`` written at test-setup time; CEIL on the resulting
    float ``89.X`` lands exactly on 90 — the natural test boundary.
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()
    ingreso_uuid = await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
        minutos_en_estacionamiento=89,
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        payload = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_uuid)},
            )
        ).scalar_one()

    assert isinstance(payload, dict), (
        f"calcular_cotizacion MUST return a jsonb dict; got {type(payload).__name__}"
    )
    expected_keys = {
        "cobrar",
        "subtotal",
        "iva",
        "total",
        "tiempo_minutos",
        "tarifa_uuid",
        "vigente_hasta",
    }
    assert set(payload.keys()) == expected_keys, (
        f"jsonb payload must carry exactly the 7 GAP-BE-09 fields; "
        f"got {sorted(payload.keys())}"
    )
    assert payload["cobrar"] is True
    assert Decimal(str(payload["total"])) == Decimal("9000"), (
        f"total must be 100 * CEIL(89.X) = 9000 (89.X < tiempo_tar_plena=120); "
        f"got {payload['total']!r}"
    )
    assert Decimal(str(payload["iva"])) == Decimal("1710"), (
        f"iva must be 9000 * 0.19 = 1710; got {payload['iva']!r}"
    )
    assert Decimal(str(payload["subtotal"])) == Decimal("7290"), (
        f"subtotal must be total - iva = 7290; got {payload['subtotal']!r}"
    )
    # ``tiempo_minutos`` carries the raw float (89 + drift); contract
    # asserts the field is present and in the (89, 90) range.
    assert 89.0 < float(payload["tiempo_minutos"]) < 90.0, (
        f"tiempo_minutos must reflect the actual elapsed time (between 89 "
        f"and 90 minutes); got {payload['tiempo_minutos']!r}"
    )
    assert payload["tarifa_uuid"], (
        f"tarifa_uuid must be present and non-empty; got {payload['tarifa_uuid']!r}"
    )
    assert payload["vigente_hasta"], (
        f"vigente_hasta must be present and non-empty; got {payload['vigente_hasta']!r}"
    )


# ---------------------------------------------------------------------------
# Caso 2 — uuid_ingreso inexistente → ingreso_no_encontrado
# ---------------------------------------------------------------------------


async def test_calcular_cotizacion_db_uuid_inexistente_devuelve_ingreso_no_encontrado(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """A ``uuid_ingreso`` that does not exist in ``prod.ingreso`` MUST
    return the jsonb envelope ``{"error":"ingreso_no_encontrado"}`` —
    the first-precedence error per REQ-OPS-024.
    """
    await _truncate_tables(pg_dsn)

    bogus_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        payload = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(bogus_uuid)},
            )
        ).scalar_one()

    assert payload == {"error": "ingreso_no_encontrado"}, (
        f"unknown uuid_ingreso MUST return exactly "
        f"{{'error': 'ingreso_no_encontrado'}}; got {payload!r}"
    )


__all__ = [
    "test_calcular_cotizacion_db_devuelve_jsonb_con_7_campos",
    "test_calcular_cotizacion_db_uuid_inexistente_devuelve_ingreso_no_encontrado",
]
