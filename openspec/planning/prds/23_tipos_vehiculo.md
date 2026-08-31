# PRD: tipos_vehiculo (T23)

> Vehicle type catalog seeded with `'auto'`, `'moto'`, `'camioneta'`, `'bicicleta'`. Mandatory FK from `ingreso` (every ingreso MUST classify the vehicle), from `vehiculos` (subscriber vehicles), from `tarifas_sucursal` (every tariff row is per `tipo_vehiculo`), and from `cantidad_vehiculos_sucursal` (cupo per branch per vehicle type). The catalog is read on EVERY ingreso creation — operator MUST select a type.

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
- **Table name**: `prod.tipos_vehiculo`
- **SQL name**: `tipos_vehiculo` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seeded 4 types) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 4 use cases covering admin CRUD, parametrization push, branch pick on ingreso, and subscriber vehiculos reference)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `tipo` unique string ('auto' / 'moto' / 'camioneta' / 'bicicleta').

## 3. SOLID Atomic Breakdown
- **S**: "one vehicle type".
- **O**: new column `descripcion`.
- **I**: admin CRUD.
- **D**: `parkos_core/models/V/tipos_vehiculo.py`.
- **Atomic**: INSERT, UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `tarifas_sucursal.uuid_tipo_vehiculo` | `\|\|--o{` | tariff per (sucursal, vehicle type) |
| `cantidad_vehiculos_sucursal.uuid_tipo_vehiculo` | `\|\|--o{` | capacity per (sucursal, vehicle type) |
| `ingreso.uuid_tipo_vehiculo` | `\|\|--o{` | ingreso's vehicle type |
| `vehiculos.uuid_tipo_vehiculo` | `\|\|--o{` | vehiculo's type |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Seed (4 types) in F1 |
| UPDATE | YES | Inside TX + `log_transaccional` |
| DELETE | NO | RESTRICT |

## 6. CodeGraph Dependencies
- `api_admin/routers/tipos-vehiculo.py`.
- `api_sucursal/routers/tipos-vehiculo.py` (read own).

## 7. Use Cases enabled by this table

The `tipos_vehiculo` table is the **mandatory FK target for every vehicle in the system**. With 4 seed rows for MVP (`auto`, `moto`, `camioneta`, `bicicleta`), the catalog is small but load-bearing: it gates `tarifas_sucursal` (every tarifa row references a `tipo_vehiculo`), `cantidad_vehiculos_sucursal` (every cupo row references it), `ingreso` (mandatory on every entry), and `vehiculos` (subscriber vehicles reference it for tarifa lookup). Use cases below describe admin CRUD, parametrization push, the operator pick on `ingreso`, and the subscriber `vehiculos` reference. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.tipos-vehiculo.admin-crud-create-or-version`

Cloud admin manages the `tipos_vehiculo` catalog. New types are rare (the seed has 4 rows for MVP) but the admin may add `tipo='motocicleta_electrica'` for the electric scooter wave or `tipo='camion'` for truck parking at commercial lots. Updates create a new `[V]` version (archive old with `vigente_hasta=NOW()`, INSERT new). Parametrization push delivers the new version to all branches. Adding a new `tipo_vehiculo` ALSO requires admin to create matching `tarifas_sucursal` rows for each branch (use case 7.3 in T14) — otherwise the operator will see "No tariff configured" on ingreso (T14 use case 7.2).

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='administrar_catalogos'`; the catalog has the 4 seed rows; if creating a new `tipo`, the name is unique.

**Steps**:
1. Admin opens `web_admin/Catalogos/TiposVehiculo`, clicks `New` or selects an existing row.
2. For CREATE: Frontend POSTs `api_admin /tipos-vehiculo` with `{tipo='motocicleta_electrica', descripcion='Vehículo eléctrico de 2 ruedas con motor <500W', vigente_desde=NOW()}`. For UPDATE: PATCH `/tipos-vehiculo/{uuid}`.
3. Backend validates `permisos_usuario` for `permiso='administrar_catalogos'`; rejects 403 if missing.
4. Backend SELECTs current vigente rows: `SELECT * FROM tipos_vehiculo WHERE vigente_hasta IS NULL`. Validates UNIQUE on `tipo` (rejects 409 if duplicate).
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. For UPDATE: UPDATE current vigente row SET `vigente_hasta=NOW()` (archive old). For CREATE: skip.
7. INSERT new `tipos_vehiculo` row (`uuid=server-generated`, `tipo`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='tipo_vehiculo_actualizado'`, `tabla_afectada='tipos_vehiculo'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=$old_snapshot`, `datos_nuevos=$new_snapshot`).
9. `queue_processor.enqueue('tipos_vehiculo', $new_uuid, $new_snapshot)` → parametrization push for all active branches within 30s.
10. If archiving: also enqueue the archived row.
11. Backend returns `{new_uuid}`.
12. Admin is prompted to create matching `tarifas_sucursal` rows (frontend shows "Add tariffs for this new vehicle type?"). If admin skips, branches will see "No tariff configured" on ingreso for this type.
13. Branch receives parametrization; UPSERT new row, UPDATE local old row.

**Tables touched (writes)**: `tipos_vehiculo` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipos_vehiculo` (current state + uniqueness), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `tipos_vehiculo` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipos_vehiculo.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (admin's branch); each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipos_vehiculo` (current state), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `tipos_vehiculo` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: the FK RESTRICT from `ingreso.uuid_tipo_vehiculo`, `tarifas_sucursal.uuid_tipo_vehiculo`, `cantidad_vehiculos_sucursal.uuid_tipo_vehiculo`, and `vehiculos.uuid_tipo_vehiculo` ensures that an archived `tipo_vehiculo` cannot be deleted while references exist. The FK is to the SPECIFIC version (`uuid_tipo_vehiculo` of the ingreso at creation time), so an archived tipo keeps working for historical FKs but cannot be picked on new ingresos.
- Related: see T14 (`tarifas_sucursal`) for the cross-table cascade — adding a new `tipo_vehiculo` requires creating matching `tarifas_sucursal` rows for each branch.

### 7.2 Use Case: `uc.tipos-vehiculo.parametrization-push-to-branches`

Whenever `tipos_vehiculo` changes (use case 7.1), cloud parametrization push delivers the new version to all active branches within 30s. Branch UPSERTs the row locally. The parametrization worker tracks per-branch delivery state in `sync_queue` (each branch's parametrization pending list) and emits `sync_log` cycle metrics. If a branch is offline, the parametrization is queued and delivered when connectivity returns (no special handling — the parametrization queue is persistent).

**Actor**: sync worker (cloud parametrization worker → branch parametrization receiver)

**Pre-conditions**: cloud has the new/updated `tipos_vehiculo` row (use case 7.1); branch is paired (valid `sync-agent-` JWT); branch has completed parametrization sync for the prior version.

**Steps**:
1. Cloud parametrization worker fires every 30s. Reads the parametrization delta: `tipos_vehiculo` rows whose `sync_status='pendiente'` AND `created_at > last_sync_per_branch[$branch]`.
2. Worker groups the delta by branch (all branches receive the same parametrization for catalogs — there's no per-branch override for `tipos_vehiculo`).
3. Worker POSTs `api_sucursal /sync/parametrization/pull` to each branch (with `sync-agent-` JWT) carrying the catalog delta.
4. Branch handler receives. Opens TX.
5. Branch SELECTs the local `tipos_vehiculo` row by `uuid` (or marks as missing for INSERT). Compares `version_hash` against the incoming.
6. Branch UPSERTs `tipos_vehiculo` row locally. For UPDATE: applies the `vigente_hasta` archive.
7. Branch INSERTs `log_transaccional` (`accion='tipos_vehiculo_parametrized'`, `tabla_afectada='tipos_vehiculo'`, `uuid_registro_afectado=$uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_anteriores=$local_snapshot`, `datos_nuevos=$cloud_snapshot`). The local chain extends.
8. Branch `queue_processor.ack` the parametrization; INSERT `sync_log` row with `operaciones_enviadas=1, operaciones_exitosas=1, duracion_ms=...`.
9. Branch UI: next `IngresoForm` render shows the new `tipo_vehiculo` in the dropdown.
10. (If branch was offline) The parametrization is queued in the branch's local `sync_queue` (separate from the operation queue). When connectivity returns, `job_sync_sucursal/drain_outbox` flushes.

**Tables touched (writes)**: `tipos_vehiculo` (UPSERT, branch local), `log_transaccional` (1 row per parametrization receipt), `sync_log` (1 row per cycle).
**Tables touched (reads)**: `tipos_vehiculo` (local + cloud via parametrization), `log_transaccional` (chain anchor), `usuarios` (SYSTEM), `sucursal` (self).
**FKs traversed**: `tipos_vehiculo` has NO FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipos_vehiculo.uuid`.
**Sync behavior**:
- Branch → cloud: NO (branch receives, doesn't push parametrization).
- Cloud → branch: YES — parametrization push every 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — each branch chain extends by 1 row per parametrization receipt.
**Integration**:
- Reads from: `tipos_vehiculo` (cloud source), `log_transaccional` (chain anchor), `usuarios` (SYSTEM), `sucursal` (self).
- Writes to: `tipos_vehiculo` (local mirror), `log_transaccional` (audit), `sync_log` (cycle metrics).
- Cross-cutting: this is the canonical **cloud→branch parametrization** flow. The catalog is identical on all branches (no per-branch override for vehicle types). Per-branch variation happens at `tarifas_sucursal` (T14) and `cantidad_vehiculos_sucursal`, which are explicitly keyed by `uuid_sucursal`.
- Related: parametrization conflicts (cloud and branch both modify the row, in theory) can't happen because branches don't write `tipos_vehiculo` — only cloud does. The `sync_queue` for parametrization is one-way (cloud → branch), no `sync_conflict` possible.

### 7.3 Use Case: `uc.tipos-vehiculo.branch-picks-on-ingreso-mandatory-fk`

Operator at the booth records an ingreso. The `IngresoForm` shows a dropdown of vigentes `tipos_vehiculo` (per use case 7.2). Operator MUST select one (the FK is NOT NULL with RESTRICT on the catalog). The selection cascades through the calculation: `tarifas_sucursal` lookup (vigente for the (sucursal, tipo_vehiculo, tipo_tarifa) triple), `cantidad_vehiculos_sucursal` check (cupo), `vehiculos` lookup (for subscribers). The ingreso row is INSERTed with `uuid_tipo_vehiculo=$selected_uuid`, FK preserved.

**Actor**: operator (branch)

**Pre-conditions**: branch has the vigentes `tipos_vehiculo` parametrized (use case 7.2); operator has `permiso='crear_ingresos'`; branch has matching `tarifas_sucursal` rows for the (sucursal, tipo_vehiculo) pair (else operador will see the banner from T14 use case 7.2).

**Steps**:
1. Vehicle arrives at the booth. Operator opens `web_sucursal/IngresoForm`.
2. Frontend GETs `api_sucursal /tipos-vehiculo?vigente_only=true` (own branch scoped).
3. Backend returns the vigentes (typically 4 rows: `auto`, `moto`, `camioneta`, `bicicleta`).
4. Frontend renders dropdown (mandatory selection). Operator **types the plate** and **selects** `tipo_vehiculo='auto'`.
5. Frontend optionally GETs `api_sucursal /tarifas-sucursal?vigente_only=true&uuid_tipo_vehiculo=auto&uuid_tipo_tarifa=por_hora` to show "Tarifa vigente: $X/hora" preview.
6. Frontend POSTs `api_sucursal /ingresos` with `{placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente: null}`.
7. Backend: SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`. SELECT `cantidad_vehiculos_sucursal` for the (sucursal, tipo_vehiculo) pair; compare against current `ingreso WHERE estado='activo' AND uuid_tipo_vehiculo=$tipo AND uuid_sucursal=$branch` count. If full → 409 `cupo_lleno` (T04 use case 7.5).
8. INSERT `ingreso` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `placa=$plate`, `uuid_tipo_vehiculo=$tipo_uuid`, `uuid_subscripcion_cliente=NULL`, `fecha_ingreso=NOW()`, `estado='activo'` derived).
9. INSERT `log_transaccional` (`accion='ingreso_creado'`, `tabla_afectada='ingreso'`, `uuid_registro_afectado=$ingreso_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_anteriores=null`, `datos_nuevos=$ingreso_snapshot`).
10. `queue_processor.enqueue('ingreso', $uuid, $snapshot)` → INSERT `sync_queue`.
11. (Optional) Barrier opens.
12. Return `{uuid, fecha_ingreso}` to frontend.

**Tables touched (writes)**: `ingreso` (1 row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `tipos_vehiculo` (vigente lookup), `tarifas_sucursal` (preview), `cantidad_vehiculos_sucursal` (cupo check), `ingreso` (current count), `log_transaccional` (chain anchor), `sucursal` (tenant + chain key).
**FKs traversed**: `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid` (the mandatory classification); `ingreso.uuid_sucursal` → `sucursal.uuid`; `tarifas_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid` (read for preview); `cantidad_vehiculos_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid` (read for cupo); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `ingreso.uuid`.
**Sync behavior**:
- Branch → cloud: YES — `ingreso` + `log_transaccional` push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact for this specific action).
- DIAN trigger: NO (ingreso doesn't trigger DIAN; only facturacion does).
- Hash chain impact: YES — branch chain extends by 1 row; cloud chain extends by 1 row on receipt.
**Integration**:
- Reads from: `tipos_vehiculo` (vigente), `tarifas_sucursal` (preview), `cantidad_vehiculos_sucursal` (cupo), `ingreso` (current count), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `ingreso` (the business event), `log_transaccional` (audit), `sync_queue` (deferred propagation).
- Cross-cutting: `uuid_tipo_vehiculo` is the FK that ties the ingreso to a specific version of the catalog. Even if admin later archives the tipo (creates a new version + `vigente_hasta=NOW()` on old), the historical ingreso keeps the FK reference to the archived version — desired for probatory integrity.
- Related: if the operator tries to submit without selecting `tipo_vehiculo`, the frontend rejects (required field). The backend ALSO validates NOT NULL at the DB level (defense in depth).

### 7.4 Use Case: `uc.tipos-vehiculo.reference-in-vehiculos-subscriber-and-tarifas`

The `tipos_vehiculo` UUID is also referenced from `vehiculos` (subscriber vehicles) and `tarifas_sucursal` (per-branch pricing). When admin creates a `vehiculos` row for a new subscriber's car, the FK to `tipos_vehiculo` classifies the vehicle (auto, moto, etc.); this classification drives the tariff at ingreso preview (via `tarifas_sucursal` lookup for the triple). At subscriber arrival (T04 use case 7.2), operator looks up by cedula, picks the right vehicle, and the system uses the FK to look up the tarifa preview — no extra UI step.

**Actor**: admin (creates `vehiculos`) + operator (subscriber lookup at arrival)

**Pre-conditions**: branch has the vigentes `tipos_vehiculo` parametrized (use case 7.2); admin has `permiso='crear_vehiculos'`; subscriber's `subscripciones_cliente` row exists with associated vehicles.

**Steps**:
1. **Admin creates subscriber vehicle**: Admin opens `web_admin/ClientesDetail/{cliente_uuid}/VehiculosTab`, clicks `Add Vehiculo`. Fills `placa='ABC123'`, selects `tipo_vehiculo='auto'` from dropdown.
2. Frontend POSTs `api_admin /vehiculos` with `{placa, uuid_tipo_vehiculo=$auto_uuid, uuid_subscripcion_cliente=$sub_uuid}`.
3. Backend: SELECT `subscripciones_cliente.cantidad_maxima_vehiculos` (from `tipo_subscripciones`); compare against current `vehiculos` count for the subscription. If exceeded → 409 `cupo_subscripcion_lleno`. Else INSERT `vehiculos` + `subscripcion_vehiculos` (junction).
4. INSERT `log_transaccional` (`accion='vehiculo_creado'`, `tabla_afectada='vehiculos'`, `uuid_registro_afectado=$vehiculo_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch_of_sub`, `datos_anteriores=null`, `datos_nuevos=$vehiculo_snapshot`).
5. `queue_processor.enqueue('vehiculos', $uuid, $snapshot)` → branch receives parametrization.
6. **Subscriber arrives** (operator flow): Operator opens `IngresoForm`, clicks "Cliente con subscripción", types `cedula='1234567890'`.
7. Backend returns the matching `clientes` row, then the `subscripciones_cliente` for that cliente at this branch, then the `subscripcion_vehiculos` JOIN `vehiculos` JOIN `tipos_vehiculo` for the subscription. Frontend shows list: `ABC123 (auto)`, `DEF456 (auto)`. Operator picks `ABC123`.
8. Frontend POSTs `api_sucursal /ingresos` with `{placa='ABC123', uuid_tipo_vehiculo=$auto_uuid_from_subscripcion_lookup, uuid_subscripcion_cliente=$sub_uuid}`.
9. Backend INSERTs `ingreso` (linked to subscription + has the `uuid_tipo_vehiculo` from the `vehiculos` lookup). INSERT `log_transaccional`.
10. At departure (subscriber flow, T05 use case 7.3): system checks `ingreso.uuid_subscripcion_cliente IS NOT NULL AND active` → NO factura is created (subscription is consumed).

**Tables touched (writes)** — admin path: `vehiculos` (1 row), `subscripcion_vehiculos` (1 junction row), `log_transaccional` (1 row), `sync_queue` (1 parametrization item). Operator path: `ingreso` (1 row), `log_transaccional` (1 row), `sync_queue` (1 operation item).
**Tables touched (reads)**: `tipos_vehiculo` (vigente for dropdown + FK lookup), `vehiculos` (admin: existing count per subscription; operator: lookup by subscripcion_vehiculos), `subscripciones_cliente` (admin: cupo check; operator: lookup by cliente), `subscripcion_vehiculos` (junction), `clientes` (operator: cedula lookup), `tipo_subscripciones` (admin: cantidad_maxima_vehiculos), `log_transaccional` (chain anchor).
**FKs traversed**: `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`. `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `vehiculos.uuid` (admin) or `ingreso.uuid` (operator).
**Sync behavior**:
- Branch → cloud: YES — admin's `vehiculos` row travels via parametrization pull (cloud→branch direction for subscribers is bidirectional: cloud is master for catalogs, branch is master for the subscriber data — both directions).
- Cloud → branch: YES — parametrization push delivers the new `vehiculos` row to the operating branch within 30s.
- DIAN trigger: NO (vehiculo creation doesn't trigger DIAN).
- Hash chain impact: YES — chain (admin branch + operating branch) extends by 1 row each.
**Integration**:
- Reads from: `tipos_vehiculo` (vigente), `vehiculos` (cupo + lookup), `subscripciones_cliente` (active check), `subscripcion_vehiculos` (junction), `clientes` (cedula lookup), `tipo_subscripciones` (cantidad_maxima_vehiculos), `log_transaccional` (chain anchor).
- Writes to: `vehiculos`, `subscripcion_vehiculos`, `log_transaccional`, `sync_queue`.
- Cross-cutting: the `tipos_vehiculo` UUID is the classification hub that ties together `ingreso`, `vehiculos`, `tarifas_sucursal`, and `cantidad_vehiculos_sucursal`. A change in classification (e.g., admin PATCHes a `vehiculos.uuid_tipo_vehiculo` from `moto` to `auto` for a vehicle the subscriber upgraded) creates a NEW version of `vehiculos` (T20) — but the historical FK to `tipos_vehiculo` is preserved.
- Related: see T20 (`vehiculos`) and T14 (`tarifas_sucursal`) for the cross-table cascade — the `tipos_vehiculo` is the join key for tariff lookup at subscriber arrival.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 31.

## 9. RED Tests
- (RED) `tipo` unique; duplicate → UNIQUE violation.
- (RED) ON DELETE RESTRICT.

## 10. Implementation Tasks
- [x] F1.x Seed (4 types).
- [ ] IT-2.x: admin CRUD.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| New type added | Low | Migration + seed + sync |

## 12. Open Questions
- (a) Dynamic types vs fixed 4?