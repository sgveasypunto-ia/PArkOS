"""test_calcular_cotizacion.py — HU-F1.8 / REQ-OPS-022..024.

TDD RED → GREEN coverage for the new ``GET /api/v1/operacion/cotizar``
handler introduced by HU-F1.8. The endpoint exposes a thin wrapper around
the PL/pgSQL function ``prod.calcular_cotizacion(p_uuid_ingreso uuid)``
(see ``migrations/versions/0022_create_calcular_cotizacion.py``) and is
the canonical server-side quotation primitive that HU-F1.7 ``POST
/operacion/salidas`` will consume as input.

Pattern: identical to the HU-F1.4 precedent in
``tests/unit/test_tarifas_vigente_en.py`` — real ``pg_engine`` (no
SQLite; the bi-temporal predicate + ``FOR SHARE`` lock + rounding on
``Numeric(18,4)`` are Postgres-only behaviour) plus an ``httpx``
``AsyncClient`` bound to the FastAPI app via ``ASGITransport``.

Four scenarios from ``openspec/changes/hu-f1-8-cotizar/proposal.md §9``:

  1. default-cotiza — happy path returns the fiscal breakdown
     (``cobrar=true``, ``subtotal``, ``iva``, ``total``, ``tiempo_minutos``,
     ``tarifa_uuid``, ``vigente_hasta``) plus the ``Cache-Control: no-store``
     header.
  2. mensualidad-vigente — when the plate has an open subscription at the
     branch, the handler returns ``{cobrar: false, motivo:
     'mensualidad_vigente'}`` and short-circuits the pricing pipeline.
  3. sin-iva-configurado — when ``impuestos`` has no row with
     ``nombre='IVA'`` vigente, the handler returns
     ``500 {"error": "iva_no_configurado"}`` (KD-IVA deployment
     blocker, owned by HU-F14.2 Parte II).
  4. sin-tarifa — when the ingreso exists but no ``tarifas_sucursal``
     row satisfies the bi-temporal predicate for the
     ``(uuid_sucursal, uuid_tipo_vehiculo)`` combination, the handler
     returns ``404 {"error": "tarifa_no_vigente"}`` (KD-3).

Issuer: ``operador-`` (precedent of all 5 existing handlers in
``api/v1/operacion.py``).
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
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.parametrize("app", ["sucursal"], indirect=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive ``datetime`` matching the DB column ``DateTime(timezone=False)``.

    PL/pgSQL's ``NOW()`` is also naive (timestamp without time zone),
    so naive datetimes are the right shape for ``vigente_desde``,
    ``vigente_hasta``, ``fecha_ingreso``.
    """
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate_tables(pg_dsn: str) -> None:
    """Truncate the tables each scenario seeds so tests don't bleed.

    Mirrors the HU-F1.1 / HU-F1.4 precedent: use the sync ``psycopg``
    connection with the superuser DSN. The list is scoped to exactly
    what this module touches — ``CASCADE`` follows FK edges into
    ``prod.salidas`` (FK from ``salidas.uuid_ingreso`` → ``ingreso``)
    so a clean slate is guaranteed regardless of the seed order.
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


async def _seed_empresa_sucursal(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
) -> None:
    """Insert one ``empresa`` + one ``sucursal`` row to satisfy FK chains.

    The operator token's ``sucursal`` claim and the tenant context are
    pinned to ``uuid_sucursal`` so the quotation's branch context is
    consistent with the token.
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
                nombre="Empresa Cotizar Test",
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
                nombre=f"Sucursal Cotizar {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"C{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Cotizar 1",
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
        await session.commit()


async def _seed_tipos(
    pg_engine,
    *,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    uuid_tipo_tarifa: uuid_lib.UUID,
) -> None:
    """Insert one ``tipos_vehiculo`` + one ``tipo_tarifa`` row.

    The PL/pgSQL function JOINs ``tipo_tarifa`` to read the modality
    (KD-2 hardcoded CASE). Seed both so the JOIN resolves. Both FKs
    on ``tarifas_sucursal`` (``uuid_tipo_vehiculo`` / ``uuid_tipo_tarifa``)
    are nullable in the ORM but the PL/pgSQL equality predicate
    ``t.uuid_tipo_vehiculo = v_ingreso.uuid_tipo_vehiculo`` requires
    matching non-NULL values to find a tariff.
    """
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
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
        await session.commit()


async def _seed_tarifa_vigente(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    uuid_tipo_tarifa: uuid_lib.UUID,
    valor: Decimal,
    valor_plena: Decimal,
) -> uuid_lib.UUID:
    """Insert one vigente ``tarifas_sucursal`` row and return its uuid."""
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        tarifa_uuid = uuid_lib.uuid4()
        session.add(
            TarifasSucursal(
                uuid=tarifa_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                uuid_tipo_tarifa=uuid_tipo_tarifa,
                valor=valor,
                valor_plena=valor_plena,
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
    return tarifa_uuid


async def _seed_iva(
    pg_engine,
    *,
    porcentaje: Decimal,
    nombre: str = "IVA",
) -> None:
    """Insert one vigente ``impuestos`` row with ``nombre='IVA'``."""
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Impuestos(
                uuid=uuid_lib.uuid4(),
                nombre=nombre,
                codigo=f"COD-{nombre}-{uuid_lib.uuid4().hex[:6]}",
                porcentaje=porcentaje,
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
        await session.commit()


async def _seed_ingreso(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID | None,
    placa: str | None,
    minutos_en_estacionamiento: int,
) -> uuid_lib.UUID:
    """Insert one ``ingreso`` row dated ``minutos_en_estacionamiento``
    minutes ago (so the PL/pgSQL's ``NOW() - fecha_ingreso`` returns
    the configured elapsed time).

    ``Ingreso`` is ``[L-E]`` (insert-only); the test does NOT need
    ``repo.event.record_event`` — a direct INSERT is sufficient and
    matches how the production code paths (after PR5 wired the helper)
    persist the row. The ``L-E`` trigger only blocks UPDATE/DELETE,
    not INSERT.
    """
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        ingreso_uuid = uuid_lib.uuid4()
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                placa=placa,
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


async def _seed_subscription_for_plate(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    placa: str,
    uuid_tipo_vehiculo: uuid_lib.UUID,
) -> None:
    """Insert one vigente ``clientes`` + ``subscripciones_cliente`` +
    ``vehiculos`` + ``subscripcion_vehiculos`` quadruple linked to
    ``placa``.

    Mirrors the precedent :func:`resolve_active_subscription_for_exit`
    (``api/v1/operacion.py:215-277``): open ``vigente_hasta`` on all
    three subscription rows, ``fecha_vencimiento`` either NULL or in
    the future. The ``clientes`` row is required because
    ``subscripciones_cliente.uuid_cliente`` has an FK to ``prod.clientes``.
    """
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
                nombre="Cliente Cotizar Test",
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


# ---------------------------------------------------------------------------
# Caso 1 — default-cotiza → desglose fiscal
# ---------------------------------------------------------------------------


async def test_cotizar_default_devuelve_desglose_fiscal(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """Happy path: a 89-minute ingreso (rounds up to 90 billed minutes
    via ``CEIL``) with ``valor=100, valor_plena=200, tipo='hora'`` and
    19% IVA seeded must return ``cobrar=true`` with the full breakdown.

    Math sanity (``unidad_minutos=60`` for ``hora``):

      ``tiempo_tar_plena = (200/100) * 60 = 120`` minutes
      ``CEIL(89 + drift) = 90`` (the drift between ``fecha_ingreso``
      written at test-setup time and the function's later ``NOW()``
      keeps ``tiempo_minutos`` strictly below 90, so ``CEIL`` lands on
      90, matching the design's ``CEIL(tiempo_minutos)`` formula).
      ``89.X < 120`` → ``total = 100 * 90 = 9000``
      ``iva = 9000 * 0.19 = 1710``
      ``subtotal = 9000 - 1710 = 7290``

    The response MUST also carry ``Cache-Control: no-store`` so no
    proxy can serve a stale quote (R8).
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_uuid)
    await _seed_tipos(
        pg_engine,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
    )
    tarifa_uuid = await _seed_tarifa_vigente(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
        valor=Decimal("100"),
        valor_plena=Decimal("200"),
    )
    await _seed_iva(pg_engine, porcentaje=Decimal("0.19"))
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        placa=None,
        minutos_en_estacionamiento=89,
    )

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    resp = await client.get(
        "/api/v1/operacion/cotizar",
        params={"uuid_ingreso": str(ingreso_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert resp.headers.get("Cache-Control") == "no-store", (
        f"Cache-Control: no-store missing on the happy-path response; "
        f"got {resp.headers.get('Cache-Control')!r}"
    )
    body = resp.json()
    assert body["cobrar"] is True
    assert Decimal(str(body["total"])) == Decimal("9000"), (
        f"total must be 100 * CEIL(89.X) = 9000 (89.X < tiempo_tar_plena=120); "
        f"got {body['total']!r}"
    )
    assert Decimal(str(body["iva"])) == Decimal("1710"), (
        f"iva must be 9000 * 0.19 = 1710; got {body['iva']!r}"
    )
    assert Decimal(str(body["subtotal"])) == Decimal("7290"), (
        f"subtotal must be total - iva = 7290; got {body['subtotal']!r}"
    )
    # ``tiempo_minutos`` is reported as the raw float (89 + drift). The
    # contract asserts the field is present and in the (89, 90) range —
    # not the integer-rounded value used by the pricing formula.
    assert 89.0 < float(body["tiempo_minutos"]) < 90.0, (
        f"tiempo_minutos must reflect the actual elapsed time (between 89 "
        f"and 90 minutes); got {body['tiempo_minutos']!r}"
    )
    assert body["tarifa_uuid"] == str(tarifa_uuid)
    assert "vigente_hasta" in body and body["vigente_hasta"]


# ---------------------------------------------------------------------------
# Caso 2 — mensualidad vigente → cobrar:false
# ---------------------------------------------------------------------------


async def test_cotizar_con_mensualidad_vigente_devuelve_cobrar_false(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """When the ingreso's plate has an active subscription at this
    branch, the handler short-circuits the pricing pipeline and
    returns ``{cobrar: false, motivo: 'mensualidad_vigente'}``
    (REQ-OPS-023).

    The tarifa row is also seeded to prove the short-circuit happens
    BEFORE the tarifa lookup — if the function evaluated the tarifa
    first, the test would still return 200 (tarifa exists) but with
    the breakdown, not with ``cobrar:false``.
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()
    placa = "MEN001"

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_uuid)
    await _seed_tipos(
        pg_engine,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
    )
    await _seed_tarifa_vigente(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
        valor=Decimal("100"),
        valor_plena=Decimal("200"),
    )
    await _seed_iva(pg_engine, porcentaje=Decimal("0.19"))
    await _seed_subscription_for_plate(
        pg_engine,
        uuid_sucursal=branch_uuid,
        placa=placa,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
    )
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        placa=placa,
        minutos_en_estacionamiento=90,
    )

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    resp = await client.get(
        "/api/v1/operacion/cotizar",
        params={"uuid_ingreso": str(ingreso_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert resp.headers.get("Cache-Control") == "no-store"
    body = resp.json()
    assert body == {
        "cobrar": False,
        "motivo": "mensualidad_vigente",
    }, (
        f"monthly-subscription short-circuit must return exactly "
        f"{{'cobrar': False, 'motivo': 'mensualidad_vigente'}}; got {body!r}"
    )


# ---------------------------------------------------------------------------
# Caso 3 — sin IVA → 500 iva_no_configurado (KD-IVA)
# ---------------------------------------------------------------------------


async def test_cotizar_sin_iva_configurado_devuelve_500(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """When ``impuestos`` has no vigente row with ``nombre='IVA'``, the
    handler returns ``500 {"error": "iva_no_configurado"}`` (KD-IVA).

    Deployment-blocker: this is the expected response in any environment
    where the ``IVA`` row has not been seeded. The exact recipe lives
    in ``design.md §4 KD-IVA`` and the housekeeping pre-F1.8 is owned
    by HU-F14.2 Parte II (the apply phase of THIS change does NOT
    seed — contractually).
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_uuid)
    await _seed_tipos(
        pg_engine,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
    )
    await _seed_tarifa_vigente(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
        valor=Decimal("100"),
        valor_plena=Decimal("200"),
    )
    # NOTE: deliberately NOT seeding an Impuestos row. The IVA lookup
    # inside PL/pgSQL MUST return zero rows → jsonb {error:'iva_no_configurado'}.
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        placa=None,
        minutos_en_estacionamiento=30,
    )

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    resp = await client.get(
        "/api/v1/operacion/cotizar",
        params={"uuid_ingreso": str(ingreso_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 500, f"got {resp.status_code}: {resp.text}"
    assert resp.headers.get("Cache-Control") == "no-store", (
        f"Cache-Control: no-store MUST be set on error responses too (R8); "
        f"got {resp.headers.get('Cache-Control')!r}"
    )
    body = resp.json()
    # FastAPI wraps ``HTTPException(detail=...)`` under ``{"detail": ...}``
    # in the JSON body (Starlette convention). Assert the typed-error
    # payload is reachable via ``body["detail"]["error"]``.
    assert body.get("detail", {}).get("error") == "iva_no_configurado", (
        f"missing-IVA must surface 'iva_no_configurado' under body.detail; "
        f"got {body!r}"
    )


# ---------------------------------------------------------------------------
# Caso 4 — sin tarifa vigente → 404 tarifa_no_vigente (KD-3)
# ---------------------------------------------------------------------------


async def test_cotizar_sin_tarifa_vigente_devuelve_404_tarifa_no_vigente(
    pg_engine, alembic_upgrade, mint_operador_jwt, client, pg_dsn
) -> None:
    """When the ingreso exists but no ``tarifas_sucursal`` row satisfies
    the bi-temporal predicate for ``(uuid_sucursal, uuid_tipo_vehiculo)``,
    the handler returns ``404 {"error": "tarifa_no_vigente"}`` (KD-3).

    Distinguishable from ``ingreso_no_encontrado`` (404 too) by the
    ``error`` field — clients can differentiate "wrong uuid" from
    "catalog gap".
    """
    await _truncate_tables(pg_dsn)

    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    tipo_vehiculo_uuid = uuid_lib.uuid4()
    tipo_tarifa_uuid = uuid_lib.uuid4()

    await _seed_empresa_sucursal(pg_engine, uuid_sucursal=branch_uuid)
    await _seed_tipos(
        pg_engine,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        uuid_tipo_tarifa=tipo_tarifa_uuid,
    )
    # NOTE: deliberately NOT seeding a TarifasSucursal row. The tarifa
    # lookup inside PL/pgSQL MUST return zero rows → jsonb
    # {error:'tarifa_no_vigente'}.
    await _seed_iva(pg_engine, porcentaje=Decimal("0.19"))
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch_uuid,
        uuid_tipo_vehiculo=tipo_vehiculo_uuid,
        placa=None,
        minutos_en_estacionamiento=30,
    )

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=branch_uuid)

    resp = await client.get(
        "/api/v1/operacion/cotizar",
        params={"uuid_ingreso": str(ingreso_uuid)},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch_uuid),
        },
    )

    assert resp.status_code == 404, f"got {resp.status_code}: {resp.text}"
    assert resp.headers.get("Cache-Control") == "no-store"
    body = resp.json()
    # FastAPI wraps ``HTTPException(detail=...)`` under ``{"detail": ...}``
    # in the JSON body (Starlette convention). Assert the typed-error
    # payload is reachable via ``body["detail"]["error"]``.
    assert body.get("detail", {}).get("error") == "tarifa_no_vigente", (
        f"missing-tarifa must surface 'tarifa_no_vigente' under body.detail; "
        f"got {body!r}"
    )


__all__ = [
    "test_cotizar_default_devuelve_desglose_fiscal",
    "test_cotizar_con_mensualidad_vigente_devuelve_cobrar_false",
    "test_cotizar_sin_iva_configurado_devuelve_500",
    "test_cotizar_sin_tarifa_vigente_devuelve_404_tarifa_no_vigente",
]
