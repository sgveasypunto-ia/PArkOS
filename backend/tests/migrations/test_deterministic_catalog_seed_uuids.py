"""Regression coverage for migration ``0095_deterministic_catalog_seed_uuids``.

Context: ``0001``/``0026``/``0031``/``0040``/``0041``/``0062`` seed catalog rows
(``impuestos``, ``tipo_arqueo``, ``tipos_vehiculo``, ``configuracion_*``) with
``gen_random_uuid()`` once per node, so cloud and every branch mint a different
identifier for the same logical row; only identity aliases cover that. ``0095``
makes a NEW node converge on ``uuid5(NAMESPACE, '<tabla>:<clave natural>')``
without touching a node that already depends on its random uuid.
"""

from __future__ import annotations

import importlib.util
import uuid as uuid_lib
from pathlib import Path

import pytest
from sqlalchemy import text

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "migrations"
    / "versions"
    / "0095_deterministic_catalog_seed_uuids.py"
)
_NAMESPACE = uuid_lib.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60")


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0095", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_hardcoded_uuids_are_uuid5_of_the_shared_namespace() -> None:
    migration = _load_migration()
    assert migration.SEEDS
    for seed in migration.SEEDS:
        assert seed.uuid == str(uuid_lib.uuid5(_NAMESPACE, f"{seed.table}:{seed.key}"))


def test_seed_keys_are_unique() -> None:
    migration = _load_migration()
    pairs = [(s.table, s.key) for s in migration.SEEDS]
    assert len(pairs) == len(set(pairs))
    assert len({s.uuid for s in migration.SEEDS}) == len(migration.SEEDS)


def test_converge_sql_is_offline_compatible_and_never_deletes() -> None:
    """``alembic upgrade --sql`` pre-flight: plain SQL strings, no bind needed."""
    migration = _load_migration()
    statements = migration.build_statements()
    assert statements
    for sql in statements:
        assert isinstance(sql, str)
        assert "DELETE" not in sql.upper().replace("DELETED", "")
        assert "gen_random_uuid" not in sql


async def _open(conn, table: str, where: str, params: dict | None = None):
    return (
        await conn.execute(
            text(f"SELECT uuid FROM prod.{table} WHERE {where} AND vigente_hasta IS NULL"),  # noqa: S608
            params or {},
        )
    ).all()


async def test_fresh_node_seeds_converge_on_deterministic_uuids(pg_engine, alembic_upgrade) -> None:
    """A freshly migrated node (rows unreferenced) holds ONLY uuid5 seeds."""
    migration = _load_migration()
    present = 0
    async with pg_engine.connect() as conn:
        for seed in migration.SEEDS:
            rows = await _open(conn, seed.table, seed.predicate)
            if not rows:
                continue
            present += 1
            assert [str(r.uuid) for r in rows] == [seed.uuid], (seed.table, seed.key)
    # The migration chain seeds at least IVA, tipo_arqueo x4, tolerancias and seguridad.
    assert present >= 7


def _synthetic_seed(migration, table: str, key: str, predicate: str, columns: tuple[str, ...]):
    return migration.Seed(
        table=table,
        key=key,
        predicate=predicate,
        columns=columns,
        uuid=str(uuid_lib.uuid5(_NAMESPACE, f"{table}:{key}")),
    )


async def test_unreferenced_random_seed_is_superseded_without_delete_and_idempotently(
    pg_engine, alembic_upgrade
) -> None:
    migration = _load_migration()
    codigo = f"zz_{uuid_lib.uuid4().hex[:8]}"
    seed = _synthetic_seed(
        migration, "tipo_arqueo", codigo, f"codigo = '{codigo}'", ("codigo", "nombre", "descripcion")
    )
    random_uuid = uuid_lib.uuid4()
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        # Live shape of an OLD node: random-uuid seed, nobody references it.
        await conn.execute(
            text(
                "INSERT INTO prod.tipo_arqueo (uuid, codigo, nombre, descripcion, vigente_desde, "
                "estado, created_at, sync_status, sync_attempts) VALUES "
                "(:u, :c, 'Nombre configurado', 'desc', clock_timestamp(), 'activo', now(), "
                "'sincronizado', 0)"
            ),
            {"u": random_uuid, "c": codigo},
        )
        await conn.run_sync(lambda sync_conn: migration.converge(sync_conn, (seed,)))

        rows = (
            await conn.execute(
                text("SELECT uuid, nombre FROM prod.tipo_arqueo WHERE codigo = :c "
                     "AND vigente_hasta IS NULL"),
                {"c": codigo},
            )
        ).all()
        assert [str(r.uuid) for r in rows] == [seed.uuid]
        assert rows[0].nombre == "Nombre configurado"  # configured values survive
        old = (
            await conn.execute(
                text("SELECT estado, vigente_hasta FROM prod.tipo_arqueo WHERE uuid = :u"),
                {"u": random_uuid},
            )
        ).one()
        assert old.estado == "inactivo" and old.vigente_hasta is not None  # closed, not deleted

        await conn.run_sync(lambda sync_conn: migration.converge(sync_conn, (seed,)))
        total = (
            await conn.execute(
                text("SELECT count(*) FROM prod.tipo_arqueo WHERE codigo = :c"), {"c": codigo}
            )
        ).scalar_one()
        assert total == 2  # second run is a no-op
        await trans.rollback()


async def test_seed_with_dependents_keeps_its_random_uuid_for_aliases(
    pg_engine, alembic_upgrade
) -> None:
    """A row already referenced by another table must NOT be superseded."""
    migration = _load_migration()
    tipo = f"zz_{uuid_lib.uuid4().hex[:8]}"
    seed = _synthetic_seed(migration, "tipos_vehiculo", tipo, f"tipo = '{tipo}'", ("tipo",))
    random_uuid = uuid_lib.uuid4()
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(
            text(
                "INSERT INTO prod.tipos_vehiculo (uuid, tipo, vigente_desde, estado, created_at, "
                "sync_status, sync_attempts) VALUES (:u, :t, clock_timestamp(), 'activo', now(), "
                "'sincronizado', 0)"
            ),
            {"u": random_uuid, "t": tipo},
        )
        await conn.execute(
            text(
                "INSERT INTO prod.tipo_subscripciones (uuid, tipo, valor, duracion_dias, "
                "cantidad_maxima_vehiculos, mismo_tipo_vehiculo, tipo_cliente_permitido, "
                "vigente_desde, estado, uuid_tipo_vehiculo) VALUES (:u, :t, 1, 1, 1, TRUE, "
                "'natural', clock_timestamp(), 'activo', :v)"
            ),
            {"u": uuid_lib.uuid4(), "t": f"plan_{tipo}", "v": random_uuid},
        )
        await conn.run_sync(lambda sync_conn: migration.converge(sync_conn, (seed,)))
        rows = (
            await conn.execute(
                text("SELECT uuid FROM prod.tipos_vehiculo WHERE tipo = :t "
                     "AND vigente_hasta IS NULL"),
                {"t": tipo},
            )
        ).all()
        assert [str(r.uuid) for r in rows] == [str(random_uuid)]
        await trans.rollback()


async def test_seed_with_several_versions_is_left_alone(pg_engine, alembic_upgrade) -> None:
    """Edited history (more than one version) is node-specific: aliases keep covering it."""
    migration = _load_migration()
    codigo = f"zz_{uuid_lib.uuid4().hex[:8]}"
    seed = _synthetic_seed(
        migration, "tipo_arqueo", codigo, f"codigo = '{codigo}'", ("codigo", "nombre", "descripcion")
    )
    first, second = uuid_lib.uuid4(), uuid_lib.uuid4()
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        for u, hasta, estado in ((first, "now()", "inactivo"), (second, "NULL", "activo")):
            await conn.execute(
                text(
                    "INSERT INTO prod.tipo_arqueo (uuid, codigo, nombre, vigente_desde, "
                    f"vigente_hasta, estado, created_at, sync_status, sync_attempts) VALUES "
                    f"(:u, :c, 'n', clock_timestamp(), {hasta}, :e, now(), 'sincronizado', 0)"  # noqa: S608
                ),
                {"u": u, "c": codigo, "e": estado},
            )
        await conn.run_sync(lambda sync_conn: migration.converge(sync_conn, (seed,)))
        rows = (
            await conn.execute(
                text("SELECT uuid FROM prod.tipo_arqueo WHERE codigo = :c AND vigente_hasta IS NULL"),
                {"c": codigo},
            )
        ).all()
        assert [str(r.uuid) for r in rows] == [str(second)]
        await trans.rollback()


@pytest.mark.parametrize("table", ["impuestos", "tipo_arqueo", "tipos_vehiculo"])
def test_every_seeded_table_is_declared(table: str) -> None:
    migration = _load_migration()
    assert table in {s.table for s in migration.SEEDS}
