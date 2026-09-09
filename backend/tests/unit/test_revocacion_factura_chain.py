"""test_revocacion_factura_chain.py — T-PR6-003/004 acceptance for
``hooks/impls/revocacion_factura_chain.py::RevocacionFacturaChain`` (REQ-HOOK-009).

Same pattern as ``test_log_transaccional_chain.py`` — real Postgres, hook
invoked directly via a hand-built ``HookContext``, asserting the exact
``hash_actual == sha256(canonical(payload) + hash_anterior)`` formula and
that the row was actually persisted through ``repo.hash_chain.append``.
Also asserts this hook is the catalog-registered replacement for the manual
``dispatcher.py`` call it supersedes (T-PR6-005).
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from datetime import UTC, datetime

from parkos_core.models.A.revocacion_factura import RevocacionFactura
from parkos_core.repo.hash_chain import _canonical_json, _genesis_hash
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.hooks.base import HookContext
from parkos_core.sync.hooks.impls.revocacion_factura_chain import (
    revocacion_factura_chain,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000ac")


async def test_revocacion_factura_chain_extends_first_row(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """First revocation event for a fresh ``uuid_sucursal`` anchors at genesis."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    spec = SYNC_CATALOG_BY_NAME["revocacion_factura"]

    async with Session() as session:
        payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "uuid_factura_electronica": None,
            "motivo": "dian_confirmada",
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }
        ctx = HookContext(
            spec=spec, payload=payload, session=session, actor_uuid=ACTOR_UUID
        )

        result = await revocacion_factura_chain(ctx)
        await session.commit()

        assert result.proceed is True
        assert result.chain_extension is not None
        hash_anterior_bytes, hash_actual_bytes = result.chain_extension

        # Filter on motivo="dian_confirmada" — PR6's genesis-row
        # auto-bootstrap (repo/hash_chain.py) ALSO lands a real row for this
        # brand-new uuid_sucursal (motivo=None, far-past sentinel
        # timestamp; ``revocacion_factura`` has no ``accion`` discriminator
        # column to filter on instead), which would otherwise double-count
        # here.
        rows = (
            await session.execute(
                select(RevocacionFactura).where(
                    RevocacionFactura.uuid_sucursal == seeded_sucursal_uuid,
                    RevocacionFactura.motivo == "dian_confirmada",
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        row = rows[0]

        assert row.hash_anterior == hash_anterior_bytes.decode("ascii")
        assert row.hash_actual == hash_actual_bytes.decode("ascii")
        assert row.hash_anterior == _genesis_hash(seeded_sucursal_uuid)

        payload_with_audit = {
            **payload,
            "created_at": row.created_at,
            "created_by": ACTOR_UUID,
        }
        expected = hashlib.sha256(
            _canonical_json(payload_with_audit) + bytes.fromhex(row.hash_anterior)
        ).hexdigest()
        assert row.hash_actual == expected


async def test_revocacion_factura_chain_second_row_links_to_prior(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """A second revocation's ``hash_anterior`` matches the first's ``hash_actual``."""
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    spec = SYNC_CATALOG_BY_NAME["revocacion_factura"]

    async with Session() as session:
        first_payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "uuid_factura_electronica": None,
            "motivo": "primera",
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }
        await revocacion_factura_chain(
            HookContext(
                spec=spec, payload=first_payload, session=session, actor_uuid=ACTOR_UUID
            )
        )
        await session.commit()

        first_row = (
            await session.execute(
                select(RevocacionFactura).where(
                    RevocacionFactura.uuid_sucursal == seeded_sucursal_uuid,
                    RevocacionFactura.motivo == "primera",
                )
            )
        ).scalar_one()
        first_hash_actual = first_row.hash_actual

        second_payload = {
            "uuid_sucursal": seeded_sucursal_uuid,
            "uuid_factura_electronica": None,
            "motivo": "segunda",
            "timestamp_evento": datetime.now(UTC).replace(tzinfo=None),
        }
        await revocacion_factura_chain(
            HookContext(
                spec=spec, payload=second_payload, session=session, actor_uuid=ACTOR_UUID
            )
        )
        await session.commit()

        second_row = (
            await session.execute(
                select(RevocacionFactura).where(
                    RevocacionFactura.uuid_sucursal == seeded_sucursal_uuid,
                    RevocacionFactura.motivo == "segunda",
                )
            )
        ).scalar_one()

        assert second_row.hash_anterior == first_hash_actual
        assert second_row.hash_actual != first_hash_actual


def test_revocacion_factura_chain_registered_on_catalog_spec() -> None:
    """T-PR6-005 — the catalog spec's ``hook_chain_extend`` slot IS this hook.

    ``dian/cloud/dispatcher.py`` looks this up via
    ``SYNC_CATALOG_BY_NAME["revocacion_factura"].hook_chain_extend`` rather
    than importing/calling ``repo.hash_chain.append`` directly.
    """
    spec = SYNC_CATALOG_BY_NAME["revocacion_factura"]
    assert spec.hook_chain_extend is revocacion_factura_chain
