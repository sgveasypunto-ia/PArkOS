# PRD: factura_otros_cobros (T44)

> `[A]` append-only snapshot of each `otros_cobros` row applied to a `facturas` row at the moment of facturacion. `valor_aplicado` is the historical cost — NOT a live FK cascade. Even if `otros_cobros.costo` is updated AFTER the factura was created, `factura_otros_cobros.valor_aplicado` remains the historical value. Same pattern as T37 (`factura_impuestos`) but for non-tax charges (tarifa nocturna, cargo por evento, etc.). DIAN retention 5+ years. Tabla candidata a hash-chaining si DIAN exige cadena de integridad sobre totales.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule S: snapshot is the audit point for non-tax charges*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[A]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.factura_otros_cobros`
- **SQL name**: `factura_otros_cobros` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN compliance — non-tax charges are part of the invoice total)
- **Hash chain**: CANDIDATE — per AGENTS.md "Tabla candidata a hash-chaining si DIAN exige cadena de integridad sobre totales". Not implemented in MVP; sprint 5+ may add `hash_anterior`/`hash_actual` if DIAN requires chain integrity over charge totals.
- **Partitioning**: partitionable by month on `created_at`
- **Origin**: F1 (schema + REVOKE + trigger) + IT-4 (writes per facturacion)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 4 use cases covering the snapshot semantic, same pattern as T37 `factura_impuestos`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_sucursal` is denormalized for partition pruning + RLS-style filtering.
- Travel: branch-origin rows travel to cloud via `sync_queue`. Cloud receives and INSERTs verbatim. DIAN cloud-side replica uses snapshot values directly.
- **Snapshot semantic**: `valor_aplicado` is the COPY of `otros_cobros.costo` at the moment of facturacion. NOT a live FK cascade. The `base_calculo` and `valor` are also snapshots (the computed charge base and final charge amount).
- **NO FK cascade on `uuid_otro_cobro`**: the FK IS present (`uuid_otro_cobro` → `otros_cobros.uuid`), but only for traceability — NOT for value cascade. The `valor_aplicado` is independent of the current `otros_cobros.costo`.

## 3. SOLID Atomic Breakdown
- **S**: "one non-tax charge application record at a moment in time" — INSERT in same TX as the parent `facturas` row.
- **O**: extensible via migration; new columns (`observaciones`, `uuid_otro_cobro_version`) added as audit requirements grow.
- **I**: branch operator API (writer — part of facturacion flow); admin read API (FacturaDetail); DIAN provider (cloud-side, reads snapshot values).
- **D**: `parkos_core/facturacion/otros_cobros_writer.py::write_otro_cobro(uuid_factura, uuid_sucursal, uuid_otro_cobro, base_calculo, valor_aplicado)` — the ONLY writer. Caller passes the vigente `otros_cobros.costo` as `valor_aplicado` (snapshot).
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, charge history dies |
| `uuid_factura` | `prod.facturas.uuid` | exactly one (NOT NULL) | CASCADE | if factura deleted (never), charge rows die |
| `uuid_otro_cobro` | `prod.otros_cobros.uuid` | exactly one (NOT NULL) | RESTRICT | FK is for traceability ONLY — no cascade. RESTRICT prevents deletion of `otros_cobros` rows that have historical applications. |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (none — `factura_otros_cobros` is a leaf for non-tax charge application records) | | | |

**Note**: The FK to `otros_cobros.uuid` is for traceability (which charge was applied) NOT for value cascade. The `valor_aplicado` is independent of the current `otros_cobros.costo`. This is the snapshot semantic — even if `otros_cobros` is archived or its `costo` is updated, `factura_otros_cobros.valor_aplicado` remains unchanged.

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `otros_cobros_writer.py::write_otro_cobro()` per charge per factura |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for DIAN retention |

**Special rules**:
- **Snapshot semantic**: `valor_aplicado` is a COPY of `otros_cobros.costo` at the moment of facturacion. NOT a live FK cascade.
- **`valor = base_calculo * valor_aplicado / 100`** computed at INSERT time (for percentage-based charges) OR `valor = base_calculo * valor_aplicado` (for fixed-amount charges, depending on `tipo_calculo`).
- **`base_calculo` source**: per `otros_cobros.base_calculo` ('subtotal' | 'subtotal_con_impuestos'). The caller passes the actual computed base value as a snapshot.
- **`tipo_calculo` source**: per `otros_cobros.tipo_calculo` ('porcentaje' | 'fijo'). The formula varies accordingly.
- **DIAN retention**: `fecha_retencion_hasta = created_at + 5 years` (configurable via `empresa.dias_retencion_empresa`).
- **Hash chain (future)**: sprint 5+ may add `hash_anterior`/`hash_actual` columns for chain integrity over charge totals if DIAN requires it.

## 6. CodeGraph Dependencies
- `parkos_core/facturacion/otros_cobros_writer.py::write_otro_cobro()` (sole writer).
- `parkos_core/facturacion/facturacion_endpoint.py::POST /facturas` (orchestrates full facturacion flow).
- `api_sucursal/routers/facturas.py::POST /facturas` (operator endpoint).
- `api_admin/routers/facturas.py::GET /facturas/{uuid}/otros-cobros` (admin detail view).
- `api_sucursal/routers/facturas.py::GET /facturas/{uuid}/otros-cobros` (own-branch view).
- `dian_dispatcher` (cloud worker — reads `factura_otros_cobros.valor_aplicado` and `valor` directly; NO JOIN to `otros_cobros` for the value).
- `web_sucursal/FacturacionForm` (displays computed charges; operator confirms).
- `web_admin/FacturaDetail` (charge breakdown view with snapshot values).
- `web_admin/CrossBranchOtrosCobrosReport` (cross-branch report by snapshot value).

## 7. Use Cases enabled by this table

The `factura_otros_cobros` table is the **append-only non-tax charge application snapshot** of every factura. Each row is a historical record of "what charge was applied, at what rate, on what base, with what final value". The snapshot semantic is critical: even if `otros_cobros.costo` is updated AFTER the factura was created, `factura_otros_cobros.valor_aplicado` remains the historical value. DIAN uses these snapshot values directly. **No cámaras, no OCR, no QR**: charge computation is from catalog dropdown + form input.

### 7.1 Use Case: `uc.factura-otros-cobros.branch-creates-factura-snapshots-otro-cobro`

**Actor**: operator (branch)

**Real-world action**: Operator in `web_sucursal/FacturacionForm` finalizes a factura with applicable non-tax charges (e.g., `tarifa_nocturna 10%`, `cargo_evento_especial 5000`). For each applicable charge, the backend SELECTs the vigente `otros_cobros.costo`, snapshots it into `factura_otros_cobros.valor_aplicado`, computes `base_calculo` and `valor`, INSERTs a row. All charge rows are inserted in the same TX as the parent `facturas` + `factura_detalle` + `factura_pagos` + `factura_impuestos`.

**Steps**:
1. Operator opens `web_sucursal/FacturacionForm`. The form auto-displays applicable charges based on `sucursal.ciudad` + line item types + time-of-day (e.g., `tarifa_nocturna` applies if `NOW().hour >= 22 OR NOW().hour < 6`).
2. Operator confirms the charge breakdown: `Tarifa nocturna 10% on $17000 = $1700`, `Cargo evento especial (fijo) = $5000`. Total non-tax charges = $6700.
3. Frontend POSTs `api_sucursal /facturas` with `{uuid_ingreso, lineas: [...], descuento: 0, pagos: [...], impuestos: [...], otros_cobros: [{uuid_otro_cobro:$tarjeta_uuid, base_calculo:17000}, {uuid_otro_cobro:$evento_uuid, base_calculo:17000}]}`. NOTE: the `otros_cobros` array is separate from `impuestos` — different tables, different snapshot semantics.
4. Backend opens TX; SELECT chain anchor from `log_transaccional`.
5. Backend validates RBAC: `permiso='facturar'`.
6. Backend SELECTs vigente `otros_cobros` for each charge: `SELECT uuid, costo, tipo_calculo, base_calculo FROM otros_cobros WHERE uuid=$uuid_otro_cobro AND vigente_hasta IS NULL`. (The vigente version at the moment of facturacion.)
7. Backend validates that posted `base_calculo` matches the server-computed value (defense against UI tampering).
8. INSERT `facturas` row (parent).
9. INSERT N `factura_detalle` rows (T35).
10. **For each non-tax charge: INSERT `factura_otros_cobros` row** with:
    - `uuid_otro_cobro=$cargo_uuid` (FK for traceability)
    - `valor_aplicado=$vigente_costo` (SNAPSHOT — copy of `otros_cobros.costo` at the moment)
    - `base_calculo=$computed_base` (SNAPSHOT — depends on `otros_cobros.base_calculo`)
    - `valor=base_calculo * valor_aplicado / 100` (if `tipo_calculo='porcentaje'`) OR `valor=valor_aplicado` (if `tipo_calculo='fijo'`)
    - `fecha_retencion_hasta=$created_at + 5_years`
11. INSERT `factura_impuestos` rows (T37 — for IVA etc., separate snapshot).
12. INSERT `factura_pagos` rows (T36 — cash + datafono breakdown).
13. INSERT `log_transaccional` (`accion='factura_creada'`, `datos_nuevos={subtotal, descuento, total, otros_cobros_count: N, factura_otros_cobros_uuids: [...]}`).
14. `queue_processor.enqueue('facturas', $uuid, $snapshot)` + `enqueue('factura_otros_cobros', ...)` for propagation.

**Tables touched (writes)**: `facturas` (1 row), `factura_detalle` (N rows), `factura_otros_cobros` (M rows — one per non-tax charge), `factura_impuestos` (K rows — taxes), `factura_pagos` (P rows — payments), `log_transaccional` (1 row), `sync_queue` (M+ items).
**Tables touched (reads)**: `otros_cobros` (vigente snapshot), `facturas` (parent), `impuestos` (for IVA), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `factura_otros_cobros.uuid_factura` → `facturas.uuid`; `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid` (FK for traceability only, no cascade); `factura_otros_cobros.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_sucursal` → `sucursal.uuid`; `factura_impuestos.uuid_factura` → `facturas.uuid`; `factura_pagos.uuid_factura` → `facturas.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `facturas.uuid`.

**Sync behavior**:
- Branch → cloud: YES (the `factura_otros_cobros` rows travel within 30s along with the parent `facturas`).
- Cloud → branch: NO.
- DIAN trigger: YES (cloud `dian_dispatcher` will INSERT `factura_electronica` after dispatch; the snapshot values from `factura_otros_cobros` are used to compose the e-factura total).
- Hash chain impact: YES — branch chain extends by 1 row (the log_transaccional); M rows of `factura_otros_cobros` extend the chain on cloud side on receipt.

**Integration with other tables**:
- Reads from: `otros_cobros` (vigente snapshot — same pattern as T37 `impuestos`), `facturas`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `facturas`, `factura_detalle`, `factura_otros_cobros` (the snapshot), `factura_impuestos` (tax snapshot), `factura_pagos`, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **facturacion snapshot cascade**. The facturacion flow writes 6 tables in one TX (facturas + 4 snapshot tables + log). Each snapshot table preserves the historical value independently.
- Same pattern as T37 (`factura_impuestos`): catalog value at moment of facturacion is the snapshot, not the current catalog value. DIAN verifies totals from snapshots.
- Related: T37 (`factura_impuestos`) covers the tax snapshot pattern; T35 (`factura_detalle`) covers the line items; T36 (`factura_pagos`) covers the payment breakdown.

### 7.2 Use Case: `uc.factura-otros-cobros.dian-verifies-snapshot-vs-current-catalog-mismatch`

**Actor**: DIAN provider (cloud)

**Real-world action**: DIAN receives the e-factura for compliance verification. They query the cloud API for the invoice detail: `GET /facturas/{uuid}/otros-cobros`. The API returns the snapshot values (`valor_aplicado`, `base_calculo`, `valor`). DIAN ALSO queries the current `otros_cobros` catalog (for cross-reference): `GET /otros-cobros/{uuid}`. If the catalog's current `costo` differs from the snapshot's `valor_aplicado`, DIAN sees the historical value used at the moment of facturacion. This is the expected behavior — the catalog may have changed AFTER the factura was created, but the snapshot preserves the historical value.

**Steps**:
1. DIAN provider receives the e-factura via their integration endpoint (Sprint 5: `POST /dian/recepcion`).
2. DIAN calls `GET /facturas/{uuid}/otros-cobros` to verify the charge breakdown.
3. Backend returns: `[{uuid_otro_cobro:$tarjeta_uuid, valor_aplicado:10, base_calculo:17000, valor:1700}, {uuid_otro_cobro:$evento_uuid, valor_aplicado:5000, base_calculo:0, valor:5000}]`. The snapshot values.
4. DIAN calls `GET /otros-cobros/$tarjeta_uuid` → returns the CURRENT catalog row: `costo: 12` (changed from 10 after the factura was issued). DIAN sees the discrepancy.
5. DIAN verifies: "Was the snapshot value (10) used at the moment of facturacion?" YES — the `factura_otros_cobros.created_at` is BEFORE the `otros_cobros.vigente_desde` of the new version. DIAN accepts the e-factura as compliant.
6. The reverse case: if DIAN queries and finds `factura_otros_cobros.valor_aplicado=10` but the catalog was 10 at the moment of facturacion (no version change), the snapshot matches the historical value. Standard compliance.
7. The problematic case: if DIAN finds `factura_otros_cobros.valor_aplicado=10` but the FACTURA'S created_at is AFTER the new version's `vigente_desde` (which has `costo=12`), DIAN may flag for investigation. This is rare (would require an INSERT into `factura_otros_cobros` AFTER the catalog was updated, which is impossible in the same TX due to the snapshot semantic).
8. (Optional) DIAN cross-references with `log_transaccional` to verify the facturacion TX integrity (hash chain).

**Tables touched (writes)**: NONE.
**Tables touched (reads)**: `factura_otros_cobros` (snapshot values), `otros_cobros` (current catalog), `facturas` (parent), `log_transaccional` (audit trail).
**FKs traversed**: `factura_otros_cobros.uuid_factura` → `facturas.uuid`; `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid` (FK for traceability, not for value).

**Sync behavior**:
- Branch → cloud: NO (DIAN query is read-only).
- Cloud → branch: NO.
- DIAN trigger: NO (this is the DIAN verification step, not dispatch).
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `factura_otros_cobros` (snapshot), `otros_cobros` (current), `facturas`, `log_transaccional`.
- Writes to: NONE.
- Cross-cutting: this is the **DIAN compliance verification** use case. The snapshot semantic is the audit defense — DIAN sees exactly what was charged at the moment of facturacion, independent of catalog changes. This is critical for retrospective audits (e.g., 5 years later when DIAN reviews a factura and the catalog has changed many times).
- Alternative (NOT implemented): the system could JOIN `factura_otros_cobros` to `otros_cobros` at query time and return the CURRENT value. This would be WRONG — it would not preserve the historical fact. The snapshot pattern is the correct approach.
- Related: T37 (`factura_impuestos`) covers the same DIAN verification pattern for taxes; T03 (`factura_electronica`) covers the e-factura dispatch flow.

### 7.3 Use Case: `uc.factura-otros-cobros.admin-cross-branch-report-by-applied-charge`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/CrossBranchOtrosCobrosReport`. Selects date range, branch (or all), and specific `uuid_otro_cobro` (e.g., `tarjeta_nocturna`). The report shows: how many facturas applied this charge, total `valor` across all branches, breakdown by branch. This helps admin understand revenue from specific charge categories and detect anomalies (e.g., one branch applies `cargo_evento_especial` 10x more than others — may indicate overcharging or service issue).

**Steps**:
1. Admin opens `web_admin/CrossBranchOtrosCobrosReport`. Form filters: date range, branch(es), `uuid_otro_cobro`.
2. Admin sets `uuid_otro_cobro=$tarjeta_uuid, desde='2026-08-01', hasta='2026-08-31'`.
3. Frontend GETs `api_admin /factura-otros-cobros?uuid_otro_cobro=$tarjeta_uuid&desde=&hasta=&uuid_sucursal=&group_by=sucursal`.
4. Backend runs:
   ```sql
   SELECT foc.uuid_sucursal, s.nombre AS sucursal_nombre,
          COUNT(DISTINCT foc.uuid_factura) AS factura_count,
          SUM(foc.valor) AS total_valor,
          AVG(foc.valor) AS avg_valor
   FROM factura_otros_cobros foc
   JOIN sucursal s ON foc.uuid_sucursal = s.uuid
   WHERE foc.uuid_otro_cobro = $tarjeta_uuid
     AND foc.created_at >= $desde AND foc.created_at < $hasta
     AND foc.uuid_sucursal IN ($sucursales_permitidas)
   GROUP BY foc.uuid_sucursal, s.nombre
   ORDER BY total_valor DESC
   ```
5. UI renders a table with: branch name, factura count, total valor (color-coded by % of total), avg valor. Admin spots anomalies.
6. Admin clicks a branch → drills into the individual `factura_otros_cobros` rows for that branch + charge in the date range. UI shows: factura UUID, fecha, placa (via JOIN `facturas` → `ingreso`), base_calculo, valor_aplicado, valor, snapshot consistency (verify snapshot = current catalog at the time of facturacion).
7. Admin exports to CSV/Excel for offline analysis.

**Tables touched (writes)**: NONE.
**Tables touched (reads)**: `factura_otros_cobros` (the snapshot, aggregated), `otros_cobros` (catalog cross-ref for current value), `sucursal` (display), `facturas` (drill-down), `ingreso` (via `facturas.uuid_ingreso` for placa).
**FKs traversed**: `factura_otros_cobros.uuid_sucursal` → `sucursal.uuid`; `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid`; `factura_otros_cobros.uuid_factura` → `facturas.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `ingreso.placa` (denormalized, no FK).

**Sync behavior**:
- Branch → cloud: NO (read of historical data).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `factura_otros_cobros` (the snapshot, aggregated), `otros_cobros` (catalog), `sucursal`, `facturas`, `ingreso`.
- Writes to: NONE.
- Cross-cutting: this is the **revenue analysis** view. The snapshot semantic enables historical reporting independent of catalog changes — admin can compare `total_valor` across time periods even if `otros_cobros.costo` changed. The drill-down verifies each factura's snapshot integrity.
- Related: T37 (`factura_impuestos`) covers the same report pattern for taxes; T27 (`otros_cobros`) covers the catalog version flow.

### 7.4 Use Case: `uc.factura-otros-cobros.catalog-version-change-does-not-affect-historical-snapshots`

**Actor**: admin (cloud)

**Real-world action**: Admin updates `otros_cobros.costo` for `tarjeta_nocturna` from 10 to 12 (new version via `[V]` flow: archive old `vigente_hasta=NOW()`, INSERT new with `vigente_desde=NOW(), costo=12`). Existing `factura_otros_cobros` rows with `uuid_otro_cobro=$tarjeta_uuid` and `valor_aplicado=10` are UNAFFECTED — they preserve the historical value. NEW facturaciones will use `valor_aplicado=12`. This is the snapshot semantic in action: catalog changes do NOT retroactively modify historical records.

**Steps**:
1. Admin opens `web_admin/OtrosCobros/{uuid}/Edit`. Changes `costo` from 10 to 12.
2. Frontend PATCHes `api_admin /otros-cobros/{uuid}` with `{costo: 12, vigente_desde: NOW()}`.
3. Backend: SELECT current vigente row `SELECT * FROM otros_cobros WHERE uuid=$uuid AND vigente_hasta IS NULL FOR UPDATE`.
4. UPDATE `otros_cobros SET vigente_hasta=NOW() WHERE uuid=$current_uuid` (archive old version with `costo=10`).
5. INSERT new `otros_cobros` row (`uuid=server-generated`, `vigente_desde=NOW()`, `costo=12`).
6. INSERT `log_transaccional` (`accion='otro_cobro_versioned'`, `datos_anteriores={costo:10, vigente_hasta:$old_ts}`, `datos_nuevos={costo:12, vigente_desde:NOW()}`).
7. `queue_processor.enqueue('otros_cobros', $new_uuid, $snapshot)` for parametrization push to branches.
8. Branches receive the new version within 30s; UPSERT locally. New facturaciones now use `valor_aplicado=12`.
9. Existing `factura_otros_cobros` rows with `valor_aplicado=10` are UNAFFECTED — the snapshot is preserved. The FK to `otros_cobros` still works (points to the archived version), but `valor_aplicado` does NOT cascade from the new version.

**Tables touched (writes)**: `otros_cobros` (1 UPDATE + 1 INSERT — versioning), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `otros_cobros` (current version lookup), `log_transaccional` (chain anchor).
**FKs traversed**: `otros_cobros` has NO outgoing FKs (catalog root); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid` (admin's primary branch); `log_transaccional.uuid_registro_afectado` (polymorphic) → `otros_cobros.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row.

**Integration with other tables**:
- Reads from: `otros_cobros` (current version), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `otros_cobros` (versioning), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **catalog versioning** use case for `otros_cobros`. The versioning flow is identical to all `[V]` tables (archive old + INSERT new + log + parametrization push). The **snapshot protection** is the key insight: `factura_otros_cobros.valor_aplicado` does NOT auto-update when the catalog changes. This is the `[A]` source-of-truth contract.
- Defense against accidental mutation: even if admin tries to UPDATE `factura_otros_cobros.valor_aplicado` to match the new catalog, the `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`. The only way to "fix" a historical snapshot is to INSERT a NEW `factura_otros_cobros` row with `observaciones='correccion'` (and an `anulaciones` workflow to void the original).
- Related: T27 (`otros_cobros`) covers the catalog version flow in detail; T37 (`factura_impuestos`) covers the same snapshot protection pattern for taxes.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers), 3 (partitioning via `pg_partman` — partitionable by month), 5 (audit constraints — REVOKE), 6 (cloud admin API for read), 7 (branch API for write as part of facturacion), 8 (Pydantic schemas), 10 (cloud sync worker for replication), 11 (branch sync worker for replication), 12 (sync_queue interop), 13 (web_admin FacturaDetail + CrossBranchOtrosCobrosReport), 14 (web_sucursal FacturacionForm), 15 (shadcn UI components for forms), 20 (structlog), 24 (pytest), 28 (docker compose), 29 (DIAN provider — reads snapshot values), 33 (DIAN compliance docs), 35 (operational dashboards).

## 9. RED Tests
- (RED) INSERT `factura_otros_cobros` from `rol_app` with valid snapshot values → success.
- (RED) `valor = base_calculo * valor_aplicado / 100` for percentage-based charges.
- (RED) `valor = valor_aplicado` for fixed-amount charges.
- (RED) `valor_aplicado` snapshot semantic: `otros_cobros.costo` updated AFTER the factura was created → `factura_otros_cobros.valor_aplicado` UNCHANGED.
- (RED) UPDATE `prod.factura_otros_cobros` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE from `prod.factura_otros_cobros` → `AUDIT_FIRST_INMUTABLE`.
- (RED) FK RESTRICT: deleting `otros_cobros` with `factura_otros_cobros` rows referencing it → error.
- (RED) `fecha_retencion_hasta = created_at + 5 years` for all rows.
- (RED) Partition pruning: query `WHERE created_at >= '2026-08-01' AND created_at < '2026-09-01'` → EXPLAIN shows single partition hit (when partitioning is enabled).
- (RED) Facturacion TX cascade: `facturas` + `factura_detalle` + `factura_otros_cobros` + `factura_impuestos` + `factura_pagos` + `log_transaccional` all in one TX. ROLLBACK on any failure.
- (RED) Defense against UI tampering: server validates `base_calculo` matches computed value; rejects with `INVALID_BASE_CALCULO` if mismatch.
- (RED) Cross-branch admin query NEVER writes to `factura_otros_cobros` (read-only).
- (RED) DIAN verification: snapshot returns historical value; current catalog value may differ; both queries return correct results.
- (RED) `[V]` catalog version change does NOT propagate to historical `factura_otros_cobros.valor_aplicado`.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger.
- [ ] F1.x `parkos_core/facturacion/otros_cobros_writer.py::write_otro_cobro()` (sole writer).
- [ ] F1.x Maintenance role for DELETE on retention-purged rows (5+ years).
- [ ] IT-4.x: `api_sucursal/routers/facturas.py::POST /facturas` integration with `otros_cobros_writer` (write snapshot per non-tax charge per factura).
- [ ] IT-4.x: snapshot semantic enforcement — caller passes `valor_aplicado` value, NOT a FK lookup.
- [ ] IT-4.x: `api_admin/routers/facturas.py::GET /facturas/{uuid}/otros-cobros` (admin detail view).
- [ ] IT-4.x: `api_sucursal/routers/facturas.py::GET /facturas/{uuid}/otros-cobros` (own-branch view).
- [ ] IT-4.x: `web_admin/FacturaDetail` (charge breakdown view with snapshot values).
- [ ] IT-4.x: `web_admin/CrossBranchOtrosCobrosReport` (revenue analysis by snapshot value).
- [ ] IT-4.x: `web_sucursal/FacturacionForm` integration — displays computed charges from snapshot.
- [ ] Sprint 5: monthly partitioning via `pg_partman` on `created_at`.
- [ ] Sprint 5: `pg_partman` retention policy (60 months).
- [ ] Sprint 5: `hash_anterior`/`hash_actual` columns if DIAN requires chain integrity over charge totals.
- [ ] Sprint 5: `factura_otros_cobros.uuid_otro_cobro_version` FK to `otros_cobros` archive rows for explicit snapshot-to-version linkage.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Catalog cost change creates billing dispute | Low | Snapshot semantic protects history; admin explains "snapshot captured historical value"; sprint 5: retroactive audit report |
| Operator misconfigures `valor_aplicado` (typo) | Low | Server validates `base_calculo` matches; `valor_aplicado` is server-fetched from vigente `otros_cobros`, NOT operator-typed |
| Operator forgets to apply an applicable charge (e.g., `tarjeta_nocturna` during night shift) | Med | Sprint 5: auto-suggestion in FacturacionForm based on time-of-day; sprint 5+: auto-application with admin review |
| High-volume branch generates many `factura_otros_cobros` rows | Med | Partitionable by month; retention 5 years; pg_partman purges > 5 years |
| DIAN queries historical `valor_aplicado` and finds it doesn't match the current catalog | Low (expected) | Snapshot semantic is the design — DIAN verification (use case 7.2) explains the difference |
| `[V]` versioning race: admin updates catalog mid-facturacion (between SELECT and INSERT) | Low | TX serializes: SELECT FOR UPDATE the vigente row + INSERT snapshot in same TX; sprint 5: explicit lock on `otros_cobros` per `uuid` |
| `valor` formula ambiguity (percentage vs fixed) | Low | `tipo_calculo` column on `otros_cobros` determines formula; writer validates before INSERT |
| Cross-tenant scope leak in admin reports | Low | Backend enforces `uuid_sucursal IN ($admin.sucursales_permitidas)` filter on EVERY query |
| `factura_electronica` total doesn't match `factura_otros_cobros.valor` sum | Low | DIAN dispatch reads `factura_otros_cobros.valor` directly; TX ensures consistency |
| `fecha_retencion_hasta` calculation drift (leap years, DST) | Low | Postgres interval arithmetic handles edge cases; retention worker tests cover boundary conditions |

## 12. Open Questions
- (a) Should `factura_otros_cobros` be partitioned by `created_at` from day 1, or only when volume warrants? Currently partitionable; sprint 5 may enable.
- (b) Should `valor_aplicado` be typed `Decimal(10,2)` (currency) or `numeric` with explicit precision? Currently `numeric` — Decimal handles currency arithmetic correctly.
- (c) Hash chain (`hash_anterior`/`hash_actual`): sprint 5 decision based on DIAN requirements.
- (d) Bulk facturacion (one factura with 50 line items + 20 charges): does the snapshot pattern scale? Per factura is a single TX; volume is moderate.
- (e) Should `factura_otros_cobros` support percentage-based charges with multiple bases (e.g., 10% on subtotal + 5% on subtotal_con_impuestos)? Currently `base_calculo` is single; sprint 5 may add JSON `bases_calculo` array.
- (f) Should the system auto-detect applicable charges based on `sucursal.ciudad` + `lineas` + time-of-day? Currently manual selection; sprint 5: rule engine.
- (g) Should `otros_cobros` be applied to ALL facturas, or only specific ones (e.g., B2B vs casual)? Sprint 5: per-`clientes.tipo_persona` applicability rules.
- (h) Per-region rules (e.g., `tarjeta_nocturna` applies in Bogotá but not Medellín)? Currently global; sprint 5: per-`sucursal.ciudad` applicability.
- (i) Should `factura_otros_cobros` be exposed to customers (visible on the printed ticket)? Sprint 5: customer-facing breakdown.
- (j) Refund flow: if a factura is anulada (T39), how are non-tax charges handled? Currently NO automatic refund of `factura_otros_cobros` (it's append-only); refund is a separate manual flow.
