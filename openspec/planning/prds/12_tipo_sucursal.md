# PRD: tipo_sucursal (T12)

> Branch type catalog (A=large + sensors, B=medium + barriers, C=small no barriers). **Defines the hardware profile** that every branch boot reads via `caracteristicas` JSON to apply its operational configuration (which DIAN stubs activate, which barriers enable, which sensors wire up). Seed A/B/C; admin CRUD for new types.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule O: `caracteristicas` JSON is the extension point*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.tipo_sucursal`
- **SQL name**: `tipo_sucursal` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seed A/B/C) + IT-2 (admin CRUD, JSON update flow)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; branch-boot + cross-branch config toggle cascades documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `codigo` is a unique natural key (`'A'`, `'B'`, `'C'`, future `'D'`, `'E'`, etc.) — enforced by UNIQUE constraint.
- `caracteristicas` is `json` (not `jsonb`) — preserves insertion order for human-readable boot config (per SOLID O, the JSON is the extension point; new keys added as needed without schema migration).

## 3. SOLID Atomic Breakdown
- **S**: "one branch type classification" with hardware profile. The catalog is the **hardware abstraction layer**: instead of `sucursal` carrying boolean flags for each module, it points to `tipo_sucursal` which carries a `caracteristicas` JSON consumed by `entrypoint.sh` at branch boot.
- **O**: `caracteristicas` JSON is the open extension point. New hardware modules added by inserting keys to JSON — no schema migration. Examples: `{sensores, barreras, capacidad_max, dian_habilitado, hardware_modules: [...]}`.
- **I**: admin CRUD via `api_admin /tipo-sucursal`; branch reads own type at boot via local parametrization lookup; no branch-side writes.
- **D**: `parkos_core/models/V/tipo_sucursal.py` (model); `parkos_core/boot/config_resolver.py` (parses `caracteristicas` into `boot_config.json`); `infra/docker/entrypoint.sh` invokes the resolver.
- **Atomic**: INSERT (admin creates new type), UPDATE (creates new version with new `caracteristicas`; archive old), DELETE forbidden by FK RESTRICT if any `sucursal` references.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog, no outgoing FKs |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `sucursal.uuid_tipo_sucursal` | `\|\|--o{` | every branch classified by one type |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin via `api_admin /tipo-sucursal`; seeded A/B/C in F1 migration |
| UPDATE | YES | Inside TX + `log_transaccional` (creates new version with `vigente_hasta=NOW()`); parametrization push to ALL branches that reference this type |
| DELETE | NO | FK RESTRICT prevents if any `sucursal` uses it; archive instead |

**Special rules**:
- F1 migration seeds three rows: A (sensores + barreras + DIAN enabled, cap 500), B (barreras only, cap 200, no DIAN), C (no hardware, cap 80, no DIAN). UUIDs are fixed (deterministic) so branches can reference them in parametrization before they pull the row.
- `caracteristicas` JSON schema is **not enforced at DB level** (free JSON). Application-level validation in `parkos_core/boot/config_validator.py` checks: required keys present, types correct, hardware_modules values from enum.
- Cross-branch impact: any UPDATE propagates to ALL active branches referencing this type via parametrization pull (within 30s). Admin sees a warning "This change affects N branches — proceed?".

## 6. CodeGraph Dependencies
- `api_admin/routers/tipo_sucursal.py::POST /tipo-sucursal`, `PATCH /tipo-sucursal/{uuid}`, `GET /tipo-sucursal`.
- `api_sucursal/routers/tipo_sucursal.py::GET /tipo-sucursal/me` (own type — branch reads at boot and during runtime if config changes).
- `parkos_core/boot/config_resolver.py::resolve_config(json_caracteristicas)` → `/var/etc/parkos/boot_config.json`.
- `parkos_core/boot/config_validator.py::validate(json_caracteristicas)` (admin POST/PATCH validates before persist).
- `infra/docker/entrypoint.sh::load_tipo_sucursal_config` (every boot).
- `job_sync_cloud::poll_parametrization_pull` (pushes new versions to all branches referencing the type).
- `web_admin/TipoSucursalForm`, `TipoSucursalDetail`.

## 7. Use Cases enabled by this table

The `tipo_sucursal` table is the **hardware abstraction layer** for the multi-tenant topology: instead of every `sucursal` row carrying boolean flags for each hardware module, it points to a `tipo_sucursal.uuid` whose `caracteristicas` JSON is read by `infra/docker/entrypoint.sh` at boot to apply the operational configuration (which DIAN stubs activate, which barriers enable, which sensors wire up). Use cases below describe how the catalog flows through admin parametrization, branch boot, and cross-branch configuration toggles.

### 7.1 Use Case: `uc.tipo-sucursal.admin-create-new-type`

Admin cloud crea un nuevo tipo de sucursal — por ejemplo, "D = Drive-Thru" para un nuevo modelo de negocio donde los vehículos pasan por la caseta sin descender del auto. Define `caracteristicas` JSON con módulos específicos: barrera rápida, cámara de placa (operador todavía escribe manualmente la placa en sistema, pero hay módulo de asistencia visual), cobro sin recibo impreso. El sistema valida el JSON, persiste la nueva fila con versión, y la parametrización queda disponible para branches futuras. El flujo toca 5 tablas: `tipo_sucursal` (W), `log_transaccional` (W), `sync_queue` (W), `permisos` (R para validar permiso del admin), `usuarios` (R admin actor).

**Actor**: admin

**Pre-conditions**: admin has `permiso='crear_tipo_sucursal'`; A/B/C seed exists; business case requires new type (e.g., opening a new parking model).

**Steps**:
1. Admin opens `web_admin/TipoSucursalForm`, fills `codigo='D'`, `nombre='Drive-Thru'`, `descripcion='Pago express sin descender del vehículo, sin impresión'`, `caracteristicas={sensores:false, barreras:true, barrera_rapida:true, capacidad_max:30, dian_habilitado:false, hardware_modules:['barrier_rapida_v1','receipt_printer_opcional'], sin_recibo_impreso:true, tiempo_max_estancia_min:120}`.
2. Frontend POSTs `api_admin /tipo-sucursal` (admin- JWT) with the payload.
3. Backend validates: `permisos_usuario` lookup for `permiso='crear_tipo_sucursal'`; rejects 403 if missing.
4. Backend validates `codigo` is unique (UNIQUE constraint); rejects 409 if collision.
5. Backend validates `caracteristicas` JSON via `config_validator`: required keys present (`sensores`, `barreras`, `capacidad_max`, `dian_habilitado`, `hardware_modules`), types correct (booleans for sensors/barreras, int for capacidad_max, array of strings for hardware_modules), enum values valid (hardware_modules ∈ known set).
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_branch_or_cloud_anchor`. (Note: cloud admin writes are not branch-scoped; the log row uses `uuid_sucursal=NULL` or a sentinel — but per AUDIT-FIRST, `log_transaccional.uuid_sucursal` is NOT NULL. Convention: cloud-originated config writes use a sentinel `uuid_sucursal='CLOUD_CONFIG'` row in `sucursal` table, or — more cleanly — the row is partitioned under the FIRST active branch's chain anchor. Sprint 5 will resolve.)
7. Backend INSERTs `tipo_sucursal` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`).
8. Backend INSERTs `log_transaccional` (`accion='tipo_sucursal_creado'`, `tabla_afectada='tipo_sucursal'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `datos_anteriores=null`, `datos_nuevos={...snapshot, caracteristicas_keys: [...], validator_passed: true}`).
9. `queue_processor.enqueue('tipo_sucursal', $new_uuid, $snapshot)` → INSERT `sync_queue` row (parametrization push).
10. Backend returns `{uuid, codigo, nombre, vigente_desde}` to frontend.
11. Admin sees success; the new type 'D' appears in the `SucursalForm` dropdown for future branch creation.

**Tables touched (writes)**: `tipo_sucursal` (1 row), `log_transaccional` (1 row), `sync_queue` (1 row).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `usuarios` (admin actor), `tipo_sucursal` (UNIQUE check on codigo), `log_transaccional` (chain anchor).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`; `sync_queue.uuid_sucursal` → (cloud sentinel or first active branch); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (per partition convention).

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the new `tipo_sucursal` row to all branches within 30s. Branches that haven't created a sucursal yet don't need this yet, but it pre-populates their catalog so future onboarding can pick it.
- DIAN trigger: NO (catalog write, no fiscal impact).
- Hash chain impact: YES — cloud chain extends by 1 row (tipo_sucursal_creado). Branches receive it via parametrization and extend their chain by 1 row when the row arrives.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `usuarios` (admin actor), `tipo_sucursal` (UNIQUE check), `log_transaccional` (chain anchor).
- Writes to: `tipo_sucursal` (new row), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: per SOLID O, the JSON is the extension point. Adding a new hardware module (e.g., `'license_plate_camera_visual'` for type D) means adding the key to `config_validator`'s enum + updating the application module loader. No schema change.
- Related: when an admin creates a new `sucursal` and selects `uuid_tipo_sucursal='D'`, the seed parametrization in `uc.sucursal.admin-onboarding-pairing-flow` step 5 uses type D's `caracteristicas` to decide which tariff seeds to create (none for `sin_recibo_impreso`), which barreras to enable, etc.

### 7.2 Use Case: `uc.tipo-sucursal.branch-boot-resolves-caracteristicas`

Branch ya pareada y operativa, reinicia por mantenimiento programado. `infra/docker/entrypoint.sh` corre `load_tipo_sucursal_config`, lee `caracteristicas` JSON desde parametrización local, y genera `/var/etc/parkos/boot_config.json` con la configuración de hardware deserializada. La aplicación `api_sucursal` lee este config al primer request y carga los módulos correspondientes. El flujo toca 4 tablas en lectura + 1 en escritura (`log_transaccional` audita el boot).

**Actor**: system (entrypoint.sh + api_sucursal module loader)

**Pre-conditions**: branch is paired and parametrized; `sucursal.uuid_tipo_sucursal` is set; `tipo_sucursal.caracteristicas` JSON has been pulled from cloud.

**Steps**:
1. Branch reboots (`docker compose restart api_sucursal`). `infra/docker/entrypoint.sh` orchestrates: `wait-postgres → rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → load_tipo_sucursal_config → exec CMD`.
2. `load_tipo_sucursal_config` runs: SELECTs `sucursal.uuid_tipo_sucursal` from local `sucursal` WHERE `uuid = $self_branch_uuid`.
3. SELECTs `tipo_sucursal` WHERE `uuid = $tipo_sucursal_uuid AND estado='activo' AND vigente_desde<=NOW() AND (vigente_hasta IS NULL OR vigente_hasta>NOW())`. (Versioned lookup: takes the vigente version.)
4. Loads `caracteristicas` JSON from the row. Parses via `config_resolver`:
   - Reads `sensores` boolean → if `true`, loads `sensor_counter_module` (live occupancy display).
   - Reads `barreras` boolean → if `true`, loads `barrier_control_module` (UI gains `OpenBarrier` button).
   - Reads `barrera_rapida` boolean (if present) → if `true`, loads `barrier_rapida_v1` module (sub-second barrier activation for type D drive-thru).
   - Reads `dian_habilitado` boolean → if `true`, loads `dian_dispatcher_stub` (sends to cloud for DIAN processing; if `false`, the stub is NOT loaded and operator sees "DIAN: cloud-only" message in `FacturacionForm`).
   - Reads `hardware_modules` array → loads each module from the module registry (e.g., `'receipt_printer'`, `'barrier_v2'`, `'sensor_counter'`).
   - Reads `capacidad_max` int → writes to `boot_config.json` as `cupo_total` reference.
   - Reads `sin_recibo_impreso` boolean (if present) → if `true`, the `FacturacionForm` skips the auto-print step; operator must explicitly click `Imprimir`.
   - Reads `tiempo_max_estancia_min` int (if present) → writes to `boot_config.json` for `salida` validation (operator sees warning if exceeded).
5. Writes the resolved config to `/var/etc/parkos/boot_config.json` (YAML or JSON, application-readable).
6. INSERTs `log_transaccional` (`accion='branch_boot_config_resolved'`, `tabla_afectada='tipo_sucursal'`, `uuid_registro_afectado=$tipo_sucursal.uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$self_branch`, `datos_nuevos={tipo_codigo, modules_loaded: [...], caracteristicas_hash: SHA256(json)}`).
7. `entrypoint.sh` continues: `exec CMD` (api_sucursal starts).
8. `api_sucursal` first request reads `boot_config.json`: loads the modules in order; if a module fails to load (e.g., missing hardware dependency), logs warning and proceeds without it (graceful degradation). INSERTs `log_transaccional` (`accion='api_sucursal_modules_loaded'`).
9. Branch is fully operational with the resolved configuration.

**Tables touched (writes)**: `log_transaccional` (1-2 rows).
**Tables touched (reads)**: `sucursal` (self uuid_tipo_sucursal FK), `tipo_sucursal` (vigente version lookup), `log_transaccional` (chain anchor), `usuarios` (SYSTEM lookup).
**FKs traversed**: `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid` (the key resolution); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipo_sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM).

**Sync behavior**:
- Branch → cloud: YES (the boot_config_resolved audit row pushes via `sync_queue` within 30s).
- Cloud → branch: NO (this is a local read-and-apply; no parametrization impact).
- DIAN trigger: NO (config decision is local; DIAN write only happens on actual invoice, and even then it's delegated to cloud for non-A types).
- Hash chain impact: YES — branch chain extends by 1-2 rows on every boot. Cloud receives and extends its chain by 1-2 rows.

**Integration with other tables**:
- Reads from: `sucursal` (uuid_tipo_sucursal FK), `tipo_sucursal` (vigente version + caracteristicas JSON), `log_transaccional` (chain anchor), `usuarios` (SYSTEM).
- Writes to: `log_transaccional` (boot audit).
- Cross-cutting: this is the **hardware-driven boot pattern**. The JSON `caracteristicas` is the contract between admin (defines capabilities) and `entrypoint.sh` (applies them). Any new hardware module is added by extending the JSON schema + `config_validator` + module loader — no SQL change.
- Related: a type B branch and a type C branch with same parametrization pull will boot with different configurations because their `tipo_sucursal.caracteristicas` differ. The `entrypoint.sh` script is identical across branches; the JSON drives the difference.

### 7.3 Use Case: `uc.tipo-sucursal.admin-toggle-barreras-cross-branch-impact`

Admin cloud quiere habilitar barreras en todas las branches de tipo B que aún no las tienen (operational upgrade: instalar barreras físicas en 5 branches tipo B). En lugar de ir branch por branch, edita `tipo_sucursal` con codigo='B' y actualiza `caracteristicas.barreras=true`. El sistema valida que el cambio no rompa la configuración actual, advierte "Esto afecta 5 branches activas", y al confirmar dispara parametrización push a TODAS esas branches. Cada branch en su próximo boot aplica la nueva configuración. El flujo toca 6 tablas: `tipo_sucursal` (UPDATE nueva versión), `sucursal` (R para contar branches afectadas), `log_transaccional` (W), `sync_queue` (W parametrización push por branch), `sync_log` (W métricas), `permisos_usuario` (R RBAC).

**Actor**: admin

**Pre-conditions**: at least one branch of the affected type is active and online (or offline — changes apply on next boot). Admin has `permiso='actualizar_tipo_sucursal'`. Operator confirms the upgrade window (off-hours, branches not operating, etc.).

**Steps**:
1. Admin opens `web_admin/TipoSucursalDetail/B`, clicks `Edit`.
2. Frontend shows `TipoSucursalForm` populated with current `caracteristicas`: `{sensores:false, barreras:false, capacidad_max:200, dian_habilitado:false, hardware_modules:['receipt_printer']}`.
3. Admin changes `barreras` from `false` to `true`, adds `'barrier_v2'` to `hardware_modules`. Submits.
4. Frontend PATCHes `api_admin /tipo-sucursal/{uuid}` with `{caracteristicas: {..., barreras:true, hardware_modules:['receipt_printer','barrier_v2']}}`.
5. Backend validates `permisos_usuario` for admin.
6. Backend validates updated JSON via `config_validator`: required keys still present, types correct, new `hardware_modules` value is in known enum.
7. Backend SELECTs COUNT of active `sucursal` WHERE `uuid_tipo_sucursal=$uuid AND estado='activo'`. Returns 5.
8. Backend returns confirmation prompt to frontend: "Esto afecta 5 branches activas — proceder?". Admin confirms.
9. Backend opens TX; SELECT chain anchor from `log_transaccional`.
10. Backend INSERTs new `tipo_sucursal` row (`vigente_desde=NOW(), vigente_hasta=NULL, caracteristicas={nueva_json}`). UPDATE old: `vigente_hasta=NOW()`. Version flow.
11. Backend INSERTs `log_transaccional` (`accion='tipo_sucursal_actualizado'`, `tabla_afectada='tipo_sucursal'`, `uuid_registro_afectado=$new_uuid`, `datos_anteriores={old_caracteristicas, branches_affected: 5}`, `datos_nuevos={new_caracteristicas, branches_affected: 5, change_reason: $admin_input}`).
12. Backend SELECTs `sucursal` rows WHERE `uuid_tipo_sucursal=$uuid AND estado='activo'`. For each, INSERTs `sync_queue` row for parametrization push (`tabla='tipo_sucursal', uuid_registro=$new_uuid, uuid_sucursal=$branch`).
13. Backend returns `{uuid_new, branches_notified: 5}` to frontend.
14. Frontend shows success; admin sees toast: "5 branches will receive the update within 30s".
15. Each branch receives parametrization within 30s. `job_sync_sucursal::drain_outbox_parametrization` UPSERTs the new `tipo_sucursal` row locally (idempotent by UUID). The local `sucursal.uuid_tipo_sucursal` FK remains pointing at the same UUID — but the vigente version is now the new row.
16. Branch does NOT auto-reboot (operators may be mid-shift). The new `tipo_sucursal` row is in the parametrization catalog but the running application still uses the old `boot_config.json`. Operator sees a banner: "Nueva configuración disponible — reiniciar para aplicar".
17. When branch reboots (end of shift, or admin dispatches via parametrization push to `api_sucursal /admin/reboot` with confirmation): `entrypoint.sh::load_tipo_sucursal_config` runs again, reads the new vigente `tipo_sucursal` row, applies the new config (now with `barrier_v2` loaded).
18. Branch `log_transaccional` extends by 1 row (tipo_sucursal_actualizado received) + 1 row on reboot (branch_boot_config_resolved with new modules).
19. Cloud receives both; cloud chain extends by 2 rows.
20. If branch is offline during the parametrization push: the `sync_queue` row sits in cloud's outbox until branch comes back. When branch reconnects, parametrization is pulled on first sync cycle, applied on next boot.

**Tables touched (writes)**: `tipo_sucursal` (1 new version + 1 archive update), `log_transaccional` (1 admin + 1-2 per branch when received/rebooted), `sync_queue` (5 rows, one per affected branch), `sync_log` (1 row per push cycle).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `sucursal` (count + list of affected branches), `log_transaccional` (chain anchor), `usuarios` (admin actor).
**FKs traversed**: `tipo_sucursal` (no outgoing FK); `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid` (the FK that drives the cascade); `sync_queue.uuid_sucursal` → `sucursal.uuid` (one per branch); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (per branch partition); `log_transaccional.uuid_usuario` → `usuarios.uuid` (admin).

**Sync behavior**:
- Branch → cloud: NO (this write happens in cloud).
- Cloud → branch: YES — parametrization push to ALL affected branches (5 rows in `sync_queue` per the example). Each branch receives and UPSERTs.
- DIAN trigger: NO (the change is operational, not fiscal).
- Hash chain impact: YES — cloud chain extends by 1 row (admin's update). Each branch chain extends by 1 row (parametrization received) + 1 row on reboot. Total: 1 + 5 + 5 = 11 rows across all chains.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `sucursal` (count affected branches), `log_transaccional` (chain anchor), `usuarios` (admin actor), `tipo_sucursal` (current version lookup).
- Writes to: `tipo_sucursal` (new version), `sucursal` (NO direct write — the FK pointer is stable, only the version changes), `log_transaccional` (audit), `sync_queue` (per-branch parametrization push), `sync_log` (cycle metrics).
- Cross-cutting: this is the **fan-out update pattern** — one catalog change cascades to N branches. The `sucursal.uuid_tipo_sucursal` FK is stable (same UUID), but the vigente version of `tipo_sucursal` changes. Branches don't need FK migration; they just need to pull the new version.
- Related: if admin wants to revert (e.g., barreras installation failed at one branch), they can: (a) re-PATCH with the old `caracteristicas` (creates a new version restoring old state); or (b) move that one branch to a new type 'B-without-barreras' if it can't be installed. The first option is simpler and respects `[V]` versioning.
- Risk consideration: if a branch operator manually overrides the boot config (e.g., disables barriers via `/var/etc/parkos/boot_config.json` local edit), the next parametrization pull of the new `tipo_sucursal` row does NOT force re-apply — it just updates the catalog. The operator's manual override persists until explicit reboot + config resolution. This is intentional (operational flexibility) but documented as a potential inconsistency vector.

## 8. Layer-by-Layer Impact
Layers: 1, 4, 6, 13, 17, 24, 31, 35.

## 9. RED Tests
- (RED) F1 migration seeds A/B/C `tipo_sucursal` rows with deterministic UUIDs.
- (RED) Admin POST `/tipo-sucursal` with `codigo='D'` and valid JSON → 201; row persisted.
- (RED) Admin POST with duplicate `codigo` → 409 conflict.
- (RED) Admin POST with invalid `caracteristicas` JSON (missing required key) → 422 with validator errors.
- (RED) Admin POST without `permiso='crear_tipo_sucursal'` → 403.
- (RED) Admin PATCH `barreras=true` → new version created; old `vigente_hasta=NOW()`; parametrization push enqueued for all `sucursal` referencing this type.
- (RED) Branch boot: type A → `sensor_counter` + `barrier_v2` + `dian_dispatcher_stub` modules loaded; type B → only `barrier_v2`; type C → only `receipt_printer`.
- (RED) Branch operator reads `api_sucursal /tipo-sucursal/me` → 200 with own type's vigente caracteristicas.
- (RED) ON DELETE RESTRICT: cannot delete `tipo_sucursal='B'` while `sucursal` references it.
- (RED) `caracteristicas` JSON stored as ordered JSON (not JSONB normalized) — boot_config.json preserves insertion order.
- (RED) Cross-branch fan-out: PATCH tipo_sucursal triggers 1 row in `sync_queue` per active `sucursal` referencing it (verified by count match).

## 10. Implementation Tasks
- [x] F1.x Schema + seed A/B/C with deterministic UUIDs.
- [ ] IT-2.x: `api_admin /tipo-sucursal` (POST, PATCH, GET list, GET detail) with `config_validator`.
- [ ] IT-2.x: parametrization push fan-out logic in PATCH handler.
- [ ] IT-2.x: `parkos_core/boot/config_resolver.py` + `config_validator.py`.
- [ ] IT-2.x: `infra/docker/entrypoint.sh::load_tipo_sucursal_config` + `/var/etc/parkos/boot_config.json` writer.
- [ ] IT-2.x: `api_sucursal` module loader reads `boot_config.json` on startup.
- [ ] IT-2.x: `web_admin/TipoSucursalForm`, `TipoSucursalDetail`, `branch_impact_warning` component.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Admin PATCH breaks branches (invalid JSON, missing module) | Med | `config_validator` rejects bad JSON at PATCH time; admin must pass dry-run validation before persist |
| Branch operator manual override of boot_config.json | Low | Documented; next parametrization pull updates catalog but doesn't force re-apply; operator intentional |
| Fan-out pushes overload cloud sync | Low | Async parametrization push via `sync_queue`; branches pull at their own pace; no global rate-limit needed (each branch has 30s polling cycle) |
| JSON schema drift across versions | Med | `config_validator` enforces required keys; new optional keys added by validator schema bump + admin docs |
| tipo_sucursal deleted while branches reference | Low | FK RESTRICT prevents; admin must archive all referencing branches first (or migrate them to a different type) |
| Cross-branch impact unannounced | Low | Frontend shows "afecta N branches" warning before PATCH; admin must confirm |

## 12. Open Questions
- (a) `caracteristicas` JSON schema versioning: how do we add new required keys without breaking existing branches that haven't pulled the new `tipo_sucursal` version? Current: `config_validator` lists ALL keys ever defined; existing branches see "missing new key" warning in `boot_config.json` but proceed with defaults. Defer stricter version negotiation to sprint 5.
- (b) Per-branch `caracteristicas` override (e.g., one type B branch wants barriers disabled): not supported by current model. Workaround: create a new type ('B-no-barreras') and migrate the branch. Acceptable for MVP.
- (c) `log_transaccional.uuid_sucursal` for cloud-only writes: use a sentinel `CLOUD_CONFIG` row in `sucursal`? Or use the first active branch's UUID? Sprint 5 decision.
- (d) `hardware_modules` enum centralization: where does the canonical list of known modules live? Currently in `parkos_core/boot/module_registry.py`; should it be in DB? Probably not — modules are application-layer concern.
- (e) Auto-reboot after parametrization push: should branches auto-reload config without manual reboot? Current: no (operator decides). Sprint 5 may add `api_sucursal /admin/reload-config` for admin-triggered reload.
