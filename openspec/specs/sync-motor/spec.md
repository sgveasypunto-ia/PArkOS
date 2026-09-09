# Spec: `sync-motor`

## Purpose

Define the `SyncMotor` API — stateless methods that dispatch per catalog
spec to the existing `repo/*` helpers, enforce audit-first invariants
(close+insert for `[V]`, append-only for `[A]`, hash chain for chain
bearers), apply a batch in dependency order, and read the
`PARKOS_SYNC_ENGINE` feature flag so legacy and catalog paths coexist
during the cutover (D11, D12). Encodes decision **D4** (replace
`_read_local_seq` stub with concrete per-`seq_strategy` lookups), **D17**
(natural-key identity reconciliation dispatch), **D18** (`apply_batch`
topological ordering and the generalized `RETRY(parent_missing)` for
`[L-E]`/`[L-W]`/`[A]`, generalizing D7), and **D20** (snapshot columns
never recomputed on apply).

## Requirements

### REQ-MOT-001: `apply_row` dispatches by `apply_strategy`
**Given** a `SyncCatalogEntry` with `apply_strategy="close_and_insert"`
**When** `SyncMotor.apply_row(spec, payload, actor_uuid=…)` is called
**Then** the motor MUST dispatch to
`repo.versioned.close_and_insert(spec.model_cls, payload, actor_uuid)`
**And** the motor MUST NOT directly write to the DB itself — it MUST
delegate to a `repo/*` helper so audit-first invariants are honored.

Mapping table for the 5 `apply_strategy` values:

| `apply_strategy` | Helper called |
|---|---|
| `close_and_insert` | `repo.versioned.close_and_insert` |
| `record_event` | `repo.event.record_event` |
| `append_event` | `repo.append_only.append_event(chain_hash=spec.hash_chain)` |
| `append_transition` | `repo.workflow.append_transition` |
| `session_cycle` | `repo.session_cycle.record_login` (insert) or `close_login_with_log` (close) based on payload `estado` field |

**Given** any spec with a non-empty `depends_on`
**When** `apply_row` runs
**Then** the motor MUST validate every declared parent (REQ-MOT-015)
**before** the repo dispatch above — parent validation is a precondition
of persistence, not an observation after the fact.

### REQ-MOT-002: `apply_row` honors bi-temporal close+insert for `[V]`
**Given** a payload for a `[V]` table (`audit_class="V"`)
**When** `apply_row` runs `repo.versioned.close_and_insert`
**Then** the helper MUST close the current row (set `vigente_hasta = NOW()`,
`estado = 'inactivo'`) AND insert a new row with `vigente_desde = NOW()`,
`vigente_hasta = NULL`, `estado = 'activo'`
**And** the original row MUST remain in the table (no DELETE, per project
canon "no physical DELETE")
**And** for the three natural-key entries (`clientes`, `clientes_b2b`,
`vehiculos`, D17), the row that `close_and_insert` closes and the row it
inserts MUST be selected by natural key, not by `uuid` — see REQ-MOT-007
and `hooks.md`'s `IdentityReconciler`.

### REQ-MOT-003: `apply_row` honors append-only for `[A]`
**Given** a payload for an `[A]` table (`audit_class="A"`)
**When** `apply_row` runs `repo.append_only.append_event`
**Then** the helper MUST call `repo/append_only.py::append_event` with
`chain_hash=spec.hash_chain`
**And** the new row MUST be `INSERT`-only; the motor MUST NOT issue any
`UPDATE` or `DELETE` against the `[A]` table
**And** for `factura_impuestos` / `factura_otros_cobros`, the columns
named in `spec.snapshot_columns` MUST be written verbatim from the
payload — the motor MUST NOT recompute them from the live `impuestos` /
`otros_cobros` catalog at any point in this call (D20, REQ-CAT-020).

### REQ-MOT-004: `apply_row` routes through hash chain when `hash_chain=True`
**Given** an entry with `hash_chain=True` (`log_transaccional` or
`revocacion_factura`)
**When** `apply_row` runs
**Then** it MUST call `repo/hash_chain.append(session, spec.model_cls,
payload, actor_uuid)` instead of `repo/append_only.append_event`
**And** the helper MUST read the per-tenant chain head (`uuid_sucursal`),
compute `hash_anterior = <previous_hash_actual>` and
`hash_actual = sha256(hash_anterior || payload)`, and write both columns
**And** the DB trigger `prod.fn_extend_hash_chain` MUST re-verify the chain
server-side; mismatches raise an exception that the motor surfaces as
`ApplyResult(status=CONFLICT, reason="hash_chain_break")`
**And**, because `revocacion_factura` now resolves to exactly one catalog
entry (`sync-catalog.md` REQ-CAT-005), there is exactly one chain per
`(tabla, uuid_sucursal)` for each of the two chain-bearing tables.

### REQ-MOT-005: `apply_row` returns `ApplyResult` with status enum
**Given** any `apply_row` call
**When** the method returns
**Then** the result MUST be an `ApplyResult` dataclass with
`status: Literal["APPLIED","CONFLICT","RETRY"]`,
`row_uuid: UUID | None`, `reason: str | None`, and
`metrics: dict[str, int] | None`
**And** `metrics` MUST always include
`{"hook_pre_insert": 0|1, "hook_post_insert": 0|1, "hook_chain_extend": 0|1,
 "hook_validate_parent": 0|1}` so the operator can audit hook invocation
per row.

**Given** a per-row `ApplyResult` from a `/sync/events` push
**When** `sync_router.py`'s handler serializes the response for the
pushing side
**Then** each internal `ApplyResult.status` value MUST map to exactly one
wire-level per-row status and one `sync_queue` outbox action on the
pushing side, per this table:

| Motor `status` | Wire status | Pushing side's `sync_queue` action |
|---|---|---|
| `APPLIED` | `applied` | `repo.sync_queue.mark_success` |
| `CONFLICT` | `conflict` | `mark_success` — delivered; a `sync_conflict` row exists at the receiver |
| `RETRY` (`reason="parent_missing"`) | `retry_parent_missing` | `mark_success` — **delivered**; ownership of the wait transfers to the receiver's dependency buffer (`sync-catalog.md` REQ-CAT-015, `hooks.md` REQ-HOOK-013, `cutover-migration.md` REQ-CUT-015) |
| transport / HTTP failure (no `ApplyResult` returned) | — | `mark_failed` → `next_retry_delay(intentos)` |

**And** a row whose declared `depends_on` parent has not yet arrived MUST
report the wire status `retry_parent_missing` — never a generic failure
status and never a silent drop
**And** `retry_parent_missing` MUST NOT increment `intentos` or set
`next_retry_at` on the pushing side's `sync_queue` row — `intentos` and
`next_retry_at` carry *transport-failure* semantics only; the row was
delivered successfully, and the wait for its parent is owned entirely by
the receiver's dependency buffer, not by the pushing side's retry budget
**And** the row MUST enter the receiver's dependency-buffer path
(`prod.sync_queue_lw_buffer`) exactly as described in
`sync-catalog.md` REQ-CAT-015 and `hooks.md` REQ-HOOK-013/014 — this
table only fixes the wire vocabulary and the pushing-side outbox
consequence; the buffering mechanism itself is unchanged.

### REQ-MOT-006: `verify_chain` walks chain-bearing tables
**Given** `SyncCatalogEntry` with `verify_chain=True`
**When** `SyncMotor.verify_chain(spec, branch_uuid)` runs
**Then** the motor MUST walk `spec.model_cls` ordered by
`(timestamp_evento, uuid)` partitioned by `branch_uuid`
**And** it MUST verify `hash_actual == sha256(hash_anterior || payload)`
for every row
**And** on the first mismatch, the walker MUST record a `ChainAnomaly`
with `{row_uuid, expected_hash, actual_hash, row_index}` and continue
**And** the method MUST return `list[ChainAnomaly]` (empty on a clean
chain)
**And** the cloud-side `job_sync_cloud._hash_chain_verifier_loop` MUST
invoke `verify_chain` for every entry where `verify_chain=True`
(`log_transaccional` and `revocacion_factura`, REQ-CAT-009).

### REQ-MOT-007: `resolve_conflict` per audit class strategy (D4, D17, D18)
**Given** a `(local, remote)` pair and a catalog spec
**When** `SyncMotor.resolve_conflict(spec, local=local, remote=remote)`
runs
**Then** the decision MUST be:

| `audit_class` | Strategy | Outcome |
|---|---|---|
| `V` with `natural_key` (`clientes`, `clientes_b2b`, `vehiculos`) | D17 reconciliation via `IdentityReconciler` (`noop` \| `forward` \| `historical`) | `APPLIED`, never blocking (REQ-MOT-008) |
| `V` without `natural_key` | `remote.seq > local.seq` (via `_read_local_seq`, REQ-MOT-009) | `APPLIED` else `MANUAL` |
| `L_E` | every declared `depends_on` parent resolves (REQ-MOT-015) | `APPLIED` else `RETRY(parent_missing)` |
| `L_W` | every declared `depends_on` parent resolves, including self-chain via `parent_fk_column` (REQ-MOT-015) | `APPLIED` else `RETRY(parent_missing)` |
| `L_S` | grace-window check (REQ-MOT-013) | `APPLIED` within window, else `MANUAL` |
| `A` | every declared `depends_on` parent resolves (REQ-MOT-015) | `APPLIED` else `RETRY(parent_missing)` |

> **Amended — `[L-E]` and `[A]` are no longer unconditionally `APPLIED`.**
> The prior REQ-MOT-007 treated `L_E` as "events immutable → always
> `APPLIED`" and `A` as "append-only → always `APPLIED`". Neither had a
> `RETRY(parent_missing)` path, so a child arriving before its declared
> parent produced a raw FK violation rather than a resolvable condition —
> precisely on the invoicing path, where children (`facturas`,
> `factura_detalle`, `factura_impuestos`, …) frequently arrive ahead of a
> parent during a burst. Both classes now gate on `depends_on` parent
> resolution (D18) while keeping append-only immutability: the row is
> never modified, only deferred in `prod.sync_queue_lw_buffer`
> (`cutover-migration.md` REQ-CUT-010).

### REQ-MOT-008: Identity reconciliation dispatch for natural-key `[V]` entries (D17)
**Given** a remote row for `clientes`, `clientes_b2b`, or `vehiculos`
**When** `resolve_conflict` runs
**Then** the motor MUST delegate to the spec's `hook_pre_insert`
(`IdentityReconciler`, `hooks.md`) rather than the `seq`-based strategy in
REQ-MOT-009
**And** the outcome MUST always be `APPLIED` — natural-key reconciliation
MUST NEVER block, because blocking a client or vehicle registration would
block the invoice on the DIAN critical path
**And** the reconciliation kind (`noop`, `forward`, `historical`) and any
divergent-data `sync_conflict` write are governed by `hooks.md`'s
`IdentityReconciler` contract, not by `resolve_conflict` directly — this
method only routes to it based on `spec.natural_key` being non-empty.

### REQ-MOT-009: Conflict resolution for `[V]` without a natural key uses `max(seq_strategy) > local_seen`
**Given** a remote row for a `[V]` table with `natural_key=()`
**When** `_read_local_seq` returns `local_seq` and the remote payload
carries `remote_seq` (parsed from `datos->>'seq'` for `seq_via_datos`,
else from `created_at`/`timestamp_evento` for the time-based strategies)
**Then** if `remote_seq > local_seq` the motor MUST return
`ConflictResolution.APPLIED`
**And** if `remote_seq <= local_seq` the motor MUST return
`ConflictResolution.MANUAL` and write a `sync_conflict` row with
`politica='seq_tiebreak'` for operator review
**And** `_read_local_seq` MUST be dispatched by `spec.seq_strategy` per
this table:

| `seq_strategy` | Query |
|---|---|
| `seq_via_datos` | `SELECT MAX((datos->>'seq')::bigint) FROM prod.sync_queue WHERE tabla = :name AND uuid_registro = :row_uuid AND uuid_sucursal IS NOT DISTINCT FROM :branch_uuid` |
| `max_timestamp_evento` | `SELECT MAX(timestamp_evento) FROM {table} WHERE uuid = :row_uuid` |
| `max_created_at` | `SELECT MAX(created_at) FROM {table} WHERE uuid = :row_uuid` |
| `none` | Return `None` immediately (for `validacion_evento` — the sole `never_propagated` entry — and `LocalOnlyCatalog` entries) |

**And** the stub at `conflict_resolver.py::_read_local_seq` MUST be
removed; every `[V]` conflict without a natural key MUST now produce a
concrete seq.

### REQ-MOT-010: Conflict resolution for entries with a non-empty `depends_on` (D18, generalizes D7)
**Given** a remote row for any entry with `depends_on != ()`
(`L_E`, `L_W`, or `A` per REQ-MOT-007)
**When** `resolve_conflict` runs
**Then** the motor MUST invoke `spec.hook_validate_parent(parent_local,
payload)` (`hooks.md` `ValidateParentChain`) for every declared parent,
resolving self-referential parents through `spec.parent_fk_column`
**And** if the hook returns `parent_valid=False` for any declared parent,
the motor MUST return `ConflictResolution.RETRY(parent_missing=True)` so
the row is buffered in `prod.sync_queue_lw_buffer`
(`cutover-migration.md` REQ-CUT-010) — it MUST NOT be re-enqueued into
`sync_queue` for this reason (D18 single-escalation-path rule)
**And** if the hook returns `parent_valid=True` for every declared parent,
the motor MUST return `ConflictResolution.APPLIED`.

### REQ-MOT-011: `apply_row` honors `PARKOS_SYNC_ENGINE` feature flag (D12, D22)
**Given** the runtime env `PARKOS_SYNC_ENGINE`
**When** `apply_row` is called
**Then** the motor MUST re-read the env value at each invocation (workers
re-read every 60s, no restart required)
**And** the enum MUST be exactly `legacy | catalog_admin | catalog_dian |
catalog | catalog_branch` (D22) — this is the single ratified enum; the
withdrawn `design.md`/`adr/001` variant
(`legacy | catalog_read | catalog_dual | catalog_only | catalog_lite`)
MUST NOT appear anywhere in this artifact
**And** the behavior MUST be:

| `PARKOS_SYNC_ENGINE` | `apply_row` behavior |
|---|---|
| `legacy` | Dispatch to the legacy applier (current behavior, no catalog consulted). Kill switch for rollback. |
| `catalog_admin` | Apply via catalog, but only for `api_admin` endpoints (read-side). |
| `catalog_dian` | Apply via catalog, but only for the DIAN dispatcher. |
| `catalog` (default after cloud cutover) | Apply via catalog for all 46 `SYNC_CATALOG` entries. |
| `catalog_branch` | Apply via catalog for branch-side workers (branch cutover). |

**And** setting `PARKOS_SYNC_ENGINE=legacy` MUST be the only kill switch;
no code restart is required.

### REQ-MOT-012: `apply_row` raises `ImportError` only for `validacion_evento` on branch (R6)
**Given** an entry with `role_required="cloud"` (only `validacion_evento`,
per `sync-catalog.md` REQ-CAT-010)
**When** a branch process (env `PARKOS_DEPLOY=branch`) imports the spec's
`model_cls` or invokes `apply_row` with this spec
**Then** `parkos_core/sync/role_guard.py::assert_role("branch")` MUST raise
`ImportError` at module import time with a message that includes the
table name and "cloud_only"
**And** the same guard MUST NOT raise for `envio_dian`
(`role_required="both"`, `originating_role="cloud"`) — the branch
legitimately holds and reads `envio_dian` rows to display the DIAN
acknowledgement
**And** the integration test `tests/integration/test_role_guard.py` MUST
assert both cases: `validacion_evento` raises `ImportError` from a
branch-flavored session, and `envio_dian` imports and applies cleanly
from the same session.

> **Amended — scope narrowed from `{envio_dian, validacion_evento}` to
> `{validacion_evento}`.** The prior REQ-MOT-012 raised `ImportError` for
> both tables, which would have crashed branch boot on `envio_dian` — a
> table the branch must legitimately read (see `sync-catalog.md`
> REQ-CAT-010 for the corrected `role_required`/`originating_role` pair).

### REQ-MOT-013: Grace-window check for `[L-S]`
**Given** a remote `[L-S]` row (`login` or `sesion`) with `timestamp_evento`
**When** `resolve_conflict` runs
**Then** the motor MUST compute
`grace_age = NOW() - remote.timestamp_evento`
**And** if `grace_age <= 24h` (configurable via `PARKOS_SESSION_GRACE_HOURS`,
default 24) the motor MUST return `ConflictResolution.APPLIED`
**And** if `grace_age > 24h` the motor MUST return
`ConflictResolution.MANUAL` (the JWT overlap window has elapsed; further
sync requires manual reconciliation).

### REQ-MOT-014: `apply_row` reads `broadcast_policy` for cloud-side emit (D5-rev, D19)
**Given** a cloud-side sync emit loop calling `apply_row` for an
outbound-to-branch row
**When** the entry's `broadcast_policy` is read
**Then** the motor MUST dispatch to:

| `broadcast_policy` | Target branches |
|---|---|
| `single_branch` | The `branch_uuid` carried on the payload |
| `all_branches` | Every branch in `sync.auto_discovery.BranchCache` |
| `all_branches_with_override` | If `uuid_sucursal IS NULL`: every branch (and the branch stores the NULL-default row); if non-NULL: only that branch (D19, `sync-catalog.md` REQ-CAT-019) |
| `subscription` | The branch resolved from the row's own `uuid_sucursal` (`subscripciones_cliente`), or **transitively** from its parent's `uuid_sucursal` when the row has none (`subscripcion_vehiculos` → `subscripciones_cliente.uuid_sucursal`) — never `all_branches`, and never a fallback (REQ-MOT-016) |

**And** the broadcast decision MUST be logged with
`{"event": "sync_broadcast", "tabla": ..., "policy": ..., "targets": N}`.

> **Amended — `subscription` no longer falls back to `all_branches`.** The
> prior REQ-MOT-014 fell back to `all_branches` with a warning for
> `subscription`, because at the time no table used that policy. The §16
> Q1 product decision ratifies `subscription` for
> `subscripciones_cliente` and `subscripcion_vehiculos`, so the fallback
> is removed and the transitive-resolution rule is specified in full
> (REQ-MOT-016). This amendment also adds the `all_branches_with_override`
> row (D19), which did not exist in the prior pass.

### REQ-MOT-015: `apply_batch` composes priority-ordered batch selection with `depends_on` topological order (D18, addendum #4)
**Given** the outbox drain selects a batch
**When** `SyncMotor.apply_batch(rows, actor_uuid=…)` is called
**Then** the batch itself MUST already have been selected by
`repo/sync_queue.py::list_pending` exactly as implemented today —
`estado='pendiente' AND (next_retry_at IS NULL OR next_retry_at <= NOW())`,
ordered `prioridad DESC, intentos ASC, created_at ASC`, `LIMIT 100`
(cap 500) — `apply_batch` MUST NOT change or replace this selection rule,
and MUST NOT drop the `intentos ASC` tiebreaker: rows with fewer prior
attempts are drained ahead of rows with more, within the same priority
level
**And**, within that selected batch, the motor MUST topologically sort
`rows` over `spec.depends_on`, excluding self-chain edges
(`sync-catalog.md` REQ-CAT-015)
**And** a cycle in the resulting graph MUST raise at import/build time, not
at apply time — a programming error, not a runtime condition (R19)
**And** the motor MUST apply each row via `apply_row` in that topological
order
**And** any row that returns `RETRY(parent_missing)` MUST go to
`prod.sync_queue_lw_buffer`, keyed on the missing `(tabla, uuid)`
**And** every child of a buffered row **within the same batch** MUST also
be buffered rather than attempted and failed — dependency ordering
prevents wasted apply attempts on rows whose parent is known to be
missing
**And** the rule applies **direction-agnostically**: on first pairing, a
branch has an empty catalog set, so the initial `cloud_to_branch`
backfill MUST also apply in topological order or every child fails
(R-D8, `cutover-migration.md`).

### REQ-MOT-016: `subscription` broadcast target resolution (§16 Q1, generalizes REQ-MOT-014)
**Given** a row for `subscripciones_cliente` or `subscripcion_vehiculos`
**When** the motor resolves the broadcast target
**Then** for `subscripciones_cliente`, the target branch MUST be the
row's own `uuid_sucursal`
**And** for `subscripcion_vehiculos`, which has no `uuid_sucursal` column,
the target branch MUST be resolved by reading the parent
`subscripciones_cliente.uuid_sucursal` — this transitive lookup MUST use
the already-validated `depends_on` parent (REQ-MOT-010), never a second
independent query
**And** the FK-closure invariant MUST hold: the selling branch is by
construction the only branch that ever receives both the parent
subscription and the junction row, so no branch receives a
`subscripcion_vehiculos` row whose `subscripciones_cliente` parent it
lacks
**And** a vehicle presenting at a non-selling branch with no local
subscription match MUST be handled per `sync-catalog.md` REQ-CAT-017
(R22) — not as a broadcast failure.

## Modified Capabilities

- `parkos_core/sync/conflict_resolver.py` — removes the 4 hardcoded
  `frozenset` constants and the stub `_read_local_seq`. Re-exports
  `ConflictResolver` as a thin shim that delegates to
  `SyncMotor.resolve_conflict` so existing callers see no API change.
- `parkos_core/sync/table_registry.py` — discarded (proposal §9.6);
  `SYNC_CATALOG[name]` lookups replace auto-discovery entirely.
- `parkos_core/jobs/sync_cloud.py` — the applier loops MUST read the
  catalog and call `SyncMotor.apply_batch` / `apply_row` /
  `verify_chain`; the legacy `emit_sync_back` loop is deleted in full
  (D1-rev) — there is no `sync_back_event` emit path to keep.
- `parkos_core/jobs/sync_sucursal.py` — the 6-step cycle MUST call
  `SyncMotor.apply_batch` for every pushed batch.
- `parkos_core/api/v1/sync_router.py` — the `/sync/events` handler MUST
  replace the trial-and-error strategy lookup with
  `SYNC_CATALOG[tabla].apply_strategy` and dispatch to `SyncMotor`; the
  uncommitted hunks in the working tree are not built upon (proposal
  §9.6).

## Out of Scope

- **Hash chain verifier dual-walk performance** (R11) — covered
  functionally by REQ-MOT-006; caching the per-tenant chain head is a
  design-phase optimization in `sdd-design`.
- **Hook callable implementations** (`IdentityReconciler`,
  `ValidateParentChain`, `PlateChangeCascade`, `SubscriptionLifecycle`,
  `BiTemporalCompensation`, chain-extend hooks) — covered by `hooks.md`.
- **Reverse migration** — covered by `cutover-migration.md`.
- **Observability emission** — `apply_row` emits structured logs and
  counters via the `hook_post_insert` path; metric definitions live in
  `operations.md`.
- **`factura_electronica`'s own retry/backoff curve and the
  sequential-numbering integrity requirement** — this is a DIAN-flow
  concern tied to D1-rev's branch-local numbering, not a generic
  `SyncMotor` retry policy; covered by `cutover-migration.md`
  REQ-CUT-014.
- **`fn_enqueue_sync_catalog` trigger DDL** — the motor reads `priority`
  from the catalog entry as a tie-break only (REQ-CAT-012); the trigger
  itself is a migration artifact covered by `cutover-migration.md`.
- **WebSocket transport** — HTTP polling only.
