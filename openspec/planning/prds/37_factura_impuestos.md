# PRD: factura_impuestos (T37)

> Append-only snapshot of each `impuestos` row applied to a `facturas` row at the moment of facturacion. `porcentaje_aplicado` is the historical percentage — NOT a live FK cascade. Even if `impuestos.porcentaje` is updated AFTER the factura was created, `factura_impuestos.porcentaje_aplicado` remains the historical value. DIAN retention 5+ years. Tabla candidata a hash-chaining if DIAN exige cadena de integridad sobre totales.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[A]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.factura_impuestos`
- **SQL name**: `factura_impuestos` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN compliance)
- **Hash chain**: CANDIDATE — per AGENTS.md "Tabla candidata a hash-chaining si DIAN exige cadena de integridad sobre totales". Not implemented in MVP; sprint 5+ may add `hash_anterior`/`hash_actual` if DIAN requires chain integrity over tax totals.
- **Partitioning**: partitionable by month on `created_at`
- **Origin**: F1 (schema + REVOKE + trigger) + IT-4 (writes per facturacion)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_sucursal` is denormalized for partition pruning + RLS-style filtering.
- Travel: branch-origin rows travel to cloud via `sync_queue`. Cloud receives and INSERTs verbatim. DIAN cloud-side replica uses snapshot values directly.
- **Snapshot semantic**: `porcentaje_aplicado` is the COPY of `impuestos.porcentaje` at the moment of facturacion. NOT a live FK cascade. The `base_calculo` and `valor` are also snapshots (the computed tax base and final tax amount).
- **NO FK cascade on `uuid_impuesto`**: the FK IS present (`uuid_impuesto` → `impuestos.uuid`), but only for traceability — NOT for value cascade. The `porcentaje_aplicado` is independent of the current `impuestos.porcentaje`.

## 3. SOLID Atomic Breakdown
- **S**: "one tax application record at a moment in time" — INSERT in same TX as the parent `facturas` row.
- **O**: extensible via migration; new columns (`observaciones`, `uuid_impuesto_version`) added as audit requirements grow.
- **I**: branch operator API (writer — part of facturacion flow); admin read API (FacturaDetail); DIAN provider (cloud-side, reads snapshot values).
- **D**: `parkos_core/facturacion/impuesto_writer.py::write_impuesto(uuid_factura, uuid_sucursal, uuid_impuesto, base_calculo, porcentaje_aplicado)` — the ONLY writer. Caller passes the vigente `impuestos.porcentaje` as `porcentaje_aplicado` (snapshot).
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, tax history dies |
| `uuid_factura` | `prod.facturas.uuid` | exactly one (NOT NULL) | CASCADE | if factura deleted (never), tax rows die |
| `uuid_impuesto` | `prod.impuestos.uuid` | exactly one (NOT NULL) | RESTRICT | FK is for traceability ONLY — no cascade. RESTRICT prevents deletion of `impuestos` rows that have historical applications. |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (none — `factura_impuestos` is a leaf for tax application records) | | | |

**Note**: The FK to `impuestos.uuid` is for traceability (which tax was applied) NOT for value cascade. The `porcentaje_aplicado` is independent of the current `impuestos.porcentaje`. This is the snapshot semantic — even if `impuestos` is archived or its `porcentaje` is updated, `factura_impuestos.porcentaje_aplicado` remains unchanged.

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `impuesto_writer.py::write_impuesto()` per tax per factura |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for DIAN retention |

**Special rules**:
- **Snapshot semantic**: `porcentaje_aplicado` is a COPY of `impuestos.porcentaje` at the moment of facturacion. NOT a live FK cascade.
- **`valor = base_calculo * porcentaje_aplicado / 100`** computed at INSERT time.
- **`base_calculo` source**: per `impuestos.base_calculo` ('subtotal' | 'subtotal_con_impuestos'). The caller passes the actual computed base value as a snapshot.
- **DIAN retention**: `fecha_retencion_hasta = created_at + 5 years` (configurable via `empresa.dias_retencion_empresa`).
- **Hash chain (future)**: sprint 5+ may add `hash_anterior`/`hash_actual` columns for chain integrity over tax totals if DIAN requires it.

## 6. CodeGraph Dependencies
- `parkos_core/facturacion/impuesto_writer.py::write_impuesto()` (sole writer).
- `parkos_core/facturacion/facturacion_endpoint.py::POST /facturas` (orchestrates full facturacion flow).
- `api_sucursal/routers/facturas.py::POST /facturas` (operator endpoint).
- `api_admin/routers/facturas.py::GET /facturas/{uuid}/impuestos` (admin detail view).
- `api_sucursal/routers/facturas.py::GET /facturas/{uuid}/impuestos` (own-branch view).
- `dian_dispatcher` (cloud worker — reads `factura_impuestos.porcentaje_aplicado` and `valor` directly; NO JOIN to `impuestos` for the percentage value).
- `web_sucursal/FacturacionForm` (displays computed taxes; operator confirms).
- `web_admin/FacturaDetail` (tax breakdown view with snapshot values).
- `web_admin/CrossBranchImpuestosReport` (cross-branch report by snapshot value).

## 7. Use Cases enabled by this table

The `factura_impuestos` table is the **append-only tax application snapshot** of every factura. Each row is a historical record of "what tax was applied, at what percentage, on what base, with what final value". The snapshot semantic is critical: even if `impuestos.porcentaje` is updated AFTER the factura was created, `factura_impuestos.porcentaje_aplicado` remains the historical value. DIAN uses these snapshot values directly. **No cámaras, no OCR, no QR**: tax computation is from catalog dropdown + form input.

### 7.1 Use Case: `uc.factura-impuestos.branch-creates-factura-snapshots-impuesto`

**Actor**: operator (branch)

**Real-world action**: Operator in `web_sucursal/FacturacionForm` finalizes a factura with applicable taxes (e.g., IVA 19%, Consumo 8%). For each applicable tax, the backend SELECTs the vigente `impuestos.porcentaje`, snapshots it into `factura_impuestos.porcentaje_aplicado`, computes `base_calculo` and `valor`, INSERTs a row. All tax rows are inserted in the same TX as the parent `facturas` + `factura_detalle` + `factura_pagos`.

**Steps**:
1. Operator opens `web_sucursal/FacturacionForm`. The form auto-displays applicable taxes based on `sucursal.ciudad` + line item types (e.g., IVA applies to most services; Consumo applies to alcohol-related if any).
2. Operator confirms the tax breakdown: `IVA 19% on $17000 = $3230`, `Consumo 8% on $17000 = $1360`. Total = $17000 + $3230 + $1360 = $21590.
3. Frontend POSTs `api_sucursal /facturas` with `{uuid_ingreso, lineas: [...], descuento: 0, pagos: [...], impuestos: [{uuid_impuesto:$iva_uuid, base_calculo:17000}, {uuid_impuesto:$consumo_uuid, base_calculo:17000}]}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional`.
5. Backend validates RBAC: `permiso='facturar'`.
6. Backend SELECTs vigente `impuestos` for each tax: `SELECT uuid, porcentaje, base_calculo FROM impuestos WHERE uuid=$uuid_impuesto AND vigente_hasta IS NULL`. (The vigente version at the moment of facturacion.)
7. Backend validates that posted `base_calculo` matches the server-computed value (defense against UI tampering).
8. INSERT `facturas` row (parent).
9. INSERT N `factura_detalle` rows (T35).
10. **For each tax: INSERT `factura_impuestos` row** with:
    - `uuid_impuesto=$impuesto_uuid` (FK for traceability)
    - `porcentaje_aplicado=$vigente_porcentaje` (SNAPSHOT — copy of `impuestos.porcentaje` at the moment)
    - `base_calculo=$computed_base` (SNAPSHOT — depends on `impuestos.base_calculo`)
    - `valor=$base_calculo * porcentaje_aplicado / 100` (computed at INSERT)
    - `fecha_retencion_hasta=$created_at + 5_years`
11. INSERT M `factura_pagos` rows (T36) — the total must match `facturas.total = subtotal + SUM(impuestos.valor) - descuento`.
12. INSERT `log_transaccional` per tax row (`accion='factura_impuesto_registrado'`, `datos_nuevos={uuid_impuesto, porcentaje_aplicado, base_calculo, valor}`).
13. `queue_processor.enqueue` for all rows.
14. Operator UI shows the tax breakdown: `IVA 19% = $3230, Consumo 8% = $1360, Total = $21590`.

**Tables touched (writes)**: `facturas`, `factura_detalle`, `factura_impuestos` (M rows), `factura_pagos`, `factura_electronica` (cloud), `log_transaccional` (4+N+M rows), `sync_queue` (3+N+M items).
**Tables touched (reads)**: `impuestos` (vigente, snapshot lookup), `permisos_usuario` (RBAC), `log_transaccional`, `usuarios`, `sucursal`.
**FKs traversed**: `factura_impuestos.uuid_sucursal` → `sucursal.uuid`; `factura_impuestos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_impuesto` → `impuestos.uuid` (traceability FK, NO cascade); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `factura_impuestos.uuid`.

**Sync behavior**:
- Branch → cloud: YES.
- Cloud → branch: YES (SyncBackEvent with `numero_oficial`).
- DIAN trigger: YES.
- Hash chain impact: YES — branch chain extends by 4+N+M rows; cloud chain extends correspondingly.

**Integration with other tables**:
- Reads from: `impuestos` (vigente, snapshot lookup), `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `factura_impuestos` (M rows), parent tables, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **tax snapshot** flow. The `porcentaje_aplicado` is the value the operator confirmed, validated against vigente `impuestos.porcentaje` at server-side. After the INSERT, this value is FOREVER independent of `impuestos.porcentaje`.
- Related: T35 (`factura_detalle`) use case 7.1 covers the line items; T36 (`factura_pagos`) covers payments; T26 (`impuestos`) covers the catalog versioning pattern.

### 7.2 Use Case: `uc.factura-impuestos.impuesto-changed-post-facturacion-detail-unaffected`

**Actor**: admin (cloud) + system (snapshot semantic invariant)

**Real-world action**: Admin updates `impuestos.porcentaje` from 19% to 20% (DIAN policy change effective 2026-07-01) AFTER a factura was already created with the 19% IVA. The `factura_impuestos.porcentaje_aplicado` remains 19% (snapshot semantic). Admin runs an audit query: "Show me all facturas billed with IVA at the OLD 19% rate in 2026-Q2" — the answer is the `factura_impuestos` rows where the snapshot percentage is 19%, regardless of the current `impuestos.porcentaje`.

**Steps**:
1. Admin opens `web_admin/ImpuestosDetail/{uuid}`, clicks `Actualizar porcentaje` → types `19 → 20`, confirms effective `vigente_desde=2026-07-01`.
2. Frontend PATCHes `api_admin /impuestos/{uuid}` with `{porcentaje: 20, vigente_desde: '2026-07-01'}` (T26 versioning pattern).
3. Backend opens TX; SELECT chain anchor from `log_transaccional`.
4. UPDATE current vigente `impuestos` row SET `vigente_hasta='2026-06-30 23:59:59'`.
5. INSERT new `impuestos` row with `porcentaje=20, vigente_desde='2026-07-01', vigente_hasta=NULL`.
6. INSERT `log_transaccional` (`accion='impuesto_actualizado'`, `tabla_afectada='impuestos'`, `datos_anteriores={porcentaje:19, vigente_hasta:null}, datos_nuevos={porcentaje:20, vigente_desde:'2026-07-01'}`).
7. `queue_processor.enqueue('impuestos', $new_uuid, $new_snapshot)` — parametrization push to all branches.
8. **Existing `factura_impuestos` rows are UNAFFECTED**: their `porcentaje_aplicado` snapshot is unchanged. The invoice still shows the historical 19%.
9. Admin runs audit query: `SELECT fi.* FROM factura_impuestos fi JOIN facturas f ON fi.uuid_factura=f.uuid WHERE fi.uuid_impuesto=$iva_uuid AND fi.porcentaje_aplicado=19 AND f.created_at < '2026-07-01'` — returns the facturas using the OLD 19% rate.
10. The audit confirms: "1500 facturas in 2026-Q2 used the old 19% IVA; their `factura_impuestos.porcentaje_aplicado` snapshots remain at 19% regardless of the new vigente 20%."

**Tables touched (writes)**: `impuestos` (archive old + INSERT new), `log_transaccional` (audit), `sync_queue` (parametrization).
**Tables touched (reads)**: `factura_impuestos` (audit query, unchanged), `facturas` (audit JOIN), `impuestos` (current vigente, archived version).
**FKs traversed**: `impuestos` (no FKs); `factura_impuestos.uuid_impuesto` → `impuestos.uuid` (traceability); `factura_impuestos.uuid_factura` → `facturas.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the archived + new version to all branches within 30s.
- DIAN trigger: NO (impuesto changes don't dispatch DIAN; only `factura_electronica` creation does).
- Hash chain impact: YES — cloud chain extends by 1-2 rows (impuesto_actualizado + new if any); each branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `factura_impuestos` (audit), `facturas` (audit JOIN), `impuestos` (vigente, archived).
- Writes to: `impuestos` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **snapshot semantic invariant for taxes**. The `porcentaje_aplicado` is FOREVER the value at the moment of facturacion. No retroactive re-evaluation, no JOIN cascade, no UPDATE. This is the same pattern as `factura_detalle.valor_unitario` (T35) and `reimpresion_ticket.costo_aplicado` (T38).
- Related: T26 (`impuestos`) use case 7.1 covers the versioning pattern; T35 (`factura_detalle`) use case 7.2 covers the same snapshot invariant for line item values.

### 7.3 Use Case: `uc.factura-impuestos.cloud-dian-receives-snapshot-porcentaje-directly`

**Actor**: dian_dispatcher (cloud worker)

**Real-world action**: Cloud `dian_dispatcher` builds the DIAN XML/JSON payload directly from `factura_impuestos.porcentaje_aplicado` and `valor` snapshot values — NO JOIN to `impuestos` is performed for the percentage value. This is critical for DIAN compliance: the DIAN representation must reflect EXACTLY what was billed, regardless of any subsequent tax rate changes.

**Steps**:
1. Cloud receives the `facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos` batch from branch (offline mode) or via online `/facturas/procesar`.
2. Cloud INSERTs each row idempotently.
3. Cloud opens TX; SELECT `empresa` FOR UPDATE for atomic `consecutivo` (T21 use case 7.2).
4. Cloud INSERTs `factura_electronica` (T03).
5. Cloud enqueues `dian_dispatcher`.
6. `dian_dispatcher` worker picks up the task; reads `factura_electronica` + `factura_detalle` + `factura_impuestos` + `factura_pagos`.
7. Worker builds DIAN payload:
   ```xml
   <Invoice>
     <Lines>...</Lines>
     <Taxes>
       <Tax>
         <Code>{impuestos.codigo}</Code>
         <Name>{impuestos.nombre}</Name>
         <Percentage>{factura_impuestos.porcentaje_aplicado snapshot}</Percentage>
         <Base>{factura_impuestos.base_calculo}</Base>
         <Value>{factura_impuestos.valor}</Value>
       </Tax>
       ...
     </Taxes>
     <Payments>...</Payments>
   </Invoice>
   ```
8. **NO JOIN to `impuestos.porcentaje`**: the `factura_impuestos.porcentaje_aplicado` snapshot is authoritative. Even if `impuestos.porcentaje` has changed since the factura was created, the DIAN payload uses the historical snapshot.
9. The `impuestos.codigo` and `impuestos.nombre` MAY come from a JOIN to `impuestos` (these are reference metadata, not rate values) — but the percentage is ALWAYS the snapshot.
10. Worker POSTs to DIAN provider.
11. DIAN responds with CUFE.
12. Worker INSERTs `log_transaccional` (`accion='dian_aceptada'`).
13. Worker INSERTs `SyncBackEvent` with CUFE for branch.

**Tables touched (writes — cloud side)**: `factura_electronica`, `empresa`, `log_transaccional`, `dian_dispatcher`, `SyncBackEvent`.
**Tables touched (writes — branch side, from sync)**: `facturas`, `factura_detalle`, `factura_impuestos`, `factura_pagos` (idempotent INSERTs).
**Tables touched (reads)**: `factura_electronica`, `factura_impuestos` (snapshot values), `impuestos` (metadata only — codigo, nombre, NOT porcentaje), `empresa`, `log_transaccional`, `sucursal`.
**FKs traversed**: per row (varies); `factura_impuestos.uuid_impuesto` → `impuestos.uuid` (metadata JOIN).

**Sync behavior**:
- Branch → cloud: YES.
- Cloud → branch: YES (SyncBackEvent).
- DIAN trigger: YES (this IS the DIAN dispatch).
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `factura_electronica`, `factura_impuestos` (snapshot), `impuestos` (metadata only), `empresa`, `log_transaccional`, `sucursal`.
- Writes to: `factura_electronica`, `empresa`, `log_transaccional`, `dian_dispatcher`, `SyncBackEvent`.
- Cross-cutting: this is the **DIAN compliance backbone for taxes**. The snapshot semantic in `factura_impuestos` is what makes the DIAN representation legally valid: the tax rates billed match the rates reported, with no dependency on current `impuestos.porcentaje`.
- Related: T03 (`factura_electronica`) covers the full DIAN flow; T35 (`factura_detalle`) use case 7.3 covers the same snapshot pattern for line items.

### 7.4 Use Case: `uc.factura-impuestos.admin-cross-branch-report-by-snapshot-percentage`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/CrossBranchImpuestosReport`. Wants to see tax revenue across all branches, filtered by the SNAPSHOT percentage (not the current `impuestos.porcentaje`). For example: "How much IVA did we collect at the old 19% rate across all branches in 2026-Q2?" The query JOINs `factura_impuestos` to `facturas` and aggregates by snapshot percentage, NOT by current `impuestos.porcentaje`.

**Steps**:
1. Admin opens `web_admin/CrossBranchImpuestosReport`.
2. Admin sets filters: `fecha_desde=2026-04-01, fecha_hasta=2026-06-30, uuid_impuesto=$iva_uuid, porcentaje_aplicado=19`.
3. Frontend GETs `api_admin /reportes/impuestos?desde=&hasta=&uuid_impuesto=&porcentaje_aplicado=&uuid_sucursal=&limit=`.
4. Backend runs:
   ```sql
   SELECT fi.uuid_sucursal, s.nombre AS sucursal_nombre,
          COUNT(DISTINCT fi.uuid_factura) AS num_facturas,
          SUM(fi.base_calculo) AS total_base_calculo,
          SUM(fi.valor) AS total_impuesto
   FROM factura_impuestos fi
   JOIN facturas f ON fi.uuid_factura = f.uuid
   JOIN sucursal s ON fi.uuid_sucursal = s.uuid
   WHERE fi.uuid_impuesto = $uuid_impuesto
     AND fi.porcentaje_aplicado = $porcentaje_aplicado  -- SNAPSHOT value
     AND f.created_at BETWEEN $desde AND $hasta
   GROUP BY fi.uuid_sucursal, s.nombre
   ORDER BY total_impuesto DESC;
   ```
5. UI renders a table: per-branch rows with num_facturas, total_base_calculo, total_impuesto. Color-coded: rows where the snapshot percentage is no longer vigente (the archived 19% rate) show a yellow badge "Archived rate".
6. Admin clicks a row → drill-down to the individual `factura_impuestos` rows.
7. (Optional) Admin exports to CSV/Excel for finance audit or DIAN reporting.
8. (Optional) Admin compares with `impuestos.porcentaje` vigente in the same period: `SELECT vigente_desde, vigente_hasta, porcentaje FROM impuestos WHERE uuid=$uuid_impuesto AND vigente_desde <= $hasta AND (vigente_hasta IS NULL OR vigente_hasta >= $desde) ORDER BY vigente_desde` — confirms the snapshot percentage matches the vigente at the moment of facturacion.

**Tables touched (writes)**: NONE for the read.
**Tables touched (reads)**: `factura_impuestos` (snapshot values), `facturas` (date filter), `sucursal` (display), `impuestos` (optional vigente lookup for cross-validation).
**FKs traversed**: `factura_impuestos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_impuesto` → `impuestos.uuid`; `factura_impuestos.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read of historical data).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `factura_impuestos` (snapshot), `facturas`, `sucursal`, `impuestos` (optional cross-validation).
- Writes to: NONE.
- Cross-cutting: this is the **snapshot-driven tax reporting** view. By filtering on `porcentaje_aplicado` (snapshot), admin gets the historical tax revenue picture regardless of tax rate evolution. Critical for finance reconciliation when rates change mid-period.
- Related: T35 (`factura_detalle`) use case 7.4 covers the same snapshot-driven reporting for line items.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers), 3 (partitioning — partitionable by month), 5 (audit constraints — REVOKE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin FacturaDetail + CrossBranchImpuestosReport), 14 (web_sucursal FacturacionForm), 15 (shadcn UI), 20 (structlog), 21 (Prometheus counters), 24 (pytest), 28 (docker compose), 29 (DIAN provider), 33 (DIAN compliance docs).

## 9. RED Tests
- (RED) INSERT `factura_impuestos` from `rol_app` → success.
- (RED) UPDATE `prod.factura_impuestos` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.factura_impuestos` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Snapshot semantic: update `impuestos.porcentaje` after factura creation → `factura_impuestos.porcentaje_aplicado` is UNCHANGED.
- (RED) `valor = base_calculo * porcentaje_aplicado / 100` invariant at INSERT time.
- (RED) Multi-tax factura: `facturas.total = subtotal + SUM(factura_impuestos.valor) - facturas.descuento`.
- (RED) DIAN payload uses `factura_impuestos.porcentaje_aplicado` snapshot directly; NO JOIN to `impuestos.porcentaje`.
- (RED) FK to `impuestos.uuid` for traceability; deleting an `impuestos` row with historical applications is RESTRICTED (cannot delete while references exist).
- (RED) `fecha_retencion_hasta = created_at + 5 years`.
- (RED) Cross-branch report filters by snapshot percentage, NOT by current `impuestos.porcentaje`.
- (RED) Admin report NEVER writes to `factura_impuestos` (read-only).
- (RED) Synchronous TX: `facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos` all in one TX. ROLLBACK on any failure.
- (RED) `base_calculo` per `impuestos.base_calculo` ('subtotal' vs 'subtotal_con_impuestos') computed correctly.
- (RED) Sprint 5+ hash chain (if activated): `hash_anterior = SHA256(...)` per `uuid_sucursal`; verifier detects tampering.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger.
- [ ] F1.x `impuesto_writer.py::write_impuesto()` helper.
- [ ] F1.x Partition setup (partitionable by month on `created_at`; sprint 5 may activate).
- [ ] IT-4.x: `parkos_core/facturacion/facturacion_endpoint.py::POST /facturas` orchestrates full facturacion flow.
- [ ] IT-4.x: server-side validation of `porcentaje_aplicado` against vigente `impuestos.porcentaje`.
- [ ] IT-4.x: server-side computation of `valor` from `base_calculo` and `porcentaje_aplicado`.
- [ ] IT-4.x: `api_admin/routers/facturas.py::GET /facturas/{uuid}/impuestos`.
- [ ] IT-4.x: `web_sucursal/FacturacionForm` displays computed taxes.
- [ ] IT-4.x: `web_admin/FacturaDetail` tax breakdown view.
- [ ] IT-4.x: `web_admin/CrossBranchImpuestosReport` with snapshot percentage filtering.
- [ ] IT-4.x: `dian_dispatcher` reads snapshot values directly (no JOIN to `impuestos.porcentaje`).
- [ ] Sprint 5: activate `pg_partman` monthly partitioning on `created_at`.
- [ ] Sprint 5+: `hash_anterior`/`hash_actual` columns if DIAN requires chain integrity over totals.
- [ ] Sprint 5+: explicit `uuid_impuesto_version` column for exact catalog version identification.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator bypasses server-side validation (UI tampering) | Low | Server validates `porcentaje_aplicado` against vigente `impuestos.porcentaje`; mismatch returns 422 |
| Admin archives the wrong `impuestos` version (current vs historical) | Low | UI shows confirmation modal with the vigente range; archive action requires explicit confirm + audit row |
| DIAN payload uses current `impuestos.porcentaje` instead of snapshot | Low | Code review + RED test enforces no JOIN; DIAN payload builder is a dedicated module with explicit contract |
| Multi-tax factura totals mismatch | Low | Server-side computation + invariant check at INSERT time |
| Snapshot value drifts from `impuestos.porcentaje` over time | Low | `[V]` versioning of `impuestos` enforces history preservation; `factura_impuestos.porcentaje_aplicado` is independent |
| `impuestos` row deletion breaks FK for historical `factura_impuestos` rows | Low | FK is `ON DELETE RESTRICT` — deletion of `impuestos` with historical applications is blocked; if business needs deletion, archive `impuestos` instead (set `vigente_hasta`) |
| High-volume branch generates many tax rows per factura | Low | Schema supports arbitrary N; partition handles scale |
| Cross-branch report query is slow on large partitions | Med | Index on `(uuid_impuesto, porcentaje_aplicado, uuid_sucursal, created_at)` for filterable aggregation |

## 12. Open Questions
- (a) Should the FK to `impuestos.uuid` be relaxed to a nullable column with `ON DELETE SET NULL` for true snapshot independence? Currently NOT NULL + RESTRICT.
- (b) Should `base_calculo` be a free decimal or constrained to specific values (e.g., 'subtotal', 'subtotal_con_impuestos')? Currently free decimal.
- (c) Hash chain: when does DIAN REQUIRE chain integrity over totals? Sprint 5+ decision based on actual DIAN mandate.
- (d) Should `factura_impuestos` be replicated to cloud as `factura_impuestos_mirror` for read scaling? Currently direct read.
- (e) Multi-branch comparison: "Branch X vs Branch Y tax rates" — requires consistent snapshot semantics across branches; sprint 5 reporting.
- (f) Refunds affecting taxes: when a factura is partially refunded, do we generate negative `factura_impuestos` rows or a separate `factura_impuestos_devolucion` table? Sprint 5.
- (g) `impuestos.codigo` (DIAN tax code) — should this be a separate column on `factura_impuestos` (snapshot of the code at the moment) to avoid JOIN in DIAN payload? Sprint 5 — currently relies on JOIN for code metadata.
- (h) Tax exemptions: how does a customer with tax-exempt status interact with `factura_impuestos`? Currently full taxes apply; sprint 5 may add exemption logic.
