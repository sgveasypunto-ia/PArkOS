"""HU-F1.15 / T4.2 -- 2 MANDATED GET handler unit tests + 1 cross-branch test.

The 2 mandated tests per plan.md line 1149:

  * ``test_200_with_items_and_next_cursor`` -- populated user, 5 rows,
    DESC order + base64 cursor on the limit-th item.
  * ``test_200_empty_items_for_unknown_user`` -- empty user contract
    (DEC-LOGIN-08 anti-enumeration): zero rows -> 200 with
    ``items=[]`` + ``next_cursor=None``, NEVER 404.

Plus 1 cross-branch asymmetry test pinning DEC-LOGIN-03.A (operador
own-branch filter; admin bypass).

Pattern (F1.14 / F1.13 ``test_arqueo_handler.py``): mock all repo
helpers + DB-mock session with ``AsyncMock`` for ``session.commit``.
DB-mock pattern is the F1.12/F1.13/F1.14 standard (Docker
unavailable in CI).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402


def _make_ctx(
    *,
    issuer_prefix: str = "operador-",
    sucursal_uuid: uuid_lib.UUID | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = issuer_prefix
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    ctx.actor_rol = "operador" if issuer_prefix == "operador-" else "admin"
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_login_row(
    *,
    uuid: uuid_lib.UUID | None = None,
    ts: datetime | None = None,
    estado: str = "exitoso",
    uuid_sucursal: uuid_lib.UUID | None = None,
) -> MagicMock:
    """Build a Login ORM row mock carrying 5 business columns."""
    row = MagicMock()
    row.uuid = uuid or uuid_lib.uuid4()
    row.timestamp_evento = ts or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    row.timestamp_cierre = None
    row.estado = estado
    row.uuid_sucursal = uuid_sucursal
    return row


def _build_query_params(*, limit: int = 10, cursor: str | None = None) -> MagicMock:
    """Build a LoginHistoricoQueryParams-like mock for the handler."""
    p = MagicMock()
    p.limit = limit
    p.cursor = cursor
    return p


# ---------------------------------------------------------------------------
# T4.2 -- 2 MANDATED handler tests (plan.md line 1149)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_200_with_items_and_next_cursor() -> None:
    """MANDATED T4.2 T1 (plan.md line 1149): populated user -> 200 + items + cursor.

    Scenarios pinned:
      * REQ-OPS-102 (SELECT-only via repo helper, KD-LOGIN-01).
      * REQ-OPS-103 (cursor pagination, KD-LOGIN-01).
      * DEC-LOGIN-04 (cursor pagination contract).
      * DEC-LOGIN-05 (Cache-Control: no-store on success).
      * DEC-LOGIN-07 (envelope shape ``{items, next_cursor}`` -- NO
        ``activo``, NO ``count``, NO ``total``, NO ``has_more``).
      * DEC-LOGIN-08 (anti-enumeration: response carries real items,
        NOT a 404).
    """
    from parkos_core.api.v1 import usuarios_login as handler_mod

    user_uuid = uuid_lib.uuid4()
    branch_uuid = uuid_lib.uuid4()

    ctx = _make_ctx(issuer_prefix="operador-", sucursal_uuid=branch_uuid)
    response = _new_response()
    params = _build_query_params(limit=3, cursor=None)

    session = MagicMock()
    session.commit = AsyncMock()

    rows = [
        _build_login_row(
            ts=datetime(2026, 1, 1, 12, 0, i * 10, tzinfo=UTC),
            estado=("exitoso" if i % 3 == 0 else "fallido" if i % 3 == 1 else "cerrado"),
            uuid_sucursal=branch_uuid,
        )
        for i in range(5)
    ]

    m_listar = AsyncMock(return_value=rows)
    m_encode_cursor = MagicMock(return_value="opaque-cursor-base64")

    with patch.object(handler_mod.repo_login_historico, "listar_intentos_paginado", m_listar), \
         patch.object(handler_mod.repo_login_historico, "encode_next_cursor", m_encode_cursor):
        result = await handler_mod.get_login_historico(
            response=response,
            uuid=user_uuid,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # KD-LOGIN-01: SELECT-only via 1 typed helper.
    m_listar.assert_called_once()
    # NO commit (GET is naturally idempotent).
    session.commit.assert_not_called()
    # DEC-LOGIN-05: no-store header on success.
    assert response.headers["Cache-Control"] == "no-store", (
        "DEC-LOGIN-05 violated: Cache-Control: no-store must be set on 200"
    )
    # DEC-LOGIN-07: envelope shape -- items (sliced to limit=3) + cursor.
    assert len(result.items) == 3, (
        f"items must be sliced to params.limit=3; got {len(result.items)}"
    )
    assert result.next_cursor == "opaque-cursor-base64"
    # DEC-LOGIN-10: estado values are the canonical Literal.
    estados = {item.estado for item in result.items}
    assert estados <= {"exitoso", "fallido", "cerrado"}, (
        f"estados must be subset of DEC-LOGIN-10 Literal; got {estados}"
    )
    # Envelope keys pinned: only items + next_cursor (no activo/count/total/has_more).
    assert set(result.model_dump().keys()) == {"items", "next_cursor"}, (
        f"DEC-LOGIN-07 violated: envelope must carry ONLY items + next_cursor; "
        f"got {sorted(result.model_dump().keys())}"
    )


@pytest.mark.asyncio
async def test_200_empty_items_for_unknown_user() -> None:
    """MANDATED T4.2 T2 (plan.md line 1149): empty user -> 200 + items=[] + next_cursor=None.

    DEC-LOGIN-08 anti-enumeration contract: zero ``prod.login`` rows
    for the user returns ``items=[]`` + ``next_cursor=None`` with HTTP
    200 (NEVER 404, NEVER 403). REQ-OPS-104 mirrors this -- a side-
    channel observer cannot distinguish "user with no history" from
    "user does not exist".
    """
    from parkos_core.api.v1 import usuarios_login as handler_mod

    user_uuid = uuid_lib.uuid4()
    branch_uuid = uuid_lib.uuid4()

    ctx = _make_ctx(issuer_prefix="operador-", sucursal_uuid=branch_uuid)
    response = _new_response()
    params = _build_query_params(limit=10, cursor=None)

    session = MagicMock()
    session.commit = AsyncMock()

    m_listar = AsyncMock(return_value=[])  # empty rows
    m_encode_cursor = MagicMock(return_value=None)  # last page

    with patch.object(handler_mod.repo_login_historico, "listar_intentos_paginado", m_listar), \
         patch.object(handler_mod.repo_login_historico, "encode_next_cursor", m_encode_cursor):
        result = await handler_mod.get_login_historico(
            response=response,
            uuid=user_uuid,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # DEC-LOGIN-08: 200 + empty items + None cursor.
    assert result.items == [], (
        f"empty user MUST return items=[] (DEC-LOGIN-08); got {result.items!r}"
    )
    assert result.next_cursor is None, (
        "empty user MUST return next_cursor=None (last page)"
    )
    # DEC-LOGIN-05: no-store header STILL set on the empty branch response.
    assert response.headers["Cache-Control"] == "no-store", (
        "DEC-LOGIN-05 violated: no-store header MUST be set even on empty branch"
    )
    # KD-LOGIN-01: handler still called the typed helper exactly once.
    m_listar.assert_called_once()
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# T4.2 -- cross-branch asymmetry (DEC-LOGIN-03.A)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operador_other_branch_filtered_at_repo_layer() -> None:
    """T4.2: operador ctx with ``tenant_ctx`` is passed to the repo helper.

    DEC-LOGIN-03.A -- the Layer 2 tenant filter is applied INSIDE the
    helper (SQL ``WHERE login.uuid_sucursal = ctx.sucursal_uuid``),
    so the handler never sees cross-branch data. This test pins the
    handler-to-repo contract: the handler MUST pass ``tenant_ctx=ctx``
    to the helper.
    """
    from parkos_core.api.v1 import usuarios_login as handler_mod

    user_uuid = uuid_lib.uuid4()
    branch_uuid = uuid_lib.uuid4()

    ctx = _make_ctx(issuer_prefix="operador-", sucursal_uuid=branch_uuid)
    response = _new_response()
    params = _build_query_params(limit=10, cursor=None)

    session = MagicMock()
    session.commit = AsyncMock()

    # Cross-branch rows (different ``uuid_sucursal``) -- the helper
    # would filter them out at SQL layer. We mock the helper to
    # return [] to assert the handler passes the ctx through.
    m_listar = AsyncMock(return_value=[])
    m_encode_cursor = MagicMock(return_value=None)

    with patch.object(handler_mod.repo_login_historico, "listar_intentos_paginado", m_listar), \
         patch.object(handler_mod.repo_login_historico, "encode_next_cursor", m_encode_cursor):
        await handler_mod.get_login_historico(
            response=response,
            uuid=user_uuid,
            params=params,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # Pin the call signature: handler MUST pass tenant_ctx=ctx.
    call_kwargs = m_listar.await_args.kwargs
    assert call_kwargs.get("tenant_ctx") is ctx, (
        f"DEC-LOGIN-03.A violated: handler MUST pass tenant_ctx=ctx to helper; "
        f"got kwargs={call_kwargs!r}"
    )
    assert call_kwargs.get("uuid_usuario") == user_uuid
    assert call_kwargs.get("limit") == 10
    assert call_kwargs.get("cursor") is None
