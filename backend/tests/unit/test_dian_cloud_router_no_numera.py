"""The cloud DIAN router must never mint a ``consecutivo`` (branch-local numbering)."""
from __future__ import annotations

import importlib
import sys
import uuid as uuid_lib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from parkos_core.schemas.facturacion import CloudFacturaElectronicaCreate


async def test_post_factura_electronica_en_nube_no_asigna_consecutivo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The module refuses to import on a branch deploy (REQ-X3): import it as
    # the cloud, fresh, and leave no cached copy behind.
    monkeypatch.setenv("PARKOS_DEPLOY", "cloud")
    for name in ("parkos_core.dian.cloud_router", "parkos_core.dian"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    cloud_router = importlib.import_module("parkos_core.dian.cloud_router")
    session = AsyncMock()
    payload = CloudFacturaElectronicaCreate(
        uuid_sucursal=uuid_lib.uuid4(),
        uuid_factura=uuid_lib.uuid4(),
        uuid_cliente=uuid_lib.uuid4(),
        uuid_resolucion_facturacion=uuid_lib.uuid4(),
        descuento=0,
    )

    with pytest.raises(HTTPException) as exc:
        await cloud_router.create_factura_electronica(
            payload, session, SimpleNamespace(actor_uuid=uuid_lib.uuid4()), None
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "fe_numeracion_solo_en_sucursal"
    session.commit.assert_not_awaited()
