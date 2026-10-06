"""test_sync_pull_logging.py — one structured record per ``POST /sync/pull``.

The record carries the pulling branch, rows per table, total rows, duration,
``since_seq`` and ``next_seq`` (as ``extra`` fields) and is promoted to WARNING
above ``_PULL_SLOW_THRESHOLD_MS``. It must never carry a row payload.
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

PULL_URL = "/api/v1/sync/pull"
ROUTER_LOGGER = "parkos_core.api.v1.sync_router"
_FIELDS = (
    "uuid_sucursal",
    "rows_por_tabla",
    "total_rows",
    "duration_ms",
    "since_seq",
    "next_seq",
)


def _model(table: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[table].model_cls


@pytest.fixture
async def member(pg_engine, alembic_upgrade, v_fixture_factory):
    """A branch with one member usuario carrying a recognizable password_hash."""
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    tag = uuid_lib.uuid4().hex[:8]
    secret = f"$2b$12$LOGSECRET-{tag}"
    since_seq = int(datetime.now(UTC).timestamp() * 1000) - 2
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        suc = v_fixture_factory.build(_model("sucursal"), nombre=f"L-{tag}")
        usr = v_fixture_factory.build(
            _model("usuarios"),
            email=f"log-{tag}@test.local",
            cedula=f"log-{tag}",
            password_hash=secret,
            rol="operador",
        )
        s.add_all([suc, usr])
        await s.commit()
        link = v_fixture_factory.build(
            _model("usuarios_sucursal"), uuid_sucursal=suc.uuid, uuid_usuario=usr.uuid
        )
        s.add(link)
        await s.commit()
    yield suc.uuid, secret, since_seq
    now = datetime.now(UTC).replace(tzinfo=None)
    async with Session() as s:
        for table, row in (("usuarios_sucursal", link), ("usuarios", usr), ("sucursal", suc)):
            model = _model(table)
            await s.execute(
                update(model)
                .where(model.uuid == row.uuid, model.vigente_hasta.is_(None))
                .values(vigente_hasta=now, estado="inactivo")
            )
        await s.commit()


async def _pull(client, token: str, since_seq: int):
    return await client.post(
        PULL_URL,
        json={"since_seq": since_seq},
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": uuid_lib.uuid4().hex},
    )


def _pull_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == ROUTER_LOGGER and r.msg.startswith("sync_pull.")]


async def test_one_structured_record_per_pull(client, mint_sync_agent_jwt, member, caplog, app):
    suc, _secret, since_seq = member
    caplog.set_level(logging.INFO, logger=ROUTER_LOGGER)
    resp = await _pull(client, mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc), since_seq)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    records = _pull_records(caplog)
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.INFO
    assert rec.msg == "sync_pull.completed"
    for name in _FIELDS:
        assert hasattr(rec, name), f"missing log field {name}"
    assert rec.uuid_sucursal == str(suc)
    assert rec.since_seq == since_seq
    assert rec.next_seq == body["next_seq"]
    assert rec.total_rows == len(body["rows"])
    assert sum(rec.rows_por_tabla.values()) == rec.total_rows
    assert rec.rows_por_tabla["usuarios"] == 1
    assert isinstance(rec.duration_ms, int | float)
    assert rec.duration_ms >= 0


async def test_record_never_carries_row_payloads(client, mint_sync_agent_jwt, member, caplog, app):
    suc, secret, since_seq = member
    caplog.set_level(logging.DEBUG, logger=ROUTER_LOGGER)
    resp = await _pull(client, mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc), since_seq)
    assert secret in resp.text  # the member's hash IS on the wire ...
    for rec in _pull_records(caplog):  # ... and in no log record
        assert secret not in repr(vars(rec))
        assert secret not in rec.getMessage()


async def test_slow_pull_is_a_warning(
    client, mint_sync_agent_jwt, member, caplog, monkeypatch, app
):
    from parkos_core.api.v1 import sync_router

    monkeypatch.setattr(sync_router, "_PULL_SLOW_THRESHOLD_MS", -1)
    suc, _secret, since_seq = member
    caplog.set_level(logging.INFO, logger=ROUTER_LOGGER)
    await _pull(client, mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc), since_seq)
    (rec,) = _pull_records(caplog)
    assert rec.levelno == logging.WARNING
    assert rec.msg == "sync_pull.slow"
