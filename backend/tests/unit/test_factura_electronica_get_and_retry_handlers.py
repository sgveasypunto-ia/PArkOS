"""HU-F1.10 / T5.1 + T5.3 + T6.1 + T6.3 — GET + /reintentar handler tests.

T5.1 happy path: GET /factura-electronica/{uuid} returns 200 with the
FE row + envio_actual chain tip from the view JOIN.
T5.3 null mapping: when the FE has zero envio rows, envio_actual is
synthesized from the FE row's created_at (REQ-OPS-068 Scenario 2).

T6.1 happy path: POST /reintentar inserts a NEW envio_dian row with
``uuid_envio_padre=<chain_tip.uuid>``, ``estado='pendiente'``.
T6.3 409: chain tip state ``aceptado`` → 409 reintento_no_permitido;
chain tip state ``pendiente`` → 409 envio_dian_already_pending.

All tests mock the repo helpers (no DB) and assert KD-FE-01 single-commit
on T6.1. The AST walks (T4.5 + T6.4 + T6.5) lock the no-UPDATE + retry
KD-FE-01 invariants separately.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from parkos_core.api.v1.facturacion import (  # noqa: E402
    get_factura_electronica,
    retry_envio_dian,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_ctx(sucursal_uuid: uuid_lib.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    return ctx


def _make_fe_orm(
    *,
    uuid: uuid_lib.UUID | None = None,
    uuid_sucursal: uuid_lib.UUID | None = None,
    uuid_factura: uuid_lib.UUID | None = None,
    uuid_resolucion: uuid_lib.UUID | None = None,
) -> MagicMock:
    fe = MagicMock()
    fe.uuid = uuid or uuid_lib.uuid4()
    fe.prefijo = "SETP"
    fe.consecutivo = 42
    fe.uuid_sucursal = uuid_sucursal or uuid_lib.uuid4()
    fe.uuid_factura = uuid_factura or uuid_lib.uuid4()
    fe.uuid_resolucion_facturacion = uuid_resolucion or uuid_lib.uuid4()
    fe.created_at = _now()
    return fe


def _make_envio_orm(
    *,
    uuid_factura_electronica: uuid_lib.UUID,
    estado: str = "pendiente",
    uuid_envio_padre: uuid_lib.UUID | None = None,
) -> MagicMock:
    envio = MagicMock()
    envio.uuid = uuid_lib.uuid4()
    envio.uuid_factura_electronica = uuid_factura_electronica
    envio.estado = estado
    envio.timestamp_evento = _now()
    envio.uuid_envio_padre = uuid_envio_padre
    envio.cufe = None
    envio.motivo_rechazo = None
    return envio


# ---------------------------------------------------------------------------
# T5.1 — GET happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_factura_electronica_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T5.1: GET returns 200 with FE row + envio_actual from view JOIN.

    Asserts:
      - response.prefijo == 'SETP' + consecutivo == 42
      - envio_actual.estado == 'aceptado' (from view)
      - envio_actual.cufe is set (from view)
      - Cache-Control: no-store header (DEC-FE-06)
    """
    import parkos_core.api.v1.facturacion as facturacion_mod

    fe_orm = _make_fe_orm()
    ctx = _make_ctx(sucursal_uuid=fe_orm.uuid_sucursal)
    session = AsyncMock()

    ack_dict = {
        "uuid": uuid_lib.uuid4(),
        "estado": "aceptado",
        "cufe": "abc123-cufe",
        "timestamp_evento": _now(),
        "motivo_rechazo": None,
    }

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "leer_factura_electronica_con_envio_via_view",
        AsyncMock(return_value=(fe_orm, ack_dict)),
    )

    response = MagicMock()
    response.headers = {}

    result = await get_factura_electronica(
        response, fe_orm.uuid, session, ctx, None
    )

    assert result.uuid == fe_orm.uuid
    assert result.prefijo == "SETP"
    assert result.consecutivo == 42
    assert result.envio_actual.estado == "aceptado"
    assert result.envio_actual.cufe == "abc123-cufe"
    assert response.headers.get("Cache-Control") == "no-store"


# ---------------------------------------------------------------------------
# T5.3 — null mapping (REQ-OPS-068 Scenario 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_factura_electronica_null_mapping_when_no_envio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T5.3: empty envio chain → envio_actual synthesized from FE row.

    The view returns NULL when the FE has zero envio rows (defensive).
    The handler must STILL return 200 with a synthesized envio_actual
    (estado='pendiente', cufe=None, motivo_rechazo=None).
    """
    import parkos_core.api.v1.facturacion as facturacion_mod

    fe_orm = _make_fe_orm()
    ctx = _make_ctx(sucursal_uuid=fe_orm.uuid_sucursal)
    session = AsyncMock()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "leer_factura_electronica_con_envio_via_view",
        AsyncMock(return_value=(fe_orm, None)),
    )

    response = MagicMock()
    response.headers = {}

    result = await get_factura_electronica(
        response, fe_orm.uuid, session, ctx, None
    )

    assert result.uuid == fe_orm.uuid
    assert result.envio_actual.estado == "pendiente"
    assert result.envio_actual.cufe is None
    assert result.envio_actual.motivo_rechazo is None
    assert result.envio_actual.uuid_factura_electronica == fe_orm.uuid


@pytest.mark.asyncio
async def test_get_factura_electronica_404_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V1 404: missing FE row → 404 factura_electronica_no_encontrada."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    missing_uuid = uuid_lib.uuid4()
    ctx = _make_ctx()
    session = AsyncMock()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "leer_factura_electronica_con_envio_via_view",
        AsyncMock(return_value=(None, None)),
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_factura_electronica(response, missing_uuid, session, ctx, None)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "factura_electronica_no_encontrada"


# ---------------------------------------------------------------------------
# T6.1 — POST /reintentar happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_envio_dian_happy_path_with_chain_tip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6.1: rejected envio → retry creates NEW row with uuid_envio_padre=<tip>.

    Asserts:
      - response.estado == 'pendiente'
      - response.uuid_envio_padre == chain_tip.uuid
      - session.commit() called exactly once (KD-FE-01)
      - Cache-Control: no-store header (DEC-FE-06)
    """
    import parkos_core.api.v1.facturacion as facturacion_mod

    fe_orm = _make_fe_orm()
    chain_tip = _make_envio_orm(
        uuid_factura_electronica=fe_orm.uuid, estado="rechazado"
    )
    new_envio = _make_envio_orm(
        uuid_factura_electronica=fe_orm.uuid,
        estado="pendiente",
        uuid_envio_padre=chain_tip.uuid,
    )

    ctx = _make_ctx(sucursal_uuid=fe_orm.uuid_sucursal)
    session = AsyncMock()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_uuid",
        AsyncMock(return_value=fe_orm),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_envio_dian_chain_tip",
        AsyncMock(return_value=chain_tip),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_envio_dian_reintento",
        AsyncMock(return_value=new_envio),
    )

    response = MagicMock()
    response.headers = {}

    result = await retry_envio_dian(response, fe_orm.uuid, session, ctx, None)

    assert result.estado == "pendiente"
    assert result.uuid_envio_padre == chain_tip.uuid
    assert result.uuid_factura_electronica == fe_orm.uuid
    # KD-FE-01: exactly one commit.
    assert session.commit.await_count == 1
    assert response.headers.get("Cache-Control") == "no-store"


# ---------------------------------------------------------------------------
# T6.3 — 409 discriminators
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_409_when_chain_tip_is_aceptado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6.3: chain tip is 'aceptado' → 409 reintento_no_permitido (DEC-FE-04)."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    fe_orm = _make_fe_orm()
    chain_tip = _make_envio_orm(
        uuid_factura_electronica=fe_orm.uuid, estado="aceptado"
    )

    ctx = _make_ctx(sucursal_uuid=fe_orm.uuid_sucursal)
    session = AsyncMock()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_uuid",
        AsyncMock(return_value=fe_orm),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_envio_dian_chain_tip",
        AsyncMock(return_value=chain_tip),
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await retry_envio_dian(response, fe_orm.uuid, session, ctx, None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "reintento_no_permitido"
    assert exc_info.value.detail["estado_actual"] == "aceptado"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_retry_409_when_chain_tip_is_pendiente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T6.3: chain tip is 'pendiente' → 409 envio_dian_already_pending."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    fe_orm = _make_fe_orm()
    chain_tip = _make_envio_orm(
        uuid_factura_electronica=fe_orm.uuid, estado="pendiente"
    )

    ctx = _make_ctx(sucursal_uuid=fe_orm.uuid_sucursal)
    session = AsyncMock()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_uuid",
        AsyncMock(return_value=fe_orm),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_envio_dian_chain_tip",
        AsyncMock(return_value=chain_tip),
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await retry_envio_dian(response, fe_orm.uuid, session, ctx, None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "envio_dian_already_pending"
    assert exc_info.value.detail["uuid_envio_pendiente"] == str(chain_tip.uuid)
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_retry_404_when_fe_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V1 404: missing FE row → 404 factura_electronica_no_encontrada."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    missing_uuid = uuid_lib.uuid4()
    ctx = _make_ctx()
    session = AsyncMock()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_uuid",
        AsyncMock(return_value=None),
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await retry_envio_dian(response, missing_uuid, session, ctx, None)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "factura_electronica_no_encontrada"
