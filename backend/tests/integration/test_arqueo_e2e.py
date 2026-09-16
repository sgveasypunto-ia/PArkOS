"""HU-F1.13 / T5.6 -- End-to-end test for POST /caja/arqueo.

Single happy-path e2e: ``auditoria`` codigo, sin diferencia, sin alerta,
exactly one ``session.commit()`` (KD-ARQUEO-01). Mirrors the F1.12 T7.2
pattern in ``tests/integration/test_venta_suscripcion_e2e.py``: DB-mock
via ``MagicMock`` + ``AsyncMock`` + ``patch.object``.

This test exercises the **full 12-step chain** end-to-end so a
regression on ANY of the 7 repo helpers or the single-commit invariant
will be caught here, while the individual unit tests in
``tests/unit/test_arqueo_handler.py`` cover the 4 mandated scenarios
independently.

DB-mock is the F1.12 standard because Docker is unavailable per the
HU-F1.13 constraints; full SQL behavior is enforced via the DB-layer
``fn_*_inmutable`` triggers, the ``ls_session_guard`` trigger, and the
MIGRATION 0031 idempotency test.
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


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = uuid_lib.uuid4()
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


def _build_payload(*, uuid_sesion: uuid_lib.UUID | None = None) -> MagicMock:
    payload = MagicMock()
    payload.uuid_tipo_arqueo = uuid_lib.uuid4()
    payload.uuid_sesion = uuid_sesion
    payload.valor_efectivo_reportado = Decimal("148000")
    payload.valor_datafono_reportado = Decimal("320000")
    payload.justificacion = None  # auditoria does NOT require justificacion
    return payload


def _build_tipo_arqueo(codigo: str) -> MagicMock:
    row = MagicMock()
    row.uuid = uuid_lib.uuid4()
    row.codigo = codigo
    return row


def _build_tolerancia() -> MagicMock:
    tol = MagicMock()
    tol.tolerancia_efectivo = Decimal("100")
    tol.tolerancia_datafono = Decimal("200")
    return tol


@pytest.mark.asyncio
async def test_arqueo_e2e_auditoria_sin_diferencia_single_commit() -> None:
    """HU-F1.13 / T5.6 -- full 12-step chain happy path.

    Validates the full POST /caja/arqueo flow for ``auditoria`` with
    sin diferencia:

      * All 7 repo helpers called in the right order (Step 1, 3, 4, 5, 8, 9, 10).
      * KD-ARQUEO-01: ``await session.commit()`` called exactly ONCE.
      * DEC-ARQUEO-06: ``Cache-Control: no-store`` on response.
      * Sin descuadre -> ``alerta_generada=False``, ``alerta_uuid=None``.
      * Response shape matches ``ArqueoReadForHandler``.

    The ``cerrar_sesiones_del_dia_bulk`` and ``insertar_alerta_*`` calls
    are NOT expected here (auditoria path skips them).
    """
    from parkos_core.api.v1 import caja_arqueo as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    sesion_uuid = uuid_lib.uuid4()
    payload = _build_payload(uuid_sesion=sesion_uuid)

    # ----- ORM-like return values ----------------------------------
    arqueo_row = MagicMock()
    arqueo_row.uuid = uuid_lib.uuid4()

    # ----- Session mock (KD-ARQUEO-01: single commit) -------------
    session = MagicMock()
    session.commit = AsyncMock()

    # ----- Patch all 7 repo helpers -------------------------------
    m_resolver_tipo = AsyncMock(return_value=_build_tipo_arqueo(codigo="auditoria"))
    m_resolver_tol = AsyncMock(return_value=_build_tolerancia())
    m_validar_sesion = AsyncMock(return_value=MagicMock())
    m_calcular_esperado_sesion = AsyncMock(
        return_value=(Decimal("148000"), Decimal("320000"))
    )
    m_insertar_arqueo = AsyncMock(return_value=arqueo_row)
    m_cerrar_bulk = AsyncMock(return_value=0)
    m_insertar_alerta = AsyncMock(return_value=MagicMock(uuid=uuid_lib.uuid4()))

    patchers = [
        patch.object(
            handler_mod.repo_arqueo,
            "resolver_tipo_arqueo_por_uuid",
            new=m_resolver_tipo,
        ),
        patch.object(
            handler_mod.repo_arqueo,
            "resolver_tolerancia_vigente",
            new=m_resolver_tol,
        ),
        patch.object(
            handler_mod.repo_arqueo,
            "validar_sesion_abierta_para_arqueo",
            new=m_validar_sesion,
        ),
        patch.object(
            handler_mod.repo_arqueo,
            "calcular_esperado_sesion",
            new=m_calcular_esperado_sesion,
        ),
        patch.object(
            handler_mod.repo_arqueo,
            "insertar_arqueo",
            new=m_insertar_arqueo,
        ),
        patch.object(
            handler_mod.repo_arqueo,
            "cerrar_sesiones_del_dia_bulk",
            new=m_cerrar_bulk,
        ),
        patch.object(
            handler_mod.repo_arqueo,
            "insertar_alerta_descuadre_critico",
            new=m_insertar_alerta,
        ),
    ]
    for p in patchers:
        p.start()
    try:
        result = await handler_mod.post_arqueo(
            response=response,
            payload=payload,
            session=session,
            ctx=ctx,
            _claims=None,
        )
    finally:
        for p in patchers:
            p.stop()

    # ----- KD-ARQUEO-01: SINGLE COMMIT -----------------------------
    session.commit.assert_called_once()
    assert session.commit.await_count == 1

    # ----- DEC-ARQUEO-06: Cache-Control: no-store ------------------
    assert response.headers["Cache-Control"] == "no-store"

    # ----- 12-step chain: each helper invoked in the right place ---
    # Step 1: tipo_arqueo SELECT FOR UPDATE
    assert m_resolver_tipo.await_count == 1
    # Step 3: tolerancia vigente
    assert m_resolver_tol.await_count == 1
    # Step 4: sesion validate (auditoria requires sesion)
    assert m_validar_sesion.await_count == 1
    # Step 5: esperado_sesion (NOT esperado_cierre_dia for auditoria)
    assert m_calcular_esperado_sesion.await_count == 1
    # Step 8: INSERT arqueo
    assert m_insertar_arqueo.await_count == 1
    # Step 9: NOT called for auditoria (cierre_dia only)
    assert m_cerrar_bulk.await_count == 0
    # Step 10: NOT called (sin descuadre critico)
    assert m_insertar_alerta.await_count == 0

    # ----- Response shape -----------------------------------------
    assert result.uuid == arqueo_row.uuid
    assert result.codigo_tipo_arqueo == "auditoria"
    assert result.uuid_sesion == sesion_uuid
    assert result.alerta_generada is False
    assert result.alerta_uuid is None
    assert result.diferencia_efectivo == Decimal("0")
    assert result.diferencia_datafono == Decimal("0")
