"""Always-on FE emission (``repo/fe_emision.py``): standard customer, failure ->
pending -> automatic retry -> admin alert, and consecutivo idempotency.

DB-free: the session is a small double and the repo collaborators are
patched, exactly like the neighbouring ``test_venta_suscripcion*`` tests.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.constants import CLIENTE_ESTANDAR_UUID
from parkos_core.models.L_W.alerta import Alerta
from parkos_core.repo import fe_emision
from parkos_core.repo.fe_emision import (
    ALERTA_FALLIDA,
    ALERTA_PENDIENTE,
    BACKOFF_S,
    MAX_REINTENTOS,
    FeEmisionResultado,
    FeRetryScheduler,
    emitir_fe_para_pago,
    reintentar_pendientes,
)
from parkos_core.repo.resolucion_facturacion import ConsecutivoRangeExhaustedError

FACTURA = uuid_lib.uuid4()
SUCURSAL = uuid_lib.uuid4()
ACTOR = uuid_lib.uuid4()


class _Nested:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> bool:
        return False  # never swallow


def _session(*, pending_marker_exists: bool = False) -> MagicMock:
    session = MagicMock(name="AsyncSession")
    factura = MagicMock()
    factura.uuid_sucursal = SUCURSAL
    factura.descuento = 0
    session.factura = factura
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.begin_nested = MagicMock(side_effect=lambda: _Nested())
    dedupe = MagicMock()
    dedupe.first = MagicMock(return_value=(1,) if pending_marker_exists else None)
    session.execute = AsyncMock(return_value=dedupe)
    return session


@pytest.fixture
def repos(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    resolucion = MagicMock()
    resolucion.uuid = uuid_lib.uuid4()
    resolucion.prefijo = "SETP"
    fe_row = MagicMock()
    fe_row.uuid = uuid_lib.uuid4()
    envio_row = MagicMock()
    envio_row.uuid = uuid_lib.uuid4()
    mocks = {
        "existente": AsyncMock(return_value=None),
        "factura": AsyncMock(side_effect=lambda session, _uuid: session.factura),
        "resolucion": AsyncMock(return_value=resolucion),
        "consecutivo": AsyncMock(return_value=42),
        "crear_fe": AsyncMock(return_value=fe_row),
        "crear_envio": AsyncMock(return_value=envio_row),
    }
    monkeypatch.setattr(
        fe_emision.repo_fe, "buscar_factura_electronica_por_factura", mocks["existente"]
    )
    monkeypatch.setattr(
        fe_emision.repo_resolucion,
        "buscar_resolucion_vigente_por_sucursal",
        mocks["resolucion"],
    )
    monkeypatch.setattr(fe_emision.repo_resolucion, "assign_consecutivo", mocks["consecutivo"])
    monkeypatch.setattr(fe_emision, "_buscar_factura", mocks["factura"])
    monkeypatch.setattr(
        fe_emision.repo_fe, "crear_factura_electronica_inicial", mocks["crear_fe"]
    )
    monkeypatch.setattr(fe_emision.repo_fe, "crear_envio_dian_inicial", mocks["crear_envio"])
    mocks["fe_row"] = fe_row  # type: ignore[assignment]
    mocks["envio_row"] = envio_row  # type: ignore[assignment]
    return mocks


def _marker(session: MagicMock) -> Alerta | None:
    for call in session.add.call_args_list:
        obj = call.args[0]
        if isinstance(obj, Alerta) and obj.tipo_alerta == ALERTA_PENDIENTE:
            return obj
    return None


# --- FE always emitted -----------------------------------------------------


async def test_sin_datos_de_cliente_emite_con_cliente_estandar(repos: dict) -> None:
    session = _session()
    res = await emitir_fe_para_pago(
        session, actor_uuid=ACTOR, uuid_factura=FACTURA, uuid_sucursal=SUCURSAL
    )
    assert res.emitida
    assert res.error is None and not res.pendiente
    kwargs = repos["crear_fe"].await_args.kwargs
    assert kwargs["uuid_cliente"] == CLIENTE_ESTANDAR_UUID
    assert kwargs["uuid_factura"] == FACTURA
    assert kwargs["consecutivo"] == 42
    repos["crear_envio"].assert_awaited_once()
    session.commit.assert_awaited_once()
    assert _marker(session) is None


async def test_con_datos_de_cliente_usa_ese_cliente(repos: dict) -> None:
    cliente = uuid_lib.uuid4()
    res = await emitir_fe_para_pago(
        _session(),
        actor_uuid=ACTOR,
        uuid_factura=FACTURA,
        uuid_sucursal=SUCURSAL,
        uuid_cliente=cliente,
        payload_extra={"uuid_subscripcion_cliente": "x"},
    )
    assert res.emitida
    assert repos["crear_fe"].await_args.kwargs["uuid_cliente"] == cliente
    payload = repos["crear_envio"].await_args.kwargs["payload"]
    assert payload["uuid_subscripcion_cliente"] == "x"
    assert payload["consecutivo"] == 42


async def test_descuento_de_la_factura_se_copia_al_documento(repos: dict) -> None:
    session = _session()
    session.factura.descuento = 1500
    await emitir_fe_para_pago(session, actor_uuid=ACTOR, uuid_factura=FACTURA)
    assert repos["crear_fe"].await_args.kwargs["descuento"] == Decimal("1500")


async def test_factura_ya_emitida_es_idempotente_y_no_consume_consecutivo(
    repos: dict,
) -> None:
    repos["existente"].return_value = repos["fe_row"]
    session = _session()
    res = await emitir_fe_para_pago(session, actor_uuid=ACTOR, uuid_factura=FACTURA)
    assert res.uuid_factura_electronica == repos["fe_row"].uuid
    repos["consecutivo"].assert_not_awaited()
    repos["crear_fe"].assert_not_awaited()
    session.commit.assert_not_awaited()


# --- failure -> pending ----------------------------------------------------


@pytest.mark.parametrize(
    ("setup", "codigo"),
    [
        ("sin_resolucion", "resolucion_facturacion_no_encontrada"),
        ("sin_prefijo", "resolucion_sin_prefijo"),
        ("agotada", "numeracion_agotada"),
        ("sin_sucursal", "missing_sucursal_context"),
    ],
)
async def test_fallo_conserva_el_pago_y_deja_factura_pendiente(
    repos: dict, setup: str, codigo: str
) -> None:
    sucursal: uuid_lib.UUID | None = SUCURSAL
    if setup == "sin_resolucion":
        repos["resolucion"].return_value = None
    elif setup == "sin_prefijo":
        repos["resolucion"].return_value.prefijo = None
    elif setup == "agotada":
        repos["consecutivo"].side_effect = ConsecutivoRangeExhaustedError("fin")
    else:
        sucursal = None
    session = _session()
    session.factura.uuid_sucursal = None if setup == "sin_sucursal" else SUCURSAL
    cliente = uuid_lib.uuid4()

    res = await emitir_fe_para_pago(
        session,
        actor_uuid=ACTOR,
        uuid_factura=FACTURA,
        uuid_sucursal=sucursal,
        uuid_cliente=cliente,
    )

    assert not res.emitida
    assert res.error == codigo
    assert res.pendiente
    repos["crear_fe"].assert_not_awaited()  # no FE row, no consumed number
    marker = _marker(session)
    assert marker is not None
    assert marker.estado == "resuelta"  # informational, not an admin task
    assert marker.datos_nuevos["uuid_factura"] == str(FACTURA)
    assert marker.datos_nuevos["uuid_cliente"] == str(cliente)
    assert marker.datos_nuevos["motivo"] == codigo
    # commit releases the numbering lock + persists the marker; never raises
    assert session.commit.await_count >= 1
    session.rollback.assert_not_awaited()


async def test_error_inesperado_no_propaga_y_queda_pendiente(repos: dict) -> None:
    repos["crear_fe"].side_effect = RuntimeError("db caida")
    session = _session()
    res = await emitir_fe_para_pago(
        session, actor_uuid=ACTOR, uuid_factura=FACTURA, uuid_sucursal=SUCURSAL
    )
    assert res.error == "fe_error_inesperado"
    assert res.pendiente
    assert _marker(session) is not None


async def test_marcador_no_se_duplica(repos: dict) -> None:
    repos["resolucion"].return_value = None
    session = _session(pending_marker_exists=True)
    res = await emitir_fe_para_pago(
        session, actor_uuid=ACTOR, uuid_factura=FACTURA, uuid_sucursal=SUCURSAL
    )
    assert res.pendiente
    assert _marker(session) is None


async def test_reintento_no_registra_otro_marcador(repos: dict) -> None:
    repos["resolucion"].return_value = None
    session = _session()
    res = await emitir_fe_para_pago(
        session,
        actor_uuid=ACTOR,
        uuid_factura=FACTURA,
        uuid_sucursal=SUCURSAL,
        registrar_pendiente=False,
    )
    assert res.error and not res.pendiente
    assert _marker(session) is None


# --- automatic retry -------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _filas(*, edad: timedelta = timedelta(minutes=2), cliente: str | None = None):
    ahora = datetime(2026, 10, 6, 12, 0, 0)
    datos = {
        "motivo": "numeracion_agotada",
        "uuid_factura": str(FACTURA),
        "uuid_cliente": cliente or str(CLIENTE_ESTANDAR_UUID),
        "payload_extra": {"k": "v"},
    }
    return ahora, [(ACTOR, ahora - edad, datos)]


def _session_retry(filas: list) -> MagicMock:
    session = _session()
    result = MagicMock()
    result.all = MagicMock(return_value=filas)
    result.first = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=result)
    return session


async def test_reintento_exitoso_emite_y_olvida(monkeypatch: pytest.MonkeyPatch) -> None:
    ahora, filas = _filas()
    session = _session_retry(filas)
    emit = AsyncMock(
        return_value=FeEmisionResultado(uuid_factura_electronica=uuid_lib.uuid4())
    )
    monkeypatch.setattr(fe_emision, "emitir_fe_para_pago", emit)
    sched = FeRetryScheduler(clock=_Clock())

    cont = await reintentar_pendientes(
        session, uuid_sucursal=SUCURSAL, scheduler=sched, now=ahora
    )

    assert cont == {"emitidas": 1, "fallidas": 0, "alertas": 0}
    kw = emit.await_args.kwargs
    assert kw["uuid_factura"] == FACTURA
    assert kw["uuid_cliente"] == CLIENTE_ESTANDAR_UUID
    assert kw["registrar_pendiente"] is False
    assert kw["payload_extra"] == {"k": "v"}
    assert sched.intentos(str(FACTURA)) == 0


async def test_reintentos_acotados_y_alerta_al_agotarse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahora, filas = _filas()
    clock = _Clock()
    sched = FeRetryScheduler(clock=clock)
    emit = AsyncMock(return_value=FeEmisionResultado(error="numeracion_agotada"))
    monkeypatch.setattr(fe_emision, "emitir_fe_para_pago", emit)

    alertas: list[Alerta] = []
    for intento in range(MAX_REINTENTOS):
        session = _session_retry(filas)
        session.add = MagicMock(side_effect=alertas.append)
        clock.t += 100_000  # past any backoff and the scan interval
        cont = await reintentar_pendientes(
            session, uuid_sucursal=SUCURSAL, scheduler=sched, now=ahora
        )
        if intento < MAX_REINTENTOS - 1:
            assert cont["alertas"] == 0
            assert not alertas
        else:
            assert cont["alertas"] == 1

    assert emit.await_count == MAX_REINTENTOS
    assert len(alertas) == 1
    alerta = alertas[0]
    assert alerta.tipo_alerta == ALERTA_FALLIDA
    assert alerta.estado == "abierta"
    assert alerta.datos_nuevos["uuid_factura"] == str(FACTURA)
    assert alerta.datos_nuevos["intentos"] == MAX_REINTENTOS
    assert alerta.datos_nuevos["motivo"] == "numeracion_agotada"
    # state forgotten after alerting
    assert sched.intentos(str(FACTURA)) == 0


async def test_backoff_respeta_la_espera_entre_reintentos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahora, filas = _filas()
    clock = _Clock()
    sched = FeRetryScheduler(clock=clock)
    emit = AsyncMock(return_value=FeEmisionResultado(error="x"))
    monkeypatch.setattr(fe_emision, "emitir_fe_para_pago", emit)

    await reintentar_pendientes(
        _session_retry(filas), uuid_sucursal=SUCURSAL, scheduler=sched, now=ahora
    )
    assert emit.await_count == 1
    # scan allowed again, but the invoice is still inside its backoff window
    clock.t += fe_emision.SCAN_INTERVAL_S + 1
    assert BACKOFF_S[0] > fe_emision.SCAN_INTERVAL_S + 1
    await reintentar_pendientes(
        _session_retry(filas), uuid_sucursal=SUCURSAL, scheduler=sched, now=ahora
    )
    assert emit.await_count == 1


async def test_pendiente_expirado_alerta_sin_reintentar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahora, filas = _filas(edad=timedelta(hours=25))
    session = _session_retry(filas)
    alertas: list[Alerta] = []
    session.add = MagicMock(side_effect=alertas.append)
    emit = AsyncMock()
    monkeypatch.setattr(fe_emision, "emitir_fe_para_pago", emit)

    cont = await reintentar_pendientes(
        session,
        uuid_sucursal=SUCURSAL,
        scheduler=FeRetryScheduler(clock=_Clock()),
        now=ahora,
    )
    assert cont["alertas"] == 1
    emit.assert_not_awaited()
    assert alertas[0].tipo_alerta == ALERTA_FALLIDA


async def test_alerta_fallida_no_se_duplica(monkeypatch: pytest.MonkeyPatch) -> None:
    ahora, filas = _filas(edad=timedelta(hours=25))
    session = _session_retry(filas)
    session.execute.return_value.first = MagicMock(return_value=(1,))  # already alerted
    session.add = MagicMock()
    monkeypatch.setattr(fe_emision, "emitir_fe_para_pago", AsyncMock())

    await reintentar_pendientes(
        session,
        uuid_sucursal=SUCURSAL,
        scheduler=FeRetryScheduler(clock=_Clock()),
        now=ahora,
    )
    session.add.assert_not_called()


async def test_scan_limitado_por_intervalo() -> None:
    clock = _Clock()
    sched = FeRetryScheduler(clock=clock)
    assert sched.scan_due() is True
    assert sched.scan_due() is False
    clock.t += fe_emision.SCAN_INTERVAL_S
    assert sched.scan_due() is True


async def test_fallo_fuera_del_savepoint_hace_rollback_y_aun_asi_deja_marcador(
    repos: dict,
) -> None:
    """A fault in a plain query (before the savepoint) may leave the tx
    aborted: roll back first so the marker can still be written."""
    repos["existente"].side_effect = RuntimeError("conexion reiniciada")
    session = _session()
    res = await emitir_fe_para_pago(
        session, actor_uuid=ACTOR, uuid_factura=FACTURA, uuid_sucursal=SUCURSAL
    )
    assert res.error == "fe_error_inesperado"
    assert res.pendiente
    session.rollback.assert_awaited()
    assert _marker(session) is not None


async def test_marcadores_duplicados_se_procesan_una_vez(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahora, filas = _filas()
    session = _session_retry(filas + filas)  # same factura twice
    emit = AsyncMock(return_value=FeEmisionResultado(uuid_factura_electronica=uuid_lib.uuid4()))
    monkeypatch.setattr(fe_emision, "emitir_fe_para_pago", emit)
    cont = await reintentar_pendientes(
        session, uuid_sucursal=SUCURSAL, scheduler=FeRetryScheduler(clock=_Clock()), now=ahora
    )
    assert cont["emitidas"] == 1
    assert emit.await_count == 1
