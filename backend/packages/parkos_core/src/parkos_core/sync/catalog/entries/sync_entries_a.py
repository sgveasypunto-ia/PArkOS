"""catalog/entries/sync_entries_a.py — 9 [A] catalog entries (T-PR2-011..013).

``factura_pagos.uuid_pago_revertido`` is a self-FK, excluded from the
topological sort (``self_chain=True``, D18). ``factura_impuestos`` /
``factura_otros_cobros`` declare ``snapshot_columns`` (D20) — persisted
verbatim, never recomputed from the live ``impuestos`` / ``otros_cobros``
catalog on apply. ``log_transaccional`` / ``revocacion_factura`` are the
**only** two entries in the whole catalog with ``hash_chain=True`` +
``verify_chain=True`` (REQ-CAT-009) — ``revocacion_factura`` resolving to
exactly one catalog entry (REQ-CAT-005) is what removes the interleaved
double-chain hazard from the superseded dual-catalog design.
"""
from __future__ import annotations

from ....dian.backoff import DIAN_BACKOFF_SCHEDULE, DIAN_MAX_RETRIES
from ....models.A.arqueo import Arqueo
from ....models.A.caja import Caja
from ....models.A.factura_detalle import FacturaDetalle
from ....models.A.factura_impuestos import FacturaImpuestos
from ....models.A.factura_otros_cobros import FacturaOtrosCobros
from ....models.A.factura_pagos import FacturaPagos
from ....models.A.log_transaccional import LogTransaccional
from ....models.A.revocacion_factura import RevocacionFactura
from ....models.A.salidas import Salidas
from ...hooks.impls.bi_temporal_compensation import bi_temporal_compensation
from ...hooks.impls.log_transaccional_chain import log_transaccional_chain
from ...hooks.impls.revocacion_factura_chain import revocacion_factura_chain
from ..schema import SyncCatalogEntry

# ---------------------------------------------------------------------------
# T-PR2-011 — group 1: salidas / factura_detalle / caja / arqueo / factura_pagos
# ---------------------------------------------------------------------------

_SALIDAS = SyncCatalogEntry(
    name="salidas",
    model_cls=Salidas,
    audit_class="A",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal", "ingreso"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=False,
)

_FACTURA_DETALLE = SyncCatalogEntry(
    name="factura_detalle",
    model_cls=FacturaDetalle,
    audit_class="A",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal", "facturas"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=False,
)

_CAJA = SyncCatalogEntry(
    name="caja",
    model_cls=Caja,
    audit_class="A",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal",),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=False,
)

_ARQUEO = SyncCatalogEntry(
    name="arqueo",
    model_cls=Arqueo,
    audit_class="A",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal", "sesion", "tipo_arqueo"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=False,
)

_FACTURA_PAGOS = SyncCatalogEntry(
    name="factura_pagos",
    model_cls=FacturaPagos,
    audit_class="A",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal", "facturas", "sesion"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=False,
    self_chain=True,
    parent_fk_column="uuid_pago_revertido",
    # T-PR5-015 (REQ-HOOK-007) — a 'reverso' row emits a compensating
    # log_transaccional row (own hash chain extended) in the same TX.
    hook_post_insert=bi_temporal_compensation,
)

# ---------------------------------------------------------------------------
# T-PR2-012 — group 2: factura_impuestos / factura_otros_cobros (D20 snapshot)
# ---------------------------------------------------------------------------

_FACTURA_IMPUESTOS = SyncCatalogEntry(
    name="factura_impuestos",
    model_cls=FacturaImpuestos,
    audit_class="A",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal", "facturas", "impuestos"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=False,
    # D20 — never recomputed from the live impuestos catalog on apply.
    snapshot_columns=frozenset({"base_calculo", "porcentaje_aplicado", "valor"}),
)

_FACTURA_OTROS_COBROS = SyncCatalogEntry(
    name="factura_otros_cobros",
    model_cls=FacturaOtrosCobros,
    audit_class="A",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal", "facturas", "otros_cobros"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=False,
    # D20 — same snapshot rule as factura_impuestos.
    snapshot_columns=frozenset({"base_calculo", "valor_aplicado", "valor"}),
)

# ---------------------------------------------------------------------------
# T-PR2-013 — group 3: log_transaccional / revocacion_factura (hash chain)
# ---------------------------------------------------------------------------

_LOG_TRANSACCIONAL = SyncCatalogEntry(
    name="log_transaccional",
    model_cls=LogTransaccional,
    audit_class="A",
    sync_strategy="append",
    direction="bidirectional",
    # No broadcast scoping either — cloud preserves the branch chain
    # verbatim and only extends it with cloud-originated rows (proposal
    # §6.1); this is not a routed/scoped distribution like [V] entries.
    broadcast_policy=None,
    apply_strategy="append_event",
    depends_on=("sucursal", "usuarios"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=True,
    verify_chain=True,
    # T-PR6-002 — REQ-HOOK-008. See log_transaccional_chain.py's module
    # docstring for the double-extension caveat vs. apply_strategy=
    # "append_event"'s own step-3 chain_hash dispatch (not currently
    # reachable: nothing calls apply_row(_LOG_TRANSACCIONAL, ...) directly).
    hook_chain_extend=log_transaccional_chain,
)

_REVOCACION_FACTURA = SyncCatalogEntry(
    name="revocacion_factura",
    model_cls=RevocacionFactura,
    audit_class="A",
    sync_strategy="append",
    # Single catalog entry (D6-rev) — not present in LocalOnlyCatalog, no
    # sync_back_event field. This is what eliminates the guaranteed false
    # HashChainBreak from two interleaved chains on the same
    # (tabla, uuid_sucursal).
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_event",
    depends_on=("sucursal", "factura_electronica"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    hash_chain=True,
    verify_chain=True,
    # T-PR6-004 — REQ-HOOK-009. Replaces the manual dispatcher.py call
    # (T-PR6-005) — see revocacion_factura_chain.py's module docstring.
    hook_chain_extend=revocacion_factura_chain,
    # T-PR9-010 — reuses the EXACT SAME DIAN curve as factura_electronica
    # (imported, not a separate copy): same DIAN evidentiary chain
    # (hash_chain + verify_chain), same regulatory deadline, and its
    # cloud-side effect is also a provider submission (design.md §2
    # Issue #9).
    backoff_schedule=DIAN_BACKOFF_SCHEDULE,
    max_retries=DIAN_MAX_RETRIES,
    on_exhaustion="fe_provider_error",
)

SYNC_ENTRIES_A: tuple[SyncCatalogEntry, ...] = (
    _SALIDAS,
    _FACTURA_DETALLE,
    _CAJA,
    _ARQUEO,
    _FACTURA_PAGOS,
    _FACTURA_IMPUESTOS,
    _FACTURA_OTROS_COBROS,
    _LOG_TRANSACCIONAL,
    _REVOCACION_FACTURA,
)

assert len(SYNC_ENTRIES_A) == 9, f"expected 9 [A] entries, got {len(SYNC_ENTRIES_A)}"

__all__ = ["SYNC_ENTRIES_A"]
