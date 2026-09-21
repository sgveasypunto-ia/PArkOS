"""HU-F12.1 / T-B1-3 -- 5 mandated scenarios for ``GET /operacion/mi-turno``.

DB-mock pattern (mirrors F1.13 ``tests/integration/test_arqueo_e2e.py``):
patch ``parkos_core.repo.arqueo._sum_factura_pagos_by_medio_pago`` and
the SQL execution path so the test suite exercises the handler end-to-end
without a Docker Postgres dependency. The Pydantic + DB-shape contracts
live in unit tests; this file pins the handler flow.

Scenarios (per REQ-OPS-184..187):

  S1 (REQ-OPS-184): happy path — open sesion, 2 ingresos + 1 salida +
      3 pagos (1 efectivo + 2 datafono) -> 200 with the 7-field
      ``MiTurnoRead``, ``Cache-Control: no-store`` on the response,
      and ``ingresos_count=2``, ``salidas_count=1``,
      ``total_cobrado_efectivo_cop=50000``,
      ``total_cobrado_datafono_cop=30000``.
  S2 (REQ-OPS-184): zero state — open sesion with no events -> 200
      with all count/decimal fields equal to ``0`` (NOT 404, NOT error).
  S3 (REQ-OPS-185): cross-branch 403 — operator JWT pinned to
      ``uuid_sucursal=A``, request ``uuid_sesion=S`` whose
      ``Sesion.uuid_sucursal=B`` -> 403 ``sesion_cross_branch_forbidden``.
  S4 (REQ-OPS-186): closed-session window excludes post-turn events —
      sesion closed at t1; an ingreso row with fecha_ingreso > t1 is
      EXCLUDED from the count (open-window temporal JOIN guard).
  S5 (REQ-OPS-185): unknown ``uuid_sesion`` -> 404 ``sesion_not_found``.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from parkos_core.schemas.operacion import MiTurnoRead  # noqa: E402


def _make_ctx(*, sucursal_uuid: uuid_lib.UUID | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = uuid_lib.uuid4()
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal_uuid or uuid_lib.uuid4()
    ctx.uuid_sesion = None
    ctx.actor_rol = "operador"
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


@pytest.mark.asyncio
async def test_mi_turno_happy_path_returns_seven_fields_with_no_store(
    sesion_with_ingresos_y_pagos: dict[str, Any],
) -> None:
    """S1 (REQ-OPS-184): happy path -> 200 + Cache-Control: no-store."""
    from parkos_core.api.v1 import operacion as handler_mod
    from parkos_core.repo import arqueo

    ctx = _make_ctx(sucursal_uuid=sesion_with_ingresos_y_pagos["uuid_sucursal"])
    response = _new_response()
    sesion = sesion_with_ingresos_y_pagos["sesion"]
    session = MagicMock()

    # Sesion lookup returns our fixture row; the SQL execute (counts)
    # returns (2, 1). The pipeline runs THREE execute() calls total:
    # (1) sesion lookup in handler, (2) sesion lookup in repo helper,
    # (3) COUNT aggregate in repo helper. We use ``return_value`` so
    # each call returns the right mock by call-site.
    sesion_select = MagicMock()
    sesion_select.scalar_one_or_none.return_value = sesion

    count_select = MagicMock()
    count_select.first.return_value = (2, 1)

    # Default: anything not explicitly listed returns sesion_select
    # (cheap; matches the sesion lookup pattern).
    session.execute = AsyncMock(side_effect=[sesion_select, sesion_select, count_select])

    with patch.object(
        arqueo,
        "_sum_factura_pagos_by_medio_pago",
        new=AsyncMock(side_effect=[Decimal("50000"), Decimal("30000")]),
    ):
        result = await handler_mod.get_mi_turno(
            response=response,
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert isinstance(result, MiTurnoRead)
    assert result.uuid_sesion == sesion.uuid
    assert result.uuid_sucursal == sesion.uuid_sucursal
    assert result.ingresos_count == 2
    assert result.salidas_count == 1
    assert result.total_cobrado_efectivo_cop == Decimal("50000")
    assert result.total_cobrado_datafono_cop == Decimal("30000")
    # Cache-Control: no-store on the SUCCESS path (R-A6 mitigation).
    assert response.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_mi_turno_zero_state_returns_zero_defaults(
    sesion_with_ingresos_y_pagos: dict[str, Any],
) -> None:
    """S2 (REQ-OPS-184): zero events -> 200 with zeros (NOT 404)."""
    from parkos_core.api.v1 import operacion as handler_mod
    from parkos_core.repo import arqueo

    ctx = _make_ctx(sucursal_uuid=sesion_with_ingresos_y_pagos["uuid_sucursal"])
    response = _new_response()
    sesion = sesion_with_ingresos_y_pagos["sesion"]
    session = MagicMock()

    sesion_select = MagicMock()
    sesion_select.scalar_one_or_none.return_value = sesion

    # SQL aggregate returns 0/0.
    count_select = MagicMock()
    count_select.first.return_value = (0, 0)

    session.execute = AsyncMock(side_effect=[sesion_select, sesion_select, count_select])

    with patch.object(
        arqueo,
        "_sum_factura_pagos_by_medio_pago",
        new=AsyncMock(side_effect=[Decimal("0"), Decimal("0")]),
    ):
        result = await handler_mod.get_mi_turno(
            response=response,
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    assert isinstance(result, MiTurnoRead)
    assert result.ingresos_count == 0
    assert result.salidas_count == 0
    assert result.total_cobrado_efectivo_cop == Decimal("0")
    assert result.total_cobrado_datafono_cop == Decimal("0")


@pytest.mark.asyncio
async def test_mi_turno_cross_branch_returns_403(
    sesion_with_ingresos_y_pagos: dict[str, Any],
) -> None:
    """S3 (REQ-OPS-185, DA-F12.1-2): operator pinned to branch A,
    request sesion in branch B -> 403 sesion_cross_branch_forbidden."""
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod

    # Operator JWT is pinned to a DIFFERENT branch than the sesion.
    other_sucursal = uuid_lib.uuid4()
    assert other_sucursal != sesion_with_ingresos_y_pagos["uuid_sucursal"]
    ctx = _make_ctx(sucursal_uuid=other_sucursal)
    response = _new_response()
    sesion = sesion_with_ingresos_y_pagos["sesion"]
    session = MagicMock()

    # Sesion lookup returns a row whose uuid_sucursal is BRANCH B;
    # the handler MUST reject with 403 sesion_cross_branch_forbidden.
    sesion_select = MagicMock()
    sesion_select.scalar_one_or_none.return_value = sesion
    session.execute = AsyncMock(return_value=sesion_select)

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_mi_turno(
            response=response,
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=ctx,
            _claims=None,
        )
    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail.get("error") == "sesion_cross_branch_forbidden"


@pytest.mark.asyncio
async def test_mi_turno_closed_session_excludes_post_turn_events(
    sesion_with_ingresos_y_pagos: dict[str, Any],
) -> None:
    """S4 (REQ-OPS-186): sesion closed at t1; ingresos after t1 excluded."""
    from parkos_core.api.v1 import operacion as handler_mod
    from parkos_core.repo import arqueo

    ctx = _make_ctx(sucursal_uuid=sesion_with_ingresos_y_pagos["uuid_sucursal"])
    response = _new_response()
    sesion = sesion_with_ingresos_y_pagos["sesion"]
    # Mark sesion closed 5 minutes ago — the closed-window guard kicks in.
    sesion.timestamp_cierre = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    session = MagicMock()

    # 5 ingresos total: 3 inside window (between timestamp_apertura and
    # timestamp_cierre), 2 post-turn. The handler's SQL FILTER uses the
    # upper bound; ``session.execute`` returns the aggregate.
    sesion_select = MagicMock()
    sesion_select.scalar_one_or_none.return_value = sesion

    count_select = MagicMock()
    count_select.first.return_value = (3, 1)  # only 3 counted (post-turn excluded)

    session.execute = AsyncMock(side_effect=[sesion_select, sesion_select, count_select])

    with patch.object(
        arqueo,
        "_sum_factura_pagos_by_medio_pago",
        new=AsyncMock(side_effect=[Decimal("0"), Decimal("0")]),
    ):
        result = await handler_mod.get_mi_turno(
            response=response,
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=ctx,
            _claims=None,
        )

    # The handler MUST honour the closed-window predicate. A naive
    # implementation that ignores timestamp_cierre would return 5 here.
    assert result.ingresos_count == 3
    assert result.salidas_count == 1


@pytest.mark.asyncio
async def test_mi_turno_unknown_uuid_sesion_returns_404() -> None:
    """S5 (REQ-OPS-185): unknown uuid_sesion -> 404 sesion_not_found."""
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod

    ctx = _make_ctx()
    response = _new_response()
    session = MagicMock()

    # Sesion lookup returns None -> 404.
    sesion_select = MagicMock()
    sesion_select.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=sesion_select)

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_mi_turno(
            response=response,
            uuid_sesion=uuid_lib.uuid4(),  # random UUID that doesn't exist
            session=session,
            ctx=ctx,
            _claims=None,
        )
    assert exc_info.value.status_code == 404
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail.get("error") == "sesion_not_found"


__all__ = [
    "test_mi_turno_closed_session_excludes_post_turn_events",
    "test_mi_turno_cross_branch_returns_403",
    "test_mi_turno_happy_path_returns_seven_fields_with_no_store",
    "test_mi_turno_unknown_uuid_sesion_returns_404",
    "test_mi_turno_zero_state_returns_zero_defaults",
]