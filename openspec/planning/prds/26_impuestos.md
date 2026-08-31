# PRD: impuestos (T26)

> **SNAPSHOT SOURCE** — tax catalog (IVA, ICA, etc.). Every tax rate is COPIED into `factura_impuestos.porcentaje_aplicado` at the moment of facturacion. The catalog row can be versioned, expired, or deleted later; the snapshot row in `factura_impuestos` is IMMUTABLE. This is CRITICAL for DIAN compliance: a factura issued with IVA 19% must remain associated with the 19% even if the catalog changes to 20%.

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
- **Table name**: `prod.impuestos`
- **SQL name**: `impuestos` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seeded) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 5 use cases covering admin CRUD, version flow on rate change, snapshot into factura_impuestos, cloud DIAN process, and cross-branch tax revenue reporting)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `codigo` unique.

## 3. SOLID Atomic Breakdown
- **S**: "one tax definition".
- **O**: new column `vigente_desde`/`vigente_hasta` for tax rates over time.
- **I**: admin CRUD.
- **D**: `parkos_core/models/V/impuestos.py`.
- **Atomic**: INSERT, UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `factura_impuestos.uuid_impuesto` | `\|\|--o{` | snapshot per invoice |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Seed |
| UPDATE | YES (archive old) | Inside TX + `log_transaccional` |
| DELETE | NO | RESTRICT |

## 6. CodeGraph Dependencies
- `api_admin/routers/impuestos.py`.

## 7. Use Cases enabled by this table

The `impuestos` table is the **DIAN-critical snapshot source** for every tax applied to a business invoice. Unlike `tarifas_sucursal` (T14) where the snapshot is `factura_detalle.valor_unitario`, here the snapshot is `factura_impuestos.porcentaje_aplicado` — the EXACT percentage at the moment of facturacion. DIAN compliance demands that historical facturas reference the historical tax rate even if the catalog row is later versioned, expired, or deleted. Use cases below describe admin CRUD, version flow on rate change, snapshot into `factura_impuestos`, cloud DIAN process, and cross-branch tax revenue reporting. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.impuestos.admin-creates-new-tax-definition`

Cloud admin creates a new tax definition via `web_admin/Catalogos/ImpuestosForm`. Fills `codigo='IVA-19'` (unique), `nombre='IVA 19%'`, `porcentaje=19.00`, `tipo_calculo='porcentaje'`, `base_calculo='subtotal'`. Backend INSERTs the tax + `log_transaccional` + parametrization push to branches. New taxes take effect at the next facturacion (the vigente lookup at that moment returns the new row).

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='administrar_catalogos'`; the `codigo` is unique (DB constraint); for percentage-based taxes, `0 < porcentaje <= 100`; for fixed taxes, `porcentaje IS NULL` and the value goes elsewhere (sprint 5 — for MVP, only `tipo_calculo='porcentaje'` is supported).

**Steps**:
1. Admin opens `web_admin/Catalogos/Impuestos`, clicks `New`.
2. Frontend POSTs `api_admin /impuestos` (admin- JWT) with `{codigo='IVA-19', nombre='IVA 19%', porcentaje=19.00, tipo_calculo='porcentaje', base_calculo='subtotal', vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigentes: `SELECT * FROM impuestos WHERE vigente_hasta IS NULL`. Validates UNIQUE on `codigo` (rejects 409 if duplicate).
5. Backend validates business consistency: if `tipo_calculo='porcentaje'`, then `porcentaje IS NOT NULL AND 0 < porcentaje <= 100`. If `tipo_calculo='fijo'`, then `porcentaje IS NULL` (sprint 5 — `valor_fijo` column not in current schema, validate only `porcentaje IS NULL`).
6. Backend validates `base_calculo` is one of `'subtotal'` | `'subtotal_con_impuestos'` | `'total'` (enum check).
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
8. INSERT `impuestos` row (`uuid=server-generated`, `codigo`, `nombre`, `porcentaje`, `tipo_calculo`, `base_calculo`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
9. INSERT `log_transaccional` (`accion='impuesto_creado'`, `tabla_afectada='impuestos'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=null`, `datos_nuevos=$tax_snapshot`).
10. `queue_processor.enqueue('impuestos', $new_uuid, $snapshot)` → parametrization push for all active branches within 30s.
11. Backend returns `{new_uuid}`.
12. Branch receives parametrization; UPSERT new row. Next `FacturacionForm` at branch includes the new tax in the calculation.

**Tables touched (writes)**: `impuestos` (1 row), `log_transaccional` (1 row), `sync_queue` (1 parametrization item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `impuestos` (uniqueness check), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `impuestos` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `impuestos.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers the new tax to all branches within 30s.
- DIAN trigger: NO (tax creation doesn't dispatch DIAN; only `factura_electronica` creation does).
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `impuestos` (uniqueness), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `impuestos` (the new tax), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: the FK from `factura_impuestos.uuid_impuesto` to `impuestos.uuid` is the SNAPSHOT REFERENCE — it points to the tax DEFINITION (which is versioned), while the snapshot row carries the actual `porcentaje_aplicado` VALUE (which is immutable).
- Related: see T05 (`facturas`) and the snapshot use case 7.3 below.

### 7.2 Use Case: `uc.impuestos.admin-expires-old-creates-new-version-on-rate-change`

Cloud admin updates a tax rate — e.g., the government announces a new IVA rate (19% → 20%) effective on a future date. Admin creates a NEW version of the tax (`vigente_desde=$effective_date`, `vigente_hasta=NULL`) and EXPIRES the current version (`vigente_hasta=$effective_date`). Existing `factura_impuestos` rows still reference the OLD version and carry the OLD `porcentaje_aplicado` — historical facturas remain accurate. New facturaciones use the new version.

**Actor**: admin (cloud)

**Pre-conditions**: tax exists and is vigente; admin has `permiso='administrar_catalogos'`; the change is a rate update (codigo stays the same); historical `factura_impuestos` rows exist referencing the current version.

**Steps**:
1. Admin opens `web_admin/Catalogos/Impuestos/{uuid}`, edits `porcentaje` from 19.00 to 20.00. Sets `vigente_desde=$effective_date` (e.g., next month).
2. Frontend PATCHes `api_admin /impuestos/{uuid}` with `{porcentaje=20.00, vigente_desde=$effective_date}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigente tax with `SELECT FOR UPDATE` (serializes concurrent admin edits).
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. UPDATE current vigente row SET `vigente_hasta=$effective_date` (archive old version with `porcentaje=19.00`).
7. INSERT new `impuestos` row (`uuid=server-generated`, same `codigo='IVA-19'`, `porcentaje=20.00`, `vigente_desde=$effective_date`, `vigente_hasta=NULL`, `estado='activo'`). The UNIQUE on `codigo` is NOT enforced across versions (only vigentes have UNIQUE — but the new version starts at a future date, so the old version is still vigente until $effective_date).
8. INSERT `log_transaccional` (`accion='impuesto_actualizado'`, `tabla_afectada='impuestos'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores={porcentaje: 19.00, vigente_desde: $old_vigente}`, `datos_nuevos={porcentaje: 20.00, vigente_desde: $new_vigente}`). The audit row preserves old vs new for probatory integrity.
9. `queue_processor.enqueue('impuestos', $new_uuid, $new_snapshot)` → parametrization push.
10. Also enqueue the archived row.
11. Backend returns `{new_uuid, old_uuid_archived, effective_date}`.
12. Branch receives parametrization; UPSERT new row, UPDATE local old row with `vigente_hasta=$effective_date`.
13. **Historical `factura_impuestos` rows are UNAFFECTED**: they still FK to the OLD version's UUID and carry `porcentaje_aplicado=19.00`. This is the canonical snapshot semantics — DIAN compliance preserved.
14. **New facturaciones** (use case 7.3) use the vigente tax at the moment of calculation: before $effective_date → 19%; on/after → 20%.
15. Admin UI shows: "IVA updated from 19% to 20% effective $effective_date. Existing invoices retain 19%."

**Tables touched (writes)**: `impuestos` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `impuestos` (current vigente + FOR UPDATE), `factura_impuestos` (count of existing snapshots — informational), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `impuestos` has NO outgoing FKs. `factura_impuestos.uuid_impuesto` → `impuestos.uuid` (REFERENCES the version vigente at facturacion time, NOT a live "current tax" lookup). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `impuestos.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `impuestos` (current state), `factura_impuestos` (existing snapshots), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `impuestos` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the canonical **tax rate evolution** pattern. The snapshot semantic (`factura_impuestos.porcentaje_aplicado` is the value, `uuid_impuesto` is the reference) preserves DIAN compliance across rate changes. The FK from `factura_impuestos.uuid_impuesto` to a SPECIFIC version (not a "current tax" lookup) is the key insight.
- Related: see T05 (`facturas`) for the snapshot semantic — `factura_impuestos` rows are inserted with `porcentaje_aplicado=impuestos.porcentaje` at the moment of facturacion. This is the same pattern as `factura_detalle.valor_unitario` (T14 use case 7.3) and `factura_otros_cobros.valor_aplicado` (T27 use case 7.3).

### 7.3 Use Case: `uc.impuestos.branch-snapshots-on-facturacion-moment`

Casual customer departs. Operator opens `FacturacionForm` at branch. Backend computes the cost (T14 use case 7.3), then applies EACH vigente `impuestos` row: for each tax, INSERT `factura_impuestos` with `porcentaje_aplicado=impuestos.porcentaje` (the **SNAPSHOT** value) and `base_calculo`, `valor` (computed). The snapshot value is captured at this moment — if admin later changes the tax rate (use case 7.2), this snapshot remains 19% (or whatever was vigente at facturacion).

**Actor**: operator (branch)

**Pre-conditions**: branch has parametrized vigentes `impuestos` (use cases 7.1/7.2); ingreso and salidas exist for the vehicle; `tarifas_sucursal` vigente exists for the (sucursal, tipo_vehiculo, tipo_tarifa) triple.

**Steps**:
1. Customer departs. Operator opens `SalidaForm`, types plate, system finds the ingreso.
2. Operator opens `FacturacionForm`. Backend reads `tarifas_sucursal` vigente, computes `subtotal = (duracion_segundos / 3600) * valor` (or the appropriate mode calculation).
3. Backend SELECTs ALL vigentes `impuestos` rows: `SELECT * FROM impuestos WHERE vigente_hasta IS NULL AND estado='activo'`. For MVP: typically just `IVA-19`. May include `ICA`, `ImpuestoConsumo` etc. as the catalog grows.
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
5. INSERT `facturas` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$ingreso_uuid`, `uuid_salida=$salida_uuid`, `subtotal=$subtotal_calculated`, `descuento=0`, `total=$subtotal + taxes`, `estado='activa'` derived).
6. INSERT `factura_detalle` snapshot (T14 use case 7.3 — the tarifa value).
7. INSERT `factura_pagos` rows (one per payment method).
8. **SNAPSHOT — INSERT `factura_impuestos` for EACH vigente tax**:
   - For each `impuestos` row with `vigente_hasta IS NULL`:
     - Compute `valor_impuesto = subtotal * (porcentaje / 100)` if `base_calculo='subtotal'`; `valor_impuesto = (subtotal + previous_taxes) * (porcentaje / 100)` if `base_calculo='subtotal_con_impuestos'`.
     - INSERT `factura_impuestos` (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_factura=$factura_uuid`, `uuid_impuesto=$tax.uuid`, `base_calculo=$subtotal_base`, `porcentaje_aplicado=$tax.porcentaje` ← **SNAPSHOT VALUE**, `valor=$valor_impuesto`, `fecha_retencion_hasta=$created_at + 5_years`).
9. INSERT `factura_otros_cobros` (snapshot from `otros_cobros`, T27 use case 7.3).
10. INSERT `log_transaccional` (`accion='factura_creada'`, `tabla_afectada='facturas'`, `uuid_registro_afectado=$factura_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={total, taxes_count: $N, impuestos_snapshot: [{codigo, porcentaje_aplicado, valor}, ...]}`).
11. `queue_processor.enqueue('facturas', $uuid, $snapshot)` + enqueue all children.
12. Continue to cloud `/facturas/procesar` (online) or fallback to offline.
13. After this point: even if admin PATCHes `impuestos` (use case 7.2) with a new rate, the `factura_impuestos.porcentaje_aplicado` is immutable. DIAN audit sees exactly what was vigente at facturacion moment.

**Tables touched (writes)**: `facturas` (1 row), `factura_detalle` (snapshot from `tarifas_sucursal`), `factura_pagos` (1+ rows), `factura_impuestos` (1 row per vigente tax — the SNAPSHOT), `factura_otros_cobros` (snapshot from `otros_cobros`), `log_transaccional` (1 row), `sync_queue` (1+ items).
**Tables touched (reads)**: `tarifas_sucursal` (vigente for subtotal), `impuestos` (vigente for snapshot), `otros_cobros` (vigente for snapshot), `ingreso` (cycle origin), `salidas` (cycle end), `clientes` (titular), `log_transaccional` (chain anchor), `sucursal` (tenant).
**FKs traversed**: `factura_impuestos.uuid_impuesto` → `impuestos.uuid` (the FK to the SPECIFIC version vigente at facturacion); `factura_impuestos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_sucursal` → `sucursal.uuid`. `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `facturas.uuid`.
**Sync behavior**:
- Branch → cloud: YES — `facturas` + all children + `log_transaccional` push via `sync_queue` within 30s.
- Cloud → branch: YES — `SyncBackEvent` flows back with the `factura_electronica.numero_oficial`.
- DIAN trigger: YES — `dian_dispatcher` enqueues after cloud receives the factura (cloud creates `factura_electronica`).
- Hash chain impact: YES — branch chain extends by 1 row (the `factura_creada` audit); cloud chain extends by 2 rows (consecutivo_asignado + factura_electronica_creada).
**Integration**:
- Reads from: `tarifas_sucursal` (vigente), `impuestos` (vigente for SNAPSHOT), `otros_cobros` (vigente for snapshot), `ingreso`, `salidas`, `clientes`, `log_transaccional`, `sucursal`.
- Writes to: `facturas`, `factura_detalle` (snapshot), `factura_pagos`, `factura_impuestos` (SNAPSHOT — `porcentaje_aplicado` is the value at this moment), `factura_otros_cobros` (snapshot), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **canonical snapshot semantic** for taxes. The `factura_impuestos` row carries TWO fields that together preserve the snapshot: `uuid_impuesto` (FK to the version vigente at facturacion) AND `porcentaje_aplicado` (the actual value at that moment). Even if `impuestos` is later versioned/expired/deleted, the snapshot is immutable.
- Related: see T05 (`facturas`) for the parent flow; T14 use case 7.3 for the parallel `tarifas_sucursal` snapshot in `factura_detalle`; T27 use case 7.3 for the `otros_cobros` snapshot in `factura_otros_cobros`.

### 7.4 Use Case: `uc.impuestos.cloud-dian-process-uses-existing-snapshot`

Cloud receives the `facturas` row (from use case 7.3) via online `/facturas/procesar` or async sync. The `factura_impuestos` snapshots are ALREADY in the business row (created by branch at facturacion moment). Cloud does NOT recompute taxes — it uses the snapshot values as-is. Cloud creates `factura_electronica` with `descuento=$factura.descuento`, but the `factura_impuestos` rows travel as children of the `facturas` row (no recomputation). This is the canonical "snapshot is the source of truth for DIAN" pattern.

**Actor**: dian_dispatcher (cloud worker)

**Pre-conditions**: branch has created `facturas` + `factura_impuestos` snapshots (use case 7.3); cloud has received via sync; `empresa` is seeded with valid range; `consecutivo_actual < rango_hasta`.

**Steps**:
1. Cloud handler opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
2. `SELECT empresa FOR UPDATE`; atomic increment (T21 use case 7.2). Compute `consecutivo_new = consecutivo_actual + 1`. UPDATE.
3. INSERT `factura_electronica` (`uuid`, `uuid_sucursal=$branch`, `uuid_factura=$factura_uuid`, `uuid_cliente=$cliente_uuid OR consumidor_final`, `reportado_dian=false`, `descuento=$factura.descuento`, `consecutivo=$consecutivo_new`, `estado='activa'`, `fecha_retencion_hasta=$created_at + 5_years`).
4. **The `factura_impuestos` rows already exist** (snapshot from branch, use case 7.3). Cloud INSERTs them verbatim into its own DB (idempotent on UUID). NO recomputation.
5. INSERT `log_transaccional` (`accion='factura_electronica_creada'`, `tabla_afectada='factura_electronica'`, `uuid_registro_afectado=$uuid_e`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `uuid_referencia=$factura_uuid`, `datos_nuevos={consecutivo, total_impuestos: $sum_of_factura_impuestos}`).
6. Enqueue `dian_dispatcher` to send to DIAN provider. DIAN provider receives the e-factura with the snapshotted taxes and accepts (the snapshot is canonical).
7. INSERT `SyncBackEvent` (concepto sprint 5; payload includes the `numero_oficial`).
8. Return `{uuid_factura_electronica, numero_oficial, consecutivo}`.

**Tables touched (writes)**: `empresa` (atomic UPDATE), `factura_electronica` (1 row), `log_transaccional` (1 row), `SyncBackEvent` (concept), `dian_dispatcher` queue. **The `factura_impuestos` rows are NOT re-INSERTed on cloud** — they're received via sync and stored verbatim (idempotent).
**Tables touched (reads)**: `facturas` (received with children), `factura_impuestos` (received as children — the snapshot), `clientes` (titular or consumidor_final), `empresa` (atomic lock), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`; `factura_electronica.uuid_sucursal` → `sucursal.uuid`. `factura_impuestos.uuid_impuesto` → `impuestos.uuid` (received snapshot — the version vigente at branch facturacion); `factura_impuestos.uuid_factura` → `facturas.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `factura_electronica.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`.
**Sync behavior**:
- Branch → cloud: YES (the `facturas` + `factura_impuestos` snapshots arrive together).
- Cloud → branch: YES — `SyncBackEvent` flows back.
- DIAN trigger: YES — `dian_dispatcher` sends to DIAN.
- Hash chain impact: YES — branch chain extends by 1 row (the `factura_creada` audit, already happened in use case 7.3); cloud chain extends by 1 row on receipt + 1 row on `factura_electronica_creada`.
**Integration**:
- Reads from: `facturas` (received), `factura_impuestos` (received as snapshot), `clientes`, `empresa` (atomic), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `empresa` (atomic UPDATE), `factura_electronica`, `log_transaccional`, `SyncBackEvent`, `dian_dispatcher` queue.
- Cross-cutting: the cloud-side `factura_impuestos` rows are an EXACT COPY of the branch-side rows (same UUIDs, same `porcentaje_aplicado`). The snapshot is the single source of truth across both sides.
- Related: see T05 (`facturas`) for the parent flow; T02 (`revocacion_factura`) for what happens if DIAN rejects (the e-factura is revoked, the snapshot rows are preserved as historical evidence).

### 7.5 Use Case: `uc.impuestos.cloud-cross-branch-tax-revenue-report`

Cloud admin (with `permiso='ver_reportes_impuestos'`) generates a cross-branch tax revenue report. Query aggregates `factura_impuestos.valor` grouped by `impuestos.codigo`, `factura_impuestos.porcentaje_aplicado`, `sucursal.nombre`. The query joins cloud's `factura_impuestos` (which mirrors all branches' snapshots) with `impuestos` (catalog) and `sucursal` (branches). The report shows tax revenue broken down by tax type, percentage applied (which may differ across rate changes), and branch.

**Actor**: admin (cloud)

**Pre-conditions**: cloud has received `factura_impuestos` rows from all branches (via sync); admin has `permiso='ver_reportes_impuestos'`; at least one `factura_impuestos` row exists.

**Steps**:
1. Admin opens `web_admin/Reportes/ImpuestosRecaudados`, selects date range (e.g., Q1 2026), optional filters (branch, tax code, percentage).
2. Frontend GETs `api_admin /impuestos/reporte-recaudo?fecha_desde=...&fecha_hasta=...&filters=...`.
3. Backend validates `permisos_usuario` for `permiso='ver_reportes_impuestos'`; rejects 403 if missing.
4. Backend SELECTs:
   ```sql
   SELECT
     i.codigo,
     fi.porcentaje_aplicado,
     s.nombre AS sucursal,
     COUNT(*) AS facturas_count,
     SUM(fi.base_calculo) AS base_total,
     SUM(fi.valor) AS valor_total
   FROM factura_impuestos fi
   JOIN impuestos i ON fi.uuid_impuesto = i.uuid
   JOIN facturas f ON fi.uuid_factura = f.uuid
   JOIN sucursal s ON fi.uuid_sucursal = s.uuid
   WHERE fi.created_at BETWEEN $fecha_desde AND $fecha_hasta
     AND (filters applied)
   GROUP BY i.codigo, fi.porcentaje_aplicado, s.nombre
   ORDER BY i.codigo, fi.porcentaje_aplicado, s.nombre;
   ```
5. Backend returns rows + summary `{total_recaudo, by_codigo: [...], by_branch: [...]}`.
6. Frontend renders pivot table. Admin can drill into specific rows.
7. Admin clicks `Export CSV` → Backend INSERTs `log_transaccional` (`accion='reporte_impuestos_exportado'`, `tabla_afectada='factura_impuestos'`, `uuid_registro_afectado=NULL`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=NULL` (cloud scope), `datos_nuevos={filters, row_count, format:'csv', file_size_bytes}`). The export is a side-effect that warrants audit.
8. Admin downloads CSV, analyzes in Excel/Python.

**Tables touched (writes)**: `log_transaccional` (1 row on CSV export — the read itself is silent per SOLID I, but the export is a side-effect that warrants audit).
**Tables touched (reads)**: `factura_impuestos` (aggregate), `impuestos` (catalog JOIN), `facturas` (FK), `sucursal` (denormalized for display), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `factura_impuestos.uuid_impuesto` → `impuestos.uuid`; `factura_impuestos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_sucursal` → `sucursal.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`.
**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** for the read itself (per SOLID I). YES for the export action (1 row extends the cloud chain).
**Integration**:
- Reads from: `factura_impuestos` (the snapshots — this is the value-add over a live `impuestos` join: the snapshot preserves historical `porcentaje_aplicado` even after rate changes), `impuestos` (catalog for display), `facturas` (FK), `sucursal` (denormalized), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin).
- Writes to: `log_transaccional` (export audit, optional).
- Cross-cutting: this report is the **canonical tax compliance report** for DIAN. The `porcentaje_aplicado` in the GROUP BY is the snapshot value — distinct rows for the same `codigo` at different rates. This is how DIAN sees the historical tax revenue per rate change.
- Related: see T05 (`facturas`) for the parent flow; T27 use case 7.4 for the parallel `otros_cobros` cross-branch report.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 29, 31.

## 9. RED Tests
- (RED) `codigo` unique.
- (RED) Snapshot takes percentage at facturacion time, not later.

## 10. Implementation Tasks
- [x] F1.x Seed (IVA 19%).
- [ ] IT-2.x: admin CRUD.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Tax rate change | Low | Snapshot at facturacion time protects history |

## 12. Open Questions
- (a) Multiple IVA rates (5%, 19%)?