# Exploration: HU-F1.13 — Endpoints arqueo + siembra `tipo_arqueo.cierre_dia` + GAP-BE-05 bundleado

> **Phase**: explore (sdd-explore) · **Status**: ready for `sdd-propose`
> **HU ID**: HU-F1.13 (Fase-1 prerequisites — backend, bundle includes GAP-BE-05 in-scope correction)
> **Inputs**: `plan.md` lines 1058-1101 (240 LOC, 4 atomic tasks T1..T4), `modelo_datos_er.mmd` blocks `tipo_arqueo` [V] (lines 167-185), `arqueo` [A] (lines 957-978), `sesion` [L-S] (lines 715-735), `alerta` [L-W] (lines 737-758), `configuracion_tolerancias` [V] (lines 250-268), `factura_pagos` [A], `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP audit-trail migration = current head pre-F1.13), `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 head template with conditional siembra + permission seed pattern — to be mirrored by 0031), `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry table for `tipo_alerta` identifiers, business-key PK, inmutable trigger), `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` (line 53 — GAP-BE-05 exact site #1), `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (line 257 — GAP-BE-05 exact site #2), `backend/packages/parkos_core/src/parkos_core/models/V/tipo_arqueo.py`, `backend/packages/parkos_core/src/parkos_core/models/A/arqueo.py` (lines 26-84), `backend/packages/parkos_core/src/parkos_core/models/L_S/sesion.py` (lines 20-47), `backend/packages/parkos_core/src/parkos_core/models/L_W/alerta.py`, `backend/packages/parkos_core/src/parkos_core/repo/{append_only,workflow,session_cycle,sesion_activa,alert_types,idempotency}.py`, `openspec/specs/operations/spec.md` lines 3217-3651 (XR1..XR5 progression), lines 3371-3611 (REQ-OPS-083..090 last-req-number series).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a328957`, F1.12 just shipped) · **PR target**: `origin/dev`.

---

## 1. Title & Goal

**Title**: "Endpoints arqueo + siembra `tipo_arqueo.cierre_dia` + corrección bundleada de GAP-BE-05 (permiso mal asignado en `caja.py`/`caja_sesion.py`)"

**Goal**: Deliver two write endpoints + one read endpoint on top of the already-shipped `prod.tipo_arqueo` [V] (3 existing values: `cierre_turno | auditoria | cierre_sesion` per `modelo_datos_er.mmd` line 171), `prod.arqueo` [A] (AppendOnlyBase composite PK `uuid + fecha_retencion_hasta` per `models/A/arqueo.py:26-84`), `prod.sesion` [L-S] (SessionBase + `ls_session_guard` trigger), `prod.alerta` [L-W] (WorkflowBase state machine `{activa -> descartada | resuelta}` per `repo/workflow.py:85-90`), `prod.configuracion_tolerancias` [V], `prod.factura_pagos` [A] (immutable), plus 2 bundled source-only GAP-BE-05 corrections:

- **`POST /api/v1/caja/arqueo`** — server-resolves `uuid_tipo_arqueo` (resolves to `codigo` ∈ `{auditoria, cierre_turno, cierre_dia}`) + computes `valor_efectivo_esperado`/`valor_datafono_esperado` from active session + `factura_pagos` (READ-only) + `configuracion_tolerancias`, then in a **single transaction** (`await session.commit()` exactly once, KD-ARQUEO-01) INSERTs:
  1. `prod.arqueo` [A] via `repo/append_only.append_event` (KD-ARQUEO-02)
  2. **`cierre_dia` path only**: mass `prod.sesion` UPDATE per-row via `repo/session_cycle.close_session_with_log` to satisfy `ls_session_guard` (KD-ARQUEO-03)
  3. **`diferencia > tolerancia` (absolute monto, KD-ARQUEO-04)**: `prod.alerta` [L-W] INSERT initial via `repo/workflow.append_transition` (KD-ARQUEO-05)
  4. `prod.log_transaccional` [A] rows (co-transactional, emitted by helpers)

- **`GET /api/v1/caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD`** — returns one row per `sesion` of the day at that branch (JOIN `arqueo` + `factura_pagos` sum by `medio_pago`) + `cierre_dia` aggregate at bottom (KD-ARQUEO-07).

- **`GAP-BE-05 bundled (DEC-ARQUEO-08)`** — 2-line source-only fix, NO migration:
  - `api/v1/caja.py:53` — `permission_required="emitir_factura"` → `"realizar_arqueo"`.
  - `api/v1/caja_sesion.py:257` — `permission_required="emitir_factura"` → `"abrir_cerrar_caja"`.

**Defense in depth (5 layers — XR6 mirror)**: (a) KD-3 issuer chain + `realizar_arqueo` permission; (b) tenant scope post-V1; (c) KD-ARQUEO-01 single-commit AST walk; (d) [A] append-only AST walk; (e) handler status mapping + `Cache-Control: no-store`.

**Scope**: ~240 LOC production + ~150 LOC tests + ~80 LOC MIGRATION 0031 (REAL siembra, not NO-OP) = ~470 LOC cumulative.

---

## 2. Context & Background

- **F1.12 just closed** (commit `a328957`). Migration head = `0030_venta_suscripcion_optional` (NO-OP). F1.13 = MIGRATION `0031_arqueo_cierre_dia_and_gap_be_05` (REAL siembra).
- **`prod.tipo_arqueo` exists** [V], migration 0001 lines 167-185, bi-temporal VersionedBase. UK `tipo_arqueo_uk01(codigo, vigente_desde)` per `models/V/tipo_arqueo.py:28`. Currently seeded with 3 values. 4th `cierre_dia` (A-07) added by F1.13.
- **`prod.arqueo` exists** [A], migration 0001 line 957+, `AppendOnlyBase` composite PK `uuid + fecha_retencion_hasta`, monthly pg_partman RANGE partition. 7 business columns. INSERT-only via `repo/append_only.append_event`.
- **`prod.sesion` exists** [L-S], `SessionBase`. UPDATE only via `repo/session_cycle.close_session_with_log` — `ls_session_guard` trigger rejects direct UPDATE without co-transactional `log_transaccional` row (per `repo/session_cycle.py:286-289`).
- **`prod.alerta` exists** [L-W], `WorkflowBase` with state machine `{activa -> descartada | resuelta}` per `repo/workflow.py:85-90`.
- **`prod.alert_types` exists** (out-of-catalog [A] registry), business-key PK `tipo_alerta`, inmutable trigger `alert_types_inmutable` (per migration 0013). 9 codes seeded as of 2026-09-15. **`descuadre_critico` NOT yet seeded** (grep across `migrations/versions/` returns 0 matches). F1.14 plan.md line 1131 plans to seed it, but F1.14 is downstream → **DEC-ARQUEO-09b: bundle in MIGRATION 0031 Op 2** with `IF NOT EXISTS` + `ON CONFLICT (tipo_alerta) DO NOTHING` (idempotent — F1.14's future seed becomes no-op).
- **`prod.configuracion_tolerancias` exists** [V], UK `configuracion_tolerancias_uk01(uuid_sucursal, vigente_desde)`. 3 columns: `uuid_sucursal` (FK, NULL=default global), `tolerancia_efectivo`, `tolerancia_datafono`.
- **`prod.factura_pagos` exists** [A], F1.9 closed, 100% immutable. F1.13 reads only via `SELECT ... WHERE uuid_sesion=...`, never mutates.
- **`ArqueoCreate` + `ArqueoRead` + `ArqueoReadList` + `ArqueoUpdate` + `ArqueoFilter`** Pydantic schemas pre-existing in `schemas/caja.py`. F1.13 EXTENDS with `ArqueoCreateV2` (new write contract) + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams`.
- **Helper modules REUSE**: `repo/append_only.append_event` (lines 64-124); `repo/workflow.append_transition` (lines 110-237) + `STATE_MACHINES['alerta']`; `repo/session_cycle.close_session_with_log` (lines 274-349); `repo/alert_types.validate` + `AlertaFactory.fire`; `repo/idempotency.guard` + `store_response`; `repo/sesion_activa.get_sesion_activa`; `api/v1/_helpers.no_store_headers()` + `apply_no_store_header()`.
- **GAP-BE-05 verbatim from plan.md line 7359**: "Cambiar `permission_required='emitir_factura'` a `permission_required='realizar_arqueo'` en `caja.py:53` y en la porción de `caja_sesion.py:204` que protege `GET /caja/arqueo`/`GET /caja/caja`; usar `abrir_cerrar_caja` para el mount de solo lectura de `sesion`. Es una corrección de una línea por archivo, sin migración."
- **Existing permission inventory**: `realizar_arqueo` pre-seeded per plan.md line 4549; `abrir_cerrar_caja` pre-seeded per F1.3. NO new permissions or role grants needed for F1.13.

### 2.1 Critical Architectural Conflict — Cross-table atomicity vs per-row sesion guard (RESOLVED in §3)

The fundamental design question: F1.13 commits `arqueo` [A] (1 INSERT) + `sesion` [L-S] UPDATEs (only `cierre_dia` path) + `alerta` [L-W] (conditional) + `log_transaccional` [A] (N+1 rows). Resolution: single `await session.commit()` covers all helper calls; per-row `close_session_with_log` does `(log INSERT + flush + UPDATE)` inside the outer TX.

---

## 3. Architectural Conflict Resolution — DEC-ARQUEO-01 + KD-ARQUEO-01

### 3.1 The conflict (R1 HIGH)

The handler writes 4 table families. Two valid PostgreSQL patterns: single-commit (F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 precedent) vs SAVEPOINTs. Complication: `ls_session_guard` DB trigger mandates per-row `log_transaccional` BEFORE any `UPDATE prod.sesion`.

### 3.2 The resolution — DEC-ARQUEO-01: single `await session.commit()` for ALL writes

1. All helpers (`append_event`, `append_transition`, `close_session_with_log`) stay commit-free — `session.add()` + `await session.flush()` only.
2. ONE `await session.commit()` at Step 12 of the handler body.
3. NO SAVEPOINTs — entire TX rolls back on any helper raise.
4. For `cierre_dia` with N open sesiones: iterate `for sesion in open_sessions: await close_session_with_log(... log_tx=True)` — each iteration does `(log INSERT + flush + UPDATE)`.
5. **Lock ordering** (KD-ARQUEO-08): `SELECT FOR UPDATE` on `prod.tipo_arqueo` row FIRST (V1) → serializes concurrent `cierre_dia` per operator.

### 3.3 Why this matters

- Cross-table atomicity for `arqueo + alerta` pair (no arqueo without its alerta when descuadre_critico).
- `ls_session_guard` per-row trigger mandates log-first ordering for every sesion UPDATE.
- AST walk `tests/static/test_arqueo_handler_single_commit.py` enforces single-commit invariant.
- Lock ordering rule prevents deadlocks under concurrent operators.

---

## 4. Affected Areas

### 4.1 Files READ (existing infrastructure — F1.13 reuse, NO modifications except GAP-BE-05 sites)

- `migrations/versions/0001_initial_schema.py` (lines 167-185, 250-268, 715-735, 737-758, 957-978).
- `migrations/versions/0013_add_alert_types.py`, `0029_reimpresion_siembra_and_permiso_anular.py` (template), `0030_venta_suscripcion_optional.py` (current head).
- `models/V/{tipo_arqueo, configuracion_tolerancias}.py`, `models/A/{arqueo, log_transaccional, alert_types, factura_pagos}.py`, `models/L_S/sesion.py`, `models/L_W/alerta.py`.
- `repo/{append_only, workflow, session_cycle, sesion_activa, alert_types, idempotency, hash_chain}.py`.
- `schemas/caja.py` (EXTEND only).
- `api/v1/{operacion, facturacion, workflows_reimpresion, _helpers, deps}.py`.
- `auth/{jwt_issuer_guard, tenancy}.py`.
- `tests/static/{test_no_raw_dml_on_a_tables.py, test_no_raw_dml_on_ls_tables.py, test_no_raw_dml_on_lw_tables.py, test_salida_handler_step_order.py, test_factura_handler_single_commit.py, test_fe_handler_single_commit.py, test_workflow_handler_single_commit.py, test_venta_handler_*.py, test_no_write_after_insert.py}` — AST walk precedents.

### 4.2 Files WRITTEN (F1.13 implementation)

- `repo/arqueo.py` (NEW, ~100 LOC) — 9 typed helpers: `resolver_tipo_arqueo_por_uuid`, `resolver_tolerancia_vigente`, `calcular_esperado_sesion`, `listar_sesiones_abiertas_del_dia`, `validar_sesion_abierta_para_arqueo`, `calcular_diferencia`, `es_descuadre_critico`, `insertar_arqueo`, `insertar_alerta_descuadre_critico`, `cerrar_sesiones_del_dia_bulk`.
- `schemas/caja.py` (EXTEND, +90 LOC) — `ArqueoCreateV2`, `ArqueoReadForHandler`, `ArqueoResumenItem`, `ArqueoResumenRead`, `CierreDiarioQueryParams`.
- `api/v1/caja_arqueo.py` (NEW, ~180 LOC) — dedicated `APIRouter` with `POST /caja/arqueo` (12-step chain) + `GET /caja/arqueo/resumen` (6-step chain).
- `migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (NEW, ~80 LOC, REAL siembra) — Op 0 pre-flight DO $$ + Op 1 siembra `tipo_arqueo.codigo='cierre_dia'` + Op 2 siembra `alert_types.tipo_alerta='descuadre_critico', severity='critical'` + Op 3 NO-DDL comment for GAP-BE-05.
- `api/v1/caja.py` (MODIFY, 1 line at :53, GAP-BE-05 site #1) — `emitir_factura` → `realizar_arqueo`.
- `api/v1/caja_sesion.py` (MODIFY, 1 line at :257, GAP-BE-05 site #2) — `emitir_factura` → `abrir_cerrar_caja`.

### 4.3 Test files (NEW)

- `tests/unit/test_arqueo_repo.py` (~50 LOC, 5 tests)
- `tests/unit/test_arqueo_handler.py` (~30 LOC, **4 tests mandated by plan.md line 1093**): sin diferencia/justificada/sobre_tolerancia/sin_justificacion
- `tests/unit/test_cierre_dia.py` (~40 LOC, 2 tests)
- `tests/unit/test_arqueo_resumen.py` (~30 LOC, 3 tests)
- `tests/static/test_arqueo_handler_single_commit.py` (~15 LOC, KD-ARQUEO-01 walk)
- `tests/static/test_arqueo_handler_no_raw_dml.py` (~20 LOC)
- `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (~15 LOC, NEW walk — no precedent)
- `tests/static/test_arqueo_handler_no_update_on_a_tables.py` (~15 LOC)
- `tests/integration/test_migration_0031_idempotency.py` (~15 LOC, 2 tests)

### 4.4 Cumulative LOC

- Production: ~290 LOC (vs plan 240 = +20% absorbed by 12-step handler chain)
- Tests: ~220 LOC across 9 files
- Migration: ~80 LOC (REAL)
- GAP-BE-05: 2 lines modified
- Total: ~590 LOC

---

## 5. Regulatory / Business Rules

- **Colombian parking industry context** (CU-10): arqueo es operación interna de control de caja. NO aplica DIAN/IRES específica.
- **Audit trail** (PR2 + PR6): `log_transaccional` co-INSERTed by helpers; handler writes no logs directly.
- **CU-10 BR1** (plan.md line 2598): base = la configurada al **inicio del arqueo**, NO la del inicio del turno. Lee `config_caja.base_inicial` (vía `configuracion_tolerancias`-pattern vigente-row lookup).
- **CU-10 BR3** (plan.md line 2600): cambios de base during active jornada permitidos; arqueos ya cerrados inmutables.
- **Tolerancia = monto absoluto** (plan.md line 1065, line 1093): `|diferencia| > tolerancia`, NOT pct.
- **Justificación asimétrica** (plan.md lines 1086-1091, line 2476):
  - `auditoria`: justificación OPCIONAL.
  - `cierre_turno`/`cierre_dia`: justificación OBLIGATORIA cuando diferencia != 0 (else 400 `justificacion_requerida`).
- **factura_pagos inmutable** (plan.md line 1065): reads only, never modifies.
- **Sync replication**: `tipo_arqueo`/`configuracion_tolerancias` cloud→branch CATALOGs; `arqueo`/`sesion`/`alerta` branch→cloud. F1.13 NO toca sync_catalog (all entries pre-existing).
- **Concurrency**: KD-ARQUEO-08 lock on `tipo_arqueo` row + per-sesion `SELECT FOR UPDATE` in `cierre_turno`.

---

## 6. Existing Infrastructure

### 6.1 Tables (5+ exist; F1.13 needs only DATA seeds)

- `prod.tipo_arqueo` [V] — UK `tipo_arqueo_uk01`. 3 seeded values. **Add `cierre_dia`**.
- `prod.arqueo` [A] — composite PK, monthly partitioned, INSERT-only.
- `prod.sesion` [L-S] — UPDATE only via `close_session_with_log`.
- `prod.alerta` [L-W] — workflow with `uuid_alerta_padre` chain FK.
- `prod.alert_types` — registry, 9 codes seeded. **Add `descuadre_critico`**.
- `prod.configuracion_tolerancias` [V] — 3 columns, branch override pattern.
- `prod.factura_pagos` [A] — F1.9 inmutable.
- `prod.usuarios` [V] — F1.13 reads `nombre` for cajero column.
- `prod.log_transaccional` [A] — hash chain carrier.

### 6.2 ORM models (all exist, reuse)

- `models/V/tipo_arqueo.py:18-33`, `models/A/arqueo.py:26-84`, `models/L_S/sesion.py:20-47`, `models/L_W/alerta.py`, `models/A/alert_types.py`, `models/V/configuracion_tolerancias.py`, `models/A/factura_pagos.py`.

### 6.3 Repo helpers — REUSE + NEW

**REUSE**: `repo/append_only.append_event` (KD-ARQUEO-02); `repo/workflow.append_transition` + `STATE_MACHINES['alerta']` (KD-ARQUEO-05); `repo/session_cycle.close_session_with_log` (KD-ARQUEO-03); `repo/alert_types.validate` + `AlertaFactory.fire`; `repo/idempotency.guard` + `store_response` (DEC-IDEM-01); `repo/sesion_activa.get_sesion_activa`.

**NEW** (`repo/arqueo.py`, ~100 LOC): 10 typed helpers wrapping the REUSE helpers above.

**GAPS closed by F1.13**: `repo/arqueo.py` not exists today; `descuadre_critico` not in `prod.alert_types`; `cierre_dia` not in `prod.tipo_arqueo`.

### 6.4 Schemas — REUSE + EXTEND

**REUSE**: `schemas/caja.py::ArqueoCreate` + `ArqueoRead` + `ArqueoReadList` + `SesionRead` (used in `ArqueoResumenItem.uuid_sesion` reference).

**EXTEND** (F1.13): `ArqueoCreateV2` (~30 LOC), `ArqueoReadForHandler` (~25 LOC), `ArqueoResumenItem` (~35 LOC), `ArqueoResumenRead` (~15 LOC), `CierreDiarioQueryParams` (~10 LOC).

### 6.5 Sync catalog entries — VERIFY PRE-FLIGHT (RESOLVED 2026-09-15)

| Table | Direction | Broadcast | F1.13 Status |
|---|---|---|---|
| `tipo_arqueo` | `cloud_to_branch` | `all_branches` | pre-existing; new `cierre_dia` propagates |
| `arqueo` | `branch_to_cloud` | `all_branches` | pre-existing |
| `sesion` | `branch_to_cloud` | `all_branches` | pre-existing |
| `alerta` | `branch_to_cloud` | `all_branches` | pre-existing |
| `configuracion_tolerancias` | `cloud_to_branch` | `all_branches` | pre-existing |

**No F1.13 sync catalog seeds needed.** DEC-ARQUEO-09 NOT extended to sync catalog.

### 6.6 Permisos — VERIFY + GAP-BE-05 BUNDLE

`realizar_arqueo` pre-seeded (per plan.md line 4549). `abrir_cerrar_caja` pre-seeded (F1.3).

**GAP-BE-05 bundled (DEC-ARQUEO-08, plan.md lines 7349-7374 verbatim)**:
- **Site #1**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 53 — inside `_mount_caja()`, change `permission_required="emitir_factura"` to `permission_required="realizar_arqueo"`. Affects BOTH `/caja/caja` and `/caja/arqueo` reads (the same factory helper mounts both). NO MIGRATION needed.
- **Site #2**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` line 257 — inside `router.include_router(make_router(resource="sesion", ...))`, change `permission_required="emitir_factura"` to `permission_required="abrir_cerrar_caja"`. NO MIGRATION needed.

---

## 7. Tables Touched

- 7.1 `prod.tipo_arqueo` [V] — READ + LOCK + siembra (Op 1 of 0031)
- 7.2 `prod.arqueo` [A] — INSERT only via `append_event` (KD-ARQUEO-02)
- 7.3 `prod.sesion` [L-S] — SELECT + conditional UPDATE through `close_session_with_log` (KD-ARQUEO-03)
- 7.4 `prod.alerta` [L-W] — conditional INSERT initial via `append_transition` (KD-ARQUEO-05)
- 7.5 `prod.configuracion_tolerancias` [V] — READ only (vigente row)
- 7.6 `prod.factura_pagos` [A] — READ only via SUM by `medio_pago`
- 7.7 `prod.alert_types` — READ + siembra (Op 2 of 0031, DEC-ARQUEO-09b)
- 7.8 `prod.log_transaccional` [A] — INSERT multiple, co-transactional by helpers

---

## 8. Endpoints Proposed

### 8.1 `POST /api/v1/caja/arqueo` (HU-F1.13-T2)

- Issuer dep: `_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")`.
- Permission: `realizar_arqueo` (the correct one after GAP-BE-05 fix).
- Request: `ArqueoCreateV2` (`uuid_tipo_arqueo`, `uuid_sesion` NULL when `cierre_dia`, `valor_efectivo_reportado`, `valor_datafono_reportado`, `justificacion`).
- Response (201): `ArqueoReadForHandler` with `uuid`, esperados, reportados, diferencias, `descuadre_pct` (informational only), `alerta_generada`, `alerta_uuid`.
- Status codes: 201; 400 `idempotency_key_required`/`cierre_dia_no_acepta_uuid_sesion`/`justificacion_requerida`; 403 `tenant_scope_violation`/`permission_denied`; 404 `tipo_arqueo_no_encontrado`/`sesion_no_encontrada`/`tolerancia_no_configurada`; 409 `sesion_ya_cerrada`/`idempotency_conflict`.
- Headers: `Cache-Control: no-store` ALWAYS (DEC-ARQUEO-06).
- Idempotency: `Idempotency-Key` HTTP header (DEC-IDEM-01).

### 8.2 `GET /api/v1/caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD` (HU-F1.13-T3)

- Response (200): `ArqueoResumenRead` with `fecha`, `uuid_sucursal`, `sesiones: [ArqueoResumenItem]`, `cierre_dia: ArqueoResumenItem | None`.
- Status: 200 always; 403; 422 missing params.
- Headers: `Cache-Control: no-store` ALWAYS.

---

## 9. Decisions

### 9.1 DEC-ARQUEO-01 — Single `await session.commit()` for ALL writes (RESOLVES R1 HIGH)

One commit at Step 12 covers 1 [A] Arqueo + N [L-S] sesion UPDATEs + N logs + 1 [L-W] alerta conditional + 1 log. NO SAVEPOINTs.

### 9.2 DEC-ARQUEO-02 — [A] append-only via `repo/append_only.append_event` (KD-ARQUEO-02)

Handler NEVER raw `session.execute(insert(Arqueo))`. AST walk `test_arqueo_handler_no_update_on_a_tables.py` enforces.

### 9.3 DEC-ARQUEO-03 — Sesion UPDATE only via `repo/session_cycle.close_session_with_log` per row (KD-ARQUEO-03)

`ls_session_guard` DB trigger mandates log-first. AST walk `test_arqueo_handler_cierre_dia_uses_session_cycle.py` enforces. For `cierre_dia` with N sesiones: iterate `close_session_with_log` per row.

### 9.4 DEC-ARQUEO-04 — Tolerancia evaluated as ABSOLUTE monto (KD-ARQUEO-04)

`|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono` → descuadre. `descuadre_pct` informational ONLY.

### 9.5 DEC-ARQUEO-05 — Dedicated `APIRouter` for `caja/arqueo` (NOT via `make_router`)

NEW `api/v1/caja_arqueo.py`. F1.10 + F1.12 precedent: cross-table atomic writes do not map to the factory's single-table contract.

### 9.6 DEC-ARQUEO-06 — `Cache-Control: no-store` on EVERY response (XR6 mirror)

Reuses `api/v1/_helpers.py:18-31`. Both success (`apply_no_store_header`) and error paths (`headers=no_store_headers()`).

### 9.7 DEC-ARQUEO-07 — `justificacion` REQUIRED (cierre_turno/cierre_dia) vs OPTIONAL (auditoria)

Per plan.md line 2476 asymmetry. `auditoria` advertencia; cierre paths requieren justification cuando diferencia != 0 (else 400).

### 9.8 DEC-ARQUEO-08 — GAP-BE-05 bundled (plan.md lines 7349-7374 verbatim)

2-line Python-only fix, NO migration. Affects `caja.py:53` + `caja_sesion.py:257`.

### 9.9 DEC-ARQUEO-09 — `cierre_dia` + `descuadre_critico` conditional siembra in MIGRATION 0031

MIGRATION 0031 seeds BOTH missing identifiers in 2 idempotent ops:
- Op 1: `prod.tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458) — `IF siembra_count = 0` + `ON CONFLICT (codigo, vigente_desde) DO NOTHING`.
- Op 2: `prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'` — `IF NOT EXISTS` + `ON CONFLICT (tipo_alerta) DO NOTHING` (respects `alert_types_inmutable`).
- Op 3: NO-DDL comment for GAP-BE-05.

Pattern mirrors `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py:134-188`.

### 9.10 DEC-ARQUEO-10 — `factura_pagos` summed per session via direct FK `uuid_sesion`

`sesion.valor_inicial_* + SUM(factura_pagos.valor) WHERE factura_pagos.uuid_sesion = sesion.uuid GROUP BY medio_pago`. NO UPDATE on `factura_pagos`.

---

## 10. Risks (12 rows)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Cross-table atomicity (4 tables in 1 TX) | HIGH (RESOLVED) | DEC-ARQUEO-01 + KD-ARQUEO-01 AST walk |
| R2 | `ls_session_guard` rejection on raw UPDATE | HIGH | DEC-ARQUEO-03 + KD-ARQUEO-03 AST walk |
| R3 | `descuadre_critico` NOT in `prod.alert_types` | HIGH (RESOLVED) | DEC-ARQUEO-09b (0031 Op 2) |
| R4 | `cierre_dia` NOT in `prod.tipo_arqueo` | HIGH (RESOLVED) | DEC-ARQUEO-09 (0031 Op 1) |
| R5 | Tolerance wrong column | MEDIUM | Pure helper + 4 unit tests |
| R6 | Justification asymmetry | MEDIUM | DEC-ARQUEO-07 + 1 unit test for each quadrant |
| R7 | GAP-BE-05 wrong permission string | LOW | DEC-ARQUEO-08 verbatim + 1 unit test asserting 403 |
| R8 | `cierre_dia` sync to branches | LOW | pre-existing cloud→branch entry propagates automatically |
| R9 | Cierre_dia mass parallel races | LOW | KD-ARQUEO-08 + 1 unit test |
| R10 | `descuadre_pct` informational confusion | LOW | DEC-ARQUEO-04 + docstring |
| R11 | A-07 / `cierre_dia` position in UI legend | MEDIUM | DEC-ARQUEO-09 + UI deferred to Fase 10 |
| R12 | Cache-Control no-store | LOW | DEC-ARQUEO-06 helpers reused |

---

## 11. Defense in Depth (5 layers — XR6 mirror)

| Layer | Mechanism | Source |
|---|---|---|
| 1 | KD-3 issuer chain (`operador-`+`admin-`) + `realizar_arqueo` permission | handler Layer 1 |
| 2 | Tenant scope post-V1 | handler Layer 2 |
| 3 | KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering | AST walk |
| 4 | Pydantic `extra='forbid'` + numeric Decimal + UUID required | `_Base` |
| 5 | 422/409/404/403/400 mapping + `Cache-Control: no-store` | handler Layer 5 |

Typed exception → HTTP mapping table in §11 — 10 typed errors. pgcode NEVER in response body.

---

## 12. Pre-Flight Verification (20 checks)

| # | Check | Source | Result |
|---|---|---|---|
| 1 | `prod.tipo_arqueo` exists | migration 0001:167-185 | ✅ |
| 2 | `prod.arqueo` exists | migration 0001:957-978 + models/A/arqueo.py:26-84 | ✅ |
| 3 | `prod.sesion` exists | migration 0001:715-735 + models/L_S/sesion.py:20-47 | ✅ |
| 4 | `prod.alerta` exists | migration 0001:737-758 | ✅ |
| 5 | `prod.configuracion_tolerancias` exists | migration 0001:250-268 | ✅ |
| 6 | `prod.factura_pagos` exists | F1.9 closed | ✅ |
| 7 | `prod.alert_types` exists | 0013 + 0025 | ✅ |
| 8 | `realizar_arqueo` permission seeded | plan.md line 4549 | ✅ |
| 9 | `abrir_cerrar_caja` permission seeded | F1.3 closed | ✅ |
| 10 | operador+admin already granted | F1.3 closure | ✅ |
| 11 | Migration head = `0030` | `git log --oneline -1 a328957` | ✅ |
| 12 | `tipo_arqueo_uk01` UK exists | models/V/tipo_arqueo.py:28 | ✅ |
| 13 | `ls_session_guard` trigger on `prod.sesion` UPDATE | migration 0001 + repo/session_cycle.py:286-289 | ✅ |
| 14 | `alert_types_inmutable` trigger | migration 0013:21-22 | ✅ |
| 15 | `descuadre_critico` alert_type NOT seeded | grep migrations/versions/*.py → 0 matches | ❌ → 0031 Op 2 |
| 16 | `cierre_dia` tipo_arqueo NOT seeded | grep → 0 matches | ❌ → 0031 Op 1 |
| 17 | STATE_MACHINES['alerta'] permits initial | repo/workflow.py:85-90 | ✅ |
| 18 | Sync catalog entries pre-existing | sync/catalog/entries/ | ✅ |
| 19 | GAP-BE-05 site #1 confirmed | api/v1/caja.py:53 literal read | ✅ BUG |
| 20 | GAP-BE-05 site #2 confirmed | api/v1/caja_sesion.py:257 literal read | ✅ BUG |

**Result**: 18 PASS + 2 KNOWN MISSING (closed by 0031 Ops 1+2). Pre-flight gate **PASS**.

---

## 13. Test Plan (9 files + 4 AST walks + 1 migration test)

- `test_arqueo_repo.py` (~50 LOC, 5 tests): pure helpers + UUID/sesion resolution
- **`test_arqueo_handler.py`** (~30 LOC, **4 mandated by plan.md line 1093**): sin diferencia/diferencia_justificada/descuadre_sobre_tolerancia/diferencia_sin_justificacion_400
- `test_cierre_dia.py` (~40 LOC, 2 tests): 3-sesion-2cerradas-1abieta path + uuid_sesion_en_body_400
- `test_arqueo_resumen.py` (~30 LOC, 3 tests): empty day / single session with arqueo / cierre_dia aggregate
- `test_arqueo_handler_single_commit.py` (~15 LOC, AST walk)
- `test_arqueo_handler_no_raw_dml.py` (~20 LOC, AST walk)
- `test_arqueo_handler_cierre_dia_uses_session_cycle.py` (~15 LOC, NEW AST walk)
- `test_arqueo_handler_no_update_on_a_tables.py` (~15 LOC, AST walk)
- `test_migration_0031_idempotency.py` (~15 LOC, 2 tests)

---

## 14. Out of Scope (F2.x+)

B2B arqueos · multi-sucursal simultaneous · UI integración (Fase 10 HU-F10.1/10.2/10.3) · Fase 10 reconciliación de tolerancia · Filtros de consulta en `GET /caja/arqueo` (F18.1) · `arqueo_pendiente_24h` alerta (F1.14) · `ABIERTO-04` `cierre_sesion` dedicated flow · ABIERTO-200 `config_caja.redondeo`.

---

## 15. Sync Catalog — pre-flight verification (RESOLVED 2026-09-15)

All 5 entries pre-existing. NO F1.13 sync catalog seeds needed. MIGRATION 0031 contains NO `INSERT INTO prod.sync_catalog`.

---

## 16. Proposed Cluster Decomposition (6 clusters)

- **T1**: MIGRATION 0031 siembra (cierre_dia + descuadre_critico) + pre-flight (~80 LOC)
- **T2**: `repo/arqueo.py` 10 helpers + schemas extend (~190 LOC)
- **T3**: `POST /caja/arqueo` 12-step handler + router mount (~180 LOC)
- **T4**: `GET /caja/arqueo/resumen` 6-step handler (~60 LOC)
- **T5**: 9 test files + 4 AST walks + 1 migration test (~220 LOC)
- **T-GAP-BE-05**: 2-line Python fix + 1 unit test (~10 LOC)

**Total: ~590 LOC** (production 290 + tests 220 + migration 80 + GAP ~10).

---

## 17. Next Recommended Phase

**Phase**: `sdd-propose hu-f1-13-arqueo` (17-section proposal at `openspec/changes/hu-f1-13-arqueo/proposal.md`).

**Pre-propose verification status** (completed 2026-09-15):
1. ✅ Static pre-flight 18/20 PASS, 2 known-MISSING closed by 0031.
2. ✅ GAP-BE-05 sites confirmed.
3. ✅ Sync catalog pre-existing.
4. ✅ All permissions pre-existing.
5. ⏭️ R11 ABIERTO-04 cierresesion deferred to Fase 2+.

**Key inputs for propose phase**: DEC-ARQUEO-01..10 (10 decisions, §9); KD-ARQUEO-01..05 (5 invariants); XR6 + REQ-OPS-091..097 (~7 new REQs + XR6); 6-cluster decomposition T1..T5 + T-GAP-BE-05; MIGRATION 0031 REAL siembra; GAP-BE-05 bundled.

---

**End of exploration.**
