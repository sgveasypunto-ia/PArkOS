"""GET /operacion/mi-turno/resumen-cierre -- post-close turn summary.

DB-mock pattern (mirrors ``test_mi_turno_endpoint.py``). The handler runs
four ``session.execute`` calls: (1) sesion lookup in the handler, (2)
sesion lookup in ``calcular_resumen_mi_turno``, (3) ingresos/salidas
COUNT, (4) the grouped ``factura_pagos`` SELECT.

Scenarios:
  S1: happy path -- payments grouped per medio_pago, reversals on their
      own line, ``transacciones_count`` = number of 'pago' rows.
  S2: zero state -- 200 with empty ``medios_pago``.
  S3: operador pinned to another branch -> 404 (uniform, no existence probe).
  S4: operador reading another operator's sesion -> 404 (uniform).
  S5: unknown sesion -> 404 sesion_not_found.
  S5b: still-open sesion -> 409 sesion_abierta (blind count is respected).
  S6: wire shape is additive and MiTurnoRead stays untouched.
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))

import pytest  # noqa: E402
from parkos_core.schemas.operacion import (  # noqa: E402
    MiTurnoRead,
    ResumenCierreTurnoRead,
)


def _make_sesion(*, sucursal: uuid_lib.UUID, usuario: uuid_lib.UUID) -> MagicMock:
    sesion = MagicMock()
    sesion.uuid = uuid_lib.uuid4()
    sesion.uuid_sucursal = sucursal
    sesion.uuid_usuario = usuario
    sesion.timestamp_apertura = datetime(2026, 10, 6, 8, 0, tzinfo=UTC).replace(tzinfo=None)
    sesion.timestamp_cierre = datetime(2026, 10, 6, 18, 0, tzinfo=UTC).replace(tzinfo=None)
    return sesion


def _make_ctx(*, sucursal: uuid_lib.UUID, actor: uuid_lib.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = actor
    ctx.issuer_prefix = "operador-"
    ctx.sucursal_uuid = sucursal
    return ctx


def _new_response() -> MagicMock:
    r = MagicMock()
    r.headers = {}
    return r


class _AllowAll:
    """Scope stub that allows every branch: isolates the operador- checks."""

    def allows(self, uuid_sucursal: uuid_lib.UUID | None) -> bool:
        return uuid_sucursal is not None


def _admin_ctx(*, actor: uuid_lib.UUID) -> MagicMock:
    ctx = MagicMock()
    ctx.actor_uuid = actor
    ctx.issuer_prefix = "admin-"
    ctx.sucursal_uuid = None  # global mode: no X-Sucursal-Context header
    return ctx


def _select_returning(sesion: MagicMock | None) -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = sesion
    return m


def _counts(ingresos: int, salidas: int) -> MagicMock:
    m = MagicMock()
    m.first.return_value = (ingresos, salidas)
    return m


def _grouped(rows: list[tuple[str | None, str | None, int, Decimal]]) -> MagicMock:
    m = MagicMock()
    m.all.return_value = rows
    return m


@pytest.mark.asyncio
async def test_happy_path_groups_by_medio_pago_and_reports_reversos() -> None:
    from parkos_core.api.v1 import operacion as handler_mod
    from parkos_core.repo import arqueo

    sucursal, usuario = uuid_lib.uuid4(), uuid_lib.uuid4()
    sesion = _make_sesion(sucursal=sucursal, usuario=usuario)
    ctx = _make_ctx(sucursal=sucursal, actor=usuario)
    response = _new_response()
    session = MagicMock()
    sel = _select_returning(sesion)
    session.execute = AsyncMock(
        side_effect=[
            sel,
            sel,
            _counts(7, 5),
            _grouped(
                [
                    ("pago", "efectivo", 4, Decimal("40000")),
                    ("pago", "datafono", 2, Decimal("30000")),
                    ("pago", None, 1, Decimal("1000")),
                    ("reverso", "efectivo", 1, Decimal("5000")),
                ]
            ),
        ]
    )

    with patch.object(
        arqueo, "_sum_factura_pagos_by_medio_pago", new=AsyncMock(return_value=Decimal("40000"))
    ):
        result = await handler_mod.get_resumen_cierre_turno(
            response=response,
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=ctx,
            _claims=None,
            scope=_AllowAll(),
        )

    assert isinstance(result, ResumenCierreTurnoRead)
    assert result.ingresos_count == 7
    assert result.salidas_count == 5
    assert result.transacciones_count == 7  # pagos only; reverso is a separate line
    by_medio = {m.medio_pago: (m.pagos_count, m.total_cop) for m in result.medios_pago}
    assert by_medio == {
        "datafono": (2, Decimal("30000")),
        "efectivo": (4, Decimal("40000")),
        "sin_especificar": (1, Decimal("1000")),
    }
    assert result.reversos_count == 1
    assert result.reversos_total_cop == Decimal("5000")
    assert response.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_zero_state_returns_empty_medios() -> None:
    from parkos_core.api.v1 import operacion as handler_mod
    from parkos_core.repo import arqueo

    sucursal, usuario = uuid_lib.uuid4(), uuid_lib.uuid4()
    sesion = _make_sesion(sucursal=sucursal, usuario=usuario)
    sel = _select_returning(sesion)
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[sel, sel, _counts(0, 0), _grouped([])])

    with patch.object(
        arqueo, "_sum_factura_pagos_by_medio_pago", new=AsyncMock(return_value=Decimal("0"))
    ):
        result = await handler_mod.get_resumen_cierre_turno(
            response=_new_response(),
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=_make_ctx(sucursal=sucursal, actor=usuario),
            _claims=None,
            scope=_AllowAll(),
        )

    assert result.medios_pago == []
    assert result.transacciones_count == 0
    assert result.reversos_count == 0
    assert result.reversos_total_cop == Decimal("0")


@pytest.mark.asyncio
async def test_cross_branch_operator_gets_uniform_404() -> None:
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod

    usuario = uuid_lib.uuid4()
    sesion = _make_sesion(sucursal=uuid_lib.uuid4(), usuario=usuario)
    session = MagicMock()
    session.execute = AsyncMock(return_value=_select_returning(sesion))

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_resumen_cierre_turno(
            response=_new_response(),
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=_make_ctx(sucursal=uuid_lib.uuid4(), actor=usuario),
            _claims=None,
            scope=_AllowAll(),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "sesion_not_found"


@pytest.mark.asyncio
async def test_other_operators_sesion_gets_uniform_404() -> None:
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod

    sucursal = uuid_lib.uuid4()
    sesion = _make_sesion(sucursal=sucursal, usuario=uuid_lib.uuid4())
    session = MagicMock()
    session.execute = AsyncMock(return_value=_select_returning(sesion))

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_resumen_cierre_turno(
            response=_new_response(),
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=_make_ctx(sucursal=sucursal, actor=uuid_lib.uuid4()),
            _claims=None,
            scope=_AllowAll(),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "sesion_not_found"


@pytest.mark.asyncio
async def test_unknown_sesion_gets_404() -> None:
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod

    session = MagicMock()
    session.execute = AsyncMock(return_value=_select_returning(None))

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_resumen_cierre_turno(
            response=_new_response(),
            uuid_sesion=uuid_lib.uuid4(),
            session=session,
            ctx=_make_ctx(sucursal=uuid_lib.uuid4(), actor=uuid_lib.uuid4()),
            _claims=None,
            scope=_AllowAll(),
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "sesion_not_found"


@pytest.mark.asyncio
async def test_open_sesion_gets_409_before_any_total_is_exposed() -> None:
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod

    sucursal, usuario = uuid_lib.uuid4(), uuid_lib.uuid4()
    sesion = _make_sesion(sucursal=sucursal, usuario=usuario)
    sesion.timestamp_cierre = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=_select_returning(sesion))

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_resumen_cierre_turno(
            response=_new_response(),
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=_make_ctx(sucursal=sucursal, actor=usuario),
            _claims=None,
            scope=_AllowAll(),
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "sesion_abierta"
    # Only the sesion lookup ran: no aggregate was computed.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_admin_outside_allowed_sucursales_gets_uniform_404_before_the_409() -> None:
    """A global-mode admin- token must not read another branch's totals."""
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod
    from parkos_core.auth.tenancy import BranchScope

    admin = uuid_lib.uuid4()
    sesion = _make_sesion(sucursal=uuid_lib.uuid4(), usuario=uuid_lib.uuid4())
    sesion.timestamp_cierre = None  # open: the 409 must NOT leak for foreign branches
    session = MagicMock()
    session.execute = AsyncMock(return_value=_select_returning(sesion))
    scope = BranchScope(
        actor_uuid=admin, issuer_prefix="admin-", permitidas=frozenset({uuid_lib.uuid4()})
    )

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_resumen_cierre_turno(
            response=_new_response(),
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=_admin_ctx(actor=admin),
            _claims=None,
            scope=scope,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "sesion_not_found"
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_admin_inside_allowed_sucursales_reaches_the_closed_sesion_check() -> None:
    from fastapi import HTTPException
    from parkos_core.api.v1 import operacion as handler_mod
    from parkos_core.auth.tenancy import BranchScope

    admin, sucursal = uuid_lib.uuid4(), uuid_lib.uuid4()
    sesion = _make_sesion(sucursal=sucursal, usuario=uuid_lib.uuid4())
    sesion.timestamp_cierre = None
    session = MagicMock()
    session.execute = AsyncMock(return_value=_select_returning(sesion))
    scope = BranchScope(actor_uuid=admin, issuer_prefix="admin-", permitidas=frozenset({sucursal}))

    with pytest.raises(HTTPException) as exc_info:
        await handler_mod.get_resumen_cierre_turno(
            response=_new_response(),
            uuid_sesion=sesion.uuid,
            session=session,
            ctx=_admin_ctx(actor=admin),
            _claims=None,
            scope=scope,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "sesion_abierta"


def test_wire_shape_is_additive_and_mi_turno_read_is_frozen() -> None:
    assert set(MiTurnoRead.model_fields) == {
        "uuid_sesion",
        "uuid_sucursal",
        "timestamp_calculo",
        "ingresos_count",
        "salidas_count",
        "total_cobrado_efectivo_cop",
        "total_cobrado_datafono_cop",
    }
    assert set(ResumenCierreTurnoRead.model_fields) == {
        "uuid_sesion",
        "uuid_sucursal",
        "timestamp_calculo",
        "ingresos_count",
        "salidas_count",
        "transacciones_count",
        "medios_pago",
        "reversos_count",
        "reversos_total_cop",
    }
    with pytest.raises(Exception):  # extra='forbid' -> pydantic ValidationError
        ResumenCierreTurnoRead(
            uuid_sesion=uuid_lib.uuid4(),
            uuid_sucursal=uuid_lib.uuid4(),
            timestamp_calculo=datetime.now(tz=UTC),
            unexpected=1,  # type: ignore[call-arg]
        )
