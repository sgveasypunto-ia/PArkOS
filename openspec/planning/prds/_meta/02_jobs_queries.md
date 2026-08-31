# Meta-PRD: Sync worker queries (PRD-02)

> **NOT a table PRD.** Documents the exact queries that each sync worker
> performs — which tables it READS from, which tables it WRITES to, in what
> order, with what idempotency guarantees.

## Required References

### Canonical files outside this folder

- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Sync exploration**: [`openspec/changes/cloud-edge-sync-architecture/exploration.md`](../../changes/cloud-edge-sync-architecture/exploration.md)
- **PRD-00 Scaffold**: [`_meta/00_scaffold.md`](00_scaffold.md)
- **PRD-01 Models**: [`_meta/01_models.md`](01_models.md)

### Shared PRD references (this folder)

- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md)
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata

- **Type**: Meta-PRD (sync workers)
- **Phase**: Phase 1+ (every iteration adds worker logic)
- **Stack**: Python 3.13 + asyncio + httpx (HTTP polling) + SQLAlchemy 2.0 async
- **Origin**: `bootstrap-monorepo-foundation/F2`
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. Why this PRD is needed

Each per-table PRD documents the table's structure. But the sync workers query across multiple tables in a single TX, with idempotency keys, backoff logic, and hash chain verification. This meta-PRD centralizes those patterns so per-table PRDs only document table-specific behavior.

## 3. Workers

| Worker | Where | Lifetime | Authentication |
|---|---|---|---|
| `job_sync_cloud` | Cloud (single instance) | Long-running | `sync_agent` JWT (cloud-issued) |
| `job_sync_sucursal` | Each branch (one per branch) | Long-running | `sync_agent` JWT (received during pairing) |

Both workers use HTTP polling (WebSocket deferred to v2). Polling interval is configurable per worker (default 30s; via env `SYNC_INTERVAL_SECONDS`).

## 4. Use Cases enabled by these workers

### 4.1 Use Case: `uc.sync.branch-event-to-cloud`

A branch operator creates a row (ingreso, factura, anulacion, etc.). The worker pushes the row to cloud within seconds.

**Steps**:
1. Branch API endpoint calls writer → INSERT row + INSERT `sync_queue` row (status='pendiente').
2. `job_sync_sucursal/drain_outbox` every 30s reads `sync_queue` rows ordered by `prioridad DESC, created_at ASC LIMIT 100`.
4. For each: serialize via Pydantic, POST `https://<cloud>/api/v1/admin/sync/push` with `sync_agent` JWT.
5. On 200: UPDATE `sync_queue SET estado='exitoso', sync_attempts++, sync_timestamp=NOW()`.
6. On 5xx or timeout: backoff `intentos++; next_retry_at=NOW() + 2^intentos seconds` (capped at 1 hour).
7. After `intentos >= 10`: UPDATE `sync_queue SET estado='descartado'` + INSERT `alerta tipo_alerta='sync_failure'`.

**Tables touched**: `sync_queue` (R/W), `log_transaccional` (W if [A]), `alerta` (W if discardado), `sync_log` (W per cycle).

**FKs incoming**: `sync_queue.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**FKs outgoing**: none (worker doesn't write to other tables directly).

### 4.2 Use Case: `uc.sync.cloud-receive-and-apply`

Cloud receives a sync push from a branch. Cloud handler inserts the row + writes audit log.

**Steps**:
1. Branch POSTs to `api_admin/sync/push`.
2. Cloud `require_sync_agent` dependency verifies JWT (audience in [api_admin, api_sucursal], scope=sync_agent).
3. Handler reads payload: `tabla`, `operacion`, `datos` (JSON snapshot), `idempotency_key`.
4. Handler Pydantic-validates payload against model schema.
5. Handler SELECT FOR UPDATE on the target UUID (lock for idempotent insert).
6. If UUID already exists → skip (idempotent).
7. If new: INSERT row.
8. For `[A|L-S]` target: in same TX, INSERT `log_transaccional` row with hash chain verification.
9. INSERT `sync_log` (operational record).
10. Return `200 {accepted: <count>}`.

**Tables touched**: target table (W), `log_transaccional` (W if [A|L-S]), `sync_log` (W).

**FKs incoming**: target table FKs (e.g., `ingreso.uuid_sucursal`, `ingreso.uuid_tipo_vehiculo`, etc.).

### 4.3 Use Case: `uc.sync.cloud-push-parametrization-to-branch`

Cloud pushes catalog/configuration updates (usuarios, permisos, clientes, etc.) to branches via parametrization pull.

**Steps**:
1. Cloud admin updates a parametrization table (e.g., `usuarios.nombre`).
2. Cloud `job_sync_cloud/push_to_branch` every 30s: SELECT parametrization tables WHERE `sync_status='pending'`.
3. For each row, HTTP POST to branch `/api/v1/sucursal/sync/pull` with the row as `datos`.
4. Branch UPSERTs locally + UPDATE `sync_status='synced'`.
5. INSERT `sync_log` (both sides).

**Tables touched**: parametrization tables (R/W on cloud, R/W on branch).

### 4.4 Use Case: `uc.sync.dian-sync-back`

After cloud processes DIAN, it writes a `SyncBackEvent` row. Branch polls for it and updates `facturas.uuid_factura_electronica` + `numero_oficial`.

**Steps**:
1. Cloud `dian_dispatcher` finishes DIAN processing → INSERT `factura_electronica` → INSERT `SyncBackEvent` row (separate table) with `(uuid_factura, numero_oficial, dian_response_at)`.
2. Branch `job_sync_sucursal/poll_dian_numbers` every 30s: GET `cloud/sync/dian-numbers?since=<last_sync_ts>`.
3. Cloud returns pending SyncBackEvents for the branch.
4. Branch for each event: UPDATE `facturas SET uuid_factura_electronica=$1, numero_oficial=$2 WHERE uuid=$3`.
5. Branch: `reimpresion_ticket` API gate now passes (numero_oficial is set).

**Tables touched**: `SyncBackEvent` (W cloud, R branch), `factura_electronica` (W cloud), `facturas` (W branch).

**Integrations**: enables `uc.workflow.reimpresion` (which requires `numero_oficial` populated).

### 4.5 Use Case: `uc.sync.hash-chain-verifier`

Nightly worker verifies hash chain integrity for `log_transaccional` + `revocacion_factura`.

**Steps**:
1. `workers/hash_chain_verifier` runs every 24h.
2. For each `uuid_sucursal` in `log_transaccional`: recompute `hash_actual` for each row, compare to stored value.
3. For each `uuid_sucursal` in `revocacion_factura`: same.
4. If mismatch: INSERT `alerta tipo_alerta='hash_chain_break', uuid_sucursal=$1, valor_diferencia_efectivo=$chain_offset, estado='abierta'`.
5. INSERT `sync_log` recording the run.

**Tables touched**: `log_transaccional` (R), `revocacion_factura` (R), `alerta` (W), `sync_log` (W).

**Integrations**: depends on `log_transaccional` (T01) and `revocacion_factura` (T02) having hash chains.

### 4.6 Use Case: `uc.sync.branch-offline-detection`

Cloud detects branches that haven't synced in 24h.

**Steps**:
1. Cloud nightly cron: `SELECT uuid_sucursal FROM sync_log WHERE timestamp > NOW() - INTERVAL '24 hours' GROUP BY uuid_sucursal`.
2. Compare with `SELECT uuid FROM sucursal WHERE estado='activo'`.
3. For each missing: INSERT `alerta tipo_alerta='branch_offline', uuid_sucursal=$missing, estado='abierta'`.

**Tables touched**: `sync_log` (R), `sucursal` (R), `alerta` (W).

### 4.7 Use Case: `uc.sync.dian-dispatcher-sends-pending-facturas-to-dian-provider`

The `dian_dispatcher` cloud worker processes pending `factura_electronica` rows by sending them to the DIAN provider (e.g., a SOAP/XML integration or a third-party API like Carvajal, Facture). It runs every X minutes (configurable; default 60s) and processes batches. The atomic `empresa.consecutivo_actual` is incremented in the SAME TX as the `factura_electronica` INSERT — branch cannot assign numeros, only cloud can.

**Steps**:
1. Cloud `dian_dispatcher` fires every 60s.
2. SELECT pending rows: `SELECT fe.*, f.subtotal, f.descuento, f.total FROM factura_electronica fe JOIN facturas f ON fe.uuid_factura=f.uuid WHERE fe.reportado_dian=false AND fe.estado='activa' ORDER BY fe.created_at ASC LIMIT 50`.
3. For each pending row: build the DIAN XML (or JSON) payload from `facturas` + `factura_detalle` + `factura_impuestos` + `factura_otros_cobros` + `factura_pagos` snapshot data.
4. Open TX; SELECT `empresa FOR UPDATE` (atomic lock); `consecutivo_new = consecutivo_actual + 1`.
5. UPDATE `empresa SET consecutivo_actual = consecutivo_new`.
6. INSERT `factura_electronica` row with `consecutivo=$consecutivo_new, numero_oficial=empresa.prefijo_factura || '-' || lpad(consecutivo_new), reportado_dian=false` (will be true after DIAN response).
7. Call `log_writer.write_log(accion='factura_electronica_creada', tabla='factura_electronica', uuid_registro=$uuid, uuid_usuario=SYSTEM, ...)`.
8. POST to DIAN provider endpoint with the XML payload + `numero_oficial`.
9. On DIAN response (synchronous within the same minute typically):
   - If `aceptada`: UPDATE `factura_electronica SET reportado_dian=true`. INSERT `log_transaccional` (`accion='dian_aceptada'`).
   - If `rechazada`: INSERT `revocacion_factura` row (T02 — hash chain extends). INSERT `alerta tipo_alerta='dian_failure'`. INSERT `log_transaccional` (`accion='dian_rechazada'`).
10. INSERT `SyncBackEvent` (concept; sprint 5 concrete table) with `{uuid_factura, numero_oficial, reportado_dian, timestamp}` — branch polls and updates `facturas.uuid_factura_electronica` + `numero_oficial`.
11. COMMIT.

**Tables touched (writes)**: `empresa` (atomic counter), `factura_electronica` (W), `log_transaccional` (W per step), `revocacion_factura` (W if rejected), `alerta` (W if rejected), `SyncBackEvent` (W), `sync_queue` (parametrization push).
**Tables touched (reads)**: `factura_electronica` (pending), `facturas` (snapshot), `factura_detalle`/`factura_impuestos`/`factura_otros_cobros`/`factura_pagos` (snapshot data), `empresa` (atomic lock), `log_transaccional` (chain anchor), `clientes` (titular), `sucursal` (chain key).
**FKs traversed**: `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`; `factura_electronica.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`; `revocacion_factura.uuid_sucursal` → `sucursal.uuid`; `empresa` (no FK; singleton); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the originating `facturas` row is already enqueued and pushed.
- Cloud → branch: YES — `SyncBackEvent` flows back via branch polling.
- DIAN trigger: YES — this IS the DIAN dispatch flow.
- Hash chain impact: YES — cloud chain extends by 1+ rows per dispatched factura.

**Integrations**: enables T03 (`factura_electronica`), T21 (`empresa` atomic counter), T01 (`log_transaccional`), T02 (`revocacion_factura`), T41 (`alerta dian_failure`), and T05 (`facturas` SyncBackEvent).

### 4.8 Use Case: `uc.sync.conflict-resolver-applies-policy-per-table`

When `job_sync_cloud/drain_inbox` detects a conflict (e.g., two branches edited the same parametrization row, OR branch-originated row has `hash_anterior` that doesn't match cloud-side `last.hash_actual`), it INSERTs a `sync_conflict` row per the conflict policy: `cloud_wins` (cloud keeps its version, branch row discarded), `local_wins` (branch row takes precedence, cloud overwrites), `append` (both rows preserved with discriminator), `manual` (admin must resolve). Default per class: `[V]` = manual, `[L-E]` = append, `[L-W]` = append, `[A]` = append, `[L-S]` = manual.

**Steps**:
1. Cloud receives a sync push from branch with conflict detected.
2. Cloud handler reads payload + cloud-side current state.
3. Detect conflict: `SELECT * FROM sync_queue WHERE uuid_registro=$X AND uuid_sucursal=$branch AND tabla=$tabla AND estado='pendiente'` — if MULTIPLE rows for same uuid_registro across branches, that's a multi-branch conflict (different from same-row-version-mismatch).
4. For `[V]` parametrization tables where both branch and cloud edited same row:
   - Compare `vigente_desde` timestamps.
   - If cloud's version is newer → apply `cloud_wins`: discard branch row, log `sync_conflict` with `politica='cloud_wins', resolucion='auto'`.
   - If branch's version is newer → apply `local_wins`: UPSERT branch row to cloud, log with `politica='local_wins', resolucion='auto'`.
   - If same timestamp (rare): apply `manual`: log `sync_conflict` with `politica='manual', resolucion='pendiente'`, INSERT `alerta tipo_alerta='sync_conflict_manual'`.
5. For `[L-E|L-W|A]` tables where the conflict is hash-chain mismatch (out-of-order arrival):
   - Apply `append`: insert branch row verbatim after the highest cloud-side row, with `datos_local=$branch_snapshot, datos_cloud=$cloud_state_before_insert`. Log with `politica='append', resolucion='auto'`.
6. `sync_conflict` row is inserted in both auto and manual cases for audit traceability.
7. If `manual`: INSERT `alerta tipo_alerta='sync_conflict_manual'`. Admin triages via `web_admin/SyncConflictsPanel` and selects resolution (cloud_wins / local_wins / merge).
8. INSERT `log_transaccional` (`accion='sync_conflict_resolved'`, `datos_nuevos={politica, resolucion, conflict_uuid}`).

**Tables touched (writes)**: `sync_conflict` (W per conflict), `alerta` (W if manual), the target table (W if cloud_wins/local_wins), `log_transaccional` (W per resolution), `sync_queue` (UPDATE — discardado).
**Tables touched (reads)**: `sync_queue` (incoming batch), the target table (current cloud state), `log_transaccional` (chain anchor).
**FKs traversed**: `sync_conflict.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — branch pushed; cloud resolved.
- Cloud → branch: NO (the conflict resolution is cloud-internal).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1+ rows per resolved conflict.

**Integrations**: enables T32 (`sync_conflict`), T41 (`alerta sync_conflict_manual`), and the audit-first contract for parametrization data.

### 4.9 Use Case: `uc.sync.parametrization-pull-from-cloud-to-branch`

The `job_sync_sucursal/parametrization_pull` worker polls the cloud for parametrization table updates every 30s. It compares the branch's `last_sync_ts` with cloud's per-table `sync_status='pending'` rows. The pull is batched (up to 100 rows per cycle) and idempotent (UPSERT by UUID).

**Steps**:
1. `job_sync_sucursal/parametrization_pull` fires every 30s.
2. Worker captures `last_sync_ts` from local cache.
3. Worker POSTs `api_admin /sync/pull?since=$last_sync_ts` with `sync-agent-` JWT.
4. Cloud handler SELECTs all parametrization rows where `sync_status='pending'` AND `updated_at > $last_sync_ts`. Returns batched JSON.
5. Branch UPSERTs each row locally (by UUID — idempotent).
6. Branch updates `sync_status='synced'` for received rows (operational UPDATE on `[V]` tables — allowed because versioning semantics).
7. INSERT `sync_log` (branch side) recording the pull cycle.
8. INSERT `log_transaccional` (branch side) per parametrization table category (e.g., `accion='usuarios_pulled'`).

**Tables touched (writes)**: parametrization tables (`usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal`, `sucursal`, `tipo_sucursal`, `documentos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`, `empresa`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `impuestos`, `otros_cobros`, `costos_servicios`, `configuracion_tolerancias`, `configuracion_seguridad`) — UPSERT, `sync_log`, `log_transaccional`.
**Tables touched (reads)**: sync_metadata table (last_sync_ts).

**Sync behavior**:
- Branch → cloud: NO (this is cloud→branch direction).
- Cloud → branch: YES — parametrization pull.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1+ rows per pulled category.

**Integrations**: enables T18 (`subscripciones_cliente`), T20 (`vehiculos`), T21 (`empresa`), T22-T28 (catalogs), T29-T30 (`configuracion_*`), and the entire parametrization layer.

## 5. `job_sync_cloud` queries

### 5.1 `pull_from_branch` — receive sync pushes from branches

**Source**: branch posts `POST /sync/push` to cloud's API.

**Reads** (from request body, in `parkos_core.sync.handler.push_from_branch`):
- `datos: dict` — row snapshot including `uuid`, all business columns, `sync_idempotency_key`.
- `tabla: str` — name of the source table (e.g., `"ingreso"`, `"salidas"`, `"facturas"`).
- `operacion: str` — `"INSERT" | "UPDATE"` (no DELETE; sync_queue operational UPDATE exception is local only).
- `uuid_sucursal: UUID` — sender's branch UUID.

**Writes**:
- INSERT or UPDATE into the corresponding `prod.<table>` row in cloud DB.
- INSERT into `prod.log_transaccional` if the table is `[A]` or `[L-S]` (mandatory `log_transaccional` row).
- INSERT into `prod.sync_log` (one row per cycle of sync received).
- INSERT into `prod.sync_conflict` if conflict detected (per `infra/sync_config.yaml`).

**Idempotency**: `(sync_queue.idempotency_key) = f"{uuid_registro}:{operacion}"` at sender side. At receiver: `INSERT ... ON CONFLICT (uuid) DO NOTHING`.

**Hash chain verification**: when writing to `log_transaccional`, verify `hash_anterior == last.hash_actual` for the same `uuid_sucursal` BEFORE INSERT. Reject with 409 if mismatch.

### 5.2 `push_to_branch` — send parametrization updates to a branch

**Reads** (from cloud DB):
- `SELECT * FROM prod.<table> WHERE sync_status='pending' AND ...`
- For `[V]` parametrization tables: `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal`, `sucursal`, `tipo_sucursal`, `documentos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`, `em`,`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `impuestos`, `otros_cobros`, `costos_servicios`, `configuracion_tolerancias`, `configuracion_seguridad`.

**Writes** (via HTTP POST to `branch_url/sync/push`):
- The row snapshot as `datos`.
- INSERT into `prod.sync_log` (cloud side) recording the push.

**Idempotency**: same key as 4.1.

### 5.3 `poll_sync_back` — send DIAN `SyncBackEvent` to branch (pull mode)

**Reads** (from cloud DB):
- `SELECT * FROM prod.facturas WHERE uuid_factura_electronica IS NULL AND uuid_sucursal = $1 AND timestamp_evento >= $2` — invoices awaiting DIAN response.
- After `dian_dispatcher` writes `factura_electronica` with `numero_oficial`, an `SyncBackEvent` row is written (separate table).

**Writes** (via HTTP GET `branch_url/sync/dian-numbers?since=<ts>` from branch; cloud side just exposes the endpoint, branch polls):
- `prod.sync_log` row recording the poll.

### 5.4 `verify_chain` — nightly cron

**Reads**: `log_transaccional` rows for each `uuid_sucursal`; recomputes SHA256 chain; compares to `hash_actual` column.

**Writes**:
- INSERT into `alerta` if chain break detected (`tipo_alerta='hash_chain_break'`, `estado='abierta'`).
- INSERT into `sync_log` recording the verification run.

## 6. `job_sync_sucursal` queries

### 6.1 `drain_outbox` — push local events to cloud

**Reads** (from branch DB):
- `SELECT * FROM prod.sync_queue WHERE estado='pendiente' AND next_retry_at <= NOW() ORDER BY prioridad DESC, created_at ASC LIMIT 100`.

**Writes**:
- `UPDATE prod.sync_queue SET estado='exitoso' WHERE uuid IN (...)` — mark processed.
- `UPDATE prod.sync_queue SET estado='fallido',', iteration_id=intentos+1, next_retry_at=... WHERE uuid IN (...)` — backoff.
- INSERT into `sync_log` (branch side) recording the cycle.

**POST** to cloud's `POST /sync/push` with the data.

### 6.2 `poll_inbox` — pull parametrization from cloud

**Reads**: from cloud's `POST /sync/pull?since=<ts>` response.

**Writes** (to branch DB):
- UPSERT into `prod.<table>` for parametrization tables.
- INSERT into `log_transaccional` if applicable (audit log).
- UPDATE `sync_log` on branch side.

### 6.3 `poll_dian_numbers` — pull DIAN sync-back

**Reads**: from cloud's `GET /sync/dian-numbers?since=<ts>` response.

**Writes** (to branch DB):
- UPDATE `prod.facturas SET uuid_factura_electronica = $1, numero_oficial = $2 WHERE uuid = $3` for each `SyncBackEvent`.
- INSERT into `log_transaccional` recording the sync-back receipt.

### 6.4 `verify_chain` (branch side, optional)

**Reads**: `log_transaccional` for the branch's `uuid_sucursal`.

**Writes**: INSERT into `alerta` if break detected.

## 7. Cross-cutting query patterns

### 7.1 SELECT with FOR UPDATE for atomicity

```sql
-- For atomic `consecucion_actual` increment in `empresa`:
SELECT consecutivo_actual, rango_hasta FROM prod.empresa
WHERE uuid = $1 FOR UPDATE;
-- Update inside same TX
UPDATE prod.empresa SET consecutivo_actual = consecutivo_actual + 1 WHERE uuid = $1;
```

### 7.2 Idempotency key derivation

```python
def idempotency_key(uuid_registro: UUID, operacion: str) -> str:
    return f"{uuid_registro}:{operacion}"
```

### 7.3 Conflict detection query (per `infra/sync_config.yaml`)

For `[V]` parametrization tables when both branch and cloud edit the same row:

```sql
SELECT * FROM prod.<table>
WHERE uuid = $1
  AND ((sync_timestamp_branch IS NOT NULL AND sync_timestamp_cloud > sync_timestamp_branch)
       OR vigente_hasta IS NOT NULL);
-- Trigger manual resolution if returned
```

## 8. FK Map

Workers reference FKs indirectly via the SQLAlchemy models. Direct FK relationships in queries:

- `sync_queue.uuid_sucursal` → `sucursal.uuid`
- `sync_log.uuid_sucursal` → `sucursal.uuid`
- `sync_conflict.uuid_sucursal` → `sucursal.uuid`
- `log_transaccional.uuid_sucursal` + `uuid_usuario` → `sucursal.uuid` + `usuarios.uuid`
- `alerta.uuid_sucursal` + `uuid_usuario` + `uuid_arqueo` → respective tables

## 9. CodeGraph Dependencies

After models + workers land, `codegraph query --name job_sync_cloud --direction both` and similarly for `job_sync_sucursal` returns the full blast radius.

## 10. Layer-by-Layer Impact

| Layer | Impact | Path |
|---|---|---|
| 10. Sync cloud→branch | YES (this PRD) | `parkos_core/sync/` + `job_sync_cloud/` |
| 11. Sync branch→cloud | YES (this PRD) | `parkos_core/sync/` + `job_sync_sucursal/` |
| 12. Sync queue/conflict | YES | `parkos_core/sync/` |
| 4. DB hash-chain | YES (verify_chain) | `parkos_core/sync/hash_chain_verifier.py` |
| 24. CI/test | YES (integration tests mock cloud+branch) | `tests/integration/test_sync_*.py` |

## 11. RED Tests

- (RED) `job_sync_sucursal.drain_outbox` reads from `sync_queue` with backoff, marks success/failure correctly.
- (RED) `job_sync_cloud.pull_from_branch` validates hash chain; rejects with 409 on mismatch.
- (RED) `job_sync_cloud.verify_chain` emits `alerta tipo_alerta='hash_chain_break'` on tampered row.
- (RED) Sync push from branch with UUID collision → UNIQUE violation, treated as success (idempotent).
- (RED) `SyncBackEvent` roundtrip: branch `facturas.numero_oficial` updated after cloud receives.

## 12. Implementation Tasks

- [ ] PRD-02.1 Implement `parkos_core/sync/queue_processor.py::enqueue_<table>(...)` per table PRD.
- [ ] PRD-02.2 Implement `parkos_core/sync/handler.py::push_from_branch(...)` (cloud side).
- [ ] PRD-02.3 Implement `parkos_core/sync/handler.py::pull_from_cloud(...)` (branch side).
- [ ] PRD-02.4 Implement `parkos_core/sync/conflict_policy.py::detect_conflict(...)` per `infra/sync_config.yaml`.
- [ ] PRD-02.5 Implement `parkos_core/sync/sync_back.py::emit_sync_back_event(...)` (cloud).
- [ ] PRD-02.6 Implement `parkos_core/sync/verify_chain.py::verify_branch_chain(uuid_sucursal)` (cloud nightly).
- [ ] PRD-02.7 Wire workers: `job_sync_cloud/__main__.py` + `job_sync_sucursal/__main__.py`.
- [ ] PRD-02.8 RED tests for each query (per RED test list).
- [ ] PRD-02.9 Integration test: full sync roundtrip (branch event → cloud INSERT → parametrization pull → branch UPSERT).

## 13. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Worker crash mid-sync | Med | Idempotency key + ON CONFLICT DO NOTHING; re-process on next cycle |
| Backoff exponential overflow | Med | Cap `intentos` at 10; mark `descartado` after that; emit `alerta tipo_alerta='sync_failure'` |
| `sync_queue` depth exceeds Postgres limits | Med | Partition by month; alert at > 1000 |
| Hash chain break partial sync | Low | Per-branch monotonic seq in `datos.idempotency_key`; cloud verifier |
| Network partition during sync push | Med | Retry with exponential backoff; idempotency key prevents duplicates |
| Worker memory leak on long-running process | Low | Periodic restart via container healthcheck + SIGTERM |

## 14. Open Questions

- (a) Sync-back transport: pull (default) vs push. PRD-01 IT-5 ratifies pull mode.
- (b) Multi-branch parallel sync — does `job_sync_cloud` need connection pooling per branch? Yes (httpx AsyncClient with limits).
- (c) Order of operations when multiple tables in same sync batch (e.g., `factura` + `factura_detalle` + `factura_pagos` in one push) — all or nothing? Yes, wrap in TX.
- (d) Compression of sync_queue.datos (JSONB) for large rows? TBD.

## 15. Hand-off

After this PRD lands, **PRD-03 (API queries)** can specify the CRUD surface that branches and admins consume.