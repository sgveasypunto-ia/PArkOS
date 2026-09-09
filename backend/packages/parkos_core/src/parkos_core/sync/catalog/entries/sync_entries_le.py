"""catalog/entries/sync_entries_le.py — 3 [L-E] catalog entries (T-PR2-007).

``factura_electronica`` is a **single** catalog entry (D1-rev, D6-rev) — no
``sync_back_event`` field, not present in ``LocalOnlyCatalog``. Emitted at
the branch with the branch's own ``resolucion_facturacion``; the cloud
validates and forwards to the DIAN provider, recording the exchange in
``envio_dian`` (``sync_entries_lw.py``).

**Bug found and fixed in PR7 (T-PR7-002).** All three entries previously
declared ``seq_strategy="max_timestamp_evento"``, but none of the three
``[L-E]`` models (``Ingreso``, ``Facturas``, ``FacturaElectronica``) carries a
``timestamp_evento`` column — only ``Login`` (``models/L_S/login.py``) does.
``motor/read_local_seq.py::ReadLocalSeq`` dispatches ``max_timestamp_evento``
to ``SELECT MAX(timestamp_evento) FROM {table} WHERE uuid = :row_uuid``
(design.md §2 Issue #4), which would raise ``AttributeError`` for these three
specs. Corrected to ``max_created_at`` — every table carries ``created_at``
unconditionally (``AuditMixin``, AGENTS.md §1), and for insert-only ``[L-E]``
rows ``created_at`` IS the event's own timestamp, so the fix changes no
observable ordering semantics.
"""
from __future__ import annotations

from ....dian.backoff import DIAN_BACKOFF_SCHEDULE, DIAN_MAX_RETRIES
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
    seq_strategy="max_created_at",
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
    seq_strategy="max_created_at",
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
    seq_strategy="max_created_at",
    # T-PR9-005, design.md §2 Issue #9 — DIAN critical path: a consumed,
    # sequential, no-gap consecutivo is already at stake the moment this
    # row is emitted. Imported from dian/backoff.py, never re-declared.
    backoff_schedule=DIAN_BACKOFF_SCHEDULE,
    max_retries=DIAN_MAX_RETRIES,
    on_exhaustion="fe_provider_error",
)

SYNC_ENTRIES_LE: tuple[SyncCatalogEntry, ...] = (
    _INGRESO,
    _FACTURAS,
    _FACTURA_ELECTRONICA,
)

assert len(SYNC_ENTRIES_LE) == 3, f"expected 3 [L-E] entries, got {len(SYNC_ENTRIES_LE)}"

__all__ = ["SYNC_ENTRIES_LE"]
