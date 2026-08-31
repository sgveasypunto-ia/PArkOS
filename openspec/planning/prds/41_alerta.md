# PRD: alerta (T41)

> `[L-W]` workflow chain for system-generated and admin-created alerts. Each state transition is a NEW row chained by `uuid_alerta_padre` (named FK per AGENTS.md convention, distinct from `reimpresion_ticket.uuid_padre` and `anulaciones.uuid_anulacion_padre`). States: `abierta` (root — system or admin emits) → `en_revision` (admin claims) → `resuelta` (admin closes with reason). The `tipo_alerta` ENUM is the cross-cutting trigger identifier: `diferencia_arqueo` (T34), `caja_baja` (T33), `fraude` (manual flag), `manual` (admin/operator), `sync_failure` (T06), `branch_offline` (T31), `hash_chain_break` (T01), `login_lockout` (T30/T42), `pairing_replay` (T11), `cupo_rejected` (T15), `dian_failure` (T03), `impuesto_change_post_facturacion` (T26/T37). Direct FK `uuid_arqueo` (nullable) for `diferencia_arqueo` lineage.

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
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — **relevant** (chain via `uuid_alerta_padre`)
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.alerta`
- **SQL name**: `alerta` (with `prod` schema)
- **Enforcement level**: `[L-W]` workflow chain (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (compliance — alerts may precede DIAN findings, fraud investigations)
- **Hash chain**: NO (workflow chain, not source-of-truth for compliance)
- **ENUM `tipo_alerta`**: `diferencia_arqueo`, `caja_baja`, `fraude`, `manual`, `sync_failure`, `branch_offline`, `hash_chain_break`, `login_lockout`, `pairing_replay`, `cupo_rejected`, `dian_failure`, `impuesto_change_post_facturacion`
- **Origin**: F1 (schema + REVOKE + trigger + ENUM type) + IT-7 (writes per emission source) + IT-12 (hash_chain_verifier + branch_offline cron)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 8 use cases covering the full `tipo_alerta` registry + the workflow chain transition pattern)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_alerta_padre` is self-FK for workflow chaining: 0..1 (NULL on root, $previous_uuid on transitions).
- `uuid_arqueo` is FK to `arqueo` (T34), ONLY populated when `tipo_alerta='diferencia_arqueo'`. NULL for all other `tipo_alerta` values.
- `uuid_usuario` is the **responsible** user (nullable on root when system-generated with no actor assigned; populated when admin claims via `en_revision`).
- Travel: branch-origin alerts (`diferencia_arqueo`, `manual`, `login_lockout`, `sync_failure`) travel to cloud via `sync_queue` within 30s. Cloud-origin alerts (`branch_offline`, `hash_chain_break`, `dian_failure`) stay in cloud only — branches never see them via parametrization push unless admin explicitly resolves and the resolution is replicated.
- **Workflow chain naming**: this table uses `uuid_alerta_padre` (named FK per AGENTS.md), distinct from `reimpresion_ticket.uuid_padre`. All chain rows of the same alerta share the same `tipo_alerta` and the same `uuid_arqueo` if applicable.

## 3. SOLID Atomic Breakdown
- **S**: "one alert event or workflow transition" — INSERT in same TX as the originating trigger + log_transaccional.
- **O**: extensible via migration; new `tipo_alerta` enum values added as new system failures are discovered (e.g., `cupo_rejected` was added in sprint 2; sprint 5 may add `impuesto_retroactivo`).
- **I**: system workers (emitters — `arqueo_writer`, `sync_worker`, `hash_chain_verifier`, `branch_offline_detector`, `login_lockout_monitor`); branch operator API (manual flag creation — `POST /alertas` with `tipo_alerta='manual'` or `'fraude'`); cloud admin API (workflow transitions — `POST /alertas/{uuid}/revisar`, `POST /alertas/{uuid}/resolver`); admin read API (`AlertasList` paginated, filterable by `tipo_alerta` + `estado` + `uuid_sucursal`).
- **D**: `parkos_core/operacion/alerta_writer.py::write_alerta(uuid_sucursal, tipo_alerta, valor_diferencia_efectivo=0, valor_diferencia_datafono=0, uuid_arqueo=None, uuid_usuario=None, uuid_alerta_padre=None, observaciones='', estado='abierta')` — the ONLY writer. Validates `tipo_alerta` is in the ENUM. Validates FK consistency (`uuid_arqueo` is set only when `tipo_alerta='diferencia_arqueo'`).
- **Atomic**: INSERT only (workflow chain). REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`. The state transition `abierta → en_revision → resuelta` is **always** a new row — NEVER an UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch where the alert originated (cloud for system alerts) |
| `uuid_usuario` | `prod.usuarios.uuid` | 0..1 (nullable) | RESTRICT | responsible user — populated on admin claim or operator manual creation |
| `uuid_arqueo` | `prod.arqueo.uuid` | 0..1 (nullable) | RESTRICT | ONLY for `tipo_alerta='diferencia_arqueo'`; NULL otherwise |
| `uuid_alerta_padre` | `prod.alerta.uuid` | 0..1 (nullable, self-ref) | RESTRICT | workflow chain link: NULL on root, $previous_uuid on transitions |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (none direct — `alerta` is leaf; emit-side FKs are reversed: `alerta.uuid_arqueo` points to `arqueo`) | | | |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `alerta_writer.py::write_alerta()` per emission or per transition |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for compliance retention |

**Special rules**:
- **Workflow chain**: root has `uuid_alerta_padre=NULL, estado='abierta'`. Transition to `en_revision` has `uuid_alerta_padre=$root.uuid, estado='en_revision', uuid_usuario=$admin`. Terminal transition to `resuelta` has `uuid_alerta_padre=$revision.uuid, estado='resuelta', uuid_usuario=$admin`. State vigente = last row in chain (query `ORDER BY created_at DESC LIMIT 1`).
- **All chain rows share `tipo_alerta`**: the same trigger identifier throughout the chain. Transitioning a `diferencia_arqueo` from `en_revision` to `resuelta` keeps `tipo_alerta='diferencia_arqueo'`.
- **`uuid_arqueo` is chain-stable**: the FK to `arqueo` is set on the root row and copied to all chain rows (so admin can JOIN `alerta.uuid_arqueo` regardless of which transition row they inspect).
- **Auto-resolve for `branch_offline`**: when connectivity returns, the worker inserts a NEW chain row with `estado='resuelta'` (the worker is the "actor" — `uuid_usuario=SYSTEM`). This is the canonical auto-close pattern: a system actor closes a system-generated alert.
- **No `rechazada` state**: alerts are never rejected; they are either resolved (closed with action) or remain open. If the underlying condition is a false positive, admin resolves with `observaciones='false_positive: <reason>'`.
- **System vs manual distinction**: when `tipo_alerta` is one of `{diferencia_arqueo, sync_failure, branch_offline, hash_chain_break, login_lockout, cupo_rejected, dian_failure, impuesto_change_post_facturacion}`, the emission is system-triggered (worker / API). When `tipo_alerta='manual'` or `'fraude'`, emission is human-triggered (operator or admin via UI).

## 6. CodeGraph Dependencies
- `parkos_core/operacion/alerta_writer.py::write_alerta()` (sole writer; validates ENUM + FK consistency).
- `parkos_core/operacion/arqueo_writer.py` (calls `write_alerta` on tolerance exceeded — T34 use case 7.2).
- `parkos_core/sync/queue_processor.py::drain_outbox` (calls `write_alerta` on `descartado` after 10 retries — T06 use case 7.x).
- `workers/hash_chain_verifier/__main__.py` (calls `write_alerta` on chain break — T01 use case 7.4).
- `workers/branch_offline_detector/__main__.py` (calls `write_alerta` for missing branches — T31 use case 7.x).
- `parkos_core/auth/login_lockout_monitor.py` (calls `write_alerta` after N failed attempts — T30/T42 use case 7.4).
- `api_sucursal/routers/alertas.py::POST /alertas` (operator manual emission).
- `api_admin/routers/alertas.py::POST /alertas/{uuid}/revisar` (admin claim).
- `api_admin/routers/alertas.py::POST /alertas/{uuid}/resolver` (admin close).
- `api_admin/routers/alertas.py::GET /alertas` (paginated, filterable by `tipo_alerta` + `estado` + `uuid_sucursal`).
- `api_admin/routers/alertas.py::GET /alertas/{uuid}/chain` (workflow chain view).
- `web_sucursal/AlertaManualForm` (operator manual alert creation).
- `web_admin/AlertasList` (filterable dashboard with `tipo_alerta` colored badges).
- `web_admin/AlertasList/{uuid}/Detail` (single alert detail with chain + cross-references).

## 7. Use Cases enabled by this table

The `alerta` table is the **central nervous system of operational signals**: every failure, anomaly, and manual flag from across the 45-table architecture funnels through this single workflow chain. The `tipo_alerta` ENUM is the cross-cutting identifier that tells admin "what went wrong and where to look first". Each `tipo_alerta` value has a specific emission source AND a specific resolution workflow. The chain via `uuid_alerta_padre` provides the audit trail of who triaged the alert when. **No cámaras, no OCR, no QR**: alerts are system-detected or manually flagged.

### 7.1 Use Case: `uc.alerta.diferencia-arqueo-emitida-triggered-by-cierre`

**Actor**: system (within TX of `arqueo_writer.write_arqueo()` — T34 use case 7.1)

**Real-world action**: Operator closes sesion via `web_sucursal/CierreCajaForm`. Backend SELECTs vigente `configuracion_tolerancias`, computes `diferencia = reportado - esperado`. If `ABS(diferencia_efectivo) > tolerancia_efectivo OR ABS(diferencia_datafono) > tolerancia_datafono`, the system INSERTs `alerta` workflow chain root with `tipo_alerta='diferencia_arqueo'`, `estado='abierta'`, `uuid_arqueo=$arqueo_uuid`, `valor_diferencia_efectivo`, `valor_diferencia_datafono`. The `uuid_arqueo` FK provides a direct drill-down path from the alert to the offending arqueo.

**Steps**:
1. Within arqueo TX (T34 use case 7.1, step 11), check tolerance.
2. If exceeded: `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='diferencia_arqueo', uuid_arqueo=$arqueo_uuid, valor_diferencia_efectivo=-2000, valor_diferencia_datafono=0, uuid_usuario=$operator, observaciones='arqueo=$uuid, esperado=50000/125000, reportado=48000/125000, tolerancia_vigente=5000/5000')`.
3. `alerta_writer` validates `tipo_alerta='diferencia_arqueo'` ⇒ `uuid_arqueo` MUST be set (NOT NULL); rejects with `INTERNAL_ALERT_VALIDATION` otherwise.
4. INSERT `alerta` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$operator`, `uuid_arqueo=$arqueo_uuid`, `uuid_alerta_padre=NULL` (CHAIN ROOT), `timestamp_evento=NOW()`, `estado='abierta'`, `tipo_alerta='diferencia_arqueo'`).
5. INSERT `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alerta_uuid`, `datos_nuevos={tipo_alerta:'diferencia_arqueo', uuid_arqueo:$arqueo_uuid, valor_diferencia_efectivo, valor_diferencia_datafono, tolerancia_vigente}`).
6. `queue_processor.enqueue('alerta', $uuid, $snapshot)` — propagates to cloud.
7. Operator UI shows red banner: "ALERTA: Diferencia efectivo fuera de tolerancia. Admin revisará." Sesion closure proceeds; the alert is informational at this point (does NOT block cierre).

**Tables touched (writes)**: `alerta` (1 root row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `configuracion_tolerancias` (vigente — read in T34 use case 7.1), `arqueo` (just inserted in same TX), `sucursal`, `usuarios` (operator), `log_transaccional` (chain anchor).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid`; `alerta.uuid_arqueo` → `arqueo.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow root, NULL on insert); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the alerta propagates with the arqueo within 30s.
- Cloud → branch: NO (the alerta workflow is cloud-side triage; branch sees the initial banner only).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row; cloud chain extends on receipt.

**Integration with other tables**:
- Reads from: `configuracion_tolerancias` (vigente at arqueo time — T29), `arqueo` (FK target), `usuarios` (operator actor), `sucursal`, `log_transaccional`.
- Writes to: `alerta` (workflow chain root), `log_transaccional`, `sync_queue`.
- Cross-cutting: the `uuid_arqueo` FK is the direct linkage — admin drill-down is one JOIN (`SELECT * FROM alerta JOIN arqueo ON alerta.uuid_arqueo = arqueo.uuid`). This is the canonical `tipo_alerta` that ties `alerta` to another domain table via direct FK.
- Related: T34 (`arqueo`) use case 7.2 covers the tolerance check pattern; T29 (`configuracion_tolerancias`) covers the snapshot semantic for tolerance.

### 7.2 Use Case: `uc.alerta.branch-offline-emitida-by-nightly-cron-resolves-on-reconnect`

**Actor**: system (`workers/branch_offline_detector` nightly cron) + system (`job_sync_cloud/drain_inbox` reconnect)

**Real-world action**: Cloud nightly cron (02:00 cloud time) walks every active branch in `sucursal` (estado='activo'), checks the latest `sync_log.timestamp` for each. If a branch has not synced in 24 hours, the cron INSERTs `alerta` workflow root with `tipo_alerta='branch_offline'`. The alerta has no `uuid_arqueo` (no arqueo involved). When the branch reconnects and pushes a new sync cycle, the receiving cloud worker INSERTs a NEW chain row with `estado='resuelta'` (auto-close by system actor `uuid_usuario=SYSTEM`).

**Steps**:
1. Cloud `workers/branch_offline_detector` runs at 02:00 cloud time (cron, after `hash_chain_verifier`).
2. SELECT active branches: `SELECT uuid FROM sucursal WHERE estado='activo'`.
3. SELECT latest sync per branch: `SELECT uuid_sucursal, MAX(timestamp) AS last_sync FROM sync_log WHERE uuid_sucursal IN (...) GROUP BY uuid_sucursal`.
4. For each branch where `last_sync < NOW() - INTERVAL '24 hours'`: check if an open alerta already exists for this branch+type (`SELECT 1 FROM alerta WHERE uuid_sucursal=$branch AND tipo_alerta='branch_offline' AND uuid_alerta_padre IS NULL AND estado='abierta'`).
5. If no open alert: `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='branch_offline', uuid_usuario=SYSTEM, observaciones='last_sync=$last_sync, threshold=24h')`.
6. INSERT `alerta` workflow chain root row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=SYSTEM`, `uuid_arqueo=NULL`, `uuid_alerta_padre=NULL`, `estado='abierta'`, `tipo_alerta='branch_offline'`).
7. INSERT `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `datos_nuevos={tipo_alerta:'branch_offline', last_sync}`).
8. (Later, when branch reconnects) `job_sync_cloud/drain_inbox` receives the first sync push from the branch. Before applying the batch, the worker checks for open `branch_offline` alerts on that branch and INSERTs a NEW chain row with `estado='resuelta', uuid_alerta_padre=$root.uuid, uuid_usuario=SYSTEM, observaciones='auto-resolved: branch reconnected, first_sync_at=$now'`. The auto-resolve happens BEFORE the batch is applied (so admin sees the alert as resolved when they query).
9. INSERT `log_transaccional` (`accion='alerta_resuelta'`, `tabla_afectada='alerta'`, `datos_nuevos={uuid_alerta_padre:$root_uuid, estado:'resuelta', trigger:'auto_reconnect'}`).

**Tables touched (writes)**: `alerta` (1 root row on emission + 1 chain row on auto-resolve), `log_transaccional` (2 rows), `sync_log` (1 row per cycle, as part of normal drain).
**Tables touched (reads)**: `sucursal` (active branches), `sync_log` (latest sync timestamp per branch), `alerta` (existing open check), `log_transaccional` (chain anchor), `usuarios` (SYSTEM lookup).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (SYSTEM on auto-resolve); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: NO (cloud-origin alert; branch never sees it via sync).
- Cloud → branch: NO (the alert is informational for cloud admin; branch is unaware it's being monitored for offline — it just experiences the offline state).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row on emission + 1 row on auto-resolve.

**Integration with other tables**:
- Reads from: `sucursal`, `sync_log` (latest sync), `alerta` (open check), `log_transaccional`.
- Writes to: `alerta` (workflow chain: root + auto-resolve row), `log_transaccional`, `sync_log`.
- Cross-cutting: this is the canonical **auto-resolve** pattern — a system actor (`uuid_usuario=SYSTEM`) closes a system-generated alert when the underlying condition normalizes. The `branch_offline` workflow is therefore typically 2 rows (abierta → resuelta), never en_revision. Admin only intervenes if the auto-resolve did NOT happen (branch never reconnected) — then admin manually resolves with motivo.
- Related: T31 (`sync_log`) provides the latest-sync data; T06 (`sync_queue`) workers trigger the auto-resolve.

### 7.3 Use Case: `uc.alerta.sync-failure-emitida-after-10-retries-descartado`

**Actor**: system (`job_sync_sucursal/drain_outbox` after backoff exhaustion)

**Real-world action**: Branch sync worker pushes `sync_queue` items to cloud. After 10 failed retries (exponential backoff capped at 1 hour), the worker marks the queue item as `descartado` AND INSERTs `alerta` workflow root with `tipo_alerta='sync_failure'`. The alerta carries the discarded queue UUID in `observaciones` (the `sync_queue.datos` may reference multiple tables; admin drill-down requires looking at the queue row). The alert is per-branch — all sync failures across all tables funnel through this single `tipo_alerta`.

**Steps**:
1. `job_sync_sucursal/drain_outbox` cycle: item N has `intentos >= 10 AND estado='fallido'`.
2. UPDATE `sync_queue SET estado='descartado', ultimo_error=$last_error WHERE uuid=$queue_uuid` (operational UPDATE exception per .mmd).
3. `alerta_writer.write_alerta(uuid_sucursal=self_branch, tipo_alerta='sync_failure', uuid_usuario=SYSTEM, observaciones='queue_uuid=$queue_uuid, tabla=$tabla, uuid_registro=$uuid_registro, last_error=$last_error, intentos=10')`.
4. INSERT `alerta` workflow root row (`uuid=server-generated`, `uuid_sucursal=self_branch`, `uuid_usuario=SYSTEM`, `uuid_arqueo=NULL`, `uuid_alerta_padre=NULL`, `estado='abierta'`, `tipo_alerta='sync_failure'`).
5. INSERT `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `datos_nuevos={tipo_alerta:'sync_failure', queue_uuid, tabla, uuid_registro, last_error}`).
6. INSERT `sync_log` (cycle metric — includes `fallidas=N` counter increment).
7. Admin sees the alert in `web_admin/AlertasList` filterable by `tipo_alerta='sync_failure'`. Click drill-down → admin views the `sync_queue` row (queue UUID in observaciones) to see WHAT failed.

**Tables touched (writes)**: `sync_queue` (UPDATE — operational exception), `alerta` (1 root row), `log_transaccional` (1 row), `sync_log` (1 row).
**Tables touched (reads)**: `sync_queue` (the discarded item), `sucursal` (tenant), `usuarios` (SYSTEM), `log_transaccional` (chain anchor).
**FKs traversed**: `sync_queue.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (SYSTEM); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow root); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the alerta propagates (the discarded item itself does NOT propagate — it's a branch-local operational state).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row.

**Integration with other tables**:
- Reads from: `sync_queue` (the discarded item), `sucursal`, `usuarios`, `log_transaccional`.
- Writes to: `sync_queue` (UPDATE — discardado), `alerta` (workflow root), `log_transaccional`, `sync_log`.
- Cross-cutting: this `tipo_alerta` has no direct FK to the failing table; the linkage is via `observaciones` text (queue UUID) → `sync_queue` JOIN. Admin drill-down is two hops (alerta → queue → table). The alert is per-FAILURE, not per-table — admin must check queue UUID to see which table failed.
- Related: T06 (`sync_queue`) covers the retry/backoff/discard flow; T31 (`sync_log`) covers the cycle metrics; T11 (`pairing_replay`) covers a similar alert pattern for sync-agent token abuse.

### 7.4 Use Case: `uc.alerta.hash-chain-break-emitida-by-nightly-verifier`

**Actor**: system (`workers/hash_chain_verifier` nightly cron)

**Real-world action**: Cloud nightly cron walks every active `uuid_sucursal` in `log_transaccional`, recomputes `hash_actual` for each row, compares to stored value. On mismatch, INSERTs `alerta` workflow root with `tipo_alerta='hash_chain_break'`. The alert carries the broken row UUIDs in `observaciones` (similar to `sync_failure`). No `uuid_arqueo` (chain break is not an arqueo issue). Resolution is manual — admin must investigate the broken rows (tampering, migration bug, partial sync).

**Steps**:
1. `workers/hash_chain_verifier/__main__.py` runs at 02:00 cloud time (cron).
2. For each `uuid_sucursal` in `log_transaccional`: walk the chain from genesis, recompute `hash_actual = SHA256(uuid + timestamp_registro + hash_anterior)`.
3. If mismatch: collect the offending row UUID(s).
4. After walking all branches: for each broken chain, `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='hash_chain_break', uuid_usuario=SYSTEM, observaciones='broken_uuids=$list, chain_offset=$offset')`.
5. INSERT `alerta` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=SYSTEM`, `uuid_arqueo=NULL`, `uuid_alerta_padre=NULL`, `estado='abierta'`, `tipo_alerta='hash_chain_break'`).
6. INSERT `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `datos_nuevos={tipo_alerta:'hash_chain_break', broken_uuids, chain_offset}`).
7. IMPORTANT: this verifier INSERT also writes its OWN `log_transaccional` row using **skip-broken** mode — `hash_anterior` references the LAST KNOWN-GOOD row, NOT the broken row. Otherwise the verifier's own audit would extend a broken chain and propagate the break.
8. Admin sees the alert in `web_admin/AlertasList`. Drill-down: admin runs `SELECT * FROM log_transaccional WHERE uuid IN ($broken_uuids)` to see the tampered rows.

**Tables touched (writes)**: `alerta` (1 root row per broken branch), `log_transaccional` (2 rows: alerta audit + verifier self-audit).
**Tables touched (reads)**: `log_transaccional` (every chain, all branches), `sucursal` (active branches), `usuarios` (SYSTEM), `log_transaccional` (chain anchor for verifier self-audit).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: NO (verifier is cloud-only; chain on branch DB is verified separately on each parametrization pull).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO direct impact on the verified chains (verifier is read-only on those). The verifier's own audit rows DO extend the chain (skip-broken mode).

**Integration with other tables**:
- Reads from: `log_transaccional` (every chain), `sucursal`, `usuarios`, `log_transaccional` (chain anchor for self-audit).
- Writes to: `alerta` (workflow root), `log_transaccional` (verifier self-audit).
- Cross-cutting: this is the **probatory integrity** alert — the most severe alert type. Admin must investigate and may need to involve the `rol_admin_auditor` (BYPASSRLS) for forensic analysis. Resolution typically involves inserting a NEW `log_transaccional` row documenting the investigation outcome (per the .mmd hash chain rules, the broken row is NEVER modified — investigation lives in NEW rows).
- Related: T01 (`log_transaccional`) use case 7.4 covers the verifier; T02 (`revocacion_factura`) has its own chain verifier (same worker).

### 7.5 Use Case: `uc.alerta.login-lockout-emitida-after-N-failed-attempts`

**Actor**: system (`parkos_core/auth/login_lockout_monitor`)

**Real-world action**: Operator attempts login with wrong password. Backend INSERTs `login` row with `estado='fallido'` (T42). The `login_lockout_monitor` counts failed login attempts for the user within the lockout window (e.g., 15 min). If count >= `configuracion_seguridad.max_intentos_login` (default 5), INSERTs `alerta` workflow root with `tipo_alerta='login_lockout'`. The user account is locked (additional failed attempts return 423 Locked, not 401 Unauthorized). Resolution: admin manually resets the lockout via `web_admin/UsuariosDetail/Unlock`.

**Steps**:
1. Operator POSTs `api_sucursal /auth/login` with wrong password (T42 use case 7.2).
2. Backend bcrypt verify → fail. INSERT `login` (`estado='fallido'`, `timestamp_evento=NOW()`, `uuid_usuario=$user`, `uuid_sucursal=$branch`). INSERT `log_transaccional` (`accion='login_fallido'`).
3. `login_lockout_monitor` (called inline OR via cron every 60s) SELECTs failed login count: `SELECT COUNT(*) FROM login WHERE uuid_usuario=$user AND estado='fallido' AND created_at > NOW() - INTERVAL '$configuracion_seguridad.minutos_bloqueo_login minutes'`.
4. If count >= `max_intentos_login` AND no existing open alert for this user: `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='login_lockout', uuid_usuario=$user, observaciones='failed_attempts=$count, window_min=$minutos_bloqueo, max_intentos=$max_intentos')`.
5. INSERT `alerta` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$user` (the locked user, NOT the actor — actor is SYSTEM), `uuid_arqueo=NULL`, `uuid_alerta_padre=NULL`, `estado='abierta'`, `tipo_alerta='login_lockout'`).
6. INSERT `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `datos_nuevos={tipo_alerta:'login_lockout', uuid_usuario, failed_attempts, max_intentos}`).
7. Backend marks the `usuarios` row as locked (via new version with `estado='bloqueado'`, vigente_hasta=archive previous). INSERT `log_transaccional` (`accion='usuario_bloqueado'`).
8. Subsequent login attempts return 423 Locked until admin resolves.
9. Admin sees the alert in `web_admin/AlertasList`. Drill-down → admin views the failed login rows via JOIN `usuarios` (the locked user) → admin clicks `Unlock` → INSERT new `alerta` chain row with `estado='resuelta', uuid_alerta_padre=$root.uuid, uuid_usuario=$admin, observaciones='unlocked by admin, motivo=$motivo'`. The user row is re-versioned to `estado='activo'`.

**Tables touched (writes)**: `login` (1 row per failed attempt), `usuarios` (new version: bloqueado), `alerta` (1 root row), `log_transaccional` (multiple rows).
**Tables touched (reads)**: `usuarios` (target user), `configuracion_seguridad` (vigente — thresholds), `login` (failed count), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (the locked user — note this is NOT the SYSTEM actor); `alerta.uuid_alerta_padre` → `alerta.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (actor — SYSTEM or admin); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the alerta propagates (and the usuarios version change).
- Cloud → branch: NO (the lockout is branch-side enforcement).
- DIAN trigger: NO.
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `usuarios`, `configuracion_seguridad`, `login`, `sucursal`, `log_transaccional`.
- Writes to: `login` (failed attempts), `usuarios` (version: bloqueado), `alerta` (workflow root), `log_transaccional`.
- Cross-cutting: this `tipo_alerta` is **user-targeted** — admin drill-down is via `alerta.uuid_usuario` JOIN to `usuarios` (not via arqueo or queue). The `uuid_usuario` is the LOCKED USER (the victim of the brute force), not the actor (SYSTEM). Resolution involves admin manually unlocking, which creates a new `usuarios` version AND a new `alerta` chain row.
- Related: T42 (`login`) use case 7.4 covers the lockout emission; T30 (`configuracion_seguridad`) covers the thresholds.

### 7.6 Use Case: `uc.alerta.manual-or-fraude-emitida-by-operator-or-admin`

**Actor**: operator (branch, `tipo_alerta='manual'`) OR admin (cloud, `tipo_alerta='fraude'`)

**Real-world action**: Operator notices something suspicious (e.g., a customer claims they were charged incorrectly, a vehicle is parked but no `ingreso` exists, a barrier failed open) and wants to flag it. Operator opens `web_sucursal/AlertaManualForm`, types motivo, selects `tipo_alerta='manual'`, optionally provides the related UUID (e.g., `uuid_ingreso`, `uuid_factura`). Backend INSERTs `alerta` workflow root. Separately, admin in cloud may flag a transaction as `tipo_alerta='fraude'` after investigation — same shape, different ENUM value and different actor.

**Steps**:
1. Operator opens `web_sucursal/AlertaManualForm`. Form shows: `tipo_alerta` (dropdown: manual, fraude — operator may only select `manual` per RBAC), `motivo` (required text), optional references (dropdown to select `ingreso`, `salida`, `factura`, `arqueo` — populated from own-branch data).
2. Operator fills the form. Submits. Frontend POSTs `api_sucursal /alertas` with `{tipo_alerta='manual', motivo='cliente reporta cobro duplicado', uuid_referencia_tipo='factura', uuid_referencia=$factura_uuid}`.
3. Backend validates RBAC: `permiso='crear_alerta_manual'`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional`.
5. `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='manual', uuid_usuario=$operator, observaciones='motivo: cliente reporta cobro duplicado; ref: factura=$factura_uuid')`. Note: the `uuid_referencia` is stored in `observaciones` as JSON-ish text — there is NO FK constraint because the reference type varies.
6. INSERT `alerta` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$operator`, `uuid_arqueo=NULL`, `uuid_alerta_padre=NULL`, `estado='abierta'`, `tipo_alerta='manual'`).
7. INSERT `log_transaccional` (`accion='alerta_manual_creada'`, `tabla_afectada='alerta'`, `datos_nuevos={tipo_alerta:'manual', motivo, uuid_referencia_tipo, uuid_referencia}`).
8. `queue_processor.enqueue('alerta', $uuid, $snapshot)` — propagates to cloud.
9. Cloud admin sees the alert in `web_admin/AlertasList` filter `tipo_alerta='manual' OR 'fraude'`. Click drill-down → admin reads motivo + ref → opens the referenced entity.

**Tables touched (writes)**: `alerta` (1 root row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `usuarios` (operator), `sucursal`, `log_transaccional` (chain anchor).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (the operator who flagged); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow root); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: YES (manual alerts originate from branches; fraude typically originates from cloud admin).
- Cloud → branch: NO (alerta workflow is cloud-side triage; branch sees the initial banner only).
- DIAN trigger: NO.
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `usuarios`, `sucursal`, `log_transaccional`.
- Writes to: `alerta` (workflow root), `log_transaccional`, `sync_queue`.
- Cross-cutting: this `tipo_alerta` has NO direct FK to the referenced entity. The linkage is via `observaciones` text. This is intentional — alerts may reference entities that aren't yet known (e.g., "vehicle left without paying", no UUID exists yet). Admin resolves by investigating the referenced context manually. The `fraude` value is reserved for cloud admin (after investigation confirms fraud); operator cannot emit `fraude`.
- Related: T40 (`reclamos`) is the CUSTOMER-initiated workflow; `alerta tipo_alerta='manual'` is the OPERATOR/ADMIN-initiated flag. They're distinct paths with distinct semantics (reclamo has customer-visible resolution; alerta is internal triage).

### 7.7 Use Case: `uc.alerta.admin-triage-workflow-chain-revisar-resolver`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/AlertasList`, filters by `estado='abierta'`, sees alerts across all `tipo_alerta` values. Clicks an alert to view `AlertaDetail`: the alert's source (`uuid_arqueo` for `diferencia_arqueo`, queue UUID for `sync_failure`, etc.), the operator who triggered it (for manual), the timestamp. Admin decides to investigate. Clicks `En Revisión` — backend SELECTs the latest chain row (root, currently `abierta`), INSERTs a NEW chain row with `uuid_alerta_padre=$root.uuid, estado='en_revision', uuid_usuario=$admin, observaciones=$admin_notes`. The chain now has 2 rows. Later, admin clicks `Resolver` — INSERTs another chain row with `estado='resuelta', uuid_alerta_padre=$revision.uuid, uuid_usuario=$admin, observaciones=$resolution_notes`. The chain now has 3 rows. The alerta's "vigente state" is the LAST row (`resuelta`).

**Steps**:
1. Admin opens `web_admin/AlertasList`. Default filter `estado='abierta'`. UI renders a paginated list with `tipo_alerta` colored badges (red = diferencia_arqueo, orange = sync_failure, yellow = branch_offline, blue = manual, etc.).
2. Frontend GETs `api_admin /alertas?estado=abierta&tipo_alerta=&uuid_sucursal=&limit=&cursor=`. Backend paginated query with JOINs to `sucursal` (display) and `usuarios` (responsible).
3. Admin clicks an alert (e.g., `tipo_alerta='diferencia_arqueo'`, `uuid_arqueo=$X`). UI shows `AlertaDetail` with the chain (currently 1 row: abierta), JOINed to `arqueo` (via `uuid_arqueo` FK) → JOINed to `sesion`, `factura_pagos`, `caja`. Admin drills into the arqueo detail (T34 use case 7.4).
4. Admin clicks `En Revisión`. Frontend POSTs `api_admin /alertas/{uuid}/revisar` with `{observaciones: 'investigating discrepancy in efectivo count'}`.
5. Backend validates RBAC: `permiso='triage_alerta'`.
6. Backend SELECTs latest chain row: `SELECT * FROM alerta WHERE uuid=$root_uuid OR uuid_alerta_padre=$root_uuid ORDER BY created_at DESC LIMIT 1`. Returns the `abierta` row.
7. Backend opens TX; SELECT chain anchor from `log_transaccional`.
8. `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta=$tipo_alerta_of_root, uuid_usuario=$admin, uuid_alerta_padre=$latest.uuid, observaciones='en_revision: $observaciones', estado='en_revision')`. CRITICAL: `tipo_alerta` MUST match the root (writer validates).
9. INSERT `alerta` chain row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$admin`, `uuid_arqueo=$root.uuid_arqueo` (chain-stable), `uuid_alerta_padre=$latest.uuid`, `estado='en_revision'`, `tipo_alerta` copied from root).
10. INSERT `log_transaccional` (`accion='alerta_revisada'`, `tabla_afectada='alerta'`, `datos_anteriores={estado:'abierta', uuid_alerta_padre:$root_uuid}`, `datos_nuevos={estado:'en_revision', uuid_alerta_padre:$latest_uuid}`).
11. `queue_processor.enqueue('alerta', $new_uuid, $snapshot)` — branch receives the chain row.
12. Admin sees the chain visualization: root (abierta, operator, timestamp) → transition (en_revision, admin, observaciones, timestamp). 2 rows.
13. Later (minutes/hours/days): admin clicks `Resolver` → POST `/alertas/{uuid}/resolver` with `{observaciones: 'investigated: cash short due to late-evening refund not registered'}`.
14. Same pattern: SELECT latest chain row (en_revision), INSERT new chain row with `estado='resuelta', uuid_alerta_padre=$revision.uuid, observaciones=$resolution`. INSERT `log_transaccional` (`accion='alerta_resuelta'`).
15. Admin UI shows the final chain: root (abierta) → transition (en_revision) → terminal (resuelta). 3 rows. State vigente = resuelta. The alerta is closed.

**Tables touched (writes — per transition)**: `alerta` (1 chain row per transition: en_revision + resuelta = 2 rows), `log_transaccional` (1 row per transition), `sync_queue` (1 item per chain row).
**Tables touched (reads — per transition)**: `alerta` (previous chain row), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow self-FK); `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (admin actor on transitions); `alerta.uuid_arqueo` → `arqueo.uuid` (chain-stable for `diferencia_arqueo`); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — chain replication via parametrization push. Branch UPSERTs the new chain rows.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per transition; branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `alerta` (previous chain row), `permisos_usuario` (RBAC), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `alerta` (new chain row per transition), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **workflow chain transition** pattern for `alerta`. The chain is per-alerta-root (i.e., all transitions of the same alert share `uuid_alerta_padre` chain). State vigente = last row in chain. The chain provides full audit trail of who reviewed when and what action was taken. Recursive CTE `WITH RECURSIVE chain AS (SELECT * FROM alerta WHERE uuid=$root UNION ALL SELECT next.* FROM alerta next JOIN chain c ON next.uuid_alerta_padre=c.uuid) SELECT * FROM chain ORDER BY created_at` returns the full chain.
- Special case: `branch_offline` SKIPS `en_revision` — the worker auto-resolves directly `abierta → resuelta` when connectivity returns. No admin involvement needed unless auto-resolve never happens.
- Related: T39 (`anulaciones`) is the analogous workflow chain pattern (`solicitada → aprobada → ejecutada`); T40 (`reclamos`) is similar (`abierto → en_revision → resuelto | rechazado`).

### 7.8 Use Case: `uc.alerta.admin-cubo-filtros-tipo-alerta-cross-branch`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/AlertasList` with no filters. Sees ALL alerts across ALL branches and ALL `tipo_alerta` values. UI renders grouped counts by `tipo_alerta` (e.g., "diferencia_arqueo: 3 abiertas", "sync_failure: 12 abiertas", "manual: 2 abiertas", "branch_offline: 1 abierta"). Admin clicks each group to filter. Admin can also filter by `uuid_sucursal` (cross-branch dashboard) and `estado` (open vs all). For deep dive, admin clicks an alert → `AlertaDetail` with chain + cross-references.

**Steps**:
1. Admin opens `web_admin/AlertasList`. UI shows tabs/groups by `tipo_alerta` with counts: `diferencia_arqueo (3)`, `caja_baja (1)`, `fraude (0)`, `manual (2)`, `sync_failure (12)`, `branch_offline (1)`, `hash_chain_break (0)`, `login_lockout (1)`, `pairing_replay (0)`, `cupo_rejected (2)`, `dian_failure (0)`, `impuesto_change_post_facturacion (0)`.
2. Frontend GETs `api_admin /alertas/groups` → backend runs: `SELECT tipo_alerta, estado, COUNT(*) FROM alerta WHERE uuid_sucursal IN ($sucursales_permitidas) GROUP BY tipo_alerta, estado ORDER BY tipo_alerta`. Returns the count matrix.
3. Admin clicks `diferencia_arqueo` group. Frontend GETs `api_admin /alertas?tipo_alerta=diferencia_arqueo&estado=abierta&limit=50` (paginated).
4. Backend runs: `SELECT a.*, s.nombre AS sucursal_nombre, u.nombre AS usuario_nombre FROM alerta a JOIN sucursal s ON a.uuid_sucursal=s.uuid LEFT JOIN usuarios u ON a.uuid_usuario=u.uuid WHERE a.tipo_alerta='diferencia_arqueo' AND a.uuid_alerta_padre IS NULL AND a.estado='abierta' AND a.uuid_sucursal IN ($sucursales_permitidas) ORDER BY a.created_at DESC LIMIT 50`.
5. UI renders the list with: branch name, operator (or "SYSTEM" for auto-emitted), `valor_diferencia_efectivo`, `valor_diferencia_datafono`, timestamp, `uuid_arqueo` link.
6. Admin clicks an alert → `AlertaDetail` (per use case 7.7) → drills into `arqueo` via `uuid_arqueo` FK → `sesion` → `factura_pagos` → `caja` snapshots.
7. Admin filters by `uuid_sucursal=$branch_X` to focus on one branch: GET `/alertas?tipo_alerta=&estado=&uuid_sucursal=$branch_X`. Backend re-runs with branch filter.
8. Admin exports filtered list to CSV/Excel for offline analysis or to attach to a `reclamos` workflow.

**Tables touched (writes)**: NONE for the read.
**Tables touched (reads)**: `alerta` (filterable, paginated, grouped), `sucursal` (display), `usuarios` (display), `arqueo` (cross-ref via `uuid_arqueo` for `diferencia_arqueo`), `sync_queue` (cross-ref via `observaciones` text for `sync_failure`).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid`; `alerta.uuid_arqueo` → `arqueo.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (for chain visualization on detail).

**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `alerta`, `sucursal`, `usuarios`, `arqueo`, `sync_queue`, `log_transaccional`, `usuarios` (SYSTEM lookup).
- Writes to: NONE.
- Cross-cutting: this is the **admin dashboard view**. The cubo de filtros (cube of filters: `tipo_alerta × estado × uuid_sucursal`) is the canonical cross-cutting query. The recursive CTE for chain resolution is used on `AlertaDetail`. Admin uses this view to identify patterns: "12 sync_failure alerts in last 24h → check branch network", "3 diferencia_arqueo alerts → check operator training", "1 branch_offline → call branch".
- Related: T31 (`sync_log`) is the data source for `branch_offline` detection; T34 (`arqueo`) is the data source for `diferencia_arqueo`; T06 (`sync_queue`) is the data source for `sync_failure`.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger + ENUM), 5 (audit constraints — REVOKE), 6 (cloud admin API for triage), 7 (branch API for manual emission), 8 (Pydantic schemas), 10 (cloud sync worker for auto-resolve on reconnect), 11 (branch sync worker for sync_failure + login_lockout), 12 (sync_queue interop), 13 (web_admin AlertasList + AlertaDetail + cross-branch dashboard), 14 (web_sucursal AlertaManualForm), 15 (shadcn UI components for forms + badges), 20 (structlog), 21 (Prometheus counters — alerts per tipo per branch per day), 24 (pytest), 28 (docker compose for cron), 30 (hash_chain_verifier cron + branch_offline_detector cron), 31 (security audit — login_lockout pattern), 33 (DIAN compliance docs — dian_failure + impuesto_change_post_facturacion), 35 (operational dashboards).

## 9. RED Tests
- (RED) INSERT `alerta` from `rol_app` with valid `tipo_alerta` and `uuid_arqueo` (for `diferencia_arqueo`) → success.
- (RED) INSERT `alerta` with `tipo_alerta='diferencia_arqueo'` but `uuid_arqueo IS NULL` → `ALERTA_ARQUEO_REQUIRED` validation error.
- (RED) INSERT `alerta` with `tipo_alerta='manual'` but `uuid_arqueo IS NOT NULL` → `ALERTA_ARQUEO_NOT_ALLOWED` validation error (consistency check).
- (RED) INSERT `alerta` with `tipo_alerta NOT IN ENUM` → `INVALID_TIPO_ALERTA` (DB CHECK constraint).
- (RED) UPDATE `prod.alerta` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.alerta` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Workflow chain: root `uuid_alerta_padre=NULL, estado='abierta'`; transition `uuid_alerta_padre=$root.uuid, estado='en_revision'`; terminal `uuid_alerta_padre=$revision.uuid, estado='resuelta'`.
- (RED) Chain-stable `tipo_alerta`: all rows of the same chain share the same `tipo_alerta`.
- (RED) Chain-stable `uuid_arqueo`: all rows of the same `diferencia_arqueo` chain share the same `uuid_arqueo`.
- (RED) State vigente query: `ORDER BY created_at DESC LIMIT 1` returns the latest chain row.
- (RED) `diferencia_arqueo` emission: tolerance exceeded → alerta emitted in same TX as arqueo INSERT; rollback on alerta failure → arqueo also rolls back.
- (RED) `branch_offline` emission: cron detects 24h gap → emits alerta; on first sync after reconnect, worker auto-resolves with `uuid_usuario=SYSTEM`.
- (RED) `sync_failure` emission: queue item with `intentos >= 10` marked `descartado` → alerta emitted; alert's `observaciones` contains `queue_uuid`, `tabla`, `uuid_registro`, `last_error`.
- (RED) `hash_chain_break` emission: verifier detects tampered row → alerta emitted; verifier self-audit uses skip-broken mode (does NOT extend broken chain).
- (RED) `login_lockout` emission: failed login count >= `max_intentos_login` → alerta emitted; user row marked `estado='bloqueado'` (new version).
- (RED) `manual` emission: operator with `permiso='crear_alerta_manual'` can POST; operator without permission → 403; admin can also POST with `tipo_alerta='fraude'`.
- (RED) Workflow transitions: admin with `permiso='triage_alerta'` can `/revisar` and `/resolver`; without permission → 403.
- (RED) `branch_offline` skips `en_revision`: auto-resolve inserts directly `abierta → resuelta`.
- (RED) Chain replication: cloud-origin chain rows (en_revision, resuelta) propagate to branch within 30s.
- (RED) Cross-branch dashboard: admin with multi-branch `sucursales_permitidas` sees alerts from all; admin with single-branch scope sees only that branch's alerts.
- (RED) RBAC enforcement: operator cannot triage alerts (no `permiso='triage_alerta'`); admin cannot emit `manual` alerts on branch they don't have scope for.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + ENUM type.
- [ ] F1.x `alerta_writer.py::write_alerta()` helper with ENUM + FK consistency validation.
- [ ] F1.x Recursive CTE query helper for chain resolution.
- [ ] IT-7.x: `api_sucursal/routers/alertas.py::POST /alertas` (operator manual emission, `tipo_alerta='manual'`).
- [ ] IT-7.x: `api_admin/routers/alertas.py::POST /alertas` (admin manual emission, `tipo_alerta IN ('manual', 'fraude')`).
- [ ] IT-7.x: `api_admin/routers/alertas.py::POST /alertas/{uuid}/revisar` (chain transition).
- [ ] IT-7.x: `api_admin/routers/alertas.py::POST /alertas/{uuid}/resolver` (terminal transition).
- [ ] IT-7.x: `api_admin/routers/alertas.py::GET /alertas` (paginated, filterable by tipo_alerta + estado + uuid_sucursal).
- [ ] IT-7.x: `api_admin/routers/alertas.py::GET /alertas/groups` (grouped counts by tipo_alerta + estado).
- [ ] IT-7.x: `api_admin/routers/alertas.py::GET /alertas/{uuid}/chain` (workflow chain view).
- [ ] IT-7.x: chain replication via parametrization push (cloud-origin rows propagate).
- [ ] IT-7.x: `arqueo_writer.py` integration — emit `diferencia_arqueo` on tolerance exceeded (T34 use case 7.2).
- [ ] IT-12.x: `workers/hash_chain_verifier/__main__.py` integration — emit `hash_chain_break` on detection.
- [ ] IT-12.x: `workers/branch_offline_detector/__main__.py` — emit `branch_offline` on 24h gap; `job_sync_cloud/drain_inbox` auto-resolves on first reconnect.
- [ ] IT-7.x: `parkos_core/auth/login_lockout_monitor.py` — emit `login_lockout` after N failed attempts; `usuarios` new version with `estado='bloqueado'`.
- [ ] IT-7.x: `parkos_core/sync/queue_processor.py` integration — emit `sync_failure` after 10 retries.
- [ ] IT-7.x: `web_sucursal/AlertaManualForm` (operator manual emission).
- [ ] IT-7.x: `web_admin/AlertasList` with grouped tabs by `tipo_alerta` + filtered list.
- [ ] IT-7.x: `web_admin/AlertasList/{uuid}/Detail` (single alert detail with chain + cross-references).
- [ ] Sprint 5: typed `uuid_referencia` columns (or polymorphic JSON) to replace `observaciones` text for `manual`/`fraude` references.
- [ ] Sprint 5: `alerta.uuid_referencia` typed FK with discriminator column (similar to `reclamos.uuid_reclamable` + `tipo_reclamable`).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Alert spam (high volume of low-severity alerts floods admin) | Med | Daily dedup per `tipo_alerta+uuid_sucursal`; quiet hours (sprint 5); per-admin notification preferences |
| Branch_offline false positive (legitimate maintenance window > 24h) | Low | Maintenance flag on `sucursal` row (sprint 5) exempts branch from offline detection |
| Manual alert `observaciones` text unsearchable / unstructured | Med | Sprint 5: `uuid_referencia_tipo` + `uuid_referencia` typed columns with discriminator |
| Worker auto-resolve `branch_offline` happens but the underlying issue was a different sync failure | Low | Worker resolves ONLY `branch_offline`; if branch reconnects AND has `sync_failure` alerts open, those remain open |
| Verifier INSERT extends a broken chain | Low | "skip-broken" mode: verifier INSERT references last known-good row's `hash_actual`, NOT the broken row |
| Chain-stable `tipo_alerta` violated (someone tries to transition `diferencia_arqueo` to `manual`) | Low | `alerta_writer` validates `tipo_alerta` matches parent chain row |
| Login lockout triggered by genuine user forgetting password (not brute force) | Med | Admin can manually unlock with motivo; lockout window is configurable; `observaciones` shows count |
| `login_lockout` alert for the same user multiple times per day | Low | Dedup check: only emit if no open alert exists for that `uuid_usuario` + `tipo_alerta` |
| Cross-tenant scope leak in admin alerts list (admin from chain A sees alerts from chain B) | Low | Backend enforces `uuid_sucursal IN ($admin.sucursales_permitidas)` filter on EVERY query |
| `alerta.uuid_arqueo` chain-stable enforcement breaks when admin forgets to copy | Low | `alerta_writer` API takes `uuid_arqueo` from root, propagates to all chain rows automatically |
| `dian_failure` alert for transient DIAN provider outage (not real failure) | Med | Retry policy before escalating to `alerta`; sprint 5: per-DIAN-provider circuit breaker |
| `impuesto_change_post_facturacion` alert: catalog change after facturacion creates alert retroactively | Low | Snapshot semantic: `factura_impuestos.porcentaje_aplicado` is the historical value; the alert is informational, not actionable. Admin may resolve immediately with `observaciones='informational: snapshot already captures historical value'`. |

## 12. Open Questions
- (a) Notification channel per `tipo_alerta`: email, SMS, in-app, PWA push? Sprint 5 (notification integration).
- (b) Should `diferencia_arqueo` chain-stay-open across multiple cierres (operator closes 3 shifts in a row with the same cash short, each triggers a separate alerta)? Current: each cierre is its own alerta (separate chain root). Sprint 5 may add "duplicate detection" to merge related alertas into a single investigation.
- (c) `cupo_rejected` alert: should this be a `tipo_alerta` (system signal that occupancy is at ceiling frequently) or should it remain a one-off `log_transaccional` event (current T04 use case 7.5)? Sprint 5 decision.
- (d) `pairing_replay` alert: when sync_agent token is replayed (T11), should it create an `alerta` (security event) or just a `log_transaccional` row? Sprint 5.
- (e) Auto-expiry of `en_revision` alerts (e.g., auto-resolve if no admin action in 7 days): sprint 5 may add a cron.
- (f) Should `alerta` support attachments (e.g., photo of damaged barrier)? Out of MVP scope; sprint 5+ with `documentos` integration.
- (g) Multi-tenancy: should admin see alerts from ALL branches (global) or only their `sucursales_permitidas`? Current: restricted to `sucursales_permitidas`.
- (h) Per-branch SLA on alert triage (e.g., admin must `en_revision` within 24h of emission): out of MVP scope; sprint 5 dashboards.
- (i) `impuesto_change_post_facturacion` trigger source: when admin updates `impuestos.porcentaje`, should the system retroactively emit alerts for all existing `factura_impuestos` rows with the old percentage? Currently informational only; sprint 5 may add retroactive scan.
- (j) `caja_baja` alert: when `caja.valor_efectivo` falls below a threshold (T33 monitoring). Currently emitted by a cron; sprint 5 may formalize threshold as a configuracion parameter.
