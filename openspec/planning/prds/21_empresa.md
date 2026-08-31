# PRD: empresa (T21)

> **CLOUD-ONLY SINGLETON** — corporate identity (NIT, regimen, resolución DIAN, prefijo, rango desde/hasta, consecutivo_actual). Sole owner of DIAN numeration. Branches NEVER write to `empresa`; they receive a read-only mirror via parametrization pull. `consecutivo_actual` is the ONLY atomic counter in the entire system — incremented by cloud `dian_dispatcher` inside the TX of `factura_electronica` creation, serialized via `SELECT FOR UPDATE`. Versioned via `vigente_desde` / `vigente_hasta` for `info`/`datos` JSON changes (admin updates).

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration_plan.md)
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
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.empresa`
- **SQL name**: `empresa` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite (singleton corporate identity)
- **Atomic counter**: `consecutivo_actual` (atomic BigInteger, ONLY mutated by cloud `dian_dispatcher`)
- **Origin**: F1 (schema, singleton seeded) + IT-2 (writes)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 6 use cases covering cloud-only singleton, atomic consecutivo_actual, branch read-only mirror, version flow, concurrent serialization, and rango_agotado 409)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. Singleton: one row only.

## 3. SOLID Atomic Breakdown
- **S**: "one corporate identity" (NIT, regimen, resolución DIAN).
- **O**: new columns via migration.
- **I**: admin CRUD (singleton).
- **D**: `parkos_core/models/V/empresa.py`.
- **Atomic**: INSERT (initial), UPDATE (archive old + create new), special atomic `consecutivo_actual` mutation.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | singleton |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | empresa is read but not FK-referenced (branches JOIN it for corporate data) |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Singleton seed |
| UPDATE | YES | Inside TX + `log_transaccional` |
| `consecutivo_actual` increment | YES | `SELECT FOR UPDATE` in same TX as `factura_electronica` insert |
| DELETE | NO | Archive |

## 6. CodeGraph Dependencies
- `api_admin/routers/empresa.py`.
- `parkos_core/dian/cloud/atomic_next_consecutivo.py`.

## 7. Use Cases enabled by this table

The `empresa` table is the **cloud-only corporate singleton** that owns the entire DIAN numeration. EVERY e-factura ever issued by the entire parking-lot chain derives its `consecutivo` from this table's `consecutivo_actual` counter. The counter is atomic (`SELECT FOR UPDATE` serializes concurrent cloud workers) and is the only mutable field outside the versioning flow (`vigente_desde` / `vigente_hasta`). Branches NEVER write to `empresa` — they receive a read-only mirror via parametrization pull (use case 7.3). Use cases below describe the singleton lifecycle (boot seed, atomic increment on facturacion, parametrization mirror, admin version flow, concurrent serialization, and the `rango_agotado` safety gate). **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.empresa.cloud-boot-seeds-singleton`

Cloud container first boot. The `infra/docker/entrypoint.sh` for the cloud side checks if `empresa` row exists. If not, INSERT with `consecutivo_actual=0`, `rango_desde=0`, `rango_hasta=0` (admin must load real range before first DIAN dispatch), `info` JSON empty, `datos` JSON empty. Then INSERT the genesis `log_transaccional` row (cloud chain needs its first link for cloud-global writes). This is a hard boot gate — cloud cannot receive business facturas until `empresa` exists.

**Actor**: system (cloud `infra/docker/entrypoint.sh`)

**Pre-conditions**: cloud Postgres is up; `log_transaccional` genesis row per `uuid_sucursal` is seeded (T01 use case 7.3); `prod.empresa` table is empty.

**Steps**:
1. `entrypoint.sh` runs `parkos_core/dian/cloud/seed_empresa_singleton.py` after `alembic upgrade head` and REVOKE/trigger verifier, before `exec CMD`.
2. Backend SELECTs `COUNT(*) FROM empresa WHERE vigente_hasta IS NULL`. If 0 → first boot. If 1 → already seeded, exit 0. If > 1 → PANIC (multiple singletons indicates migration bug or tampering).
3. Backend opens TX. INSERT `empresa` row (`uuid=server-generated`, `nombre='easypunto_parkos_demo'`, `nit='900000000-0'`, `regimen='simplificado'`, `resolucion_facturacion=''`, `prefijo_factura='FAC'`, `rango_desde=0`, `rango_hasta=0`, `consecutivo_actual=0`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`). Singleton UNIQUE partial index `(vigente_hasta IS NULL)` enforces at most one active row.
4. SELECT chain anchor from `log_transaccional` for the admin's primary branch `uuid_sucursal=$admin_primary_branch` (cloud-global writes use the admin's branch as chain key per the convention established in T01/T14; alternative is a synthetic `CLOUD_ROOT` sentinel — sprint 5 decision).
5. INSERT `log_transaccional` (`accion='empresa_seeded'`, `tabla_afectada='empresa'`, `uuid_registro_afectado=$empresa_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=null`, `datos_nuevos={nombre, nit, regimen, prefijo, rango_desde, rango_hasta, consecutivo_actual}`).
6. Backend INSERTs a startup `sync_log` row noting the singleton seed event (cycle metrics for the parametrization round).
7. Backend returns the new `empresa.uuid` to the entrypoint script.
8. Entrypoint stores the `empresa.uuid` in the cloud's runtime config (`/etc/parkos/empresa_uuid`) for fast lookup by `dian_dispatcher`.
9. Admin sees a yellow banner in `web_admin/Dashboard` advising "Load DIAN resolution before first dispatch" until admin PATCHes `rango_desde`/`rango_hasta`.
10. Until admin loads a real range, every `/facturas/procesar` call returns 409 `rango_no_cargado` (use case 7.6 extension).

**Tables touched (writes)**: `empresa` (1 row), `log_transaccional` (1 row), `sync_log` (1 row).
**Tables touched (reads)**: `empresa` (count check), `log_transaccional` (chain anchor), `usuarios` (SYSTEM lookup), `sucursal` (admin primary branch lookup).
**FKs traversed**: `empresa` has NO outgoing FKs (singleton). `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (admin primary branch); `log_transaccional.uuid_registro_afectado` (polymorphic) → `empresa.uuid`; `sync_log.uuid_sucursal` → `sucursal.uuid` (admin primary branch).
**Sync behavior**:
- Branch → cloud: NO (this is cloud-bootstrap).
- Cloud → branch: YES — `empresa` row is enqueued for parametrization pull; all active branches receive it as read-only mirror (use case 7.3) within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row for the admin's primary branch `uuid_sucursal`.
**Integration**:
- Reads from: `empresa` (count check), `log_transaccional` (chain anchor), `usuarios` (SYSTEM), `sucursal` (admin primary branch).
- Writes to: `empresa` (the singleton), `log_transaccional` (genesis for cloud-global writes), `sync_log` (boot cycle metrics), parametrization `sync_queue` for branches.
- Cross-cutting: the cloud cannot serve `/facturas/procesar` without `empresa` seeded. `entrypoint.sh` aborts non-zero if seed fails — this is a boot-blocking integrity check.

### 7.2 Use Case: `uc.empresa.cloud-atomic-consecutivo-increment-on-facturacion`

Cloud receives a business `facturas` row from a branch (either synchronously via online `/facturas/procesar` or asynchronously via sync after offline branch reconnect). Cloud opens a TX, takes an atomic lock on `empresa`, computes `consecutivo_new = consecutivo_actual + 1`, UPDATEs the counter, INSERTs `factura_electronica` with the new consecutivo, and emits `SyncBackEvent` for the branch. **The lock + increment + e-factura INSERT are atomic** — if the cloud process crashes mid-TX, the counter is rolled back and the next `/facturas/procesar` retries from the same starting number (DIAN accepts gaps only if explicitly logged; the rollback is logged as `log_transaccional accion='consecutivo_rollback'`).

**Actor**: dian_dispatcher (cloud worker, triggered by `/facturas/procesar` online or by `job_sync_cloud/drain_inbox_facturas`)

**Pre-conditions**: `empresa` is seeded (use case 7.1); `rango_desde > 0` (admin loaded real range); `consecutivo_actual <= rango_hasta` (gate, use case 7.6 if exceeded); branch has inserted a `facturas` row locally and either POSTed online or pushed via sync.

**Steps**:
1. Cloud handler opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch` (where the originating factura is).
2. `SELECT empresa WHERE uuid=$empresa_uuid FOR UPDATE` — acquires the atomic row lock. ANY concurrent cloud worker calling `/facturas/procesar` for ANY branch waits at this point.
3. Compute `consecutivo_new = consecutivo_actual + 1`. If `consecutivo_new > rango_hasta`: ROLLBACK, return 409 `rango_agotado` (use case 7.6), no e-factura written, INSERT `alerta tipo_alerta='rango_agotado'`.
4. UPDATE `empresa SET consecutivo_actual = $consecutivo_new` (still under lock).
5. INSERT `factura_electronica` (`uuid`, `uuid_sucursal=$branch`, `uuid_factura=$factura_uuid`, `uuid_cliente=$cliente_uuid OR consumidor_final_default`, `reportado_dian=false`, `descuento=$factura_descuento`, `consecutivo=$consecutivo_new`, `estado='activa'`, `fecha_retencion_hasta=$created_at + 5_years`).
6. INSERT `log_transaccional` (`accion='consecutivo_asignado'`, `tabla_afectada='empresa'`, `uuid_registro_afectado=$empresa_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_anteriores={consecutivo_actual: $old}`, `datos_nuevos={consecutivo_actual: $new, uuid_factura_electronica: $uuid_e}`).
7. INSERT `log_transaccional` (`accion='factura_electronica_creada'`, `tabla_afectada='factura_electronica'`, `uuid_registro_afectado=$uuid_e`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `uuid_referencia=$factura_uuid`, `datos_anteriores=null`, `datos_nuevos={consecutivo, uuid_factura, reportado_dian: false}`).
8. COMMIT. Lock releases. Concurrent workers proceed serially.
9. Enqueue `dian_dispatcher` task to send the e-factura to DIAN provider.
10. INSERT `SyncBackEvent` (concepto a modelar en sprint 5; payload `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={uuid_factura_electronica, numero_oficial, consecutivo, reportado_dian: false}, timestamp}`).
11. Return `{uuid_factura_electronica, numero_oficial, consecutivo}` synchronously (online) or queue for branch poll (offline).

**Tables touched (writes)**: `empresa` (atomic UPDATE), `factura_electronica` (INSERT), `log_transaccional` (2 rows), `SyncBackEvent` (concept), possibly `dian_dispatcher` queue.
**Tables touched (reads)**: `empresa` (SELECT FOR UPDATE), `facturas` (received from branch), `clientes` (titular or consumidor_final default), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `empresa` (no outgoing FKs, but INCOMING from this UPDATE). `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`; `factura_electronica.uuid_sucursal` → `sucursal.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `empresa.uuid` (first row) or `factura_electronica.uuid` (second row); `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`.
**Sync behavior**:
- Branch → cloud: YES — the originating `facturas` row was already enqueued and pushed (or POSTed online); idempotent on retry.
- Cloud → branch: YES — `SyncBackEvent` flows back; branch UPSERTs `facturas.uuid_factura_electronica` + `numero_oficial`, clears preliminar badge.
- DIAN trigger: YES — `dian_dispatcher` picks up the e-factura after this TX commits.
- Hash chain impact: YES — cloud chain extends by 2 rows for the branch `uuid_sucursal`. Branch chain extends when sync-back is processed (the receipt of `factura_electronica` is itself a state mutation logged on branch).
**Integration**:
- Reads from: `empresa` (atomic lock), `facturas` (received), `clientes` (titular), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `empresa` (atomic UPDATE), `factura_electronica` (the DIAN doc), `log_transaccional` (2 audit rows), `SyncBackEvent` (concept), `dian_dispatcher` queue.
- Cross-cutting: the atomic counter is the **DIAN numeration integrity backbone**. Two concurrent workers cannot produce the same consecutivo — guaranteed by the row lock. The lock is held for the duration of the TX (milliseconds), not for the duration of the entire DIAN dispatch.
- Related: T02 (`revocacion_factura`) is the counterpart — when an e-factura is revoked, no consecutivo is consumed; the next factura uses `consecutivo_actual + 1` regardless.

### 7.3 Use Case: `uc.empresa.branch-read-only-mirror-via-parametrization`

Branch boots up (or receives parametrization pull) and needs to know the corporate identity to render tickets, receipts, and resolve `empresa.prefijo_factura` for ticket numbering on the branch UI. Branch receives `empresa` via parametrization pull and UPSERTs the row locally (read-only mirror — branch NEVER writes to `empresa`). The local row is used for display purposes (prefijo on printed tickets, NIT on receipts, mensaje_bienvenida on ingreso confirmation); branch NEVER sources the `consecutivo_actual` from its local row — it asks cloud for the real one via `/facturas/procesar`.

**Actor**: sync worker (cloud parametrization worker → branch parametrization receiver)

**Pre-conditions**: branch is paired (has a valid `sync-agent-` JWT); cloud has the `empresa` row vigente (use case 7.1 or 7.4); branch has completed its genesis chain bootstrap.

**Steps**:
1. Cloud parametrization worker fires every 30s; detects `empresa` row changes (via `sync_queue` with `tabla='empresa'` and new UUID since last pull).
2. Worker POSTs `api_sucursal /sync/parametrization/pull` with `{tablas: ['empresa']}` (the `sync-agent-` JWT authenticates the pull).
3. Branch handler receives the pull; opens TX.
4. Branch SELECTs the local `empresa` row (typically 0 or 1 — never write on branch). Compares `cloud.uuid + version_hash` against the local row.
5. Branch UPSERTs `empresa` row locally (INSERT if missing, UPDATE if hash differs). The UPDATE only touches display fields (`prefijo_factura`, `mensaje_bienvenida`, `mensaje_salida`, `nombre`, `nit`); `consecutivo_actual` is OVERWRITTEN with the cloud value BUT is never used by branch logic (only by cloud).
6. Branch INSERTs `log_transaccional` (`accion='empresa_mirror_updated'`, `tabla_afectada='empresa'`, `uuid_registro_afectado=$empresa_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_anteriores=$local_snapshot`, `datos_nuevos=$cloud_snapshot`). The local chain extends — this is a parametrization write on the branch side.
7. Branch `queue_processor.ack` the parametrization pull; INSERT `sync_log` row with `operaciones_exitosas=1, duracion_ms=...`.
8. Branch UI (`web_sucursal/IngresoForm` confirmation, `web_sucursal/FacturacionForm` ticket header) now renders with the latest `prefijo_factura` (e.g., `FAC-`).
9. Operator in `web_sucursal` may click "Ver datos empresa" to inspect the local mirror; system shows: "Esta es una copia. Para cambios, contacte al admin cloud".

**Tables touched (writes)**: `empresa` (UPSERT, branch local), `log_transaccional` (1 row), `sync_log` (1 row).
**Tables touched (reads)**: `empresa` (local + cloud via parametrization), `log_transaccional` (chain anchor), `usuarios` (SYSTEM), `sucursal` (self).
**FKs traversed**: `empresa` has NO FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (the branch); `log_transaccional.uuid_registro_afectado` (polymorphic) → `empresa.uuid`.
**Sync behavior**:
- Branch → cloud: NO (branch does NOT push `empresa` writes; it only RECEIVES them).
- Cloud → branch: YES — parametrization pull delivers the `empresa` row to all active branches within 30s of any cloud-side change (seed use case 7.1, version update use case 7.4).
- DIAN trigger: NO (mirror update doesn't trigger DIAN).
- Hash chain impact: YES — branch chain extends by 1 row per parametrization receipt (the receipt itself is a state mutation logged locally).
**Integration**:
- Reads from: `empresa` (cloud source via parametrization), `log_transaccional` (chain anchor), `usuarios` (SYSTEM), `sucursal` (self).
- Writes to: `empresa` (local mirror), `log_transaccional` (parametrization receipt audit), `sync_log` (cycle metrics).
- Cross-cutting: this is the canonical "cloud-owned, branch-mirrored" pattern. Branch display uses the local row but cannot mutate the corporate identity. The `consecutivo_actual` mirror is purely informational on the branch — branch NEVER uses it to assign numbers (only cloud does, via `SELECT FOR UPDATE` in use case 7.2).
- Related: branches receiving an updated `prefijo_factura` after admin PATCH must update their ticket-print templates; this is a frontend concern handled in `web_sucursal/print_templates/`.

### 7.4 Use Case: `uc.empresa.admin-updates-info-versioned`

Cloud admin updates the corporate identity via `web_admin/EmpresaForm` — change of `regimen`, `mensaje_bienvenida`, `resolucion_facturacion` (when DIAN assigns a new resolution number), `prefijo_factura`, `rango_desde`/`rango_hasta` (when loading a new range after old one exhausts). The update creates a NEW version row (archive old with `vigente_hasta=NOW()`, INSERT new with `vigente_desde=NOW()`, `vigente_hasta=NULL`). Parametrization push delivers the new version to all branches. The `consecutivo_actual` is NOT touched by this flow (it has its own atomic update mechanism, use case 7.2).

**Actor**: admin (cloud)

**Pre-conditions**: `empresa` is seeded (use case 7.1); admin has `permiso='actualizar_empresa'`; the change is non-trivial (NIT, regimen, resolución, prefijo, rango).

**Steps**:
1. Admin opens `web_admin/EmpresaForm`, edits fields (e.g., `prefijo_factura='FE'` (was 'FAC'), `resolucion_facturacion='18764000012345'`, `rango_desde=1000`, `rango_hasta=5000`).
2. Admin confirms. Frontend PATCHes `api_admin /empresa` (admin- JWT) with `{prefijo_factura, resolucion_facturacion, rango_desde, rango_hasta, vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario` for `permiso='actualizar_empresa'`; rejects 403 if missing.
4. Backend SELECTs the current vigente `empresa` row (`vigente_hasta IS NULL`); locks it with `SELECT FOR UPDATE` to serialize concurrent admin edits.
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. UPDATE current vigente row SET `vigente_hasta=$now` (archives old version). The archived row preserves the historical identity for re-audit.
7. INSERT new `empresa` row (`uuid=server-generated`, same business fields except the updates, `vigente_desde=$now`, `vigente_hasta=NULL`, `estado='activo'`). The UNIQUE partial index on `(vigente_hasta IS NULL)` enforces the singleton.
8. INSERT `log_transaccional` (`accion='empresa_actualizada'`, `tabla_afectada='empresa'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=$old_snapshot`, `datos_nuevos=$new_snapshot`). The audit row preserves old vs new for probatory integrity.
9. `queue_processor.enqueue('empresa', $new_uuid, $new_snapshot)` → parametrization push for all active branches within 30s.
10. The archived old row also needs to be delivered to branches as `vigente_hasta=$now` (idempotent — branch UPSERTs). Enqueue 2nd parametrization item.
11. Backend returns `{new_uuid, old_uuid_archived, vigente_desde}` to frontend.
12. Branch receives parametrization (per use case 7.3): UPSERT new row, UPDATE local old row with `vigente_hasta=$now`. The local mirror reflects the new corporate identity.
13. Next `FacturacionForm` at branch uses new `prefijo_factura` for ticket numbering; new `rango_desde`/`rango_hasta` is propagated.
14. Next `/facturas/procesar` at cloud (use case 7.2) uses the new vigente row for the atomic counter increment. The `consecutivo_actual` from the old version is COPIED to the new version (preserved across versions).

**Tables touched (writes)**: `empresa` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items: new + archive).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `empresa` (current vigente), `log_transaccional` (chain anchor), `usuarios` (admin actor), `sucursal` (admin primary branch).
**FKs traversed**: `empresa` has NO FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `empresa.uuid`.
**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO (the change itself doesn't dispatch; only the next `factura_electronica` creation uses the new range).
- Hash chain impact: YES — cloud chain extends by 1 row (empresa_actualizada); each branch chain extends by 1 row when parametrization is received (per use case 7.3).
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `empresa` (current vigente), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `empresa` (archive old + insert new), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: this is the canonical `[V]` versioning pattern for singletons. Unlike `tarifas_sucursal` (T14 use case 7.1) which has multiple vigentes per (sucursal, tipo_vehiculo, tipo_tarifa) tuple, `empresa` has exactly ONE vigente at any time (singleton). The UNIQUE partial index enforces this.
- Related: changing `rango_hasta` does NOT reset `consecutivo_actual` — the counter is preserved across versions. If admin reduces `rango_hasta` below `consecutivo_actual`, the system warns but allows it (admin override; `/facturas/procesar` will return 409 `rango_agotado` going forward until a new range is loaded).

### 7.5 Use Case: `uc.empresa.cloud-concurrent-facturacion-serialized`

Two cloud workers receive `facturas` simultaneously (e.g., one from online `/facturas/procesar` for Branch A, one from `job_sync_cloud/drain_inbox_facturas` for Branch B's offline queue). Both attempt to acquire `empresa` FOR UPDATE. The row lock serializes them: Worker A acquires first, computes `consecutivo=N+1`, UPDATEs, INSERTs e-factura, COMMITs. Worker B wakes from the wait, re-reads `consecutivo_actual` (now `N+1`), computes `N+2`, UPDATEs, INSERTs e-factura, COMMITs. Result: zero race, zero duplicate consecutivo, zero gap (atomic TX).

**Actor**: dian_dispatcher (two concurrent cloud workers, A and B)

**Pre-conditions**: `empresa` is seeded (use case 7.1); `rango_desde > 0`; `consecutivo_actual <= rango_hasta`; both workers have valid business `facturas` to process (one synchronous, one sync-async).

**Steps**:
1. **T=0**: Worker A receives online `/facturas/procesar` for Branch A. Worker B receives offline sync queue item for Branch B. Both open TXs simultaneously.
2. **T=0+ε**: Worker A executes `SELECT empresa FOR UPDATE`. Lock acquired (state: `consecutivo_actual=N`). Worker B executes the same SELECT. BLOCKS — waits for Worker A's lock.
3. Worker A: `consecutivo_new = N + 1`. UPDATE `empresa SET consecutivo_actual = N+1`. INSERT `factura_electronica` with `consecutivo=N+1`. INSERT 2 `log_transaccional` rows. COMMIT at T=Δ. Lock releases.
4. Worker B wakes from the wait. Re-reads `empresa` (the locked view is now `consecutivo_actual=N+1`). Compute `consecutivo_new = N+2`. UPDATE. INSERT `factura_electronica` with `consecutivo=N+2`. INSERT 2 `log_transaccional` rows. COMMIT at T=2Δ. Lock releases.
5. Cloud emits 2 SyncBackEvents (one per worker). Branch A polls and gets `numero_oficial` for its factura; Branch B does the same.
6. Both branches receive their correct, sequential `consecutivo` values. No duplicate. No gap. The atomic counter is the DIAN compliance backbone.
7. (Verification) Nightly `hash_chain_verifier` checks `log_transaccional` chain integrity for both branches — both chains are unbroken (each branch has exactly 1 new chain row + the corresponding cloud-side row).

**Tables touched (writes)**: `empresa` (2 atomic UPDATEs), `factura_electronica` (2 INSERTs), `log_transaccional` (4 rows: 2 per worker × 2 workers), `SyncBackEvent` (2 concept items).
**Tables touched (reads)**: `empresa` (SELECT FOR UPDATE x2), `facturas` (2 received), `clientes` (titular each), `log_transaccional` (chain anchors), `sucursal` (chain keys).
**FKs traversed**: `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`; `factura_electronica.uuid_sucursal` → `sucursal.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (different per worker — Branch A vs Branch B); `log_transaccional.uuid_registro_afectado` (polymorphic) → `empresa.uuid` (consecutivo_asignado) or `factura_electronica.uuid` (factura_electronica_creada).
**Sync behavior**:
- Branch → cloud: YES (both branches pushed their `facturas` rows; idempotent on retry).
- Cloud → branch: YES (2 SyncBackEvents; each branch receives its own).
- DIAN trigger: YES (2 e-facturas enqueued for DIAN dispatch).
- Hash chain impact: YES — 2 distinct branch chains extend by 1 row each (Branch A's chain and Branch B's chain); cloud chains extend correspondingly.
**Integration**:
- Reads from: `empresa` (atomic lock), `facturas` (received), `clientes` (titular), `log_transaccional` (chain anchor per branch), `sucursal` (chain keys).
- Writes to: `empresa` (atomic UPDATEs), `factura_electronica` (the e-facturas), `log_transaccional` (4 audit rows), `SyncBackEvent` (2 items), `dian_dispatcher` queue.
- Cross-cutting: this is the canonical **race-free DIAN numeration** invariant. Without `SELECT FOR UPDATE`, two concurrent workers could both read `N`, both increment to `N+1`, both INSERT `factura_electronica` with the same `consecutivo=N+1` — a DIAN compliance violation (duplicate official number). The row lock makes this impossible.
- Related: the lock duration is bounded by the TX (milliseconds). Cloud workers do NOT hold the lock during the DIAN provider call (that happens after COMMIT, in a separate worker). The lock is purely for the counter increment + e-factura INSERT.

### 7.6 Use Case: `uc.empresa.rango-agotado-returns-409-and-emits-alerta`

Cloud `/facturas/procesar` detects that the next `consecutivo_new` would exceed `rango_hasta` (the DIAN-assigned range is exhausted). The cloud ROLLBACKs the TX (no `factura_electronica` written), returns 409 `rango_agotado` to the branch (online) or to the sync queue worker (offline), and INSERTs `alerta tipo_alerta='rango_agotado'` for the admin to triage. The branch UI shows a red banner and prompts admin to load a new resolution. **The counter is NOT incremented** (rolled back), so the next valid range starts exactly at `rango_hasta + 1`.

**Actor**: dian_dispatcher (cloud worker) + admin (cloud, alerted via workflow)

**Pre-conditions**: `empresa` is seeded and vigente; `consecutivo_actual` is approaching or has reached `rango_hasta`; a new `facturas` row arrives for processing.

**Steps**:
1. Cloud worker opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
2. `SELECT empresa FOR UPDATE`; reads `consecutivo_actual=$current, rango_hasta=$max`.
3. Compute `consecutivo_new = $current + 1`. Compare against `$max`.
4. If `$consecutivo_new > $max`: trigger gate.
5. **ROLLBACK** the TX. No UPDATE on `empresa`. No INSERT on `factura_electronica`. No `log_transaccional` row (the rollback discards everything). The chain is NOT extended for this attempt.
6. Backend INSERTs `alerta` workflow chain root row (`uuid_type='rango_agotado'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_usuario=NULL`, `uuid_alerta_padre=NULL`, `uuid_arqueo=NULL`, `valor_diferencia_efectivo=0`, `valor_diferencia_datafono=0`, `observaciones='consecutivo_new=$new exceeds rango_hasta=$max, $remaining consecutivos remaining'`). This is the cloud-admin-triggers-it, not branch-originated, but the workflow lives in the branch's chain because the failing factura originated at the branch.
7. Backend INSERTs `log_transaccional` (`accion='rango_agotado_detectado'`, `tabla_afectada='empresa'`, `uuid_registro_afectado=$empresa_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={consecutivo_actual: $current, rango_hasta: $max, attempted_new: $new}`).
9. Backend INSERTs `SyncBackEvent` (concepto sprint 5; payload `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={estado:'rechazada_rango_agotado', retry_after:'admin_load_new_range'}, timestamp}`).
10. Return 409 Conflict `{detail: 'rango_agotado', consecutivo_actual: $current, rango_hasta: $max, branch_uuid, alert_uuid}` to the caller (online branch backend, or sync worker for offline branch).
11. Branch (online) receives 409; UI shows red banner "Rango DIAN agotado. Admin debe cargar nueva resolución.". The original business `facturas` row stays in branch DB with `uuid_factura_electronica=NULL` (will be retried when admin loads new range and cloud reprocesses).
12. Branch (offline) — the sync worker marks the queue item as `estado='fallido'`, `ultimo_error='rango_agotado'`, `next_retry_at=NOW() + 1h`. Will retry when admin acts.
13. Admin sees `alerta tipo_alerta='rango_agotado'` in `web_admin/AlertasList` (red badge). Opens `EmpresaForm`, loads new `resolucion_facturacion`, `rango_desde=$max+1`, `rango_hasta=$max+5000` (per use case 7.4).
14. Once new range is loaded, parametrization push delivers the new `empresa` version to branches. The sync worker retries the queued factura; cloud reprocesses successfully (consecutivo_new=$max+1, dentro del nuevo rango).
15. Admin resolves the alerta: workflow chain `abierta → en_revision → resuelta` with `observaciones='new_range_loaded_<uuid>'`.

**Tables touched (writes)**: `alerta` (1 root + 2 transitions for the workflow chain), `log_transaccional` (1 row for the detection), `SyncBackEvent` (1 concept item).
**Tables touched (reads)**: `empresa` (FOR UPDATE), `log_transaccional` (chain anchor), `sucursal` (chain key), `usuarios` (SYSTEM).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `empresa.uuid`.
**Sync behavior**:
- Branch → cloud: NO (this is the cloud rejecting a branch-pushed factura).
- Cloud → branch: YES — `SyncBackEvent` flows back with the rejection state; branch UI updates the red banner.
- DIAN trigger: NO (no e-factura was written, so nothing to dispatch).
- Hash chain impact: YES — branch chain extends by 1 row (the detection event); the rejected business factura does NOT extend the chain (no log row for it). The alert workflow chain extends by 1-3 rows as admin triages.
**Integration**:
- Reads from: `empresa` (atomic lock + range check), `log_transaccional` (chain anchor), `sucursal` (chain key), `usuarios` (SYSTEM).
- Writes to: `alerta` (workflow root), `log_transaccional` (detection audit), `SyncBackEvent` (rejection state), `sync_queue` (retry scheduling for offline branches).
- Cross-cutting: this is the **safety gate** that prevents DIAN range exhaustion. Without it, the cloud would happily assign `consecutivo=rango_hasta+1`, `+2`, `+3`... beyond the DIAN-assigned range — a compliance violation. The ROLLBACK preserves the counter at `rango_hasta` exactly, so the next valid range can start at `rango_hasta+1` without gaps.
- Related: the `alerta tipo_alerta='rango_agotado'` workflow is distinct from `cupo_lleno` (T04 use case 7.5) and `diferencia_arqueo` (T29 use case 7.4) — three different operational alerts that flow through the same `alerta` table with different `tipo_alerta` enum values.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 28, 29 (DIAN), 33.

## 9. RED Tests
- (RED) Two concurrent `/facturas/procesar` → different consecutivos.
- (RED) `consecutivo_actual > rango_hasta` → 409.
- (RED) Singleton check: second INSERT → UNIQUE violation on custom constraint.

## 10. Implementation Tasks
- [x] F1.x Schema + seed singleton.
- [ ] IT-2.x: admin CRUD.
- [ ] IT-5.x: `atomic_next_consecutivo(empresa_id)` with `SELECT FOR UPDATE`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Concurrent consecutivo race | Low | `SELECT FOR UPDATE` |
| Rango agotado mid-day | Low | Admin pre-loads new range |

## 12. Open Questions
- (a) Multiple empresas (multi-tenant SaaS)? Singleton enforced; out of MVP.