"""Lowest-layer guard: nobody in the cloud may mint a ``consecutivo``.

The HTTP/emission entry points already refuse (``fe_numeracion_solo_en_sucursal``);
this pins the allocators themselves so a future caller cannot reintroduce the
collision on ``factura_electronica_uk01`` (live incident 2026-10).
"""
from __future__ import annotations

import uuid as uuid_lib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.repo import resolucion_facturacion as repo_resolucion
from parkos_core.repo.resolucion_facturacion import NumeracionSoloEnSucursalError


async def test_assign_consecutivo_en_nube_se_niega_sin_tocar_la_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    session = AsyncMock()

    with pytest.raises(NumeracionSoloEnSucursalError):
        await repo_resolucion.assign_consecutivo(
            session, resolucion_uuid=uuid_lib.uuid4(), source_event_uuid=uuid_lib.uuid4()
        )

    session.execute.assert_not_awaited()


async def test_assign_consecutivo_en_sucursal_sigue_numerando(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PARKOS_DEPLOY", "branch")
    resolucion = SimpleNamespace(rango_desde=1, rango_hasta=100)
    results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # idempotency
        MagicMock(scalar_one_or_none=MagicMock(return_value=resolucion)),  # lock
        MagicMock(scalar_one=MagicMock(return_value=4)),  # MAX
    ]
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=results)

    n = await repo_resolucion.assign_consecutivo(
        session, resolucion_uuid=uuid_lib.uuid4(), source_event_uuid=uuid_lib.uuid4()
    )

    assert n == 5


async def test_allocator_de_nube_se_niega_en_una_resolucion_de_sucursal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    from parkos_core.dian.cloud import atomic_next_consecutivo as atomic

    fila = SimpleNamespace(uuid_sucursal=uuid_lib.uuid4(), prefijo="QA", rango_desde=1)
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fila))
    )

    with pytest.raises(NumeracionSoloEnSucursalError):
        await atomic.next_consecutivo(session, uuid_resolucion_facturacion=uuid_lib.uuid4())

    # only the row lookup ran: the MAX() was never computed
    assert session.execute.await_count == 1
