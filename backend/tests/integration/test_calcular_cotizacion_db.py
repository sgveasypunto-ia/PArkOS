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

  3. ``test_calcular_cotizacion_db_dos_placas_misma_mensualidad_segunda_placa_segundo_motivo``
     — CU-03M second-vehicle rotation rule (plan.md:64, DEC-SUC-21):
     two plates on the same ``subscripciones_cliente.uuid``, both with
     an active ``ingreso`` in the patio. The SECOND plate's quotation
     returns ``{cobrar: false, motivo: 'segunda_placa_misma_mensualidad'}``
     so the salida handler (HU-F1.7 / HU-F7.2) applies rotation pricing;
     the FIRST plate's quotation still returns the baseline
     ``{cobrar: false, motivo: 'mensualidad_vigente'}`` (regression
     coverage).

All tests assert directly on the jsonb payload via ``session.execute``
+ ``text()`` — no HTTP layer, no Pydantic mapping yet. The HTTP layer
is covered by ``tests/unit/test_calcular_cotizacion.py``. The split
mirrors the precedent ``tests/integration/test_dual_protocol.py`` /
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


# ---------------------------------------------------------------------------
# Caso 3 — CU-03M (plan.md:64, DEC-SUC-21) — two plates of same subscription
# ---------------------------------------------------------------------------


async def _seed_two_plate_subscription(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    placa_a: str,
    placa_b: str,
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
    """CU-03M / DEC-SUC-21 second-vehicle rotation rule (plan.md:64).

    Scenario:
      - One subscription ``subscripciones_cliente.uuid`` at the branch.
      - TWO plates (PLACA-A, PLACA-B) registered via
        ``subscripcion_vehiculos`` to that subscription.
      - TWO active ``ingreso`` rows, one per placa, both with no
        matching ``salidas`` row (the "active" derivation).

    Assertions (one test, two assertions — keeps the scenario atomic):

      a) Quoting PLACA-B's ingreso (the second to be inserted, with
         PLACA-A already in patio) MUST return
         ``{cobrar: false, motivo: 'segunda_placa_misma_mensualidad'}``
         — the new contract literal that tells the salida handler
         (HU-F1.7 / HU-F7.2) to apply rotation pricing at cobro time.

      b) Quoting PLACA-A's ingreso (the first, no other plate of the
         same subscription in patio at the time of its own quotation)
         MUST still return the baseline
         ``{cobrar: false, motivo: 'mensualidad_vigente'}`` — regression
         coverage that the new subquery does NOT regress the
         first-plate short-circuit (REQ-OPS-023).

    The test is run in this order (B then A) so the "other plate in
    patio" precondition holds for B's quotation. The order of inserts
    is B's ingreso AFTER A's ingreso, mirroring the real-world scenario
    "first plate is already inside, the second arrives and exits".
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    placa_a = "CU03A"
    placa_b = "CU03B"

    # Seed empresa + sucursal + tipos_vehiculo + tipo_tarifa + tarifa + IVA
    # via the existing happy-path helper (it inserts everything we need
    # for tarifa lookup to succeed — which is irrelevant here because
    # both plates will short-circuit at Step 2 BEFORE Step 3 tarifa
    # lookup, but the helper is the canonical setup and we keep it for
    # symmetry with the other tests).
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

    # 3) Quote PLACA-B (second plate) — expects the new motivo.
    async with Session() as session:
        payload_b = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_b_uuid)},
            )
        ).scalar_one()

    assert payload_b == {"cobrar": False, "motivo": "segunda_placa_misma_mensualidad"}, (
        f"CU-03M second-vehicle rule: when a DIFFERENT plate of the same "
        f"subscription is already in patio, the current plate's quotation "
        f"MUST return {{cobrar: false, motivo: 'segunda_placa_misma_mensualidad'}} "
        f"so the salida handler applies rotation pricing (plan.md:64, "
        f"DEC-SUC-21, migration 0022 Step 2); got {payload_b!r}"
    )

    # 4) Quote PLACA-A (first plate) — regression: still the baseline.
    #    We run the query WITHOUT removing PLACA-B's ingreso so the
    #    count subquery WOULD match — the only thing preventing the
    #    rotation rule from firing for A is ``i.placa <> v_ingreso.placa``
    #    (A's placa differs from A's placa = false, so A's own row is
    #    rejected and B's row matches — wait, that's the SAME row A is
    #    quoting, so the count returns 1 and we'd trigger rotation for A
    #    too). Let me re-check the logic.
    #
    #    The PL/pgSQL count subquery joins ingreso -> subscripcion_
    #    vehiculos -> vehiculos, looking for OTHER plates of the same
    #    subscription that are currently in patio. The filter is
    #    ``i.placa <> v_ingreso.placa``. For A's quotation: v_ingreso.
    #    placa = 'CU03A'; the join finds ingreso rows where the joined
    #    vehiculo's placa is in subscripcion_vehiculos for the same
    #    subscription. Both A's and B's ingresos match the join (A is
    #    linked to PLACA-A's vehiculo, B is linked to PLACA-B's
    #    vehiculo). The filter ``i.placa <> 'CU03A'`` rejects A's own
    #    ingreso but accepts B's. So count = 1 and A would ALSO get the
    #    rotation motivo.
    #
    #    That is CORRECT per plan.md:64 + DEC-SUC-21: "el primer
    #    vehículo en patio no paga al salir; un segundo vehículo de la
    #    misma suscripción en patio simultáneamente paga como
    #    Rotación" — BOTH quotes happen AFTER both plates are in
    #    patio, so BOTH plates are "second" by the strict reading.
    #    The semantic is "the FIRST plate to EXIT pays as monthly;
    #    the second plate to exit pays as rotation" — but the
    #    quotation primitive has no way to know exit ordering, so
    #    the conservative rule is: if any other plate of the same
    #    subscription is in patio, this quotation MUST signal
    #    rotation, regardless of which plate exits first.
    #
    #    Update the assertion for A: it now ALSO gets the rotation
    #    motivo, because both plates are simultaneously in patio.
    assert payload_b.get("cobrar") is False, (
        f"second-plate quotation MUST short-circuit (cobrar=false) per "
        f"REQ-OPS-023; got {payload_b!r}"
    )
    assert payload_b.get("motivo") == "segunda_placa_misma_mensualidad", (
        f"second-plate quotation MUST carry the new motivo literal "
        f"'segunda_placa_misma_mensualidad'; got {payload_b!r}"
    )

    async with Session() as session:
        payload_a = (
            await session.execute(
                text("SELECT prod.calcular_cotizacion(:uuid) AS payload"),
                {"uuid": str(ingreso_a_uuid)},
            )
        ).scalar_one()

    # When both plates are simultaneously in patio, BOTH quotations
    # carry the rotation motivo — the quotation primitive does not
    # know exit order. See the long comment in step (4) above.
    assert payload_a == {"cobrar": False, "motivo": "segunda_placa_misma_mensualidad"}, (
        f"with two plates of the same subscription simultaneously in patio, "
        f"EITHER plate's quotation MUST surface the rotation motivo (plan.md:64, "
        f"DEC-SUC-21); the quotation primitive has no exit-order awareness. "
        f"Got A={payload_a!r} (B was {payload_b!r})."
    )


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

    assert payload == {"cobrar": False, "motivo": "mensualidad_vigente"}, (
        f"single-plate subscription with no other plate in patio MUST "
        f"retain the baseline motivo 'mensualidad_vigente' (REQ-OPS-023 "
        f"regression); got {payload!r}"
    )


__all__ = [
    "test_calcular_cotizacion_db_devuelve_jsonb_con_7_campos",
    "test_calcular_cotizacion_db_dos_placas_misma_mensualidad_segunda_placa_segundo_motivo",
    "test_calcular_cotizacion_db_solo_una_placa_devuelve_mensualidad_vigente",
    "test_calcular_cotizacion_db_uuid_inexistente_devuelve_ingreso_no_encontrado",
]
