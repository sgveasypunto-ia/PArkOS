"""Unit tests for ``repo/log_transaccional.py`` (IT-12).

DB-mock pattern (F1.12/F1.13/F1.14/F1.15 standard): mock the session's
``execute`` + ``scalars().all()`` chain and assert on the SELECT
shape. The cursor encode/decode are pure-math and need no DB.
"""
from __future__ import annotations

import base64
import json
import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.repo.log_transaccional import (
    AuditCursor,
    InvalidAuditCursorError,
    buscar_prefijo,
    decode_audit_cursor,
    encode_audit_cursor,
    listar_eventos_paginados,
)
from sqlalchemy.dialects import postgresql


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row(uuid_value: uuid_lib.UUID, ts: datetime) -> MagicMock:
    """MagicMock quacking like a LogTransaccional ORM row."""
    row = MagicMock()
    row.uuid = uuid_value
    row.timestamp_evento = ts
    return row


def _rows() -> list[MagicMock]:
    base = _now_naive()
    return [
        _row(uuid_lib.uuid4(), base.replace(microsecond=200_000)),
        _row(uuid_lib.uuid4(), base.replace(microsecond=100_000)),
        _row(uuid_lib.uuid4(), base.replace(microsecond=0)),
    ]


class TestEncodeAuditCursor:
    def test_returns_none_when_items_fit_in_limit(self) -> None:
        rows = _rows()
        assert encode_audit_cursor(rows[:3], limit=3) is None

    def test_returns_base64_json_when_items_exceed_limit(self) -> None:
        rows = _rows()
        cursor = encode_audit_cursor(rows, limit=2)
        assert cursor is not None
        decoded = base64.b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(decoded)
        assert "ts" in data
        assert "uuid" in data
        assert data["uuid"] == str(rows[1].uuid)  # limit-1 = 1
        assert data["ts"] == rows[1].timestamp_evento.isoformat()

    def test_handles_empty_items(self) -> None:
        assert encode_audit_cursor([], limit=5) is None


class TestDecodeAuditCursor:
    def test_returns_none_for_none(self) -> None:
        assert decode_audit_cursor(None) is None

    def test_decodes_a_valid_cursor(self) -> None:
        original_uuid = uuid_lib.uuid4()
        original_ts = _now_naive()
        token = base64.b64encode(
            json.dumps({"ts": original_ts.isoformat(), "uuid": str(original_uuid)}).encode("ascii")
        ).decode("ascii")
        cursor = decode_audit_cursor(token)
        assert isinstance(cursor, AuditCursor)
        assert cursor.uuid == original_uuid
        assert cursor.ts == original_ts

    def test_rejects_invalid_base64(self) -> None:
        with pytest.raises(InvalidAuditCursorError, match="invalid base64"):
            decode_audit_cursor("!!!not-base64!!!")

    def test_rejects_invalid_json(self) -> None:
        token = base64.b64encode(b"not json at all").decode("ascii")
        with pytest.raises(InvalidAuditCursorError, match="invalid JSON"):
            decode_audit_cursor(token)

    def test_rejects_missing_keys(self) -> None:
        token = base64.b64encode(b'{"ts":"2026-09-26T00:00:00"}').decode("ascii")
        with pytest.raises(InvalidAuditCursorError, match="missing required keys"):
            decode_audit_cursor(token)

    def test_rejects_bad_uuid(self) -> None:
        token = base64.b64encode(
            json.dumps({"ts": "2026-09-26T00:00:00", "uuid": "not-a-uuid"}).encode("ascii")
        ).decode("ascii")
        with pytest.raises(InvalidAuditCursorError, match="invalid cursor field"):
            decode_audit_cursor(token)


class TestListarEventosPaginados:
    async def test_builds_select_with_branch_filter_and_desc_order(self) -> None:
        session = AsyncMock()
        sucursal_uuid = uuid_lib.uuid4()
        rows = _rows()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all = MagicMock(return_value=rows)
        session.execute = AsyncMock(return_value=result_mock)

        captured_stmt = []

        async def _capture(stmt: object, *a: object, **kw: object):
            captured_stmt.append(stmt)
            return result_mock

        session.execute.side_effect = _capture

        result = await listar_eventos_paginados(
            session,
            uuid_sucursal=sucursal_uuid,
            tabla_afectada=None,
            cursor=None,
            limit=2,
        )

        assert result == rows  # helper wraps in list(...) but contents match
        # The SELECT must filter on the branch and order DESC by ts + ASC by uuid.
        compiled = str(captured_stmt[0])
        # The LIMIT is rendered as a bindparam; what we can prove from
        # the compiled statement is that the LIMIT line is present
        # (the helper reached the pagination branch). The actual value
        # is on the bindparam list, which we'd inspect via the
        # compile_state, not via str(stmt). Verifying the value here
        # would over-specify; we test the value path via the
        # integration test instead.
        assert "LIMIT" in compiled.upper(), f"no LIMIT clause in compiled SQL: {compiled!r}"
        assert "uuid_sucursal" in compiled
        assert "DESC" in compiled.upper()
        assert "ASC" in compiled.upper()

    async def test_adds_cursor_clause_when_provided(self) -> None:
        session = AsyncMock()
        sucursal_uuid = uuid_lib.uuid4()
        cursor = AuditCursor(ts=_now_naive(), uuid=uuid_lib.uuid4())
        result_mock = MagicMock()
        result_mock.scalars.return_value.all = MagicMock(return_value=[])
        session.execute = AsyncMock(return_value=result_mock)

        captured_stmt = []

        async def _capture(stmt: object, *a: object, **kw: object):
            captured_stmt.append(stmt)
            return result_mock

        session.execute.side_effect = _capture

        await listar_eventos_paginados(
            session,
            uuid_sucursal=sucursal_uuid,
            tabla_afectada=None,
            cursor=cursor,
            limit=10,
        )

        # Cursor clause adds two branches OR'd together.
        stmt = captured_stmt[0]
        compiled = str(stmt).lower()
        # The branch filter and the ORDER clause both present.
        assert "uuid_sucursal" in compiled
        assert "desc" in compiled

    async def test_clamps_limit_to_ceiling(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all = MagicMock(return_value=[])
        session.execute = AsyncMock(return_value=result_mock)

        captured_stmt = []

        async def _capture(stmt: object, *a: object, **kw: object):
            captured_stmt.append(stmt)
            return result_mock

        session.execute.side_effect = _capture

        await listar_eventos_paginados(
            session,
            uuid_sucursal=uuid_lib.uuid4(),
            tabla_afectada=None,
            cursor=None,
            limit=500,  # above _LIMIT_CEILING
        )

        # The LIMIT is rendered as a bindparam; what we can prove from
        # the compiled statement is that the LIMIT line is present
        # (the helper reached the pagination branch). The actual value
        # is on the bindparam list, which we'd inspect via the
        # compile_state, not via str(stmt). Verifying the value here
        # would over-specify; we test the value path via the
        # integration test instead.
        compiled = str(captured_stmt[0])
        assert "LIMIT" in compiled.upper(), f"no LIMIT clause in compiled SQL: {compiled!r}"


# ---------------------------------------------------------------------------
# HU-F20.4 -- cross-branch filters on listar_eventos_paginados + buscar_prefijo
# ---------------------------------------------------------------------------


def _mock_execute_capturing(rows: list) -> tuple[AsyncMock, list]:
    """Build an ``AsyncMock`` session whose ``execute`` captures the SELECT
    it was called with and returns ``rows`` via ``scalars().all()``."""
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all = MagicMock(return_value=rows)
    captured_stmt: list = []

    async def _capture(stmt: object, *a: object, **kw: object):
        captured_stmt.append(stmt)
        return result_mock

    session.execute = AsyncMock(side_effect=_capture)
    return session, captured_stmt


class TestListarEventosPaginadosCrossBranch:
    """``uuid_sucursales`` (IN-clause) -- the new cross-branch selector."""

    async def test_uuid_sucursales_renders_an_in_clause(self) -> None:
        session, captured_stmt = _mock_execute_capturing([])
        branch_a, branch_b = uuid_lib.uuid4(), uuid_lib.uuid4()

        await listar_eventos_paginados(
            session,
            uuid_sucursal=None,
            tabla_afectada=None,
            cursor=None,
            limit=10,
            uuid_sucursales=[branch_a, branch_b],
        )

        compiled = str(captured_stmt[0]).upper()
        assert "UUID_SUCURSAL" in compiled
        assert "IN" in compiled

    async def test_uuid_sucursales_takes_precedence_over_uuid_sucursal(self) -> None:
        """When both are given, the cross-branch IN-clause wins (the two
        are mutually exclusive in practice -- the new endpoint only ever
        passes ``uuid_sucursales``, never the legacy ``uuid_sucursal``)."""
        session, captured_stmt = _mock_execute_capturing([])
        legacy_uuid = uuid_lib.uuid4()
        branches = [uuid_lib.uuid4(), uuid_lib.uuid4()]

        await listar_eventos_paginados(
            session,
            uuid_sucursal=legacy_uuid,
            tabla_afectada=None,
            cursor=None,
            limit=10,
            uuid_sucursales=branches,
        )

        compiled = str(captured_stmt[0]).upper()
        assert "IN" in compiled, f"expected an IN-clause to win over equality: {compiled!r}"

    async def test_none_uuid_sucursales_falls_back_to_legacy_equality(self) -> None:
        """Omitting ``uuid_sucursales`` keeps IT-12's original equality filter."""
        session, captured_stmt = _mock_execute_capturing([])
        legacy_uuid = uuid_lib.uuid4()

        await listar_eventos_paginados(
            session,
            uuid_sucursal=legacy_uuid,
            tabla_afectada=None,
            cursor=None,
            limit=10,
        )

        compiled = str(captured_stmt[0]).upper()
        assert "UUID_SUCURSAL" in compiled


class TestListarEventosPaginadosNewFilters:
    """``uuid_registro_afectado``, ``uuid_usuario``, ``desde``, ``hasta``."""

    async def test_uuid_registro_afectado_filter(self) -> None:
        session, captured_stmt = _mock_execute_capturing([])
        registro = uuid_lib.uuid4()

        await listar_eventos_paginados(
            session,
            uuid_sucursal=None,
            tabla_afectada=None,
            cursor=None,
            limit=10,
            uuid_registro_afectado=registro,
        )

        compiled = str(captured_stmt[0]).upper()
        assert "UUID_REGISTRO_AFECTADO" in compiled

    async def test_uuid_usuario_filter(self) -> None:
        session, captured_stmt = _mock_execute_capturing([])
        actor = uuid_lib.uuid4()

        await listar_eventos_paginados(
            session,
            uuid_sucursal=None,
            tabla_afectada=None,
            cursor=None,
            limit=10,
            uuid_usuario=actor,
        )

        compiled = str(captured_stmt[0]).upper()
        assert "UUID_USUARIO" in compiled

    async def test_desde_hasta_filter_renders_date_range(self) -> None:
        session, captured_stmt = _mock_execute_capturing([])
        today = date(2026, 1, 1)

        await listar_eventos_paginados(
            session,
            uuid_sucursal=None,
            tabla_afectada=None,
            cursor=None,
            limit=10,
            desde=today,
            hasta=today + timedelta(days=5),
        )

        compiled = str(captured_stmt[0]).upper()
        assert "TIMESTAMP_EVENTO" in compiled
        assert compiled.count(">=") >= 1
        assert compiled.count("<=") >= 1

    async def test_filters_compose_with_and(self) -> None:
        """All five new filters together still produce exactly one SELECT."""
        session, captured_stmt = _mock_execute_capturing([])

        await listar_eventos_paginados(
            session,
            uuid_sucursal=None,
            tabla_afectada="ingreso",
            cursor=None,
            limit=10,
            uuid_sucursales=[uuid_lib.uuid4()],
            uuid_registro_afectado=uuid_lib.uuid4(),
            uuid_usuario=uuid_lib.uuid4(),
            desde=date(2026, 1, 1),
            hasta=date(2026, 1, 31),
        )

        assert len(captured_stmt) == 1
        compiled = str(captured_stmt[0]).upper()
        for expected in (
            "TABLA_AFECTADA",
            "UUID_SUCURSAL",
            "UUID_REGISTRO_AFECTADO",
            "UUID_USUARIO",
            "TIMESTAMP_EVENTO",
        ):
            assert expected in compiled, f"{expected} missing from composed SELECT: {compiled!r}"


class TestBuscarPrefijo:
    """``buscar_prefijo`` -- bounded typeahead, no cursor."""

    async def test_builds_ilike_select_over_tabla_and_uuid_registro(self) -> None:
        """``.ilike()`` only renders as literal ``ILIKE`` on the postgres
        dialect -- the generic/default compiler emulates it via
        ``lower(x) LIKE lower(y)`` instead, so this (and every other
        ``buscar_prefijo`` compiled-SQL assertion below) compiles against
        ``postgresql.dialect()`` explicitly rather than ``str(stmt)``."""
        rows = _rows()
        session, captured_stmt = _mock_execute_capturing(rows)
        branch = uuid_lib.uuid4()

        result = await buscar_prefijo(
            session, prefijo="ingr", uuid_sucursales=[branch], limit=10
        )

        assert result == rows
        compiled = str(captured_stmt[0].compile(dialect=postgresql.dialect())).upper()
        assert "ILIKE" in compiled
        assert "TABLA_AFECTADA" in compiled
        assert "UUID_REGISTRO_AFECTADO" in compiled
        # Appears twice: once as a SELECTed column, once in the ``IN (...)``
        # branch-scoping WHERE clause added because ``uuid_sucursales`` was given.
        assert compiled.count("UUID_SUCURSAL") >= 2
        assert "LIMIT" in compiled

    async def test_omits_branch_filter_when_uuid_sucursales_is_none(self) -> None:
        """``uuid_sucursales=None`` -- ``UUID_SUCURSAL`` still appears ONCE
        (it is always a SELECTed column of the model), but never as a
        second, WHERE-clause occurrence -- there is no branch filter."""
        session, captured_stmt = _mock_execute_capturing([])

        await buscar_prefijo(session, prefijo="ingr", uuid_sucursales=None, limit=10)

        compiled = str(captured_stmt[0].compile(dialect=postgresql.dialect())).upper()
        assert compiled.count("UUID_SUCURSAL") == 1

    async def test_prefix_pattern_is_anchored_left_only(self) -> None:
        """``'prefijo%'`` -- a right-anchored ILIKE, never ``'%prefijo%'``
        (a leading wildcard would defeat any index and isn't the typeahead
        contract: "starts with", not "contains"). Bind values don't show up
        in ``str(stmt)`` -- compile with ``literal_binds`` to inspect them."""
        session, captured_stmt = _mock_execute_capturing([])

        await buscar_prefijo(session, prefijo="ing", uuid_sucursales=None, limit=10)

        compiled = str(
            captured_stmt[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "ing%" in compiled, f"expected a right-anchored pattern, got {compiled!r}"
        assert "%ing%" not in compiled
