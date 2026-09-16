"""test_deterministic_permisos_uuids.py — regression coverage for migration
``0019_deterministic_permisos_uuids``.

Confirmed real (Docker, 2026-09-10): ``permisos`` is genuinely meant to
replicate cloud→branch (``modelo_datos_er.mmd``, confirmed by
``test_check_catalog_drift.py``), but each node independently seeds the
same 16 canonical codes with ``gen_random_uuid()`` — once real pull started
working, the SAME code ended up with two different uuids across nodes,
and any ``permisos_usuario`` grant referencing one node's uuid could never
push to the other (FK violation). After this migration, every node
converges on the SAME uuid per canonical code.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Computed at module level (never inside the async test below — ASYNC240,
# matching tests/unit/test_dependency_graph.py's own established
# precedent for this exact "import a migration module by file path" need,
# since alembic revision modules are not normal importable packages).
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "migrations"
    / "versions"
    / "0019_deterministic_permisos_uuids.py"
)


async def test_permisos_uuids_are_deterministic_after_migration(pg_engine, alembic_upgrade) -> None:
    from parkos_core.models.V.permisos import Permisos
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    spec = importlib.util.spec_from_file_location("migration_0019", _MIGRATION_PATH)
    migration_0019 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_0019)  # type: ignore[union-attr]

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for codigo, expected_uuid in migration_0019._DETERMINISTIC_UUIDS.items():
            row = (
                await session.execute(
                    select(Permisos).where(
                        Permisos.permiso == codigo, Permisos.vigente_hasta.is_(None)
                    )
                )
            ).scalar_one()
            assert str(row.uuid) == expected_uuid, (
                f"{codigo}: expected deterministic uuid {expected_uuid}, got {row.uuid} "
                "— every node must converge on the same uuid per canonical code"
            )
