"""Schema/policy tests for per-branch config override resolution (REQ-OP-12, SC-OP-06).

Per PR4 plan, these are pure-Python tests — no live Postgres. We mock
``AsyncSession.execute()`` to verify the resolution policy:

- Per-branch row (vigente_hasta IS NULL AND uuid_sucursal = :requested) wins.
- Falls back to global default (uuid_sucursal IS NULL) when no per-branch.
- Returns None if neither is configured (caller raises 404).
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from parkos_core.models.V.configuracion_seguridad import ConfiguracionSeguridad
from parkos_core.repo.config_override import resolve_efectiva_seguridad

BRANCH_A = uuid_lib.UUID("00000000-0000-0000-0000-00000000000a")
BRANCH_B = uuid_lib.UUID("00000000-0000-0000-0000-00000000000b")
NOW = datetime(2026, 1, 1, 12, 0, 0)


def _row(
    *,
    uuid_sucursal: uuid_lib.UUID | None,
    dias_exp: int,
    max_int: int,
    mins_bloq: int,
) -> MagicMock:
    """Build a mock ORM row for ``configuracion_seguridad``."""
    row = MagicMock(spec=ConfiguracionSeguridad)
    row.uuid = uuid_lib.uuid4()
    row.uuid_sucursal = uuid_sucursal
    row.dias_expiracion_password = dias_exp
    row.max_intentos_login = max_int
    row.minutos_bloqueo_login = mins_bloq
    row.vigente_desde = NOW
    row.vigente_hasta = None
    row.estado = "activo"
    row.created_at = NOW
    row.created_by = None
    row.sync_status = None
    return row


def _result_for(row) -> MagicMock:
    """Wrap a row in a SQLAlchemy ``Result``-shaped mock with ``scalar_one_or_none``."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    return result


def _session_with_rows(*, branch_result, global_result) -> AsyncMock:
    """Mock AsyncSession whose ``execute()`` returns the given row sequence.

    The session.execute(stmt) is awaited once per call (1 branch, 1 global).
    Each call returns a ``Result``-shaped object that exposes
    ``scalar_one_or_none()`` returning the configured row (or ``None``).
    """
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[_result_for(branch_result), _result_for(global_result)]
    )
    return session


class TestResolveEfectivaSeguridad:
    """Per-branch override → global default resolution policy (REQ-OP-12, SC-OP-06)."""

    @pytest.mark.asyncio
    async def test_per_branch_wins_over_global(self):
        """Per-branch row wins when both are configured (override)."""
        branch_row = _row(uuid_sucursal=BRANCH_A, dias_exp=30, max_int=3, mins_bloq=15)
        global_row = _row(uuid_sucursal=None, dias_exp=90, max_int=5, mins_bloq=30)
        session = _session_with_rows(branch_result=branch_row, global_result=global_row)

        result = await resolve_efectiva_seguridad(session, BRANCH_A)

        assert result is branch_row, "Per-branch override must win over global"
        assert result.dias_expiracion_password == 30
        assert result.max_intentos_login == 3
        assert result.minutos_bloqueo_login == 15

    @pytest.mark.asyncio
    async def test_falls_back_to_global_when_no_per_branch(self):
        """Non-override branch (no per-branch row) gets the global default."""
        global_row = _row(uuid_sucursal=None, dias_exp=90, max_int=5, mins_bloq=30)
        session = _session_with_rows(branch_result=None, global_result=global_row)

        result = await resolve_efectiva_seguridad(session, BRANCH_B)

        assert result is global_row, "Non-override branch must get global default"
        assert result.dias_expiracion_password == 90

    @pytest.mark.asyncio
    async def test_returns_none_when_neither_configured(self):
        """No per-branch, no global → None (caller raises 404)."""
        session = _session_with_rows(branch_result=None, global_result=None)

        result = await resolve_efectiva_seguridad(session, BRANCH_A)

        assert result is None

    @pytest.mark.asyncio
    async def test_branch_a_overrides_branch_b_global_shared(self):
        """Two branches share global, only one overrides — each gets the right value."""
        branch_a_row = _row(uuid_sucursal=BRANCH_A, dias_exp=15, max_int=2, mins_bloq=10)
        global_row = _row(uuid_sucursal=None, dias_exp=60, max_int=4, mins_bloq=20)
        # For BRANCH_A: branch=branch_a_row, global=global_row → override wins
        session_a = _session_with_rows(branch_result=branch_a_row, global_result=global_row)
        result_a = await resolve_efectiva_seguridad(session_a, BRANCH_A)
        assert result_a is branch_a_row
        # For BRANCH_B: branch=None, global=global_row → fallback to global
        session_b = _session_with_rows(branch_result=None, global_result=global_row)
        result_b = await resolve_efectiva_seguridad(session_b, BRANCH_B)
        assert result_b is global_row


class TestConfiguracionSeguridadSchemaOverride:
    """Pydantic schema allows both None (global) and uuid (per-branch)."""

    def test_create_global_default(self):
        from parkos_core.schemas.configuracion import ConfiguracionSeguridadCreate
        c = ConfiguracionSeguridadCreate(
            uuid_sucursal=None,
            dias_expiracion_password=90,
            max_intentos_login=5,
            minutos_bloqueo_login=30,
        )
        assert c.uuid_sucursal is None
        assert c.dias_expiracion_password == 90

    def test_create_per_branch_override(self):
        from parkos_core.schemas.configuracion import ConfiguracionSeguridadCreate
        c = ConfiguracionSeguridadCreate(
            uuid_sucursal=BRANCH_A,
            dias_expiracion_password=15,
            max_intentos_login=2,
            minutos_bloqueo_login=10,
        )
        assert c.uuid_sucursal == BRANCH_A
        assert c.dias_expiracion_password == 15