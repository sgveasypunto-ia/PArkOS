"""test_config_override_tenant_scope_global.py — GLOBAL/override config rows
survive an active (non-matching) tenant scope.

THE DEFECT (found QA-testing configuracion-tolerancias/configuracion-seguridad,
2026-10-02)
--------------------------------------------------------------------------
``configuracion_tolerancias``/``configuracion_seguridad``/``configuracion_caja``
use ``uuid_sucursal IS NULL`` as an intentional GLOBAL-default row, with
per-branch rows overriding it (REQ-OP-12, SC-OP-06). ``db/tenancy.py``'s
``do_orm_execute`` listener auto-filters EVERY SELECT/UPDATE/DELETE on a
``uuid_sucursal``-bearing table by the admin's active branch
(``X-Sucursal-Context``) whenever that scope is bound — correct for genuinely
per-branch operational tables, but wrong here: a NULL column never satisfies
``uuid_sucursal = :ctx``, so with an active scope bound:

- ``router_factory``'s ``create_endpoint``/``update_endpoint`` call
  ``session.refresh(new_row)`` right after committing a GLOBAL insert/update;
  the listener scopes that refresh SELECT too, finds 0 rows, and SQLAlchemy
  raises ``InvalidRequestError: Could not refresh instance`` — a bare 500 on
  an otherwise-successful write. Live symptom: creating the GLOBAL default
  tolerancia/seguridad from the admin UI 500'd every time (an admin always
  has SOME branch active once one is selected).
- ``repo.config_override.resolve_efectiva_*`` (``GET .../efectiva``) can never
  fall back to the global default while a scope is bound: its own fallback
  SELECT (``uuid_sucursal IS NULL``) gets the same ``AND uuid_sucursal = :ctx``
  appended and never matches, so a branch with no override of its own
  incorrectly 404s instead of resolving the global default.

THE FIX
-------
``db.tenancy.suspend_tenant_context()`` temporarily unbinds the ContextVar for
one block; ``router_factory`` wraps its post-write refresh (and, for
``tenant_scoped=False`` resources, the versioned update's own pre-update
lookup) in it, and ``config_override.resolve_efectiva_*`` wraps its own two
SELECTs in it unconditionally (the resolver always takes an explicit target
branch, so it must never be narrowed by the CALLER's active branch).
"""

from __future__ import annotations

import uuid as uuid_lib
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from parkos_core.api import deps as api_deps  # installs the do_orm_execute listener
from parkos_core.db.tenancy import (
    get_current_sucursal_uuid,
    set_tenant_context,
    suspend_tenant_context,
)
from parkos_core.models.V.configuracion_seguridad import ConfiguracionSeguridad
from parkos_core.models.V.configuracion_tolerancias import ConfiguracionTolerancias
from parkos_core.repo.config_override import resolve_efectiva_seguridad
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from tests.conftest import VFixtureFactory

_ = api_deps


@pytest.fixture(autouse=True)
def _no_leaked_tenant_scope() -> AsyncIterator[None]:
    """Guarantee a clean ``ContextVar`` before and after every test (see the
    identical fixture in ``test_tenant_listener_isolation.py``)."""
    set_tenant_context(None)
    yield
    set_tenant_context(None)


async def test_suspend_tenant_context_restores_previous_scope_on_exit() -> None:
    branch = uuid_lib.uuid4()
    set_tenant_context(branch)

    with suspend_tenant_context():
        assert get_current_sucursal_uuid() is None

    assert get_current_sucursal_uuid() == branch


async def test_refresh_of_global_row_crashes_under_active_scope_and_suspend_fixes_it(
    pg_engine: AsyncEngine,
) -> None:
    """Pins the production 500 at the SQLAlchemy level, and that
    ``suspend_tenant_context`` is what ``router_factory`` now relies on to
    avoid it."""
    active_branch = uuid_lib.uuid4()
    Session = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with Session() as session:
        row = VFixtureFactory.build(
            ConfiguracionTolerancias,
            uuid_sucursal=None,
            tolerancia_efectivo=Decimal("1000"),
            tolerancia_datafono=Decimal("1000"),
        )
        session.add(row)
        await session.commit()

        set_tenant_context(active_branch)
        with pytest.raises(InvalidRequestError):
            await session.refresh(row)

        with suspend_tenant_context():
            await session.refresh(row)  # no longer raises

        assert row.uuid_sucursal is None


async def test_resolve_efectiva_falls_back_to_global_despite_active_scope_mismatch(
    pg_engine: AsyncEngine,
) -> None:
    requested_branch = uuid_lib.uuid4()  # has no override row of its own
    active_branch = uuid_lib.uuid4()  # admin's currently active branch — different

    Session = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with Session() as session:
        global_row = VFixtureFactory.build(
            ConfiguracionSeguridad,
            uuid_sucursal=None,
            max_intentos_login=5,
            minutos_bloqueo_login=15,
        )
        session.add(global_row)
        await session.commit()

        set_tenant_context(active_branch)
        resolved = await resolve_efectiva_seguridad(session, requested_branch)

    assert resolved is not None, "global fallback must resolve regardless of the active scope"
    assert resolved.uuid_sucursal is None
    assert resolved.max_intentos_login == 5
