"""catalog/entries/sync_entries_le.py — 3 [L-E] catalog entries (T-PR2-007).

``factura_electronica`` is a **single** catalog entry (D1-rev, D6-rev) — no
``sync_back_event`` field, not present in ``LocalOnlyCatalog``. Emitted at
the branch with the branch's own ``resolucion_facturacion``; the cloud
validates and forwards to the DIAN provider, recording the exchange in
``envio_dian`` (``sync_entries_lw.py``).
"""
from __future__ import annotations

from ....models.L_E.factura_electronica import FacturaElectronica
from ....models.L_E.facturas import Facturas
from ....models.L_E.ingreso import Ingreso
from ..schema import SyncCatalogEntry

_INGRESO = SyncCatalogEntry(
    name="ingreso",
    model_cls=Ingreso,
    audit_class="L_E",
    sync_strategy="append",
    direction="branch_to_cloud",
    # No broadcast target — branch_to_cloud entries have a single
    # destination (cloud); broadcast_policy only scopes cloud_to_branch /
    # bidirectional distribution (REQ-CAT-004: "—" for this ER signal).
    broadcast_policy=None,
    apply_strategy="record_event",
    depends_on=("sucursal", "tipos_vehiculo"),
    has_uuid_sucursal=True,
    seq_strategy="max_timestamp_evento",
)

_FACTURAS = SyncCatalogEntry(
    name="facturas",
    model_cls=Facturas,
    audit_class="L_E",
    sync_strategy="append",
    direction="branch_to_cloud",
    # No broadcast target — branch_to_cloud entries have a single
    # destination (cloud); broadcast_policy only scopes cloud_to_branch /
    # bidirectional distribution (REQ-CAT-004: "—" for this ER signal).
    broadcast_policy=None,
    apply_strategy="record_event",
    depends_on=("sucursal", "ingreso", "salidas"),
    has_uuid_sucursal=True,
    seq_strategy="max_timestamp_evento",
)

_FACTURA_ELECTRONICA = SyncCatalogEntry(
    name="factura_electronica",
    model_cls=FacturaElectronica,
    audit_class="L_E",
    sync_strategy="append",
    # D1-rev — emitted EN sucursal con SU resolución; the branch assigns
    # consecutivo locally. Single catalog entry (D6-rev): removed from
    # LocalOnlyCatalog, no sync_back_event flag.
    direction="branch_to_cloud",
    # No broadcast target — branch_to_cloud entries have a single
    # destination (cloud); broadcast_policy only scopes cloud_to_branch /
    # bidirectional distribution (REQ-CAT-004: "—" for this ER signal).
    broadcast_policy=None,
    apply_strategy="record_event",
    depends_on=("sucursal", "facturas", "clientes", "resolucion_facturacion"),
    has_uuid_sucursal=True,
    seq_strategy="max_timestamp_evento",
)

SYNC_ENTRIES_LE: tuple[SyncCatalogEntry, ...] = (
    _INGRESO,
    _FACTURAS,
    _FACTURA_ELECTRONICA,
)

assert len(SYNC_ENTRIES_LE) == 3, f"expected 3 [L-E] entries, got {len(SYNC_ENTRIES_LE)}"

__all__ = ["SYNC_ENTRIES_LE"]
