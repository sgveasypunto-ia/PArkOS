"""HU-F1.10 / T4.1 + T4.3 — POST /factura-electronica handler unit tests.

T4.1 happy path (mocked AsyncSession + repo helpers): the 12-step chain
returns ``FacturaElectronicaRead`` carrying the assigned ``prefijo`` +
``consecutivo`` + an ``envio_actual`` with ``estado='pendiente'`` +
``uuid_envio_padre=None``.

T4.3 error paths: V1 (404 factura_no_encontrada), V2 (409
factura_electronica_ya_existe), V3 (409 resolucion_no_vigente), V4 (409
numeracion_agotada + alerta).

All tests mock the repo helpers + ``assign_consecutivo`` to keep them
DB-independent — the AST walk in ``tests/static/test_fe_handler_single_commit.py``
locks the single-commit invariant and ``tests/integration/test_migration_0028_idempotent.py``
covers the partial UK race. ``Cache-Control: no-store`` is asserted on
the success response (DEC-FE-06).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from parkos_core.api.v1.facturacion import create_factura_electronica  # noqa: E402
from parkos_core.repo.resolucion_facturacion import (  # noqa: E402
    ConsecutivoRangeExhaustedError,
)
from parkos_core.schemas.facturacion import FacturaElectronicaCreate  # noqa: E402


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _make_ctx(actor_uuid: uuid_lib.UUID | None = None) -> MagicMock:
    """Build a TenantContext-like MagicMock."""
    ctx = MagicMock()
    ctx.actor_uuid = actor_uuid or uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_lib.uuid4()
    return ctx


def _make_payload(uuid_factura: uuid_lib.UUID | None = None) -> FacturaElectronicaCreate:
    return FacturaElectronicaCreate(uuid_factura=uuid_factura or uuid_lib.uuid4())


def _make_factura_orm(
    *, uuid_factura: uuid_lib.UUID, uuid_sucursal: uuid_lib.UUID | None = None
) -> MagicMock:
    """ORM-like factura row for ``buscar_factura_por_uuid``."""
    factura = MagicMock()
    factura.uuid = uuid_factura
    factura.uuid_sucursal = uuid_sucursal or uuid_lib.uuid4()
    return factura


def _make_resolucion_orm(
    *, uuid: uuid_lib.UUID | None = None, rango_hasta: int = 5000
) -> MagicMock:
    """ORM-like resolucion row for ``buscar_resolucion_vigente_por_sucursal``."""
    r = MagicMock()
    r.uuid = uuid or uuid_lib.uuid4()
    r.prefijo = "SETP"
    r.rango_hasta = rango_hasta
    return r


def _make_fe_orm(
    *,
    uuid_factura: uuid_lib.UUID,
    uuid_resolucion: uuid_lib.UUID,
    prefijo: str = "SETP",
    consecutivo: int = 42,
) -> MagicMock:
    fe = MagicMock()
    fe.uuid = uuid_lib.uuid4()
    fe.prefijo = prefijo
    fe.consecutivo = consecutivo
    fe.uuid_factura = uuid_factura
    fe.uuid_resolucion_facturacion = uuid_resolucion
    fe.created_at = _now()
    return fe


def _make_envio_orm(
    *,
    uuid_factura_electronica: uuid_lib.UUID,
    uuid_envio_padre: uuid_lib.UUID | None = None,
) -> MagicMock:
    envio = MagicMock()
    envio.uuid = uuid_lib.uuid4()
    envio.uuid_factura_electronica = uuid_factura_electronica
    envio.estado = "pendiente"
    envio.timestamp_evento = _now()
    envio.uuid_envio_padre = uuid_envio_padre
    envio.cufe = None
    envio.motivo_rechazo = None
    return envio


# ---------------------------------------------------------------------------
# T4.1 — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_factura_electronica_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.1: 12-step chain returns 201 with prefijo+consecutivo+envio_actual.

    Mocked repo helpers + ``assign_consecutivo`` + ``AlertaFactory.fire``
    so the test runs without a DB. Asserts:
      - response shape FacturaElectronicaRead
      - prefijo='SETP' + consecutivo=42 (snapshot from V3 + assign_consecutivo)
      - envio_actual.estado == 'pendiente'
      - envio_actual.uuid_envio_padre is None (initial envio)
      - Cache-Control: no-store header set (DEC-FE-06)
      - session.commit() called exactly once (KD-FE-01)
    """
    import parkos_core.api.v1.facturacion as facturacion_mod

    uuid_factura = uuid_lib.uuid4()
    uuid_sucursal = uuid_lib.uuid4()
    uuid_resolucion = uuid_lib.uuid4()
    payload = _make_payload(uuid_factura=uuid_factura)
    ctx = _make_ctx()
    ctx.sucursal_uuid = uuid_sucursal  # match → no 403

    factura_orm = _make_factura_orm(uuid_factura=uuid_factura, uuid_sucursal=uuid_sucursal)
    resolucion_orm = _make_resolucion_orm(uuid=uuid_resolucion)
    fe_orm = _make_fe_orm(uuid_factura=uuid_factura, uuid_resolucion=uuid_resolucion)
    envio_orm = _make_envio_orm(uuid_factura_electronica=fe_orm.uuid)

    session = AsyncMock()

    # Patch the repo + resolver helpers referenced inside the handler.
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
        facturacion_mod,
        "buscar_resolucion_vigente_por_sucursal",
        AsyncMock(return_value=resolucion_orm),
    )
    monkeypatch.setattr(
        facturacion_mod, "assign_consecutivo", AsyncMock(return_value=42)
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_factura_electronica_inicial",
        AsyncMock(return_value=fe_orm),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "crear_envio_dian_inicial",
        AsyncMock(return_value=envio_orm),
    )

    # Stub the alerta factory to avoid DB.
    factory_instance = MagicMock()
    factory_instance.fire = AsyncMock()
    monkeypatch.setattr(
        facturacion_mod, "AlertaFactory", MagicMock(return_value=factory_instance)
    )

    response = MagicMock()
    response.headers = {}

    result = await create_factura_electronica(response, payload, session, ctx, None)

    # Response shape.
    assert result.prefijo == "SETP"
    assert result.consecutivo == 42
    assert result.uuid_factura == uuid_factura
    assert result.uuid_resolucion_facturacion == uuid_resolucion
    assert result.envio_actual.estado == "pendiente"
    assert result.envio_actual.uuid_envio_padre is None
    assert result.envio_actual.uuid_factura_electronica == fe_orm.uuid

    # DEC-FE-06: Cache-Control: no-store.
    assert response.headers.get("Cache-Control") == "no-store"

    # KD-FE-01: exactly one commit.
    assert session.commit.await_count == 1


# ---------------------------------------------------------------------------
# T4.3 — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_v1_factura_no_encontrada_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.3 V1: missing ``prod.facturas`` row → 404 factura_no_encontrada."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    payload = _make_payload()
    ctx = _make_ctx()
    session = AsyncMock()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=None),
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_electronica(response, payload, session, ctx, None)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "factura_no_encontrada"
    assert exc_info.value.detail["uuid_factura"] == str(payload.uuid_factura)
    # KD-FE-01: no commit happened.
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_create_v2_fe_ya_existe_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.3 V2: existing FE row → 409 factura_electronica_ya_existe."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    uuid_factura = uuid_lib.uuid4()
    payload = _make_payload(uuid_factura=uuid_factura)
    ctx = _make_ctx()
    session = AsyncMock()

    factura_orm = _make_factura_orm(
        uuid_factura=uuid_factura, uuid_sucursal=ctx.sucursal_uuid
    )
    existing_fe = MagicMock()
    existing_fe.uuid = uuid_lib.uuid4()

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=factura_orm),
    )
    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_electronica_por_factura",
        AsyncMock(return_value=existing_fe),
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_electronica(response, payload, session, ctx, None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "factura_electronica_ya_existe"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_create_v3_resolucion_no_vigente_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.3 V3: no vigente resolucion → 409 resolucion_no_vigente."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    uuid_factura = uuid_lib.uuid4()
    payload = _make_payload(uuid_factura=uuid_factura)
    ctx = _make_ctx()
    session = AsyncMock()

    factura_orm = _make_factura_orm(
        uuid_factura=uuid_factura, uuid_sucursal=ctx.sucursal_uuid
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
        facturacion_mod,
        "buscar_resolucion_vigente_por_sucursal",
        AsyncMock(return_value=None),
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_electronica(response, payload, session, ctx, None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "resolucion_no_vigente"
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_create_v4_numeracion_agotada_fires_alerta_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.3 V4: range exhausted → 409 numeracion_agotada + alerta fired."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    uuid_factura = uuid_lib.uuid4()
    payload = _make_payload(uuid_factura=uuid_factura)
    ctx = _make_ctx()
    session = AsyncMock()

    factura_orm = _make_factura_orm(
        uuid_factura=uuid_factura, uuid_sucursal=ctx.sucursal_uuid
    )
    resolucion_orm = _make_resolucion_orm(rango_hasta=5000)

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
        facturacion_mod,
        "buscar_resolucion_vigente_por_sucursal",
        AsyncMock(return_value=resolucion_orm),
    )

    async def _raise_exhausted(*_args, **_kwargs):
        raise ConsecutivoRangeExhaustedError("rango exhausted")

    monkeypatch.setattr(facturacion_mod, "assign_consecutivo", _raise_exhausted)

    factory_instance = MagicMock()
    factory_instance.fire = AsyncMock()
    monkeypatch.setattr(
        facturacion_mod, "AlertaFactory", MagicMock(return_value=factory_instance)
    )

    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_electronica(response, payload, session, ctx, None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "numeracion_agotada"
    assert exc_info.value.detail["prefijo"] == "SETP"
    # DEC-FE-03: alerta fired.
    assert factory_instance.fire.await_count == 1
    # KD-FE-01: no commit (alerta is in the same TX but rolled back with the 409).
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_create_tenant_scope_violation_returns_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4.3 KD-S2 analog: operador cross-branch → 403 tenant_scope_violation."""
    import parkos_core.api.v1.facturacion as facturacion_mod

    uuid_factura = uuid_lib.uuid4()
    payload = _make_payload(uuid_factura=uuid_factura)
    ctx = _make_ctx()
    # Make the ctx.sucursal_uuid DIFFERENT from the factura's.
    other_sucursal = uuid_lib.uuid4()
    ctx.sucursal_uuid = other_sucursal

    factura_orm = _make_factura_orm(
        uuid_factura=uuid_factura, uuid_sucursal=uuid_lib.uuid4()  # different again
    )

    monkeypatch.setattr(
        facturacion_mod.repo_factura_electronica,
        "buscar_factura_por_uuid",
        AsyncMock(return_value=factura_orm),
    )

    session = AsyncMock()
    response = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_factura_electronica(response, payload, session, ctx, None)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "tenant_scope_violation"
    assert session.commit.await_count == 0
