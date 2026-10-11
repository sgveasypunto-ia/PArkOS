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
     raises ``VersioningConflictError`` (the UK on ``usuarios_uk01``,
     mapped from the underlying ``IntegrityError`` by the helper --
     HU-tarifas-batch).

The helper writes a co-transactional ``log_transaccional`` row in the
same TX. That is the ONLY [A] write the helper performs (per design §4.1)
and the AST test ``test_no_raw_dml_on_a_tables.py`` allowlists this file.
"""

from __future__ import annotations

import uuid as uuid_lib

import pytest


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
        assert len(all_rows) == 2, f"expected 2 history rows for {cedula}, got {len(all_rows)}"


async def test_close_and_insert_uk_violation(pg_engine, alembic_upgrade) -> None:
    """Inserting two rows with the same ``(cedula, vigente_desde)`` raises
    ``VersioningConflictError`` (the typed exception introduced by
    HU-tarifas-batch; previously this raised the raw ``IntegrityError``).

    The mapping ``IntegrityError → VersioningConflictError`` lives in
    ``repo.versioned.close_and_insert`` (see
    ``tests/unit/test_close_and_insert_conflict.py`` for the unit-level
    pinning of the same mapping across drivers). The end-to-end
    consequence for callers: an HTTP handler catching
    ``VersioningConflictError`` translates it to 409 with the constraint
    name attached, instead of letting a bare 500 leak to the FE.

    ``close_and_insert`` computes ``vigente_desde`` from ``datetime.now()``
    INTERNALLY on every call — two separate calls a moment apart therefore
    get two DIFFERENT ``vigente_desde`` values (down to microsecond
    resolution) and would never actually collide on the ``usuarios_uk01``
    unique constraint. Pass an explicit, identical ``vigente_desde`` via
    ``new_attrs`` (which the helper's ``payload`` dict lets a caller
    override) so the test deterministically reproduces the collision it is
    meant to verify, instead of depending on two wall-clock reads
    coincidentally matching.
    """
    from datetime import UTC, datetime

    from parkos_core.models.V.usuarios import Usuarios
    from parkos_core.repo.versioned import VersioningConflictError, close_and_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    cedula = f"test-{uuid_lib.uuid4().hex[:8]}"
    shared_vigente_desde = datetime.now(UTC).replace(tzinfo=None)

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
                "vigente_desde": shared_vigente_desde,
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()

        # Same cedula + same vigente_desde → UK violation.
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
                    "vigente_desde": shared_vigente_desde,
                },
                actor_uuid=actor,
                log_tx=True,
            )
            await session.commit()

        with pytest.raises(VersioningConflictError) as exc_info:
            await _attempt_duplicate()
        # The constraint name is extracted from the asyncpg diag struct
        # on the live Postgres path (this is an integration test using
        # testcontainers, so asyncpg is the driver).
        assert exc_info.value.constraint_name == "usuarios_uk01"
        await session.rollback()


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


async def test_close_and_insert_drops_validation_only_schema_fields(
    pg_engine, alembic_upgrade
) -> None:
    """Schema fields with no column are dropped, not passed to the model.

    ``ClientesCreate.dv`` is the canonical case: the DIAN NIT modulo-11
    check needs a check digit, and the schema computes it for validation
    only -- ``prod.clientes`` has eight business columns and none of them is
    ``dv``. Handing that dict to the declarative constructor raised
    ``TypeError: 'dv' is an invalid keyword argument for Clientes`` inside
    SQLAlchemy's ``_declarative_constructor``, which the API surfaced as a
    bare 500 on ``POST /api/v1/clientes/clientes``.

    The fix filters ``new_attrs`` against the model's real columns inside
    the shared helper, so every ``make_router``-mounted resource is covered
    rather than only the repos that already stripped ``dv`` by hand.
    """
    from parkos_core.models.V.clientes import Clientes
    from parkos_core.repo.versioned import close_and_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()

    assert "dv" not in {c.name for c in Clientes.__table__.columns}, (
        "precondition: prod.clientes must NOT have a dv column -- if a "
        "migration added one, this test is asserting the wrong thing"
    )

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        row = await close_and_insert(
            session,
            Clientes,
            current_uuid=None,
            new_attrs={
                "tipo_identificador": "NIT",
                "numero_identificacion": f"900{uuid_lib.uuid4().hex[:9]}",
                "nombre": "Validacion",
                "apellido": "Schema",
                # Validation-only: present in ClientesCreate, absent from the table.
                "dv": "3",
                # Also absent from the table -- a typo-shaped extra must not
                # become a 500 either.
                "campo_inexistente": "ignorar",
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()
        await session.refresh(row)

        assert row.uuid is not None
        assert row.estado == "activo"
        assert row.nombre == "Validacion"
        assert not hasattr(row, "dv"), "dv must not be bound on the instance"


async def test_close_and_insert_update_path_drops_validation_only_fields(
    pg_engine, alembic_upgrade
) -> None:
    """The close+insert (Actualizaci6n) path filters them too, not just INSERT.

    The Actualizaci6n path merges ``carried_forward`` (attributes carried
    from the closed row) with ``new_attrs``. Only ``new_attrs`` comes from a
    Pydantic schema, but the merge happens after both dicts are filtered, so
    a validation-only key can never reach the constructor on either path.
    """
    from parkos_core.models.V.clientes import Clientes
    from parkos_core.repo.versioned import close_and_insert
    from sqlalchemy.ext.asyncio import async_sessionmaker

    actor = uuid_lib.uuid4()
    numero = f"901{uuid_lib.uuid4().hex[:9]}"

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        v1 = await close_and_insert(
            session,
            Clientes,
            current_uuid=None,
            new_attrs={
                "tipo_identificador": "NIT",
                "numero_identificacion": numero,
                "nombre": "Antes",
                "dv": "1",
            },
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()
        v1_uuid = v1.uuid

        v2 = await close_and_insert(
            session,
            Clientes,
            current_uuid=v1_uuid,
            new_attrs={"nombre": "Despues", "dv": "1"},
            actor_uuid=actor,
            log_tx=True,
        )
        await session.commit()
        await session.refresh(v2)

        assert v2.uuid != v1_uuid, "close_and_insert must open a NEW version"
        assert v2.nombre == "Despues"
        # The untouched business columns carried forward across the version
        # boundary -- proof the filter did not eat real columns.
        assert v2.numero_identificacion == numero
        assert v2.vigente_hasta is None
        assert v2.estado == "activo"
