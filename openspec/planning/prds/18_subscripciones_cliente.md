# PRD: subscripciones_cliente (T18)

> Customer subscription to a parking plan at a specific branch. Links `clientes` + `sucursal` + `tipo_subscripciones` with `fecha_vencimiento`. Vehicles are linked via the `subscripcion_vehiculos` bridge table. **The lifecycle is critical**: `estado` traverses `activa → vencida/suspendida` (or `activa → inactiva` via archive). Subscribers DON'T pay per visit — the subscription is "consumed" at departure (no `facturas` row generated).

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I: subscription CRUD is segregated from arrival lookup*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.subscripciones_cliente`
- **SQL name**: `subscripciones_cliente` (with `prod` schema)
- **Enforcement level**: `[V]` projection (lifecycle-driven via `estado` field, which is updated via version flow — new row with new `estado`)
- **Retention**: indefinite (legal subscription record)
- **Origin**: F1 (schema) + IT-10 (admin CRUD, lifecycle management)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; subscription-consumed-not-factura pattern + lifecycle + polymorphic FK documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `fecha_vencimiento` is `date` — when the subscription expires. Independent of the parent B2B `clientes_b2b.fecha_vencimiento` (this is per-subscription; the B2B contract is corporate-level).
- `estado` is `string` with business-level enum: `'activa'`, `'vencida'`, `'suspendida'`, `'inactiva'`, `'archivada'`. Updated via version flow (new row with new `estado`, archive old).

## 3. SOLID Atomic Breakdown
- **S**: "one customer subscription at one branch with one plan, with a specific expiry date and lifecycle state". The subscription is the **commercial anchor** for the subscriber's parking experience — distinct from the per-visit `facturas` used for casual visitors.
- **O**: extensible via migration if new `estado` values are needed (e.g., `'morosa'` for overdue payment); per SOLID O, prefer JSON `registro` if extension is one-off.
- **I**: admin CRUD via `api_admin /subscripciones-cliente`; branch reads own via `api_sucursal /subscripciones-cliente` (for operator lookup at arrival); `clientes/expiry_monitor` cron enforces lifecycle on `clientes_b2b` expiry cascade.
- **D**: `parkos_core/models/V/subscripciones_cliente.py` (model); `parkos_core/subscripciones/lifecycle_service.py` (state transitions); `parkos_core/subscripciones/lookup_service.py` (active lookup at arrival).
- **Atomic**: INSERT (admin creates), UPDATE (creates new version on state transition — archive old, new with new `estado` / `fecha_vencimiento`), DELETE forbidden by FK RESTRICT (vehiculos reference via `subscripcion_vehiculos`).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_cliente` | `prod.clientes.uuid` | exactly one (NOT NULL) | RESTRICT | the customer |
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch (subscription is branch-pinned) |
| `uuid_tipo_subscripcion` | `prod.tipo_subscripciones.uuid` | exactly one (NOT NULL) | RESTRICT | the plan |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `subscripcion_vehiculos.uuid_subscripcion_cliente` | `\|\|--o{` | vehicles in this subscription |
| `ingreso.uuid_subscripcion_cliente` | `\|\|--o{` | ingresos tied to this subscription |
| `reclamos` (polymorphic) | — | FK polimórfica `tipo_reclamable='subscripcion'` (canonical type for customer claims; see T16 7.6) |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin creates new subscription; inside TX + `log_transaccional` |
| UPDATE | YES (version flow) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted with new UUID + new `estado` / `fecha_vencimiento` / etc. State transitions are version flows. |
| DELETE | NO | Archive via version flow; FK RESTRICT prevents |

**Special rules**:
- **Lifecycle states**: `activa` (default after creation) → `vencida` (when `fecha_vencimiento < NOW()` OR when parent `clientes_b2b` expires — per T16/T17) → `suspendida` (admin action for non-payment, etc.) → `inactiva` (archive, general close-out) → `archivada` (terminal, no reactivation).
- **State transitions are version flows** — every change creates a NEW row. The vigente row is the one with `vigente_hasta IS NULL AND estado='activa'` (or whatever state is vigente).
- **Cross-table constraints**:
  - When parent `clientes` is archived, all active subscriptions for that cliente are also marked `inactiva` (per T17 7.3 cascade).
  - When parent `clientes_b2b` expires (T16 7.4), all subscriptions for that cliente are marked `vencida`.
  - When subscription is archived, all `subscripcion_vehiculos` for that sub are also archived (T19).
- **The subscriber-doesn't-pay-per-visit rule** is enforced at the `salidas` creation path (T05 7.3): if `ingreso.uuid_subscripcion_cliente IS NOT NULL AND subscripciones_cliente.estado='activa' AND vigente_desde<=NOW() AND (vigente_hasta IS NULL OR vigente_hasta>NOW())`, NO `facturas` row is created.

## 6. CodeGraph Dependencies
- `api_admin/routers/subscripciones_cliente.py::POST /subscripciones-cliente`, `PATCH /subscripciones-cliente/{uuid}`, `POST /subscripciones-cliente/{uuid}/reactivar`, `GET /subscripciones-cliente`, `GET /subscripciones-cliente/{uuid}`.
- `api_sucursal/routers/subscripciones_cliente.py::GET /subscripciones-cliente?uuid_cliente=...&estado=activa` (operator lookup at arrival).
- `api_sucursal/routers/subscripciones_cliente.py::GET /subscripciones-cliente/{uuid}/vehiculos` (JOIN for operator display).
- `parkos_core/subscripciones/lookup_service.py::active_at(uuid_cliente, uuid_sucursal)` (single-row lookup).
- `parkos_core/subscripciones/lifecycle_service.py::transition(uuid_subscripcion, new_estado, reason)` (state transition with version flow).
- `api_sucursal/routers/salidas.py::POST /salidas` (consumes subscription — checks `ingreso.uuid_subscripcion_cliente` is active; skips facturacion if yes).
- `workers/clientes/expiry_monitor.py` (T16 cron — marks subscriptions as `vencida` when B2B contract expires).
- `web_admin/SubscripcionesList`, `SubscripcionForm`, `SubscripcionDetail/VehiculosTab`.

## 7. Use Cases enabled by this table

The `subscripciones_cliente` table is the **commercial anchor for the subscriber experience**: when a customer has an active subscription, every arrival is linked to it, and every departure CONSUMES it (no `facturas` generated). Use cases below describe the admin create flow (with vehicle linking), the operator lookup at arrival (canonical subscription lookup), the departure-consumes-not-factura rule (the critical business logic), the lifecycle enforcement on expiry, and the polymorphic FK in `reclamos`.

### 7.1 Use Case: `uc.subscripciones.admin-creates-with-vehiculos`

Admin cloud crea una nueva subscripción para un cliente en una branch con un plan específico y N vehículos autorizados (validando contra `tipo_subscripciones.cantidad_maxima_vehiculos`). Las dos escrituras (subscripcion + subscripcion_vehiculos) van en la misma TX para garantizar atomicidad. El flujo toca 8 tablas: `subscripciones_cliente` (W), `subscripcion_vehiculos` (W N bridge rows), `clientes` (R), `sucursal` (R), `tipo_subscripciones` (R validación cantidad_maxima), `vehiculos` (R para validar UUIDs), `permisos_usuario` (R RBAC), `log_transaccional` (W), `sync_queue` (W parametrización).

**Actor**: admin

**Pre-conditions**: `clientes` row exists (B2C natural or B2B juridica); `sucursal` exists with `estado='activo'`; `tipo_subscripciones` exists with desired `cantidad_maxima_vehiculos` (e.g., `Plan_Mensual_Auto` allows 2 vehicles); N `vehiculos` rows exist for this cliente; admin has `permiso='crear_subscripciones'`.

**Steps**:
1. Admin opens `web_admin/ClientesDetail/{uuid_cliente}/SubscripcionesTab`, clicks `New Subscription`.
2. Frontend shows `SubscripcionForm`: branch selector (multi-branch possible — admin picks one), `uuid_tipo_subscripcion` dropdown (shows `Plan_Mensual_Auto`, `Plan_Anual_Moto`, etc., with `cantidad_maxima_vehiculos` displayed), `fecha_vencimiento` (default = NOW() + duracion_dias from `tipo_subscripciones`).
3. Admin selects branch `Sucursal Norte`, plan `Plan_Mensual_Auto` (cantidad_maxima=2), `fecha_vencimiento='2026-09-30'`. The `vehiculos` field shows multi-select of the cliente's existing vehiculos. Admin selects 2: `ABC123 (auto)`, `DEF456 (auto)`.
4. Frontend POSTs `api_admin /subscripciones-cliente` (admin- JWT) with `{uuid_cliente, uuid_sucursal, uuid_tipo_subscripcion, fecha_vencimiento, vehiculos_uuids: ['ABC123_uuid', 'DEF456_uuid']}`.
5. Backend validates `permisos_usuario` for `permiso='crear_subscripciones'`.
6. Backend SELECTs `tipo_subscripciones` WHERE `uuid=$uuid_tipo_subscripcion`. Returns `cantidad_maxima_vehiculos=2`. Validates `len(vehiculos_uuids) <= cantidad_maxima_vehiculos`. If exceeds: 422.
7. Backend SELECTs `clientes` WHERE `uuid=$uuid_cliente` (validate exists), `sucursal` WHERE `uuid=$uuid_sucursal` (validate exists + activo), `vehiculos` WHERE `uuid IN (vehiculos_uuids) AND uuid_cliente_compatible` (validate each vehiculo belongs to the cliente via implicit JOIN).
8. Backend opens TX; SELECT chain anchor from `log_transaccional`.
9. Backend INSERTs `subscripciones_cliente` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activa'`).
10. Backend INSERTs `subscripcion_vehiculos` rows (N bridge rows, one per `vehiculos_uuid`). Each row: `vigente_desde=NOW(), vigente_hasta=NULL, estado='activa'`.
11. Backend INSERTs `log_transaccional` for the subscripcion creation (`accion='subscripcion_creada'`, `tabla_afectada='subscripciones_cliente'`, `uuid_registro_afectado=$new_uuid`, `datos_nuevos={uuid_cliente, uuid_sucursal, uuid_tipo_subscripcion, vehiculos_count: $N}`).
12. Backend INSERTs `log_transaccional` for each `subscripcion_vehiculos` row (or batched).
13. `queue_processor.enqueue('subscripciones_cliente', $new_uuid, $snapshot)` + enqueue each `subscripcion_vehiculos` → INSERT N+1 `sync_queue` rows.
14. Backend returns `{uuid, vehiculos_count, vigente_desde}` to frontend.
15. Branches receive parametrization within 30s. UPSERTs locally. Operator in `web_sucursal/ClientesDetail/{uuid_cliente}/SubscripcionesTab` sees the active subscription.

**Tables touched (writes)**: `subscripciones_cliente` (1 row), `subscripcion_vehiculos` (N rows), `log_transaccional` (1+N rows), `sync_queue` (1+N rows).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `clientes` (validate), `sucursal` (validate + activo), `tipo_subscripciones` (validate cantidad_maxima), `vehiculos` (validate ownership), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `subscripciones_cliente.uuid` + `subscripcion_vehiculos.uuid` (separate rows); `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push delivers all N+1 rows within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1+N rows. Branch chain extends by 1+N rows when received.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `clientes`, `sucursal`, `tipo_subscripciones`, `vehiculos`, `log_transaccional`, `usuarios`.
- Writes to: `subscripciones_cliente` (new), `subscripcion_vehiculos` (N bridge rows), `log_transaccional` (1+N audits), `sync_queue` (1+N parametrización).
- Cross-cutting: this is the **canonical subscription creation flow**. The atomic TX ensures the subscription + vehicles are always in sync (no orphan subscription without vehicles, no orphan vehicle linking). Validation against `tipo_subscripciones.cantidad_maxima_vehiculos` enforces the plan quota.
- Related: if `clientes_b2b` exists for the parent cliente (B2B corporate), the subscription may reference the B2B contract terms indirectly via the JOIN. Sprint 5 may add a direct `uuid_clientes_b2b` FK for clarity.

### 7.2 Use Case: `uc.subscripciones.subscriber-arrival-lookup-3-step-get-chain`

Llega un suscriptor y el operador necesita encontrar su subscripción activa para vincular el ingreso. Ya cubierto en `uc.clientes.subscriber-arrival-lookup-by-cedula` desde el lado `clientes`; aquí lo documentamos desde el lado `subscripciones_cliente`: el operador (o el flujo automatizado) hace el 3-step GET chain. Esta vez, el flujo toca 6 tablas: `subscripciones_cliente` (R), `subscripcion_vehiculos` (R JOIN), `vehiculos` (R), `tipos_vehiculo` (R), `tipo_subscripciones` (R), `sucursal` (R tenant). **Es READ puro** — no extiende la hash chain.

**Actor**: operator (display only)

**Pre-conditions**: cliente has active subscription at current branch; subscription has vehicles linked.

**Steps**:
1. Operator opens `IngresoForm` and selects `Cliente con subscripción`. (Already covered in T16 7.1 for the cliente lookup; this focuses on the subscription lookup.)
2. After cliente is selected, Frontend GETs `api_sucursal /subscripciones-cliente?uuid_cliente=$cliente_uuid&estado=activa&uuid_sucursal=$JWT_branch`.
3. Backend SELECTs `subscripciones_cliente` WHERE `uuid_cliente=$c AND uuid_sucursal=$branch AND estado='activa' AND vigente_hasta IS NULL AND fecha_vencimiento>=CURRENT_DATE`. Returns 1+ rows.
4. For each subscription, Frontend GETs `api_sucursal /subscripciones-cliente/{uuid}/vehiculos`.
5. Backend SELECTs `subscripcion_vehiculos sv JOIN vehiculos v ON sv.uuid_vehiculo=v.uuid JOIN tipos_vehiculo tv ON v.uuid_tipo_vehiculo=tv.uuid` WHERE `sv.uuid_subscripcion_cliente=$sub AND sv.vigente_hasta IS NULL`. Returns the vehicles.
6. Frontend displays: "Subscripción activa: Plan_Mensual_Auto (vence 2026-09-30). Vehículos: ABC123 (auto), DEF456 (auto). Seleccione el vehículo que llega:".
7. Operator picks the vehicle → flujo proceeds to ingreso creation (per `uc.ingreso.subscriber-lookup-by-cedula`).
8. (No writes; no `log_transaccional`; no `sync_queue`. Per SOLID I, reads don't extend the chain.)

**Tables touched (writes)**: NONE.
**Tables touched (reads)**: `subscripciones_cliente` (active filter), `subscripcion_vehiculos` (JOIN), `vehiculos`, `tipos_vehiculo`, `tipo_subscripciones` (catalog), `sucursal` (tenant), `usuarios_sucursal` (JWT scope).
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** (read-only).

**Integration with other tables**:
- Reads from: `subscripciones_cliente` (active filter), `subscripcion_vehiculos`, `vehiculos`, `tipos_vehiculo`, `tipo_subscripciones`, `sucursal`, `usuarios_sucursal`.
- Writes to: NONE.
- Cross-cutting: this is the **subscriber lookup pattern** — the second half of the 3-step GET chain. The first half (cliente lookup by cedula) is in T16 7.1; this case is the subscription + vehicles lookup.
- Related: if the cliente has multiple active subscriptions at the current branch (e.g., 2 vehicles on 2 different plans), the frontend shows both and the operator picks one. The operator must select the matching vehicle too.

### 7.3 Use Case: `uc.subscripciones.subscriber-departure-consumes-not-factura`

El suscriptor termina su visita y se va. El operador registra la salida. El sistema verifica que `ingreso.uuid_subscripcion_cliente IS NOT NULL AND subscripcion.estado='activa'`. Si es así, NO se crea una `facturas` — la subscripción se "consume" (registrada via `log_transaccional accion='salida_por_subscripcion'`). Esta es la regla comercial crítica: **subscribers no pagan por visita**. Ya cubierto parcialmente en T05 7.3 desde el lado `facturas`; aquí lo documentamos desde el lado `subscripciones_cliente` para enfatizar el impacto en su lifecycle. El flujo toca 7 tablas: `ingreso` (R para validar uuid_subscripcion), `subscripciones_cliente` (R validar activa), `salidas` (W), `log_transaccional` (W), `sync_queue` (W), `subscripcion_vehiculos` (R para tracking de consumo), `sucursal` (R tenant).

**Actor**: operator

**Pre-conditions**: subscriber has active `subscripciones_cliente` at current branch; the vehicle's `ingreso` has `uuid_subscripcion_cliente` set.

**Steps**:
1. Subscriber departs. Operator opens `SalidaForm`, types plate. Backend finds the `ingreso` with `estado='activo'`.
2. Backend SELECTs `subscripciones_cliente` WHERE `uuid=$ingreso.uuid_subscripcion_cliente AND estado='activa' AND vigente_hasta IS NULL AND fecha_vencimiento>=CURRENT_DATE`.
3. If active subscription found: subscriber-departure path. Backend INSERTs `salidas` row (`fecha_salida=NOW(), uuid_ingreso=$ingreso.uuid`).
4. Backend INSERTs `log_transaccional` (`accion='salida_por_subscripcion'`, `tabla_afectada='salidas'`, `uuid_registro_afectado=$salida_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={ingreso_uuid, subscription_uuid, cliente_uuid, vehiculo_placa, duracion_segundos, consumo: 'subscripcion'}`, `uuid_referencia=$ingreso.uuid`).
5. **NO `facturas` row is created.** This is the critical rule.
6. `queue_processor.enqueue('salidas', $uuid, $snapshot)` + enqueue log.
7. Backend returns `{salida_uuid, duracion_segundos, subscription_consumed: true, factura_uuid: null}` to frontend.
8. Operator UI shows: "Salida registrada — subscripción consumida. No requiere pago." Barrier opens (or operator allows departure manually).
9. Branch receives parametrization (cloud side eventually). Cloud tracks the consumption metric: count of `salidas WHERE ingreso.uuid_subscripcion_cliente IS NOT NULL AND fecha_salida >= period_start` per subscription.
10. The subscription is NOT modified by the consumption — it remains `estado='activa'` until `fecha_vencimiento` passes. The consumption is recorded in `log_transaccional` for analytics.

**Tables touched (writes)**: `salidas` (1 row), `log_transaccional` (1 row), `sync_queue` (deferred propagation).
**Tables touched (reads)**: `ingreso` (find by placa + estado='activo'), `subscripciones_cliente` (validate activa), `subscripcion_vehiculos` (lookup which vehiculo was used), `vehiculos` (validate placa), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator).
**FKs traversed**: `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid` (the key link); `ingreso.uuid_sucursal` → `sucursal.uuid`; `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `salidas.uuid_ingreso` → `ingreso.uuid`; `salidas.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `salidas.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `ingreso.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `salidas` row + `log_transaccional` row push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO (no invoice = no DIAN).
- Hash chain impact: YES — branch chain extends by 1 row (salida_por_subscripcion); cloud chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `ingreso`, `subscripciones_cliente` (active validate), `subscripcion_vehiculos`, `vehiculos`, `log_transaccional`, `sucursal`, `usuarios`.
- Writes to: `salidas`, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **subscription-consumed-not-factura rule** — the single most important business rule for the subscription model. Violating it would cause the subscriber to be billed per visit AND consume subscription quota, which is the worst possible outcome (double charge).
- Related: if at departure the subscription is found EXPIRED (`fecha_vencimiento < CURRENT_DATE`), the system falls back to casual flow (creates `facturas` per `uc.facturas.casual-departure`). The subscriber is informed that their subscription lapsed and they need to renew + pay this visit.

### 7.4 Use Case: `uc.subscripciones.lifecycle-flags-vencida-on-fecha-or-b2b-expiry`

Worker cron `clientes/expiry_monitor` (T16) detecta que una subscripcion tiene `fecha_vencimiento < CURRENT_DATE` O que su parent `clientes_b2b` venció. Crea una nueva versión de la subscripcion con `estado='vencida'` (archive old). Emite `alerta tipo_alerta='subscripcion_vencida'` para que el admin gestione la renovación. El flujo toca 6 tablas: `subscripciones_cliente` (W UPDATE para flag vencida), `subscripcion_vehiculos` (R para contar vehículos afectados), `alerta` (W workflow root), `log_transaccional` (W), `sync_queue` (W), `sucursal` (R tenant).

**Actor**: system (cloud `clientes/expiry_monitor` cron worker)

**Pre-conditions**: at least one `subscripciones_cliente` with `fecha_vencimiento < CURRENT_DATE OR parent B2B expired`; cron is enabled.

**Steps**:
1. Cron fires daily. SELECTs `subscripciones_cliente s JOIN clientes_b2b cb ON s.uuid_cliente=cb.uuid_cliente WHERE s.estado='activa' AND (s.fecha_vencimiento < CURRENT_DATE OR cb.fecha_vencimiento < CURRENT_DATE AND cb.vigente_hasta IS NULL)`.
2. For each affected subscription, also checks if it's already marked `vencida` (skip duplicates).
3. Backend opens TX per affected subscription; SELECT chain anchor.
4. UPDATE old `subscripciones_cliente` row: `vigente_hasta=NOW()`.
5. INSERT new `subscripciones_cliente` row: `vigente_desde=NOW(), vigente_hasta=NULL, estado='vencida'` (the new vigente state). Other fields (fecha_vencimiento, vehiculos, etc.) preserved.
6. INSERT `log_transaccional` (`accion='subscripcion_marcada_vencida'`, `tabla_afectada='subscripciones_cliente'`, `datos_anteriores={old_estado: 'activa'}`, `datos_nuevos={new_estado: 'vencida', reason: 'fecha_vencimiento_passed' | 'b2b_contract_expired'}`).
7. INSERT `alerta tipo_alerta='subscripcion_vencida'`, `uuid_sucursal=$branch`, `observaciones='subscripcion:$uuid, cliente:$cliente_uuid, fecha_vencimiento:$date, vehiculos_count:$N'`.
8. `queue_processor.enqueue('subscripciones_cliente', $new_uuid, $snapshot)` → parametrization push.
9. INSERT `log_transaccional` for alerta emission.
10. Branches receive parametrization. UPSERTs locally. Operator lookup at arrival now returns 0 active subscriptions for this cliente (they're all `vencida`). Subscriber is informed they need to renew.
11. Alerta workflow chain emits 1+ `log_transaccional` rows (root + transitions).

**Tables touched (writes)**: `subscripciones_cliente` (1 new version per affected sub + 1 archive UPDATE), `alerta` (1 root per affected sub + 2-3 transitions), `log_transaccional` (2+ rows per sub), `sync_queue` (1 per sub), `sync_log` (1 cycle).
**Tables touched (reads)**: `subscripciones_cliente` (scan), `clientes_b2b` (JOIN for B2B expiry cascade), `subscripcion_vehiculos` (count affected vehicles), `alerta` (dedup), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (SYSTEM).
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `clientes_b2b.uuid_cliente` → `clientes.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_referencia` (polymorphic) → `subscripciones_cliente.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (cron cloud-side).
- Cloud → branch: YES — parametrization push delivers the updated `subscripciones_cliente` versions within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1+ rows per affected sub + 2-3 per workflow transitions.

**Integration with other tables**:
- Reads from: `subscripciones_cliente`, `clientes_b2b` (B2B cascade), `subscripcion_vehiculos` (count), `alerta` (dedup), `log_transaccional`, `sucursal`, `usuarios` (SYSTEM).
- Writes to: `subscripciones_cliente` (version flow), `alerta` (workflow), `log_transaccional` (multiple), `sync_queue` (parametrization), `sync_log` (cycle).
- Cross-cutting: this is the **lifecycle enforcement** — the cron ensures subscriptions don't silently linger in `activa` state past their expiry. Combined with the B2B contract expiry cascade (T16 7.4), this provides complete coverage of the "subscription expired" path.
- Related: when admin renews (PATCH `fecha_vencimiento` + INSERT new version with `estado='activa'`), the cron next run sees the new vigente and DOES NOT emit alerts. The workflow transition of the alerta to `resuelta` is manual.

### 7.5 Use Case: `uc.subscripciones.admin-suspends-for-non-payment-then-reactivates`

Admin cloud suspende una subscripción (por falta de pago, disputa temporal, etc.) — crea nueva versión con `estado='suspendida'`. Subscriber no puede entrar mientras esté suspendida. Después de pago o resolución, admin reactiva: nueva versión con `estado='activa'`. El flujo toca 6 tablas: `subscripciones_cliente` (W nueva versión suspendida/activa), `alerta` (W opcional cuando se reactiva), `log_transaccional` (W x 2), `sync_queue` (W), `permisos_usuario` (R RBAC), `usuarios` (R admin), `sucursal` (R tenant).

**Actor**: admin

**Pre-conditions**: subscription exists with `estado='activa'`; admin has `permiso='suspender_subscripciones'` (for suspension) OR `permiso='reactivar_subscripciones'` (for reactivation); reason documented.

**Steps**:
1. Admin opens `web_admin/SubscripcionesList/{uuid}`, clicks `Suspend`.
2. Frontend shows `SuspensionForm`: reason (e.g., 'falta_pago_mes_agosto'), expected reactivation date (optional).
3. Admin confirms. Frontend PATCHes `api_admin /subscripciones-cliente/{uuid}/suspender` with `{motivo: 'falta_pago_mes_agosto'}`.
4. Backend validates `permisos_usuario` for `permiso='suspender_subscripciones'`.
5. Backend SELECTs current vigente `subscripciones_cliente`. Validates `estado='activa'` (cannot suspend already suspended).
6. Backend opens TX; SELECT chain anchor.
7. Backend UPDATEs old row: `vigente_hasta=NOW()`. INSERTs new row: `vigente_desde=NOW(), vigente_hasta=NULL, estado='suspendida'`.
8. Backend INSERTs `log_transaccional` (`accion='subscripcion_suspendida'`, `datos_anteriores={estado: 'activa'}`, `datos_nuevos={estado: 'suspendida', motivo: 'falta_pago_mes_agosto'}`).
9. `queue_processor.enqueue('subscripciones_cliente', $new_uuid, $snapshot)`.
10. Branches receive parametrization. UPSERTs locally. Operator lookup at arrival returns 0 active subscriptions (the vigente is now `suspendida`). Subscriber attempts to enter → backend finds 0 active subs → proceeds as casual (charged per visit). Subscriber is informed their subscription is suspended.
11. Later, admin resolves the issue (payment received, dispute settled). Admin clicks `Reactivar` in `web_admin/SubscripcionesList/{uuid}`.
12. Frontend POSTs `api_admin /subscripciones-cliente/{uuid}/reactivar` with `{motivo: 'pago_recibido'}`.
13. Backend validates `permisos_usuario` for `permiso='reactivar_subscripciones'`. Validates `estado='suspendida'`.
14. Backend UPDATEs suspended row: `vigente_hasta=NOW()`. INSERTs new row: `vigente_desde=NOW(), vigente_hasta=NULL, estado='activa'`.
15. Backend INSERTs `log_transaccional` (`accion='subscripcion_reactivada'`, `datos_anteriores={estado: 'suspendida', suspension_motivo: 'falta_pago_mes_agosto'}`, `datos_nuevos={estado: 'activa', reactivation_motivo: 'pago_recibido', suspended_for_hours: $X}`).
16. `queue_processor.enqueue` for the reactivation. Branches UPSERTs. Subscriber can enter again.

**Tables touched (writes)**: `subscripciones_cliente` (2 new versions per suspend+reactivate cycle + 2 archive UPDATEs), `log_transaccional` (2 rows), `sync_queue` (2 rows).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `subscripciones_cliente` (vigente lookup), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (tenant).
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `subscripciones_cliente.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push on each version change.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per state transition (2 rows for suspend+reactivate cycle).

**Integration with other tables**:
- Reads from: `permisos_usuario`, `subscripciones_cliente`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `subscripciones_cliente` (version flow), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **manual lifecycle override** — admin can suspend/reactivate independently of the automatic expiry-driven vencida transition. Used for operational concerns (payment issues, customer service holds, fraud investigations).
- Related: while `estado='suspendida'`, the subscription's `subscripcion_vehiculos` remain vigente (the vehicles are still registered). When admin reactivates, the subscription becomes active again and operator lookup returns it. If admin wants to permanently cancel (not suspend), they archive via PATCH `estado='inactiva'`.

### 7.6 Use Case: `uc.subscripciones.polymorphic-fk-target-in-reclamos`

Customer presenta un reclamo sobre su subscripción (ejemplo: "Me cobraron de más en la renovación"). Operator o admin crea `reclamos tipo_reclamable='subscripcion', uuid_reclamable=$subscripcion_uuid`. Esto es el caso canónico del polymorphic FK en reclamos (descrito en T16 7.6 desde el lado cliente; aquí desde el lado subscripcion). El flujo toca 5 tablas: `subscripciones_cliente` (R), `reclamos` (W workflow root), `log_transaccional` (W), `sucursal` (R tenant), `permisos_usuario` (R RBAC).

**Actor**: operator (creates reclamo) + admin (triages)

**Pre-conditions**: subscripcion exists; operator/admin has `permiso='crear_reclamos'`; the issue is genuinely tied to the subscription (not just the cliente in general).

**Steps**:
1. Customer files complaint: "Me cobraron $X de más en la renovación del mes pasado". Operator opens `web_sucursal/ReclamosForm`.
2. Frontend shows `ReclamoLookup`. Operator searches the cliente by cedula (per T16 7.1).
3. Frontend GETs `api_sucursal /clientes/{uuid_cliente}/subscripciones` (per T18 7.2 — returns all subs, including archived/historical).
4. Operator selects the specific subscription being complained about.
5. Frontend POSTs `api_sucursal /reclamos` with `{uuid_sucursal, tipo_reclamable: 'subscripcion', uuid_reclamable: $sub_uuid, motivo: 'cobro_excesivo_renovacion_agosto', observaciones: 'Cliente pagó $50.000 pero el sistema cobró $80.000'}`.
6. Backend validates `permisos_usuario` for `permiso='crear_reclamos'`.
7. Backend validates `tipo_reclamable` is in enum `{ingreso, salida, factura, subscripcion}` — `'subscripcion'` is valid.
8. Backend SELECTs `subscripciones_cliente` WHERE `uuid=$uuid_reclamable AND uuid_sucursal=$branch`. (Cross-tenant protection.)
9. Backend INSERTs `reclamos` workflow root (`estado='abierto', uuid_reclamo_padre=NULL`, `uuid_reclamable=$sub_uuid`).
10. Backend INSERTs `log_transaccional` (`accion='reclamo_abierto'`, `tabla_afectada='reclamos'`, `uuid_registro_afectado=$reclamo_uuid`, `uuid_referencia=$sub_uuid`).
11. `queue_processor.enqueue('reclamos', $uuid, $snapshot)`.
12. Cloud receives; admin reviews in `web_admin/ReclamosList`.
13. Admin investigates: pulls up `subscripciones_cliente` history, sees the renewal version (T18 7.2 created), cross-references with `cliente_b2b` (if applicable) and `factura_pagos` (if the customer was charged).
14. Admin triages: workflow chain `abierto → en_revision → resuelto` (or `rechazado`). Each transition is a new `reclamos` row with `uuid_reclamo_padre`.

**Tables touched (writes)**: `reclamos` (1 workflow root + 2-3 transitions), `log_transaccional` (1+ rows), `sync_queue` (1+ rows).
**Tables touched (reads)**: `clientes` (lookup), `subscripciones_cliente` (validate cross-tenant + selection), `reclamos` (enum constraint), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator/admin).
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `reclamos.uuid_sucursal` → `sucursal.uuid`; `reclamos.uuid_reclamable` (polymorphic) → `subscripciones_cliente.uuid`; `reclamos.uuid_reclamo_padre` → `reclamos.uuid` (workflow chain self-reference); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `subscripciones_cliente.uuid`.

**Sync behavior**:
- Branch → cloud: YES (workflow root + transitions).
- Cloud → branch: YES (parametrization push of transitions).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (reclamo_abierto); cloud chain extends by 1 row per transition.

**Integration with other tables**:
- Reads from: `clientes`, `subscripciones_cliente`, `reclamos`, `permisos_usuario`, `log_transaccional`, `sucursal`, `usuarios`.
- Writes to: `reclamos` (workflow), `log_transaccional` (audit), `sync_queue` (deferred propagation).
- Cross-cutting: this is the **canonical polymorphic FK target** for reclamos — `tipo_reclamable='subscripcion'` is the cleanest way to file a claim against a subscription without needing to extend the enum to include `'cliente'`. The reclamo inherits all subscription context (branch, dates, plan, vehicles) automatically via JOIN.
- Related: if the issue is about the subscription's tarifa (not the subscription itself), the operator could file `tipo_reclamable='factura'` referencing the renewal factura instead. The polymorphic FK supports both patterns — admin triages and routes accordingly.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 28, 31.

## 9. RED Tests
- (RED) F1 schema includes `subscripciones_cliente`.
- (RED) Admin POST `/subscripciones-cliente` with vehiculos_uuids within `cantidad_maxima_vehiculos` → 201; subscription + bridge rows created.
- (RED) Admin POST with vehiculos_uuids exceeding `cantidad_maxima_vehiculos` → 422.
- (RED) Operator GET `/subscripciones-cliente?uuid_cliente=X&estado=activa` → 200 with active subscriptions.
- (RED) Operator GET with no active subscriptions → 404.
- (RED) Subscriber departure: `ingreso.uuid_subscripcion_cliente` set + subscription active → `salidas` created, NO `facturas` row.
- (RED) Subscriber departure with subscription expired → falls back to casual: `facturas` row created.
- (RED) Expiry monitor: `subscripciones_cliente.fecha_vencimiento < CURRENT_DATE` → new version with `estado='vencida'`.
- (RED) B2B contract expiry cascade: all active subscriptions for the cliente marked `vencida`.
- (RED) Suspend: admin PATCH → new version with `estado='suspendida'`. Operator lookup at arrival returns 0 active.
- (RED) Reactivar: admin POST → new version with `estado='activa'`. Operator lookup returns it again.
- (RED) Cannot suspend already-suspended subscription → 422.
- (RED) Cannot reactivate active subscription → 422.
- (RED) Reclamo with `tipo_reclamable='subscripcion'` + `uuid_reclamable` referencing sub from another branch → 403 (cross-tenant).
- (RED) Subscription archive cascade: when parent `clientes` archived, all active subs for that cliente → `estado='inactiva'`.
- (RED) Hash chain: every subscription state transition writes `log_transaccional` with `datos_anteriores.estado` and `datos_nuevos.estado`.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-10.x: `api_admin /subscripciones-cliente` (POST, PATCH, POST suspender, POST reactivar, GET list, GET detail).
- [ ] IT-10.x: `api_sucursal /subscripciones-cliente` (lookup, GET detail, GET vehiculos).
- [ ] IT-10.x: parametrization push for subscription updates.
- [ ] IT-10.x: `parkos_core/subscripciones/lifecycle_service.py::transition()`.
- [ ] IT-10.x: `parkos_core/subscripciones/lookup_service.py::active_at()`.
- [ ] IT-10.x: `workers/clientes/expiry_monitor.py` integration (subscription expiry + B2B cascade).
- [ ] IT-10.x: `api_sucursal /salidas` integration — subscriber-departure path skips facturacion.
- [ ] IT-10.x: `web_admin/SubscripcionesList`, `SubscripcionForm`, `SubscripcionDetail/VehiculosTab`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Subscriber-doesn't-pay rule violated (subscriber charged per visit) | Low | Branch operator training; backend refuses `facturas` creation when subscription active; integration test on every subscriber departure |
| Subscription quota exceeded (more vehicles than `cantidad_maxima_vehiculos`) | Low | Validation at subscripcion_vehiculos INSERT; admin must remove a vehicle or upgrade plan |
| B2B expiry cascade missed | Low | Cron retry; alert if cron fails; manual admin override possible |
| Suspended subscription not reactivated (customer abandoned) | Med | Alerta emitted after 30 days suspended; admin can archive or reactivate |
| Cross-branch subscription confusion | Med | Subscription is branch-pinned; UI clearly shows scope; cross-branch lookup returns 0 (subscriber must have separate subs per branch) |
| Subscription resurrection (unarchive) | Low | Out of MVP; sprint 5; current flow requires new subscription creation |
| Reclamo against subscription vs cliente confusion | Med | Polymorphic FK constraint enforces specificity; admin UI guides operator to pick the most specific `tipo_reclamable` |

## 12. Open Questions
- (a) Subscription quota vs B2B `cantidad`: is the per-subscription `cantidad_maxima_vehiculos` enforced independently of the B2B contract `cantidad`? Current: yes (each subscription enforces its own max). Sprint 5 may add B2B-level cap aggregation.
- (b) Mid-subscription plan upgrade: can admin change `uuid_tipo_subscripcion` to a different plan mid-term? Current: would require archive + new subscription. Sprint 5 may add `tipo_subscripcion_history` for in-place upgrades with pro-rated billing.
- (c) Auto-renewal: `fecha_vencimiento` extended automatically by N days if customer has been active. Sprint 5.
- (d) Pro-rated billing for partial periods: when subscription activates mid-month, does the customer pay full or pro-rated? Out of MVP; sprint 5.
- (e) Multi-vehicle subscription with mixed casual entry: e.g., a subscriber brings 2 vehicles (within quota) and a friend (casual). All enter; subscriber's 2 are linked to subscription, friend's is casual. Per `uc.ingreso.subscriber-rotacion-cupo-agotado`, if subscriber brings 3 vehicles (1 over quota), the 3rd enters as casual (rotation). Currently documented; sprint 5 may add UI improvements.
- (f) Subscription transfer (subscriber sells their subscription to another cliente): out of MVP; sprint 5 may add `subscripcion_transferencia` workflow.
- (g) Family plans (multiple persons on one subscription): current model: each person has their own `clientes` row + own subscription. Sprint 5 may add `subscripcion_grupo` for shared subscriptions.
- (h) `reclamos.tipo_reclamable='cliente'` (general cliente complaint, not anchored to specific subscription or event): sprint 5 model extension.
