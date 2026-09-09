# Spec: `hooks`

## Purpose

Define the per-table hook contract — typed callables that the `SyncMotor`
invokes before, after, or in lieu of the `repo/*` write. Encodes decision
**D2** (amended — `[V]` bi-temporal generic apply, now live for
`clientes`/`vehiculos`/`subscripcion_vehiculos` because D8-rev actually
replicates them), **D17** (identity reconciliation for `clientes` /
`clientes_b2b` / `vehiculos`, and the re-targeted `PlateChangeCascade`),
and **D18** (`ValidateParentChain` generalized to any entry with a
non-empty `depends_on`, generalizing D7, with a single escalation path).
Hooks are pure callables
(`Callable[[HookContext], Awaitable[HookResult]]`) that tests can inject
as lambdas (R7).

> **Amendment note.** D1's `SyncBackEventEmitter` hook is removed in full
> (D1-rev) — there is no `prod.sync_back_events` table, no DIAN
> sync-back event, and no `reimpresion_ticket.origen` column for this hook
> to distinguish. Two other hooks are re-scoped for reasons that follow
> directly from D8-rev making `clientes`/`vehiculos` actually replicate:
> `PIIRedactor` (§ REQ-HOOK-004) and `PlateChangeCascade` (§ REQ-HOOK-005).
> Where a requirement below replaces removed or superseded content, the
> superseded text is kept visible in a blockquote, per the proposal's
> amendment rule (§0).

## Requirements

### REQ-HOOK-001: `HookContext` dataclass
**Given** a hook callable registered on a `SyncCatalogEntry`
**When** the motor invokes the hook
**Then** the hook MUST receive a `HookContext` carrying
`spec: SyncCatalogEntry`, `payload: dict` (mutable; `hook_pre_insert` may
adjust fields), `session: AsyncSession`, `actor_uuid: UUID`,
`chain_head: bytes | None = None` (set for `hook_chain_extend`),
`parent_local: dict | None = None` (set for `hook_validate_parent`),
`open_version: dict | None = None` (set for `natural_key` specs — D17 —
carries the currently-open version row for `IdentityReconciler` to
compare against), `branch_uuid: UUID | None = None`.

> **Amended.** The prior `HookContext` did not carry `open_version`. D17's
> `IdentityReconciler` needs the currently-open version to decide between
> `noop` / `forward` / `historical` (REQ-HOOK-010); this field is added so
> the hook does not have to re-query it.

### REQ-HOOK-002: `HookResult` dataclass
**Given** a hook callable
**When** the hook returns
**Then** the hook MUST return a `HookResult` carrying
`proceed: bool` (False aborts `apply_row`),
`payload_override: dict | None` (used by `hook_pre_insert`),
`chain_extension: tuple[bytes, bytes] | None` (used by `hook_chain_extend`,
`(hash_anterior, hash_actual)`),
`parent_valid: bool = True` (used by `hook_validate_parent`, False
triggers `RETRY(parent_missing)`),
`reconciliation: Literal["noop","forward","historical"] | None = None`
(D17 — set by `IdentityReconciler`),
`cascade_rows: list[tuple[str, dict]] = field(default_factory=list)`
(rows a hook wants the motor to apply in the same transaction, e.g.
`PlateChangeCascade`'s closed/inserted `subscripcion_vehiculos` rows).

> **Amended.** `reconciliation` and `cascade_rows` are new fields (D17,
> `PlateChangeCascade` re-target). Neither existed in the prior pass.

### REQ-HOOK-003: Hook lifecycle order in `apply_row`
**Given** any `apply_row` call
**When** the motor processes a row
**Then** the invocation order MUST be:

1. **`hook_validate_parent`** (if `spec.depends_on != ()`, for **any**
   audit class — D18, generalizes the prior L_W-only rule) — resolves
   every declared parent, using `spec.parent_fk_column` for self-chain
   edges. If any declared parent returns `parent_valid=False`, the motor
   MUST short-circuit and return
   `ApplyResult(status=RETRY, reason="parent_missing")` **before** any
   write is attempted.
2. **`hook_pre_insert`** (if set on the spec) — identity reconciliation
   (D17) or payload adjustment. The motor MUST use
   `result.payload_override` if present, otherwise the original
   `payload`.
3. **Repo call** — dispatches per `spec.apply_strategy`. `snapshot_columns`
   (D20) are written verbatim.
4. **`hook_post_insert`** (if set) — telemetry emission (D10); applies any
   `result.cascade_rows` through the motor (recursively, via `apply_row`)
   so cascades honor the same invariants — audit-first, dependency
   validation, hash-chain extension — as primary rows.
5. **`hook_chain_extend`** (if `spec.hash_chain=True` and set) — sets
   `chain_extension`. The motor MUST call
   `repo/hash_chain.append(session, spec.model_cls, payload, actor_uuid,
   chain_extension=result.chain_extension)`. The DB trigger
   `fn_extend_hash_chain` re-verifies server-side.

> **Superseded — see D18.** The prior REQ-HOOK-003 ran `hook_pre_insert`
> first, the repo call second, `hook_validate_parent` third (gated on
> `audit_class == "L_W"` only), `hook_post_insert` fourth, and
> `hook_chain_extend` fifth — parent validation ran *after* persistence,
> which cannot prevent an FK violation, only observe one. D18 moves
> `hook_validate_parent` ahead of the repo call and generalizes it beyond
> `[L_W]` to any entry with a non-empty `depends_on` (`[L-E]` and `[A]`
> now included, per `sync-motor.md` REQ-MOT-007).

### REQ-HOOK-004: `hook_pre_insert` re-scoped — `PIIRedactor` protects observability surfaces, not the replicated payload (§8)
**Given** the `clientes` spec, now `bidirectional` and `all_branches`
(D8-rev)
**When** the motor applies a `clientes` row
**Then** `PIIRedactor` MUST NOT run as `hook_pre_insert` on `clientes` and
MUST NOT redact `email`, `telefono`, `direccion`, `nombre`, or `apellido`
from the replicated payload — the ER states `clientes.email` "recibe la
representación gráfica de la factura electrónica" and `telefono` /
`nombre` / `apellido` are the acquirer identity on the electronic
document; stripping them would make every replicated client unusable as
an invoice acquirer
**And** `PIIRedactor` MUST instead redact PII **only** in three
observability surfaces: `sync_log` entries, structured logs (`structlog`
output, `operations.md` REQ-OPS-007), and `sync_conflict.datos_local` /
`sync_conflict.datos_remoto` — none of which require the PII for a
business function
**And** the cross-tenant transport of the `clientes` payload itself relies
on TLS 1.3 plus the `sync-agent-` JWT as its control, not on redaction
**And** test fixtures for `clientes` MUST use generated data only (no real
PII), per R20.

> **Superseded — see §8 (proposal amendment).** The prior REQ-HOOK-004
> bound `PIIRedactor` as `hook_pre_insert` on `clientes`, redacting
> `email`/`telefono`/`direccion` to `***` in `HookResult.payload_override`
> before the cross-tenant push, on the premise that `clientes` was
> `never_propagated` and any push was incidental. D8-rev makes `clientes`
> actually replicate `bidirectional`/`all_branches`; redacting the
> acquirer's contact fields on the wire would break DIAN invoice emission
> at every branch that only received the redacted view.

### REQ-HOOK-005: `hook_post_insert` re-targeted — `PlateChangeCascade` closes and reopens `subscripcion_vehiculos`, not `reclamos` (§8)
**Given** the `vehiculos` spec with `hook_post_insert=PlateChangeCascade`
(now `bidirectional`, D8-rev)
**When** the motor applies a `vehiculos` row whose `placa` (normalized per
`sync-catalog.md` REQ-CAT-018) differs from the locally-stored version
**Then** the hook MUST identify every `subscripcion_vehiculos` row that
currently points at the **old** `vehiculos` version
**And** the hook MUST emit `cascade_rows` that close those junction rows
(`vigente_hasta = NOW()`) and insert replacement rows pointing at the
**new** `vehiculos` version, via the same `close_and_insert` bi-temporal
mechanism used for any other `[V]` transition
**And** the audit trail for this transition MUST be `log_transaccional`,
the same mechanism as every other bi-temporal transition — not a
`reclamos` row
**And** the `vehiculos` write itself MUST proceed regardless (no abort)
**And** the motor MUST apply the returned `cascade_rows` in the same
transaction, per REQ-HOOK-003 step 4.

> **Superseded — see §8 (proposal amendment).** The prior REQ-HOOK-005 ran
> `PlateChangeCascade` as `hook_pre_insert` and had it emit a new
> `reclamos` `[L-W]` row with `uuid_padre=<vehiculos_uuid>`,
> `motivo='plate_change'`. This is not storable: `reclamos.uuid_reclamo_padre`
> is a **self**-FK and `reclamos.tipo_reclamable ∈ {ingreso, salida,
> factura, subscripcion}` — there is no vehicle reclamable. The genuine
> integrity concern is narrower and different: `vehiculos.uuid` identifies
> a *version*, so a plate change mints a new version while existing
> `subscripcion_vehiculos` rows still point at the old one — the
> subscription would silently keep covering the previous plate. The
> corrected cascade closes and re-inserts the junction rows instead.

### REQ-HOOK-006: `hook_pre_insert` validates subscription lifecycle and vehicle-capacity on `subscripcion_vehiculos`
**Given** the `subscripcion_vehiculos` spec with
`hook_pre_insert=SubscriptionLifecycle` (now `bidirectional`,
`broadcast_policy="subscription"`, `sync-catalog.md` REQ-CAT-017)
**When** the motor applies a row whose `estado` is a state-transition
that is not in the legal-transition table for this audit class
**Then** the hook MUST return `HookResult(proceed=False, reason=...)`
**And** the motor MUST abort `apply_row` with
`ApplyResult(status=CONFLICT, reason="illegal_state_transition")`
**And** the abort MUST write a `sync_conflict` row with
`politica='illegal_lifecycle'` for operator review

**Given** a row that adds a vehicle to an active subscription
**When** the hook validates the transition
**Then** the hook MUST ALSO validate the resulting vehicle count against
the parent plan's `cantidad_maxima_vehiculos` (`tipo_subscripciones`,
resolved through the already-validated `depends_on` parent
`subscripciones_cliente`)
**And** a row that would exceed `cantidad_maxima_vehiculos` MUST be
treated the same as an illegal state transition — `proceed=False`,
`ApplyResult(status=CONFLICT, reason="illegal_state_transition")`, and a
`sync_conflict` row with `politica='illegal_lifecycle'`.

The legal transitions table is:

| From `estado` | Allowed `estado` values |
|---|---|
| `activa` | `suspendida`, `cancelada` |
| `suspendida` | `activa`, `cancelada` |
| `cancelada` | (terminal) |

### REQ-HOOK-007: `hook_post_insert` emits bi-temporal compensation on `factura_pagos`
**Given** the `factura_pagos` spec with
`hook_post_insert=BiTemporalCompensation`
**When** the motor applies a row whose `tipo_movimiento='reverso'`
**Then** the hook MUST emit a compensating `log_transaccional` row in the
same transaction with `datos->>'compensacion_para'=<original_pago_uuid>`
**And** the compensating row MUST extend the hash chain
(`hook_chain_extend` runs as part of the same `apply_row`)
**And** the hook MUST NOT modify the original `factura_pagos` row (it is
immutable; the reverso is a NEW row, never an UPDATE)
**And** `factura_pagos.uuid_pago_revertido` is a self-chain FK
(`self_chain=True`, `parent_fk_column="uuid_pago_revertido"`,
`sync-catalog.md` REQ-CAT-015), excluded from the topological sort and
resolved by `ValidateParentChain` (REQ-HOOK-012) like every other
self-chain.

### REQ-HOOK-008: `hook_chain_extend` on `log_transaccional`
**Given** the `log_transaccional` spec with
`hook_chain_extend=LogTransaccionalChain`
**When** the motor applies any row that emits a `log_transaccional` entry
**Then** the hook MUST compute
`hash_anterior = current_chain_head_for(uuid_sucursal)`
**And** `hash_actual = sha256(hash_anterior || canonical(payload))`
**And** return `HookResult(chain_extension=(hash_anterior, hash_actual))`
**And** the motor MUST call `repo/hash_chain.append` with this extension
**And** the DB trigger `fn_extend_hash_chain` MUST re-verify server-side.

### REQ-HOOK-009: `hook_chain_extend` on `revocacion_factura`
**Given** the `revocacion_factura` spec with
`hook_chain_extend=RevocacionFacturaChain`
**When** the DIAN dispatcher confirms `aceptado` and writes a
`revocacion_factura` row
**Then** the hook MUST extend the per-tenant chain with the same pattern
as `log_transaccional` (REQ-HOOK-008)
**And** the hook MUST replace the manual
`hash_chain.append(RevocacionFactura, ...)` call currently in
`dian/cloud/dispatcher.py` lines 488-493
**And** `verify_chain` MUST iterate this entry alongside `log_transaccional`
(`sync-motor.md` REQ-MOT-006)
**And**, because `revocacion_factura` now resolves to exactly one catalog
entry (`sync-catalog.md` REQ-CAT-005), this hook extends exactly one
chain per `(tabla, uuid_sucursal)` — the interleaved double-chain hazard
from the superseded dual-catalog design cannot recur.

### REQ-HOOK-010: `IdentityReconciler` — natural-key reconciliation for `clientes`, `clientes_b2b`, `vehiculos` (D17)
**Given** the three `bidirectional` identity masters, each declaring a
`natural_key` (`sync-catalog.md` REQ-CAT-018)
**When** the motor's `hook_pre_insert=IdentityReconciler` runs on an
arriving row
**Then** the hook MUST compare the arriving row against the currently
open version (`HookContext.open_version`) by **normalized** natural key
only — never by `uuid`
**And** the hook MUST classify the arrival into exactly one of:

1. **`noop`** — the arriving row's business columns are identical to the
   open version (ignoring `uuid`, `created_at`, `created_by`, `sync_*`).
   The hook MUST return `HookResult(proceed=True, reconciliation="noop")`
   and the apply MUST be a no-op that still reports `APPLIED` — this is
   the common case of two branches registering the same client from the
   same document, and it is what prevents version-chain inflation.
2. **`forward`** — the arriving `vigente_desde` is **later** than the open
   version's. The hook MUST return
   `HookResult(proceed=True, reconciliation="forward")` and the motor MUST
   perform the ordinary `close_and_insert`: close the open version at the
   arriving row's `vigente_desde`, insert the arriving row as the new open
   version. The arriving branch's `uuid` survives as the current version.
3. **`historical`** — the arriving `vigente_desde` is **earlier** than the
   open version's (a late arrival after a partition). The hook MUST return
   `HookResult(proceed=True, reconciliation="historical")` and the motor
   MUST insert the arriving row as an already-closed historical version
   (`vigente_hasta` = the open version's `vigente_desde`). The current
   version MUST NOT be touched, and no UPDATE of a newer row's business
   columns ever occurs.

**And**, for `forward` or `historical` arrivals whose business columns
(name, email, phone, `uuid_tipo_persona`, …) differ materially from the
open version, the hook MUST ALSO write an informational `sync_conflict`
row (`politica='identity_divergence'`) so an operator can review — the
apply MUST still succeed; it MUST NOT block, because blocking a client
registration blocks the invoice on the DIAN critical path
**And** the hook MUST NEVER rewrite an existing FK
(`factura_electronica.uuid_cliente`, `subscripcion_vehiculos.uuid_vehiculo`,
…) — those FKs keep pointing at the version the emitting branch actually
saw; current-identity resolution happens by natural key at read time, in
a view, never by mutating a stored FK
**And** the comparison MUST use the normalized natural key
(`sync-catalog.md` REQ-CAT-018): un-normalized `ABC-123` vs `ABC123` MUST
NOT be treated as distinct entities.

> **Superseded — see D1-rev.** This requirement slot previously specified
> `SyncBackEventEmitter`: a `hook_post_insert` bound to
> `factura_electronica`, `revocacion_factura`, and `envio_dian` that
> emitted a `sync_back_event` row (either a sibling table or a
> `sync_queue` row with `operacion='sync_back_event'`) carrying
> `numero_oficial` back to the branch, which the branch worker then used
> to update `factura_electronica.numero_temporal → numero_oficial`. D1-rev
> removes this hook, the table, the flag, and the vocabulary entirely —
> there is no `numero_temporal`/`numero_oficial` split to reconcile; the
> branch numbers once, in-branch (`cutover-migration.md` REQ-CUT-014).

### REQ-HOOK-011: `reimpresion_ticket` direction is `branch_to_cloud`; no `origen` column
**Given** the `reimpresion_ticket` catalog entry
**When** the entry is inspected
**Then** the entry's `direction` field MUST be `branch_to_cloud` —
narrowed from `bidirectional` because, with D1-rev, nothing in the cloud
initiates a reprint; there is no cloud→branch leg to model
**And** the entry MUST NOT declare an `origen: Literal["manual","auto"]`
column — that field existed only to distinguish an auto-reprint triggered
by the withdrawn sync-back arrival, and D1-rev removes it in full
**And** the entry's `hook_validate_parent` MUST verify every declared
`depends_on` parent, including `facturas` and the self-chain
`uuid_reimpresion_padre` via `parent_fk_column` (REQ-HOOK-012) — reprint
availability does not depend on cloud connectivity (`cutover-migration.md`
REQ-CUT-013).

> **Fixed defect — the prior REQ-HOOK-011 assigned a `direction` value to
> the `broadcast_policy` field.** The prior text read: "the entry's
> `broadcast_policy` MUST be `bidirectional`" — `bidirectional` is a
> member of the `direction` enum, not the `broadcast_policy` enum
> (`single_branch | all_branches | all_branches_with_override |
> subscription`, `sync-catalog.md` REQ-CAT-001), so the requirement as
> written was untypeable and would fail the CI assertion that the two
> enums are disjoint (REQ-CAT-001). The behavior the prior requirement was
> actually trying to pin down — that `reimpresion_ticket` participates in
> both directions of the DIAN reprint story — is superseded outright by
> D1-rev: the correct, single value for the correct field is
> `direction="branch_to_cloud"`, stated above. The rest of the prior
> requirement (the `origen='auto'` rejection rule and the DIAN
> sync-back-derived parent-chain check) is also superseded, since both
> depended on the removed `SyncBackEventEmitter`/`origen` machinery.

### REQ-HOOK-012: `ValidateParentChain` generalized to any entry with `depends_on` (D18, generalizes D7)
**Given** any `SyncCatalogEntry` with a non-empty `depends_on`
(`sync-catalog.md` REQ-CAT-015 — no longer limited to the 6 `[L-W]`
entries)
**When** the motor processes a row
**Then** the hook MUST, for **every** name in `spec.depends_on`, resolve
the FK column on `spec.model_cls` pointing at that parent table and query
`SELECT 1 FROM {parent_table} WHERE uuid = :fk_value AND uuid_sucursal IS
NOT DISTINCT FROM :branch_uuid`
**And**, for the seven self-referential FKs marked `self_chain=True`
(`sync-catalog.md` REQ-CAT-015), the hook MUST resolve the parent column
via `spec.parent_fk_column` instead of the generic FK-to-parent-table
lookup — the six `[L-W]` tables plus `factura_pagos` each use a
differently-named self-chain column, which the prior single-`uuid_padre`
contract did not account for
**And** if every declared parent exists locally OR appears earlier in the
same in-flight batch (`sync-motor.md` REQ-MOT-015), the hook MUST return
`HookResult(parent_valid=True)`
**And** if any declared parent is missing locally AND not earlier in the
batch, the hook MUST return
`HookResult(parent_valid=False, proceed=False)`
**And** the motor MUST return
`ApplyResult(status=RETRY, reason="parent_missing")`
**And** `ingreso.uuid_subscripcion_cliente` MUST NEVER be resolved by this
hook — it is explicitly excluded from `ingreso.depends_on`
(`sync-catalog.md` REQ-CAT-017, R22); a missing local
`subscripciones_cliente` match at a non-selling branch is not a
parent-missing condition.

> **Amended — see D18.** The prior REQ-HOOK-012 scoped this hook to the 6
> `[L-W]` entries and a single `uuid_padre` column. D18 generalizes both:
> the hook now applies to any entry with `depends_on != ()` (including
> `[L-E]` and `[A]` per `sync-motor.md` REQ-MOT-007), and resolves each
> declared parent by its own FK column, with `parent_fk_column` reserved
> for self-chain edges only.

### REQ-HOOK-013: One escalation path for a missing declared parent (D18, reconciles R13)
**Given** a row for which `hook_validate_parent` returns
`parent_valid=False`
**When** the motor decides how to handle the deferral
**Then** the row MUST be buffered in `prod.sync_queue_lw_buffer`
(`cutover-migration.md` REQ-CUT-010), keyed on the missing declared
parent's `(tabla_padre, uuid_padre)`
**And** the row MUST NOT be re-enqueued into `sync_queue` for this reason
— the two previously-uncoordinated paths (`sync_queue` re-enqueue at
`intentos>=6`, and the buffer's own TTL sweep) are reconciled into this
single mechanism
**And** the buffer alone owns the wait; the sweep alone owns the timeout;
the timeout alone emits `alerta tipo_alerta='orphan_workflow_chain'`
(REQ-HOOK-014) — there is no double-counting between a `sync_queue`
retry counter and the buffer's TTL.

> **Superseded — see D18.** This requirement slot previously specified the
> `SyncBackEventEmitter` transactionality contract (persist the
> `sync_back_event` row atomically with the source write; roll back both
> together). D1-rev removes that hook in full (REQ-HOOK-010); this slot
> now carries the D18 single-escalation-path rule instead, which replaces
> the two-path design the prior REQ-HOOK-014 described.

### REQ-HOOK-014: Buffered-row release and TTL escalation (D18, generalizes D15)
**Given** a row buffered in `prod.sync_queue_lw_buffer` because a declared
parent was missing (REQ-HOOK-013)
**When** the parent row later arrives
**Then** the buffer MUST release all dependent rows for that parent in the
order they were buffered (strict causal order, FIFO within a parent)
**And** if the parent has not arrived after a maximum TTL of 24 hours, the
hourly buffer sweep MUST write an `alerta` row with
`tipo_alerta='orphan_workflow_chain'`, `uuid_registro=<orphan_uuid>`,
`tabla=<buffered_table>`, `uuid_sucursal=<branch_uuid>`
**And** the buffered row MUST be marked `estado='fallido'` in
`prod.sync_queue_lw_buffer` with `ultimo_error='parent_missing_timeout'`
— no DELETE
**And** the row MUST remain retrievable for operator inspection; the
buffer table, like every `[A]` table, is append/update-only under a
`REVOKE`+trigger contract (`cutover-migration.md` REQ-CUT-010).

> **Superseded — see D18.** The prior REQ-HOOK-014 re-enqueued the row
> into `sync_queue` with a `datos->>'parent_missing'='true'` flag and
> `intentos += 1`, escalating to an `alerta` only after `intentos >= 6`.
> This produced two uncoordinated escalation paths for the same
> condition. D18 reconciles them into the single buffer-owns-wait,
> sweep-owns-timeout mechanism above (REQ-HOOK-013).

### REQ-HOOK-015: Hooks are pure callables — test injection pattern (R7)
**Given** a test that exercises `apply_row` for a spec with a hook
**When** the test sets up the spec
**Then** the test MUST inject the hook as a lambda or function:
```python
spec = replace(spec, hook_post_insert=lambda ctx: HookResult(proceed=True))
```
**And** the test MUST NOT depend on the production hook implementation
**And** the `conftest.py::make_spec` helper MUST expose a fluent API for
overriding any of the 4 hook slots per test, including the D17-specific
`reconciliation` and `cascade_rows` fields on the returned `HookResult`
**And** the precedent from `tests/unit/test_event_record.py::_make_session()`
MUST be preserved and extended for hook injection
**And** the parametrize helper (`operations.md` REQ-OPS-010) MUST cover
every one of the 46 `SYNC_CATALOG` entries that binds at least one hook.

## Modified Capabilities

- `parkos_core/dian/cloud/dispatcher.py` — removes the manual
  `hash_chain.append(RevocacionFactura, ...)` call (lines 488-493) — the
  hook does it via the catalog spec — AND removes the
  `operacion='sync_back_event'` emit loop (~line 496) in full (D1-rev);
  there is no replacement emit loop because there is no `sync_back_event`.
- `parkos_core/models/L_W/reimpresion_ticket.py` — does **not** gain an
  `origen` column (superseded, REQ-HOOK-011).
- `parkos_core/repo/event.py::record_event` — its current inline
  `hash_chain.append(LogTransaccional, ...)` call MUST be replaced by the
  hook invocation so the chain extension flows through the spec's
  `hook_chain_extend` slot.
- `parkos_core/sync/hooks/identity_reconciler.py` — new module
  implementing `IdentityReconciler` (D17, REQ-HOOK-010).
- `parkos_core/sync/hooks/plate_change_cascade.py` — re-targeted to close
  and reopen `subscripcion_vehiculos` rows (REQ-HOOK-005), no longer
  writes `reclamos`.

## Out of Scope

- **New hook kinds** (e.g. pre-validate, post-emit) — the 4 hook slots
  (`hook_pre_insert`, `hook_post_insert`, `hook_chain_extend`,
  `hook_validate_parent`) are sufficient for all 46 `SYNC_CATALOG`
  entries; future changes add new slots if a need arises.
- **Hook runtime metrics** — the motor records hook invocation in
  `ApplyResult.metrics` (`sync-motor.md` REQ-MOT-005); metric emission is
  `operations.md` REQ-OPS-006.
- **Webhook fan-out to external systems** — the DIAN provider remains the
  only external integration; no new HTTP webhooks are introduced.
- **`factura_electronica`'s own retry/backoff curve** — a DIAN-flow
  concern covered by `cutover-migration.md` REQ-CUT-014, not a hook.
