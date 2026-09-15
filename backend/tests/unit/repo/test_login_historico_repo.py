"""HU-F1.15 / T2.1..T2.4 -- ``repo/login_historico.py`` unit tests.

Pure unit tests: AsyncMock for ``listar_intentos_paginado`` (no real DB
roundtrip), pure base64 math for ``encode_next_cursor`` +
``decode_cursor_or_none``. The handler-level integration tests live in
``tests/unit/api/v1/test_usuarios_login_handler.py`` (gated by
``PARKOS_DOCKER_TEST=1``).

KD-LOGIN-01 SELECT-only invariant is asserted via AST walk
``tests/static/test_login_historico_read_only.py`` -- these unit tests
verify the SHAPE (signature + commit-free contract + tenant filter
+ cursor helpers).
"""
from __future__ import annotations

import importlib
import sys
import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# ---------------------------------------------------------------------------
# T2.1 -- module import + helper signatures
# ---------------------------------------------------------------------------


def test_repo_login_historico_module_imports_with_helpers() -> None:
    """T2.1 RED/GREEN: module imports + 3 helpers exposed via ``__all__``.

    Mirrors F1.14 ``test_repo_sync_estado_module_imports``. Pre-
    implementation this raises ``ModuleNotFoundError`` -- that is the
    RED state.
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    for name in ("listar_intentos_paginado", "encode_next_cursor", "decode_cursor_or_none"):
        assert name in mod.__all__, f"helper {name!r} not exposed via __all__"
        assert callable(getattr(mod, name)), f"helper {name!r} is not callable"


# ---------------------------------------------------------------------------
# T2.3 -- listar_intentos_paginado (SELECT-only, tenant filter, cursor)
# ---------------------------------------------------------------------------


def _make_login_row(
    *,
    uuid: uuid_lib.UUID,
    ts,
    estado: str,
    uuid_sucursal: uuid_lib.UUID | None,
) -> MagicMock:
    """Build a Login-like ORM row for assertions."""
    row = MagicMock()
    row.uuid = uuid
    row.timestamp_evento = ts
    row.timestamp_cierre = None
    row.estado = estado
    row.uuid_sucursal = uuid_sucursal
    return row


def _empty_session() -> AsyncMock:
    """Build an AsyncMock session whose execute() resolves to an empty result set."""
    empty_inner = MagicMock(return_value=[])
    empty_scalars = MagicMock(return_value=MagicMock(all=empty_inner))
    empty_result = MagicMock(scalars=empty_scalars)
    session = AsyncMock()
    session.execute.return_value = empty_result
    return session


@pytest.mark.asyncio
async def test_listar_intentos_paginado_select_only_returns_rows() -> None:
    """T2.3: ``session.execute`` is called exactly once with a SELECT (KD-LOGIN-01).

    DEC-LOGIN-08: empty ``prod.login`` for the user returns ``[]``
    (anti-enumeration empty-user contract).
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    session = _empty_session()
    ctx = MagicMock(issuer_prefix="operador-", sucursal_uuid=uuid_lib.uuid4())

    rows = await mod.listar_intentos_paginado(
        session,
        uuid_usuario=uuid_lib.uuid4(),
        cursor=None,
        limit=10,
        tenant_ctx=ctx,
    )

    assert rows == [], "empty result must return [] (DEC-LOGIN-08)"
    assert session.execute.await_count == 1, (
        "listar_intentos_paginado must call session.execute exactly once (KD-LOGIN-01)"
    )
    # KD-LOGIN-01: NO commit. AsyncMock would raise on .commit if called.
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_listar_intentos_paginado_layer2_filter_operador() -> None:
    """T2.3: operador issuer adds ``login.uuid_sucursal = ctx.sucursal_uuid`` SQL filter.

    DEC-LOGIN-03.A -- operador own-branch only. The filter is applied
    at SQL layer (NOT post-filter in Python) so cross-branch data
    never enters the result set.
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    session = _empty_session()
    ctx = MagicMock(issuer_prefix="operador-", sucursal_uuid=uuid_lib.uuid4())

    await mod.listar_intentos_paginado(
        session,
        uuid_usuario=uuid_lib.uuid4(),
        cursor=None,
        limit=10,
        tenant_ctx=ctx,
    )

    # Verify the WHERE clause carries the Layer 2 filter on
    # ``Login.uuid_sucursal == ctx.sucursal_uuid``.
    stmt = session.execute.await_args.args[0]
    compiled_sql = str(stmt.compile())
    assert "login.uuid_sucursal" in compiled_sql, (
        f"operador Layer 2 filter MUST appear in compiled SQL; got {compiled_sql!r}"
    )


@pytest.mark.asyncio
async def test_listar_intentos_paginado_layer2_bypass_admin() -> None:
    """T2.3: admin issuer SKIPS the Layer 2 filter (cross-branch audit).

    DEC-LOGIN-03.A -- admin bypasses. No ``login.uuid_sucursal``
    predicate on the SELECT for admin- issuer.
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    session = _empty_session()
    ctx = MagicMock(issuer_prefix="admin-", sucursal_uuid=uuid_lib.uuid4())

    await mod.listar_intentos_paginado(
        session,
        uuid_usuario=uuid_lib.uuid4(),
        cursor=None,
        limit=10,
        tenant_ctx=ctx,
    )

    stmt = session.execute.await_args.args[0]
    compiled_sql = str(stmt.compile())
    # admin bypass: NO predicate on uuid_sucursal in the WHERE.
    # The base WHERE on uuid_usuario MUST still be present (so the
    # user-scoped filter remains); but no extra uuid_sucursal
    # predicate is added for admin-.
    assert "uuid_usuario = :uuid_usuario_1" in compiled_sql, (
        f"the base WHERE on uuid_usuario must still be present; got {compiled_sql!r}"
    )
    # Admin MUST NOT add a uuid_sucursal filter -- only the operador path adds it.
    # The compiled SQL may still reference uuid_sucursal in the SELECT list,
    # so we check that it is NOT a WHERE predicate by absence of the comparison.
    assert "uuid_sucursal = " not in compiled_sql, (
        f"admin bypass MUST NOT add uuid_sucursal = predicate; got {compiled_sql!r}"
    )


@pytest.mark.asyncio
async def test_listar_intentos_paginado_no_commit_anywhere() -> None:
    """T2.3: NO ``session.commit()`` anywhere (KD-LOGIN-01 SELECT-only).

    Belt-and-suspenders: AsyncMock's ``commit`` is auto-magically
    tracked; we assert it was never awaited.
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    session = _empty_session()
    ctx = MagicMock(issuer_prefix="operador-", sucursal_uuid=uuid_lib.uuid4())

    await mod.listar_intentos_paginado(
        session,
        uuid_usuario=uuid_lib.uuid4(),
        cursor=None,
        limit=10,
        tenant_ctx=ctx,
    )

    session.commit.assert_not_called()
    session.rollback.assert_not_called()


# ---------------------------------------------------------------------------
# T2.3 -- encode_next_cursor (pure math)
# ---------------------------------------------------------------------------


def test_encode_next_cursor_items_fit_within_limit_returns_none() -> None:
    """T2.3: ``len(items) <= limit`` -> ``None`` (last page).

    DEC-LOGIN-04: stable cursor pagination. When the helper fetches
    ``limit + 1`` rows and gets back ``<= limit``, the page is the
    last page (no next cursor).
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    from datetime import UTC, datetime

    items = [
        _make_login_row(
            uuid=uuid_lib.uuid4(),
            ts=datetime(2026, 1, 1, 12, 0, i, tzinfo=UTC),
            estado="exitoso",
            uuid_sucursal=None,
        )
        for i in range(5)
    ]
    assert mod.encode_next_cursor(items, limit=10) is None, (
        "5 items + limit=10 must return None (last page)"
    )


def test_encode_next_cursor_more_than_limit_returns_base64() -> None:
    """T2.3: ``len(items) > limit`` -> base64 JSON cursor for the limit-th item.

    DEC-LOGIN-04: encode the last item on the page (after slicing).
    The cursor carries ``(timestamp_evento.isoformat(), str(uuid))`` of
    the ``limit``-th item (index ``limit - 1``).
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    from datetime import UTC, datetime

    items = [
        _make_login_row(
            uuid=uuid_lib.uuid4(),
            ts=datetime(2026, 1, 1, 12, 0, i, tzinfo=UTC),
            estado="exitoso",
            uuid_sucursal=None,
        )
        for i in range(11)
    ]
    cursor = mod.encode_next_cursor(items, limit=10)
    assert cursor is not None, "11 items + limit=10 must produce a non-null cursor"
    assert isinstance(cursor, str)
    # base64-decodable.
    import base64
    import json
    padded = cursor + "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    payload = json.loads(raw.decode("utf-8"))
    assert payload["uuid"] == str(items[9].uuid), (
        f"cursor must encode item[9].uuid; got {payload!r}"
    )
    assert payload.get("vigente_desde"), (
        f"cursor must carry vigente_desde ISO timestamp; got {payload!r}"
    )


def test_encode_next_cursor_pure_function_no_side_effects() -> None:
    """T2.4: ``encode_next_cursor`` is deterministic (pure math, no side effects).

    Calling twice with the same inputs yields identical outputs.
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    from datetime import UTC, datetime

    items = [
        _make_login_row(
            uuid=uuid_lib.uuid4(),
            ts=datetime(2026, 1, 1, 12, 0, i, tzinfo=UTC),
            estado="exitoso",
            uuid_sucursal=None,
        )
        for i in range(11)
    ]
    a = mod.encode_next_cursor(items, limit=10)
    b = mod.encode_next_cursor(items, limit=10)
    assert a == b, "encode_next_cursor must be deterministic (pure function)"


# ---------------------------------------------------------------------------
# T2.3 -- decode_cursor_or_none (cursor validator)
# ---------------------------------------------------------------------------


def test_decode_cursor_or_none_none_returns_none() -> None:
    """T2.3: ``decode_cursor_or_none(None)`` returns ``None`` (first page).

    Cursor is OPTIONAL. The helper never raises on ``None`` input.
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    assert mod.decode_cursor_or_none(None) is None, (
        "decode_cursor_or_none(None) must return None (cursor optional)"
    )


def test_decode_cursor_or_none_malformed_raises_cursor_invalid_error() -> None:
    """T2.3: malformed cursor raises ``InvalidCursorError`` (handler -> 400).

    DEC-LOGIN-04: a corrupted cursor must NOT silently fall through to
    the first page -- the client gets HTTP 400 with
    ``error="cursor_invalid"``.
    """
    mod = importlib.import_module("parkos_core.repo.login_historico")
    pagination = importlib.import_module("parkos_core.repo.pagination")
    with pytest.raises(pagination.InvalidCursorError):
        mod.decode_cursor_or_none("not-base64-json-{}")


def test_decode_cursor_or_none_valid_cursor_passthrough() -> None:
    """T2.3: valid cursor passes through unchanged (round-trip)."""
    mod = importlib.import_module("parkos_core.repo.login_historico")
    pagination = importlib.import_module("parkos_core.repo.pagination")
    # Build a real cursor via the encode helper -- round-trip semantics.
    test_uuid = uuid_lib.uuid4()
    encoded = pagination.encode(
        pagination.Cursor(
            vigente_desde="2026-01-01T12:00:00",
            created_at=None,
            uuid=str(test_uuid),
        )
    )
    out = mod.decode_cursor_or_none(encoded)
    assert out == encoded, "valid cursor must round-trip unchanged"
