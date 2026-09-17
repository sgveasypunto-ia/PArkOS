"""HU-F1.7 / D0 -- DB integration tests for ``POST /operacion/salidas``.

Runs against a real Postgres (testcontainers via ``PARKOS_DOCKER_TEST=1``,
``pg_engine`` fixture) + ``alembic upgrade head`` session fixture (must
include migration 0026 with the IVA seed + 2 alert_types + partial unique
index ``one_exit_per_ingreso``).

Verifies:
  - R5: salida + alerta INSERT commit atomico (single ``session.commit()``)
  - R4: partial unique index ``one_exit_per_ingreso`` rejects the second
        concurrent insert with ``IntegrityError`` mapped to 409
  - KD-IVA: when ``prod.impuestos`` has no IVA row, salida returns 500
            (``iva_no_configurado``); post-migration-0026 the IVA row is
            seeded inline, so the happy path uses the same fixture
            (delete the row in the KD-IVA test only)

Pattern: F1.6 ``test_ingreso_create_db.py`` (3 tests, session-scope
``pg_engine``, ``mint_operador_jwt`` + ``client`` + ``pg_dsn`` fixtures).
"""
from __future__ import annotations

import json
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from parkos_core.models.A.salidas import Salidas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.cantidad_vehiculos_sucursal import (
    CantidadVehiculosSucursal,
)
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.impuestos import Impuestos
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tarifas_sucursal import TarifasSucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate(pg_dsn: str) -> None:
    """Truncate every table the F1.7 test path touches (in dependency
    order; CASCADE so the partial unique index does not block TRUNCATE)."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.salidas, prod.ingreso, "
            "prod.anulaciones, prod.tarifas_sucursal, "
            "prod.cantidad_vehiculos_sucursal, prod.tipos_vehiculo, "
            "prod.subscripciones_cliente, prod.subscripcion_vehiculos, "
            "prod.vehiculos, prod.impuestos, prod.sucursal, prod.empresa "
            "CASCADE"
        )
        conn.commit()


async def _reseed_iva(pg_engine, *, porcentaje: float = 0.19) -> None:
    """Re-seed the ``prod.impuestos`` IVA row after a KD-IVA test deleted
    it. Mirrors the migration 0026 inline-seed exactly (codigo='IVA',
    porcentaje=0.19, vigente_hasta=NULL, estado='activo'). Idempotent
    because the migration uses ``ON CONFLICT (codigo, vigente_desde) DO
    NOTHING``."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    now = _now_naive()
    async with Session() as session:
        await session.execute(
            text(
                "INSERT INTO prod.impuestos "
                "(uuid, codigo, nombre, porcentaje, "
                " vigente_desde, vigente_hasta, estado, created_at) "
                "VALUES (gen_random_uuid(), 'IVA', 'IVA', :porcentaje, "
                " :ahora, NULL, 'activo', :ahora) "
                "ON CONFLICT (codigo, vigente_desde) DO NOTHING"
            ),
            {"porcentaje": porcentaje, "ahora": now},
        )
        await session.commit()


async def _seed_branch(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> None:
    """Seed ``prod.empresa`` + ``prod.sucursal`` for the test branch."""
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="F1.7 Test SA",
                nit=f"901{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hi",
                mensaje_salida="bye",
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
                nombre=f"Suc F1.7 {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"F{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle F1.7",
                telefono="+57111111",
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


async def _seed_tarifa_vigente(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_auto: uuid_lib.UUID,
    valor_hora: float = 5000.0,
) -> None:
    """Seed a vigente ``prod.tarifas_sucursal`` row (F1.8 KD-1 bi-temporal
    canonical predicate: vigente_desde <= NOW() AND (vigente_hasta IS NULL
    OR vigente_hasta > NOW()) AND estado='activo')."""
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            TarifasSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_auto,
                valor_hora=valor_hora,
                vigente_desde=now - timedelta(days=1),
                vigente_hasta=None,
                estado="activo",
                created_at=now - timedelta(days=1),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        session.add(
            TiposVehiculo(
                uuid=uuid_tipo_auto,
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
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_auto,
                cantidad=50,
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


async def _seed_ingreso(
    pg_engine,
    *,
    placa: str,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_auto: uuid_lib.UUID,
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None,
) -> uuid_lib.UUID:
    """Seed an active ``prod.ingreso`` row (no prior salida, no anulada)."""
    now = _now_naive()
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_auto,
                placa=placa,
                uuid_subscripcion_cliente=uuid_subscripcion_cliente,
                fecha_ingreso=now - timedelta(hours=2),
                observaciones=None,
                created_at=now - timedelta(hours=2),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


# ---------------------------------------------------------------------------
# T1: salida + alerta committed in same TX (R5 -- KD-S7 lock continuity)
# ---------------------------------------------------------------------------


async def test_insert_salida_con_alerta_forzado_atomico(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """R5 verification: tarifa no vigente (V5 bypass) emits a single
    alerta in the same TX as the salida INSERT. Both rows MUST commit in
    ONE ``session.commit()`` (KD-S7 lock continuity invariant).

    Bypass reason chosen: ``tarifa_no_vigente`` -- a 422 is rejected,
    so we need to (a) DELETE the vigente tarifa first, then (b) POST with
    ``forzado=true`` + prefix + motivo >=10 chars. The handler then runs
    Step 7 (cotizar fails), Step 8 (INSERT salida), Step 9 (alerta
    ``tarifa_vigente_forzado`` + single commit). Both rows must be
    visible after the 201 response.
    """
    await _truncate(pg_dsn)
    await _reseed_iva(pg_engine)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_tarifa_vigente(
        pg_engine, uuid_sucursal=branch, uuid_tipo_auto=tipo_auto
    )
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        placa="ABC123",
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
    )

    # Drop the tarifa so V5 (``cotizar_para_salida``) raises
    # ``TarifaNoVigente`` and forces the V5 bypass path.
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE prod.tarifas_sucursal SET vigente_hasta = NOW() "
            "WHERE uuid_sucursal = %s",
            (str(branch),),
        )
        conn.commit()

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    motivo = "tarifa en renegociacion con operador 2026-09-14"
    resp = await client.post(
        "/api/v1/operacion/salidas",
        json={
            "uuid_ingreso": str(ingreso_uuid),
            "placa": "ABC123",
            "forzado": True,
            "observaciones": f"[FORZADO: {motivo}]",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 201, f"got {resp.status_code}: {resp.text}"

    dsn = str(pg_engine.url).replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # Salida inserted
        cur.execute(
            "SELECT count(*) FROM prod.salidas WHERE uuid_ingreso = %s",
            (str(ingreso_uuid),),
        )
        salida_count = cur.fetchone()[0]
        # Alerta inserted in same TX
        cur.execute(
            "SELECT tipo_alerta, datos_nuevos FROM prod.alerta "
            "WHERE uuid_sucursal = %s "
            "AND tipo_alerta = 'tarifa_vigente_forzado'",
            (str(branch),),
        )
        alerta_row = cur.fetchone()

    assert salida_count == 1, "salida INSERT must succeed"
    assert alerta_row is not None, (
        "alerta INSERT must share the same commit (R5)"
    )
    payload = alerta_row[1]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["motivo"] == motivo, (
        f"alerta motivo mismatch: {payload.get('motivo')!r} != {motivo!r}"
    )


# ---------------------------------------------------------------------------
# T2: partial unique index ``one_exit_per_ingreso`` race-closes TOCTOU (R4)
# ---------------------------------------------------------------------------


async def test_partial_unique_index_emite_409(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """R4: the partial unique index ``one_exit_per_ingreso`` (migration
    0026 Op 4) closes the TOCTOU race on V1 EXISTS. After a successful
    salida, a SECOND ``POST /operacion/salidas`` for the same
    ``uuid_ingreso`` MUST return 409 ``salida_duplicada`` (mapped from
    ``IntegrityError``).

    Note: the partial index excludes anuladas (``WHERE NOT EXISTS ...``)
    so re-creation post-anulacion is preserved; that branch is owned by
    Fase 7 (anulación workflow) and is out of scope here.
    """
    await _truncate(pg_dsn)
    await _reseed_iva(pg_engine)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_tarifa_vigente(
        pg_engine, uuid_sucursal=branch, uuid_tipo_auto=tipo_auto
    )
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        placa="ABC123",
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch),
    }

    # First POST: 201
    resp_first = await client.post(
        "/api/v1/operacion/salidas",
        json={"uuid_ingreso": str(ingreso_uuid), "placa": "ABC123"},
        headers=headers,
    )
    assert resp_first.status_code == 201, (
        f"first POST must succeed; got {resp_first.status_code}: "
        f"{resp_first.text}"
    )

    # Second POST for the same uuid_ingreso: 409 salida_duplicada
    resp_second = await client.post(
        "/api/v1/operacion/salidas",
        json={"uuid_ingreso": str(ingreso_uuid), "placa": "ABC123"},
        headers=headers,
    )
    assert resp_second.status_code == 409, (
        f"second POST must hit partial unique index -> 409; "
        f"got {resp_second.status_code}: {resp_second.text}"
    )
    body = resp_second.json()
    detail = body.get("detail", body)
    assert detail["error"] == "salida_duplicada", (
        f"409 discriminator must be 'salida_duplicada'; got {detail!r}"
    )
    assert detail["uuid_ingreso"] == str(ingreso_uuid)

    # Sanity: only ONE salida row for this uuid_ingreso (partial index
    # prevented the second INSERT from committing).
    import psycopg

    dsn = str(pg_engine.url).replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM prod.salidas WHERE uuid_ingreso = %s",
            (str(ingreso_uuid),),
        )
        salida_count = cur.fetchone()[0]
    assert salida_count == 1, (
        "partial unique index must reject the second INSERT; "
        f"got {salida_count} salida rows for the same uuid_ingreso"
    )


# ---------------------------------------------------------------------------
# T3: KD-IVA path -- IVA row absent => 500 iva_no_configurado
# ---------------------------------------------------------------------------


async def test_iva_no_sembrado_retorna_500(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """KD-IVA: when ``prod.impuestos`` has NO ``codigo='IVA'`` row, the
    F1.8 PL/pgSQL ``prod.calcular_cotizacion`` raises ``IVANoConfigurado``
    and the handler MUST map it to ``500 iva_no_configurado`` (per design
    §3 KD-IVA + Step 7 handler chain).

    Setup: delete the IVA row seeded by migration 0026. The
    tarifa + ingreso + branch chain is otherwise complete. POST without
    ``forzado`` (so the rejection path runs, NOT the bypass path).
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo_auto = uuid_lib.uuid4()

    # Re-seed the tables EXCEPT impuestos.IVA -- the handler path needs
    # tarifas_vigente (Step 7) but the IVA row is the missing piece.
    now = _now_naive()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await session.execute(
            text("DELETE FROM prod.impuestos WHERE codigo = 'IVA'")
        )
        await session.commit()

    await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_tarifa_vigente(
        pg_engine, uuid_sucursal=branch, uuid_tipo_auto=tipo_auto
    )
    ingreso_uuid = await _seed_ingreso(
        pg_engine,
        placa="ABC123",
        uuid_sucursal=branch,
        uuid_tipo_auto=tipo_auto,
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.post(
        "/api/v1/operacion/salidas",
        json={"uuid_ingreso": str(ingreso_uuid), "placa": "ABC123"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Sucursal-Context": str(branch),
        },
    )
    assert resp.status_code == 500, (
        f"missing IVA row must yield 500 iva_no_configurado; "
        f"got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["error"] == "iva_no_configurado", (
        f"500 discriminator must be 'iva_no_configurado'; got {detail!r}"
    )

    # Sanity: NO salida was inserted (Step 8 runs AFTER Step 7's IVA
    # check; an IVANoConfigurado raise aborts the handler before INSERT).
    import psycopg

    dsn = str(pg_engine.url).replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM prod.salidas")
        salida_count = cur.fetchone()[0]
    assert salida_count == 0, (
        "IVANoConfigurado must abort the handler BEFORE the salida INSERT; "
        f"got {salida_count} salida rows"
    )

    # Re-seed IVA so the rest of the integration suite is not poisoned.
    await _reseed_iva(pg_engine)


__all__ = [
    "test_insert_salida_con_alerta_forzado_atomico",
    "test_partial_unique_index_emite_409",
    "test_iva_no_sembrado_retorna_500",
]
