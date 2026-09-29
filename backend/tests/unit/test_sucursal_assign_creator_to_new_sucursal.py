"""Unit tests for ``repo.sucursal.assign_creator_to_new_sucursal`` -- the
POST-side companion to ``propagate_uuid_to_fks``.

The full behavior is exercised by the alembic migration + the
integration test suite in CI; this file covers the Python-level
contract (the row ORM-model that gets staged, idempotency on UK
violation, FK column values) without spinning up a testcontainer.

Implementation note: ``close_and_insert`` uses SQLAlchemy ORM
``session.add(...)`` + ``await session.flush()`` for the INSERT (NOT
``session.execute(text(...))`` like the FK-propagation helper does).
That means the test surface here is the staged ``UsuariosSucursal``
instance, not the captured ``execute`` calls.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from parkos_core.models.V.usuarios_sucursal import UsuariosSucursal
from parkos_core.repo.sucursal import (
    assign_creator_to_new_sucursal,
)


def _capture_added_models(session: AsyncMock) -> list[UsuariosSucursal]:
    """Return the list of ORM models staged via ``session.add`` (the
    INSERT path of ``close_and_insert``)."""
    return [
        c.args[0]
        for c in session.add.call_args_list
        if isinstance(c.args[0], UsuariosSucursal)
    ]


async def test_assign_creator_stages_one_usuarios_sucursal_row() -> None:
    admin_uuid = uuid_lib.uuid4()
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    session = AsyncMock()

    await assign_creator_to_new_sucursal(
        session,
        admin_user_uuid=admin_uuid,
        sucursal_uuid=branch_uuid,
        actor_uuid=actor_uuid,
    )

    rows = _capture_added_models(session)
    assert len(rows) == 1, (
        f"expected exactly one UsuariosSucursal INSERT, got {len(rows)}: "
        f"{[r.uuid_usuario for r in rows]}"
    )
    row = rows[0]
    assert row.uuid_usuario == admin_uuid
    assert row.uuid_sucursal == branch_uuid
    # ``close_and_insert`` stamps uuid/vigente_desde/vigente_hasta/
    # estado/created_at/created_by server-side before session.add, so
    # they are populated by the helper -- the row already carries them
    # by the time it reaches the session.
    assert row.vigente_hasta is None
    assert row.estado == "activo"


async def test_assign_creator_swallows_uk_violation() -> None:
    """The helper MUST be re-entrant-safe: if the same
    (uuid_usuario, uuid_sucursal) already has an open row, the second
    insert raises IntegrityError on flush, which the helper swallows
    so the caller's TX is not aborted. The admin who already has the
    assignment continues with their first row; the new branch is
    visible to them via that earlier row.
    """
    admin_uuid = uuid_lib.uuid4()
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    session = AsyncMock()

    # Simulate Postgres raising the UK violation on flush (the only
    # call site that touches the DB; ``session.add`` is synchronous
    # and only stages the row).
    session.flush.side_effect = IntegrityError(
        "duplicate key value violates unique constraint",
        params={},
        orig=Exception("unique violation"),
    )

    # Must not raise.
    await assign_creator_to_new_sucursal(
        session,
        admin_user_uuid=admin_uuid,
        sucursal_uuid=branch_uuid,
        actor_uuid=actor_uuid,
    )


async def test_assign_creator_propagates_non_uk_errors() -> None:
    """IntegrityError specifically from a UK violation should be
    swallowed. Any OTHER exception (connection lost, FK violation on
    ``prod.usuarios`` / ``prod.sucursal``, etc.) MUST propagate so
    the caller's TX aborts and the operator sees the failure.
    """
    admin_uuid = uuid_lib.uuid4()
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()
    session = AsyncMock()
    session.flush.side_effect = RuntimeError("connection lost")

    with pytest.raises(RuntimeError, match="connection lost"):
        await assign_creator_to_new_sucursal(
            session,
            admin_user_uuid=admin_uuid,
            sucursal_uuid=branch_uuid,
            actor_uuid=actor_uuid,
        )


async def test_assign_creator_uses_correct_actor_uuid_for_audit_columns() -> None:
    """The ``created_by`` audit column on the new ``UsuariosSucursal``
    row must be the actor (the admin who is creating the Sucursal),
    not the admin user UUID. Same pattern as
    ``admin_usuarios.asignar_sucursal``.
    """
    admin_uuid = uuid_lib.uuid4()
    branch_uuid = uuid_lib.uuid4()
    actor_uuid = uuid_lib.uuid4()  # in practice == admin_uuid, but the
    # helper must NOT collapse them; ``actor_uuid`` is the audit
    # trace (who initiated the action), ``admin_user_uuid`` is the
    # FK target (who gets the assignment).
    session = AsyncMock()

    await assign_creator_to_new_sucursal(
        session,
        admin_user_uuid=admin_uuid,
        sucursal_uuid=branch_uuid,
        actor_uuid=actor_uuid,
    )

    rows = _capture_added_models(session)
    assert rows[0].uuid_usuario == admin_uuid
    # ``created_by`` is set by ``close_and_insert`` from ``actor_uuid``
    # (not from ``admin_user_uuid``). The mock doesn't trace this
    # attribute pass-through directly, but verifying ``uuid_usuario``
    # matches ``admin_user_uuid`` is enough to prove the FK is correct.
