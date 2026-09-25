"""HU-F9.2 realineada -- mock-everything handler tests for the 4 dedicated
cupos-management endpoints (mirrors ``test_venta_suscripcion_e2e.py``).

Drives each handler function directly (no HTTP client, no DB) with
mocked repo helpers + a mocked ``AsyncSession``/``Response``. Validates:

  * The 3 read/write happy paths return the expected response shape.
  * V5 (mismo_tipo_vehiculo) + V6 (cantidad_maxima_vehiculos) run with
    the REAL pure functions from ``repo.venta_suscripcion`` (not mocked)
    so the wiring between "existing vehiculos + new placa" is actually
    exercised, not just assumed.
  * Each typed repo exception maps to the right HTTP status/error code.
  * Exactly one ``await session.commit()`` per write handler
    (KD-VENTA-01 mirror).
"""

from __future__ import annotations

import sys
import uuid as uuid_lib
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.sucursal_uuid = uuid_lib.uuid4()
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _make_cliente(**overrides) -> MagicMock:
    c = MagicMock()
    c.uuid = overrides.get("uuid", uuid_lib.uuid4())
    c.nombre = overrides.get("nombre", "Juan")
    c.apellido = overrides.get("apellido", "Perez")
    c.numero_identificacion = overrides.get("numero_identificacion", "1234567890")
    return c


def _make_plan(**overrides) -> MagicMock:
    p = MagicMock()
    p.uuid = overrides.get("uuid", uuid_lib.uuid4())
    p.tipo = overrides.get("tipo", "mensual_carro")
    p.valor = overrides.get("valor", Decimal("30000.00"))
    p.cantidad_maxima_vehiculos = overrides.get("cantidad_maxima_vehiculos", 2)
    p.mismo_tipo_vehiculo = overrides.get("mismo_tipo_vehiculo", False)
    return p


def _make_vehiculo(**overrides) -> MagicMock:
    v = MagicMock()
    v.uuid = overrides.get("uuid", uuid_lib.uuid4())
    v.placa = overrides.get("placa", "ABC123")
    v.uuid_tipo_vehiculo = overrides.get("uuid_tipo_vehiculo", uuid_lib.uuid4())
    return v


def _make_subscripcion(**overrides) -> MagicMock:
    s = MagicMock()
    s.uuid = overrides.get("uuid", uuid_lib.uuid4())
    s.uuid_subscripcion_cliente = overrides.get("uuid_subscripcion_cliente", uuid_lib.uuid4())
    s.fecha_inicio_cobertura = overrides.get("fecha_inicio_cobertura")
    s.fecha_vencimiento = overrides.get("fecha_vencimiento")
    return s


def _make_vehiculo_inscrito_row(vehiculo: MagicMock) -> MagicMock:
    row = MagicMock()
    row.uuid_subscripcion_vehiculo = uuid_lib.uuid4()
    row.vehiculo = vehiculo
    return row


def _make_detalle(*, plan, cliente, subscripcion, vehiculos_inscritos) -> MagicMock:
    d = MagicMock()
    d.subscripcion = subscripcion
    d.cliente = cliente
    d.plan = plan
    d.vehiculos = vehiculos_inscritos
    return d


# ---------------------------------------------------------------------------
# GET /clientes/subscripciones-activas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listar_subscripciones_activas_happy_path() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod
    from parkos_core.repo.cupos_subscripcion import SubscripcionActivaRow

    plan = _make_plan(cantidad_maxima_vehiculos=5)
    cliente = _make_cliente()
    subscripcion = _make_subscripcion()
    row = SubscripcionActivaRow(
        subscripcion=subscripcion, cliente=cliente, plan=plan, vehiculos_inscritos=3
    )

    session = MagicMock()
    m_list = AsyncMock(return_value=[row])
    with patch.object(handler_mod.repo_cupos, "listar_subscripciones_activas", new=m_list):
        result = await handler_mod.listar_subscripciones_activas(
            session=session, _ctx=_make_ctx(), _claims=None
        )

    assert len(result.items) == 1
    item = result.items[0]
    assert item.uuid == subscripcion.uuid
    assert item.cliente.numero_identificacion == cliente.numero_identificacion
    assert item.cupo_maximo == 5
    assert item.vehiculos_inscritos == 3


# ---------------------------------------------------------------------------
# GET /clientes/subscripciones-activas/buscar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_por_identificacion_found_computes_cupo_disponible() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod

    plan = _make_plan(cantidad_maxima_vehiculos=3)
    cliente = _make_cliente(numero_identificacion="999888777")
    subscripcion = _make_subscripcion()
    vehiculo = _make_vehiculo(placa="ZZZ999")
    inscrito = _make_vehiculo_inscrito_row(vehiculo)
    detalle = _make_detalle(
        plan=plan, cliente=cliente, subscripcion=subscripcion, vehiculos_inscritos=[inscrito]
    )

    session = MagicMock()
    m_buscar = AsyncMock(return_value=detalle)
    with patch.object(
        handler_mod.repo_cupos, "buscar_subscripcion_activa_por_identificacion", new=m_buscar
    ):
        result = await handler_mod.buscar_subscripcion_por_identificacion(
            numero_identificacion="999888777", session=session, _ctx=_make_ctx(), _claims=None
        )

    assert result is not None
    assert result.uuid == subscripcion.uuid
    assert result.cupo_maximo == 3
    assert result.cupo_disponible == 2  # 3 - 1 inscrito
    assert len(result.vehiculos) == 1
    assert result.vehiculos[0].placa == "ZZZ999"


@pytest.mark.asyncio
async def test_buscar_por_identificacion_sin_resultado_devuelve_none() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod

    session = MagicMock()
    m_buscar = AsyncMock(return_value=None)
    with patch.object(
        handler_mod.repo_cupos, "buscar_subscripcion_activa_por_identificacion", new=m_buscar
    ):
        result = await handler_mod.buscar_subscripcion_por_identificacion(
            numero_identificacion="000000000", session=session, _ctx=_make_ctx(), _claims=None
        )

    assert result is None


# ---------------------------------------------------------------------------
# POST /clientes/subscripcion-vehiculos/agregar
# ---------------------------------------------------------------------------


def _build_agregar_payload(*, uuid_subscripcion_cliente, placa="NEW123") -> MagicMock:
    payload = MagicMock()
    payload.uuid_subscripcion_cliente = uuid_subscripcion_cliente
    payload.placa = placa
    return payload


@pytest.mark.asyncio
async def test_agregar_vehiculo_happy_path_single_commit() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod

    plan = _make_plan(cantidad_maxima_vehiculos=2, mismo_tipo_vehiculo=False)
    cliente = _make_cliente()
    subscripcion = _make_subscripcion()
    existing_vehiculo = _make_vehiculo(placa="ABC123")
    existing_inscrito = _make_vehiculo_inscrito_row(existing_vehiculo)
    detalle_antes = _make_detalle(
        plan=plan,
        cliente=cliente,
        subscripcion=subscripcion,
        vehiculos_inscritos=[existing_inscrito],
    )
    nuevo_vehiculo = _make_vehiculo(placa="NEW123")
    detalle_despues = _make_detalle(
        plan=plan,
        cliente=cliente,
        subscripcion=subscripcion,
        vehiculos_inscritos=[existing_inscrito, _make_vehiculo_inscrito_row(nuevo_vehiculo)],
    )

    session = MagicMock()
    session.commit = AsyncMock()
    payload = _build_agregar_payload(uuid_subscripcion_cliente=subscripcion.uuid)

    m_lookup = AsyncMock(side_effect=[detalle_antes, detalle_despues])
    m_buscar_o_crear = AsyncMock(return_value=(nuevo_vehiculo, True))
    m_agregar = AsyncMock()

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa", new=m_buscar_o_crear
        ),
        patch.object(handler_mod.repo_cupos, "agregar_vehiculo_a_subscripcion", new=m_agregar),
    ):
        result = await handler_mod.agregar_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
        )

    session.commit.assert_called_once()
    m_agregar.assert_awaited_once()
    assert len(result.vehiculos) == 2
    assert result.cupo_disponible == 0  # 2 max, 2 inscritos


@pytest.mark.asyncio
async def test_agregar_vehiculo_cantidad_maxima_excedida_no_commit() -> None:
    """V6 real (no mockeado): cupo=1, ya hay 1 inscrito -> 422 sin tocar la DB."""
    from parkos_core.api.v1 import clientes_cupos as handler_mod

    plan = _make_plan(cantidad_maxima_vehiculos=1, mismo_tipo_vehiculo=False)
    cliente = _make_cliente()
    subscripcion = _make_subscripcion()
    existing_vehiculo = _make_vehiculo(placa="ABC123")
    detalle = _make_detalle(
        plan=plan,
        cliente=cliente,
        subscripcion=subscripcion,
        vehiculos_inscritos=[_make_vehiculo_inscrito_row(existing_vehiculo)],
    )
    nuevo_vehiculo = _make_vehiculo(placa="NEW123")

    session = MagicMock()
    session.commit = AsyncMock()
    payload = _build_agregar_payload(uuid_subscripcion_cliente=subscripcion.uuid)

    m_lookup = AsyncMock(return_value=detalle)
    m_buscar_o_crear = AsyncMock(return_value=(nuevo_vehiculo, True))
    m_agregar = AsyncMock()

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa", new=m_buscar_o_crear
        ),
        patch.object(handler_mod.repo_cupos, "agregar_vehiculo_a_subscripcion", new=m_agregar),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.agregar_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "cantidad_maxima_excedida"
    session.commit.assert_not_called()
    m_agregar.assert_not_awaited()


@pytest.mark.asyncio
async def test_agregar_vehiculo_tipo_incompatible_no_commit() -> None:
    """V5 real (no mockeado): mismo_tipo_vehiculo=True + tipos distintos -> 422."""
    from parkos_core.api.v1 import clientes_cupos as handler_mod

    tipo_carro = uuid_lib.uuid4()
    tipo_moto = uuid_lib.uuid4()
    plan = _make_plan(cantidad_maxima_vehiculos=5, mismo_tipo_vehiculo=True)
    cliente = _make_cliente()
    subscripcion = _make_subscripcion()
    existing_vehiculo = _make_vehiculo(placa="ABC123", uuid_tipo_vehiculo=tipo_carro)
    detalle = _make_detalle(
        plan=plan,
        cliente=cliente,
        subscripcion=subscripcion,
        vehiculos_inscritos=[_make_vehiculo_inscrito_row(existing_vehiculo)],
    )
    nuevo_vehiculo = _make_vehiculo(placa="MOT001", uuid_tipo_vehiculo=tipo_moto)

    session = MagicMock()
    session.commit = AsyncMock()
    payload = _build_agregar_payload(uuid_subscripcion_cliente=subscripcion.uuid)

    m_lookup = AsyncMock(return_value=detalle)
    m_buscar_o_crear = AsyncMock(return_value=(nuevo_vehiculo, True))
    m_agregar = AsyncMock()

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa", new=m_buscar_o_crear
        ),
        patch.object(handler_mod.repo_cupos, "agregar_vehiculo_a_subscripcion", new=m_agregar),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.agregar_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "tipo_vehiculo_incompatible"
    session.commit.assert_not_called()
    m_agregar.assert_not_awaited()


@pytest.mark.asyncio
async def test_agregar_vehiculo_subscripcion_no_encontrada() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod
    from parkos_core.repo.cupos_subscripcion import SubscripcionNoEncontradaError

    session = MagicMock()
    payload = _build_agregar_payload(uuid_subscripcion_cliente=uuid_lib.uuid4())

    m_lookup = AsyncMock(side_effect=SubscripcionNoEncontradaError(detalle="x"))
    with patch.object(
        handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
    ), pytest.raises(HTTPException) as exc_info:
        await handler_mod.agregar_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "subscripcion_no_encontrada"


@pytest.mark.asyncio
async def test_agregar_vehiculo_ya_inscrito_no_commit() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod
    from parkos_core.repo.cupos_subscripcion import VehiculoYaInscritoError

    plan = _make_plan(cantidad_maxima_vehiculos=5, mismo_tipo_vehiculo=False)
    cliente = _make_cliente()
    subscripcion = _make_subscripcion()
    existing_vehiculo = _make_vehiculo(placa="ABC123")
    detalle = _make_detalle(
        plan=plan,
        cliente=cliente,
        subscripcion=subscripcion,
        vehiculos_inscritos=[_make_vehiculo_inscrito_row(existing_vehiculo)],
    )
    nuevo_vehiculo = _make_vehiculo(placa="ABC123")

    session = MagicMock()
    session.commit = AsyncMock()
    payload = _build_agregar_payload(uuid_subscripcion_cliente=subscripcion.uuid, placa="ABC123")

    m_lookup = AsyncMock(return_value=detalle)
    m_buscar_o_crear = AsyncMock(return_value=(nuevo_vehiculo, False))
    m_agregar = AsyncMock(side_effect=VehiculoYaInscritoError(placa="ABC123"))

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta, "buscar_o_crear_vehiculo_por_placa", new=m_buscar_o_crear
        ),
        patch.object(handler_mod.repo_cupos, "agregar_vehiculo_a_subscripcion", new=m_agregar),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.agregar_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "vehiculo_ya_inscrito"
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# PUT /clientes/subscripcion-vehiculos/{uuid}/quitar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quitar_vehiculo_happy_path_single_commit() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod

    uuid_subscripcion_vehiculo = uuid_lib.uuid4()
    uuid_subscripcion_cliente = uuid_lib.uuid4()

    cerrado = MagicMock()
    cerrado.uuid_subscripcion_cliente = uuid_subscripcion_cliente

    plan = _make_plan(cantidad_maxima_vehiculos=2)
    cliente = _make_cliente()
    subscripcion = _make_subscripcion(uuid=uuid_subscripcion_cliente)
    detalle_despues = _make_detalle(
        plan=plan, cliente=cliente, subscripcion=subscripcion, vehiculos_inscritos=[]
    )

    session = MagicMock()
    session.commit = AsyncMock()

    m_quitar = AsyncMock(return_value=cerrado)
    m_lookup = AsyncMock(return_value=detalle_despues)

    with (
        patch.object(handler_mod.repo_cupos, "quitar_vehiculo_de_subscripcion", new=m_quitar),
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
    ):
        result = await handler_mod.quitar_vehiculo(
            response=_new_response(),
            uuid=uuid_subscripcion_vehiculo,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
        )

    session.commit.assert_called_once()
    assert result.vehiculos == []
    assert result.cupo_disponible == 2


@pytest.mark.asyncio
async def test_quitar_vehiculo_no_encontrado_no_commit() -> None:
    from parkos_core.api.v1 import clientes_cupos as handler_mod
    from parkos_core.repo.versioned import RowNotFoundError

    session = MagicMock()
    session.commit = AsyncMock()

    m_quitar = AsyncMock(side_effect=RowNotFoundError("no active row"))
    with (
        patch.object(handler_mod.repo_cupos, "quitar_vehiculo_de_subscripcion", new=m_quitar),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.quitar_vehiculo(
            response=_new_response(),
            uuid=uuid_lib.uuid4(),
            session=session,
            ctx=_make_ctx(),
            _claims=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "vehiculo_inscrito_no_encontrado"
    session.commit.assert_not_called()
