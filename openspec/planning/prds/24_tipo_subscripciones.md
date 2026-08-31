# PRD: tipo_subscripciones (T24)

> Subscription plan catalog with **business rules encoded in the row**: `cantidad_maxima_vehiculos` (quota), `mismo_tipo_vehiculo` (B2C: TRUE means all vehicles in the sub must be same type; B2B: FALSE), `tipo_cliente_permitido` ('b2c' | 'b2b' | 'ambos'). Rules are enforced at `subscripcion_vehiculos` INSERT (quota check) and at `subscripciones_cliente` creation (client-type check). Versioned via `vigente_desde` / `vigente_hasta` for plan evolution.

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
- **Table name**: `prod.tipo_subscripciones`
- **SQL name**: `tipo_subscripciones` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seeded plans) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 4 use cases covering admin create, branch pick on subscripcion create, quota enforcement at arrival, and plan versioning on rule change)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `tipo` unique string ('mensual' / 'trimestral' / 'anual').

## 3. SOLID Atomic Breakdown
- **S**: "one subscription plan".
- **O**: new column `mismo_tipo_vehiculo` (B2C: TRUE means vehicles must be same type; B2B: FALSE).
- **I**: admin CRUD.
- **D**: `parkos_core/models/V/tipo_subscripciones.py`.
- **Atomic**: INSERT, UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `subscripciones_cliente.uuid_tipo_subscripcion` | `\|\|--o{` | subscriptions |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Seed |
| UPDATE | YES | Inside TX + `log_transaccional` |
| DELETE | NO | RESTRICT |

## 6. CodeGraph Dependencies
- `api_admin/routers/tipo-subscripciones.py`.

## 7. Use Cases enabled by this table

The `tipo_subscripciones` table is the **subscription plan catalog that encodes business rules**. Unlike `tipo_persona` (T22) which is purely a classification, `tipo_subscripciones` carries enforcement logic: `cantidad_maxima_vehiculos` (quota), `mismo_tipo_vehiculo` (B2C vs B2B vehicle homogeneity), and `tipo_cliente_permitido` (which client types can subscribe to this plan). These rules are NOT enforced at DB level (they're application-layer checks) but are READ at every `subscripcion_vehiculos` INSERT and at every subscriber arrival. Use cases below describe admin CRUD, the branch pick on `subscripciones_cliente` creation, the quota enforcement at arrival (T04 use case 7.6 reference), and the plan versioning on rule change. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.tipo-subscripciones.admin-creates-plan`

Cloud admin creates a new subscription plan via `web_admin/Catalogos/TipoSubscripcionesForm`. Fills the business rules: `tipo='mensual_plus'`, `valor=150000` (COP), `duracion_dias=30`, `cantidad_maxima_vehiculos=3`, `mismo_tipo_vehiculo=false` (B2B — vehicles can be of different types within one subscription), `tipo_cliente_permitido='ambos'` (both B2C natural and B2B juridica can subscribe). Backend INSERTs the plan + `log_transaccional` + parametrization push to branches.

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='administrar_catalogos'`; the new `tipo` is unique (DB constraint); the plan rules are internally consistent (e.g., if `tipo_cliente_permitido='b2c'`, then `mismo_tipo_vehiculo` should typically be TRUE).

**Steps**:
1. Admin opens `web_admin/Catalogos/TipoSubscripciones`, clicks `New`.
2. Frontend POSTs `api_admin /tipo-subscripciones` (admin- JWT) with `{tipo='mensual_plus', valor=150000, duracion_dias=30, cantidad_maxima_vehiculos=3, mismo_tipo_vehiculo=false, tipo_cliente_permitido='ambos', vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario` for `permiso='administrar_catalogos'`; rejects 403 if missing.
4. Backend SELECTs current vigentes: `SELECT * FROM tipo_subscripciones WHERE vigente_hasta IS NULL`. Validates UNIQUE on `tipo` (rejects 409 if duplicate).
5. Backend validates business consistency: if `tipo_cliente_permitido='b2c' AND mismo_tipo_vehiculo=false`, WARN but allow (admin may have a B2C plan with heterogeneous vehicles — uncommon but valid).
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
7. INSERT `tipo_subscripciones` row (`uuid=server-generated`, `tipo`, `valor`, `duracion_dias`, `cantidad_maxima_vehiculos`, `mismo_tipo_vehiculo`, `tipo_cliente_permitido`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='tipo_subscripcion_creado'`, `tabla_afectada='tipo_subscripciones'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=null`, `datos_nuevos=$plan_snapshot`).
9. `queue_processor.enqueue('tipo_subscripciones', $new_uuid, $snapshot)` → parametrization push for all active branches within 30s.
10. Backend returns `{new_uuid}`.
11. Branch receives parametrization; UPSERT new row locally. New plan appears in `web_sucursal/SubscripcionesForm` dropdown.
12. Admin may immediately create a new `subscripciones_cliente` for a cliente using this plan (use case 7.2).

**Tables touched (writes)**: `tipo_subscripciones` (1 row), `log_transaccional` (1 row), `sync_queue` (1 parametrization item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_subscripciones` (uniqueness check), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `tipo_subscripciones` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipo_subscripciones.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers the new plan to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipo_subscripciones` (uniqueness check), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `tipo_subscripciones` (the new plan), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: this is a one-time catalog creation; the versioning happens via use case 7.4 (plan evolution). The plan's business rules are stored as-is — no separate `reglas_subscripcion` table. Rules are evaluated at `subscripcion_vehiculos` INSERT (use case 7.3) and at `subscripciones_cliente` creation.
- Related: see T18 (`subscripciones_cliente`) and T20 (`vehiculos`) for the cross-table cascade when a plan is actually applied to a cliente.

### 7.2 Use Case: `uc.tipo-subscripciones.branch-picks-on-subscripcion-create`

Admin (cloud or branch) creates a new `subscripciones_cliente` row for a cliente. Frontend shows a dropdown of vigentes `tipo_subscripciones` plans; admin picks one. Backend validates the plan is compatible with the cliente type (`tipo_cliente_permitido` check) and creates the subscription. The `cantidad_maxima_vehiculos` rule is stored in the plan and applied at `subscripcion_vehiculos` INSERT (use case 7.3).

**Actor**: admin (cloud or branch)

**Pre-conditions**: branch has parametrized vigentes plans (use case 7.1); admin has `permiso='crear_subscripciones'`; cliente exists (`clientes.uuid`).

**Steps**:
1. Admin opens `SubscripcionForm`, selects the cliente (e.g., `Juan Pérez` with `tipo_persona='natural'`), picks the plan from dropdown (e.g., `'mensual_plus'`).
2. Frontend GETs `api_admin /tipo-subscripciones?vigente_only=true` (or branch equivalent).
3. Backend returns vigentes plans.
4. Frontend POSTs `api_admin /subscripciones-cliente` with `{uuid_cliente=$cliente_uuid, uuid_sucursal=$branch, uuid_tipo_subscripcion=$plan_uuid, fecha_vencimiento=$now + duracion_dias}`.
5. Backend validates: SELECT `clientes.uuid_tipo_persona`, JOIN `tipo_persona.tipo`. Check plan's `tipo_cliente_permitido`: if `'b2c'` and cliente is `'juridica'` → 409 `plan_incompatible`. If `'b2b'` and cliente is `'natural'` → 409. If `'ambos'` → OK.
6. Backend SELECTs `tipo_subscripciones.valor`, `duracion_dias` to compute `fecha_vencimiento` if admin didn't override. Validates `cantidad_maxima_vehiculos > 0` (rule sanity).
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
8. INSERT `subscripciones_cliente` row (`uuid=server-generated`, `uuid_cliente`, `uuid_sucursal`, `uuid_tipo_subscripcion`, `fecha_vencimiento=$now+$duracion_dias`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
9. INSERT `log_transaccional` (`accion='subscripcion_creada'`, `tabla_afectada='subscripciones_cliente'`, `uuid_registro_afectado=$sub_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores=null`, `datos_nuevos={cliente_uuid, plan_uuid, fecha_vencimiento, cantidad_maxima_vehiculos}`).
10. `queue_processor.enqueue('subscripciones_cliente', $uuid, $snapshot)` → parametrization push to all branches within 30s.
11. Backend returns `{uuid}`.
12. Admin may now add vehicles via `subscripcion_vehiculos` (subject to `cantidad_maxima_vehiculos` enforcement, use case 7.3).

**Tables touched (writes)**: `subscripciones_cliente` (1 row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_subscripciones` (vigente for dropdown + rules), `clientes` (tipo_persona check), `tipo_persona` (compatibilidad), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (branch).
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`. `clientes.uuid_tipo_persona` → `tipo_persona.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `subscripciones_cliente.uuid`.
**Sync behavior**:
- Branch → cloud: NO (if admin is cloud; if branch, the sub is enqueued for cloud receipt).
- Cloud → branch: YES — parametrization push delivers the new sub to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — chain extends by 1 row on creation; each other branch extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipo_subscripciones` (rules), `clientes` (tipo_persona), `tipo_persona` (compatibilidad), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (branch).
- Writes to: `subscripciones_cliente` (the new subscription), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: the `tipo_cliente_permitido` rule is checked at SUBSCRIPTION CREATION (not at every arrival). Once the sub exists, even if admin later changes the rule (e.g., plan becomes B2C-only), the existing subscription is preserved (historical FK to the plan version vigente at creation time).
- Related: see T18 (`subscripciones_cliente`) for the full lifecycle (creation, activation, expiry, renewal, cancellation).

### 7.3 Use Case: `uc.tipo-subscripciones.quota-enforcement-at-subscriber-arrival`

Subscriber arrives. Operator looks up by cedula (T04 use case 7.2). System reads `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.cantidad_maxima_vehiculos`. Counts current `ingreso` rows WHERE `uuid_subscripcion_cliente=$sub.uuid AND estado='activo'` (derived via `salidas`). If count >= cantidad_maxima → either **block** the subscriber (rare; treats subscription as rigid) or **rotation** (more common; allows the vehicle in but as casual, charging per tariff at departure, opens `alerta` for admin to extend). T04 use case 7.6 documents the rotation flow. This use case focuses on the quota enforcement and the `alerta` trigger.

**Actor**: operator (branch) + admin (cloud, alerted via workflow)

**Pre-conditions**: subscriber has active `subscripciones_cliente`; `tipo_subscripciones.cantidad_maxima_vehiculos=N` (e.g., 3); branch has parametrized vigentes plans; operator has opened `IngresoForm`.

**Steps**:
1. Subscriber arrives. Operator opens `IngresoForm`, clicks "Cliente con subscripción", types `cedula='1234567890'`.
2. Frontend GETs `api_sucursal /clientes?numero_identificacion=$cedula`; backend returns the `clientes` row (with `tipo_persona='natural'`).
3. Frontend GETs `api_sucursal /subscripciones-cliente?uuid_cliente=$cliente_uuid&estado='activa'`; backend returns active subscriptions for that cliente at this branch.
4. Backend SELECTs `tipo_subscripciones.cantidad_maxima_vehiculos` for each subscription (JOIN on `uuid_tipo_subscripcion`).
5. Backend counts current active ingresos: `SELECT COUNT(*) FROM ingreso WHERE uuid_subscripcion_cliente=$sub.uuid AND uuid_sucursal=$branch AND NOT EXISTS (SELECT 1 FROM salidas WHERE salidas.uuid_ingreso = ingreso.uuid) AND NOT EXISTS (SELECT 1 FROM anulaciones WHERE anulaciones.uuid_ingreso = ingreso.uuid AND anulaciones.estado='ejecutada')`. Effectively: ingresos without a matching salida or anulacion.
6. If `current_count >= cantidad_maxima_vehiculos`: trigger quota enforcement.
7. Backend SELECTs chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
8. INSERT `log_transaccional` (`accion='subscripcion_cupo_agotado'`, `tabla_afectada='subscripciones_cliente'`, `uuid_registro_afectado=$sub.uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_anteriores=null`, `datos_nuevos={plate: $plate_arriving, current_count: $count, max_count: $cantidad_maxima_vehiculos}`). Audit row for probatory purposes.
9. INSERT `alerta` workflow chain root (`tipo_alerta='subscripcion_rotacion'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_usuario=$admin_to_notify`, `uuid_alerta_padre=NULL`, `uuid_arqueo=NULL`, `valor_diferencia_efectivo=0`, `valor_diferencia_datafono=0`, `observaciones='subscriber_exceeded_max_vehiculos_at_branch_$branch'`).
10. INSERT `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alert_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `uuid_referencia=$sub.uuid`).
11. INSERT `ingreso` with `uuid_subscripcion_cliente=NULL` (rotation, not subscribed entry) — the ingreso is now a casual entry; the subscriber will pay per tariff at departure. INSERT `log_transaccional` (`accion='ingreso_rotacion_creado'`).
12. `queue_processor.enqueue('ingreso', $uuid, $snapshot)` + parametrization for the alert.
13. Operator UI shows: "Subscripción tiene N/M vehículos ocupados — este ingreso se cobra como casual".
14. Admin sees the `alerta tipo_alerta='subscripcion_rotacion'` in `web_admin/AlertasList`. May follow up to extend the subscription (PATCH `cantidad_maxima_vehiculos` via a new plan version or contact cliente for upsell).

**Tables touched (writes)**: `log_transaccional` (3 rows: subscripcion_cupo_agotado audit + alerta_emitida audit + ingreso_rotacion_creado audit), `alerta` (workflow root), `ingreso` (rotation entry), `sync_queue` (parametrization for alert + operation for ingreso).
**Tables touched (reads)**: `subscripciones_cliente` (active lookup), `tipo_subscripciones` (cantidad_maxima_vehiculos), `clientes` (cedula lookup), `ingreso` (current count), `salidas` (to determine active count), `anulaciones` (to exclude annulled ingresos), `log_transaccional` (chain anchor), `usuarios` (operator + admin to notify), `sucursal` (branch).
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid` (NULL in this case); `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `subscripciones_cliente.uuid` (audit) / `alerta.uuid` (audit) / `ingreso.uuid` (audit); `log_transaccional.uuid_referencia` (polymorphic) → `subscripciones_cliente.uuid` (for alerta_emitida).
**Sync behavior**:
- Branch → cloud: YES — the 3 logs + `alerta` + `ingreso` push via `sync_queue` within 30s.
- Cloud → branch: NO.
- DIAN trigger: NO (ingreso rotation doesn't trigger DIAN directly).
- Hash chain impact: YES — branch chain extends by 3 rows (the 3 logs); cloud chain extends correspondingly on receipt.
**Integration**:
- Reads from: `subscripciones_cliente` (active), `tipo_subscripciones` (rules), `clientes` (cedula), `ingreso` (count), `salidas` (exclude closed), `anulaciones` (exclude annulled), `log_transaccional` (chain anchor).
- Writes to: `log_transaccional` (3 audit rows), `alerta` (workflow root), `ingreso` (rotation entry), `sync_queue`.
- Cross-cutting: the quota enforcement is **application-layer**, NOT DB-layer. PostgreSQL doesn't have a CHECK constraint that can express "max N rows in subscripcion_vehiculos for a given subscription" with referential integrity. The enforcement is in the service layer (`parkos_core/operacion/ingreso_writer.py`). If the service has a bug, the quota can be exceeded — but the `alerta` is the safety net that notifies admin.
- Related: see T04 use case 7.6 for the full rotation flow (this use case is the quota check + alerta trigger; T04 adds the `ingreso` insertion + operator UI). See T41 (`alerta`) for the workflow chain transitions (`abierta → en_revision → resuelta`).

### 7.4 Use Case: `uc.tipo-subscripciones.plan-versioning-on-rule-change`

Cloud admin updates a plan's rules — e.g., `cantidad_maxima_vehiculos` from 3 to 5, or `mismo_tipo_vehiculo` from TRUE to FALSE. The update creates a NEW version of `tipo_subscripciones` (archive old with `vigente_hasta=NOW()`, INSERT new with the changes). Existing `subscripciones_cliente` rows keep their FK reference to the OLD version (the version vigente at the time of subscription creation) — the new version applies only to FUTURE subscriptions. Parametrization push delivers the new version to all branches.

**Actor**: admin (cloud)

**Pre-conditions**: plan exists and is vigente; admin has `permiso='administrar_catalogos'`; at least one `subscripciones_cliente` row references the current plan.

**Steps**:
1. Admin opens `web_admin/Catalogos/TipoSubscripciones/{uuid}`, edits `cantidad_maxima_vehiculos` from 3 to 5.
2. Frontend PATCHes `api_admin /tipo-subscripciones/{uuid}` with `{cantidad_maxima_vehiculos=5, vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigente plan with `SELECT FOR UPDATE` (serializes concurrent admin edits).
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. UPDATE current vigente row SET `vigente_hasta=NOW()` (archive old version with `cantidad_maxima_vehiculos=3`).
7. INSERT new `tipo_subscripciones` row (`uuid=server-generated`, same fields except `cantidad_maxima_vehiculos=5`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='tipo_subscripcion_actualizado'`, `tabla_afectada='tipo_subscripciones'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores={cantidad_maxima_vehiculos: 3, ...}`, `datos_nuevos={cantidad_maxima_vehiculos: 5, ...}`). The audit row preserves old vs new.
9. `queue_processor.enqueue('tipo_subscripciones', $new_uuid, $new_snapshot)` → parametrization push for all branches.
10. Also enqueue the archived row (`vigente_hasta=NOW()`) so branches can update their local mirror.
11. Backend returns `{new_uuid, old_uuid_archived}`.
12. Branch receives parametrization; UPSERT new row, UPDATE local old row with `vigente_hasta=NOW()`. The local mirror reflects the new plan + archived version.
13. **Existing subscriptions are unaffected**: `subscripciones_cliente` rows still FK to the OLD `tipo_subscripciones.uuid` (the archived one). The quota check (use case 7.3) uses the OLD `cantidad_maxima_vehiculos=3` for those subscriptions.
14. **New subscriptions** (use case 7.2) reference the NEW `tipo_subscripciones.uuid` and use `cantidad_maxima_vehiculos=5`.
15. Admin UI shows: "Plan 'mensual_plus' updated from 3 to 5 vehicles. Existing subscriptions retain the 3-vehicle limit until renewal."

**Tables touched (writes)**: `tipo_subscripciones` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_subscripciones` (current vigente + FOR UPDATE), `subscripciones_cliente` (count of existing references — informational), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `tipo_subscripciones` has NO outgoing FKs. `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid` (REFERENCES the version vigente at subscription creation time, NOT a live "current plan" lookup). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipo_subscripciones.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipo_subscripciones` (current state), `subscripciones_cliente` (existing references — informational), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `tipo_subscripciones` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: this is the canonical **plan evolution** pattern. The FK from `subscripciones_cliente.uuid_tipo_subscripcion` to a SPECIFIC version (not a "current plan" lookup) is the key insight — it preserves historical quota limits for existing subscribers. This is the same versioning pattern as T14 (`tarifas_sucursal`) and T26 (`impuestos`): catalog evolution creates new versions, downstream references are pinned to the version at creation time.
- Related: if admin wants to ALSO upgrade existing subscriptions to the new quota, that's a separate `subscripciones_cliente` UPDATE flow (T18) that creates new versions of each affected subscription with `vigente_hasta=NOW()` on old + new with `uuid_tipo_subscripcion=$new_plan_uuid`. Not part of THIS use case.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 10, 11, 13, 31.

## 9. RED Tests
- (RED) `tipo` unique.
- (RED) `cantidad_maxima_vehiculos` enforced at `subscripcion_vehiculos` creation.

## 10. Implementation Tasks
- [x] F1.x Seed.
- [ ] IT-2.x: admin CRUD.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Plan change breaks existing subs | Low | New version with `vigente_desde` |

## 12. Open Questions
- (a) Plan auto-renewal? Out of MVP.