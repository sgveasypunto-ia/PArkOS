"""test_consecutivo_concurrent_posts.py — REQ-OPS-193 / HU-INGRESO-SIN-PLACA.

Integration test for the ``POST /operacion/ingresos`` no-placa path
under concurrent load. Verifies that 10 simultaneous POSTs from
multiple "kioskos" on the same branch serialize cleanly through the
``assign_ingreso_consecutivo`` ``SELECT FOR UPDATE`` and produce 10
distinct ``BICI-NNNNNN-<uuid8>`` consecutivos (no collision, no gap,
n=1..10).

Pattern mirrors ``tests/integration/test_consecutivo_concurrent.py``
(REQ-OPS-071, the prior assign_consecutivo concurrent path) and
``tests/integration/test_ingreso_create_db.py`` (HU-F1.6 DB-level
fixture pattern).

Skipped under default pytest (no Docker daemon) per
``backend/tests/conftest.py:212``. Requires ``PARKOS_DOCKER_TEST=1``
plus a reachable ``parkos-branch-db`` with migration 0042 applied.
"""
from __future__ import annotations

import asyncio
import os
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest
from parkos_core.models.V.empresa import Empresa
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy.ext.asyncio import async_sessionmaker

_DOCKER_TEST = os.environ.get("PARKOS_DOCKER_TEST") == "1"

pytestmark = pytest.mark.skipif(
    not _DOCKER_TEST,
    reason=(
        "PARKOS_DOCKER_TEST=1 not set; skip consecutive counter "
        "concurrent integration test (requires live branch-db "
        "with migration 0042 applied)."
    ),
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_minimal(pg_engine, *, uuid_sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    """Seed empresa + sucursal + tipos_vehiculo for bicicleta.

    Returns the bicicleta tipo UUID.
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        empresa_uuid = uuid_lib.uuid4()
        session.add(
            Empresa(
                uuid=empresa_uuid,
                nombre="Empresa consec concurrent",
                nit=f"900{empresa_uuid.hex[:6]}",
                mensaje_bienvenida="hi",
                mensaje_salida="bye",
                regimen="comun",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
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
                nombre=f"Suc consec concurrent {uuid_sucursal.hex[:6]}",
                prefijo_nombre=f"CC{uuid_sucursal.hex[:4]}",
                ciudad="Bogota",
                direccion="Calle concurrent 1",
                telefono="+57111",
                horario="24/7",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )

        tipo_bici = uuid_lib.uuid4()
        session.add(
            TiposVehiculo(
                uuid=tipo_bici,
                tipo="bicicleta",
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )

        # Seed tarifa_sucursal so V3 (validar_tarifa_vigente) passes.
        from parkos_core.models.V.tarifas_sucursal import TarifasSucursal

        session.add(
            TarifasSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=tipo_bici,
                tarifa_hora=1000,
                tarifa_dia=10000,
                tarifa_mes=100000,
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )

        # Seed cantidad_vehiculos_sucursal so V1 (validar_cupo_disponible)
        # returns cupo_no_configurado=False.
        from parkos_core.models.V.cantidad_vehiculos_sucursal import (
            CantidadVehiculosSucursal,
        )

        session.add(
            CantidadVehiculosSucursal(
                uuid=uuid_lib.uuid4(),
                uuid_sucursal=uuid_sucursal,
                uuid_tipo_vehiculo=tipo_bici,
                cantidad=100,
                vigente_desde=_now(),
                vigente_hasta=None,
                estado="activo",
                created_at=_now(),
                created_by=None,
                sync_status="sincronizado",
                sync_timestamp=None,
                sync_attempts=0,
            )
        )

        await session.commit()
        return tipo_bici


async def _truncate(pg_dsn: str) -> None:
    """Best-effort TRUNCATE for a clean test state."""
    import psycopg

    with psycopg.connect(pg_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE prod.alerta, prod.ingreso, prod.salidas, "
            "prod.anulaciones, prod.cantidad_vehiculos_sucursal, "
            "prod.tarifas_sucursal, prod.tipos_vehiculo, "
            "prod.sucursal, prod.empresa CASCADE"
        )
        conn.commit()


# ---------------------------------------------------------------------------
# T-A4.3: 10 concurrent POSTs produce 10 distinct consecutivos (n=1..10).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_10_concurrent_posts_produce_10_distinct_consecutivos(
    pg_engine, pg_dsn: str, mint_operador_jwt, client
) -> None:
    """10 ``asyncio.gather`` POSTs with no-placa payload on the same (sucursal, bicicleta).

    The ``assign_ingreso_consecutivo`` ``SELECT FOR UPDATE`` must
    serialize the 10 calls so the 10 returned consecutivos are
    ``BICI-000001`` .. ``BICI-000010`` (no gap, no collision). Each
    response body carries a non-null ``consecutivo`` (REQ-OPS-197).
    """

    await _truncate(pg_dsn)
    sucursal_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    tipo_bici = await _seed_minimal(pg_engine, uuid_sucursal=sucursal_uuid)

    token = mint_operador_jwt(actor_uuid=actor_uuid, sucursal_uuid=sucursal_uuid)

    async def _one_post() -> dict[str, object]:
        resp = await client.post(
            "/api/v1/operacion/ingresos",
            json={"placa_presente": False, "uuid_tipo_vehiculo": str(tipo_bici)},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Sucursal-Context": str(sucursal_uuid),
                "Idempotency-Key": uuid_lib.uuid4().hex,
            },
        )
        assert resp.status_code == 201, (
            f"got {resp.status_code}: {resp.text}"
        )
        return resp.json()

    responses = await asyncio.gather(*[_one_post() for _ in range(10)])

    # Extract consecutivos and the n from each.
    consecutivos = [r["consecutivo"] for r in responses]
    ns = sorted(int(c.split("-")[1]) for c in consecutivos if c is not None)

    assert len(consecutivos) == 10, f"expected 10 consecutivos, got {len(consecutivos)}"
    assert all(c is not None for c in consecutivos), (
        f"every no-placa response must carry consecutivo; got: {consecutivos!r}"
    )
    assert len(set(consecutivos)) == 10, (
        f"consecutivos must be unique across 10 concurrent POSTs; got: "
        f"{consecutivos!r}"
    )
    assert ns == list(range(1, 11)), (
        f"expected consecutivos 1..10 with no gaps; got n={ns!r}"
    )

    # Format check: all start with BICI-NNNNNN-<uuid8>.
    for c in consecutivos:
        assert c.startswith("BICI-"), f"unexpected format: {c!r}"
        parts = c.split("-")
        assert len(parts) == 3, f"unexpected format (need 3 dash-separated parts): {c!r}"
        assert len(parts[1]) == 6, f"n must be 6 digits zero-padded: {c!r}"
        assert len(parts[2]) == 8, f"uuid8 suffix must be 8 hex chars: {c!r}"


__all__ = [
    "test_10_concurrent_posts_produce_10_distinct_consecutivos",
]