"""Unit tests for ``repo/admin_usuarios.py`` (IT-1.4, IT-1.5).

DB-mock pattern (F1.12/F1.13/F1.14 standard): mock all repo helpers
and DB-mock session with ``AsyncMock``. Tests focus on:
- bcrypt hash + 12-round cost factor symmetric with ``auth.py``.
- ``close_and_insert`` is called with the right payload shape.
- One ``sync_queue`` row per branch assignment is enqueued with the
  right ``operacion``/``tabla``/``datos`` shape.
- The helper raises ``UsuarioYaAsignadoError`` on duplicate open
  assignments.

Integration coverage lives in ``tests/integration/test_admin_usuarios_db.py``
(Docker real).
"""

from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.repo import admin_usuarios as admin_repo
from parkos_core.repo.admin_usuarios import (
    BCRYPT_ROUNDS,
    UsuarioYaAsignadoError,
    _bcrypt_hash,
)


def _actor_uuid() -> uuid_lib.UUID:
    return uuid_lib.UUID("00000000-0000-0000-0000-0000000000ad")


def _sucursal_uuid() -> uuid_lib.UUID:
    return uuid_lib.UUID("00000000-0000-0000-0000-0000000000b1")


# ---------------------------------------------------------------------------
# bcrypt helper -- the only piece that doesn't need a DB at all.
# ---------------------------------------------------------------------------


class TestBcryptHelper:
    def test_produces_a_2b_prefixed_hash(self) -> None:
        h = _bcrypt_hash("Pass1234word")
        assert h.startswith("$2b$")

    def test_cost_factor_matches_constant(self) -> None:
        # The 12 in ``$2b$12$`` MUST match BCRYPT_ROUNDS -- otherwise the
        # ``auth.py::login`` path (which uses the default 12) and this
        # hash would diverge.
        h = _bcrypt_hash("Pass1234word")
        cost = int(h.split("$")[2])
        assert cost == BCRYPT_ROUNDS
        assert cost == 12

    def test_verifies_round_trip(self) -> None:
        import bcrypt

        h = _bcrypt_hash("Pass1234word")
        assert bcrypt.checkpw(b"Pass1234word", h.encode("ascii"))


# ---------------------------------------------------------------------------
# create_admin_usuario
# ---------------------------------------------------------------------------


class TestCreateAdminUsuario:
    async def test_writes_one_user_and_one_sync_queue_per_branch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()

        user_row = MagicMock()
        user_row.uuid = uuid_lib.uuid4()
        user_row.nombre = "Ana"
        user_row.apellido = "Pérez"
        user_row.cedula = "1234567"
        user_row.email = "ana@parkos.local"
        user_row.password_hash = "$2b$12$" + "x" * 53
        user_row.rol = "operador"

        assignment_row_1 = MagicMock()
        assignment_row_1.uuid = uuid_lib.uuid4()
        assignment_row_2 = MagicMock()
        assignment_row_2.uuid = uuid_lib.uuid4()

        # First SELECT is ``create_admin_usuario``'s own email-uniqueness
        # pre-check (``EmailYaRegistradoError`` guard) -- it must report
        # "no existing active user" or the call raises before reaching
        # ``close_and_insert`` at all. Every SELECT after that is the
        # snapshot fetch inside ``_asignar_sucursal_helper`` (one per
        # branch assignment), which reads via ``scalar_one()``.
        call_count = {"n": 0}

        async def _execute_scalar(stmt: object, *a: object, **kw: object):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one.return_value = user_row
                result.scalar_one_or_none.return_value = user_row
            return result

        session.execute.side_effect = _execute_scalar

        call_log: list[str] = []

        async def _fake_close_and_insert(*args: object, **kwargs: object):
            model_cls = kwargs.get("model_cls") or args[1]
            call_log.append(model_cls.__name__)
            if model_cls.__name__ == "Usuarios":
                return user_row
            n = sum(1 for x in call_log if x == "UsuariosSucursal")
            return assignment_row_1 if n == 1 else assignment_row_2

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)

        enqueued: list[dict] = []

        async def _fake_enqueue(*args: object, **kwargs: object):
            enqueued.append(kwargs)
            return MagicMock()

        monkeypatch.setattr(admin_repo, "enqueue", _fake_enqueue)

        result = await admin_repo.create_admin_usuario(
            session,
            actor_uuid=_actor_uuid(),
            nombre="Ana",
            apellido="Pérez",
            cedula="1234567",
            email="ana@parkos.local",
            password="Pass1234word",
            rol="operador",
            sucursales_asignadas=[
                _sucursal_uuid(),
                uuid_lib.UUID("00000000-0000-0000-0000-0000000000b2"),
            ],
        )

        assert result is user_row
        assert call_log.count("Usuarios") == 1
        assert call_log.count("UsuariosSucursal") == 2
        assert len(enqueued) == 2
        for eq in enqueued:
            assert eq["operacion"] == "insert"
            assert eq["tabla"] == "usuarios_sucursal"
            assert eq["uuid_sucursal"] in (
                _sucursal_uuid(),
                uuid_lib.UUID("00000000-0000-0000-0000-0000000000b2"),
            )

    async def test_with_no_branches_writes_user_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()
        user_row = MagicMock()
        user_row.uuid = uuid_lib.uuid4()
        user_row.email = "solo@parkos.local"
        user_row.password_hash = "$2b$12$" + "x" * 53
        user_row.rol = "admin"

        # First SELECT is the email-uniqueness pre-check -- must report
        # "no existing active user" (see the sibling test above for why).
        call_count = {"n": 0}

        async def _execute_scalar(stmt: object, *a: object, **kw: object):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one.return_value = user_row
                result.scalar_one_or_none.return_value = user_row
            return result

        session.execute.side_effect = _execute_scalar

        call_log: list[str] = []

        async def _fake_close_and_insert(*args: object, **kwargs: object):
            model_cls = kwargs.get("model_cls") or args[1]
            call_log.append(model_cls.__name__)
            return user_row

        async def _fake_enqueue(*args: object, **kwargs: object):
            raise AssertionError("no enqueue expected when no branches")

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)
        monkeypatch.setattr(admin_repo, "enqueue", _fake_enqueue)

        await admin_repo.create_admin_usuario(
            session,
            actor_uuid=_actor_uuid(),
            nombre=None,
            apellido=None,
            cedula=None,
            email="solo@parkos.local",
            password="Pass1234word",
            rol="admin",
            sucursales_asignadas=[],
        )
        assert call_log == ["Usuarios"]

    async def test_raises_email_ya_registrado_on_duplicate_precheck(self) -> None:
        """INP-001 (Alto): the SELECT-then-INSERT pre-check must still
        reject a duplicate email on the common (non-concurrent) path."""
        session = AsyncMock()

        async def _execute_scalar(stmt: object, *a: object, **kw: object):
            result = MagicMock()
            # An active user already holds this email.
            result.scalar_one_or_none.return_value = uuid_lib.uuid4()
            return result

        session.execute.side_effect = _execute_scalar

        with pytest.raises(admin_repo.EmailYaRegistradoError):
            await admin_repo.create_admin_usuario(
                session,
                actor_uuid=_actor_uuid(),
                nombre=None,
                apellido=None,
                cedula=None,
                email="dup@parkos.local",
                password="Pass1234word",
                rol="operador",
                sucursales_asignadas=[],
            )

    async def test_raises_email_ya_registrado_on_integrity_error_race(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """INP-001 (Alto) race-condition backstop: two concurrent creates
        both pass the SELECT pre-check (neither has committed yet); the
        loser must surface the partial-unique-index violation
        (``IntegrityError`` wrapping asyncpg's ``UniqueViolationError``)
        as ``EmailYaRegistradoError``, not a raw 500."""
        session = AsyncMock()
        session.rollback = AsyncMock()

        async def _execute_scalar(stmt: object, *a: object, **kw: object):
            result = MagicMock()
            # Pre-check reports "no active row" -- the race: the other
            # concurrent request hasn't committed yet.
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = _execute_scalar

        async def _fake_close_and_insert(*args: object, **kwargs: object):
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError(
                "INSERT INTO prod.usuarios ...",
                {},
                Exception(
                    'duplicate key value violates unique constraint '
                    '"usuarios_email_uk01"'
                ),
            )

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)

        with pytest.raises(admin_repo.EmailYaRegistradoError):
            await admin_repo.create_admin_usuario(
                session,
                actor_uuid=_actor_uuid(),
                nombre=None,
                apellido=None,
                cedula=None,
                email="race@parkos.local",
                password="Pass1234word",
                rol="operador",
                sucursales_asignadas=[],
            )
        session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_admin_usuario
# ---------------------------------------------------------------------------


class TestUpdateAdminUsuario:
    @staticmethod
    def _current_row(*, uuid: uuid_lib.UUID, email: str | None) -> MagicMock:
        row = MagicMock()
        row.uuid = uuid
        row.email = email
        return row

    async def test_returns_none_when_no_open_row(self) -> None:
        session = AsyncMock()

        async def _execute(stmt: object, *a: object, **kw: object):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = _execute

        result = await admin_repo.update_admin_usuario(
            session,
            actor_uuid=_actor_uuid(),
            usuario_uuid=uuid_lib.uuid4(),
            nombre=None,
            apellido=None,
            cedula=None,
            email=None,
            rol=None,
        )
        assert result is None

    async def test_does_not_raise_when_email_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resubmitting the user's own current email (e.g. an edit form
        that re-sends every field) must NOT self-conflict with the
        uniqueness guard."""
        user_uuid = uuid_lib.uuid4()
        current = self._current_row(uuid=user_uuid, email="same@parkos.local")
        session = AsyncMock()

        async def _execute(stmt: object, *a: object, **kw: object):
            result = MagicMock()
            result.scalar_one_or_none.return_value = current
            return result

        session.execute.side_effect = _execute

        new_row = MagicMock()

        async def _fake_close_and_insert(*a: object, **kw: object):
            return new_row

        async def _fake_enqueue(*a: object, **kw: object):
            return MagicMock()

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)
        monkeypatch.setattr(admin_repo, "enqueue", _fake_enqueue)

        result = await admin_repo.update_admin_usuario(
            session,
            actor_uuid=_actor_uuid(),
            usuario_uuid=user_uuid,
            nombre="Nuevo Nombre",
            apellido=None,
            cedula=None,
            email="same@parkos.local",
            rol=None,
        )
        assert result is new_row
        # Only the initial SELECT for the open row -- the email pre-check
        # must be skipped entirely because ``email == current.email``.
        assert session.execute.await_count == 1

    async def test_raises_email_ya_registrado_on_duplicate_precheck(self) -> None:
        user_uuid = uuid_lib.uuid4()
        current = self._current_row(uuid=user_uuid, email="old@parkos.local")
        session = AsyncMock()
        call_count = {"n": 0}

        async def _execute(stmt: object, *a: object, **kw: object):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = current
            else:
                # Another ACTIVE user already holds the new email.
                result.scalar_one_or_none.return_value = uuid_lib.uuid4()
            return result

        session.execute.side_effect = _execute

        with pytest.raises(admin_repo.EmailYaRegistradoError):
            await admin_repo.update_admin_usuario(
                session,
                actor_uuid=_actor_uuid(),
                usuario_uuid=user_uuid,
                nombre=None,
                apellido=None,
                cedula=None,
                email="taken@parkos.local",
                rol=None,
            )

    async def test_raises_email_ya_registrado_on_integrity_error_race(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """INP-001 (Alto): editing a user's email had NO guard at all
        before this fix -- neither a pre-check nor an IntegrityError
        backstop. Both must now be in place."""
        user_uuid = uuid_lib.uuid4()
        current = self._current_row(uuid=user_uuid, email="old@parkos.local")
        session = AsyncMock()
        session.rollback = AsyncMock()
        call_count = {"n": 0}

        async def _execute(stmt: object, *a: object, **kw: object):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = current
            else:
                # Pre-check passes -- race: concurrent writer not
                # committed yet.
                result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = _execute

        async def _fake_close_and_insert(*a: object, **kw: object):
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError(
                "UPDATE prod.usuarios ...",
                {},
                Exception(
                    'duplicate key value violates unique constraint '
                    '"usuarios_email_uk01"'
                ),
            )

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)

        with pytest.raises(admin_repo.EmailYaRegistradoError):
            await admin_repo.update_admin_usuario(
                session,
                actor_uuid=_actor_uuid(),
                usuario_uuid=user_uuid,
                nombre=None,
                apellido=None,
                cedula=None,
                email="race@parkos.local",
                rol=None,
            )
        session.rollback.assert_awaited_once()

    async def test_updates_fields_and_enqueues_patch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_uuid = uuid_lib.uuid4()
        current = self._current_row(uuid=user_uuid, email="old@parkos.local")
        session = AsyncMock()
        call_count = {"n": 0}

        async def _execute(stmt: object, *a: object, **kw: object):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalar_one_or_none.return_value = current
            else:
                result.scalar_one_or_none.return_value = None  # no dup
            return result

        session.execute.side_effect = _execute

        new_row = MagicMock()
        new_row.uuid = uuid_lib.uuid4()

        captured_overrides: dict[str, object] = {}

        async def _fake_close_and_insert(*args: object, **kwargs: object):
            captured_overrides.update(kwargs.get("new_attrs", {}))
            return new_row

        enqueued: list[dict] = []

        async def _fake_enqueue(*args: object, **kwargs: object):
            enqueued.append(kwargs)
            return MagicMock()

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)
        monkeypatch.setattr(admin_repo, "enqueue", _fake_enqueue)

        result = await admin_repo.update_admin_usuario(
            session,
            actor_uuid=_actor_uuid(),
            usuario_uuid=user_uuid,
            nombre="Nuevo",
            apellido=None,
            cedula=None,
            email="new@parkos.local",
            rol=None,
        )

        assert result is new_row
        assert captured_overrides == {"nombre": "Nuevo", "email": "new@parkos.local"}
        assert len(enqueued) == 1
        assert enqueued[0]["operacion"] == "update"
        assert enqueued[0]["tabla"] == "usuarios"


# ---------------------------------------------------------------------------
# asignar_sucursal
# ---------------------------------------------------------------------------


class TestAsignarSucursal:
    async def test_raises_on_duplicate_open_assignment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()
        existing = MagicMock()
        existing.uuid_sucursal = _sucursal_uuid()

        async def _fake_list(*a: object, **kw: object) -> list:
            return [existing]

        monkeypatch.setattr(admin_repo, "list_active_asignaciones_usuario", _fake_list)
        with pytest.raises(UsuarioYaAsignadoError):
            await admin_repo.asignar_sucursal(
                session,
                actor_uuid=_actor_uuid(),
                usuario_uuid=uuid_lib.uuid4(),
                sucursal_uuid=_sucursal_uuid(),
            )

    async def test_inserts_new_assignment_when_no_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = AsyncMock()
        session.flush = AsyncMock()
        new_row = MagicMock()
        new_row.uuid = uuid_lib.uuid4()

        async def _fake_list(*a: object, **kw: object) -> list:
            return []

        async def _fake_close_and_insert(*a: object, **kw: object):
            return new_row

        async def _fake_enqueue(*a: object, **kw: object):
            return MagicMock()

        monkeypatch.setattr(admin_repo, "list_active_asignaciones_usuario", _fake_list)
        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)
        monkeypatch.setattr(admin_repo, "enqueue", _fake_enqueue)

        result = await admin_repo.asignar_sucursal(
            session,
            actor_uuid=_actor_uuid(),
            usuario_uuid=uuid_lib.uuid4(),
            sucursal_uuid=_sucursal_uuid(),
        )
        assert result is new_row
        session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# list_branch_assignments_for_users
# ---------------------------------------------------------------------------


class TestListBranchAssignmentsForUsers:
    async def test_empty_user_list_short_circuits_to_empty_dict(self) -> None:
        session = AsyncMock()

        async def _execute(stmt: object, *a: object, **kw: object):
            raise AssertionError(
                "session.execute must not be called when user_uuids is empty"
            )

        session.execute.side_effect = _execute

        result = await admin_repo.list_branch_assignments_for_users(
            session, user_uuids=[]
        )
        assert result == {}

    async def test_no_assignments_returns_empty_lists_per_user(self) -> None:
        session = AsyncMock()
        user_a = uuid_lib.uuid4()
        user_b = uuid_lib.uuid4()

        async def _execute(stmt: object, *a: object, **kw: object):
            mock_result = MagicMock()
            mock_result.all = MagicMock(return_value=[])
            return mock_result

        session.execute.side_effect = _execute

        result = await admin_repo.list_branch_assignments_for_users(
            session, user_uuids=[user_a, user_b]
        )
        assert set(result.keys()) == {user_a, user_b}
        assert result[user_a] == []
        assert result[user_b] == []

    async def test_stitches_assignments_with_open_branch_snapshot(self) -> None:
        session = AsyncMock()
        user_a = uuid_lib.uuid4()
        user_b = uuid_lib.uuid4()
        branch_p = uuid_lib.uuid4()
        branch_q = uuid_lib.uuid4()
        from datetime import UTC, datetime

        ts = datetime.now(UTC).replace(tzinfo=None)

        # First execute: SELECT usuarios_sucursal rows.
        # Second execute: SELECT sucursal rows.
        call_count = {"n": 0}

        async def _execute(stmt: object, *a: object, **kw: object):
            call_count["n"] += 1
            mock_result = MagicMock()
            if call_count["n"] == 1:
                mock_result.all = MagicMock(
                    return_value=[
                        (uuid_lib.uuid4(), user_a, branch_p, ts),
                        (uuid_lib.uuid4(), user_b, branch_q, ts),
                    ]
                )
            else:
                mock_result.all = MagicMock(
                    return_value=[
                        (branch_p, "Sucursal P", "P"),
                        (branch_q, None, None),  # closed branch: still appears
                    ]
                )
            return mock_result

        session.execute.side_effect = _execute

        result = await admin_repo.list_branch_assignments_for_users(
            session, user_uuids=[user_a, user_b]
        )
        assert call_count["n"] == 2
        assert len(result[user_a]) == 1
        assert result[user_a][0].uuid_sucursal == branch_p
        assert result[user_a][0].nombre == "Sucursal P"
        assert result[user_a][0].prefijo_nombre == "P"
        assert result[user_a][0].vigente_desde == ts
        # Closed-branch assignment: row still appears with None name fields.
        assert len(result[user_b]) == 1
        assert result[user_b][0].uuid_sucursal == branch_q
        assert result[user_b][0].nombre is None
        assert result[user_b][0].prefijo_nombre is None


# ---------------------------------------------------------------------------
# desasignar_sucursal
# ---------------------------------------------------------------------------


class TestDesasignarSucursal:
    async def test_no_op_when_no_open_assignment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = AsyncMock()

        async def _execute(stmt: object, *a: object, **kw: object):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=None)
            return mock_result

        session.execute.side_effect = _execute

        async def _fake_close_and_insert(*a: object, **kw: object):
            raise AssertionError("close_and_insert should not be called when no open row")

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)
        # Reaching here without an exception is the assertion.
        await admin_repo.desasignar_sucursal(
            session,
            actor_uuid=_actor_uuid(),
            usuario_uuid=uuid_lib.uuid4(),
            sucursal_uuid=_sucursal_uuid(),
        )

    async def test_closes_when_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = AsyncMock()
        open_row = MagicMock()
        open_row.uuid = uuid_lib.uuid4()
        open_row.uuid_usuario = uuid_lib.uuid4()
        open_row.uuid_sucursal = _sucursal_uuid()

        async def _execute(stmt: object, *a: object, **kw: object):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=open_row)
            return mock_result

        session.execute.side_effect = _execute

        update_calls: list = []

        async def _fake_execute_for_update(stmt: object, *a: object, **kw: object) -> MagicMock:
            update_calls.append(stmt)
            return MagicMock()

        # Track the second ``session.execute`` call separately so the
        # update statement is captured (the first execute is the SELECT
        # for the open row).
        call_count = {"n": 0}

        async def _execute_router(stmt: object, *a: object, **kw: object):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First execute: SELECT for the open row.
                mock_result = MagicMock()
                mock_result.scalar_one_or_none = MagicMock(return_value=open_row)
                return mock_result
            update_calls.append(stmt)
            return MagicMock()

        session.execute.side_effect = _execute_router

        # ``close_and_insert`` MUST NOT be called on a deassignment -- the
        # helper does an in-place UPDATE on the open row instead.
        async def _fake_close_and_insert(*a: object, **kw: object):
            raise AssertionError("close_and_insert should not be called for a deassignment")

        monkeypatch.setattr(admin_repo, "close_and_insert", _fake_close_and_insert)

        await admin_repo.desasignar_sucursal(
            session,
            actor_uuid=_actor_uuid(),
            usuario_uuid=uuid_lib.uuid4(),
            sucursal_uuid=_sucursal_uuid(),
        )

        # Two ``session.execute`` calls: SELECT + UPDATE.
        assert call_count["n"] == 2
        assert len(update_calls) == 1
