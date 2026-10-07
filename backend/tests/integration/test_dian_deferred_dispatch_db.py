"""DD1 - the deferred DIAN dispatch against a REAL Postgres and a fake provider.

Reproduces the sync push shape: the FE is inserted inside a SAVEPOINT of the
request session, the hooks queue the dispatch, and only the request-level
``commit()`` may start it. The provider is an ``httpx.MockTransport``.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian.cloud import dispatcher
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY

from parkos_core.dian.cloud.sweep import find_stale_pendientes  # noqa: E402
from parkos_core.models.L_E.factura_electronica import FacturaElectronica  # noqa: E402
from parkos_core.models.L_E.facturas import Facturas  # noqa: E402
from parkos_core.models.L_W.alerta import Alerta  # noqa: E402
from parkos_core.models.L_W.envio_dian import EnvioDian  # noqa: E402
from parkos_core.models.V.clientes import Clientes  # noqa: E402
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion  # noqa: E402
from parkos_core.sync.hooks import base as hook_base  # noqa: E402
from parkos_core.sync.hooks.impls import dian_dispatch_on_sync as hooks  # noqa: E402

# ``parkos_core.db.engine`` the NAME is shadowed by the lazy engine proxy.
engine_module = importlib.import_module("parkos_core.db.engine")

PROVIDER_URL = "http://test-dian-provider"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def token_path(tmp_path: Path) -> Path:
    path = tmp_path / "dian.token"
    path.write_text("test-bearer-token", encoding="utf-8")
    return path


@pytest.fixture
def provider_calls(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Fake provider: accepts every document at the first poll."""
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"trackId": "track-ok"})
        return httpx.Response(200, json={"estado": "aceptado", "cufe": "cufe-ok"})

    transport = httpx.MockTransport(_handler)
    monkeypatch.setattr(
        dispatcher.FactusProvider,
        "_default_session_factory",
        lambda _self: httpx.AsyncClient(transport=transport),
    )
    real_sleep = asyncio.sleep

    async def _fast(_seconds: float) -> None:
        await real_sleep(0.01)

    monkeypatch.setattr(asyncio, "sleep", _fast)
    return seen


@pytest.fixture(autouse=True)
def _clean_module_state(monkeypatch: pytest.MonkeyPatch, token_path: Path):
    hooks._INFLIGHT.clear()
    monkeypatch.setattr(hooks, "_DIAN_PROVIDER_URL", PROVIDER_URL)
    monkeypatch.setattr(hooks, "_DIAN_TOKEN_PATH", token_path)
    yield
    hooks._INFLIGHT.clear()


async def _seed_support(pg_engine: AsyncEngine, sucursal: uuid_lib.UUID) -> dict:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        resolucion = ResolucionFacturacion(
            uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal,
            numero_resolucion=f"RES-{uuid_lib.uuid4().hex[:8]}", prefijo="SETP",
            rango_desde=1, rango_hasta=999999999, fecha_resolucion=date.today(),
            fecha_inicio_vigencia=date.today(), fecha_fin_vigencia=None,
            vigente_desde=_now(), vigente_hasta=None, estado="activo",
            created_at=_now(), created_by=None, sync_status="pendiente",
            sync_timestamp=None, sync_attempts=0,
        )
        facturas = [
            Facturas(
                uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal, subtotal=10000,
                descuento=0, total=10000, uuid_ingreso=None, uuid_salida=None,
                created_at=_now(), created_by=None,
            )
            for _ in range(3)
        ]
        cliente = Clientes(
            uuid=uuid_lib.uuid4(), tipo_identificador="CC",
            numero_identificacion=str(uuid_lib.uuid4().int)[:10], nombre="Cliente",
            apellido="Diferido", vigente_desde=_now(), vigente_hasta=None,
            estado="activo", created_at=_now(), created_by=None,
            sync_status="pendiente", sync_timestamp=None, sync_attempts=0,
        )
        session.add_all([resolucion, *facturas, cliente])
        await session.commit()
        return {"res": resolucion.uuid, "cli": cliente.uuid, "facs": [f.uuid for f in facturas]}


def _fe(sucursal: uuid_lib.UUID, ids: dict, consecutivo: int, idx: int = 0) -> FacturaElectronica:
    return FacturaElectronica(
        uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal, uuid_factura=ids["facs"][idx],
        uuid_cliente=ids["cli"], uuid_resolucion_facturacion=ids["res"],
        prefijo="SETP", consecutivo=consecutivo, descuento=0,
        created_at=_now(), created_by=None,
    )


def _ctx(session, *, row_uuid=None, payload=None) -> hook_base.HookContext:
    return hook_base.HookContext(
        spec=SimpleNamespace(), payload=payload or {}, session=session,
        actor_uuid=uuid_lib.uuid4(), row_uuid=row_uuid,
    )


@pytest.mark.asyncio
async def test_dispatch_starts_only_after_the_outer_commit_and_sends_once(
    pg_engine: AsyncEngine, seeded_sucursal_uuid, provider_calls, monkeypatch,
) -> None:
    """FE inserted inside a SAVEPOINT; BOTH hooks (FE + branch envio pendiente)
    queue the same document. The task must see the FE and submit it once."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    monkeypatch.setitem(vars(engine_module), "SessionLocal", Session)
    ids = await _seed_support(pg_engine, seeded_sucursal_uuid)
    fe = _fe(seeded_sucursal_uuid, ids, consecutivo=1)

    async with Session() as push:
        async with push.begin_nested():
            push.add(fe)
            await push.flush()
            await hooks.dian_factura_electronica_dispatch_hook(_ctx(push, row_uuid=fe.uuid))
        async with push.begin_nested():
            await hooks.envio_dian_resume_hook(
                _ctx(push, payload={"estado": "pendiente", "uuid_factura_electronica": str(fe.uuid)})
            )
        # Savepoints released: NOTHING may have started yet.
        assert not hooks._BACKGROUND_TASKS
        assert provider_calls == []
        await push.commit()

    await asyncio.gather(*list(hooks._BACKGROUND_TASKS))

    async with Session() as check:
        chain = (
            await check.execute(
                select(EnvioDian).where(EnvioDian.uuid_factura_electronica == fe.uuid)
            )
        ).scalars().all()
    assert len(chain) == 1, "document dispatched twice (FE hook + envio hook)"
    assert chain[0].estado == dispatcher.ESTADO_ACEPTADO
    assert [r.method for r in provider_calls].count("POST") == 1


@pytest.mark.asyncio
async def test_second_dispatch_of_an_already_sent_document_is_refused(
    pg_engine: AsyncEngine, seeded_sucursal_uuid, provider_calls, token_path,
) -> None:
    """Cross-process guard: a later trigger (e.g. the sweep) finds the chain."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    ids = await _seed_support(pg_engine, seeded_sucursal_uuid)
    fe = _fe(seeded_sucursal_uuid, ids, consecutivo=2)
    async with Session() as s:
        s.add(fe)
        await s.commit()
    kwargs = dict(
        uuid_factura_electronica=fe.uuid, actor_uuid=uuid_lib.uuid4(),
        dian_provider_url=PROVIDER_URL, dian_token_path=token_path,
        skip_if_dispatched=True,
    )
    async with Session() as s:
        await dispatcher.dispatch_factura_electronica_with_backoff(s, **kwargs)
    async with Session() as s:
        with pytest.raises(dispatcher.DispatchAlreadyHandledError):
            await dispatcher.dispatch_factura_electronica_with_backoff(s, **kwargs)
    assert [r.method for r in provider_calls].count("POST") == 1


@pytest.mark.asyncio
async def test_failed_dispatch_is_alerted_and_stays_resumable(
    pg_engine: AsyncEngine, seeded_sucursal_uuid, provider_calls, monkeypatch,
) -> None:
    """A dispatch that dies before any envio exists (consecutivo out of range)
    leaves the branch pendiente row untouched, raises ONE dian_error alerta,
    and the sweep still lists the document until the failure cap."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    monkeypatch.setitem(vars(engine_module), "SessionLocal", Session)
    ids = await _seed_support(pg_engine, seeded_sucursal_uuid)
    fe = _fe(seeded_sucursal_uuid, ids, consecutivo=1_000_000_000)  # > rango_hasta
    old = _now() - timedelta(hours=1)
    async with Session() as s:
        s.add(fe)
        await s.flush()
        s.add(
            EnvioDian(
                uuid_sucursal=seeded_sucursal_uuid, uuid_factura_electronica=fe.uuid,
                payload={"prefijo": "SETP", "consecutivo": 1_000_000_000}, estado="pendiente",
                timestamp_evento=old, created_at=old, created_by=seeded_sucursal_uuid,
            )
        )
        await s.commit()

    await hooks._run_deferred(
        lambda session: dispatcher.dispatch_factura_electronica_with_backoff(
            session, uuid_factura_electronica=fe.uuid, actor_uuid=uuid_lib.uuid4(),
            dian_provider_url=PROVIDER_URL, dian_token_path=Path("/nonexistent"),
            skip_if_dispatched=True,
        ),
        ("fe", fe.uuid),
    )
    async with Session() as s:
        alerts = (
            await s.execute(
                select(Alerta).where(
                    Alerta.uuid_arqueo == fe.uuid, Alerta.tipo_alerta == "dian_error"
                )
            )
        ).scalars().all()
        pendiente = (
            await s.execute(
                select(EnvioDian).where(
                    EnvioDian.uuid_factura_electronica == fe.uuid,
                    EnvioDian.estado == "pendiente",
                )
            )
        ).scalars().all()
        resumable = await find_stale_pendientes(s, older_than=timedelta(minutes=10))
    assert len(alerts) == 1
    assert len(pendiente) == 1
    assert fe.uuid in resumable
    assert provider_calls == []


@pytest.mark.asyncio
async def test_sweep_selects_only_documents_without_a_cloud_chain(
    pg_engine: AsyncEngine, seeded_sucursal_uuid, provider_calls, token_path,
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    ids = await _seed_support(pg_engine, seeded_sucursal_uuid)
    old = _now() - timedelta(hours=1)
    fresh_fe, stale_fe, sent_fe = (
        _fe(seeded_sucursal_uuid, ids, n, idx=i) for i, n in enumerate((4, 5, 6))
    )
    async with Session() as s:
        s.add_all([fresh_fe, stale_fe, sent_fe])
        await s.flush()
        for fe, created in ((fresh_fe, _now()), (stale_fe, old), (sent_fe, old)):
            s.add(
                EnvioDian(
                    uuid_sucursal=seeded_sucursal_uuid, uuid_factura_electronica=fe.uuid,
                    payload={"prefijo": "SETP"}, estado="pendiente",
                    timestamp_evento=created, created_at=created,
                    created_by=seeded_sucursal_uuid,
                )
            )
        await s.commit()
    async with Session() as s:
        await dispatcher.dispatch_factura_electronica_with_backoff(
            s, uuid_factura_electronica=sent_fe.uuid, actor_uuid=uuid_lib.uuid4(),
            dian_provider_url=PROVIDER_URL, dian_token_path=token_path,
            skip_if_dispatched=True,
        )
    async with Session() as s:
        found = await find_stale_pendientes(s, older_than=timedelta(minutes=10), limit=50)
    assert stale_fe.uuid in found
    assert fresh_fe.uuid not in found  # not stale yet
    assert sent_fe.uuid not in found  # a cloud chain owns it
