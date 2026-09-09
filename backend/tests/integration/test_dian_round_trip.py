"""test_dian_round_trip.py — T-PR9-008.

``dispatch_factura_electronica_with_backoff`` against a REAL Postgres
database (rule: no mocked DB for the round trip — only the DIAN provider
HTTP transport is mocked, via ``httpx.MockTransport``, matching the
established pattern in ``tests/unit/dian/test_dispatcher.py``).

  - Success: a mocked-provider ``aceptado`` on the FIRST attempt populates
    ``cufe``/``estado`` on the single resulting ``envio_dian`` row.
  - Exhaustion: a mocked-provider that never resolves runs the full
    ``DIAN_MAX_RETRIES`` (6) attempts, chained via ``uuid_envio_padre``,
    then stamps the terminal ``estado='error'`` and raises ``alerta
    tipo_alerta='fe_provider_error'``.
"""
from __future__ import annotations

import asyncio
import itertools
import os
import uuid as uuid_lib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

# Import-time guard (T-PR11-07) — same pattern as tests/unit/dian/conftest.py.
_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian.cloud import dispatcher
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY

from parkos_core.models.L_E.factura_electronica import FacturaElectronica  # noqa: E402
from parkos_core.models.L_E.facturas import Facturas  # noqa: E402
from parkos_core.models.L_W.alerta import Alerta  # noqa: E402
from parkos_core.models.L_W.envio_dian import EnvioDian  # noqa: E402
from parkos_core.models.V.clientes import Clientes  # noqa: E402
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion  # noqa: E402

PROVIDER_URL = "http://test-dian-provider"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def token_path(tmp_path: Path) -> Path:
    path = tmp_path / "dian.token"
    path.write_text("test-bearer-token", encoding="utf-8")
    return path


async def _seed_factura_electronica(
    pg_engine: AsyncEngine, *, uuid_sucursal: uuid_lib.UUID
) -> uuid_lib.UUID:
    """Seed resolucion + facturas + clientes + one factura_electronica row."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        resolucion = ResolucionFacturacion(
            uuid=uuid_lib.uuid4(),
            uuid_sucursal=uuid_sucursal,
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
            uuid_sucursal=uuid_sucursal,
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
            apellido="Round Trip",
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
            uuid_sucursal=uuid_sucursal,
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
        return factura_electronica.uuid


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(_wrapped)
    monkeypatch.setattr(
        dispatcher.FactusProvider,
        "_default_session_factory",
        lambda _self: httpx.AsyncClient(transport=transport),
    )
    return seen


def _shim_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse EVERY ``asyncio.sleep`` (poll interval, per-attempt HTTP
    backoff, AND the outer ``DIAN_BACKOFF_SCHEDULE`` wait — up to 24h) to
    10ms so the exhaustion path runs in milliseconds, not a day."""
    real_sleep = asyncio.sleep

    async def _fast(_seconds: float) -> None:
        await real_sleep(0.01)

    monkeypatch.setattr(asyncio, "sleep", _fast)


@pytest.mark.asyncio
async def test_success_on_first_attempt_populates_cufe_and_estado(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    token_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factura_uuid = await _seed_factura_electronica(
        pg_engine, uuid_sucursal=seeded_sucursal_uuid
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"trackId": "track-ok"})
        return httpx.Response(200, json={"estado": "aceptado", "cufe": "cufe-ok-123"})

    _install_transport(monkeypatch, _handler)
    _shim_sleep(monkeypatch)

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        envio = await dispatcher.dispatch_factura_electronica_with_backoff(
            session,
            uuid_factura_electronica=factura_uuid,
            actor_uuid=uuid_lib.uuid4(),
            dian_provider_url=PROVIDER_URL,
            dian_token_path=token_path,
        )

    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_ACEPTADO
    assert envio.cufe == "cufe-ok-123"
    assert envio.estado == dispatcher.ESTADO_ACEPTADO
    assert envio.uuid_envio_padre is None  # first (and only) attempt

    async with Session() as session:
        rows = (
            await session.execute(
                select(EnvioDian).where(
                    EnvioDian.uuid_factura_electronica == factura_uuid
                )
            )
        ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_exhaustion_chains_six_attempts_and_raises_provider_error_alert(
    pg_engine: AsyncEngine,
    seeded_sucursal_uuid: uuid_lib.UUID,
    token_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factura_uuid = await _seed_factura_electronica(
        pg_engine, uuid_sucursal=seeded_sucursal_uuid
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"trackId": "track-stuck"})
        return httpx.Response(200, json={"estado": "en_proceso"})  # never resolves

    _install_transport(monkeypatch, _handler)
    _shim_sleep(monkeypatch)
    monkeypatch.setenv("PARKOS_DIAN_TIMEOUT_S", "0.001")
    monkeypatch.setenv("PARKOS_DIAN_RETRY_MAX", "0")  # one poll window per attempt

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        envio = await dispatcher.dispatch_factura_electronica_with_backoff(
            session,
            uuid_factura_electronica=factura_uuid,
            actor_uuid=uuid_lib.uuid4(),
            dian_provider_url=PROVIDER_URL,
            dian_token_path=token_path,
        )

    assert envio.estado == dispatcher.ESTADO_ERROR
    assert envio.respuesta_proveedor["estado_dian"] == dispatcher.ESTADO_ERROR

    async with Session() as session:
        chain = (
            await session.execute(
                select(EnvioDian)
                .where(EnvioDian.uuid_factura_electronica == factura_uuid)
                .order_by(EnvioDian.created_at.asc())
            )
        ).scalars().all()
        provider_error_alerts = (
            await session.execute(
                select(Alerta).where(
                    Alerta.uuid_arqueo == envio.uuid,
                    Alerta.tipo_alerta == "fe_provider_error",
                )
            )
        ).scalars().all()

    assert len(chain) == dispatcher.DIAN_MAX_RETRIES == 6
    # Each attempt (after the first) points at the PRIOR attempt's uuid.
    by_uuid = {row.uuid: row for row in chain}
    assert chain[0].uuid_envio_padre is None
    for prior, current in itertools.pairwise(chain):
        assert current.uuid_envio_padre == prior.uuid
        assert by_uuid[current.uuid_envio_padre] is prior

    # Exactly one budget-exhaustion alert (distinct from each individual
    # attempt's own ``dian_timeout`` alert, which ALSO references the
    # final attempt's envio.uuid — that per-attempt alert is expected,
    # not a duplicate of this one).
    assert len(provider_error_alerts) == 1
