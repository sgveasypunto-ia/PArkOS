"""DIAN1 - the cloud DIAN dispatch against the REAL restricted role (``rol_app``).

``envio_dian`` is append-only for ``rol_app`` (``REVOKE UPDATE, DELETE`` except
a narrow column grant). The dispatcher used to assign ``envio.estado`` /
``respuesta_proveedor`` on the loaded ORM row and commit, which the database
rejects (``permission denied for table envio_dian``): in production every
terminal outcome was lost, the chain stayed ``activo`` forever and no
``dian_timeout`` alerta was raised. Every other DB test of the dispatcher runs
as the superuser, which is allowed to UPDATE, so none of them could notice.

Here every session runs ``SET LOCAL ROLE rol_app``; a fake provider stands in
for Factus. The contract: a dispatch only INSERTS rows chained through
``uuid_envio_padre``; the LAST row of the chain is the state.
"""
from __future__ import annotations

import asyncio
import os
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    from parkos_core.dian import cloud_router
    from parkos_core.dian.cloud import dispatcher
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY

from parkos_core.dian.cloud.sweep import find_stale_inflight  # noqa: E402
from parkos_core.models.A.factura_detalle import FacturaDetalle  # noqa: E402
from parkos_core.models.A.factura_impuestos import FacturaImpuestos  # noqa: E402
from parkos_core.models.L_E.factura_electronica import FacturaElectronica  # noqa: E402
from parkos_core.models.L_E.facturas import Facturas  # noqa: E402
from parkos_core.models.L_W.alerta import Alerta  # noqa: E402
from parkos_core.models.L_W.envio_dian import EnvioDian  # noqa: E402
from parkos_core.models.V.clientes import Clientes  # noqa: E402
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion  # noqa: E402

PROVIDER_URL = "http://test-dian-provider"
_CONSECUTIVO = iter(range(5000, 6000))


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def token_path(tmp_path: Path) -> Path:
    path = tmp_path / "dian.token"
    path.write_text("test-bearer-token", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    real_sleep = asyncio.sleep

    async def _fast(_seconds: float) -> None:
        await real_sleep(0.001)

    monkeypatch.setattr(asyncio, "sleep", _fast)
    monkeypatch.setenv("PARKOS_DIAN_TIMEOUT_S", "0.001")
    monkeypatch.setenv("PARKOS_DIAN_RETRY_MAX", "1")


def _install_provider(monkeypatch: pytest.MonkeyPatch, *, poll: dict | None, post_status: int = 200):
    """Fake Factus. ``poll=None`` means the poll never leaves ``en_proceso``."""
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            if post_status != 200:
                return httpx.Response(post_status, json={"error": "bad request"})
            return httpx.Response(200, json={"trackId": "track-db"})
        return httpx.Response(200, json=poll or {"estado": "en_proceso"})

    transport = httpx.MockTransport(_handler)
    monkeypatch.setattr(
        dispatcher.FactusProvider,
        "_default_session_factory",
        lambda _self: httpx.AsyncClient(transport=transport),
    )
    return seen


@pytest_asyncio.fixture
async def app_sessions(pg_async_dsn: str, pg_engine: AsyncEngine):
    """Sessions that run as ``rol_app``, the production application role."""
    engine = create_async_engine(pg_async_dsn, pool_pre_ping=True)

    @event.listens_for(engine.sync_engine, "begin")
    def _as_rol_app(conn) -> None:  # noqa: ANN001
        conn.exec_driver_sql("SET LOCAL ROLE rol_app")

    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def admin_sessions(pg_engine: AsyncEngine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)


async def _seed_fe(admin_sessions, sucursal: uuid_lib.UUID) -> uuid_lib.UUID:
    async with admin_sessions() as session:
        resolucion = ResolucionFacturacion(
            uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal,
            numero_resolucion=f"RES-{uuid_lib.uuid4().hex[:8]}", prefijo="SETP",
            rango_desde=1, rango_hasta=999999999, fecha_resolucion=date.today(),
            fecha_inicio_vigencia=date.today(), fecha_fin_vigencia=None,
            vigente_desde=_now(), vigente_hasta=None, estado="activo",
            created_at=_now(), created_by=None, sync_status="pendiente",
            sync_timestamp=None, sync_attempts=0,
        )
        factura = Facturas(
            uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal, subtotal=10000,
            descuento=0, total=10000, uuid_ingreso=None, uuid_salida=None,
            created_at=_now(), created_by=None,
        )
        cliente = Clientes(
            uuid=uuid_lib.uuid4(), tipo_identificador="CC",
            numero_identificacion=str(uuid_lib.uuid4().int)[:10], nombre="Cliente",
            apellido="Append", vigente_desde=_now(), vigente_hasta=None,
            estado="activo", created_at=_now(), created_by=None,
            sync_status="pendiente", sync_timestamp=None, sync_attempts=0,
        )
        session.add_all([resolucion, factura, cliente])
        await session.flush()
        # A real invoice always carries lines + tax detail: the UBL is built
        # from them and the dispatcher refuses an invoice without lines.
        session.add_all(
            [
                FacturaDetalle(
                    uuid_factura=factura.uuid, uuid_sucursal=sucursal,
                    concepto="servicio", cantidad=1, valor_unitario=8403.36,
                    subtotal=8403.36, fecha_retencion_hasta=date.today(),
                ),
                FacturaImpuestos(
                    uuid_factura=factura.uuid, uuid_sucursal=sucursal,
                    base_calculo=8403.36, porcentaje_aplicado=0.19, valor=1596.64,
                    fecha_retencion_hasta=date.today(),
                ),
            ]
        )
        await session.flush()
        fe = FacturaElectronica(
            uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal, uuid_factura=factura.uuid,
            uuid_cliente=cliente.uuid, uuid_resolucion_facturacion=resolucion.uuid,
            prefijo="SETP", consecutivo=next(_CONSECUTIVO), descuento=0,
            created_at=_now(), created_by=None,
        )
        session.add(fe)
        await session.commit()
        return fe.uuid


async def _chain(admin_sessions, fe_uuid: uuid_lib.UUID) -> list[EnvioDian]:
    async with admin_sessions() as session:
        rows = (
            await session.execute(
                select(EnvioDian)
                .where(EnvioDian.uuid_factura_electronica == fe_uuid)
                .order_by(EnvioDian.timestamp_evento, EnvioDian.uuid)
            )
        ).scalars().all()
    return list(rows)


async def _alertas(admin_sessions, rows: list[EnvioDian]) -> list[str]:
    async with admin_sessions() as session:
        found = (
            await session.execute(
                select(Alerta.tipo_alerta).where(
                    Alerta.uuid_arqueo.in_([r.uuid for r in rows])
                )
            )
        ).scalars().all()
    return sorted(found)


async def _acuse(admin_sessions, fe_uuid: uuid_lib.UUID):
    async with admin_sessions() as session:
        return (
            await session.execute(
                text(
                    "SELECT estado, cufe FROM prod.v_factura_electronica_acuse "
                    "WHERE uuid_factura_electronica = :fe"
                ),
                {"fe": fe_uuid},
            )
        ).one()


async def _dispatch(app_sessions, fe_uuid, token_path, **extra):
    async with app_sessions() as session:
        return await dispatcher.dispatch_factura_electronica(
            session,
            uuid_factura_electronica=fe_uuid,
            actor_uuid=uuid_lib.uuid4(),
            dian_provider_url=PROVIDER_URL,
            dian_token_path=token_path,
            **extra,
        )


@pytest.mark.asyncio
async def test_sessions_really_run_as_rol_app_and_cannot_update_envio(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    """Guard of the guard: the role is the restricted one, and the failure the
    old code hit (UPDATE of ``estado``) is really rejected by the database."""
    from sqlalchemy.exc import DBAPIError

    _install_provider(monkeypatch, poll={"estado": "aceptado", "cufe": "c"})
    fe = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    await _dispatch(app_sessions, fe, token_path)
    async with app_sessions() as session:
        assert (await session.execute(text("SELECT current_user"))).scalar_one() == "rol_app"
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                text("UPDATE prod.envio_dian SET estado = 'x' WHERE uuid_factura_electronica = :f"),
                {"f": fe},
            )


@pytest.mark.asyncio
async def test_aceptado_is_appended_as_chain_rows_and_never_updated(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    seen = _install_provider(monkeypatch, poll={"estado": "aceptado", "cufe": "cufe-db"})
    fe = await _seed_fe(admin_sessions, seeded_sucursal_uuid)

    terminal = await _dispatch(app_sessions, fe, token_path)

    chain = await _chain(admin_sessions, fe)
    assert [r.estado for r in chain] == ["activo", "enviado", "aceptado"]
    attempt, sent, accepted = chain
    assert sent.uuid_envio_padre == attempt.uuid
    assert accepted.uuid_envio_padre == sent.uuid
    assert accepted.uuid == terminal.uuid
    # The first row is exactly as inserted: it was NOT edited into the outcome.
    assert attempt.respuesta_proveedor is None and attempt.cufe is None
    assert accepted.cufe == "cufe-db"
    assert accepted.respuesta_proveedor["estado_dian"] == "aceptado"
    assert accepted.payload["track_id"] == "track-db"
    assert all(r.fecha_retencion_hasta is not None for r in chain)
    assert await _alertas(admin_sessions, chain) == []
    acuse = await _acuse(admin_sessions, fe)
    assert (acuse.estado, acuse.cufe) == ("aceptado", "cufe-db")
    assert [r.method for r in seen] == ["POST", "GET"]


@pytest.mark.asyncio
async def test_timeout_is_persisted_and_alerted_exactly_once(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    _install_provider(monkeypatch, poll=None)  # never leaves en_proceso
    fe = await _seed_fe(admin_sessions, seeded_sucursal_uuid)

    await _dispatch(app_sessions, fe, token_path)

    chain = await _chain(admin_sessions, fe)
    assert [r.estado for r in chain] == ["activo", "enviado", "timeout"]
    assert chain[-1].respuesta_proveedor["motivo_rechazo"] == "dian_poll_timeout"
    assert await _alertas(admin_sessions, chain) == ["dian_timeout"]
    assert (await _acuse(admin_sessions, fe)).estado == "timeout"


@pytest.mark.asyncio
async def test_rechazado_and_provider_unavailable_error_are_persisted(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    _install_provider(monkeypatch, poll=None, post_status=400)
    rejected = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    await _dispatch(app_sessions, rejected, token_path)
    chain = await _chain(admin_sessions, rejected)
    assert [r.estado for r in chain] == ["activo", "rechazado"]
    assert await _alertas(admin_sessions, chain) == ["dian_rechazada"]

    # Provider not configured (token file missing): OSError -> terminal error.
    unavailable = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    await _dispatch(app_sessions, unavailable, Path("/nonexistent/token"))
    chain = await _chain(admin_sessions, unavailable)
    assert [r.estado for r in chain] == ["activo", "error"]
    assert chain[-1].respuesta_proveedor["motivo_rechazo"].startswith("send: provider_unavailable")
    assert await _alertas(admin_sessions, chain) == ["dian_error"]


@pytest.mark.asyncio
async def test_backoff_exhaustion_appends_error_row_with_one_alert_per_outcome(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    _install_provider(monkeypatch, poll=None)
    fe = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    async with app_sessions() as session:
        await dispatcher.dispatch_factura_electronica_with_backoff(
            session, uuid_factura_electronica=fe, actor_uuid=uuid_lib.uuid4(),
            dian_provider_url=PROVIDER_URL, dian_token_path=token_path,
            max_retries=2,
        )
    chain = await _chain(admin_sessions, fe)
    assert [r.estado for r in chain] == [
        "activo", "enviado", "timeout", "activo", "enviado", "timeout", "error",
    ]
    # Every row hangs from the previous one: ONE chain, last row = state.
    assert [r.uuid_envio_padre for r in chain[1:]] == [r.uuid for r in chain[:-1]]
    assert await _alertas(admin_sessions, chain) == [
        "dian_timeout", "dian_timeout", "fe_provider_error",
    ]
    assert (await _acuse(admin_sessions, fe)).estado == "error"


@pytest.mark.asyncio
async def test_second_pass_does_not_resend_a_finished_document(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    seen = _install_provider(monkeypatch, poll={"estado": "aceptado", "cufe": "c"})
    fe = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    kwargs = dict(
        uuid_factura_electronica=fe, actor_uuid=uuid_lib.uuid4(),
        dian_provider_url=PROVIDER_URL, dian_token_path=token_path,
        skip_if_dispatched=True, recover_orphans_after=timedelta(hours=1),
    )
    async with app_sessions() as session:
        await dispatcher.dispatch_factura_electronica_with_backoff(session, **kwargs)
    before = await _chain(admin_sessions, fe)
    async with app_sessions() as session:
        with pytest.raises(dispatcher.DispatchAlreadyHandledError):
            await dispatcher.dispatch_factura_electronica_with_backoff(session, **kwargs)
    assert [r.method for r in seen].count("POST") == 1
    assert [r.uuid for r in await _chain(admin_sessions, fe)] == [r.uuid for r in before]
    async with admin_sessions() as session:
        assert fe not in await find_stale_inflight(session, older_than=timedelta(0), limit=500)


async def _plant_orphan(admin_sessions, sucursal, fe_uuid, *, estado: str, age: timedelta):
    """A cloud chain whose dispatcher died: last row still in flight, old."""
    when = _now() - age
    payload = {"xml_sha256": "ab" * 32, "estado_dian": estado}
    if estado == "enviado":
        payload["track_id"] = "track-lost"
    async with admin_sessions() as session:
        row = EnvioDian(
            uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal, uuid_factura_electronica=fe_uuid,
            payload=payload, estado=estado, timestamp_evento=when, created_at=when,
            created_by=sucursal, fecha_retencion_hasta=date.today() + timedelta(days=1825),
        )
        session.add(row)
        await session.commit()
        return row.uuid


@pytest.mark.asyncio
async def test_stale_activo_orphan_is_recovered_once_without_double_submission(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    """The 'stuck activo' rows of production: never submitted (no track_id)."""
    seen = _install_provider(monkeypatch, poll={"estado": "aceptado", "cufe": "c"})
    fe = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    fresh = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    orphan = await _plant_orphan(
        admin_sessions, seeded_sucursal_uuid, fe, estado="activo", age=timedelta(hours=3)
    )
    await _plant_orphan(
        admin_sessions, seeded_sucursal_uuid, fresh, estado="activo", age=timedelta(minutes=2)
    )
    async with admin_sessions() as session:
        found = await find_stale_inflight(session, older_than=timedelta(hours=1), limit=500)
    assert fe in found and fresh not in found  # a live dispatch is not touched

    kwargs = dict(
        uuid_factura_electronica=fe, actor_uuid=uuid_lib.uuid4(),
        dian_provider_url=PROVIDER_URL, dian_token_path=token_path,
        skip_if_dispatched=True, recover_orphans_after=timedelta(hours=1),
    )
    async with app_sessions() as session:
        await dispatcher.dispatch_factura_electronica_with_backoff(session, **kwargs)

    chain = await _chain(admin_sessions, fe)
    assert [r.estado for r in chain] == ["activo", "error", "activo", "enviado", "aceptado"]
    assert chain[0].uuid == orphan and chain[0].respuesta_proveedor is None  # untouched
    closure = chain[1]
    assert closure.uuid_envio_padre == orphan and closure.payload["interrupted"] is True
    assert chain[2].uuid_envio_padre == closure.uuid
    assert await _alertas(admin_sessions, chain) == ["dian_error"]
    assert [r.method for r in seen].count("POST") == 1

    # Second sweep pass: nothing to recover, nothing resent.
    async with admin_sessions() as session:
        assert fe not in await find_stale_inflight(session, older_than=timedelta(hours=1), limit=500)
    async with app_sessions() as session:
        with pytest.raises(dispatcher.DispatchAlreadyHandledError):
            await dispatcher.dispatch_factura_electronica_with_backoff(session, **kwargs)
    assert [r.method for r in seen].count("POST") == 1


@pytest.mark.asyncio
async def test_stale_enviado_orphan_is_closed_and_alerted_but_never_resent(
    app_sessions, admin_sessions, seeded_sucursal_uuid, token_path, monkeypatch
) -> None:
    """The provider already holds the document (track_id): resending could
    duplicate it, so the orphan is closed with an alerta and a human decides."""
    seen = _install_provider(monkeypatch, poll={"estado": "aceptado", "cufe": "c"})
    fe = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    await _plant_orphan(
        admin_sessions, seeded_sucursal_uuid, fe, estado="enviado", age=timedelta(hours=3)
    )
    async with app_sessions() as session:
        with pytest.raises(dispatcher.DispatchAlreadyHandledError):
            await dispatcher.dispatch_factura_electronica_with_backoff(
                session, uuid_factura_electronica=fe, actor_uuid=uuid_lib.uuid4(),
                dian_provider_url=PROVIDER_URL, dian_token_path=token_path,
                skip_if_dispatched=True, recover_orphans_after=timedelta(hours=1),
            )
    chain = await _chain(admin_sessions, fe)
    assert [r.estado for r in chain] == ["enviado", "error"]
    assert await _alertas(admin_sessions, chain) == ["dian_error"]
    assert seen == []
    async with admin_sessions() as session:
        assert fe not in await find_stale_inflight(session, older_than=timedelta(0), limit=500)


@pytest.mark.asyncio
async def test_listing_shows_only_the_last_row_and_counts_activo_as_en_proceso(
    admin_sessions, seeded_sucursal_uuid
) -> None:
    done = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    stuck = await _seed_fe(admin_sessions, seeded_sucursal_uuid)
    async with admin_sessions() as session:
        attempt = await _plant_orphan(
            admin_sessions, seeded_sucursal_uuid, done, estado="activo", age=timedelta(minutes=5)
        )
        parent = (
            await session.execute(select(EnvioDian).where(EnvioDian.uuid == attempt))
        ).scalar_one()
        session.add(
            dispatcher._chain_row(
                parent, estado="timeout", payload=dict(parent.payload),
                respuesta_proveedor={"estado_dian": "timeout"},
            )
        )
        await session.commit()
    await _plant_orphan(
        admin_sessions, seeded_sucursal_uuid, stuck, estado="activo", age=timedelta(minutes=5)
    )

    async def _listed(estado: str | None, solo_tip: bool = True) -> set[tuple[uuid_lib.UUID, str]]:
        async with admin_sessions() as session:
            extra = [
                EnvioDian.uuid_factura_electronica.in_([done, stuck]),
            ]
            if solo_tip:
                extra.append(~cloud_router._superseded_envio_exists())
            rows, _ = await cloud_router._list_workflow_rows(
                session, model_cls=EnvioDian, estado_values=cloud_router._ENVIO_DIAN_ESTADOS,
                estado=estado, cursor=None, limit=100, extra_where=extra,
                estado_aliases=cloud_router._ENVIO_DIAN_ESTADO_ALIASES,
            )
        return {(r.uuid_factura_electronica, r.estado) for r in rows}

    assert await _listed(None) == {(done, "timeout"), (stuck, "activo")}
    assert await _listed("en_proceso") == {(stuck, "activo")}
    assert await _listed("timeout") == {(done, "timeout")}
    full = await _listed(None, solo_tip=False)
    assert (done, "activo") in full and (done, "timeout") in full
