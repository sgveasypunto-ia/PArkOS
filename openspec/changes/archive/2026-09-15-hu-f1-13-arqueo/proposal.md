# Proposal: HU-F1.13 — Endpoints arqueo + siembra `tipo_arqueo.cierre_dia` + GAP-BE-05 bundleado

> **Change**: `hu-f1-13-arqueo` · **Folder**: `openspec/changes/hu-f1-13-arqueo/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.13 (Fase-1 prerequisites — backend, includes GAP-BE-05 bundled in-scope correction)
> **Inputs**: `plan.md` lines 1058-1101 (240 LOC production, 4 atomic tasks T1..T4, 4 tests mandated at line 1093, GAP-BE-05 mandate at lines 7349-7374), `openspec/changes/hu-f1-13-arqueo/exploration.md` (17 sections, ~770 LOC, 12 risks R1..R12, pre-flight 18/20 PASS + 2 known-MISSING closed by MIGRATION 0031 Ops 1+2), `modelo_datos_er.mmd` blocks `tipo_arqueo` [V] line 167-185, `configuracion_tolerancias` [V] line 250-268, `sesion` [L-S] line 715-735, `alerta` [L-W] line 737-758, `arqueo` [A] line 957-978, `factura_pagos` [A] (F1.9 inmutable), `alert_types` (migration 0013, registry, inmutable trigger), `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP head pre-F1.13), `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (template for MIGRATION 0031 siembra pattern, lines 134-188), `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry table for `tipo_alerta` + inmutable trigger), `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 53 (GAP-BE-05 site #1 confirmed), `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2 confirmed), `backend/packages/parkos_core/src/parkos_core/models/V/tipo_arqueo.py`, `backend/packages/parkos_core/src/parkos_core/models/A/arqueo.py` lines 26-84, `backend/packages/parkos_core/src/parkos_core/models/L_S/sesion.py` lines 20-47, `backend/packages/parkos_core/src/parkos_core/models/L_W/alerta.py`, `backend/packages/parkos_core/src/parkos_core/repo/{append_only,workflow,session_cycle,sesion_activa,alert_types,idempotency}.py`, `openspec/specs/operations/spec.md` lines 3217-3651 (XR1..XR5 progression, last req-number series REQ-OPS-083..090 + XR5 — next available is REQ-OPS-091), `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/proposal.md` (sibling precedent for 16-section structure verbatim).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a328957`) · **PR target**: `origin/dev`.
> **Language note**: artifact authored in English per the project's `Language Domain Contract` (default for technical SDD artifacts). DEC-ARQUEO-NN and KD-ARQUEO-NN identifiers follow the established F1.x naming pattern. GAP-BE-05 (already catalogued by plan.md) is bundled in-scope per plan.md lines 7349-7374 verbatim mandate.

---

## 1. Title & Goal

**Title**: "Endpoints arqueo (POST /caja/arqueo + GET /caja/arqueo/resumen) + siembra `tipo_arqueo.cierre_dia` y `alert_types.descuadre_critico` + corrección bundleada GAP-BE-05"

**Goal**: Deliver two write/read endpoints on top of the already-shipped `prod.tipo_arqueo` [V] (3 existing values: `cierre_turno | auditoria | cierre_sesion` per `modelo_datos_er.mmd` line 171, 4th `cierre_dia` added by F1.13 siembra), `prod.arqueo` [A] (AppendOnlyBase composite PK `uuid + fecha_retencion_hasta` per `models/A/arqueo.py:26-84`), `prod.sesion` [L-S] (SessionBase + `ls_session_guard` trigger per `repo/session_cycle.py:286-289`), `prod.alerta` [L-W] (WorkflowBase state machine `{activa -> descartada | resuelta}` per `repo/workflow.py:85-90`), `prod.configuracion_tolerancias` [V], `prod.factura_pagos` [A] (immutable), plus bundle the 2-line Python-only GAP-BE-05 correction (DEC-ARQUEO-08):

- **`POST /api/v1/caja/arqueo`** — Given `uuid_tipo_arqueo` (resolves to `codigo` ∈ `{auditoria, cierre_turno, cierre_dia}`) + `uuid_sesion` (NULL when `cierre_dia`) + `valor_efectivo_reportado` + `valor_datafono_reportado` + `justificacion`, server-resolves the plan + tolerances + sesion, then in a **single transaction** (`await session.commit()` exactly once, KD-ARQUEO-01) INSERTs:
  1. `prod.arqueo` [A] via `repo/append_only.append_event` (KD-ARQUEO-02)
  2. **`cierre_dia` path only**: mass `prod.sesion` UPDATE per-row via `repo/session_cycle.close_session_with_log` to satisfy `ls_session_guard` (KD-ARQUEO-03)
  3. **`diferencia > tolerancia` (absolute monto, KD-ARQUEO-04)**: `prod.alerta` [L-W] INSERT initial via `repo/workflow.append_transition` (KD-ARQUEO-05)
  4. `prod.log_transaccional` [A] rows (co-transactional, emitted by helpers)

- **`GET /api/v1/caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD`** — returns one row per `sesion` of the day at that branch (JOIN `arqueo` + `factura_pagos` sum by `medio_pago`) + `cierre_dia` aggregate at bottom (KD-ARQUEO-07).

- **`GAP-BE-05 bundled (DEC-ARQUEO-08)`** — 2-line source-only fix, NO migration:
  - `api/v1/caja.py:53` — `permission_required="emitir_factura"` → `"realizar_arqueo"`.
  - `api/v1/caja_sesion.py:257` — `permission_required="emitir_factura"` → `"abrir_cerrar_caja"`.

**Defense in depth (5 layers — XR6 mirror from F1.11 + F1.12)**:

- (a) KD-3 issuer chain (`requires_issuer("operador-", "admin-")`) + permission gate (`realizar_arqueo` — already seeded per plan.md line 4549; `abrir_cerrar_caja` — already seeded per F1.3).
- (b) Tenant scope post-V1 (KD-S2 analog from F1.7) — operador cross-branch rejected with 403.
- (c) KD-ARQUEO-01 single-commit invariant (AST walk `tests/static/test_arqueo_handler_single_commit.py`).
- (d) KD-ARQUEO-02 `[A]` append-only AST walk (`tests/static/test_arqueo_handler_no_raw_dml.py` + `tests/static/test_arqueo_handler_no_update_on_a_tables.py`).
- (e) Handler 422/409/404/403/400 mapping + `Cache-Control: no-store` on every response (DEC-ARQUEO-06).

**Scope**: ~290 LOC production (vs plan 240 = +20% absorbed by 12-step POST handler + 6-step GET handler + 10 typed helpers) + ~220 LOC tests (9 test files including 4 AST walks + 1 migration test) + ~80 LOC MIGRATION 0031 (REAL siembra, not NO-OP) + ~10 LOC GAP-BE-05 2-line fix + 1 unit test = ~590 LOC cumulative.

---

## 2. Context & Background

- **F1.12 just closed** (2026-09-15, commit `a328957`). Migration head = `0030_venta_suscripcion_optional` (NO-OP audit trail). F1.13 will be migration `0031_arqueo_cierre_dia_and_gap_be_05` (REAL siembra — conditional Op 1 `cierre_dia` + Op 2 `descuadre_critico`).
- **`prod.tipo_arqueo` exists** (`[V]`, migration 0001 lines 167-185, bi-temporal VersionedBase). UK `tipo_arqueo_uk01(codigo, vigente_desde)` per `models/V/tipo_arqueo.py:28`. Currently seeded with 3 values. **4th `cierre_dia` (A-07, plan.md line 458) added by F1.13 MIGRATION 0031 Op 1**.
- **`prod.arqueo` exists** (`[A]`, migration 0001 lines 957-978, `AppendOnlyBase` composite PK `uuid + fecha_retencion_hasta`, monthly pg_partman RANGE partition). 7 business columns. **INSERT-only via `repo/append_only.append_event`** (lines 64-124). NEVER raw UPDATE outside `append_event`.
- **`prod.sesion` exists** (`[L-S]`, `SessionBase`). UPDATE only via `repo/session_cycle.close_session_with_log` (lines 274-349) — `ls_session_guard` DB trigger (per migration 0001 + `repo/session_cycle.py:286-289`) REJECTS direct UPDATE without co-transactional `log_transaccional` row.
- **`prod.alerta` exists** (`[L-W]`, `WorkflowBase` with state machine `{activa -> descartada | resuelta}` per `repo/workflow.py:85-90`). INSERT-only initial via `repo/workflow.append_transition` (lines 110-237). NEVER raw UPDATE outside `WorkflowBase`.
- **`prod.alert_types` exists** (out-of-catalog [A] registry, migration 0013 + 0025), business-key PK `tipo_alerta`, inmutable trigger `alert_types_inmutable` (per migration 0013:21-22). 9 codes seeded as of 2026-09-15. **`descuadre_critico` NOT yet seeded** (grep across `migrations/versions/` returns 0 matches — confirmed by pre-flight 2026-09-15). F1.14 plan.md line 1131 plans to seed it, but F1.14 is downstream → **DEC-ARQUEO-09b: bundle in MIGRATION 0031 Op 2** with `IF NOT EXISTS` + `ON CONFLICT (tipo_alerta) DO NOTHING` (idempotent — F1.14's future seed becomes no-op).
- **`prod.configuracion_tolerancias` exists** (`[V]`, migration 0001 lines 250-268, bi-temporal VersionedBase). UK `configuracion_tolerancias_uk01(uuid_sucursal, vigente_desde)`. 3 columns: `uuid_sucursal` (FK, NULL=default global), `tolerancia_efectivo` (Numeric), `tolerancia_datafono` (Numeric). F1.13 reads vigente row only.
- **`prod.factura_pagos` exists** (`[A]`, F1.9 closed, 100% immutable per `fn_factura_pagos_inmutable` trigger migration 0001 lines 2024-2088). F1.13 reads only via `SELECT ... WHERE uuid_sesion=...`, never mutates (DEC-ARQUEO-10).
- **`ArqueoCreate` + `ArqueoRead` + `ArqueoReadList` + `ArqueoUpdate` + `ArqueoFilter`** Pydantic schemas pre-existing in `schemas/caja.py`. **F1.13 EXTENDS** with `ArqueoCreateV2` (new write contract) + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams`.
- **Helper modules REUSE**: `repo/append_only.append_event` (lines 64-124); `repo/workflow.append_transition` (lines 110-237) + `STATE_MACHINES['alerta']`; `repo/session_cycle.close_session_with_log` (lines 274-349); `repo/alert_types.validate` + `AlertaFactory.fire`; `repo/idempotency.guard` + `store_response`; `repo/sesion_activa.get_sesion_activa`; `api/v1/_helpers.no_store_headers()` + `apply_no_store_header()` (lines 18-31).
- **GAP-BE-05 verbatim from plan.md line 7359**: "Cambiar `permission_required='emitir_factura'` a `permission_required='realizar_arqueo'` en `caja.py:53` y en la porción de `caja_sesion.py:204` que protege `GET /caja/arqueo`/`GET /caja/caja`; usar `abrir_cerrar_caja` para el mount de solo lectura de `sesion`. Es una corrección de una línea por archivo, sin migración." Pre-flight 2026-09-15 confirms site #1 is now at `caja_sesion.py:257` (line shift between plan.md write date and F1.13 implementation — verified by literal read of the source).
- **Existing permission inventory**: `realizar_arqueo` pre-seeded per plan.md line 4549; `abrir_cerrar_caja` pre-seeded per F1.3. **NO new permissions or role grants needed** for F1.13.
- **A-07** (plan.md line 458): "4th `tipo_arqueo` value `cierre_dia` seeded at migration time" — F1.13 MIGRATION 0031 Op 1 fulfills.
- **F1.13 is a "ampliación de producto" + "corrección bundleada"** (plan.md lines 1058-1101 + lines 7349-7374): the CU-10 business capability + GAP-BE-05 catalog gap. The proposal phase records both scope decisions.

### 2.1 Critical Architectural Conflict — Cross-table atomicity vs per-row sesion guard (RESOLVED in §3)

The fundamental design question of F1.13: the handler must commit `arqueo` [A] (1 INSERT) + `sesion` [L-S] UPDATEs (only `cierre_dia` path, N rows) + `alerta` [L-W] (conditional 1 INSERT) + `log_transaccional` [A] (N+1 rows). Resolution: single `await session.commit()` covers all helper calls; per-row `close_session_with_log` does `(log INSERT + flush + UPDATE)` inside the outer TX.

---

## 3. Architectural Conflict Resolution — DEC-ARQUEO-01 + KD-ARQUEO-01

This section is **mandatory** for the proposal. It documents R1 HIGH from exploration §10 and records the resolution.

### 3.1 The conflict (R1 HIGH)

The handler writes to 4 table families (`arqueo` [A], `sesion` [L-S], `alerta` [L-W], `log_transaccional` [A]). Two architectural choices are valid in PostgreSQL:

| Source | Statement | Authority weight |
|---|---|---|
| F1.11 KD-TKT-01 | "single `await session.commit()` covering all writes" | **CANONICAL** for cross-table writes |
| F1.12 KD-VENTA-01 | "single `await session.commit()` covering 9 tables" | **CANONICAL** for cross-table writes |
| PostgreSQL docs | SAVEPOINTs allow partial rollback within a TX | Valid but adds complexity |
| `ls_session_guard` trigger (per `repo/session_cycle.py:286-289`) | "Per-row `log_transaccional` MUST be INSERTed BEFORE any UPDATE on `prod.sesion`" | **HARD CONSTRAINT** from DB |

The complication: `ls_session_guard` mandates per-row log-first ordering for every sesion UPDATE — not a single global pre-commit hook.

### 3.2 The resolution — DEC-ARQUEO-01: single `await session.commit()` for ALL writes

**Resolution path** (mandated by F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 precedent + DB trigger constraint):

1. **All helpers (`append_event`, `append_transition`, `close_session_with_log`)** stay commit-free — they `session.add()` + `await session.flush()` only.
2. **One `await session.commit()` at the END of the POST handler body** (Step 12), after all helper calls return.
3. **No SAVEPOINTs** in F1.13. If any helper raises, the entire TX rolls back (caller catches the HTTPException and the session is discarded by the FastAPI dependency teardown).
4. **For `cierre_dia` with N open sesiones**: iterate `for sesion in open_sessions: await close_session_with_log(... log_tx=True)` — each iteration does `(log INSERT + flush + UPDATE)` (KD-ARQUEO-03 + `ls_session_guard` trigger).
5. **Lock ordering** (KD-ARQUEO-08): `SELECT FOR UPDATE` on `prod.tipo_arqueo` row FIRST (V1) → serializes concurrent `cierre_dia` per operator.

### 3.3 Why this matters

- **Cross-table atomicity for `arqueo + alerta` pair** — no arqueo without its alerta when descuadre_critico. A SAVEPOINT strategy would partially commit, leaving orphan arqueos without the matched alerta.
- **`ls_session_guard` per-row trigger** mandates log-first ordering for every sesion UPDATE — the per-row `(log INSERT + flush + UPDATE)` pattern in `close_session_with_log` is the only allowed path.
- **The single-commit invariant becomes the AST walk contract** — `tests/static/test_arqueo_handler_single_commit.py` will scan the POST handler body and reject any second `await session.commit()` call (mirror of `test_venta_handler_single_commit.py`).
- **The lock ordering rule prevents deadlocks** under concurrent operators. Operator A acquires plan lock first, operator B waits. Operator A then iterates sesiones (each `close_session_with_log` per-row); operator B's `SELECT FOR UPDATE` on `prod.tipo_arqueo` waits until A commits. No cycle.

---

## 4. Endpoints

Two endpoints, mounted under `/api/v1/caja` via a NEW dedicated router (`api/v1/caja_arqueo.py`).

### 4.1 `POST /api/v1/caja/arqueo` (HU-F1.13-T2)

- **Purpose**: Single transactional arqueo — audita, cierra turno, o cierra día, con alerta condicional sobre descuadre crítico.
- **Issuer dep**: `_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")`.
- **Permission**: `realizar_arqueo` (the correct one after GAP-BE-05 fix; pre-seeded per plan.md line 4549).
- **Request body** (`ArqueoCreateV2`, §9.1):
  ```jsonc
  {
    "uuid_tipo_arqueo": "...",             // resolves to codigo ∈ {auditoria, cierre_turno, cierre_dia}
    "uuid_sesion": "...",                   // NULL if codigo='cierre_dia'
    "valor_efectivo_reportado": 148000,
    "valor_datafono_reportado": 320000,
    "justificacion": "Faltante por vueltos mal calculados en 2 operaciones"
  }
  ```
- **Response (201)** (`ArqueoReadForHandler`): `uuid`, esperados, reportados, diferencias, `descuadre_pct` (informational only, DEC-ARQUEO-04), `alerta_generada`, `alerta_uuid`.
- **Status codes**:
  - `201 Created` — happy path
  - `400 idempotency_key_required` (DEC-IDEM-01 middleware)
  - `400 cierre_dia_no_acepta_uuid_sesion` (V1, `cierre_dia` + `uuid_sesion` provided)
  - `400 justificacion_requerida` (DEC-ARQUEO-07, cierre_turno/cierre_dia + diferencia != 0 + sin justificacion)
  - `403 tenant_scope_violation`
  - `403 permission_denied` (no `realizar_arqueo`)
  - `404 tipo_arqueo_no_encontrado` (V1)
  - `404 sesion_no_encontrada` (V2)
  - `404 tolerancia_no_configurada` (V3)
  - `409 sesion_ya_cerrada` (V4)
  - `409 idempotency_conflict` (DEC-IDEM-01)
- **Headers**: `Cache-Control: no-store` on EVERY response (DEC-ARQUEO-06, success + error).
- **Idempotency**: `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse, shared with F1.6/F1.9/F1.10/F1.11/F1.12).

### 4.2 `GET /api/v1/caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD` (HU-F1.13-T3)

- **Purpose**: Read-only resumen of a branch's day — one row per sesion + `cierre_dia` aggregate at bottom.
- **Issuer dep**: `_caja_resumen_issuer_dep = requires_issuer("operador-", "admin-")`.
- **Permission**: `realizar_arqueo` (after GAP-BE-05 fix at `caja.py:53`).
- **Query params** (`CierreDiarioQueryParams`): `uuid_sucursal: UUID` (required), `fecha: date` (required, `YYYY-MM-DD`).
- **Response (200)** (`ArqueoResumenRead`): `fecha`, `uuid_sucursal`, `sesiones: list[ArqueoResumenItem]`, `cierre_dia: ArqueoResumenItem | None`.
- **Status codes**:
  - `200 OK` — happy path (even if zero sesiones)
  - `403 tenant_scope_violation`
  - `422 missing_query_params`
- **Headers**: `Cache-Control: no-store` on EVERY response.

---

## 5. Tables Touched

Five existing tables (always read) + one [A] INSERT-only table (always) + one [L-S] UPDATE-only table (conditional, `cierre_dia`) + one [L-W] INSERT-only table (conditional, descuadre) + `log_transaccional` rows (auto-co-inserted by helpers) + 2 siembra rows (`cierre_dia` + `descuadre_critico` in MIGRATION 0031).

### 5.1 `prod.tipo_arqueo` [V] (READ + LOCK + siembra)

- **Operations**: V1 SELECT vigente row + `SELECT FOR UPDATE` row lock (KD-ARQUEO-08, DEC-ARQUEO-09 lookup). Op 1 MIGRATION 0031 siembra `codigo='cierre_dia'` (A-07).
- **Columns read**: `uuid`, `codigo`, `vigente_desde`, `vigente_hasta`, `nombre`.
- **Defense in depth**: bi-temporal VersionedBase guarantees at most one vigente row per `codigo`. Handler returns 404 `tipo_arqueo_no_encontrado` if lookup returns NULL.

### 5.2 `prod.arqueo` [A] (INSERT only)

- **Operations**: V5 INSERT via `repo/append_only.append_event` (KD-ARQUEO-02). Handler NEVER raw `session.execute(insert(Arqueo))` — AST walk enforces.
- **Columns write (INSERT)**: `uuid` (server-set), `fecha_retencion_hasta` (server-set, monthly partition key), `uuid_sesion` (NULL for `cierre_dia`), `uuid_usuario` (from `ctx.actor_uuid`), `uuid_tipo_arqueo`, `valor_efectivo_esperado`, `valor_datafono_esperado`, `valor_efectivo_reportado`, `valor_datafono_reportado`, `diferencia_efectivo`, `diferencia_datafono`, `descuadre_pct`, `justificacion`, `alerta_generada`, `alerta_uuid`. Audit + sync columns server-set.
- **Indexes**: composite PK `(uuid, fecha_retencion_hasta)`. Monthly RANGE partition by `fecha_retencion_hasta`.
- **Defense in depth**: `fn_arqueo_inmutable` trigger (migration 0001) rejects UPDATE/DELETE outside `append_event`.

### 5.3 `prod.sesion` [L-S] (SELECT + conditional UPDATE)

- **Operations**: V2 SELECT vigente sesion (when `cierre_turno`/`auditoria`); V4 conditional UPDATE per-row via `close_session_with_log` ONLY when `cierre_dia` (KD-ARQUEO-03 + `ls_session_guard` trigger).
- **For `cierre_dia` with N open sesiones**: iterate `for sesion in open_sessions: await close_session_with_log(session, sesion_uuid, ..., log_tx=True)`. Each iteration does `(log_transaccional INSERT + flush + sesion UPDATE estado='cerrada', timestamp_cierre=...)`.
- **Columns update (cierre_dia only)**: `estado`, `timestamp_cierre`, `uuid_usuario_cierre`.
- **Defense in depth**: `ls_session_guard` DB trigger rejects raw UPDATE without co-transactional `log_transaccional` row. AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` enforces.

### 5.4 `prod.alerta` [L-W] (conditional INSERT only)

- **Operations**: V8 conditional INSERT initial via `repo/workflow.append_transition` when `es_descuadre_critico(plan, valor_efectivo_reportado, valor_datafono_reportado) == True` (KD-ARQUEO-04 + KD-ARQUEO-05).
- **Columns write (INSERT)**: `uuid_alerta` (server-set), `uuid_alerta_padre=NULL` (initial), `tipo_alerta='descuadre_critico'` (validated by `alert_types.validate` — Op 2 MIGRATION 0031 seeds the registry), `severity='critical'`, `uuid_sucursal`, `uuid_recurso_origen=arqueo_uuid`, `tipo_recurso_origen='arqueo'`, `payload_json`, `workflow_estado='activa'`, `created_at`, `created_by`.
- **Defense in depth**: `append_transition` uses `STATE_MACHINES['alerta']` which permits initial state `{activa -> descartada | resuelta}` only.

### 5.5 `prod.configuracion_tolerancias` [V] (READ only)

- **Operations**: V3 SELECT vigente row by `uuid_sucursal=target_sucursal OR uuid_sucursal IS NULL` (NULL = default global). Returns tolerance pair `(tolerancia_efectivo, tolerancia_datafono)`.
- **Columns read**: `uuid_sucursal`, `tolerancia_efectivo`, `tolerancia_datafono`, `vigente_desde`.
- **Defense in depth**: bi-temporal VersionedBase. Returns 404 `tolerancia_no_configurada` if neither branch nor global vigente row exists.

### 5.6 `prod.factura_pagos` [A] (READ only)

- **Operations**: V4 SELECT `SUM(valor) WHERE uuid_sesion=:sesion_uuid GROUP BY medio_pago` (DEC-ARQUEO-10). NEVER UPDATE/INSERT/DELETE on `factura_pagos`.
- **Columns read**: `uuid`, `uuid_sesion`, `medio_pago`, `valor`, `tipo_movimiento` (filter to `'pago'`).
- **Defense in depth**: `fn_factura_pagos_inmutable` trigger (migration 0001 lines 2024-2088) + F1.9 immutability contract. AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` enforces no UPDATE/INSERT/DELETE on `prod.factura_pagos`.

### 5.7 `prod.alert_types` (READ + siembra)

- **Operations**: V8 `validate(tipo_alerta='descuadre_critico')` before INSERT into `prod.alerta`. Op 2 MIGRATION 0031 siembra `tipo_alerta='descuadre_critico', severity='critical'`.
- **Defense in depth**: `alert_types_inmutable` trigger (migration 0013:21-22) blocks UPDATE/DELETE on existing codes — only INSERT at siembra time (when `IF NOT EXISTS` + `ON CONFLICT (tipo_alerta) DO NOTHING`).

### 5.8 `prod.log_transaccional` [A] (INSERT — multiple)

- **Operations**: AUTO-INSERTED via `repo/append_only.append_event` (one per `[A]` Arqueo INSERT) + `repo/workflow.append_transition` (one per `[L-W]` Alerta INSERT) + `repo/session_cycle.close_session_with_log` (one per `[L-S]` Sesion UPDATE, `cierre_dia` only). F1.13 NOT responsible — they are co-transactional by design.

### 5.9 Sync catalog pre-flight (RESOLVED 2026-09-15 — no F1.13 sync catalog seeds needed)

| Table | Direction | Broadcast | F1.13 Status |
|---|---|---|---|
| `tipo_arqueo` | `cloud_to_branch` | `all_branches` | pre-existing; new `cierre_dia` propagates automatically |
| `arqueo` | `branch_to_cloud` | `all_branches` | pre-existing |
| `sesion` | `branch_to_cloud` | `all_branches` | pre-existing |
| `alerta` | `branch_to_cloud` | `all_branches` | pre-existing |
| `configuracion_tolerancias` | `cloud_to_branch` | `all_branches` | pre-existing |

**All 5 entries pre-existing.** MIGRATION 0031 has NO sync catalog seed operation. DEC-ARQUEO-09 NOT extended to sync catalog.

---

## 6. Decisions

### 6.1 DEC-ARQUEO-01 — Single `await session.commit()` for ALL writes (RESOLVES R1 HIGH)

**Decision**: One `await session.commit()` at Step 12 of the POST handler body, covering 1 [A] Arqueo + N [L-S] sesion UPDATEs (cierre_dia path only) + 1 [L-W] alerta (conditional) + N+1 `log_transaccional` rows. No SAVEPOINTs.

**Rationale**: F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 precedent. Cross-table atomicity is the entire business requirement for `arqueo + alerta` pair. The `ls_session_guard` per-row trigger mandates log-first ordering for every sesion UPDATE — the per-row `(log INSERT + flush + UPDATE)` pattern in `close_session_with_log` is the only allowed path inside the outer TX. PostgreSQL handles single TX with multiple inserts/updates easily (no long-held locks).

**Alternatives considered**:
- *SAVEPOINT per write group* — REJECTED. Partial commits would leave orphan arqueos without the matched alerta if alerta write failed.
- *Separate endpoint per write group* — REJECTED. Defeats the purpose of F1.13.
- *Async background task for alerta* — REJECTED. Alerta must be atomic with arqueo (defense in depth against cache poisoning of descuadre state).

### 6.2 DEC-ARQUEO-02 — [A] append-only via `repo/append_only.append_event` (KD-ARQUEO-02)

**Decision**: Handler NEVER raw `session.execute(insert(Arqueo))`. All `prod.arqueo` writes go through `repo/append_only.append_event` (lines 64-124). AST walk `tests/static/test_arqueo_handler_no_update_on_a_tables.py` enforces NO UPDATE/DELETE on `[A]` tables in the handler body.

**Rationale**: `AppendOnlyBase` + `fn_arqueo_inmutable` trigger provide DB-layer immutability. The helper centralizes the audit/sync columns and the partition-key computation.

**Alternatives considered**:
- *Direct INSERT via ORM `session.add(Arqueo(...))`* — REJECTED. Bypasses the audit/sync columns and the helper's `fecha_retencion_hasta` partition-key computation.

### 6.3 DEC-ARQUEO-03 — Sesion UPDATE only via `repo/session_cycle.close_session_with_log` per row (KD-ARQUEO-03)

**Decision**: For `cierre_dia` with N open sesiones: iterate `for sesion in open_sessions: await close_session_with_log(session, sesion_uuid, log_tx=True)`. NEVER raw `session.execute(update(Sesion))`. AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (NEW walk — no precedent) enforces.

**Rationale**: `ls_session_guard` DB trigger (per `repo/session_cycle.py:286-289`) REJECTS raw UPDATE on `prod.sesion` without co-transactional `log_transaccional` row. The helper does `(log INSERT + flush + UPDATE)` per row, satisfying the trigger's per-row constraint.

**Alternatives considered**:
- *Bulk UPDATE all sesiones at once* — REJECTED. `ls_session_guard` is per-row; bulk UPDATE without per-row log would trigger the rejection.
- *Disable trigger during bulk update* — REJECTED. Loses the audit trail integrity guarantee.

### 6.4 DEC-ARQUEO-04 — Tolerancia evaluated as ABSOLUTE monto (KD-ARQUEO-04)

**Decision**: `|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono` → descuadre → INSERT alerta. `descuadre_pct` is informational ONLY (returned in response body but NOT used for alerta decision).

**Rationale**: plan.md line 1065 + line 1093 mandate: "tolerancia = monto absoluto (no porcentaje)". The Fase 10 reconciliation may revise to percentage — out of scope for F1.13. The `descuadre_pct` field is informational for the operator's UX (visualization) but the alerta decision uses absolute monto per the F1.13 contract.

**Alternatives considered**:
- *Evaluate descuadre on percentage* — REJECTED. plan.md line 1065 explicit.
- *Single combined threshold* — REJECTED. Efectivo and datafono have different tolerances (plan.md line 2476).

### 6.5 DEC-ARQUEO-05 — Dedicated `APIRouter` for `caja/arqueo` (NOT via `make_router`)

**Decision**: NEW `api/v1/caja_arqueo.py` with `router = APIRouter(prefix="/caja", tags=["caja"])` mounted into the existing `caja.py` via `router.include_router(...)`. Both endpoints (POST + GET) live in the dedicated router.

**Rationale**: The factory mount `make_router` emits generic POST + GET routes on the 5 individual `[V]` tables. The `arqueo` endpoint writes to `arqueo` [A] + `sesion` [L-S] + `alerta` [L-W] in a single TX — it does not map cleanly to a single resource. F1.10 + F1.12 precedent: cross-table atomic writes do not map to the factory's single-table contract.

**Alternatives considered**:
- *Add `arqueo` to the `make_router` mount* — REJECTED. The factory does not support cross-table atomic writes.
- *Separate top-level router `/arqueo`* — REJECTED. The resource logically belongs under `/caja` (it's a CAJA operation).

### 6.6 DEC-ARQUEO-06 — `Cache-Control: no-store` on EVERY response (XR6 mirror from F1.11 + F1.12)

**Decision**: All responses (201 + 4xx + 5xx) on BOTH endpoints (POST + GET) carry `Cache-Control: no-store`. Both success (`apply_no_store_header`) and error (`no_store_headers()` in `HTTPException(headers=...)`) routes.

**Rationale**: XR2/XR6 mirror from F1.10/F1.11/F1.12 DEC-TKT-06/DEC-VENTA-06. A proxy that serves a stale arqueo response would silently accept out-of-date state (e.g., the reported values or descuadre status).

### 6.7 DEC-ARQUEO-07 — `justificacion` REQUIRED (cierre_turno/cierre_dia) vs OPTIONAL (auditoria)

**Decision**: When `tipo_arqueo.codigo == 'auditoria'`, `justificacion` is OPTIONAL. When `tipo_arqueo.codigo in ('cierre_turno', 'cierre_dia')` AND `diferencia != 0` (either `diferencia_efectivo != 0 OR diferencia_datafono != 0`), `justificacion` is REQUIRED (else 400 `justificacion_requerida`).

**Rationale**: plan.md lines 1086-1091 + line 2476 mandate the asymmetry. `auditoria` is an internal control step (advertencia only); `cierre_turno`/`cierre_dia` are operational commitments (justification required when there's a delta).

**Alternatives considered**:
- *Always require `justificacion`* — REJECTED. Burdens operators doing routine auditorias.
- *Never require `justificacion`* — REJECTED. Violates audit-trail integrity for cierre paths.

### 6.8 DEC-ARQUEO-08 — GAP-BE-05 bundled (plan.md lines 7349-7374 verbatim)

**Decision**: 2-line Python-only fix, NO migration. Affects `api/v1/caja.py:53` (emitir_factura → realizar_arqueo) + `api/v1/caja_sesion.py:257` (emitir_factura → abrir_cerrar_caja). Both sites confirmed by literal read 2026-09-15.

**Rationale**: plan.md lines 7355-7361 verbatim — the permisos are semantically incorrect (caja routes protected by facturacion permission). plan.md line 7361 explicitly recommends bundling in HU-F1.13 "por cercanía de archivo". Both permissions are already seeded.

**Alternatives considered**:
- *Separate HU* — REJECTED per plan.md line 7361 ("evita abrir una HU nueva solo para esto").
- *Bundle in HU-F18.1 (Parte 2)* — REJECTED per plan.md line 7361 recommendation.

### 6.9 DEC-ARQUEO-09 — `cierre_dia` + `descuadre_critico` conditional siembra in MIGRATION 0031

**Decision**: MIGRATION 0031 seeds BOTH missing identifiers in 2 idempotent ops:
- Op 1: `prod.tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458) — `IF siembra_count = 0` + `ON CONFLICT (codigo, vigente_desde) DO NOTHING`.
- Op 2: `prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'` — `IF NOT EXISTS` + `ON CONFLICT (tipo_alerta) DO NOTHING` (respects `alert_types_inmutable`).
- Op 3: NO-DDL comment for GAP-BE-05.

**Rationale**: Both identifiers are missing from the seeded catalog (pre-flight 2026-09-15 confirmed). `cierre_dia` is needed at runtime V1 lookup; `descuadre_critico` is needed at `append_transition` validation. Pattern mirrors `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py:134-188`. Idempotency via `IF NOT EXISTS` + `ON CONFLICT DO NOTHING` ensures F1.14's future seed of `descuadre_critico` becomes a no-op.

**Alternatives considered**:
- *Defer `descuadre_critico` to F1.14* — REJECTED. F1.13 needs it at runtime; deferring would create a runtime error.
- *Hardcode the values in the handler* — REJECTED. Violates the `alert_types` registry contract.

### 6.10 DEC-ARQUEO-10 — `factura_pagos` summed per session via direct FK `uuid_sesion`

**Decision**: `SELECT medio_pago, SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=:sesion_uuid AND tipo_movimiento='pago' GROUP BY medio_pago`. The result feeds `valor_efectivo_esperado` (sum of `medio_pago='efectivo'`) and `valor_datafono_esperado` (sum of `medio_pago IN ('tarjeta', 'datafono')`). NO UPDATE/INSERT/DELETE on `factura_pagos`.

**Rationale**: F1.9 `factura_pagos` is immutable (F1.9 REQ-OPS-058 + `fn_factura_pagos_inmutable` trigger). F1.13 reads only. The direct FK is `prod.factura_pagos.uuid_sesion` (per migration 0001 line 716). The grouping matches the arqueo contract (plan.md lines 1062-1065).

**Alternatives considered**:
- *JOIN `facturas` then `factura_pagos` to get sesion via `factura.uuid_salida → salida.uuid_sesion`* — REJECTED. Adds 1 join for no semantic gain; `factura_pagos.uuid_sesion` is already denormalized.
- *Compute expected from `sesion.valor_inicial_*` only* — REJECTED. Misses the per-medio_pago sum required by the contract.

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Cross-table atomicity** — 4-table single commit + per-row sesion guard is the largest TX in the codebase after F1.12. A bug in any helper could leave inconsistent state. | **HIGH (RESOLVED)** | DEC-ARQUEO-01 (§6.1) + KD-ARQUEO-01 AST walk `tests/static/test_arqueo_handler_single_commit.py`. Verify all helpers do NOT call `session.commit()`. |
| **R2** | **`ls_session_guard` rejection on raw UPDATE** — direct `session.execute(update(Sesion))` on `prod.sesion` triggers DB rejection without co-transactional `log_transaccional`. | **HIGH** | DEC-ARQUEO-03 (§6.3) + KD-ARQUEO-03 AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py`. The `close_session_with_log` helper does `(log INSERT + flush + UPDATE)` per row. |
| **R3** | **`descuadre_critico` NOT in `prod.alert_types`** — `append_transition` validation would fail at runtime if registry missing. | **HIGH (RESOLVED)** | DEC-ARQUEO-09b (MIGRATION 0031 Op 2). Pre-flight 2026-09-15 confirmed the gap; Op 2 closes it with `IF NOT EXISTS` + `ON CONFLICT DO NOTHING` (idempotent). |
| **R4** | **`cierre_dia` NOT in `prod.tipo_arqueo`** — V1 lookup would return NULL → 404 `tipo_arqueo_no_encontrado`. | **HIGH (RESOLVED)** | DEC-ARQUEO-09 (MIGRATION 0031 Op 1). Pre-flight 2026-09-15 confirmed the gap; Op 1 closes it with `IF siembra_count = 0` + `ON CONFLICT DO NOTHING`. |
| **R5** | **Tolerance wrong column** — using `descuadre_pct` for alerta decision instead of absolute monto would silently accept descuadres > tolerance. | **MEDIUM** | DEC-ARQUEO-04 (§6.4) + 4 unit tests in `tests/unit/test_arqueo_handler.py` covering sin diferencia/diferencia_justificada/sobre_tolerancia/sin_justificacion. |
| **R6** | **Justification asymmetry** — requiring justification for auditoria (burdens operator) OR not requiring for cierre_turno (audit gap). | **MEDIUM** | DEC-ARQUEO-07 (§6.7) + 1 unit test per quadrant (auditoria/cierre_turno/cierre_dia × con_sin_diferencia × con_sin_justificacion). |
| **R7** | **GAP-BE-05 wrong permission string** — using a typo'd permission name would silently 403 all operador calls. | **LOW** | DEC-ARQUEO-08 (§6.8) verbatim + 1 unit test asserting 403 on `emitir_factura`-only role + 200 on `realizar_arqueo`/`abrir_cerrar_caja` role. |
| **R8** | **`cierre_dia` sync to branches** — new `tipo_arqueo` value needs cloud→branch propagation. | **LOW** | Pre-existing `cloud_to_branch all_branches` sync entry propagates automatically; no F1.13 sync catalog seed needed (pre-flight verified). |
| **R9** | **Cierre_dia mass parallel races** — two operators triggering `cierre_dia` simultaneously on overlapping sesiones. | **LOW** | KD-ARQUEO-08 (`SELECT FOR UPDATE` on `tipo_arqueo` row) + per-sesion `SELECT FOR UPDATE` inside `close_session_with_log` serializes per-row. 1 unit test in `tests/unit/test_cierre_dia.py` covering concurrent 3-sesiones-2cerradas-1abieta path. |
| **R10** | **`descuadre_pct` informational confusion** — operator might assume pct vs absolute. | **LOW** | DEC-ARQUEO-04 + docstring on `ArqueoReadForHandler.descuadre_pct` clarifying "informational only; alerta decision uses absolute monto". |
| **R11** | **A-07 / `cierre_dia` position in UI legend** — UI legend order vs catalog order. | **MEDIUM** | DEC-ARQUEO-09 + UI deferred to Fase 10 (out of F1.13 scope). |
| **R12** | **Cache-Control no-store (DEC-ARQUEO-06)** — every response must carry the header, including the 422 Pydantic validation errors. | **LOW** | DEC-ARQUEO-06. The `_helpers.no_store_headers()` + `apply_no_store_header()` helpers are reused verbatim from F1.6. |

---

## 8. Defense in Depth

5 layers mirror the F1.10 + F1.11 + F1.12 precedent:

### Layer 1 — KD-3 issuer chain + permission check

`_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")`. The dedicated router uses `permission_required="realizar_arqueo"` (after GAP-BE-05 fix at `caja.py:53`). The `abrir_cerrar_caja` permission applies to `caja_sesion.py` (after GAP-BE-05 site #2).

### Layer 2 — Tenant scope post-V1

After resolving `target_sucursal` from the request body (V1) or query params (GET), if `ctx.issuer_prefix == "operador-"` and `target_sucursal != ctx.sucursal_uuid`, return `403 tenant_scope_violation`. Admin bypasses.

### Layer 3 — KD-ARQUEO-01 single-commit invariant + KD-ARQUEO-02 `[A]` append-only + KD-ARQUEO-03 sesion guard + KD-ARQUEO-08 lock ordering

Step 1: `SELECT FOR UPDATE` on `prod.tipo_arqueo` (vigente row). Lock held until Step 12 commit. Step 12: ONE `await session.commit()`. No SAVEPOINTs. AST walks enforce every layer.

### Layer 4 — Pydantic `extra='forbid'` + numeric Decimal + UUID required

`ArqueoCreateV2(_Base)` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams` inherit `extra='forbid'` from `schemas/common.py`. Numeric `valor_efectivo_reportado`/`valor_datafono_reportado` use `Decimal` with `ge=0`. UUID fields required where mandated.

### Layer 5 — Handler 422/409/404/403/400 mapping + `Cache-Control: no-store`

| Typed exception | HTTP | `error` body | Source |
|---|---|---|---|
| `TipoArqueoNoEncontradoError` | 404 | `tipo_arqueo_no_encontrado` + `uuid_tipo_arqueo` | `repo/arqueo.py` (NEW) |
| `SesionNoEncontradaError` | 404 | `sesion_no_encontrada` + `uuid_sesion` | `repo/arqueo.py` (NEW) |
| `ToleranciaNoConfiguradaError` | 404 | `tolerancia_no_configurada` + `uuid_sucursal` | `repo/arqueo.py` (NEW) |
| `SesionYaCerradaError` | 409 | `sesion_ya_cerrada` + `uuid_sesion` | `repo/arqueo.py` (NEW) |
| `CierreDiaNoAceptaSesionError` | 400 | `cierre_dia_no_acepta_uuid_sesion` | `repo/arqueo.py` (NEW) |
| `JustificacionRequeridaError` | 400 | `justificacion_requerida` | `repo/arqueo.py` (NEW) |
| `TenantScopeViolationError` | 403 | `tenant_scope_violation` | handler Layer 2 |
| `PermissionDeniedError` | 403 | `permission_denied` | `require_permission` |
| `IdempotencyKeyRequiredError` | 400 | `idempotency_key_required` | middleware |
| `IdempotencyConflictError` | 409 | `idempotency_conflict` | middleware |

The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

---

## 9. API Contracts

Append to `schemas/caja.py` + update `__all__`.

### 9.1 Request schemas

```python
class ArqueoCreateV2(_Base):
    """HU-F1.13: POST /api/v1/caja/arqueo payload.

    uuid_sesion MUST be NULL when uuid_tipo_arqueo resolves to codigo='cierre_dia'
    (DEC-ARQUEO-09 + DEC-ARQUEO-03). Otherwise MUST be a valid sesion UUID.

    justificacion is REQUIRED for cierre_turno/cierre_dia when diferencia != 0
    (DEC-ARQUEO-07). Optional for auditoria.

    extra='forbid' (inherited from _Base) blocks client smuggling of
    uuid_usuario, fecha_retencion_hasta, alerta_generada, alerta_uuid,
    descuadre_pct (all server-derived).
    """
    uuid_tipo_arqueo: uuid_lib.UUID
    uuid_sesion: uuid_lib.UUID | None = None
    valor_efectivo_reportado: Decimal
    valor_datafono_reportado: Decimal
    justificacion: str | None = None


class CierreDiarioQueryParams(_Base):
    """HU-F1.13: GET /api/v1/caja/arqueo/resumen query params."""
    uuid_sucursal: uuid_lib.UUID
    fecha: datetime.date
```

### 9.2 Response schemas

```python
class ArqueoReadForHandler(_Base):
    """HU-F1.13: POST /api/v1/caja/arqueo response (201)."""
    uuid: uuid_lib.UUID
    uuid_tipo_arqueo: uuid_lib.UUID
    codigo_tipo_arqueo: Literal["auditoria", "cierre_turno", "cierre_dia"]
    uuid_sesion: uuid_lib.UUID | None
    valor_efectivo_esperado: Decimal
    valor_datafono_esperado: Decimal
    valor_efectivo_reportado: Decimal
    valor_datafono_reportado: Decimal
    diferencia_efectivo: Decimal
    diferencia_datafono: Decimal
    descuadre_pct: Decimal | None      # informational ONLY (DEC-ARQUEO-04)
    alerta_generada: bool              # evaluates against |diferencia| > tolerancia
    alerta_uuid: uuid_lib.UUID | None


class ArqueoResumenItem(_Base):
    """HU-F1.13: one sesion in the daily resumen."""
    uuid_sesion: uuid_lib.UUID
    uuid_cajero: uuid_lib.UUID
    nombre_cajero: str
    timestamp_apertura: datetime.datetime
    timestamp_cierre: datetime.datetime | None
    estado: Literal["abierta", "cerrada"]
    valor_inicial_efectivo: Decimal
    valor_inicial_datafono: Decimal
    valor_efectivo_esperado: Decimal
    valor_datafono_esperado: Decimal
    valor_efectivo_reportado: Decimal | None
    valor_datafono_reportado: Decimal | None
    diferencia_efectivo: Decimal | None
    diferencia_datafono: Decimal | None
    justificacion: str | None
    uuid_arqueo: uuid_lib.UUID | None


class ArqueoResumenRead(_Base):
    """HU-F1.13: GET /api/v1/caja/arqueo/resumen response (200)."""
    fecha: datetime.date
    uuid_sucursal: uuid_lib.UUID
    sesiones: list[ArqueoResumenItem]
    cierre_dia: ArqueoResumenItem | None     # aggregate row for cierre_dia
```

### 9.3 Typed error schemas

```python
class TipoArqueoNoEncontradoError(_Base):
    error: Literal["tipo_arqueo_no_encontrado"]
    uuid_tipo_arqueo: str


class SesionNoEncontradaError(_Base):
    error: Literal["sesion_no_encontrada"]
    uuid_sesion: str


class ToleranciaNoConfiguradaError(_Base):
    error: Literal["tolerancia_no_configurada"]
    uuid_sucursal: str


class SesionYaCerradaError(_Base):
    error: Literal["sesion_ya_cerrada"]
    uuid_sesion: str


class CierreDiaNoAceptaSesionError(_Base):
    error: Literal["cierre_dia_no_acepta_uuid_sesion"]


class JustificacionRequeridaError(_Base):
    error: Literal["justificacion_requerida"]
```

Append to `schemas/caja.py` + update `__all__`. `extra='forbid'` (inherited from `_Base`) rejects client smuggling.

---

## 10. Handler Skeleton

Two handlers in one dedicated router — POST with 12-step chain (mirrors F1.11 + F1.12 shape), GET with 6-step chain (read-only).

### 10.1 POST handler (12 steps)

```python
# api/v1/caja_arqueo.py — NEW (~180 LOC)

router = APIRouter(prefix="/caja", tags=["caja"])


@router.post(
    "/arqueo",
    response_model=ArqueoReadForHandler,
    status_code=201,
    responses={
        400: {"model": CierreDiaNoAceptaSesionError},
        403: {"model": TenantScopeViolationError},
        404: {"model": TipoArqueoNoEncontradoError},
        409: {"model": SesionYaCerradaError},
    },
)
async def post_arqueo(
    response: Response,
    payload: ArqueoCreateV2,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_caja_arqueo_issuer_dep),
) -> ArqueoReadForHandler:
    no_store = no_store_headers()

    # Step 1 (KD-ARQUEO-08 + DEC-ARQUEO-09): SELECT FOR UPDATE on prod.tipo_arqueo
    tipo_arqueo = await repo_arqueo.resolver_tipo_arqueo_por_uuid(
        session, uuid_tipo_arqueo=payload.uuid_tipo_arqueo
    )
    if tipo_arqueo is None:
        raise HTTPException(404, {"error": "tipo_arqueo_no_encontrado", "uuid_tipo_arqueo": str(payload.uuid_tipo_arqueo)}, headers=no_store)

    # Step 2 (V1): cierre_dia MUST have uuid_sesion NULL; otherwise required
    if tipo_arqueo.codigo == "cierre_dia" and payload.uuid_sesion is not None:
        raise HTTPException(400, {"error": "cierre_dia_no_acepta_uuid_sesion"}, headers=no_store)
    if tipo_arqueo.codigo != "cierre_dia" and payload.uuid_sesion is None:
        raise HTTPException(400, {"error": "sesion_requerida_para_auditoria_o_cierre_turno"}, headers=no_store)

    # Layer 2 — Tenant scope post-V1
    target_sucursal = ctx.sucursal_uuid

    # Step 3 (V3): tolerance vigente row by target_sucursal
    tolerancia = await repo_arqueo.resolver_tolerancia_vigente(session, uuid_sucursal=target_sucursal)
    if tolerancia is None:
        raise HTTPException(404, {"error": "tolerancia_no_configurada", "uuid_sucursal": str(target_sucursal)}, headers=no_store)

    # Step 4 (V2 + V4): validate sesion is open (when not cierre_dia)
    if payload.uuid_sesion is not None:
        sesion = await repo_arqueo.validar_sesion_abierta_para_arqueo(session, uuid_sesion=payload.uuid_sesion, target_sucursal=target_sucursal)
        if sesion is None:
            raise HTTPException(409, {"error": "sesion_ya_cerrada", "uuid_sesion": str(payload.uuid_sesion)}, headers=no_store)

    # Step 5 (V5 + DEC-ARQUEO-04 + DEC-ARQUEO-10): compute esperado + diferencia
    if tipo_arqueo.codigo == "cierre_dia":
        esperado_efectivo, esperado_datafono = await repo_arqueo.calcular_esperado_cierre_dia(session, target_sucursal=target_sucursal, fecha=date.today())
    else:
        esperado_efectivo, esperado_datafono = await repo_arqueo.calcular_esperado_sesion(session, uuid_sesion=payload.uuid_sesion)
    diferencia_efectivo = payload.valor_efectivo_reportado - esperado_efectivo
    diferencia_datafono = payload.valor_datafono_reportado - esperado_datafono

    # Step 6 (DEC-ARQUEO-07): justificacion required when diferencia != 0 in cierre paths
    if tipo_arqueo.codigo != "auditoria" and (diferencia_efectivo != 0 or diferencia_datafono != 0):
        if not payload.justificacion:
            raise HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store)

    # Step 7 (DEC-ARQUEO-04 + KD-ARQUEO-04): descuadre decision
    es_critico = repo_arqueo.es_descuadre_critico(
        diferencia_efectivo=diferencia_efectivo,
        diferencia_datafono=diferencia_datafono,
        tolerancia_efectivo=tolerancia.tolerancia_efectivo,
        tolerancia_datafono=tolerancia.tolerancia_datafono,
    )

    # Step 8 (KD-ARQUEO-02 + DEC-ARQUEO-02): INSERT prod.arqueo [A] via append_event
    descuadre_pct = None  # informational only
    if esperado_efectivo + esperado_datafono > 0:
        descuadre_pct = ((diferencia_efectivo + diferencia_datafono) / (esperado_efectivo + esperado_datafono)) * 100
    uuid_arqueo = await repo_arqueo.insertar_arqueo(
        session, actor_uuid=ctx.actor_uuid, uuid_tipo_arqueo=tipo_arqueo.uuid,
        uuid_sesion=payload.uuid_sesion, valor_efectivo_esperado=esperado_efectivo,
        valor_datafono_esperado=esperado_datafono, valor_efectivo_reportado=payload.valor_efectivo_reportado,
        valor_datafono_reportado=payload.valor_datafono_reportado,
        diferencia_efectivo=diferencia_efectivo, diferencia_datafono=diferencia_datafono,
        descuadre_pct=descuadre_pct, justificacion=payload.justificacion,
    )

    # Step 9 (DEC-ARQUEO-03 + KD-ARQUEO-03): cierre_dia path only — close all open sesiones
    if tipo_arqueo.codigo == "cierre_dia":
        await repo_arqueo.cerrar_sesiones_del_dia_bulk(
            session, actor_uuid=ctx.actor_uuid, target_sucursal=target_sucursal, fecha=date.today()
        )

    # Step 10 (KD-ARQUEO-05 + DEC-ARQUEO-05): conditional alerta INSERT via append_transition
    alerta_uuid = None
    alerta_generada = False
    if es_critico:
        alerta_uuid = await repo_arqueo.insertar_alerta_descuadre_critico(
            session, actor_uuid=ctx.actor_uuid, uuid_arqueo=uuid_arqueo,
            uuid_sucursal=target_sucursal, diferencia_efectivo=diferencia_efectivo,
            diferencia_datafono=diferencia_datafono, payload_json={...},
        )
        alerta_generada = True

    # Step 12: KD-ARQUEO-01 SINGLE COMMIT
    await session.commit()

    apply_no_store_header(response)
    return ArqueoReadForHandler(
        uuid=uuid_arqueo,
        uuid_tipo_arqueo=tipo_arqueo.uuid,
        codigo_tipo_arqueo=tipo_arqueo.codigo,
        uuid_sesion=payload.uuid_sesion,
        valor_efectivo_esperado=esperado_efectivo,
        valor_datafono_esperado=esperado_datafono,
        valor_efectivo_reportado=payload.valor_efectivo_reportado,
        valor_datafono_reportado=payload.valor_datafono_reportado,
        diferencia_efectivo=diferencia_efectivo,
        diferencia_datafono=diferencia_datafono,
        descuadre_pct=descuadre_pct,
        alerta_generada=alerta_generada,
        alerta_uuid=alerta_uuid,
    )
```

### 10.2 GET handler (6 steps)

```python
@router.get(
    "/arqueo/resumen",
    response_model=ArqueoResumenRead,
    status_code=200,
)
async def get_arqueo_resumen(
    response: Response,
    params: CierreDiarioQueryParams = Depends(),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_caja_resumen_issuer_dep),
) -> ArqueoResumenRead:
    no_store = no_store_headers()

    # Step 1: Layer 2 tenant scope
    if ctx.issuer_prefix == "operador-" and ctx.sucursal_uuid is not None and ctx.sucursal_uuid != params.uuid_sucursal:
        raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)

    # Step 2: list sesiones of the day at branch
    sesiones = await repo_arqueo.listar_sesiones_del_dia(
        session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha
    )

    # Step 3: aggregate arqueo per sesion
    items: list[ArqueoResumenItem] = []
    for sesion in sesiones:
        item = await repo_arqueo.construir_resumen_sesion(session, sesion=sesion)
        items.append(item)

    # Step 4: cierre_dia aggregate (if exists for this fecha+sucursal)
    cierre_dia = await repo_arqueo.obtener_cierre_dia_del_dia(
        session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha
    )

    # Step 5: build ArqueoResumenRead
    resumen = ArqueoResumenRead(
        fecha=params.fecha,
        uuid_sucursal=params.uuid_sucursal,
        sesiones=items,
        cierre_dia=cierre_dia,
    )

    # Step 6: apply no-store
    apply_no_store_header(response)
    return resumen
```

Mount in `api/v1/caja.py` (`+5 LOC`):
```python
from .caja_arqueo import router as caja_arqueo_router

router.include_router(caja_arqueo_router)
```

---

## 11. Tests

9 test files + 4 AST walks + 1 migration test, ~220 LOC tests + ~290 LOC production + ~80 LOC migration + ~10 LOC GAP-BE-05 = ~590 LOC cumulative.

### 11.1 `tests/unit/test_arqueo_repo.py` (~50 LOC, 5 tests)

- `resolver_tipo_arqueo_por_uuid` (vigente + non-vigente + UUID malformed).
- `resolver_tolerancia_vigente` (branch + global fallback).
- `calcular_esperado_sesion` (sum by `medio_pago`).
- `validar_sesion_abierta_para_arqueo` (open + already-closed + not-found).
- `es_descuadre_critico` (sobre_tolerancia + igual_tolerancia + dentro_tolerancia).

### 11.2 `tests/unit/test_arqueo_handler.py` (~30 LOC, **4 tests mandated by plan.md line 1093**)

- `test_sin_diferencia_arqueo_exitoso` — happy path, sin diferencia, `auditoria` codigo, no alerta.
- `test_diferencia_justificada_arqueo_exitoso` — `cierre_turno` + diferencia != 0 + justificacion → OK, no alerta.
- `test_descuadre_sobre_tolerancia_genera_alerta` — `cierre_turno` + `|diferencia| > tolerancia` + justificacion → alerta_generada=True.
- `test_diferencia_sin_justificacion_400` — `cierre_turno` + diferencia != 0 + justificacion=None → 400 `justificacion_requerida`.

### 11.3 `tests/unit/test_cierre_dia.py` (~40 LOC, 2 tests)

- `test_cierre_dia_masivo_3_sesiones_2_cerradas_1_abierta` — verifies that only the open sesion is closed, others already closed are skipped, arqueo `uuid_sesion=NULL` is INSERTed.
- `test_cierre_dia_no_acepta_uuid_sesion_400` — POST with `codigo='cierre_dia'` + `uuid_sesion=...` → 400.

### 11.4 `tests/unit/test_arqueo_resumen.py` (~30 LOC, 3 tests)

- `test_resumen_dia_vacio` — empty day, `sesiones=[]`, `cierre_dia=None`.
- `test_resumen_dia_single_sesion_with_arqueo` — 1 sesion + 1 arqueo → 1 item.
- `test_resumen_dia_con_cierre_dia_aggregate` — N sesiones + 1 cierre_dia arqueo → N items + cierre_dia aggregate at bottom.

### 11.5 `tests/static/test_arqueo_handler_single_commit.py` (~15 LOC, KD-ARQUEO-01 walk)

- KD-ARQUEO-01 single-commit invariant. The walk scans `api/v1/caja_arqueo.py::post_arqueo` body and asserts EXACTLY ONE `await session.commit()` call. Mirror of `test_venta_handler_single_commit.py`.

### 11.6 `tests/static/test_arqueo_handler_no_raw_dml.py` (~20 LOC, KD-ARQUEO-02 walk)

- No raw INSERT/UPDATE/DELETE on `[A]`/`[V]` tables outside the `repo/arqueo.py` helpers. Specifically: no raw `session.execute(insert(Arqueo))`, no raw `session.execute(update(FacturaPago))`, no raw `session.execute(update(Arqueo))`.

### 11.7 `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (~15 LOC, NEW KD-ARQUEO-03 walk — no precedent)

- Asserts that `post_arqueo` for `cierre_dia` codigo calls `repo.session_cycle.close_session_with_log` (NOT direct `session.execute(update(Sesion))`).

### 11.8 `tests/static/test_arqueo_handler_no_update_on_a_tables.py` (~15 LOC, KD-ARQUEO-02 walk)

- No UPDATE on user-meaningful fields of `[A]` tables in the handler body. Mirror of `test_no_raw_dml_on_a_tables.py` (F1.5 PR5-016 precedent) at handler-body scope.

### 11.9 `tests/integration/test_migration_0031_idempotency.py` (~15 LOC, 2 tests)

- `alembic upgrade head` is idempotent (running twice produces the same `tstamp` + same `cierre_dia`/`descuadre_critico` rows).
- `alembic downgrade -1` reverses cleanly (drops both seeds). No schema changes applied (verify via `\d prod.tipo_arqueo` column count unchanged).

### 11.10 GAP-BE-05 unit test (~5 LOC, in `tests/unit/test_gap_be_05.py`)

- `test_caja_arqueo_endpoint_requires_realizar_arqueo_not_emitir_factura` — role with `emitir_factura` only → 403; role with `realizar_arqueo` only → 200.
- `test_caja_sesion_endpoint_requires_abrir_cerrar_caja_not_emitir_factura` — analogous for `caja_sesion.py:257`.

Total: 9 verification artifacts + 1 GAP-BE-05 unit test = 10 test artifacts.

---

## 12. Out of Scope (F2.x+)

- **B2B arqueos** (Fase 2+): corporate arqueos, multi-branch consolidated — out per plan.md line 1102.
- **Multi-sucursal simultaneous arqueo** (consolidated): out per plan.md scope.
- **UI integration** (Fase 10 HU-F10.1/10.2/10.3): deferred to Fase 10.
- **Fase 10 reconciliación de tolerancia** (pct vs absolute): plan.md line 1065 explicitly defers — Fase 10 owns.
- **Filtros de consulta en `GET /caja/arqueo`** (F18.1): out per plan.md Part 2 reference.
- **`arqueo_pendiente_24h` alerta** (F1.14): out per plan.md line 1105.
- **`ABIERTO-04` `cierre_sesion` dedicated flow** (different from `cierre_dia` arqueo): out — Fase 2+ per exploration §14.
- **`ABIERTO-200` `config_caja.redondeo`** (config-level rounding rule): out — Fase 2+.
- **Frontend reconciliation for `caja.py` factory mount**: out (Fase 8 frontend).

---

## 13. Requirements (REQ-OPS-091..097 + XR6)

The following REQ-OPS-NNN placeholders will be formalized by `sdd-spec` in `openspec/changes/hu-f1-13-arqueo/specs/operations/spec.md`:

- **REQ-OPS-091 (NEW)** — `POST /api/v1/caja/arqueo` contract: `ArqueoCreateV2` input (`{uuid_tipo_arqueo, uuid_sesion?, valor_efectivo_reportado, valor_datafono_reportado, justificacion?}`) + `ArqueoReadForHandler` output (nested UUIDs + esperados, reportados, diferencias, `descuadre_pct` informational, `alerta_generada`, `alerta_uuid`). KD-3 issuer chain (`requires_issuer("operador-", "admin-")`); `Cache-Control: no-store`; `Idempotency-Key` HTTP header (DEC-IDEM-01).

- **REQ-OPS-092 (NEW, DEC-ARQUEO-01 + KD-ARQUEO-01)** — Single-commit atomic invariant: ONE `await session.commit()` at Step 12 covers 1 [A] Arqueo + N [L-S] sesion UPDATEs (cierre_dia only) + 1 [L-W] alerta (conditional) + N+1 `log_transaccional` rows. No SAVEPOINTs. Enforced by KD-ARQUEO-01 AST walk.

- **REQ-OPS-093 (NEW, DEC-ARQUEO-09 + KD-ARQUEO-08)** — Lock ordering rule. `SELECT FOR UPDATE` on `prod.tipo_arqueo` FIRST (Step 1). Serializes concurrent `cierre_dia` per operator. Prevents deadlocks.

- **REQ-OPS-094 (NEW, DEC-ARQUEO-02 + KD-ARQUEO-02)** — `[A]` append-only via `repo/append_only.append_event`. Handler NEVER raw `session.execute(insert(Arqueo))`. AST walk enforces.

- **REQ-OPS-095 (NEW, DEC-ARQUEO-03 + KD-ARQUEO-03)** — Sesion UPDATE only via `repo/session_cycle.close_session_with_log` per-row (ls_session_guard trigger mandates log-first). For `cierre_dia` with N open sesiones: iterate per-row. AST walk `test_arqueo_handler_cierre_dia_uses_session_cycle.py` enforces.

- **REQ-OPS-096 (NEW, DEC-ARQUEO-04 + KD-ARQUEO-04)** — Tolerancia evaluated as ABSOLUTE monto. `|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono` → descuadre. `descuadre_pct` informational ONLY.

- **REQ-OPS-097 (NEW, DEC-ARQUEO-07)** — `justificacion` REQUIRED (cierre_turno/cierre_dia) when diferencia != 0, OPTIONAL for auditoria. Asymmetric per plan.md lines 1086-1091 + line 2476.

Additional defense-in-depth XR:

- **REQ-OPS-XR6 (NEW)** — Defense in depth 5 layers + single-commit AST walk (DEC-ARQUEO-06 + DEC-ARQUEO-05). F1.13 MUST apply the F1.10 + F1.11 + F1.12 defense-in-depth pattern. AST walk `tests/static/test_arqueo_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` call in `api/v1/caja_arqueo.py::post_arqueo`. Mirror of F1.10 XR1 (single-commit) + F1.11 XR4 (insert-only) + F1.12 XR5 (5-layer defense).

Additional GAP-BE-05 requirement:

- **REQ-OPS-098 (NEW, DEC-ARQUEO-08)** — `permission_required` correction in `api/v1/caja.py:53` (emitir_factura → realizar_arqueo) + `api/v1/caja_sesion.py:257` (emitir_factura → abrir_cerrar_caja). NO MIGRATION. Enforced by `tests/unit/test_gap_be_05.py`.

Wait — re-counting per the orchestrator contract: REQ-OPS-091..097 (7 REQs) + XR6 (1) = 8 requirements. REQ-OPS-098 above is a GAP-BE-05 specific REQ not counted in the 8. The 8 are:

- REQ-OPS-091: POST contract
- REQ-OPS-092: Single-commit
- REQ-OPS-093: Lock ordering
- REQ-OPS-094: [A] append-only
- REQ-OPS-095: Sesion guard
- REQ-OPS-096: Tolerancia absolute
- REQ-OPS-097: Justification asymmetry
- REQ-OPS-XR6: Defense in depth 5 layers

REQ-OPS-098 (GAP-BE-05) is supplementary, not in the 8.

---

## 14. Migrations

**MIGRATION 0031** (~80 LOC, REAL siembra). `down_revision = "0030_venta_suscripcion_optional"`.

```python
"""0031_arqueo_cierre_dia_and_gap_be_05.py — MIGRATION 0031 (REAL siembra).

Pre-flight 2026-09-15 confirmed:
- prod.tipo_arqueo exists with 3 seeded values (cierre_turno, auditoria, cierre_sesion).
- prod.alert_types exists with 9 seeded values (registry migration 0013 + 0025).
- prod.tipo_arqueo.cierre_dia NOT seeded (A-07, plan.md line 458).
- prod.alert_types.descuadre_critico NOT seeded (F1.13 needs at runtime).
- GAP-BE-05 site #1 (caja.py:53) + site #2 (caja_sesion.py:257) are Python-only
  fixes; NO migration needed (DEC-ARQUEO-08 + plan.md line 7359).

This migration ships:
- Op 0: pre-flight DO $$ block asserting required tables exist.
- Op 1: siembra prod.tipo_arqueo.codigo='cierre_dia' (A-07) — idempotent via
  IF siembra_count = 0 + ON CONFLICT (codigo, vigente_desde) DO NOTHING.
- Op 2: siembra prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'
  — idempotent via IF NOT EXISTS + ON CONFLICT (tipo_alerta) DO NOTHING
  (respects alert_types_inmutable trigger, migration 0013:21-22).
- Op 3: NO-DDL comment for GAP-BE-05 (Python-only correction in DEC-ARQUEO-08).

Idempotency ensures F1.14's future seed of `descuadre_critico` becomes a no-op.
"""
from alembic import op

revision = "0031_arqueo_cierre_dia_and_gap_be_05"
down_revision = "0030_venta_suscripcion_optional"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Op 0: pre-flight DO $$ — verify required tables exist (mandatory preamble)
    op.execute("""
        DO $$
        BEGIN
            ASSERT (
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema='prod' AND table_name IN (
                    'tipo_arqueo', 'alert_types', 'arqueo', 'sesion', 'alerta',
                    'configuracion_tolerancias', 'factura_pagos'
                )
            ) = 7, 'F1.13 requires all 7 tables to exist';
        END $$;
    """)

    # Op 1: siembra prod.tipo_arqueo.codigo='cierre_dia' (A-07, plan.md line 458)
    op.execute("""
        DO $$
        DECLARE
            siembra_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO siembra_count
            FROM prod.tipo_arqueo
            WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;
            IF siembra_count = 0 THEN
                INSERT INTO prod.tipo_arqueo (codigo, nombre, vigente_desde, vigente_hasta, estado, created_at, created_by)
                VALUES ('cierre_dia', 'Cierre de día (mass cierre de sesiones)', NOW(), NULL, 'activo', NOW(), 'migrations/0031');
            END IF;
        END $$;
    """)

    # Op 2: siembra prod.alert_types.tipo_alerta='descuadre_critico' (DEC-ARQUEO-09b)
    op.execute("""
        INSERT INTO prod.alert_types (tipo_alerta, severity, created_at, created_by)
        VALUES ('descuadre_critico', 'critical', NOW(), 'migrations/0031')
        ON CONFLICT (tipo_alerta) DO NOTHING;
    """)

    # Op 3: NO-DDL — GAP-BE-05 is a Python-only correction (DEC-ARQUEO-08)
    # Sites: api/v1/caja.py:53 + api/v1/caja_sesion.py:257
    # No DB schema changes; this comment serves as an audit-trail anchor.
    pass


def downgrade() -> None:
    # Reverse Op 2: remove descuadre_critico from alert_types
    # NOTE: alert_types_inmutable trigger blocks DELETE; disable temporarily.
    op.execute("ALTER TABLE prod.alert_types DISABLE TRIGGER alert_types_inmutable;")
    op.execute("DELETE FROM prod.alert_types WHERE tipo_alerta = 'descuadre_critico';")
    op.execute("ALTER TABLE prod.alert_types ENABLE TRIGGER alert_types_inmutable;")

    # Reverse Op 1: close the vigente row for cierre_dia (bi-temporal VersionedBase)
    op.execute("""
        UPDATE prod.tipo_arqueo
        SET vigente_hasta = NOW()
        WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;
    """)

    # Op 3: NO-DDL — GAP-BE-05 reversal is a Python revert (out of scope for downgrade()).
    # The Python sites must be reverted manually if needed.
    pass
```

### Pre-flight DO $$ block (mandatory in upgrade preamble)

The Op 0 block above asserts all 7 required tables exist (`tipo_arqueo`, `alert_types`, `arqueo`, `sesion`, `alerta`, `configuracion_tolerancias`, `factura_pagos`). Mirrors the F1.11 MIGRATION 0029 preamble pattern (`migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py:78-123`).

---

## 15. References

- `plan.md` lines 1058-1101 (HU-F1.13 definition, 4 atomic tasks T1..T4, 4 tests mandated at line 1093, 240 LOC budget)
- `plan.md` lines 7349-7374 (GAP-BE-05 verbatim mandate + bundle recommendation)
- `plan.md` line 458 (A-07 `cierre_dia` siembra)
- `plan.md` line 1065 (tolerancia = monto absoluto)
- `plan.md` lines 1086-1091 (justificacion asymmetry)
- `plan.md` line 2476 (justificacion asymmetry, duplicate)
- `plan.md` line 4549 (`realizar_arqueo` permission seeded)
- `modelo_datos_er.mmd` line 167-185 (`tipo_arqueo` [V]), line 250-268 (`configuracion_tolerancias` [V]), line 715-735 (`sesion` [L-S]), line 737-758 (`alerta` [L-W]), line 957-978 (`arqueo` [A])
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 167-185 (`tipo_arqueo` schema + bi-temporal VersionedBase), lines 250-268 (`configuracion_tolerancias`), lines 715-735 (`sesion`), lines 737-758 (`alerta`), lines 957-978 (`arqueo`), lines 2024-2088 (inmutability triggers)
- `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22)
- `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 head template for conditional siembra + permission seed pattern, lines 134-188)
- `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP audit trail head pre-F1.13)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 53 (GAP-BE-05 site #1 confirmed)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2 confirmed)
- `backend/packages/parkos_core/src/parkos_core/models/V/{tipo_arqueo, configuracion_tolerancias}.py`, `models/A/{arqueo, alert_types, factura_pagos}.py`, `models/L_S/sesion.py`, `models/L_W/alerta.py`
- `backend/packages/parkos_core/src/parkos_core/repo/{append_only, workflow, session_cycle, sesion_activa, alert_types, idempotency, hash_chain}.py` (helpers reused + `close_session_with_log` ls_session_guard lines 286-289)
- `backend/packages/parkos_core/src/parkos_core/api/v1/{operacion, facturacion, workflows_reimpresion, _helpers, deps}.py` (handler envelope references)
- `openspec/specs/operations/spec.md` lines 3217-3651 (XR1..XR5 progression, last req-number series REQ-OPS-083..090 + XR5 — next available is REQ-OPS-091)
- `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/proposal.md` (sibling precedent for 16-section structure)
- `openspec/changes/hu-f1-13-arqueo/exploration.md` (R1..R12 risks, pre-flight 18/20 PASS, DEC-ARQUEO-08 GAP-BE-05 mandate verbatim)

---

## 16. Cross-HU Implications

| HU | Relationship | Implication |
|---|---|---|
| **F1.3 (closed)** | F1.13 reuses the `abrir_cerrar_caja` permission (after GAP-BE-05 fix at `caja_sesion.py:257`) for sesion read-only routes. F1.13 reuses the sesion lifecycle contract (open/close via `close_session_with_log`). | No shared atomic transaction boundary. |
| **F1.5 (closed)** | F1.13 inherits `AppendOnlyBase` (from F1.5 PR5-016) for `prod.arqueo` + `fn_arqueo_inmutable` DB trigger. The AST walks `test_no_raw_dml_on_a_tables.py` (F1.5) is the precedent for F1.13's `test_arqueo_handler_no_update_on_a_tables.py`. | Reuses immutability contract + AST walk pattern. |
| **F1.7 (closed)** | F1.13 reuses `repo/sesion_activa.get_sesion_activa` for V2 open-sesion validation. Tenant scope post-V1 follows KD-S2 analog. | Read-only reuse. |
| **F1.9 (closed)** | F1.13 reads `prod.factura_pagos` (F1.9 inmutable) — NEVER writes. KD-FACT-01 immutability preserved. | Read-only consumption. |
| **F1.10 (closed)** | F1.13 reuses the dedicated-router pattern (`api/v1/facturacion.py` shape for `api/v1/caja_arqueo.py`) + DEC-FE-06 `Cache-Control: no-store` (XR2/XR6 mirror). | Pattern reuse. |
| **F1.11 (closed)** | F1.13 reuses `repo/workflow.append_transition` + KD-TKT-01 single-commit AST walk. DEC-TKT-06 `Cache-Control: no-store` (XR2/XR6 mirror). | Pattern reuse. |
| **F1.12 (closed)** | F1.13 reuses the dedicated-router mount pattern (`api/v1/clientes_venta.py` shape) + KD-VENTA-01 single-commit + DEC-VENTA-06 `Cache-Control: no-store` (XR6 mirror). | Pattern reuse. |
| **F1.14 (sync estado)** | F1.14 plans to seed `alert_types.descuadre_critico` (plan.md line 1131). F1.13 MIGRATION 0031 Op 2 already seeds it idempotently → F1.14's seed becomes no-op (`ON CONFLICT DO NOTHING`). | Avoids conflict; F1.14's planned seed is a no-op after F1.13. |
| **F18.1 (Parte 2)** | F18.1 will add filtros to `GET /caja/arqueo` — F1.13's `GET /caja/arqueo/resumen` is a different endpoint (resumen only), not the single-arqueo GET. | Coexistence; F18.1 extends the F1.13 contract. |
| **HU-F10.1/10.2/10.3 (frontend arqueo UX)** | Primary consumers of POST + GET. | Frontend owns the arqueo UI flow. |
| **HU-F22.3 / HU-F24.4 (Parte 3 installer)** | GAP-BE-06 already closes the `parkos_app` least-privilege story. F1.13 inherits the role contract. | No F1.13-specific installer work. |

---

**End of proposal.**
