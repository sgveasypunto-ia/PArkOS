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
* ``reconciliation`` writes NO ``sync_identity_alias`` row and never rewrites a FK
  (Phase 0 finding), so nothing links B's uuid to A's.

The tests that PASS pin the behavior that holds. The ``xfail(strict=True)`` tests
pin the REAL GAPS this exposes, stating the behavior that would be correct; each
flips to a hard failure the day the gap is closed, forcing the marker off.
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "GAP: the derived scope matches clientes by uuid, but a [V] version bump mints a new "
        "uuid and subscripciones_cliente / factura_electronica keep pointing at the OLD one "
        "(close_and_insert never rewrites those FKs; readers resolve by natural key via "
        "v_clientes_actual). After the cloud closes A's version and opens B's, A's scope "
        "('uuid IN subscription/invoice cliente ids') matches only the closed row, so A is "
        "never sent the canonical open version. all_branches used to deliver it."
    ),
)
async def test_divergent_a_receives_the_canonical_open_version(world: World) -> None:
    x_b = world.b_version(same_data=False)
    await _push(world.client, world.tok_b, "clientes", x_b)

    pulled = world.clientes(await _pull(world.client, world.tok_a, world.since))
    assert pulled == {str(x_b.uuid)}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "GAP (same root cause as the divergent case, no reconciliation needed): editing a "
        "subscribed cliente at the cloud (close_and_insert -> new uuid) leaves the branch's "
        "subscription pointing at the closed version, so the edit never reaches the branch."
    ),
)
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "GAP (pre-existing, Phase 0): identity reconciliation is a noop without a "
        "sync_identity_alias row, so B's local cliente uuid is unknown to the cloud and "
        "every dependent B pushes (subscripciones_cliente, factura_electronica, ...) fails "
        "with a FK violation (apply_error) forever. The derived pull scope does not change "
        "this: B has no subscription/invoice on A's uuid, so A's row is never pulled either."
    ),
)
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "GAP (same root cause as the cliente version bump): subscripcion_vehiculos keeps "
        "pointing at the closed vehiculos uuid after close_and_insert, so the branch's "
        "subscription no longer matches the open version and the edit is never delivered."
    ),
)
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
