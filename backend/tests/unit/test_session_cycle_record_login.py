"""test_session_cycle_record_login.py — REQ-42, REQ-43.

Unit tests for ``repo.session_cycle.record_login`` and the (skeleton)
``close_login_with_log`` helper.

The DB layer enforces:

  - INSERT on ``login`` is unconditional (no co-transactional log row needed).
  - UPDATE on ``login`` requires a co-transactional ``log_transaccional``
    row referencing the login row's uuid.

PR1b ships:

  - ``record_login`` — INSERTs a ``login`` row with ``estado='exitoso'``
    (or ``'fallido'``) and a co-transactional ``log_transaccional`` row
    with ``accion='login'``. Verified here.
  - ``close_login_with_log`` — skeleton. Full impl lands in PR7.
    We test the basic happy path: log row FIRST, then UPDATE.

We do NOT need a Usuarios row for these tests because the helper only
sets ``uuid_usuario`` + ``uuid_sucursal`` columns. The FK to ``usuarios``
is intentionally nullable in the schema (PR1b design choice).
"""
from __future__ import annotations

import uuid as uuid_lib


async def test_record_login_inserts_login_row(pg_engine, alembic_upgrade) -> None:
    """``record_login(success=True)` inserts a ``login`` row with ``estado='exitoso'``."""
    from parkos_core.models.L_S.login import Login
    from parkos_core.repo.session_cycle import record_login
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    usuario = uuid_lib.uuid4()
    sucursal = uuid_lib.uuid4()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await record_login(
            session,
            usuario_uuid=usuario,
            sucursal_uuid=sucursal,
            actor_uuid=actor,
            success=True,
        )
        await session.commit()
        await session.refresh(row)

        assert row.uuid is not None
        assert row.uuid_usuario == usuario
        assert row.uuid_sucursal == sucursal
        assert row.estado == "exitoso"
        assert row.vigente_hasta is None
        assert row.created_by == actor

        # The login row is observable via direct select.
        stmt = select(Login).where(Login.uuid == row.uuid)
        fetched = (await session.execute(stmt)).scalar_one()
        assert fetched.estado == "exitoso"


async def test_record_login_failed_inserts_with_estado_fallido(
    pg_engine, alembic_upgrade
) -> None:
    """``record_login(success=False)` inserts with ``estado='fallido'``."""
    from parkos_core.repo.session_cycle import record_login
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await record_login(
            session,
            usuario_uuid=uuid_lib.uuid4(),
            sucursal_uuid=uuid_lib.uuid4(),
            actor_uuid=actor,
            success=False,
            motivo="bad_password",
        )
        await session.commit()
        await session.refresh(row)
        assert row.estado == "fallido"


async def test_record_login_writes_log_row(pg_engine, alembic_upgrade) -> None:
    """``record_login`` writes a co-transactional ``log_transaccional`` row."""
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.repo.session_cycle import record_login
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    sucursal = uuid_lib.uuid4()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        await record_login(
            session,
            usuario_uuid=uuid_lib.uuid4(),
            sucursal_uuid=sucursal,
            actor_uuid=actor,
            success=True,
        )
        await session.commit()

        # Look for the log row.
        stmt = (
            select(LogTransaccional)
            .where(LogTransaccional.uuid_usuario == actor)
            .where(LogTransaccional.accion == "login")
            .where(LogTransaccional.tabla_afectada == "login")
        )
        log_row = (await session.execute(stmt)).scalar_one_or_none()
        assert log_row is not None, (
            "record_login did not write a co-transactional log_transaccional row"
        )
        assert log_row.uuid_sucursal == sucursal


async def test_close_login_with_log_skipped_in_pr1b(pg_engine, alembic_upgrade) -> None:
    """``close_login_with_log`` is a PR1b skeleton; PR7 lands the full impl.

    We still exercise the helper to ensure the skeleton doesn't crash on
    a happy path: insert a login row, call ``close_login_with_log``,
    observe the UPDATE applied and a new log row written.
    """
    from parkos_core.models.A.log_transaccional import LogTransaccional
    from parkos_core.models.L_S.login import Login
    from parkos_core.repo.session_cycle import close_login_with_log, record_login
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    sucursal = uuid_lib.uuid4()

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        login_row = await record_login(
            session,
            usuario_uuid=actor,
            sucursal_uuid=sucursal,
            actor_uuid=actor,
            success=True,
        )
        await session.commit()

        await close_login_with_log(
            session,
            login_uuid=login_row.uuid,
            actor_uuid=actor,
        )
        await session.commit()

        # The login row should now have timestamp_cierre + estado='cerrado'.
        stmt = select(Login).where(Login.uuid == login_row.uuid)
        refreshed = (await session.execute(stmt)).scalar_one()
        assert refreshed.timestamp_cierre is not None, (
            "close_login_with_log did not set timestamp_cierre"
        )
        assert refreshed.estado == "cerrado", (
            f"close_login_with_log did not transition estado (got {refreshed.estado!r})"
        )

        # A second log row (accion='logout') must exist.
        logout_stmt = (
            select(LogTransaccional)
            .where(LogTransaccional.uuid_usuario == actor)
            .where(LogTransaccional.accion == "logout")
        )
        logout_row = (await session.execute(logout_stmt)).scalar_one_or_none()
        assert logout_row is not None, (
            "close_login_with_log did not write the logout log_transaccional row"
        )