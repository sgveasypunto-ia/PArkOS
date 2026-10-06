"""test_sync_pull_scope_matrix.py — per-table scope matrix for ``POST /sync/pull``.

Every catalog entry a branch may pull (``direction`` in ``cloud_to_branch`` /
``bidirectional`` with a non-``None`` ``broadcast_policy``) is classified in
``EXPECTED_SCOPE``. A meta-test fails if an entry is added to (or removed
from) the catalog without deciding its scope here.

Classes:
  global        every branch receives the row
  owned         only the branch named by ``uuid_sucursal`` (``sucursal``: its own uuid)
  override      NULL ``uuid_sucursal`` = global default, otherwise only that branch
  subscription  only the branch that sold the subscription (directly or via parent)
  derived       scope derived through bridge tables; leak tests live in
                ``test_sync_pull_scope_derived.py``

The edge tests pin the endpoint contract that must survive the SQL push-down:
auth failures, the per-call row cap and the ``next_seq`` cursor.
"""

from __future__ import annotations

import functools
import uuid as uuid_lib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from tests.pull_scope_expected import EXPECTED_SCOPE

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

PULL_URL = "/api/v1/sync/pull"

GLOBAL_TABLES = sorted(t for t, c in EXPECTED_SCOPE.items() if c == "global")
OWNED_TABLES = sorted(t for t, c in EXPECTED_SCOPE.items() if c == "owned")
OVERRIDE_TABLES = sorted(t for t, c in EXPECTED_SCOPE.items() if c == "override")
SUBSCRIPTION_TABLES = sorted(t for t, c in EXPECTED_SCOPE.items() if c == "subscription")


def _model(table: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[table].model_cls


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


async def _pull(client, token: str, since_seq: int = 0):
    # Distinct X-Request-Id per call: the endpoint's idempotency cache would
    # otherwise replay the first response.
    return await client.post(
        PULL_URL,
        json={"since_seq": since_seq},
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": uuid_lib.uuid4().hex},
    )


async def _retire(engine, pending: list[tuple[str, list[uuid_lib.UUID]]]) -> None:
    """Close the vigente version of every row a test created.

    The pull caps at 500 rows ordered by ``created_at`` and reads only open
    ``[V]`` versions, so leaving test rows open would push later tests'
    rows past the cap. Logical close only, never a DELETE.
    """
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(UTC).replace(tzinfo=None)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        for table, ids in pending:
            model = _model(table)
            await s.execute(
                update(model)
                .where(model.uuid.in_(ids), model.vigente_hasta.is_(None))
                .values(vigente_hasta=now, estado="inactivo")
            )
        await s.commit()


@pytest.fixture
async def retire(pg_engine):
    pending: list[tuple[str, list[uuid_lib.UUID]]] = []
    yield lambda table, ids: pending.append((table, list(ids)))
    await _retire(pg_engine, pending)


def _keys(body: dict) -> set[tuple[str, str]]:
    return {(r["tabla"], r["uuid_registro"]) for r in body["rows"]}


@dataclass
class World:
    """Two branches with one row per scope class, plus what each one pulled."""

    suc_a: uuid_lib.UUID
    suc_b: uuid_lib.UUID
    ids: dict[tuple[str, str], uuid_lib.UUID] = field(default_factory=dict)
    pulled: dict[str, set[tuple[str, str]]] = field(default_factory=dict)

    def key(self, table: str, who: str) -> tuple[str, str]:
        return (table, str(self.ids[(table, who)]))


async def _seed_world(engine, factory) -> tuple[World, int]:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    since_seq = _now_ms() - 2  # only rows created by this seed are pulled back
    Session = async_sessionmaker(engine, expire_on_commit=False)
    ids: dict[tuple[str, str], uuid_lib.UUID] = {}

    def build(table: str, who: str, **kw):
        row = factory.build(_model(table), **kw)
        ids[(table, who)] = row.uuid
        return row

    tag = uuid_lib.uuid4().hex[:8]
    async with Session() as s:
        stage1 = [
            build("sucursal", "a", nombre=f"A-{tag}"),
            build("sucursal", "b", nombre=f"B-{tag}"),
            build("usuarios", "a", email=f"a-{tag}@test.local"),
            build("usuarios", "b", email=f"b-{tag}@test.local"),
            build("clientes", "a", numero_identificacion=f"A{tag}"),
            build("clientes", "b", numero_identificacion=f"B{tag}"),
            build("vehiculos", "a", placa=f"A{tag}"),
            build("vehiculos", "b", placa=f"B{tag}"),
        ]
        stage1 += [build(t, "global") for t in GLOBAL_TABLES]
        s.add_all(stage1)
        await s.commit()

        suc_a, suc_b = ids[("sucursal", "a")], ids[("sucursal", "b")]
        tipo_veh = ids[("tipos_vehiculo", "global")]
        tipo_tarifa = ids[("tipo_tarifa", "global")]
        tipo_sub = ids[("tipo_subscripciones", "global")]

        stage2 = []
        for who, suc in (("a", suc_a), ("b", suc_b)):
            stage2 += [
                build("resolucion_facturacion", who, uuid_sucursal=suc, prefijo=f"{who}{tag}"),
                build(
                    "usuarios_sucursal", who, uuid_sucursal=suc, uuid_usuario=ids[("usuarios", who)]
                ),
                build("documentos", who, uuid_sucursal=suc, tipo=f"doc-{who}-{tag}"),
                build(
                    "tarifas_sucursal",
                    who,
                    uuid_sucursal=suc,
                    uuid_tipo_vehiculo=tipo_veh,
                    uuid_tipo_tarifa=tipo_tarifa,
                ),
                build(
                    "cantidad_vehiculos_sucursal",
                    who,
                    uuid_sucursal=suc,
                    uuid_tipo_vehiculo=tipo_veh,
                    cantidad=1,
                ),
                build("configuracion_tolerancias", who, uuid_sucursal=suc),
                build("configuracion_seguridad", who, uuid_sucursal=suc),
                build(
                    "subscripciones_cliente",
                    who,
                    uuid_sucursal=suc,
                    uuid_cliente=ids[("clientes", who)],
                    uuid_tipo_subscripcion=tipo_sub,
                ),
            ]
        stage2 += [
            build("configuracion_tolerancias", "global", uuid_sucursal=None),
            build("configuracion_seguridad", "global", uuid_sucursal=None),
        ]
        s.add_all(stage2)
        await s.commit()

        stage3 = [
            build(
                "subscripcion_vehiculos",
                who,
                uuid_subscripcion_cliente=ids[("subscripciones_cliente", who)],
                uuid_vehiculo=ids[("vehiculos", who)],
            )
            for who in ("a", "b")
        ]
        s.add_all(stage3)
        await s.commit()

    return World(suc_a=suc_a, suc_b=suc_b, ids=ids), since_seq


@pytest.fixture
async def world(client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory, retire):
    w, since_seq = await _seed_world(pg_engine, v_fixture_factory)
    by_table: dict[str, list[uuid_lib.UUID]] = {}
    for (table, _who), row_uuid in w.ids.items():
        by_table.setdefault(table, []).append(row_uuid)
    for table, ids in by_table.items():
        retire(table, ids)
    for who, suc in (("a", w.suc_a), ("b", w.suc_b)):
        token = mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc)
        resp = await _pull(client, token, since_seq)
        assert resp.status_code == 200, resp.text
        w.pulled[who] = _keys(resp.json())
    return w


# ---------------------------------------------------------------------------
# Meta-test: the matrix covers exactly the pull-eligible catalog
# ---------------------------------------------------------------------------


def test_expected_scope_matches_pull_eligible_catalog(app) -> None:
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG

    eligible = {
        s.name
        for s in SYNC_CATALOG
        if s.direction in {"cloud_to_branch", "bidirectional"} and s.broadcast_policy is not None
    }
    assert eligible - set(EXPECTED_SCOPE) == set(), "catalog entries with no decided pull scope"
    assert set(EXPECTED_SCOPE) - eligible == set(), "EXPECTED_SCOPE names non pull-eligible entries"
    assert len(EXPECTED_SCOPE) == 26


# ---------------------------------------------------------------------------
# global / owned / override / subscription
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", GLOBAL_TABLES)
async def test_global_row_reaches_every_branch(world: World, table: str, app) -> None:
    assert world.key(table, "global") in world.pulled["a"]
    assert world.key(table, "global") in world.pulled["b"]


@pytest.mark.parametrize("table", OWNED_TABLES)
async def test_owned_rows_never_cross_branches(world: World, table: str, app) -> None:
    a_row, b_row = world.key(table, "a"), world.key(table, "b")
    assert a_row in world.pulled["a"]
    assert b_row in world.pulled["b"]
    assert b_row not in world.pulled["a"], f"{table}: A received B's row"
    assert a_row not in world.pulled["b"], f"{table}: B received A's row"


@pytest.mark.parametrize("table", OVERRIDE_TABLES)
async def test_override_gives_global_default_and_own_override_only(
    world: World, table: str, app
) -> None:
    default = world.key(table, "global")
    a_row, b_row = world.key(table, "a"), world.key(table, "b")
    assert {default, a_row} <= world.pulled["a"]
    assert {default, b_row} <= world.pulled["b"]
    assert b_row not in world.pulled["a"], f"{table}: A received B's override"
    assert a_row not in world.pulled["b"], f"{table}: B received A's override"


async def test_subscription_direct_stays_in_selling_branch(world: World, app) -> None:
    a_row = world.key("subscripciones_cliente", "a")
    b_row = world.key("subscripciones_cliente", "b")
    assert a_row in world.pulled["a"]
    assert b_row in world.pulled["b"]
    assert b_row not in world.pulled["a"]
    assert a_row not in world.pulled["b"]


async def test_subscription_transitive_follows_parent_branch(world: World, app) -> None:
    a_row = world.key("subscripcion_vehiculos", "a")
    b_row = world.key("subscripcion_vehiculos", "b")
    assert a_row in world.pulled["a"]
    assert b_row in world.pulled["b"]
    # parent subscription belongs to B: the child must never reach A
    assert b_row not in world.pulled["a"]
    assert a_row not in world.pulled["b"]


# ---------------------------------------------------------------------------
# Edge cases: auth
# ---------------------------------------------------------------------------


async def test_pull_rejects_revoked_token(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, app
) -> None:
    from parkos_core.api.v1.sync_router import decode_jwt_header_kid
    from parkos_core.auth.tokens import verify_token
    from parkos_core.repo.revoked_sync_jwt import revoke_jwt
    from sqlalchemy.ext.asyncio import async_sessionmaker

    token = mint_sync_agent_jwt(scope="branch")
    ok = await _pull(client, token, _now_ms())
    assert ok.status_code == 200, ok.text

    async with async_sessionmaker(pg_engine, expire_on_commit=False)() as s:
        await revoke_jwt(
            s,
            kid=decode_jwt_header_kid(token),
            jwt_uuid=str(verify_token(token)["jti"]),
            motivo="scope-matrix-test",
            actor_uuid=None,
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        )
        await s.commit()

    resp = await _pull(client, token, _now_ms())
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "sync_jwt_revoked"


@pytest.mark.parametrize("scope", ["cloud", "admin"])
async def test_pull_requires_branch_scope(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, scope: str, app
) -> None:
    resp = await _pull(client, mint_sync_agent_jwt(scope=scope))
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "pull_requires_branch_scope"


@pytest.mark.parametrize(
    "claims",
    [
        {"scope": "branch"},
        {"scope": "branch", "sucursal": None},
        {"scope": "branch", "sucursal": ""},
        {"scope": "branch", "sucursal": "not-a-uuid"},
    ],
    ids=["missing", "null", "empty", "malformed"],
)
async def test_pull_rejects_missing_or_malformed_sucursal_claim(
    client, pg_engine, alembic_upgrade, claims: dict, app
) -> None:
    from parkos_core.auth.tokens import issue_token

    token = issue_token(subject_uuid=uuid_lib.uuid4(), issuer="sync-agent-test", claims=claims)
    resp = await _pull(client, token)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "missing_or_invalid_sucursal_claim"


# ---------------------------------------------------------------------------
# Edge cases: row cap and next_seq cursor
# ---------------------------------------------------------------------------


def test_pull_batch_limit_constant_is_500(app) -> None:
    from parkos_core.api.v1 import sync_router

    assert sync_router._PULL_BATCH_LIMIT == 500


@pytest.fixture
def small_pull_limit(monkeypatch):
    """Cap pulls at 2 rows.

    ``_PULL_BATCH_LIMIT`` is bound as a default argument of
    ``_fetch_pull_rows`` at import time, so patching the constant has no
    effect; wrapping the function is what actually changes the cap.
    """
    from parkos_core.api.v1 import sync_router

    limit = 2
    monkeypatch.setattr(
        sync_router,
        "_fetch_pull_rows",
        functools.partial(sync_router._fetch_pull_rows, limit=limit),
    )
    return limit


async def _seed_global_tipos(engine, factory, created_ats: list[datetime]):
    from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
    from sqlalchemy.ext.asyncio import async_sessionmaker

    rows = [
        factory.build(TiposVehiculo, tipo=f"cap-{uuid_lib.uuid4().hex[:8]}", created_at=ts)
        for ts in created_ats
    ]
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        s.add_all(rows)
        await s.commit()
    return [str(r.uuid) for r in rows]


def _ms_floor(dt: datetime) -> datetime:
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


async def test_pull_cap_and_next_seq_cursor_page_through_all_rows(
    client,
    pg_engine,
    alembic_upgrade,
    mint_sync_agent_jwt,
    v_fixture_factory,
    small_pull_limit: int,
    retire,
    app,
) -> None:
    since_seq = _now_ms() - 2
    base = _ms_floor(datetime.now(UTC).replace(tzinfo=None))
    expected = await _seed_global_tipos(
        pg_engine, v_fixture_factory, [base + timedelta(milliseconds=10 * i) for i in range(5)]
    )
    retire("tipos_vehiculo", [uuid_lib.UUID(u) for u in expected])
    token = mint_sync_agent_jwt(scope="branch")

    seen: list[str] = []
    cursor = since_seq
    for _ in range(10):
        resp = await _pull(client, token, cursor)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["rows"]) <= small_pull_limit
        if not body["rows"]:
            assert body["next_seq"] == cursor, "an empty page must not move the cursor"
            break
        seqs = [r["seq"] for r in body["rows"]]
        assert seqs == sorted(seqs)
        assert body["next_seq"] == seqs[-1]
        assert body["next_seq"] > cursor
        seen += [r["uuid_registro"] for r in body["rows"]]
        cursor = body["next_seq"]
    else:
        pytest.fail("cursor never reached an empty page")

    assert seen == expected, "pages must be disjoint, ordered by created_at, and complete"


async def test_pull_cursor_with_one_ms_overlap_recovers_tied_rows(
    client,
    pg_engine,
    alembic_upgrade,
    mint_sync_agent_jwt,
    v_fixture_factory,
    small_pull_limit: int,
    retire,
    app,
) -> None:
    """Rows sharing one ``created_at`` millisecond can straddle a page boundary.

    The branch worker re-pulls from ``next_seq - 1`` (1 ms overlap) and relies
    on idempotent apply, so the tied row must come back on the next page.
    """
    since_seq = _now_ms() - 2
    base = _ms_floor(datetime.now(UTC).replace(tzinfo=None))
    tied = base + timedelta(milliseconds=20)
    seeded = await _seed_global_tipos(pg_engine, v_fixture_factory, [base, tied, tied])
    retire("tipos_vehiculo", [uuid_lib.UUID(u) for u in seeded])
    expected = set(seeded)
    token = mint_sync_agent_jwt(scope="branch")

    first = (await _pull(client, token, since_seq)).json()
    assert len(first["rows"]) == small_pull_limit
    second = (await _pull(client, token, first["next_seq"] - 1)).json()

    got = {r["uuid_registro"] for r in first["rows"]} | {r["uuid_registro"] for r in second["rows"]}
    assert got == expected, "a row tied on created_at at the page boundary was lost"


async def test_pull_since_seq_beyond_everything_returns_nothing(
    client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, app
) -> None:
    far_future = _now_ms() + 10 * 365 * 24 * 3600 * 1000
    resp = await _pull(client, mint_sync_agent_jwt(scope="branch"), far_future)
    assert resp.status_code == 200
    assert resp.json() == {"rows": [], "next_seq": far_future}
