"""test_sync_pull_scope_entry.py — scope-entry delivery of ``derived`` rows.

The production worker pulls INCREMENTALLY (``since_seq`` = cursor - 1). For a
``derived`` table the row's own ``created_at`` says nothing about when it ENTERED
the branch's scope: a user created long ago and assigned to branch A today has an
old ``created_at`` and a fresh ``usuarios_sucursal`` bridge row. Filtering by
``created_at`` alone delivers the bridge row and never the user (offline login
breaks). Every scenario here pulls with ``since_seq`` set just before the bridge
row exists and after the parent's ``created_at``.

Parents are created ``_OLD`` ago; bridge rows are created "now" (``t0 + i ms``).
"""

from __future__ import annotations

import functools
import uuid as uuid_lib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

_OLD = timedelta(days=1)
_SINGLETON_INDEX = "empresa_singleton_uk"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _ms(moment: datetime) -> int:
    return (moment - datetime(1970, 1, 1)) // timedelta(milliseconds=1)


def _model(table: str):
    from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME

    return SYNC_CATALOG_BY_NAME[table].model_cls


@dataclass
class World:
    engine: object
    factory: object
    t0: datetime = field(default_factory=_now)
    ids: dict[str, uuid_lib.UUID] = field(default_factory=dict)
    since_seq: int = 0

    def __post_init__(self) -> None:
        self.since_seq = _ms(self.t0) - 1
        self.old = self.t0 - _OLD

    def at(self, offset_ms: int = 0) -> datetime:
        """A bridge-row ``created_at`` inside the pull window."""
        return self.t0 + timedelta(milliseconds=offset_ms)

    def build(self, table: str, who: str, **kw):
        row = self.factory.build(_model(table), **kw)
        self.ids[f"{table}:{who}"] = row.uuid
        return row

    def old_row(self, table: str, who: str, **kw):
        return self.build(table, who, **{"created_at": self.old, "vigente_desde": self.old, **kw})

    def session(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        return async_sessionmaker(self.engine, expire_on_commit=False)()

    async def add(self, *rows) -> None:
        async with self.session() as s:
            s.add_all(rows)
            await s.commit()

    async def base(self) -> None:
        """Two OLD branches, an old subscription type and an old permiso."""
        tag = uuid_lib.uuid4().hex[:8]
        await self.add(
            self.old_row("sucursal", "a", nombre=f"A-{tag}"),
            self.old_row("sucursal", "b", nombre=f"B-{tag}"),
            self.old_row("tipo_subscripciones", "x"),
            self.old_row("permisos", "x", permiso=f"perm-{tag}"),
        )

    async def pull(self, branch: str, since_seq: int | None = None, limit: int | None = None):
        from parkos_core.api.v1.sync_router import _fetch_pull_rows

        fetch = (
            _fetch_pull_rows if limit is None else functools.partial(_fetch_pull_rows, limit=limit)
        )
        async with self.session() as s:
            rows, next_seq = await fetch(
                s,
                uuid_sucursal=self.ids[f"sucursal:{branch}"],
                since_seq=self.since_seq if since_seq is None else since_seq,
            )
        return rows, next_seq

    async def pulled(self, branch: str, **kw) -> set[tuple[str, uuid_lib.UUID]]:
        rows, _ = await self.pull(branch, **kw)
        return {(r.tabla, r.uuid_registro) for r in rows}

    def has(self, pulled: set[tuple[str, uuid_lib.UUID]], table: str, who: str) -> bool:
        return (table, self.ids[f"{table}:{who}"]) in pulled

    async def retire(self) -> None:
        """Logical close of every ``[V]`` row the test created (never a DELETE)."""
        from sqlalchemy import update

        by_table: dict[str, list[uuid_lib.UUID]] = {}
        for key, value in self.ids.items():
            by_table.setdefault(key.split(":")[0], []).append(value)
        now = _now()
        async with self.session() as s:
            for table, ids in by_table.items():
                model = _model(table)
                if not hasattr(model, "vigente_hasta"):
                    continue
                await s.execute(
                    update(model)
                    .where(model.uuid.in_(ids), model.vigente_hasta.is_(None))
                    .values(vigente_hasta=now, estado="inactivo")
                )
            await s.commit()


@pytest.fixture
async def world(pg_engine, alembic_upgrade, v_fixture_factory):
    w = World(engine=pg_engine, factory=v_fixture_factory)
    await w.base()
    yield w
    await w.retire()


# ---------------------------------------------------------------------------
# usuarios / permisos_usuario
# ---------------------------------------------------------------------------


async def test_old_user_assigned_later_arrives_with_the_membership(world: World) -> None:
    await world.add(
        world.old_row(
            "usuarios",
            "u",
            email=f"u-{uuid_lib.uuid4().hex[:6]}@test.local",
            cedula=uuid_lib.uuid4().hex[:10],
            password_hash="$2b$12$x",
            rol="operador",
        ),
    )
    await world.add(
        world.old_row(
            "permisos_usuario",
            "u",
            uuid_usuario=world.ids["usuarios:u"],
            uuid_permiso=world.ids["permisos:x"],
        ),
        world.build(
            "usuarios_sucursal",
            "u",
            uuid_sucursal=world.ids["sucursal:a"],
            uuid_usuario=world.ids["usuarios:u"],
            created_at=world.at(),
        ),
    )

    got = await world.pulled("a")

    assert world.has(got, "usuarios_sucursal", "u")
    assert world.has(got, "usuarios", "u"), "the user never reached the branch (offline login)"
    assert world.has(got, "permisos_usuario", "u"), "permisos of a newly assigned user"


async def test_old_user_assigned_to_another_branch_is_not_delivered(world: World) -> None:
    await world.add(
        world.old_row(
            "usuarios",
            "u",
            email=f"u-{uuid_lib.uuid4().hex[:6]}@test.local",
            cedula=uuid_lib.uuid4().hex[:10],
            password_hash="$2b$12$x",
            rol="operador",
        ),
    )
    await world.add(
        world.old_row(
            "permisos_usuario",
            "u",
            uuid_usuario=world.ids["usuarios:u"],
            uuid_permiso=world.ids["permisos:x"],
        ),
        world.build(
            "usuarios_sucursal",
            "u",
            uuid_sucursal=world.ids["sucursal:b"],
            uuid_usuario=world.ids["usuarios:u"],
            created_at=world.at(),
        ),
    )

    got_a = await world.pulled("a")
    got_b = await world.pulled("b")

    assert not world.has(got_a, "usuarios", "u")
    assert not world.has(got_a, "permisos_usuario", "u")
    assert world.has(got_b, "usuarios", "u")


# ---------------------------------------------------------------------------
# clientes / clientes_b2b / vehiculos
# ---------------------------------------------------------------------------


async def test_old_cliente_with_a_later_subscription_arrives_with_its_b2b(world: World) -> None:
    tag = uuid_lib.uuid4().hex[:8]
    await world.add(world.old_row("clientes", "c", numero_identificacion=f"c-{tag}"))
    await world.add(world.old_row("clientes_b2b", "c", uuid_cliente=world.ids["clientes:c"]))
    await world.add(
        world.build(
            "subscripciones_cliente",
            "a",
            uuid_sucursal=world.ids["sucursal:a"],
            uuid_cliente=world.ids["clientes:c"],
            uuid_tipo_subscripcion=world.ids["tipo_subscripciones:x"],
            created_at=world.at(),
        ),
    )

    got = await world.pulled("a")

    assert world.has(got, "clientes", "c")
    assert world.has(got, "clientes_b2b", "c")
    got_b = await world.pulled("b")
    assert not world.has(got_b, "clientes", "c")
    assert not world.has(got_b, "clientes_b2b", "c")


async def test_old_cliente_with_a_later_subscription_arrives_by_natural_key(world: World) -> None:
    """The subscription points at a CLOSED old version; the OPEN version (new uuid,
    same natural key, also old) is what the branch must receive."""
    tag = uuid_lib.uuid4().hex[:8]
    await world.add(
        world.old_row(
            "clientes",
            "closed",
            tipo_identificador="CC",
            numero_identificacion=f"k-{tag}",
            vigente_hasta=world.old + timedelta(hours=1),
            estado="inactivo",
        ),
        world.old_row(
            "clientes",
            "open",
            tipo_identificador="CC",
            numero_identificacion=f"k-{tag}",
            vigente_desde=world.old + timedelta(hours=1),
        ),
    )
    await world.add(
        world.build(
            "subscripciones_cliente",
            "a",
            uuid_sucursal=world.ids["sucursal:a"],
            uuid_cliente=world.ids["clientes:closed"],
            uuid_tipo_subscripcion=world.ids["tipo_subscripciones:x"],
            created_at=world.at(),
        ),
    )

    got = await world.pulled("a")

    assert world.has(got, "clientes", "open")


async def test_old_cliente_with_a_later_invoice_arrives(world: World) -> None:
    from parkos_core.models.L_E.factura_electronica import FacturaElectronica

    tag = uuid_lib.uuid4().hex[:8]
    await world.add(world.old_row("clientes", "c", numero_identificacion=f"i-{tag}"))
    await world.add(world.old_row("clientes_b2b", "c", uuid_cliente=world.ids["clientes:c"]))
    await world.add(
        FacturaElectronica(
            uuid=uuid_lib.uuid4(),
            created_at=world.at(),
            uuid_sucursal=world.ids["sucursal:a"],
            uuid_cliente=world.ids["clientes:c"],
            fecha_retencion_hasta=world.t0.date().replace(year=world.t0.year + 6),
        )
    )

    got = await world.pulled("a")

    assert world.has(got, "clientes", "c")
    assert world.has(got, "clientes_b2b", "c")


async def test_old_vehiculo_linked_later_arrives(world: World) -> None:
    tag = uuid_lib.uuid4().hex[:8]
    await world.add(
        world.old_row("vehiculos", "v", placa=f"v-{tag}"[:12]),
        world.old_row("vehiculos", "w", placa=f"w-{tag}"[:12]),
        world.old_row("clientes", "c", numero_identificacion=f"s-{tag}"),
    )
    await world.add(
        # an OLD subscription: only the link row is new
        world.old_row(
            "subscripciones_cliente",
            "a",
            uuid_sucursal=world.ids["sucursal:a"],
            uuid_cliente=world.ids["clientes:c"],
            uuid_tipo_subscripcion=world.ids["tipo_subscripciones:x"],
        ),
    )
    await world.add(
        world.build(
            "subscripcion_vehiculos",
            "v",
            uuid_vehiculo=world.ids["vehiculos:v"],
            uuid_subscripcion_cliente=world.ids["subscripciones_cliente:a"],
            created_at=world.at(),
        ),
    )

    got = await world.pulled("a")

    assert world.has(got, "vehiculos", "v")
    assert not world.has(got, "vehiculos", "w"), "unlinked vehicle must not be delivered"


async def test_old_vehiculo_on_a_new_subscription_arrives(world: World) -> None:
    tag = uuid_lib.uuid4().hex[:8]
    await world.add(
        world.old_row("vehiculos", "v", placa=f"n-{tag}"[:12]),
        world.old_row("clientes", "c", numero_identificacion=f"n-{tag}"),
    )
    await world.add(
        world.build(
            "subscripciones_cliente",
            "a",
            uuid_sucursal=world.ids["sucursal:a"],
            uuid_cliente=world.ids["clientes:c"],
            uuid_tipo_subscripcion=world.ids["tipo_subscripciones:x"],
            created_at=world.at(),
        ),
    )
    await world.add(
        # link row older than the subscription it hangs from: only the subscription is new
        world.old_row(
            "subscripcion_vehiculos",
            "v",
            uuid_vehiculo=world.ids["vehiculos:v"],
            uuid_subscripcion_cliente=world.ids["subscripciones_cliente:a"],
        ),
    )

    assert world.has(await world.pulled("a"), "vehiculos", "v")


# ---------------------------------------------------------------------------
# empresa
# ---------------------------------------------------------------------------


async def test_empresa_delivered_when_the_branch_row_enters_the_window(
    pg_engine, alembic_upgrade, v_fixture_factory
) -> None:
    """The branch row is created after its (old) empresa: an incremental pull must
    still carry the empresa. ``empresa_singleton_uk`` allows ONE open row, so the
    index is dropped for the test and restored (with the rows it closed) after."""
    from parkos_core.models.V.empresa import Empresa
    from sqlalchemy import text, update

    w = World(engine=pg_engine, factory=v_fixture_factory)
    tag = uuid_lib.uuid4().hex[:8]
    async with w.session() as s:
        previously_open = (
            (await s.execute(text("SELECT uuid FROM prod.empresa WHERE vigente_hasta IS NULL")))
            .scalars()
            .all()
        )
        await s.execute(
            update(Empresa)
            .where(Empresa.vigente_hasta.is_(None))
            .values(vigente_hasta=w.t0, estado="inactivo")
        )
        await s.execute(text(f"DROP INDEX IF EXISTS prod.{_SINGLETON_INDEX}"))
        await s.commit()
    try:
        await w.add(
            w.old_row("empresa", "mine", nit=f"900-{tag}", nombre=f"E-{tag}"),
            w.old_row("empresa", "other", nit=f"901-{tag}", nombre=f"O-{tag}"),
        )
        await w.add(
            w.build(
                "sucursal",
                "a",
                nombre=f"A-{tag}",
                uuid_empresa=w.ids["empresa:mine"],
                created_at=w.at(),
            ),
            w.old_row("sucursal", "c", nombre=f"C-{tag}", uuid_empresa=w.ids["empresa:other"]),
        )

        got_a = await w.pulled("a")
        got_c = await w.pulled("c")

        assert w.has(got_a, "empresa", "mine"), "empresa of a newly created branch not delivered"
        assert not w.has(got_a, "empresa", "other")
        assert not w.has(got_c, "empresa", "mine")
    finally:
        await w.retire()
        async with w.session() as s:
            if previously_open:
                await s.execute(
                    update(Empresa)
                    .where(Empresa.uuid == previously_open[-1])
                    .values(vigente_hasta=None, estado="activo")
                )
            await s.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {_SINGLETON_INDEX} "
                    "ON prod.empresa ((true)) WHERE vigente_hasta IS NULL"
                )
            )
            await s.commit()


# ---------------------------------------------------------------------------
# idempotence, cursor, LIMIT, since_seq=0
# ---------------------------------------------------------------------------


async def _old_user_with_membership(world: World, who: str, offset_ms: int, branch: str = "a"):
    await world.add(
        world.old_row(
            "usuarios",
            who,
            email=f"{who}-{uuid_lib.uuid4().hex[:6]}@test.local",
            cedula=uuid_lib.uuid4().hex[:10],
            password_hash="$2b$12$x",
            rol="operador",
        ),
    )
    await world.add(
        world.build(
            "usuarios_sucursal",
            who,
            uuid_sucursal=world.ids[f"sucursal:{branch}"],
            uuid_usuario=world.ids[f"usuarios:{who}"],
            created_at=world.at(offset_ms),
        ),
    )


async def test_repeating_the_pull_is_idempotent_and_the_cursor_never_regresses(
    world: World,
) -> None:
    await _old_user_with_membership(world, "u", 5)

    first, next_first = await world.pull("a")
    second, next_second = await world.pull("a")

    assert {(r.tabla, r.uuid_registro) for r in first} == {
        (r.tabla, r.uuid_registro) for r in second
    }
    assert next_first == next_second
    assert next_first >= world.since_seq
    assert len({(r.tabla, r.uuid_registro) for r in first}) == len(first), "duplicates in a page"

    # advancing the cursor past the bridge row: the user is not delivered again
    again, next_again = await world.pull("a", since_seq=next_first)
    assert not world.has({(r.tabla, r.uuid_registro) for r in again}, "usuarios", "u")
    assert next_again >= next_first


async def test_next_seq_never_goes_below_since_seq_when_only_old_rows_qualify(
    world: World,
) -> None:
    await _old_user_with_membership(world, "u", 5)
    _, next_seq = await world.pull("a", since_seq=_ms(world.t0) + 10_000)
    assert next_seq == _ms(world.t0) + 10_000


async def test_limit_cut_delivers_each_newly_scoped_parent_with_its_bridge_row(
    world: World,
) -> None:
    """Three old users assigned 10 ms apart, page of 2: the first page carries the
    first two memberships AND their users; the next carries the third pair. Nothing
    is lost and the cursor makes progress (no livelock on re-delivered old rows)."""
    for index, who in enumerate(("u1", "u2", "u3")):
        await _old_user_with_membership(world, who, 10 * (index + 1))

    first, next_first = await world.pull("a", limit=2)
    first_set = {(r.tabla, r.uuid_registro) for r in first}
    assert world.has(first_set, "usuarios_sucursal", "u1")
    assert world.has(first_set, "usuarios_sucursal", "u2")
    assert world.has(first_set, "usuarios", "u1")
    assert world.has(first_set, "usuarios", "u2")
    assert not world.has(first_set, "usuarios_sucursal", "u3")
    assert not world.has(first_set, "usuarios", "u3")
    assert next_first > world.since_seq

    second, next_second = await world.pull("a", since_seq=next_first, limit=2)
    second_set = {(r.tabla, r.uuid_registro) for r in second}
    assert world.has(second_set, "usuarios_sucursal", "u3")
    assert world.has(second_set, "usuarios", "u3")
    assert not world.has(second_set, "usuarios", "u1")
    assert next_second >= next_first


async def test_parents_are_listed_before_the_bridge_rows_that_brought_them(world: World) -> None:
    await _old_user_with_membership(world, "u", 5)
    rows, _ = await world.pull("a")
    order = [(r.tabla, r.uuid_registro) for r in rows]
    user = ("usuarios", world.ids["usuarios:u"])
    membership = ("usuarios_sucursal", world.ids["usuarios_sucursal:u"])
    assert order.index(user) < order.index(membership)


async def test_since_seq_zero_has_no_duplicates_and_still_delivers_old_rows(world: World) -> None:
    await _old_user_with_membership(world, "u", 5)
    rows, _ = await world.pull("a", since_seq=0)
    keys = [(r.tabla, r.uuid_registro) for r in rows]
    assert len(keys) == len(set(keys))
    assert world.has(set(keys), "usuarios", "u")
    assert world.has(set(keys), "usuarios_sucursal", "u")
