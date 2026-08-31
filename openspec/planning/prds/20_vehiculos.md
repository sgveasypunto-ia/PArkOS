# PRD: vehiculos (T20)

> Subscriber vehicles (with active subscription). The placa is **UNIQUE per business** — same plate can only exist once across the system (casual visitors don't have a row here; their plate is captured directly on `ingreso.placa` as a string). Vehicles are linked to subscriptions via `subscripcion_vehiculos` bridge (N:M).

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I: vehiculo CRUD is segregated from ingreso CRUD (casual plates NOT stored here)*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.vehiculos`
- **SQL name**: `vehiculos` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite (legal vehicle record per subscriber)
- **Origin**: F1 (schema) + IT-10 (admin CRUD, plate changes)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; casual-no-FK distinction + plate change cascade documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `placa` is **UNIQUE** (business rule) — same plate can only exist ONCE in the system. Two subscribers cannot register the same plate (data entry error protection).
- **`placa` is NOT a FK**. The casual visitor's placa (captured on `ingreso.placa`) is a string that may or may not match an entry in `vehiculos`. If match → subscriber arrival; if no match → casual arrival.
- `uuid_tipo_vehiculo` is FK to `tipos_vehiculo` (auto, moto, camioneta, bicicleta).

## 3. SOLID Atomic Breakdown
- **S**: "one subscriber vehicle" — a vehicle with active subscription registered in the system. The casual visitor's placa is NOT stored here (per business model).
- **O**: extensible via migration if new attributes are needed (e.g., `marca`, `modelo`, `color`, `soat_vencimiento`); current model has only `placa` + `uuid_tipo_vehiculo`. Per SOLID O, prefer JSON `registro` if extension is one-off (sprint 5 may add).
- **I**: admin CRUD via `api_admin /vehiculos`; branch reads own + cross-branch lookup via `api_sucursal /vehiculos?placa=...` (for operator arrival lookup).
- **D**: `parkos_core/models/V/vehiculos.py` (model); `parkos_core/vehiculos/placa_lookup_service.py::find_active(placa)` (returns vehiculo + active subscription + cliente).
- **Atomic**: INSERT (admin creates), UPDATE (creates new version on plate change — archive old, new with new `placa` + `uuid_tipo_vehiculo`), DELETE forbidden by FK RESTRICT (subscripcion_vehiculos references).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_tipo_vehiculo` | `prod.tipos_vehiculo.uuid` | exactly one (NOT NULL) | RESTRICT | the vehicle type |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `subscripcion_vehiculos.uuid_vehiculo` | `\|\|--o{` | vehiculo in subscriptions (N:M) |

**Important distinction**: `ingreso.placa` is a STRING column on `ingreso` — it is NOT a FK to `vehiculos.placa`. Casual visitor plates are captured as strings without requiring a `vehiculos` row.

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin creates new vehiculo (placa + tipo); inside TX + `log_transaccional` |
| UPDATE | YES (version flow) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted with new `placa` / `uuid_tipo_vehiculo`. Plate change = new row (different UUID), old archived. |
| DELETE | NO | Archive via version flow; FK RESTRICT prevents |

**Special rules**:
- **UNIQUE on `placa`** — only ONE vigente row per placa at a time (enforced via UNIQUE constraint or partial UNIQUE index `WHERE vigente_hasta IS NULL`).
- **Plate change pattern**: when subscriber sells their car and gets a new one with a different plate, admin archives the old `vehiculos` row (with `motivo='vehiculo_vendido'`) and creates a NEW row for the new plate. The old row stays forever (audit). The subscriber's subscriptions remain — admin must add the new vehiculo to each subscription via T19 7.1.
- **Casual plates NOT stored here**: a casual visitor's plate is captured directly on `ingreso.placa` (string, not FK). If the same casual later becomes a subscriber, the admin can either: (a) create a new `vehiculos` row with the same plate (the system checks for existence — if a soft match is found, admin can decide to link); (b) the casual visits accumulate as `ingreso.placa` strings in the historical data but are never reconciled to `vehiculos`.

## 6. CodeGraph Dependencies
- `api_admin/routers/vehiculos.py::POST /vehiculos`, `PATCH /vehiculos/{uuid}`, `GET /vehiculos`, `GET /vehiculos/{uuid}`.
- `api_sucursal/routers/vehiculos.py::GET /vehiculos?placa=...` (operator lookup at arrival — the heart of subscriber identification).
- `api_sucursal/routers/vehiculos.py::GET /vehiculos/{uuid}/subscripciones` (joined: vehiculo + active subscriptions + cliente).
- `parkos_core/vehiculos/placa_lookup_service.py::find_active(placa)` (returns vehiculo + active subs + cliente).
- `web_admin/VehiculosList`, `VehiculoForm`, `VehiculoDetail/SubscripcionesTab`.

## 7. Use Cases enabled by this table

The `vehiculos` table is the **subscriber vehicle registry**: each row represents one vehicle with an active subscription, identified by `placa` (UNIQUE). The critical distinction is that **casual visitor plates are NOT stored here** — they're captured as strings on `ingreso.placa`. Use cases below describe the admin create flow, the operator lookup at subscriber arrival, the casual-no-FK distinction (critical for the data model), and the plate change cascade pattern.

### 7.1 Use Case: `uc.vehiculos.admin-creates-for-cliente`

Admin cloud registra un nuevo vehículo para un cliente (cliente compró un auto, quiere incluirlo en su subscripción). Inserta la fila `vehiculos` con `placa`, `uuid_tipo_vehiculo`. La placa es UNIQUE — si ya existe (casual previo que ahora es subscriber), el sistema detecta y permite archivar el anterior o rechazar. Después de crear el vehiculo, el admin típicamente lo agrega a una o más subscripciones via T19 7.1. El flujo toca 6 tablas: `vehiculos` (W), `clientes` (R validar), `tipos_vehiculo` (R), `permisos_usuario` (R RBAC), `log_transaccional` (W), `sync_queue` (W).

**Actor**: admin

**Pre-conditions**: `clientes` row exists (typically with active subscriptions); `tipos_vehiculo` exists; admin has `permiso='crear_vehiculos'`; no existing `vehiculos` row with same `placa` vigente.

**Steps**:
1. Admin opens `web_admin/ClientesDetail/{uuid_cliente}/VehiculosTab`, clicks `New Vehiculo`.
2. Frontend shows `VehiculoForm`: `placa='GHI789'`, `uuid_tipo_vehiculo='auto'` (or 'moto', 'camioneta', 'bicicleta' from catalog). Optional `registro` JSON: `{marca: 'Toyota', modelo: 'Corolla', color: 'Gris', soat_vencimiento: '2027-01-15'}` (sprint 5 may add).
3. Frontend POSTs `api_admin /vehiculos` (admin- JWT) with `{placa, uuid_tipo_vehiculo, registro}`.
4. Backend validates `permisos_usuario` for `permiso='crear_vehiculos'`.
5. Backend SELECTs `vehiculos` WHERE `placa='GHI789' AND vigente_hasta IS NULL`. If exists: 409 conflict (UNIQUE violation).
6. Backend SELECTs `tipos_vehiculo` WHERE `uuid=$uuid_tipo_vehiculo AND vigente_hasta IS NULL`. Validates exists.
7. Backend opens TX; SELECT chain anchor from `log_transaccional`.
8. Backend INSERTs `vehiculos` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`).
9. Backend INSERTs `log_transaccional` (`accion='vehiculo_creado'`, `tabla_afectada='vehiculos'`, `uuid_registro_afectado=$new_uuid`, `datos_anteriores=null`, `datos_nuevos={placa, uuid_tipo_vehiculo, uuid_cliente_implied: $c}`).
10. `queue_processor.enqueue('vehiculos', $new_uuid, $snapshot)` → parametrization push.
11. Backend returns `{uuid, placa, uuid_tipo_vehiculo, vigente_desde}` to frontend.
12. Branches receive parametrization within 30s. UPSERTs locally. Operator can now find this vehiculo by placa.

**Tables touched (writes)**: `vehiculos` (1 row), `log_transaccional` (1 row), `sync_queue` (1 row).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `vehiculos` (UNIQUE check), `tipos_vehiculo` (catalog), `clientes` (validate context — admin is creating for a specific cliente, but the FK is implicit via subscription, not direct), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `vehiculos.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (vehiculo_creado); branch chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `vehiculos` (UNIQUE check), `tipos_vehiculo`, `clientes` (context), `log_transaccional`, `usuarios`.
- Writes to: `vehiculos` (new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **subscriber vehicle registration**. After creation, the vehiculo is "available" — but NOT yet in any subscription. Admin typically follows up with T19 7.1 to add it to one or more subscriptions.
- Related: there is NO direct FK from `vehiculos` to `clientes` in the current model — the relationship is implicit via `subscripcion_vehiculos` bridge → `subscripciones_cliente` → `clientes`. This allows a vehiculo to be in subscriptions for multiple clientes (rare but possible — e.g., shared family car). Sprint 5 may add `vehiculos.uuid_cliente_propietario` FK for direct ownership tracking.

### 7.2 Use Case: `uc.vehiculos.branch-lookup-by-placa-at-subscriber-arrival`

Llega un vehículo al parqueadero. El operador NO tiene escáner (sistema sin QR/OCR) — tipea la placa en el `IngresoForm`. El frontend hace GET al endpoint de vehiculos. Si match → el operador ve los detalles del cliente + subscripciones activas + vehículos y selecciona el apropiado. Si no match → operador selecciona "Cliente con subscripción" (lookup por cedula) o "Casual" (no subscriber). **Es READ puro** — no extiende la hash chain.

**Actor**: operator (display only)

**Pre-conditions**: subscriber is registered; vehiculo is linked to active subscription at this branch.

**Steps**:
1. Vehicle arrives. Operator opens `IngresoForm`, types placa `ABC123` in the `placa` input.
2. Frontend GETs `api_sucursal /vehiculos?placa=ABC123&vigente_only=true`.
3. Backend SELECTs `vehiculos` WHERE `placa='ABC123' AND vigente_hasta IS NULL`. Returns 1 row.
4. If no match: frontend shows "Placa no encontrada — es casual, o busque por cedula". Operator selects `Casual` or `Cliente con subscripción` (lookup by cedula per T16 7.1).
5. If match: Frontend GETs `api_sucursal /vehiculos/{uuid}/subscripciones?estado=activa&uuid_sucursal=$branch`.
6. Backend SELECTs `subscripcion_vehiculos sv JOIN subscripciones_cliente s ON sv.uuid_subscripcion_cliente=s.uuid JOIN clientes c ON s.uuid_cliente=c.uuid` WHERE `sv.uuid_vehiculo=$vehiculo_uuid AND sv.vigente_hasta IS NULL AND s.estado='activa' AND s.vigente_hasta IS NULL AND s.uuid_sucursal=$branch AND s.fecha_vencimiento>=CURRENT_DATE`. Returns 1+ rows (vehiculo in N active subscriptions at this branch).
7. Frontend displays: "Vehículo: ABC123 (auto). Cliente: Juan Pérez. Subscripciones activas: 1 (Plan_Mensual_Auto, vence 2026-09-30). Confirmar ingreso:".
8. Operator confirms. Frontend POSTs `api_sucursal /ingresos` with `{placa: 'ABC123', uuid_tipo_vehiculo: $auto_uuid, uuid_subscripcion_cliente: $sub_uuid}` (per T18 / T04 7.2).
9. (No writes for the lookup itself; the subsequent ingreso creation writes the log row.)

**Tables touched (writes)**: NONE for the lookup.
**Tables touched (reads)**: `vehiculos` (placa lookup), `subscripcion_vehiculos` (JOIN), `subscripciones_cliente` (active filter), `clientes` (denormalized display), `tipos_vehiculo` (catalog JOIN), `usuarios_sucursal` (JWT scope), `sucursal` (tenant).
**FKs traversed**: `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** (read-only).

**Integration with other tables**:
- Reads from: `vehiculos` (placa lookup), `subscripcion_vehiculos`, `subscripciones_cliente`, `clientes`, `tipos_vehiculo`, `usuarios_sucursal`, `sucursal`.
- Writes to: NONE.
- Cross-cutting: this is the **canonical subscriber arrival pattern** — the 2-step GET chain (placa → subscriptions) is the FASTEST path. Operators prefer this over the 3-step chain (cedula → cliente → subscriptions) because most subscribers know their plate but not their cedula.
- Related: if the placa lookup fails (no `vehiculos` row with that plate), the operator falls back to cedula lookup OR marks the visit as casual. The casual placa is captured directly on `ingreso.placa` (next use case).

### 7.3 Use Case: `uc.vehiculos.casual-placa-not-stored-in-vehiculos-table`

Cuando un vehículo casual (NO subscriber) llega al parqueadero, el operador tipea la placa en el `IngresoForm` y selecciona `Casual`. **NO se crea una fila en `vehiculos`** — la placa se captura directamente en `ingreso.placa` (string). Si el mismo casual visita 50 veces, hay 50 filas `ingreso` con la misma `placa` string repetida, pero CERO filas `vehiculos`. Esta es la distinción clave del modelo. El flujo toca 3 tablas en escritura: `ingreso` (W), `log_transaccional` (W), `sync_queue` (W).

**Actor**: operator

**Pre-conditions**: visitor is NOT a subscriber (no `vehiculos` row with that plate).

**Steps**:
1. Casual vehicle arrives. Operator opens `IngresoForm`, types placa `XYZ999`.
2. Frontend GETs `api_sucursal /vehiculos?placa=XYZ999&vigente_only=true`.
3. Backend SELECTs `vehiculos` WHERE `placa='XYZ999' AND vigente_hasta IS NULL`. Returns 0 rows.
4. Frontend shows: "Placa XYZ999 no encontrada. ¿Es casual o busca por cedula?". Operator clicks `Casual`.
5. Frontend shows casual form: `uuid_tipo_vehiculo` selector (auto/moto/etc.), no cliente, no subscripcion.
6. Operator selects `uuid_tipo_vehiculo='auto'`, confirms. Frontend POSTs `api_sucursal /ingresos` with `{placa: 'XYZ999', uuid_tipo_vehiculo: $auto_uuid, uuid_subscripcion_cliente: null}`.
7. Backend INSERTs `ingreso` row (`placa='XYZ999'`, `uuid_subscripcion_cliente=NULL`).
8. Backend INSERTs `log_transaccional` (`accion='ingreso_casual_creado'`, `tabla_afectada='ingreso'`, `uuid_registro_afectado=$ingreso_uuid`, `datos_nuevos={placa, uuid_tipo_vehiculo, casual: true}`).
9. `queue_processor.enqueue`.
10. Vehicle departs later; operator charges per `tarifas_sucursal` vigente (per T05 / T14 7.3 snapshot semantic).
11. **NO `vehiculos` row is ever created** for `XYZ999` — the casual plates live forever as strings in `ingreso.placa` and `salidas.placa`. The historical record is preserved for analysis but doesn't impact the subscriber vehicle catalog.

**Tables touched (writes)**: `ingreso` (1 row), `log_transaccional` (1 row), `sync_queue` (deferred propagation). Later: `salidas` + `facturas` + children per the casual flow.
**Tables touched (reads)**: `vehiculos` (lookup returns 0), `tipos_vehiculo` (catalog), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator).
**FKs traversed**: `ingreso.uuid_sucursal` → `sucursal.uuid`; `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid` (NULL for casual); `ingreso.placa` is a STRING, NOT a FK; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `ingreso.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `ingreso` row + `log_transaccional` row push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact for casual visits).
- DIAN trigger: NO (ingreso doesn't trigger DIAN; only facturacion at departure does).
- Hash chain impact: YES — branch chain extends by 1 row (ingreso_casual_creado); cloud chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `vehiculos` (lookup returns 0), `tipos_vehiculo` (catalog), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator).
- Writes to: `ingreso`, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **CRITICAL MODEL DISTINCTION** — casual plates are NOT in `vehiculos`. The model enforces this by having `ingreso.placa` as a free-form string without FK. This means:
  - No UNIQUE constraint on placa across all visitors (only across subscribers).
  - Historical casual visits are preserved even after the casual's identity is forgotten.
  - Casual visit count for a plate is queryable via `SELECT COUNT(*) FROM ingreso WHERE placa='XYZ999'`.
  - If the casual becomes a subscriber, the admin creates a `vehiculos` row with the same plate (UNIQUE check ensures no conflict — admin can decide whether to backfill historical casual visits into the new vehiculo's record or leave them separate).
- Related: sprint 5 may add `casual_to_subscriber` reconciliation: when admin creates `vehiculos` for a previously-casual plate, optionally backfill the historical `ingreso`/`salidas` rows to link via `uuid_vehiculo` (adding nullable FK to existing tables).

### 7.4 Use Case: `uc.vehiculos.plate-change-archives-old-cascades-bridge`

Admin cloud registra un cambio de placa: el cliente vendió su auto (placa `ABC123`) y compró uno nuevo (placa `JKL012`). Admin archiva la fila vieja de `vehiculos` (con `motivo='vehiculo_vendido'`) y crea una nueva fila con la placa nueva. Las filas `subscripcion_vehiculos` activas para el vehiculo viejo se archivan en la misma TX (cascade). Admin luego agrega el vehiculo nuevo a las subscripciones via T19 7.1. El flujo toca 6 tablas: `vehiculos` (W archive + W nuevo), `subscripcion_vehiculos` (W archive cascade), `log_transaccional` (W x 2-3), `sync_queue` (W parametrización), `permisos_usuario` (R RBAC), `usuarios` (R admin), `sucursal` (R tenant).

**Actor**: admin

**Pre-conditions**: old vehiculo exists with `estado='activo'`; new placa not already in use; admin has `permiso='gestionar_vehiculos'`.

**Steps**:
1. Client calls admin: "Vendí mi ABC123, compré JKL012". Admin opens `web_admin/VehiculosList/{uuid_old}`, clicks `Archive + Replace`.
2. Frontend shows `PlateChangeForm`: old `placa='ABC123'`, new `placa='JKL012'`, optional `uuid_tipo_vehiculo` change (e.g., from auto to camioneta if the new vehicle is different type), `motivo='vehiculo_vendido'`.
3. Frontend PATCHes `api_admin /vehiculos/{uuid_old}/plate-change` with `{new_placa: 'JKL012', new_uuid_tipo_vehiculo: $tipo, motivo: 'vehiculo_vendido'}`.
4. Backend validates `permisos_usuario` for `permiso='gestionar_vehiculos'`.
5. Backend SELECTs `vehiculos` WHERE `placa='JKL012' AND vigente_hasta IS NULL`. If exists: 409 conflict.
6. Backend SELECTs `subscripcion_vehiculos` WHERE `uuid_vehiculo=$uuid_old AND vigente_hasta IS NULL`. Returns N rows (the bridge links to active subscriptions).
7. Backend opens TX; SELECT chain anchor.
8. Backend UPDATEs old `vehiculos` row: SET `vigente_hasta=NOW()` (archive with motivo in `log_transaccional.datos_nuevos.motivo`).
9. Backend UPDATEs each active `subscripcion_vehiculos` row: SET `vigente_hasta=NOW()` (cascade archive in same TX).
10. Backend INSERTs new `vehiculos` row with `placa='JKL012', uuid_tipo_vehiculo=$new_tipo, vigente_desde=NOW(), vigente_hasta=NULL`.
11. Backend INSERTs `log_transaccional` (`accion='vehiculo_plate_changed'`, `tabla_afectada='vehiculos'`, `uuid_registro_afectado=$new_uuid`, `datos_anteriores={old_placa: 'ABC123', old_uuid_vehiculo: $uuid_old, subscriptions_affected: $N}`, `datos_nuevos={new_placa: 'JKL012', motivo: 'vehiculo_vendido'}`).
12. Backend INSERTs additional `log_transaccional` rows for the bulk bridge archive (or one consolidated row).
13. `queue_processor.enqueue` for the new vehiculo + the bridge archives → INSERT N+1 `sync_queue` rows.
14. Backend returns `{new_uuid, old_uuid_archived, subscriptions_affected: $N}`.
15. Branches receive parametrization within 30s. UPSERTs the new vehiculo + the bridge archives. Operator lookup by `ABC123` now returns the archived (no vigente match); lookup by `JKL012` returns the new vehiculo.
16. Admin now needs to add `JKL012` to the same subscriptions: PATCH `/subscripciones-cliente/{uuid}/vehiculos` to add the new vehiculo via T19 7.1 (this is a SEPARATE call; the plate change only archives old, doesn't auto-add new).

**Tables touched (writes)**: `vehiculos` (1 archive UPDATE + 1 new INSERT), `subscripcion_vehiculos` (N archive UPDATEs in bulk), `log_transaccional` (1-2 rows), `sync_queue` (N+1 rows).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `vehiculos` (UNIQUE check for new placa), `subscripcion_vehiculos` (bulk scan for cascade), `subscripciones_cliente` (validate), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (tenant).
**FKs traversed**: `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid` (old UUID for archive); `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `vehiculos.uuid` (new) + `subscripcion_vehiculos.uuid` (cascade log); `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push delivers all changes within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1-2 rows (plate_changed + cascade); branch chain extends when received.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `vehiculos` (UNIQUE check), `subscripcion_vehiculos` (cascade scan), `subscripciones_cliente` (validate), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `vehiculos` (archive + new), `subscripcion_vehiculos` (cascade archive), `log_transaccional` (audit + cascade), `sync_queue` (parametrization).
- Cross-cutting: this is the **plate change cascade pattern** — old vehiculo archived, bridges cascade, new vehiculo created. The subscriptions remain (still `estado='activa'`); admin must separately add the new vehiculo to them. This two-step (archive + add-new) is intentional — it preserves the full audit trail and allows admin to verify the new vehiculo's details before linking.
- Related: if the plate change is a typo correction (e.g., admin typed `ABC123` but the real plate is `ABC124`), the same flow applies but with `motivo='correccion_tipo'` instead of `'vehiculo_vendido'`. The historical `ingreso` rows for `ABC123` would remain orphan (linked to the archived vehiculo via bi-temporal query, but not to the new one) — sprint 5 may add `ingreso.uuid_vehiculo` nullable FK to link historical casual visits to the subscriber vehiculo post-fact.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 28, 31.

## 9. RED Tests
- (RED) F1 schema includes `vehiculos` with UNIQUE on `placa`.
- (RED) Admin POST `/vehiculos` with new placa → 201; row persisted.
- (RED) Admin POST with duplicate placa → 409 (UNIQUE violation).
- (RED) Operator GET `/vehiculos?placa=ABC123` → 200 with vehiculo + active subscriptions.
- (RED) Operator GET with non-existent placa → 404.
- (RED) Casual ingreso: `ingreso.placa='XYZ999'` is captured even though NO `vehiculos` row exists for `XYZ999`.
- (RED) Subscriber arrival: `ingreso.placa='ABC123'` where `vehiculos` row exists → ingreso linked to subscription.
- (RED) Plate change: admin PATCH → old vehiculo archived, new created, bridge rows cascade archived.
- (RED) Plate change with new placa already in use → 409.
- (RED) Cross-audience: operador from branch A to `/vehiculos/{uuid_b}` (vehiculo belongs to another branch's subscription) → 403.
- (RED) ON DELETE RESTRICT: cannot delete `tipos_vehiculo` while `vehiculos` references it.
- (RED) ON DELETE RESTRICT: cannot delete `vehiculos` while `subscripcion_vehiculos` references it.

## 10. Implementation Tasks
- [x] F1.x Schema with UNIQUE on `placa`.
- [ ] IT-10.x: `api_admin /vehiculos` (POST, PATCH, GET list, GET detail).
- [ ] IT-10.x: `api_admin /vehiculos/{uuid}/plate-change` (admin plate change flow with cascade).
- [ ] IT-10.x: `api_sucursal /vehiculos` (lookup, GET detail, GET subscripciones).
- [ ] IT-10.x: `parkos_core/vehiculos/placa_lookup_service.py::find_active()`.
- [ ] IT-10.x: parametrization push for vehiculo updates.
- [ ] Sprint 5: `vehiculos.registro` JSON for `marca`, `modelo`, `color`, `soat_vencimiento` (current model has only placa + tipo).
- [ ] Sprint 5: `vehiculos.uuid_cliente_propietario` FK for direct ownership (current: implicit via subscription bridge).
- [ ] IT-10.x: `web_admin/VehiculosList`, `VehiculoForm`, `VehiculoDetail/SubscripcionesTab`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Plate typo at creation | Med | UNIQUE catches duplicates; admin can use plate-change flow with motivo='correccion_tipo' |
| Casual becomes subscriber (need to create vehiculo with existing casual plate) | Med | Admin creates vehiculo with same placa; UNIQUE check passes if no vigente match; historical casual `ingreso` rows remain string-based (not linked) |
| Plate change orphan: bridge cascade but admin forgets to add new vehiculo | Low | UI shows warning "Subscriptions archived; remember to add new vehiculo"; admin must confirm |
| Concurrent placa creation race | Low | UNIQUE constraint catches at INSERT; second admin sees 409 |
| Cross-branch vehiculo confusion | Med | Documented: vehiculo is GLOBAL (UNIQUE placa system-wide); subscriptions are branch-pinned. Operator in branch A sees vehiculo from branch B's subscription — UI shows scope clearly. |
| `ingreso.placa` typo (operator error) | Med | Per T04 7.4 — operator can anulate and re-create. NO UPDATE on `ingreso`. |

## 12. Open Questions
- (a) `vehiculos.registro` JSON for `marca`, `modelo`, `color`, `soat_vencimiento`: sprint 5 migration. Current model lacks these; admins track them informally.
- (b) `vehiculos.uuid_cliente_propietario` FK: would simplify queries ("all vehiculos owned by cliente X") but breaks the N:M flexibility (shared family car). Sprint 5 may add as nullable + explicit JOIN.
- (c) Plate format validation (e.g., Colombia: 3 letters + 3 digits, or 3 letters + 3 digits + 1 letter): per-application validator; sprint 5 may add per-country format support.
- (d) Soat/technical inspection expiry monitoring: like `documentos/expiry_monitor` for licenses; sprint 5 may add `vehiculos/expiry_monitor` for soat_vencimiento.
- (e) Casual-to-subscriber reconciliation: backfill historical `ingreso`/`salidas` rows to link to new `vehiculos` via nullable FK. Sprint 5.
- (f) Multi-vehicle owner (1 vehiculo in 2 subscriptions across branches): supported by current N:M bridge; UI may need clarity on "show all subscriptions for this vehiculo across branches".
- (g) Plate change vs correct typo: distinguish via `motivo` field on `log_transaccional`; sprint 5 may add dedicated `vehiculo_evento` table for richer event tracking.
- (h) `placa` formatting (uppercase, no spaces): current model stores as-typed. Sprint 5 may normalize at INSERT (e.g., always UPPERCASE, strip whitespace).
