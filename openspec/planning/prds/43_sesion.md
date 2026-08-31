# PRD: sesion (T43)

> `[L-S]` cash session lifecycle (`abierta → cerrada`). One open sesion per branch at a time (UNIQUE partial index on `uuid_sucursal, estado='abierta'`). UPDATE permitted ONLY on `estado='cerrada', timestamp_cierre=NOW()` via `ls_session_update_guard` trigger, with `log_transaccional` INSERT mandatory in same TX. The cierre TX is the atomic cascade: UPDATE `sesion` + INSERT `arqueo` + INSERT `caja` snapshot + (conditional) INSERT `alerta` (T34/T41). Operator-change mid-shift = close current sesion + open new one (per AGENTS.md policy, no parallel shifts). Abuse detection: `sesion.estado='abierta' AND timestamp_apertura < NOW() - 16h` flags a stale open shift.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule S: sesion is the single audit point for cash-shift lifecycle*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[L-S]` table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.sesion`
- **SQL name**: `sesion` (with `prod` schema)
- **Enforcement level**: `[L-S]` session/cycle (UPDATE permitted only on `estado='cerrada', timestamp_cierre` via `ls_session_update_guard`)
- **Retention**: 5+ years (DIAN compliance — sesion is the source for cash-shift reconciliation + arqueo lineage)
- **Hash chain**: NO (operational audit, not source-of-truth for compliance)
- **UNIQUE partial index**: `(uuid_sucursal) WHERE estado='abierta'` — one open sesion per branch
- **Origin**: F1 (schema + REVOKE + `ls_session_update_guard` trigger + UNIQUE partial index) + IT-5 (writes from operator actions)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 5 use cases covering the full apertura/durante/cierre/operator-change/abuse-detection lifecycle with explicit before/after states)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `valor_inicial_efectivo` is the cash the operator starts with (mandatory); `valor_inicial_datafono` is typically 0 (datafono terminal tracks itself).
- `timestamp_apertura` is when the operator opened the shift; `timestamp_cierre` is set by the cierre UPDATE.
- Travel: branch-origin rows travel to cloud via `sync_queue` within 30s. The UPDATE to `cerrada` is replicated as an UPDATE on cloud (same `ls_session_update_guard` validates).
- **UPDATE constraint**: only `estado='cerrada', timestamp_cierre=NOW()` transition is permitted. Trigger `ls_session_update_guard` enforces (a) only these two columns are being modified, and (b) an INSERT into `log_transaccional` occurs in the SAME TX. Any other UPDATE is rejected.

## 3. SOLID Atomic Breakdown
- **S**: "one cash session lifecycle (open → close)" — INSERT on apertura; UPDATE on cierre (the only permitted UPDATE).
- **O**: extensible via migration; new columns (e.g., `motivo_cierre`, `cerrada_por_admin_uuid`) for forensic detail.
- **I**: branch operator API (writer — `POST /sesiones` apertura, `PATCH /sesiones/{uuid}` cierre); admin read API (`SesionesPanel` paginated, filterable by `estado`, `uuid_sucursal`, `uuid_usuario`); auditor read API (BYPASSRLS).
- **D**: `parkos_core/caja/sesion_writer.py::open_sesion(uuid_sucursal, uuid_usuario, valor_inicial_efectivo, valor_inicial_datafono=0)` (the ONLY writer for apertura INSERT); `parkos_core/caja/sesion_writer.py::close_sesion(uuid, reportado_efectivo, reportado_datafono, observaciones=None)` (the ONLY writer for cierre UPDATE, orchestrates the full cascade).
- **Atomic**: INSERT for apertura (one row, no TX dependency beyond the UNIQUE partial index check); UPDATE for cierre, gated by `ls_session_update_guard` + concurrent `log_transaccional` write in same TX, AND wrapped in a TX with `arqueo` INSERT + `caja` snapshot + conditional `alerta` INSERT.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch |
| `uuid_usuario` | `prod.usuarios.uuid` | exactly one (NOT NULL) | RESTRICT | the operator who opened the session |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `arqueo.uuid_sucursal` (correlation) | (no FK — see T34 use case 7.1 note) | 1:1 per sesion | `arqueo` correlates to `sesion` via `created_at` proximity + `observaciones` text + `uuid_sucursal` (sprint 5: explicit `uuid_sesion` FK) |
| `caja.uuid_sucursal` (correlation) | (no FK) | N:1 | `caja` snapshots reference sesion via `observaciones='sesion=$uuid'` text |
| `alerta.uuid_arqueo` (cross-ref) | (no FK) | 0..1 | `alerta tipo_alerta='diferencia_arqueo'` references the arqueo created during this sesion's cierre |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `sesion_writer.py::open_sesion()` per apertura. UNIQUE partial index `(uuid_sucursal, estado='abierta')` enforces one open session per branch. |
| UPDATE `estado='cerrada', timestamp_cierre=NOW()` | YES (only via `ls_session_update_guard` + concurrent `log_transaccional`) | Inside TX, by `sesion_writer.py::close_sesion()`. The cierre TX is the full cascade. |
| UPDATE other columns / other transitions | NO | `ls_session_update_guard` trigger raises `LS_SESSION_FORBIDDEN_COLUMN` |
| DELETE | NO | Append-only |

**Special rules**:
- **`ls_session_update_guard` trigger** (per AGENTS.md): validates (a) NEW.estado='cerrada' AND OLD.estado='abierta', (b) NEW.timestamp_cierre IS NOT NULL AND NEW.timestamp_cierre > OLD.timestamp_apertura, (c) the TX includes a `log_transaccional` INSERT for the same `uuid_sucursal` with `accion='sesion_cerrada'`, (d) NO other column is being modified (NEW.uuid_usuario = OLD.uuid_usuario, NEW.valor_inicial_efectivo = OLD.valor_inicial_efectivo, etc.). On violation: RAISE EXCEPTION.
- **UNIQUE partial index `(uuid_sucursal WHERE estado='abierta')`**: at most one open session per branch. Attempting to open a second session while one is open → 409 `sesion_ya_abierta`.
- **Cierre TX cascade**: UPDATE `sesion` + INSERT `arqueo` (T34) + INSERT `caja` snapshot (T33) + (conditional) INSERT `alerta` (T41 if `diferencia > tolerancia`) + INSERT `log_transaccional` (mandatory by trigger). All 4-5 writes are in ONE TX. If any fails, the whole cierre rolls back.
- **No mid-shift state changes**: `valor_inicial_efectivo` is immutable after apertura. If the operator needs to add cash (e.g., mid-shift replenishment), they INSERT a new `caja` snapshot row with `tipo_movimiento='replenishment'` (T33); the sesion stays `abierta`.
- **One operator per sesion at a time**: per AGENTS.md policy, no parallel shifts. Operator-change mid-shift = close current sesion (with full cierre TX) + open new sesion (with new apertura INSERT). The new sesion's `valor_inicial_efectivo` = the closed sesion's `valor_efectivo_reportado` (carryover).
- **Abuse detection**: `sesion.estado='abierta' AND timestamp_apertura < NOW() - 16h` → flagged as stale. A nightly cron emits `alerta tipo_alerta='manual'` (operator forgot to close) and admin triages.

## 6. CodeGraph Dependencies
- `parkos_core/caja/sesion_writer.py::open_sesion()` (sole writer for apertura INSERT).
- `parkos_core/caja/sesion_writer.py::close_sesion()` (sole writer for cierre UPDATE + cascade orchestrator).
- `parkos_core/caja/caja_writer.py::write_snapshot()` (called by cierre for the snapshot).
- `parkos_core/caja/arqueo_writer.py::write_arqueo()` (called by cierre for the arqueo).
- `parkos_core/operacion/alerta_writer.py::write_alerta()` (called by cierre on tolerance exceeded).
- `api_sucursal/routers/sesiones.py::POST /sesiones` (operator apertura endpoint).
- `api_sucursal/routers/sesiones.py::PATCH /sesiones/{uuid}` (cierre endpoint).
- `api_admin/routers/sesiones.py::GET /sesiones` (paginated, filterable).
- `api_admin/routers/sesiones.py::GET /sesiones/{uuid}` (single sesion detail with snapshot + arqueo).
- `workers/stale_session_detector/__main__.py` (nightly cron — emits `alerta tipo_alerta='manual'` for > 16h abierto).
- `web_sucursal/SesionForm` (apertura form: enters `valor_inicial_efectivo`, `valor_inicial_datafono`).
- `web_sucursal/CierreCajaForm` (cierre form: enters `valor_efectivo_reportado`, `valor_datafono_reportado`).
- `web_admin/SesionesPanel` (cross-branch open sessions dashboard).

## 7. Use Cases enabled by this table

The `sesion` table is the **canonical lifecycle anchor for cash-shift operations**: every cash session is INSERTed on apertura (one operator, one branch, `estado='abierta'`), and UPDATEd to `cerrada` on cierre via the `[L-S]` trigger. The cierre TX is the most critical atomic event in the entire cash-management subsystem — it cascades to `arqueo` (T34), `caja` snapshot (T33), and conditional `alerta` (T41). Use cases below describe the full lifecycle with explicit before/after states. **Manual operator input** for cash counts (no scanner, no OCR).

### 7.1 Use Case: `uc.sesion.operator-apertura-shift-morning`

**Actor**: operator (branch)

**Real-world action**: Operator arrives at the booth at 8:00am. Opens `web_sucursal/SesionForm`. Form requires `valor_inicial_efectivo` (the cash in the drawer at shift start, e.g., $50,000 COP); `valor_inicial_datafono` is typically 0 (datafono terminal tracks itself). Backend SELECTs to verify NO open sesion exists for this branch (UNIQUE partial index check). INSERTs `sesion` row with `estado='abierta', timestamp_apertura=NOW(), uuid_usuario=$operator, uuid_sucursal=$branch`. INSERTs `caja` snapshot (`tipo_movimiento='apertura'`). INSERTs `log_transaccional`. From this point, the operator can record ingresos, process salidas, generate facturas.

**Steps (BEFORE → DURING → AFTER)**:

**BEFORE**:
- `sesion` table: no row with `uuid_sucursal=$branch AND estado='abierta'`.
- `caja` table: last snapshot for this branch has some prior state (from yesterday's cierre).
- `configuracion_tolerancias`: vigente tolerance for cierre check.

**STEPS**:
1. Operator opens `web_sucursal/SesionForm`. Form is loaded only if NO open sesion exists; otherwise UI redirects to current shift dashboard.
2. Form fields: `valor_inicial_efectivo` (mandatory, numeric, min=0), `valor_inicial_datafono` (default 0). UI does NOT have a "datafono initial value" field — that's terminal-tracked.
3. Operator counts cash in drawer; types `valor_inicial_efectivo=50000`.
4. Frontend POSTs `api_sucursal /sesiones` with `{valor_inicial_efectivo: 50000, valor_inicial_datafono: 0}`.
5. Backend: SELECT `SELECT 1 FROM sesion WHERE uuid_sucursal=$branch AND estado='abierta'`. If exists → 409 `sesion_ya_abierta`. (The UNIQUE partial index would also reject the INSERT, but the application check provides a friendlier error message.)
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
7. INSERT `sesion` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$operator`, `timestamp_apertura=NOW()`, `valor_inicial_efectivo=50000`, `valor_inicial_datafono=0`, `estado='abierta'`, `timestamp_cierre=NULL`).
8. INSERT `caja` snapshot row (T33 use case 7.1): `tipo_movimiento='apertura'`, `valor_efectivo=50000, valor_datafono=0`, `observaciones='sesion=$sesion_uuid, apertura_efectivo=50000'`.
9. INSERT `log_transaccional` (`accion='sesion_apertura'`, `tabla_afectada='sesion'`, `uuid_registro_afectado=$sesion_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_nuevos={valor_inicial_efectivo: 50000, valor_inicial_datafono: 0}`).
10. INSERT `log_transaccional` (`accion='caja_snapshot'`, `tabla_afectada='caja'`, `uuid_registro_afectado=$caja_uuid`, `datos_nuevos={tipo_movimiento:'apertura', valor_efectivo:50000, valor_datafono:0}`).
11. `queue_processor.enqueue('sesion', $uuid, $snapshot)` + `enqueue('caja', $uuid, $snapshot)`.
12. Backend returns `{uuid: $sesion_uuid, timestamp_apertura, valor_inicial_efectivo: 50000}`.

**AFTER**:
- `sesion` table: 1 new row, `estado='abierta'`. UNIQUE partial index enforces one open sesion per branch.
- `caja` table: 1 new snapshot (`tipo_movimiento='apertura'`).
- `log_transaccional` table: 2 new rows (sesion + caja audits).
- `sync_queue`: 2 items queued for cloud.

**Tables touched (writes)**: `sesion` (1 INSERT), `caja` (1 INSERT), `log_transaccional` (2 rows), `sync_queue` (2 items).
**Tables touched (reads)**: `configuracion_tolerancias` (vigente — not strictly needed for apertura but pre-loaded for the cierre form), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `sesion.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`; `caja.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `sesion.uuid` or `caja.uuid`.

**Sync behavior**:
- Branch → cloud: YES (both sesion and caja propagate within 30s).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 2 rows.

**Integration with other tables**:
- Reads from: `configuracion_tolerancias` (vigente, pre-load), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
- Writes to: `sesion` (INSERT), `caja` (apertura snapshot), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **start-of-shift** anchor. The `sesion` row's `uuid` is referenced by every cash event during the shift (implicitly via `created_at` proximity + `uuid_sucursal`; sprint 5: explicit `uuid_sesion` FK on `factura_pagos`, `arqueo`, `alerta`). The `estado='abierta'` flag is the gate for downstream operations (e.g., `facturas` POST checks for open sesion; if none → 422 `sesion_cerrada_no_se_puede_facturar`).

### 7.2 Use Case: `uc.sesion.durante-shift-estado-abierta-caja-snapshots-at-key-moments`

**Actor**: system (background events) + operator (manual snapshots)

**Real-world action**: During the shift, `sesion.estado` stays `='abierta'`. The `sesion` row is NEVER UPDATEd during the shift (the `[L-S]` constraint allows UPDATE only on cierre). However, `caja` snapshots are INSERTed at key moments: each `factura_pagos` write, each cash replenishment, each cash withdrawal. The "current state" of cash is reconstructed by reading the `caja` snapshot history. The `sesion` row is the immutable anchor — all events during the shift correlate to it via `uuid_sucursal` + `created_at`.

**Steps (BEFORE → DURING → AFTER)**:

**BEFORE**:
- `sesion`: 1 row, `estado='abierta'`, opened at 8:00am (use case 7.1).
- `caja`: several snapshots from earlier in the shift.

**STEPS** (representative events during shift):
1. **Ingreso**: Operator records vehicle arrival (T04 use case 7.1). No `caja` snapshot for ingresos (no cash changes hands).
2. **Factura creation with cash payment**: Operator finalizes a factura with `medio_pago='efectivo'` (T05). The facturacion flow:
   - INSERT `factura_pagos` row with `valor=$X, medio_pago='efectivo'`.
   - INSERT `caja` snapshot (`tipo_movimiento='pago_efectivo'`, `valor_efectivo=current+=$X, valor_datafono=current`, `observaciones='factura=$factura_uuid, factura_pago=$pago_uuid'`). The snapshot is the canonical "cash balance increased by $X" record.
   - INSERT `log_transaccional` for the factura + caja + log.
3. **Factura creation with datafono payment**: similar, but `caja` snapshot with `valor_datafono` increase.
4. **Cash replenishment** (rare): admin delivers extra cash. Operator INSERTs `caja` snapshot (`tipo_movimiento='replenishment'`, `valor_efectivo=current+=$X`, `observaciones='motivo=...'`) directly via `POST /caja` (admin-only endpoint OR operator with permission).
5. **Cash withdrawal** (e.g., operator buys cleaning supplies with parking cash): INSERT `caja` snapshot (`tipo_movimiento='withdrawal'`, `valor_efectivo=current-=$X`).
6. **Mid-shift `caja_baja` alert**: cron runs every hour, checks `caja` last snapshot for the open sesion — if `valor_efectivo < threshold` (configurable, default $20,000), INSERTs `alerta tipo_alerta='caja_baja'`. The operator sees the alert in their dashboard.

**AFTER (snapshot reconstruction)**:
- Query: `SELECT * FROM caja WHERE uuid_sucursal=$branch AND created_at BETWEEN $sesion.timestamp_apertura AND $now ORDER BY created_at ASC` returns the full snapshot history for this shift.
- "Current cash": `SELECT valor_efectivo FROM caja WHERE uuid_sucursal=$branch ORDER BY created_at DESC LIMIT 1`.
- "Sum of efectivo receipts": `SELECT SUM(valor) FROM factura_pagos WHERE uuid_sucursal=$branch AND medio_pago='efectivo' AND created_at BETWEEN $sesion.timestamp_apertura AND $now`.

**Tables touched (writes per event)**: `factura_pagos` (1 row per pago), `caja` (1 snapshot per cash movement), `facturas` (1 row per facturacion), `factura_detalle`, `factura_impuestos`, `factura_otros_cobros` (snapshots), `factura_electronica` (cloud-only), `log_transaccional` (audits), `sync_queue` (deferred propagation).
**Tables touched (reads)**: `caja` (last snapshot), `factura_pagos` (sum for expected), `configuracion_tolerancias` (for caja_baja threshold), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.

**Sync behavior**:
- Branch → cloud: YES (all writes propagate within 30s).
- Cloud → branch: NO.
- DIAN trigger: YES (on facturacion; cloud `dian_dispatcher` sends to DIAN provider).
- Hash chain impact: YES — every event writes a log row.

**Integration with other tables**:
- Reads from: `sesion` (the open anchor), `caja` (last snapshot), `factura_pagos`, `configuracion_tolerancias`, `log_transaccional`.
- Writes to: `caja` (snapshots), `factura_pagos`, `facturas`, `alerta` (caja_baja, conditional), `log_transaccional`, `sync_queue`.
- Cross-cutting: the `sesion` stays `estado='abierta'` and is NEVER UPDATEd during the shift. All cash movements are captured by NEW `caja` rows — the snapshot pattern. The `sesion` row is the **invariant anchor**; `caja` rows are the **mutable history**. This separation is critical for the `[L-S]` UPDATE constraint: the only UPDATE is at cierre.
- Special: `caja_baja` alert (T41) is a system-detected alert type for low cash during shift. The threshold is configurable per branch (sprint 5; MVP uses global threshold from `configuracion_tolerancias` or a new `configuracion_caja_baja` singleton).
- Related: T33 (`caja`) covers the snapshot pattern; T05 (`facturas`) covers the facturacion flow.

### 7.3 Use Case: `uc.sesion.operator-cierre-shift-evening-full-cascade`

**Actor**: operator (branch)

**Real-world action**: At end of shift, operator clicks "Cerrar Caja" in `web_sucursal/TopBar`. Opens `CierreCajaForm`. Form pre-fills `valor_esperado_efectivo` = `valor_inicial + SUM(factura_pagos WHERE medio_pago='efectivo' AND uuid_sucursal=$branch AND created_at BETWEEN timestamp_apertura AND NOW())`. Operator counts cash in drawer, types `valor_efectivo_reportado`. Same for datafono (typically = expected). Backend runs the cierre TX: SELECT `sesion FOR UPDATE` (verify 'abierta') → UPDATE `sesion SET estado='cerrada', timestamp_cierre=NOW()` (gated by `ls_session_update_guard`) → INSERT `arqueo` with `diferencia = reportado - esperado` (T34) → INSERT `caja` snapshot (`tipo_movimiento='cierre'`) → (conditional) INSERT `alerta tipo_alerta='diferencia_arqueo'` if `ABS(diferencia) > tolerancia` (T41) → INSERT `log_transaccional`. Operator UI shows either "Cierre OK" or "Alerta emitida".

**Steps (BEFORE → DURING → AFTER)**:

**BEFORE**:
- `sesion`: 1 row, `estado='abierta'`, opened 8:00am (use case 7.1).
- `factura_pagos`: N rows for this sesion.
- `caja`: several snapshots.
- `arqueo`: NO rows for this sesion yet.

**STEPS**:
1. Operator opens `web_sucursal/CierreCajaForm`. Form pre-fills:
   - `valor_inicial_efectivo` = `sesion.valor_inicial_efectivo` (e.g., 50000).
   - `valor_esperado_efectivo` = `valor_inicial + SUM(factura_pagos.valor WHERE medio_pago='efectivo' AND created_at BETWEEN $sesion.timestamp_apertura AND NOW())` (e.g., 50000 + 80000 = 130000).
   - `tolerancia_efectivo` = `configuracion_tolerancias.vigente.tolerancia_efectivo` (e.g., 5000).
   - Same for datafono.
2. Operator counts cash in drawer; types `valor_efectivo_reportado = 128000` (vs expected 130000 → diferencia -2000).
3. Operator checks datafono terminal report; types `valor_datafono_reportado = 100000` (vs expected 100000 → diferencia 0).
4. Frontend POSTs `api_sucursal /sesiones/{uuid}` (PATCH) with `{valor_efectivo_reportado: 128000, valor_datafono_reportado: 100000, observaciones: 'cierre_normal'}`.
5. Backend: SELECT `sesion WHERE uuid=$uuid FOR UPDATE`. Verify `estado='abierta'`. Returns the sesion row.
6. Backend opens TX; SELECT chain anchor from `log_transaccional`.
7. Backend computes `diferencia_efectivo = 128000 - 130000 = -2000`, `diferencia_datafono = 0`.
8. UPDATE `sesion SET estado='cerrada', timestamp_cierre=NOW() WHERE uuid=$uuid`. The `ls_session_update_guard` trigger fires:
   - Validates NEW.estado='cerrada' AND OLD.estado='abierta'.
   - Validates NEW.timestamp_cierre > OLD.timestamp_apertura.
   - Validates NO other column is being modified.
   - Validates the TX includes a `log_transaccional` INSERT with `accion='sesion_cerrada'`. If missing → RAISE EXCEPTION.
9. INSERT `arqueo` row (T34 use case 7.1): `valor_efectivo_esperado=130000, valor_datafono_esperado=100000, valor_efectivo_reportado=128000, valor_datafono_reportado=100000, diferencia_efectivo=-2000, diferencia_datafono=0`, `observaciones='sesion=$sesion_uuid'`.
10. INSERT `caja` snapshot (T33 use case 7.4): `tipo_movimiento='cierre'`, `valor_efectivo=128000, valor_datafono=100000, observaciones='sesion=$sesion_uuid, arqueo=$arqueo_uuid'`.
11. If `ABS(diferencia_efectivo) > tolerancia_efectivo` (2000 < 5000 → no alert): SKIP alerta emission. If `ABS(diferencia_datafono) > tolerancia_datafono` (0 < 5000 → no alert): SKIP. (Both within tolerance in this scenario.)
12. INSERT `log_transaccional` (`accion='sesion_cerrada'`, `tabla_afectada='sesion'`, `uuid_registro_afectado=$sesion_uuid`, `datos_anteriores={estado:'abierta', timestamp_apertura, valor_inicial_efectivo: 50000}`, `datos_nuevos={estado:'cerrada', timestamp_cierre}`).
13. INSERT `log_transaccional` (`accion='arqueo_registrado'`, `tabla_afectada='arqueo'`, `uuid_registro_afectado=$arqueo_uuid`, `datos_nuevos={valor_efectivo_esperado:130000, valor_efectivo_reportado:128000, diferencia_efectivo:-2000}`).
14. INSERT `log_transaccional` (`accion='caja_snapshot'`, `tabla_afectada='caja'`, `datos_nuevos={tipo_movimiento:'cierre', valor_efectivo:128000}`).
15. `queue_processor.enqueue('sesion', $uuid, $snapshot)` + `enqueue('arqueo', $uuid, $snapshot)` + `enqueue('caja', $uuid, $snapshot)`.
16. Backend returns `{uuid: $sesion_uuid, estado:'cerrada', timestamp_cierre, diferencia_efectivo:-2000, diferencia_datafono:0, alerta_emitida:false}`.

**AFTER**:
- `sesion`: 1 row, `estado='cerrada'`, `timestamp_cierre` set. UNIQUE partial index no longer constrains (the row is `cerrada`).
- `arqueo`: 1 new row (correlation to sesion via `observaciones` text + `uuid_sucursal` + `created_at`).
- `caja`: 1 new snapshot (`tipo_movimiento='cierre'`).
- `log_transaccional`: 3 rows.
- `sync_queue`: 3 items.

**Tables touched (writes)**: `sesion` (1 UPDATE — `[L-S]` exception), `arqueo` (1 INSERT), `caja` (1 INSERT), `log_transaccional` (3 rows), `sync_queue` (3 items).
**Tables touched (reads)**: `sesion` (FOR UPDATE), `factura_pagos` (SUM for expected), `configuracion_tolerancias` (vigente — tolerance check), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `sesion.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`; `arqueo.uuid_sucursal` → `sucursal.uuid`; `caja.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `sesion.uuid` or `arqueo.uuid` or `caja.uuid`.

**Sync behavior**:
- Branch → cloud: YES — sesion UPDATE replicates (same `ls_session_update_guard` validates on cloud side); arqueo + caja INSERTs propagate.
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 3 rows.

**Integration with other tables**:
- Reads from: `sesion` (the open anchor), `factura_pagos` (sum expected), `configuracion_tolerancias` (vigente tolerance), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `sesion` (UPDATE via `[L-S]`), `arqueo` (T34), `caja` (T33), `alerta` (T41 if exceeded), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **end-of-shift** atomic cascade. The `[L-S]` UPDATE constraint is the cornerstone — without it, the cierre could happen without an audit row, breaking the probatory integrity. The trigger enforces "every state mutation has a log row in the same TX".
- Critical: if any write in the cascade fails (e.g., `log_transaccional` hash chain break), the WHOLE cierre rolls back. The operator retries. The sesion stays `estado='abierta'` until the cierre succeeds atomically.
- Same pattern: T42 (`login`) uses `ls_session_update_guard` for the `cerrado` transition; both `[L-S]` tables share the trigger logic.
- Related: T34 (`arqueo`) use case 7.1 covers the arqueo INSERT + tolerance check; T33 (`caja`) use case 7.4 covers the cierre snapshot; T41 (`alerta`) use case 7.1 covers the alerta emission.

### 7.4 Use Case: `uc.sesion.operator-change-mid-shift-close-then-open-new-sesion`

**Actor**: operator A (closing) + operator B (opening)

**Real-world action**: Operator A is on shift 8am-4pm. Operator B takes over at 4pm. Per AGENTS.md policy, parallel shifts are NOT allowed — operator A must close the sesion, then operator B opens a new sesion. Operator A's cierre proceeds exactly as in use case 7.3 (with reported cash counts matching expected). Operator B's apertura uses the `valor_efectivo_reportado` from operator A's cierre as the `valor_inicial_efectivo` for the new sesion — the cash physically transfers from drawer to drawer without leaving the booth.

**Steps (BEFORE → DURING → AFTER)**:

**BEFORE**:
- `sesion` (operator A's): 1 row, `estado='abierta'`, opened at 8:00am (8h ago).
- `caja`: snapshots throughout the shift.

**STEPS**:
1. At 4:00pm, operator A clicks "Cerrar Caja". Cierre TX proceeds (use case 7.3).
2. Operator A hands the cash drawer to operator B. The drawer contains the reported amount (e.g., 128000 efectivo).
3. Operator B opens `web_sucursal/SesionForm`. Form requires `valor_inicial_efectivo` — the system pre-fills with operator A's `valor_efectivo_reportado` (128000) as a suggestion. Operator B confirms or adjusts (if there's a physical discrepancy, operator B types the actual count and an `observaciones` note explaining the variance).
4. Frontend POSTs `api_sucursal /sesiones` with `{valor_inicial_efectivo: 128000, valor_inicial_datafono: 0, observaciones: 'cambio_turno: operador A → B'}`.
5. Backend: SELECT verify NO open sesion exists. Operator A's sesion is `estado='cerrada'`, so no conflict.
6. Backend opens TX; SELECT chain anchor from `log_transaccional`.
7. INSERT `sesion` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$operator_B`, `timestamp_apertura=NOW()`, `valor_inicial_efectivo=128000, valor_inicial_datafono=0`, `estado='abierta'`).
8. INSERT `caja` snapshot (`tipo_movimiento='cambio_turno'`, `valor_efectivo=128000, valor_datafono=0`, `observaciones='sesion_anterior=$sesion_A_uuid, sesion_nueva=$sesion_B_uuid'`).
9. INSERT `log_transaccional` (`accion='sesion_apertura'`, `datos_nuevos={valor_inicial_efectivo: 128000, cambio_turno_from: $operator_A}`).
10. `queue_processor.enqueue('sesion', $uuid, $snapshot)` + `enqueue('caja', $uuid, $snapshot)`.

**AFTER**:
- `sesion`: 2 rows — A (cerrada) + B (abierta). UNIQUE partial index allows because A is cerrada.
- `caja`: 1 new snapshot (`tipo_movimiento='cambio_turno'`).

**Tables touched (writes)**: `sesion` (1 INSERT for B's apertura — A's cierre already happened in use case 7.3), `caja` (1 INSERT), `log_transaccional` (1+ rows), `sync_queue` (2 items).
**Tables touched (reads)**: `sesion` (verify no open conflict), `caja` (last snapshot for carryover), `log_transaccional`, `usuarios`, `sucursal`.
**FKs traversed**: `sesion.uuid_usuario` → `usuarios.uuid` (operator B), `sesion.uuid_sucursal` → `sucursal.uuid`; `caja.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (operator B), `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `sesion.uuid` or `caja.uuid`.

**Sync behavior**:
- Branch → cloud: YES.
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 2 rows.

**Integration with other tables**:
- Reads from: `sesion` (A's cerrada row for carryover), `caja` (last snapshot), `log_transaccional`.
- Writes to: `sesion` (INSERT for B), `caja` (cambio_turno snapshot), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **operator handover** pattern. Per AGENTS.md policy "no parallel shifts", the cash drawer physically transfers but the data model treats them as TWO separate sesions. The `caja tipo_movimiento='cambio_turno'` snapshot links them for audit. The cash variance between A's `valor_efectivo_reportado` and B's `valor_inicial_efectivo` is captured in `observaciones` if B adjusted.
- Sprint 5 may add explicit `sesion.uuid_sesion_anterior` FK for direct lineage; currently linked via `observaciones` text on the `caja` snapshot.
- Related: T33 (`caja`) covers the snapshot patterns (apertura, cambio_turno, cierre, replenishment, withdrawal).

### 7.5 Use Case: `uc.sesion.stale-shift-detected-by-nightly-cron-16h-abierto-emits-alerta`

**Actor**: system (`workers/stale_session_detector` nightly cron)

**Real-world action**: Operator A opened a sesion at 8:00am yesterday, then forgot to close before going home. Today is 10:00am (26 hours later). The nightly cron at 02:00 cloud time detected: `SELECT * FROM sesion WHERE estado='abierta' AND timestamp_apertura < NOW() - INTERVAL '16 hours'`. Backend SELECTs the operator, INSERTs `alerta tipo_alerta='manual'` with `observaciones='sesion=$uuid, abierta_desde=$timestamp_apertura, horas_abiertas=26, posible_olvido_cierre'`. Admin triages: typically contacts operator to confirm whether to close retroactively or to mark as fraud.

**Steps (BEFORE → DURING → AFTER)**:

**BEFORE**:
- `sesion`: 1 row, `estado='abierta'`, opened 26 hours ago.

**STEPS**:
1. Cloud `workers/stale_session_detector/__main__.py` runs at 02:00 cloud time.
2. SELECT stale open sessions: `SELECT s.*, u.nombre AS operador_nombre, su.nombre AS sucursal_nombre FROM sesion s JOIN usuarios u ON s.uuid_usuario=u.uuid JOIN sucursal su ON s.uuid_sucursal=su.uuid WHERE s.estado='abierta' AND s.timestamp_apertura < NOW() - INTERVAL '16 hours'`.
3. For each stale sesion: check for existing open `alerta tipo_alerta='manual'` for this sesion (deduplication). If none exists:
4. `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='manual', uuid_usuario=$operator, observaciones='sesion=$sesion_uuid, abierta_desde=$timestamp_apertura, horas_abiertas=$hours, posible_olvido_cierre')`.
5. INSERT `alerta` workflow root row.
6. INSERT `log_transaccional` (`accion='alerta_emitida'`, `datos_nuevos={tipo_alerta:'manual', sesion_uuid, horas_abiertas}`).
7. (Optional) Sprint 5: send notification to operator's email/SMS.
8. Admin sees alert in `web_admin/AlertasList` filter `tipo_alerta='manual'`. Admin clicks → `AlertaDetail` → drills into the sesion → drills into `factura_pagos` for the time period.
9. Admin triages: typically calls operator, who closes the sesion retroactively (POST `/sesiones/{uuid}` PATCH with `valor_efectivo_reportado` based on actual cash + late factura adjustments). The cierre UPDATE proceeds (use case 7.3), with `observaciones='cierre_retroactivo_por_alerta_stale, admin=$admin_uuid'`. The `log_transaccional` row records the alert resolution.
10. INSERT `alerta` chain row with `estado='resuelta', uuid_alerta_padre=$root.uuid, uuid_usuario=$admin, observaciones='resolved: cierre retroactivo autorizado'`.

**AFTER**:
- `sesion`: 1 row, `estado='cerrada'` (after admin-authorized retroactive cierre).
- `alerta`: 1 root row + 1 resuelta chain row.
- `arqueo`: 1 new row (from the retroactive cierre, possibly with discrepancy).

**Tables touched (writes — detection)**: `alerta` (1 root row), `log_transaccional` (1 row).
**Tables touched (writes — retroactive cierre)**: `sesion` (UPDATE), `arqueo` (INSERT), `caja` (INSERT), `alerta` (chain row resuelta), `log_transaccional` (3 rows), `sync_queue`.
**Tables touched (reads)**: `sesion` (stale check), `usuarios` (operator), `sucursal`, `log_transaccional` (chain anchor), `alerta` (dedup check).
**FKs traversed**: `sesion.uuid_usuario` → `usuarios.uuid`; `sesion.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (the operator who forgot); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid` or `sesion.uuid` or `arqueo.uuid`.

**Sync behavior**:
- Branch → cloud: YES (the alerta originates on branch side via cron; the cron is cloud-side per meta-PRD-02, but branch DB has the sesion row).
- Cloud → branch: NO (the alerta is informational for cloud admin; branch is unaware).
- DIAN trigger: NO.
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `sesion` (stale check), `usuarios`, `sucursal`, `log_transaccional`, `alerta` (dedup).
- Writes to: `alerta` (workflow root + chain resuelta), `sesion` (UPDATE — retroactive cierre), `arqueo`, `caja`, `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **abuse detection** pattern. The 16-hour threshold is configurable (sprint 5 may make it per-branch). The retroactive cierre is the resolution — admin authorizes a `[L-S]` UPDATE on a stale `estado='abierta'` row. This is the ONLY legitimate path for closing a stale sesion without operator present (the trigger still validates the UPDATE).
- Edge case: if the stale sesion is actually fraud (operator absconded with cash), admin marks the alerta with `observaciones='fraud_investigation_opened'` and opens a `reclamos` workflow (T40). The sesion is NEVER closed retroactively until the investigation concludes.
- Related: T41 (`alerta`) use case 7.6 covers manual emission; T40 (`reclamos`) covers the fraud investigation.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + `ls_session_update_guard` trigger + UNIQUE partial index), 5 (audit constraints — REVOKE + trigger), 6 (cloud admin API for read), 7 (branch API for apertura/cierre), 8 (Pydantic schemas), 10 (cloud sync worker for replication), 11 (branch sync worker for replication), 12 (sync_queue interop), 13 (web_admin SesionesPanel), 14 (web_sucursal SesionForm + CierreCajaForm), 15 (shadcn UI components for forms), 20 (structlog), 21 (Prometheus counters — sessions per branch per day), 24 (pytest), 28 (docker compose), 30 (stale_session_detector cron), 31 (security audit — fraud detection via stale shifts).

## 9. RED Tests
- (RED) INSERT `sesion` with `estado='abierta'` for a branch with NO open sesion → success.
- (RED) INSERT second `sesion` with `estado='abierta'` for same branch → UNIQUE partial index violation → `SESION_YA_ABIERTA`.
- (RED) UPDATE `sesion SET estado='cerrada', timestamp_cierre=NOW()` AND concurrent `log_transaccional` INSERT in same TX → success.
- (RED) UPDATE `sesion SET estado='cerrada'` WITHOUT concurrent `log_transaccional` → `LS_SESSION_LOG_MISSING`.
- (RED) UPDATE `sesion SET valor_inicial_efectivo=$X` (any column other than `estado`, `timestamp_cierre`) → `LS_SESSION_FORBIDDEN_COLUMN`.
- (RED) UPDATE `sesion SET timestamp_cierre=$X` without changing estado → trigger raises (cierre requires estado='cerrada').
- (RED) UPDATE `sesion SET estado='cerrada', timestamp_cierre=$t WHERE timestamp_cierre <= timestamp_apertura` → `LS_SESSION_INVALID_TIMESTAMP`.
- (RED) DELETE `prod.sesion` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Cierre TX cascade: sesion UPDATE + arqueo INSERT + caja INSERT + log_transaccional INSERT all atomic. ROLLBACK on any failure.
- (RED) Tolerance exceeded: INSERT alerta in same TX; rollback on alerta failure → sesion UPDATE also rolls back.
- (RED) Stale detection: sesion abierta > 16h → cron emits `alerta tipo_alerta='manual'`.
- (RED) Operator change: sesion A cerrada + sesion B abierta → 2 sesion rows, UNIQUE partial index allows because A is cerrada.
- (RED) FK RESTRICT: deleting `usuarios` with sesion rows → error.
- (RED) Cierre blocks subsequent facturacion: closed sesion → `POST /facturas` returns 422 `sesion_cerrada`.
- (RED) `valor_inicial_efectivo` immutability: UPDATE to change initial value → `LS_SESSION_FORBIDDEN_COLUMN` (only `estado` + `timestamp_cierre` allowed).

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + `ls_session_update_guard` trigger + UNIQUE partial index.
- [ ] F1.x `parkos_core/caja/sesion_writer.py::open_sesion()` (apertura INSERT).
- [ ] F1.x `parkos_core/caja/sesion_writer.py::close_sesion()` (cierre UPDATE + cascade orchestrator).
- [ ] F1.x Recursive helper for "open sesion per branch" check.
- [ ] IT-5.x: `api_sucursal/routers/sesiones.py::POST /sesiones` (operator apertura).
- [ ] IT-5.x: `api_sucursal/routers/sesiones.py::PATCH /sesiones/{uuid}` (cierre with cascade).
- [ ] IT-5.x: existing-sesion check (409 friendly error).
- [ ] IT-5.x: cascade orchestrator integration with `arqueo_writer` (T34), `caja_writer` (T33), `alerta_writer` (T41).
- [ ] IT-5.x: tolerance check integration with `configuracion_tolerancias` snapshot semantic (T29).
- [ ] IT-5.x: `api_admin/routers/sesiones.py::GET /sesiones` (paginated, filterable).
- [ ] IT-5.x: `api_admin/routers/sesiones.py::GET /sesiones/{uuid}` (detail with snapshot + arqueo correlation).
- [ ] IT-5.x: `workers/stale_session_detector/__main__.py` nightly cron at 02:00 cloud.
- [ ] IT-5.x: `web_sucursal/SesionForm` (apertura form).
- [ ] IT-5.x: `web_sucursal/CierreCajaForm` (cierre form with tolerance warning).
- [ ] IT-5.x: `web_admin/SesionesPanel` (cross-branch open sessions dashboard).
- [ ] Sprint 5: explicit `uuid_sesion` FK on `factura_pagos`, `arqueo`, `alerta` (vs current correlation via `observaciones` + `created_at`).
- [ ] Sprint 5: explicit `sesion.uuid_sesion_anterior` FK for operator change lineage.
- [ ] Sprint 5: per-branch `caja_baja` threshold configuracion (vs current global).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator forgets to close sesion at end of shift | Med | Stale cron emits alerta after 16h; sprint 5: per-branch shorter threshold (8h) + admin alerts |
| Two operators try to open sesion simultaneously (race condition) | Low | UNIQUE partial index serializes; second attempt gets `SESION_YA_ABIERTA` |
| Cierre TX fails halfway (e.g., `log_transaccional` hash chain break) | Low | Whole TX rolls back; operator retries; sesion remains `estado='abierta'` |
| Operator leaves with cash (fraud) | Low | Stale cron + `caja_baja` alert + admin `reclamos` investigation |
| Tolerance miscalibration: too tight → false alertas flood admin | Med | Tolerance configurable via `configuracion_tolerancias`; admin monitors alerta rate; sprint 5: per-branch tolerance overrides |
| Operator counts cash wrong (typo in `valor_efectivo_reportado`) | Low | Form requires confirmation modal; arqueo correction via NEW row + `uuid_arqueo_original` (sprint 5, per T34 use case 7.1 note) |
| Mid-shift operator change without proper cierre → cash unaccounted | Low | UI blocks new apertura if previous sesion is `abierta`; admin must authorize retroactive cierre |
| `[L-S]` trigger bypassed by direct DB connection (rogue admin) | Low | Trigger on table itself; even `rol_admin_auditor` cannot bypass without DROP TRIGGER (which is logged in `log_transaccional`) |
| `valor_inicial_efectivo` typo (operator types wrong amount at apertura) | Low | Form requires confirmation modal; correction via `anulaciones` workflow (T39) if discovered within hours; sprint 5: explicit correction table |
| High-volume branch generates many sesions (multi-shift 24h operations) | Med | 1-3 rows per branch per day; trivial volume. Partitioning not needed. |
| Stale cron false positive (legitimate 24h operation during holiday) | Low | Admin triages; sprint 5: per-branch skip flag |

## 12. Open Questions
- (a) Should `valor_inicial_datafono` ever be non-zero? Currently always 0 (datafono is terminal-tracked). Some businesses might track datafono "starting float".
- (b) Should `caja_baja` alert be emitted hourly during shift, or only at cierre? Currently hourly cron; sprint 5 may add real-time on each `caja` snapshot.
- (c) Auto-close sesion on app shutdown (operator closes browser without logout)? Currently NO — sesion stays abierta until explicit operator action. Sprint 5 may auto-close on grace period.
- (d) Should `sesion` rows survive `usuarios` version archive? Currently RESTRICT FK prevents `usuarios` deletion but allows version archive; old sesion rows point to the version-active UUID at INSERT time.
- (e) Multi-operator single-shift (e.g., 2 operators at one branch during busy period)? Currently NO per AGENTS.md policy; sprint 5 may add `sesion.uuid_usuario_secundario` for tagging without parallel shifts.
- (f) Should the `caja_baja` threshold be a `[V]` singleton like `configuracion_tolerancias`? Sprint 5 may add `configuracion_caja_baja`.
- (g) `valor_inicial_efectivo` correction: currently requires `anulaciones` workflow if discovered post-apertura. Sprint 5 may add a direct `[V]` correction flow with audit.
- (h) Stale threshold (16h) configurable per branch? Sprint 5 — currently global.
- (i) Should the stale cron also close the sesion automatically after N days (e.g., 7 days)? Currently NO — admin triages manually.
- (j) `sesion` reporting: should admin dashboard show "average shift duration" / "shifts per operator per week"? Sprint 5 analytics.
- (k) Multi-branch operator (admin who works at 2 branches in one day) — does this require 2 sesions? Yes, one per branch. The operator changes `uuid_sucursal` via re-login.
