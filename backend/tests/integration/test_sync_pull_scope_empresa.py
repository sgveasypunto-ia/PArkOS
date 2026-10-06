"""test_sync_pull_scope_empresa.py — pull scope of ``empresa``.

``empresa`` is no longer broadcast to every branch. The rule (``derived``):

  * the pulling branch's ``sucursal.uuid_empresa`` names its empresa; the open
    empresa version(s) carrying the NIT of the referenced row are delivered
    (a [V] bump mints a new uuid, so the reference may point at a closed version);
  * a branch with NULL ``uuid_empresa`` (a real case) falls back to the open empresa row(s):
    never zero rows, or the branch would lose NIT / ticket messages.

``sucursal.uuid_empresa`` carries a DB FK (``fk_sucursal_uuid_empresa``), so a
dangling reference cannot exist.

``empresa_singleton_uk`` allows ONE open row, so a multi-empresa world needs the
index out of the way for the duration of a test; the fixture drops it, restores
the rows it closed and recreates the index on teardown.

T4.4: ``configuracion_tolerancias`` / ``configuracion_seguridad`` override
semantics ("A gets the global default plus its own override, never B's") are
already pinned by ``test_override_gives_global_default_and_own_override_only``
in ``test_sync_pull_scope_matrix.py``; nothing to add here.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.parametrize("app", ["admin"], indirect=True)

PULL_URL = "/api/v1/sync/pull"
_SINGLETON_INDEX = "prod.empresa_singleton_uk"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _pull_empresas(client, token: str, since_seq: int) -> set[str]:
    resp = await client.post(
        PULL_URL,
        json={"since_seq": since_seq},
        headers={"Authorization": f"Bearer {token}", "X-Request-Id": uuid_lib.uuid4().hex},
    )
    assert resp.status_code == 200, resp.text
    return {r["uuid_registro"] for r in resp.json()["rows"] if r["tabla"] == "empresa"}


@pytest.fixture
async def world(client, pg_engine, alembic_upgrade, mint_sync_agent_jwt, v_fixture_factory):
    """Factory ``await world(empresas=..., branches=...)`` -> (ids, pull).

    ``empresas``: ``{label: {"nit": ..., "closed": bool}}``.
    ``branches``: ``{label: <empresa label | None>}``.
    ``pull(branch_label)`` returns the set of empresa uuids (as str) delivered.
    """
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.sucursal import Sucursal
    from sqlalchemy import text, update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    previously_open: list[uuid_lib.UUID] = []
    mine: list[uuid_lib.UUID] = []
    branches_created: list[uuid_lib.UUID] = []
    state: dict[str, object] = {"since_seq": 0, "tokens": {}}

    async def build(*, empresas: dict, branches: dict):
        tag = uuid_lib.uuid4().hex[:8]
        now = _now()
        ids: dict[str, uuid_lib.UUID] = {}
        async with Session() as s:
            open_rows = (
                (await s.execute(text("SELECT uuid FROM prod.empresa WHERE vigente_hasta IS NULL")))
                .scalars()
                .all()
            )
            previously_open.extend(open_rows)
            await s.execute(
                update(Empresa)
                .where(Empresa.vigente_hasta.is_(None))
                .values(vigente_hasta=now, estado="inactivo")
            )
            await s.execute(text(f"DROP INDEX IF EXISTS {_SINGLETON_INDEX}"))
            rows = []
            for label, spec in empresas.items():
                kw: dict = {"nit": f"{spec['nit']}-{tag}", "nombre": f"E-{label}-{tag}"}
                if spec.get("closed"):
                    kw.update(
                        vigente_desde=now - timedelta(days=1), vigente_hasta=now, estado="inactivo"
                    )
                row = v_fixture_factory.build(Empresa, **kw)
                ids[label] = row.uuid
                mine.append(row.uuid)
                rows.append(row)
            s.add_all(rows)
            await s.commit()

            sucursales = []
            for label, ref in branches.items():
                uuid_empresa = None if ref is None else ids[ref]
                row = v_fixture_factory.build(
                    Sucursal, nombre=f"S-{label}-{tag}", uuid_empresa=uuid_empresa
                )
                ids[f"branch:{label}"] = row.uuid
                branches_created.append(row.uuid)
                sucursales.append(row)
            s.add_all(sucursales)
            await s.commit()

        state["since_seq"] = int(datetime.now(UTC).timestamp() * 1000) - 5000
        return ids

    async def pull(branch_uuid: uuid_lib.UUID) -> set[str]:
        token = mint_sync_agent_jwt(scope="branch", sucursal_uuid=branch_uuid)
        return await _pull_empresas(client, token, int(state["since_seq"]))

    yield build, pull

    now = _now()
    async with Session() as s:
        await s.execute(
            update(Empresa)
            .where(Empresa.uuid.in_(mine), Empresa.vigente_hasta.is_(None))
            .values(vigente_hasta=now, estado="inactivo")
        )
        await s.execute(
            update(Sucursal)
            .where(Sucursal.uuid.in_(branches_created), Sucursal.vigente_hasta.is_(None))
            .values(vigente_hasta=now, estado="inactivo")
        )
        # Reopen only the single most recent row that was open before this test.
        if previously_open:
            await s.execute(
                update(Empresa)
                .where(Empresa.uuid == previously_open[-1])
                .values(vigente_hasta=None, estado="activo")
            )
        await s.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {_SINGLETON_INDEX.split('.')[1]} "
                "ON prod.empresa ((true)) WHERE vigente_hasta IS NULL"
            )
        )
        await s.commit()


async def test_branch_gets_exactly_its_empresa(world, app) -> None:
    build, pull = world
    ids = await build(
        empresas={"e1": {"nit": "900100"}, "e2": {"nit": "900200"}},
        branches={"a": "e1", "b": "e2"},
    )
    got_a = await pull(ids["branch:a"])
    got_b = await pull(ids["branch:b"])
    assert str(ids["e1"]) in got_a
    assert str(ids["e2"]) not in got_a, "A received the empresa of another operator"
    assert str(ids["e2"]) in got_b
    assert str(ids["e1"]) not in got_b, "B received the empresa of another operator"


async def test_branch_with_null_empresa_still_gets_the_single_active_empresa(world, app) -> None:
    build, pull = world
    ids = await build(empresas={"e1": {"nit": "900100"}}, branches={"orphan": None})
    assert str(ids["e1"]) in await pull(ids["branch:orphan"])


async def test_empresa_version_bump_still_reaches_the_branch(world, app) -> None:
    """The branch points at the CLOSED version; the new open version (new uuid,
    same NIT) is what must be delivered, and an unrelated empresa must not."""
    build, pull = world
    ids = await build(
        empresas={
            "old": {"nit": "900100", "closed": True},
            "new": {"nit": "900100"},
            "other": {"nit": "900200"},
        },
        branches={"a": "old"},
    )
    # same NIT across the bump: the helper suffixes nit with the tag, identical for all rows
    got = await pull(ids["branch:a"])
    assert str(ids["new"]) in got
    assert str(ids["other"]) not in got


async def test_nit_corrected_bump_falls_back_to_the_open_empresa(world, app) -> None:
    """Regression: the branch points at a CLOSED version whose NIT differs from the
    open one (a NIT correction). The NIT match is empty, but a branch must never end
    up with zero empresa rows: it gets the open row, like the NULL-reference case."""
    build, pull = world
    ids = await build(
        empresas={
            "old": {"nit": "900100", "closed": True},
            "new": {"nit": "900109"},
        },
        branches={"a": "old"},
    )
    got = await pull(ids["branch:a"])
    assert str(ids["new"]) in got
    assert str(ids["old"]) not in got, "closed versions are never delivered"
