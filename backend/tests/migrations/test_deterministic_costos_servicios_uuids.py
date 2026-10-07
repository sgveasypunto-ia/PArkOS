"""Regression coverage for migration ``0093_deterministic_costos_servicios_uuids``.

Live defect (2026-10-07): ``0029`` seeds ``costos_servicios.concepto='reimpresion'``
independently on every node with ``gen_random_uuid()`` and ``NOW()``. The cloud
held ``ad489879`` and the branch ``c09e5d24``; ``costos_servicios`` replicates
cloud -> branch only, so a ``reimpresion_ticket`` created on the branch named a
cost row the cloud never had and its push failed forever with an FK violation.
After the migration every node converges on the SAME uuid for the seeded row.
"""

from __future__ import annotations

import importlib.util
import uuid as uuid_lib
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "migrations"
    / "versions"
    / "0093_deterministic_costos_servicios_uuids.py"
)
_NAMESPACE = uuid_lib.UUID("a3f1c9d4-6b2e-4e8a-9c1a-7d5f2b8e4c60")


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0093", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_hardcoded_uuids_are_uuid5_of_the_shared_namespace() -> None:
    migration = _load_migration()
    assert migration._DETERMINISTIC_UUIDS  # noqa: SLF001
    for concepto, value in migration._DETERMINISTIC_UUIDS.items():  # noqa: SLF001
        assert value == str(uuid_lib.uuid5(_NAMESPACE, f"costos_servicios:{concepto}"))


async def _open_rows(conn, concepto: str) -> list:
    return (
        await conn.execute(
            text(
                "SELECT uuid, costo, tipo_calculo FROM prod.costos_servicios "
                "WHERE concepto = :c AND vigente_hasta IS NULL"
            ),
            {"c": concepto},
        )
    ).all()


async def test_fresh_node_converges_on_the_deterministic_uuid(pg_engine, alembic_upgrade) -> None:
    migration = _load_migration()
    async with pg_engine.connect() as conn:
        rows = await _open_rows(conn, "reimpresion")
    assert [str(r.uuid) for r in rows] == [migration._DETERMINISTIC_UUIDS["reimpresion"]]  # noqa: SLF001


async def test_divergent_random_seed_is_closed_and_replaced_without_delete(
    pg_engine, alembic_upgrade
) -> None:
    migration = _load_migration()
    concepto = f"zz_prueba_{uuid_lib.uuid4().hex[:8]}"
    det = str(uuid_lib.uuid5(_NAMESPACE, f"costos_servicios:{concepto}"))
    migration._DETERMINISTIC_UUIDS = {concepto: det}  # noqa: SLF001
    random_uuid = uuid_lib.uuid4()
    async with pg_engine.begin() as conn:
        # Live shape: this node minted a random-uuid seed with a configured price.
        await conn.execute(
            text(
                "INSERT INTO prod.costos_servicios (uuid, concepto, costo, tipo_calculo, "
                "vigente_desde, vigente_hasta, estado, created_at, sync_status, sync_attempts) "
                "VALUES (:u, :c, 1500, 'fijo', clock_timestamp(), NULL, 'activo', "
                "now(), 'sincronizado', 0)"
            ),
            {"u": random_uuid, "c": concepto},
        )
        await conn.run_sync(lambda sync_conn: migration.converge_costos_servicios(sync_conn))

        rows = await _open_rows(conn, concepto)
        assert [str(r.uuid) for r in rows] == [det]
        assert float(rows[0].costo) == 1500.0  # the configured price survives
        stale = (
            await conn.execute(
                text("SELECT estado, vigente_hasta FROM prod.costos_servicios WHERE uuid = :u"),
                {"u": random_uuid},
            )
        ).one()
        assert stale.estado == "inactivo" and stale.vigente_hasta is not None
        total = (
            await conn.execute(
                text("SELECT count(*) FROM prod.costos_servicios WHERE concepto = :c"),
                {"c": concepto},
            )
        ).scalar_one()
        assert total == 2  # superseded row kept, nothing deleted

        # Idempotent: a second run is a no-op.
        await conn.run_sync(lambda sync_conn: migration.converge_costos_servicios(sync_conn))
        assert [str(r.uuid) for r in await _open_rows(conn, concepto)] == [det]


async def test_reimpresion_referencing_the_seed_uuid_is_accepted_but_a_node_local_uuid_is_not(
    pg_engine, alembic_upgrade
) -> None:
    """The failure class: FK of a transactional row onto a seeded catalog row."""
    migration = _load_migration()
    det = migration._DETERMINISTIC_UUIDS["reimpresion"]  # noqa: SLF001
    insert = text(
        "INSERT INTO prod.reimpresion_ticket (uuid, uuid_costo_servicio, costo_aplicado, "
        "created_at) VALUES (:u, :c, 0, now())"
    )
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(insert, {"u": uuid_lib.uuid4(), "c": det})
        await trans.rollback()
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        with pytest.raises(IntegrityError):
            await conn.execute(insert, {"u": uuid_lib.uuid4(), "c": uuid_lib.uuid4()})
        await trans.rollback()
