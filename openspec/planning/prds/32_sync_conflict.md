# PRD: sync_conflict (T32)

> Snapshot of every sync conflict detected between branch and cloud. Append-only; admin resolves manually via the conflict workflow. Retention: 1 year post-resolution. Distinct from `sync_log.conflictos` (which is the per-cycle aggregate count); this is the per-conflict detail with both sides' data.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[A]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.sync_conflict`
- **SQL name**: `sync_conflict` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth with **operational UPDATE exception** on `resolucion` field
- **Retention**: 1 year post-resolution (i.e., `fecha_retencion_hasta = resolved_at + 1 year` for resolved rows; unresolvable rows kept indefinitely)
- **Origin**: F1 (schema + REVOKE + trigger + operational UPDATE exception on `resolucion`) + IT-1+ (writes from sync workers on detection) + IT-12 (admin resolution endpoint)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `tabla` + `uuid_registro` form a polymorphic pointer (NO DB FK; application validates the table+uuid combination). The `tabla` column is constrained by ENUM (one of: `ingreso`, `facturas`, `factura_electronica`, `log_transaccional`, `tarifas_sucursal`, `permisos_usuario`, etc. — the full set of propagated tables).
- `datos_local` is the JSON snapshot received from the branch (cloud-side mirror of branch state at push time).
- `datos_cloud` is the JSON snapshot of the cloud's existing row (if any) at detection time.
- Travel: branch-origin conflicts NEVER exist (the conflict is detected CLOUD-SIDE when receiving a branch push); cloud-origin conflicts are cloud-only. `sync_conflict` rows do NOT propagate via sync.

## 3. SOLID Atomic Breakdown
- **S**: "one detected conflict snapshot" — INSERT in the same TX as the receiver's conflict detection.
- **O**: per-table conflict policy configurable via `empresa` or `configuracion_tolerancias` (sprint 5); new `tabla` enum values added as new tables become sync-able.
- **I**: sync worker (writer — `sync_conflict_writer.py::record_conflict(...)`); admin API (read + UPDATE on `resolucion` only); `web_admin/ConflictResolutionPanel` (UI for resolution).
- **D**: `parkos_core/sync/conflict_writer.py::record_conflict(uuid_sucursal, tabla, uuid_registro, datos_local, datos_cloud, politica)` — the SOLE writer. Idempotent on (uuid_registro, operacion): re-pushes with the same conflict DON'T create duplicate rows (`ON CONFLICT (uuid_registro, tabla) WHERE resolucion='pendiente' DO NOTHING`).
- **Atomic**: INSERT (detection); UPDATE on `resolucion` only (resolution). REVOKE UPDATE on all other columns; `BEFORE UPDATE` trigger checks `OLD.resolucion` and ONLY allows UPDATE if changing `resolucion` to a valid value (`'manual'`, `'manual-cloud'`, `'manual-branch'`, `'auto-cloud-wins'`, `'auto-branch-wins'`, `'auto-timestamp'`).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, conflicts die |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `log_transaccional.uuid_referencia` (polymorphic) | n/a | 0..1 | admin resolution writes a log row with `uuid_referencia=$sync_conflict.uuid` for traceability |
| `alerta.uuid_origen_conflict` (polymorphic — sprint 5 column) | n/a | 0..1 | `alerta tipo_alerta='sync_conflict_manual'` references the conflict UUID |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `conflict_writer.py::record_conflict()` per detection |
| UPDATE on `resolucion` | YES | Special `BEFORE UPDATE` trigger allows ONLY this column |
| UPDATE on other columns | NO | Trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | REVOKE + same trigger; rows preserved for forensic audit |

**Special rules**:
- **Operational UPDATE exception**: ONLY `resolucion` is mutable (and `resolved_by` and `resolved_at` are derived/written together in the same UPDATE statement).
- **Conflict policy enforcement**: per `tabla_afectada` and the table's enforcement level (`[V]`/`[L-E]`/`[L-W]`/`[A]`/`[L-S]`), the conflict policy is applied at write time:
  - `[V]` projection: `politica='manual'` (always). Reason: state conflicts require human judgment (e.g., admin changed tarifa while branch was offline with a factura referencing the old tarifa).
  - `[L-E]` event: `politica='append'` (no conflict possible — events are append-only; branch-origin events that don't conflict with cloud-only events are merged; identical UUIDs with different data are flagged `politica='manual'`).
  - `[L-W]` workflow: `politica='append'` (workflow chains are local until replicated; conflicts arise only if both sides appended with different timestamps — apply `auto-timestamp`).
  - `[A]` source-of-truth: `politica='append'` (same UUID with different data should never happen for `[A]` — if it does, it's a critical incident, flagged `politica='manual'`).
  - `[L-S]` session: `politica='manual'` (close events have business meaning; conflicting close states need human review).
- **Retention**: `fecha_retencion_hasta = COALESCE(resolved_at, NOW()) + INTERVAL '1 year'`. Unresolved rows: no automatic purging (admin must resolve or explicitly archive).
- **JSON storage**: `datos_local` and `datos_cloud` are JSONB; total size per row may be 10–100KB for tables with many columns (e.g., `log_transaccional.datos_nuevos`).

## 6. CodeGraph Dependencies
- `parkos_core/sync/conflict_writer.py::record_conflict()` (sole writer on detection).
- `job_sync_cloud/drain_inbox` → calls `conflict_writer.record_conflict(...)` on hash mismatch or UUID collision.
- `parkos_core/sync/conflict_resolver.py::resolve(uuid, resolucion, resolved_by, datos_merged=null)` (updates `resolucion` field).
- `api_admin/routers/sync-conflict.py::GET /sync-conflict` (filterable, paginated).
- `api_admin/routers/sync-conflict.py::GET /sync-conflict/{uuid}` (single conflict detail with `datos_local` vs `datos_cloud` diff view).
- `api_admin/routers/sync-conflict.py::POST /sync-conflict/{uuid}/resolve` (manual resolution).
- `web_admin/SyncMonitor/Conflictos` (list view, filterable by `estado`='pendiente', `politica`, `tabla`).
- `web_admin/SyncMonitor/Conflictos/{uuid}/DiffView` (side-by-side diff UI).
- `web_admin/SyncMonitor/Conflictos/{uuid}/Resolve` (resolution UI: choose manual-cloud, manual-branch, manual-merge).

## 7. Use Cases enabled by this table

The `sync_conflict` table is the **per-conflict forensic record** that pairs with the per-cycle aggregate count in `sync_log.conflictos`. Every detected conflict is a snapshot of both branch (`datos_local`) and cloud (`datos_cloud`) at the moment of detection. Admin resolves manually (or auto-policy applies for `[L-E]/[L-W]/[A]`). Retention: 1 year post-resolution. **No manual operator input** for the detection flow; **admin input** for resolution.

### 7.1 Use Case: `uc.sync-conflict.branch-push-detects-conflict-on-receive`

**Actor**: sync worker (cloud `job_sync_cloud/drain_inbox`)

**Real-world action**: Cloud receives a batch from a branch via `/sync/push`. The receiver detects a conflict when the incoming item's UUID collides with an existing cloud row but the contents differ (e.g., branch updated `tarifas_sucursal` while offline and cloud received an admin update with a different value). The receiver INSERTs a `sync_conflict` row with `datos_local` (the incoming branch snapshot) and `datos_cloud` (the existing cloud row), applies the per-class policy (`[V]` → manual, `[L-E]`/`[L-W]`/`[A]` → append or auto-timestamp), and emits `alerta tipo_alerta='sync_conflict_manual'` if the policy is `manual`.

**Steps**:
1. Branch POSTs `/sync/push` with batch containing an item (e.g., `tabla='tarifas_sucursal'`, `uuid=$tarifa_uuid`, `datos=$branch_snapshot`).
2. Cloud handler opens TX per item; SELECTs the existing cloud row by `uuid_registro + tabla`.
3. If exists AND `datos_snapshot_branch != datos_snapshot_cloud`: conflict detected.
4. Determine `tabla`'s enforcement level from the catalog (e.g., `tarifas_sucursal` is `[V]` → `politica='manual'`; `log_transaccional` is `[A]` → `politica='append'` IF `datos_anteriores` matches, else `politica='manual'`).
5. Cloud handler calls `conflict_writer.record_conflict(uuid_sucursal=$branch, tabla='tarifas_sucursal', uuid_registro=$tarifa_uuid, datos_local=$branch_snapshot, datos_cloud=$cloud_snapshot, politica='manual')`.
6. `conflict_writer` INSERTs `sync_conflict` row with `resolucion='pendiente'`, `timestamp=NOW()`.
7. Cloud INSERTs `alerta` workflow chain root (`tipo_alerta='sync_conflict_manual'`, `estado='abierta'`, `uuid_sucursal=$branch`, `observaciones="tabla=tarifas_sucursal uuid=$tarifa_uuid conflict detected"`, `uuid_alerta_padre=NULL`).
8. Cloud INSERTs `log_transaccional` (`accion='sync_conflict_detected'`, `tabla_afectada='sync_conflict'`, `uuid_registro_afectado=$conflict_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={tabla, uuid_registro, politica}`).
9. Cloud marks the queue item as `estado='exitoso'` (the push succeeded; the conflict is recorded separately).
10. Cloud returns response to branch: per-item status with `conflict_detected=true` flag; branch logs but does NOT retry.
11. The cloud's existing row is NOT overwritten; the conflict is the forensic record.

**Tables touched (writes)**: `sync_conflict` (1 row per conflict), `alerta` (1 workflow root per manual conflict), `log_transaccional` (1 row per detection).
**Tables touched (reads)**: existing cloud row (the conflicting one), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `sync_conflict.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `sync_conflict.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the push that triggered the conflict.
- Cloud → branch: NO (the parametrization pull is not affected; the conflict resolution may generate a parametrization push later if admin picks `manual-cloud`).
- DIAN trigger: NO (conflicts on `tarifas_sucursal` don't trigger DIAN; conflicts on `factura_electronica` are different — handled in T03).
- Hash chain impact: YES — cloud chain extends by 1 row (`sync_conflict_detected`). Branch chain does NOT extend for this conflict (the branch pushed; conflict is cloud-side detection).

**Integration with other tables**:
- Reads from: destination table (existing cloud row), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `sync_conflict` (this row), `alerta` (workflow root), `log_transaccional` (audit).
- Cross-cutting: this is the **conflict detection** path. The matching **conflict resolution** path is use case 7.2. The `alerta` is the admin-visible notification; the `sync_conflict` is the forensic record.

### 7.2 Use Case: `uc.sync-conflict.admin-resolves-conflict-manually`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/SyncMonitor/Conflictos/{uuid}` and sees a side-by-side diff of `datos_local` vs `datos_cloud`. They choose a resolution: "Accept cloud" (discard branch), "Accept branch" (overwrite cloud), or "Manual merge" (provide a merged JSON). The backend UPDATE `sync_conflict SET resolucion=..., resolved_by=$admin_uuid, resolved_at=NOW()`, INSERTs `log_transaccional` documenting the choice, and (if `Accept branch`) generates a parametrization push to apply the change cloud-side.

**Steps**:
1. Admin opens `web_admin/SyncMonitor/Conflictos/{uuid}`.
2. Frontend GETs `api_admin /sync-conflict/{uuid}` — returns `{datos_local, datos_cloud, politica, tabla, uuid_registro, ...}`.
3. UI renders side-by-side JSON diff (key-by-key, highlighting divergent fields).
4. Admin chooses resolution:
   - **Accept cloud** (`resolucion='manual-cloud'`): branch's incoming data is discarded; no cloud-side change. Cloud row remains.
   - **Accept branch** (`resolucion='manual-branch'`): cloud row UPSERTs with branch's data; parametrization push to branch (verifies branch's state matches cloud now).
   - **Manual merge** (`resolucion='manual-merge'`): admin types the merged JSON; backend UPSERTs cloud with `datos_merged`; parametrization push.
5. Admin clicks `Resolver`. Frontend POSTs `api_admin /sync-conflict/{uuid}/resolve` with `{resolucion, datos_merged?}`.
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
7. Backend calls `conflict_resolver.resolve(uuid, resolucion, $admin_uuid, datos_merged)` — UPDATE `sync_conflict SET resolucion=..., resolved_by=..., resolved_at=NOW() WHERE uuid=...` (operational exception on `resolucion` only).
8. If `resolucion='manual-branch'` or `='manual-merge'`: backend applies the change cloud-side (UPSERT into destination table) AND `queue_processor.enqueue($tabla, $uuid_registro, $new_data)` for parametrization push.
9. INSERT `log_transaccional` (`accion='sync_conflict_resolved_manual'`, `tabla_afectada='sync_conflict'`, `uuid_registro_afectado=$conflict_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores={resolucion:'pendiente'}`, `datos_nuevos={resolucion, resolved_by, resolved_at, datos_merged?}`).
10. UPDATE `alerta` workflow chain (T41): `INSERT alerta` new chain row with `uuid_alerta_padre=$root_alerta.uuid, estado='resuelta'`, `observaciones="conflict=$uuid resolved=$resolucion"`.
11. INSERT `log_transaccional` (`accion='alerta_transicion'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alerta_new.uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `uuid_referencia=$conflict_uuid`).
12. Backend returns the updated `sync_conflict` row to frontend.

**Tables touched (writes)**: `sync_conflict` (UPDATE on `resolucion`), destination table (if `manual-branch` or `manual-merge` — UPSERT), `alerta` (workflow transition), `log_transaccional` (2 rows: resolution + alerta transition), `sync_queue` (parametrization push if cloud changed).
**Tables touched (reads)**: `sync_conflict` (current state), destination table (existing row for UPSERT), `log_transaccional` (chain anchor), `usuarios` (admin actor), `sucursal` (chain key), `alerta` (workflow root).
**FKs traversed**: `sync_conflict.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `sync_conflict.uuid` or `alerta.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `sync_conflict.uuid` for the alerta transition.

**Sync behavior**:
- Branch → cloud: NO (the resolution is cloud-side).
- Cloud → branch: YES if `manual-branch` or `manual-merge` — parametrization push within 30s propagates the resolved value.
- DIAN trigger: NO (unless the conflict was on `factura_electronica` and resolution involves revocation — separate flow, T03 use case 7.x).
- Hash chain impact: YES — cloud chain extends by 2 rows (resolution + alerta transition); branch chain extends by 1 row on parametrization receipt (if applicable).

**Integration with other tables**:
- Reads from: `sync_conflict` (the conflict row), destination table (the conflicting row), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (chain key), `alerta` (workflow root).
- Writes to: `sync_conflict` (UPDATE — operational exception), destination table (UPSERT), `alerta` (workflow transition), `log_transaccional` (audit + alerta audit), `sync_queue` (parametrization push).
- Cross-cutting: the admin resolution is the **manual** path. The `auto-cloud-wins`/`auto-branch-wins`/`auto-timestamp` paths (use case 7.3) are non-admin paths.

### 7.3 Use Case: `uc.sync-conflict.auto-resolution-by-class-policy`

**Actor**: system (sync worker)

**Real-world action**: For `[L-E]`/`[L-W]`/`[A]` conflicts where the policy is `append` or `auto-timestamp` (NOT `manual`), the cloud worker auto-resolves the conflict WITHOUT admin intervention. For `[L-E]`: the conflict is impossible by construction (events are append-only; identical UUIDs are the same event, not a conflict — if `datos_anteriores` differs, it's a hash chain break, escalated to `manual`). For `[L-W]`: conflicts arise when both sides appended different timestamps for the same workflow; `auto-timestamp` picks the later one. For `[A]`: conflicts should never happen; if they do, escalate to `manual`.

**Steps**:
1. Cloud receiver detects conflict (per use case 7.1, steps 1-4).
2. Determine policy:
   - `[V]` (e.g., `tarifas_sucursal`, `permisos_usuario`) → `politica='manual'` (use case 7.2 path).
   - `[L-E]` (e.g., `ingreso`, `facturas`, `factura_electronica`) → identical UUID with identical payload is NOT a conflict (idempotent re-push); identical UUID with different payload is a critical incident, escalate to `politica='manual'` AND emit `alerta tipo_alerta='hash_chain_break'`.
   - `[L-W]` (e.g., `anulaciones`, `reclamos`, `alerta`) → identical UUID with different payload means both sides appended to the workflow. Apply `auto-timestamp`: pick the row with later `created_at`. If that row is on the cloud, it stays. If on the branch, parametrization push to overwrite the cloud's row.
   - `[A]` (e.g., `log_transaccional`) → identical UUID with different payload is a hash chain break; escalate to `politica='manual'`. Identical UUID with identical payload is idempotent re-push, not a conflict.
   - `[L-S]` (e.g., `sesion`) → `politica='manual'` (close events have business meaning).
3. For `auto-timestamp` cases:
   a. Compare `created_at` of both rows. Pick the later one.
   b. INSERT `sync_conflict` row with `politica='auto-timestamp'`, `resolucion='auto-resolved-pending-merge'`, `datos_local=branch_later`, `datos_cloud=cloud_earlier` (or vice versa).
   c. Apply the winning row to the losing side (UPSERT cloud with branch data, or queue parametrization push).
   d. UPDATE `sync_conflict SET resolucion='auto-resolved-applied', resolved_by=SYSTEM, resolved_at=NOW()`.
   e. INSERT `log_transaccional` (`accion='sync_conflict_auto_resolved'`, `tabla_afectada='sync_conflict'`, `uuid_registro_afectado=$conflict_uuid`, `datos_nuevos={politica, winning_side, applied_at}`).
4. For `manual` escalations: per use case 7.1 (insert `sync_conflict` + `alerta` + `log_transaccional`).

**Tables touched (writes)**: `sync_conflict` (INSERT + UPDATE on `resolucion`), destination table (UPSERT if applied), `sync_queue` (parametrization push), `log_transaccional` (1 row).
**Tables touched (reads)**: existing cloud row, incoming branch row, `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: per use case 7.1 plus the destination table FKs.

**Sync behavior**:
- Branch → cloud: NO (auto-resolution is cloud-side).
- Cloud → branch: YES if branch's data wins (parametrization push to reconcile).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (`sync_conflict_auto_resolved`).

**Integration with other tables**:
- Reads from: destination table (both versions), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `sync_conflict` (INSERT + UPDATE), destination table (UPSERT if applied), `sync_queue` (parametrization push), `log_transaccional` (audit).
- Cross-cutting: this is the **policy-driven auto-resolution** path. Confirms the contract: `[V]` and `[L-S]` always manual; `[L-E]` and `[A]` manual for hash chain breaks; `[L-W]` auto-timestamp.
- **Critical invariant**: for `[A]` tables with hash chains (`log_transaccional`, `revocacion_factura`), auto-resolution is NEVER applied — any conflict on these tables is a hash chain break and must be investigated manually.

### 7.4 Use Case: `uc.sync-conflict.retention-purge-after-one-year-post-resolution`

**Actor**: system (retention worker)

**Real-world action**: A nightly retention worker scans `sync_conflict` for resolved rows where `resolved_at + 1 year < NOW()`. For each, it physically DELETEs the row (operational exception: DELETE allowed on resolved rows past retention). The DELETE is permitted because the row's forensic purpose is complete (1 year post-resolution gives admin ample time to audit and produce reports). Unresolved rows are NEVER deleted (admin must explicitly archive them).

**Steps**:
1. `workers/sync_conflict_retention/__main__.py` runs nightly at 02:30 cloud time (cron, after `hash_chain_verifier` at 02:00 and before `sync_aggregator` at 03:00).
2. SELECT rows to purge: `SELECT uuid FROM sync_conflict WHERE resolucion NOT IN ('pendiente') AND resolved_at + INTERVAL '1 year' < NOW()`.
3. For each row: physically DELETE — this is the ONE place where DELETE is permitted on `sync_conflict`. The DELETE is NOT a `rol_app` operation; it runs as a maintenance role with explicit DELETE grant. The deletion is logged via `log_transaccional` (a SEPARATE row, not the deleted one — the deleted one is gone).
4. INSERT `log_transaccional` (`accion='sync_conflict_purged'`, `tabla_afectada='sync_conflict'`, `uuid_registro_afectado=$deleted_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch_of_deleted_conflict`, `datos_anteriores={resolucion, resolved_at, tabla, uuid_registro}`, `datos_nuevos=null`).
5. SELECT unresolved rows past their `fecha_retencion_hasta`: emit `alerta tipo_alerta='conflict_aging'` for admin attention (these need manual resolution or explicit archive).

**Tables touched (writes)**: `sync_conflict` (DELETE — maintenance exception on resolved rows past retention), `log_transaccional` (1 row per purge).
**Tables touched (reads)**: `sync_conflict` (the rows to purge), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `sync_conflict.uuid_sucursal` → `sucursal.uuid` (pre-delete lookup); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is cloud-internal retention).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per purged conflict. The chain NEVER references the deleted row (since the row is gone), but the purge audit row is part of the chain for forensic completeness.

**Integration with other tables**:
- Reads from: `sync_conflict` (rows to purge), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `sync_conflict` (DELETE — maintenance exception), `log_transaccional` (purge audit), `alerta` (aging warning).
- Cross-cutting: this is the **retention lifecycle** for `sync_conflict`. Unlike `[A]` tables with `pg_partman` partitioning, `sync_conflict` uses a logical retention (timestamp-based) + manual DELETE because (a) `fecha_retencion_hasta` is per-row (depends on `resolved_at`), not per-partition, and (b) unresolved rows must never be auto-purged.
- Related: the operational UPDATE exception on `resolucion` is the only mutation path for `rol_app`. This DELETE is reserved for the maintenance role, NOT `rol_app`.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers — UPDATE exception on `resolucion`), 5 (audit constraints — REVOKE + maintenance role for DELETE), 6 (cloud admin API), 10 (cloud sync worker — receiver path), 12 (sync_queue interop, parametrization push), 13 (web_admin Conflictos UI), 20 (structlog metrics), 21 (Prometheus counters — conflicts per cycle), 24 (pytest), 28 (docker compose for retention cron), 30 (retention worker cron).

## 9. RED Tests
- (RED) INSERT `sync_conflict` from `rol_app` → success.
- (RED) UPDATE `sync_conflict SET datos_local='{}'` → `AUDIT_FIRST_INMUTABLE` (only `resolucion` is mutable).
- (RED) UPDATE `sync_conflict SET resolucion='manual-cloud'` → success.
- (RED) DELETE `sync_conflict` from `rol_app` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE from maintenance role on resolved row past retention → success; `log_transaccional` row written.
- (RED) DELETE from maintenance role on UNRESOLVED row → `AUDIT_FIRST_INMUTABLE`.
- (RED) Per-class policy enforcement: `[V]` conflict → `politica='manual'`; `[L-E]` identical UUID → NOT a conflict; `[L-E]` differing payload → `politica='manual'` + hash chain alert; `[L-W]` differing payload → `politica='auto-timestamp'`.
- (RED) Hash chain break on `log_transaccional` conflict → escalate to manual, NOT auto-resolve.
- (RED) Admin resolves conflict → `sync_conflict.resolucion` updated, `log_transaccional` row written, `alerta` workflow transitioned to `resuelta`.
- (RED) Admin resolution with `manual-branch` → parametrization push generated; branch receives the new value within 30s.
- (RED) `fecha_retencion_hasta = resolved_at + 1 year` for resolved rows; `fecha_retencion_hasta = NULL or far-future` for unresolved rows.
- (RED) Retention purge is idempotent: re-running the worker doesn't double-write `log_transaccional` for already-purged rows.
- (RED) `datos_local` and `datos_cloud` JSONB accept arbitrary shape; `tabla` is constrained by ENUM.
- (RED) Same (tabla, uuid_registro, operacion) re-push with same conflict data → no duplicate `sync_conflict` row (idempotency).
- (RED) Conflict resolution preserves both `datos_local` and `datos_cloud` for audit; only `resolucion`/`resolved_by`/`resolved_at` change.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + operational UPDATE exception on `resolucion`.
- [x] F1.x `conflict_writer.py::record_conflict()` helper.
- [ ] IT-1.x: `job_sync_cloud/drain_inbox` invokes `conflict_writer` on hash mismatch or UUID collision.
- [ ] IT-1.x: per-class policy table or config (sprint 5 column on `empresa` or env-driven).
- [ ] IT-12.x: `conflict_resolver.py::resolve(uuid, resolucion, resolved_by, datos_merged)` helper.
- [ ] IT-12.x: `api_admin/routers/sync-conflict.py::GET /sync-conflict` (filterable by `estado`, `politica`, `tabla`, `uuid_sucursal`).
- [ ] IT-12.x: `api_admin/routers/sync-conflict.py::GET /sync-conflict/{uuid}` (diff view).
- [ ] IT-12.x: `api_admin/routers/sync-conflict.py::POST /sync-conflict/{uuid}/resolve` (admin resolution).
- [ ] IT-12.x: `web_admin/SyncMonitor/Conflictos` list + diff UI + resolve UI.
- [ ] IT-12.x: parametrization push generation on `manual-branch` and `manual-merge`.
- [ ] IT-12.x: aging warning `alerta tipo_alerta='conflict_aging'` for unresolved rows past retention.
- [ ] IT-12.x: `workers/sync_conflict_retention/__main__.py::purge_resolved_conflicts()` nightly cron.
- [ ] Sprint 5: explicit `uuid_origen_conflict` column on `alerta` for direct conflict→alert linkage.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Auto-resolution applied incorrectly on `[A]` hash chain break | Low | Explicit guard: `[A]` + hash chain → never auto-resolve; test coverage in RED |
| Admin resolution with stale data (admin reads conflict 2 weeks after detection, business context changed) | Med | Diff view shows `created_at` of both sides; UI shows age of conflict; warns if > 7 days old |
| Retention purge deletes a conflict under active admin investigation | Low | UI shows "mark as in_investigation" flag that exempts row from purge for 30 more days |
| Resolution UPSERT to destination table fails (e.g., FK constraint violation) | Low | TX wraps UPSERT + UPDATE `sync_conflict`; ROLLBACK if UPSERT fails; admin alerted |
| Conflict JSONB grows unbounded (very large `datos_nuevos` from `log_transaccional`) | Med | JSONB compression (TOAST); per-row size cap at 1MB (warning, not enforced) |
| `politica` configurable per tenant but misconfiguration causes auto-apply on `[V]` | Low | Default policy is conservative (`manual` for `[V]`/`[L-S]`); admin changes require explicit confirmation + audit row |
| Operational UPDATE on `resolucion` is too permissive | Low | Trigger checks `OLD.resolucion` is the only mutating field; all other columns trigger `AUDIT_FIRST_INMUTABLE` |
| Retention DELETE bypasses `rol_app` REVOKE — security concern | Low | DELETE is reserved for maintenance role; the role has no application code path; documented as infrastructure-only operation |

## 12. Open Questions
- (a) Should unresolved conflicts be auto-archived after N days with a warning `alerta`, or stay forever until admin acts? Sprint 5 decision.
- (b) Per-tenant conflict policy (different chains may want different auto-resolve behavior)? Currently global per enforcement level.
- (c) Should `datos_merged` (for `manual-merge` resolution) be a separate column or stored in `datos_nuevos`? Currently planned as separate column.
- (d) JSON diff view in UI — what's the canonical diff library (RFC 6902 JSON Patch)? Sprint 5.
- (e) `conflict_aging` warning — at what age should it fire (30d, 90d, 180d)?
- (f) Should `sync_conflict` rows be replicated to branches for transparency, or kept cloud-only? Currently cloud-only (admin decision is cloud-side; branch doesn't need to know).
- (g) Conflict policy for cross-table scenarios (e.g., conflict on `permisos_usuario` cascades to `usuarios_sucursal`) — manual or auto?
