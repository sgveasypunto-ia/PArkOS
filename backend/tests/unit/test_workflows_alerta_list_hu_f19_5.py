"""HU-F19.5 / T1 — GET /api/v1/workflows/alerta (list) + GET /{uuid} tests.

Mock-everything pattern (no DB), mirrors ``test_workflows_alerta_descartar.py``
(HU-F19.4 precedent for this same module). Covers the two design notes in
``api/v1/workflows_alerta.py``'s module docstring:

  - BR4: ``severity`` is ``null`` when the row's ``tipo_alerta`` has no
    matching ``prod.alert_types`` row (LEFT JOIN semantics), never dropped.
  - Authorization: ``operador-`` pinned to its own JWT ``sucursal`` claim
    (403 ``tenant_scope_violation`` on a cross-branch ``uuid_sucursal``
    filter); ``admin-`` cross-branch via
    ``extract_sucursales_permitidas_fresh`` (400 ``missing_sucursal_context``
    when it resolves empty, 403 ``unauthorized_sucursal_context`` when the
    caller names a branch outside that set) -- never ``get_tenant_ctx``/
    ``BranchScope``.

Also covers ``rango_fecha_invalido`` (422), ``invalid_cursor`` (400), the
cursor-pagination truncation (``limit + 1`` rows -> ``next_cursor`` set),
and ``GET /{uuid}`` (current_version passthrough, 404 on a missing row).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from parkos_core.repo.pagination import Cursor  # noqa: E402
from parkos_core.repo.pagination import encode as cursor_encode  # noqa: E402


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_alerta_row(
    *,
    uuid: uuid_lib.UUID | None = None,
    uuid_sucursal: uuid_lib.UUID,
    tipo_alerta: str = "descuadre_critico",
    estado: str = "abierta",
    vigente_desde: datetime | None = None,
) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid or uuid_lib.uuid4()
    row.fecha_retencion_hasta = _now().date()
    row.created_at = _now()
    row.created_by = uuid_lib.uuid4()
    row.sync_status = None
    row.sync_timestamp = None
    row.sync_attempts = None
    row.uuid_sucursal = uuid_sucursal
    row.uuid_usuario = uuid_lib.uuid4()
    row.uuid_arqueo = None
    row.tipo_alerta = tipo_alerta
    row.valor_diferencia_efectivo = None
    row.valor_diferencia_datafono = None
    row.uuid_alerta_padre = None
    row.timestamp_evento = _now()
    row.vigente_desde = vigente_desde or _now()
    row.vigente_hasta = None
    row.estado = estado
    return row


def _session_returning(rows: list) -> MagicMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    return session


def _operador_claims(*, actor_uuid: uuid_lib.UUID, sucursal: uuid_lib.UUID) -> dict:
    return {"sub": str(actor_uuid), "iss": "operador-test", "sucursal": str(sucursal)}


def _admin_claims(*, actor_uuid: uuid_lib.UUID) -> dict:
    return {"sub": str(actor_uuid), "iss": "admin-test"}


# ---------------------------------------------------------------------------
# BR4 — severity LEFT JOIN null-safety + response shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alertas_severity_null_when_no_catalog_row() -> None:
    """A tipo_alerta with no prod.alert_types row lists with severity=None (BR4)."""
    import parkos_core.api.v1.workflows_alerta as mod

    sucursal = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    row = _make_alerta_row(uuid_sucursal=sucursal, tipo_alerta="out_of_catalog_type")
    session = _session_returning([(row, None)])

    result = await mod.list_alertas(
        _operador_claims(actor_uuid=actor, sucursal=sucursal),
        session,
    )

    assert len(result.items) == 1
    assert result.items[0].severity is None
    assert result.items[0].uuid == row.uuid
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_list_alertas_severity_populated_from_join() -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    sucursal = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    row = _make_alerta_row(uuid_sucursal=sucursal)
    session = _session_returning([(row, "critical")])

    result = await mod.list_alertas(
        _operador_claims(actor_uuid=actor, sucursal=sucursal),
        session,
    )

    assert result.items[0].severity == "critical"


@pytest.mark.asyncio
async def test_list_alertas_pagination_truncates_and_sets_next_cursor() -> None:
    """limit+1 rows fetched -> response truncates to limit, next_cursor set."""
    import parkos_core.api.v1.workflows_alerta as mod

    sucursal = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    rows = [(_make_alerta_row(uuid_sucursal=sucursal), "info") for _ in range(3)]
    session = _session_returning(rows)

    result = await mod.list_alertas(
        _operador_claims(actor_uuid=actor, sucursal=sucursal),
        session,
        limit=2,
    )

    assert len(result.items) == 2
    assert result.next_cursor is not None


# ---------------------------------------------------------------------------
# Authorization — operador- pinned to own branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alertas_operador_cross_branch_returns_403() -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    own_sucursal = uuid_lib.uuid4()
    other_sucursal = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    session = _session_returning([])

    with pytest.raises(HTTPException) as exc_info:
        await mod.list_alertas(
            _operador_claims(actor_uuid=actor, sucursal=own_sucursal),
            session,
            uuid_sucursal=other_sucursal,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_list_alertas_operador_missing_sucursal_claim_returns_401() -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    actor = uuid_lib.uuid4()
    session = _session_returning([])
    claims = {"sub": str(actor), "iss": "operador-test"}  # no 'sucursal' claim

    with pytest.raises(HTTPException) as exc_info:
        await mod.list_alertas(claims, session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error"] == "missing_sucursal_in_jwt"


# ---------------------------------------------------------------------------
# Authorization — admin- cross-branch via extract_sucursales_permitidas_fresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alertas_admin_no_uuid_sucursal_scopes_to_every_permitida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    actor = uuid_lib.uuid4()
    branch_a, branch_b = uuid_lib.uuid4(), uuid_lib.uuid4()
    monkeypatch.setattr(
        mod, "extract_sucursales_permitidas_fresh", AsyncMock(return_value=[branch_a, branch_b])
    )
    row = _make_alerta_row(uuid_sucursal=branch_a)
    session = _session_returning([(row, "warning")])

    result = await mod.list_alertas(_admin_claims(actor_uuid=actor), session)

    assert len(result.items) == 1
    mod.extract_sucursales_permitidas_fresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_alertas_admin_no_permitidas_returns_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    actor = uuid_lib.uuid4()
    monkeypatch.setattr(
        mod, "extract_sucursales_permitidas_fresh", AsyncMock(return_value=[])
    )
    session = _session_returning([])

    with pytest.raises(HTTPException) as exc_info:
        await mod.list_alertas(_admin_claims(actor_uuid=actor), session)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "missing_sucursal_context"


@pytest.mark.asyncio
async def test_list_alertas_admin_unauthorized_branch_returns_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    actor = uuid_lib.uuid4()
    permitida = uuid_lib.uuid4()
    other = uuid_lib.uuid4()
    monkeypatch.setattr(
        mod, "extract_sucursales_permitidas_fresh", AsyncMock(return_value=[permitida])
    )
    session = _session_returning([])

    with pytest.raises(HTTPException) as exc_info:
        await mod.list_alertas(
            _admin_claims(actor_uuid=actor), session, uuid_sucursal=other
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "unauthorized_sucursal_context"
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Validation — rango_fecha_invalido (422) + invalid_cursor (400)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_alertas_rango_fecha_invalido_returns_422() -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    sucursal = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    session = _session_returning([])

    with pytest.raises(HTTPException) as exc_info:
        await mod.list_alertas(
            _operador_claims(actor_uuid=actor, sucursal=sucursal),
            session,
            desde=date(2026, 1, 10),
            hasta=date(2026, 1, 1),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rango_fecha_invalido"
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_list_alertas_invalid_cursor_returns_400() -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    sucursal = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    session = _session_returning([])

    with pytest.raises(HTTPException) as exc_info:
        await mod.list_alertas(
            _operador_claims(actor_uuid=actor, sucursal=sucursal),
            session,
            cursor="not-a-valid-cursor!!",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "invalid_cursor"


@pytest.mark.asyncio
async def test_list_alertas_valid_cursor_is_decoded_and_applied() -> None:
    """A well-formed cursor does not raise; the handler proceeds to query."""
    import parkos_core.api.v1.workflows_alerta as mod

    sucursal = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()
    session = _session_returning([])
    cursor = cursor_encode(Cursor(vigente_desde=_now().isoformat(), uuid=str(uuid_lib.uuid4())))

    result = await mod.list_alertas(
        _operador_claims(actor_uuid=actor, sucursal=sucursal),
        session,
        cursor=cursor,
    )

    assert result.items == []
    session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /{uuid} — current_version passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_alerta_returns_current_version(monkeypatch: pytest.MonkeyPatch) -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    sucursal = uuid_lib.uuid4()
    row = _make_alerta_row(uuid_sucursal=sucursal)
    monkeypatch.setattr(mod, "current_version", AsyncMock(return_value=row))
    session = AsyncMock()

    result = await mod.get_alerta(row.uuid, session, MagicMock(), None)

    assert result.uuid == row.uuid


@pytest.mark.asyncio
async def test_get_alerta_returns_404_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import parkos_core.api.v1.workflows_alerta as mod

    missing_uuid = uuid_lib.uuid4()
    monkeypatch.setattr(mod, "current_version", AsyncMock(return_value=None))
    session = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await mod.get_alerta(missing_uuid, session, MagicMock(), None)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "not_found"
