# PRD: arqueo (T34)

> Append-only cash session close record. Partitioned monthly; retention 5+ years (DIAN compliance + audit). Cross-validates `sesion` running totals against operator-reported counts. Triggers `alerta tipo_alerta='diferencia_arqueo'` workflow if `ABS(diferencia) > tolerancia` per `configuracion_tolerancias` vigente. Source of truth for the final cash state of each shift.

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
- **Table name**: `prod.arqueo`
- **SQL name**: `arqueo` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN compliance + audit, default `created_at + 5 years`)
- **Partitioning**: monthly on `created_at` (one row per shift per branch; ~1 row/branch/day)
- **Origin**: F1 (schema + REVOKE + trigger + monthly partition + DIAN retention) + IT-5 (writes per cash-session close)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- No polymorphic FKs; `uuid_sucursal` is the only business FK.
- Travel: branch-origin rows travel to cloud via `sync_queue` (as queue items, separate rows). Cloud receives and INSERTs verbatim. Partition pruning critical: queries by date range MUST hit one partition.
- **Correction pattern**: per AGENTS.md comment, "Si hay corrección del arqueo, se inserta una nueva fila con referencia al arqueo original (ver uuid_arquee_original si se agrega)". Sprint 5 may add explicit `uuid_arqueo_original` column for correction chains; currently correction is handled via `observaciones` text + a new `arqueo` row linked via `observaciones`.

## 3. SOLID Atomic Breakdown
- **S**: "one cash session close record" — INSERT in same TX as the sesion close UPDATE + the caja cierre snapshot.
- **O**: extensible via migration; new `motivo_correccion` enum values, `uuid_arqueo_original` FK for corrections.
- **I**: branch operator API (writer — single endpoint per cierre); admin read API (`ArqueosList`, paginated, filterable); auditor API (BYPASSRLS, read-only audit).
- **D**: `parkos_core/caja/arqueo_writer.py::write_arqueo(uuid_sucursal, uuid_sesion, valor_efectivo_reportado, valor_datafono_reportado, reportado_por, observaciones=None)` — the ONLY writer. Computes `diferencia_efectivo = reportado - esperado`, `diferencia_datafono = reportado - esperado` by SELECTing `factura_pagos` SUMs for the sesion.
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, arqueo history dies |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `alerta.uuid_arqueo` (FK) | n/a | 0..1 | `alerta tipo_alerta='diferencia_arqueo'` carries `uuid_arqueo` pointing to the offending arqueo row (T41 use case 7.x) |
| `documentos.uuid_referencia` (polymorphic) | n/a | 0..1 | optional PDF upload of printed arqueo (T13 use case 7.x) |
| `caja.observaciones` (text) | n/a | 0..1 | cierre caja snapshot stores `observaciones='sesion=$uuid, arqueo=$uuid'` for correlation (T33) |

**Note**: `arqueo` does NOT have an explicit `uuid_sesion` FK; correlation is via `observaciones` text + `created_at` proximity + `uuid_sucursal`. Sprint 5 may add explicit `uuid_sesion` column for unambiguous linking (same pattern as T33 `caja`).

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `arqueo_writer.py::write_arqueo()` per sesion close |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for DIAN retention |

**Special rules**:
- **Monthly partitioning**: `pg_partman` partitions by `created_at` month. Retention: 60 months (5 years).
- **`diferencia = reportado - esperado` semantic**: positive = sobrante (cash over); negative = faltante (cash short).
- **Tolerance check**: `if ABS(diferencia_efectivo) > tolerancia_efectivo OR ABS(diferencia_datafono) > tolerancia_datafono → INSERT alerta`. Tolerance is from `configuracion_tolerancias` vigente AT THE MOMENT OF ARQUEO (snapshot semantic; see T29 use case 7.3 — tolerance vigente at arqueo time is the one that governs, NOT a retroactive re-evaluation).
- **DIAN retention**: `fecha_retencion_hasta = created_at + 5 years` (per factura retention; aligned with `empresa.dias_retencion_empresa` default).
- **Correction pattern**: a NEW arqueo row is inserted with `observaciones='correccion de $uuid_arqueo_original'` and (sprint 5) explicit `uuid_arqueo_original` FK. The original row is NEVER modified.

## 6. CodeGraph Dependencies
- `parkos_core/caja/arqueo_writer.py::write_arqueo()` (sole writer).
- `api_sucursal/routers/arqueos.py::POST /arqueos` (operator cierre endpoint).
- `api_admin/routers/arqueos.py::GET /arqueos` (paginated, filterable).
- `api_admin/routers/arqueos.py::GET /arqueos/{uuid}` (single arqueo detail with related `alerta`, `sesion`).
- `api_admin/routers/arqueos.py::GET /arqueos/{uuid_sucursal}/cross-branch` (admin cross-branch dashboard).
- `parkos_core/caja/arqueo_pdf.py::generate_pdf(uuid)` (PDF generation for printable arqueo).
- `web_sucursal/CierreCajaForm` (cierre form with tolerance warning).
- `web_sucursal/ArqueosHistory` (own-branch arqueo list).
- `web_admin/ArqueosList` (cross-branch arqueo dashboard).
- `web_admin/ArqueosList/{uuid}/Detail` (single arqueo detail with alerta cross-link).
- `alerta tipo_alerta='diferencia_arqueo'` writer (via T41 use case 7.x).

## 7. Use Cases enabled by this table

The `arqueo` table is the **canonical cash session close record**: one row per sesion close, capturing `valor_efectivo_esperado`, `valor_efectivo_reportado`, and `diferencia_efectivo` (same for datafono). Triggers `alerta tipo_alerta='diferencia_arqueo'` if `ABS(diferencia) > tolerancia` vigente. Partitioned monthly for retention; DIAN retention 5+ years. **Manual operator input** for cash counts (no scanner, no OCR).

### 7.1 Use Case: `uc.arqueo.operator-cierre-sesion-writes-arquo-with-tolerance-check`

**Actor**: operator (branch)

**Real-world action**: Operator closes sesion via `web_sucursal/CierreCajaForm`. Counts cash in drawer (manual count), enters `valor_efectivo_reportado` and `valor_datafono_reportado`. Backend SELECTs vigente `configuracion_tolerancias`, computes `diferencia = reportado - esperado` (where `esperado = sesion.valor_inicial + SUM(factura_pagos WHERE uuid_sesion=$X)`), INSERTs `arqueo` row, INSERTs `caja` cierre snapshot, emits `alerta` if tolerance exceeded. The whole cierre flow is one TX: `sesion` UPDATE to cerrada + `arqueo` INSERT + `caja` INSERT + `log_transaccional` rows + (conditional) `alerta` INSERT.

**Steps**:
1. Operator opens `web_sucursal/CierreCajaForm`. Form pre-fills `valor_inicial_efectivo` from `sesion` apertura; shows `valor_esperado_efectivo` (= `valor_inicial + SUM(factura_pagos WHERE uuid_sesion=$X AND medio_pago='efectivo')`); same for datafono.
2. Operator counts cash in drawer; types `valor_efectivo_reportado = $48000` (vs expected $50000 → diferencia -$2000).
3. Operator checks datafono terminal report; types `valor_datafono_reportado = $125000` (vs expected $125000 → diferencia $0).
4. Frontend POSTs `api_sucursal /arqueos` with `{uuid_sesion, valor_efectivo_reportado: 48000, valor_datafono_reportado: 125000, observaciones: null}`.
5. Backend SELECTs vigente `configuracion_tolerancias` (T29) → `tolerancia_efectivo=$5000, tolerancia_datafono=$5000` (snapshot semantic: tolerance vigente at arqueo time).
6. Backend computes `diferencia_efectivo = 48000 - 50000 = -2000`, `diferencia_datafono = 125000 - 125000 = 0`.
7. Backend SELECTs open sesion: `SELECT * FROM sesion WHERE uuid=$uuid_sesion AND estado='abierta'` — rejects 409 if not open.
8. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
9. INSERT `arqueo` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `valor_efectivo_esperado=$50000, valor_datafono_esperado=$125000`, `valor_efectivo_reportado=48000, valor_datafono_reportado=125000`, `diferencia_efectivo=-2000, diferencia_datafono=0`, `fecha_retencion_hasta=$created_at + 5_years`, `observaciones=null`).
10. INSERT `log_transaccional` (`accion='arqueo_registrado'`, `tabla_afectada='arqueo'`, `uuid_registro_afectado=$arqueo_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_nuevos={valor_efectivo_esperado, valor_efectivo_reportado, diferencia_efectivo, diferencia_datafono, tolerancia_vigente}`).
11. If `ABS(diferencia_efectivo) > tolerancia_efectivo OR ABS(diferencia_datafono) > tolerancia_datafono`: INSERT `alerta` workflow chain root (`tipo_alerta='diferencia_arqueo'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_usuario=$operator`, `uuid_arqueo=$arqueo_uuid`, `valor_diferencia_efectivo=-2000, valor_diferencia_datafono=0`, `uuid_alerta_padre=NULL`, `observaciones='arqueo=$uuid, esperado=50000/125000, reportado=48000/125000'`). The alerta is a workflow root — admin will triage via `en_revision → resuelta` (T41).
12. INSERT `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alerta_uuid`, `datos_nuevos={tipo_alerta:'diferencia_arqueo', uuid_arqueo}`).
13. Call `snapshot_writer.write_snapshot($branch, 'cierre', valor_efectivo=48000, valor_datafono=125000, observaciones='sesion=$sesion_uuid, arqueo=$arqueo_uuid')` — INSERT `caja` row (T33 use case 7.4).
14. UPDATE `sesion` SET `estado='cerrada', timestamp_cierre=NOW()` (T43 — [L-S] operational exception with mandatory log).
15. INSERT `log_transaccional` (`accion='sesion_cerrada'`, `tabla_afectada='sesion'`, `uuid_registro_afectado=$sesion_uuid`).
16. `queue_processor.enqueue('arqueo', $uuid, $snapshot)` + `enqueue('caja', $caja_uuid, $snapshot)` + `enqueue('sesion', $sesion_uuid, $snapshot)` for propagation.
17. Operator UI: "Cierre registrado. Diferencia efectivo: -$2000 (tolerancia: $5000) → DENTRO DE TOLERANCIA. Caja cerrada." OR "ALERTA: Diferencia efectivo fuera de tolerancia. Admin revisará."

**Tables touched (writes)**: `arqueo` (1 row), `caja` (1 row cierre snapshot), `sesion` (UPDATE — [L-S]), `alerta` (1 row if tolerance exceeded), `log_transaccional` (3-4 rows), `sync_queue` (3 items).
**Tables touched (reads)**: `configuracion_tolerancias` (vigente), `sesion` (current), `factura_pagos` (SUM for expected), `log_transaccional` (chain anchor), `usuarios` (operator), `sucursal` (tenant).
**FKs traversed**: `arqueo.uuid_sucursal` → `sucursal.uuid`; `caja.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_arqueo` → `arqueo.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow root); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `arqueo.uuid` / `caja.uuid` / `sesion.uuid` / `alerta.uuid`.

**Sync behavior**:
- Branch → cloud: YES — arqueo + caja + sesion UPDATE propagate.
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 4-5 rows; cloud chain extends correspondingly.

**Integration with other tables**:
- Reads from: `configuracion_tolerancias` (vigente), `sesion` (current), `factura_pagos` (SUM), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
- Writes to: `arqueo`, `caja` (cierre snapshot), `sesion` (UPDATE), `alerta` (if exceeded), `log_transaccional` (audits), `sync_queue`.
- Cross-cutting: this is the canonical **cash-session end**. The cierre is atomic — all 4 writes happen in one TX. If any fails (e.g., log_transaccional hash chain break), the whole cierre rolls back; operator retries.
- Related: T29 (`configuracion_tolerancias`) use case 7.2 covers the tolerance check pattern; T41 (`alerta`) use case 7.x covers diferencia_arqueo workflow; T33 (`caja`) use case 7.4 covers the cierre snapshot.

### 7.2 Use Case: `uc.arqueo.tolerance-exceeded-emits-alerta-workflow`

**Actor**: system (within TX of use case 7.1) + admin (cloud, triage)

**Real-world action**: Within the arqueo INSERT (use case 7.1), if `ABS(diferencia) > tolerancia`, the system INSERTs `alerta` workflow chain root with `tipo_alerta='diferencia_arqueo'`, `estado='abierta'`, `uuid_arqueo=$arqueo_uuid`. The alerta's `uuid_arqueo` provides a direct FK from alerta to arqueo, enabling admin drill-down: "Show me the alerta → show me the arqueo → show me the related sesion and factura_pagos". Admin triages via `en_revision → resuelta` workflow chain (T41).

**Steps**:
1. Within arqueo TX (use case 7.1, step 11), INSERT `alerta` workflow root row.
2. The `alerta` row's `uuid_arqueo` FK directly references the offending arqueo — admin can JOIN `alerta` ON `uuid_arqueo` to get the arqueo detail in one query.
3. `alerta.observaciones` carries the human-readable summary: `arqueo=$uuid, esperado=50000/125000, reportado=48000/125000, tolerancia_vigente=5000/5000`.
4. `alerta.valor_diferencia_efectivo=-2000, valor_diferencia_datafono=0` — typed fields for filtering and reporting.
5. `log_transaccional` rows capture the full audit trail.
6. Operator UI shows the red banner; admin sees the alerta in `web_admin/AlertasList` (filterable by `tipo_alerta='diferencia_arqueo'`).
7. Admin clicks alerta → opens `AlertaDetail` showing the arqueo detail (cross-ref via `uuid_arqueo` FK).
8. Admin triages: transitions workflow `abierta → en_revision` (INSERT new alerta row with `uuid_alerta_padre=$root.uuid`, `estado='en_revision'`).
9. Admin investigates: views `factura_pagos` for the sesion (sum, individual transactions), `caja` snapshots (pre-cierre), `sesion` detail (apertura values, operator).
10. Admin resolves: transitions workflow `en_revision → resuelta` (INSERT new alerta row with `estado='resuelta'`, `observaciones='investigated: cash short due to late-evening refund not registered' or similar`).
11. The arqueo row is NEVER modified; the alerta workflow lives separately.

**Tables touched (writes — within use case 7.1 TX)**: `alerta` (1 root row + workflow chain rows on admin triage).
**Tables touched (writes — separate TX on admin triage)**: `alerta` (chain rows for `en_revision`, `resuelta`), `log_transaccional` (audit per transition).
**Tables touched (reads)**: `arqueo` (joined via `alerta.uuid_arqueo`), `factura_pagos`, `caja`, `sesion`, `log_transaccional` (chain anchor).
**FKs traversed**: `alerta.uuid_arqueo` → `arqueo.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain); `alerta.uuid_usuario` → `usuarios.uuid` (responsible admin).

**Sync behavior**:
- Branch → cloud: YES — the alerta propagates with the arqueo.
- Cloud → branch: NO (the alerta workflow is cloud-side triage; branch sees the initial banner only).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (alerta INSERT); cloud chain extends by N rows (N = workflow chain length, typically 3: abierta → en_revision → resuelta).

**Integration with other tables**:
- Reads from: `arqueo` (via `uuid_arqueo` FK), `factura_pagos`, `caja`, `sesion`, `log_transaccional`.
- Writes to: `alerta` (workflow chain), `log_transaccional` (audit).
- Cross-cutting: the `alerta.uuid_arqueo` FK is the direct linkage — admin drill-down is one JOIN. The workflow chain provides the audit trail of who reviewed when.
- Related: T41 (`alerta`) use case 7.x covers the diferencia_arqueo workflow in detail.

### 7.3 Use Case: `uc.arqueo.operator-prints-arquo-for-audit-archive`

**Actor**: operator (branch)

**Real-world action**: After cierre (use case 7.1), operator clicks "Imprimir Arqueo" in `web_sucursal/ArqueosHistory/{uuid}/Detail`. The backend generates a PDF of the arqueo summary (incl. sesion detail, factura_pagos totals, observaciones), returns it for printing. Optionally, the operator uploads the PDF to `documentos` (T13) as a 'arqueo_pdf' archive for cloud-side retention.

**Steps**:
1. Operator opens `web_sucursal/ArqueosHistory/{uuid}`.
2. Operator clicks `Imprimir Arqueo`.
3. Frontend GETs `api_sucursal /arqueos/{uuid}/pdf` (returns binary PDF stream).
4. Backend SELECTs `arqueo` row + JOIN `sesion` (apertura values, operator) + JOIN `factura_pagos` (SUM for the sesion, plus list of individual transactions).
5. Backend calls `arqueo_pdf.generate_pdf(...)` which renders a printable PDF using a Jinja2 template (or similar). The PDF includes: branch info (JOIN `sucursal` + `empresa` mirror for header), sesion info, arqueo values, expected vs reported, diferencia, observaciones, operator signature line, date.
6. Backend returns the PDF binary with `Content-Type: application/pdf`.
7. Frontend triggers browser print dialog. Operator prints.
8. (Optional) Operator clicks `Subir a Documentos` — POST `/arqueos/{uuid}/upload-pdf` with the PDF binary.
9. Backend INSERTs `documentos` row (`uuid_sucursal=$branch`, `tipo='arqueo_pdf'`, `formato='pdf'`, `documento_b64=$base64_pdf`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
10. INSERT `log_transaccional` (`accion='documento_arquo_subido'`, `tabla_afectada='documentos'`, `uuid_registro_afectado=$documento_uuid`, `datos_nuevos={uuid_arqueo, tipo:'arqueo_pdf'}`).
11. `queue_processor.enqueue('documentos', $uuid, $snapshot)` — propagates to cloud.

**Tables touched (writes — print only)**: NONE (PDF generation is read-only).
**Tables touched (writes — upload)**: `documentos` (1 row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `arqueo` (the row), `sesion` (JOIN), `factura_pagos` (SUM + list), `sucursal` (header), `empresa` (mirror for header), `usuarios` (operator display), `log_transaccional` (chain anchor for upload step).

**Sync behavior**:
- Branch → cloud: NO for print; YES for upload (documents table propagates).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO for print; YES for upload (chain extends by 1-2 rows).

**Integration with other tables**:
- Reads from: `arqueo`, `sesion`, `factura_pagos`, `sucursal`, `empresa` (mirror), `usuarios`, `log_transaccional` (for upload).
- Writes to: `documentos` (upload), `log_transaccional` (upload audit), `sync_queue` (upload propagation).
- Cross-cutting: the PDF is a printable, archivable artifact. The optional upload to `documentos` provides redundancy for cloud-side compliance audits (DIAN may request arqueo history).
- Related: T13 (`documentos`) covers the document archive pattern.

### 7.4 Use Case: `uc.arqueo.admin-cross-branch-history-report`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/ArqueosList` with filters: date range, branch, with-diferencia > tolerancia. Views cross-branch arqueo history for fraud detection (operator at one branch consistently reports short; or one branch always reports exact match while others have variance). The query is a paginated `SELECT * FROM arqueo WHERE uuid_sucursal IN (...) AND created_at BETWEEN ...`.

**Steps**:
1. Admin opens `web_admin/ArqueosList`. Default view: last 7 days, all active branches.
2. Frontend GETs `api_admin /arqueos?desde=&hasta=&uuid_sucursal=&con_diferencia=&limit=&cursor=`.
3. Backend runs paginated query with partition-friendly date predicates: `SELECT * FROM arqueo WHERE created_at >= $desde AND created_at < $hasta [AND uuid_sucursal=$branch] [AND ABS(diferencia_efectivo) > 0 OR ABS(diferencia_datafono) > 0] ORDER BY created_at DESC LIMIT 50`.
4. UI renders the list with: branch name (JOIN `sucursal`), operator (JOIN `sesion.uuid_usuario`), expected vs reported (split into efectivo/datafono), diferencia (color-coded: green if within tolerance, yellow if approaching, red if exceeded), alerta status (cross-ref `alerta.uuid_arqueo`).
5. Admin filters by `con_diferencia=true` to see all arqueos with any variance (regardless of tolerance).
6. Admin filters by branch: GET `/arqueos?uuid_sucursal=$branch&...` → focused view.
7. Admin clicks an arqueo → opens `ArqueoDetail` with: arqueo values, sesion detail (apertura), factura_pagos list, related `alerta` (if tolerance exceeded), related `documentos` (if PDF uploaded).
8. Admin exports to CSV/Excel for offline analysis.
9. Admin notices a pattern: operator X at branch Y has 10 arqueos in a row with `diferencia_efectivo = -$1000` (consistent short). Admin opens `reclamos` (T40) workflow to investigate — REQUIRES creating a new chain on `reclamos` referencing the operator's history.

**Tables touched (writes)**: NONE for the read. (Admin actions like creating `reclamos` are separate use cases.)
**Tables touched (reads)**: `arqueo` (filterable, paginated), `sucursal` (display), `sesion` (operator display), `usuarios` (display), `alerta` (cross-ref via `uuid_arqueo`), `documentos` (PDF cross-ref via polymorphic `uuid_referencia` — sprint 5 column), `factura_pagos` (drill-down).
**FKs traversed**: `arqueo.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`; `alerta.uuid_arqueo` → `arqueo.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read of historical data).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `arqueo` (the main table), `sucursal`, `sesion`, `usuarios`, `alerta`, `documentos`, `factura_pagos`.
- Writes to: NONE.
- Cross-cutting: this is the **fraud detection** view. Admin uses it to identify patterns of cash mishandling, which may lead to operator retraining, `reclamos` (T40) investigation, or `usuarios` deactivation (T07).
- Related: T40 (`reclamos`) use case 7.4 covers admin rejection of a problematic operator's claim; T07 (`usuarios`) use case 7.x covers operator deactivation.

### 7.5 Use Case: `uc.arqueo.diian-retention-purge-after-5-years`

**Actor**: system (retention worker)

**Real-world action**: Nightly worker scans `arqueo` for rows where `fecha_retencion_hasta < NOW()`. For each, it physically DELETEs the row (operational exception: DELETE allowed on rows past retention, similar to `sync_conflict` retention). The DELETE is permitted because the row's DIAN retention period has expired (5 years). Each deletion is logged via `log_transaccional` for forensic traceability of what was purged when.

**Steps**:
1. `workers/arqueo_retention/__main__.py` runs nightly at 02:00 cloud time (cron, after `hash_chain_verifier`).
2. SELECT rows to purge: `SELECT uuid FROM arqueo WHERE fecha_retencion_hasta < NOW()`.
3. For each row: physically DELETE — maintenance role with explicit DELETE grant. The deletion is logged via a NEW `log_transaccional` row (the deleted one is gone).
4. INSERT `log_transaccional` (`accion='arqueo_purged'`, `tabla_afectada='arqueo'`, `uuid_registro_afectado=$deleted_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch_of_deleted_arqueo`, `datos_anteriores={valor_efectivo_esperado, valor_datafono_esperado, valor_efectivo_reportado, valor_datafono_reportado, diferencia_efectivo, diferencia_datafono, fecha_retencion_hasta, created_at}`).
5. The `log_transaccional` row itself has its own `fecha_retencion_hasta` (separate retention policy for log_transaccional — typically 5-10 years).

**Tables touched (writes)**: `arqueo` (DELETE — maintenance exception on rows past retention), `log_transaccional` (1 row per purge).
**Tables touched (reads)**: `arqueo` (rows to purge), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `arqueo.uuid_sucursal` → `sucursal.uuid` (pre-delete lookup); `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is cloud-internal retention).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row per purged arqueo. The chain NEVER references the deleted row (since the row is gone), but the purge audit row is part of the chain for forensic completeness.

**Integration with other tables**:
- Reads from: `arqueo` (rows to purge), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `arqueo` (DELETE — maintenance exception), `log_transaccional` (purge audit).
- Cross-cutting: this is the **retention lifecycle** for `arqueo`. Unlike `sync_log`/`caja`/`sync_conflict` with shorter retention, `arqueo` has DIAN-driven 5+ year retention. The DELETE is reserved for the maintenance role, NOT `rol_app`.
- Related: T02 (`revocacion_factura`) and T05 (`facturas`) have similar DIAN retention patterns; the maintenance DELETE pattern is shared infrastructure.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers), 3 (partitioning via `pg_partman`), 5 (audit constraints — REVOKE + maintenance role for DELETE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin ArqueosList), 14 (web_sucursal CierreCajaForm + ArqueosHistory), 15 (shadcn UI components for forms), 16 (Zustand cash state), 20 (structlog), 21 (Prometheus counters — arqueos per branch per day), 24 (pytest), 28 (docker compose for cron), 30 (retention worker cron), 33 (DIAN compliance docs).

## 9. RED Tests
- (RED) INSERT `arqueo` from `rol_app` → success.
- (RED) UPDATE `prod.arqueo` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE from `rol_app` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE from maintenance role on row past retention → success; `log_transaccional` row written.
- (RED) Tolerance check: `diferencia_efectivo = reportado - esperado` (sign convention verified).
- (RED) Tolerance exceeded (within tolerance: no alerta; exceeded: alerta emitted).
- (RED) Tolerance snapshot semantic: arqueo uses tolerance vigente at arqueo time, NOT current tolerance.
- (RED) Cierre is atomic: sesion UPDATE + arqueo INSERT + caja INSERT + alerta (conditional) all in one TX. ROLLBACK on any failure.
- (RED) `alerta.uuid_arqueo` FK points to the correct arqueo row.
- (RED) `fecha_retencion_hasta = created_at + 5 years` for all rows.
- (RED) Partition pruning: query `WHERE created_at >= '2026-08-01' AND created_at < '2026-09-01'` → EXPLAIN shows single partition hit.
- (RED) `pg_partman` retention: rows older than 60 months are dropped automatically; `log_transaccional` audit row written per purge.
- (RED) Cross-branch admin query NEVER writes to `arqueo` (read-only).
- (RED) PDF generation returns valid PDF binary; upload to `documentos` creates `tipo='arqueo_pdf'` row.
- (RED) Correction pattern: new arqueo row references `uuid_arqueo_original` (sprint 5) or via `observaciones` text; original row is NEVER modified.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + monthly `pg_partman` partition.
- [ ] F1.x `arqueo_writer.py::write_arqueo()` helper.
- [ ] F1.x Partition retention policy (60 months) — automated purge via `pg_partman`.
- [ ] F1.x Maintenance role for DELETE on retention-purged rows.
- [ ] IT-5.x: `api_sucursal/routers/arqueos.py::POST /arqueos` (operator cierre endpoint).
- [ ] IT-5.x: tolerance check integration with `configuracion_tolerancias` snapshot semantic.
- [ ] IT-5.x: `alerta tipo_alerta='diferencia_arqueo'` emission on tolerance exceeded.
- [ ] IT-5.x: `api_sucursal/routers/arqueos.py::GET /arqueos/{uuid}/pdf` (PDF generation).
- [ ] IT-5.x: `api_sucursal/routers/arqueos.py::POST /arqueos/{uuid}/upload-pdf` (archive to documentos).
- [ ] IT-5.x: `api_admin/routers/arqueos.py::GET /arqueos` (paginated, filterable).
- [ ] IT-5.x: `api_admin/routers/arqueos.py::GET /arqueos/{uuid}` (detail with alerta + documentos cross-link).
- [ ] IT-5.x: `api_admin/routers/arqueos.py::GET /arqueos/{uuid_sucursal}/cross-branch` (cross-branch dashboard).
- [ ] IT-5.x: `web_sucursal/CierreCajaForm` with tolerance warning.
- [ ] IT-5.x: `web_sucursal/ArqueosHistory` (own-branch arqueo list).
- [ ] IT-5.x: `web_admin/ArqueosList` (cross-branch arqueo dashboard).
- [ ] IT-5.x: `web_admin/ArqueosList/{uuid}/Detail` (single arqueo detail).
- [ ] IT-5.x: `workers/arqueo_retention/__main__.py::purge_expired_arqueos()` nightly cron at 02:00 cloud.
- [ ] Sprint 5: explicit `uuid_sesion` column on `arqueo`.
- [ ] Sprint 5: explicit `uuid_arqueo_original` column for correction chains.
- [ ] Sprint 5: `documentos.uuid_referencia` polymorphic FK for direct PDF linkage.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Tolerance miscalibration: too tight → false positives (alertas flood); too loose → real variance missed | Med | Tolerance is configurable via `configuracion_tolerancias`; admin monitors alerta rate; sprint 5: per-branch tolerance overrides |
| Operator types wrong `valor_efectivo_reportado` (typo) | Low | Form requires confirmation modal; arqueo correction via new row + `uuid_arqueo_original` (sprint 5) |
| Tolerance vigente at arqueo time differs from current after admin update | Low | Snapshot semantic enforced: tolerance at arqueo moment is the one that governs (T29 use case 7.3) |
| PDF generation breaks (template error, encoding issue) | Low | PDF generation is read-only; failure to generate doesn't affect the arqueo INSERT (already committed); operator can retry |
| Partition purge deletes a row under active admin investigation | Low | UI shows "mark as in_investigation" flag that exempts row from purge; audit logs the exemption |
| `alerta.uuid_arqueo` FK breaks the alerta's tenant isolation (alerta.uuid_sucursal must match arqueo.uuid_sucursal) | Low | Trigger validates FK consistency; UI shows cross-link only within tenant |
| Operator disables tolerance check by manipulating frontend | Low | Tolerance check is server-side; UI is presentation only |
| High-volume branch generates many arqueos (multi-shift) — partition growth | Low | 1 row per shift per branch = ~30 rows/branch/month; 60 months × 30 branches = ~54K rows; trivial |
| Cierre TX fails halfway (e.g., log_transaccional hash chain break) | Low | Whole TX rolls back; operator retries; sesion remains 'abierta' |

## 12. Open Questions
- (a) Should tolerance be absolute (e.g., $5000) or relative (e.g., 1% of expected)? Current: absolute.
- (b) Should multiple arqueos per sesion be allowed (mid-shift closures)? Currently NO — one arqueo per sesion, sesion UPDATE to cerrada is the atomic end.
- (c) Should `diferencia_datafono` ever generate alerts? Currently yes (same tolerance check); some businesses might allow datafono variance without alert.
- (d) PDF template: Spanish or bilingual (es-CO default per i18n)? Sprint 5.
- (e) Cross-branch dashboard: should it aggregate by operator (fraud detection) or by branch (operational variance)? Both views needed.
- (f) Should `arqueo` rows be replicated to branches (read-only mirror) or kept cloud-only? Currently cloud-only (branches see their own via own DB).
- (g) Refunds during shift: counted as negative `factura_pagos` or separate? Affects SUM computation in `valor_esperado`.
- (h) Mid-shift operator change: do we record operator A's cierre and operator B's apertura as separate arqueos, or one arqueo spanning the operator change?
