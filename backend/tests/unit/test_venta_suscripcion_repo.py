"""HU-F1.12 / T3.1 + T3.3 + T3.5: repo helper unit tests (mock-everything).

F1.10 + F1.11 mock pattern (no live DB required -- Docker unavailable on
this host). Each helper is exercised via ``unittest.mock.AsyncMock`` /
``MagicMock`` for the SQLAlchemy session + the ``versioned.close_and_insert``
collaborator. Tests assert:

* V1 new-cliente branch: ``close_and_insert(Clientes, current_uuid=None,
  new_attrs=<datos_cliente minus 'dv'>, actor_uuid=...)`` called once
  with the right args; ``dv`` is filtered out (DEC-VENTA-07).
* V1 existing-cliente branch: ``session.get(Clientes, uuid)`` returns
  row -> helper returns row; ``None`` -> raises ``ClienteNoEncontradoError``
  carrying ``uuid_cliente``.
* V1 facade dispatch: ``uuid_cliente`` -> existing branch,
  ``datos_cliente`` -> new branch; both None -> ValueError.
* V2 plan: ``select(TipoSubscripciones)...with_for_update()`` is used
  (KD-VENTA-02 + DEC-VENTA-04); SQL string contains ``FOR UPDATE``
  (verified via the compiled ``str(stmt)``); does NOT contain
  ``FOR SHARE`` (exclusive lock).
* V3 vehiculo: existing row -> returns row + ``was_created=False``;
  no row -> ``detectar_tipo_vehiculo`` called + ``close_and_insert``
  + returns new row + ``was_created=True``.

No real DB, no fixtures, no conftest skipping. Pattern: F1.10
``test_factura_create_handler.py`` + F1.11 ``test_reimpresion_ticket_create_handler.py``.
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

# ---------------------------------------------------------------------------
# V1 NEW branch -- buscar_cliente_por_uuid_o_crear_nuevo (T3.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_cliente_por_uuid_o_crear_nuevo_drops_dv() -> None:
    """T3.1 T1: NEW branch filters ``dv`` and delegates to close_and_insert.

    DEC-VENTA-07: ``dv`` is Pydantic-validated but NOT persisted (no
    ``dv`` column on ``prod.clientes``). The helper filters it out
    before calling ``close_and_insert``.

    KD-VENTA-01: the helper NEVER calls ``session.commit()`` -- that is
    owned by the handler at Step 10.
    """
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    actor = uuid_lib.uuid4()
    new_row = MagicMock()
    new_row.uuid = uuid_lib.uuid4()

    with patch.object(
        repo_venta.versioned, "close_and_insert", new=AsyncMock(return_value=new_row)
    ) as mock_cai:
        result = await repo_venta.buscar_cliente_por_uuid_o_crear_nuevo(
            session,
            datos_cliente={
                "tipo_identificador": "CC",
                "numero_identificacion": "1234567890",
                "nombre": "Juan",
                "dv": "5",
            },
            actor_uuid=actor,
        )

    assert result is new_row
    assert mock_cai.await_count == 1
    args, kwargs = mock_cai.call_args
    # session positional, Clientes class positional, kwargs follow
    assert args[0] is session
    assert args[1] is repo_venta.Clientes
    assert kwargs["current_uuid"] is None
    assert kwargs["actor_uuid"] == actor
    # CRITICAL: dv is NOT in new_attrs
    assert "dv" not in kwargs["new_attrs"]
    assert kwargs["new_attrs"]["tipo_identificador"] == "CC"
    assert kwargs["new_attrs"]["numero_identificacion"] == "1234567890"
    assert kwargs["new_attrs"]["nombre"] == "Juan"


# ---------------------------------------------------------------------------
# V1 EXISTING branch -- buscar_cliente_por_uuid_o_crear_existente (T3.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_cliente_por_uuid_o_crear_existente_returns_row() -> None:
    """T3.3 T1: EXISTING branch returns row from ``session.get(Clientes, uuid)``."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    expected_row = MagicMock()
    expected_row.uuid = uuid_lib.uuid4()
    session.get = AsyncMock(return_value=expected_row)

    uuid_cliente = uuid_lib.uuid4()
    result = await repo_venta.buscar_cliente_por_uuid_o_crear_existente(
        session, uuid_cliente=uuid_cliente
    )

    assert result is expected_row
    session.get.assert_awaited_once_with(repo_venta.Clientes, uuid_cliente)


@pytest.mark.asyncio
async def test_buscar_cliente_por_uuid_o_crear_raises_when_cliente_missing() -> None:
    """T3.3 T2: raises ClienteNoEncontradoError when session.get returns None."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    session.get = AsyncMock(return_value=None)

    uuid_cliente = uuid_lib.uuid4()
    with pytest.raises(repo_venta.ClienteNoEncontradoError) as excinfo:
        await repo_venta.buscar_cliente_por_uuid_o_crear_existente(
            session, uuid_cliente=uuid_cliente
        )

    assert excinfo.value.uuid_cliente == uuid_cliente
    assert "cliente_no_encontrado" in str(excinfo.value)


# ---------------------------------------------------------------------------
# V2 -- buscar_tipo_subscripcion_vigente_por_uuid (T3.5 T1 + T2 + T3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_tipo_subscripcion_vigente_por_uuid_uses_with_for_update() -> None:
    """T3.5 T2: SELECT stmt contains FOR UPDATE (KD-VENTA-02 + DEC-VENTA-04)."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    expected_row = MagicMock()
    # ``session.execute`` is awaited; ``scalar_one_or_none`` is sync on the result.
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=expected_row)
    session.execute = AsyncMock(return_value=execute_result)

    uuid_plan = uuid_lib.uuid4()
    result = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(
        session, uuid_tipo_subscripcion=uuid_plan
    )

    assert result is expected_row
    assert session.execute.await_count == 1
    stmt_arg = session.execute.await_args.args[0]
    compiled_sql = str(stmt_arg.compile(compile_kwargs={"literal_binds": True}))
    assert "FOR UPDATE" in compiled_sql.upper(), (
        f"V2 violated: SELECT stmt must lock the plan row with FOR UPDATE "
        f"(KD-VENTA-02 + DEC-VENTA-04); got: {compiled_sql!r}"
    )
    assert "FOR SHARE" not in compiled_sql.upper(), (
        "V2 violated: must use FOR UPDATE (exclusive), NOT FOR SHARE "
        "(F1.9 used FOR SHARE on prod.tarifas_sucursal -- F1.12 uses exclusive)"
    )


@pytest.mark.asyncio
async def test_buscar_tipo_subscripcion_vigente_por_uuid_returns_plan() -> None:
    """T3.5 T1: vigente row returned as-is."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    expected_row = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=expected_row)
    session.execute = AsyncMock(return_value=execute_result)

    result = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(
        session, uuid_tipo_subscripcion=uuid_lib.uuid4()
    )
    assert result is expected_row


@pytest.mark.asyncio
async def test_buscar_tipo_subscripcion_vigente_por_uuid_returns_none_when_no_vigente() -> None:
    """T3.5 T3: helper returns None when no vigente row (handler maps to 404)."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=execute_result)

    result = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(
        session, uuid_tipo_subscripcion=uuid_lib.uuid4()
    )
    assert result is None


# ---------------------------------------------------------------------------
# V3 -- buscar_o_crear_vehiculo_por_placa
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_o_crear_vehiculo_por_placa_returns_existing_when_present() -> None:
    """V3 hit: existing vigente row returned with ``was_created=False``."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    expected_row = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=expected_row)
    session.execute = AsyncMock(return_value=execute_result)

    vehiculo, was_created = await repo_venta.buscar_o_crear_vehiculo_por_placa(
        session, placa="ABC123", actor_uuid=uuid_lib.uuid4()
    )

    assert vehiculo is expected_row
    assert was_created is False


@pytest.mark.asyncio
async def test_buscar_o_crear_vehiculo_por_placa_inserts_when_missing() -> None:
    """V3 miss: detectar_tipo_vehiculo + close_and_insert + was_created=True."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=None)
    session.execute = AsyncMock(return_value=execute_result)

    detected_uuid = uuid_lib.uuid4()
    new_row = MagicMock()
    new_row.uuid = uuid_lib.uuid4()
    actor = uuid_lib.uuid4()

    async def fake_detectar(_placa: str) -> uuid_lib.UUID:
        return detected_uuid

    with patch.object(
        repo_venta.repo_placa, "detectar_tipo_vehiculo", new=fake_detectar
    ), patch.object(
        repo_venta.versioned, "close_and_insert", new=AsyncMock(return_value=new_row)
    ) as mock_cai:
        vehiculo, was_created = await repo_venta.buscar_o_crear_vehiculo_por_placa(
            session, placa="XYZ999", actor_uuid=actor
        )

    assert vehiculo is new_row
    assert was_created is True
    args, kwargs = mock_cai.call_args
    assert args[0] is session
    assert args[1] is repo_venta.Vehiculos
    assert kwargs["current_uuid"] is None
    assert kwargs["new_attrs"]["placa"] == "XYZ999"
    assert kwargs["new_attrs"]["uuid_tipo_vehiculo"] == detected_uuid
    assert kwargs["actor_uuid"] == actor


# ---------------------------------------------------------------------------
# V1 facade dispatch (T3.2 + T3.4 combined) -- sanity check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_cliente_por_uuid_o_crear_dispatches_to_existente() -> None:
    """V1 facade: uuid_cliente branch delegates to existing branch helper."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    expected_row = MagicMock()
    session.get = AsyncMock(return_value=expected_row)
    uuid_cliente = uuid_lib.uuid4()

    result = await repo_venta.buscar_cliente_por_uuid_o_crear(
        session,
        uuid_cliente=uuid_cliente,
        datos_cliente=None,
        actor_uuid=uuid_lib.uuid4(),
    )
    assert result is expected_row
    session.get.assert_awaited_once_with(repo_venta.Clientes, uuid_cliente)


@pytest.mark.asyncio
async def test_buscar_cliente_por_uuid_o_crear_dispatches_to_nuevo() -> None:
    """V1 facade: datos_cliente branch delegates to new branch helper."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    new_row = MagicMock()
    actor = uuid_lib.uuid4()

    with patch.object(
        repo_venta.versioned, "close_and_insert", new=AsyncMock(return_value=new_row)
    ):
        result = await repo_venta.buscar_cliente_por_uuid_o_crear(
            session,
            uuid_cliente=None,
            datos_cliente={
                "tipo_identificador": "NIT",
                "numero_identificacion": "900123456",
                "nombre": "Acme S.A.",
            },
            actor_uuid=actor,
        )
    assert result is new_row


@pytest.mark.asyncio
async def test_buscar_cliente_por_uuid_o_crear_raises_when_both_none() -> None:
    """V1 facade: both branches None -> ValueError (Pydantic XOR should reject first)."""
    from parkos_core.repo import venta_suscripcion as repo_venta

    session = MagicMock()
    with pytest.raises(ValueError) as excinfo:
        await repo_venta.buscar_cliente_por_uuid_o_crear(
            session,
            uuid_cliente=None,
            datos_cliente=None,
            actor_uuid=uuid_lib.uuid4(),
        )
    assert "exactly one of" in str(excinfo.value)
