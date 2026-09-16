"""HU-F1.10 / T8.1 — End-to-end integration test (POST → GET → reintentar → GET).

Mocked-DB exercise of the full happy-path user journey:

  1. POST   /factura-electronica                  → 201 + envio_actual=pendiente
  2. GET    /factura-electronica/{uuid}           → 200 + envio_actual=pendiente
  3. POST   /factura-electronica/{uuid}/reintentar → 201 + new envio row
  4. GET    /factura-electronica/{uuid}           → 200 + envio_actual=pendiente
                                                       (chain advanced by retry)

Mocks the repo helpers end-to-end (no DB). Asserts:
  - State machine correctness across the 4 calls
  - KD-FE-01 single-commit per write call
  - DEC-FE-02 retry row carries ``uuid_envio_padre=<prior chain tip>``
  - DEC-FE-06 Cache-Control: no-store on every response
  - Tenant scope is enforced on every call (ctx.sucursal_uuid matches FE row)
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


def _make_ctx(sucursal_uuid: uuid_lib.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal_uuid
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


@pytest.mark.asyncio
async def test_e2e_post_get_retry_get_full_journey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T8.1: POST → GET → /reintentar → GET across the 3 handlers.

    Mocks the repo helpers to drive a coherent state machine through
    the full lifecycle. No DB. Asserts:
      - Each write call invokes ``session.commit()`` exactly once (KD-FE-01).
      - The retry's ``uuid_envio_padre`` equals the prior chain tip's uuid.
      - Every response carries ``Cache-Control: no-store`` (DEC-FE-06).
      - ``envio_actual.estado`` is ``'pendiente'`` after both writes and reads.
    """
    import parkos_core.api.v1.facturacion as facturacion_mod

    # ----- Scenario state ----------------------------------------------
    uuid_sucursal = uuid_lib.uuid4()
    uuid_factura = uuid_lib.uuid4()
    uuid_resolucion = uuid_lib.uuid4()
    fe_uuid = uuid_lib.uuid4()
    first_envio_uuid = uuid_lib.uuid4()
    retry_envio_uuid = uuid_lib.uuid4()

    # ORM-like objects.
    factura_orm = MagicMock()
    factura_orm.uuid = uuid_factura
    factura_orm.uuid_sucursal = uuid_sucursal

    resolucion_orm = MagicMock()
    resolucion_orm.uuid = uuid_resolucion
    resolucion_orm.prefijo = "SETP"
    resolucion_orm.rango_hasta = 5000

    fe_row = MagicMock()
    fe_row.uuid = fe_uuid
    fe_row.prefijo = "SETP"
    fe_row.consecutivo = 100
    fe_row.uuid_sucursal = uuid_sucursal
    fe_row.uuid_factura = uuid_factura
    fe_row.uuid_resolucion_facturacion = uuid_resolucion
    fe_row.created_at = _now()

    first_envio_orm = MagicMock()
    first_envio_orm.uuid = first_envio_uuid
    first_envio_orm.uuid_factura_electronica = fe_uuid
    first_envio_orm.estado = "pendiente"
    first_envio_orm.timestamp_evento = _now()
    first_envio_orm.uuid_envio_padre = None
    first_envio_orm.cufe = None
    first_envio_orm.motivo_rechazo = None

    retry_envio_orm = MagicMock()
    retry_envio_orm.uuid = retry_envio_uuid
    retry_envio_orm.uuid_factura_electronica = fe_uuid
    retry_envio_orm.estado = "pendiente"
    retry_envio_orm.timestamp_evento = _now()
    retry_envio_orm.uuid_envio_padre = first_envio_uuid
    retry_envio_orm.cufe = None
    retry_envio_orm.motivo_rechazo = None

    # Mutable state for the view JOIN in subsequent GET calls.
    state: dict[str, object] = {
        "ack": {
            "uuid": first_envio_uuid,
            "estado": "pendiente",
            "cufe": None,
            "timestamp_evento": _now(),
            "motivo_rechazo": None,
        }
    }

    async def _view_join(session, *, uuid):
        return fe_row, state["ack"]

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "leer_factura_electronica_con_envio_via_view",
        _view_join,
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=factura_orm),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_factura",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_uuid",
        AsyncMock(return_value=fe_row),
    )
    monkeypatch.setattr(
        facturacion_mod,
        "buscar_resolucion_vigente_por_sucursal",
        AsyncMock(return_value=resolucion_orm),
    )
    monkeypatch.setattr(
        facturacion_mod, "assign_consecutivo", AsyncMock(return_value=100)
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_factura_electronica_inicial",
        AsyncMock(return_value=fe_row),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_envio_dian_inicial",
        AsyncMock(return_value=first_envio_orm),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_envio_dian_reintento",
        AsyncMock(return_value=retry_envio_orm),
    )

    async def _chain_tip(session, *, uuid_factura_electronica):
        # After the retry, advance the chain tip view.
        return state["chain_tip"]

    state["chain_tip"] = first_envio_orm
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_envio_dian_chain_tip",
        _chain_tip,
    )

    factory = MagicMock()
    factory.fire = AsyncMock()
    monkeypatch.setattr(
        facturacion_mod, "AlertaFactory", MagicMock(return_value=factory)
    )

    ctx = _make_ctx(uuid_sucursal)
    payload = FacturaElectronicaCreate(uuid_factura=uuid_factura)

    # ----- 1. POST /factura-electronica -------------------------------
    session = AsyncMock()
    response = _new_response()
    result_post = await create_factura_electronica(
        response, payload, session, ctx, None
    )
    assert result_post.uuid == fe_uuid
    assert result_post.prefijo == "SETP"
    assert result_post.consecutivo == 100
    assert result_post.envio_actual.estado == "pendiente"
    assert result_post.envio_actual.uuid_envio_padre is None
    assert response.headers["Cache-Control"] == "no-store"
    assert session.commit.await_count == 1  # KD-FE-01

    # ----- 2. GET /factura-electronica/{uuid} --------------------------
    session = AsyncMock()
    response = _new_response()
    result_get1 = await get_factura_electronica(
        response, fe_uuid, session, ctx, None
    )
    assert result_get1.uuid == fe_uuid
    assert result_get1.envio_actual.estado == "pendiente"
    assert result_get1.envio_actual.uuid == first_envio_uuid
    assert response.headers["Cache-Control"] == "no-store"
    # GET is read-only — zero commits.
    assert session.commit.await_count == 0

    # ----- 3. POST /factura-electronica/{uuid}/reintentar --------------
    # Simulate the cloud flipping the initial envio to 'rechazado' between
    # step 2 and step 3.
    state["chain_tip"] = MagicMock()
    state["chain_tip"].uuid = first_envio_uuid
    state["chain_tip"].estado = "rechazado"

    session = AsyncMock()
    response = _new_response()
    result_retry = await retry_envio_dian(
        response, fe_uuid, session, ctx, None
    )
    assert result_retry.estado == "pendiente"
    assert result_retry.uuid_envio_padre == first_envio_uuid
    assert result_retry.uuid == retry_envio_uuid
    assert response.headers["Cache-Control"] == "no-store"
    assert session.commit.await_count == 1  # KD-FE-01

    # ----- 4. GET /factura-electronica/{uuid} (post-retry) -------------
    # Simulate the view returning the new chain tip (retry envio).
    state["ack"] = {
        "uuid": retry_envio_uuid,
        "estado": "pendiente",
        "cufe": None,
        "timestamp_evento": _now(),
        "motivo_rechazo": None,
    }

    session = AsyncMock()
    response = _new_response()
    result_get2 = await get_factura_electronica(
        response, fe_uuid, session, ctx, None
    )
    assert result_get2.uuid == fe_uuid
    assert result_get2.envio_actual.uuid == retry_envio_uuid
    assert result_get2.envio_actual.estado == "pendiente"
    assert response.headers["Cache-Control"] == "no-store"
    assert session.commit.await_count == 0

    # ----- Cross-cutting assertions -----------------------------------
    # The retry helper was called with the prior chain tip as parent.
    call_kwargs = (
        facturacion_mod.repo_factura_electronica.crear_envio_dian_reintento.call_args.kwargs
    )
    assert call_kwargs["uuid_envio_padre"] == first_envio_uuid
    assert call_kwargs["uuid_factura_electronica"] == fe_uuid
