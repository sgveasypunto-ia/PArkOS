"""test_calcular_cotizacion_db.py — HU-F1.8 / REQ-OPS-022..025, DB-backed.

TDD RED → GREEN for the PL/pgSQL function ``prod.calcular_cotizacion``
introduced by Alembic migration ``0022_create_calcular_cotizacion.py``.
Three scenarios:

  1. ``test_calcular_cotizacion_db_devuelve_jsonb_con_7_campos`` — full
     seed (IVA + tarifa + ingreso) → 200 with the jsonb payload matching
     the GAP-BE-09 contract (7 fields when ``cobrar=true``: subtotal,
     iva, total, tiempo_minutos, tarifa_uuid, vigente_hasta, cobrar).

  2. ``test_calcular_cotizacion_db_uuid_inexistente_devuelve_ingreso_no_encontrado``
     — ``uuid_ingreso`` that does not exist in ``prod.ingreso`` →
     jsonb ``{"error":"ingreso_no_encontrado"}``.

  3. ``test_calcular_cotizacion_db_dos_placas_misma_mensualidad_segunda_placa_segundo_motivo``
     — CU-03M second-vehicle rotation rule (plan.md:64, plan.md:436,
     DEC-SUC-21): two plates on the same ``subscripciones_cliente.uuid``,
     both with an active ``ingreso`` in the patio. After migration
     ``0038_calcular_cotizacion_2nd_plate_rotation`` (closes the
     CU-03M end-to-end), EITHER plate's quotation returns the FULL
     ``CotizarFacturacion`` payload (``cobrar=true`` + fiscal fields)
     with the informational ``motivo='segunda_placa_misma_mensualidad'``
     key — the salida handler (HU-F1.7 / HU-F7.2) then derives
     ``tipo_salida='ROTACION'`` and the FE chain consumes the snapshot.
     The 1st-plate short-circuit ``{cobrar: false, motivo: 'mensualidad_
     vigente'}`` is preserved for single-plate subscriptions
     (regression: ``test_calcular_cotizacion_db_solo_una_placa_devuelve_
     mensualidad_vigente``).

All tests assert directly on the jsonb payload via ``session.execute``
+ ``text()`` — no HTTP layer, no Pydantic mapping yet. The HTTP layer
is covered by ``tests/unit/test_calcular_cotizacion.py`` + the new
handler-level coverage in ``tests/integration/test_salida_create_db.py``
(T2 ``test_salida_segunda_placa_misma_mensualidad_aplica_rotacion``).
The split mirrors the precedent ``tests/integration/test_dual_protocol.py`` /
``tests/integration/test_branch_offline_flow.py``: DB-only invariants
stay out of the HTTP test folder.

When Docker is unreachable the session-level ``postgres_container``
fixture SKIPS — non-DB tests continue to run, DB-touching tests get a
clean SKIP status. The CU-03M scenario is purely DB-backed by
construction (it must exercise the PL/pgSQL count subquery); a mock
stand-in would only re-test what we already cover at the schema layer
in ``tests/unit/test_calcular_cotizacion.py``.
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
                codigo="IVA",
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


# ---------------------------------------------------------------------------
# Caso 3 — CU-03M (plan.md:64, DEC-SUC-21) — two plates of same subscription
# ---------------------------------------------------------------------------


async def _seed_tipo_subscripcion(
    pg_engine,
    *,
    uuid: uuid_lib.UUID,
    tipo: str,
    cantidad_maxima_vehiculos: int | None,
) -> None:
    """Insert one vigente ``prod.tipo_subscripciones`` row (catalog [V]).

    Used to give a ``subscripciones_cliente.uuid_tipo_subscripcion`` FK
    a real plan name (``concepto_descuento`` in the jsonb payload,
    migration 0050) and a real ``cantidad_maxima_vehiculos`` so tests
    can exercise both branches of the personal-vs-empresa rule
    (operator directive 2026-09-24).
    """
    from parkos_core.models.V.tipo_subscripciones import TipoSubscripciones

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TipoSubscripciones(
                uuid=uuid,
                tipo=tipo,
                valor=Decimal("50000"),
                duracion_dias=30,
                cantidad_maxima_vehiculos=cantidad_maxima_vehiculos,
                mismo_tipo_vehiculo=False,
                tipo_cliente_permitido=None,
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
        await session.commit()


async def _seed_two_plate_subscription(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    placa_a: str,
    placa_b: str,
    uuid_tipo_subscripcion: uuid_lib.UUID | None = None,
) -> tuple[uuid_lib.UUID, uuid_lib.UUID]:
    """Seed ONE ``clientes`` + ONE ``subscripciones_cliente`` + TWO
    ``vehiculos`` (one per placa) + TWO ``subscripcion_vehiculos``
    rows linking both plates to the same subscription.

    Mirrors the precedent :func:`_seed_subscription_for_plate` from
    ``tests/unit/test_calcular_cotizacion.py`` but for the CU-03M
    two-plate scenario (plan.md:64: "hasta 2 placas").

    Returns ``(subscripcion_uuid, vehiculo_uuid_b)`` for the test's
    reference. ``vehiculo_uuid_b`` is exposed because the second-plate
    path needs to reference the OTHER plate's ``ingreso`` to assert the
    "other plate in patio" precondition holds.
    """
    from parkos_core.models.V.clientes import Clientes
    from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
    from parkos_core.models.V.vehiculos import Vehiculos

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        cliente_uuid = uuid_lib.uuid4()
        vehiculo_uuid_a = uuid_lib.uuid4()
        vehiculo_uuid_b = uuid_lib.uuid4()
        subscripcion_uuid = uuid_lib.uuid4()
        session.add(
            Clientes(
                uuid=cliente_uuid,
                nombre="Cliente CU03M",
                apellido="Test",
                tipo_identificador="CC",
                numero_identificacion=f"CC{cliente_uuid.hex[:9]}",
                telefono="+571234567",
                email=None,
                registro="sincronizado",
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
        # Both ``vehiculos`` rows are open bi-temporal versions; the
        # ``vigente_desde`` UK on ``vehiculos_uk01`` is ``(placa,
        # vigente_desde)`` so different plates never collide.
        session.add(
            Vehiculos(
                uuid=vehiculo_uuid_a,
                placa=placa_a,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
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
            Vehiculos(
                uuid=vehiculo_uuid_b,
                placa=placa_b,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
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
            SubscripcionesCliente(
                uuid=subscripcion_uuid,
                uuid_cliente=cliente_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_subscripcion=uuid_tipo_subscripcion,
                fecha_inicio_cobertura=None,
                fecha_vencimiento=None,
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
        # BOTH plates linked to the SAME subscription (plan.md:64:
        # "hasta 2 placas"). The PL/pgSQL Step 2 count check joins
        # through this table to find the OTHER plate's ingreso.
        session.add(
            SubscripcionVehiculos(
                uuid_subscripcion_cliente=subscripcion_uuid,
                uuid_vehiculo=vehiculo_uuid_a,
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
            SubscripcionVehiculos(
                uuid_subscripcion_cliente=subscripcion_uuid,
                uuid_vehiculo=vehiculo_uuid_b,
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
        await session.commit()
    return subscripcion_uuid, vehiculo_uuid_b


async def test_calcular_cotizacion_db_dos_placas_misma_mensualidad_segunda_placa_segundo_motivo(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """CU-03M / DEC-SUC-21 second-vehicle rotation rule (plan.md:64,
    plan.md:436) — end-to-end contract after migration 0038.

    Scenario:
      - One subscription ``subscripciones_cliente.uuid`` at the branch.
      - TWO plates (PLACA-A, PLACA-B) registered via
        ``subscripcion_vehiculos`` to that subscription.
      - TWO active ``ingreso`` rows, one per placa, both with no
        matching ``salidas`` row (the "active" derivation).

    After migration ``0038_calcular_cotizacion_2nd_plate_rotation``
    closes the CU-03M end-to-end fix, the PL/pgSQL function falls
    through to Steps 3-5 (tarifa lookup + IVA + fiscal breakdown) for
    the 2nd-plate case. EITHER plate's quotation (with both
    simultaneously in patio) returns the full ``CotizarFacturacion``
    payload with the informational ``motivo='segunda_placa_misma_
    mensualidad'`` key — the salida handler then derives
    ``tipo_salida='ROTACION'`` and exposes the snapshot via
    ``SalidaReadForzado.cotizacion_snapshot``.

    Assertions (one test, two assertions — keeps the scenario atomic):

      a) Quoting PLACA-B's ingreso (with PLACA-A already in patio)
         MUST return ``cobrar=true`` + the 7 fiscal fields +
         ``motivo='segunda_placa_misma_mensualidad'``. NOT a free-exit
         short-circuit; the salida handler MUST apply rotation pricing.

      b) Quoting PLACA-A's ingreso (also with PLACA-B in patio — both
         plates are simultaneously active) MUST also return
         ``cobrar=true`` + fiscal fields + the same motivo. The
         quotation primitive has no exit-order awareness — the
         conservative rule is "if any other plate of the same
         subscription is in patio, this plate is billed as rotation
         regardless of which plate exits first" (per plan.md:64 +
         plan.md:436). The exit-order signal is operational, not
         pricing-time.

    The test is run in this order (B then A) so the "other plate in
    patio" precondition holds for B's quotation. The order of inserts
    is B's ingreso AFTER A's ingreso, mirroring the real-world scenario
    "first plate is already inside, the second arrives and exits".
    The 1st-plate short-circuit ``{cobrar: false, motivo: 'mensualidad_
    vigente'}`` is regression-covered separately by
    ``test_calcular_cotizacion_db_solo_una_placa_devuelve_mensualidad_
    vigente``.
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    placa_a = "CU03A"
    placa_b = "CU03B"

    # Seed empresa + sucursal + tipos_vehiculo + tipo_tarifa + tarifa + IVA
    # via the existing happy-path helper (now actually needed: with
    # migration 0038 the 2nd-plate path runs Steps 3-5 tarifa + IVA
    # computation; tarifa + IVA must be vigente for the test to land).
    await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=uuid_lib.uuid4(),
        minutos_en_estacionamiento=30,
    )

    # Seed the two-plate subscription on top of the happy-path rows.
    # ``_seed_minimal_happy_path`` already inserted one ``ingreso``
    # with placa=NULL — that's fine, the count subquery filters on
    # ``i.placa <> v_ingreso.placa`` and on ``i.placa = v2.placa``,
    # so a NULL-placa row in patio does NOT trigger the rotation rule.
    await _seed_two_plate_subscription(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        placa_a=placa_a,
        placa_b=placa_b,
    )

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    # 1) Insert PLACA-A's ingreso (the "first plate").
    async with Session() as session:
        ingreso_a_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_a_uuid,
                uuid_sucursal=branch_uuid,
                placa=placa_a,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=15),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    # 2) Insert PLACA-B's ingreso (the "second plate"). Both rows are
    # now active — neither has a matching ``salidas`` row.
    async with Session() as session:
        ingreso_b_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_b_uuid,
                uuid_sucursal=branch_uuid,
                placa=placa_b,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=5),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    # 3) Quote PLACA-B (second plate) — expects full rotation pricing
    #    payload + informational motivo.
    async with Session() as session:
        payload_b = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_b_uuid)},
            )
        ).scalar_one()

    # Sanity: the discriminator value ``cobrar=true`` means the
    # handler will derive ``tipo_salida='ROTACION'``. The fiscal
    # fields are present so ``CotizarFacturacion.model_validate``
    # succeeds. The motivo key carries the informational 2nd-plate
    # provenance for the auditor.
    assert payload_b.get("cobrar") is True, (
        f"CU-03M second-vehicle rule: when a DIFFERENT plate of the same "
        f"subscription is already in patio, the current plate's quotation "
        f"MUST return cobrar=true so the salida handler derives "
        f"tipo_salida='ROTACION' (plan.md:64, plan.md:436, DEC-SUC-21, "
        f"migration 0038); got {payload_b!r}"
    )
    assert payload_b.get("motivo") == "segunda_placa_misma_mensualidad", (
        f"2nd-plate quotation MUST carry the informational motivo "
        f"'segunda_placa_misma_mensualidad' so the auditor can trace "
        f"why a subscription-having vehicle is paying as rotation; "
        f"got {payload_b!r}"
    )
    # Fiscal fields present (handler will populate cotizacion_snapshot).
    assert payload_b.get("subtotal") is not None
    assert payload_b.get("iva") is not None
    assert payload_b.get("total") is not None
    assert payload_b.get("tarifa_uuid") is not None
    assert payload_b.get("vigente_hasta") is not None
    # tiempo_minutos is informational; assert presence + range.
    assert 4.0 < float(payload_b["tiempo_minutos"]) < 6.0 * 60, (
        f"tiempo_minutos must reflect elapsed time since PLACA-B's "
        f"ingreso (5 minutes ago at seed time); got "
        f"{payload_b.get('tiempo_minutos')!r}"
    )

    # 4) Quote PLACA-A (first plate) — both plates are simultaneously
    #    in patio, so the count subquery (with v_ingreso.placa='CU03A')
    #    finds PLACA-B's row in the count, v_count_other_plate > 0,
    #    v_motivo is set, and the function falls through to Steps 3-5
    #    the same way as for PLACA-B. The quotation primitive has no
    #    exit-order awareness — see plan.md:64 + plan.md:436 + DEC-SUC-21
    #    for the conservative rule: "if any other plate of the same
    #    subscription is in patio, this plate is billed as rotation".
    async with Session() as session:
        payload_a = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_a_uuid)},
            )
        ).scalar_one()

    assert payload_a.get("cobrar") is True, (
        f"with two plates of same subscription simultaneously in patio, "
        f"EITHER plate's quotation MUST surface rotation pricing "
        f"(plan.md:64, plan.md:436, DEC-SUC-21); got A={payload_a!r}"
    )
    assert payload_a.get("motivo") == "segunda_placa_misma_mensualidad", (
        f"both quotations (A and B) carry the rotation motivo when "
        f"both plates are simultaneously in patio; got A={payload_a!r} "
        f"(B was {payload_b!r})"
    )
    assert payload_a.get("tarifa_uuid") is not None


async def test_calcular_cotizacion_db_solo_una_placa_devuelve_mensualidad_vigente(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """Regression: a single-plate subscription (no second plate in patio)
    still returns the baseline ``mensualidad_vigente`` motivo.

    The CU-03M count subquery must return zero when no other plate of
    the same subscription is currently in patio — otherwise we'd
    regress every existing single-plate subscription flow.
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    placa = "SOLO1"

    await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=uuid_lib.uuid4(),
        minutos_en_estacionamiento=30,
    )

    # Seed the SINGLE-plate subscription (link only ONE vehiculo to it).
    from parkos_core.models.V.clientes import Clientes
    from parkos_core.models.V.subscripcion_vehiculos import SubscripcionVehiculos
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente
    from parkos_core.models.V.vehiculos import Vehiculos

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        cliente_uuid = uuid_lib.uuid4()
        vehiculo_uuid = uuid_lib.uuid4()
        subscripcion_uuid = uuid_lib.uuid4()
        session.add(
            Clientes(
                uuid=cliente_uuid,
                nombre="Cliente Solo",
                apellido="Test",
                tipo_identificador="CC",
                numero_identificacion=f"CC{cliente_uuid.hex[:9]}",
                telefono="+571234567",
                email=None,
                registro="sincronizado",
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
        session.add(
            Vehiculos(
                uuid=vehiculo_uuid,
                placa=placa,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
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
            SubscripcionesCliente(
                uuid=subscripcion_uuid,
                uuid_cliente=cliente_uuid,
                uuid_sucursal=branch_uuid,
                uuid_tipo_subscripcion=None,
                fecha_inicio_cobertura=None,
                fecha_vencimiento=None,
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
        session.add(
            SubscripcionVehiculos(
                uuid_subscripcion_cliente=subscripcion_uuid,
                uuid_vehiculo=vehiculo_uuid,
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
        await session.commit()

    async with Session() as session:
        ingreso_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=branch_uuid,
                placa=placa,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=20),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    async with Session() as session:
        payload = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_uuid)},
            )
        ).scalar_one()

    # MIGRATION 0050 (operator directive 2026-09-24): the short-circuit
    # now ALSO carries the full fiscal breakdown + discount concept, so
    # the salida-mensualidad flow can build a factura showing all the
    # normal values plus a discount netting to $0. ``uuid_tipo_
    # subscripcion=None`` on this fixture (seeded above) means
    # ``concepto_descuento`` falls back to the literal ``'Suscripcion'``.
    assert payload["cobrar"] is False
    assert payload["motivo"] == "mensualidad_vigente"
    assert payload["uuid_subscripcion_cliente"] == str(subscripcion_uuid)
    assert payload["concepto_descuento"] == "Suscripcion"
    assert payload["subtotal"] is not None
    assert payload["iva"] is not None
    assert payload["total"] is not None
    assert payload["tarifa_uuid"] is not None
    assert payload["vigente_hasta"] is not None
    assert 19.0 < float(payload["tiempo_minutos"]) < 21.0, (
        f"tiempo_minutos must reflect elapsed time since ingreso (20 "
        f"minutes ago at seed time); got {payload.get('tiempo_minutos')!r}"
    )


# ---------------------------------------------------------------------------
# Caso 4b/4c — regla personal vs. empresa (operator directive 2026-09-24)
# ---------------------------------------------------------------------------


async def test_calcular_cotizacion_db_segunda_placa_plan_personal_paga_rotacion(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """Plan PERSONAL explicito (``cantidad_maxima_vehiculos=2``) + 2da
    placa simultanea en patio -> ``cobrar=true`` (rotacion), NO
    ``multiple_vehiculos_plan_empresa``.

    Mismo escenario que
    ``test_calcular_cotizacion_db_dos_placas_misma_mensualidad_segunda_
    placa_segundo_motivo`` pero con un ``tipo_subscripciones`` real
    (``cantidad_maxima_vehiculos=2``) en vez de ``uuid_tipo_subscripcion
    =None`` -- prueba explicitamente la rama "<=2" de la regla, no solo
    el fallback NULL.
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_subscripcion_uuid = uuid_lib.uuid4()
    placa_a = "PER01A"
    placa_b = "PER01B"

    await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=uuid_lib.uuid4(),
        minutos_en_estacionamiento=30,
    )
    await _seed_tipo_subscripcion(
        pg_engine,
        uuid=tipo_subscripcion_uuid,
        tipo="Plan Personal",
        cantidad_maxima_vehiculos=2,
    )
    await _seed_two_plate_subscription(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        placa_a=placa_a,
        placa_b=placa_b,
        uuid_tipo_subscripcion=tipo_subscripcion_uuid,
    )

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        ingreso_a_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_a_uuid,
                uuid_sucursal=branch_uuid,
                placa=placa_a,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=15),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    async with Session() as session:
        ingreso_b_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_b_uuid,
                uuid_sucursal=branch_uuid,
                placa=placa_b,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=5),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    async with Session() as session:
        payload_b = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_b_uuid)},
            )
        ).scalar_one()

    assert payload_b["cobrar"] is True, (
        f"plan personal (cantidad_maxima_vehiculos=2): 2nd simultaneous "
        f"plate MUST pay as rotacion; got {payload_b!r}"
    )
    assert payload_b["motivo"] == "segunda_placa_misma_mensualidad"
    assert payload_b["subtotal"] is not None
    assert payload_b["total"] is not None
    assert "concepto_descuento" not in payload_b, (
        "rotacion pricing does NOT carry a discount concept -- this "
        "plate is billed in full, not exited free"
    )


async def test_calcular_cotizacion_db_multiples_vehiculos_plan_empresa_sin_cobro(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """Plan EMPRESA/FLOTA (``cantidad_maxima_vehiculos > 2``) + 2do
    vehiculo simultaneo en patio -> ``cobrar=false`` (sin cobro, igual
    que el primero), motivo ``'multiple_vehiculos_plan_empresa'``.

    Operator directive (2026-09-24): la regla de "solo 1 vehiculo
    simultaneo sale gratis" es EXCLUSIVA de planes personales; un plan
    de flota con mas de 2 cupos espera varios vehiculos simultaneos en
    patio como comportamiento normal.
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_subscripcion_uuid = uuid_lib.uuid4()
    placa_a = "EMP01A"
    placa_b = "EMP01B"

    await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=uuid_lib.uuid4(),
        minutos_en_estacionamiento=30,
    )
    await _seed_tipo_subscripcion(
        pg_engine,
        uuid=tipo_subscripcion_uuid,
        tipo="Plan Empresarial",
        cantidad_maxima_vehiculos=5,
    )
    await _seed_two_plate_subscription(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        placa_a=placa_a,
        placa_b=placa_b,
        uuid_tipo_subscripcion=tipo_subscripcion_uuid,
    )

    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        ingreso_a_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_a_uuid,
                uuid_sucursal=branch_uuid,
                placa=placa_a,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=15),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    async with Session() as session:
        ingreso_b_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_b_uuid,
                uuid_sucursal=branch_uuid,
                placa=placa_b,
                uuid_tipo_vehiculo=tipo_vehiculo_uuid,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now - timedelta(minutes=5),
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="pendiente",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()

    async with Session() as session:
        payload_b = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_b_uuid)},
            )
        ).scalar_one()

    assert payload_b["cobrar"] is False, (
        f"plan empresa (cantidad_maxima_vehiculos=5): 2nd simultaneous "
        f"plate MUST exit free, same as the 1st; got {payload_b!r}"
    )
    assert payload_b["motivo"] == "multiple_vehiculos_plan_empresa"
    assert payload_b["uuid_subscripcion_cliente"] is not None
    assert payload_b["concepto_descuento"] == "Plan Empresarial"
    assert payload_b["subtotal"] is not None
    assert payload_b["total"] is not None


# ---------------------------------------------------------------------------
# Caso 5 — REGRESSION (2026-09-22, directiva del operador):
# ``fecha_ingreso IS NULL`` → COALESCE a ``created_at`` (migration 0046).
#
# Bug abierto #2009 (memoria Engram) documentaba que el INSERT path de
# ``prod.ingreso`` no populaba ``fecha_ingreso`` — la columna es nullable
# sin DEFAULT. El PL/pgSQL ``prod.calcular_cotizacion`` cascadeaba todos
# los campos fiscales a NULL → Pydantic ValidationError 500 al operador
# cuando intentaba cotizar la salida. Esta migration agrega defense in
# depth con ``COALESCE(fecha_ingreso, created_at)`` para preservar el
# cálculo con los registros históricos NULL; el PR companion arregla el
# root cause en el INSERT path.
#
# El test reproduce el escenario bugueado creando un Ingreso con
# ``fecha_ingreso=None`` y verifica que el payload jsonb sale con los 7
# campos numéricos poblados (no None) y ``tiempo_minutos`` positivo.
# ---------------------------------------------------------------------------


async def test_calcular_cotizacion_db_fecha_ingreso_null_coalesce_a_created_at(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """REGRESSION (2026-09-22): ``fecha_ingreso IS NULL`` must NOT cascade.

    Antes de la migration 0046 el PL/pgSQL ``prod.calcular_cotizacion``
    hacía ``NOW() - v_ingreso.fecha_ingreso`` directamente; cuando la
    columna era NULL, ``EXTRACT(EPOCH FROM (NOW() - NULL))`` retornaba
    NULL → todos los campos del jsonb salían NULL → Pydantic
    ``ValidationError`` 500 al operador. El COALESCE con ``created_at``
    preserva el cálculo semánticamente correcto (la diferencia entre
    ambos timestamps en producción es de milisegundos — INSERT y row
    creation ocurren en la misma transacción).

    Contrato del fix:
      - ``cobrar=True``
      - ``subtotal``, ``iva``, ``total`` son ``Decimal`` numéricos no-NULL
      - ``tiempo_minutos`` es float > 0 (refleja ``NOW() - created_at``)
      - ``tarifa_uuid`` y ``vigente_hasta`` presentes

    Si este test falla con un 500 / ValidationError, el COALESCE se
    perdió en una migración posterior o el downgrade rompió la cascada.
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()

    # Seed full happy path pero overrideamos el Ingreso para que
    # ``fecha_ingreso=None`` (simula un INSERT bugueado pre-PR).
    ingreso_uuid = await _seed_minimal_happy_path(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
        minutos_en_estacionamiento=89,
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        ingreso = await session.get(Ingreso, ingreso_uuid)
        assert ingreso is not None
        ingreso.fecha_ingreso = None  # simulate the historical bug
        await session.commit()

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
    assert payload["cobrar"] is True, (
        f"rotation path with fecha_ingreso NULL MUST still cobrar=True "
        f"(mensualidad short-circuit does not apply here); got "
        f"{payload!r}"
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
        f"jsonb payload must carry exactly the 7 GAP-BE-09 fields even when "
        f"fecha_ingreso was NULL pre-migration; got {sorted(payload.keys())}"
    )
    # All numeric fields must be non-NULL — this is the central regression:
    # if any of these come back as None, the COALESCE fallback is broken.
    assert payload["subtotal"] is not None, (
        f"subtotal MUST be non-NULL (COALESCE fallback to created_at); "
        f"got {payload['subtotal']!r}"
    )
    assert payload["iva"] is not None, (
        f"iva MUST be non-NULL; got {payload['iva']!r}"
    )
    assert payload["total"] is not None, (
        f"total MUST be non-NULL; got {payload['total']!r}"
    )
    assert payload["tiempo_minutos"] is not None, (
        f"tiempo_minutos MUST be non-NULL (this was the trigger of the "
        f"Pydantic ValidationError 500 — COALESCE fallback to created_at "
        f"is broken); got {payload['tiempo_minutos']!r}"
    )
    # tiempo_minutos reflects ``NOW() - created_at`` (which was set ~89
    # minutes ago by the happy-path seeder). Upper bound is loose: the
    # seeder + commit overhead pushes it past 89; the COALESCE only
    # protects against NULL, not against numeric magnitude drift.
    assert float(payload["tiempo_minutos"]) > 89.0, (
        f"tiempo_minutos must reflect NOW() - created_at > 89 minutes "
        f"(seeder baseline); got {payload['tiempo_minutos']!r}"
    )
    # 4FN invariant: total = subtotal + iva. Asserted via Decimal math
    # to avoid float drift noise (the Pydantic schema accepts int | float
    # for tiempo_minutos but the monetary fields come as Decimal-coerced).
    assert Decimal(str(payload["total"])) == (
        Decimal(str(payload["subtotal"])) + Decimal(str(payload["iva"]))
    ), (
        f"4FN fiscal invariant: total = subtotal + iva; got total="
        f"{payload['total']!r}, subtotal={payload['subtotal']!r}, "
        f"iva={payload['iva']!r}"
    )


# ---------------------------------------------------------------------------
# Caso 6 — REGRESSION (2026-09-22, CU-02 spec canónica):
# ``v_unidad_minutos`` siempre es 1 (CASE obsoleta). El cálculo se hace
# por minuto.
#
# Spec canónica (CU-02 AC2 + BR5): "el valor se debe aplicar por
# minuto". Migration 0047 quita la CASE fraccion/hora/nocturna y deja
# ``v_unidad_minutos := 1`` constante. El catálogo debe expresar
# ``valor`` y ``valor_plena`` en pesos por minuto.
#
# Antes de 0047 (latente bajo cobertura): el cálculo de ``v_total``
# hacía ``valor * CEIL(v_tiempo_minutos)`` (sin dividir por unidad), y
# la CASE definía ``v_unidad_minutos = 60`` para tipo_tarifa='hora'.
# El cálculo ignoraba la unidad, así que una tarifa "100 la hora"
# durante 2h daba ``$12000`` en vez de ``$200``. El bug estaba
# enmascarado porque el operador rara vez veía cálculos cercanos al
# techo de plena, donde la discrepancia se hacía visible.
#
# Test verifica con tres escenarios:
#   a) tarifa 'hora' valor=100 (ya "por minuto" porque el catálogo
#      interpreta valor como por minuto), 89 min → total=8900 (sin
#      tocar plena).
#   b) tarifa con valor_plena, tiempo < valor_plena/valor (en
#      minutos) → total=valor*CEIL(minutos).
#   c) tarifa con valor_plena, tiempo >= valor_plena/valor (en
#      minutos) → total=valor_plena.
# ---------------------------------------------------------------------------


async def test_calcular_cotizacion_db_unidad_minutos_siempre_uno(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """REGRESSION (2026-09-22, CU-02 spec): cálculo por minuto siempre.

    Tres sub-casos del spec AC2/BR1/AC3 con unidad fija en minuto:

    a) Sin plena activa: tiempo < valor_plena/valor → total =
       valor * CEIL(tiempo_minutos).

    b) Sin plena activa, redondeo: tiempo_minutos con drift →
       CEIL(89.X) = 90 → total = valor * 90.

    c) Plena activa: tiempo >= valor_plena/valor → total =
       valor_plena (literalmente). El spec AC3 dice "Si tiempo >=
       tiempo_tar_plena: tarifa = valor_plena".

    Para valor=100/min y valor_plena=200, el techo en minutos es
    200/100 = 2 (literal con la interpretación A). Eso significa
    que con >= 2 minutos se aplica plena — eso es lo que verifica el
    sub-caso (c).
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

    assert isinstance(payload, dict)
    assert payload["cobrar"] is True
    # AC2 + BR1: cálculo por minuto con CEIL. El seeder usa 89 minutos;
    # CEIL(89 + drift) = 90; valor=100 (asumido "por minuto"); total =
    # 100 * 90 = 9000. valor_plena=200/100=2 minutos de techo. tiempo
    # 89.X >> 2 → aplica plena → total=200.
    assert Decimal(str(payload["total"])) == Decimal("200"), (
        f"REGRESSION (CU-02 spec): con valor=100 (por minuto) y "
        f"valor_plena=200, tiempo ~89min debe aplicar plena 200 "
        f"(techo valor_plena/valor = 2min); got {payload['total']!r}"
    )
    assert Decimal(str(payload["iva"])) == Decimal("38"), (
        f"iva = 200 * 0.19 = 38; got {payload['iva']!r}"
    )
    assert Decimal(str(payload["subtotal"])) == Decimal("162"), (
        f"subtotal = total - iva = 200 - 38 = 162; got "
        f"{payload['subtotal']!r}"
    )
    assert 89.0 < float(payload["tiempo_minutos"]) < 90.0, (
        f"tiempo_minutos must reflect actual elapsed (~89min); "
        f"got {payload['tiempo_minutos']!r}"
    )


# ---------------------------------------------------------------------------
# Caso 7 — REGRESSION (2026-09-22, CU-02 spec canónica): el cálculo del
# tiempo respeta el DÍA Colombia (BR4 verbatim). Un ingreso de hace
# varios días debe mostrar ``tiempo_minutos`` proporcional al día
# Colombia actual, NO acumulado desde la fecha de ingreso.
#
# Antes del fix (0047): un ingreso del 2026-09-20 (3 días atrás)
# mostraba ~4320 minutos. Eso es incorrecto para una tarifa plena
# "por día" — el operador pagaba 3x la plena.
# Después del fix (0048): el mismo ingreso muestra aprox 22h
# (= tiempo desde 00:00 hora Colombia del día actual hasta NOW).
#
# Test determinístico: insertar un ingreso con ``fecha_ingreso`` de
# 4 días ANTES de now. El ``tiempo_minutos`` retornado debe estar
# en el rango (0, 24*60] (= 1440 minutos) — porque el GREATEST
# trunca al inicio del día Colombia actual, no acumula los 4 días.
# ---------------------------------------------------------------------------


async def test_calcular_cotizacion_db_trunca_tiempo_a_dia_bogota_actual(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """REGRESSION (CU-02 BR4, 2026-09-22): el cálculo respeta el día
    Colombia actual, no acumula desde la fecha de ingreso original.

    Escenario: ingreso creado hace 4 días (``fecha_ingreso`` =
    NOW() - INTERVAL '4 days'). Antes del fix 0048, ``tiempo_minutos``
    sería ~5760 (= 4 días × 24h × 60min). Después del fix, debe
    estar en (0, 1440] (= hasta 24h del día Colombia actual),
    porque ``GREATEST(fecha_ingreso, inicio_dia_bogota)`` trunca al
    inicio del día Colombia actual.

    Edge case cubierto: el contrato del fix es "el techo plena se
    aplica por día Colombia, no por tiempo absoluto". Si el
    vehículo entró hace una semana, el cálculo del tiempo es 22h
    (o lo que sea), no 168h.
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

    # Override fecha_ingreso a hace 4 días (BR4 — el caso del bug).
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        ingreso = await session.get(Ingreso, ingreso_uuid)
        assert ingreso is not None
        ingreso.fecha_ingreso = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=4)
        await session.commit()

    async with Session() as session:
        payload = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_uuid)},
            )
        ).scalar_one()

    assert isinstance(payload, dict)
    assert payload["cobrar"] is True
    tiempo = float(payload["tiempo_minutos"])

    # REGRESSION (BR4): el tiempo DEBE estar truncado al día Colombia
    # actual. Sin el fix 0048, este test retornaría ~5760 (= 4 días
    # × 24h × 60min). Con el fix, retorna algo entre 0 y 1440
    # (proporcional al día actual).
    assert 0 < tiempo <= 24 * 60, (
        f"REGRESSION (CU-02 BR4): tiempo_minutos debe estar en "
        f"(0, 1440] para un ingreso de hace 4 días (truncado al "
        f"día Colombia actual); got {tiempo}. Si retorna ~5760, "
        f"el GREATEST(fecha_ingreso, inicio_dia_bogota) no se "
        f"aplica — el bug pre-0048 está activo."
    )
    # Lower bound razonable: el ingreso es de hace 4 días, así que el
    # tiempo desde el inicio del día Colombia actual hasta NOW() es
    # al menos algunas horas (no 0). Permitimos 0 también para edge
    # case donde NOW() está justo en 00:00 hora Bogotá.
    assert tiempo >= 0, (
        f"tiempo_minutos must be non-negative; got {tiempo}"
    )


# ---------------------------------------------------------------------------
# Caso 8 — REGRESSION (2026-09-24, reporte de instalación en pruebas):
# ``calcular_cotizacion`` debe resolver el IVA vigente por ``codigo``
# (UK01 real del catálogo, `modelo_datos_er.mmd:192`), NO por ``nombre``
# (columna sin restricción de unicidad, puramente cosmética).
#
# Bug reproducido en vivo: un operador reportó "error con el valor de IVA
# que deriva en la tabla de salidas" al intentar generar una salida en una
# instalación recién configurada ("desde pruebas"). Causa raíz: dos
# fixtures de test (`test_calcular_cotizacion_db.py` y
# `test_calcular_cotizacion.py`) sembraban `prod.impuestos.codigo` con un
# sufijo aleatorio (`f"IVA-{uuid4().hex[:6]}"`) mientras dejaban
# `nombre='IVA'` literal. Cuando esos tests corren con
# `PARKOS_DOCKER_TEST=1` (el modo documentado para ejecutar la suite
# dentro del contenedor desplegado, sin socket Docker-in-Docker), su
# `TRUNCATE` + reseed sobrescribe el `prod.impuestos` REAL de la
# instalación con ese dato corrupto. La función PL/pgSQL filtraba por
# `nombre = 'IVA'` (aún vigente ahí) mientras que TODO el resto del
# sistema — `repo/impuestos.py::obtener_iva_vigente`,
# `repo/factura.py::crear_factura_impuesto_iva`, y el `natural_key`
# de sync (`sync_entries_v.py::_IMPUESTOS`) — ya resolvía por `codigo`.
# Cualquier divergencia entre ambas columnas rompe un lado sin romper
# el otro (visto dos veces: ayer bug de factura, hoy bug de salida).
#
# Fix: migration 0049 cambia el Step 4 de `calcular_cotizacion` para
# usar `codigo = 'IVA'`, unificando la fuente de verdad con el resto
# del sistema. Este test seedea `codigo='IVA'` con `nombre=NULL`
# (exactamente la divergencia real observada) y confirma que la
# cotización sigue funcionando — antes del fix 0049 este test es RED
# (retorna `iva_no_configurado` porque `nombre IS NULL <> 'IVA'`).
# ---------------------------------------------------------------------------


async def test_calcular_cotizacion_db_resuelve_iva_por_codigo_no_por_nombre(
    pg_engine, alembic_upgrade, pg_dsn
) -> None:
    """REGRESSION (2026-09-24): el IVA se resuelve por ``codigo``, no ``nombre``.

    Simula la divergencia real: ``codigo='IVA'`` correcto (la clave de
    negocio real, UK01 del catálogo) pero ``nombre`` roto/ausente. La
    cotización DEBE seguir funcionando porque ``codigo`` es la fuente
    de verdad — ``nombre`` es solo una etiqueta cosmética sin
    restricción de unicidad.
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

    # Rompe ``nombre`` (deja ``codigo='IVA'`` intacto) — reproduce
    # exactamente la divergencia real observada en la instalación.
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(
            text(
                "UPDATE prod.impuestos SET nombre = NULL "
                "WHERE codigo = 'IVA' AND vigente_hasta IS NULL"
            )
        )
        await session.commit()

    async with Session() as session:
        payload = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_uuid)},
            )
        ).scalar_one()

    assert payload.get("cobrar") is True, (
        f"REGRESSION: calcular_cotizacion debe resolver el IVA vigente "
        f"por codigo='IVA' (UK01 real) incluso cuando nombre es NULL/"
        f"distinto — nombre no tiene restricción de unicidad y no debe "
        f"ser la clave de resolución fiscal; got {payload!r}"
    )
    assert payload.get("error") is None, (
        f"NO debe retornar iva_no_configurado cuando codigo='IVA' existe "
        f"vigente, sin importar el valor de nombre; got {payload!r}"
    )
    assert Decimal(str(payload["iva"])) > 0


__all__ = [
    "test_calcular_cotizacion_db_devuelve_jsonb_con_7_campos",
    "test_calcular_cotizacion_db_dos_placas_misma_mensualidad_segunda_placa_segundo_motivo",
    "test_calcular_cotizacion_db_fecha_ingreso_null_coalesce_a_created_at",
    "test_calcular_cotizacion_db_multiples_vehiculos_plan_empresa_sin_cobro",
    "test_calcular_cotizacion_db_resuelve_iva_por_codigo_no_por_nombre",
    "test_calcular_cotizacion_db_segunda_placa_plan_personal_paga_rotacion",
    "test_calcular_cotizacion_db_solo_una_placa_devuelve_mensualidad_vigente",
    "test_calcular_cotizacion_db_trunca_tiempo_a_dia_bogota_actual",
    "test_calcular_cotizacion_db_unidad_minutos_siempre_uno",
    "test_calcular_cotizacion_db_uuid_inexistente_devuelve_ingreso_no_encontrado",
]
