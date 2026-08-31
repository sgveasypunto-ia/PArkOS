# PRD: ingreso (T04)

> Branch-side event for each vehicle entry. State derived from `salidas` + `anulaciones`.

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
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[L-E]` table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.ingreso`
- **SQL name**: `ingreso` (with `prod` schema)
- **Enforcement level**: `[L-E]` event (branch writes; cloud receives via sync)
- **Retention**: operational (~2 years; configurable)
- **Origin**: F1 (schema) + IT-3 (writes)
- **PRD status**: Draft
- **PRD version**: 3.0 (use cases rewritten per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `placa` is string (NOT FK; captured at the door).

## 3. SOLID Atomic Breakdown
- **S**: "one vehicle entry event".
- **O**: `observaciones` text column extensible.
- **I**: branch operator API + admin read API.
- **D**: `parkos_core/operacion/ingreso_writer.py`.
- **Atomic**: INSERT only (state derived).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | mandatory; the branch |
| `uuid_tipo_vehiculo` | `prod.tipos_vehiculo.uuid` | exactly one (NOT NULL) | RESTRICT | mandatory; vehicle type |
| `uuid_subscripcion_cliente` | `prod.subscripciones_cliente.uuid` | 0..1 (nullable) | RESTRICT | for subscribers |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `prod.salidas.uuid_ingreso` | 1:1 | each ingreso has 0..1 salida |
| `prod.anulaciones.uuid_ingreso` | 1:N | an ingreso may be anulada |
| `prod.facturas.uuid_ingreso` | 1:N | ingreso can have multiple facturas |
| `prod.reclamos` (polymorphic) | — | `tipo_reclamable='ingreso'` |
| `prod.reimpresion_ticket.uuid_ingreso` | 1:N | reimpresiones reference ingreso |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Branch operator |
| UPDATE | NO | State derived from `salidas` + `anulaciones` |
| DELETE | NO | Append-only |

## 6. CodeGraph Dependencies
- `api_sucursal/routers/ingresos.py`.
- `api_admin/routers/ingresos.py`.
- `job_sync_sucursal/drain_outbox_ingresos`.
- `job_sync_cloud/drain_inbox_ingresos`.
- `web_sucursal/IngresoForm`.
- `web_admin/IngresosList`.

## 7. Use Cases enabled by this table

The `ingreso` table is the **operational entry point of the parking-lot business cycle**: every vehicle that enters the lot creates one row. Use cases below describe the real parking-lot workflow with **manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.ingreso.casual-visitor-manual-entry`

Llega un casual al parqueadero: el operador tipea la placa a mano, elige el tipo de vehículo del dropdown, y el sistema crea el ingreso. Todo manual — sin cámaras, sin OCR, sin QR scanners.

**Actor**: operator

**Steps**:
1. Vehicle arrives at the booth. Operator opens `web_sucursal/IngresoForm` (loaded as the default screen at the start of shift).
2. Operator **types the plate** (e.g., `ABC123`) into the `placa` input.
3. Operator **selects** `uuid_tipo_vehiculo` from a dropdown (auto, moto, camioneta, bicicleta — fetched from `tipos_vehiculo`).
4. Operator confirms: the system shows cupos available (`cantidad_vehiculos_sucursal` minus current `ingreso.estado='activo'` count for that `uuid_tipo_vehiculo`).
5. Frontend POSTs `api_sucursal /ingresos` with `{placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente: null}`.
6. Backend: SELECT chain anchor from `log_transaccional`; INSERT `ingreso` row (`estado='activo'`, `fecha_ingreso=NOW()`, `observaciones=null`).
7. INSERT `log_transaccional` (`accion='ingreso_creado'`, `hash_anterior=$last.hash_actual`, `hash_actual=SHA256(...)`).
8. `queue_processor.enqueue('ingreso', uuid, datos)` → INSERT `sync_queue` row.
9. (Optional) Barrier opens (operator clicks "Open Barrier" or auto if hardware enabled).
10. Return `{uuid, fecha_ingreso}` to frontend.

**Tables touched (writes)**: `ingreso`, `log_transaccional`, `sync_queue`
**Tables touched (reads)**: `tipos_vehiculo`, `cantidad_vehiculos_sucursal`, current count from `ingreso`, `log_transaccional` (chain anchor)
**FKs traversed**: `uuid_sucursal` (mandatory), `uuid_tipo_vehiculo` (mandatory), `uuid_subscripcion_cliente` (null for casual)

**Sync behavior**:
- Branch → cloud: YES, every ingreso. The `sync_queue` row is pushed by `job_sync_sucursal` within 30s. Cloud receives and INSERTs in `log_transaccional` + `ingreso` rows.
- Cloud → branch: NO for casual (no parametrization pull needed).
- DIAN trigger: NO.
- Hash chain impact: YES — every ingreso writes a `log_transaccional` row with hash chain verification on both branch and cloud side.

**Integration with other tables**:
- Reads from: `sucursal` (tenant), `tipos_vehiculo` (catalog), `cantidad_vehiculos_sucursal` (capacity), `log_transaccional` (chain anchor).
- Writes to: `ingreso`, `log_transaccional`, `sync_queue`.
- Future FKs (after departure): `salidas` (1:1), `facturas` (1:N), `anulaciones` (1:N).

### 7.2 Use Case: `uc.ingreso.subscriber-lookup-by-cedula`

Llega un suscriptor: el operador NO escanea QR (el sistema no tiene scanner) — pregunta la cédula, la tipea, y el sistema le muestra los vehículos de la subscripción para que el operador elija el correcto.

**Actor**: operator

**Steps**:
1. Operator opens `IngresoForm`, clicks "Cliente con subscripción".
2. Frontend shows `ClienteLookup` input.
3. Operator **types the cedula** of the customer (e.g., `1234567890`).
4. Frontend GETs `api_sucursal /clientes?numero_identificacion=$cedula` (own branch scoped).
5. Backend returns matching `clientes` row (with `tipo_persona='natural'`).
6. Frontend GETs `api_sucursal /subscripciones-cliente?uuid_cliente=$cliente_uuid&estado='activa'`.
7. Backend returns active `subscripciones_cliente` rows for this cliente (with `subscripcion_vehiculos` joined).
8. Frontend shows list of `vehiculos` in the subscription: e.g., `ABC123 (auto)`, `DEF456 (auto)`.
9. Operator **selects** the vehicle that just arrived (e.g., `ABC123`).
10. Frontend POSTs `api_sucursal /ingresos` with `{placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente=$sub.uuid}`.
11. Backend: SELECT chain anchor from `log_transaccional`; INSERT `ingreso` (linked to subscription, `observaciones='subscriber_arrival'`).
12. INSERT `log_transaccional`.
13. `queue_processor.enqueue`.
14. (Optional) Barrier opens.

**Tables touched (writes)**: `ingreso`, `log_transaccional`, `sync_queue`
**Tables touched (reads)**: `clientes` (cedula lookup), `subscripciones_cliente` (active subscriptions), `subscripcion_vehiculos` (vehicles in sub), `vehiculos` (details), `tipos_vehiculo`, `log_transaccional` (chain anchor)

**FKs traversed**:
- Reads: `clientes.uuid_tipo_persona`, `subscripciones_cliente.uuid_cliente`, `subscripcion_vehiculos.uuid_subscripcion_cliente`, `subscripcion_vehiculos.uuid_vehiculo`, `vehiculos.uuid_tipo_vehiculo`.
- Writes: `ingreso.uuid_sucursal`, `ingreso.uuid_tipo_vehiculo`, `ingreso.uuid_subscripcion_cliente`.

**Sync behavior**:
- Branch → cloud: YES. Cloud receives and may push back via parametrization pull if subscription is revoked while vehicle is in the lot.
- Cloud → branch: YES, parametrization pull on subscription changes.
- DIAN trigger: NO.
- Hash chain impact: YES.

**Integration with other tables**:
- When the subscriber departs (`salidas` use case), the system reads `ingreso.uuid_subscripcion_cliente` and DOES NOT generate a factura (the subscription is consumed instead). This is a critical business rule: subscribers don't pay per visit; they have a flat subscription.

### 7.3 Use Case: `uc.ingreso.offline-entry`

Se cae internet en la branch: el operador sigue registrando ingresos que se acumulan en `sync_queue` hasta que vuelva la conectividad. La hash chain avanza en branch DB local y se sincroniza a cloud después.

**Actor**: operator

**Steps**:
1. Same as 7.1 (casual visitor manual entry) up to step 6.
2. INSERT `ingreso` with `observaciones='offline_entry_<timestamp>'`.
3. INSERT `log_transaccional`.
4. `queue_processor.enqueue` — the row accumulates in local `sync_queue` (no push possible while offline).
5. When internet returns, `job_sync_sucursal/drain_outbox` pushes the queue.

**Tables touched (writes)**: `ingreso`, `log_transaccional`, `sync_queue`

**Sync behavior**:
- Branch → cloud: YES, but delayed. `sync_queue.depth` grows during offline; alert emitted at depth > 1000.
- Cloud → branch: NO (downstream effects happen when cloud receives).
- DIAN trigger: NO (ingreso doesn't trigger DIAN; only facturacion does).
- Hash chain impact: NO impact while offline; hash chain advances when cloud receives.

**Integration with other tables**:
- When sync queue flushes: cloud applies the same `ingreso` insert + `log_transaccional` write. The `datos.idempotency_key` (UUID of ingreso) ensures duplicate detection.
- If two branches accidentally recorded the same plate at the same time (network split-brain): `sync_conflict` may be created with policy `manual` (admin must resolve).

### 7.4 Use Case: `uc.ingreso.plate-typo-correction`

El operador escribió mal la placa. Como `ingreso` es append-only, NO se puede UPDATE — se anula el ingreso incorrecto y se crea uno nuevo. La anulación dispara el workflow `[L-W]` `anulaciones` (solicitada → aprobada → ejecutada).

**Actor**: operator

**Steps**:
1. Operator notices the typo within minutes.
2. Operator clicks `Anular` on the ingreso (workflow `anulaciones`).
3. Frontend POSTs `api_sucursal /anulaciones` with `{uuid_ingreso=$wrong, motivo='plate_typo_<correct_plate>'}`.
4. Backend: INSERT `anulaciones` chain root (`estado='solicitada'`).
5. INSERT `log_transaccional`.
6. Operator creates a new ingreso with the correct plate (case 7.1).

**Tables touched (writes)**: `anulaciones`, `log_transaccional`, (new) `ingreso`

**Sync behavior**:
- Branch → cloud: YES for both `anulaciones` and the new `ingreso`.
- Cloud → branch: NO.
- Hash chain impact: YES (both `anulaciones` and `ingreso` write log rows).

**Integration with other tables**:
- The `anulaciones` workflow proceeds: admin reviews (IT-6). On `ejecutada`, the original `ingreso` is marked as annulled (state derived from anulaciones existence).
- The new `ingreso` is the active one for the vehicle.

### 7.5 Use Case: `uc.ingreso.operator-cupo-rejected`

El operador llega a la caseta y el sistema detecta que el cupo para ese `uuid_tipo_vehiculo` está lleno (`cantidad_vehiculos_sucursal` reached). El operador rechaza la entrada del vehículo (lo redirige a otro parqueadero cercano) o escala al admin. NO se inserta `ingreso`. Sí se inserta un evento en `log_transaccional` para auditoría (el rechazo es una decisión operativa que debe quedar registrada) más una `alerta` para que el admin investigue.

**Actor**: operator

**Steps**:
1. Vehicle arrives. Operator types plate and selects vehicle type.
2. Frontend POSTs `api_sucursal /ingresos`.
3. Backend SELECTs `cantidad_vehiculos_sucursal` for `uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo`. Compara contra current count from `ingreso WHERE estado='activo' AND uuid_tipo_vehiculo=$tipo AND uuid_sucursal=$branch`.
4. If `current_count >= cantidad`: cupo is full. Backend SELECTs chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
5. INSERT `log_transaccional` (`accion='cupo_rechazado'`, `tabla_afectada='cantidad_vehiculos_sucursal'`, `uuid_registro_afectado=$cupo_uuid`, `uuid_referencia=NULL` — no ingreso was created). Extends branch chain by 1 row.
6. INSERT `alerta` (`tipo_alerta='cupo_lleno'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_alerta_padre=NULL`, `observaciones='cupo agotado para tipo_vehiculo X'`) — admin must investigate (may authorize expansion or redirect traffic). This is the workflow chain root for the `alerta` table.
7. Return 409 Conflict `{detail: 'cupo_lleno', tipo_vehiculo: $tipo, cupo_total: $cantidad, cupo_actual: $current_count}` to frontend.
8. Operator UI shows the rejection with a red banner; operator tells the customer the lot is full and suggests the next branch.
9. Admin sees the `alerta` in `web_admin/AlertasList`; may dispatch a manual intervention (call the operator, ask to close a `salidas` row that's overdue, expand cupo via `cantidad_vehiculos_sucursal` new version with higher `cantidad`).

**Tables touched (writes)**: `log_transaccional` (cupo_rechazado audit), `alerta` (workflow chain root), `sync_queue` (deferred propagation).
**Tables touched (reads)**: `cantidad_vehiculos_sucursal` (capacity), `ingreso` (current count), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `cantidad_vehiculos_sucursal.uuid_sucursal` → `sucursal.uuid`; `cantidad_vehiculos_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain for `en_revision → resuelta` transitions).

**Sync behavior**:
- Branch → cloud: YES — the `log_transaccional` audit row + `alerta` workflow root row are pushed via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact; this is a branch-originated operational event).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (`accion='cupo_rechazado'`); cloud chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `cantidad_vehiculos_sucursal` (capacity ceiling), `ingreso` (current active count), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `log_transaccional` (audit), `alerta` (workflow chain root — admin triage), `sync_queue` (deferred propagation).
- Downstream: admin can resolve via the `alerta` workflow chain (`en_revision → resuelta`). Resolution may include expanding `cantidad_vehiculos_sucursal` (new version with higher `cantidad` — T15 catalog write).
- Cross-cutting: NO `ingreso` row is created. The vehicle does NOT enter the parking lot. The rejection is recorded for probatory purposes (the lot's occupancy state at that moment).

### 7.6 Use Case: `uc.ingreso.subscriber-rotacion-cupo-agotado`

Llega un suscriptor pero su `subscripcion_cliente` ya tiene `cantidad_maxima_vehiculos` vehículos adentro (cupo de la suscripción agotado, NO del parqueadero). El operador le permite entrar igual — pero como rotación (NO se asocia a la subscripción; el ingreso queda como `uuid_subscripcion_cliente=NULL` y se cobra como casual al salir). El sistema registra la decisión en `log_transaccional` y abre `alerta` para que el admin negocie la extensión.

**Actor**: operator

**Steps**:
1. Subscriber arrives. Operator looks up by cedula (per use case 7.2); finds the `subscripciones_cliente` row.
2. Backend counts current `ingreso` rows WHERE `uuid_subscripcion_cliente=$sub.uuid AND estado='activo'` (via `salidas` derivation). Compare against `tipo_subscripciones.cantidad_maxima_vehiculos`.
3. If `subscriber_count >= cantidad_maxima_vehiculos`: subscription cup is full. Backend SELECTs chain anchor.
4. INSERT `log_transaccional` (`accion='subscripcion_cupo_agotado'`, `tabla_afectada='subscripciones_cliente'`, `uuid_registro_afectado=$sub.uuid`, `datos_nuevos={plate, current_count, max_count, fecha_evento}`) — records the rotation decision for audit.
5. INSERT `alerta` (`tipo_alerta='subscripcion_rotacion'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_alerta_padre=NULL`, `observaciones='subscriber exceeded max vehicles'`) — admin may follow up to extend the subscription.
6. INSERT `ingreso` with `uuid_subscripcion_cliente=NULL` (it's a rotation, not a subscribed entry) — the ingreso is now a casual entry; the subscriber will pay per visit at departure.
7. INSERT `log_transaccional` (`accion='ingreso_rotacion_creado'`, `tabla_afectada='ingreso'`, `uuid_registro_afectado=$ingreso_uuid`, `uuid_referencia=$sub.uuid`).
8. `queue_processor.enqueue('ingreso', uuid, datos)`.
9. Operator UI shows: "Subscripción tiene N/M vehículos ocupados — este ingreso se cobra como casual".
10. At departure (`salidas` + `facturas`, T45 + T05): the operator charges per tariff like a casual visitor, NOT consuming subscription quota.

**Tables touched (writes)**: `ingreso` (with NULL subscripcion), `log_transaccional` (2 rows: subscripcion_cupo_agotado audit + ingreso_rotacion_creado audit), `alerta` (workflow root), `sync_queue`.
**Tables touched (reads)**: `subscripciones_cliente`, `tipo_subscripciones` (cantidad_maxima_vehiculos), `ingreso` (current subscribed count), `subscripcion_vehiculos` (vehicles in sub for display), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid` (NULL in this case); `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: YES — all 4 writes (ingreso, 2 logs, alerta) push via `sync_queue` within 30s.
- Cloud → branch: NO.
- DIAN trigger: NO (ingreso doesn't trigger DIAN).
- Hash chain impact: YES — branch chain extends by 2 rows (the two `log_transaccional` rows); cloud chain extends by 2 rows when received.

**Integration with other tables**:
- Reads from: `subscripciones_cliente`, `tipo_subscripciones`, `ingreso`, `subscripcion_vehiculos`, `log_transaccional`, `sucursal`.
- Writes to: `ingreso` (with NULL subscripcion), `log_transaccional` (2 audits), `alerta` (workflow chain root), `sync_queue`.
- Cross-cutting: this is a critical business rule — subscribers MAY exceed their quota via rotation. The system does NOT block them from entering; it just charges them as casual. The `alerta` notifies admin to follow up on subscription extension or quota renegotiation.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 15, 17, 20, 24, 28, 31.

## 9. RED Tests
- (RED) Branch POST inserts locally; cloud receives via sync.
- (RED) `estado` not updated by direct UPDATE (derived).
- (RED) `estado='anulado'` set without corresponding `anulaciones` row.
- (RED) Cross-audience: admin JWT to `api_sucursal/ingresos` → 401.
- (RED) FK RESTRICT: deleting `sucursal` with `ingresos` → error.
- (RED) Hash chain: cloud-side `log_transaccional` written for each synced ingreso.
- (RED) Manual operator: `placa` and `uuid_tipo_vehiculo` mandatory; `uuid_subscripcion_cliente` optional.
- (RED) Subscriber lookup by cedula works: 3-step GET chain returns vehiculos for the sub.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-3.x GREEN: `api_sucursal/routers/ingresos.py::POST /ingresos` INSERT + enqueue.
- [ ] IT-3.x GREEN: `job_sync_sucursal::drain_outbox_ingresos`.
- [ ] IT-3.x GREEN: cloud `api_admin/sync::POST /sync/push` handles `tabla='ingreso'` with hash-chain write.
- [ ] IT-3.x GREEN: subscriber lookup by cedula (3-step GET chain).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Plate typo at door | Med | `observaciones` column for free-text; annul + re-create pattern |
| Offline branch queue overflow | Med | Backoff exponential; admin alerts on `sync_queue` depth |
| Concurrent ingreso for same placa | Low | Allowed (rotación); one `ingreso` per active `salida` |
| Network split-brain (two branches same plate) | Low | `sync_conflict` with `manual` policy |
| Subscriber uses subscription for non-subscribed vehicle | Med | Subscriber must select from `subscripcion_vehiculos` list (UI prevents free entry) |

## 12. Open Questions
- (a) Should `ingreso` validate that cupos aren't exceeded?
- (b) Automatic closure after X hours without `salidas`?
- (c) Late departure (after closing sesion) — automatic?