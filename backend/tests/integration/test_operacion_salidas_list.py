"""Integration tests for the read-only ``GET /operacion/salidas`` views.

PR A — the admin list/detail screens need a way to read exits before any UI
exists. ``prod.salidas`` is an ``[A]`` append-only EVENT table with no
vehicle identity on it, so these endpoints are the first read path that has
to join ``prod.ingreso`` to answer "which vehicle left, and when".

What these tests pin down, and why each one exists:

1. ``uuid_sucursal`` filter — the tenant selector is the primary control on
   the screen; a leak here shows one branch's exits under another.
2. ``placa`` filter via the join — proves the plate really comes from
   ``prod.ingreso`` and is not silently ignored (an unmapped ``Ingreso.placa``
   reference would raise, so this guards the reverse: that the filter is wired
   and not a no-op).
3. Ordering — ``fecha_salida DESC NULLS LAST``. ``fecha_salida`` is nullable
   and Postgres sorts NULLs FIRST under DESC; without the explicit NULLS LAST
   undated exits float to the top of a recency list.
4. A salida with ``uuid_ingreso = NULL`` still appears — this is the LEFT
   JOIN test. An INNER JOIN would hide it and under-report occupancy, a
   failure that looks like correct behaviour.
5. Detail endpoint returns the joined columns, and 404s on an unknown uuid.
6. An invalid/absent JWT is rejected — read-only endpoints are still the
   easiest thing to expose by accident.

Pattern: ``test_operacion_ingresos_list_activo.py`` (F11).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from parkos_core.models.A.salidas import Salidas
from parkos_core.models.L_E.ingreso import Ingreso
from parkos_core.models.V.cantidad_vehiculos_sucursal import (
    CantidadVehiculosSucursal,
)
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _truncate(pg_dsn: str) -> None:
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, "
            "prod.anulaciones, prod.cantidad_vehiculos_sucursal, "
            "prod.tipos_vehiculo, prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


async def _seed_branch(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    """Seed empresa/sucursal/tipo_vehiculo/cupo. Returns uuid_tipo_vehiculo."""
    now = _now_naive()
    tipo_auto = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Salidas List Test SA",
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
                nombre=f"Suc List {uuid_sucursal.hex[:8]}",
                prefijo_nombre=f"L{uuid_sucursal.hex[:6]}",
                ciudad="Bogota",
                direccion="Calle Lista",
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
        session.add(
            TiposVehiculo(
                uuid=tipo_auto,
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
        await session.commit()
    async with Session() as session:
        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=tipo_auto,
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
    return tipo_auto


async def _seed_ingreso(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_tipo_vehiculo: uuid_lib.UUID,
    placa: str | None = None,
    consecutivo: str | None = None,
) -> uuid_lib.UUID:
    now = _now_naive()
    ingreso_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Ingreso(
                uuid=ingreso_uuid,
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=uuid_tipo_vehiculo,
                placa=placa,
                consecutivo=consecutivo,
                uuid_subscripcion_cliente=None,
                fecha_ingreso=now,
                observaciones=None,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return ingreso_uuid


async def _seed_salida(
    pg_engine,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_ingreso: uuid_lib.UUID | None,
    fecha_salida: datetime | None = None,
) -> uuid_lib.UUID:
    """Seed one ``prod.salidas`` row.

    ``uuid_ingreso`` accepts ``None`` on purpose: the table declares it
    nullable and the LEFT JOIN behaviour for that case is under test.
    ``fecha_salida`` accepts ``None`` for the NULLS LAST ordering test.
    """
    now = _now_naive()
    salida_uuid = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(
            Salidas(
                uuid=salida_uuid,
                fecha_retencion_hasta=now.date(),
                uuid_sucursal=uuid_sucursal,
                uuid_ingreso=uuid_ingreso,
                fecha_salida=fecha_salida,
                created_at=now,
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )
        await session.commit()
    return salida_uuid


def _auth(token: str, branch: uuid_lib.UUID) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Sucursal-Context": str(branch),
    }


async def test_list_filtra_por_sucursal_y_ordena_por_fecha_desc(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T1: only the requested branch's exits, most recent first."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    other_branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo = await _seed_branch(pg_engine, uuid_sucursal=branch)
    await _seed_branch(pg_engine, uuid_sucursal=other_branch)

    ing_a = await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="AAA111"
    )
    ing_b = await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="BBB222"
    )
    base = _now_naive()
    antigua = await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing_a,
        fecha_salida=base - timedelta(hours=3),
    )
    reciente = await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing_b,
        fecha_salida=base - timedelta(minutes=5),
    )
    # Belongs to another tenant: must never appear.
    ing_otro = await _seed_ingreso(
        pg_engine, uuid_sucursal=other_branch, uuid_tipo_vehiculo=tipo, placa="ZZZ999"
    )
    await _seed_salida(
        pg_engine,
        uuid_sucursal=other_branch,
        uuid_ingreso=ing_otro,
        fecha_salida=base - timedelta(minutes=1),
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.get(
        f"/api/v1/operacion/salidas?uuid_sucursal={branch}",
        headers=_auth(token, branch),
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    uuids = [item["uuid"] for item in resp.json()]
    assert uuids == [str(reciente), str(antigua)], "expected newest-first, own-branch only"


async def test_list_filtra_por_placa_traves_del_join(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T2: ``placa`` resolves through the joined ``prod.ingreso`` row."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo = await _seed_branch(pg_engine, uuid_sucursal=branch)

    ing_hit = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="XYZ789",
        consecutivo="C-0001",
    )
    await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="OTHER11"
    )
    hit = await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing_hit,
        fecha_salida=_now_naive(),
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.get(
        f"/api/v1/operacion/salidas?uuid_sucursal={branch}&placa=XYZ789",
        headers=_auth(token, branch),
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert len(body) == 1, f"plate filter did not narrow the list: {body}"
    assert body[0]["uuid"] == str(hit)
    # The joined columns the UI needs without a second round-trip.
    assert body[0]["placa"] == "XYZ789"
    assert body[0]["consecutivo"] == "C-0001"
    assert body[0]["uuid_ingreso"] == str(ing_hit)


async def test_list_incluye_salida_sin_ingreso_y_al_final_las_sin_fecha(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T3/T4: LEFT JOIN keeps an orphan exit; NULLS LAST sinks undated rows.

    Both halves matter for the same reason: an exit that disappears from,
    or floats to the top of, the list is an occupancy lie the operator
    cannot detect.
    """
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo = await _seed_branch(pg_engine, uuid_sucursal=branch)

    ing = await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="KEEP01"
    )
    dated = await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing,
        fecha_salida=_now_naive(),
    )
    # One non-annulled salida per ingreso (``fn_salidas_one_exit_per_ingreso``):
    # the undated exit belongs to an ingreso of its own.
    ing_undated = await _seed_ingreso(
        pg_engine, uuid_sucursal=branch, uuid_tipo_vehiculo=tipo, placa="KEEP02"
    )
    undated = await _seed_salida(
        pg_engine, uuid_sucursal=branch, uuid_ingreso=ing_undated, fecha_salida=None
    )
    orphan = await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=None,
        fecha_salida=_now_naive(),
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.get(
        f"/api/v1/operacion/salidas?uuid_sucursal={branch}",
        headers=_auth(token, branch),
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    body = resp.json()
    uuids = [item["uuid"] for item in body]

    # The orphan (LEFT JOIN must not drop it) and the undated row are both
    # present; the undated one sorts after every dated row.
    assert str(orphan) in uuids, "LEFT JOIN dropped a salida with no ingreso"
    assert str(dated) in uuids
    assert len(body) == 3, f"expected 3 salidas, got {len(body)}"
    assert uuids[-1] == str(undated), "NULL fecha_salida was not sorted last"

    orphan_row = next(item for item in body if item["uuid"] == str(orphan))
    assert orphan_row["uuid_ingreso"] is None
    assert orphan_row["placa"] is None


async def test_list_vacia_devuelve_lista_en_blanco(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T5: no rows is ``[]``, never 404 and never null."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    await _seed_branch(pg_engine, uuid_sucursal=branch)

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    resp = await client.get(
        f"/api/v1/operacion/salidas?uuid_sucursal={branch}",
        headers=_auth(token, branch),
    )
    assert resp.status_code == 200, f"got {resp.status_code}: {resp.text}"
    assert resp.json() == []


async def test_detail_devuelve_join_y_404_para_uuid_desconocido(
    pg_engine, mint_operador_jwt, client, pg_dsn
) -> None:
    """T6: detail echoes the joined columns; unknown uuid is a typed 404."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    tipo = await _seed_branch(pg_engine, uuid_sucursal=branch)

    ing = await _seed_ingreso(
        pg_engine,
        uuid_sucursal=branch,
        uuid_tipo_vehiculo=tipo,
        placa="DET111",
        consecutivo="C-0009",
    )
    salida = await _seed_salida(
        pg_engine,
        uuid_sucursal=branch,
        uuid_ingreso=ing,
        fecha_salida=_now_naive(),
    )

    token = mint_operador_jwt(actor_uuid=actor, sucursal_uuid=branch)
    ok = await client.get(
        f"/api/v1/operacion/salidas/{salida}",
        headers=_auth(token, branch),
    )
    assert ok.status_code == 200, f"got {ok.status_code}: {ok.text}"
    detail = ok.json()
    assert detail["uuid"] == str(salida)
    assert detail["uuid_sucursal"] == str(branch)
    assert detail["uuid_ingreso"] == str(ing)
    assert detail["placa"] == "DET111"
    assert detail["consecutivo"] == "C-0009"

    missing_uuid = uuid_lib.uuid4()
    missing = await client.get(
        f"/api/v1/operacion/salidas/{missing_uuid}",
        headers=_auth(token, branch),
    )
    assert missing.status_code == 404, f"got {missing.status_code}: {missing.text}"
    assert missing.json()["detail"]["error"] == "salida_no_encontrada"
    assert missing.json()["detail"]["uuid_salida"] == str(missing_uuid)


async def test_list_y_detail_rechazan_jwt_invalido(client, pg_dsn) -> None:
    """T7: read-only does not mean unauthenticated."""
    await _truncate(pg_dsn)
    branch = uuid_lib.uuid4()

    anonymous = await client.get(f"/api/v1/operacion/salidas?uuid_sucursal={branch}")
    assert anonymous.status_code == 401, (
        f"unauthenticated list got {anonymous.status_code}: {anonymous.text}"
    )

    garbage = await client.get(
        f"/api/v1/operacion/salidas?uuid_sucursal={branch}",
        headers=_auth("not-a-jwt", branch),
    )
    assert garbage.status_code == 401, (
        f"bad-token list got {garbage.status_code}: {garbage.text}"
    )

    garbage_detail = await client.get(
        f"/api/v1/operacion/salidas/{uuid_lib.uuid4()}",
        headers=_auth("not-a-jwt", branch),
    )
    assert garbage_detail.status_code == 401, (
        f"bad-token detail got {garbage_detail.status_code}: {garbage_detail.text}"
    )
