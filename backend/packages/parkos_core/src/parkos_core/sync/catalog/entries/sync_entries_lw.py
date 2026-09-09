"""catalog/entries/sync_entries_lw.py — 6 [L-W] catalog entries (T-PR2-008..009).

``envio_dian`` is **flipped** to ``cloud_to_branch`` (D1-rev, D5-rev) — it is
the ordinary return channel carrying ``cufe``/``estado`` back to the branch,
replacing the withdrawn ``sync_back_events`` table entirely.
``validacion_evento`` is the **sole** ``never_propagated`` entry in the whole
catalog (D8-rev, REQ-CAT-016) — CLOUD-ONLY admin review tray.

None of the four branch-authored entries declares an ``origen`` column
(D1-rev — it existed only to distinguish an auto-reprint triggered by the
withdrawn sync-back arrival).
"""
from __future__ import annotations

from ....models.L_W.alerta import Alerta
from ....models.L_W.anulaciones import Anulaciones
from ....models.L_W.envio_dian import EnvioDian
from ....models.L_W.reclamos import Reclamos
from ....models.L_W.reimpresion_ticket import ReimpresionTicket
from ....models.L_W.validacion_evento import ValidacionEvento
from ..schema import SyncCatalogEntry

# ---------------------------------------------------------------------------
# T-PR2-008 — group 1: 4 branch-side workflow entries
# ---------------------------------------------------------------------------

_REIMPRESION_TICKET = SyncCatalogEntry(
    name="reimpresion_ticket",
    model_cls=ReimpresionTicket,
    audit_class="L_W",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_transition",
    depends_on=("sucursal", "ingreso", "usuarios", "costos_servicios", "facturas"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    self_chain=True,
    parent_fk_column="uuid_reimpresion_padre",
)

_ANULACIONES = SyncCatalogEntry(
    name="anulaciones",
    model_cls=Anulaciones,
    audit_class="L_W",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_transition",
    # T-PR3-001 fix (R22 guard): "salidas" REMOVED from depends_on.
    # ER modelo_datos_er.mmd:629 — uuid_salida FK "salida anulada (solo
    # cuando tipo_anulable = salida; NULL en anulación de ingreso)" is a
    # nullable FK (it is NULL for every anulación of tipo_anulable='ingreso').
    # ADR-003 Part 1 / D18: depends_on holds ONLY mandatory (NOT NULL) FKs —
    # a nullable FK here would wait forever for a "salida" that legitimately
    # never exists (the exact R22 hazard, applied to this table instead of
    # ingreso/subscripciones_cliente). uuid_ingreso stays: its own ER comment
    # states it is "siempre presente" (always present) regardless of
    # tipo_anulable — a real mandatory FK.
    depends_on=("sucursal", "ingreso", "usuarios"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    self_chain=True,
    parent_fk_column="uuid_anulacion_padre",
)

_RECLAMOS = SyncCatalogEntry(
    name="reclamos",
    model_cls=Reclamos,
    audit_class="L_W",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_transition",
    # T-PR3-001 fix: depends_on reduced to ("sucursal",) only.
    # ER modelo_datos_er.mmd:651 — the polymorphic target is carried by a
    # SINGLE generic column, `uuid_reclamable`, explicitly annotated "sin FK
    # física" (no physical FK) — `tipo_reclamable` is a string discriminator,
    # not a real per-table foreign key. ingreso/salidas/facturas/
    # subscripciones_cliente were previously listed here (proposal.md §6.4's
    # pre-ER-alignment table), but none of them is backed by an actual
    # mandatory NOT NULL FK column pointing at that specific table — the
    # ADR-003 depends_on contract ("every table it holds a mandatory FK to")
    # does not apply to a polymorphic, constraint-free reference. Only
    # `uuid_sucursal` is a real FK-tagged, non-nullable column on this table.
    depends_on=("sucursal",),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    self_chain=True,
    parent_fk_column="uuid_reclamo_padre",
)

_ALERTA = SyncCatalogEntry(
    name="alerta",
    model_cls=Alerta,
    audit_class="L_W",
    sync_strategy="append",
    direction="branch_to_cloud",
    broadcast_policy=None,  # single destination (cloud); no broadcast scope
    apply_strategy="append_transition",
    depends_on=("sucursal", "usuarios"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    self_chain=True,
    parent_fk_column="uuid_alerta_padre",
)

# ---------------------------------------------------------------------------
# T-PR2-009 — group 2: envio_dian (flipped) + validacion_evento (never_propagated)
# ---------------------------------------------------------------------------

_ENVIO_DIAN = SyncCatalogEntry(
    name="envio_dian",
    model_cls=EnvioDian,
    audit_class="L_W",
    sync_strategy="append",
    # Flipped from branch_to_cloud (D1-rev, D5-rev) — ER: "CLOUD-ONLY: único
    # punto de salida hacia el proveedor de factura electrónica DIAN".
    direction="cloud_to_branch",
    broadcast_policy="single_branch",
    apply_strategy="append_transition",
    originating_role="cloud",
    role_required="both",  # branch legitimately holds and reads these rows
    depends_on=("sucursal", "factura_electronica", "resolucion_facturacion"),
    has_uuid_sucursal=True,
    seq_strategy="seq_via_datos",
    self_chain=True,
    parent_fk_column="uuid_envio_padre",
)

_VALIDACION_EVENTO = SyncCatalogEntry(
    name="validacion_evento",
    model_cls=ValidacionEvento,
    audit_class="L_W",
    # Sole never_propagated entry in the whole catalog (D8-rev, REQ-CAT-016).
    sync_strategy="never_propagated",
    direction=None,
    broadcast_policy=None,
    apply_strategy=None,
    role_required="cloud",
    originating_role="cloud",
    # T-PR3-001 fix: depends_on=("sucursal",) — previously left empty.
    # ER modelo_datos_er.mmd:920 — uuid_sucursal FK "sucursal que originó el
    # evento" carries no nullability marker, i.e. a real mandatory FK
    # (uuid_usuario at :921 IS nullable — "NULL en recepción automática" —
    # and correctly stays excluded). This entry is never_propagated (never
    # enters a sync batch), so the fix is inert at runtime; it only makes
    # the declared value match the ER, per T-PR3-001's uniform, CI-derived
    # rule (ADR-003: "depends_on is CI-derived, not hand-maintained").
    depends_on=("sucursal",),
    has_uuid_sucursal=True,
    seq_strategy="none",
    self_chain=True,
    parent_fk_column="uuid_validacion_padre",
    justification=(
        "ER CLOUD-ONLY admin review tray, no stated branch-side need — 'bandeja del "
        "admin para validar cada evento recibido de sucursal'. Structurally present in "
        "the branch schema for parity, never populated there."
    ),
)

SYNC_ENTRIES_LW: tuple[SyncCatalogEntry, ...] = (
    _REIMPRESION_TICKET,
    _ANULACIONES,
    _RECLAMOS,
    _ALERTA,
    _ENVIO_DIAN,
    _VALIDACION_EVENTO,
)

assert len(SYNC_ENTRIES_LW) == 6, f"expected 6 [L-W] entries, got {len(SYNC_ENTRIES_LW)}"

__all__ = ["SYNC_ENTRIES_LW"]
