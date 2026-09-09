# Spec: `cutover-migration`

## Purpose

Define the cutover and rollback contract — how the cloud and branches
transition from the legacy `fn_enqueue_sync` + `frozenset` sync surface to
the new catalog-driven `SyncMotor`, in 6 cloud-first stages with a 14-day
dual-protocol grace period (D11), a single-feature-flag kill switch (D12),
cloud-first staged cutover (D13, amended), a generalized dependency
buffer for out-of-order events (D18, generalizes D15), a per-branch
catalog-backfill gate before branch cutover (R-D8), a UI degraded mode for
network partitions that has shrunk in scope (D16, amended), and the
branch-local DIAN numbering integrity contract that replaces the withdrawn
`sync_back_event` return channel (D1-rev).

## Requirements

### REQ-CUT-001: `PARKOS_SYNC_ENGINE` feature flag (D12, D22)
**Given** the runtime env `PARKOS_SYNC_ENGINE` is read by the worker
entrypoints
**When** workers boot (cloud `job_sync_cloud`, branch `job_sync_sucursal`,
API `api_admin` and `api_sucursal`)
**Then** the flag MUST accept exactly the ratified D22 enum:
`legacy` (default until stage 1), `catalog_admin` (stage 1, `api_admin`
reads catalog but applies legacy), `catalog_dian` (stage 2, DIAN
dispatcher), `catalog` (stage 3, `job_sync_cloud`; also the default after
stage 5 cleanup), `catalog_branch` (stage 4, branch cutover)
**And** this MUST be the same enum used by `sync-motor.md` REQ-MOT-011 —
the withdrawn `design.md`/`adr/001` variant
(`legacy | catalog_read | catalog_dual | catalog_only | catalog_lite`)
MUST NOT appear anywhere in this artifact
**And** workers MUST re-read the env value every 60 seconds so a rollback
does NOT require a container restart (the only kill switch).

### REQ-CUT-002: Drain check before stage 4 (R2)
**Given** the cutover is about to advance from stage 3 to stage 4 (branch
cutover)
**When** the operator (or automated gate) issues the SQL
```sql
SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente';
```
**Then** the count MUST be 0 within `2 * poll_interval_s` (default
`poll_interval_s=5`, so 10s) before stage 4 advances
**And** if the count is non-zero, the cutover MUST halt and the operator
MUST see a structured alert
**And** the drain check MUST run from `openspec/scripts/check_drain.py`
(`operations.md` REQ-OPS-013) so it is reproducible in CI.

### REQ-CUT-003: Dual-protocol grace period of 14 days (D11, R-D6)
**Given** the cloud reaches stage 3 (`PARKOS_SYNC_ENGINE=catalog`)
**When** a branch first calls `GET /sync/hello` against the cloud
**Then** the response MUST include:
```json
{
  "protocol_version": "catalog",
  "min_branch_version": "1.5.0",
  "grace_until": "2026-10-08T00:00:00Z"
}
```
**And** the cloud MUST continue serving the legacy `/sync/push` and
`/sync/pull` endpoints for 14 calendar days
**And** the branch auto-detects: if `protocol_version == "legacy"` →
legacy applier; if `"catalog"` and `version >= min_branch_version` →
catalog applier
**And** after 14 days, a follow-up `PR-remove-legacy` (NOT in this change)
removes the legacy endpoints.

### REQ-CUT-004: `/sync/hello` response shape (D11)
**Given** any branch calls `GET /sync/hello`
**When** the cloud responds
**Then** the JSON body MUST contain:
`protocol_version: "legacy" | "catalog"`,
`min_branch_version: string` (semver, branches below this use legacy),
`grace_until: ISO-8601 datetime` (null when `protocol_version == "legacy"`),
`catalog_revision: string` (git SHA of the catalog at the time of the
deployment, so branches can detect catalog updates during the grace period)
**And** the response MUST be cached by the branch for `ttl=300s` to avoid
hammering the cloud.

### REQ-CUT-005: Branch auto-detects protocol from `/sync/hello` (D11)
**Given** the branch receives a `/sync/hello` response
**When** the branch worker decides which applier to use
**Then** the decision MUST be:

| Condition | Applier |
|---|---|
| `protocol_version == "legacy"` | Legacy applier (current code) |
| `protocol_version == "catalog"` AND `branch_version >= min_branch_version` | `SyncMotor` with `PARKOS_SYNC_ENGINE=catalog_branch` |
| `protocol_version == "catalog"` AND `branch_version < min_branch_version` | Legacy applier + a `WARN catalog_too_new` log |
| HTTP error / timeout | Legacy applier (fail-safe to avoid blocking branch operations) |

### REQ-CUT-006: 6-stage cloud-first cutover with concrete gate criteria (D13 amended, R-D7, R-D8)
**Given** the cutover follows the stages defined in the amended proposal §11
**When** the operator evaluates whether to advance to the next stage
**Then** the gate criteria MUST be continuously met for 24 hours:

| Stage | Service | Flag | Gate (24h continuous) |
|---|---|---|---|
| **0 — Catalog skeleton** | All | `legacy` | CI green; catalog drift check green (`operations.md` REQ-OPS-003); `depends_on`↔ER rule green; DAG assertion green; reverse dry-run OK (REQ-CUT-009). |
| **1 — `api_admin` reads catalog, applies legacy** | `api_admin` | `catalog_admin` | 0 `ImportError`; 0 5xx on `/sync/events`; chain verifier 0 anomalies. |
| **2 — DIAN path** | `dian/cloud/dispatcher` | `catalog_dian` | Zero rows with `operacion='sync_back_event'` anywhere; a branch-emitted `factura_electronica` is range-validated against its `resolucion_facturacion` and forwarded to the provider; `envio_dian` (`cufe`, `estado`) applies at the originating branch; reprint remains available at the branch throughout, including with the cloud unreachable (REQ-CUT-014). |
| **3 — `job_sync_cloud`** | `jobs/sync_cloud` (3 loops) | `catalog` | Backlog < 1000 rows; conflict rate < 0.5%; `sync_dependency_wait` draining (no row past TTL); chain verifier 0 anomalies; `sync_apply_total` emits per table. |
| **4 — Branch cutover** | branch workers | `catalog_branch` | **R-D8**: `catalog_backfill_complete{uuid_sucursal} = 1` for the branch before it advances; every `cloud_to_branch` entry applied in topological order with zero unresolved declared parents; offline login, pricing, and invoice emission verified with the cloud unreachable. |
| **5 — Cleanup** | All | flag default = `catalog` | Legacy `fn_enqueue_sync` dropped from replicated tables (`fn_enqueue_sync_catalog` is the source, REQ-CUT-015); infra triggers dropped from `sync_log`/`sync_conflict` (D21, `operations.md` REQ-OPS-014); rollback switch tested; drain check < 60s. |

**And** branch cutover (stage 4) MUST follow the cloud's stage-5 stability
by a 7-day stabilization window (D3, REQ-CUT-007) before it begins.

> **Amended — see D13.** The prior REQ-CUT-006 defined only 5 stages
> (0-4), collapsing branch cutover and cleanup into a single "4 —
> Cleanup" stage and never assigning the `catalog_branch` flag value to
> any stage — an omission that left the D22 enum's fifth member
> unreachable from the stage table. This amendment restores the
> 6-stage structure from the amended proposal §11, gives branch cutover
> its own stage 4 with the R-D8 backfill gate (the direct control for the
> failure that motivated this whole amendment), and moves the stage-2 DIAN
> gate criteria to match D1-rev (no more `numero_oficial` assignment
> criterion; the branch-local numbering + range-validation criteria
> replace it).

### REQ-CUT-007: Branch follows cloud by 7 days, gated by R-D8 (D3, R-D8)
**Given** the cloud completes stage 5
**When** the operator announces the cloud cutover is stable
**Then** branches MUST begin their own stage-4 cutover after a 7-day
stabilization window
**And** the same gate criteria apply (REQ-CUT-006 stage 4), with
`catalog_branch` as the flag value
**And** a branch MUST NOT advance past its own initial backfill until
`catalog_backfill_complete{uuid_sucursal} = 1` — i.e. every
`cloud_to_branch` `SYNC_CATALOG` entry has applied its initial topological
backfill for that branch (R-D8)
**And** the `branch-prerelease` chain MUST follow the
`create-49-table-apis` PR9 precedent (feature-branch-chain).

### REQ-CUT-008: Workers re-read `PARKOS_SYNC_ENGINE` every 60s (D12)
**Given** the worker is in steady-state operation
**When** the operator changes `PARKOS_SYNC_ENGINE` in the environment
(without restart)
**Then** the worker MUST pick up the new value within 60 seconds on the
next sleep tick
**And** the worker MUST log the flag transition as
`{"event": "sync_engine_flag_change", "old": ..., "new": ..., "ts": ...}`
so the audit trail is complete
**And** setting the flag to `legacy` MUST drain the in-flight batch
(marks `estado='exitoso'` for completed rows; abandons pending rows back
to `pendiente` for the legacy applier to pick up next cycle).

### REQ-CUT-009: Reverse migration script (D12)
**Given** the operator decides to roll back
**When** the operator runs `openspec/scripts/reverse_sync_overhaul.py`
**Then** the script MUST execute these 6 steps in order and report after
each:

1. **Set `PARKOS_SYNC_ENGINE=legacy`** on all worker processes (env
   update; no restart). Verify via `GET /sync/hello` returning
   `protocol_version=legacy`.
2. **Wait for drain** — poll
   `SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'`
   every 5s; abort if 0 not reached within 5 minutes.
3. **Drain `prod.sync_queue_lw_buffer`** — every buffered row re-enters
   the legacy path (the legacy applier does not honor `depends_on`; this
   is an accepted, documented rollback degradation, not a defect).
4. **Disable new endpoints** — `api_admin /sync/events v2` and
   `/sync/hello` return 404; legacy `/sync/push` and `/sync/pull`
   remain.
5. **Restore legacy applier paths** in `sync_router.py` (rollback of the
   catalog-cutover changes — only the routes that switch to the catalog
   applier).
6. **Verify chain verifier is still green** — invoke
   `job_sync_cloud._hash_chain_verifier_loop` once; assert 0 anomalies.

**And** the script MUST be idempotent (running it twice is a no-op after
the first run completes)
**And** the script MUST support `--dry-run` mode (`operations.md`
REQ-OPS-012)
**And** the `fn_enqueue_sync_catalog` triggers added for the 18
previously-untriggered `[V]` tables (REQ-CUT-015) MUST be **left in
place** on rollback — removing them would re-open the missing-catalog gap
this change exists to close; the legacy applier tolerates the extra
`sync_queue` rows it produces.

> **Amended — new step 3.** The prior REQ-CUT-009 had 5 steps and did not
> account for `prod.sync_queue_lw_buffer` (a table the prior pass's D15
> buffer design did not generalize the way D18 does). The buffer-drain
> step is inserted so a rollback does not strand dependency-deferred rows.

### REQ-CUT-010: Generalized dependency buffer, `prod.sync_queue_lw_buffer` (D18, generalizes D15)
**Given** the cloud or branch worker receives a row (any audit class with
a non-empty `depends_on`, per `sync-catalog.md` REQ-CAT-015 — no longer
limited to `[L-W]`) whose declared parent does not exist locally
**When** `SyncMotor.apply_row` / `resolve_conflict` returns
`RETRY(parent_missing=True)` (per `hooks.md` REQ-HOOK-013,
`sync-motor.md` REQ-MOT-010)
**Then** the worker MUST place the row in the buffer keyed by
`(tabla_padre, uuid_padre)` — the generic name for "the missing parent's
table and uuid", not only the `[L-W]` self-chain column
**And** when the parent row arrives, the buffer MUST release all
dependent rows in the order they were buffered (strict causal order, FIFO
within a parent)
**And** the buffer MUST hold each row for a maximum TTL of 24 hours
**And** the buffer MUST be persisted in `prod.sync_queue_lw_buffer`, a new
`[A]` table added by **migration `0009_add_sync_queue_lw_buffer.py`**
(NOT `0001_initial_schema.py`, which is already applied in production and
MUST NOT be edited) — it is NOT in the catalog because it is operational
state (`sync-catalog.md` REQ-CAT-006)
**And**, per the project canon for `[A]` tables, the same migration MUST
include `REVOKE UPDATE, DELETE ON prod.sync_queue_lw_buffer FROM app_user`
and a `BEFORE UPDATE OR DELETE` trigger raising an exception, mirroring the
`prod.bitacora` pattern
**And** the migration MUST partition the table via
`pg_partman.create_parent(p_parent_table := 'prod.sync_queue_lw_buffer',
p_control := 'buffered_at', p_type := 'range', p_interval := '1 day',
p_premake := 3)`
**And** the table's columns MUST be
`(uuid, uuid_sucursal, tabla, uuid_registro, tabla_padre, uuid_padre,
datos JSONB, estado, buffered_at, expires_at)` — covering any declared
parent, not only `uuid_padre`
**And** the migration MUST create a partial index on
`(tabla_padre, uuid_padre) WHERE estado='pendiente'` and an index on
`(expires_at)` to support the sweep.

> **Amended — see D18.** The prior REQ-CUT-010 scoped the buffer to
> `[L-W]` rows keyed strictly by `uuid_padre`, and its "Modified
> Capabilities" section placed the migration inside
> `0001_initial_schema.py`. Both are corrected: the buffer now serves any
> audit class with a declared parent, and the migration is a new revision
> (proposal §9.2 explicitly calls out and corrects this exact
> inconsistency between the prior pass's spec and its design/tasks).

### REQ-CUT-011: Orphan dependency chain → `alerta` after 24h TTL (D18, R13)
**Given** a row has been in `prod.sync_queue_lw_buffer` for 24 hours
without its declared parent arriving
**When** the buffer sweep runs (every hour via
`job_sync_cloud._lw_buffer_sweep`)
**Then** the sweep MUST write an `alerta` row with
`tipo_alerta='orphan_workflow_chain'`, `uuid_registro=<orphan_uuid>`,
`tabla=<buffered_table>`, `uuid_sucursal=<branch_uuid>`,
`datos->>'buffered_at'=<timestamp>`,
`datos->>'buffer_age_seconds'=N`
**And** the orphan row MUST be marked `estado='fallido'` in the buffer
with `ultimo_error='parent_missing_timeout'`
**And** `tipo_alerta='orphan_workflow_chain'` MUST be seeded in
`prod.alert_types` by migration `0010_add_alert_types.py`
(`sync-catalog.md` REQ-CAT-021)
**And** the operator MUST see a Grafana alert (`operations.md`
REQ-OPS-008) when `orphan_workflow_chain` rate exceeds 1 per hour per
branch
**And** this is the single escalation path (`hooks.md` REQ-HOOK-013) —
`sync_queue` is never re-enqueued for this condition.

### REQ-CUT-012: Network partition → buffer locally + degraded mode (D16 amended)
**Given** the branch cannot reach the cloud (`/sync/hello` returns
HTTP error / timeout for 3 consecutive attempts)
**When** the branch worker enters partition state
**Then** the worker MUST continue local `[V]`/`[A]`/`[L-S]` writes (no
blocking on cloud connectivity)
**And** the worker MUST continue local `[L-E]`/`[L-W]` writes, **including
`factura_electronica` emission and numbering, and `reimpresion_ticket`**
— per D1-rev, both are branch-local operations with no cloud round-trip
dependency (REQ-CUT-014); the worker MUST enqueue them into the local
`sync_queue` as usual, flushed when connectivity returns
**And** the branch MUST surface a UI banner (amarillo) via the
`/sync/health` endpoint returning
`{"status":"degraded","partitioned":true,"last_cloud_contact":...}`
**And** the worker MUST NOT attempt rollback to `legacy` automatically
(the partition is local; the catalog path is the correct applier).

> **Amended — see D16.** The prior REQ-CUT-012 was silent on whether
> `factura_electronica` emission continued during a partition, deferring
> to the superseded D1's cloud-dependent numbering. D1-rev makes the
> answer explicit: emission and numbering are branch-local and unaffected
> by connectivity.

### REQ-CUT-013: Degraded mode narrows to DIAN acknowledgement visibility only (D16 amended)
**Given** the branch is in partition state
**When** the operator UI (Cajero / Kiosko / Admin-Op) queries the local
API
**Then** the API MUST return
`{"degraded_features": ["factura_electronica_dian_ack_pending"]}`
**And** the UI MUST show a pending-acknowledgement indicator on
`factura_electronica` — the DIAN `cufe`/`estado` fields (sourced from
`envio_dian`, D1-rev) are not yet available — while the document itself
is presented as **final**, not preliminary
**And** the UI MUST NOT hide or disable reprinting — reprint is always
available, online or offline (there is no `origen='auto'`/`origen='manual'`
distinction to gate on; `hooks.md` REQ-HOOK-011)
**And** the UI MUST NOT show a `numero_temporal` or a `preliminar` badge —
neither exists; the document is final at emission
**And** local writes MUST continue for both `reimpresion_ticket` and
`factura_electronica` without restriction.

> **Superseded — see D1-rev, D16 amended.** The prior REQ-CUT-013 returned
> `degraded_features: ["reimpresion_ticket_auto",
> "factura_electronica_realtime_ack"]`, hid the "Auto reprint" button
> (leaving only manual reprint available during partition), and showed a
> `numero_temporal` with a `preliminar` badge while waiting for a DIAN
> ack. All three behaviors depended on the withdrawn `sync_back_event`
> design. Under D1-rev the degraded surface shrinks to exactly one
> indicator: DIAN acknowledgement visibility. This is the corrected
> `AGENTS.md` canon the proposal requires at lines 234-235 (proposal
> §9.5) — the frontend implementation itself is a separate `sdd-new`
> change; this requirement defines the API contract only.

### REQ-CUT-014: DIAN numbering integrity and its own retry/backoff curve (D1-rev, addendum #1, #3)
**Given** the branch emits `factura_electronica` using its own
`resolucion_facturacion` and assigns `consecutivo` within that
resolution's `rango_desde`/`rango_hasta`
**When** the assignment step runs, including under retry or offline
conditions
**Then** the assignment MUST be **transactional and idempotent per source
event** — numbering is strictly sequential per branch resolution, with no
gaps: a retry MUST NEVER generate a `consecutivo`, discard it, and
generate a new one; if the transaction that would persist the assigned
number fails, no number is considered consumed
**And** the cloud MUST validate, on receipt, that the branch-assigned
`consecutivo` falls within the resolution's authorized
`rango_desde`/`rango_hasta` range, and MUST reject any document outside
that range
**And** range exhaustion (no remaining `consecutivo` in the authorized
range) MUST raise an `alerta` with a generic `tipo_alerta='fe_numbering_exhausted'`
— never the literal name of the third-party DIAN provider (addendum #5)
**And** the branch-to-provider round trip (an `envio_dian` self-chain
transition per attempt, `uuid_envio_padre`) MUST follow its own backoff
curve, distinct from the general `sync_queue` backoff
(`BACKOFF_SCHEDULE` in `repo/sync_queue.py`, 1s...300s max,
`FALLIDO_PERMANENTE` after 24h unprocessed): **1 minute → 5 minutes → 15
minutes → 1 hour → 6 hours → 24 hours**, transitioning to a terminal
`estado='rechazado'`-equivalent `ERROR` outcome and raising
`alerta tipo_alerta='fe_provider_error'` after 6 failed attempts
**And** `revocacion_factura` submissions to the provider MUST reuse this
same curve — both `envio_dian` and `revocacion_factura` are retry
attempts against the same DIAN provider integration and dispatcher code
path, and the business docs specify no distinct curve for revocation; a
second, invented curve would add inconsistency without a stated rule to
justify it
**And** `factura_electronica` itself has no independent retry loop — its
"own" curve, as stated in the business docs, IS the `envio_dian` retry
sequence carried out on its behalf; `factura_electronica`'s lifecycle
(`ER: V_FE_ESTADO_DIAN`) is a **derived view** over `envio_dian` and
`revocacion_factura`, never a stored retry counter on
`factura_electronica` itself.

### REQ-CUT-015: `/sync/events` per-row wire status `retry_parent_missing` (D18)
**Given** a `/sync/events` push batch that includes a row whose declared
`depends_on` parent (`sync-catalog.md` REQ-CAT-015) is not yet present on
the receiving side
**When** the receiver's `SyncMotor.apply_row` / `resolve_conflict`
returns `RETRY(parent_missing=True)` (`sync-motor.md` REQ-MOT-010,
`hooks.md` REQ-HOOK-013) and the receiver buffers the row in
`prod.sync_queue_lw_buffer` (REQ-CUT-010)
**Then** the `/sync/events` response MUST report that row's per-row status
as the literal wire value `retry_parent_missing` — never a generic
failure status, never `applied`, and never a silently dropped row
**And** the pushing side MUST treat `retry_parent_missing` as **delivered**
: it MUST call `repo.sync_queue.mark_success` on its local `sync_queue`
row for this table/uuid, and MUST NOT increment `intentos` or set
`next_retry_at` — ownership of the wait has transferred to the receiver's
dependency buffer, and the pushing side's transport-retry budget MUST NOT
be spent on a condition the pushing side did not cause and cannot resolve
**And** the full per-row wire status vocabulary and the pushing side's
corresponding `sync_queue` action are defined once, in
`sync-motor.md` REQ-MOT-005 — this requirement fixes only the wire name
(`retry_parent_missing`) and the receiving-side trigger condition
(a missing declared parent); it does not redefine the buffer mechanism
itself.

## Modified Capabilities

- `parkos_core/api/v1/sync_router.py` — the `/sync/events` handler emits
  the per-row `retry_parent_missing` wire status (REQ-CUT-015).
- `infra/docker/entrypoint.sh` — adds the `--sync-engine=${PARKOS_SYNC_ENGINE}`
  arg passthrough and the periodic 60s re-read (D12, REQ-CUT-008).
- `infra/deploy/docker-compose.cloud.yml` and
  `infra/deploy/docker-compose.branch.yml` — adds `PARKOS_SYNC_ENGINE`
  env (default `legacy` for cloud until stage 3; `catalog_branch` for
  branches after stage 4).
- `backend/packages/parkos_core/migrations/versions/0009_add_sync_queue_lw_buffer.py`
  (new) — `prod.sync_queue_lw_buffer` `[A]` table + `REVOKE` + trigger +
  `pg_partman` daily partitioning (REQ-CUT-010).
- `backend/packages/parkos_core/migrations/versions/0010_add_alert_types.py`
  (new) — `prod.alert_types` registry + `REVOKE` + trigger, seeded on
  both cloud and branch (`sync-catalog.md` REQ-CAT-021).
- `backend/packages/parkos_core/api/v1/sync_router.py::sync_hello` —
  endpoint returning the JSON shape in REQ-CUT-004.
- `infra/deploy/.gitignore` — adds `infra/deploy/.env.*` before any task
  stages files under `infra/deploy/` (`infra/deploy/.env.cloud` is
  currently untracked and not ignored).
- `modelo_datos_er.mmd` — gains the `sync_queue_lw_buffer` and
  `alert_types` `[A]` blocks (`sync-catalog.md` Modified Capabilities);
  `check_schema_match.py` and `check_table_counts.py` gate on this file
  being amended.

## Out of Scope

- **`fn_enqueue_sync_catalog` trigger DDL for the 18 previously-untriggered
  `[V]` tables** (migration `0011_add_catalog_triggers.py`) and **dropping
  the infra triggers from `sync_log`/`sync_conflict`** (migration
  `0012_drop_infra_triggers.py`, D21) — the requirement that these
  triggers exist and that the catalog reads them is covered by
  `sync-catalog.md` REQ-CAT-004/REQ-CAT-012; `operations.md` REQ-OPS-014
  covers the runtime skip-not-fail guard for infra tables.
- **`AGENTS.md` canon corrections** (lines 112, 113, 205-207, 208,
  234-235, 255) — required by D1-rev (proposal §9.5) but not an editable
  target of this proposal phase; a task in `tasks.md` applies the exact
  edits.
- **Frontend UI implementation** — the API contract (REQ-CUT-013) is
  defined here; the React component is a separate `sdd-new` change.
- **Cross-region HA** — `job_sync_cloud` runs as `replicas=1`; HA with
  Postgres advisory locks per `uuid_sucursal` is deferred to v2.
- **Removing legacy endpoints after grace period** — a follow-up
  `PR-remove-legacy` change ships after day 14 of stage 3.
- **Cloud-side verifier performance optimization** — `sync-motor.md`
  REQ-MOT-006 walks the chain; caching the per-tenant head is a
  design-phase optimization.
- **WebSocket transport** — HTTP polling only (AGENTS.md §"Sync").
