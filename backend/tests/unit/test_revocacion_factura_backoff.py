"""test_revocacion_factura_backoff.py — T-PR9-010.

``revocacion_factura`` reuses the EXACT SAME DIAN backoff curve as
``factura_electronica`` — same DIAN evidentiary chain (``hash_chain`` +
``verify_chain``), same regulatory deadline. Asserts equality, not just
presence, so a divergent per-table curve is explicitly rejected.
"""
from __future__ import annotations

from parkos_core.dian.backoff import DIAN_BACKOFF_SCHEDULE, DIAN_MAX_RETRIES
from parkos_core.sync.catalog.sync_catalog import SYNC_CATALOG_BY_NAME


def test_revocacion_factura_and_factura_electronica_share_the_dian_curve() -> None:
    factura = SYNC_CATALOG_BY_NAME["factura_electronica"]
    revocacion = SYNC_CATALOG_BY_NAME["revocacion_factura"]

    assert factura.backoff_schedule == DIAN_BACKOFF_SCHEDULE
    assert revocacion.backoff_schedule == DIAN_BACKOFF_SCHEDULE
    # Equality, not just "both truthy" — a divergent per-table curve
    # (e.g. revocacion_factura declaring its own, slightly different
    # tuple) must be explicitly rejected by this assertion.
    assert factura.backoff_schedule == revocacion.backoff_schedule

    assert factura.max_retries == DIAN_MAX_RETRIES
    assert revocacion.max_retries == DIAN_MAX_RETRIES
    assert factura.max_retries == revocacion.max_retries

    assert factura.on_exhaustion == "fe_provider_error"
    assert revocacion.on_exhaustion == "fe_provider_error"
    assert factura.on_exhaustion == revocacion.on_exhaustion


def test_revocacion_factura_shares_the_dian_evidentiary_chain_shape() -> None:
    """Same regulatory clock, same hash-chain contract (not just the curve)."""
    revocacion = SYNC_CATALOG_BY_NAME["revocacion_factura"]
    assert revocacion.hash_chain is True
    assert revocacion.verify_chain is True


def test_envio_dian_explicitly_has_no_backoff_override() -> None:
    """T-PR9-005 acceptance: envio_dian's replication leg stays on the general curve."""
    envio_dian = SYNC_CATALOG_BY_NAME["envio_dian"]
    assert envio_dian.backoff_schedule is None
    assert envio_dian.max_retries is None
    assert envio_dian.on_exhaustion is None
