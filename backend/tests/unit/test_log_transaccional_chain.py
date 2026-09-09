"""test_log_transaccional_chain.py — T-PR6-001/002 acceptance for
``hooks/impls/log_transaccional_chain.py::LogTransaccionalChain`` (REQ-HOOK-008).

Real Postgres throughout — the hook is invoked directly (constructing its own
``HookContext``, the same pattern ``test_bi_temporal_compensation.py`` uses),
asserting ``hash_actual == sha256(canonical(payload) + hash_anterior)`` (the
exact formula ``repo.hash_chain.append`` computes) and that the hook's own
call into that helper actually persisted a correctly-chained row.
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from datetime import UTC, datetime

from parkos_core.models.A.log_transaccional import LogTransaccional
from parkos_core.repo.hash_chain import _canonical_json, _genesis_hash
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.hooks.base import HookContext
from parkos_core.sync.hooks.impls.log_transaccional_chain import log_transaccional_chain
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000ab")


async def test_log_transaccional_chain_extends_first_row(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """First event for a fresh ``uuid_sucursal`` anchors at the genesis hash."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    spec = SYNC_CATALOG_BY_NAME["log_transaccional"]

    async with Session() as session:
        payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "accion": "crear",
            "tabla_afectada": "ingreso",
            "uuid_registro_afectado": uuid_lib.uuid4(),
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }
        ctx = HookContext(
            spec=spec,
            payload=payload,
            session=session,
            actor_uuid=ACTOR_UUID,
        )

        result = await log_transaccional_chain(ctx)
        await session.commit()

        assert result.proceed is True
        assert result.chain_extension is not None
        hash_anterior_bytes, hash_actual_bytes = result.chain_extension

        rows = (
            await session.execute(
                select(LogTransaccional).where(
                    LogTransaccional.uuid_sucursal == seeded_sucursal_uuid,
                    LogTransaccional.accion == "crear",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        row = rows[0]

        # repo.hash_chain.append was genuinely invoked (T-PR6-001's
        # "invokes hash_chain.append" acceptance criterion): the row is
        # persisted with a correctly-computed chain, not a no-op.
        assert row.hash_anterior == hash_anterior_bytes.decode("ascii")
        assert row.hash_actual == hash_actual_bytes.decode("ascii")
        assert row.hash_anterior == _genesis_hash(seeded_sucursal_uuid)

        # hash_actual == sha256(hash_anterior || canonical(payload)) —
        # exact formula from repo/hash_chain.py::append.
        payload_with_audit = {
            **payload,
            "created_at": row.created_at,
            "created_by": ACTOR_UUID,
        }
        expected = hashlib.sha256(
            _canonical_json(payload_with_audit) + bytes.fromhex(row.hash_anterior)
        ).hexdigest()
        assert row.hash_actual == expected


async def test_log_transaccional_chain_second_row_links_to_prior(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """A second event's ``hash_anterior`` matches the first event's ``hash_actual``."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    spec = SYNC_CATALOG_BY_NAME["log_transaccional"]

    async with Session() as session:
        first_payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "accion": "crear",
            "tabla_afectada": "ingreso",
            "uuid_registro_afectado": uuid_lib.uuid4(),
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }
        await log_transaccional_chain(
            HookContext(
                spec=spec, payload=first_payload, session=session, actor_uuid=ACTOR_UUID
            )
        )
        await session.commit()

        first_row = (
            await session.execute(
                select(LogTransaccional).where(
                    LogTransaccional.uuid_sucursal == seeded_sucursal_uuid,
                    LogTransaccional.accion == "crear",
                )
            )
        ).scalar_one()
        first_hash_actual = first_row.hash_actual

        second_payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "accion": "actualizar",
            "tabla_afectada": "ingreso",
            "uuid_registro_afectado": uuid_lib.uuid4(),
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }
        await log_transaccional_chain(
            HookContext(
                spec=spec, payload=second_payload, session=session, actor_uuid=ACTOR_UUID
            )
        )
        await session.commit()

        second_row = (
            await session.execute(
                select(LogTransaccional).where(
                    LogTransaccional.uuid_sucursal == seeded_sucursal_uuid,
                    LogTransaccional.accion == "actualizar",
                )
            )
        ).scalar_one()

        assert second_row.hash_anterior == first_hash_actual
        assert second_row.hash_actual != first_hash_actual
