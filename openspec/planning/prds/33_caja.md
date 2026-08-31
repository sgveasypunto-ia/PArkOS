# PRD: caja (T33)

> Append-only cash snapshot per `uuid_sucursal`. Current state derived from `ORDER BY created_at DESC LIMIT 1` per branch. NOT per-payment — written at strategic moments (apertura, pre-cierre, cierre, manual mid-shift snapshots). Partitioned monthly via `pg_partman` for retention control. Source of truth for end-of-shift reconciliation cross-check against `factura_pagos`.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_search.md`](_meta/00_scaffold.md)
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
- **Table name**: `prod.caja`
- **SQL name**: `caja` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 2 years operational (partition by month via `pg_partman`)
- **Partitioning**: monthly on `created_at` (high write rate during shifts; ~5-10 rows per shift)
- **Origin**: F1 (schema + REVOKE + trigger + monthly partition) + IT-5 (writes per cash-session lifecycle)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- No polymorphic FKs; `uuid_sucursal` is the only business FK.
- Travel: branch-origin rows travel to cloud via `sync_queue` (as queue items, separate rows); cloud-origin rows do NOT travel back (operational snapshots are cloud-mirrored, like `sync_queue`). Partition pruning critical: queries by date range MUST hit one partition.
- **Snapshot semantic**: each row is a point-in-time snapshot of cash state (`valor_efectivo`, `valor_datafono`). The "current" state is always derived via `SELECT ... ORDER BY created_at DESC LIMIT 1` per `uuid_sucursal`. NO column tracks `es_vigente` — that would violate append-only.

## 3. SOLID Atomic Breakdown
- **S**: "one cash state snapshot at a moment in time" — INSERT in same TX as the triggering event (sesion apertura, pre-cierre snapshot, cierre, manual mid-shift).
- **O**: extensible via migration; new `tipo_movimiento` enum values added as new snapshot triggers emerge (e.g., `auditoria_externa`, `correlativo_arqueo`).
- **I**: branch operator API (writes per snapshot trigger); admin read API (current state per branch, paginated history); cloud worker (mirror for cloud-admin visibility).
- **D**: `parkos_core/caja/snapshot_writer.py::write_snapshot(uuid_sucursal, tipo_movimiento, valor_efectivo, valor_datafono, observaciones=None)` — the ONLY writer. Computes `valor_efectivo` and `valor_datafono` from current `factura_pagos` SUMs + `valor_inicial_efectivo` from current `sesion` (the running total at the snapshot moment).
- **Atomic**: INSERT only. REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | CASCADE | if branch decommissioned, snapshots die |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `arqueo` (T34) | (implicit via `created_at` correlation with `sesion`) | 0..1 | arqueo rows reference the cierre snapshot via `created_at` for cross-validation |
| `sesion` (T43) | (implicit via `created_at`) | 0..N | sesion apertura/cierre events trigger caja snapshots but no FK at DB level |

**Note**: `caja` does NOT have an explicit `uuid_sesion` FK; correlation is via `created_at` timestamp proximity and `uuid_sucursal`. Sprint 5 may add explicit `uuid_sesion` column for unambiguous linking.

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `snapshot_writer.py::write_snapshot()` per trigger event |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved until `pg_partman` retention purges partitions older than 2 years |

**Special rules**:
- **Monthly partitioning**: `pg_partman` partitions by `created_at` month. Retention: 24 months.
- **Snapshot semantic**: `valor_efectivo` and `valor_datafono` are RUNNING TOTALS at the snapshot moment, NOT deltas. To compute the delta between two snapshots: `delta_efectivo = new.valor_efectivo - old.valor_efectivo`.
- **`tipo_movimiento` enum**: `apertura`, `pre_cierre_snapshot`, `cierre`, `auditoria_interna`, `manual`, `correlativo_arqueo` (sprint 5 may add more).
- **Cross-validation**: at cierre, `arqueo.diferencia_efectivo` MUST match `(cierre_caja.valor_efectivo - sum(factura_pagos WHERE medio_pago='efectivo' AND uuid_sesion=$X)) - valor_inicial_efectivo`. Any discrepancy is the operator's reported vs system-expected delta (alerted via `alerta tipo_alerta='diferencia_arqueo'`).

## 6. CodeGraph Dependencies
- `parkos_core/caja/snapshot_writer.py::write_snapshot()` (sole writer for snapshots).
- `api_sucursal/routers/sesion.py::POST /sesion` (writes `apertura` snapshot when sesion opens).
- `api_sucursal/routers/sesion.py::POST /sesion/{uuid}/pre-cierre` (writes `pre_cierre_snapshot`).
- `api_sucursal/routers/arqueos.py::POST /arqueos` (writes `cierre` snapshot when sesion closes — T34 use case 7.1).
- `api_sucursal/routers/caja.py::POST /caja/snapshot` (manual snapshot trigger — operator-initiated).
- `api_admin/routers/caja.py::GET /caja/{uuid_sucursal}/current` (current state per branch).
- `api_admin/routers/caja.py::GET /caja/{uuid_sucursal}/history` (paginated snapshots).
- `web_sucursal/CajaView` (shows current cash state during shift).
- `web_admin/CajaMonitor` (cross-branch current state dashboard).

## 7. Use Cases enabled by this table

The `caja` table is the **append-only cash state journal**: each row is a point-in-time snapshot of `valor_efectivo` and `valor_datafono` for a branch. Written at strategic moments (apertura, pre-cierre, cierre, manual), NOT per-payment. The "current" state is derived from the latest row per `uuid_sucursal`. **No cámaras, no OCR, no QR**: snapshots are operator- or system-triggered; cash counts come from manual input.

### 7.1 Use Case: `uc.caja.sesion-abre-writes-apertura-snapshot`

**Actor**: operator (branch)

**Real-world action**: Operator opens `web_sucursal/AperturaCajaForm` at start of shift. Types the initial cash in the drawer (`valor_inicial_efectivo`) and the datafono's starting balance (`valor_inicial_datafono`, usually 0). The backend INSERTs a `sesion` row with `estado='abierta'` and immediately INSERTs a `caja` row with `tipo_movimiento='apertura'`, `valor_efectivo=$inicial`, `valor_datafono=$inicial_datafono`. The apertura snapshot is the seed for the shift's running totals.

**Steps**:
1. Operator opens `web_sucursal/AperturaCajaForm`. Sees pre-filled `uuid_usuario` (the logged-in operator) and `uuid_sucursal` (their branch).
2. Operator counts cash in the drawer (manual count, no scanner); types `valor_inicial_efectivo = $50000` into the input.
3. Operator confirms datafono starting balance (usually 0); types `valor_inicial_datafono = $0`.
4. Frontend POSTs `api_sucursal /sesion` with `{valor_inicial_efectivo: 50000, valor_inicial_datafono: 0}`.
5. Backend validates RBAC: operator must have `permiso='abrir_sesion'` (T08 derivation).
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
7. Backend SELECTs open sesion check: `SELECT uuid FROM sesion WHERE uuid_sucursal=$branch AND uuid_usuario=$operator AND estado='abierta'`. If exists: return 409 `sesion_ya_abierta`.
8. INSERT `sesion` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$operator`, `valor_inicial_efectivo=50000`, `valor_inicial_datafono=0`, `timestamp_apertura=NOW()`, `timestamp_cierre=NULL`, `estado='abierta'`).
9. INSERT `log_transaccional` (`accion='sesion_abierta'`, `tabla_afectada='sesion'`, `uuid_registro_afectado=$sesion_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_nuevos={valor_inicial_efectivo, valor_inicial_datafono}`).
10. Call `snapshot_writer.write_snapshot(uuid_sucursal=$branch, tipo_movimiento='apertura', valor_efectivo=50000, valor_datafono=0, observaciones='sesion=$sesion_uuid')`.
11. `snapshot_writer` INSERTs `caja` row with `valor_efectivo=50000, valor_datafono=0, fecha_retencion_hasta=$created_at + 2_years`.
12. INSERT `log_transaccional` (`accion='caja_snapshot'`, `tabla_afectada='caja'`, `uuid_registro_afectado=$caja_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_nuevos={tipo_movimiento:'apertura', valor_efectivo, valor_datafono}`).
13. `queue_processor.enqueue('sesion', $sesion_uuid, $snapshot)` and `queue_processor.enqueue('caja', $caja_uuid, $snapshot)` for branch→cloud propagation.
14. Operator UI shows: "Sesión abierta. Efectivo inicial: $50000. Datafono inicial: $0".

**Tables touched (writes)**: `sesion` (1 row), `caja` (1 row apertura snapshot), `log_transaccional` (2 rows), `sync_queue` (2 items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `sesion` (open sesion check), `log_transaccional` (chain anchor), `usuarios` (operator), `sucursal` (tenant).
**FKs traversed**: `sesion.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`; `caja.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `sesion.uuid` or `caja.uuid`.

**Sync behavior**:
- Branch → cloud: YES — both `sesion` and `caja` rows enqueued; cloud receives within 30s.
- Cloud → branch: NO (parametrization impact only on tolerance updates, not sesion lifecycle).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 4 rows (sesion INSERT + sesion audit + caja INSERT + caja audit); cloud chain extends by 2 rows (the audit rows after sync receipt).

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `sesion` (open check), `log_transaccional` (chain anchor), `usuarios` (operator), `sucursal` (tenant).
- Writes to: `sesion` (the sesion row), `caja` (the apertura snapshot), `log_transaccional` (2 audit rows), `sync_queue` (2 items).
- Cross-cutting: this is the canonical **cash-session seed**. Every caja snapshot in this shift's lifecycle will be derived from this apertura row's `valor_efectivo` and the running `SUM(factura_pagos WHERE uuid_sesion=$X AND medio_pago='efectivo')`.
- Related: T43 (`sesion`) use case 7.1 covers the full sesion lifecycle; T34 (`arqueo`) use case 7.1 covers the cierre.

### 7.2 Use Case: `uc.caja.factura-pagos-accumulate-no-caja-write-per-payment`

**Actor**: system (payment handler)

**Real-world action**: During the shift, every `factura_pagos` INSERT (T36) does NOT trigger a `caja` snapshot. The cash state is reconstructable at any moment via `SELECT SUM(valor) FROM factura_pagos WHERE uuid_sucursal=$branch AND uuid_sesion=$X AND medio_pago='efectivo' AND timestamp_evento <= $T`. Caja snapshots are written at strategic moments only — NOT per-payment. This keeps the `caja` partition count manageable (~5-10 rows per shift, not ~hundreds).

**Steps**:
1. Operator in `web_sucursal/FacturacionForm` processes a payment: POST `/facturas/procesar` with `{uuid_factura, pagos: [{medio_pago:'efectivo', valor:5000}]}`.
2. Backend INSERTs `factura_pagos` row with `timestamp_evento=NOW()`.
3. Backend INSERTs `log_transaccional` (`accion='factura_pago_registrado'`, `tabla_afectada='factura_pagos'`, `uuid_registro_afectado=$pago_uuid`).
4. **NO caja INSERT**. The cash state will be reflected in the NEXT snapshot (pre-cierre, cierre, or manual).
5. (Optional) If operator triggers a manual mid-shift snapshot via `POST /caja/snapshot` with `tipo_movimiento='auditoria_interna'`: backend SELECTs `SUM(factura_pagos WHERE uuid_sesion=$X AND medio_pago='efectivo')` to compute current running total, INSERTs `caja` row.

**Tables touched (writes)**: `factura_pagos` (1 row per payment), `log_transaccional` (1 row).
**Tables touched (reads)**: `factura_pagos` (running total query, only on manual snapshot), `sesion` (current sesion), `log_transaccional` (chain anchor).

**Sync behavior**:
- Branch → cloud: YES — `factura_pagos` rows propagate via `sync_queue`.
- Cloud → branch: NO.
- DIAN trigger: per `factura_electronica` creation (separate flow).
- Hash chain impact: YES — chain extends by 1 row per payment.

**Integration with other tables**:
- Reads from: `sesion` (current), `factura_pagos` (running SUM), `log_transaccional` (chain anchor).
- Writes to: `factura_pagos` (the payment), `log_transaccional` (audit).
- Cross-cutting: this is the **NO snapshot per payment** invariant. Documented for compliance: caja rows are NOT a high-frequency operational record; they're strategic checkpoints. The per-payment detail lives in `factura_pagos` (T36) and is the source of truth for cross-validation at cierre (T34).
- Related: T36 (`factura_pagos`) covers the payment lifecycle; T34 (`arqueo`) cross-validates at cierre.

### 7.3 Use Case: `uc.caja.pre-cierre-snapshot-writes-running-totals`

**Actor**: system (cron worker OR operator trigger)

**Real-world action**: 30 minutes before sesion close (configurable via `configuracion_general.snapshot_pre_cierre_minutes`, sprint 5), the system INSERTs a `caja` row with `tipo_movimiento='pre_cierre_snapshot'`. The snapshot captures the running totals at that moment: `valor_efectivo = valor_inicial_efectivo + SUM(factura_pagos WHERE medio_pago='efectivo' AND uuid_sesion=$X)`, `valor_datafono = valor_inicial_datafono + SUM(factura_pagos WHERE medio_pago='datafono' AND uuid_sesion=$X)`. This gives the operator a "30-min remaining" checkpoint.

**Steps**:
1. `workers/pre_cierre_snapshotter/__main__.py` fires 30min before configured `cierre_horario` per branch.
2. For each active branch with an open sesion:
   a. SELECT `sesion` WHERE `uuid_sucursal=$branch AND estado='abierta'`.
   b. SELECT `SUM(valor) FILTER (WHERE medio_pago='efectivo') AS total_efectivo, SUM(valor) FILTER (WHERE medio_pago='datafono') AS total_datafono FROM factura_pagos WHERE uuid_sucursal=$branch AND uuid_sesion=$sesion_uuid`.
   c. Compute `valor_efectivo = sesion.valor_inicial_efectivo + total_efectivo`, `valor_datafono = sesion.valor_inicial_datafono + total_datafono`.
3. Backend opens TX; SELECT chain anchor from `log_transaccional`.
4. INSERT `log_transaccional` (`accion='pre_cierre_snapshot_triggered'`, `tabla_afectada='caja'`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={sesion_uuid, valor_efectivo, valor_datafono, minutos_hasta_cierre: 30}`).
5. Call `snapshot_writer.write_snapshot(uuid_sucursal=$branch, tipo_movimiento='pre_cierre_snapshot', valor_efectivo, valor_datafono, observaciones='sesion=$sesion_uuid, minutos_hasta_cierre=30')`.
6. `snapshot_writer` INSERTs `caja` row.
7. `queue_processor.enqueue('caja', $caja_uuid, $snapshot)`.
8. Operator UI shows: "Pre-cierre snapshot: Efectivo $X, Datafono $Y. Quedan 30min para cierre." Optional: highlight any expected anomalies (e.g., too many refunds).

**Tables touched (writes)**: `caja` (1 row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `sesion` (current), `factura_pagos` (running SUM), `sucursal` (cierre_horario), `log_transaccional` (chain anchor).

**Sync behavior**:
- Branch → cloud: YES — the pre-cierre snapshot propagates for cloud visibility.
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 2 rows (snapshot + audit); cloud chain extends correspondingly.

**Integration with other tables**:
- Reads from: `sesion` (current), `factura_pagos` (running SUM), `sucursal` (cierre_horario), `log_transaccional` (chain anchor).
- Writes to: `caja` (snapshot), `log_transaccional` (audit), `sync_queue` (propagation).
- Cross-cutting: this is the **30-min checkpoint**. It gives admin visibility into the shift's running state before cierre (when the operator is rushed). The snapshot is NOT used for alerting (it's an informational checkpoint); alerts come from `arqueo` tolerance checks at cierre (T34).
- Related: T34 use case 7.1 covers the cierre snapshot.

### 7.4 Use Case: `uc.caja.cierre-snapshot-writes-final-state-on-sesion-close`

**Actor**: operator (branch) + system (sync worker)

**Real-world action**: Operator closes the shift via `web_sucursal/CierreCajaForm`. Enters `valor_efectivo_reportado` (counted cash) and `valor_datafono_reportado` (datafono terminal report). Backend INSERTs `arqueo` row with `diferencia_efectivo = reportado - esperado`, INSERTs `caja` row with `tipo_movimiento='cierre'`, `valor_efectivo=reportado, valor_datafono=reportado`, and emits `alerta tipo_alerta='diferencia_arqueo'` if `ABS(diferencia) > tolerancia`. The cierre snapshot is the **final state** of the shift.

**Steps**:
1. Operator opens `web_sucursal/CierreCajaForm`. Form pre-fills `valor_inicial_efectivo` (from sesion apertura) and shows the SUM of `factura_pagos WHERE uuid_sesion=$X` (the expected values).
2. Operator counts cash in the drawer, types `valor_efectivo_reportado = $48000` (vs expected $50000 → diferencia -$2000).
3. Operator enters `valor_datafono_reportado = $125000` (vs expected $125000 → diferencia $0).
4. Frontend POSTs `api_sucursal /arqueos` with `{uuid_sesion, valor_efectivo_reportado: 48000, valor_datafono_reportado: 125000, observaciones}`.
5. Backend SELECTs vigente `configuracion_tolerancias` (T29) for tolerance check.
6. Backend computes `diferencia_efectivo = 48000 - 50000 = -2000`, `diferencia_datafono = 125000 - 125000 = 0`.
7. Backend SELECTs `valor_esperado_efectivo = sesion.valor_inicial_efectivo + SUM(factura_pagos WHERE uuid_sesion=$X AND medio_pago='efectivo')`, `valor_esperado_datafono = sesion.valor_inicial_datafono + SUM(factura_pagos WHERE uuid_sesion=$X AND medio_pago='datafono')`.
8. INSERT `arqueo` row (`valor_efectivo_esperado=$X, valor_datafono_esperado=$Y, valor_efectivo_reportado=48000, valor_datafono_reportado=125000, diferencia_efectivo=-2000, diferencia_datafono=0`).
9. INSERT `log_transaccional` (`accion='arqueo_registrado'`, `tabla_afectada='arqueo'`).
10. If `ABS(diferencia_efectivo) > tolerancia_efectivo OR ABS(diferencia_datafono) > tolerancia_datafono`: INSERT `alerta` workflow root (`tipo_alerta='diferencia_arqueo'`, `estado='abierta'`, `uuid_arqueo=$arqueo_uuid`).
11. Call `snapshot_writer.write_snapshot(uuid_sucursal=$branch, tipo_movimiento='cierre', valor_efectivo=48000, valor_datafono=125000, observaciones='sesion=$sesion_uuid, arqueo=$arqueo_uuid')`.
12. INSERT `caja` row with the cierre snapshot.
13. INSERT `log_transaccional` (`accion='caja_snapshot'`, `tabla_afectada='caja'`, `datos_nuevos={tipo_movimiento:'cierre', valor_efectivo:48000, valor_datafono:125000}`).
14. UPDATE `sesion` SET `estado='cerrada', timestamp_cierre=NOW()` (T43 — with log).
15. INSERT `log_transaccional` (`accion='sesion_cerrada'`).
16. `queue_processor.enqueue('arqueo', $arqueo_uuid, $snapshot)` + `enqueue('caja', $caja_uuid, $snapshot)` + `enqueue('sesion', $sesion_uuid, $snapshot)`.

**Tables touched (writes)**: `arqueo` (1 row), `caja` (1 row cierre snapshot), `sesion` (UPDATE — [L-S] operational exception), `alerta` (if tolerance exceeded), `log_transaccional` (3-4 rows), `sync_queue` (3 items).
**Tables touched (reads)**: `configuracion_tolerancias` (vigente), `sesion` (current), `factura_pagos` (SUM), `log_transaccional` (chain anchor), `usuarios` (operator), `sucursal` (tenant).

**Sync behavior**:
- Branch → cloud: YES — arqueo + caja + sesion UPDATE propagate.
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 4-5 rows; cloud chain extends correspondingly.

**Integration with other tables**:
- Reads from: `configuracion_tolerancias` (tolerance check), `sesion` (current), `factura_pagos` (SUM), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
- Writes to: `arqueo` (the cash count), `caja` (cierre snapshot), `sesion` (UPDATE — cierre), `alerta` (if tolerance exceeded), `log_transaccional` (audit), `sync_queue`.
- Cross-cutting: this is the **canonical cash-session end**. The cierre snapshot IS the canonical state at end of shift; admin queries for "current caja" at any moment get the latest row, which during off-hours is the cierre snapshot of the last shift.
- Related: T34 (`arqueo`) use case 7.1 covers the full cierre flow including tolerance alerting.

### 7.5 Use Case: `uc.caja.admin-queries-current-caja-state-per-branch`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/CajaMonitor`. Sees current `valor_efectivo` and `valor_datafono` per branch (latest snapshot). For a deep dive, admin clicks a branch → sees the snapshot history (apertura → mid-shift → pre-cierre → cierre). The query is a simple `ORDER BY created_at DESC LIMIT 1` per `uuid_sucursal` for current; paginated for history.

**Steps**:
1. Admin opens `web_admin/CajaMonitor`.
2. Frontend GETs `api_admin /caja/{uuid_sucursal}/current` for each active branch (or one branch at a time).
3. Backend runs: `SELECT * FROM caja WHERE uuid_sucursal=$branch ORDER BY created_at DESC LIMIT 1`.
4. Returns the row: `{uuid, uuid_sucursal, valor_efectivo, valor_datafono, fecha_retencion_hasta, created_at, ...}`.
5. UI renders the data with: branch name (JOIN `sucursal`), last snapshot age, current operator (JOIN `sesion.uuid_usuario WHERE estado='abierta'`), shift duration.
6. Admin clicks a branch → GET `/caja/{uuid_sucursal}/history?desde=&hasta=&limit=` paginated.
7. Backend runs: `SELECT * FROM caja WHERE uuid_sucursal=$branch AND created_at BETWEEN $desde AND $hasta ORDER BY created_at DESC LIMIT $limit`.
8. UI renders the timeline: apertura → mid-shift (if any) → pre-cierre → cierre, with annotations for tolerance events (cross-references `arqueo` and `alerta`).
9. Admin clicks a snapshot row → modal shows `observaciones`, related `sesion`, related `arqueo` (if cierre), related `alerta` (if tolerance exceeded).
10. (Optional) Export to CSV/Excel for reporting.

**Tables touched (writes)**: NONE for the read. (If admin takes action like "force snapshot", it would be a write — separate use case.)
**Tables touched (reads)**: `caja` (current + history), `sucursal` (display), `sesion` (current operator), `arqueo` (cierre correlation), `alerta` (tolerance correlation), `usuarios` (display).
**FKs traversed**: `caja.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`; `arqueo.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read of historical data).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `caja` (current + history), `sucursal`, `sesion`, `arqueo`, `alerta`, `usuarios`.
- Writes to: NONE.
- Cross-cutting: this is the canonical **cash visibility** view. Admin uses it to monitor shift health, investigate discrepancies, and verify operator-reported values against system-computed ones.
- Related: T34 (`arqueo`) use case 7.4 covers admin cross-branch arqueo reporting; T41 (`alerta`) workflow covers diferencia_arqueo alerts.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers), 3 (partitioning via `pg_partman`), 5 (audit constraints — REVOKE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas for snapshots), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin CajaMonitor), 14 (web_sucursal CajaView + Apertura/CierreCaja forms), 15 (shadcn UI components for cash display), 16 (Zustand cash state), 20 (structlog), 21 (Prometheus counters — snapshots per shift), 24 (pytest), 28 (docker compose for cron workers), 30 (pre_cierre_snapshotter cron).

## 9. RED Tests
- (RED) INSERT `caja` from `rol_app` → success.
- (RED) UPDATE `prod.caja` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.caja` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Snapshot writer computes `valor_efectivo = valor_inicial_efectivo + SUM(factura_pagos WHERE uuid_sesion=$X AND medio_pago='efectivo')` correctly.
- (RED) Apertura snapshot is the seed; all subsequent snapshots in the same shift's `uuid_sesion` correlate via `created_at` proximity.
- (RED) NO caja INSERT per `factura_pagos` (invariant: only apertura / pre_cierre / cierre / manual snapshots).
- (RED) Pre-cierre snapshot fires 30 min before configured cierre_horario (cron test).
- (RED) Cierre snapshot has `tipo_movimiento='cierre'` and correlates with `arqueo` via `observaciones`.
- (RED) Current state query `ORDER BY created_at DESC LIMIT 1` returns the latest snapshot, even across multiple shifts.
- (RED) Partition pruning: query `WHERE created_at >= '2026-08-01' AND created_at < '2026-09-01'` → EXPLAIN shows single partition hit.
- (RED) `pg_partman` retention: rows older than 24 months are dropped automatically.
- (RED) Snapshot semantic: `valor_efectivo` is a RUNNING TOTAL, not a delta. Delta computation requires two snapshots.
- (RED) Admin current-state query NEVER writes to `caja` (read-only).
- (RED) Snapshot `observaciones` field captures `uuid_sesion` and (for cierre) `uuid_arqueo` for correlation.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + monthly `pg_partman` partition.
- [ ] F1.x `snapshot_writer.py::write_snapshot()` helper.
- [ ] F1.x Partition retention policy (24 months) — automated purge via `pg_partman`.
- [ ] IT-5.x: `api_sucursal/routers/sesion.py::POST /sesion` writes `apertura` snapshot.
- [ ] IT-5.x: `api_sucursal/routers/sesion.py::POST /sesion/{uuid}/pre-cierre` writes `pre_cierre_snapshot`.
- [ ] IT-5.x: `api_sucursal/routers/arqueos.py::POST /arqueos` writes `cierre` snapshot (cross-ref T34).
- [ ] IT-5.x: `api_sucursal/routers/caja.py::POST /caja/snapshot` (manual mid-shift snapshot).
- [ ] IT-5.x: `api_admin/routers/caja.py::GET /caja/{uuid_sucursal}/current`.
- [ ] IT-5.x: `api_admin/routers/caja.py::GET /caja/{uuid_sucursal}/history`.
- [ ] IT-5.x: `web_sucursal/CajaView` shows current state during shift.
- [ ] IT-5.x: `web_admin/CajaMonitor` cross-branch current state dashboard.
- [ ] IT-5.x: `workers/pre_cierre_snapshotter/__main__.py` cron 30 min before `cierre_horario`.
- [ ] Sprint 5: explicit `uuid_sesion` column on `caja` for unambiguous correlation.
- [ ] Sprint 5: explicit `uuid_arqueo` column on `caja` for cierre correlation.
- [ ] Sprint 5: configurable `cierre_horario` per `sucursal` (currently global).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator forgets to take apertura snapshot → next snapshot missing the seed | Low | Apertura is REQUIRED to open sesion; sesion apertura form is the only path to open sesion |
| Pre-cierre cron fires at wrong time (cron downtime, clock drift) | Low | Operator can manually trigger via `POST /caja/snapshot` with `tipo_movimiento='pre_cierre_snapshot'` |
| `valor_efectivo` running total diverges from `sesion.valor_inicial_efectivo + SUM(factura_pagos)` due to refund handling | Med | Document refund handling explicitly (refund = negative pago); cross-validate at cierre |
| Partition grows fast during high-volume shifts | Low | 5-10 snapshots per shift × 30 days × N branches = ~150N rows/month; manageable |
| Admin current-state query latency on large partitions | Low | `ORDER BY created_at DESC LIMIT 1` hits the latest partition; index on `(uuid_sucursal, created_at DESC)` |
| Operator types `valor_inicial_efectivo` wrong (typo) | Low | Apertura form requires confirmation modal showing the typed value; admin can correct via arqueo process at cierre |
| Caja row loses correlation with `sesion` (no FK, only `observaciones` text field) | Med | Sprint 5: add explicit `uuid_sesion` column; until then, `observaciones` carries the UUID for query correlation |

## 12. Open Questions
- (a) Should `tipo_movimiento='auditoria_interna'` be a separate audit table (e.g., `auditoria_caja`) or remain in `caja`? Currently in `caja`.
- (b) Should caja snapshots include `uuid_arqueo` directly (FK) or rely on `observaciones` text? Sprint 5 decision.
- (c) Should the pre-cierre snapshot be configurable per branch (some branches close at 22:00, others at 06:00)? Currently global via `configuracion_general.snapshot_pre_cierre_minutes`.
- (d) Snapshot frequency during long shifts (e.g., 24h shifts): should the system auto-snapshot every 4 hours? Or stay operator-triggered only?
- (e) Should `caja` be replicated to cloud as `caja_mirror` (separate table for cloud-only admin queries) to avoid coupling read traffic with branch write traffic?
- (f) Refund handling: are refunds negative `factura_pagos` rows or separate `factura_pagos` with `valor<0`? Affects SUM computation.
- (g) Should `valor_datafono` include voucher payments, or split into `valor_datafono_credito`, `valor_datafono_debito`, `valor_datafono_transfer`? Currently single field.
