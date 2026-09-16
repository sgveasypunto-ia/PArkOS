"""HU-F1.10 / T7.3 — Cache-Control: no-store on every FE handler.

DEC-FE-06 / R-A6 mitigation: every response from an operator-facing
mutating endpoint (POST + GET on FE) MUST carry the ``Cache-Control:
no-store`` header. A proxy that served a stale FE read or a stale
retry submission would silently accept out-of-date state.

The test instantiates a MagicMock ``Response`` per handler and asserts
``response.headers["Cache-Control"] == "no-store"`` after the handler
returns. Error responses (404 / 403 / 409) get the same header via
``no_store_headers()``; the unit tests in
``test_factura_electronica_create_handler.py`` already cover the error
paths. This file covers the 2xx success paths only.
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
from parkos_core.api.v1.facturacion import (  # noqa: E402
    create_factura_electronica,
    get_factura_electronica,
    retry_envio_dian,
)
from parkos_core.schemas.facturacion import FacturaElectronicaCreate  # noqa: E402


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_ctx(sucursal_uuid: uuid_lib.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    return ctx


def _patch_full_create(
    monkeypatch: pytest.MonkeyPatch, *, fe_uuid: uuid_lib.UUID
) -> None:
    """Patch the create handler's repo + helper deps for a happy-path run."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    uuid_sucursal = uuid_lib.uuid4()
    uuid_resolucion = uuid_lib.uuid4()
    uuid_factura = uuid_lib.uuid4()

    factura = MagicMock()
    factura.uuid = uuid_factura
    factura.uuid_sucursal = uuid_sucursal

    resolucion = MagicMock()
    resolucion.uuid = uuid_resolucion
    resolucion.prefijo = "SETP"
    resolucion.rango_hasta = 5000

    fe_row = MagicMock()
    fe_row.uuid = fe_uuid
    fe_row.prefijo = "SETP"
    fe_row.consecutivo = 42
    fe_row.uuid_factura = uuid_factura
    fe_row.uuid_resolucion_facturacion = uuid_resolucion
    fe_row.created_at = _now()

    envio = MagicMock()
    envio.uuid = uuid_lib.uuid4()
    envio.uuid_factura_electronica = fe_uuid
    envio.estado = "pendiente"
    envio.timestamp_evento = _now()
    envio.uuid_envio_padre = None
    envio.cufe = None
    envio.motivo_rechazo = None

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=factura),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_factura",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        facturacion_mod,
        "buscar_resolucion_vigente_por_sucursal",
        AsyncMock(return_value=resolucion),
    )
    monkeypatch.setattr(
        facturacion_mod, "assign_consecutivo", AsyncMock(return_value=42)
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_factura_electronica_inicial",
        AsyncMock(return_value=fe_row),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_envio_dian_inicial",
        AsyncMock(return_value=envio),
    )
    factory = MagicMock()
    factory.fire = AsyncMock()
    monkeypatch.setattr(
        facturacion_mod, "AlertaFactory", MagicMock(return_value=factory)
    )


@pytest.mark.asyncio
async def test_create_handler_sets_cache_control_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T7.3 / DEC-FE-06: POST /factura-electronica sets Cache-Control: no-store."""
    fe_uuid = uuid_lib.uuid4()
    _patch_full_create(monkeypatch, fe_uuid=fe_uuid)
    import parkos_core.api.v1.facturacion as facturacion_mod

    factura_orm = MagicMock()
    factura_orm.uuid_sucursal = uuid_lib.uuid4()
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=factura_orm),
    )

    payload = FacturaElectronicaCreate(uuid_factura=uuid_lib.uuid4())
    ctx = _make_ctx()
    response = MagicMock()
    response.headers = {}
    session = AsyncMock()

    await create_factura_electronica(response, payload, session, ctx, None)
    assert response.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_get_handler_sets_cache_control_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T7.3 / DEC-FE-06: GET /factura-electronica/{uuid} sets no-store."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    fe_row = MagicMock()
    fe_row.uuid = uuid_lib.uuid4()
    fe_row.prefijo = "SETP"
    fe_row.consecutivo = 42
    fe_row.uuid_sucursal = uuid_lib.uuid4()
    fe_row.uuid_factura = uuid_lib.uuid4()
    fe_row.uuid_resolucion_facturacion = uuid_lib.uuid4()
    fe_row.created_at = _now()

    ack_dict = {
        "uuid": uuid_lib.uuid4(),
        "estado": "aceptado",
        "cufe": "abc",
        "timestamp_evento": _now(),
        "motivo_rechazo": None,
    }

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "leer_factura_electronica_con_envio_via_view",
        AsyncMock(return_value=(fe_row, ack_dict)),
    )

    response = MagicMock()
    response.headers = {}
    session = AsyncMock()
    ctx = _make_ctx(sucursal_uuid=fe_row.uuid_sucursal)

    await get_factura_electronica(response, fe_row.uuid, session, ctx, None)
    assert response.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_retry_handler_sets_cache_control_no_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T7.3 / DEC-FE-06: POST /reintentar sets no-store."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    fe_row = MagicMock()
    fe_row.uuid = uuid_lib.uuid4()
    fe_row.prefijo = "SETP"
    fe_row.consecutivo = 42
    fe_row.uuid_sucursal = uuid_lib.uuid4()
    fe_row.uuid_factura = uuid_lib.uuid4()
    fe_row.uuid_resolucion_facturacion = uuid_lib.uuid4()

    chain_tip = MagicMock()
    chain_tip.uuid = uuid_lib.uuid4()
    chain_tip.estado = "rechazado"

    new_envio = MagicMock()
    new_envio.uuid = uuid_lib.uuid4()
    new_envio.timestamp_evento = _now()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_uuid",
        AsyncMock(return_value=fe_row),
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
    session = AsyncMock()
    ctx = _make_ctx(sucursal_uuid=fe_row.uuid_sucursal)

    await retry_envio_dian(response, fe_row.uuid, session, ctx, None)
    assert response.headers.get("Cache-Control") == "no-store"
