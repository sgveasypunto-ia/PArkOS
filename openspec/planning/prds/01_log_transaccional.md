# PRD: log_transaccional (T01)

> Append-only audit log of every business action. SHA256 hash chain per `uuid_sucursal`. The single source of truth for probatory integrity — every other table's history can be reconstructed from this table. **Mutation-only**: only INSERTs extend the chain. READS do NOT write log rows (per SOLID I — segregated concerns; per audit semantics: hash chain is integrity over writes, not queries).

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration_plan.md`](../iteration_plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I (segregated): reads do not write audit*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[A]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.log_transaccional`
- **SQL name**: `log_transaccional` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN); ampliable a 10 para acciones de facturación
- **Hash chain**: YES — SHA256 per `uuid_sucursal` (`hash_anterior` → `hash_actual`)
- **Origin**: F1 (schema + REVOKE + trigger + hash-chain genesis per `uuid_sucursal`) + IT-1 (sync_queue writes) + IT-3+ (every business action writes)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; READS do NOT extend chain per SOLID I)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_referencia` is a **polymorphic FK** (no DB constraint; application validates it points to a valid row in `tabla_afectada`). Used when one log is derived from another (e.g., anulación de una factura referencia al `anulaciones.uuid` original).
- `uuid_registro_afectado` is the UUID of the row in `tabla_afectada`.
- `uuid_usuario` is NOT NULL — for system events (hash_chain_verifier, dian_dispatcher, sync worker), a pre-seeded `usuarios.uuid='SYSTEM'` row is used.
- Same UUID travel rules: branch-side row travels verbatim to cloud via `sync_queue`; cloud-side row travels to branch via parametrization pull. UUID is the idempotency key for re-deliveries.

## 3. SOLID Atomic Breakdown
- **S**: "one auditable business action" — INSERT in same TX as the actual mutation.
- **O**: `datos_anteriores`/`datos_nuevos` JSON snapshots are extensible; new `accion` values added as the system grows.
- **I**: branch operator API (writes on every mutation); admin read API (`AuditDashboard`, reports — **read-only, never writes**); `hash_chain_verifier` worker (read-only verification, may write its own verifier audit row in a separate, independent TX).
- **D**: `parkos_core/audit/log_writer.py::write_log(accion, tabla, uuid_registro, uuid_usuario, datos_prev, datos_new, uuid_sucursal, uuid_referencia=None)` — the ONLY writer for business actions. Computes `hash_anterior = previous.hash_actual` per `uuid_sucursal` BEFORE insert; `hash_actual = SHA256(uuid + timestamp_registro + hash_anterior)`.
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. Same TX as the triggering mutation. **READS are not logged**: a SELECT against `log_transaccional` does NOT extend the chain. Only mutations (state changes) extend the chain.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_usuario` | `prod.usuarios.uuid` | exactly one (NOT NULL) | RESTRICT | the actor of the action |
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | hash-chain partitioning key |
| `uuid_registro_afectado` | polymorphic (no DB FK) | exactly one | n/a | UUID in `tabla_afectada` |
| `uuid_referencia` | polymorphic (no DB FK) | 0..1 | n/a | optional; links to origin event |

### Incoming FKs (heavy — every business table writes here)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (no FK references INTO log_transaccional; the relationship is one-way — this table is the audit sink for ALL other tables) | — | — | — |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `log_writer.py` in same TX as the triggering mutation |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | REVOKE + same trigger |

**Special rules**:
- Genesis row per `uuid_sucursal`: `hash_anterior = NULL`, `hash_actual = SHA256('{uuid_sucursal}||{created_at}||{payload}')`. Inserted once per branch at first boot. Inspected by `infra/docker/entrypoint.sh`.
- Every subsequent INSERT verifies `hash_anterior == previous.hash_actual` for the same `uuid_sucursal` BEFORE insert (in same TX). On mismatch: `HASH_CHAIN_BREAK` exception aborts the TX.
- `datos_anteriores` and `datos_nuevos` are JSON snapshots; NULL allowed for read-only events (e.g., `login_exitoso` is **a mutation**, so it writes with `datos_nuevos`; a SELECT against `log_transaccional` is **not a mutation** and writes nothing at all).
- DIAN retention: `fecha_retencion_hasta = created_at + dias_retencion_accion` (default 5 años; configurable por empresa).
- Partitioned by month via `pg_partman` on `created_at` (high-volume: ~200k–500k events/day per branch).
- Cloud-only `rol_admin_auditor` has `BYPASSRLS` for fraud investigations; its SELECTs do NOT extend the chain but the queries are recorded elsewhere (operational audit trail of `rol_admin_auditor` is a separate concern, out of MVP scope).

## 6. CodeGraph Dependencies
- `parkos_core/audit/log_writer.py::write_log()` (sole writer for business actions).
- `parkos_core/audit/hash_chain.py::compute_hash_anterior()` (helper).
- `api_admin/routers/audit.py::GET /audit/log` (cloud read API — **never writes**).
- `api_admin/routers/audit.py::GET /audit/log/{uuid_sucursal}/chain` (verify chain endpoint — read-only).
- `api_sucursal/routers/audit.py::GET /audit/log` (own-branch read API — **never writes**).
- `workers/hash_chain_verifier/__main__.py::verify_all_chains()` (nightly cron — writes its own audit row in a separate TX with `accion='chain_verification_ok'` or `'chain_verification_failed'`).
- `web_admin/AuditDashboard` (filterable by sucursal/tabla/usuario/fecha/chain_status).
- `web_sucursal/AuditView` (own-branch view, read-only).
- `job_sync_sucursal::drain_outbox_log` (pushes branch-origin logs to cloud).
- `job_sync_cloud::drain_inbox_log` (cloud receives + extends chain).

## 7. Use Cases enabled by this table

The `log_transaccional` table is the **probatory backbone of the entire parking-lot system**: every state-mutating action — operator creating an ingreso, admin assigning a permission, cloud assigning a DIAN `consecutivo`, the `hash_chain_verifier` running nightly — writes a row here, with the SHA256 chain extending per `uuid_sucursal`. **Mutation-only semantics**: only INSERTs extend the chain. READS do NOT write log rows. Use cases below describe how real parking-lot operations flow through this audit log, with **manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.log-transaccional.operator-arrival-writes-log`

**Actor**: operator

**Real-world action**: A casual driver arrives at the parking-lot booth. The operator types the plate and selects the vehicle type. The system records the ingreso **and** the corresponding audit row in a single TX so the chain advances atomically.

**Steps**:
1. Vehicle arrives at the booth. Operator opens `web_sucursal/IngresoForm`.
2. Operator **types the plate** (e.g., `ABC123`) into the `placa` input.
3. Operator **selects** `uuid_tipo_vehiculo` from the `tipos_vehiculo` dropdown.
4. Frontend POSTs `api_sucursal /ingresos` with `{placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente: null}`.
5. Backend opens a single TX; `SELECT last.log_transaccional.hash_actual FROM log_transaccional WHERE uuid_sucursal = $1 ORDER BY created_at DESC LIMIT 1` (this is the `hash_anterior`).
6. Backend SELECTs `cantidad_vehiculos_sucursal` for this `uuid_sucursal` + `uuid_tipo_vehiculo` to verify cupo disponible (see T04 use case `operator-cupo-rejected` for the failure path).
7. INSERT `ingreso` row (`estado='activo'` derived, `fecha_ingreso=NOW()`, `observaciones=null`).
8. Call `log_writer.write_log(accion='ingreso_creado', tabla='ingreso', uuid_registro=$ingreso_uuid, uuid_usuario=$operator_uuid, datos_anteriores=null, datos_nuevos={...ingreso snapshot}, uuid_sucursal=$sucursal_uuid)`.
9. `log_writer` INSERTs `log_transaccional` row with `hash_anterior=$last.hash_actual, hash_actual=SHA256(...)`.
10. `queue_processor.enqueue('ingreso', uuid, datos)` → INSERT `sync_queue` row (separately, also enqueue the log row for sync).
11. (Optional) Barrier opens if hardware enabled.
12. Return `{uuid, fecha_ingreso}` to the frontend.

**Tables touched (writes)**: `ingreso`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `tipos_vehiculo` (catalog), `cantidad_vehiculos_sucursal` (cupo check), `log_transaccional` (last hash), `sucursal` (tenant + chain key).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `ingreso.uuid`; `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`.

**Sync behavior**:
- Branch → cloud: YES, within 30s. The `ingreso` row and the `log_transaccional` row both travel via `sync_queue` (separate queue items, idempotent by UUID). Cloud receives, INSERTs both rows; cloud verifies the **incoming `hash_anterior`** matches the **cloud-side `last.hash_actual`** for that `uuid_sucursal`. Cloud preserves the branch chain verbatim, only extends with cloud-originated rows after.
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO (ingreso doesn't trigger DIAN; only facturación does).
- Hash chain impact: YES — extends the branch chain by one row AND the cloud chain by one row (the cloud chain receives the branch-originated row verbatim).

**Integration with other tables**:
- Reads from: `usuarios` (actor), `sucursal` (tenant + chain key), `log_transaccional` (last hash), `tipos_vehiculo` (catalog), `cantidad_vehiculos_sucursal` (cupo check), `ingreso` (the affected row, written in same TX).
- Writes to: `log_transaccional` (this row), `ingreso` (the business event), `sync_queue` (deferred propagation).
- Future FKs (after departure): `salidas`, `facturas`, `anulaciones` will each emit their own `log_transaccional` rows pointing back to `ingreso.uuid` via `uuid_referencia`.

### 7.2 Use Case: `uc.log-transaccional.cloud-dian-assigns-consecutivo`

**Actor**: dian_dispatcher

**Real-world action**: After a branch writes a business `facturas` row (offline mode with `numero_temporal`), the cloud receives it via sync, assigns the DIAN `consecutivo` atomically, INSERTs `factura_electronica`, AND emits the audit row in the same TX so the hash chain advances atomically.

**Steps**:
1. Cloud receives `facturas` row via `job_sync_cloud/poll_inbox` (polled every 30s).
2. Cloud opens the TX; `SELECT last.log_transaccional.hash_actual FROM log_transaccional WHERE uuid_sucursal = $1 ORDER BY created_at DESC LIMIT 1`.
3. `SELECT empresa FOR UPDATE` (atomic lock); `consecutivo_new = consecutivo_actual + 1`.
4. `UPDATE empresa SET consecutivo_actual = consecutivo_new`.
5. INSERT `factura_electronica` row (`uuid`, `consecutivo=$consecutivo_new`, `numero_oficial=FAC-$prefijo-$consecutivo_new`, `reportado_dian=false`).
6. Call `log_writer.write_log(accion='factura_electronica_creada', tabla='factura_electronica', uuid_registro=$uuid, uuid_usuario=$system_uuid, datos_anteriores=null, datos_nuevos={...snapshot}, uuid_sucursal=$sucursal_uuid, uuid_referencia=$factura_uuid)`.
7. `log_writer` INSERTs `log_transaccional` with `hash_anterior=$last.hash_actual, hash_actual=SHA256(...)`.
8. Enqueue `dian_dispatcher` to send to DIAN provider.
9. INSERT `SyncBackEvent` (concepto a modelar en sprint 5; payload esperado `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={uuid_factura_electronica, numero_oficial, consecutivo, reportado_dian=false}, timestamp}`) — branch polls for this and updates `facturas.uuid_factura_electronica` + `numero_oficial`.

**Tables touched (writes)**: `factura_electronica`, `empresa`, `log_transaccional`, `SyncBackEvent` (concept).
**Tables touched (reads)**: `facturas` (received from branch), `log_transaccional` (last hash), `empresa` (atomic lock), `clientes` (titular), `sucursal` (chain key).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid` (system user); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`; `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the originating `facturas` row was already enqueued and pushed.
- Cloud → branch: YES — `SyncBackEvent` flows back; branch polls and UPSERTs `facturas.uuid_factura_electronica` + `numero_oficial`.
- DIAN trigger: YES — `dian_dispatcher` queue picks up the `factura_electronica` and calls DIAN provider.
- Hash chain impact: YES — cloud extends the chain for this `uuid_sucursal` with a cloud-originated row (action='factura_electronica_creada'). The branch chain was NOT extended for this specific action — but it WAS extended earlier for `facturas` INSERT (in branch TX) and for `factura_electronica_creada` cloud INSERT (received via sync).

**Integration with other tables**:
- Reads from: `facturas` (received from branch), `empresa` (atomic `consecutivo_actual`), `log_transaccional` (last hash), `clientes` (titular), `sucursal` (chain key).
- Writes to: `empresa` (atomic increment), `factura_electronica` (the DIAN doc), `log_transaccional` (this audit row), `SyncBackEvent` (concept: cloud→branch signal).
- Related workflows: `dian_dispatcher` will INSERT ANOTHER `log_transaccional` row later with `accion='dian_aceptada'` once DIAN responds (separate TX, separate chain extension on cloud side).

### 7.3 Use Case: `uc.log-transaccional.branch-hash-chain-genesis`

**Actor**: system (entrypoint.sh on branch first boot)

**Real-world action**: First time a branch boots up, there are zero rows in `log_transaccional` for its `uuid_sucursal`. The bootstrap process must INSERT a genesis row with `hash_anterior=NULL` and `hash_actual=SHA256(uuid_sucursal || created_at || 'GENESIS')`. This row is the seed of the chain for that branch; all subsequent rows reference it via `hash_anterior=previous.hash_actual`.

**Steps**:
1. `infra/docker/entrypoint.sh` runs `parkos_core/audit/bootstrap_genesis.py` as the last step before `exec CMD`.
2. SELECT count of `log_transaccional` rows WHERE `uuid_sucursal=$self_branch AND hash_anterior IS NULL`.
3. If count == 0: this is first boot — proceed to step 4. If count == 1: chain already initialized, exit 0. If count > 1: PANIC (multiple genesis rows indicate tampering or bootstrap bug).
4. INSERT `log_transaccional` row (`accion='bootstrap_genesis'`, `tabla_afectada='log_transaccional'`, `uuid_registro_afectado=$self_branch_uuid`, `uuid_usuario=SYSTEM`, `datos_anteriores=null`, `datos_nuevos={marker: 'genesis', uuid_sucursal: $self_branch_uuid, boot_id: $boot_id}`, `hash_anterior=NULL`, `hash_actual=SHA256($self_branch_uuid || $created_at || 'GENESIS')`).
5. The row travels to cloud on first sync (`job_sync_sucursal/drain_outbox`); cloud receives it and INSERTs verbatim (cloud allows `hash_anterior IS NULL` only on the genesis row).
6. Cloud writes its OWN genesis row separately for the cloud-side chain of that branch (cloud has its own chain per `uuid_sucursal`, distinct from the branch chain — cloud chain starts empty for that branch and is built by receiving branch rows in order, then extending with cloud-originated rows after the highest branch row).

**Tables touched (writes)**: `log_transaccional` (1 row on branch + 1 row on cloud per uuid_sucursal).
**Tables touched (reads)**: `log_transaccional` (count check), `sucursal` (self uuid), `usuarios` (SYSTEM row).
**FKs traversed**: `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM).

**Sync behavior**:
- Branch → cloud: YES — the branch genesis row syncs to cloud on first `drain_outbox`.
- Cloud → branch: NO (cloud doesn't push genesis back).
- DIAN trigger: NO.
- Hash chain impact: YES — establishes the chain seed. `hash_anterior=NULL` is **only allowed on the genesis row**; every subsequent INSERT in that `uuid_sucursal` must verify `hash_anterior == previous.hash_actual` before accepting.

**Integration with other tables**:
- Reads from: `log_transaccional` (genesis check), `sucursal` (self uuid), `usuarios` (SYSTEM).
- Writes to: `log_transaccional` (genesis row, branch + cloud).
- Cross-cutting: the entrypoint aborts non-zero if genesis missing — this is a boot-blocking integrity check. A branch CANNOT operate without an established chain seed.

### 7.4 Use Case: `uc.log-transaccional.nightly-hash-chain-verifier`

**Actor**: verifier

**Real-world action**: A nightly cron runs in cloud and verifies the SHA256 hash chain for **every** `uuid_sucursal` in `log_transaccional`. If a row has been tampered with (or a gap exists), the verifier emits an `alerta` and a `log_transaccional` row that documents the detection.

**Steps**:
1. `workers/hash_chain_verifier/__main__.py` runs at 02:00 cloud time (cron).
2. SELECT DISTINCT `uuid_sucursal` from `log_transaccional` (active branches).
3. For each `uuid_sucursal`: recursive query to walk the chain from genesis to tip.
4. For each row in the chain: recompute `hash_actual_expected = SHA256(uuid + timestamp_registro + hash_anterior)`; compare to stored `hash_actual`.
5. If mismatch: collect the offending row UUID + the discrepancy.
6. After walking all branches: for each broken chain, INSERT `alerta` row (`tipo_alerta='hash_chain_break', estado='abierta', uuid_sucursal=$branch, valor_diferencia_efectivo=0, observaciones=$summary`, `uuid_alerta_padre=NULL` — root of the workflow chain).
7. INSERT `log_transaccional` (`accion='chain_verification_failed', tabla_afectada='log_transaccional', datos_nuevos={broken_uuids: [...]}, uuid_sucursal=$branch`) — the verifier's own audit row. **Important**: this verifier row uses "skip-broken" mode where `hash_anterior` references the **last known-good** row, NOT the broken row's `hash_actual`. Otherwise the verifier's own insert would fail the chain integrity check.
8. INSERT `sync_log` row with `{operaciones_enviadas=0, exitosas=0, fallidas=$broken_count, duracion_ms=...}`.
9. Alert appears in `web_admin/AlertasList` (red badge); admin triages manually (workflow `alerta` chain `abierta → en_revision → resuelta`).
10. If all chains intact: INSERT `log_transaccional` (`accion='chain_verification_ok'`) — happy path; chain extends normally.

**Tables touched (writes)**: `alerta`, `log_transaccional`, `sync_log`.
**Tables touched (reads)**: `log_transaccional` (every chain), `sucursal` (active branches).
**FKs traversed**: `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` (responsible) → `usuarios.uuid` (NULL until claimed); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference for subsequent transitions).

**Sync behavior**:
- Branch → cloud: NO (verifier runs in cloud; chains on branch DB are verified separately, see below).
- Cloud → branch: NO (alerts are cloud-only; branches don't need to know about chain integrity unless the broken row was branch-originated).
- DIAN trigger: NO.
- Hash chain impact: NO direct impact on the verified chains (verifier is read-only). However, the verifier's own audit rows DO extend the chain (each INSERT creates a new chain row) using skip-broken mode (see step 7).

**Integration with other tables**:
- Reads from: `log_transaccional` (every chain), `sucursal` (active branches).
- Writes to: `alerta` (on break), `log_transaccional` (verifier audit, skip-broken), `sync_log` (cycle metrics).
- Cross-cutting: this worker also verifies `revocacion_factura` chain (same `hash_chain_verifier` walks both tables; see T02 `uc.revocacion-factura.nightly-hash-chain-verifier`).
- Branch-side: a lighter verifier checks branch chain on every parametrization pull from cloud (per `infra/docker/entrypoint.sh`), so branches detect their own chain breaks between cloud visits.

### 7.5 Use Case: `uc.log-transaccional.admin-grants-permission-writes-log`

**Actor**: admin

**Real-world action**: Admin assigns a new permission (e.g., `aprobar_anulacion`) to an operador at a branch via `web_admin`. The `[V]` table update creates a new row version, archives the old, AND emits a `log_transaccional` row (one for the INSERT of the new version) — all in the same TX so the chain advances atomically.

**Steps**:
1. Admin opens `web_admin/UsuariosDetail/PermisosTab`, clicks `Add Permission`.
2. Selects `permiso='aprobar_anulacion'` from the `permisos` catalog dropdown.
3. Frontend POSTs `api_admin /permisos-usuario` with `{uuid_usuario, uuid_permiso, vigente_desde=NOW()}`.
4. Backend opens a TX; SELECT last hash for `uuid_sucursal=$branch_of_the_user` (the chain partition key is the branch where the operator works).
5. INSERT `permisos_usuario` row (new version, `vigente_desde=NOW(), vigente_hasta=NULL`).
6. Call `log_writer.write_log(accion='permiso_asignado', tabla='permisos_usuario', uuid_registro=$new_uuid, uuid_usuario=$admin_uuid, datos_anteriores=null, datos_nuevos={permiso_uuid, user_uuid, vigente_desde}, uuid_sucursal=$branch)`.
7. `log_writer` INSERTs `log_transaccional` (extends chain).
8. `queue_processor.enqueue('permisos_usuario', uuid, datos)` → parametrization pull will push to the assigned branch within 30s.
9. (No archive row yet — INSERT only; revocation comes later via UPDATE that creates a new revoked version.)

**Tables touched (writes)**: `permisos_usuario`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `permisos` (catalog), `usuarios` (target), `usuarios_sucursal` (find the user's branch for chain key), `sucursal` (chain key), `log_transaccional` (last hash).
**FKs traversed**: `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin who did it); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this write happens in cloud; the originating actor is cloud admin).
- Cloud → branch: YES — parametrization pull. Branch receives the new `permisos_usuario` row + the `log_transaccional` row (idempotent by UUID). Branch local chain is extended by the received row.
- DIAN trigger: NO.
- Hash chain impact: YES — both cloud chain (where the row originated) and branch chain (where it arrives via pull) extend by one row. Cloud computes its own chain link; branch receives the link and verifies against its local `last.hash_actual` before INSERT.

**Integration with other tables**:
- Reads from: `permisos` (catalog), `usuarios` (target user), `usuarios_sucursal` (which branch to push to), `sucursal` (chain key), `log_transaccional` (last hash).
- Writes to: `permisos_usuario` (the new row), `log_transaccional` (this audit row), `sync_queue` (cloud→branch parametrization).
- Related: when the operator later logs in at the branch, `require_permission('aprobar_anulacion')` checks `permisos_usuario` rows for that user (see T09 use case `operator-login-inherits-permissions`).

### 7.6 Use Case: `uc.log-transaccional.branch-sync-push-extends-cloud-chain`

**Actor**: sync worker

**Real-world action**: Branch has been offline for 4 hours and accumulated 200 `log_transaccional` rows. Internet comes back; the branch's `job_sync_sucursal/drain_outbox` pushes all 200 items to cloud via `/sync/push`. The cloud worker receives them in order, verifies the chain, and INSERTs them — extending the cloud-side chain for that `uuid_sucursal` by 200 rows in one batch.

**Steps**:
1. Branch `job_sync_sucursal/drain_outbox` fires every 30s; finds 200 items with `estado='pendiente'` and `tabla IN ('log_transaccional', 'ingreso', 'facturas', ...)`.
2. Worker groups by `uuid_sucursal` and posts each group to `api_admin /sync/push` with the sync_agent JWT.
3. Cloud `POST /sync/push` handler: for each item, validate idempotency (UUID-based; reject duplicates via `ON CONFLICT (uuid) DO NOTHING`).
4. For the `log_transaccional` rows in the batch: open a TX per row; SELECT last hash for that `uuid_sucursal` on the cloud side; verify `incoming_hash_anterior == cloud_last.hash_actual`.
5. If match: INSERT `log_transaccional` row verbatim (UUID, hash_anterior, hash_actual all preserved from branch).
6. If mismatch (out-of-order arrival, gap, or tampering): apply `sync_conflict` policy `manual` (insert `sync_conflict` row with `{tabla='log_transaccional', uuid_registro=$row, datos_local={...branch snapshot}, datos_cloud={...cloud last}, politica='manual', resolucion='pendiente'}`); INSERT `alerta tipo_alerta='sync_conflict_manual'`.
7. After all rows: UPDATE `sync_queue` rows (branch-side, separate endpoint) to `estado='exitoso'`; INSERT `sync_log` row (cloud-side, separate).
8. If `hash_anterior` was the chain genesis (`NULL`): it's the first row — special branch-first-boot logic (handled by `uc.log-transaccional.branch-hash-chain-genesis`).

**Tables touched (writes)**: `log_transaccional` (cloud-side extension), `sync_conflict` (on mismatch), `alerta` (on mismatch), `sync_log` (cycle metrics).
**Tables touched (reads)**: `sync_queue` (incoming batch), `log_transaccional` (last hash for verification), `usuarios` (actor JOIN for display), `sucursal` (chain key).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid` (the original branch operator); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (the originating branch); `sync_conflict.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — this is the entire point. Branch pushes, cloud receives.
- Cloud → branch: NO (this is branch→cloud direction).
- DIAN trigger: NO (sync of `log_transaccional` rows doesn't trigger DIAN; only `factura_electronica` does).
- Hash chain impact: YES — cloud chain extends for that `uuid_sucursal` by the number of rows in the batch. The chain preserves branch-originated rows verbatim; cloud only appends its own rows AFTER the highest branch-originated row.

**Integration with other tables**:
- Reads from: `sync_queue` (incoming batch), `log_transaccional` (last cloud-side hash for verification), `usuarios` (actor JOIN), `sucursal` (chain key).
- Writes to: `log_transaccional` (the extended chain), `sync_conflict` (on mismatch), `alerta` (on mismatch), `sync_log` (cycle metrics).
- Related: cloud receives `ingreso`, `facturas`, etc. rows in the SAME batch; each of those emits its own `log_transaccional` write (the chain extension here covers the log rows themselves, not the business rows).

### 7.7 Use Case: `uc.log-transaccional.rol-admin-auditor-bypass-rls-reads-no-chain`

**Actor**: admin (auditor role)

**Real-world action**: A fraud investigator with the `rol_admin_auditor` (separate from `rol_admin`; has `BYPASSRLS` for read access on `[A]` tables) opens `web_admin/FraudInvestigation`. They query `log_transaccional` for a specific `uuid_sucursal` looking for patterns: same operator logging masivo ingresos at 3am, or `datos_nuevos` showing tarifa modifications outside business hours. **Per SOLID I — segregated concerns, the READS do NOT extend the chain. Reads are not mutations; the audit log is integrity over writes, not queries.**

**Steps**:
1. Auditor opens `web_admin/FraudInvestigation` (separate role-based UI; not the standard `web_admin`).
2. Auditor queries `api_admin /audit/log?uuid_sucursal=$branch&tabla_afectada='ingreso'&fecha_desde=$start&fecha_hasta=$end`.
3. Backend connects as `rol_admin_auditor` (BYPASSRLS) — bypasses RLS policies but **does NOT bypass the `log_transaccional` REVOKE/trigger** because that's a REVOKE on `rol_app`, not RLS. Auditor SELECTs only.
4. Backend paginates with cursor; returns the rows. NO `log_transaccional` INSERT is performed for the SELECT itself.
5. Auditor drills into a specific row, sees `datos_anteriores`/`datos_nuevos` JSON snapshots.
6. If auditor finds a suspicious pattern (e.g., an `ingreso_creado` row with `uuid_usuario=$operator_X` at 3am): auditor clicks `Flag`, which opens an `alerta` workflow with `tipo_alerta='fraud_investigation'` — that **IS** a mutation and writes a `log_transaccional` row.
7. Auditor's own investigation actions (open alerta, attach notes) are audited under a SEPARATE operational audit table (out of MVP scope) — NOT in `log_transaccional`. This is the deliberate separation: `log_transaccional` integrity chain = business mutations; operational audit = auditor actions (separate concern, separate storage).

**Tables touched (writes)**: NONE for the read itself. If auditor opens an `alerta`: `alerta` (W) + `log_transaccional` (W, one row for the alerta creation).
**Tables touched (reads)**: `log_transaccional` (queried rows, BYPASSRLS), `usuarios` (actor JOIN), `sucursal` (chain key), `alerta` (if flagging).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic).

**Sync behavior**:
- Branch → cloud: NO (this is a cloud-only read; the auditor query doesn't mutate state on branches).
- Cloud → branch: NO (audit query is read-only).
- DIAN trigger: NO.
- Hash chain impact: **NO** — the SELECT itself does NOT extend the chain. The chain extends ONLY if the SELECT triggers a downstream mutation (e.g., flagging via `alerta`). Per SOLID I (segregated concerns): reads and writes are distinct operations; one is logged only if the other is also a write.

**Integration with other tables**:
- Reads from: `log_transaccional` (queried rows, BYPASSRLS), `usuarios` (actor JOIN), `sucursal` (tenant).
- Writes to: NONE for the read. If downstream mutation: `alerta` + `log_transaccional` (the alerta creation itself is a mutation).
- Cross-cutting: this is the canonical example of the **read/write separation in the audit log**. A naive implementation that writes `log_transaccional` rows on every read would explode log volume (per the open question a in section 12). The current design is **mutation-only**: reads are free, writes are logged atomically in the same TX as the mutation they describe.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (partitioning via `pg_partman`), 3 (hash-chain triggers), 4 (audit middleware — every mutation goes through `log_writer`), 5 (RBAC + BYPASSRLS for auditor), 6 (cloud API + branch API), 7 (DIAN retention logic), 10 (branch sync worker), 11 (cloud sync worker), 13 (web_admin AuditDashboard), 14 (web_sucursal AuditView), 15 (alerting), 17 (compliance reports), 20 (metrics), 24 (DIAN compliance docs), 28 (operational dashboards), 30 (hash_chain_verifier worker), 31 (security audit), 33 (DIAN compliance docs), 38 (multi-tenant boundaries).

## 9. RED Tests
- (RED) INSERT `log_transaccional` from `rol_app` with `hash_anterior` matching previous → success.
- (RED) INSERT with `hash_anterior != previous.hash_actual` → `HASH_CHAIN_BREAK` exception.
- (RED) `UPDATE prod.log_transaccional SET datos_nuevos='{}'` → `AUDIT_FIRST_INMUTABLE`.
- (RED) `DELETE FROM prod.log_transaccional` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Branch DB INSERT with `hash_anterior=NULL` after genesis → `HASH_CHAIN_BREAK` (only genesis row can have NULL).
- (RED) Genesis row per `uuid_sucursal`: missing → boot fails with `HASH_CHAIN_GENESIS_MISSING` (entrypoint checks).
- (RED) Multiple genesis rows per `uuid_sucursal` → `HASH_CHAIN_DUPLICATE_GENESIS` PANIC.
- (RED) Hash chain verifier detects tampering: manually UPDATE `hash_actual` of one row (bypassing REVOKE via `rol_admin_auditor`); verifier emits `alerta tipo_alerta='hash_chain_break'`.
- (RED) Cloud receives branch-origin log with stale `hash_anterior` → `sync_conflict` row created (policy `manual`) + `alerta`.
- (RED) `log_writer` writes within same TX as the business mutation: rollback the business mutation → log row also rolls back (no orphan audit).
- (RED) `datos_anteriores`/`datos_nuevos` JSONB columns accept any shape; `accion` is free text but constrained by ENUM check.
- (RED) **Read does NOT write log**: admin GETs `/audit/log` → response paginated; admin-only auth; operador JWT → 401. The GET itself does NOT trigger any `log_transaccional` INSERT.
- (RED) Auditor `rol_admin_auditor` BYPASSRLS can SELECT `[A]` tables including `log_transaccional`; the SELECT does NOT extend the chain.
- (RED) Auditor with BYPASSRLS still cannot UPDATE/DELETE `log_transaccional` (REVOKE is on `rol_app`, not RLS) — UPDATE attempt → `AUDIT_FIRST_INMUTABLE`.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + `pg_partman` partition + hash-chain genesis per `uuid_sucursal`.
- [x] F1.x `log_writer.py::write_log()` helper.
- [ ] IT-1.x: `job_sync_sucursal/drain_outbox_log` — branch pushes log rows within 30s.
- [ ] IT-1.x: `job_sync_cloud/drain_inbox_log` — cloud receives, verifies hash, INSERTs.
- [ ] IT-1.x: `api_admin/routers/audit.py::GET /audit/log` (paginated, cursor-based; **read-only, never writes**).
- [ ] IT-1.x: `api_admin/routers/audit.py::GET /audit/log/{uuid_sucursal}/chain` (verify endpoint, read-only).
- [ ] IT-12.x: `workers/hash_chain_verifier/__main__.py::verify_all_chains()` nightly cron with skip-broken mode.
- [ ] IT-12.x: `web_admin/AuditDashboard` with chain-status badge per branch (read-only view).
- [ ] IT-12.x: emit `alerta tipo_alerta='hash_chain_break'` on detection.
- [ ] IT-12.x: separate `rol_admin_auditor` for fraud investigation with BYPASSRLS.
- [ ] Sprint 5: model `SyncBackEvent` as concrete table or queue channel (current: concepto documentado en use cases 7.2, 7.6).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Hash chain break on partial sync (out-of-order arrival) | Med | Per-branch monotonic seq in `datos` JSON; cloud worker applies strictly in-order; `sync_conflict` on mismatch |
| Genesis row missing on first branch boot | Low | `infra/docker/entrypoint.sh` checks `prod.log_transaccional WHERE uuid_sucursal=$X AND hash_anterior IS NULL` exists; aborts boot if missing |
| Multiple genesis rows per branch | Low | entrypoint aborts if count > 1 |
| Cloud-originated row breaks branch chain | Low | Cloud appends ONLY AFTER the highest branch-originated row; explicit "cloud-originated" flag in payload |
| `datos_anteriores`/`datos_nuevos` JSON grows unbounded | Low | JSONB compression; retention purges after `fecha_retencion_hasta` |
| Verifier INSERT extends a broken chain | Low | "skip-broken" mode: INSERT references last known-good row, not the broken row's `hash_actual` |
| Read audit flood if naively implemented | Med | **SOLID I separation**: reads do NOT write log rows. Only mutations extend the chain. |
| Auditor with BYPASSRLS bypasses RLS but not REVOKE | Low | Documented; auditor cannot UPDATE/DELETE (REVOKE on rol_app remains in force); any auditor SELECT leaves no log trace by design |
| SyncBackEvent not modeled yet (concept only) | Med | Document expected payload in use cases 7.2 and 7.6; sprint 5 task to materialize as concrete table or queue channel |

## 12. Open Questions
- (a) ~~Read-audit policy~~ **RESOLVED**: reads do NOT write `log_transaccional` per SOLID I (segregated concerns). Only mutations extend the chain. Auditor actions are out of MVP scope for operational audit.
- (b) `datos_anteriores`/`datos_nuevos` schema versioning: today free JSONB; do we need a Pydantic v2 model per `accion` to enforce shape?
- (c) Multi-region cloud (latency): if cloud spans regions, does each region have its own chain or one global chain per `uuid_sucursal`?
- (d) Branch-side verifier on every boot? Current: cloud-only nightly + lighter parametrization-pull check on branch boot.
- (e) Operational audit table for `rol_admin_auditor` actions — out of MVP scope; revisit if fraud investigation volume grows.
- (f) `SyncBackEvent` materialization: concrete table vs queue channel vs webhook; sprint 5 decision.