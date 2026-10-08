"""test_sync_cloud_dispatch_wireup.py — CU-05 fix #2 acceptance (T-PR11-cu05).

The cloud-side catalog-driven sync apply loop
(``jobs/sync_cloud.py::_apply_pending_batch_once``, T-PR11-001) drains
``prod.sync_queue`` and applies every row through
:meth:`motor.apply_row.apply_row`. For three DIAN-bound catalog entries
(``factura_electronica``, ``revocacion_factura``, and
``envio_dian(estado='pendiente')``) a successful apply was leaving the
row in the cloud DB forever without ever being forwarded to the DIAN
provider — ``dian/cloud_router.py`` calls
:func:`dian.cloud.dispatcher.dispatch_factura_electronica_with_backoff`
on its direct admin POST endpoint, but the same call site was MISSING
on the sync apply path.

CU-05 critical fix #2 wires ``hook_post_insert`` on the three catalog
entries (see ``sync/catalog/entries/sync_entries_{le,lw,a}.py`` and
``sync/hooks/impls/dian_dispatch_on_sync.py``'s module docstring). The
hooks delegate to the dispatcher's ``dispatch_*_with_backoff`` API so
the cloud-side apply path now mirrors the cloud-router's direct call.

Acceptance for this fix — pure mock-based, no DB — proves:

  1. ``factura_electronica`` apply fires
     ``dispatch_factura_electronica_with_backoff`` with the just-written
     row's uuid.
  2. ``revocacion_factura`` apply fires
     ``dispatch_revocacion_with_backoff`` with the just-written row's
     uuid.
  3. ``envio_dian`` is cloud_to_branch (cloud is the only DIAN egress):
     it carries NO dispatch hook, so applying it at the branch never
     reaches the cloud-only dispatcher.
  4. The FE / revocacion entries' ``hook_post_insert`` field is actually
     bound to the dispatch hook (regression guard — a forgotten
     re-import in ``sync_entries_*.py`` would silently drop the
     wire-up).

Pattern follows ``test_motor_apply_row.py`` (T-PR4-001/006/007): mock
the repo helpers + dispatcher at their source modules, drive
``apply_row`` directly, assert the dispatcher was called with the
expected kwargs.
"""
from __future__ import annotations

import uuid as uuid_lib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME
from parkos_core.sync.hooks import registry as hook_registry
from parkos_core.sync.hooks.impls import dian_dispatch_on_sync
from parkos_core.sync.motor.apply_row import apply_row

# Warm the dispatcher module import path so ``unittest.mock.patch`` can
# resolve ``parkos_core.dian.cloud.dispatcher.dispatch_factura_electronica_
# with_backoff``. The dispatcher carries an import-time guard
# (``dian/cloud/dispatcher.py`` lines 80-84) that raises ImportError when
# ``PARKOS_DEPLOY=branch`` — the test-suite-wide default
# (``tests/conftest.py`` line 116). Stamp ``PARKOS_DEPLOY=cloud`` JUST
# long enough to load the module (the guard is import-time only — once
# the module sits in ``sys.modules`` it never re-runs), then revert.
# Also: ``parkos_core.dian.cloud.__init__`` does NOT import its
# submodules, so the pre-import below is what makes
# ``getattr(parkos_core.dian.cloud, 'dispatcher')`` succeed when
# ``unittest.mock.patch`` walks the dotted path during the test.
import os

_PREV_DEPLOY = os.environ.get("PARKOS_DEPLOY")
os.environ["PARKOS_DEPLOY"] = "cloud"
try:
    import parkos_core.dian.cloud.dispatcher  # noqa: E402,F401
finally:
    if _PREV_DEPLOY is None:
        os.environ.pop("PARKOS_DEPLOY", None)
    else:
        os.environ["PARKOS_DEPLOY"] = _PREV_DEPLOY

ACTOR_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000aa")
SUCURSAL_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000bb")
RESOLUCION_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000cc")
FE_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000d1")
REV_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000d2")
ENVIO_UUID = uuid_lib.UUID("00000000-0000-0000-0000-0000000000d3")


def _fake_session() -> MagicMock:
    """Minimal session stand-in — every repo call is mocked, the session
    is only forwarded to those mocks + ``apply_row``'s own ``flush()``.
    """
    session = MagicMock(name="session")
    session.flush = AsyncMock()
    # D5: dispatches are DEFERRED to after the commit (``defer_dispatch``
    # queues them in ``sync_session.info``); ``_drain`` plays the part of
    # the post-commit listener.
    session.sync_session = SimpleNamespace(
        info={}, get_nested_transaction=lambda: None, get_transaction=lambda: None
    )
    return session


async def _drain(session: MagicMock) -> None:
    """Run what the hooks queued, as the after-commit listener would."""
    queued = session.sync_session.info.get(dian_dispatch_on_sync._PENDING_KEY, [])
    for item in list(queued):
        await item.make(MagicMock(name="fresh_session"))
    queued.clear()


@pytest.fixture(autouse=True)
def _no_session_listeners():
    with patch.object(dian_dispatch_on_sync.event, "listen"):
        yield


def _fake_row(row_uuid: uuid_lib.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(uuid=row_uuid or uuid_lib.uuid4())


# ---------------------------------------------------------------------------
# 6. Catalog wiring — the hook is actually bound
# ---------------------------------------------------------------------------


class TestCatalogWiring:
    """``hook_post_insert`` is bound on the three DIAN-bound entries.

    Regression guard: a forgotten import in ``sync_entries_*.py`` would
    silently drop the wire-up (the catalog entry would simply not carry
    a ``hook_post_insert`` and the apply path would no-op). Pin the
    callables here so the binding cannot drift unnoticed.
    """

    def test_factura_electronica_hook_post_insert_is_dispatch_hook(self) -> None:
        spec = SYNC_CATALOG_BY_NAME["factura_electronica"]
        assert spec.hook_post_insert is dian_dispatch_on_sync.dian_factura_electronica_dispatch_hook

    def test_envio_dian_is_not_bound_to_the_cloud_dispatcher(self) -> None:
        """``envio_dian`` is cloud_to_branch: it is APPLIED at the branch, where the
        cloud dispatcher cannot be imported. The cloud dispatches from the
        ``factura_electronica`` / ``revocacion_factura`` hooks instead.
        """
        spec = SYNC_CATALOG_BY_NAME["envio_dian"]
        assert spec.direction == "cloud_to_branch"
        assert spec.hook_post_insert is None

    def test_revocacion_factura_hook_post_insert_is_dispatch_hook(self) -> None:
        spec = SYNC_CATALOG_BY_NAME["revocacion_factura"]
        assert spec.hook_post_insert is dian_dispatch_on_sync.dian_revocacion_factura_dispatch_hook

    def test_hooks_registered_in_registry_by_name(self) -> None:
        """The hooks self-register under stable names for introspection."""
        assert (
            hook_registry.get_hook("dian_factura_electronica_dispatch")
            is dian_dispatch_on_sync.dian_factura_electronica_dispatch_hook
        )
        assert (
            hook_registry.get_hook("dian_revocacion_factura_dispatch")
            is dian_dispatch_on_sync.dian_revocacion_factura_dispatch_hook
        )
        assert (
            hook_registry.get_hook("envio_dian_resume")
            is dian_dispatch_on_sync.envio_dian_resume_hook
        )


# ---------------------------------------------------------------------------
# 1. factura_electronica apply -> FE dispatcher fires
# ---------------------------------------------------------------------------


class TestFacturaElectronicaApplyFiresDispatch:
    """``factura_electronica`` apply dispatches via with-backoff on the
    just-written FE row's uuid.
    """

    @pytest.mark.asyncio
    async def test_apply_row_calls_dispatch_factura_electronica_with_backoff(
        self,
    ) -> None:
        spec = SYNC_CATALOG_BY_NAME["factura_electronica"]
        session = _fake_session()

        fe_row = _fake_row(FE_UUID)

        with (
            patch(
                "parkos_core.repo.event.record_event",
                new=AsyncMock(return_value=fe_row),
            ) as _record_mock,
            patch(
                "parkos_core.dian.cloud.dispatcher."
                "dispatch_factura_electronica_with_backoff",
                new=AsyncMock(),
            ) as dispatch_mock,
        ):
            payload = {
                "uuid_sucursal": SUCURSAL_UUID,
                "uuid_factura": uuid_lib.uuid4(),
                "uuid_cliente": None,
                "uuid_resolucion_facturacion": RESOLUCION_UUID,
                "prefijo": "SETP",
                "consecutivo": 42,
                "descuento": None,
            }
            result = await apply_row(
                session, spec, dict(payload), actor_uuid=ACTOR_UUID
            )

        await _drain(session)

        assert result.status == "APPLIED"
        assert result.row_uuid == FE_UUID

        # The hook ran — call signature binds the just-written FE uuid.
        dispatch_mock.assert_awaited_once()
        kwargs = dispatch_mock.await_args.kwargs
        assert kwargs["uuid_factura_electronica"] == FE_UUID
        assert kwargs["actor_uuid"] == ACTOR_UUID
        # Same env defaults the dispatcher module reads; the hook
        # forwards the URL + token path from its own module-load reads.
        assert "dian_provider_url" in kwargs
        assert "dian_token_path" in kwargs


# ---------------------------------------------------------------------------
# 2. revocacion_factura apply -> revocacion dispatcher fires
# ---------------------------------------------------------------------------


class TestRevocacionFacturaApplyFiresDispatch:
    """``revocacion_factura`` apply dispatches via with-backoff on the
    just-written revocacion row's uuid.
    """

    @pytest.mark.asyncio
    async def test_apply_row_calls_dispatch_revocacion_with_backoff(
        self,
    ) -> None:
        spec = SYNC_CATALOG_BY_NAME["revocacion_factura"]
        session = _fake_session()

        rev_row = _fake_row(REV_UUID)

        with (
            patch(
                "parkos_core.repo.append_only.append_event",
                new=AsyncMock(return_value=rev_row),
            ) as _append_mock,
            patch(
                "parkos_core.dian.cloud.dispatcher."
                "dispatch_revocacion_with_backoff",
                new=AsyncMock(),
            ) as dispatch_mock,
        ):
            payload = {
                "uuid_sucursal": SUCURSAL_UUID,
                "uuid_factura_electronica": uuid_lib.uuid4(),
                "uuid_factura_electronica_reemplazo": None,
                "motivo": "test motivo",
            }
            result = await apply_row(
                session, spec, dict(payload), actor_uuid=ACTOR_UUID
            )

        await _drain(session)

        assert result.status == "APPLIED"
        assert result.row_uuid == REV_UUID

        dispatch_mock.assert_awaited_once()
        kwargs = dispatch_mock.await_args.kwargs
        assert kwargs["uuid_revocacion_factura"] == REV_UUID
        assert kwargs["actor_uuid"] == ACTOR_UUID
