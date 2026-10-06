"""CI guard: ``IDENTITY_FK_COLUMNS`` (the columns the identity-alias remap rewrites)
agrees with the real ``pg_constraint`` of a migrated database.

The ORM models declare no ``ForeignKey`` on these columns, so the constraints in the
migrations are the only ground truth; a new FK onto an identity-reconciled master
(or a dropped one) must update the map or this test fails.
"""

from __future__ import annotations

from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.motor.identity_fk_map import IDENTITY_FK_COLUMNS
from parkos_core.sync.motor.sync_motor import identity_fk_columns
from sqlalchemy import text

_NEVER = {"uuid", "created_by", "current_uuid"}


def _reconciled_masters() -> list[str]:
    return sorted(
        name
        for name, entry in SYNC_CATALOG_BY_NAME.items()
        if entry.hook_pre_insert is not None
        and entry.hook_pre_insert.__name__ == "identity_reconciler"
    )


async def _db_fk_pairs(pg_engine, parents: list[str]) -> set[tuple[str, str, str]]:
    async with pg_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text "
                    "FROM pg_constraint c JOIN pg_attribute a "
                    "ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
                    "WHERE c.contype = 'f' AND c.confrelid::regclass::text = ANY (:p)"
                ),
                {"p": [f"prod.{m}" for m in parents]},
            )
        ).all()
    return {(c.removeprefix("prod."), col, p.removeprefix("prod.")) for c, col, p in rows}


async def test_map_agrees_with_pg_constraint_for_all_reconciled_masters(
    pg_engine, alembic_upgrade
) -> None:
    masters = [m for m in _reconciled_masters() if m != "sucursal"]
    pairs = await _db_fk_pairs(pg_engine, masters)
    expected: dict[str, set[str]] = {}
    for child, col, _parent in pairs:
        if child in SYNC_CATALOG_BY_NAME and child != "sucursal" and col not in _NEVER:
            expected.setdefault(child, set()).add(col)
    assert {k: set(v) for k, v in IDENTITY_FK_COLUMNS.items()} == expected


async def test_three_masters_clientes_vehiculos_usuarios_agree(pg_engine, alembic_upgrade) -> None:
    for master in ("clientes", "vehiculos", "usuarios"):
        pairs = await _db_fk_pairs(pg_engine, [master])
        db = {
            (child, col)
            for child, col, _p in pairs
            if child in SYNC_CATALOG_BY_NAME and child != "sucursal" and col not in _NEVER
        }
        assert db, master
        derived = {
            (name, col)
            for name, spec in SYNC_CATALOG_BY_NAME.items()
            for col in identity_fk_columns(spec)
        }
        assert db <= derived, master
