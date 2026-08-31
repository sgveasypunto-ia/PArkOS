# PRD: tarifas_sucursal (T14)

> Tariff per (sucursal, tipo_vehiculo, tipo_tarifa). **Critical for DIAN billing history**: the versioning is mandatory so a ticket issued with the 2024-01-01 tariff calculates correctly even after a 2026 tariff update. NO FK from `facturas` — the calculation is **snapshotted** into `factura_detalle` at invoice time; `tarifas_sucursal` is only consulted at calculation moment, not referenced after.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule S: tariffs are calculation inputs, not FK targets*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.tarifas_sucursal`
- **SQL name**: `tarifas_sucursal` (with `prod` schema)
- **Enforcement level**: `[V]` projection (CRITICAL for billing history; every change emits `log_transaccional`)
- **Retention**: indefinite (legal billing requirement — must preserve historical tariff grid for re-audit)
- **Origin**: F1 (schema + parametrization seed in `uc.sucursal.admin-onboarding-pairing-flow`) + IT-2 (admin CRUD, version flow)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; snapshot semantic + DIAN recalc + cross-branch reporting documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `valor` is `decimal(10,2)` (e.g., `3500.00` COP per hour for autos).
- `valor_plena` is `decimal(10,2)` (the "full-day" rate for B2B subscriptions; NULL for casual `por_hora` / `por_minuto` modes).
- `vigente_desde` / `vigente_hasta` form the version window. A vigente row has `vigente_hasta IS NULL`. An expired row has `vigente_hasta < NOW()`.

## 3. SOLID Atomic Breakdown
- **S**: "one tariff rate for (sucursal, tipo_vehiculo, tipo_tarifa) tuple at a specific time window". Tariffs are calculation inputs consulted at invoice time — NOT referenced by FK from `facturas`.
- **O**: adding a new `tipo_tarifa` (e.g., `'por_dia'`) requires no schema change (it's a catalog row); adding a new column to `tarifas_sucursal` (e.g., `valor_finde_semana`) requires migration but is rare.
- **I**: admin CRUD via `api_admin /tarifas-sucursal`; branch reads own vigentes at calculation time; cloud admin reads cross-branch grid for audit.
- **D**: `parkos_core/models/V/tarifas_sucursal.py` (model); `parkos_core/facturacion/tariff_resolver.py` (vigente lookup at calculation time); `workers/tarifas/expiry_monitor.py` (alerts when tarifa is about to expire without replacement).
- **Atomic**: INSERT (admin creates new tarifa), UPDATE (creates new version — `vigente_hasta=NOW()` on old, new row with `vigente_desde=NOW()`), DELETE forbidden by FK RESTRICT (sucursal + tipos_vehiculo + tipo_tarifa all reference).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch |
| `uuid_tipo_vehiculo` | `prod.tipos_vehiculo.uuid` | exactly one (NOT NULL) | RESTRICT | the vehicle type |
| `uuid_tipo_tarifa` | `prod.tipo_tarifa.uuid` | exactly one (NOT NULL) | RESTRICT | the tariff mode |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | tariffs are NOT referenced by FK from `facturas`/`factura_detalle`. The calculation is snapshotted into `factura_detalle.concepto + valor_unitario + subtotal` at invoice time. See use case 7.3 for snapshot semantics. |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin via `api_admin /tarifas-sucursal` (initial creation); inside TX + `log_transaccional` |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted with new UUID. NEVER modify `valor` of existing version — DIAN audit. |
| DELETE | NO | Archive via version flow; FK RESTRICT prevents |

**Special rules**:
- Versioning is **mandatory** for DIAN audit. Every tarifa change = new row version + archive old. The `log_transaccional` row records `datos_anteriores={old_valor}` and `datos_nuevos={new_valor}` for probatory integrity.
- The vigente lookup query: `SELECT * FROM tarifas_sucursal WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo AND uuid_tipo_tarifa=$modo AND vigente_desde<=NOW() AND (vigente_hasta IS NULL OR vigente_hasta>NOW())`. Always returns 1 row (enforced by application logic + UNIQUE partial index `(uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa) WHERE vigente_hasta IS NULL`).
- `tarifas_sucursal` is read at calculation time (ingreso lookup for "expected cost" preview + salida lookup for actual factura calculation), NOT referenced by FK from `factura_detalle`. The snapshot is in `factura_detalle.concepto + valor_unitario + subtotal`.

## 6. CodeGraph Dependencies
- `api_admin/routers/tarifas_sucursal.py::POST /tarifas-sucursal`, `PATCH /tarifas-sucursal/{uuid}`, `GET /tarifas-sucursal`, `GET /tarifas-sucursal/audit`.
- `api_sucursal/routers/tarifas_sucursal.py::GET /tarifas-sucursal` (own vigentes; used at ingreso preview + facturacion calculation).
- `parkos_core/facturacion/tariff_resolver.py::vigente(uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, at_datetime)` (single-row lookup).
- `parkos_core/facturacion/cost_calculator.py::calcular(ingreso, salida)` (uses tariff_resolver + duration).
- `workers/tarifas/expiry_monitor.py` (cron — alerts when vigente tarifa has `vigente_desde + max_age > NOW()` and no replacement scheduled).
- `web_admin/TarifasForm`, `TarifasGrid` (cross-branch view).

## 7. Use Cases enabled by this table

The `tarifas_sucursal` table is the **calculation input for every business factura** — the operator needs the vigente rate at the moment of invoicing to compute `subtotal = duracion × valor_por_unidad_tiempo`. Use cases below describe the version-flow (how a new rate replaces an old one), the calculation-time lookup (read-only), the snapshot semantic (why `facturas` does NOT FK to `tarifas_sucursal`), and the monitoring that ensures no branch is left without a vigente rate.

### 7.1 Use Case: `uc.tarifas.admin-creates-new-tarifa-version`

Admin cloud crea una nueva versión de tarifa para una branch: la vigente actual se archiva con `vigente_hasta=NOW()` y se inserta una nueva fila `[V]` con `vigente_desde=NOW(), vigente_hasta=NULL`. El sistema valida que no haya overlap con otras versiones vigentes para el mismo `(sucursal, tipo_vehiculo, tipo_tarifa)` triple, persiste ambas escrituras en la misma TX, y dispara parametrización push a la branch para que el operador local vea la nueva tarifa al cobrar. El flujo toca 7 tablas: `tarifas_sucursal` (W nueva + UPDATE archivo anterior), `sucursal` (R tenant), `tipos_vehiculo` (R), `tipo_tarifa` (R), `usuarios` (R admin actor), `log_transaccional` (W), `sync_queue` (W parametrización push).

**Actor**: admin

**Pre-conditions**: branch exists with `estado='activo'`; previous tarifa version exists (unless first-time creation, where there is no vigente row to archive); admin has `permiso='actualizar_tarifas'`; `tipos_vehiculo` and `tipo_tarifa` catalogs are populated.

**Steps**:
1. Admin opens `web_admin/SucursalesList/{branch}/TarifasTab`, clicks `New Tarifa` for the (auto, por_hora) cell.
2. Frontend shows `TarifasForm`: `uuid_tipo_vehiculo='auto'` (pre-filled), `uuid_tipo_tarifa='por_hora'` (pre-filled), `valor=4000.00` (new rate), `valor_plena=null`, `vigente_desde=NOW()` (pre-filled, but admin can backdate if needed).
3. Admin confirms. Frontend POSTs `api_admin /tarifas-sucursal` (admin- JWT) with `{uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, valor, valor_plena, vigente_desde}`.
4. Backend validates: `permisos_usuario` for `permiso='actualizar_tarifas'`; rejects 403 if missing.
5. Backend SELECTs the current vigente row: `SELECT uuid FROM tarifas_sucursal WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo_v AND uuid_tipo_tarifa=$modo AND vigente_hasta IS NULL`. If found: this is an UPDATE flow (archive + new). If not found: this is an INSERT flow (first-time).
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
7. Backend validates no overlap: SELECTs any `tarifas_sucursal` rows WHERE `uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo_v AND uuid_tipo_tarifa=$modo AND vigente_hasta IS NULL AND (vigente_desde < $new_vigente_desde OR $new_vigente_desde IS NULL)`. Rejects 409 if overlap.
8. If UPDATE flow: UPDATE old vigente row SET `vigente_hasta=NOW()` (or `$new_vigente_desde` if backdating). Capture the previous row data for `datos_anteriores`.
9. Backend INSERTs new `tarifas_sucursal` row (`vigente_desde=$new_vigente_desde, vigente_hasta=NULL, estado='activo'`).
10. Backend INSERTs `log_transaccional` (`accion='tarifa_actualizada'`, `tabla_afectada='tarifas_sucursal'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores={old_valor, old_vigente_desde, old_vigente_hasta: NOW()}`, `datos_nuevos={new_valor, new_vigente_desde, new_vigente_hasta: null}`).
11. `queue_processor.enqueue('tarifas_sucursal', $new_uuid, $snapshot)` + parametrization push for the archived old row (so branch also updates `vigente_hasta`). INSERT `sync_queue` rows (typically 2 rows: 1 for new, 1 for old archive).
12. Backend returns `{new_uuid, old_uuid_archived, vigente_desde}` to frontend.
13. Branch receives parametrization within 30s. UPSERTs new row + UPDATE local old row to `vigente_hasta=NOW()` (idempotent).
14. Next `FacturacionForm` lookup at branch uses the new tarifa; the old one is no longer vigente.
15. Operator in `web_sucursal/TarifasList` sees the new vigente version highlighted in green.

**Tables touched (writes)**: `tarifas_sucursal` (1 new + 1 archive UPDATE), `log_transaccional` (1 row), `sync_queue` (1-2 rows).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `sucursal` (tenant), `tipos_vehiculo` (catalog), `tipo_tarifa` (catalog), `tarifas_sucursal` (current vigente + overlap check), `log_transaccional` (chain anchor), `usuarios` (admin actor).
**FKs traversed**: `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`; `tarifas_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `tarifas_sucursal.uuid_tipo_tarifa` → `tipo_tarifa.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tarifas_sucursal.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the new version + archive update within 30s. Branch applies both atomically.
- DIAN trigger: NO (tarifa change doesn't trigger DIAN directly; only the next `factura_electronica` creation that uses the new tarifa will).
- Hash chain impact: YES — cloud chain extends by 1 row (tarifa_actualizada); branch chain extends by 1 row when parametrization received.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `sucursal` (tenant), `tipos_vehiculo` + `tipo_tarifa` (catalogs), `tarifas_sucursal` (vigente lookup + overlap check), `log_transaccional` (chain anchor), `usuarios` (admin).
- Writes to: `tarifas_sucursal` (new version + archive old), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: this is the **canonical versioning pattern** for DIAN audit. The `log_transaccional.datos_anteriores` snapshot of the OLD `valor` is what makes retroactive re-audit possible: if a regulatory body asks "what was the tarifa on 2026-01-15?", the answer is reconstructed from `tarifas_sucursal` vigente at that date, AND from `log_transaccional` to confirm the value was never silently altered.
- Related: the `tarifas_sucursal` is read at calculation time (use case 7.2) and snapshotted into `factura_detalle` (use case 7.3) — both read paths assume the vigente version is correct.

### 7.2 Use Case: `uc.tarifas.branch-queries-vigente-at-ingreso-expected-cost`

Cuando llega un vehículo casual y el operador registra el ingreso, el sistema muestra un "costo esperado" en el `IngresoForm` basado en la tarifa vigente. Esto ayuda al operador a informar al cliente cuánto pagará aproximadamente al salir. La query es: SELECTs `tarifas_sucursal` WHERE `uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo AND uuid_tipo_tarifa='por_hora' AND vigente_hasta IS NULL`. Devuelve `valor` (COP/hora). El operador ve "Aprox $X por hora" en la UI. El flujo NO genera escrituras — es READ puro (no extiende la hash chain).

**Actor**: operator (triggers the read via IngresoForm render)

**Pre-conditions**: branch is operational; `tarifas_sucursal` has vigentes rows for the `(sucursal, tipo_vehiculo='auto', tipo_tarifa='por_hora')` triple (seeded during onboarding in `uc.sucursal.admin-onboarding-pairing-flow` step 5); operator is creating an ingreso via `IngresoForm`.

**Steps**:
1. Operator opens `web_sucursal/IngresoForm`, selects `uuid_tipo_vehiculo='auto'`. Frontend fires `GET api_sucursal /tarifas-sucursal?vigente_only=true&uuid_tipo_vehiculo=auto&uuid_tipo_tarifa=por_hora`.
2. Backend SELECTs `tarifas_sucursal` WHERE `uuid_sucursal=$JWT_branch AND uuid_tipo_vehiculo=$tipo_v AND uuid_tipo_tarifa='por_hora' AND vigente_hasta IS NULL`. Returns 1 row with `valor=4000.00`.
3. Frontend displays: "Tarifa vigente: $4,000/hora. Estancia aprox 1h → $4,000".
4. If the operator changes `uuid_tipo_vehiculo='moto'`, frontend re-fires the GET and shows "$2,500/hora" (different rate).
5. Operator continues with ingreso creation. The expected cost is purely informational — NOT stored anywhere.
6. (No writes; no `log_transaccional`; no `sync_queue`. Per SOLID I, reads do not extend the chain.)

**Tables touched (writes)**: NONE.
**Tables touched (reads)**: `tarifas_sucursal` (vigente lookup).
**FKs traversed**: `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`; `tarifas_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `tarifas_sucursal.uuid_tipo_tarifa` → `tipo_tarifa.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** — this is a read; per SOLID I, reads do not extend the chain.

**Integration with other tables**:
- Reads from: `tarifas_sucursal` (vigente lookup).
- Writes to: NONE.
- Cross-cutting: the expected cost display is a UX feature, NOT a billing record. The actual `factura_detalle` calculation (use case 7.3) happens at `salidas` time, using the same vigente lookup but with the actual `fecha_salida - fecha_ingreso` duration. If a tarifa was vigente at ingreso but expired before salida (rare edge case), the system uses the vigente at SALIDA time (the moment of calculation), not at INGRESO time. This is configurable per business rule (sprint 5 may add a flag).
- Related: if `tarifas_sucursal` has NO vigente row for the (sucursal, tipo_vehiculo, tipo_tarifa) triple (e.g., admin forgot to create one), the GET returns 404 → frontend shows red banner "No tariff configured — contact admin". The operator cannot complete the ingreso. Admin must create the missing tarifa.

### 7.3 Use Case: `uc.tarifas.snapshot-into-factura-detalle-no-fk-to-tarifas`

Cuando un vehículo sale y el operador crea la factura, el sistema lee la `tarifas_sucursal` vigente al momento de salida, calcula el costo (`duracion_segundos / 3600 * valor_por_hora`), y snapshotea el cálculo en `factura_detalle` con `concepto='estancia_por_hora'`, `cantidad=$duracion_horas`, `valor_unitario=$valor_tarifa`, `subtotal=$subtotal_calculado`. **El `factura_detalle` NO FK a `tarifas_sucursal`** — el cálculo es autosuficiente: contiene todos los números necesarios para reconstruir el cobro sin consultar la tabla original. Esto es crítico para DIAN: si la tarifa original se modifica o se borra después, la factura emitida permanece exacta. El flujo toca 8 tablas: `tarifas_sucursal` (R), `facturas` (W), `factura_detalle` (W snapshot), `factura_pagos` (W), `factura_impuestos` (W), `factura_otros_cobros` (W), `log_transaccional` (W), `sync_queue` (W).

**Actor**: operator (creates the factura)

**Pre-conditions**: branch is operational; `ingreso` and `salidas` exist for the vehicle; `tarifas_sucursal` has vigente rows for the relevant triple.

**Steps**:
1. Subscriber (or casual) departs. Operator opens `SalidaForm`, types plate, system finds the `ingreso` (per `uc.ingreso.*`).
2. System checks: is this a subscriber with active subscription? If yes → no factura (per `uc.facturas.subscriber-departure-without-bill`). If casual → proceeds to facturacion.
3. Operator opens `FacturacionForm`. Frontend computes cost preview by calling backend `GET /facturacion/preview?uuid_ingreso=$ingreso_uuid`.
4. Backend reads `ingreso` (get `fecha_ingreso`, `uuid_tipo_vehiculo`), reads `salidas` (or uses NOW() if salida not yet recorded). Computes `duracion_segundos = NOW() - fecha_ingreso`.
5. Backend SELECTs `tarifas_sucursal` WHERE `uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo AND uuid_tipo_tarifa='por_hora' AND vigente_hasta IS NULL` (vigente at this moment).
6. Backend computes `subtotal = (duracion_segundos / 3600) * valor`. Returns preview to frontend.
7. Operator confirms payment (cash + card mixto possible). Frontend POSTs `api_sucursal /facturas` with `{uuid_ingreso, uuid_salida, pagos: [...], observaciones}`.
8. Backend opens TX; SELECT chain anchor from `log_transaccional`.
9. Backend INSERTs `facturas` row (`subtotal, descuento, total`).
10. Backend INSERTs `factura_detalle` row (THE SNAPSHOT): `concepto='estancia_por_hora_tarifa_vigente'`, `cantidad=$duracion_horas`, `valor_unitario=$valor_tarifa`, `subtotal=$subtotal`. **No FK to `tarifas_sucursal`** — all calculation data is in the row itself.
11. Backend INSERTs `factura_pagos` rows (one per payment method).
12. Backend INSERTs `factura_impuestos` rows (snapshot from `impuestos` vigente at the moment).
13. Backend INSERTs `factura_otros_cobros` rows (snapshot from `otros_cobros` vigente at the moment).
14. Backend INSERTs `log_transaccional` (`accion='factura_creada'`, ...).
15. `queue_processor.enqueue('facturas', $uuid, $snapshot)` + enqueue all children.
16. Backend returns `{factura_uuid, total}` to frontend.
17. Cloud receives via sync; cloud assigns `factura_electronica.uuid`, `numero_oficial` (per `uc.facturas.online-mode-cloud-assigns-dian-number`); `SyncBackEvent` flows back to branch.
18. **At this point, even if admin later PATCHes the tarifa (use case 7.1) creating a new version with `vigente_desde > fecha_salida`, the snapshot in `factura_detalle` is immutable. The historical factura remains accurate to the moment of calculation.**

**Tables touched (writes)**: `facturas`, `factura_detalle` (snapshot — NO FK), `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `tarifas_sucursal` (vigente lookup at calculation moment), `ingreso`, `salidas`, `impuestos`, `otros_cobros`, `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`; `tarifas_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `tarifas_sucursal.uuid_tipo_tarifa` → `tipo_tarifa.uuid` (READS); `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`; `factura_detalle.uuid_sucursal` → `sucursal.uuid`; `factura_detalle.uuid_factura` → `facturas.uuid` (the FK is to the parent factura, NOT to `tarifas_sucursal`); `factura_pagos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_factura` → `facturas.uuid` + `factura_impuestos.uuid_impuesto` → `impuestos.uuid`; `factura_otros_cobros.uuid_factura` → `facturas.uuid` + `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `facturas` + all children + `log_transaccional` push via `sync_queue` within 30s. Cloud preserves branch chain verbatim.
- Cloud → branch: YES — `SyncBackEvent` flows back with the `factura_electronica.numero_oficial`.
- DIAN trigger: YES — `dian_dispatcher` enqueues after cloud receives the factura.
- Hash chain impact: YES — branch chain extends by 1 row (factura_creada); cloud chain extends by 1 row on receipt + 1 row on `factura_electronica_creada`.

**Integration with other tables**:
- Reads from: `tarifas_sucursal` (vigente lookup), `ingreso`, `salidas`, `impuestos` (snapshot source), `otros_cobros` (snapshot source), `log_transaccional` (chain anchor), `sucursal` (tenant).
- Writes to: `facturas`, `factura_detalle` (snapshot), `factura_pagos`, `factura_impuestos` (snapshot), `factura_otros_cobros` (snapshot), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **DIAN snapshot pattern** — every calculation input is snapshotted into the factura at issuance time. The factura is self-contained and accurate even if upstream catalogs change. This is essential for regulatory audit: a factura from 2026-01-15 must show the EXACT `valor` that was vigente on that date, regardless of subsequent tarifa updates.
- Related: `factura_impuestos` and `factura_otros_cobros` follow the same snapshot pattern — `porcentaje_aplicado` (for impuestos) and `valor_aplicado` (for otros_cobros) are snapshotted, NOT referenced by FK to the live catalog. The `valor_aplicado` is the calculation result; the `valor_unitario` from `otros_cobros` is the source.

### 7.4 Use Case: `uc.tarifas.expiry-monitor-warns-tarifa-without-replacement`

Worker cron `tarifas/expiry_monitor` corre diariamente en cloud. Escanea tarifas vigentes con `vigente_desde + anticipated_validity_days < NOW()` (configurable, default 365 days) que NO tengan una versión de reemplazo ya creada (`vigente_desde > NOW()` scheduled). Para cada una, emite `alerta tipo_alerta='tarifa_por_vencer'` (warning). Si llega a `vigente_desde + anticipated_validity_days + 7 days` sin reemplazo: emite `alerta tipo_alerta='tarifa_sin_reemplazo_critico'` (critical). El admin debe actuar creando una nueva versión (use case 7.1) antes de que la actual expire. El flujo toca 5 tablas: `tarifas_sucursal` (R scan), `alerta` (W workflow root), `log_transaccional` (W), `sync_log` (W ciclo), `sucursal` (R tenant).

**Actor**: system (cloud `tarifas/expiry_monitor` cron worker)

**Pre-conditions**: at least one `tarifas_sucursal` row is vigente with `vigente_desde` older than `anticipated_validity_days` (default 365). Cron is enabled (daily 02:30 cloud time, after `documentos/expiry_monitor` at 02:00).

**Steps**:
1. `expiry_monitor` cron fires daily at 02:30 cloud time. SELECTs `tarifas_sucursal` WHERE `vigente_hasta IS NULL AND estado='activo'`.
2. For each row, computes `days_since_vigente_desde = CURRENT_DATE - vigente_desde::date`. Also SELECTs whether a replacement exists: `SELECT uuid FROM tarifas_sucursal WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo_v AND uuid_tipo_tarifa=$modo AND vigente_desde > NOW() AND vigente_desde IS NOT NULL LIMIT 1`. (Replacement = row scheduled for future activation.)
3. If `days_since_vigente_desde >= anticipated_validity_days AND replacement IS NULL`: tarifa is approaching end-of-life with no successor.
4. Two buckets:
   - **Warning (between threshold and threshold + 7 days)**: `days_since_vigente_desde >= anticipated_validity_days AND < anticipated_validity_days + 7` → INSERT `alerta tipo_alerta='tarifa_por_vencer'`, `estado='abierta'`, `uuid_sucursal=$branch`, `observaciones='tarifa_${tipo}_${modo}_vigente_desde_${date}_sin_reemplazo, days_active:$X'`.
   - **Critical (>= threshold + 7 days)**: `days_since_vigente_desde >= anticipated_validity_days + 7` → INSERT `alerta tipo_alerta='tarifa_sin_reemplazo_critico'`, `estado='abierta'`, similar observations.
5. Before INSERT, checks for existing open `alerta` for same `(tipo_alerta, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa)` to dedup.
6. For each `alerta`: INSERT `log_transaccional` (`accion='tarifa_expiry_alert_emitted'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alert.uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={tarifa_uuid, days_active, replacement_exists: false}`).
7. INSERT `sync_log` (cycle metrics).
8. Admin sees alerta in `web_admin/AlertasList`. Clicks → opens `TarifasForm` for the (branch, tipo_vehiculo, tipo_tarifa) triple, pre-fills with `vigente_desde=NOW() + 1 day` (or NOW() for immediate) and current `valor` as default. Admin creates the replacement (per use case 7.1).
9. After replacement created, the new version has `vigente_desde > NOW()`. The `expiry_monitor` next run will see the replacement exists and NOT emit the alert.
10. Admin manually resolves the alerta: workflow chain transition `en_revision → resuelta` with `observaciones='reemplazo_creado_<uuid>'`.
11. Alerta workflow chain emits 1-3 `log_transaccional` rows total.

**Tables touched (writes)**: `alerta` (1 root per affected tarifa + 2-3 transitions), `log_transaccional` (1 per alert + 2-3 per transitions), `sync_log` (1 cycle).
**Tables touched (reads)**: `tarifas_sucursal` (scan + replacement check), `alerta` (dedup), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (SYSTEM lookup).
**FKs traversed**: `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_referencia` (polymorphic) → `tarifas_sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (monitor runs cloud-side).
- Cloud → branch: NO (alerta is cloud-only operational; branch sees the new tarifa only when parametrization push delivers it).
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per alert + 1-3 rows per alert workflow transitions.

**Integration with other tables**:
- Reads from: `tarifas_sucursal` (scan), `alerta` (dedup), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (SYSTEM).
- Writes to: `alerta` (workflow root + transitions), `log_transaccional` (audit), `sync_log` (cycle metrics).
- Cross-cutting: this is the **tarifa lifecycle enforcer**. Without this monitor, a tarifa could be silently vigente for years, becoming outdated relative to market rates. The monitor is a forcing function for periodic review.
- Related: if `anticipated_validity_days` is too short (e.g., 90 days for inflationary economy), the alert noise is too high. If too long (730 days), outdated tarifas persist. Configurable per `empresa` (corporate policy) — sprint 5 may move the threshold there.
- Dedup strategy: only one open `alerta` per `(tipo_alerta, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa)`. Resolved alerts allow new alerts to be emitted if condition persists.

### 7.5 Use Case: `uc.tarifas.cloud-cross-branch-grid-reporting`

Admin cloud (con `permiso='ver_reportes_tarifas'`) genera un reporte cross-branch del grid tarifario actual para análisis de competitividad, auditoría DIAN, o decisión de pricing. Usa la query cross-branch: SELECTs `tarifas_sucursal` JOIN `sucursal` JOIN `tipos_vehiculo` JOIN `tipo_tarifa` WHERE `vigente_hasta IS NULL`. Devuelve una tabla pivot con todas las branches × tipos_vehiculo × tipos_tarifa y sus `valor` actuales. El admin puede exportar a CSV, comparar entre branches, identificar branches con tarifas desactualizadas. El flujo NO genera escrituras — es READ puro (no extiende la hash chain, pero SÍ se loguea si el admin exporta, como una `log_transaccional accion='reporte_exportado'`).

**Actor**: admin

**Pre-conditions**: at least one `tarifas_sucursal` row is vigente across branches; admin has reporting permissions; cloud has all branches' parametrization (via sync from branches' own writes, which are rare — branches don't write `tarifas_sucursal`, only cloud does).

**Steps**:
1. Admin opens `web_admin/Reportes/TarifasCrossBranch`, selects date range (defaults to "current vigentes"), optional filters (branch type, ciudad, tipo_vehiculo, tipo_tarifa).
2. Frontend GETs `api_admin /tarifas-sucursal/cross-branch?vigente_only=true&filters=...` (admin- JWT).
3. Backend validates `permisos_usuario` for `permiso='ver_reportes_tarifas'`.
4. Backend SELECTs `tarifas_sucursal ts JOIN sucursal s ON ts.uuid_sucursal=s.uuid JOIN tipos_vehiculo tv ON ts.uuid_tipo_vehiculo=tv.uuid JOIN tipo_tarifa tt ON ts.uuid_tipo_tarifa=tt.uuid WHERE ts.vigente_hasta IS NULL AND ts.estado='activo' AND (filters applied)`. Returns rows.
5. Backend returns `{rows: [{uuid_sucursal, sucursal_nombre, sucursal_ciudad, sucursal_uuid_tipo_sucursal, tipo_vehiculo_nombre, tipo_tarifa_nombre, valor, valor_plena, vigente_desde}], summary: {branches_count, avg_valor, min_valor, max_valor}}`.
6. Frontend renders the pivot table. Admin can sort by column, filter, search.
7. Admin clicks `Export CSV` → Frontend POSTs `api_admin /reportes/tarifas/export` with `{filters, format:'csv'}`.
8. Backend generates CSV, returns download URL. INSERT `log_transaccional` (`accion='reporte_exportado'`, `tabla_afectada='tarifas_sucursal'`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=NULL` (cloud scope), `datos_nuevos={filters, row_count, format:'csv', file_size_bytes}`).
9. Admin downloads CSV, analyzes in Excel/Python.
10. (No state mutation beyond the export log; no parametrization impact.)

**Tables touched (writes)**: `log_transaccional` (1 row on CSV export — the read itself is silent per SOLID I, but the export is a side-effect that warrants audit).
**Tables touched (reads)**: `tarifas_sucursal` (cross-branch vigente grid), `sucursal` (denormalized for display), `tipos_vehiculo` (catalog JOIN), `tipo_tarifa` (catalog JOIN), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin actor).
**FKs traversed**: `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`; `tarifas_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `tarifas_sucursal.uuid_tipo_tarifa` → `tipo_tarifa.uuid`; `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** for the read itself (per SOLID I). YES for the export action (1 row extends the chain).

**Integration with other tables**:
- Reads from: `tarifas_sucursal` (cross-branch vigente grid), `sucursal` (denormalized JOIN), `tipos_vehiculo`, `tipo_tarifa` (catalogs), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin).
- Writes to: `log_transaccional` (export audit, optional).
- Cross-cutting: this is the **reporting layer** for tarifas. The cross-branch view is essential for competitive analysis (compare your branches against each other) and DIAN audit (verify no branch has anomalous tariffs).
- Related: the report may surface "branches with no vigente tarifa" — these need attention. Admin can drill into `web_admin/SucursalDetail/{uuid}/TarifasTab` to create the missing tarifa.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 28, 31.

## 9. RED Tests
- (RED) F1 schema includes `tarifas_sucursal` with UNIQUE partial index on vigentes.
- (RED) F1 onboarding seed (per `uc.sucursal.admin-onboarding-pairing-flow`) inserts 12 placeholder rows (4 tipos_vehiculo × 3 tipo_tarifa).
- (RED) Admin POST `/tarifas-sucursal` with new valor → 201; old vigente row archived; new row vigente.
- (RED) Admin POST with overlap (vigente_desde before now but old vigente row not yet archived) → 409.
- (RED) Admin POST without `permiso='actualizar_tarifas'` → 403.
- (RED) Vigente lookup at ingreso preview: SELECT returns exactly 1 row for the (branch, tipo_vehiculo, tipo_tarifa) triple.
- (RED) Vigente lookup with no vigente row (admin forgot to create) → returns 0 rows; frontend shows banner.
- (RED) Factura creation: `factura_detalle.valor_unitario` equals `tarifas_sucursal.valor` at the moment of calculation (snapshot integrity).
- (RED) After admin PATCHes the tarifa (new version), historical `factura_detalle` rows still show the OLD `valor_unitario` (snapshot preserved).
- (RED) Expiry monitor: tarifa vigente for 365+ days with no replacement → emits `alerta tipo_alerta='tarifa_por_vencer'`.
- (RED) Expiry monitor: 372+ days without replacement → escalates to `tarifa_sin_reemplazo_critico`.
- (RED) Expiry monitor dedup: existing open alerta → no duplicate.
- (RED) Cross-branch report: SELECT returns all vigentes across all active branches; JOINs with catalog tables denormalize correctly.
- (RED) CSV export: triggers `log_transaccional accion='reporte_exportado'`.
- (RED) Cross-audience: branch operator JWT to `api_admin /tarifas-sucursal/cross-branch` → 401 (admin-only).
- (RED) ON DELETE RESTRICT: cannot delete `tipo_vehiculo` while `tarifas_sucursal` references it.

## 10. Implementation Tasks
- [x] F1.x Schema + UNIQUE partial index on vigentes.
- [x] F1.x Onboarding seed (12 placeholder rows per branch).
- [ ] IT-2.x: `api_admin /tarifas-sucursal` (POST, PATCH, GET list, GET detail, GET audit, GET cross-branch).
- [ ] IT-2.x: parametrization push on tarifa change.
- [ ] IT-2.x: `parkos_core/facturacion/tariff_resolver.py::vigente()` with caching.
- [ ] IT-2.x: `parkos_core/facturacion/cost_calculator.py::calcular()` uses resolver.
- [ ] IT-2.x: `workers/tarifas/expiry_monitor.py` (cron, daily 02:30 cloud).
- [ ] IT-2.x: `web_admin/TarifasForm`, `TarifasGrid` (cross-branch view), `Reportes/TarifasCrossBranch`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Admin forgets to create replacement before expiry | Med | `expiry_monitor` cron alerts 30/7 days before; admin dashboard flags |
| Tarifa change retroactive (backdated) | Low | Backdate allowed for corrections; `vigente_desde` set to past, old vigente row's `vigente_hasta` set to backdated moment; `log_transaccional` records the backdate |
| Snapshot drift in `factura_detalle` (valor_unitario doesn't match historical vigente) | Low | `cost_calculator` validates at write time: `valor_unitario == vigente.valor` (rejects otherwise) |
| Cross-branch report performance | Med | Indexed query on vigentes; materialized view if N grows large; sprint 5 may add `tarifas_grid_cache` table |
| Two admins race on tarifa update | Low | SELECT FOR UPDATE on the vigente row before UPDATE/INSERT; second admin's TX waits or fails with 409 |
| Currency / decimal precision | Low | All monetary fields use `decimal(10,2)`; arithmetic in DB; no client-side float math |

## 12. Open Questions
- (a) Backdating tarifa changes: should they be allowed? Currently yes for corrections; sprint 5 may add audit trail with `backdate_reason`.
- (b) Time-of-day variations (nocturnal tariff): future scope. Could be a `tarifas_horario` extension table.
- (c) Anticipated validity per `tipo_tarifa`: `por_hora` may need shorter review cycle (90 days) than `plena` B2B (730 days). Currently global default 365; sprint 5 may per-`tipo_tarifa`.
- (d) Tariff bundled with subscription (`tipo_subscripciones.valor` is the subscription fee, not per-stay): distinct from `tarifas_sucursal`. The `plena` mode is for B2B but not subscription — sprint 5 may formalize.
- (e) Auto-suggest tarifa updates based on market data: out of MVP; admin manually PATCHes.
- (f) Branch-override of corporate tarifa: not supported; all branches use the cloud-admin-set value. Per-branch override would require a `sucursal_id_override` field or a separate `tarifas_override` table.
