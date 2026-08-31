# PRD: sync_queue (T06)

> Local-only operational queue. Branch writes; pushes to cloud via `job_sync_sucursal`. NEVER propagated.

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

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[A]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.sync_queue`
- **SQL name**: `sync_queue` (with `prod` schema)
- **Enforcement level**: `[A]` with operational UPDATE exception
- **Retention**: 1-2 years operational (partition by month)
- **Origin**: F1 (schema) + IT-1+ (writes per iteration)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `uuid_registro` is the UUID of the row in the source table (idempotency key).

## 3. SOLID Atomic Breakdown
- **S**: "one pending sync operation".
- **O**: `prioridad` column extensible (int).
- **I**: `queue_processor` abstraction; no API endpoint directly manipulates.
- **D**: `parkos_core/sync/queue_processor.py` is the only writer.
- **Atomic**: INSERT (initial) + UPDATE on operational fields ONLY.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, queue dies |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| Indirect: every writeable operation in the system (via `queue_processor.enqueue_<table>(...)`) | — | — | |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | | Initial queue insert |
| UPDATE on (estado, intentos, next_retry_at, ultimo_error) | YES | | Special `BEFORE UPDATE` trigger allows ONLY these columns |
| UPDATE on other columns | NO | | Trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | | REVOKE; queue rows are append-only history |

## 6. CodeGraph Dependencies
- `parkos_core/sync/queue_processor.py::enqueue_<table>(...)` per table.
- `job_sync_sucursal/drain_outbox`.
- `job_sync_cloud` (when processing received queue items).

## 7. Use Cases enabled by this table

The `sync_queue` table is the **local-only operational queue** that buffers every state-mutating write for eventual propagation to cloud. Branch writes locally; `job_sync_sucursal/drain_outbox` pushes within 30s. The table is `[A]` with an operational UPDATE exception: ONLY `estado`, `intentos`, `next_retry_at`, `ultimo_error` are mutable; all other columns are append-only. Never propagated (queue dies with the branch on decommission).

### 7.1 Use Case: `uc.sync-queue.enqueue-on-every-write`

**Actor**: system

**Real-world action**: Every state-mutating API call (POST `/ingresos`, POST `/facturas`, POST `/salidas`, etc.) calls `queue_processor.enqueue` after the INSERT. The queue row carries the snapshot (Pydantic dump) so the receiver can UPSERT idempotently.

**Steps**:
1. Operator POSTs `api_sucursal /ingresos` with the ingreso payload.
2. Backend opens TX; SELECT chain anchor from `log_transaccional`; INSERT `ingreso`; INSERT `log_transaccional`.
3. Backend calls `queue_processor.enqueue('ingreso', uuid_ingreso, datos)` — the helper builds a Pydantic dump of the new row.
4. `queue_processor` INSERTs `sync_queue` row (`estado='pendiente'`, `prioridad=5`, `intentos=0`, `next_retry_at=NOW()`, `datos={...Pydantic snapshot, uuid_registro, operacion='INSERT', idempotency_key=...}`).
5. Returns to caller; operator sees the success response.

**Tables touched (writes)**: `ingreso`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `log_transaccional` (chain anchor).
**FKs traversed**: `sync_queue.uuid_sucursal` → `sucursal.uuid`; `sync_queue.tabla` + `sync_queue.uuid_registro` is a polymorphic pointer (no DB FK); application-level validation.

**Sync behavior**:
- Branch → cloud: NO (this is the ENQUEUE step; the actual push happens in use case 7.2).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO direct impact on `log_transaccional` (the enqueue happens AFTER the log row is written; no separate log row for enqueue itself — enqueue is a meta-operation).

**Integration with other tables**:
- Reads from: `log_transaccional` (chain anchor), `ingreso` (the row being enqueued).
- Writes to: `sync_queue` (the queue row), `ingreso` (the business event), `log_transaccional` (the audit).
- Note: `sync_queue` is the ONLY `[A]` table that allows UPDATE (on operational columns). The helper `queue_processor.enqueue_<table>(...)` is the SOLE writer — direct INSERTs from API routers are forbidden by convention.

### 7.2 Use Case: `uc.sync-queue.drain-outbox-with-exponential-backoff`

**Actor**: sync worker

**Real-world action**: The branch worker fires every 30s. It drains pending queue rows with exponential backoff on transient cloud failures (`2^intentos` seconds, capped at 1h). Each successful push updates `estado='exitoso'`; failures bump `intentos` and push `next_retry_at` out.

**Steps**:
1. `job_sync_sucursal/drain_outbox` cron tick (every 30s).
2. SELECT `sync_queue` rows WHERE `estado='pendiente' AND next_retry_at <= NOW() AND prioridad >= $threshold` ORDER BY `prioridad DESC, created_at ASC` (priority-aware).
4. For each row: load `datos` (Pydantic snapshot); build HTTP POST to `api_admin /sync/push` with the sync_agent JWT.
5. On 200 OK: UPDATE `sync_queue SET estado='exitoso', ultimo_error=NULL, intentos=intentos+1` (only operational cols).
6. On 4xx (client error, bad payload): UPDATE `sync_queue SET estado='fallido', ultimo_error=$msg, intentos=intentos+1, next_retry_at=NOW()+2^intentos sec` (capped at 1h).
7. On 5xx (server error, transient): same as 4xx; the backoff naturally retries.
8. On network timeout (cloud unreachable): same as 5xx; retries continue on next tick.
9. INSERT `sync_log` row (operational record: `operaciones_enviadas=$n, exitosas=$ok, fallidas=$fail, duracion_ms=...`).
10. INSERT `log_transaccional` (`accion='sync_cycle', tabla_afectada='sync_queue'`) per cycle (read audit).

**Tables touched (writes)**: `sync_queue` (UPDATE on operational cols only), `sync_log`, `log_transaccional`.
**Tables touched (reads)**: `sync_queue` (the batch), `sucursal` (own branch context).
**FKs traversed**: `sync_queue.uuid_sucursal` → `sucursal.uuid`; `sync_log.uuid_sucursal` → `sucursal.uuid` (separate table, T31).

**Sync behavior**:
- Branch → cloud: YES — this is THE mechanism for branch→cloud propagation. Every cycle pushes a batch.
- Cloud → branch: NO.
- DIAN trigger: NO (queue drain doesn't itself trigger DIAN; only the downstream cloud processing does).
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row per cycle (`accion='sync_cycle'`), shared with whatever rows were pushed in that cycle (each pushed row also wrote its own log row when originally created).

**Integration with other tables**:
- Reads from: `sync_queue` (the batch), `sucursal` (own branch).
- Writes to: `sync_queue` (UPDATE — operational exception), `sync_log` (cycle metrics), `log_transaccional` (cycle audit).
- Related: cloud receives via `job_sync_cloud/poll_inbox` (separate worker); the receiver applies `ON CONFLICT (uuid_registro, operacion) DO NOTHING` semantics.

### 7.3 Use Case: `uc.sync-queue.discard-after-max-retries-emits-alert`

**Actor**: sync worker

**Real-world action**: A queue row has failed 10+ times (`intentos >= 10`). The worker marks it `descartado` and emits an `alerta tipo_alerta='sync_failure'`. Admin must investigate manually — the row is NOT deleted (append-only history).

**Steps**:
1. During `drain_outbox` cycle (use case 7.2), check rows WHERE `intentos >= 10 AND estado IN ('pendiente', 'fallido')`.
2. For each: UPDATE `sync_queue SET estado='descartado', ultimo_error='MAX_RETRIES_EXCEEDED'` (operational column only).
3. INSERT `alerta` (`tipo_alerta='sync_failure', estado='abierta', uuid_sucursal=$branch, valor_diferencia_efectivo=0, observaciones=$ultimo_error`).
4. INSERT `log_transaccional` (`accion='sync_failure_alerted'`).
5. Admin sees the alert in `web_admin/AlertasList` (red badge); opens `AlertaDetail` to see the `sync_queue` row history.
6. Admin may manually re-queue (insert new `sync_queue` row with `uuid_registro` and `operacion='INSERT'`; id=old is left as `descartado`) OR mark the alert as resolved if the underlying issue is acknowledged.

**Tables touched (writes)**: `sync_queue` (UPDATE), `alerta`, `log_transaccional`.
**Tables touched (reads)**: `sync_queue` (the offending row), `sucursal` (tenant), `log_transaccional` (chain anchor).
**FKs traversed**: `sync_queue.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` (responsible) → `usuarios.uuid` (NULL until claimed).

**Sync behavior**:
- Branch → cloud: NO (the discard is a local-only event).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row (`accion='sync_failure_alerted'`).

**Integration with other tables**:
- Reads from: `sync_queue` (the failing row), `log_transaccional` (chain anchor).
- Writes to: `sync_queue` (UPDATE — operational exception), `alerta` (admin notification), `log_transaccional` (audit).
- Cross-cutting: this is the only path where `sync_queue` rows transition to `descartado`. The original row data (`datos` JSONB) is preserved in the row for forensic purposes even after discard — the row stays in the partition until `fecha_retencion_hasta`.

### 7.4 Use Case: `uc.sync-queue.cloud-receives-hash-mismatch-creates-conflict`

**Actor**: sync worker (cloud side)

**Real-world action**: Branch pushes 200 `log_transaccional` rows via `sync_queue` while offline. Internet returns, batch lands on cloud. Cloud worker opens TX per row and verifies `incoming_hash_anterior == cloud_last.hash_actual` per `uuid_sucursal`. One row arrives out-of-order (e.g., the chain has a gap because the branch queue had two batches interleaved). The cloud worker applies `sync_conflict` policy `manual` — inserts `sync_conflict` row, INSERTs `alerta tipo_alerta='sync_conflict_manual'`, and DOES NOT INSERT the offending `log_transaccional` row into the cloud chain (it stays in branch queue for later resolution).

**Steps**:
1. Branch `job_sync_sucursal/drain_outbox` pushes batch of 200 `log_transaccional` rows.
2. Cloud `job_sync_cloud/drain_inbox` receives batch; for each row: opens TX; SELECT cloud-side `last.hash_actual` for `uuid_sucursal=$branch`.
3. Compare `incoming_row.hash_anterior` against `cloud_last.hash_actual`.
4. If match: INSERT `log_transaccional` row verbatim (cloud chain extends). Mark `sync_queue.estado='exitoso'`.
5. If mismatch (out-of-order, gap, or tampering): INSERT `sync_conflict` row (`uuid_sucursal=$branch`, `tabla='log_transaccional'`, `uuid_registro=$row_uuid`, `datos_local={...incoming snapshot}, datos_cloud={...cloud_last snapshot}, politica='manual', resol='pendiente', timestamp=NOW()`). INSERT `alerta` (`tipo_alerta='sync_conflict_manual'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_alerta_padre=NULL`, `observaciones=$summary`) — root of the `alerta` workflow chain for admin triage. Mark `sync_queue.estado='exitoso'` (the push succeeded; the conflict is recorded separately).
6. INSERT `log_transaccional` (`accion='sync_conflict_detected'`, `tabla_afectada='sync_conflict'`, `uuid_registro_afectado=$conflict_uuid`) — extends cloud log chain.
7. Admin sees the `alerta` in `web_admin/AlertasList`; opens `AlertaDetail` to see both `datos_local` and `datos_cloud` for manual resolution.
8. Admin decides: either accept branch version (manual merge) or accept cloud version (discard branch). The decision creates new `log_transaccional` row with `accion='sync_conflict_resolved_manual'` documenting the choice.

**Tables touched (writes)**: `sync_conflict` (1 row per mismatch), `alerta` (1 row per mismatch), `log_transaccional` (audit; uses skip-broken mode because the cloud chain is also being verified).
**Tables touched (reads)**: `sync_queue` (incoming batch), `log_transaccional` (cloud-side last hash for verification), `sucursal` (chain key).
**FKs traversed**: `sync_conflict.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `sync_conflict.uuid`.

**Sync behavior**:
- Branch → cloud: YES — this is the receiving side.
- Cloud → branch: NO (no parametrization impact; the conflict is cloud-internal until admin resolves).
- DIAN trigger: NO.
- Hash chain impact: The cloud chain does NOT extend with the offending row (it stays in branch queue). The audit `log_transaccional` row uses skip-broken mode (last known-good as `hash_anterior`). Admin's resolution later creates additional `log_transaccional` rows to extend the chain correctly.

**Integration with other tables**:
- Reads from: `sync_queue` (incoming batch), `log_transaccional` (cloud-side last hash), `sucursal`.
- Writes to: `sync_conflict` (manual policy), `alerta` (workflow chain root), `log_transaccional` (audit, skip-broken).
- Cross-cutting: this is the canonical cross-table cascade for sync_conflict — `sync_queue` → `sync_conflict` + `alerta` + `log_transaccional`. Total tables touched: 4.

### 7.5 Use Case: `uc.sync-queue.priority-promotion-dian-events`

**Actor**: system (queue_processor)

**Real-world action**: When the operator triggers a facturacion that needs DIAN numbering (cloud call), the `queue_processor` enqueues the `facturas` row with `prioridad=10` (higher than default 5). On drain, the worker picks higher-priority items first (facturas before plain ingresos). This ensures DIAN-bound rows don't wait behind 1000 ingreso rows in offline backfill.

**Steps**:
1. Operator POSTs `api_sucursal /facturas`; backend INSERTS `facturas` + children + `log_transaccional`.
2. `queue_processor.enqueue('facturas', uuid, datos, prioridad=10)` — higher than default.
3. Meanwhile, 800 `ingreso` rows accumulated in `sync_queue` during offline (all `prioridad=5`).
4. Branch `job_sync_sucursal/drain_outbox` cron fires: SELECT `sync_queue` rows WHERE `estado='pendiente' AND next_retry_at <= NOW()` ORDER BY `prioridad DESC, created_at ASC` (higher priority first).
5. The factura row goes out first; the 800 ingresos follow.
6. Cloud receives the factura first, processes `/facturas/procesar`, emits `SyncBackEvent` (numero_oficial back to branch); then processes ingresos in order.

**Tables touched (writes)**: `sync_queue` (the prioridad-prioritized batch).
**Tables touched (reads)**: `sync_queue` (priority-sorted batch), `log_transaccional` (chain anchor for writes that happen during sync).
**FKs traversed**: `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — but with priority ordering.
- Cloud → branch: NO (parametrization direction unaffected).
- DIAN trigger: YES indirectly — the factura row reaches cloud earlier, so DIAN processing starts earlier.
- Hash chain impact: NO direct impact (ordering affects propagation latency, not chain integrity).

**Integration with other tables**:
- Reads from: `sync_queue` (priority-sorted batch).
- Writes to: `sync_queue` (priority ordering is an enqueue-time decision; no UPDATE on operational cols here).
- Cross-cutting: priority is application-defined per `queue_processor.enqueue_<table>(prioridad=X)`. Default is 5 (operational events); DIAN-bound is 10; sync-conflict-replay is 15; alerts is 20.

### 7.6 Use Case: `uc.sync-queue.branch-offline-detection-emits-alert`

**Actor**: sync worker (cloud side)

**Real-world action**: Cloud `job_sync_cloud/poll_inbox` expects to receive a `sync_log` cycle from each branch every 30s (operational heartbeat). If a branch hasn't pushed anything in 24 hours (no `sync_log` row from that `uuid_sucursal` with `created_at >= NOW() - 24h`), the cloud emits `alerta tipo_alerta='branch_offline'` for admin investigation.

**Steps**:
1. Cloud `job_sync_cloud/heartbeat_monitor` cron fires every 5 minutes.
2. SELECT `sucursal` rows WHERE `estado='activo'`.
3. For each: SELECT MAX(`sync_log.created_at`) FROM `sync_log` WHERE `uuid_sucursal=$sucursal`.
4. If MAX is NULL or `< NOW() - 24h`: branch is offline (no recent sync cycles).
5. INSERT `alerta` (`tipo_alerta='branch_offline'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_alerta_padre=NULL`, `observaciones='no sync activity in 24h'`) — root of the `alerta` workflow chain.
6. INSERT `log_transaccional` (`accion='branch_offline_detected'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alerta_uuid`) — extends cloud log chain.
7. Admin sees the alert in `web_admin/AlertasList` (red badge); calls the branch operator to check connectivity.
8. When the branch comes back online, the next `sync_log` row arrives; the worker (separate) emits a NEW `alerta` row with `uuid_alerta_padre=$previous, estado='resuelta'` — workflow chain `abierta → resuelta` transition.

**Tables touched (writes)**: `alerta` (workflow root), `log_transaccional` (audit).
**Tables touched (reads)**: `sucursal` (active branches), `sync_log` (heartbeat query), `log_transaccional` (chain anchor).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain for the `resuelta` transition); `sync_log.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is cloud monitoring of branch behavior).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (`accion='branch_offline_detected'`). When branch returns online and the `resuelta` row is created, cloud chain extends by another 1 row.

**Integration with other tables**:
- Reads from: `sucursal`, `sync_log` (heartbeat), `log_transaccional` (chain anchor).
- Writes to: `alerta` (workflow chain root), `log_transaccional` (audit).
- Cross-cutting: this is the canonical branch-offline detection; uses `sync_log` as the operational heartbeat. The `alerta` workflow chain (`abierta → en_revision → resuelta`) provides the admin's resolution trail.

## 8. Layer-by-Layer Impact
Layers: 1, 2 (special trigger), 3 (partitioning), 5 (audit), 10, 11, 12, 24, 28.

## 9. RED Tests
- (RED) `DELETE FROM prod.sync_queue` → `AUDIT_FIRST_INMUTABLE`.
- (RED) `UPDATE prod.sync_queue SET datos='{}'` → `AUDIT_FIRST_INMUTABLE`.
- (RED) `UPDATE prod.sync_queue SET estado='exitoso'` → success.
- (RED) `UPDATE prod.sync_queue SET prioridad=1` → `AUDIT_FIRST_INMUTABLE`.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE on DELETE + special UPDATE trigger + partition.
- [ ] IT-1+ each iteration's writer calls `queue_processor.enqueue_<table>(...)`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Queue grows unbounded on offline branch | Med | Alert at depth > 1000; backoff exponential |
| `datos` snapshot becomes stale | Low | Idempotency key uses UUID |
| Operational UPDATE exception leaks | Low | Special trigger + REVOKE on other cols |

## 12. Open Questions
- (a) TTL for `estado='exitoso'` rows? (purge after 90 days?)
- (b) Compression for old partitions?