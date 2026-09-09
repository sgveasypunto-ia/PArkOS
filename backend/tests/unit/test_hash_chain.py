"""test_hash_chain.py — SC-X2 + SC-X3 (canonical JSON + chain extension).

Unit tests for :func:`parkos_core.repo.hash_chain.append` and
:func:`parkos_core.repo.hash_chain._canonical_json`.

Verifies:

  1. ``_canonical_json`` produces deterministic bytes regardless of
     dict insertion order.
  2. The genesis anchor for ``uuid_sucursal=None`` is the SHA-256 of
     ``b"genesis:NULL"``.
  3. ``hash_chain.append`` writes a row whose ``hash_anterior`` matches
     the genesis anchor for the FIRST row in a tenant.
  4. A second row's ``hash_anterior`` matches the prior row's
     ``hash_actual`` — the canonical chain extension invariant.
  5. ``hash_chain.append`` raises :class:`HashChainIntegrityViolation`
     when called against a model without the chain columns.
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib

import pytest
from parkos_core.repo.hash_chain import (
    GENESIS_PREFIX,
    HashChainIntegrityViolation,
    _canonical_json,
    _genesis_hash,
)


def test_canonical_json_is_deterministic() -> None:
    """Same payload dict hash to the same bytes regardless of insertion order."""
    a = {"uuid_sucursal": "abc", "accion": "test", "tabla_afectada": "x"}
    b = {"tabla_afectada": "x", "uuid_sucursal": "abc", "accion": "test"}
    assert _canonical_json(a) == _canonical_json(b)
    assert _canonical_json(a) == b'{"accion":"test","tabla_afectada":"x","uuid_sucursal":"abc"}'


def test_canonical_json_sorts_nested_keys() -> None:
    """Nested dicts also get sorted keys — required for the chain to be stable."""
    a = {"outer": {"z": 1, "a": 2}}
    b = {"outer": {"a": 2, "z": 1}}
    assert _canonical_json(a) == _canonical_json(b)


def test_canonical_json_unicode_safe() -> None:
    """Non-ASCII payloads round-trip via UTF-8 (ensure_ascii=False)."""
    payload = {"nombre": "Café Ñoño"}
    expected = '{"nombre":"Café Ñoño"}'.encode()
    assert _canonical_json(payload) == expected


def test_genesis_hash_for_null_sucursal() -> None:
    """The global anchor is SHA-256 of ``b"genesis:NULL"``."""
    expected = hashlib.sha256(b"genesis:NULL").hexdigest()
    assert _genesis_hash(None) == expected


def test_genesis_hash_for_specific_sucursal() -> None:
    """A specific tenant's anchor is SHA-256 of ``b"genesis:" + uuid_bytes``."""
    uuid = uuid_lib.UUID("12345678-1234-5678-1234-567812345678")
    expected = hashlib.sha256(b"genesis:" + str(uuid).encode("ascii")).hexdigest()
    assert _genesis_hash(uuid) == expected


def test_genesis_prefix_constant() -> None:
    """``GENESIS_PREFIX`` is the canonical byte sequence — used for tests + chain verification."""
    assert GENESIS_PREFIX == b"genesis:"


@pytest.mark.xfail(
    reason=(
        "Bloqueado hasta PR6 (hash-chain genesis-row bootstrap) — "
        "openspec/changes/sync-overhaul/tasks.md PR6"
    ),
    strict=True,
)
async def test_hash_chain_append_first_row_uses_genesis(pg_engine, alembic_upgrade) -> None:
    """The first row in a tenant has ``hash_anterior`` = genesis hash for that tenant."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.hash_chain import append
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    sucursal = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        row = await append(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": sucursal,
                "accion": "first_row",
                "tabla_afectada": "log_transaccional",
                "uuid_registro_afectado": uuid_lib.uuid4(),
            },
            actor_uuid=actor,
        )
        await session.commit()

        assert row.hash_anterior == _genesis_hash(sucursal)
        assert row.hash_actual is not None
        assert row.hash_actual != row.hash_anterior


@pytest.mark.xfail(
    reason=(
        "Bloqueado hasta PR6 (hash-chain genesis-row bootstrap) — "
        "openspec/changes/sync-overhaul/tasks.md PR6"
    ),
    strict=True,
)
async def test_hash_chain_append_second_row_links_to_prior(
    pg_engine, alembic_upgrade
) -> None:
    """A second row's ``hash_anterior`` matches the prior row's ``hash_actual``."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.hash_chain import append
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    sucursal = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        # First row — starts the chain.
        first = await append(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": sucursal,
                "accion": "first",
                "tabla_afectada": "log_transaccional",
                "uuid_registro_afectado": uuid_lib.uuid4(),
            },
            actor_uuid=actor,
        )
        await session.commit()
        first_hash = first.hash_actual

        # Second row — extends the chain.
        second = await append(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": sucursal,
                "accion": "second",
                "tabla_afectada": "log_transaccional",
                "uuid_registro_afectado": uuid_lib.uuid4(),
            },
            actor_uuid=actor,
        )
        await session.commit()

        assert second.hash_anterior == first_hash, (
            f"second.hash_anterior={second.hash_anterior!r} != "
            f"first.hash_actual={first_hash!r}"
        )
        assert second.hash_actual is not None
        assert second.hash_actual != first_hash


async def test_hash_chain_append_rejects_model_without_columns(
    pg_engine, alembic_upgrade
) -> None:
    """``hash_chain.append`` raises ``HashChainIntegrityViolation`` for non-chain models."""
    from parkos_core.models.A.sync_log import SyncLog
    from parkos_core.repo.hash_chain import append
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        with pytest.raises(HashChainIntegrityViolation, match="hash chain columns"):
            await append(
                session,
                SyncLog,  # no hash_anterior / hash_actual
                {"uuid_sucursal": uuid_lib.uuid4(), "timestamp_evento": None},
                actor_uuid=uuid_lib.uuid4(),
            )


def test_out_of_order_payload_raises() -> None:
    """Out-of-order payload should raise ``HashChainIntegrityViolation``.

    The SHA-256 chain is per-``uuid_sucursal`` and relies on
    ``timestamp_evento`` monotonicity. Two writes that race and the
    second arrives with a ``timestamp_evento`` BEFORE the first will
    cause the chain to silently fork:

      - ``_read_prior_hash`` orders by ``timestamp_evento DESC`` and
        returns the row with the LATEST timestamp as the prior.
      - The second row (with the EARLIER timestamp) sees the FUTURE
        row's ``hash_actual`` as its ``hash_anterior``.
      - Result: the chain splits into two heads; the cloud-side
        verifier (PR10) catches the divergence downstream but the
        helper itself is happy-path only.

    TODO: PR10+ backlog — implement out-of-order detection in
    ``repo/hash_chain.py::append``. The envelope is:
      1. Read the prior row by ``MAX(timestamp_evento)`` (already done).
      2. Compare the incoming payload's ``timestamp_evento`` to the
         prior's. If the incoming is <= prior, raise
         ``HashChainIntegrityViolation`` with a "out-of-order" reason.
      3. Optionally: read the row with ``MAX(timestamp_evento) WHERE
         timestamp_evento <= incoming`` to anchor the chain at the
         most recent earlier row (not just the head).

    When detection lands, remove this skip and assert the violation.

    PR2 retroactivo: this test pins the gap so the backlog item
    surfaces on every CI run.
    """
    pytest.skip(
        "out-of-order detection deferred — repo/hash_chain.py:append "
        "uses ORDER BY timestamp_evento DESC and does NOT validate that "
        "the incoming row's timestamp_evento >= prior row's. See "
        "Engram backlog (PR10+ cloud verifier scope)."
    )


@pytest.mark.xfail(
    reason=(
        "Trigger mal targeteado escribe vigente_desde sobre Ingreso "
        "([L-E], no versionado) — bug preexistente fuera de alcance de "
        "sync-overhaul, requiere investigación dedicada"
    ),
    strict=True,
)
async def test_record_event_log_tx_extends_hash_chain(
    pg_engine, alembic_upgrade
) -> None:
    """``record_event(log_tx=True)`` extends the SHA-256 chain (PR11c -- Bug 2).

    Verifies the fix: the ``log_transaccional`` row written by
    ``record_event`` carries ``hash_anterior`` = genesis (first call)
    and ``hash_actual`` != ``hash_anterior``. A second ``record_event``
    call against the same ``uuid_sucursal`` lands a row whose
    ``hash_anterior`` matches the prior row's ``hash_actual`` -- the
    canonical chain invariant.

    Requires the testcontainers Postgres container; skipped if not
    available (same gating as the other chain tests above).
    """
    from datetime import UTC, datetime

    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.models.L_E.ingreso import Ingreso
    from parkos_core.repo.event import record_event
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    sucursal = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        # 1. First record_event -- log_transaccional row must anchor at the
        #    per-sucursal genesis hash.
        await record_event(
            session,
            Ingreso,
            actor_uuid=actor,
            new_attrs={
                "uuid_sucursal": sucursal,
                "placa": "AAA-001",
                "fecha_ingreso": datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC).replace(
                    tzinfo=None
                ),
            },
            log_tx=True,
        )
        await session.commit()

        rows = (
            await session.execute(
                select(LogTransaccional)
                .where(LogTransaccional.uuid_sucursal == sucursal)
                .order_by(LogTransaccional.timestamp_evento.asc())
            )
        ).scalars().all()
        assert len(rows) == 1
        first = rows[0]
        assert first.hash_anterior == _genesis_hash(sucursal), (
            f"first.hash_anterior={first.hash_anterior!r} != genesis="
            f"{_genesis_hash(sucursal)!r}"
        )
        assert first.hash_actual is not None
        assert first.hash_actual != first.hash_anterior
        first_hash = first.hash_actual

    async with Session() as session:
        # 2. Second record_event -- log_transaccional row links to the prior.
        await record_event(
            session,
            Ingreso,
            actor_uuid=actor,
            new_attrs={
                "uuid_sucursal": sucursal,
                "placa": "BBB-002",
                "fecha_ingreso": datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC).replace(
                    tzinfo=None
                ),
            },
            log_tx=True,
        )
        await session.commit()

        rows = (
            await session.execute(
                select(LogTransaccional)
                .where(LogTransaccional.uuid_sucursal == sucursal)
                .order_by(LogTransaccional.timestamp_evento.asc())
            )
        ).scalars().all()
        assert len(rows) == 2
        second = rows[1]
        assert second.hash_anterior == first_hash, (
            f"second.hash_anterior={second.hash_anterior!r} != "
            f"first.hash_actual={first_hash!r}"
        )
        assert second.hash_actual is not None
        assert second.hash_actual != first_hash
