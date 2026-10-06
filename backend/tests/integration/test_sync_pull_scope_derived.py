"""test_sync_pull_scope_derived.py — RED tests for the derived pull scope.

``usuarios``, ``permisos_usuario``, ``clientes``, ``clientes_b2b`` and
``vehiculos`` carry no ``uuid_sucursal`` and are declared ``all_branches``
today, so every branch receives every user (``password_hash`` included),
client and plate in the network. The intended scope, derived through bridge
tables, is:

  usuarios / permisos_usuario  users with a vigente ``usuarios_sucursal`` row
                               at the pulling branch
  clientes                     a ``subscripciones_cliente`` or an emitted
                               ``factura_electronica`` at the pulling branch
  clientes_b2b                 follows its cliente
  vehiculos                    ``subscripcion_vehiculos`` whose subscription
                               belongs to the pulling branch

Tests named ``..._not_leaked`` / ``..._never_...`` fail today (the leak).
The ``..._still_delivered`` tests pass today and must keep passing once the
scope is narrowed.
"""

from __future__ import annotations

import uuid as uuid_lib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

PULL_URL = "/api/v1/sync/pull"


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _model(table: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[table].model_cls


async def _pull(client, token: str, since_seq: int):
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


@dataclass
class Scope:
    ids: dict[str, uuid_lib.UUID] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    pulled: set[tuple[str, str]] = field(default_factory=set)
    raw_body: str = ""

    def has(self, table: str, who: str) -> bool:
        return (table, str(self.ids[f"{table}:{who}"])) in self.pulled


async def _seed(engine, factory) -> tuple[Scope, uuid_lib.UUID, int]:
    """Seed users / clients / vehicles around branches A and B.

    Suffix legend: ``a`` belongs to A, ``b`` to B, ``none`` to nobody,
    ``closed`` is a user whose membership at A was closed, ``inv`` is a
    client known to A only through an issued invoice.
    """
    from parkos_core.models.L_E.factura_electronica import FacturaElectronica
    from sqlalchemy.ext.asyncio import async_sessionmaker

    since_seq = _now_ms() - 2
    now = datetime.now(UTC).replace(tzinfo=None)
    tag = uuid_lib.uuid4().hex[:8]
    sc = Scope()

    def build(table: str, who: str, **kw):
        row = factory.build(_model(table), **kw)
        sc.ids[f"{table}:{who}"] = row.uuid
        return row

    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        users = ("a", "b", "none", "closed")
        for who in users:
            sc.secrets[who] = f"$2b$12$PW-{who}-{tag}"
        stage1 = [
            build("sucursal", "a", nombre=f"A-{tag}"),
            build("sucursal", "b", nombre=f"B-{tag}"),
            build("permisos", "x", permiso=f"perm-{tag}"),
            build("tipo_subscripciones", "x"),
        ]
        stage1 += [
            build(
                "usuarios",
                who,
                email=f"{who}-{tag}@test.local",
                cedula=f"{who}-{tag}",
                password_hash=sc.secrets[who],
                rol="operador",
            )
            for who in users
        ]
        stage1 += [
            build("clientes", who, numero_identificacion=f"{who}-{tag}")
            for who in ("sub_a", "sub_b", "inv_a", "none")
        ]
        stage1 += [build("vehiculos", who, placa=f"{who}-{tag}"[:12]) for who in ("a", "b", "none")]
        s.add_all(stage1)
        await s.commit()

        suc_a, suc_b = sc.ids["sucursal:a"], sc.ids["sucursal:b"]
        stage2 = [
            build("usuarios_sucursal", "a", uuid_sucursal=suc_a, uuid_usuario=sc.ids["usuarios:a"]),
            build("usuarios_sucursal", "b", uuid_sucursal=suc_b, uuid_usuario=sc.ids["usuarios:b"]),
            build(
                "usuarios_sucursal",
                "closed",
                uuid_sucursal=suc_a,
                uuid_usuario=sc.ids["usuarios:closed"],
                vigente_hasta=now,
                estado="inactivo",
            ),
            build(
                "subscripciones_cliente",
                "a",
                uuid_sucursal=suc_a,
                uuid_cliente=sc.ids["clientes:sub_a"],
                uuid_tipo_subscripcion=sc.ids["tipo_subscripciones:x"],
            ),
            build(
                "subscripciones_cliente",
                "b",
                uuid_sucursal=suc_b,
                uuid_cliente=sc.ids["clientes:sub_b"],
                uuid_tipo_subscripcion=sc.ids["tipo_subscripciones:x"],
            ),
        ]
        for who in users:
            stage2.append(
                build(
                    "permisos_usuario",
                    who,
                    uuid_usuario=sc.ids[f"usuarios:{who}"],
                    uuid_permiso=sc.ids["permisos:x"],
                )
            )
        for who in ("sub_a", "sub_b", "inv_a", "none"):
            stage2.append(build("clientes_b2b", who, uuid_cliente=sc.ids[f"clientes:{who}"]))
        invoice = FacturaElectronica(
            uuid=uuid_lib.uuid4(),
            created_at=now,
            uuid_sucursal=suc_a,
            uuid_cliente=sc.ids["clientes:inv_a"],
            fecha_retencion_hasta=now.date().replace(year=now.year + 6),
        )
        stage2.append(invoice)
        s.add_all(stage2)
        await s.commit()

        s.add_all(
            [
                build(
                    "subscripcion_vehiculos",
                    who,
                    uuid_subscripcion_cliente=sc.ids[f"subscripciones_cliente:{who}"],
                    uuid_vehiculo=sc.ids[f"vehiculos:{who}"],
                )
                for who in ("a", "b")
            ]
        )
        await s.commit()

    return sc, suc_a, since_seq


@pytest.fixture
async def scope(client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory, retire):
    sc, suc_a, since_seq = await _seed(pg_engine, v_fixture_factory)
    by_table: dict[str, list[uuid_lib.UUID]] = {}
    for name, row_uuid in sc.ids.items():
        by_table.setdefault(name.split(":")[0], []).append(row_uuid)
    for table, ids in by_table.items():
        retire(table, ids)
    token = mint_sync_agent_jwt(scope="branch", sucursal_uuid=suc_a)
    resp = await _pull(client, token, since_seq)
    assert resp.status_code == 200, resp.text
    sc.raw_body = resp.text
    sc.pulled = {(r["tabla"], r["uuid_registro"]) for r in resp.json()["rows"]}
    return sc


# ---------------------------------------------------------------------------
# usuarios / permisos_usuario
# ---------------------------------------------------------------------------


async def test_usuarios_still_delivered_for_vigente_members(scope: Scope, app) -> None:
    assert scope.has("usuarios", "a")


@pytest.mark.parametrize("who", ["b", "none", "closed"])
async def test_usuarios_outside_branch_membership_not_leaked(scope: Scope, who: str, app) -> None:
    assert not scope.has("usuarios", who), (
        f"usuario '{who}' has no vigente usuarios_sucursal row at A"
    )


async def test_permisos_usuario_still_delivered_for_vigente_members(scope: Scope, app) -> None:
    assert scope.has("permisos_usuario", "a")


@pytest.mark.parametrize("who", ["b", "none", "closed"])
async def test_permisos_usuario_outside_branch_membership_not_leaked(
    scope: Scope, who: str, app
) -> None:
    assert not scope.has("permisos_usuario", who), f"{who}: leaked into the pull of A"


# ---------------------------------------------------------------------------
# clientes / clientes_b2b / vehiculos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["sub_a", "inv_a"])
async def test_clientes_with_subscription_or_invoice_still_delivered(
    scope: Scope, who: str, app
) -> None:
    assert scope.has("clientes", who)
    assert scope.has("clientes_b2b", who)


@pytest.mark.parametrize("who", ["sub_b", "none"])
async def test_clientes_without_activity_at_branch_not_leaked(scope: Scope, who: str, app) -> None:
    assert not scope.has("clientes", who), f"cliente '{who}' has no subscription or invoice at A"


@pytest.mark.parametrize("who", ["sub_b", "none"])
async def test_clientes_b2b_follow_their_cliente_not_leaked(scope: Scope, who: str, app) -> None:
    assert not scope.has("clientes_b2b", who), f"{who}: leaked into the pull of A"


async def test_vehiculos_with_branch_subscription_still_delivered(scope: Scope, app) -> None:
    assert scope.has("vehiculos", "a")


@pytest.mark.parametrize("who", ["b", "none"])
async def test_vehiculos_without_subscription_at_branch_not_leaked(
    scope: Scope, who: str, app
) -> None:
    assert not scope.has("vehiculos", who), f"{who}: leaked into the pull of A"


# ---------------------------------------------------------------------------
# password_hash
# ---------------------------------------------------------------------------


async def test_member_password_hash_still_delivered(scope: Scope, app) -> None:
    assert scope.secrets["a"] in scope.raw_body


@pytest.mark.parametrize("who", ["b", "none", "closed"])
async def test_password_hash_of_non_members_never_in_response(scope: Scope, who: str, app) -> None:
    assert scope.secrets[who] not in scope.raw_body, (
        f"password_hash of usuario '{who}' (not a member of A) is on the wire"
    )
