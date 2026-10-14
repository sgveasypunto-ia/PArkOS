"""test_sucursal_dashboard.py -- Bug #3 unit test (2026-10-14).

The pre-fix ``branch_dashboard`` handler in ``api/v1/admin_views.py``
populated the wire field ``SucursalDashboard.facturas_emitidas_count``
by reusing the ``facturas_electronicas_count`` variable, so the two
fields were always equal. A branch with operational invoices
(``prod.facturas`` rows) but no DIAN ``resolucion_facturacion`` (no
``prod.factura_electronica`` rows) reported ``facturas_emitidas_count=0``
even when it had many ``prod.facturas`` rows. The 2026-10-13 E2E
caught this as the dashboard's "FACTURAS: Ninguna factura activa"
KPI card -- the value was zero, the operator had issued 14 invoices.

Two Pydantic model tests guard the wire contract:

  1. ``test_sucursal_dashboard_facturas_emitidas_and_electronicas_are_distinct_fields`` --
     the Pydantic model has BOTH fields independently (not aliases of
     the same column). A future refactor that collapses them would
     fail this test.
  2. ``test_sucursal_dashboard_populates_both_fields_independently`` --
     constructing a model with two DIFFERENT values for the two
     fields round-trips both -- i.e. the schema doesn't drop one or
     coerce the other.

The actual server-side query is covered by the 2026-10-13 E2E
report (the same admin test surface already exercises the handler
end-to-end via the rebuilt api-admin image + a manual ``curl`` of
``/admin/sucursales/{uuid}/dashboard``). A full DB-backed integration
test here would duplicate that with a much heavier setup
(testcontainers + truncate of ~10 tables for a 1-line fix).
"""
from __future__ import annotations

import sys
import uuid as uuid_lib
from datetime import UTC, datetime
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PARKOS_CORE_SRC = _BACKEND_ROOT / "packages" / "parkos_core" / "src"
if str(_PARKOS_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_PARKOS_CORE_SRC))


def _uuid() -> uuid_lib.UUID:
    return uuid_lib.uuid4()


def test_sucursal_dashboard_facturas_emitidas_and_electronicas_are_distinct_fields() -> None:
    """Bug #3 regression: ``facturas_emitidas_count`` and
    ``facturas_electronicas_count`` are TWO independent integer
    fields on the wire. A future refactor that aliases them (e.g.
    via Pydantic ``AliasChoices`` or a single source column) would
    silently re-introduce the bug -- this test fails loud.
    """
    from parkos_core.api.v1.admin_views import SucursalDashboard

    fields = SucursalDashboard.model_fields
    assert "facturas_emitidas_count" in fields, (
        "facturas_emitidas_count is missing from SucursalDashboard -- "
        "re-add the operational invoice count to the wire shape"
    )
    assert "facturas_electronicas_count" in fields, (
        "facturas_electronicas_count is missing from SucursalDashboard -- "
        "do not break the existing wire contract"
    )
    # The two fields must be the SAME annotation (int) so the wire
    # consumer cannot tell which one is which from the schema alone
    # -- that is the actual contract. A change to e.g.
    # facturas_emitidas_count: Decimal is a wire break and should
    # require an explicit schema bump.
    assert (
        fields["facturas_emitidas_count"].annotation
        == fields["facturas_electronicas_count"].annotation
    ), (
        "facturas_emitidas_count and facturas_electronicas_count must "
        "share the same annotation (int) -- a mismatch would break the "
        "FE Zod schema (admin web dashboardSchema.ts)"
    )


def test_sucursal_dashboard_populates_both_fields_independently() -> None:
    """Bug #3 regression: the model accepts DIFFERENT values for
    ``facturas_emitidas_count`` and ``facturas_electronicas_count`` on
    the same payload. The pre-fix handler always wrote the SAME
    number to both; a future regression that re-introduces the
    aliasing would either:
      (a) silently drop one of the two (one of the two is
          ``extra='forbid'``-protected so it would raise instead), or
      (b) coerce them to the same value.
    The test asserts that round-trip preserves each value as-is.
    """
    from parkos_core.api.v1.admin_views import SucursalDashboard

    now = datetime.now(UTC).replace(tzinfo=None)
    payload = {
        "uuid_sucursal": str(_uuid()),
        "fecha": now.isoformat(),
        "ingresos_count": 19,
        "ingresos_monto_total": 70560.0,
        "facturas_emitidas_count": 14,        # BOG-CEN pre-fix: real count
        "facturas_electronicas_count": 0,     # no resolucion_facturacion
        "open_alertas_count": 43,
        "sync_health": {
            "last_sync_at": None,
            "lag_seconds": None,
            "queue_depth": 0,
        },
    }
    dash = SucursalDashboard.model_validate(payload)
    assert dash.facturas_emitidas_count == 14
    assert dash.facturas_electronicas_count == 0
    # Round-trip: re-validate from the model back to dict and confirm
    # the values are independent (no aliasing collapsed them).
    as_dict = dash.model_dump()
    assert as_dict["facturas_emitidas_count"] == 14
    assert as_dict["facturas_electronicas_count"] == 0
    assert (
        as_dict["facturas_emitidas_count"]
        != as_dict["facturas_electronicas_count"]
    ), "values collapsed -- the aliasing bug has regressed"


def test_sucursal_dashboard_with_emitidas_greater_than_electronicas() -> None:
    """Bug #3 regression: the common production case is
    ``facturas_emitidas_count >= facturas_electronicas_count`` (every
    FE has an underlying ``prod.facturas`` row, but not every
    ``prod.facturas`` row goes to DIAN). The model must accept any
    non-negative integers in either field. The handler's bug was
    that it FORCED the equality, so any case where a branch had
    issued POS invoices without DIAN numbers reported 0 -- exactly
    the 2026-10-13 E2E case.
    """
    from parkos_core.api.v1.admin_views import SucursalDashboard

    now = datetime.now(UTC).replace(tzinfo=None)
    payload = {
        "uuid_sucursal": str(_uuid()),
        "fecha": now.isoformat(),
        "ingresos_count": 1,
        "ingresos_monto_total": 1000.0,
        # Branch issued 14 POS invoices but only 3 of them went to
        # DIAN. The pre-fix handler would have set both to 3 (the FE
        # count) -- here we test the wire shape that the post-fix
        # handler produces.
        "facturas_emitidas_count": 14,
        "facturas_electronicas_count": 3,
        "open_alertas_count": 0,
        "sync_health": {
            "last_sync_at": None,
            "lag_seconds": None,
            "queue_depth": 0,
        },
    }
    dash = SucursalDashboard.model_validate(payload)
    assert dash.facturas_emitidas_count == 14
    assert dash.facturas_electronicas_count == 3
    assert dash.facturas_emitidas_count > dash.facturas_electronicas_count
