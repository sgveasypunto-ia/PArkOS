# PRD: factura_detalle (T35)

> Append-only lines of a `facturas` row. Each row is a snapshot of the `tarifas_sucursal.valor` (or `otros_cobros.costo`) at the moment of facturacion — NOT a live FK cascade. DIAN retention 5+ years. Source of truth for what was billed, line-by-line, regardless of subsequent catalog changes.

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
- **Table name**: `prod.factura_detalle`
- **SQL name**: `factura_detalle` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN compliance)
- **Partitioning**: partitionable by month on `created_at` (high write rate during peak; one row per line per factura)
- **Origin**: F1 (schema + REVOKE + trigger) + IT-4 (writes per facturacion)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_sucursal` is denormalized (transitive via `facturas.uuid_sucursal`) for partition pruning + RLS-style filtering at read time.
- Travel: branch-origin rows travel to cloud via `sync_queue` (as queue items, separate rows). Cloud receives and INSERTs verbatim. DIAN cloud-side replica uses snapshot values directly (no need to JOIN to `tarifas_sucursal`).
- **Snapshot semantic**: `valor_unitario` is the snapshot of `tarifas_sucursal.valor` at the moment of facturacion. NO FK cascade — even if `tarifas_sucursal` is updated (archived) AFTER the factura was created, `factura_detalle.valor_unitario` remains unchanged.

## 3. SOLID Atomic Breakdown
- **S**: "one line of a factura" — INSERT in same TX as the `facturas` row + `factura_impuestos` + `factura_pagos` + `factura_electronica` (for online DIAN flow).
- **O**: extensible via migration; new columns (`descuento_pct`, `observaciones`) added as business rules grow.
- **I**: branch operator API (writer — single endpoint per facturacion); admin read API (`FacturaDetail`, drill-down); DIAN provider (cloud-side, reads snapshot values).
- **D**: `parkos_core/facturacion/detalle_writer.py::write_detalle(uuid_factura, uuid_sucursal, concepto, cantidad, valor_unitario, subtotal)` — the ONLY writer. The `concepto` and `valor_unitario` are passed in by the caller (caller resolves from `tarifas_sucursal` vigente at moment of facturacion); this is the snapshot guarantee.
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, detalle history dies |
| `uuid_factura` | `prod.facturas.uuid` | exactly one (NOT NULL) | CASCADE | if factura deleted (never — append-only), detalle dies; but factura is `[L-E]` and never deleted |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `factura_electronica.uuid_factura` (T03) | (joins via `facturas.uuid`) | 1..1 | e-factura references the factura; detalle is read for DIAN payload |
| `reclamos.uuid_reclamable` (polymorphic, T40) | n/a | 0..1 | a reclamo may target a factura; admin drills into detalle via `facturas.uuid` JOIN |

**Note**: NO FK to `tarifas_sucursal` or `otros_cobros` — by design. The snapshot semantic requires that the value remain constant even if the catalog row is archived or updated. Sprint 5 may add an optional `uuid_tarifa_sucursal_snapshot` column for traceability without enforcing FK cascade.

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `detalle_writer.py::write_detalle()` per line per factura |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for DIAN retention |

**Special rules**:
- **Snapshot semantic**: `valor_unitario` is a COPY of `tarifas_sucursal.valor` (or `otros_cobros.costo`) at the moment of facturacion. NOT a live FK cascade.
- **`subtotal = cantidad * valor_unitario` computed at INSERT time**: stored as a column for query speed; computed deterministically from the two snapshot values.
- **DIAN retention**: `fecha_retencion_hasta = created_at + 5 years` (configurable via `empresa.dias_retencion_empresa`).
- **Multi-line facturas**: a single `facturas` row may have N `factura_detalle` rows (1..N). The `facturas.total` is the sum of `factura_detalle.subtotal` minus `facturas.descuento` plus `factura_impuestos.valor`.

## 6. CodeGraph Dependencies
- `parkos_core/facturacion/detalle_writer.py::write_detalle()` (sole writer).
- `parkos_core/facturacion/facturacion_endpoint.py::POST /facturas` (orchestrates: tarifas lookup → detalle INSERT → impuestos INSERT → pagos INSERT → facturas INSERT → log + sync_queue).
- `api_sucursal/routers/facturas.py::POST /facturas` (operator endpoint).
- `api_admin/routers/facturas.py::GET /facturas/{uuid}/detalle` (admin detail view).
- `api_sucursal/routers/facturas.py::GET /facturas/{uuid}/detalle` (own-branch detail view).
- `dian_dispatcher` (cloud worker — reads `factura_detalle.valor_unitario` directly for DIAN payload; no JOIN to `tarifas_sucursal`).
- `web_sucursal/FacturacionForm` (multi-line factura entry with tariff dropdown).
- `web_admin/FacturaDetail` (line-by-line view with snapshot values).
- `web_admin/CrossBranchDetalleReport` (cross-branch report by snapshot value, no longer by catalog FK).

## 7. Use Cases enabled by this table

The `factura_detalle` table is the **append-only line-item snapshot** of every factura. Each row is a historical record of "what was billed, at what unit price, in what quantity". The snapshot semantic is critical: even if `tarifas_sucursal.valor` is updated AFTER the factura was created, the `factura_detalle.valor_unitario` remains the historical value. DIAN uses these snapshot values directly for the e-factura representation. **No cámaras, no OCR, no QR**: tariff selection is from a dropdown (catalog); quantity and unit price are operator inputs.

### 7.1 Use Case: `uc.factura-detalle.branch-creates-multi-line-factura-snapshots-tariff`

**Actor**: operator (branch)

**Real-world action**: Operator in `web_sucursal/FacturacionForm` finalizes a multi-line factura for a customer leaving. The factura has 3 lines: 1 hour of auto parking ($5000), 1 hour of moto parking ($2000), 1 "lavado" extra ($10000). For each line, the operator selects the service from a dropdown; the backend resolves the vigente `tarifas_sucursal.valor` (or `otros_cobros.costo`), snapshots it into `factura_detalle.valor_unitario`, computes `subtotal = cantidad * valor_unitario`, and INSERTs a row. All lines are inserted in the same TX as the parent `facturas` row.

**Steps**:
1. Operator opens `web_sucursal/FacturacionForm`. Selects `uuid_factura_padre` (or creates new from `ingreso`/`salida` flow).
2. Operator adds lines: clicks `Agregar línea` 3 times. For each line, selects from dropdown:
   - Line 1: `concepto='Auto - Por hora'`, `cantidad=1` (dropdown auto-populates `valor_unitario=$5000` from vigente `tarifas_sucursal`).
   - Line 2: `concepto='Moto - Por hora'`, `cantidad=1` (`valor_unitario=$2000`).
   - Line 3: `concepto='Lavado'`, `cantidad=1` (`valor_unitario=$10000` from vigente `otros_cobros`).
3. Operator confirms. Frontend POSTs `api_sucursal /facturas` with `{uuid_ingreso, uuid_salida, lineas: [{concepto, cantidad, valor_unitario}, ...], descuento: 0, pagos: [{medio_pago:'efectivo', valor:17000}]}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
5. Backend validates RBAC: operator must have `permiso='facturar'`.
6. Backend SELECTs vigente `tarifas_sucursal` / `otros_cobros` for each line to verify the posted `valor_unitario` matches the vigente catalog value (defense against UI tampering). If mismatch: return 422 with detail.
7. INSERT `facturas` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso`, `uuid_salida`, `subtotal=17000, descuento=0, total=17000`, `estado='activa'` derived, `fecha_retencion_hasta=$created_at + 5_years`).
8. For each line: INSERT `factura_detalle` row (`uuid_sucursal=$branch`, `uuid_factura=$factura_uuid`, `concepto`, `cantidad`, `valor_unitario=$snapshot`, `subtotal=$cantidad * $snapshot`).
9. INSERT `factura_pagos` row(s) per payment (T36 use case 7.1-7.3).
10. INSERT `factura_impuestos` rows per applicable tax (T37 use case 7.1).
11. INSERT `log_transaccional` (`accion='factura_creada'`, `tabla_afectada='facturas'`, `uuid_registro_afectado=$factura_uuid`).
12. INSERT `log_transaccional` (`accion='factura_detalle_creado'`, `tabla_afectada='factura_detalle'`, `uuid_registro_afectado=$detalle_uuid`, `datos_nuevos={concepto, cantidad, valor_unitario, subtotal}`) — one per line.
13. `queue_processor.enqueue('facturas', $uuid, $snapshot)` + `enqueue('factura_detalle', $detalle_uuid, $snapshot)` × N + `enqueue('factura_pagos', ...)` + `enqueue('factura_impuestos', ...)`.
14. Online DIAN flow (if branch online): POST `/api_admin/facturas/procesar` with the `facturas` row; cloud INSERTs `factura_electronica` + updates branch via SyncBackEvent. Offline flow: branch prints `numero_temporal`; SyncBackEvent arrives later.
15. Operator UI shows the new factura with line items + total + DIAN number (online) or `preliminar` badge (offline).

**Tables touched (writes)**: `facturas` (1 row), `factura_detalle` (N rows), `factura_pagos` (1+ rows), `factura_impuestos` (0+ rows), `factura_electronica` (cloud-side, online flow), `log_transaccional` (2+N rows), `sync_queue` (2+N items).
**Tables touched (reads)**: `tarifas_sucursal` (vigente, snapshot lookup), `otros_cobros` (vigente), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `ingreso` (parent), `salidas` (parent), `usuarios` (operator), `sucursal` (tenant).
**FKs traversed**: `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`; `factura_detalle.uuid_factura` → `facturas.uuid`; `factura_detalle.uuid_sucursal` → `sucursal.uuid`; `factura_pagos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_impuesto` → `impuestos.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `facturas.uuid` / `factura_detalle.uuid` / etc.

**Sync behavior**:
- Branch → cloud: YES — all rows enqueued; cloud receives within 30s.
- Cloud → branch: YES (SyncBackEvent with `numero_oficial`, online flow only).
- DIAN trigger: YES (online flow → `dian_dispatcher` enqueued; offline flow → SyncBackEvent triggers later dispatch).
- Hash chain impact: YES — branch chain extends by 2+N rows; cloud chain extends correspondingly.

**Integration with other tables**:
- Reads from: `tarifas_sucursal` (snapshot lookup), `otros_cobros` (snapshot), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `ingreso`, `salidas`, `usuarios`, `sucursal`.
- Writes to: `facturas`, `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_electronica` (cloud), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **canonical facturacion flow**. The snapshot semantic is enforced at INSERT time: `valor_unitario` is the value the operator confirmed, validated against vigente catalog at server-side.
- Related: T05 (`facturas`) covers the parent factura lifecycle; T36 (`factura_pagos`) covers payments; T37 (`factura_impuestos`) covers taxes; T03 (`factura_electronica`) covers the DIAN representation.

### 7.2 Use Case: `uc.factura-detalle.tarifa-archived-post-facturacion-detail-unaffected`

**Actor**: admin (cloud) + system (snapshot semantic invariant)

**Real-world action**: Admin archives an old `tarifas_sucursal` version (sets `vigente_hasta=NOW()`) AFTER a factura was already created with that tarifa. The `factura_detalle.valor_unitario` remains unchanged (snapshot semantic). Admin runs an audit query: "Show me all facturas using the archived tarifa" — the answer is the `factura_detalle` rows where the snapshot value matches the archived value (or the catalog UUID matches, when sprint 5 adds `uuid_tarifa_sucursal_snapshot`).

**Steps**:
1. Admin opens `web_admin/TarifasSucursalList/{uuid}/Detail`, clicks `Archivar versión`.
2. Frontend PATCHes `api_admin /tarifas-sucursal/{uuid}` with `{vigente_hasta=NOW()}` (archives the old version; new version may be INSERTed by admin with the new value).
3. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
4. UPDATE current vigente row SET `vigente_hasta=$now` (T14 versioning pattern).
5. (Optional) INSERT new `tarifas_sucursal` row with `vigente_desde=$now, vigente_hasta=NULL`.
6. INSERT `log_transaccional` (`accion='tarifa_archivada'`, `tabla_afectada='tarifas_sucursal'`, `datos_anteriores=$old, datos_nuevos=$new_if_any`).
7. `queue_processor.enqueue('tarifas_sucursal', $uuid, $new_snapshot)` — parametrization push to all branches.
8. **Existing `factura_detalle` rows are UNAFFECTED**: their `valor_unitario` snapshot is unchanged. The invoice still shows the historical price.
9. Admin runs audit query: `SELECT fd.* FROM factura_detalle fd JOIN facturas f ON fd.uuid_factura=f.uuid WHERE fd.uuid_sucursal=$branch AND fd.concepto='Auto - Por hora' AND fd.valor_unitario=$archived_value` — returns the facturas using the old tarifa. (Sprint 5: JOIN also on `uuid_tarifa_sucursal_snapshot` for exact catalog identification.)
10. The audit confirms: "12 facturas between 2026-01-01 and 2026-06-30 used the old $5000 tarifa; their `factura_detalle.valor_unitario` snapshots remain at $5000 regardless of the new vigente value."

**Tables touched (writes)**: `tarifas_sucursal` (archive + optional new version), `log_transaccional` (audit), `sync_queue` (parametrization).
**Tables touched (reads)**: `factura_detalle` (audit query, unchanged), `facturas` (audit JOIN), `tarifas_sucursal` (current vigente, archived version).
**FKs traversed**: `tarifas_sucursal.uuid_sucursal` → `sucursal.uuid`; `factura_detalle.uuid_sucursal` → `sucursal.uuid`; `factura_detalle.uuid_factura` → `facturas.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the archived + new version to all branches within 30s.
- DIAN trigger: NO (tarifa changes don't dispatch DIAN; only `factura_electronica` creation does).
- Hash chain impact: YES — cloud chain extends by 1-2 rows (tarifa archivada + new if any); each branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `factura_detalle` (audit), `facturas` (audit), `tarifas_sucursal` (vigente, archived).
- Writes to: `tarifas_sucursal` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **snapshot semantic invariant**. The factura_detalle.valor_unitario is FOREVER the value at the moment of facturacion. No retroactive re-evaluation, no JOIN cascade, no UPDATE. This is the same pattern as `factura_impuestos.porcentaje_aplicado` (T37) and `reimpresion_ticket.costo_aplicado` (T38).
- Related: T14 (`tarifas_sucursal`) use case 7.1 covers the versioning pattern; T37 (`factura_impuestos`) use case 7.2 covers the same snapshot invariant for taxes.

### 7.3 Use Case: `uc.factura-detalle.cloud-dian-receives-snapshot-values-directly`

**Actor**: dian_dispatcher (cloud worker)

**Real-world action**: Cloud receives the `facturas` row + N `factura_detalle` rows from a branch via sync (offline mode) or via online `/facturas/procesar`. The `dian_dispatcher` cloud worker builds the DIAN XML/JSON payload directly from the `factura_detalle.valor_unitario` snapshot values — NO JOIN to `tarifas_sucursal` is performed. This is critical for DIAN compliance: the DIAN representation must reflect EXACTLY what was billed, regardless of any subsequent catalog changes.

**Steps**:
1. Cloud receives the batch (offline) or online POST.
2. Cloud processes per-item:
   a. INSERT `facturas` row (idempotent on UUID).
   b. INSERT each `factura_detalle` row (idempotent on UUID).
   c. INSERT each `factura_pagos` row.
   d. INSERT each `factura_impuestos` row.
3. Cloud opens TX; SELECT `empresa` FOR UPDATE for atomic `consecutivo` increment (T21 use case 7.2).
4. Cloud INSERTs `factura_electronica` with `consecutivo=$new, reportado_dian=false, fecha_retencion_hasta=$created_at + 5_years`.
5. Cloud INSERTs `log_transaccional` rows (`consecutivo_asignado`, `factura_electronica_creada`).
6. Cloud enqueues `dian_dispatcher` task.
7. `dian_dispatcher` worker picks up the task; reads `factura_electronica` + `factura_detalle` (snapshot values) + `factura_pagos` + `factura_impuestos` (snapshot values).
8. Worker builds DIAN XML/JSON payload: `<Invoice><Lines><Line><Description>{concepto}</Description><Quantity>{cantidad}</Quantity><UnitPrice>{valor_unitario snapshot}</UnitPrice><Subtotal>{subtotal}</Subtotal></Line>...</Lines></Invoice>`.
9. **NO JOIN to `tarifas_sucursal`**: the snapshot values are authoritative. Even if `tarifas_sucursal.valor` has changed since the factura was created, the DIAN payload uses the historical snapshot.
10. Worker POSTs to DIAN provider API with the payload + signature.
11. DIAN responds with `CUFE` (electronic invoice unique code) and acceptance status.
12. Worker UPDATE `factura_electronica SET reportado_dian=true, cufe=$cufe, fecha_reporte_dian=NOW()` — wait, this is `[L-E]` and NEVER updated. Correction: the response is captured in a SEPARATE `[A]` table (T03 concept: `reporte_dian_log` or similar) — sprint 5 decision. For now: `reportado_dian=true` is captured in `factura_electronica.estado` derived from the existence of the DIAN log row.
13. Worker INSERTs `log_transaccional` (`accion='dian_aceptada'`, `datos_nuevos={cufe, fecha_aceptacion}`).
14. Worker INSERTs `SyncBackEvent` (concept) for the branch with the `cufe` + `numero_oficial`.

**Tables touched (writes — cloud side)**: `factura_electronica` (1 row), `empresa` (atomic UPDATE), `log_transaccional` (2+ rows), `dian_dispatcher` queue, `SyncBackEvent` (concept), `reporte_dian_log` (sprint 5).
**Tables touched (writes — branch side, from sync)**: `facturas`, `factura_detalle`, `factura_pagos`, `factura_impuestos` (idempotent INSERTs).
**Tables touched (reads)**: `factura_electronica` (read for DIAN payload), `factura_detalle` (snapshot values, NO JOIN to catalog), `factura_pagos`, `factura_impuestos`, `empresa` (atomic lock), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: per row (varies); `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES (the originating batch).
- Cloud → branch: YES (SyncBackEvent with CUFE + numero_oficial).
- DIAN trigger: YES (this IS the DIAN dispatch flow).
- Hash chain impact: YES — both branch and cloud chains extend for the receipt + dispatch.

**Integration with other tables**:
- Reads from: `factura_electronica`, `factura_detalle` (snapshot), `factura_pagos` (snapshot), `factura_impuestos` (snapshot), `empresa`, `log_transaccional`, `sucursal`.
- Writes to: `factura_electronica`, `empresa`, `log_transaccional`, `dian_dispatcher`, `SyncBackEvent`, `reporte_dian_log` (sprint 5).
- Cross-cutting: this is the **DIAN compliance backbone**. The snapshot semantic in `factura_detalle` is what makes the DIAN representation legally valid: the values billed match the values reported, with no dependency on current catalog state.
- Related: T03 (`factura_electronica`) use case 7.x covers the full DIAN flow; T37 (`factura_impuestos`) use case 7.3 covers the same snapshot pattern for taxes.

### 7.4 Use Case: `uc.factura-detalle.admin-cross-branch-detalle-report-by-snapshot-value`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/CrossBranchDetalleReport`. Wants to see revenue by service across all branches, but filtered by the SNAPSHOT VALUE (not the current catalog value). For example: "How much revenue did we get from 'Auto - Por hora' across all branches in 2026, billed at the OLD $5000 tarifa (which was vigente Jan-Jun)?" The query JOINs `factura_detalle` to `facturas` and aggregates by snapshot value, NOT by current `tarifas_sucursal.valor`.

**Steps**:
1. Admin opens `web_admin/CrossBranchDetalleReport`.
2. Admin sets filters: `fecha_desde=2026-01-01, fecha_hasta=2026-12-31, concepto='Auto - Por hora', valor_unitario=5000, uuid_sucursal=ANY`.
3. Frontend GETs `api_admin /reportes/detalle?desde=&hasta=&concepto=&valor_unitario=&uuid_sucursal=&limit=`.
4. Backend runs:
   ```sql
   SELECT fd.uuid_sucursal, s.nombre AS sucursal_nombre,
          COUNT(DISTINCT fd.uuid_factura) AS num_facturas,
          SUM(fd.cantidad) AS total_cantidad,
          SUM(fd.subtotal) AS revenue_total
   FROM factura_detalle fd
   JOIN facturas f ON fd.uuid_factura = f.uuid
   JOIN sucursal s ON fd.uuid_sucursal = s.uuid
   WHERE fd.concepto = $concepto
     AND fd.valor_unitario = $valor_unitario  -- SNAPSHOT value
     AND f.created_at BETWEEN $desde AND $hasta
   GROUP BY fd.uuid_sucursal, s.nombre
   ORDER BY revenue_total DESC;
   ```
5. UI renders a table: per-branch rows with num_facturas, total_cantidad, revenue_total. Color-coded: branches where the snapshot value is no longer vigente (the archived $5000 tarifa) show a yellow badge "Archived tarifa".
6. Admin clicks a row → drill-down to the individual `factura_detalle` rows.
7. (Optional) Admin exports to CSV/Excel for offline reporting (BI tool, finance audit).
8. (Optional) Admin compares with `tarifas_sucursal.valor` vigente in the same period: `SELECT vigente_desde, vigente_hasta, valor FROM tarifas_sucursal WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$auto AND uuid_tipo_tarifa=$hora AND vigente_desde <= $hasta AND (vigente_hasta IS NULL OR vigente_hasta >= $desde) ORDER BY vigente_desde` — confirms the snapshot value matches the vigente at the moment of facturacion.

**Tables touched (writes)**: NONE for the read.
**Tables touched (reads)**: `factura_detalle` (snapshot values), `facturas` (date filter), `sucursal` (display), `tarifas_sucursal` (optional vigente lookup for cross-validation).
**FKs traversed**: `factura_detalle.uuid_factura` → `facturas.uuid`; `factura_detalle.uuid_sucursal` → `sucursal.uuid`; `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid` (display only).

**Sync behavior**:
- Branch → cloud: NO (read of historical data).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `factura_detalle` (snapshot), `facturas`, `sucursal`, `tarifas_sucursal` (optional cross-validation).
- Writes to: NONE.
- Cross-cutting: this is the **snapshot-driven reporting** view. By filtering on `valor_unitario` (snapshot), admin gets the historical revenue picture regardless of catalog evolution. This is the **inverse** of catalog-driven reporting: instead of "how much did we bill at the current $5500 tarifa?", it's "how much did we bill when the tarifa was $5000?"
- Related: T37 (`factura_impuestos`) use case 7.4 covers the same snapshot-driven reporting for taxes.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers), 3 (partitioning via `pg_partman` — partitionable by month), 5 (audit constraints — REVOKE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin FacturaDetail + CrossBranchDetalleReport), 14 (web_sucursal FacturacionForm), 15 (shadcn UI components for forms), 20 (structlog), 21 (Prometheus counters), 24 (pytest), 28 (docker compose), 29 (DIAN provider), 30 (cron — none specifically for detalle), 33 (DIAN compliance docs).

## 9. RED Tests
- (RED) INSERT `factura_detalle` from `rol_app` → success.
- (RED) UPDATE `prod.factura_detalle` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.factura_detalle` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Snapshot semantic: archive `tarifas_sucursal` after factura creation → `factura_detalle.valor_unitario` is UNCHANGED.
- (RED) Multi-line factura: `facturas.total = SUM(factura_detalle.subtotal) - facturas.descuento + SUM(factura_impuestos.valor)` invariant.
- (RED) DIAN payload uses `factura_detalle.valor_unitario` snapshot directly; NO JOIN to `tarifas_sucursal` in `dian_dispatcher` query path.
- (RED) `subtotal = cantidad * valor_unitario` invariant at INSERT time.
- (RED) `fecha_retencion_hasta = created_at + 5 years` for all rows.
- (RED) Cross-branch report filters by snapshot value, NOT by catalog current value.
- (RED) Admin report NEVER writes to `factura_detalle` (read-only).
- (RED) Synchronous TX: `facturas` + `factura_detalle` + `factura_pagos` + `factura_impuestos` all in one TX. ROLLBACK on any failure.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger.
- [ ] F1.x `detalle_writer.py::write_detalle()` helper.
- [ ] F1.x Partition setup (partitionable by month on `created_at`; sprint 5 may activate).
- [ ] IT-4.x: `parkos_core/facturacion/facturacion_endpoint.py::POST /facturas` orchestrates full facturacion flow.
- [ ] IT-4.x: server-side validation that posted `valor_unitario` matches vigente `tarifas_sucursal.valor`.
- [ ] IT-4.x: `api_sucursal/routers/facturas.py::POST /facturas` (operator endpoint).
- [ ] IT-4.x: `api_admin/routers/facturas.py::GET /facturas/{uuid}/detalle`.
- [ ] IT-4.x: `web_sucursal/FacturacionForm` with multi-line entry + tariff dropdown auto-populating snapshot value.
- [ ] IT-4.x: `web_admin/FacturaDetail` with line-by-line view showing snapshot values.
- [ ] IT-4.x: `web_admin/CrossBranchDetalleReport` with snapshot value filtering.
- [ ] IT-4.x: `dian_dispatcher` reads snapshot values directly (no JOIN to `tarifas_sucursal`).
- [ ] Sprint 5: `uuid_tarifa_sucursal_snapshot` column for exact catalog identification.
- [ ] Sprint 5: activate `pg_partman` monthly partitioning on `created_at`.
- [ ] Sprint 5: `reporte_dian_log` separate `[A]` table for DIAN acceptance audit.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator bypasses server-side validation (UI tampering) | Low | Server validates `valor_unitario` against vigente catalog; mismatch returns 422 |
| Admin archives the wrong `tarifas_sucursal` version (current vs historical) | Low | UI shows confirmation modal with the vigente range; archive action requires explicit confirm + audit row |
| DIAN payload uses current catalog value instead of snapshot | Low | Code review + RED test enforces no JOIN; DIAN payload builder is a dedicated module with explicit contract |
| Multi-line factura totals mismatch (`facturas.total` doesn't sum `factura_detalle`) | Low | Server-side computation + invariant check at INSERT time; UI re-displays for operator confirmation |
| Snapshot value drifts from catalog over time (e.g., admin manually corrects `tarifas_sucursal` after the fact) | Low | `[V]` versioning of `tarifas_sucursal` enforces history preservation; `factura_detalle.valor_unitario` is independent |
| High-volume branch generates many line items per factura (e.g., 100+ lines for B2B contract) | Low | Schema supports arbitrary N; no upper limit; partition handles scale |
| Cross-branch report query is slow on large partitions | Med | Index on `(concepto, valor_unitario, uuid_sucursal, created_at)` for filterable aggregation |

## 12. Open Questions
- (a) Should `concepto` be a free-text string or constrained to a catalog `conceptos_factura`? Currently free-text; sprint 5 may add catalog.
- (b) Should `valor_unitario` support fractional cents (e.g., $1234.56)? Currently decimal(10,2); aligns with DIAN.
- (c) Should there be a `descuento_por_linea` column (per-line discount in addition to `facturas.descuento` global)? Sprint 5.
- (d) Should `factura_detalle` be replicated to cloud as `factura_detalle_mirror` for read scaling? Currently direct read.
- (e) `uuid_tarifa_sucursal_snapshot` column: with or without FK? Sprint 5 — likely NO FK (snapshot semantic) but column for traceability.
- (f) Should the snapshot include the `tarifas_sucursal.uuid` of the specific version vigente at facturacion time (for bi-temporal queries)? Sprint 5.
- (g) Should refunds generate negative `factura_detalle` rows or a separate `factura_detalle_devolucion` table? Affects SUM in reporting.
