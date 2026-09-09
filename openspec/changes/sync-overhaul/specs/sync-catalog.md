# Spec: `sync-catalog`

## Purpose

Define the declarative `SyncCatalog` (46 entries), `LocalOnlyCatalog` (3
entries), and the explicit out-of-catalog set (5 entries) that together
classify every one of the 54 physical prod tables exactly once. Replace the
4 hardcoded `frozenset` lists in `sync/conflict_resolver.py` and the 30
hardcoded `fn_enqueue_sync` triggers in `migrations/0001_initial_schema.py`
with a typed, table-aware, CI-verifiable surface whose direction and scope
are **derived from `modelo_datos_er.mmd`**, not from the trigger inventory
already installed in the database.

Encodes decisions **D5-rev** (direction/`broadcast_policy` derived from the
ER, not from installed triggers), **D6-rev** (exactly one catalog per
table — no dual `factura_electronica`/`revocacion_factura` entries),
**D8-rev** (`never_propagated` eliminated except for `validacion_evento`),
**D14-rev** (direction is ratified in this change, no per-table deferral),
**D17** (natural-key identity reconciliation fields for `clientes` /
`clientes_b2b` / `vehiculos`), **D18** (`depends_on` and the generalized
`RETRY(parent_missing)` mechanism, generalizing D7), **D19**
(`all_branches_with_override` for the two default+override configuration
tables), **D20** (snapshot columns never recomputed on apply), and **D21**
(infrastructure tables never enqueued).

> **Amendment note.** D1 (DIAN `sync_back_event`), D6 (dual catalog), D8
> (18 `never_propagated` tables), and D14 (deferred direction ratification)
> were superseded by this proposal's corrective amendment. Where a
> requirement below replaces one of those decisions, the superseded text is
> kept visible in a blockquote immediately above the replacement, per the
> proposal's amendment rule (§0).

## Requirements

### REQ-CAT-001: `SyncCatalogEntry` dataclass schema
**Given** the project declares a `SyncCatalogEntry` as a frozen dataclass
**When** a spec is constructed
**Then** the entry MUST carry these groups of attributes (proposal §5):
- identity — `name: str`, `model_cls: type[DeclarativeBase]`,
  `audit_class: Literal["V","L_E","L_W","L_S","A"]`
- policy — `sync_strategy: Literal["append","manual","grace_window",
  "never_propagated","local_only","is_sync_outbox"]`,
  `direction: Literal["cloud_to_branch","branch_to_cloud","bidirectional"] |
  None` (`None` iff `sync_strategy="never_propagated"`),
  `broadcast_policy: Literal["single_branch","all_branches",
  "all_branches_with_override","subscription"] | None = "single_branch"`
- apply — `apply_strategy: Literal["close_and_insert","record_event",
  "append_event","append_transition","session_cycle"] | None`
- dependency ordering (D18) — `depends_on: tuple[str, ...] = ()`,
  `parent_fk_column: str | None = None`, `self_chain: bool = False`
- sequence — `has_uuid_sucursal: bool`,
  `seq_strategy: Literal["seq_via_datos","max_timestamp_evento",
  "max_created_at","none"] | None`
- identity reconciliation (D17) — `natural_key: tuple[str, ...] = ()`,
  `natural_key_normalizer: Callable[[dict], dict] | None = None`
- hash chain — `hash_chain: bool = False`, `verify_chain: bool = False`
- role / scope — `role_required: Literal["cloud","branch","both"] =
  "both"`, `originating_role: Literal["cloud","branch","both"] = "branch"`
- snapshot immutability (D20) — `snapshot_columns: frozenset[str] | None
  = None`
- hooks — `hook_pre_insert`, `hook_post_insert`, `hook_chain_extend`,
  `hook_validate_parent: HookFn | None = None` (four slots)
- operational — `is_sync_outbox: bool = False`,
  `state_mutable_columns: frozenset[str] | None = None`
- metadata — `justification: str | None = None` (required iff
  `never_propagated`), `priority: int = 1`, `chain_priority: int = 0`

**And** the dataclass MUST be `frozen=True` so catalog entries are
immutable at runtime
**And** `model_cls` MUST be a `type[DeclarativeBase]` subclass so AST
checks can resolve `name` ↔ `__tablename__` ↔ model
**And** the dataclass MUST NOT carry `cloud_only`, `sync_back_event`, or
`direction_proposed` — these three fields are removed by this amendment
(`cloud_only` is replaced by the `role_required` / `originating_role`
pair; `sync_back_event` is removed with D1-rev; `direction_proposed` is
removed with D14-rev)
**And** `broadcast_policy` MUST NEVER receive a `direction` enum value
(e.g. `"bidirectional"`); CI (REQ-OPS-003) MUST assert the two enums are
disjoint sets of string literals.

### REQ-CAT-002: `SyncCatalog` declares 46 entries
**Given** the SyncCatalog file `parkos_core/sync/catalog.py::SYNC_CATALOG`
**When** `len(SYNC_CATALOG)` is read
**Then** the count MUST equal 46
**And** the entries MUST span: 26 `[V]` (REQ-CAT-004, REQ-CAT-016), 3
`[L-E]`, 6 `[L-W]`, 2 `[L-S]`, and 9 `[A]` (26+3+6+2+9 = 46)
**And** every entry MUST have a non-null `name` matching its
`model_cls.__tablename__`
**And** this count MUST be recomputed from the amended proposal's §6
enumeration on every future table addition — CI (REQ-OPS-003) asserts the
literal value, and no artifact may hardcode a different number.

### REQ-CAT-003: `LocalOnlyCatalog` declares 3 entries
**Given** the LocalOnlyCatalog file
`parkos_core/sync/local_only_catalog.py::LOCAL_ONLY_CATALOG`
**When** `len(LOCAL_ONLY_CATALOG)` is read
**Then** the count MUST equal 3
**And** the entries MUST be exactly: `idempotency_keys`, `pairing_tokens`,
`revoked_sync_jwts` — all with `sync_strategy="local_only"`,
`role_required="both"`
**And** none of these three MUST have an ER counterpart in
`modelo_datos_er.mmd` (they are non-ER operational tables)
**And** the motor MUST NEVER enqueue any of these three into `sync_queue`.

> **Superseded — see D6-rev.** The prior pass declared `LocalOnlyCatalog`
> with 5 entries, adding branch-side views of `factura_electronica`
> (`role_required="branch"`) and `revocacion_factura`
> (`role_required="branch"`) alongside a cloud-side `SyncCatalog` entry for
> the same two tables. This produced two independent hash chains for the
> same `(tabla, uuid_sucursal)`, which `verify_chain`'s
> `(timestamp_evento, uuid)` walk would see interleaved — a guaranteed
> false `HashChainBreak`. D6-rev removes both tables from
> `LocalOnlyCatalog` entirely; see REQ-CAT-005.

### REQ-CAT-004: Direction and `broadcast_policy` derived from the ER (D5-rev)
**Given** an ER entity's class tag and `uuid_sucursal` presence
**When** the SyncCatalog assigns `direction` and `broadcast_policy` to its
entry
**Then** the assignment MUST follow this derivation table, and
`check_catalog_drift.py` MUST re-derive the same values from
`modelo_datos_er.mmd` and fail the build on any mismatch (R1):

| ER signal | `direction` | `broadcast_policy` |
|---|---|---|
| `[V]` without `uuid_sucursal` | `cloud_to_branch` | `all_branches` |
| `[V]` with `uuid_sucursal` | `cloud_to_branch` | `single_branch` |
| `[V]` with nullable `uuid_sucursal` (global default + override) | `cloud_to_branch` | `all_branches_with_override` (D19, REQ-CAT-019) |
| `[V]` identity master written on both sides | `bidirectional` | per REQ-CAT-018, reconciled by D17 |
| `[V]` scoped to the selling/owning branch, written on both sides | `bidirectional` | `subscription` (REQ-CAT-017) |
| `[L-E]`, `[L-S]`, `[A]` | `branch_to_cloud` | — |
| `[L-W]` | `branch_to_cloud` | — |
| `[L-W]` marked CLOUD-ONLY in the ER | `cloud_to_branch` or excluded | `single_branch` |
| `[A]` infrastructure (`sync_*`, `alert_types`) | out of catalog | — |

**And** all 26 `[V]` entries MUST carry a concrete, ratified `direction`
value — there is no `direction_proposed` placeholder (D14-rev, REQ-CAT-007)
**And** the following 18 `[V]` tables, previously misclassified as
`never_propagated`, MUST now carry `direction="cloud_to_branch"`,
`broadcast_policy="all_branches"` (unless noted otherwise below):
`usuarios`, `permisos`, `permisos_usuario`, `tipo_persona`,
`tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`,
`tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios`, `empresa`
(`broadcast_policy="all_branches"`, tenant-filtered per the branch's own
`sucursal.uuid_empresa`), `sucursal` (`broadcast_policy="single_branch"`),
`configuracion_tolerancias`, `configuracion_seguridad`
(`broadcast_policy="all_branches_with_override"`, REQ-CAT-019), `clientes`
and `vehiculos` (`direction="bidirectional"`, `broadcast_policy=
"all_branches"`, reconciled per D17, REQ-CAT-018)
**And** `permisos_usuario`, `clientes_b2b`, and `subscripcion_vehiculos`
MUST inherit their direction/scope from their respective parent tables per
the same table above
**And** `envio_dian` MUST carry `direction="cloud_to_branch"`,
`broadcast_policy="single_branch"` — flipped from `branch_to_cloud`
(REQ-CAT-008)
**And** `validacion_evento` is the sole entry keeping
`sync_strategy="never_propagated"` (REQ-CAT-016).

**Given** a table with no direction-changing signal in this table
**When** the catalog is loaded
**Then** the following 15 tables MUST keep their unchanged, already-correct
direction/scope: `resolucion_facturacion` (`cloud_to_branch`,
`single_branch`), `usuarios_sucursal`, `documentos`, `tarifas_sucursal`,
`cantidad_vehiculos_sucursal` (all `cloud_to_branch`, `single_branch`);
`ingreso`, `facturas`, `factura_electronica` (all `branch_to_cloud`, see
REQ-CAT-005 for the last); `reimpresion_ticket`, `anulaciones`,
`reclamos`, `alerta` (all `branch_to_cloud`); `login`, `sesion` (both
`branch_to_cloud`); `salidas`, `factura_detalle`, `factura_impuestos`,
`factura_otros_cobros`, `factura_pagos`, `caja`, `arqueo`,
`log_transaccional` (`bidirectional`), `revocacion_factura` (see
REQ-CAT-005).

> **Superseded — see D5-rev, D8-rev.** The prior REQ-CAT-004 declared that
> 18 `[V]` tables — `permisos`, `permisos_usuario`, `empresa`, `usuarios`,
> `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`,
> `tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`,
> `costos_servicios`, `sucursal`, `clientes`, `clientes_b2b`, `vehiculos`,
> `subscripcion_vehiculos` — carried `sync_strategy="never_propagated"`
> with a required per-table `justification` string, on the theory of an
> unspecified "boot snapshot" mechanism. The ER states the opposite for
> several of these (`usuarios`: "se replica a sucursales para login
> offline"; `permisos`: "replica cloud a sucursales"), and the "boot
> snapshot" mechanism exists in no requirement, task, or module. This is
> the root cause the amendment corrects: a branch could not classify,
> price, authenticate, authorize, or invoice offline because its
> catalog was never actually populated.

### REQ-CAT-005: Exactly one catalog per table (D6-rev)
**Given** `factura_electronica` and `revocacion_factura`
**When** the SyncCatalog and LocalOnlyCatalog are both loaded
**Then** both tables MUST appear in `SYNC_CATALOG` only, with
`sync_strategy="append"`
**And** `factura_electronica` MUST have `apply_strategy="record_event"`,
`direction="branch_to_cloud"` — it is emitted **at the branch** with the
branch's own `resolucion_facturacion` (D1-rev)
**And** `revocacion_factura` MUST have `apply_strategy="append_event"`,
`direction="branch_to_cloud"`, `hash_chain=True`, `verify_chain=True`
**And** neither table MUST appear in `LOCAL_ONLY_CATALOG`
**And** every ORM class in `parkos_core/models/{V,L_E,L_W,L_S,A}/` MUST
resolve to exactly one of `SYNC_CATALOG`, `LOCAL_ONLY_CATALOG`, or the
out-of-catalog set (REQ-CAT-006) — `check_catalog_drift.py` rule 2 (R1)
MUST hold with **no exceptions**.

> **Superseded — see D1-rev, D6-rev.** The prior REQ-CAT-005 required BOTH
> a `SYNC_CATALOG` entry (`direction="branch_to_cloud"`, `cloud_only=False`
> — "cloud-side catalog: receives branch push, applies via `record_event`,
> extends the chain, decides `numero_oficial`") AND a `LOCAL_ONLY_CATALOG`
> entry (`role_required="branch"` — "branch-side catalog: branches write
> locally with `numero_temporal`, never push upstream — cloud pulls") for
> the same two tables. This was the second-order effect of the old,
> superseded D1 (central `numero_oficial` allocator): it existed to
> express split ownership between a branch-local preliminary number and a
> cloud-assigned official one. D1-rev removes the split entirely — the
> branch assigns `consecutivo` once, inside its own resolution's
> authorized range — so there is nothing left to express with a second
> catalog entry, and the dual entry was actively harmful (two hash chains
> for one `(tabla, uuid_sucursal)`, guaranteed false `HashChainBreak`).

### REQ-CAT-006: Out-of-catalog set — 5 entries, explicitly excluded
**Given** the tables that are sync infrastructure or deploy-seeded
registries rather than ER business entities requiring replication
**When** the SyncCatalog and LocalOnlyCatalog are loaded
**Then** none of `sync_queue`, `sync_log`, `sync_conflict`,
`sync_queue_lw_buffer`, or `alert_types` MUST appear in either catalog
**And** `check_catalog_drift.py`'s exemption list MUST carry **exactly**
these five names (REQ-OPS-003)
**And** `openspec/scripts/check_sync_queue_carveout.py` (R-D3, REQ-OPS-004)
MUST verify that no code path outside `repo/sync_queue.py` issues an
`UPDATE` or `DELETE` against `sync_queue`
**And** the cloud worker MUST **skip** (not `mark_failed(unknown_table)`)
any row whose table is one of these five, per D21 (REQ-OPS-014).

**Given** the discriminator for why `alert_types` is out of catalog while
every other `[V]` table now replicates
**When** a future table is classified
**Then** the rule MUST be: a table an operator edits at runtime through
the admin UI (e.g. `tipos_vehiculo`, `impuestos`, `tarifas_sucursal`) MUST
replicate, because a new value must reach the branch without a deploy; a
table whose members are referenced **by identifier in Python source**
(e.g. `alert_types.tipo_alerta` values like `orphan_workflow_chain`,
`hash_chain_anomaly`, `fe_provider_error`) is excluded and is instead
seeded idempotently by the same migration/seed script on both cloud and
branch (REQ-CAT-021), because adding a member is a code change that ships
with a deploy anyway.

> **Amended — was 3 entries.** The prior REQ-CAT-006 excluded only
> `sync_queue`, `sync_log`, and `sync_conflict`. This amendment adds two
> new `[A]` operational tables introduced by D18 (`sync_queue_lw_buffer`,
> the generalized dependency buffer) and D6-rev (`alert_types`, the
> deploy-seeded alert registry) — see `cutover-migration.md` REQ-CUT-010
> for the buffer's schema and `operations.md` REQ-OPS-014 for the alert
> registry's classification rule.

### REQ-CAT-007: `direction` is ratified, not proposed (D14-rev)
**Given** every SyncCatalog entry
**When** `entry.direction` is read
**Then** the value MUST be one of `cloud_to_branch`, `branch_to_cloud`,
`bidirectional`
**And** entries where `sync_strategy="never_propagated"` (only
`validacion_evento`, REQ-CAT-016) MAY omit `direction` (`None`)
**And** the dataclass MUST NOT carry a `direction_proposed` field — every
value is final for this change; there is no follow-up per-table
ratification PR.

> **Superseded — see D14-rev.** The prior REQ-CAT-007 required
> `direction_proposed=True` on all 26 `[V]` entries plus an inline code
> comment recording the "real" proposed value (e.g.
> `direction="bidirectional"  # direction_proposed: cloud_to_branch —
> ratify in PR-D14-*"`), deferring ratification to future PRs. D14-rev
> ratifies every value in this change because direction is now *derived*
> from the ER by a stated, CI-asserted rule (D5-rev) rather than guessed
> from trigger presence — a per-table human ratification gate would add a
> review queue without adding information.

### REQ-CAT-008: `envio_dian` is the sole DIAN return channel (D1-rev)
**Given** the DIAN provider exchange
**When** the SyncCatalog is loaded
**Then** `envio_dian` MUST have `direction="cloud_to_branch"`,
`broadcast_policy="single_branch"`, `apply_strategy="append_transition"`,
`originating_role="cloud"`, `role_required="both"` — the branch
legitimately holds and reads these rows
**And** `envio_dian` MUST carry `cufe` and `estado` as the fields that
reach the branch through the ordinary `cloud_to_branch` catalog mechanism
**And** no entry MUST carry a `sync_back_event` field — the dataclass does
not declare one (REQ-CAT-001)
**And** `factura_electronica`, `revocacion_factura`, and `envio_dian` MUST
NOT bind any `SyncBackEventEmitter`-style `hook_post_insert` — that hook
is removed entirely (`hooks.md`)
**And** `reimpresion_ticket` MUST NOT carry an `origen` column — it
existed only to distinguish an auto-reprint triggered by the withdrawn
sync-back arrival (`hooks.md` REQ-HOOK-011).

> **Superseded — see D1-rev.** The prior REQ-CAT-008 required
> `factura_electronica`, `revocacion_factura`, and `envio_dian` to carry
> `sync_back_event=True`, bind a `SyncBackEventEmitter` hook to
> `hook_post_insert`, and required `reimpresion_ticket` to carry an
> `origen: Literal["manual","auto"]` field. D1-rev removes
> `prod.sync_back_events`, the `SyncBackEventEmitter` hook, the
> `sync_back_event` flag, and the `origen` column in full — the branch
> numbers `factura_electronica` locally within its own resolution's
> range, and `envio_dian` (already modeled in the ER as CLOUD-ONLY) is the
> ordinary channel that carries `cufe`/`estado` back.

### REQ-CAT-009: `hash_chain=True` + `verify_chain=True` on chain-bearing tables only
**Given** the SyncCatalog is loaded
**When** every entry's `hash_chain` field is read
**Then** ONLY `log_transaccional` and `revocacion_factura` MUST have
`hash_chain=True`
**And** ONLY those two MUST also have `verify_chain=True` so the cloud-side
`job_sync_cloud._hash_chain_verifier_loop` iterates them
**And** all other entries MUST have `hash_chain=False` and
`verify_chain=False`
**And**, because `revocacion_factura` now resolves to exactly one catalog
entry (REQ-CAT-005), there is exactly one hash chain per
`(tabla, uuid_sucursal)` for both chain-bearing tables — the interleaved
double-chain hazard from the superseded dual-catalog design cannot recur.

### REQ-CAT-010: `role_required` / `originating_role` replace `cloud_only` (D5-rev, R6)
**Given** the SyncCatalog is loaded
**When** `validacion_evento` and `envio_dian` are inspected
**Then** ONLY `validacion_evento` MUST have `role_required="cloud"` — the
ER states no branch-side need ("bandeja del admin para validar cada
evento recibido de sucursal") and it stays structurally present in the
branch schema but is never populated there
**And** `envio_dian` MUST have `role_required="both"`,
`originating_role="cloud"` — the branch legitimately holds and reads
these rows, so it MUST NOT trigger the import guard
**And** the build-time guard `parkos_core/sync/role_guard.py::assert_role`
(REQ-OPS-005) MUST raise `ImportError` only when a branch process imports
`validacion_evento`'s model class, never for `envio_dian`.

> **Superseded — see D5-rev, R6.** The prior REQ-CAT-010 declared
> `cloud_only=True` and `role_required="cloud"` on BOTH `envio_dian` and
> `validacion_evento`, which would crash branch boot on `envio_dian` — a
> table the branch must legitimately read to display the DIAN
> acknowledgement. The `cloud_only: bool` field is removed from the
> dataclass entirely (REQ-CAT-001); the `role_required` /
> `originating_role` pair distinguishes "may not exist here"
> (`validacion_evento`, `role_required="cloud"`) from "is not authored
> here but is legitimately present" (`envio_dian`,
> `originating_role="cloud"` with `role_required="both"`).

### REQ-CAT-011: `role_required` declares deployment scope
**Given** every SyncCatalog and LocalOnlyCatalog entry
**When** `entry.role_required` is read
**Then** the value MUST be one of `cloud`, `branch`, or `both`
**And** `validacion_evento` MUST be the only entry with
`role_required="cloud"`
**And** all three `LocalOnlyCatalog` entries MUST have
`role_required="both"`
**And** no entry MUST have `role_required="branch"` — the branch-side
views of `factura_electronica`/`revocacion_factura` that previously used
this value no longer exist (REQ-CAT-005).

### REQ-CAT-012: `priority` is an intra-level FIFO tie-break only (D18, R12)
**Given** every SyncCatalog entry
**When** `entry.priority` is read
**Then** the value MUST be a positive integer
**And** `priority` MUST NEVER be used for cross-table ordering — the only
cross-table ordering mechanism is the topological sort over `depends_on`
(REQ-CAT-015)
**And** `priority` MUST be used exclusively as a FIFO tie-break *within*
one topological level of a single `apply_batch` call
**And** `check_catalog_drift.py` or an equivalent AST check MUST assert
`priority` is referenced nowhere in the dependency-ordering code path
**And** the legacy hardcoded values (`factura_electronica` /
`revocacion_factura = 10`; `ingreso` / `salidas` / `factura_pagos = 5`;
all others `= 1`) MAY be preserved as the tie-break value, but MUST NOT be
read as an ordering guarantee — those values previously put
`factura_pagos` ahead of `facturas`, a child ahead of its parent, which
`depends_on` now prevents structurally.

### REQ-CAT-013: `seq_strategy` per audit class
**Given** the SyncCatalog is loaded
**When** `entry.seq_strategy` is read
**Then** `[V]` tables with a trigger today MUST have
`seq_strategy="seq_via_datos"` so the motor reads `datos->>'seq'` from the
JSONB payload
**And** `[L-E]` tables MUST have `seq_strategy="max_timestamp_evento"`
**And** `[A]` tables MUST have `seq_strategy="seq_via_datos"`
**And** `validacion_evento` (the sole `never_propagated` entry,
REQ-CAT-016) MAY have `seq_strategy="none"`
**And** `LocalOnlyCatalog` entries MUST have `seq_strategy="none"`.

### REQ-CAT-014: `state_mutable_columns` declared on `sync_queue` carve-out
**Given** the operational outbox carve-out for `sync_queue`
**When** the entry is constructed outside any catalog (per REQ-CAT-006)
**Then** a separate constant
`parkos_core/repo/sync_queue.py::ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS` MUST
exist as `frozenset[str] = frozenset({"estado","intentos","next_retry_at","ultimo_error"})`
**And** the AST check (REQ-OPS-004) MUST reference this constant to
verify no other code mutates these columns.

### REQ-CAT-015: `depends_on` and the generalized `RETRY(parent_missing)` (D18, generalizes D7)
**Given** a `SyncCatalogEntry` for a table with a mandatory FK to another
`SyncCatalog` entry
**When** the catalog is loaded
**Then** the entry MUST declare `depends_on: tuple[str, ...]` naming every
such parent table, per this table (proposal §6.4):

| Entry | `depends_on` | Self-chain column (`parent_fk_column`, `self_chain=True`) |
|---|---|---|
| `permisos_usuario` | `usuarios`, `permisos` | — |
| `usuarios_sucursal` | `usuarios`, `sucursal` | — |
| `sucursal` | `empresa`, `tipo_sucursal` | — |
| `resolucion_facturacion` | `sucursal` | — |
| `documentos` | `sucursal` | — |
| `tarifas_sucursal` | `sucursal`, `tipos_vehiculo`, `tipo_tarifa` | — |
| `cantidad_vehiculos_sucursal` | `sucursal`, `tipos_vehiculo` | — |
| `configuracion_tolerancias` / `configuracion_seguridad` | — (nullable `uuid_sucursal`) | — |
| `clientes` | `tipo_persona` | — |
| `clientes_b2b` | `clientes` | — |
| `subscripciones_cliente` | `clientes`, `sucursal`, `tipo_subscripciones` | — |
| `vehiculos` | `tipos_vehiculo` | — |
| `subscripcion_vehiculos` | `subscripciones_cliente`, `vehiculos` | — |
| `login` | `usuarios`, `sucursal` | — |
| `ingreso` | `sucursal`, `tipos_vehiculo` | — |
| `salidas` | `sucursal`, `ingreso` | — |
| `facturas` | `sucursal`, `ingreso`, `salidas` | — |
| `factura_detalle` | `sucursal`, `facturas` | — |
| `factura_impuestos` | `sucursal`, `facturas`, `impuestos` | — |
| `factura_otros_cobros` | `sucursal`, `facturas`, `otros_cobros` | — |
| `factura_pagos` | `sucursal`, `facturas`, `sesion` | `uuid_pago_revertido` |
| `factura_electronica` | `sucursal`, `facturas`, `clientes`, `resolucion_facturacion` | — |
| `revocacion_factura` | `sucursal`, `factura_electronica` | — |
| `envio_dian` | `sucursal`, `factura_electronica`, `resolucion_facturacion` | `uuid_envio_padre` |
| `sesion` | `sucursal`, `usuarios` | — |
| `caja` | `sucursal` | — |
| `arqueo` | `sucursal`, `sesion`, `tipo_arqueo` | — |
| `alerta` | `sucursal`, `usuarios` | `uuid_alerta_padre` |
| `reimpresion_ticket` | `sucursal`, `ingreso`, `usuarios`, `costos_servicios`, `facturas` | `uuid_reimpresion_padre` |
| `anulaciones` | `sucursal`, `ingreso`, `salidas`, `usuarios` | `uuid_anulacion_padre` |
| `reclamos` | `sucursal`, `ingreso`, `salidas`, `facturas`, `subscripciones_cliente` | `uuid_reclamo_padre` |
| `log_transaccional` | `sucursal`, `usuarios` | — |
| `validacion_evento` | — (`never_propagated`) | `uuid_validacion_padre` |

Every other entry (the root `[V]` catalogs — `usuarios`, `permisos`,
`tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`,
`tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`,
`costos_servicios`, `empresa`) MUST declare `depends_on=()` — they are
roots of the dependency graph.

**And** `check_catalog_drift.py` MUST assert `depends_on` equals the set
of mandatory-FK parents `modelo_datos_er.mmd` declares for that entity —
a hand-edited value that drifts from the ER MUST fail the build
**And** the seven self-referential FKs (`reclamos.uuid_reclamo_padre`,
`anulaciones.uuid_anulacion_padre`, `alerta.uuid_alerta_padre`,
`reimpresion_ticket.uuid_reimpresion_padre`, `envio_dian.uuid_envio_padre`,
`validacion_evento.uuid_validacion_padre`,
`factura_pagos.uuid_pago_revertido`) MUST be marked `self_chain=True` with
`parent_fk_column` set to the exact column name, and MUST be **excluded**
from the topological sort — they are handled by the existing self-chain
logic instead
**And** the resulting `depends_on` graph, with self-chain edges removed,
MUST be a DAG; CI MUST assert this and a cycle MUST raise at import time
(a programming error, not a runtime condition), never at apply time (R19)
**And** any missing declared parent (not only the `[L-W]` self-chain
`uuid_padre` from the superseded D7) MUST produce
`RETRY(parent_missing)` and buffer the row in `prod.sync_queue_lw_buffer`
(`cutover-migration.md` REQ-CUT-010)
**And** dependency ordering MUST compose with, not replace, the existing
`ORDER BY prioridad DESC, intentos ASC, created_at ASC LIMIT 100`
batch-selection rule (`repo/sync_queue.py::list_pending`):
the outbox drain still selects a batch of ≤100 rows that way; the motor
then applies rows *within* that batch in `depends_on` topological order,
buffering any child whose parent is not yet in the same batch
(`sync-motor.md` REQ-MOT-015)
**And** `ingreso.uuid_subscripcion_cliente` MUST NEVER appear in
`ingreso`'s `depends_on` — see REQ-CAT-017 (R22) for the rationale.

> **Superseded — see D7, D18.** The prior REQ-CAT-015 required only the 6
> `[L-W]` entries to carry a `hook_validate_parent` bound to
> `ValidateParentChain`, keyed on a single `uuid_padre` self-chain column,
> with no general `depends_on` field. D18 generalizes this: any entry with
> a mandatory FK to another `SyncCatalog` entry — including `[L-E]` and
> `[A]` tables on the invoicing path, which previously had no
> `RETRY(parent_missing)` path at all and instead produced a raw FK
> violation when a child arrived before its parent — now declares
> `depends_on` and gates on parent resolution the same way.

### REQ-CAT-016: `validacion_evento` is the sole `never_propagated` entry (D8-rev)
**Given** the SyncCatalog is loaded
**When** every entry's `sync_strategy` is read
**Then** ONLY `validacion_evento` MUST have
`sync_strategy="never_propagated"`
**And** `validacion_evento` MUST carry a non-empty `justification: str`
field stating the ER-derived reason (CLOUD-ONLY admin review tray, no
stated branch-side need)
**And** `validacion_evento` MUST remain a `SyncCatalog` entry (not an
out-of-catalog exemption) — `check_catalog_drift.py` rule 1 requires every
ORM class to resolve to exactly one catalog, and only a catalog entry has
somewhere to declare `role_required="cloud"`, which makes the R6 import
guard enforceable
**And** `validacion_evento` MUST remain structurally present in the branch
schema (schema parity is a hard project invariant), but no branch process
MUST ever populate it
**And** no other entry MUST set `sync_strategy="never_propagated"` — CI
MUST assert this (R4).

> **Superseded — see D8-rev.** The prior REQ-CAT-004 required 18 entries
> to carry `never_propagated` with individual justifications (reproduced
> above, REQ-CAT-004). D8-rev eliminates the strategy for all of them
> except `validacion_evento`; see REQ-CAT-004 for the corrected direction
> each of those 18 tables now carries.

### REQ-CAT-017: Subscriptions are `bidirectional` + `broadcast_policy="subscription"`, branch-scoped (§16 Q1, R22)
**Given** `subscripciones_cliente` and `subscripcion_vehiculos`
**When** the SyncCatalog is loaded
**Then** both entries MUST have `direction="bidirectional"` (authored on
both sides — cloud admin sells or renews a plan, a cashier enrols one
offline) and `broadcast_policy="subscription"`
**And** `subscripciones_cliente`'s target branch MUST resolve from the
row's own `uuid_sucursal`
**And** `subscripcion_vehiculos` carries no `uuid_sucursal` of its own; its
target branch MUST resolve **transitively** through
`subscripciones_cliente.uuid_sucursal` — this transitive resolution is
exactly what `broadcast_policy="subscription"` means (`sync-motor.md`
REQ-MOT-016)
**And** a subscription row MUST reach **only** the branch that sold it —
this is a deliberate product decision, not an availability accident: the
customer returns to the selling branch to use the plan
**And** the exit-with-subscription validation query (the `ingreso`/`salida`
flow that checks whether a vehicle has an active subscription) MUST
explicitly filter by the current branch's `uuid_sucursal` **in addition
to** relying on `broadcast_policy="subscription"` scoped sync — this is a
defense-in-depth data-integrity control: branch-scoped sync is an
*availability* control (a branch that never receives another branch's
rows cannot see them), not a guarantee against a stale or manually
inserted row that would still validate if the query trusted presence
alone.

**Given** a vehicle with an active subscription presents at a branch that
did not sell it (`ingreso` with no local `subscripciones_cliente` match)
**When** the entry (`ingreso`) flow runs the subscription lookup
**Then** the missing match MUST NOT be treated as an error, MUST NOT
produce a `sync_conflict` row, and MUST NOT trigger `RETRY(parent_missing)`
— it is the **correct** state for a non-selling branch, not a replication
failure (R22)
**And** `ingreso.uuid_subscripcion_cliente` MUST NEVER appear in
`ingreso`'s `depends_on` (REQ-CAT-015) — including it would buffer every
occasional entry at a non-selling branch against a parent that will never
arrive
**And** the branch MUST charge the standard tariff for the entry
**And** the operator-facing UI copy MUST read "no subscription at this
branch" — a phrase distinct from "subscription expired", so the operator
does not mistake branch-scoping for an account problem.

**And** `vehiculos` and `clientes` MUST stay `broadcast_policy="all_branches"`
and MUST NOT be `subscription`-scoped — neither carries a `uuid_sucursal`,
so their only link to a branch runs through `subscripcion_vehiculos`, a
child; deriving a parent's scope from its child would invert the
`depends_on` ordering requirement (REQ-CAT-015), so identity stays global
while subscription entitlement stays local.

### REQ-CAT-018: Identity reconciliation `natural_key` fields (D17)
**Given** `clientes`, `clientes_b2b`, and `vehiculos` — the three
`bidirectional` identity masters
**When** the SyncCatalog is loaded
**Then** `clientes` MUST declare
`natural_key=("tipo_identificador", "numero_identificacion")`
**And** `clientes_b2b` MUST declare `natural_key=("uuid_cliente",)`
**And** `vehiculos` MUST declare `natural_key=("placa",)`
**And** all three MUST declare a `natural_key_normalizer` that trims
separators and whitespace from `numero_identificacion`, and uppercases and
strips separators from `placa` — comparing un-normalized values (e.g.
`ABC-123` vs `ABC123`) MUST NOT be treated as the same entity, and doing
so is a defect: normalization is part of the rule, not an implementation
detail
**And** for these three entries, the `uuid` column identifies a
**version**, not the entity; the natural key identifies the entity —
`resolve_conflict` (`sync-motor.md` REQ-MOT-007) and `hook_pre_insert`
(`hooks.md`, `IdentityReconciler`) MUST key on the natural key, never on
`uuid`, when deciding whether an arriving row is the same entity as the
locally-open version
**And** existing FKs (`factura_electronica.uuid_cliente`,
`subscripcion_vehiculos.uuid_vehiculo`, …) MUST continue to point at the
version the emitting branch actually saw — no FK rewriting ever occurs;
current-identity resolution happens by natural key at read time, in a
view, never by mutating a stored FK
**And** a CI invariant test MUST assert at most one `vigente_hasta IS NULL`
row per normalized natural key across `clientes`, `clientes_b2b`, and
`vehiculos` (R17, `operations.md`).

### REQ-CAT-019: `all_branches_with_override` broadcast policy (D19)
**Given** `configuracion_tolerancias` and `configuracion_seguridad`
**When** the SyncCatalog is loaded
**Then** both entries MUST have `direction="cloud_to_branch"`,
`broadcast_policy="all_branches_with_override"`
**And** rows with `uuid_sucursal IS NULL` (the global default) MUST
broadcast to **all** branches, and every branch MUST store that row
**And** rows with a non-NULL `uuid_sucursal` MUST go **only** to that
branch
**And** the branch pull query MUST be
`WHERE uuid_sucursal IS NULL OR uuid_sucursal = :branch_uuid`
**And** read-time resolution precedence MUST be most-specific-wins: a
branch row overrides the NULL default.

### REQ-CAT-020: `snapshot_columns` never recomputed on apply (D20)
**Given** `factura_impuestos` and `factura_otros_cobros`
**When** the SyncCatalog is loaded
**Then** both entries MUST declare `snapshot_columns` naming every column
that carries a snapshotted rate or amount from `impuestos` /
`otros_cobros` respectively
**And** the applier (`sync-motor.md` REQ-MOT-009) MUST persist these
columns **exactly as received**, on either side, at any time
**And** the applier MUST NOT re-read the live `impuestos` / `otros_cobros`
catalog to recompute a rate or amount during apply — a branch that
receives a new tax-rate version between emission and apply MUST NOT
silently recompute an already-issued invoice, because the rate in force
at emission is the rate the document must carry (ER: "la factura NUNCA lo
lee en vivo").

### REQ-CAT-021: `alert_types` classification and seeding (D6-rev)
**Given** `alert_types` is excluded from every catalog (REQ-CAT-006)
**When** `alert_types` is inspected
**Then** it MUST be classified as `[A]`, deploy-seeded on **both** cloud
and branch by the same idempotent migration/seed script
(`0010_add_alert_types.py`, `ON CONFLICT DO NOTHING`)
**And** every `tipo_alerta` identifier referenced in Python source or
persisted to `alert_types`/`alerta`/`sync_conflict` MUST use a generic
identifier — DIAN-provider failure alert types MUST read as
`fe_provider_error`, `fe_numbering_exhausted`, or an equivalent generic
name, and MUST NEVER contain the literal name of the third-party
electronic-invoicing provider
**And** this table MUST NOT enter the replication pipeline under any
circumstance — adding a new `tipo_alerta` value is a code change that
ships with a deploy, which is the discriminator stated in REQ-CAT-006
**And**, per the project canon for `[A]` tables, the migration that
creates `prod.alert_types` (`0010_add_alert_types.py`,
`cutover-migration.md` Modified Capabilities) MUST include
`REVOKE UPDATE, DELETE ON prod.alert_types FROM app_user` and a
`BEFORE UPDATE OR DELETE` trigger raising an exception, mirroring the
`prod.bitacora` pattern — the registry is append-only even though it is
deploy-seeded, not synced.

## Modified Capabilities

- `parkos_core/sync/conflict_resolver.py` — removes the 4 hardcoded
  `frozenset` constants (`APPEND_ONLY_TABLES`, `LIFECYCLE_EVENT_TABLES`,
  `WORKFLOW_TABLES`, `SESSION_TABLES`) and replaces each lookup with
  `SYNC_CATALOG[name].audit_class` (Gap 2, exploration §3).
- `migrations/versions/0011_add_catalog_triggers.py` — adds
  `fn_enqueue_sync_catalog` coverage for the 18 previously-untriggered
  `[V]` tables (D8-rev), reading `SyncCatalogEntry.priority` only as an
  intra-level tie-break (REQ-CAT-012).
- `parkos_core/sync/table_registry.py` — the untracked reflective
  auto-discovery module is **discarded**, not merged (proposal §9.6); the
  catalog module (`SYNC_CATALOG` + `LOCAL_ONLY_CATALOG`) replaces it
  entirely.
- `modelo_datos_er.mmd` — gains two `%% [A]` entity blocks
  (`sync_queue_lw_buffer`, `alert_types`) plus their relationship lines to
  `sucursal`, bringing the ER to 51 entities (proposal §9.3).

## Out of Scope

- **Adding `fn_enqueue_sync_catalog` triggers for the 18 previously
  untriggered `[V]` tables** — declared in the catalog by this spec, but
  the trigger DDL itself belongs to `cutover-migration.md` (D8-rev is now
  in scope for the whole change, unlike the withdrawn D8 deferral).
- **WebSocket transport** — HTTP polling only (AGENTS.md §"Sync").
- **Auth chain changes** — `sync_router` JWT, pairing, revocation list
  remain untouched (catalog refactor is payload-layer only).
- **Frontend UI for D16 degraded mode banner** — separate `sdd-new`
  change.
- **SyncMotor API surface** — covered by `sync-motor.md`.
- **Hook callable implementations** — covered by `hooks.md`.
- **Volume-bounded `clientes` broadcast** — `clientes` broadcasts in full
  under `all_branches`; a volume-bounded broadcast is deferred (R18).
- **Identity alias / merge table** — D17 reconciles by natural key without
  one; a merge mechanism would require FK rewriting, which the no-UPDATE
  canon forbids.
