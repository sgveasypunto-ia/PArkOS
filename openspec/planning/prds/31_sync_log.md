# PRD: sync_log (T31)

> Per-cycle sync metrics — append-only operational record of every branch→cloud / cloud→branch synchronization cycle. Partitioned monthly by `pg_partman` for retention control. Drives admin dashboards (SyncMonitor), offline branch detection, and conflict aggregation across the fleet.

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
- **Table name**: `prod.sync_log`
- **SQL name**: `sync_log` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 1 year (partition by month via `pg_partman`; purga controlada por `pg_partman` retention policy)
- **Partitioning**: monthly on `created_at` (high write rate — ~3 cycles/min/branch × N branches × 24h)
- **Origin**: F1 (schema + REVOKE + trigger + monthly partition + retention config) + IT-1+ (writes per iteration: every sync cycle writes 1 row per direction per branch)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- No polymorphic FKs here; the `uuid_sucursal` is the only business FK.
- `sync-origen` is implicit per direction: branch workers write rows tagged with the branch of origin (the `uuid_sucursal` IS the origin); cloud workers write rows using the branch that owns the cycle. There is no separate `origen` column — direction is recoverable from `uuid_sucursal` + worker JWT + `created_at`.
- Travel: branch-origin rows travel to cloud via `sync_queue` (as queue items, separate rows); cloud-origin rows do NOT travel back (operational metrics are cloud-only, like `sync_queue`). Partition pruning is critical: queries by date range MUST hit one partition.

## 3. SOLID Atomic Breakdown
- **S**: "one sync cycle metric record" — INSERT in same TX as the cycle's queue drain (or the cycle's reception).
- **O**: future columns extensible via migration (e.g., `bytes_enviados`, `latencia_p95_ms`); new metric dimensions added as the system grows.
- **I**: branch operator API (writes per drain cycle, single writer); admin read API (`SyncMonitor` dashboard, paginated, read-only); cloud worker (`job_sync_cloud/drain_inbox` writes on receive cycle).
- **D**: `parkos_core/sync/metrics.py::record_cycle(uuid_sucursal, timestamp_inicio, operaciones_enviadas, exitosas, fallidas, conflictos, duracion_ms)` — the ONLY writer. Computes `duracion_ms` from `timestamp_inicio` and `NOW()`. Idempotent on retry: same `timestamp_inicio` produces the same cycle (no double-counting).
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`. `sync_log` is **operational metadata**, not historical compliance — but it is still append-only for `rol_app` to keep the metric stream uncontaminated.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, log dies with it |

### Incoming FKs (cross-table references via `uuid_sucursal`)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `web_admin/SyncMonitor` | (filter) | 0..N per branch | filtered by `uuid_sucursal`; rendered by date range |
| `web_admin/AlertasList` | (joins via uuid_sucursal) | 0..N per alert | the `branch_offline` alert cross-references the latest `sync_log.timestamp` per branch |
| `job_sync_cloud::nightly_aggregator` | (read) | 1..N per branch | rolls up per-day metrics |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `metrics.py::record_cycle()` per cycle (branch drain or cloud receive) |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved until `pg_partman` retention purges partitions older than 1 year |

**Special rules**:
- **Monthly partitioning**: `pg_partman` partitions by `created_at` month. Retention: 12 months. Query pattern: WHERE clauses on `created_at` MUST include a date range to leverage partition pruning.
- **Hash chain**: NO — `sync_log` is operational metadata, not probatory. The hash chain lives on `log_transaccional` per `uuid_sucursal`. `sync_log` is NOT chained.
- **Per-cycle granularity**: one row per direction per branch per cycle. A full bidirectional cycle (branch drain + cloud receive + cloud parametrization pull + branch parametrization receipt) is 4 rows minimum (2 in branch DB, 2 in cloud DB).
- **Conflict count semantics**: `conflictos` is the number of conflicts DETECTED in this cycle (NOT the number resolved). Resolution happens via `sync_conflict` (T32) and `alerta` (T41), separate tables.
- **`duracion_ms` semantics**: wall-clock duration of the cycle, from worker invocation start to last item ack. NOT the database TX duration.

## 6. CodeGraph Dependencies
- `parkos_core/sync/metrics.py::record_cycle()` (sole writer for cycle metrics).
- `job_sync_sucursal/drain_outbox` → writes 1 row per drain tick.
- `job_sync_sucursal/parametrization_pull` → writes 1 row per parametrization pull.
- `job_sync_cloud/drain_inbox` → writes 1 row per receive cycle.
- `job_sync_cloud/nightly_aggregator` → reads all rows per branch per day, rolls up to `resumen_metrics` (T01-derived concept).
- `api_admin/routers/sync-log.py::GET /sync-log` (paginated, cursor-based).
- `api_admin/routers/sync-log.py::GET /sync-log/{uuid_sucursal}/summary?desde=&hasta=` (rollup view).
- `api_sucursal/routers/sync-log.py::GET /sync-log` (own-branch view).
- `web_admin/SyncMonitor` (filterable by branch/fecha/conflictos > 0).
- `web_admin/AlertasList` (cross-references latest `sync_log.timestamp` per branch for `branch_offline` detection).
- `web_sucursal/SyncStatus` (own-branch view, last cycle timestamp).

## 7. Use Cases enabled by this table

The `sync_log` table is the **operational heartbeat** of the multi-tenant sync infrastructure: every branch→cloud / cloud→branch cycle writes a row with per-cycle counts of operations, conflicts, and duration. The data drives the admin `SyncMonitor` dashboard, the nightly aggregation worker, and the `branch_offline` detection worker. Append-only partitioned by month for retention control. **No manual operator input** for these flows — all writes are from workers.

### 7.1 Use Case: `uc.sync-log.branch-drain-cycle-records-metrics`

**Actor**: sync worker (branch `job_sync_sucursal/drain_outbox`)

**Real-world action**: The branch drain worker fires every 30s. It collects all `sync_queue` rows with `estado='pendiente' AND next_retry_at <= NOW()`, groups them into a batch, pushes to `api_admin /sync/push`, processes the response, and writes a single `sync_log` row summarizing the cycle. The row records `operaciones_enviadas`, `operaciones_exitosas`, `operaciones_fallidas`, `conflictos`, and `duracion_ms` for this tick.

**Steps**:
1. `job_sync_sucursal/drain_outbox` cron tick (every 30s).
2. Worker SELECTs pending queue rows: `SELECT * FROM sync_queue WHERE estado='pendiente' AND next_retry_at <= NOW() ORDER BY prioridad DESC, created_at ASC LIMIT 500`.
3. Worker captures `timestamp_inicio = NOW()`.
4. Worker builds HTTP POST to `api_admin /sync/push` with the sync-agent JWT carrying the batch.
5. On response: worker categorizes the batch results: `exitosas = sum of items with 200 OK`, `fallidas = sum of items with 4xx/5xx`, `conflictos = sum of items where response includes `conflict_detected` marker (T32 receives)`.
6. Worker computes `duracion_ms = NOW() - timestamp_inicio` (in milliseconds).
7. Worker calls `metrics.record_cycle(uuid_sucursal=self_branch, timestamp_inicio, operaciones_enviadas=batch_size, exitosas, fallidas, conflictos, duracion_ms)`.
8. `metrics.py` INSERTs `sync_log` row with the cycle metrics.
9. Worker UPDATEs `sync_queue` rows on success/fail (operational exception).
10. Worker `queue_processor.ack` the queue items; INSERT `log_transaccional` (`accion='sync_cycle'`, `tabla_afectada='sync_queue'`) per cycle.

**Tables touched (writes)**: `sync_log` (1 row per cycle), `sync_queue` (UPDATE — operational exception), `log_transaccional` (1 row per cycle audit).
**Tables touched (reads)**: `sync_queue` (the batch), `sucursal` (own branch context).
**FKs traversed**: `sync_log.uuid_sucursal` → `sucursal.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is the recording of the cycle; the actual push happened in step 4).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO direct impact on `sync_log`'s hash (it has none); `log_transaccional` chain extends by 1 row per cycle.

**Integration with other tables**:
- Reads from: `sync_queue` (the batch processed), `sucursal` (own branch).
- Writes to: `sync_log` (this row), `sync_queue` (UPDATE — operational exception), `log_transaccional` (audit).
- Cross-cutting: this is the canonical branch-side cycle write. Cloud receives equivalent rows via use case 7.2. The two are correlated by `timestamp_inicio` (cloud inserts its row shortly after branch's, within seconds).

### 7.2 Use Case: `uc.sync-log.cloud-receives-branch-push-cycle-records-metrics`

**Actor**: sync worker (cloud `job_sync_cloud/drain_inbox`)

**Real-world action**: Cloud receives a batch of N items from a branch via `/sync/push`. The cloud worker processes each item (idempotent INSERT/UPSERT into the destination table), detects any conflicts (T32) inline, and writes a single `sync_log` row summarizing the receive cycle. This is the cloud-side mirror of the branch's drain row — same `timestamp_inicio`, same `operaciones_enviadas`, but cloud's view of `exitosas`/`fallidas` may differ (the branch's "exitosa" might be cloud's "fallida" if validation failed post-push).

**Steps**:
1. Branch POSTs `/sync/push` with the batch (sync-agent JWT).
2. Cloud handler opens TX; for each item, validate idempotency (`ON CONFLICT (uuid_registro, operacion) DO NOTHING`); INSERT or UPSERT into the destination table.
3. Cloud handler detects conflicts inline: if `hash_anterior` mismatch on `log_transaccional`, or `uuid` collision with different content → INSERT `sync_conflict` row (T32 use case 7.1).
4. Cloud handler aggregates: `exitosas = items processed cleanly`, `fallidas = items rejected post-validation`, `conflictos = items where conflict row was created`.
5. Cloud captures `duracion_ms = NOW() - timestamp_inicio_received`.
6. Cloud calls `metrics.record_cycle(uuid_sucursal=$branch, timestamp_inicio=$inicio, ...)` — INSERTs `sync_log` row on cloud side.
7. Cloud returns response to branch with the per-item results.
8. Cloud INSERTs `log_transaccional` (`accion='sync_receive_cycle'`, `tabla_afectada='sync_queue'`) per cycle.

**Tables touched (writes)**: destination tables per item (ingreso, facturas, log_transaccional, etc.), `sync_conflict` (on conflict), `sync_log` (1 row per cycle), `log_transaccional` (1 row per cycle audit).
**Tables touched (reads)**: destination tables (idempotency check), `log_transaccional` (chain anchor for verification), `sucursal` (chain key).
**FKs traversed**: per item (varies); `sync_log.uuid_sucursal` → `sucursal.uuid`; `sync_conflict.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — this IS the receiving side of the cycle.
- Cloud → branch: NO (cloud's parametrization pull is a separate cycle, not this one).
- DIAN trigger: NO (this cycle is generic sync; DIAN is handled separately on `factura_electronica` inserts).
- Hash chain impact: depends on items received; if `log_transaccional` rows were in the batch, the cloud chain extends for that branch.

**Integration with other tables**:
- Reads from: destination tables (idempotency), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: destination tables (per item), `sync_conflict` (on conflict), `sync_log` (this row), `log_transaccional` (audit).
- Cross-cutting: `conflictos > 0` in the cloud-side `sync_log` row DOES NOT auto-emit `alerta` — each conflict gets its own `alerta tipo_alerta='sync_conflict_manual'` row (T41) via the receiver's conflict path. The `sync_log.conflictos` count is an aggregate metric for the dashboard.

### 7.3 Use Case: `uc.sync-log.branch-parametrization-pull-records-metrics`

**Actor**: sync worker (branch `job_sync_sucursal/parametrization_pull`)

**Real-world action**: Branch pulls parametrization changes from cloud (e.g., a new `tarifas_sucursal` version, an updated `impuestos`, a new `permisos_usuario` for an operator). The pull worker fetches the deltas, UPSERTs locally, and writes a `sync_log` row with `operaciones_recibidas=$count` (NOT `enviadas`). Direction is recoverable: cloud-origin rows have the branch as `uuid_sucursal` (the destination), but the metric is `operaciones_recibidas` not `operaciones_enviadas`.

**Steps**:
1. Branch `parametrization_pull` cron tick (every 60s).
2. Worker POSTs `api_admin /sync/parametrization/pull` with `{last_sync_timestamp=$local_high_water_mark}` (sync-agent JWT).
3. Cloud returns the delta: list of changed `tabla`/`uuid_registro` pairs since `last_sync_timestamp`.
4. Branch captures `timestamp_inicio = NOW()`.
5. Worker fetches each delta via `api_admin /sync/parametrization/row?tabla=&uuid=` (separate request per row, or bulk).
6. Branch UPSERTs each row locally; `log_transaccional` row per received parametrization (chain extends).
7. Worker computes `operaciones_recibidas = $count`, `duracion_ms`.
8. Worker calls `metrics.record_cycle(...)` with `operaciones_enviadas=0, operaciones_recibidas=$count, exitosas, conflictos=0` — INSERTs `sync_log` row.
9. Worker UPDATEs local `sync_cursor` table with new `high_water_mark = max(timestamp)`.

**Tables touched (writes)**: parametrization destination tables (tarifas_sucursal, impuestos, etc.), `sync_log` (1 row), `log_transaccional` (1 row per received parametrization), `sync_cursor` (high-water mark).
**Tables touched (reads)**: cloud via parametrization endpoint, `sync_cursor` (own high-water mark).
**FKs traversed**: per parametrization destination (varies).

**Sync behavior**:
- Branch → cloud: NO (this is branch receiving FROM cloud).
- Cloud → branch: YES — parametrization pull.
- DIAN trigger: NO (parametrization changes don't dispatch DIAN; only `factura_electronica` creation does).
- Hash chain impact: YES — branch chain extends by N rows where N = parametrization items received.

**Integration with other tables**:
- Reads from: parametrization source (cloud), `sync_cursor` (own high-water mark), `log_transaccional` (chain anchor).
- Writes to: parametrization destination (UPSERT), `sync_log` (this row), `log_transaccional` (audit), `sync_cursor` (high-water).
- Cross-cutting: this use case is the cloud→branch direction. The metric shape differs from use case 7.1: `operaciones_enviadas=0, operaciones_recibidas=N` (vs `enviadas=N, recibidas=0` for branch→cloud).

### 7.4 Use Case: `uc.sync-log.cloud-nightly-rollup-aggregator`

**Actor**: cloud nightly cron (cloud-only worker)

**Real-world action**: At 03:00 cloud time, the aggregator scans all `sync_log` rows from the previous 24 hours, groups by `uuid_sucursal`, and computes daily rollups: `total_operaciones_enviadas`, `total_exitosas`, `total_fallidas`, `total_conflictos`, `p95_duracion_ms`, `p99_duracion_ms`, `cycles_with_conflictos`. The rollup is written to a summary table (concept: `resumen_metrics`, derivable from `sync_log` via SQL VIEW) and one `log_transaccional` row per branch per day is emitted for the audit chain.

**Steps**:
1. `workers/sync_aggregator/__main__.py` runs at 03:00 cloud time (cron).
2. SELECT DISTINCT `uuid_sucursal` from `sync_log` where `created_at >= NOW() - INTERVAL '24 hours'`.
3. For each branch: SELECT aggregate query: `SELECT COUNT(*) FILTER (WHERE operaciones_enviadas > 0) AS cycles_total, SUM(operaciones_enviadas) AS total_enviadas, SUM(operaciones_exitosas) AS total_exitosas, SUM(operaciones_fallidas) AS total_fallidas, SUM(conflictos) AS total_conflictos, PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duracion_ms) AS p95_duracion_ms, PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duracion_ms) AS p99_duracion_ms, COUNT(*) FILTER (WHERE conflictos > 0) AS cycles_with_conflictos FROM sync_log WHERE uuid_sucursal = $1 AND created_at >= NOW() - INTERVAL '24 hours'`.
4. INSERT `log_transaccional` (`accion='sync_rollup_daily'`, `tabla_afectada='sync_log'`, `uuid_registro_afectado=$branch_uuid_marker`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={cycles_total, total_enviadas, ..., p99_duracion_ms}`).
5. INSERT into the `resumen_metrics` VIEW materialization table (or just write the rollup as a new `sync_log` row tagged with `tipo_registro='rollup'` — pending sprint 5 decision).
6. (Optional) If `total_fallidas / total_enviadas > 0.05` (5% failure threshold): INSERT `alerta tipo_alerta='sync_failure'` workflow root.

**Tables touched (writes)**: `log_transaccional` (1 row per branch per day), `alerta` (if threshold exceeded), `sync_log` (the raw rows are NOT modified — aggregator is read-only on them).
**Tables touched (reads)**: `sync_log` (24h window per branch), `sucursal` (active branches), `log_transaccional` (chain anchor).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain root).

**Sync behavior**:
- Branch → cloud: NO (this is cloud-internal rollup).
- Cloud → branch: NO (rollup is cloud-only; branches see their own cycle data via `web_sucursal/SyncStatus`).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per branch per day (`sync_rollup_daily`). Branches do NOT receive these rollup rows (they're cloud-only metadata).

**Integration with other tables**:
- Reads from: `sync_log` (24h window per branch), `sucursal` (active), `log_transaccional` (chain anchor).
- Writes to: `log_transaccional` (rollup audit), `alerta` (if failure threshold exceeded).
- Cross-cutting: this is the **cross-batch rollup**. The 24h window may span multiple monthly partitions of `sync_log` (rare, only on month boundaries). The query MUST use partition-friendly predicates (`created_at >= NOW() - INTERVAL '24 hours' AND created_at < NOW()`).

### 7.5 Use Case: `uc.sync-log.branch-offline-detection-worker`

**Actor**: cloud nightly cron (cloud-only worker)

**Real-world action**: At 04:00 cloud time, a worker detects branches that haven't synced in >24 hours. For each, it INSERTs an `alerta tipo_alerta='branch_offline'` workflow root with the offline duration, and emits one `log_transaccional` row per detected branch. The detection logic uses the MAX(`created_at`) per `uuid_sucursal` in `sync_log` — a branch that hasn't logged a cycle in 24h is offline (or its `job_sync_sucursal` worker is dead).

**Steps**:
1. `workers/branch_offline_detector/__main__.py` runs at 04:00 cloud time (cron).
2. SELECT active branches: `SELECT uuid FROM sucursal WHERE estado='activo' AND vigente_hasta IS NULL`.
3. For each branch: `SELECT MAX(created_at) AS last_cycle FROM sync_log WHERE uuid_sucursal = $branch AND created_at >= NOW() - INTERVAL '7 days'`.
4. If `last_cycle IS NULL` (never synced) OR `NOW() - last_cycle > INTERVAL '24 hours'`: branch is offline.
5. INSERT `alerta` workflow chain root (`tipo_alerta='branch_offline'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_usuario=NULL` (no operator assigned yet), `uuid_alerta_padre=NULL`, `uuid_arqueo=NULL`, `valor_diferencia_efectivo=0`, `valor_diferencia_datafono=0`, `observaciones='last_sync=$last_cycle, offline_for=$duration'`).
6. INSERT `log_transaccional` (`accion='branch_offline_detected'`, `tabla_afectada='sync_log'`, `uuid_registro_afectado=$branch_marker`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={last_sync: $last_cycle, offline_hours: $hours}`).
7. INSERT a `sync_log` row on cloud side? NO — this is cloud-internal activity; cloud's own cycle (the detector itself) doesn't write to `sync_log`. The detector emits `log_transaccional` only.
8. Admin sees the `alerta` in `web_admin/AlertasList` (red badge); clicks it → opens `AlertaDetail` with the offline duration and last sync timestamp.
9. When connectivity is restored (next drain_outbox fires and inserts a `sync_log` row with `NOW()`), the alert is NOT auto-resolved. The `alerta` workflow chain has `abierta → en_revision → resuelta` transitions (T41 use case 7.x). Admin manually transitions.

**Tables touched (writes)**: `alerta` (1 row per offline branch), `log_transaccional` (1 row per offline branch).
**Tables touched (reads)**: `sync_log` (MAX per branch), `sucursal` (active branches), `log_transaccional` (chain anchor).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain root); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (the offline branch is not syncing).
- Cloud → branch: NO (the parametrization pull is not the issue — branch-offline is the issue).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (`branch_offline_detected`) when sync is restored; cloud chain extends now (the detection row is cloud-origin).

**Integration with other tables**:
- Reads from: `sync_log` (MAX per branch), `sucursal` (active), `log_transaccional` (chain anchor).
- Writes to: `alerta` (workflow root), `log_transaccional` (audit).
- Cross-cutting: this is the canonical **branch-offline alerting** flow. The `alerta tipo_alerta='branch_offline'` is distinct from `sync_failure` (T06 use case 7.3 — local queue exhausted) and `sync_conflict_manual` (T32 — push-time conflict). All three flow through the same `alerta` table with different `tipo_alerta` enum values.
- Related: when connectivity returns, the branch's first `sync_log` row in 24h+ does NOT auto-resolve the alerta; admin must triage manually via the workflow chain.

### 7.6 Use Case: `uc.sync-log.admin-conflict-dashboard-aggregation`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/SyncMonitor`, filters by `conflictos > 0`, groups by `uuid_sucursal`, and views the conflict hotspots across the fleet. The query hits `sync_log` rows with `conflictos > 0` and JOINs to `sync_conflict` (T32) for the per-conflict details (which table, which row, local vs cloud snapshot, resolution status).

**Steps**:
1. Admin opens `web_admin/SyncMonitor/Conflictos`.
2. Frontend GETs `api_admin /sync-log?conflictos__gt=0&desde=&hasta=&uuid_sucursal=&cursor=` (paginated).
3. Backend runs: `SELECT uuid, uuid_sucursal, timestamp, operaciones_enviadas, conflictos, duracion_ms FROM sync_log WHERE conflictos > 0 AND created_at >= $desde AND created_at <= $hasta ORDER BY created_at DESC LIMIT 50`.
4. For each row, the dashboard shows: branch name (JOIN `sucursal`), cycle timestamp, conflict count, duration.
5. Admin clicks a row → expands to show the `sync_conflict` rows for this cycle: `SELECT * FROM sync_conflict WHERE uuid_sucursal = $branch AND timestamp >= $cycle_start AND timestamp < $cycle_end`.
6. Admin clicks a `sync_conflict` row → opens `ConflictDetail` showing `datos_local` vs `datos_cloud` JSON diffs side-by-side.
7. Admin chooses resolution: "Accept cloud", "Accept branch", "Manual merge" (T32 use case 7.2 details).
8. Backend INSERTs `log_transaccional` (`accion='sync_conflict_resolved_manual'`, `tabla_afectada='sync_conflict'`, `uuid_registro_afectado=$conflict_uuid`).
9. The conflict's `sync_log` row is NOT modified (it remains a historical record of the cycle); the resolution is a downstream event.

**Tables touched (writes)**: `log_transaccional` (1 row per resolution), `sync_conflict` (UPDATE — operational exception per T32; resolution field is mutable).
**Tables touched (reads)**: `sync_log` (filterable), `sync_conflict` (per cycle), `sucursal` (JOIN for display), `usuarios` (actor display), `log_transaccional` (chain anchor).
**FKs traversed**: `sync_log.uuid_sucursal` → `sucursal.uuid`; `sync_conflict.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is a cloud-only read of historical metrics).
- Cloud → branch: NO (admin triage is cloud-internal until the resolution creates a new sync event).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per admin resolution action (`sync_conflict_resolved_manual`).

**Integration with other tables**:
- Reads from: `sync_log` (the cycle rows), `sync_conflict` (the conflict details), `sucursal` (display), `usuarios` (display), `log_transaccional` (chain anchor).
- Writes to: `log_transaccional` (resolution audit), `sync_conflict` (UPDATE — operational exception, resolution field).
- Cross-cutting: this is the **cross-batch conflict aggregation** view. `sync_log.conflictos > 0` IS the index of conflict hotspots; `sync_conflict` is the per-conflict detail. Both are needed for the dashboard. The `sync_log` row is **never modified** post-resolution — the resolution lives in `sync_conflict.resolucion` (mutable operational field).

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (partitioning via `pg_partman`), 3 (partition retention), 5 (audit constraints — REVOKE only), 6 (cloud API router), 7 (branch API router), 10 (cloud sync worker writes), 11 (branch sync worker writes), 12 (sync_queue interop), 13 (web_admin SyncMonitor), 14 (web_sucursal SyncStatus), 20 (structlog metrics), 21 (Prometheus counters — T21-derived), 24 (pytest), 28 (docker compose for cron workers), 30 (cron workers — nightly aggregator + offline detector).

## 9. RED Tests
- (RED) INSERT `sync_log` from `rol_app` → success.
- (RED) UPDATE `prod.sync_log` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.sync_log` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Partition pruning: query `WHERE created_at >= '2026-08-01' AND created_at < '2026-09-01'` → EXPLAIN shows single partition hit, not full scan.
- (RED) `pg_partman` retention: rows older than 12 months are dropped automatically (simulate by advancing retention config).
- (RED) `metrics.record_cycle(...)` is idempotent: same `timestamp_inicio` produces no double-count.
- (RED) Branch drain cycle row + cloud receive cycle row have matching `timestamp_inicio` (correlatable by query).
- (RED) `operaciones_enviadas = operaciones_exitosas + operaciones_fallidas + conflictos` invariant holds per row.
- (RED) `duracion_ms >= 0` always.
- (RED) Admin GETs `/sync-log?conflictos__gt=0` → paginated, response shape stable, NEVER writes to `sync_log`.
- (RED) Branch offline detector: simulate a branch with no `sync_log` rows in 24h → INSERT `alerta tipo_alerta='branch_offline'`.
- (RED) Sync log metric shape: branch→cloud rows have `operaciones_enviadas > 0 OR operaciones_recibidas > 0`; cloud→branch rows have `operaciones_enviadas > 0 OR operaciones_recibidas > 0` (direction recoverable).

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + monthly `pg_partman` partition.
- [ ] F1.x `metrics.py::record_cycle()` helper.
- [ ] F1.x Partition retention policy (12 months) — automated purge via `pg_partman`.
- [ ] IT-1.x: `job_sync_sucursal/drain_outbox` writes branch-side cycle row.
- [ ] IT-1.x: `job_sync_cloud/drain_inbox` writes cloud-side cycle row.
- [ ] IT-2.x: `job_sync_sucursal/parametrization_pull` writes branch parametrization cycle row (with `operaciones_recibidas=N`).
- [ ] IT-2.x: parametrization pull endpoint exposes deltas since `last_sync_timestamp`.
- [ ] IT-2.x: `api_admin/routers/sync-log.py::GET /sync-log` (paginated, cursor-based).
- [ ] IT-2.x: `api_admin/routers/sync-log.py::GET /sync-log/{uuid_sucursal}/summary` (rollup view).
- [ ] IT-12.x: `workers/sync_aggregator/__main__.py::aggregate_daily()` nightly cron at 03:00 cloud.
- [ ] IT-12.x: `workers/branch_offline_detector/__main__.py::detect_offline_branches()` nightly cron at 04:00 cloud.
- [ ] IT-12.x: failure-threshold alert (`>5%` failures) emits `alerta tipo_alerta='sync_failure'`.
- [ ] IT-12.x: `web_admin/SyncMonitor` dashboard with `conflictos > 0` filter and `sync_conflict` cross-link.
- [ ] IT-12.x: `web_sucursal/SyncStatus` shows last cycle timestamp + 24h cycle count.
- [ ] Sprint 5: `resumen_metrics` materialized view (currently derivable via SQL).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| High write rate (3 cycles/min × N branches × 24h) bloats the table | Med | Partition by month; `pg_partman` retention purge at 12 months |
| Cross-partition scan on dashboard queries without date range | Med | API endpoints REQUIRE `desde` and `hasta` query params (no full table scan allowed) |
| Conflict count in `sync_log` diverges from `sync_conflict` row count | Low | Both are derived from the same cycle's processing; invariant enforced in the receiver worker |
| Branch offline detector fires false positives during legitimate maintenance windows | Low | Configurable `OFFLINE_THRESHOLD_HOURS` env var (default 24h); admin can mask via `alerta.resolucion` |
| Aggregator queries span partition boundary (rare on month rollover) | Low | Use `BETWEEN` predicates on `created_at` to limit scan to 2 partitions max |
| Metric `operaciones_enviadas` over-counts batched pushes (partial success) | Med | Receiver returns per-item status; branch sums successes/failures correctly |
| No hash chain on `sync_log` → tampering undetectable | Low | Acceptable: operational metadata, not compliance-critical; `log_transaccional` chain covers business actions; sync_log tampering can be cross-referenced against log_transaccional chains |

## 12. Open Questions
- (a) Should `resumen_metrics` be a materialized view, a new table, or queryable on the fly? Sprint 5 decision.
- (b) `operaciones_recibidas` vs `operaciones_enviadas` — should we add a `direccion` ENUM column (`branch_to_cloud` | `cloud_to_branch`) for clarity, or is the count differential sufficient?
- (c) `bytes_enviados` / `bytes_recibidos` columns for bandwidth tracking — needed?
- (d) Should `conflictos` include only manual conflicts or also auto-resolved (append-class)?
- (e) Cross-branch `sync_log` JOIN performance for fleet-wide dashboards at scale — do we need a `sync_log_fleet` rollup table refreshed every 5min?
- (f) `branch_offline` threshold per branch type (Tipo A vs B vs C) — do branches with sensors have higher connectivity requirements?
