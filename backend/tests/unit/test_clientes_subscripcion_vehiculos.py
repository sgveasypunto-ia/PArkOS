"""HU-F20.2 -- mock-everything handler tests for the dedicated
``POST /clientes/subscripcion-vehiculos`` endpoint
(``api/v1/clientes_subscripcion_vehiculos.py``).

Mirrors ``test_clientes_cupos_e2e.py``'s pattern (HU-F9.2 realineada):
drives the handler function directly (no HTTP client, no real DB) with a
mocked ``AsyncSession``/``Response``, and lets the REAL pure validators
(V5 ``validar_placas_mismo_tipo_vehiculo`` / V6
``validar_cantidad_maxima_vehiculos``) run unmocked so the wiring between
"existing vehiculos + new vehiculo" is actually exercised.

Covers the 3 new 422 codes (HU-F20.2 "Errores"):
``placa_con_suscripcion_vigente``, ``cantidad_vehiculos_excede_plan``,
``tipo_vehiculo_mixto_no_permitido`` -- plus the 404/409 guard rails and
the single-commit + real advisory-lock invariant on the happy path.
"""

from __future__ import annotations

import sys
import uuid as uuid_lib
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


def _make_plan(**overrides) -> MagicMock:
    p = MagicMock()
    p.uuid = overrides.get("uuid", uuid_lib.uuid4())
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
    return s


def _make_vehiculo_inscrito_row(vehiculo: MagicMock) -> MagicMock:
    row = MagicMock()
    row.uuid_subscripcion_vehiculo = uuid_lib.uuid4()
    row.vehiculo = vehiculo
    return row


def _make_detalle(*, plan, subscripcion, vehiculos_inscritos) -> MagicMock:
    d = MagicMock()
    d.subscripcion = subscripcion
    d.plan = plan
    d.vehiculos = vehiculos_inscritos
    return d


def _make_payload(*, uuid_subscripcion_cliente, uuid_vehiculo) -> MagicMock:
    payload = MagicMock()
    payload.uuid_subscripcion_cliente = uuid_subscripcion_cliente
    payload.uuid_vehiculo = uuid_vehiculo
    return payload


def _session_with_vehiculo(vehiculo: MagicMock) -> MagicMock:
    """``session.execute(...)`` returns a result whose
    ``scalar_one_or_none()`` is ``vehiculo`` -- used both by the handler's
    own vehiculo lookup AND (harmlessly, return value unused) by
    ``crear_subscripcion_vehiculos_bulk``'s advisory-lock call."""
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = vehiculo
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    # ``crear_subscripcion_vehiculos_bulk`` builds a real ``SubscripcionVehiculos``
    # ORM instance without a PK (``uuid`` is a DB ``server_default
    # gen_random_uuid()``) -- a real ``session.refresh`` would populate it
    # post-INSERT. Simulate that write-back so the handler's
    # ``SubscripcionVehiculosRead.model_validate(nuevo)`` has a non-None uuid.
    async def _fake_refresh(row: MagicMock) -> None:
        if getattr(row, "uuid", None) is None:
            row.uuid = uuid_lib.uuid4()

    session.refresh = AsyncMock(side_effect=_fake_refresh)
    return session


# ---------------------------------------------------------------------------
# Happy path -- single commit + real advisory lock (not mocked away).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculo_happy_path_single_commit() -> None:
    from parkos_core.api.v1 import clientes_subscripcion_vehiculos as handler_mod

    plan = _make_plan(cantidad_maxima_vehiculos=2, mismo_tipo_vehiculo=False)
    subscripcion = _make_subscripcion()
    existing_vehiculo = _make_vehiculo(placa="OLD111")
    detalle = _make_detalle(
        plan=plan,
        subscripcion=subscripcion,
        vehiculos_inscritos=[_make_vehiculo_inscrito_row(existing_vehiculo)],
    )
    nuevo_vehiculo = _make_vehiculo(placa="NEW123")
    payload = _make_payload(
        uuid_subscripcion_cliente=subscripcion.uuid, uuid_vehiculo=nuevo_vehiculo.uuid
    )

    session = _session_with_vehiculo(nuevo_vehiculo)
    m_lookup = AsyncMock(return_value=detalle)
    m_validar_vigente = AsyncMock(return_value=None)

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta,
            "validar_vehiculo_sin_suscripcion_vigente_distinta",
            new=m_validar_vigente,
        ),
    ):
        result = await handler_mod.crear_subscripcion_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
            _perm=None,
        )

    session.commit.assert_awaited_once()
    assert result.uuid_vehiculo == nuevo_vehiculo.uuid
    assert result.uuid_subscripcion_cliente == subscripcion.uuid


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculo_subscripcion_no_encontrada_404() -> None:
    from parkos_core.api.v1 import clientes_subscripcion_vehiculos as handler_mod
    from parkos_core.repo import cupos_subscripcion as repo_cupos

    payload = _make_payload(
        uuid_subscripcion_cliente=uuid_lib.uuid4(), uuid_vehiculo=uuid_lib.uuid4()
    )
    session = MagicMock()
    m_lookup = AsyncMock(
        side_effect=repo_cupos.SubscripcionNoEncontradaError(detalle="x")
    )

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.crear_subscripcion_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
            _perm=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "subscripcion_no_encontrada"


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculo_vehiculo_no_encontrado_404() -> None:
    from parkos_core.api.v1 import clientes_subscripcion_vehiculos as handler_mod

    plan = _make_plan()
    subscripcion = _make_subscripcion()
    detalle = _make_detalle(plan=plan, subscripcion=subscripcion, vehiculos_inscritos=[])
    payload = _make_payload(
        uuid_subscripcion_cliente=subscripcion.uuid, uuid_vehiculo=uuid_lib.uuid4()
    )

    session = _session_with_vehiculo(None)  # vehiculo lookup misses
    m_lookup = AsyncMock(return_value=detalle)

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.crear_subscripcion_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
            _perm=None,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "vehiculo_no_encontrado"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculo_ya_inscrito_409() -> None:
    from parkos_core.api.v1 import clientes_subscripcion_vehiculos as handler_mod

    plan = _make_plan(cantidad_maxima_vehiculos=5)
    subscripcion = _make_subscripcion()
    vehiculo = _make_vehiculo(placa="DUP123")
    detalle = _make_detalle(
        plan=plan,
        subscripcion=subscripcion,
        vehiculos_inscritos=[_make_vehiculo_inscrito_row(vehiculo)],
    )
    # Same vehiculo uuid requested again.
    payload = _make_payload(
        uuid_subscripcion_cliente=subscripcion.uuid, uuid_vehiculo=vehiculo.uuid
    )

    session = _session_with_vehiculo(vehiculo)
    m_lookup = AsyncMock(return_value=detalle)

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.crear_subscripcion_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
            _perm=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "vehiculo_ya_inscrito"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculo_placa_con_suscripcion_vigente_422() -> None:
    """BR3/E1 (NEW): vehiculo already active on a DIFFERENT subscripcion."""
    from parkos_core.api.v1 import clientes_subscripcion_vehiculos as handler_mod
    from parkos_core.repo import venta_suscripcion as repo_venta

    plan = _make_plan(cantidad_maxima_vehiculos=5, mismo_tipo_vehiculo=False)
    subscripcion = _make_subscripcion()
    detalle = _make_detalle(plan=plan, subscripcion=subscripcion, vehiculos_inscritos=[])
    nuevo_vehiculo = _make_vehiculo(placa="OTRO456")
    payload = _make_payload(
        uuid_subscripcion_cliente=subscripcion.uuid, uuid_vehiculo=nuevo_vehiculo.uuid
    )

    session = _session_with_vehiculo(nuevo_vehiculo)
    m_lookup = AsyncMock(return_value=detalle)
    m_validar_vigente = AsyncMock(
        side_effect=repo_venta.PlacaConSuscripcionVigenteError(
            uuid_vehiculo=nuevo_vehiculo.uuid
        )
    )

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta,
            "validar_vehiculo_sin_suscripcion_vigente_distinta",
            new=m_validar_vigente,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.crear_subscripcion_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
            _perm=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "placa_con_suscripcion_vigente"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculo_cantidad_vehiculos_excede_plan_422() -> None:
    """V6 real (unmocked): cupo=1, ya hay 1 inscrito -> 422 sin tocar la DB."""
    from parkos_core.api.v1 import clientes_subscripcion_vehiculos as handler_mod

    plan = _make_plan(cantidad_maxima_vehiculos=1, mismo_tipo_vehiculo=False)
    subscripcion = _make_subscripcion()
    existing_vehiculo = _make_vehiculo(placa="OLD111")
    detalle = _make_detalle(
        plan=plan,
        subscripcion=subscripcion,
        vehiculos_inscritos=[_make_vehiculo_inscrito_row(existing_vehiculo)],
    )
    nuevo_vehiculo = _make_vehiculo(placa="NEW123")
    payload = _make_payload(
        uuid_subscripcion_cliente=subscripcion.uuid, uuid_vehiculo=nuevo_vehiculo.uuid
    )

    session = _session_with_vehiculo(nuevo_vehiculo)
    m_lookup = AsyncMock(return_value=detalle)
    m_validar_vigente = AsyncMock(return_value=None)

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta,
            "validar_vehiculo_sin_suscripcion_vigente_distinta",
            new=m_validar_vigente,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.crear_subscripcion_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
            _perm=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "cantidad_vehiculos_excede_plan"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_crear_subscripcion_vehiculo_tipo_vehiculo_mixto_no_permitido_422() -> None:
    """V5 real (unmocked): mismo_tipo_vehiculo=True + tipos distintos -> 422."""
    from parkos_core.api.v1 import clientes_subscripcion_vehiculos as handler_mod

    tipo_carro = uuid_lib.uuid4()
    tipo_moto = uuid_lib.uuid4()
    plan = _make_plan(cantidad_maxima_vehiculos=5, mismo_tipo_vehiculo=True)
    subscripcion = _make_subscripcion()
    existing_vehiculo = _make_vehiculo(placa="ABC123", uuid_tipo_vehiculo=tipo_carro)
    detalle = _make_detalle(
        plan=plan,
        subscripcion=subscripcion,
        vehiculos_inscritos=[_make_vehiculo_inscrito_row(existing_vehiculo)],
    )
    nuevo_vehiculo = _make_vehiculo(placa="MOT001", uuid_tipo_vehiculo=tipo_moto)
    payload = _make_payload(
        uuid_subscripcion_cliente=subscripcion.uuid, uuid_vehiculo=nuevo_vehiculo.uuid
    )

    session = _session_with_vehiculo(nuevo_vehiculo)
    m_lookup = AsyncMock(return_value=detalle)
    m_validar_vigente = AsyncMock(return_value=None)

    with (
        patch.object(
            handler_mod.repo_cupos, "buscar_subscripcion_con_vehiculos_por_uuid", new=m_lookup
        ),
        patch.object(
            handler_mod.repo_venta,
            "validar_vehiculo_sin_suscripcion_vigente_distinta",
            new=m_validar_vigente,
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await handler_mod.crear_subscripcion_vehiculo(
            response=_new_response(),
            payload=payload,
            session=session,
            ctx=_make_ctx(),
            _claims=None,
            _perm=None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "tipo_vehiculo_mixto_no_permitido"
    session.commit.assert_not_awaited()
