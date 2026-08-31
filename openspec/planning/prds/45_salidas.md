# PRD: salidas (T45)

> `[A]` source-of-truth for every vehicle exit (1:1 with `ingreso` when the sale happens). Partitioned monthly by `pg_partman` for retention control (~3 exits/branch/day × N branches × 24h). `placa` is denormalized (captured at the door — NOT FK). Closes the ingreso via the derived state: `ingreso.estado='cerrado'` is the existence of a `salidas` row pointing to it. Subscriber exits skip `factura` (subscriber consumption). Monthly partitioning enables efficient retention purge.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule S: salidas is the single closure point for ingresos*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[A]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.salidas`
- **SQL name**: `salidas` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 2 years (operational, shorter than DIAN retention)
- **Partitioning**: monthly on `created_at` via `pg_partman` (high write rate — ~3 exits/branch/day × N branches × 24h)
- **UNIQUE constraint**: `UNIQUE (uuid_ingreso)` — enforces 1:1 with `ingreso` (an ingreso has at most one salida)
- **Origin**: F1 (schema + REVOKE + trigger + monthly partition + UNIQUE constraint) + IT-4 (writes per vehicle exit)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 5 use cases covering casual/subscriber/same-day/partitioning/no-show flows)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_ingreso` is UNIQUE — one salida per ingreso. INSERT with duplicate `uuid_ingreso` → UNIQUE violation.
- `placa` is denormalized string (captured at the door — NOT FK to `vehiculos.placa`). For subscriber exits, the placa matches the subscriber's `vehiculos.placa`. For casual exits, the placa matches the `ingreso.placa`.
- `fecha_salida` is the business event time (when the vehicle physically exits); `created_at` is when the DB registered the row.
- Travel: branch-origin rows travel to cloud via `sync_queue` within 30s.
- **1:1 with ingreso**: enforced via UNIQUE constraint. The derived state: `ingreso.estado='cerrado'` is the existence of a `salidas` row pointing to it (no row → `estado='activo'`; row exists → `estado='cerrado'`; row in `anulaciones` with `estado='ejecutada'` → `estado='anulado'`).

## 3. SOLID Atomic Breakdown
- **S**: "one vehicle exit event" — INSERT in same TX as the closure of `ingreso` (derived state) + (for casual) the `factura_pagos` cascade (T05/T36) + `log_transaccional`.
- **O**: extensible via migration; new columns (e.g., `observaciones`, `uuid_usuario_salida` for the operator who processed the exit) for forensic detail.
- **I**: branch operator API (writer — `POST /salidas`); cloud admin read API (`SalidasList` paginated, filterable); DIAN provider (cloud, reads via JOIN to `factura_electronica` for e-factura retrieval).
- **D**: `parkos_core/operacion/salida_writer.py::write_salida(uuid_ingreso, uuid_sucursal, placa, fecha_salida)` — the ONLY writer. Validates: (a) `ingreso` exists and is `estado='activo'` (no prior `salidas` row), (b) `placa` matches `ingreso.placa` (defense against operator typo).
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`. The UNIQUE constraint on `uuid_ingreso` enforces 1:1 at DB level.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch |
| `uuid_ingreso` | `prod.ingreso.uuid` | exactly one (NOT NULL, UNIQUE) | RESTRICT | the parent ingreso (1:1 enforced by UNIQUE constraint) |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `prod.facturas.uuid_salida` | FK | 1:0..1 | `facturas` references the salida for casual-exits-with-factura (T05) |
| `prod.reclamos` (polymorphic) | — | 0..1 | `tipo_reclamable='salida'` for customer complaints on the exit |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `salida_writer.py::write_salida()` per vehicle exit. UNIQUE constraint on `uuid_ingreso` enforces 1:1. |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for retention (2 years via `pg_partman` purge) |

**Special rules**:
- **UNIQUE constraint on `uuid_ingreso`**: at most one `salidas` row per ingreso. Duplicate INSERT → `UNIQUE_VIOLATION`. This enforces 1:1 with `ingreso` at DB level (defense against application bugs).
- **Monthly partitioning**: `pg_partman` partitions by `created_at` month. Retention: 24 months. Query pattern: WHERE clauses on `created_at` MUST include a date range to leverage partition pruning.
- **Hash chain**: NO — `salidas` is operational, not source-of-truth for compliance.
- **`placa` denormalized**: captured at the door, copied from `ingreso.placa`. Defense against operator typo: writer validates `placa == ingreso.placa` BEFORE INSERT.
- **Subscriber exits**: `ingreso.uuid_subscripcion_cliente IS NOT NULL` → NO `factura` generated; the subscription is consumed (the `subscripcion_vehiculos` quota remains the same, but the vehicle's `ingreso` is closed). The salida row IS inserted (1:1 still holds), but with `observaciones='subscriber_exit'` (sprint 5 may add `es_subscripcion` boolean column).
- **No-show handling**: ingreso exists but no `salidas` row is ever inserted (vehicle never returned). Admin can manually close via `anulaciones` workflow (T39). The ingreso stays `estado='activo'` until manually handled.

## 6. CodeGraph Dependencies
- `parkos_core/operacion/salida_writer.py::write_salida()` (sole writer; validates UNIQUE constraint + placa match).
- `api_sucursal/routers/salidas.py::POST /salidas` (operator exit endpoint).
- `api_admin/routers/salidas.py::GET /salidas` (paginated, filterable).
- `api_sucursal/routers/salidas.py::GET /salidas/{uuid}` (single salida detail with related ingreso + factura).
- `job_sync_sucursal/drain_outbox_salidas` (push to cloud within 30s).
- `job_sync_cloud/drain_inbox_salidas` (cloud receives + INSERTs + writes log_transaccional).
- `web_sucursal/SalidaForm` (operator form: types placa, selects ingreso, computes cost, processes payment).
- `web_sucursal/SalidasHistory` (own-branch exit list).
- `web_admin/SalidasList` (cross-branch exit dashboard).
- `workers/no_show_detector/__main__.py` (nightly cron — flags ingresos without salidas after X days; emits `alerta tipo_alerta='manual'`).

## 7. Use Cases enabled by this table

The `salidas` table is the **canonical vehicle exit event** — one row per vehicle that leaves the parking lot. The 1:1 relationship with `ingreso` is enforced by UNIQUE constraint. The derived state `ingreso.estado='cerrado'` is the existence of a `salidas` row. Use cases below cover the casual exit (with factura cascade), the subscriber exit (no factura, quota consumed), the same-day return (multi-ingreso for same placa), the monthly partitioning behavior, and the no-show handling. **Manual operator input** for placa and payment methods.

### 7.1 Use Case: `uc.salida.casual-exit-with-factura-cascade-online`

**Actor**: operator (branch)

**Real-world action**: A casual vehicle exits. Operator types the plate in `web_sucursal/SalidaForm`. Frontend GETs the matching `ingreso` via `GET /ingresos?placa=$plate&estado=activo`. Backend returns the ingreso. Operator confirms payment methods (efectivo + datafono mix allowed). Frontend POSTs `api_sucursal /salidas` with `{uuid_ingreso, placa, pagos: [{medio_pago:'efectivo', valor:130000}, {medio_pago:'datafono', valor:100000}]}`. Backend runs the full cascade TX: validate ingreso → INSERT `salidas` (1:1) → INSERT `facturas` (if applicable) → INSERT `factura_detalle` (T35) → INSERT `factura_impuestos` (T37) → INSERT `factura_otros_cobros` (T44) → INSERT `factura_pagos` (T36) → INSERT `log_transaccional`. Online mode (cloud reachable): dian_dispatcher will INSERT `factura_electronica` after dispatch (asynchronous, separate TX). Barrier opens.

**Steps**:
1. Vehicle arrives at exit barrier. Operator types plate `ABC123` in `web_sucursal/SalidaForm`.
2. Frontend GETs `api_sucursal /ingresos?placa=ABC123&estado=activo`. Backend SELECTs `ingreso WHERE placa='ABC123' AND estado='activo' (derived: no salidas row exists) AND uuid_sucursal=$branch`. Returns the ingreso with `fecha_ingreso=2026-08-31 08:00:00`, `uuid_tipo_vehiculo`, `uuid_subscripcion_cliente=null`.
3. Backend computes the cost server-side: `SELECT * FROM tarifas_sucursal WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo_v AND uuid_tipo_tarifa=$tarifa_vigente (vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta > NOW()))`. Cost = `valor * (NOW() - ingreso.fecha_ingreso) in hours (rounded)` for `por_hora`/`por_minuto`, or `valor_plena` for `plena`.
4. Operator confirms payment methods: `efectivo: 130000, datafono: 100000` (total $230000).
5. Frontend POSTs `api_sucursal /salidas` with `{uuid_ingreso, placa:'ABC123', pagos: [...]}`.
6. Backend opens TX; SELECT chain anchor from `log_transaccional`.
7. Backend SELECTs `ingreso WHERE uuid=$uuid_ingreso FOR UPDATE`. Verify `estado='activo'` (derived: no salidas row).
8. Backend validates `placa='ABC123' == ingreso.placa='ABC123'`. Reject with `PLACA_MISMATCH` if mismatch.
9. Backend validates tarifa snapshot: `SELECT valor, valor_plena FROM tarifas_sucursal WHERE uuid=$tarifa_uuid` (vigente at moment of exit).
10. INSERT `salidas` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$ingreso_uuid`, `placa='ABC123'`, `fecha_salida=NOW()`, `fecha_retencion_hasta=$created_at + 2_years`).
11. INSERT `facturas` row (`uuid_sucursal=$branch`, `subtotal=$subtotal`, `descuento=0`, `total=$total`, `uuid_ingreso=$ingreso_uuid`, `uuid_salida=$salida_uuid`, `estado='activa'` derived). Cloud will assign `numero_oficial` after dian_dispatcher.
12. INSERT `factura_detalle` rows (T35).
13. INSERT `factura_impuestos` rows (T37 — IVA 19% snapshot).
14. INSERT `factura_otros_cobros` rows (T44 — any applicable non-tax charges).
15. INSERT `factura_pagos` rows (T36 — 2 rows: efectivo $130000 + datafono $100000).
16. INSERT `log_transaccional` (`accion='salida_creada'`, `tabla_afectada='salidas'`, `uuid_registro_afectado=$salida_uuid`, `datos_nuevos={placa, total, pagos_count: 2, factura_uuid}`).
17. INSERT `log_transaccional` (`accion='factura_creada'`, `tabla_afectada='facturas'`, `uuid_registro_afectado=$factura_uuid`, `datos_nuevos={subtotal, descuento, total}`).
18. INSERT `log_transaccional` (`accion='factura_pagos_creados'`, `tabla_afectada='factura_pagos'`, `datos_nuevos={pagos_count: 2}`).
19. `queue_processor.enqueue('salidas', $uuid, $snapshot)` + `enqueue('facturas', ...)` + `enqueue('factura_pagos', ...)`.
20. (Online mode) cloud `dian_dispatcher` will receive the `facturas` row via sync, INSERT `factura_electronica`, generate `numero_oficial`, INSERT SyncBackEvent.
21. Backend returns `{uuid_salida, uuid_factura, total, numero_temporal: 'TEMP-ABC123-$timestamp' (placeholder until cloud dispatches), barrier_open: true}`.
22. Operator clicks "Open Barrier" — barrier opens, vehicle exits.
23. The `ingreso.estado` is now `'cerrado'` derived (existence of `salidas` row).

**Tables touched (writes)**: `salidas` (1 row — the closure), `facturas` (1 row), `factura_detalle` (N rows), `factura_impuestos` (K rows), `factura_otros_cobros` (M rows), `factura_pagos` (P rows), `log_transaccional` (3+ rows), `sync_queue` (M+ items).
**Tables touched (reads)**: `ingreso` (lookup + FOR UPDATE), `tarifas_sucursal` (vigente snapshot), `impuestos` (vigente snapshot), `otros_cobros` (vigente snapshot), `configuracion_tolerancias` (NOT needed for salidas), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `salidas.uuid_sucursal` → `sucursal.uuid`; `salidas.uuid_ingreso` → `ingreso.uuid` (UNIQUE); `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`; `facturas.uuid_sucursal` → `sucursal.uuid`; `factura_detalle.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_factura` → `facturas.uuid`; `factura_otros_cobros.uuid_factura` → `facturas.uuid`; `factura_pagos.uuid_factura` → `facturas.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `salidas.uuid` or `facturas.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `salidas` row + the entire facturacion cascade (`facturas` + snapshots + pagos) travel within 30s.
- Cloud → branch: YES — `SyncBackEvent` flows back with `numero_oficial`; branch updates `facturas.uuid_factura_electronica` + `numero_oficial`. Until then, `reimpresion_ticket` is BLOCKED (T38 gating).
- DIAN trigger: YES — `dian_dispatcher` sends `factura_electronica` to DIAN provider; INSERTs `SyncBackEvent`.
- Hash chain impact: YES — branch chain extends by 3+ rows; cloud chain extends on receipt + on `factura_electronica` insertion.

**Integration with other tables**:
- Reads from: `ingreso` (the open one), `tarifas_sucursal`, `impuestos`, `otros_cobros`, `log_transaccional`.
- Writes to: `salidas` (the closure), `facturas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **canonical casual exit** flow. The whole exit is one TX — if any fails, the vehicle does NOT leave (barrier stays closed). The 1:1 with `ingreso` is enforced by UNIQUE constraint — operator cannot accidentally double-record an exit.
- Special rule (online mode): branch creates `factura` with `numero_temporal` placeholder. Cloud `dian_dispatcher` assigns real `numero_oficial` after dispatch. Until SyncBackEvent, the operator can show the `numero_temporal` to the customer as a receipt — but `reimpresion_ticket` (T38) is BLOCKED because `facturas.uuid_factura_electronica IS NULL`.
- Related: T04 (`ingreso`) covers the open state; T05 (`facturas`) covers the cascade; T38 (`reimpresion_ticket`) covers the SyncBackEvent gating.

### 7.2 Use Case: `uc.salida.subscriber-exit-no-factura-quota-consumed`

**Actor**: operator (branch)

**Real-world action**: A subscriber vehicle exits. Operator types the plate `DEF456` (which matches a `vehiculos.placa` in the subscriber's subscription). Backend SELECTs the matching `ingreso` AND JOINs to `subscripciones_cliente` to find the active subscription. Backend computes cost = $0 (subscriber consumption). Operator processes exit without payment (no `factura` generated). The subscriber's `subscripcion_vehiculos` quota is NOT consumed per-exit (it's a flat subscription, not per-visit) — but the vehicle's `ingreso` IS closed. The subscriber's `clientes` row + `subscripciones_cliente` row are read-only referenced. INSERT `salidas` row with `observaciones='subscriber_exit'`.

**Steps**:
1. Subscriber vehicle arrives at exit barrier. Operator types plate `DEF456`.
2. Frontend GETs `api_sucursal /ingresos?placa=DEF456&estado=activo`. Backend SELECTs the ingreso.
3. Backend JOINs to `subscripcion_vehiculos` and `subscripciones_cliente`: `SELECT i.*, sv.uuid_subscripcion_cliente, sc.uuid_cliente, sc.uuid_tipo_subscripcion FROM ingreso i LEFT JOIN subscripcion_vehiculos sv ON sv.uuid_vehiculo=(SELECT uuid FROM vehiculos WHERE placa='DEF456') LEFT JOIN subscripciones_cliente sc ON sv.uuid_subscripcion_cliente=sc.uuid WHERE i.uuid=$ingreso_uuid AND sc.estado='activo' AND sc.uuid_sucursal=$branch`. Returns the matching subscription.
4. Backend verifies: `ingreso.uuid_subscripcion_cliente IS NOT NULL` AND matches the active subscription. (If mismatch — e.g., subscriber's vehicle but ingreso recorded as casual — proceed as casual.)
5. Backend computes `total = 0` (subscriber consumption, no per-visit charge).
6. Operator confirms exit (no payment UI required — UI shows "Subscriber exit, no charge").
7. Frontend POSTs `api_sucursal /salidas` with `{uuid_ingreso, placa:'DEF456', pagos: []}` (empty pagos array).
8. Backend opens TX; SELECT chain anchor from `log_transaccional`.
9. Backend SELECTs `ingreso FOR UPDATE`. Verify `estado='activo'` AND `uuid_subscripcion_cliente IS NOT NULL`.
10. INSERT `salidas` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$ingreso_uuid`, `placa='DEF456'`, `fecha_salida=NOW()`, `fecha_retencion_hasta=$created_at + 2_years`). NO `facturas` row created (subscribers don't get facturas per visit).
11. INSERT `log_transaccional` (`accion='salida_subscriber'`, `tabla_afectada='salidas'`, `uuid_registro_afectado=$salida_uuid`, `datos_nuevos={placa, subscriber_uuid, total:0}`).
12. `queue_processor.enqueue('salidas', $uuid, $snapshot)`.
13. Backend returns `{uuid_salida, total:0, is_subscriber:true, barrier_open:true}`.
14. Barrier opens. Subscriber exits without paying.
15. The `ingreso.estado` is now `'cerrado'` derived.
16. Sprint 5 may deduct the exit from the subscription's quota counter if `tipo_subscripciones.cantidad_maxima_vehiculos` is per-month (currently quota is total, not per-period).

**Tables touched (writes)**: `salidas` (1 row — the closure), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `ingreso` (lookup + FOR UPDATE), `vehiculos` (placa → uuid), `subscripcion_vehiculos` (join), `subscripciones_cliente` (active subscription), `clientes` (subscriber detail), `log_transaccional`.
**FKs traversed**: `salidas.uuid_sucursal` → `sucursal.uuid`; `salidas.uuid_ingreso` → `ingreso.uuid` (UNIQUE); `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid` (nullable); `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `vehiculos.placa` (denormalized, no FK); `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `salidas.uuid`.

**Sync behavior**:
- Branch → cloud: YES.
- Cloud → branch: NO.
- DIAN trigger: NO (no factura = no DIAN dispatch).
- Hash chain impact: YES — branch chain extends by 1 row.

**Integration with other tables**:
- Reads from: `ingreso`, `vehiculos`, `subscripcion_vehiculos`, `subscripciones_cliente`, `clientes`, `log_transaccional`.
- Writes to: `salidas`, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **subscriber exit** flow. The 1:1 with `ingreso` STILL HOLDS — every subscriber exit is still a `salidas` row. The DIFFERENCE is no `factura` cascade. The subscriber's `clientes` + `subscripcion_vehiculos` are read-only referenced (subscriber consumption is the business model, not the data model).
- Sprint 5: explicit `salidas.uuid_subscripcion_cliente` FK for direct lineage (currently derived via `ingreso.uuid_subscripcion_cliente`).
- Related: T18 (`subscripciones_cliente`) covers the subscription model; T20 (`vehiculos`) covers the subscriber vehicles.

### 7.3 Use Case: `uc.salida.same-day-return-visitor-leaves-and-comes-back`

**Actor**: operator (branch) + casual visitor

**Real-world action**: Casual visitor enters at 10:00am with plate `ABC123` (`ingreso_1`). Exits at 12:00pm with factura (`salidas_1` + `factura_1` for $5000). Visitor returns at 2:00pm with same plate `ABC123` — this is a NEW ingreso (`ingreso_2`, different uuid, same placa). Visitor exits at 4:00pm with another factura (`salidas_2` + `factura_2` for $5000). The system handles this correctly because each ingreso is unique by uuid, even though the placa repeats. The 1:1 with `salidas` is enforced per-uuid_ingreso, NOT per-placa. The old salida (`salidas_1`) is immutable — no UPDATE to "reopen" the visitor.

**Steps**:
1. **First visit (morning)**:
   - Operator at 10:00am types plate `ABC123` in `web_sucursal/IngresoForm`. Backend INSERTs `ingreso_1` (`uuid_ingreso_1`, `placa='ABC123'`, `estado='activo'` derived).
   - Operator at 12:00pm types plate `ABC123` in `SalidaForm`. Backend SELECTs `ingreso WHERE placa='ABC123' AND estado='activo'`. Returns `ingreso_1` (only one with that plate in active state). Backend INSERTs `salidas_1` (1:1 with `ingreso_1`), cascades to `factura_1` ($5000). Visitor exits.
   - `ingreso_1.estado` = `'cerrado'` derived.
2. **Second visit (afternoon, same day)**:
   - Operator at 2:00pm types plate `ABC123` in `web_sucursal/IngresoForm`. Backend SELECTs `ingreso WHERE placa='ABC123' AND estado='activo'`. Returns ZERO rows (ingreso_1 is cerrado, ingreso_2 doesn't exist yet). Backend INSERTs `ingreso_2` (`uuid_ingreso_2`, `placa='ABC123'`, `estado='activo'` derived, `observaciones='same_day_return'`). This is a DIFFERENT UUID from ingreso_1.
   - Operator at 4:00pm types plate `ABC123` in `SalidaForm`. Backend SELECTs `ingreso WHERE placa='ABC123' AND estado='activo'`. Returns `ingreso_2` (only one with that plate in active state — ingreso_1 is still cerrado from this morning). Backend INSERTs `salidas_2` (1:1 with `ingreso_2`, different uuid_ingreso from salidas_1), cascades to `factura_2` ($5000). Visitor exits.
3. **End of day**: the system has 2 ingresos + 2 salidas + 2 facturas for the same plate, all immutable. Admin reporting shows 2 visits for plate `ABC123` today.
4. **No UPDATE on salidas_1**: the old salida is NEVER modified. If admin queries `salidas WHERE placa='ABC123'`, returns 2 rows (salidas_1 + salidas_2), each linked to its own ingreso.

**Tables touched (writes)**: 2 `ingreso` + 2 `salidas` + 2 `facturas` + `factura_detalle` + `factura_pagos` + `log_transaccional` (multiple rows).
**Tables touched (reads)**: `ingreso` (lookup by placa + estado='activo'), `tarifas_sucursal`, `log_transaccional`.
**FKs traversed**: `ingreso.uuid_sucursal` → `sucursal.uuid`; `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid` (NULL for casual); `salidas.uuid_ingreso` → `ingreso.uuid` (UNIQUE per ingreso); `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`.

**Sync behavior**:
- Branch → cloud: YES (all events propagate).
- Cloud → branch: YES (SyncBackEvent for each factura's numero_oficial).
- DIAN trigger: YES (2 facturas → 2 e-facturas).
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `ingreso`, `tarifas_sucursal`, `log_transaccional`.
- Writes to: `ingreso`, `salidas`, `facturas`, `factura_detalle`, `factura_impuestos`, `factura_pagos`, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **same-day return** scenario. The 1:1 UNIQUE constraint on `salidas.uuid_ingreso` is per-uuid, not per-placa. The placa is denormalized and can repeat across multiple ingresos. This is by design — the system models "each visit is a separate event" rather than "one ongoing visit per placa".
- Defense against double-counting: the `ingreso.estado='activo'` derivation filters out already-closed ingresos when looking up the active one for a placa.
- Edge case: if visitor returns after `ingreso_1` is closed but `ingreso_2` is still active, the system correctly returns `ingreso_2`. The plate is NOT a unique identifier — the active ingreso is.
- Related: T04 (`ingreso`) covers the open/closed/anulado derivation.

### 7.4 Use Case: `uc.salida.monthly-partitioning-purge-after-2-years-via-pg-partman`

**Actor**: system (`workers/salidas_retention/__main__.py` nightly cron)

**Real-world action**: Nightly retention worker scans `salidas` for rows where `fecha_retencion_hasta < NOW()`. For each, `pg_partman` drops the entire monthly partition containing expired rows (rather than DELETEing individual rows). The drop is permitted because the rows' retention period has expired (2 years operational). Each partition drop is logged via `log_transaccional` for forensic traceability of what was purged when.

**Steps**:
1. `workers/salidas_retention/__main__.py` runs nightly at 03:00 cloud time (after `hash_chain_verifier` at 02:00).
2. SELECT partitions to drop: `SELECT partition_name FROM information_schema.tables WHERE table_schema='prod' AND table_name LIKE 'salidas_%' AND partition_name < 'salidas_$2years_ago'`.
3. For each expired partition: execute `DROP TABLE prod.$partition_name`. `pg_partman` does this in O(1) (drops the whole partition as a single DDL).
4. POST-DROP INSERT `log_transaccional` (`accion='salidas_partition_dropped'`, `tabla_afectada='salidas'`, `uuid_registro_afectado=$partition_uuid_marker`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores={partition_name, row_count: $count, oldest_row_date: $min, newest_row_date: $max}`, `datos_nuevos=null`).
5. INSERT `sync_log` row noting the retention cycle.
6. The dropped partition is GONE — individual rows are not preserved. The retention worker cannot recover them.

**Tables touched (writes)**: `salidas` (DROP partition — `pg_partman` maintenance, NOT a regular DELETE), `log_transaccional` (1 row per partition dropped), `sync_log` (1 row per cycle).
**Tables touched (reads)**: `information_schema.tables` (partition metadata), `log_transaccional` (chain anchor).
**FKs traversed**: NONE for the DROP (no row-level FK check on DROP TABLE).

**Sync behavior**:
- Branch → cloud: NO (cloud-internal retention).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per partition dropped.

**Integration with other tables**:
- Reads from: `information_schema.tables` (partition metadata), `log_transaccional` (chain anchor).
- Writes to: `salidas` (DROP partition — maintenance exception), `log_transaccional`, `sync_log`.
- Cross-cutting: this is the **monthly partitioning + retention purge** pattern. `pg_partman` handles the partition management automatically — partitions are pre-created N months ahead, and old ones are dropped after retention. The DROP is the maintenance exception to the `[A]` REVOKE UPDATE/DELETE — the table-level REVOKE applies to DML, not DDL. Partition drops require a maintenance role with explicit DROP grant.
- Performance benefit: queries by date range with `created_at BETWEEN ...` get partition pruning — only the relevant month partitions are scanned. For 24 months of data at ~3 exits/branch/day × 30 branches × 30 days = 2700 rows/partition, partition pruning makes queries O(rows-in-partition) instead of O(all-rows).
- Related: T31 (`sync_log`) covers a similar retention pattern (1 year); T34 (`arqueo`) covers a longer retention pattern (5 years DIAN).

### 7.5 Use Case: `uc.salida.no-show-detected-ingreso-without-salida-emits-alerta`

**Actor**: system (`workers/no_show_detector` nightly cron) + admin (cloud, triage)

**Real-world action**: A vehicle entered the parking lot 3 days ago (`ingreso` with `estado='activo'`) but never exited (no `salidas` row exists). The nightly cron detects: `SELECT i.* FROM ingreso i WHERE i.estado='activo' AND i.created_at < NOW() - INTERVAL '3 days' AND NOT EXISTS (SELECT 1 FROM salidas WHERE uuid_ingreso=i.uuid)`. For each, emit `alerta tipo_alerta='manual'` with `observaciones='ingreso=$uuid, abierto_desde=$fecha_ingreso, dias_abierto=$dias, posible_no_show_o_perdida'`. Admin triages: typically contacts the operator, who either closes the ingreso retroactively (via `anulaciones` workflow, T39) or opens a `reclamos` investigation (T40).

**Steps**:
1. Cloud `workers/no_show_detector/__main__.py` runs nightly at 03:30 cloud time (after retention purge).
2. SELECT stale active ingresos: `SELECT i.*, s.placa, s.observaciones FROM ingreso i JOIN sucursal s ON i.uuid_sucursal=s.uuid WHERE NOT EXISTS (SELECT 1 FROM salidas WHERE uuid_ingreso=i.uuid) AND i.created_at < NOW() - INTERVAL '3 days' AND i.estado NOT IN ('anulado')` (the `anulado` filter excludes already-handled via anulaciones).
3. For each stale ingreso: check for existing open `alerta tipo_alerta='manual'` for this ingreso (deduplication via `observaciones` LIKE pattern). If none:
4. `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='manual', uuid_usuario=SYSTEM, observaciones='ingreso=$uuid, placa=$placa, abierto_desde=$fecha_ingreso, dias_abierto=$dias, posible_no_show_o_perdida')`.
5. INSERT `alerta` workflow root row.
6. INSERT `log_transaccional` (`accion='alerta_emitida'`, `datos_nuevos={tipo_alerta:'manual', ingreso_uuid, placa, dias_abierto}`).
7. Admin sees alert in `web_admin/AlertasList` filter `tipo_alerta='manual'`. Admin clicks → `AlertaDetail` → drills into the ingreso detail.
8. Admin triages:
   - **Case A: False positive** (operator forgot to record exit; vehicle actually left). Admin asks operator to INSERT a `salidas` row retroactively. The retroactive INSERT is allowed (the `[A]` constraint only blocks UPDATE/DELETE; INSERT is always allowed). The `created_at` is the current time, but `fecha_salida` in the INSERT can be set to the actual exit time. INSERT `log_transaccional` (`accion='salida_retroactiva_por_admin'`, `datos_nuevos={ingreso_uuid, fecha_salida_real}`). Alert resolved: INSERT `alerta` chain row with `estado='resuelta'`.
   - **Case B: True no-show** (vehicle still in lot, barrier malfunctioned). Admin dispatches operator to physically verify. Operator opens `anulaciones` workflow (T39) to formally close the ingreso via `ejecutada`. The `anulaciones` workflow may also trigger DIAN `revocacion_factura` if a factura was issued.
   - **Case C: Theft/loss** (vehicle was stolen). Admin opens `reclamos` workflow (T40) referencing the ingreso AND opens a `documentos` record with the police report.

**Tables touched (writes — detection)**: `alerta` (1 root row), `log_transaccional` (1 row).
**Tables touched (writes — Case A retroactive)**: `salidas` (1 INSERT), `log_transaccional` (1 row), `alerta` (chain row resuelta).
**Tables touched (writes — Case B anulacion)**: `anulaciones` (workflow chain), `ingreso` (derived close via `ejecutada`), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `ingreso` (stale check), `salidas` (NOT EXISTS subquery for active state), `sucursal` (display), `log_transaccional`, `alerta` (dedup check).
**FKs traversed**: `ingreso.uuid_sucursal` → `sucursal.uuid`; `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid` (NULL for casual); `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (SYSTEM); `salidas.uuid_ingreso` → `ingreso.uuid` (UNIQUE — the retroactive INSERT must respect this); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid` or `salidas.uuid` or `anulaciones.uuid`.

**Sync behavior**:
- Branch → cloud: YES (the alerta originates from branch data; the retroactive INSERT replicates).
- Cloud → branch: NO (the alerta is informational for cloud admin).
- DIAN trigger: NO (no factura was issued).
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `ingreso` (stale check), `salidas` (NOT EXISTS for active state derivation), `sucursal`, `log_transaccional`, `alerta`.
- Writes to: `alerta` (workflow root), `salidas` (retroactive INSERT in Case A), `anulaciones` (workflow chain in Case B), `reclamos` (Case C), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **no-show detection** pattern. The `salidas` table's existence (or absence) is the source of truth for whether an ingreso is closed. The cron detects the "stuck open" state and emits an alert. Resolution paths vary (retroactive INSERT, anulacion, reclamos) depending on the actual situation.
- Sprint 5: per-branch configurable no-show threshold (default 3 days, but high-traffic branches may want 1 day, low-traffic may want 7 days).
- Related: T04 (`ingreso`) covers the active/closed/anulado derivation; T39 (`anulaciones`) covers the formal close workflow; T40 (`reclamos`) covers the investigation path; T41 (`alerta`) covers the alert emission pattern.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger + UNIQUE constraint + monthly partition), 2 (DB triggers + pg_partman), 3 (partitioning via pg_partman), 5 (audit constraints — REVOKE), 6 (cloud admin API for read), 7 (branch API for write + read), 8 (Pydantic schemas), 10 (cloud sync worker for replication), 11 (branch sync worker for replication), 12 (sync_queue interop), 13 (web_admin SalidasList), 14 (web_sucursal SalidaForm + SalidasHistory), 15 (shadcn UI components for forms), 20 (structlog), 21 (Prometheus counters — exits per branch per hour), 24 (pytest), 28 (docker compose), 30 (no_show_detector cron + salidas_retention cron), 31 (security audit — fraud detection via no-show patterns).

## 9. RED Tests
- (RED) INSERT `salidas` for an `ingreso` with `estado='activo'` → success.
- (RED) INSERT second `salidas` for same `ingreso` → UNIQUE violation (`uuid_ingreso` constraint).
- (RED) UPDATE `prod.salidas` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE from `prod.salidas` → `AUDIT_FIRST_INMUTABLE` (from `rol_app`; maintenance role via DROP PARTITION).
- (RED) `placa` validation: `placa != ingreso.placa` → `PLACA_MISMATCH`.
- (RED) Subscriber exit: `ingreso.uuid_subscripcion_cliente IS NOT NULL` → NO `factura` created; `total=0`; `salidas` row still inserted.
- (RED) Casual exit: `ingreso.uuid_subscripcion_cliente IS NULL` → `factura` cascade created.
- (RED) Same-day return: 2 ingresos + 2 salidas for same placa → both pairs valid (different uuid_ingreso).
- (RED) No-show: ingreso > 3 days without salidas → cron emits `alerta tipo_alerta='manual'`.
- (RED) Retroactive INSERT: admin authorizes `salidas` INSERT with `fecha_salida=$past_time` for old ingreso → success; `log_transaccional` records `salida_retroactiva_por_admin`.
- (RED) Partition pruning: query `WHERE created_at >= '2026-08-01' AND created_at < '2026-09-01'` → EXPLAIN shows single partition hit.
- (RED) `pg_partman` retention: partitions older than 24 months dropped automatically; `log_transaccional` audit row per partition drop.
- (RED) FK RESTRICT: deleting `ingreso` with `salidas` row → error.
- (RED) Cross-branch admin query NEVER writes to `salidas` (read-only).
- (RED) Late exit after closing sesion (T43): operator closed sesion at 6pm, vehicle exits at 6:30pm → operator opens new sesion, then processes exit. The `salidas` row is created normally; the sesion transition is independent.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + UNIQUE constraint + monthly partition.
- [ ] F1.x `parkos_core/operacion/salida_writer.py::write_salida()` (sole writer; validates UNIQUE + placa match).
- [ ] F1.x `pg_partman` partition management config (pre-create 3 months ahead, retain 24 months).
- [ ] F1.x Maintenance role for DROP PARTITION (retention purge exception).
- [ ] IT-4.x: `api_sucursal/routers/salidas.py::POST /salidas` (operator exit endpoint with subscriber detection).
- [ ] IT-4.x: subscriber exit path (skip factura cascade).
- [ ] IT-4.x: casual exit path (full facturacion cascade).
- [ ] IT-4.x: `api_sucursal/routers/salidas.py::GET /salidas/{uuid}` (detail with related ingreso + factura).
- [ ] IT-4.x: `api_admin/routers/salidas.py::GET /salidas` (paginated, filterable).
- [ ] IT-4.x: `job_sync_sucursal/drain_outbox_salidas` (push to cloud within 30s).
- [ ] IT-4.x: `job_sync_cloud/drain_inbox_salidas` (cloud receives + INSERTs + writes log).
- [ ] IT-4.x: `web_sucursal/SalidaForm` (operator form: placa lookup, payment breakdown, subscriber detection).
- [ ] IT-4.x: `web_sucursal/SalidasHistory` (own-branch exit list).
- [ ] IT-4.x: `web_admin/SalidasList` (cross-branch exit dashboard).
- [ ] IT-4.x: `workers/no_show_detector/__main__.py` nightly cron at 03:30 cloud.
- [ ] IT-4.x: `workers/salidas_retention/__main__.py` nightly cron at 03:00 cloud (partition DROP + audit).
- [ ] Sprint 5: explicit `salidas.uuid_subscripcion_cliente` FK for direct lineage (vs current derived via `ingreso`).
- [ ] Sprint 5: explicit `salidas.es_subscripcion` boolean column for query speed (vs current `observaciones` text).
- [ ] Sprint 5: per-branch configurable no-show threshold.
- [ ] Sprint 5: barrier integration (auto-open on INSERT success if hardware enabled).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator types wrong placa (typo) | Low | Writer validates `placa == ingreso.placa`; mismatch rejected |
| Operator forgets to record exit (no-show) | Med | Nightly cron emits alert after 3 days; sprint 5: per-branch shorter threshold |
| Subscriber exit recorded as casual (operator error) | Low | UI shows "Subscriber detected" badge; operator must explicitly confirm casual override |
| UNIQUE constraint violation during race (two operators record same exit simultaneously) | Low | First INSERT wins; second gets `UNIQUE_VIOLATION` → operator UI shows "already exited" |
| Late exit (after closing sesion) | Med | Operator opens new sesion before processing exit; system handles via independent flows |
| Partition prune misses date range queries (performance issue) | Low | `created_at` is partition key; date range queries always prune |
| Partition DROP accidentally drops live rows | Low | `fecha_retencion_hasta < NOW()` check before DROP; sprint 5: grace period of 7 days |
| Subscriber subscription expires mid-visit (vehicle enters as subscriber, exits after expiration) | Med | Backend detects on exit: `subscripciones_cliente.fecha_vencimiento < NOW()` → convert to casual charge (UI shows "Subscription expired — charging casual rate") |
| Vehicle exits without operator processing (barrier open without system record) | Med | Sprint 5: barrier integration — barrier only opens after `POST /salidas` succeeds |
| Massive exit queue during peak hours (end of month, holidays) | Med | Operator UI queues multiple exits; backend processes sequentially; partition pruning keeps query fast |
| `facturas` cascade fails mid-TX (e.g., log_transaccional hash chain break) | Low | Whole TX rolls back; barrier stays closed; operator retries |

## 12. Open Questions
- (a) Late exit after closing sesion — automatic? Currently operator opens new sesion before processing exit. Sprint 5 may auto-open a new sesion for late exits.
- (b) Subscriber exit when subscription expired mid-visit — automatic conversion to casual? Currently UI shows override option; sprint 5 may auto-convert.
- (c) Per-branch no-show threshold? Sprint 5 — currently global 3 days.
- (d) Barrier integration: should the barrier open automatically on `POST /salidas` success, or require operator click? Sprint 5 — depends on hardware (Tipo A/B/C per AGENTS.md).
- (e) Should `salidas` support partial exits (e.g., one person exits but passengers stay)? Currently NO — 1:1 with ingreso, the vehicle is the unit. Sprint 5 may add `salidas_parciales` for partial exit.
- (f) Should `salidas` carry `observaciones` typed fields (e.g., `motivo_salida_temprana`)? Currently free-text; sprint 5 may ENUM.
- (g) No-show vs theft distinction — how does the cron differentiate? Currently the alert is informational; admin triages manually.
- (h) Same-day return: should the system WARN the operator "this plate already exited today"? Sprint 5 may add daily visit count to operator UI.
- (i) Should `salidas` partition pruning be mandatory in queries (i.e., reject queries without date range)? Sprint 5 may add query interceptor.
- (j) Multi-vehicle exit (e.g., a truck with trailer) — single salida or two? Currently single (the truck); sprint 5 may add trailer support.
- (k) Refund flow: if `factura` is anulada AFTER `salidas`, should the `salidas` row also be flagged? Currently NO — `salidas` is append-only and immutable. Sprint 5 may add `salidas.anulada` boolean (which would violate [A]; better to use `anulaciones` workflow).
- (l) Should `salidas` retention be aligned with `facturas` retention (5 years DIAN) for compliance? Currently 2 years operational; sprint 5 may extend to 5 years for cross-reference with DIAN retention.
