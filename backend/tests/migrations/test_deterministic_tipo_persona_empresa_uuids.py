"""test_deterministic_tipo_persona_empresa_uuids.py — regression coverage
for migration ``0020_deterministic_tipo_persona_empresa_uuids``.

Confirmed real (2026-09-10, full-suite run against a freshly-rebuilt
Docker cloud+branch stack): ``tipo_persona`` and ``empresa`` are both
seeded independently on every node via ``gen_random_uuid()``
(``0001_initial_schema.py``) — the exact same defect migration 0019 fixed
for ``permisos``. Backfilling a ``clientes`` (``uuid_tipo_persona``) or
``sucursal`` (``uuid_empresa``) row across two independently-migrated
databases raised a real ``ForeignKeyViolationError`` every time, because
each node's copy of the referenced row has a different random uuid.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "parkos_core"
    / "migrations"
    / "versions"
    / "0020_deterministic_tipo_persona_empresa_uuids.py"
)


async def test_tipo_persona_and_empresa_uuids_are_deterministic_after_migration(
    pg_engine, alembic_upgrade
) -> None:
    from parkos_core.models.V.empresa import Empresa
    from parkos_core.models.V.tipo_persona import TipoPersona
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    spec = importlib.util.spec_from_file_location("migration_0020", _MIGRATION_PATH)
    migration_0020 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_0020)  # type: ignore[union-attr]

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        for tipo, expected_uuid in migration_0020._TIPO_PERSONA_DETERMINISTIC_UUIDS.items():
            row = (
                await session.execute(
                    select(TipoPersona).where(
                        TipoPersona.tipo == tipo, TipoPersona.vigente_hasta.is_(None)
                    )
                )
            ).scalar_one()
            assert str(row.uuid) == expected_uuid, (
                f"tipo_persona '{tipo}': expected deterministic uuid {expected_uuid}, "
                f"got {row.uuid} — every node must converge on the same uuid"
            )

        for nit, expected_uuid in migration_0020._EMPRESA_DETERMINISTIC_UUIDS.items():
            row = (
                await session.execute(
                    select(Empresa).where(Empresa.nit == nit, Empresa.vigente_hasta.is_(None))
                )
            ).scalar_one()
            assert str(row.uuid) == expected_uuid, (
                f"empresa nit '{nit}': expected deterministic uuid {expected_uuid}, "
                f"got {row.uuid} — every node must converge on the same uuid"
            )
