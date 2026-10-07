"""``POST /sync/push`` must isolate a poison row (real Postgres, real HTTP).

Live incident (dev, 2026-10): the cloud and a branch both numbered
``(resolucion, consecutivo) = (R, 1)``. The branch push then hit
``factura_electronica_uk01`` on the cloud; the exception escaped the row loop,
the single batch rollback discarded every row and the endpoint answered 500
forever, so no other row of the batch was ever applied.

Contract pinned here: a row that violates a constraint is reported
``apply_error`` (class + SQLSTATE + constraint, no row values) and recorded as
an informational ``sync_conflict``; every other row of the batch is applied and
committed; the response is 207, never a 500.

Also pins the deployment split of ``emitir_fe_para_pago``: in the cloud it never
numbers (so it can never collide), in a branch it emits with the branch's own
numbering and retries the cloud-created marker.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from parkos_core.models.A.sync_conflict import SyncConflict
from parkos_core.models.L_E.factura_electronica import FacturaElectronica
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.models.V.resolucion_facturacion import ResolucionFacturacion
from parkos_core.repo import factura as repo_factura
from parkos_core.repo import factura_electronica as repo_fe
from parkos_core.repo.fe_emision import (
    ALERTA_PENDIENTE,
    FeRetryScheduler,
    emitir_fe_para_pago,
    reintentar_pendientes,
)
from parkos_core.runtime import engine_flag
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


async def _sucursal(Session) -> uuid_lib.UUID:  # noqa: N803
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal

    suc = uuid_lib.uuid4()
    async with Session() as s:
        empresa = (
            await s.execute(select(Empresa.uuid).where(Empresa.vigente_hasta.is_(None)))
        ).scalars().first()
        s.add(
            Sucursal(
                uuid=suc, uuid_empresa=empresa, uuid_tipo_sucursal=None,
                nombre=f"Suc PR {suc.hex[:6]}", prefijo_nombre=f"PR{suc.hex[:4]}",
                ciudad="Ciudad", direccion="Calle 1", telefono="+57111", horario="24/7",
                vigente_desde=_now(), vigente_hasta=None, estado="activo",
                created_at=_now(), created_by=None, sync_status="sincronizado",
                sync_timestamp=None, sync_attempts=0,
            )
        )
        await s.commit()
    return suc


async def _resolucion(session, sucursal, *, desde=1, hasta=1000, prefijo="QA"):
    row = ResolucionFacturacion(
        uuid=uuid_lib.uuid4(), uuid_sucursal=sucursal,
        numero_resolucion=f"R-{uuid_lib.uuid4().hex[:10]}", prefijo=prefijo,
        rango_desde=desde, rango_hasta=hasta, vigente_desde=_now(), vigente_hasta=None,
        estado="activo", created_at=_now(), created_by=None,
        sync_status="sincronizado", sync_attempts=0,
    )
    session.add(row)
    await session.commit()
    return row


async def _factura(session, sucursal) -> uuid_lib.UUID:
    f = await repo_factura.crear_factura_evento(
        session,
        actor_uuid=None,
        new_attrs={
            "uuid_sucursal": sucursal,
            "subtotal": Decimal("1000"),
            "descuento": Decimal("0"),
            "total": Decimal("1190"),
        },
    )
    await session.commit()
    return f.uuid


async def _fes(session, sucursal):
    return (
        (
            await session.execute(
                select(FacturaElectronica)
                .where(FacturaElectronica.uuid_sucursal == sucursal)
                .order_by(FacturaElectronica.consecutivo)
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# (a) + (b) deployment split of the emission
# ---------------------------------------------------------------------------


async def test_nube_no_numera_y_la_sucursal_emite_con_su_numeracion(
    pg_engine, alembic_upgrade, monkeypatch: pytest.MonkeyPatch
) -> None:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)  # noqa: N806
    suc = await _sucursal(Session)
    async with Session() as s:
        await _resolucion(s, suc, desde=1, hasta=5000)
        fac = await _factura(s, suc)

        # (a) charge originated in the CLOUD: no FE, no consecutivo consumed,
        # pending marker left for the branch.
        monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
        res = await emitir_fe_para_pago(s, actor_uuid=None, uuid_factura=fac)
        assert res.pendiente and not res.emitida and res.error is None
        assert await _fes(s, suc) == []
        marcadores = (
            (
                await s.execute(
                    select(Alerta).where(
                        Alerta.uuid_sucursal == suc, Alerta.tipo_alerta == ALERTA_PENDIENTE
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(marcadores) == 1
        assert marcadores[0].datos_nuevos["origen"] == "nube"
        assert marcadores[0].datos_nuevos["uuid_factura"] == str(fac)

        # asking again in the cloud neither stacks markers nor numbers.
        await emitir_fe_para_pago(s, actor_uuid=None, uuid_factura=fac)
        assert await _fes(s, suc) == []

        # (b) the BRANCH worker takes the marker and emits with ITS numbering.
        monkeypatch.setenv("PARKOS_DEPLOY", "branch")
        cont = await reintentar_pendientes(s, uuid_sucursal=suc, scheduler=FeRetryScheduler())
        assert cont["emitidas"] == 1 and cont["alertas"] == 0
        fes = await _fes(s, suc)
        assert [(fe.prefijo, fe.consecutivo, fe.uuid_factura) for fe in fes] == [("QA", 1, fac)]


# ---------------------------------------------------------------------------
# (c) poison row in a push batch
# ---------------------------------------------------------------------------


def _fe_payload(*, suc, resolucion, factura, consecutivo) -> dict:
    return {
        "uuid": str(uuid_lib.uuid4()),
        "fecha_retencion_hasta": date.today().isoformat(),
        "uuid_sucursal": str(suc),
        "uuid_factura": str(factura),
        "uuid_resolucion_facturacion": str(resolucion.uuid),
        "prefijo": resolucion.prefijo,
        "consecutivo": consecutivo,
        "descuento": "0",
    }


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_push_con_fila_que_viola_uk01_no_da_500_y_aplica_las_demas(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The receiving node is the CLOUD (the DIAN post-insert hook is cloud-only).
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    # Provider egress is not under test: stub the cloud DIAN dispatcher the
    # post-insert hook calls (it would read a provider token file / call HTTP).
    from unittest.mock import AsyncMock

    from parkos_core.dian.cloud import dispatcher

    monkeypatch.setattr(
        dispatcher, "dispatch_factura_electronica_with_backoff", AsyncMock(return_value=None)
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)  # noqa: N806
    suc = await _sucursal(Session)
    async with Session() as s:
        resolucion = await _resolucion(s, suc, desde=1, hasta=5000)
        f_existente = await _factura(s, suc)
        f_mala = await _factura(s, suc)
        f_buena = await _factura(s, suc)
        # the "other node" already holds (resolucion, 1): seeded directly, as
        # the cloud never numbers through emitir_fe_para_pago any more.
        await repo_fe.crear_factura_electronica_inicial(
            s, actor_uuid=None, uuid_sucursal=suc, uuid_factura=f_existente,
            uuid_resolucion_facturacion=resolucion.uuid, prefijo=resolucion.prefijo,
            consecutivo=1,
        )
        await s.commit()

    mala = _fe_payload(suc=suc, resolucion=resolucion, factura=f_mala, consecutivo=1)
    buena = _fe_payload(suc=suc, resolucion=resolucion, factura=f_buena, consecutivo=2)
    token = mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc)
    resp = await client.post(
        "/api/v1/sync/push",
        json={
            "rows": [
                {"tabla": "factura_electronica", "uuid_registro": mala["uuid"], "seq": 1,
                 "datos": mala},
                {"tabla": "factura_electronica", "uuid_registro": buena["uuid"], "seq": 2,
                 "datos": buena},
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 207, resp.text
    results = resp.json()["results"]
    assert [r["status"] for r in results] == ["apply_error", "applied"], resp.text
    assert "factura_electronica_uk01" in results[0]["detail"]
    assert "23505" in results[0]["detail"]
    # row values never travel back in the diagnostic
    assert str(f_mala) not in results[0]["detail"]

    async with Session() as s:
        assert [fe.consecutivo for fe in await _fes(s, suc)] == [1, 2]
        assert {fe.uuid_factura for fe in await _fes(s, suc)} == {f_existente, f_buena}
        conflictos = (
            await s.execute(
                select(func.count())
                .select_from(SyncConflict)
                .where(
                    SyncConflict.tabla == "factura_electronica",
                    SyncConflict.politica == "constraint_violation",
                    SyncConflict.uuid_registro == uuid_lib.UUID(mala["uuid"]),
                )
            )
        ).scalar_one()
        assert conflictos == 1


@pytest.mark.parametrize("app", ["admin"], indirect=True)
async def test_fe_de_sucursal_con_consecutivo_n_aplica_en_nube_aunque_haya_otra_fe(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cloud keeps the branch-assigned number verbatim: a branch FE with
    consecutivo N applies even when the cloud already holds another FE of the
    same resolution, and the cloud never renumbers it."""
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    from unittest.mock import AsyncMock

    from parkos_core.dian.cloud import dispatcher

    monkeypatch.setattr(
        dispatcher, "dispatch_factura_electronica_with_backoff", AsyncMock(return_value=None)
    )
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)  # noqa: N806
    suc = await _sucursal(Session)
    async with Session() as s:
        resolucion = await _resolucion(s, suc, desde=1, hasta=5000)
        f_otra = await _factura(s, suc)
        f_sucursal = await _factura(s, suc)
        await repo_fe.crear_factura_electronica_inicial(
            s, actor_uuid=None, uuid_sucursal=suc, uuid_factura=f_otra,
            uuid_resolucion_facturacion=resolucion.uuid, prefijo=resolucion.prefijo,
            consecutivo=1,
        )
        await s.commit()

    fe = _fe_payload(suc=suc, resolucion=resolucion, factura=f_sucursal, consecutivo=7)
    token = mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc)
    resp = await client.post(
        "/api/v1/sync/push",
        json={"rows": [{"tabla": "factura_electronica", "uuid_registro": fe["uuid"],
                        "seq": 1, "datos": fe}]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 207, resp.text
    assert [r["status"] for r in resp.json()["results"]] == ["applied"], resp.text
    async with Session() as s:
        assert [(x.consecutivo, x.uuid_factura) for x in await _fes(s, suc)] == [
            (1, f_otra),
            (7, f_sucursal),
        ]
