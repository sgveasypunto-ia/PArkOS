# PRD: tipo_tarifa (T25)

> Tariff mode catalog seeded with `'por_hora'`, `'por_minuto'`, `'plena'`. Determines the calculation modality at `factura_detalle`: `por_hora` = `duracion_segundos / 3600 * valor`; `por_minuto` = `duracion_segundos / 60 * valor`; `plena` = flat fee (B2B subscription bundled). FK target for `tarifas_sucursal` — every tarifa row references a mode.

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
- **Table name**: `prod.tipo_tarifa`
- **SQL name**: `tipo_tarifa` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seeded 3 modes) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 3 use cases covering admin CRUD, parametrization push, and branch pick on tarifas_sucursal)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `tipo` unique string.

## 3. SOLID Atomic Breakdown
- **S**: "one tariff mode".
- **O**: new columns via migration.
- **I**: admin CRUD.
- **D**: `parkos_core/models/V/tipo_tarifa.py`.
- **Atomic**: INSERT, UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `tarifas_sucursal.uuid_tipo_tarifa` | `\|\|--o{` | tariff per (sucursal, vehicle, mode) |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Seed |
| UPDATE | YES | Inside TX + `log_transaccional` |
| DELETE | NO | RESTRICT |

## 6. CodeGraph Dependencies
- `api_admin/routers/tipo-tarifa.py`.

## 7. Use Cases enabled by this table

The `tipo_tarifa` table is the **calculation modality catalog** that determines how `factura_detalle` computes its `subtotal`. With 3 seed rows (`por_hora`, `por_minuto`, `plena`), the catalog is small but central — it gates `tarifas_sucursal` (every tarifa row references a mode) and indirectly drives the snapshot in `factura_detalle` at facturacion. Use cases below describe admin CRUD, parametrization push, and the admin pick on `tarifas_sucursal` configuration. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.tipo-tarifa.admin-crud-create-or-version`

Cloud admin manages the `tipo_tarifa` catalog. New modes are rare (3 seed rows for MVP) but the admin may add `tipo='mensualidad'` for monthly flat-rate subscriptions or `tipo='quincena'` for biweekly corporate contracts. Updates create a new `[V]` version (archive old with `vigente_hasta=NOW()`, INSERT new). Parametrization push delivers the new version to all branches. Adding a new `tipo_tarifa` mode ALSO requires creating matching `tarifas_sucursal` rows for each branch × `tipo_vehiculo` × new mode — otherwise operators will see "No tariff configured" on ingreso for the new mode.

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='administrar_catalogos'`; the catalog has the 3 seed rows; if creating a new `tipo`, the name is unique.

**Steps**:
1. Admin opens `web_admin/Catalogos/TipoTarifa`, clicks `New`.
2. Frontend POSTs `api_admin /tipo-tarifa` with `{tipo='mensualidad', vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigentes; validates UNIQUE on `tipo` (rejects 409 if duplicate).
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. INSERT `tipo_tarifa` row (`uuid=server-generated`, `tipo`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
7. INSERT `log_transaccional` (`accion='tipo_tarifa_creado'`, `tabla_afectada='tipo_tarifa'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=null`, `datos_nuevos={tipo: 'mensualidad'}`).
8. `queue_processor.enqueue('tipo_tarifa', $new_uuid, $snapshot)` → parametrization push.
9. Backend returns `{new_uuid}`.
10. Admin is prompted to create matching `tarifas_sucursal` rows for each branch × `tipo_vehiculo` × new mode (admin may defer — `tarifas_sucursal` is per branch).
11. Branch receives parametrization; UPSERT new row.

**Tables touched (writes)**: `tipo_tarifa` (1 row), `log_transaccional` (1 row), `sync_queue` (1 parametrization item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_tarifa` (uniqueness check), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `tipo_tarifa` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipo_tarifa.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers the new mode to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipo_tarifa` (uniqueness), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `tipo_tarifa` (the new mode), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the lightest catalog write — only `tipo` string + version metadata. The actual calculation logic (how `factura_detalle` uses the mode) is in the application layer (`parkos_core/facturacion/cost_calculator.py`), keyed by the `tipo` string. Adding a new mode requires updating `cost_calculator.py` to handle the new mode (sprint 5 code change).
- Related: see T14 (`tarifas_sucursal`) for the cross-table cascade — `tipo_tarifa` is the modality key; `tarifas_sucursal` is the actual price per (sucursal, tipo_vehiculo, tipo_tarifa).

### 7.2 Use Case: `uc.tipo-tarifa.parametrization-push-to-branches`

Whenever `tipo_tarifa` changes (use case 7.1), cloud parametrization push delivers the new version to all active branches within 30s. Branch UPSERTs the row locally. The parametrization worker tracks per-branch delivery state in `sync_queue` and emits `sync_log` cycle metrics. If a branch is offline, the parametrization is queued and delivered when connectivity returns.

**Actor**: sync worker (cloud parametrization worker → branch parametrization receiver)

**Pre-conditions**: cloud has the new/updated `tipo_tarifa` row; branch is paired; branch has completed parametrization sync for the prior version.

**Steps**:
1. Cloud parametrization worker fires every 30s. Reads the parametrization delta: `tipo_tarifa` rows whose `sync_status='pendiente'` AND `created_at > last_sync_per_branch[$branch]`.
2. Worker groups the delta by branch (all branches receive the same parametrization for catalogs).
3. Worker POSTs `api_sucursal /sync/parametrization/pull` to each branch (with `sync-agent-` JWT) carrying the catalog delta.
4. Branch handler receives. Opens TX.
5. Branch SELECTs the local `tipo_tarifa` row by `uuid`. Compares `version_hash` against the incoming.
6. Branch UPSERTs `tipo_tarifa` row locally. For UPDATE: applies the `vigente_hasta` archive.
7. Branch INSERTs `log_transaccional` (`accion='tipo_tarifa_parametrized'`, `tabla_afectada='tipo_tarifa'`, `uuid_registro_afectado=$uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_anteriores=$local_snapshot`, `datos_nuevos=$cloud_snapshot`). The local chain extends.
8. Branch `queue_processor.ack` the parametrization; INSERT `sync_log` row.
9. Branch UI: next `TarifasForm` (admin configuring branch tarifa) shows the new `tipo_tarifa` mode in the dropdown.

**Tables touched (writes)**: `tipo_tarifa` (UPSERT, branch local), `log_transaccional` (1 row per parametrization receipt), `sync_log` (1 row per cycle).
**Tables touched (reads)**: `tipo_tarifa` (local + cloud via parametrization), `log_transaccional` (chain anchor), `usuarios` (SYSTEM), `sucursal` (self).
**FKs traversed**: `tipo_tarifa` has NO FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipo_tarifa.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push every 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — each branch chain extends by 1 row per parametrization receipt.
**Integration**:
- Reads from: `tipo_tarifa` (cloud source), `log_transaccional` (chain anchor), `usuarios` (SYSTEM), `sucursal` (self).
- Writes to: `tipo_tarifa` (local mirror), `log_transaccional` (audit), `sync_log` (cycle metrics).
- Cross-cutting: this is the same canonical **cloud→branch parametrization** flow as T22/T23 use case 7.2. The catalog is identical on all branches (no per-branch override for tariff modes). Per-branch variation happens at `tarifas_sucursal` (T14), which is explicitly keyed by `uuid_sucursal`.
- Related: parametrization conflicts (cloud and branch both modify the row) can't happen because branches don't write `tipo_tarifa` — only cloud does. The `sync_queue` for parametrization is one-way (cloud → branch), no `sync_conflict` possible.

### 7.3 Use Case: `uc.tipo-tarifa.admin-picks-on-tarifas-sucursal-config`

Cloud admin configures a `tarifas_sucursal` row (T14 use case 7.1). For each (sucursal, tipo_vehiculo) pair, admin configures up to 3 tarifas — one per `tipo_tarifa` mode (`por_hora`, `por_minuto`, `plena`). Each tarifa row references a `tipo_tarifa.uuid`. The combination is the (sucursal, tipo_vehiculo, tipo_tarifa) tuple — must be UNIQUE for vigentes. This use case focuses on the `tipo_tarifa` FK reference from `tarifas_sucursal`; see T14 for the full versioning + snapshot flow.

**Actor**: admin (cloud)

**Pre-conditions**: branch has parametrized vigentes `tipo_tarifa` modes (use case 7.2); admin has `permiso='actualizar_tarifas'`; branch has at least one `tipos_vehiculo` parametrized.

**Steps**:
1. Admin opens `web_admin/SucursalesList/{branch}/TarifasTab`. The grid shows rows = `tipos_vehiculo` (auto, moto, camioneta, bicicleta) × columns = `tipo_tarifa` (por_hora, por_minuto, plena).
2. Admin clicks cell `(auto, por_hora)`, fills `valor=4000`, `valor_plena=null`.
3. Frontend GETs `api_admin /tipo-tarifa?vigente_only=true` (already loaded in the column headers).
4. Frontend POSTs `api_admin /tarifas-sucursal` with `{uuid_sucursal=$branch, uuid_tipo_vehiculo=$auto_uuid, uuid_tipo_tarifa=$por_hora_uuid, valor=4000, vigente_desde=NOW()}`.
5. Backend validates `permisos_usuario` for `permiso='actualizar_tarifas'`; rejects 403 if missing.
6. Backend validates UNIQUE: `SELECT uuid FROM tarifas_sucursal WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$auto_uuid AND uuid_tipo_tarifa=$por_hora_uuid AND vigente_hasta IS NULL`. If found → UPDATE flow (archive old). If not → INSERT flow.
7. Backend SELECTs the FK targets to validate they exist and are vigentes: `tipos_vehiculo` (the `auto` row, RESTRICT), `tipo_tarifa` (the `por_hora` row, RESTRICT), `sucursal` (the branch, RESTRICT).
8. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
9. If UPDATE: UPDATE old row SET `vigente_hasta=NOW()`. INSERT new row with `valor=4000`.
10. If INSERT: INSERT new row directly.
11. INSERT `log_transaccional` (`accion='tarifa_actualizada'`, `tabla_afectada='tarifas_sucursal'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores=$old_snapshot`, `datos_nuevos=$new_snapshot`).
12. `queue_processor.enqueue('tarifas_sucursal', $new_uuid, $snapshot)` → parametrization push.
13. Backend returns `{new_uuid}`.
14. Admin may repeat for `(auto, por_minuto)`, `(auto, plena)`, `(moto, por_hora)`, etc. — 12 cells total for the standard (4 tipos_vehiculo × 3 tipo_tarifa) grid.

**Tables touched (writes)**: `tarifas_sucursal` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_tarifa` (vigente for FK validation), `tipos_vehiculo` (vigente for FK validation), `sucursal` (branch for FK validation), `tarifas_sucursal` (current vigente + UNIQUE check), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `tarifas_sucursal.uuid_tipo_tarifa` → `tipo_tarifa.uuid` (the modality FK, RESTRICT); `tarifas_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tarifas_sucursal.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to the target branch within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (the branch's key); branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipo_tarifa` (vigente), `tipos_vehiculo` (vigente), `sucursal` (branch), `tarifas_sucursal` (current state), `log_transaccional` (chain anchor), `usuarios` (admin).
- Writes to: `tarifas_sucursal` (the new tarifa), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: the FK from `tarifas_sucursal.uuid_tipo_tarifa` to `tipo_tarifa.uuid` is the modality anchor. The mode determines how `factura_detalle.subtotal` is computed (via `cost_calculator.py`). If admin changes the mode (e.g., archive `por_hora`, create `por_hora_nuevo`), the `tarifas_sucursal` rows keep referencing the OLD mode's UUID — historical tarifas remain calculable.
- Related: see T14 (`tarifas_sucursal`) use case 7.3 for the snapshot semantic — the `tarifa` value (not the mode) is snapshotted into `factura_detalle.valor_unitario` at facturacion. The mode is referenced by FK from `factura_detalle` indirectly (via `concepto='estancia_por_hora_tarifa_vigente'` etc.) — `factura_detalle` itself does NOT FK to `tipo_tarifa`.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 31.

## 9. RED Tests
- (RED) `tipo` unique.
- (RED) ON DELETE RESTRICT.

## 10. Implementation Tasks
- [x] F1.x Seed.
- [ ] IT-2.x: admin CRUD.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| New mode added | Low | Migration + seed |

## 12. Open Questions
- (a) Dynamic modes vs fixed 3?