"""test_sync_pull_scope_reconciliation.py -- T3.9: what the derived pull scope does
when a client is reconciled by natural key between branches.

Scenario: cliente X (same ``tipo_identificador`` + ``numero_identificacion``) is
created at branch A (the cloud has it, A holds a subscription on it). Branch B
creates the same X locally and pushes it through ``POST /sync/events``; the cloud's
``identity_reconciler`` resolves it by natural key (``identity_lookup``).

Observed end to end (real HTTP, ``PARKOS_SYNC_ENGINE=catalog``):

* divergent data -> the cloud closes A's version and opens B's (B's uuid is
  preserved): exactly one open row, plus an informational ``sync_conflict``.
* identical data -> ``noop``: the cloud keeps A's row open and never stores B's uuid.
* the ``noop`` records ``B uuid -> A uuid`` in ``sync_identity_alias`` and the motor
  remaps B's dependents (FK columns onto identity-reconciled masters only) before
  applying them, so they reach the cloud (formerly an xfail-strict FK gap).

The derived scope matches by NATURAL KEY, so a version bump (new uuid, referencing
rows still on the old one) keeps the open version in scope.
"""

from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.encoders import jsonable_encoder
from parkos_core.runtime import engine_flag

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

#: Tables the scenarios touch; their rows are logically closed at teardown so the
#: 500-row pull cap of later tests is not crowded by this module's leftovers.
_TOUCHED = (
    "clientes",
    "clientes_b2b",
    "subscripciones_cliente",
    "usuarios",
    "usuarios_sucursal",
    "tipo_subscripciones",
    "sucursal",
    "vehiculos",
    "subscripcion_vehiculos",
)


@pytest.fixture(autouse=True)
def _catalog_engine_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "catalog")
    engine_flag._reset_cache_for_tests()


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _model(table: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[table].model_cls


def _wire(row) -> dict:
    """A branch's ``sync_queue`` payload for ``row``: every column but audit metadata."""
    from sqlalchemy import inspect as sa_inspect

    skip = {"created_at", "created_by", "sync_status", "sync_attempts", "sync_timestamp"}
    columns = sa_inspect(type(row)).columns
    return jsonable_encoder({c.name: getattr(row, c.name) for c in columns if c.name not in skip})


async def _push(client, token: str, tabla: str, row) -> str:
    # A fresh X-Request-Id per call: the idempotency cache would otherwise replay the
    # previous response for the same issuer/subject.
    resp = await client.post(
        "/api/v1/sync/events",
        json={
            "events": [
                {
                    "event_type": "row_push",
                    "tabla": tabla,
                    "uuid_registro": str(row.uuid),
                    "payload": _wire(row),
                }
            ]
        },
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": uuid_lib.uuid4().hex},
    )
    assert resp.status_code in (200, 207), resp.text
    return resp.json()["results"][0]["status"]


async def _pull(client, token: str, since_seq: int) -> list[tuple[str, str]]:
    resp = await client.post(
        "/api/v1/sync/pull",
        json={"since_seq": since_seq},
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": uuid_lib.uuid4().hex},
    )
    assert resp.status_code == 200, resp.text
    return [(r["tabla"], r["uuid_registro"]) for r in resp.json()["rows"]]


@dataclass
class World:
    client: object
    sessions: object
    factory: object
    since: int
    key: str
    suc_a: uuid_lib.UUID
    suc_b: uuid_lib.UUID
    tipo: uuid_lib.UUID
    x_a: object  # A's cliente row, subscribed at A
    tok_a: str
    tok_b: str

    def clientes(self, pulled: list[tuple[str, str]]) -> set[str]:
        return {u for t, u in pulled if t == "clientes"}

    def b_version(self, *, same_data: bool):
        """B's independently created version of the same natural key."""
        return self.factory.build(
            _model("clientes"),
            tipo_identificador="CC",
            numero_identificacion=self.key,
            nombre=self.x_a.nombre,
            apellido=self.x_a.apellido,
            telefono=self.x_a.telefono if same_data else "3009999999",
        )

    async def open_rows(self) -> list:
        from sqlalchemy import select

        clientes = _model("clientes")
        async with self.sessions() as s:
            stmt = select(clientes).where(
                clientes.numero_identificacion == self.key, clientes.vigente_hasta.is_(None)
            )
            return list((await s.execute(stmt)).scalars().all())


@pytest.fixture
async def world(client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory):
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sessions = async_sessionmaker(pg_engine, expire_on_commit=False)
    since = _now_ms() - 2
    tag = uuid_lib.uuid4().hex[:8]
    key = f"X{tag}"
    async with sessions() as s:
        suc_a = v_fixture_factory.build(_model("sucursal"), nombre=f"A-{tag}")
        suc_b = v_fixture_factory.build(_model("sucursal"), nombre=f"B-{tag}")
        tipo = v_fixture_factory.build(_model("tipo_subscripciones"))
        x_a = v_fixture_factory.build(
            _model("clientes"),
            tipo_identificador="CC",
            numero_identificacion=key,
            telefono="3001111111",
        )
        s.add_all([suc_a, suc_b, tipo, x_a])
        await s.commit()
        s.add(
            v_fixture_factory.build(
                _model("subscripciones_cliente"),
                uuid_sucursal=suc_a.uuid,
                uuid_cliente=x_a.uuid,
                uuid_tipo_subscripcion=tipo.uuid,
            )
        )
        await s.commit()

    yield World(
        client=client,
        sessions=sessions,
        factory=v_fixture_factory,
        since=since,
        key=key,
        suc_a=suc_a.uuid,
        suc_b=suc_b.uuid,
        tipo=tipo.uuid,
        x_a=x_a,
        tok_a=mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc_a.uuid),
        tok_b=mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc_b.uuid),
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    floor = datetime.fromtimestamp(since / 1000, UTC).replace(tzinfo=None)
    async with sessions() as s:
        for table in _TOUCHED:
            model = _model(table)
            await s.execute(
                update(model)
                .where(model.created_at >= floor, model.vigente_hasta.is_(None))
                .values(vigente_hasta=now, estado="inactivo")
            )
        await s.commit()


# ---------------------------------------------------------------------------
# divergent data: the cloud closes A's version and opens B's
# ---------------------------------------------------------------------------


async def test_divergent_push_converges_to_one_open_row_without_duplicate(world: World) -> None:
    x_b = world.b_version(same_data=False)
    assert await _push(world.client, world.tok_b, "clientes", x_b) == "applied"

    open_rows = await world.open_rows()
    assert [r.uuid for r in open_rows] == [x_b.uuid], "exactly one open row: B's version"
    assert open_rows[0].telefono == "3009999999"


async def test_divergent_b_receives_the_canonical_row_once_it_subscribes(world: World) -> None:
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente

    x_b = world.b_version(same_data=False)
    await _push(world.client, world.tok_b, "clientes", x_b)
    # Until B has a subscription or an invoice on X in the cloud, X is out of B's scope.
    assert world.clientes(await _pull(world.client, world.tok_b, world.since)) == set()

    sc_b = world.factory.build(
        SubscripcionesCliente,
        uuid_sucursal=world.suc_b,
        uuid_cliente=x_b.uuid,
        uuid_tipo_subscripcion=world.tipo,
    )
    assert await _push(world.client, world.tok_b, "subscripciones_cliente", sc_b) == "applied"

    pulled = world.clientes(await _pull(world.client, world.tok_b, world.since))
    assert pulled == {str(x_b.uuid)}, "B gets its own canonical row, once, and not A's closed one"


async def test_divergent_a_receives_the_canonical_open_version(world: World) -> None:
    x_b = world.b_version(same_data=False)
    await _push(world.client, world.tok_b, "clientes", x_b)

    pulled = world.clientes(await _pull(world.client, world.tok_a, world.since))
    assert pulled == {str(x_b.uuid)}


async def test_cloud_edit_of_a_subscribed_cliente_reaches_the_branch(world: World) -> None:
    from parkos_core.repo import versioned

    async with world.sessions() as s:
        edited = await versioned.close_and_insert(
            s,
            _model("clientes"),
            current_uuid=world.x_a.uuid,
            new_attrs={"telefono": "3000000000"},
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )
        await s.commit()

    pulled = world.clientes(await _pull(world.client, world.tok_a, world.since))
    assert pulled == {str(edited.uuid)}


# ---------------------------------------------------------------------------
# identical data: noop, nothing is stored for B and nothing is aliased
# ---------------------------------------------------------------------------


async def test_identical_push_is_noop_and_creates_no_duplicate(world: World) -> None:
    x_b = world.b_version(same_data=True)
    assert await _push(world.client, world.tok_b, "clientes", x_b) == "applied"

    open_rows = await world.open_rows()
    assert [r.uuid for r in open_rows] == [world.x_a.uuid], "A's row stays; B's uuid is not stored"


async def test_identical_push_dependents_of_b_reach_the_cloud(world: World) -> None:
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente

    x_b = world.b_version(same_data=True)
    await _push(world.client, world.tok_b, "clientes", x_b)
    sc_b = world.factory.build(
        SubscripcionesCliente,
        uuid_sucursal=world.suc_b,
        uuid_cliente=x_b.uuid,
        uuid_tipo_subscripcion=world.tipo,
    )
    assert await _push(world.client, world.tok_b, "subscripciones_cliente", sc_b) == "applied"


# ---------------------------------------------------------------------------
# the same version-bump question for the other derived entries
# ---------------------------------------------------------------------------


async def test_cloud_edit_of_a_member_usuario_reaches_the_branch(world: World) -> None:
    """``close_and_insert`` on ``usuarios`` repoints ``usuarios_sucursal`` /
    ``permisos_usuario`` onto the new uuid (``propagate_usuario_uuid_to_fks``), so the
    membership subselect keeps matching the open version."""
    from parkos_core.repo import versioned

    tag = uuid_lib.uuid4().hex[:8]
    async with world.sessions() as s:
        user = world.factory.build(
            _model("usuarios"),
            email=f"m-{tag}@test.local",
            cedula=f"m{tag}",
            password_hash="x",
            rol="operador",
        )
        s.add(user)
        await s.commit()
        s.add(
            world.factory.build(
                _model("usuarios_sucursal"), uuid_sucursal=world.suc_a, uuid_usuario=user.uuid
            )
        )
        await s.commit()
        edited = await versioned.close_and_insert(
            s,
            _model("usuarios"),
            current_uuid=user.uuid,
            new_attrs={"nombre": "Renamed"},
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )
        await s.commit()

    pulled = {u for t, u in await _pull(world.client, world.tok_a, world.since) if t == "usuarios"}
    assert str(edited.uuid) in pulled
    assert str(user.uuid) not in pulled


async def test_cloud_edit_of_a_subscribed_vehiculo_reaches_the_branch(world: World) -> None:
    from parkos_core.repo import versioned
    from sqlalchemy import select

    sub = _model("subscripciones_cliente")
    async with world.sessions() as s:
        vehiculo = world.factory.build(_model("vehiculos"), placa=f"V{uuid_lib.uuid4().hex[:7]}")
        s.add(vehiculo)
        await s.commit()
        sc_a = (
            await s.execute(select(sub).where(sub.uuid_sucursal == world.suc_a))
        ).scalars().one()
        s.add(
            world.factory.build(
                _model("subscripcion_vehiculos"),
                uuid_subscripcion_cliente=sc_a.uuid,
                uuid_vehiculo=vehiculo.uuid,
            )
        )
        await s.commit()
        edited = await versioned.close_and_insert(
            s,
            _model("vehiculos"),
            current_uuid=vehiculo.uuid,
            new_attrs={"color": "rojo"},
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )
        await s.commit()

    pulled = {u for t, u in await _pull(world.client, world.tok_a, world.since) if t == "vehiculos"}
    assert pulled == {str(edited.uuid)}


# ---------------------------------------------------------------------------
# natural-key scoping: what must NOT be delivered
# ---------------------------------------------------------------------------


async def test_cliente_with_an_unrelated_key_is_not_delivered(world: World) -> None:
    """A cliente known only to branch B (or to nobody) stays out of A's pull even
    though natural-key matching is now in play."""
    from parkos_core.models.V.subscripciones_cliente import SubscripcionesCliente

    async with world.sessions() as s:
        only_b = world.factory.build(
            _model("clientes"), tipo_identificador="CC", numero_identificacion=f"B{world.key}"
        )
        nobody = world.factory.build(
            _model("clientes"), tipo_identificador="CC", numero_identificacion=f"N{world.key}"
        )
        s.add_all([only_b, nobody])
        await s.commit()
        s.add(
            world.factory.build(
                SubscripcionesCliente,
                uuid_sucursal=world.suc_b,
                uuid_cliente=only_b.uuid,
                uuid_tipo_subscripcion=world.tipo,
            )
        )
        await s.commit()

    for_a = world.clientes(await _pull(world.client, world.tok_a, world.since))
    assert for_a == {str(world.x_a.uuid)}
    for_b = world.clientes(await _pull(world.client, world.tok_b, world.since))
    assert for_b == {str(only_b.uuid)}


async def test_same_number_with_another_tipo_identificador_is_not_conflated(world: World) -> None:
    async with world.sessions() as s:
        other_tipo = world.factory.build(
            _model("clientes"), tipo_identificador="NIT", numero_identificacion=world.key
        )
        s.add(other_tipo)
        await s.commit()

    pulled = world.clientes(await _pull(world.client, world.tok_a, world.since))
    assert pulled == {str(world.x_a.uuid)}, "a NIT sharing the number is another client"


async def test_cliente_matched_through_a_formatted_number(world: World) -> None:
    """The key is normalized like ``ix_clientes_nk_open``: separators do not matter."""
    from parkos_core.repo import versioned

    async with world.sessions() as s:
        edited = await versioned.close_and_insert(
            s,
            _model("clientes"),
            current_uuid=world.x_a.uuid,
            new_attrs={"numero_identificacion": f"{world.key[:3]}-{world.key[3:]}"},
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )
        await s.commit()

    pulled = world.clientes(await _pull(world.client, world.tok_a, world.since))
    assert pulled == {str(edited.uuid)}


async def test_cloud_edit_of_a_subscribed_cliente_reaches_the_branch_with_its_b2b(
    world: World,
) -> None:
    """A b2b row keeps pointing at the closed cliente version; it still follows the key."""
    from parkos_core.repo import versioned

    async with world.sessions() as s:
        b2b = world.factory.build(_model("clientes_b2b"), uuid_cliente=world.x_a.uuid)
        s.add(b2b)
        await s.commit()
        edited = await versioned.close_and_insert(
            s,
            _model("clientes"),
            current_uuid=world.x_a.uuid,
            new_attrs={"telefono": "3000000001"},
            actor_uuid=uuid_lib.uuid4(),
            log_tx=False,
        )
        await s.commit()

    pulled = await _pull(world.client, world.tok_a, world.since)
    assert world.clientes(pulled) == {str(edited.uuid)}
    assert {u for t, u in pulled if t == "clientes_b2b"} == {str(b2b.uuid)}
    # the other branch does not get the client's b2b row
    for_b = await _pull(world.client, world.tok_b, world.since)
    assert not [u for t, u in for_b if t == "clientes_b2b"]


async def test_vehiculo_with_an_unrelated_placa_is_not_delivered(world: World) -> None:
    from sqlalchemy import select

    sub = _model("subscripciones_cliente")
    async with world.sessions() as s:
        linked = world.factory.build(_model("vehiculos"), placa=f"L{uuid_lib.uuid4().hex[:6]}")
        stranger = world.factory.build(_model("vehiculos"), placa=f"S{uuid_lib.uuid4().hex[:6]}")
        s.add_all([linked, stranger])
        await s.commit()
        sc_a = (
            await s.execute(select(sub).where(sub.uuid_sucursal == world.suc_a))
        ).scalars().one()
        s.add(
            world.factory.build(
                _model("subscripcion_vehiculos"),
                uuid_subscripcion_cliente=sc_a.uuid,
                uuid_vehiculo=linked.uuid,
            )
        )
        await s.commit()

    pulled = {u for t, u in await _pull(world.client, world.tok_a, world.since) if t == "vehiculos"}
    assert pulled == {str(linked.uuid)}


# ---------------------------------------------------------------------------
# identity alias writer + motor-level remap
# ---------------------------------------------------------------------------

_AUDIT_SKIP = {"uuid", "created_at", "created_by", "sync_status", "sync_attempts", "sync_timestamp"}
_VERSION_SKIP = {"vigente_desde", "vigente_hasta", "estado"}


def _spec(name: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[name]


def _twin(factory, row):
    """A new row (new uuid) carrying the same business columns as ``row``."""
    model = type(row)
    copy = {
        c.name: getattr(row, c.name)
        for c in model.__table__.columns
        if c.name not in _AUDIT_SKIP and c.name not in _VERSION_SKIP
    }
    return factory.build(model, **copy)


async def _aliases(world: World, origen) -> list[tuple[str, str]]:
    from sqlalchemy import text

    async with world.sessions() as s:
        rows = await s.execute(
            text(
                "SELECT uuid_origen::text, uuid_resuelto::text "
                "FROM prod.sync_identity_alias WHERE uuid_origen = :o"
            ),
            {"o": origen},
        )
        return [tuple(r) for r in rows.all()]


async def _push_batch(client, token: str, items: list[tuple[str, object]]) -> list[str]:
    resp = await client.post(
        "/api/v1/sync/events",
        json={
            "events": [
                {
                    "event_type": "row_push",
                    "tabla": tabla,
                    "uuid_registro": str(row.uuid),
                    "payload": _wire(row),
                }
                for tabla, row in items
            ]
        },
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": uuid_lib.uuid4().hex},
    )
    assert resp.status_code in (200, 207), resp.text
    return [r["status"] for r in resp.json()["results"]]


def _sc_b(world: World, x_b):
    return world.factory.build(
        _model("subscripciones_cliente"),
        uuid_sucursal=world.suc_b,
        uuid_cliente=x_b.uuid,
        uuid_tipo_subscripcion=world.tipo,
    )


async def test_identical_push_records_the_alias(world: World) -> None:
    x_b = world.b_version(same_data=True)
    await _push(world.client, world.tok_b, "clientes", x_b)
    assert await _aliases(world, x_b.uuid) == [(str(x_b.uuid), str(world.x_a.uuid))]


async def test_dependent_subscription_is_stored_on_the_canonical_cliente(world: World) -> None:
    from sqlalchemy import select

    x_b = world.b_version(same_data=True)
    sc_b = _sc_b(world, x_b)
    await _push(world.client, world.tok_b, "clientes", x_b)
    assert await _push(world.client, world.tok_b, "subscripciones_cliente", sc_b) == "applied"

    sub = _model("subscripciones_cliente")
    async with world.sessions() as s:
        stored = (await s.execute(select(sub).where(sub.uuid == sc_b.uuid))).scalars().one()
    assert stored.uuid_cliente == world.x_a.uuid, "FK repointed onto A's row; own uuid kept"


async def test_cliente_and_subscription_in_one_batch_respect_ordering(world: World) -> None:
    """The alias written by the cliente row is visible to the dependent of the SAME
    request (why the remap lives in the motor and is not pre-resolved per request)."""
    x_b = world.b_version(same_data=True)
    sc_b = _sc_b(world, x_b)
    statuses = await _push_batch(
        world.client,
        world.tok_b,
        [("subscripciones_cliente", sc_b), ("clientes", x_b)],  # child listed first
    )
    assert statuses == ["applied", "applied"]


async def test_vehiculo_and_subscripcion_vehiculos_pair(world: World) -> None:
    from sqlalchemy import select, text

    sub = _model("subscripciones_cliente")
    async with world.sessions() as s:
        v_a = world.factory.build(_model("vehiculos"), placa=f"P{uuid_lib.uuid4().hex[:6]}")
        s.add(v_a)
        await s.commit()
        sc_a = (
            await s.execute(select(sub).where(sub.uuid_sucursal == world.suc_a))
        ).scalars().one()
    v_b = _twin(world.factory, v_a)
    sv_b = world.factory.build(
        _model("subscripcion_vehiculos"),
        uuid_subscripcion_cliente=sc_a.uuid,
        uuid_vehiculo=v_b.uuid,
    )
    assert await _push(world.client, world.tok_b, "vehiculos", v_b) == "applied"
    assert await _push(world.client, world.tok_b, "subscripcion_vehiculos", sv_b) == "applied"
    async with world.sessions() as s:
        row = (
            await s.execute(
                text("SELECT uuid_vehiculo FROM prod.subscripcion_vehiculos WHERE uuid = :u"),
                {"u": sv_b.uuid},
            )
        ).one()
    assert row.uuid_vehiculo == v_a.uuid


async def test_replaying_the_same_cliente_push_writes_no_second_alias(world: World) -> None:
    x_b = world.b_version(same_data=True)
    await _push(world.client, world.tok_b, "clientes", x_b)
    await _push(world.client, world.tok_b, "clientes", x_b)
    assert len(await _aliases(world, x_b.uuid)) == 1


async def test_legacy_engine_push_does_not_reconcile_and_writes_no_alias(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documents the legacy default: ``PARKOS_SYNC_ENGINE=legacy`` never looks up the
    open version, so ``identity_reconciler`` does not run and no alias is written."""
    monkeypatch.setenv("PARKOS_SYNC_ENGINE", "legacy")
    engine_flag._reset_cache_for_tests()
    x_b = world.b_version(same_data=True)
    try:
        await _push(world.client, world.tok_b, "clientes", x_b)
    finally:
        engine_flag._reset_cache_for_tests()
    assert await _aliases(world, x_b.uuid) == []
    open_uuids = {r.uuid for r in await world.open_rows()}
    assert x_b.uuid in open_uuids, "legacy stores B's row as a plain insert (no reconciliation)"


async def test_branch_pull_of_the_canonical_cliente_collapses_onto_the_local_one(
    world: World,
) -> None:
    """Branch-side mirror: B holds its own open cliente (uB); the cloud's identical uA
    arrives by pull. One open row remains, uA is aliased to uB, B's own subscription
    pulled back with uuid_cliente=uA does not violate the FK (``row_already_present``)
    and a foreign subscription naming uA is remapped onto uB."""
    from parkos_core.sync.motor.sync_motor import SyncMotor
    from sqlalchemy import select

    key = f"K{uuid_lib.uuid4().hex[:8]}"
    clientes = _model("clientes")
    sub = _model("subscripciones_cliente")
    async with world.sessions() as s:
        u_b = world.factory.build(
            clientes, tipo_identificador="CC", numero_identificacion=key, telefono="3002222222"
        )
        s.add(u_b)
        await s.commit()
        sc_own = world.factory.build(
            sub, uuid_sucursal=world.suc_b, uuid_cliente=u_b.uuid, uuid_tipo_subscripcion=world.tipo
        )
        s.add(sc_own)
        await s.commit()
    u_a = _twin(world.factory, u_b)
    sc_other = world.factory.build(
        sub, uuid_sucursal=world.suc_b, uuid_cliente=u_a.uuid, uuid_tipo_subscripcion=world.tipo
    )
    sc_pulled_back = _wire(sc_own) | {"uuid_cliente": str(u_a.uuid)}

    motor = SyncMotor(engine=engine_flag.EngineMode.CATALOG_BRANCH)
    actor = uuid_lib.uuid4()
    async with world.sessions() as s:
        r1 = await motor.apply_row(s, _spec("clientes"), _wire(u_a), actor_uuid=actor)
        spec_sc = _spec("subscripciones_cliente")
        r2 = await motor.apply_row(s, spec_sc, _wire(sc_other), actor_uuid=actor)
        r3 = await motor.apply_row(s, spec_sc, sc_pulled_back, actor_uuid=actor)
        await s.commit()
    assert (r1.status, r2.status, r3.status) == ("APPLIED", "APPLIED", "APPLIED")

    async with world.sessions() as s:
        open_ = (
            await s.execute(
                select(clientes).where(
                    clientes.numero_identificacion == key, clientes.vigente_hasta.is_(None)
                )
            )
        ).scalars().all()
        other = (await s.execute(select(sub).where(sub.uuid == sc_other.uuid))).scalars().one()
        own = (await s.execute(select(sub).where(sub.uuid == sc_own.uuid))).scalars().one()
    assert [r.uuid for r in open_] == [u_b.uuid]
    assert other.uuid_cliente == u_b.uuid
    assert own.uuid_cliente == u_b.uuid
    assert await _aliases(world, u_a.uuid) == [(str(u_a.uuid), str(u_b.uuid))]
