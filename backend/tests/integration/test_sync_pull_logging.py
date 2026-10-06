"""test_sync_pull_logging.py — one structured record per ``POST /sync/pull``.

The record goes through the REQ-OPS-007 sink (``sync/observability/logs.py``:
structlog JSON on stdout) so it is visible in a container where no stdlib
handler is configured for ``parkos_core`` loggers. It carries the 7 required
keys plus counts, is promoted to ``warning`` above ``_PULL_SLOW_THRESHOLD_MS``
and must never carry a row payload.
"""

from __future__ import annotations

import json
import uuid as uuid_lib
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

PULL_URL = "/api/v1/sync/pull"
_REQUIRED = (
    "event",
    "tabla",
    "uuid_sucursal",
    "actor_uuid",
    "correlation_id",
    "ts",
    "level",
)
_COUNTS = ("rows_total", "rows_por_tabla", "duration_ms", "since_seq", "next_seq")


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


async def _pull(client, token: str, since_seq: int, request_id: str | None = None):
    return await client.post(
        PULL_URL,
        json={"since_seq": since_seq},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Request-Id": request_id or uuid_lib.uuid4().hex,
        },
    )


def _pull_lines(out: str) -> list[dict]:
    lines = []
    for raw in out.splitlines():
        raw = raw.strip()
        if raw.startswith("{") and '"sync_pull.' in raw:
            lines.append(json.loads(raw))
    return lines


async def test_one_structured_record_per_pull(client, mint_sync_agent_jwt, member, capsys, app):
    suc, _secret, since_seq = member
    rid = uuid_lib.uuid4().hex
    capsys.readouterr()
    resp = await _pull(
        client, mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc), since_seq, rid
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    records = _pull_lines(capsys.readouterr().out)
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == "sync_pull.completed"
    assert rec["level"] == "info"
    for name in (*_REQUIRED, *_COUNTS):
        assert name in rec, f"missing log field {name}"
    assert rec["uuid_sucursal"] == str(suc)
    assert rec["correlation_id"] == rid
    assert rec["actor_uuid"]
    assert rec["since_seq"] == since_seq
    assert rec["next_seq"] == body["next_seq"]
    assert rec["rows_total"] == len(body["rows"])
    assert sum(rec["rows_por_tabla"].values()) == rec["rows_total"]
    assert rec["rows_por_tabla"]["usuarios"] == 1
    assert isinstance(rec["duration_ms"], int | float)
    assert rec["duration_ms"] >= 0


async def test_record_never_carries_row_payloads(client, mint_sync_agent_jwt, member, capsys, app):
    suc, secret, since_seq = member
    capsys.readouterr()
    resp = await _pull(client, mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc), since_seq)
    assert secret in resp.text  # the member's hash IS on the wire ...
    out = capsys.readouterr().out
    assert _pull_lines(out)
    # ... and nowhere in what was logged (no hash, email, cedula or payload).
    for line in out.splitlines():
        assert secret not in line
        assert "@test.local" not in line
        assert "password_hash" not in line
        assert "cedula" not in line
        assert "placa" not in line
        assert '"payload"' not in line


async def test_slow_pull_is_a_warning(
    client, mint_sync_agent_jwt, member, capsys, monkeypatch, app
):
    from parkos_core.api.v1 import sync_router

    monkeypatch.setattr(sync_router, "_PULL_SLOW_THRESHOLD_MS", -1)
    suc, _secret, since_seq = member
    capsys.readouterr()
    await _pull(client, mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc), since_seq)
    (rec,) = _pull_lines(capsys.readouterr().out)
    assert rec["level"] == "warning"
    assert rec["event"] == "sync_pull.slow"
    for name in _REQUIRED:
        assert name in rec
