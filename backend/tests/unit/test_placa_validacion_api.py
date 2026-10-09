"""Defecto Operacion/ALTA: el backend debe validar el formato de placa.

El front (``placa.ts``: ``REGEX_AUTO`` / ``REGEX_MOTO`` tras
``trim + upper + quitar espacios``) ya lo hace, pero llamando la API directo
se aceptaban ``AB``, ``AB12``, ``AB@123``, ``ABCDEFGH``. Estos tests fijan:

  1. la funcion pura reutilizable (misma semantica que el front),
  2. cada schema de entrada con placa (validacion en el borde),
  3. el shape del 422 sobre HTTP (error + message + placa), igual al de los
     422 existentes (``placa_duplicada_en_venta``).

Sin base de datos: ni la funcion ni los schemas ni el handler la necesitan.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from parkos_core.api.placa_errors import register_placa_validation_handler
from parkos_core.repo.placa_formato import (
    PlacaFormatoInvalidoError,
    normalizar_placa,
    validar_placa,
)
from parkos_core.schemas.clientes import (
    AgregarVehiculoCupoRequest,
    VehiculosCreate,
    VehiculosUpdate,
    VentaSuscripcionCreate,
)
from parkos_core.schemas.operacion import IngresoCreateForzado, SalidaCreateForzado
from pydantic import ValidationError

INVALIDAS = [
    "AB",
    "AB12",
    "AB@123",
    "ABCDEFGH",
    "",
    "   ",
    "ABC-123",  # el front tampoco acepta separadores
    "ABC1234",
    "AB1234",
    "123ABC",
    "ABCD12",
    "ÁBC123",  # unicode (acento)
    "ＡＢＣ１２３",  # fullwidth: isalpha()/isdigit() lo aceptan  # noqa: RUF001
    "ABC١٢٣",  # digitos arabes: \d de re los aceptaria  # noqa: RUF001
    "ABC12 3D",
    "ABC12DE",
]
VALIDAS_CANONICAS = [
    ("ABC123", "ABC123"),  # carro
    ("XYZ12A", "XYZ12A"),  # moto
    ("abc123", "ABC123"),  # el front normaliza a mayuscula
    ("  abc123  ", "ABC123"),  # trim
    ("ab c 123", "ABC123"),  # espacios internos (el front los quita)
    ("ABC12D", "ABC12D"),
    ("kqe 45z", "KQE45Z"),
    ("ABC123" + chr(10), "ABC123"),  # trim() del front tambien lo acepta
]


# --------------------------------------------------------------------------
# 1. Funcion pura
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw", INVALIDAS)
def test_validar_placa_rechaza_formatos_invalidos(raw: str) -> None:
    with pytest.raises(PlacaFormatoInvalidoError) as exc:
        validar_placa(raw)
    assert exc.value.placa == raw


@pytest.mark.parametrize(("raw", "esperada"), VALIDAS_CANONICAS)
def test_validar_placa_normaliza_y_acepta(raw: str, esperada: str) -> None:
    assert validar_placa(raw) == esperada
    assert normalizar_placa(raw) == esperada


# --------------------------------------------------------------------------
# 2. Schemas de entrada con placa
# --------------------------------------------------------------------------


def _venta(placas: list[str]) -> VentaSuscripcionCreate:
    return VentaSuscripcionCreate(
        uuid_cliente=uuid_lib.uuid4(),
        placas=placas,
        uuid_tipo_subscripcion=uuid_lib.uuid4(),
        fecha_inicio_cobertura=date(2026, 10, 1),
    )


# Cada fabrica recibe la placa cruda y devuelve la placa ya canonica.
FABRICAS = {
    "ingreso": lambda p: IngresoCreateForzado(placa=p).placa,
    "salida": lambda p: SalidaCreateForzado(
        uuid_ingreso=uuid_lib.uuid4(), placa=p
    ).placa,
    "venta": lambda p: _venta([p]).placas[0],
    "agregar_vehiculo": lambda p: AgregarVehiculoCupoRequest(
        uuid_subscripcion_cliente=uuid_lib.uuid4(), placa=p
    ).placa,
    "vehiculos_create": lambda p: VehiculosCreate(placa=p).placa,
    "vehiculos_update": lambda p: VehiculosUpdate(placa=p).placa,
}


@pytest.mark.parametrize("schema", sorted(FABRICAS))
@pytest.mark.parametrize("raw", INVALIDAS)
def test_schema_rechaza_placa_invalida(schema: str, raw: str) -> None:
    with pytest.raises(ValidationError):
        FABRICAS[schema](raw)


@pytest.mark.parametrize("schema", sorted(FABRICAS))
@pytest.mark.parametrize(("raw", "esperada"), VALIDAS_CANONICAS)
def test_schema_acepta_y_normaliza_placa_valida(
    schema: str, raw: str, esperada: str
) -> None:
    assert FABRICAS[schema](raw) == esperada


def test_venta_valida_cada_placa_de_la_lista() -> None:
    with pytest.raises(ValidationError):
        _venta(["ABC123", "AB@123"])


def test_venta_detecta_duplicada_tras_normalizar() -> None:
    # "abc123" y "ABC123" son la misma placa: ahora llegan canonicas al
    # handler y ``validar_placas_no_duplicadas`` las ve iguales.
    assert _venta(["abc123", "ABC 123"]).placas == ["ABC123", "ABC123"]


@pytest.mark.parametrize("schema", ["ingreso", "salida"])
def test_placa_opcional_sigue_aceptando_none(schema: str) -> None:
    # Ingreso sin placa (bici/patineta, REQ-OPS-194) y salida sin placa.
    assert FABRICAS[schema](None) is None


# --------------------------------------------------------------------------
# 3. Shape del 422 sobre HTTP
# --------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_placa_validation_handler(app)

    @app.post("/ingresos")
    async def _ingreso(payload: IngresoCreateForzado) -> dict:
        return {"placa": payload.placa}

    @app.post("/venta")
    async def _venta_ep(payload: VentaSuscripcionCreate) -> dict:
        return {"placas": payload.placas}

    @app.post("/otro")
    async def _otro(payload: AgregarVehiculoCupoRequest) -> dict:
        return {"placa": payload.placa}

    return TestClient(app)


@pytest.mark.parametrize("raw", ["AB", "AB12", "AB@123", "ABCDEFGH"])
def test_422_tiene_shape_consistente_con_los_422_existentes(
    client: TestClient, raw: str
) -> None:
    body = {"placa": raw, "uuid_tipo_vehiculo": str(uuid_lib.uuid4())}
    r = client.post("/ingresos", json=body)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["error"] == "placa_formato_invalido"
    assert detail["placa"] == raw
    assert isinstance(detail["message"], str)
    assert raw in detail["message"]
    assert detail["formatos_aceptados"] == ["ABC123", "ABC12D"]
    assert r.headers["Cache-Control"] == "no-store"


def test_422_en_lista_reporta_la_placa_ofensora(client: TestClient) -> None:
    r = client.post(
        "/venta",
        json={
            "uuid_cliente": str(uuid_lib.uuid4()),
            "placas": ["ABC123", "AB@123"],
            "uuid_tipo_subscripcion": str(uuid_lib.uuid4()),
            "fecha_inicio_cobertura": "2026-10-01",
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "placa_formato_invalido"
    assert r.json()["detail"]["placa"] == "AB@123"


def test_placa_valida_pasa_y_llega_canonica(client: TestClient) -> None:
    body = {"uuid_subscripcion_cliente": str(uuid_lib.uuid4()), "placa": " abc12d "}
    r = client.post("/otro", json=body)
    assert r.status_code == 200
    assert r.json() == {"placa": "ABC12D"}


def test_otros_errores_de_validacion_conservan_el_shape_por_defecto(
    client: TestClient,
) -> None:
    r = client.post("/otro", json={"placa": "ABC123"})  # falta el uuid
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def test_placa_no_string_no_revienta(client: TestClient) -> None:
    body = {"uuid_subscripcion_cliente": str(uuid_lib.uuid4()), "placa": 123}
    r = client.post("/otro", json=body)
    assert r.status_code == 422


@pytest.mark.parametrize("modulo", ["api_sucursal_main.app", "api_admin_main.app"])
def test_ambas_apps_registran_el_handler(modulo: str) -> None:
    import importlib

    from fastapi.exceptions import RequestValidationError

    try:
        app = importlib.import_module(modulo).app
    except Exception as exc:  # pragma: no cover - entorno sin deps
        pytest.skip(f"{modulo} no importable: {exc}")
    handler = app.exception_handlers[RequestValidationError]
    assert handler.__module__ == "parkos_core.api.placa_errors"


def test_422_no_refleja_una_placa_gigante_completa(client: TestClient) -> None:
    body = {"uuid_subscripcion_cliente": str(uuid_lib.uuid4()), "placa": "A" * 100_000}
    r = client.post("/otro", json=body)
    assert r.status_code == 422
    assert len(r.text) < 1_000
