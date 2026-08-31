# PRD: subscripcion_vehiculos (T19)

> N:M bridge table between `subscripciones_cliente` and `vehiculos`. Resolves the 1NF problem of having `placavehiculo1, placavehiculo2, ...` as columns on a subscription. Each row represents one vehicle authorized under one subscription. Cap enforcement: `cantidad` of rows per `subscripcion_cliente.uuid` must not exceed `tipo_subscripciones.cantidad_maxima_vehiculos`.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I: bridge table CRUD is segregated from both subscription and vehiculo CRUD*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.subscripcion_vehiculos`
- **SQL name**: `subscripcion_vehiculos` (with `prod` schema)
- **Enforcement level**: `[V]` projection (versioned — add/remove creates new rows)
- **Retention**: indefinite
- **Origin**: F1 (schema) + IT-10 (admin CRUD, vehiculo add/remove)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; quota enforcement + cascade + N:M bridge semantics documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- The bridge has **no UNIQUE on (uuid_subscripcion_cliente, uuid_vehiculo)** — same vehicle CAN be in multiple subscriptions over time (different branches, different plans, sequential subscriptions), as long as only ONE is vigente at a time. Application enforces this via the vigente filter; sprint 5 may add partial UNIQUE for stricter guarantees.
- Vigente filter: `vigente_hasta IS NULL`.

## 3. SOLID Atomic Breakdown
- **S**: "one vehicle authorized under one subscription". The bridge is the **N:M resolver** — replacing the anti-pattern of comma-separated plate columns on the subscription.
- **O**: extensible; new metadata about the vehicle-subscription pair (e.g., `fecha_vencimiento_vehiculo`, `soat_al_dia`) could go in `registro` JSON (not in current model; sprint 5).
- **I**: admin CRUD via `api_admin /subscripcion-vehiculos`; branch reads own vigentes via `api_sucursal /subscripcion-vehiculos` (for operator lookup at arrival); subscription lifecycle (T18) triggers bridge archive on parent archive.
- **D**: `parkos_core/models/V/subscripcion_vehiculos.py` (model); `parkos_core/subscripciones/quota_service.py::count_vehicles(sub_uuid) <= cantidad_maxima_vehiculos` (validation).
- **Atomic**: INSERT (admin adds vehiculo, with quota validation), UPDATE (archive old + new with new `estado` if needed), DELETE forbidden by FK RESTRICT (both parents protect).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_subscripcion_cliente` | `prod.subscripciones_cliente.uuid` | exactly one (NOT NULL) | RESTRICT | the subscription |
| `uuid_vehiculo` | `prod.vehiculos.uuid` | exactly one (NOT NULL) | RESTRICT | the vehicle |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | bridge — referenced only via JOIN through either parent |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin adds vehiculo (with quota validation); inside TX + `log_transaccional` |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted if state changes (rare; mostly archive-only) |
| DELETE | NO | Archive via UPDATE; FK RESTRICT prevents |

**Special rules**:
- **Quota enforcement**: COUNT(subscripcion_vehiculos WHERE uuid_subscripcion_cliente=$sub AND vigente_hasta IS NULL) must be <= `tipo_subscripciones.cantidad_maxima_vehiculos`. Validated at INSERT.
- **Same vehiculo in multiple subscriptions**: allowed across time (sequential) and even overlapping in rare cases (e.g., one subscription at Branch A and another at Branch B simultaneously). The vehicle's UUID is the same; the bridge rows are different.
- **Cascade on subscription archive**: when `subscripciones_cliente` is archived (per T18 7.4 / T17 7.3), the bridge rows are archived in the same TX (application orchestrates, NOT DB cascade).
- **Cascade on vehiculo archive**: when `vehiculos` is archived (e.g., vehicle sold, plate changed), the bridge rows are archived too.

## 6. CodeGraph Dependencies
- `api_admin/routers/subscripcion_vehiculos.py::POST /subscripcion-vehiculos`, `PATCH /subscripcion-vehiculos/{uuid}/remove` (archive), `GET /subscripcion-vehiculos`.
- `api_sucursal/routers/subscripcion_vehiculos.py::GET /subscripcion-vehiculos?uuid_subscripcion_cliente=...&vigente_only=true` (operator display).
- `parkos_core/subscripciones/quota_service.py::count_and_validate(uuid_subscripcion_cliente, new_uuid_vehiculo_to_add)` (returns `{current_count, max_allowed, can_add: boolean}`).
- `api_admin/routers/subscripciones_cliente.py::POST /subscripciones-cliente` (T18 — calls quota_service to validate N vehicles in the same TX).
- `web_admin/SubscripcionDetail/VehiculosTab` (admin manages vehicles in subscription).

## 7. Use Cases enabled by this table

The `subscripcion_vehiculos` table is the **N:M bridge** that resolves the 1NF anti-pattern of comma-separated vehicle columns on a subscription. Each row represents one vehicle authorized under one subscription, with quota enforcement against `tipo_subscripciones.cantidad_maxima_vehiculos`. Use cases below describe the add flow (with quota validation), the remove flow (subscription end or vehicle change), the operator lookup at arrival, and the cascade behavior on parent archive.

### 7.1 Use Case: `uc.subscripcion-vehiculos.admin-adds-vehiculo-within-quota`

Admin cloud quiere agregar un nuevo vehículo a una subscripción existente (cliente compró un auto nuevo, quiere incluirlo en su plan). Valida que la subscripción no haya alcanzado `tipo_subscripciones.cantidad_maxima_vehiculos`, verifica que el vehiculo pertenece al cliente (FK implication), e inserta la fila bridge con versionado `[V]`. El flujo toca 8 tablas: `subscripcion_vehiculos` (W), `subscripciones_cliente` (R), `vehiculos` (R para validar), `clientes` (R para validar que el vehiculo pertenece al cliente via JOIN), `tipo_subscripciones` (R para cantidad_maxima), `permisos_usuario` (R RBAC), `log_transaccional` (W), `sync_queue` (W).

**Actor**: admin

**Pre-conditions**: `subscripciones_cliente` exists with `estado='activa'`; `vehiculos` row exists; the vehiculo's `uuid_tipo_vehiculo` matches the subscription's plan allowed types (sprint 5 may add stricter validation); admin has `permiso='gestionar_subscripcion_vehiculos'`.

**Steps**:
1. Admin opens `web_admin/SubscripcionDetail/{uuid_sub}/VehiculosTab`, clicks `Add Vehiculo`.
2. Frontend shows `AddVehiculoForm`: cliente lookup (auto-filled with subscription's cliente), vehiculo dropdown (filtered to cliente's existing vehiculos not already in this subscription).
3. Admin selects `GHI789 (camioneta)`. Frontend shows current quota usage: "2/2 vehiculos usados (Plan_Mensual_Auto permite max 2). ¿Desea agregar igual?". Admin confirms (or admin first upgrades plan to allow 3).
4. Frontend POSTs `api_admin /subscripcion-vehiculos` (admin- JWT) with `{uuid_subscripcion_cliente, uuid_vehiculo: $GHI789_uuid}`.
5. Backend validates `permisos_usuario` for `permiso='gestionar_subscripcion_vehiculos'`.
6. Backend SELECTs `subscripciones_cliente` WHERE `uuid=$sub AND estado='activa'`. Validates exists and active.
7. Backend SELECTs `tipo_subscripciones` WHERE `uuid=$sub.uuid_tipo_subscripcion`. Returns `cantidad_maxima_vehiculos=2`.
8. Backend SELECTs COUNT from `subscripcion_vehiculos` WHERE `uuid_subscripcion_cliente=$sub AND vigente_hasta IS NULL`. Returns 2 (already at cap).
9. Backend rejects: returns 422 `{detail: 'cuota_excedida', current_count: 2, max_allowed: 2, plan: 'Plan_Mensual_Auto'}`.
10. Admin sees the error. Options: (a) upgrade plan to `Plan_Mensual_Auto_Premium` with `cantidad_maxima_vehiculos=3` (PATCH subscripcion via T18 — creates new version); (b) remove an existing vehiculo first.
11. Admin upgrades plan: PATCH `/subscripciones-cliente/{uuid_sub}` with `{uuid_tipo_subscripcion: $plan_premium_uuid}`. New version of subscripcion created with the premium plan. Now `cantidad_maxima_vehiculos=3`.
12. Admin retries: POST `/subscripcion-vehiculos` with `{uuid_subscripcion_cliente, uuid_vehiculo: $GHI789_uuid}`.
13. Backend re-validates quota: COUNT=2 (unchanged), max=3 (new). `2+1 <= 3` → allowed.
14. Backend SELECTs `vehiculos` WHERE `uuid=$GHI789_uuid`. Validates `uuid_tipo_vehiculo IN (allowed types for plan)` — `Plan_Mensual_Auto_Premium` allows auto + camioneta + moto.
15. Backend opens TX; SELECT chain anchor from `log_transaccional`.
16. Backend INSERTs `subscripcion_vehiculos` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activa'`).
17. Backend INSERTs `log_transaccional` (`accion='subscripcion_vehiculo_added'`, `tabla_afectada='subscripcion_vehiculos'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={uuid_subscripcion_cliente, uuid_vehiculo, vehiculo_placa, current_count: 3, max_allowed: 3}`).
18. `queue_processor.enqueue('subscripcion_vehiculos', $new_uuid, $snapshot)` → parametrization push.
19. Branches receive parametrization within 30s. UPSERTs locally. Operator sees the new vehiculo available for this subscription.

**Tables touched (writes)**: `subscripcion_vehiculos` (1 row), `log_transaccional` (1 row), `sync_queue` (1 row). Plus optional `subscripciones_cliente` new version (plan upgrade).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `subscripciones_cliente` (active validate), `tipo_subscripciones` (cantidad_maxima), `vehiculos` (validate + tipo_vehiculo check), `clientes` (validate ownership via JOIN), `subscripcion_vehiculos` (count), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (tenant).
**FKs traversed**: `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `vehiculos.uuid_cliente_implied` (via JOIN to clientes via `registro` or implicit — sprint 5 may formalize); `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `subscripcion_vehiculos.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; branch chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `subscripciones_cliente`, `tipo_subscripciones`, `vehiculos`, `clientes`, `subscripcion_vehiculos`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `subscripcion_vehiculos` (new), `log_transaccional` (audit), `sync_queue` (parametrization), optional `subscripciones_cliente` (plan upgrade version).
- Cross-cutting: this is the **N:M bridge write** with quota enforcement. The validation happens BEFORE INSERT, so the database never holds an over-quota state. The `count_and_validate` helper is critical — it's called from both `POST /subscripcion-vehiculos` (this use case) and `POST /subscripciones-cliente` (T18 7.1, when creating with N initial vehicles).
- Related: the quota is per-subscription, NOT global to the cliente. A cliente can have multiple subscriptions (different branches), each with its own quota. The `tipo_subscripciones.cantidad_maxima_vehiculos` is the per-sub cap.

### 7.2 Use Case: `uc.subscripcion-vehiculos.admin-removes-vehiculo-at-subscription-end-or-vehicle-change`

Admin cloud quita un vehículo de una subscripción — escenarios: el vehículo se vendió, el cliente cambió de auto (nueva placa), o el cliente terminó su subscripción pero el vehículo sigue en su `vehiculos` catalog (sigue siendo suyo, pero ya no bajo el plan). Archiva la fila bridge con `vigente_hasta=NOW()` (NO DELETE). El vehículo sigue existiendo en la tabla `vehiculos` — solo se desvincula de esta subscripción. El flujo toca 6 tablas: `subscripcion_vehiculos` (W archive), `subscripciones_cliente` (R validar activa), `vehiculos` (R validar), `log_transaccional` (W), `sync_queue` (W), `permisos_usuario` (R RBAC), `usuarios` (R admin), `sucursal` (R tenant).

**Actor**: admin

**Pre-conditions**: bridge row exists with `vigente_hasta IS NULL`; admin has `permiso='gestionar_subscripcion_vehiculos'`.

**Steps**:
1. Admin opens `web_admin/SubscripcionDetail/{uuid_sub}/VehiculosTab`, sees the 3 vehiculos in the subscription. Clicks `Remove` on `GHI789 (camioneta)`.
2. Frontend shows confirmation: "¿Quitar GHI789 de la subscripción? El vehículo seguirá existiendo en el catálogo del cliente pero ya no estará autorizado bajo este plan. ¿Continuar?"
3. Admin confirms. Frontend PATCHes `api_admin /subscripcion-vehiculos/{uuid_bridge}/remove` with `{motivo: 'vehiculo_vendido'}`.
4. Backend validates `permisos_usuario` for `permiso='gestionar_subscripcion_vehiculos'`.
5. Backend SELECTs current vigente bridge row. Validates `uuid_subscripcion_cliente` matches active subscription.
6. Backend opens TX; SELECT chain anchor.
7. Backend UPDATEs bridge row: SET `vigente_hasta=NOW()`. (No new INSERT — this is an archive, not a state change. The bridge is one-way: add → archive. No "unarchive" via version flow because that would re-add the same vehiculo which doesn't make sense.)
8. Backend INSERTs `log_transaccional` (`accion='subscripcion_vehiculo_removed'`, `tabla_afectada='subscripcion_vehiculos'`, `uuid_registro_afectado=$uuid_bridge`, `datos_anteriores={vehiculo_uuid, vehiculo_placa, vigente_desde, vigente_hasta: null}`, `datos_nuevos={vehiculo_uuid, vehiculo_placa, vigente_hasta: NOW(), motivo: 'vehiculo_vendido'}`).
9. `queue_processor.enqueue('subscripcion_vehiculos', $uuid_bridge, $snapshot)` → parametrization push (the archive update).
10. Branches receive parametrization within 30s. UPSERTs locally. Operator sees the subscription now has 2 vehiculos (GHI789 removed).
11. The `vehiculos` row is NOT deleted — it persists. The cliente can add it to a different subscription (different branch or plan) in the future, or it can be added back to this one.

**Tables touched (writes)**: `subscripcion_vehiculos` (1 archive UPDATE), `log_transaccional` (1 row), `sync_queue` (1 row).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `subscripcion_vehiculos` (vigente lookup), `subscripciones_cliente` (validate active), `vehiculos` (validate), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (tenant).
**FKs traversed**: `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `subscripcion_vehiculos.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push delivers the archive update within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (subscripcion_vehiculo_removed); branch chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `subscripcion_vehiculos`, `subscripciones_cliente`, `vehiculos`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `subscripcion_vehiculos` (archive), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **bridge archive pattern** — a remove is just an archive (`vigente_hasta=NOW()`). The vehiculo is preserved, the bridge history is preserved, and the subscription remains active (just with fewer vehicles). Re-adding the same vehiculo later creates a NEW bridge row (different UUID), preserving the full history.
- Related: if the admin wants to PERMANENTLY remove the vehiculo (e.g., it was destroyed), they should archive the `vehiculos` row (per T20 7.4), which cascades to archive all `subscripcion_vehiculos` rows for that vehiculo. The vehiculo row stays as archive but is excluded from queries.

### 7.3 Use Case: `uc.subscripcion-vehiculos.subscription-or-vehiculo-archive-cascades-bridge`

Cuando el `subscripciones_cliente` se archiva (per T18 7.4 lifecycle, T17 7.3 parent archive, o cualquier otro archive flow), TODAS las filas `subscripcion_vehiculos` vigentes para esa subscripcion se archivan en la misma TX (aplicación orquesta, NO DB cascade porque FK RESTRICT). Similarmente, si el `vehiculos` se archiva (per T20 7.4), todas las filas bridge vigentes para ese vehiculo se archivan. Esto evita "orphan" bridge rows con un padre archivado. El flujo toca 5 tablas: `subscripcion_vehiculos` (W archive UPDATE en bulk), `subscripciones_cliente` o `vehiculos` (R parent archive trigger), `log_transaccional` (W bulk o uno por fila), `sync_queue` (W bulk), `permisos_usuario` (R RBAC), `sucursal` (R tenant).

**Actor**: admin (or system via cron)

**Pre-conditions**: parent `subscripciones_cliente` or `vehiculos` row being archived via the standard version flow; admin has the appropriate archive permission.

**Steps**:
1. Admin archives a `subscripciones_cliente` (e.g., per T18 lifecycle — vence → archive). The archive TX is open.
2. Backend SELECTs all `subscripcion_vehiculos` WHERE `uuid_subscripcion_cliente=$sub AND vigente_hasta IS NULL`. Returns N rows.
3. Backend UPDATEs each bridge row: SET `vigente_hasta=$archive_timestamp`. Bulk UPDATE in one statement.
4. Backend INSERTs ONE `log_transaccional` row that summarizes the bulk operation (`accion='subscripcion_vehiculos_archived_bulk'`, `tabla_afectada='subscripcion_vehiculos'`, `uuid_registro_afectado=$archive_log_uuid`, `datos_nuevos={uuid_subscripcion_cliente, bridges_archived_count: $N, trigger: 'subscripcion_archived'}`). This consolidates the audit (one row per archive event, not N rows).
5. (Optional, if also archiving a vehiculo) Backend SELECTs all `subscripcion_vehiculos` WHERE `uuid_vehiculo=$vehiculo AND vigente_hasta IS NULL`. Returns M rows. UPDATEs bulk. INSERTs `log_transaccional`.
6. `queue_processor.enqueue` for each affected bridge row (or batched) → INSERT N `sync_queue` rows.
7. Backend returns archive summary.
8. Branches receive parametrization. UPSERTs archive versions locally. Operator sees the bridge as inactive.

**Tables touched (writes)**: `subscripcion_vehiculos` (N archive UPDATEs in bulk), `log_transaccional` (1+ bulk audit row per parent archive), `sync_queue` (N parametrización rows).
**Tables touched (reads)**: `subscripcion_vehiculos` (vigente scan for the parent), `subscripciones_cliente` (parent archive trigger), `vehiculos` (alternative parent trigger), `log_transaccional` (chain anchor), `usuarios` (admin or SYSTEM), `sucursal` (tenant).
**FKs traversed**: `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `subscripcion_vehiculos.uuid` (one bulk log row); `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (parent archive is admin/system write).
- Cloud → branch: YES — parametrization push delivers all N archive updates within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1+ rows (one bulk audit per parent archive); branch chain extends by N rows when received.

**Integration with other tables**:
- Reads from: `subscripcion_vehiculos` (vigente scan), `subscripciones_cliente` (parent trigger), `vehiculos` (alternative trigger), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
- Writes to: `subscripcion_vehiculos` (bulk archive), `log_transaccional` (bulk audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **cascade archive via application** pattern. The bridge table sits BETWEEN two parents — either parent's archive cascades through it. The application orchestrates the bulk UPDATE in the same TX as the parent archive, ensuring atomicity.
- Related: this is intentionally a soft cascade (archive, not delete). The bridge history is preserved forever — you can always query "which vehicles were in subscription X on date Y" via bi-temporal query.

### 7.4 Use Case: `uc.subscripcion-vehiculos.branch-uses-for-ingreso-validation`

Operator en la branch está creando un ingreso. Necesita saber si el vehiculo entrante está bajo alguna subscripción activa (en este branch). El frontend hace GET al endpoint de subscripcion_vehiculos JOIN subscripciones_cliente JOIN clientes. Si hay match → ingreso se vincula a la subscripción, NO se cobra al salir. Si no hay match → ingreso casual (cobro al salir). Esta es la mitad "vehiculos-side" del lookup — el otro lado (subscripcion-side) está en T18 7.2. **Es READ puro** — no extiende la hash chain.

**Actor**: operator (display only)

**Pre-conditions**: cliente has been looked up by cedula (per T16 7.1); operator is creating an ingreso.

**Steps**:
1. After cliente lookup, Frontend has the `cliente.uuid`. GETs `api_sucursal /subscripcion-vehiculos?uuid_cliente=$c&vigente_only=true&uuid_sucursal=$branch`.
2. Backend SELECTs `subscripcion_vehiculos sv JOIN subscripciones_cliente s ON sv.uuid_subscripcion_cliente=s.uuid` WHERE `s.uuid_cliente=$c AND s.uuid_sucursal=$branch AND s.estado='activa' AND s.vigente_hasta IS NULL AND sv.vigente_hasta IS NULL AND s.fecha_vencimiento>=CURRENT_DATE`. Returns bridge rows with subscription + vehiculo details.
3. Frontend displays: "Vehículos bajo subscripción activa: ABC123 (auto), DEF456 (auto). ¿Cuál está entrando?"
4. Operator selects the vehicle → flow proceeds to ingreso creation.
5. (No writes; no `log_transaccional`; no `sync_queue`. Per SOLID I, reads don't extend the chain.)

**Tables touched (writes)**: NONE.
**Tables touched (reads)**: `subscripcion_vehiculos` (vigente JOIN), `subscripciones_cliente` (active JOIN), `vehiculos` (JOIN), `clientes` (filter), `usuarios_sucursal` (JWT scope), `sucursal` (tenant).
**FKs traversed**: `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** (read-only).

**Integration with other tables**:
- Reads from: `subscripcion_vehiculos`, `subscripciones_cliente`, `vehiculos`, `clientes`, `usuarios_sucursal`, `sucursal`.
- Writes to: NONE.
- Cross-cutting: this is the **N:M bridge read pattern** — the bridge table is the join point between subscription and vehicle, and queries traverse it in both directions. The bridge's INDEX on `uuid_subscripcion_cliente + vigente_hasta IS NULL` and `uuid_vehiculo + vigente_hasta IS NULL` (sprint 5) ensures fast lookups.
- Related: if the operator types a placa NOT in the bridge (casual vehicle), the lookup returns 0 → operator proceeds as casual. The vehiculo is created implicitly via `ingreso.placa` (string, NOT FK per the model — see T20 7.4).

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 28, 31.

## 9. RED Tests
- (RED) F1 schema includes `subscripcion_vehiculos` bridge.
- (RED) Admin POST `/subscripcion-vehiculos` within quota → 201; bridge row persisted.
- (RED) Admin POST exceeding `cantidad_maxima_vehiculos` → 422 with quota details.
- (RED) Admin POST with vehiculo from a different cliente → 422 (cross-cliente ownership).
- (RED) Admin PATCH `/subscripcion-vehiculos/{uuid}/remove` → archive UPDATE; bridge `vigente_hasta=NOW()`.
- (RED) `vehiculos` archive cascades bridge → all vigentes for that vehiculo archived.
- (RED) `subscripciones_cliente` archive cascades bridge → all vigentes for that sub archived in same TX.
- (RED) Operator GET `/subscripcion-vehiculos?uuid_cliente=X` returns vigentes only.
- (RED) Operator GET with `vigente_only=false` returns historical (for audit).
- (RED) Cross-audience: operador from branch A → 403 on subscripcion from branch B (via JOIN check).
- (RED) ON DELETE RESTRICT: cannot delete `vehiculos` or `subscripciones_cliente` while bridge references them.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-10.x: `api_admin /subscripcion-vehiculos` (POST, PATCH remove, GET list, GET detail).
- [ ] IT-10.x: `api_sucursal /subscripcion-vehiculos` (lookup).
- [ ] IT-10.x: `parkos_core/subscripciones/quota_service.py::count_and_validate()`.
- [ ] IT-10.x: cascade logic in subscription archive (T18 7.4) and vehiculo archive (T20 7.4).
- [ ] IT-10.x: parametrization push for bridge updates.
- [ ] IT-10.x: `web_admin/SubscripcionDetail/VehiculosTab` (admin UI).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Quota exceeded | Low | Validation at INSERT; admin must upgrade plan or remove a vehicle first |
| Orphan bridge rows (parent archived, bridge active) | Low | Application cascade in same TX; bulk archive; bi-temporal query always reflects vigente |
| Race condition on quota check (two concurrent inserts when count = max-1) | Low | `SELECT FOR UPDATE` on the count query OR `pg_advisory_xact_lock(sub_uuid)` serializes inserts per subscription |
| Same vehiculo in overlapping subscriptions | Med | Allowed across branches; rejected only if same branch + same time (sprint 5 partial UNIQUE) |
| Bridge history explosion (many adds/removes) | Low | Acceptable; `[V]` versioning preserves all history; bi-temporal query supported |

## 12. Open Questions
- (a) Partial UNIQUE on (uuid_subscripcion_cliente, uuid_vehiculo) WHERE vigente_hasta IS NULL: enforce "no duplicate active bridge". Currently allowed by design; sprint 5 may add.
- (b) `subscripcion_vehiculos.registro` JSON for per-vehicle metadata (soat_al_dia, fecha_vencimiento_vehiculo): sprint 5.
- (c) Vehicle swap mid-subscription: when cliente changes plate, current flow requires add-new + remove-old (T20 7.4). Could be a single operation. Sprint 5.
- (d) Per-subscription `vehiculo_principal` flag (one vehiculo is the "primary" for billing/notification): sprint 5.
- (e) Bulk import of vehicles (admin uploads CSV of 50 plates to add to a corporate subscription): sprint 5.
- (f) Auto-add on vehiculo creation: when admin creates a new `vehiculos` row for a cliente with active subscriptions, should it auto-add to all of them? Currently NO (manual add via this PRD); sprint 5 may add.
- (g) Cascade trigger when `clientes_b2b` is archived (different from individual cliente archive): currently handled via subscription archive (T18 7.4). Sprint 5 may add explicit B2B-cascade.
