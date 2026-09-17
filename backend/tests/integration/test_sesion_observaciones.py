"""test_sesion_observaciones.py -- REQ-OPS-135 (Bug 5 of qa-2026-09-17).

QA-2026-09-17 bug-remediation: bug 5 surfaced the case where
``POST /caja-sesion/sesiones`` rejected ``observaciones`` from the
F3.3 frontend with HTTP 422 ``extra_forbidden`` because
``SesionCreate`` inherited ``extra='forbid'`` from ``_Base`` and the
column did not exist on ``prod.sesion``. Migration 0035 +
``models/L_S/sesion.py`` + ``schemas/caja.py`` + ``repo/session_cycle.py``
together heal the path end-to-end.

TDD RED-then-GREEN coverage:

  T1 -- ``test_open_session_persists_observations_and_logs``: when
       ``observaciones='Apertura turno mañana'`` is supplied, the
       ``Sesion`` row carries the value AND the
       ``prod.log_transaccional.datos_nuevos`` JSONB carries the same
       value under the ``observaciones`` key (audit propagation
       per REQ-OPS-021).

  T2 -- ``test_open_session_observations_omitted_when_null``: when
       ``observaciones`` is omitted, the column is ``NULL`` AND the
       ``datos_nuevos`` JSONB does NOT carry the ``observaciones``
       key (no empty-key noise in audit).

  T3 -- ``test_sesion_create_schema_accepts_observations_field``: the
       ``SesionCreate`` Pydantic model accepts the field and rejects
       extras (REQ-OPS-135 ``extra='forbid'``).

  T4 -- ``test_sesion_create_schema_rejects_extra_field``: an unknown
       ``foo: 'bar'`` field is rejected by ``extra='forbid'``,
       matching the 422 ``extra_forbidden`` discriminated error
       documented in REQ-OPS-135 scenario 2.

Mock-based: the source-level tests do NOT require Docker; the
DB-layer assertions are exercised via ``pg_engine`` + alembic
upgrade in CI with ``PARKOS_DOCKER_TEST=1``.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import uuid as uuid_lib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_add_capture(captured_session_rows, captured_log_rows):
    """Return a ``side_effect`` callback for ``session.add`` that
    routes ``Sesion`` instances to one list and ``LogTransaccional``
    to another.
    """
    def _cb(obj):
        if obj.__class__.__name__ == "Sesion":
            captured_session_rows.append(obj)
        else:
            captured_log_rows.append(obj)
    return _cb


def _run_open_session(**overrides):
    """Execute ``open_session`` against a MagicMock session. Returns
    ``(captured_session_rows, captured_log_rows)``.
    """
    captured_session_rows: list = []
    captured_log_rows: list = []

    mock_session = MagicMock()
    mock_session.add = MagicMock(
        side_effect=_classify_add_capture(captured_session_rows, captured_log_rows)
    )
    mock_session.flush = AsyncMock()
    mock_session.rollback = AsyncMock()

    actor_uuid = uuid_lib.uuid4()
    suc_uuid = uuid_lib.uuid4()
    user_uuid = uuid_lib.uuid4()

    async def _drive():
        from parkos_core.repo.session_cycle import open_session

        return await open_session(
            mock_session,
            actor_uuid=actor_uuid,
            uuid_sucursal=suc_uuid,
            valor_inicial_efectivo=100.0,
            valor_inicial_datafono=0.0,
            uuid_usuario=user_uuid,
            log_tx=True,
            **overrides,
        )

    asyncio.run(_drive())
    return captured_session_rows, captured_log_rows


# ---------------------------------------------------------------------------
# T1 + T2 -- open_session() propagates observaciones to row + log
# ---------------------------------------------------------------------------


def test_open_session_persists_observations_and_logs() -> None:
    """T1 GREEN: ``open_session(observaciones=...)`` writes to BOTH
    the ``Sesion`` row AND the ``datos_nuevos`` JSONB audit field.

    REQ-OPS-135 AUDIT-FIRST canon: the value is mirrored into
    ``prod.log_transaccional.datos_nuevos`` so the canonical audit
    log carries the operator's notes (no information loss between the
    source column and the audit row).
    """
    captured_session_rows, captured_log_rows = _run_open_session(
        observaciones="Apertura turno mañana",
    )

    assert len(captured_session_rows) == 1, (
        "REQ-OPS-135 violated: open_session must persist exactly one "
        f"Sesion row; got {len(captured_session_rows)}"
    )
    sesion_row = captured_session_rows[0]
    assert sesion_row.observaciones == "Apertura turno mañana", (
        f"REQ-OPS-135 violated: Sesion.observaciones must equal "
        f"'Apertura turno mañana'; got {sesion_row.observaciones!r}"
    )

    assert len(captured_log_rows) == 1, (
        "REQ-OPS-135 violated: log_tx=True must emit exactly one "
        f"log_transaccional row; got {len(captured_log_rows)}"
    )
    log_row = captured_log_rows[0]
    assert log_row.datos_nuevos is not None, (
        "REQ-OPS-135 violated: datos_nuevos must be a dict (not None)"
    )
    assert "observaciones" in log_row.datos_nuevos, (
        "REQ-OPS-135 violated: datos_nuevos must carry 'observaciones' "
        f"key when observations is non-empty; got "
        f"{sorted(log_row.datos_nuevos)!r}"
    )
    assert log_row.datos_nuevos["observaciones"] == "Apertura turno mañana", (
        "REQ-OPS-135 violated: datos_nuevos.observaciones must equal "
        "the input value; got "
        f"{log_row.datos_nuevos['observaciones']!r}"
    )
    # The cash columns MUST also be present (regression guard):
    assert "valor_inicial_efectivo" in log_row.datos_nuevos
    assert "valor_inicial_datafono" in log_row.datos_nuevos


def test_open_session_observations_omitted_when_null() -> None:
    """T2 GREEN: ``observaciones=None`` produces a NULL column AND no
    ``observaciones`` key in ``datos_nuevos`` (no empty-key noise).
    """
    captured_session_rows, captured_log_rows = _run_open_session(
        observaciones=None,
    )

    assert len(captured_session_rows) == 1
    sesion_row = captured_session_rows[0]
    assert sesion_row.observaciones is None, (
        f"REQ-OPS-135 violated: Sesion.observaciones must be None when "
        f"input is None; got {sesion_row.observaciones!r}"
    )

    assert len(captured_log_rows) == 1
    log_row = captured_log_rows[0]
    assert "observaciones" not in log_row.datos_nuevos, (
        "REQ-OPS-135 violated: datos_nuevos must NOT carry "
        f"'observaciones' key when observations is None; got "
        f"{sorted(log_row.datos_nuevos)!r}"
    )


def test_open_session_empty_string_observations_treated_as_none() -> None:
    """T2 GOLD: empty-string observaciones is normalized to no-key
    in ``datos_nuevos`` (the column still gets the empty string,
    but the audit payload does NOT carry the empty-key noise).
    """
    captured_session_rows, captured_log_rows = _run_open_session(
        observaciones="",
    )

    sesion_row = captured_session_rows[0]
    # The column carries empty string (operator input is preserved).
    assert sesion_row.observaciones == "", (
        "Sesion.observaciones must equal the empty-string input"
    )

    log_row = captured_log_rows[0]
    assert "observaciones" not in log_row.datos_nuevos, (
        "REQ-OPS-135 violated: empty-string observations must NOT "
        "appear as a key in datos_nuevos (no empty-key noise); got "
        f"{sorted(log_row.datos_nuevos)!r}"
    )


# ---------------------------------------------------------------------------
# T3 + T4 -- SesionCreate Pydantic schema accepts/rejects the field
# ---------------------------------------------------------------------------


def test_sesion_create_schema_accepts_observations_field() -> None:
    """T3 GREEN: ``SesionCreate`` accepts the ``observaciones`` field
    (capped at 500 chars per REQ-OPS-135 / F3.3 cap).
    """
    from parkos_core.schemas.caja import SesionCreate

    s = SesionCreate(
        uuid_sucursal="00000000-0000-0000-0000-000000000001",
        uuid_usuario="00000000-0000-0000-0000-000000000002",
        valor_inicial_efectivo=100.0,
        valor_inicial_datafono=0.0,
        observaciones="Apertura turno mañana",
    )
    assert s.observaciones == "Apertura turno mañana", (
        f"SesionCreate.observaciones must equal the input; got {s.observaciones!r}"
    )

    # NULL is valid (operator without notes).
    s2 = SesionCreate(
        uuid_sucursal="00000000-0000-0000-0000-000000000001",
        uuid_usuario="00000000-0000-0000-0000-000000000002",
        valor_inicial_efectivo=100.0,
        valor_inicial_datafono=0.0,
    )
    assert s2.observaciones is None, (
        "SesionCreate.observaciones must default to None when omitted"
    )


def test_sesion_create_schema_rejects_extra_field() -> None:
    """T4 GREEN: ``SesionCreate`` rejects an unknown ``foo: 'bar'`` field
    with the 422 ``extra_forbidden`` discriminator documented in
    REQ-OPS-135 scenario 2.
    """
    from parkos_core.schemas.caja import SesionCreate

    with pytest.raises(Exception) as exc_info:
        SesionCreate(
            uuid_sucursal="00000000-0000-0000-0000-000000000001",
            uuid_usuario="00000000-0000-0000-0000-000000000002",
            valor_inicial_efectivo=100.0,
            valor_inicial_datafono=0.0,
            foo="bar",  # noqa: unknown field -- should be rejected
        )
    # Pydantic v2 raises ``ValidationError`` with type='extra_forbidden'
    err_str = str(exc_info.value)
    assert "extra_forbidden" in err_str or "extra" in err_str.lower(), (
        f"REQ-OPS-135 violated: SesionCreate must reject unknown fields "
        f"with the extra_forbidden discriminator; got {err_str!r}"
    )


def test_sesion_create_schema_rejects_observations_over_max_length() -> None:
    """T4 GOLD: 501+ char observaciones is rejected (F3.3 cap is 500)."""
    from parkos_core.schemas.caja import SesionCreate

    with pytest.raises(Exception) as exc_info:
        SesionCreate(
            uuid_sucursal="00000000-0000-0000-0000-000000000001",
            uuid_usuario="00000000-0000-0000-0000-000000000002",
            valor_inicial_efectivo=100.0,
            valor_inicial_datafono=0.0,
            observaciones="X" * 501,
        )
    err_str = str(exc_info.value)
    assert "500" in err_str or "max_length" in err_str.lower(), (
        f"REQ-OPS-135 violated: SesionCreate must reject observaciones > "
        f"500 chars; got {err_str!r}"
    )


# ---------------------------------------------------------------------------
# Migration 0035 module metadata (REQ-OPS-135 contract)
# ---------------------------------------------------------------------------


def test_migration_0035_module_chains_after_0034() -> None:
    """REQ-OPS-135 contract: migration 0035 chains off F1.5 / MV gate
    (migration 0034) so the chain stays linear in ``alembic_version``.

    Pre-implementation this raises ``ModuleNotFoundError`` -- that is
    the RED state. The test pins the source-level invariant so a
    future refactor cannot silently re-parent 0035 to a different
    head and break the chain.
    """
    sys.path.insert(
        0,
        str(
            _BACKEND_ROOT
            / "packages"
            / "parkos_core"
            / "migrations"
            / "versions"
        ),
    )
    mod = importlib.import_module("0035_add_observaciones_to_sesion")
    assert mod.revision == "0035_add_observaciones_to_sesion", (
        f"unexpected revision id: {mod.revision!r}"
    )
    assert mod.down_revision == "0034_recreate_mv_ocupacion_diaria_idempotent", (
        "REQ-OPS-135 violated: migration 0035 must chain off 0034 "
        f"(MV gate); got {mod.down_revision!r}"
    )
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


__all__ = [
    "test_migration_0035_module_chains_after_0034",
    "test_open_session_empty_string_observations_treated_as_none",
    "test_open_session_observations_omitted_when_null",
    "test_open_session_persists_observations_and_logs",
    "test_sesion_create_schema_accepts_observations_field",
    "test_sesion_create_schema_rejects_extra_field",
    "test_sesion_create_schema_rejects_observations_over_max_length",
]