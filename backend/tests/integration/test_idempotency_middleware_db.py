"""Defect L3 -- IdempotencyKeyMiddleware against real Postgres.

Same ``Idempotency-Key`` twice -> ONE side effect; the second answer is the
stored response with ``Idempotent-Replay: true``. Exercises the real
``prod.idempotency_keys`` table (UK, JSONB, append-only triggers) and real
JWT verification (the key is scoped per caller).
"""
from __future__ import annotations

import uuid as uuid_lib

import httpx
import pytest
from fastapi import FastAPI
from parkos_core.api.middleware import IdempotencyKeyMiddleware
from parkos_core.models.A.idempotency_keys import IdempotencyKeys
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

pytestmark = pytest.mark.asyncio


def _app(effects: list[dict]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(IdempotencyKeyMiddleware)

    @app.post("/api/v1/operacion/ingresos", status_code=201)
    async def crear(payload: dict) -> dict:
        effects.append(payload)
        return {"uuid_ingreso": str(uuid_lib.uuid4()), "n": len(effects)}

    return app


async def _rows(pg_engine, key_prefix: str | None = None) -> int:
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as s:
        return (
            await s.execute(select(func.count()).select_from(IdempotencyKeys))
        ).scalar_one()


async def _post(app, body, key, token):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(
            "/api/v1/operacion/ingresos",
            json=body,
            headers={"Idempotency-Key": key, "Authorization": f"Bearer {token}"},
        )


async def test_same_key_twice_runs_handler_once_and_replays(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    effects: list[dict] = []
    app = _app(effects)
    token = mint_operador_jwt(actor_uuid=uuid_lib.uuid4(), sucursal_uuid=uuid_lib.uuid4())
    key = f"k-{uuid_lib.uuid4()}"
    before = await _rows(pg_engine)

    r1 = await _post(app, {"placa": "AAA111"}, key, token)
    r2 = await _post(app, {"placa": "AAA111"}, key, token)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert len(effects) == 1  # ONE side effect
    assert r2.json() == r1.json()  # same stored response
    assert "idempotent-replay" not in r1.headers
    assert r2.headers["idempotent-replay"] == "true"
    assert await _rows(pg_engine) == before + 1


async def test_same_key_different_body_is_409_and_no_second_effect(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    effects: list[dict] = []
    app = _app(effects)
    token = mint_operador_jwt()
    key = f"k-{uuid_lib.uuid4()}"

    await _post(app, {"placa": "AAA111"}, key, token)
    r2 = await _post(app, {"placa": "ZZZ999"}, key, token)

    assert r2.status_code == 409
    assert r2.json()["detail"]["error"] == "idempotency_key_conflict"
    assert len(effects) == 1


async def test_distinct_keys_are_distinct_requests(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    """parkosFetch sends a per-call nonce: identical actions are NOT replayed."""
    effects: list[dict] = []
    app = _app(effects)
    token = mint_operador_jwt()

    r1 = await _post(app, {"placa": "AAA111"}, f"k-{uuid_lib.uuid4()}", token)
    r2 = await _post(app, {"placa": "AAA111"}, f"k-{uuid_lib.uuid4()}", token)

    assert len(effects) == 2
    assert "idempotent-replay" not in r2.headers
    assert r1.json()["uuid_ingreso"] != r2.json()["uuid_ingreso"]


async def test_key_is_scoped_per_caller(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    effects: list[dict] = []
    app = _app(effects)
    key = f"k-{uuid_lib.uuid4()}"

    await _post(app, {"x": 1}, key, mint_operador_jwt(actor_uuid=uuid_lib.uuid4()))
    r2 = await _post(app, {"x": 1}, key, mint_operador_jwt(actor_uuid=uuid_lib.uuid4()))

    assert len(effects) == 2  # another caller never receives someone else's response
    assert "idempotent-replay" not in r2.headers


async def test_expired_key_is_a_new_request_not_410(
    client, pg_engine, alembic_upgrade, mint_operador_jwt
) -> None:
    effects: list[dict] = []
    app = _app(effects)
    token = mint_operador_jwt()
    key = f"k-{uuid_lib.uuid4()}"

    await _post(app, {"x": 1}, key, token)
    # Age the stored row past its TTL (the sweep runs as superuser, not rol_app).
    async with pg_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE prod.idempotency_keys DISABLE TRIGGER USER"))
        await conn.execute(
            text("UPDATE prod.idempotency_keys SET expires_at = NOW() - INTERVAL '1 hour'")
        )
        await conn.execute(text("ALTER TABLE prod.idempotency_keys ENABLE TRIGGER USER"))

    r2 = await _post(app, {"x": 1}, key, token)

    assert r2.status_code == 201
    assert len(effects) == 2
    assert "idempotent-replay" not in r2.headers
