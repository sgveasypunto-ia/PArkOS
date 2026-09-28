"""test_tenant_listener_isolation.py â€” the tenant auto-filter actually filters.

``db/tenancy.py::install_tenant_event_listener`` has advertised, in its own
docstring and in ``auth/tenancy.py``, that every SELECT/UPDATE/DELETE on a
table carrying ``uuid_sucursal`` is auto-scoped to the request's branch. Since
the listener was registered, that guarantee was false: the handler read
``state.column_descriptions`` off the SQLAlchemy ``ORMExecuteState``, which has
no such attribute, so ``getattr(..., [])`` returned an empty list, the loop body
never ran, and no predicate was ever injected.

The listener was installed, ran on every ORM statement, and did nothing. No
test caught it because the codebase tests the *composition helpers*
(``apply_admin_scope``) rather than the listener that guards every resource
mounted by ``router_factory``.

Measured against the cloud API before the fix: an ``operador-`` token scoped to
E2E-NORTE, requesting ``GET /empresa/tarifas-sucursal`` with its own
``X-Sucursal-Context``, received 11 rows â€” its own 6 plus 5 belonging to
BOG-CEN. 19 factory-mounted resources were exposed this way, including
``facturas``, ``factura-pagos``, ``caja``, ``arqueo``, ``sesion`` and
``documentos``. The ``X-Sucursal-Context`` guard was never the problem: it
correctly 403s a cross-branch *header*, it just never reached the query.

These tests pin the listener's behaviour at the SQL level, because the failure
mode is silent â€” a regression reintroduces the leak without any error.
"""

from __future__ import annotations

import uuid as uuid_lib
from collections.abc import AsyncIterator

import pytest
from parkos_core.api import deps as api_deps  # noqa: F401  (installs the listener)
from parkos_core.db.tenancy import (
    _HASH_CHAIN_TABLES,
    set_tenant_context,
)
from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.models.V.cantidad_vehiculos_sucursal import CantidadVehiculosSucursal
from parkos_core.models.V.sucursal import Sucursal
from parkos_core.models.V.tarifas_sucursal import TarifasSucursal
from parkos_core.models.V.tipos_vehiculo import TiposVehiculo
from sqlalchemy import event, func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

BRANCHES = 2
ROWS_PER_BRANCH = 3


@pytest.fixture(autouse=True)
def _no_leaked_tenant_scope() -> AsyncIterator[None]:
    """Guarantee a clean ``ContextVar`` before and after every test.

    ``set_tenant_context`` writes a ``ContextVar`` that an HTTP request in the
    same task can leave behind. A test that inherits a scope would assert
    against a filter it did not ask for.
    """
    set_tenant_context(None)
    yield
    set_tenant_context(None)


async def _seed_two_branches(engine: AsyncEngine) -> list[uuid_lib.UUID]:
    """Create ``BRANCHES`` branches with ``ROWS_PER_BRANCH`` open tarifas each."""
    Session = async_sessionmaker(engine, expire_on_commit=False)
    branch_uuids: list[uuid_lib.UUID] = []
    async with Session() as session:
        for _ in range(BRANCHES):
            sucursal = VFixtureFactory.build(Sucursal)
            session.add(sucursal)
            await session.flush()
            branch_uuids.append(sucursal.uuid)

            for _ in range(ROWS_PER_BRANCH):
                session.add(
                    VFixtureFactory.build(
                        TarifasSucursal,
                        uuid_sucursal=sucursal.uuid,
                    )
                )
                session.add(
                    VFixtureFactory.build(
                        CantidadVehiculosSucursal,
                        uuid_sucursal=sucursal.uuid,
                    )
                )
        await session.commit()
    return branch_uuids


def _only(rows: list, branch: uuid_lib.UUID) -> bool:
    return all(r.uuid_sucursal == branch for r in rows)


async def test_entity_select_is_scoped_to_the_request_branch(
    pg_engine: AsyncEngine,
) -> None:
    """The core guarantee: a branch sees its own rows and nobody else's."""
    branches = await _seed_two_branches(pg_engine)
    target, other = branches[0], branches[1]
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        set_tenant_context(target)
        rows = (await session.execute(select(TarifasSucursal))).scalars().all()
        scoped = [r for r in rows if r.uuid_sucursal in branches]

        assert _only(scoped, target), "scoped read returned another branch's rows"
        assert len(scoped) >= ROWS_PER_BRANCH
        assert not any(r.uuid_sucursal == other for r in scoped)


async def test_the_two_branch_scopes_partition_the_whole_seeded_set(
    pg_engine: AsyncEngine,
) -> None:
    """Filtering must lose nothing: scope A + scope B covers every seeded row.

    A filter that simply returned fewer rows would pass the test above while
    silently dropping data the branch is entitled to. This pins both halves.
    """
    branches = await _seed_two_branches(pg_engine)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    seen: set[uuid_lib.UUID] = set()
    async with Session() as session:
        for branch in branches:
            set_tenant_context(branch)
            rows = (await session.execute(select(TarifasSucursal))).scalars().all()
            seen.update(r.uuid_sucursal for r in rows)

    assert seen == set(branches), "the per-branch scopes do not cover every branch"


async def test_aggregate_select_is_scoped(pg_engine: AsyncEngine) -> None:
    """``select(func.count()).select_from(Model)`` is scoped too.

    An aggregate carries no mapped entity in ``column_descriptions`` â€” its only
    column is the ``count()`` expression â€” so a listener that resolves entities
    from that attribute alone leaves every count() unfiltered and leaks a row
    count per branch.

    Counts are restricted to the branches this test seeded: the database is
    shared across the suite, so a bare total would depend on test ordering.
    """
    branches = await _seed_two_branches(pg_engine)
    target, other = branches[0], branches[1]
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    def _count() -> object:
        return (
            select(func.count())
            .select_from(TarifasSucursal)
            .where(TarifasSucursal.uuid_sucursal.in_(branches))
        )

    async with Session() as session:
        set_tenant_context(target)
        scoped = (await session.execute(_count())).scalar_one()
        set_tenant_context(other)
        other_scoped = (await session.execute(_count())).scalar_one()
        set_tenant_context(None)
        unfiltered = (await session.execute(_count())).scalar_one()

    assert scoped == other_scoped == ROWS_PER_BRANCH
    assert unfiltered == BRANCHES * ROWS_PER_BRANCH


async def test_join_of_two_tenant_scoped_tables_is_scoped(
    pg_engine: AsyncEngine,
) -> None:
    """A join may reference more than one tenant-scoped table; both are scoped."""
    branches = await _seed_two_branches(pg_engine)
    target, other = branches[0], branches[1]
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    stmt = (
        select(TarifasSucursal, CantidadVehiculosSucursal)
        .join(
            CantidadVehiculosSucursal,
            CantidadVehiculosSucursal.uuid_sucursal == TarifasSucursal.uuid_sucursal,
        )
        .where(TarifasSucursal.uuid_sucursal.in_(branches))
    )
    async with Session() as session:
        set_tenant_context(target)
        pairs = (await session.execute(stmt)).all()

    assert pairs, "seeded join produced no rows"
    assert all(a.uuid_sucursal == target and b.uuid_sucursal == target for a, b in pairs)
    assert not any(a.uuid_sucursal == other for a, _ in pairs)


async def test_update_touches_only_the_request_branch(pg_engine: AsyncEngine) -> None:
    """A write is scoped too, so a branch-scoped write cannot touch a sibling."""
    branches = await _seed_two_branches(pg_engine)
    target, other = branches[0], branches[1]
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        set_tenant_context(target)
        result = await session.execute(
            update(TarifasSucursal)
            .where(TarifasSucursal.uuid_sucursal.in_(branches))
            .values(estado="activo")
        )
        touched = result.rowcount
        await session.commit()

    assert touched == ROWS_PER_BRANCH, "update reached outside the request branch"

    async with Session() as session:
        set_tenant_context(other)
        rows = (await session.execute(select(TarifasSucursal))).scalars().all()
    assert _only(rows, other)


async def test_catalog_table_without_uuid_sucursal_is_left_alone(
    pg_engine: AsyncEngine,
) -> None:
    """A tenant scope must not narrow the catalogs every branch reads.

    ``tipo_vehiculo`` and friends carry no ``uuid_sucursal``; filtering them
    would empty every pricing selector in the UI.
    """
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        session.add(VFixtureFactory.build(TiposVehiculo))
        await session.commit()

        set_tenant_context(uuid_lib.uuid4())
        rows = (await session.execute(select(TiposVehiculo))).scalars().all()

    assert rows, "a catalog table was emptied by a tenant scope"


async def test_hash_chain_tables_are_exempt_from_scoping(
    pg_engine: AsyncEngine,
) -> None:
    """Compliance hash chains must stay whole, so they are never auto-scoped.

    ``log_transaccional`` and ``revocacion_factura`` use a NULL
    ``uuid_sucursal`` to mark the GLOBAL chain. A ``uuid_sucursal = :ctx``
    predicate hides those NULL rows from the chain-head probe, and
    ``prod.fn_extend_hash_chain`` then rejects the next insert as a second
    genesis over a live chain (HASH_CHAIN_INTEGRITY_VIOLATION). Asserted on the
    emitted SQL so the guarantee holds even while the table is empty.
    """
    assert {"log_transaccional", "revocacion_factura"} == _HASH_CHAIN_TABLES

    emitted: list[tuple[str, object]] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        emitted.append((statement, parameters))

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        event.listen(pg_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            set_tenant_context(uuid_lib.uuid4())
            await session.execute(select(LogTransaccional))
        finally:
            event.remove(pg_engine.sync_engine, "before_cursor_execute", _capture)

    selects = [
        (sql, params)
        for sql, params in emitted
        if "log_transaccional" in sql and sql.lstrip().upper().startswith("SELECT")
    ]
    assert selects, "the probe never reached the database"

    # ``uuid_sucursal`` legitimately appears in the projection list, so the
    # assertion targets the predicate: an injected scope binds the branch uuid
    # as a parameter, while the chain's own genesis probe filters on
    # ``uuid_sucursal IS NULL`` and binds nothing.
    for sql, params in selects:
        assert "uuid_sucursal =" not in sql, (
            "a tenant equality predicate was injected into a hash-chain read: "
            "the global genesis row would become invisible to the chain probe"
        )
        assert not params, f"an injected predicate bound parameters: {params!r}"


async def test_query_without_a_tenant_context_is_untouched(
    pg_engine: AsyncEngine,
) -> None:
    """Jobs, sync workers and the DIAN dispatcher run with no branch scope.

    ``set_tenant_context`` is called only from ``auth/tenancy.py`` on the HTTP
    path, so an unbound ``ContextVar`` must mean "no filter" â€” otherwise a
    background job would be silently narrowed to whatever branch last served a
    request in its task.
    """
    branches = await _seed_two_branches(pg_engine)
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        set_tenant_context(None)
        rows = (await session.execute(select(TarifasSucursal))).scalars().all()

    seeded = {r.uuid_sucursal for r in rows} & set(branches)
    assert seeded == set(branches), "an unbound scope hid rows from a non-HTTP caller"
