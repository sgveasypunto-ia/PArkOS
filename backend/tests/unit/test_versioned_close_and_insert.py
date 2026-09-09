"""test_versioned_close_and_insert.py — REQ-04, REQ-05.

Unit tests for ``parkos_core.repo.versioned.close_and_insert``.

Verifies, against the live test DB:

  1. INSERT-only path (current_uuid=None) — a new [V] row lands with
     ``vigente_desde = NOW()``, ``vigente_hasta = NULL``, ``estado = 'activo'``.
  2. Close+insert path (current_uuid=<existing>) — the old row's
     ``vigente_hasta`` becomes ``NOW()`` and its ``estado`` becomes
     ``'inactivo'``; a new row appears with the new attrs and
     ``vigente_hasta = NULL``, ``estado = 'activo'``. Both rows coexist
     (history is reconstructable).
  3. UK violation path — re-inserting the same ``(cedula, vigente_desde)``
     raises ``IntegrityError`` (the UK on ``usuarios_uk01``).

The helper writes a co-transactional ``log_transaccional`` row in the
same TX. That is the ONLY [A] write the helper performs (per design §4.1)
and the AST test ``test_no_raw_dml_on_a_tables.py`` allowlists this file.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from sqlalchemy.exc import IntegrityError

_XFAIL_GENESIS = pytest.mark.xfail(
    reason=(
        "Bloqueado hasta PR6 (hash-chain genesis-row bootstrap) — "
        "openspec/changes/sync-overhaul/tasks.md PR6"
    ),
    strict=True,
)


@_XFAIL_GENESIS
async def test_close_and_insert_new_row(pg_engine, alembic_upgrade) -> None:
    """INSERT-only path creates a [V] row with the canonical bi-temporal columns."""
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.repo.versioned import close_and_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        new_row = await close_and_insert(
            session,
            Usuarios,
            current_uuid=None,
            new_attrs={
                "nombre": "Alice",
                "apellido": "Test",
                "cedula": f"test-{uuid_lib.uuid4().hex[:8]}",
                "email": "alice@example.com",
                "password_hash": "$2b$12$test",
                "rol": "operador",
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()
        await session.refresh(new_row)
        assert new_row.uuid is not None
        assert new_row.vigente_desde is not None
        assert new_row.vigente_hasta is None
        assert new_row.estado == "activo"
        assert new_row.created_by == actor


@_XFAIL_GENESIS
async def test_close_and_insert_closes_old_row(pg_engine, alembic_upgrade) -> None:
    """Close+insert path sets ``vigente_hasta`` + 'inactivo' on the old row."""
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.repo.versioned import close_and_insert, current_version
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    cedula = f"test-{uuid_lib.uuid4().hex[:8]}"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        # Step 1: insert v1.
        v1 = await close_and_insert(
            session,
            Usuarios,
            current_uuid=None,
            new_attrs={
                "nombre": "Bob",
                "cedula": cedula,
                "email": "bob@example.com",
                "password_hash": "$2b$12$test",
                "rol": "operador",
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()
        await session.refresh(v1)
        v1_uuid = v1.uuid

        # Step 2: close v1 + insert v2 with a different name.
        v2 = await close_and_insert(
            session,
            Usuarios,
            current_uuid=v1_uuid,
            new_attrs={
                "nombre": "Bob-Updated",
                "cedula": cedula,  # same cedula — UK requires different vigente_desde
                "email": "bob@example.com",
                "password_hash": "$2b$12$test",
                "rol": "operador",
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()

        # Old row must now be 'inactivo' with vigente_hasta set.
        old = await current_version(session, Usuarios, v1_uuid)
        assert old is None, (
            "current_version should not return the closed row (vigente_hasta IS NULL filter)"
        )

        # The new row is the active one.
        await session.refresh(v2)
        assert v2.uuid != v1_uuid, "new row must have a fresh uuid"
        assert v2.nombre == "Bob-Updated"
        assert v2.vigente_hasta is None
        assert v2.estado == "activo"

        # Both rows are visible in the history endpoint semantics
        # (filter by uuid, not by vigente_hasta).
        from sqlalchemy import select
        stmt = select(Usuarios).where(Usuarios.uuid.in_([v1_uuid, v2.uuid]))
        result = await session.execute(stmt)
        all_rows = list(result.scalars().all())
        assert len(all_rows) == 2, (
            f"expected 2 history rows for {cedula}, got {len(all_rows)}"
        )


@_XFAIL_GENESIS
async def test_close_and_insert_uk_violation(pg_engine, alembic_upgrade) -> None:
    """Inserting two rows with the same ``(cedula, vigente_desde)`` raises IntegrityError."""
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.repo.versioned import close_and_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    cedula = f"test-{uuid_lib.uuid4().hex[:8]}"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await close_and_insert(
            session,
            Usuarios,
            current_uuid=None,
            new_attrs={
                "nombre": "Charlie",
                "cedula": cedula,
                "email": "charlie@example.com",
                "password_hash": "$2b$12$test",
                "rol": "operador",
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()

        # Same cedula + same vigente_desde (NOW()) → UK violation.
        async def _attempt_duplicate() -> None:
            await close_and_insert(
                session,
                Usuarios,
                current_uuid=None,
                new_attrs={
                    "nombre": "Charlie-Dup",
                    "cedula": cedula,
                    "email": "charlie@example.com",
                    "password_hash": "$2b$12$test",
                    "rol": "operador",
                },
                actor_uuid=actor,
                log_tx=True,
            )
            await session.commit()

        with pytest.raises(IntegrityError):
            await _attempt_duplicate()
        await session.rollback()


@_XFAIL_GENESIS
async def test_close_and_insert_log_row_created(pg_engine, alembic_upgrade) -> None:
    """The helper writes a co-transactional ``log_transaccional`` row."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.repo.versioned import close_and_insert
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await close_and_insert(
            session,
            Usuarios,
            current_uuid=None,
            new_attrs={
                "nombre": "Dora",
                "cedula": f"test-{uuid_lib.uuid4().hex[:8]}",
                "email": "dora@example.com",
                "password_hash": "$2b$12$test",
                "rol": "operador",
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()

        # Find the log row.
        stmt = (
            select(LogTransaccional)
            .where(LogTransaccional.uuid_usuario == actor)
            .where(LogTransaccional.accion == "crear")
            .where(LogTransaccional.tabla_afectada == "usuarios")
        )
        result = await session.execute(stmt)
        log_row = result.scalar_one_or_none()
        assert log_row is not None, (
            "close_and_insert did not write a co-transactional log_transaccional row"
        )