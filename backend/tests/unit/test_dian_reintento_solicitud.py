"""The manual DIAN retry travels branch -> cloud as an ``alerta`` request.

``envio_dian`` is cloud-authored (``cloud_to_branch``) and the branch never
pushes it, so the branch asks for a retry by appending a request row to an
existing ``branch_to_cloud`` workflow entity (``alerta``,
``tipo_alerta='dian_reintento_solicitado'``). On arrival the cloud hook creates
the retry attempt through the dispatcher. These tests pin the contract of that
channel without a database.
"""
from __future__ import annotations

import uuid as uuid_lib
from unittest.mock import MagicMock, patch

import pytest
from parkos_core.repo import factura_electronica as repo_fe
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.hooks import base as hook_base
from parkos_core.sync.hooks.impls import dian_dispatch_on_sync as hooks

FE_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000f1")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000bb")


def _ctx(payload: dict) -> hook_base.HookContext:
    return hook_base.HookContext(
        spec=MagicMock(), payload=payload, session=MagicMock(), actor_uuid=uuid_lib.uuid4()
    )


def test_request_type_is_a_stable_identifier() -> None:
    assert repo_fe.TIPO_ALERTA_REINTENTO_DIAN == "dian_reintento_solicitado"


def test_alerta_is_the_branch_to_cloud_carrier_and_runs_the_retry_hook() -> None:
    spec = SYNC_CATALOG_BY_NAME["alerta"]
    assert spec.direction == "branch_to_cloud"
    assert spec.hook_post_insert is hooks.dian_reintento_solicitado_hook


def test_retry_hook_is_registered_by_name() -> None:
    from parkos_core.sync.hooks import registry

    assert registry.get_hook("dian_reintento_solicitado") is hooks.dian_reintento_solicitado_hook


@pytest.mark.asyncio
async def test_any_other_alerta_is_ignored() -> None:
    ctx = _ctx({"tipo_alerta": "dian_error", "uuid_arqueo": str(FE_UUID)})
    with patch.object(hooks, "defer_dispatch") as defer:
        result = await hooks.dian_reintento_solicitado_hook(ctx)
    assert result.proceed is True
    defer.assert_not_called()


@pytest.mark.asyncio
async def test_request_without_a_document_reference_is_ignored() -> None:
    ctx = _ctx({"tipo_alerta": repo_fe.TIPO_ALERTA_REINTENTO_DIAN, "uuid_arqueo": None})
    with patch.object(hooks, "defer_dispatch") as defer:
        result = await hooks.dian_reintento_solicitado_hook(ctx)
    assert result.proceed is True
    defer.assert_not_called()


@pytest.mark.asyncio
async def test_request_queues_one_deferred_retry_keyed_by_the_document() -> None:
    ctx = _ctx(
        {
            "tipo_alerta": repo_fe.TIPO_ALERTA_REINTENTO_DIAN,
            "uuid_arqueo": str(FE_UUID),
            "uuid_sucursal": str(SUCURSAL_UUID),
        }
    )
    with patch.object(hooks, "defer_dispatch") as defer:
        result = await hooks.dian_reintento_solicitado_hook(ctx)
    assert result.proceed is True
    defer.assert_called_once()
    assert defer.call_args.kwargs["key"] == ("fe", FE_UUID)
    # same key as the FE-arrival hook: the in-flight guard de-duplicates both
    assert callable(defer.call_args.args[1])
