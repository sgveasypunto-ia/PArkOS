"""test_pairing_and_revoked_jwts_default_partition.py — regression coverage
for migration ``0018_add_default_partitions_pairing_revoked_jwts``.

Confirmed real (Docker + testcontainers, 2026-09-10): ``prod.pairing_tokens``
and ``prod.revoked_sync_jwts`` had NO partition attached at all —
``0006_add_pairing_tokens_and_normalized_revoked_sync_jwts`` declares the
composite ``(uuid, fecha_retencion_hasta)`` PK pg_partman range-partitioning
requires, but (unlike ``0001_initial_schema.py``'s 8 tables) never attaches
a child partition, so every real INSERT via the actual service layer
(``repo.pairing.create_pairing_token``, ``repo.revoked_sync_jwt.revoke_jwt``)
failed with ``CheckViolationError: no partition of relation ... found for
row``. Must pass cleanly after ``0018``'s ``DEFAULT`` partition.
"""

from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker


async def test_create_pairing_token_succeeds_after_default_partition(
    pg_engine, alembic_upgrade
) -> None:
    from parkos_core.repo.pairing import create_pairing_token

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await create_pairing_token(session, uuid_sucursal=None, ttl_hours=24)
        await session.commit()
        assert row.uuid is not None
        assert row.used is False


async def test_revoke_jwt_succeeds_after_default_partition(pg_engine, alembic_upgrade) -> None:
    from parkos_core.repo.revoked_sync_jwt import revoke_jwt

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await revoke_jwt(
            session,
            kid="admin-current",
            jwt_uuid=str(uuid_lib.uuid4()),
            motivo="test_default_partition",
            actor_uuid=None,
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        )
        await session.commit()
        assert row is not None
