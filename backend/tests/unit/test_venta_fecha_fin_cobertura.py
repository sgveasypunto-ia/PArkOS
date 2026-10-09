"""Suscripciones bug 6 -- fecha de fin de cobertura editable (solo acortar).

Regla: el operador puede ajustar el fin dentro de
``[fecha_inicio_cobertura, inicio + duracion_dias - 1]``. Nunca extender
mas alla de lo pagado. Sin el campo, el calculo actual queda intacto. El
valor cobrado NO cambia (sin prorrateo, PT-3).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "parkos_core" / "src"))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

INICIO = date(2026, 9, 20)
MAXIMO = date(2026, 10, 19)  # 30 dias: 20/09 + 29


# ---------------------------------------------------------------------------
# Repo: validar_fecha_fin_cobertura
# ---------------------------------------------------------------------------


def test_sin_fecha_solicitada_devuelve_el_calculo_del_plan() -> None:
    from parkos_core.repo import venta_suscripcion as repo

    assert (
        repo.resolver_fecha_fin_cobertura(
            fecha_inicio_cobertura=INICIO, fecha_fin_plan=MAXIMO, fecha_fin_solicitada=None
        )
        == MAXIMO
    )


@pytest.mark.parametrize(
    "solicitada", [date(2026, 9, 20), date(2026, 10, 5), date(2026, 10, 19)]
)
def test_fin_dentro_del_rango_se_acepta(solicitada: date) -> None:
    from parkos_core.repo import venta_suscripcion as repo

    assert (
        repo.resolver_fecha_fin_cobertura(
            fecha_inicio_cobertura=INICIO,
            fecha_fin_plan=MAXIMO,
            fecha_fin_solicitada=solicitada,
        )
        == solicitada
    )


@pytest.mark.parametrize("solicitada", [date(2026, 10, 20), date(2027, 1, 1)])
def test_fin_mayor_al_calculado_se_rechaza(solicitada: date) -> None:
    from parkos_core.repo import venta_suscripcion as repo

    with pytest.raises(repo.FechaFinFueraDeRangoError) as exc:
        repo.resolver_fecha_fin_cobertura(
            fecha_inicio_cobertura=INICIO,
            fecha_fin_plan=MAXIMO,
            fecha_fin_solicitada=solicitada,
        )
    assert exc.value.fecha_fin_maxima == MAXIMO
    assert exc.value.fecha_inicio_cobertura == INICIO
    assert exc.value.fecha_fin_solicitada == solicitada


def test_fin_menor_al_inicio_se_rechaza() -> None:
    from parkos_core.repo import venta_suscripcion as repo

    with pytest.raises(repo.FechaFinFueraDeRangoError):
        repo.resolver_fecha_fin_cobertura(
            fecha_inicio_cobertura=INICIO,
            fecha_fin_plan=MAXIMO,
            fecha_fin_solicitada=date(2026, 9, 19),
        )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def _body(**extra: object) -> dict:
    return {
        "uuid_cliente": str(uuid_lib.uuid4()),
        "placas": ["ABC123"],
        "uuid_tipo_subscripcion": str(uuid_lib.uuid4()),
        "fecha_inicio_cobertura": "2026-09-20",
        **extra,
    }


def test_schema_acepta_fecha_fin_cobertura_opcional() -> None:
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    assert VentaSuscripcionCreate(**_body()).fecha_fin_cobertura is None
    assert VentaSuscripcionCreate(
        **_body(fecha_fin_cobertura="2026-10-05")
    ).fecha_fin_cobertura == date(2026, 10, 5)


def test_schema_rechaza_fecha_fin_invalida() -> None:
    from parkos_core.schemas.clientes import VentaSuscripcionCreate

    with pytest.raises(ValidationError):
        VentaSuscripcionCreate(**_body(fecha_fin_cobertura="no-es-fecha"))


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.sucursal_uuid = uuid_lib.uuid4()
    return ctx


def _response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _payload(*, fecha_fin: date | None, placas: list[str] | None = None) -> MagicMock:
    p = MagicMock()
    p.cliente = None
    p.uuid_cliente = uuid_lib.uuid4()
    p.placas = placas if placas is not None else ["ABC123"]
    p.uuid_tipo_subscripcion = uuid_lib.uuid4()
    p.fecha_inicio_cobertura = INICIO
    p.fecha_fin_cobertura = fecha_fin
    p.cobrar_ahora = False
    p.emitir_factura_electronica = False
    p.medio_pago = "efectivo"
    p.referencia = None
    return p


def _plan() -> MagicMock:
    plan = MagicMock()
    plan.uuid = uuid_lib.uuid4()
    plan.valor = Decimal("30000.00")
    plan.duracion_dias = 30
    plan.mismo_tipo_vehiculo = True
    plan.cantidad_maxima_vehiculos = 2
    return plan


async def _llamar(fecha_fin: date | None, placas: list[str] | None = None):
    from parkos_core.api.v1 import clientes_venta as h

    session = MagicMock()
    session.commit = AsyncMock()
    sub = MagicMock()
    sub.uuid = uuid_lib.uuid4()
    veh = MagicMock()
    veh.uuid = uuid_lib.uuid4()
    cliente = MagicMock()
    cliente.uuid = uuid_lib.uuid4()
    crear = AsyncMock(return_value=sub)
    auditoria = AsyncMock()
    with patch.object(
        h.repo_venta, "buscar_tipo_subscripcion_vigente_por_uuid",
        new=AsyncMock(return_value=_plan()),
    ), patch.object(
        h.repo_venta, "buscar_cliente_por_uuid_o_crear", new=AsyncMock(return_value=cliente),
    ), patch.object(
        h.repo_venta, "buscar_o_crear_vehiculo_por_placa",
        new=AsyncMock(return_value=(veh, False)),
    ), patch.object(h.repo_venta, "validar_placas_mismo_tipo_vehiculo"), patch.object(
        h.repo_venta, "validar_cantidad_maxima_vehiculos"
    ), patch.object(
        h.repo_venta, "validar_placa_duplicada_subscripcion", new=AsyncMock()
    ), patch.object(h.repo_venta, "crear_subscripcion_cliente", new=crear), patch.object(
        h.repo_venta, "crear_subscripcion_vehiculos_bulk", new=AsyncMock(return_value=[veh])
    ), patch.object(h.repo_venta, "registrar_ajuste_fin_vigencia", new=auditoria):
        try:
            result = await h.venta_suscripcion(
                response=_response(),
                payload=_payload(fecha_fin=fecha_fin, placas=placas),
                session=session,
                ctx=_ctx(),
                _claims=None,
            )
        except HTTPException as exc:
            return None, crear, auditoria, session, exc
    return result, crear, auditoria, session, None


@pytest.mark.asyncio
async def test_handler_fin_acortado_se_persiste_y_se_audita() -> None:
    result, crear, auditoria, session, exc = await _llamar(date(2026, 10, 5))
    assert exc is None
    assert crear.await_args.kwargs["fecha_vencimiento"] == date(2026, 10, 5)
    assert result.fecha_vencimiento == date(2026, 10, 5)
    # El valor cobrado NO cambia (sin prorrateo).
    assert result.valor_total_plan == Decimal("30000.00")
    assert auditoria.await_count == 1
    kw = auditoria.await_args.kwargs
    assert kw["fecha_fin_plan"] == MAXIMO
    assert kw["fecha_fin_efectiva"] == date(2026, 10, 5)
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_handler_sin_campo_conserva_el_calculo_y_no_audita() -> None:
    result, crear, auditoria, _session, exc = await _llamar(None)
    assert exc is None
    assert crear.await_args.kwargs["fecha_vencimiento"] == MAXIMO
    assert result.fecha_vencimiento == MAXIMO
    assert auditoria.await_count == 0


@pytest.mark.asyncio
async def test_handler_fin_igual_al_calculado_no_audita() -> None:
    result, _crear, auditoria, _s, exc = await _llamar(MAXIMO)
    assert exc is None
    assert result.fecha_vencimiento == MAXIMO
    assert auditoria.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("fin", [date(2026, 10, 20), date(2026, 9, 19)])
async def test_handler_fin_fuera_de_rango_422_sin_escribir(fin: date) -> None:
    _r, crear, auditoria, session, exc = await _llamar(fin)
    assert exc is not None
    assert exc.status_code == 422
    assert exc.detail["error"] == "fecha_fin_fuera_de_rango"
    assert exc.detail["message"]
    assert exc.detail["fecha_inicio_cobertura"] == "2026-09-20"
    assert exc.detail["fecha_fin_maxima"] == "2026-10-19"
    assert exc.headers == {"Cache-Control": "no-store"}
    assert crear.await_count == 0
    assert auditoria.await_count == 0
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_handler_dos_vehiculos_comparten_el_fin_ajustado() -> None:
    result, crear, _a, _s, exc = await _llamar(date(2026, 10, 1), placas=["ABC123", "DEF456"])
    assert exc is None
    assert crear.await_count == 1  # una sola suscripcion para ambas placas
    assert result.fecha_vencimiento == date(2026, 10, 1)
    assert len(result.uuid_vehiculos) == 2


# ---------------------------------------------------------------------------
# Auditoria + idempotencia
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auditoria_agrega_fila_en_hash_chain_sin_mutar() -> None:
    from parkos_core.repo import venta_suscripcion as repo

    sub = MagicMock()
    sub.uuid = uuid_lib.uuid4()
    actor, suc = uuid_lib.uuid4(), uuid_lib.uuid4()
    with patch.object(repo.hash_chain, "append", new=AsyncMock()) as append:
        await repo.registrar_ajuste_fin_vigencia(
            MagicMock(),
            actor_uuid=actor,
            uuid_sucursal=suc,
            uuid_subscripcion=sub.uuid,
            fecha_inicio_cobertura=INICIO,
            fecha_fin_plan=MAXIMO,
            fecha_fin_efectiva=date(2026, 10, 5),
        )
    payload = append.await_args.args[2]
    assert payload["accion"] == "ajustar_fin_vigencia"
    assert payload["uuid_registro_afectado"] == sub.uuid
    assert payload["uuid_sucursal"] == suc
    assert payload["datos_anteriores"]["fecha_vencimiento"] == "2026-10-19"
    assert payload["datos_nuevos"]["fecha_vencimiento"] == "2026-10-05"


def test_idempotencia_cuerpo_distinto_no_reutiliza_la_misma_huella() -> None:
    """Misma key + otro fin => huella distinta (no se reproduce la respuesta vieja)."""
    from parkos_core.api import middleware

    a = middleware._hash_request_body(b'{"fecha_fin_cobertura":"2026-10-05"}')
    b = middleware._hash_request_body(b'{"fecha_fin_cobertura":"2026-10-06"}')
    c = middleware._hash_request_body(b'{"fecha_fin_cobertura":"2026-10-05"}')
    assert a != b
    assert a == c
