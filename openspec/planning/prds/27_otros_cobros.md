# PRD: otros_cobros (T27)

> **SNAPSHOT SOURCE** — additional charges catalog (tarifa nocturna, cargo por evento, etc.). NOT taxes (those are T26), but charges that augment the factura. Every charge's `costo` is COPIED into `factura_otros_cobros.valor_aplicado` at the moment of facturacion. The catalog row can be versioned, expired, or deleted later; the snapshot row is IMMUTABLE.

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
- **Table name**: `prod.otros_cobros`
- **SQL name**: `otros_cobros` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seeded) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 4 use cases covering admin CRUD, version flow, snapshot into factura_otros_cobros, and cross-branch report)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `nombre` unique.

## 3. SOLID Atomic Breakdown
- **S**: "one other charge definition".
- **O**: new columns via migration.
- **I**: admin CRUD.
- **D**: `parkos_core/models/V/otros_cobros.py`.
- **Atomic**: INSERT, UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `factura_otros_cobros.uuid_otro_cobro` | `\|\|--o{` | snapshot per invoice |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Seed |
| UPDATE | YES (archive old) | Inside TX + `log_transaccional` |
| DELETE | NO | RESTRICT |

## 6. CodeGraph Dependencies
- `api_admin/routers/otros-cobros.py`.

## 7. Use Cases enabled by this table

The `otros_cobros` table is the **catalog of additional charges** (e.g., `tarifa_nocturna` for nighttime fee, `cargo_por_evento` for special events, `seguro_danios` for damage insurance). These are NOT taxes (T26); they're charges that augment the factura. Like `impuestos` and `tarifas_sucursal`, every charge's `costo` is COPIED into `factura_otros_cobros.valor_aplicado` at the moment of facturacion — the catalog row can change later; the snapshot row is immutable. Use cases below describe admin CRUD, version flow on cost change, snapshot into `factura_otros_cobros`, and cross-branch report. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.otros-cobros.admin-crud-create-or-version`

Cloud admin manages the `otros_cobros` catalog. New charges are added as the business evolves — e.g., adding `seguro_danios` for damage insurance or `recargo_finde` for weekend surcharge. Updates create a new `[V]` version (archive old with `vigente_hasta=NOW()`, INSERT new). Parametrization push delivers the new version to all branches.

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='administrar_catalogos'`; the `nombre` is unique (DB constraint); the `tipo_calculo` is one of `'fijo'` | `'porcentaje'`; `costo > 0`.

**Steps**:
1. Admin opens `web_admin/Catalogos/OtrosCobros`, clicks `New`.
2. Frontend POSTs `api_admin /otros-cobros` with `{nombre='seguro_danios', costo=2000, tipo_calculo='fijo', base_calculo='ninguna', vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigentes: `SELECT * FROM otros_cobros WHERE vigente_hasta IS NULL`. Validates UNIQUE on `nombre` (rejects 409 if duplicate).
5. Backend validates business consistency: `tipo_calculo` ∈ {`'fijo'`, `'porcentaje'`}; `costo > 0`; `base_calculo` ∈ {`'subtotal'`, `'subtotal_con_impuestos'`, `'ninguna'`} (where `'ninguna'` means the charge is fixed regardless of base).
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
7. INSERT `otros_cobros` row (`uuid=server-generated`, `nombre`, `costo`, `tipo_calculo`, `base_calculo`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='otro_cobro_creado'`, `tabla_afectada='otros_cobros'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=null`, `datos_nuevos=$charge_snapshot`).
9. `queue_processor.enqueue('otros_cobros', $new_uuid, $snapshot)` → parametrization push.
10. Backend returns `{new_uuid}`.
11. Branch receives parametrization; UPSERT new row. New charge appears in `FacturacionForm`'s additional charges list (operator may toggle per-factura).

**Tables touched (writes)**: `otros_cobros` (1 row), `log_transaccional` (1 row), `sync_queue` (1 parametrization item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `otros_cobros` (uniqueness), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `otros_cobros` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `otros_cobros.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers the new charge to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `otros_cobros` (uniqueness), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `otros_cobros` (the new charge), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: the FK from `factura_otros_cobros.uuid_otro_cobro` to `otros_cobros.uuid` is the SNAPSHOT REFERENCE — it points to the charge DEFINITION (which is versioned), while the snapshot row carries `valor_aplicado` (the value at facturacion moment).
- Related: see T05 (`facturas`) and the snapshot use case 7.3 below.

### 7.2 Use Case: `uc.otros-cobros.admin-versioning-on-cost-change`

Cloud admin updates a charge's `costo` — e.g., `seguro_danios` from $2000 to $2500 effective next month. Admin creates a NEW version (`vigente_desde=$effective_date`, `vigente_hasta=NULL`) and EXPIRES the current version (`vigente_hasta=$effective_date`). Existing `factura_otros_cobros` rows still reference the OLD version and carry the OLD `valor_aplicado=$2000` — historical facturas remain accurate.

**Actor**: admin (cloud)

**Pre-conditions**: charge exists and is vigente; admin has `permiso='administrar_catalogos'`; the change is a cost update (nombre stays the same); historical `factura_otros_cobros` rows exist referencing the current version.

**Steps**:
1. Admin opens `web_admin/Catalogos/OtrosCobros/{uuid}`, edits `costo` from 2000 to 2500. Sets `vigente_desde=$effective_date`.
2. Frontend PATCHes `api_admin /otros-cobros/{uuid}` with `{costo=2500, vigente_desde=$effective_date}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigente charge with `SELECT FOR UPDATE`.
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. UPDATE current vigente row SET `vigente_hasta=$effective_date` (archive old version with `costo=2000`).
7. INSERT new `otros_cobros` row (`uuid=server-generated`, same `nombre='seguro_danios'`, `costo=2500`, `vigente_desde=$effective_date`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='otro_cobro_actualizado'`, `tabla_afectada='otros_cobros'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores={costo: 2000, vigente_desde: $old_vigente}`, `datos_nuevos={costo: 2500, vigente_desde: $new_vigente}`).
9. `queue_processor.enqueue('otros_cobros', $new_uuid, $new_snapshot)` → parametrization push.
10. Also enqueue the archived row.
11. Backend returns `{new_uuid, old_uuid_archived, effective_date}`.
12. Branch receives parametrization; UPSERT new row, UPDATE local old row.
13. **Historical `factura_otros_cobros` rows are UNAFFECTED**: they still FK to the OLD version's UUID and carry `valor_aplicado=2000`.
14. **New facturaciones** (use case 7.3) use the vigente charge at the moment of calculation: before $effective_date → 2000; on/after → 2500.

**Tables touched (writes)**: `otros_cobros` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `otros_cobros` (current state), `factura_otros_cobros` (count of existing snapshots — informational), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `otros_cobros` has NO outgoing FKs. `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid` (REFERENCES the version vigente at facturacion). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `otros_cobros.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `otros_cobros` (current state), `factura_otros_cobros` (existing snapshots), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `otros_cobros` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the same canonical versioning pattern as T26 use case 7.2 (impuestos) and T14 (tarifas_sucursal). The snapshot semantic (`factura_otros_cobros.valor_aplicado` is the value, `uuid_otro_cobro` is the reference) preserves historical accuracy across cost changes.
- Related: see T05 (`facturas`) for the parent flow.

### 7.3 Use Case: `uc.otros-cobros.branch-snapshots-on-facturacion-moment`

Casual customer departs at night (21:00). Operator opens `FacturacionForm` at branch. Backend computes the cost (T14 use case 7.3 + T26 use case 7.3 — tarifa + taxes), then applies EACH vigente `otros_cobros` row that matches the scenario (e.g., `tarifa_nocturna` if `fecha_salida - fecha_ingreso` spans the nighttime window 20:00-06:00). For each matching charge, INSERT `factura_otros_cobros` with `valor_aplicado=otros_cobros.costo` (the **SNAPSHOT** value) and `base_calculo`, `valor` (computed).

**Actor**: operator (branch)

**Pre-conditions**: branch has parametrized vigentes `otros_cobros` (use cases 7.1/7.2); `tarifas_sucursal` and `impuestos` snapshots already computed (T14, T26); business rules for when each charge applies are configured (sprint 5 — for MVP, all vigentes are applied automatically).

**Steps**:
1. Customer departs. Operator opens `SalidaForm`, types plate, system finds the ingreso.
2. Operator opens `FacturacionForm`. Backend computes subtotal (T14), taxes (T26).
3. Backend SELECTs vigentes `otros_cobros` rows. For MVP: all vigentes are applied. Sprint 5: business rules (e.g., `tarifa_nocturna` only if stay spans nighttime).
4. Backend opens TX; SELECT chain anchor from `log_transaccional`.
5. INSERT `facturas` row (`subtotal`, `descuento`, `total=$subtotal + $taxes + $other_charges`).
6. INSERT `factura_detalle` snapshot (tarifa).
7. INSERT `factura_pagos` rows.
8. INSERT `factura_impuestos` snapshots (T26 use case 7.3).
9. **SNAPSHOT — INSERT `factura_otros_cobros` for EACH matching charge**:
   - For each applicable `otros_cobros` row:
     - Compute `valor = otros_cobros.costo` if `tipo_calculo='fijo'`; `valor = base_calculo * (otros_cobros.costo / 100)` if `tipo_calculo='porcentaje'`.
     - INSERT `factura_otros_cobros` (`uuid`, `uuid_sucursal=$branch`, `uuid_factura=$factura_uuid`, `uuid_otro_cobro=$charge.uuid`, `base_calculo`, `valor_aplicado=$charge.costo` ← **SNAPSHOT VALUE**, `valor=$computed_valor`, `fecha_retencion_hasta=$created_at + 5_years`).
10. INSERT `log_transaccional` (`accion='factura_creada'`, `tabla_afectada='facturas'`, `uuid_registro_afectado=$factura_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={total, otros_cobros_snapshot: [{nombre, valor_aplicado, valor}, ...]}`).
11. `queue_processor.enqueue('facturas', $uuid, $snapshot)` + children.
12. Continue to cloud `/facturas/procesar` (online) or offline.

**Tables touched (writes)**: `facturas` (1 row), `factura_detalle` (snapshot from `tarifas_sucursal`), `factura_pagos`, `factura_impuestos` (snapshot), `factura_otros_cobros` (1 row per applicable charge — the SNAPSHOT), `log_transaccional` (1 row), `sync_queue` (1+ items).
**Tables touched (reads)**: `tarifas_sucursal` (vigente), `impuestos` (vigente for snapshot), `otros_cobros` (vigente for SNAPSHOT), `ingreso`, `salidas`, `clientes`, `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid` (FK to SPECIFIC version); `factura_otros_cobros.uuid_factura` → `facturas.uuid`; `factura_otros_cobros.uuid_sucursal` → `sucursal.uuid`. `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `facturas.uuid`.
**Sync behavior**:
- Branch → cloud: YES — `facturas` + all children + `log_transaccional` push via `sync_queue` within 30s.
- Cloud → branch: YES — `SyncBackEvent` flows back with `factura_electronica.numero_oficial`.
- DIAN trigger: YES (cloud creates `factura_electronica` and dispatches).
- Hash chain impact: YES — branch chain extends by 1 row (factura_creada); cloud chain extends by 2 rows (consecutivo_asignado + factura_electronica_creada).
**Integration**:
- Reads from: `tarifas_sucursal` (vigente), `impuestos` (vigente for snapshot), `otros_cobros` (vigente for SNAPSHOT), `ingreso`, `salidas`, `clientes`, `log_transaccional`, `sucursal`.
- Writes to: `facturas`, `factura_detalle` (snapshot), `factura_pagos`, `factura_impuestos` (snapshot), `factura_otros_cobros` (SNAPSHOT — `valor_aplicado` is the value at this moment), `log_transaccional`, `sync_queue`.
- Cross-cutting: same canonical snapshot semantic as T26 use case 7.3 (impuestos) and T14 use case 7.3 (tarifas_sucursal). The `factura_otros_cobros` row carries TWO fields: `uuid_otro_cobro` (FK to version) AND `valor_aplicado` (snapshot value). Both are needed for probatory integrity.
- Related: see T05 (`facturas`) for the parent flow; T26 use case 7.3 for the parallel `impuestos` snapshot in `factura_impuestos`.

### 7.4 Use Case: `uc.otros-cobros.cloud-cross-branch-other-charges-report`

Cloud admin generates a cross-branch report of additional charges collected. Query aggregates `factura_otros_cobros.valor` grouped by `otros_cobros.nombre`, `factura_otros_cobros.valor_aplicado`, `sucursal.nombre`. The query joins cloud's `factura_otros_cobros` (which mirrors all branches' snapshots) with `otros_cobros` (catalog) and `sucursal` (branches).

**Actor**: admin (cloud)

**Pre-conditions**: cloud has received `factura_otros_cobros` rows from all branches; admin has `permiso='ver_reportes_otros_cobros'`; at least one `factura_otros_cobros` row exists.

**Steps**:
1. Admin opens `web_admin/Reportes/OtrosCobrosRecaudados`, selects date range, filters.
2. Frontend GETs `api_admin /otros-cobros/reporte-recaudo?fecha_desde=...&fecha_hasta=...&filters=...`.
3. Backend validates `permisos_usuario`.
4. Backend SELECTs:
   ```sql
   SELECT
     oc.nombre,
     foc.valor_aplicado,
     s.nombre AS sucursal,
     COUNT(*) AS facturas_count,
     SUM(foc.valor) AS valor_total
   FROM factura_otros_cobros foc
   JOIN otros_cobros oc ON foc.uuid_otro_cobro = oc.uuid
   JOIN facturas f ON foc.uuid_factura = f.uuid
   JOIN sucursal s ON foc.uuid_sucursal = s.uuid
   WHERE foc.created_at BETWEEN $fecha_desde AND $fecha_hasta
   GROUP BY oc.nombre, foc.valor_aplicado, s.nombre
   ORDER BY oc.nombre, foc.valor_aplicado, s.nombre;
   ```
5. Backend returns rows + summary `{total_recaudo, by_cargo: [...], by_branch: [...]}`.
6. Frontend renders pivot table.
7. Admin clicks `Export CSV` → Backend INSERTs `log_transaccional` (`accion='reporte_otros_cobros_exportado'`, ...). The export is a side-effect that warrants audit.
8. Admin downloads CSV.

**Tables touched (writes)**: `log_transaccional` (1 row on CSV export).
**Tables touched (reads)**: `factura_otros_cobros` (aggregate), `otros_cobros` (catalog JOIN), `facturas` (FK), `sucursal` (denormalized), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid`; `factura_otros_cobros.uuid_factura` → `facturas.uuid`; `factura_otros_cobros.uuid_sucursal` → `sucursal.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`.
**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: **NO** for the read itself. YES for the export action (1 row extends the cloud chain).
**Integration**:
- Reads from: `factura_otros_cobros` (the snapshots), `otros_cobros` (catalog), `facturas`, `sucursal`, `permisos_usuario`, `log_transaccional`, `usuarios`.
- Writes to: `log_transaccional` (export audit, optional).
- Cross-cutting: this is the cross-branch revenue report for additional charges (excluding taxes — those are T26 use case 7.5). The `valor_aplicado` in the GROUP BY preserves historical rate distinct rows.
- Related: see T05 (`facturas`) for the parent flow; T26 use case 7.5 for the parallel `impuestos` cross-branch report.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 29, 31.

## 9. RED Tests
- (RED) `nombre` unique.
- (RED) Snapshot takes values at facturacion time.

## 10. Implementation Tasks
- [x] F1.x Seed.
- [ ] IT-2.x: admin CRUD.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Cost change | Low | Snapshot at facturacion time protects history |

## 12. Open Questions
- (a) Time-based charges (weekend, holiday)?