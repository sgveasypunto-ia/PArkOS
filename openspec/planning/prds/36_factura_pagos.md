# PRD: factura_pagos (T36)

> Append-only payment records of a `facturas` row. Supports single + mixed payments (multiple `medio_pago` for one factura). Snapshot of the payment event at the moment of receipt — timestamp_evento, valor, medio_pago, referencia (for datafono). Source of truth for cross-validation against `arqueo` at sesion cierre (T34).

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
- **Table name**: `prod.factura_pagos`
- **SQL name**: `factura_pagos` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN + arqueo integration)
- **Partitioning**: partitionable by month on `created_at` (one or more rows per factura)
- **Origin**: F1 (schema + REVOKE + trigger) + IT-4 (writes per facturacion)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_sucursal` is denormalized (transitive via `facturas.uuid_sucursal`) for partition pruning + RLS-style filtering.
- Travel: branch-origin rows travel to cloud via `sync_queue`. Cloud receives and INSERTs verbatim.
- **NO snapshot semantic on `valor`**: the payment value is the actual cash/datafono received at the moment. NOT a snapshot of a catalog — there's no catalog for payment values. The payment event IS the source.
- **`referencia` for datafono**: the terminal authorization code (e.g., `AUTH123`). NULL for `efectivo`. This is a soft constraint (NOT a DB-level FK), validated at INSERT time.

## 3. SOLID Atomic Breakdown
- **S**: "one payment received for a factura" — INSERT in same TX as the parent `facturas` row + `factura_detalle` + `factura_impuestos`.
- **O**: extensible via migration; new `medio_pago` enum values (`transfer`, `check`, `crypto`) added as business grows.
- **I**: branch operator API (writer — single endpoint per facturacion); admin read API (FacturaDetail, ArqueoDetail cross-link); `arqueo_writer` reads for SUM at cierre.
- **D**: `parkos_core/facturacion/pago_writer.py::write_pago(uuid_factura, uuid_sucursal, medio_pago, valor, referencia=None, timestamp_evento=None)` — the ONLY writer. Idempotent on (uuid_factura, medio_pago, timestamp_evento) tuple to prevent duplicate payment inserts on retry.
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, payment history dies |
| `uuid_factura` | `prod.facturas.uuid` | exactly one (NOT NULL) | CASCADE | if factura deleted (never), pagos die |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (none — `factura_pagos` is a leaf; no other table references it via FK) | | | |

**Note**: `factura_pagos` is referenced by REPORTS (e.g., `arqueo` cross-validation SUMs via `uuid_sucursal + uuid_sesion + medio_pago`), not by FKs. The relationship is query-time, not DB-enforced.

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `pago_writer.py::write_pago()` per payment per factura |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for DIAN + arqueo audit |

**Special rules**:
- **`medio_pago` enum**: `efectivo`, `datafono`, `transfer` (sprint 5), `check` (sprint 5). Adding new values requires migration.
- **`referencia` constraint**: NULL for `efectivo`, NON-NULL for `datafono` (the terminal authorization code). Enforced at INSERT time via trigger or application validation.
- **Multi-payment invariant**: `SUM(factura_pagos WHERE uuid_factura=$X) >= facturas.total` (overpayment allowed for change; underpayment is `pago_parcial`, see use case 7.3). For exact payment: `SUM = facturas.total`.
- **`timestamp_evento` vs `created_at`**: `timestamp_evento` is when the payment was received in caja (business event); `created_at` is when the DB registered the row (can differ during offline-sync delay).
- **DIAN retention**: `fecha_retencion_hasta = created_at + 5 years`.

## 6. CodeGraph Dependencies
- `parkos_core/facturacion/pago_writer.py::write_pago()` (sole writer).
- `parkos_core/facturacion/facturacion_endpoint.py::POST /facturas` (orchestrates full facturacion flow including pagos).
- `api_sucursal/routers/facturas.py::POST /facturas` (operator endpoint).
- `api_sucursal/routers/facturas.py::POST /facturas/{uuid}/pago` (additional payment for pago parcial or datafono retry).
- `api_sucursal/routers/datafono.py::POST /datafono/retry` (datafono retry handler — T36 use case 7.4).
- `api_admin/routers/facturas.py::GET /facturas/{uuid}/pagos` (admin detail view).
- `api_sucursal/routers/facturas.py::GET /facturas/{uuid}/pagos` (own-branch view).
- `parkos_core/caja/arqueo_writer.py::read_pagos(uuid_sesion, medio_pago)` (SUM at cierre, T34 use case 7.1).
- `web_sucursal/FacturacionForm` (payment entry: medio_pago dropdown, valor, referencia for datafono).
- `web_sucursal/DatafonoRetry` (datafono failure handling UI).
- `web_admin/FacturaDetail` (payment list per factura).

## 7. Use Cases enabled by this table

The `factura_pagos` table is the **append-only payment record** of every factura. Supports single + mixed payments (one factura can have multiple `factura_pagos` rows with different `medio_pago`). Snapshot of the payment event at the moment of receipt: `timestamp_evento` (business) + `valor` + `medio_pago` + `referencia` (for datafono authorization). **No cámaras, no OCR, no QR**: payment entry is from operator input (manual cash count + datafono terminal).

### 7.1 Use Case: `uc.factura-pagos.single-pago-efectivo`

**Actor**: operator (branch)

**Real-world action**: Operator processes a simple cash payment for a factura. Customer hands over $17000 cash; operator types the amount into `FacturacionForm`, selects `medio_pago='efectivo'`, references=NULL (no terminal authorization). Backend INSERTs one `factura_pagos` row with `valor=17000, medio_pago='efectivo', referencia=NULL, timestamp_evento=NOW()`.

**Steps**:
1. Operator opens `web_sucursal/FacturacionForm`. The form pre-fills `facturas.total = $17000` (computed from line items + taxes).
2. Customer hands over $17000 cash. Operator types `valor=17000`, selects `medio_pago='efectivo'`, leaves `referencia` blank.
3. Frontend POSTs `api_sucursal /facturas` with `{uuid_ingreso, uuid_salida, lineas: [...], descuento: 0, pagos: [{medio_pago:'efectivo', valor:17000}]}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
5. Backend validates RBAC: `permiso='facturar'`.
6. Backend INSERTs `facturas` row (parent).
7. Backend INSERTs N `factura_detalle` rows (T35).
8. Backend INSERTs M `factura_impuestos` rows (T37).
9. **Backend INSERTs `factura_pagos` row** (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_factura=$factura_uuid`, `medio_pago='efectivo'`, `valor=17000`, `referencia=NULL`, `timestamp_evento=NOW()`, `fecha_retencion_hasta=$created_at + 5_years`).
10. Backend validates invariant: `SUM(factura_pagos WHERE uuid_factura=$X) >= facturas.total` (overpayment allowed for change; $17000 = $17000 → exact).
11. INSERT `log_transaccional` (`accion='factura_pago_registrado'`, `tabla_afectada='factura_pagos'`, `uuid_registro_afectado=$pago_uuid`, `datos_nuevos={medio_pago, valor, timestamp_evento}`).
12. `queue_processor.enqueue('factura_pagos', $pago_uuid, $snapshot)` + other enqueues for the batch.
13. Online DIAN flow: `dian_dispatcher` enqueued.
14. Operator UI shows the factura with the cash payment line, total = $17000, change = $0 (exact payment).

**Tables touched (writes)**: `facturas` (1 row), `factura_detalle` (N rows), `factura_impuestos` (M rows), `factura_pagos` (1 row), `factura_electronica` (cloud, online flow), `log_transaccional` (4+N+M rows), `sync_queue` (3+N+M items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `factura_pagos.uuid_sucursal` → `sucursal.uuid`; `factura_pagos.uuid_factura` → `facturas.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `factura_pagos.uuid`.

**Sync behavior**:
- Branch → cloud: YES.
- Cloud → branch: YES (SyncBackEvent with `numero_oficial`, online flow).
- DIAN trigger: YES (online flow).
- Hash chain impact: YES — chain extends by 4+N+M rows on branch; correspondingly on cloud.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
- Writes to: `facturas`, `factura_detalle`, `factura_impuestos`, `factura_pagos` (this row), `factura_electronica` (cloud), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **simplest payment case**. Most customer transactions are single-pago-efectivo. The same TX enforces the SUM invariant.
- Related: T05 (`facturas`) covers the parent factura; T35 (`factura_detalle`) covers the lines; T37 (`factura_impuestos`) covers the taxes.

### 7.2 Use Case: `uc.factura-pagos.mixed-pago-efectivo-datafono`

**Actor**: operator (branch)

**Real-world action**: Customer wants to pay $17000 but only has $5000 cash + wants to use datafono for $12000. Operator enters two payment lines: one `efectivo` $5000 (no reference), one `datafono` $12000 (with reference `AUTH123`). Backend INSERTs two `factura_pagos` rows with the same `uuid_factura` but different `medio_pago` and `valor`. The SUM invariant holds: $5000 + $12000 = $17000.

**Steps**:
1. Operator opens `web_sucursal/FacturacionForm`. Customer requests split payment.
2. Operator clicks `Agregar pago`. Selects `medio_pago='efectivo', valor=5000`. Customer hands over $5000 cash.
3. Operator clicks `Agregar pago` again. Selects `medio_pago='datafono', valor=12000`. Customer inserts card into datafono terminal.
4. Datafono terminal returns `AUTH123`. Operator types `referencia='AUTH123'`.
5. Frontend POSTs `api_sucursal /facturas` with `pagos: [{medio_pago:'efectivo', valor:5000}, {medio_pago:'datafono', valor:12000, referencia:'AUTH123'}]`.
6. Backend opens TX; SELECT chain anchor from `log_transaccional`.
7. Backend INSERTs `facturas` + `factura_detalle` + `factura_impuestos` (per parent flow).
8. **Backend INSERTs two `factura_pagos` rows** (one per payment):
   - Row 1: `medio_pago='efectivo', valor=5000, referencia=NULL, timestamp_evento=NOW()`.
   - Row 2: `medio_pago='datafono', valor=12000, referencia='AUTH123', timestamp_evento=NOW()`.
9. Backend validates invariant: `SUM = $17000 = facturas.total` (exact).
10. INSERT `log_transaccional` per pago row.
11. `queue_processor.enqueue` per row.
12. Operator UI shows both payment lines: `Efectivo $5000 + Datafono $12000 (AUTH123) = $17000`.

**Tables touched (writes)**: `factura_pagos` (2 rows), `facturas`, `factura_detalle`, `factura_impuestos`, `factura_electronica` (cloud), `log_transaccional` (5+N+M rows), `sync_queue` (4+N+M items).
**Tables touched (reads)**: `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.

**Sync behavior**:
- Branch → cloud: YES.
- Cloud → branch: YES (SyncBackEvent).
- DIAN trigger: YES.
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `factura_pagos` (2 rows), `facturas`, `factura_detalle`, `factura_impuestos`, `factura_electronica` (cloud), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **mixed payment** case. Same `uuid_factura`, different `medio_pago`. The arqueo cross-validation SUMs by `medio_pago` per sesion.
- Related: T34 (`arqueo`) use case 7.1 cross-validates SUMs by medio_pago at cierre.

### 7.3 Use Case: `uc.factura-pagos.pago-parcial-customer-owes-balance`

**Actor**: operator (branch)

**Real-world action**: Customer pays only $10000 against a $17000 factura, promising to return tomorrow with the remaining $7000. Operator enters one `factura_pagos` row with `valor=10000, medio_pago='efectivo'`, plus a flag `es_pago_parcial=true` (or via separate column `estado_pago='parcial'`, sprint 5 decision). Backend INSERTs the partial pago. The factura's `estado` is DERIVED: `activa` (not `pagada`) because `SUM(pagos) < total`. The operator UI shows a "Saldo pendiente: $7000" indicator. When the customer returns, a second `factura_pagos` row completes the payment.

**Steps**:
1. Operator opens `web_sucursal/FacturacionForm`. Customer requests partial payment.
2. Operator types `valor=10000`, selects `medio_pago='efectivo'`. Flags `es_pago_parcial=true` (or selects from a dropdown).
3. Frontend POSTs `api_sucursal /facturas` with `pagos: [{medio_pago:'efectivo', valor:10000, es_pago_parcial:true}]`.
4. Backend opens TX.
5. Backend INSERTs `facturas` (`estado='activa'`, derived: `SUM(pagos) < total → activa`).
6. Backend INSERTs N `factura_detalle`, M `factura_impuestos`.
7. Backend INSERTs `factura_pagos` row with `valor=10000`. The `es_pago_parcial` flag is captured in `observaciones` (text) or a separate column (sprint 5: `estado_pago ENUM('completo', 'parcial')`).
8. Backend validates invariant: `SUM(pagos WHERE uuid_factura=$X) = $10000 < $17000 = total → ALLOWED for pago_parcial`. The `facturas.estado` remains `activa` (derived; NOT updated, derived from the existence of a `factura_pagos` row where `valor < total` is implied).
9. INSERT `log_transaccional` per pago.
10. Operator UI shows: "Pago parcial: $10000. Saldo pendiente: $7000. Factura sigue activa."
11. (Optional) Backend INSERTs `alerta` reminder? NO — pago_parcial is operational, not an alert.
12. The `factura_electronica` (cloud-side, online flow) uses the snapshot `valor=10000` for the DIAN representation. The saldo is tracked locally on the branch and resolved when the customer returns.

**Tables touched (writes)**: `facturas`, `factura_detalle`, `factura_impuestos`, `factura_pagos` (1 row), `factura_electronica` (cloud, with snapshot valor), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: per parent flow.

**Sync behavior**:
- Branch → cloud: YES (with snapshot valor).
- Cloud → branch: YES.
- DIAN trigger: YES (DIAN represents the partial payment as such; the saldo is local until next pago).
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: parent flow.
- Writes to: `factura_pagos` (the partial row), parent tables.
- Cross-cutting: this is the **pago parcial** case. The DIAN representation reflects the partial payment; the saldo is operational (not DIAN-relevant). Sprint 5: `estado_pago` ENUM on `factura_pagos` row(s) for clearer semantics.

### 7.4 Use Case: `uc.factura-pagos.datafono-retry-emits-log-no-factura-pagos-row`

**Actor**: operator (branch) + system (datafono integration)

**Real-world action**: Datafono terminal fails on first attempt (network error, card declined, terminal timeout). Operator retries the datafono transaction. Backend does NOT INSERT a `factura_pagos` row on the failed attempt — only successful authorizations generate a row. The failed attempt is logged via `log_transaccional` with `accion='datafono_retry_failed', datos_nuevos={retry_attempt, error_code, terminal_id}`. After N retries, the operator may offer alternative payment (efectivo).

**Steps**:
1. Operator clicks `Procesar Datafono` in `FacturacionForm`. Backend sends request to datafono terminal integration.
2. Datafono returns error: `timeout` (network issue), `declined` (card declined), `terminal_offline`.
3. **NO `factura_pagos` INSERT**. The transaction didn't happen.
4. Backend INSERTs `log_transaccional` (`accion='datafono_retry_failed'`, `tabla_afectada='factura_pagos'`, `datos_nuevos={retry_attempt: 1, error_code, terminal_id, uuid_factura}`). The log captures the attempt for audit.
5. Operator UI shows: "Datafono falló. Reintentar?" with options: `Reintentar`, `Cambiar a efectivo`, `Cancelar factura`.
6. Operator clicks `Reintentar`. Frontend POSTs `api_sucursal /datafono/retry` with `{uuid_factura, retry_attempt: 2}`.
7. Backend sends request to datafono again.
8. On success: datafono returns `AUTH456`; backend INSERTs `factura_pagos` row with `medio_pago='datafono', valor=17000, referencia='AUTH456', timestamp_evento=NOW()`. INSERT `log_transaccional` (`accion='factura_pago_registrado'`).
9. Operator UI shows: "Datafono exitoso. AUTH456. Factura pagada."
10. After N retries (configurable, default 3), if all fail: operator must cancel the factura or change payment method. No automatic fallback.

**Tables touched (writes — failed retry)**: `log_transaccional` (1 row).
**Tables touched (writes — successful retry)**: `factura_pagos` (1 row), `log_transaccional` (1+ rows), `sync_queue` (1+ items).
**Tables touched (reads)**: `permisos_usuario` (RBAC for retry endpoint), `log_transaccional` (chain anchor), `factura_pagos` (existing rows for this factura, to compute saldo pendiente).

**Sync behavior**:
- Branch → cloud: NO for failed retry (log only); YES for successful retry (factura_pagos + log propagate).
- Cloud → branch: NO.
- DIAN trigger: NO for failed; YES for successful (after DIAN dispatch).
- Hash chain impact: YES — log chain extends by 1 row per attempt.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `log_transaccional`, `factura_pagos` (existing saldo).
- Writes to: `log_transaccional` (always); `factura_pagos` (only on success).
- Cross-cutting: this is the **datafono retry** invariant. NO partial state — only successful authorization generates a `factura_pagos` row. Failed attempts are logged but don't pollute the payment record.
- Related: the datafono terminal integration is external (sprint 5 may add a `datafono_terminales` table for terminal config per branch).

### 7.5 Use Case: `uc.factura-pagos.arqueo-cross-validates-sums-by-medio-pago-at-cierre`

**Actor**: system (within `arqueo_writer.write_arqueo()` at sesion close, cross-ref T34 use case 7.1)

**Real-world action**: At sesion cierre, `arqueo_writer` SELECTs `SUM(factura_pagos WHERE uuid_sucursal=$branch AND uuid_sesion=$X AND medio_pago='efectivo')` to compute `valor_efectivo_esperado`. The same SUM for `medio_pago='datafono'` gives `valor_datafono_esperado`. The operator-reported `valor_efectivo_reportado` and `valor_datafono_reportado` are compared against these expected values; `diferencia = reportado - esperado` per medio_pago. If `ABS(diferencia) > tolerancia`: INSERT `alerta tipo_alerta='diferencia_arqueo'` (T34 + T41).

**Steps**:
1. Operator triggers sesion cierre via `POST /arqueos` (T34 use case 7.1).
2. `arqueo_writer.write_arqueo()` opens TX.
3. Backend SELECTs vigente `configuracion_tolerancias`.
4. Backend SELECTs `SUM(factura_pagos.valor) WHERE uuid_sucursal=$branch AND uuid_sesion=$X AND medio_pago='efectivo' AND timestamp_evento >= sesion.timestamp_apertura AND timestamp_evento <= NOW()`.
5. Backend SELECTs `SUM(factura_pagos.valor) WHERE ... AND medio_pago='datafono'`.
6. Backend computes `valor_efectivo_esperado = sesion.valor_inicial_efectivo + SUM(efectivo_pagos)`; same for datafono.
7. Backend INSERTs `arqueo` row with `valor_efectivo_esperado`, `valor_datafono_esperado`, `valor_efectivo_reportado`, `valor_datafono_reportado`, `diferencia_efectivo`, `diferencia_datafono`.
8. If `ABS(diferencia) > tolerancia`: INSERT `alerta` (T41).
9. INSERT `log_transaccional` (`accion='arqueo_registrado'`, `datos_nuevos={valor_efectivo_esperado, valor_efectivo_reportado, diferencia_efectivo, diferencia_datafono, sum_pagos_efectivo, sum_pagos_datafono}`).

**Tables touched (writes)**: `arqueo` (1 row), `alerta` (if exceeded), `log_transaccional` (2 rows), `caja` (cierre snapshot).
**Tables touched (reads)**: `configuracion_tolerancias`, `sesion` (current), `factura_pagos` (SUMs), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `factura_pagos.uuid_sucursal` → `sucursal.uuid`; `factura_pagos.uuid_factura` → `facturas.uuid` (SUM grouping).

**Sync behavior**:
- Branch → cloud: YES (arqueo + alerta propagate).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `configuracion_tolerancias`, `sesion`, `factura_pagos` (SUMs), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `arqueo`, `alerta`, `log_transaccional`, `caja`, `sync_queue`.
- Cross-cutting: this is the **cross-validation** between `factura_pagos` (per-payment detail) and `arqueo` (end-of-shift count). The SUMs must reconcile — any divergence is the operator-reported variance.
- Related: T34 (`arqueo`) use case 7.1 covers the full cierre flow.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers — `referencia` constraint for datafono), 5 (audit constraints — REVOKE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin FacturaDetail), 14 (web_sucursal FacturacionForm + DatafonoRetry), 15 (shadcn UI), 16 (Zustand facturacion state), 20 (structlog), 24 (pytest), 28 (docker compose), 29 (DIAN provider — receives snapshot payment info).

## 9. RED Tests
- (RED) INSERT `factura_pagos` from `rol_app` → success.
- (RED) UPDATE `prod.factura_pagos` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.factura_pagos` → `AUDIT_FIRST_INMUTABLE`.
- (RED) `referencia` NULL constraint for `efectivo` → success; NON-NULL constraint → success.
- (RED) `referencia` NON-NULL for `datafono` → success; NULL → 422 validation error.
- (RED) Single pago: `SUM(factura_pagos WHERE uuid_factura=$X) = facturas.total` invariant.
- (RED) Mixed pago: 2 rows same `uuid_factura`, different `medio_pago`; SUM invariant holds.
- (RED) Pago parcial: 1 row `valor < total`; `facturas.estado` derived `activa`; saldo pendiente computed correctly.
- (RED) Datafono retry failure: NO `factura_pagos` INSERT; `log_transaccional` row written.
- (RED) Datafono retry success: `factura_pagos` row INSERTed with `referencia=$auth_code`.
- (RED) SUM at arqueo: `SUM(factura_pagos WHERE uuid_sucursal=$branch AND uuid_sesion=$X AND medio_pago='efectivo')` matches the operator's reported efectivo count within tolerance.
- (RED) Idempotent INSERT on retry: same `(uuid_factura, medio_pago, timestamp_evento, valor)` tuple doesn't create duplicate.
- (RED) `fecha_retencion_hasta = created_at + 5 years`.
- (RED) Cross-validation at cierre: `diferencia = reportado - esperado` per medio_pago.
- (RED) Admin report NEVER writes to `factura_pagos` (read-only).

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + `referencia` constraint for datafono.
- [ ] F1.x `pago_writer.py::write_pago()` helper.
- [ ] IT-4.x: `parkos_core/facturacion/facturacion_endpoint.py::POST /facturas` orchestrates full facturacion flow.
- [ ] IT-4.x: server-side validation of `referencia` constraint.
- [ ] IT-4.x: idempotent INSERT on retry (same tuple).
- [ ] IT-4.x: SUM invariant check at INSERT time.
- [ ] IT-4.x: `api_sucursal/routers/facturas.py::POST /facturas/{uuid}/pago` (additional payment for pago parcial).
- [ ] IT-4.x: `api_sucursal/routers/datafono.py::POST /datafono/retry` (retry handler).
- [ ] IT-4.x: datafono terminal integration (external API).
- [ ] IT-4.x: `api_admin/routers/facturas.py::GET /facturas/{uuid}/pagos` (admin detail).
- [ ] IT-4.x: `web_sucursal/FacturacionForm` with multi-payment entry.
- [ ] IT-4.x: `web_sucursal/DatafonoRetry` (datafono failure handling UI).
- [ ] IT-4.x: `web_admin/FacturaDetail` (payment list per factura).
- [ ] IT-5.x: `arqueo_writer.py::read_pagos()` SUM at cierre (T34).
- [ ] Sprint 5: `estado_pago ENUM('completo', 'parcial')` column on `factura_pagos` row(s).
- [ ] Sprint 5: `datafono_terminales` table for terminal config per branch.
- [ ] Sprint 5: activate `pg_partman` monthly partitioning on `created_at`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator types wrong `valor` (typo) | Low | Form requires confirmation modal showing the typed value; SUM invariant check at INSERT time |
| Mixed pago totals don't match `facturas.total` | Low | Server-side invariant check; mismatch returns 422 |
| Datafono retry creates duplicate `factura_pagos` row | Low | Idempotent INSERT on `(uuid_factura, medio_pago, timestamp_evento, valor)` tuple |
| Pago parcial saldo drifts from operator expectation | Low | UI shows "Saldo pendiente" prominently; second pago re-computes; alerts if saldo > 7 days |
| Datafono terminal offline for extended period | Med | Operator falls back to efectivo or `pago_parcial`; UI shows clear "Datafono offline" indicator |
| SUM cross-validation at arqueo detects false positive (e.g., refund not yet reflected in `factura_pagos`) | Low | Refund handling is explicit (separate `factura_pagos` row with `valor<0`); documented in operations |
| `referencia` constraint bypassed (NULL for datafono) | Low | Server-side validation triggers error before INSERT |
| High-volume branch generates many pagos per shift | Low | Schema supports arbitrary N; partition handles scale |

## 12. Open Questions
- (a) Should refunds be modeled as negative `factura_pagos` rows or a separate `factura_pagos_devolucion` table? Currently planned as negative rows; sprint 5 may split.
- (b) `medio_pago='transfer'` and `'check'`: when are these activated? Sprint 5.
- (c) Should `pago_parcial` have a deadline (e.g., 7 days before automatic escalation to admin)? Sprint 5.
- (d) Datafono terminal: is this a per-branch physical terminal or a cloud service (e.g., Stripe Terminal)? Affects integration architecture.
- (e) Should failed datafono retries emit `alerta tipo_alerta='datafono_failure'`? Currently only logged, not alerted.
- (f) Should `factura_pagos.referencia` be a FK to a `datafono_transacciones` table for full audit? Sprint 5.
- (g) Pago mixto with more than 2 medios (e.g., efectivo + datafono + transfer)? Schema supports N; UI may limit to 2-3.
- (h) Should `factura_pagos` be replicated to cloud as `factura_pagos_mirror` for read scaling? Currently direct read.
