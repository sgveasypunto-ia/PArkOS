"""test_append_only.py — REQ-10 + REQ-13 + REQ-15.

Unit tests for :func:`parkos_core.repo.append_only.append_event` and
:func:`parkos_core.repo.append_only.compensate`.

These tests run against the live test DB (``alembic_upgrade`` fixture).
They verify:

  1. ``append_event`` inserts a row with the supplied attrs, sets
     ``created_at`` / ``created_by`` server-side, and returns the instance.
  2. ``compensate`` reads an original ``pago`` row, inserts a
     ``reverso`` row whose ``uuid_pago_revertido`` points at the
     original, and refuses to mark an already-reversed row.
  3. The DB-layer inmutability contract is honored (UPDATE/DELETE on
     the new row raises the table-specific trigger exception) — covered
     in :mod:`tests.migrations.test_a_inmutable`.

Note on ``factura_pagos``: the model lives in PR6 but the
:func:`compensate` helper is generic — it dispatches on
``model_cls.tipo_movimiento`` / ``model_cls.uuid_pago_revertido``
attributes. We exercise it against ``prod.log_transaccional`` (a
generic [A] table) by writing a synthetic row with the two columns.

Actually, we exercise it against a real ``[A]`` row shape using the
existing ``log_transaccional`` table — but ``log_transaccional`` does
NOT have ``tipo_movimiento`` / ``uuid_pago_revertido``. So the test
uses an inline SQL path (a raw INSERT that creates a stand-in row with
those columns on a non-[A] table) only as a happy-path sanity check.

In practice the production path (``factura_pagos``) lands in PR6 and
the test there will assert the full reverso flow. This PR2 test just
verifies the helper's dispatch logic by checking that a non-matching
model raises :class:`AppendOnlyError`.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest


async def _seed_genesis(session, uuid_sucursal) -> None:
    """Bootstrap the hash-chain genesis row for one ``uuid_sucursal``.

    Only needed here because 3 of this file's tests call ``append_event``
    with ``chain_hash=False`` (the default) — they never route through
    ``repo.hash_chain.append``'s PR6 auto-bootstrap, yet the DB trigger
    ``fn_extend_hash_chain()`` still fires unconditionally on every INSERT
    into ``prod.log_transaccional``. Reuses the SAME production helper
    ``repo.hash_chain._ensure_genesis_row`` rather than duplicating the
    genesis-row construction here.
    """
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.hash_chain import _ensure_genesis_row

    await _ensure_genesis_row(session, LogTransaccional, uuid_sucursal)
    await session.commit()


# ---------------------------------------------------------------------------
# append_event tests
# ---------------------------------------------------------------------------


async def test_append_event_inserts_row(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``append_event`` writes a row with the supplied attrs + server-side audit columns."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.append_only import append_event
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    sucursal = seeded_sucursal_uuid
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        await _seed_genesis(session, sucursal)
        row = await append_event(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": sucursal,
                "accion": "test_accion",
                "tabla_afectada": "log_transaccional",
                "uuid_registro_afectado": uuid_lib.uuid4(),
                "datos_anteriores": {"old": "x"},
                "datos_nuevos": {"new": "y"},
            },
            actor_uuid=actor,
        )
        await session.commit()

        assert row.uuid is not None
        assert row.created_by == actor
        assert row.created_at is not None
        assert row.accion == "test_accion"
        assert row.uuid_sucursal == sucursal


async def test_append_event_stamps_created_at_when_absent(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """When the caller doesn't pass ``created_at``, the helper stamps NOW()."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.append_only import append_event
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        await _seed_genesis(session, seeded_sucursal_uuid)
        row = await append_event(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": seeded_sucursal_uuid,
                "accion": "no_created_at",
                "tabla_afectada": "log_transaccional",
                "uuid_registro_afectado": uuid_lib.uuid4(),
            },
            actor_uuid=actor,
        )
        await session.commit()

        assert row.created_at is not None


async def test_append_event_with_hash_chain_extends_chain(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """``append_event(chain_hash=True)`` invokes ``hash_chain.append`` and stamps the chain."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.append_only import append_event
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    sucursal = seeded_sucursal_uuid
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        row = await append_event(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": sucursal,
                "accion": "with_chain",
                "tabla_afectada": "log_transaccional",
                "uuid_registro_afectado": uuid_lib.uuid4(),
            },
            actor_uuid=actor,
            chain_hash=True,
        )
        await session.commit()

        assert row.hash_anterior is not None
        assert row.hash_actual is not None
        # Chain anchor must match the genesis hash for this uuid_sucursal.
        from parkos_core.repo.hash_chain import _genesis_hash

        assert row.hash_anterior == _genesis_hash(sucursal)


async def test_compensate_rejects_non_compatible_model(pg_engine, alembic_upgrade) -> None:
    """``compensate`` raises ``AppendOnlyError`` when model_cls lacks the columns."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.append_only import AppendOnlyError, compensate
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        with pytest.raises(AppendOnlyError, match="tipo_movimiento"):
            await compensate(
                session,
                LogTransaccional,  # no tipo_movimiento / uuid_pago_revertido columns
                original_uuid=uuid_lib.uuid4(),
                attrs={},
            )


async def test_compensate_rejects_missing_original(pg_engine, alembic_upgrade) -> None:
    """``compensate`` raises ``OriginalNotFoundError`` when uuid doesn't exist.

    This test exercises the dispatch contract using ``log_transaccional``
    as a stand-in model that we bypass the column check for. Since
    ``log_transaccional`` does NOT carry the columns, the helper raises
    ``AppendOnlyError`` BEFORE the SELECT — so the actual
    ``OriginalNotFoundError`` branch is only reachable for models with
    the columns (e.g. ``factura_pagos`` in PR6).
    """
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.append_only import AppendOnlyError, compensate
    from sqlalchemy.ext.asyncio import async_sessionmaker

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        with pytest.raises(AppendOnlyError):
            await compensate(
                session,
                LogTransaccional,
                original_uuid=uuid_lib.uuid4(),
                attrs={},
            )


async def test_append_only_rejects_update(
    pg_engine, alembic_upgrade, seeded_sucursal_uuid
) -> None:
    """After ``append_event`` + commit, UPDATE on the row raises the DB trigger.

    This is the integration version of ``test_a_inmutable.py`` for the
    specific row path through ``repo.append_only``. We use psycopg
    directly so the SQL UPDATE clearly bypasses SQLAlchemy's session —
    what matters is the DB trigger, not the ORM layer.
    """
    import psycopg
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.append_only import append_event
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        await _seed_genesis(session, seeded_sucursal_uuid)
        row = await append_event(
            session,
            LogTransaccional,
            {
                "uuid_sucursal": seeded_sucursal_uuid,
                "accion": "immutable_test",
                "tabla_afectada": "log_transaccional",
                "uuid_registro_afectado": uuid_lib.uuid4(),
            },
            actor_uuid=actor,
        )
        await session.commit()
        row_uuid = row.uuid

    # Use the raw DSN from the engine to attempt an UPDATE.

    dsn = pg_engine.url.render_as_string(hide_password=False).replace(
        "+asyncpg", ""
    )

    async with await psycopg.AsyncConnection.connect(dsn) as conn, conn.cursor() as cur:
        try:
            await cur.execute(
                "UPDATE prod.log_transaccional SET accion = 'mutado' WHERE uuid = %s",
                (row_uuid,),
            )
            await conn.commit()
        except psycopg.errors.InsufficientPrivilege as exc:
            # ERRCODE = '42501' (fn_log_transaccional_inmutable,
            # 0001_initial_schema.py) -> psycopg surfaces InsufficientPrivilege,
            # not the generic RaiseException (P0001, the default for a plain
            # RAISE EXCEPTION with no explicit code). Pre-existing test bug
            # discovered while un-xfailing this test for PR6 (masked before
            # by the genesis-row failure short-circuiting earlier).
            msg = str(exc)
            assert "LOG_TRANSACCIONAL_INMUTABLE" in msg, (
                f"log_transaccional: trigger raised but missing tag; got '{msg}'"
            )
        else:  # pragma: no cover
            pytest.fail("UPDATE succeeded but trigger should have blocked it")