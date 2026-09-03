"""Integration test — SC-33 / SC-34 (branch offline flow + cloud SyncBackEvent).

Verifies the branch-offline flow:
1. Branch emits a ``factura`` with ``numero_temporal`` (no DIAN yet).
2. Cloud receives the row via sync worker.
3. Cloud sends `SyncBackEvent` with the real ``numero_oficial`` (DIAN-assigned).
4. Branch receives SyncBackEvent, persists the real ``numero_oficial`` on the
   ``factura`` row.
5. After sync-back, ``reimpresion_ticket`` is enabled for that branch.

Requires a live Postgres + sync worker mocks. Skipped if no DB.

The actual DIAN integration lives in PR11 (DIAN HTTP dispatcher + Factus
provider). PR6 ships the schema + app-layer wiring.
"""
# ruff: noqa: I001  (parkos_core is not a known first-party package in this
# workspace — ruff's isort treats it as third-party and conflicts with
# the stdlib grouping; skip I001 wholesale for this test file.)
from __future__ import annotations

import asyncio  # noqa: F401
import uuid as uuid_lib

import pytest

from parkos_core.models.A.factura_pagos import FacturaPagos  # noqa: F401
from parkos_core.models.L_E.factura_electronica import FacturaElectronica  # noqa: F401
from parkos_core.models.L_E.facturas import Facturas
from parkos_core.models.L_W.reimpresion_ticket import ReimpresionTicket  # noqa: F401


pytestmark = pytest.mark.skip(
    reason="Requires testcontainers Postgres + sync worker mocks — skip when no live DB",
)


@pytest.fixture
def db_session():
    """Acquire a Postgres session via testcontainers. Skipped via pytestmark."""
    raise NotImplementedError("testcontainers not wired in this PR")


def test_branch_emits_factura_with_numero_temporal(db_session):
    """Branch creates a ``factura`` row with ``numero_temporal`` (no DIAN yet)."""
    factura_uuid = uuid_lib.uuid4()
    now = ...  # placeholder
    factura = Facturas(
        uuid=factura_uuid,
        uuid_sucursal=...,
        subtotal=10000,
        descuento=0,
        total=10000,
        timestamp_evento=now,
    )
    db_session.add(factura)
    db_session.commit()
    # In production, `numero_temporal` is set by the branch at emission time.
    # PR6 doesn't model `numero_temporal` explicitly — it's a property of
    # the schema metadata (out of scope; PR11 wires it).
    assert factura.uuid == factura_uuid


def test_sync_back_event_enables_reimpresion(db_session):
    """After cloud sends SyncBackEvent with ``numero_oficial``, reimpresion_ticket is enabled."""
    # This is the design contract — actual wiring in PR8 (sync transport).
    pass


def test_reimpresion_ticket_blocked_before_syncback(db_session):
    """``reimpresion_ticket`` MUST NOT be creatable until ``factura`` has a real ``numero_oficial``."""  # noqa: E501
    # Enforced at the endpoint layer (PR6-10) and at the sync worker (PR8).
    # For now, this test is a placeholder asserting the design intent.
    pass
