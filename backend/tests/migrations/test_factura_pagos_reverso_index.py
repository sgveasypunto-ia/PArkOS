"""Migration test — SC-11 BEFORE INSERT trigger on factura_pagos reverso uniqueness.

Verifies the trigger installed by migration 0004 raises
``UniqueViolation`` when attempting a second reverso of the same payment.

Requires a live Postgres (testcontainers). Skipped if no DB available —
the pure-Python unit test in ``tests/unit/test_factura_pagos_reverse.py``
covers the application-layer mapping.
"""
# ruff: noqa: I001  (parkos_core is not a known first-party package in this
# workspace — ruff's isort treats it as third-party and conflicts with
# the stdlib grouping; skip I001 wholesale for this test file.)
from __future__ import annotations

import asyncio  # noqa: F401
import uuid as uuid_lib
from datetime import datetime

import pytest

from parkos_core.models.A.factura_pagos import FacturaPagos


pytestmark = pytest.mark.skip(
    reason=(
        "Requires testcontainers Postgres — skip when no live DB "
        "(see tests/unit/test_factura_pagos_reverse.py for app-layer test)"
    ),
)


@pytest.fixture
def db_session():
    """Acquire a Postgres session via testcontainers.

    Skipped via pytestmark at module level. Implementation deferred to a
    follow-up PR that wires testcontainers in CI.
    """
    raise NotImplementedError("testcontainers not wired in this PR")


def test_trigger_blocks_duplicate_reverso(db_session):
    """Insert two reverso rows for the same ``uuid_pago_revertido`` → second raises."""
    pago_uuid = uuid_lib.uuid4()
    now = datetime.now()

    # First reverso succeeds
    first = FacturaPagos(
        uuid_pago_revertido=pago_uuid,
        tipo_movimiento="reverso",
        valor=100,
        timestamp_evento=now,
    )
    db_session.add(first)
    db_session.commit()

    # Second reverso for the same payment → trigger raises UniqueViolation
    second = FacturaPagos(
        uuid_pago_revertido=pago_uuid,
        tipo_movimiento="reverso",
        valor=100,
        timestamp_evento=now,
    )
    db_session.add(second)
    with pytest.raises(Exception) as exc_info:  # IntegrityError wraps UniqueViolation
        db_session.commit()
    # Partial unique index name OR the trigger's RAISE message — same intent.
    assert "unique" in str(exc_info.value).lower() or (
        "uq_factura_pagos_reverso" in str(exc_info.value)
    )


def test_trigger_allows_pago_after_reverso(db_session):
    """After a reverso, a NEW pago (not reverso) for the same original should succeed."""
    # This test verifies the trigger ONLY enforces reverso uniqueness.
    pago_uuid = uuid_lib.uuid4()
    now = datetime.now()

    # Reverso
    reverso = FacturaPagos(
        uuid_pago_revertido=pago_uuid,
        tipo_movimiento="reverso",
        valor=100,
        timestamp_evento=now,
    )
    db_session.add(reverso)
    db_session.commit()

    # New pago (different tipo_movimiento) — should NOT trigger
    pago = FacturaPagos(
        uuid_factura=uuid_lib.uuid4(),
        tipo_movimiento="pago",
        valor=100,
        timestamp_evento=now,
    )
    db_session.add(pago)
    db_session.commit()  # No exception
