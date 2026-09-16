# Design: HU-F1.13 — Endpoints arqueo + siembra `tipo_arqueo.cierre_dia` + GAP-BE-05 bundleado

> **Change**: `hu-f1-13-arqueo`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.13 — `POST /api/v1/caja/arqueo` (1 dedicated handler, 12-step chain) + `GET /api/v1/caja/arqueo/resumen` (1 dedicated handler, 6-step chain) — Given `uuid_tipo_arqueo` (resolves to `codigo` ∈ `{auditoria, cierre_turno, cierre_dia}`) + `uuid_sesion` (NULL when `cierre_dia`) + `valor_efectivo_reportado` + `valor_datafono_reportado` + optional `justificacion`, server-resolves the plan + tolerances + sesion, then in a **single `await session.commit()` (KD-ARQUEO-01)** writes 1 [A] Arqueo INSERT + N [L-S] sesion UPDATEs (`cierre_dia` only) + 1 conditional [L-W] alerta INSERT + N+1 `log_transaccional` co-INSERTs. Plus bundle GAP-BE-05: 2-line Python-only correction at `api/v1/caja.py:53` (`emitir_factura` → `realizar_arqueo`) + `api/v1/caja_sesion.py:257` (`emitir_factura` → `abrir_cerrar_caja`). MIGRATION 0031 = REAL siembra: Op 0 pre-flight + Op 1 `tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458) + Op 2 `alert_types.tipo_alerta='descuadre_critico', severity='critical'` + Op 3 NO-DDL comment for GAP-BE-05.
> **Date**: 2026-09-15
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a328957`; F1.1..F1.12 closed)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (16 sections, ~485 LOC, DEC-ARQUEO-01..10, KD-ARQUEO-01..05, R1 HIGH RESOLVED, R2..R12) + `specs/operations/spec.md` (REQ-OPS-091..097 + REQ-OPS-XR6, 8 new requirements in Given/When/Then/And form + 1 cross-cutting XR6).
> **Cross-references**: `modelo_datos_er.mmd` (`tipo_arqueo` [V] line 167-185, `configuracion_tolerancias` [V] line 250-268, `sesion` [L-S] line 715-735, `alerta` [L-W] line 737-758, `arqueo` [A] line 957-978, `factura_pagos` [A], `alert_types` [A] registry); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (`tipo_arqueo` lines 167-185, `configuracion_tolerancias` lines 250-268, `sesion` lines 715-735, `alerta` lines 737-758, `arqueo` lines 957-978, immutability triggers lines 2024-2088); `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22); `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 head template for siembra pattern, lines 134-188); `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP audit-trail head pre-F1.13); `backend/packages/parkos_core/src/parkos_core/models/V/{tipo_arqueo, configuracion_tolerancias}.py`, `models/A/{arqueo, alert_types, factura_pagos, log_transaccional}.py`, `models/L_S/sesion.py`, `models/L_W/alerta.py`; `backend/packages/parkos_core/src/parkos_core/repo/{append_only, workflow, session_cycle, sesion_activa, alert_types, idempotency, hash_chain}.py`; `backend/packages/parkos_core/src/parkos_core/api/v1/{operacion, facturacion, workflows_reimpresion, caja, caja_sesion, _helpers, deps}.py` (handler envelope references); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'`); `plan.md` lines 1058-1101 (HU-F1.13 definition, 4 atomic tasks T1..T4, 240 LOC production budget, 4 tests mandated at line 1093, A-07 at line 458); `plan.md` lines 7349-7374 (GAP-BE-05 verbatim mandate + bundle recommendation); `plan.md` lines 1062-1093 (full Given/When/Then contract); `plan.md` line 2476 (justification asymmetry duplicate); `plan.md` line 4549 (`realizar_arqueo` permission seeded); `openspec/specs/operations/spec.md` lines 2517-3651 (XR1..XR5 progression + REQ-OPS-083..090 last-req-number series — next available is REQ-OPS-091).
> **Precedents mirrored**: F1.12 (REQ-OPS-083..090 + REQ-OPS-XR5, KD-VENTA-01 single-commit AST walk, DEC-VENTA-06 `Cache-Control: no-store`, DEC-IDEM-01 `Idempotency-Key` middleware, dedicated `APIRouter` pattern, AST walk `tests/static/test_venta_handler_single_commit.py` shape), F1.11 (REQ-OPS-075..080 + XR4, KD-TKT-01 single-commit AST walk, KD-3 issuer `requires_issuer("operador-","admin-")` verbatim), F1.10 (REQ-OPS-064..074 + XR1..XR3, KD-FE-01 single-commit, `assign_consecutivo` `SELECT FOR UPDATE` pattern), F1.9 (REQ-OPS-053..063, KD-FACT-01 single-commit + KD-FACT-02 `FOR SHARE` lock pattern, `fn_factura_pagos_inmutable` trigger migration 0001 lines 2024-2088, inmutability contract), F1.7 (REQ-OPS-042..052, KD-S2 tenant scope post-V1), F1.6 (REQ-OPS-034..041, KD-7 pre-flight pattern, DEC-IDEM-01 Idempotency-Key header, `get_tenant_ctx` derivation), F1.5 (PR5-016, AppendOnlyBase + AST walk `tests/static/test_no_raw_dml_on_a_tables.py` precedent, REVOKE UPDATE/DELETE on [A] tables), F1.3 (`abrir_cerrar_caja` permission seeded, sesion lifecycle contract via `close_session_with_log`).

---

## 1. Title & Goal

**Design goal.** Deliver HU-F1.13: the back-end `POST /api/v1/caja/arqueo` + `GET /api/v1/caja/arqueo/resumen` endpoint pair that closes the **operador-facing caja-control workflow** (CU-10 Fase 1 prerequisite per plan.md lines 1058-1101) on top of the already-shipped `prod.tipo_arqueo` [V] (3 existing values: `cierre_turno | auditoria | cierre_sesion` per `modelo_datos_er.mmd` line 171; 4th `cierre_dia` added by F1.13 siembra per A-07 plan.md line 458), `prod.arqueo` [A] (AppendOnlyBase composite PK `uuid + fecha_retencion_hasta` per `models/A/arqueo.py:26-84`), `prod.sesion` [L-S] (SessionBase + `ls_session_guard` trigger per `repo/session_cycle.py:286-289`), `prod.alerta` [L-W] (WorkflowBase state machine `{activa -> descartada | resuelta}` per `repo/workflow.py:85-90`), `prod.configuracion_tolerancias` [V], `prod.factura_pagos` [A] (F1.9 immutable per `fn_factura_pagos_inmutable` trigger migration 0001 lines 2024-2088), and `prod.alert_types` (registry, 9 codes seeded as of 2026-09-15; `descuadre_critico` added by F1.13 siembra) by enforcing the **KD-ARQUEO-01 single-commit invariant** (exactly one `await session.commit()` per handler body covering 1 [A] Arqueo + N [L-S] sesion UPDATEs (cierre_dia only) + 1 conditional [L-W] alerta + N+1 `log_transaccional` rows) plus the **KD-ARQUEO-08 lock ordering rule** (`SELECT FOR UPDATE` on `prod.tipo_arqueo` vigente row FIRST, DEC-ARQUEO-09) plus the **5-layer defense in depth** (KD-3 issuer chain + tenant scope post-V1 + KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering + KD-ARQUEO-02/03 helpers + handler 422/409/404 mapping + `Cache-Control: no-store`) plus the **bundled GAP-BE-05 correction** (DEC-ARQUEO-08, plan.md lines 7349-7374 verbatim: 2-line Python-only permission fix at `api/v1/caja.py:53` and `api/v1/caja_sesion.py:257`, NO migration).

The design enforces **DEC-ARQUEO-01** (single `await session.commit()` at Step 12 covers 1 [A] Arqueo + N [L-S] sesion UPDATEs (cierre_dia only) + 1 conditional [L-W] alerta + N+1 `log_transaccional` rows; NO SAVEPOINT; RESOLVES R1 HIGH), **DEC-ARQUEO-02** ([A] append-only via `repo/append_only.append_event` per KD-ARQUEO-02), **DEC-ARQUEO-03** (sesion UPDATE only via `repo/session_cycle.close_session_with_log` per row per KD-ARQUEO-03 — `ls_session_guard` trigger mandates log-first ordering), **DEC-ARQUEO-04** (tolerancia evaluated as ABSOLUTE monto per plan.md line 1065; `descuadre_pct` informational ONLY), **DEC-ARQUEO-05** (dedicated `APIRouter` mounted via `router.include_router` on `caja.py` — NOT via `make_router` factory which does not support cross-table atomic writes), **DEC-ARQUEO-06** (`Cache-Control: no-store` on EVERY response — XR6 mirror from F1.10/F1.11/F1.12), **DEC-ARQUEO-07** (`justificacion` REQUIRED (cierre_turno/cierre_dia) when diferencia != 0 vs OPTIONAL (auditoria) per plan.md lines 1086-1091 + line 2476), **DEC-ARQUEO-08** (GAP-BE-05 bundled: 2-line Python-only fix at `caja.py:53` + `caja_sesion.py:257`, NO migration), **DEC-ARQUEO-09** (`cierre_dia` + `descuadre_critico` conditional siembra in MIGRATION 0031 Op 1 + Op 2), **DEC-ARQUEO-10** (`factura_pagos` summed per session via direct FK `uuid_sesion`), plus the **KD-ARQUEO-01 single-commit invariant** (mirror of F1.10 KD-FE-01 + F1.11 KD-TKT-01 + F1.12 KD-VENTA-01) and the **KD-ARQUEO-08 lock ordering rule** (`SELECT FOR UPDATE` on `prod.tipo_arqueo` vigente row at Step 1, deadlock prevention).

The handler enforces 9 validations server-side across the 12-step chain:

- V1 tipo_arqueo lookup + `SELECT FOR UPDATE`: `SELECT * FROM prod.tipo_arqueo WHERE uuid=:t AND vigente_hasta IS NULL ORDER BY vigente_desde DESC LIMIT 1 FOR UPDATE` (KD-ARQUEO-08 + DEC-ARQUEO-09); raises 404 `tipo_arqueo_no_encontrado` if missing.
- V2 cierre_dia + uuid_sesion cross-validation: when `tipo_arqueo.codigo == 'cierre_dia'` AND `payload.uuid_sesion is not None`, raise 400 `cierre_dia_no_acepta_uuid_sesion`; when `tipo_arqueo.codigo != 'cierre_dia'` AND `payload.uuid_sesion is None`, raise 400 `sesion_requerida_para_auditoria_o_cierre_turno`.
- V3 tolerance vigente row by `target_sucursal`: raises 404 `tolerancia_no_configurada` if neither branch nor global vigente row exists.
- V4 sesion validate (cerrre_turno/auditoria only): `validar_sesion_abierta_para_arqueo(session, uuid_sesion, target_sucursal)` raises 409 `sesion_ya_cerrada` when `timestamp_cierre IS NOT NULL`.
- V5 esperado compute + diferencia: `valor_efectivo_esperado = sesion.valor_inicial_efectivo + SUM(factura_pagos.valor WHERE uuid_sesion=:ses AND medio_pago='efectivo')` (DEC-ARQUEO-10); diferencia = reportado - esperado.
- V6 justificacion required on cierre_turno/cierre_dia when diferencia != 0: 400 `justificacion_requerida`.
- V7 descuadre decision: `|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono` → descuadre (DEC-ARQUEO-04).
- V8 INSERT prod.arqueo [A] via `repo/append_only.append_event`: 1 [A] row + 1 co-INSERT `log_transaccional`.
- V9 cierre_dia path only — mass sesion close via `repo_arqueo.cerrar_sesiones_del_dia_bulk` which iterates per open sesion calling `close_session_with_log(session, uuid_sesion=..., log_tx=True)` (DEC-ARQUEO-03 + KD-ARQUEO-03 + `ls_session_guard` trigger).
- V10 conditional alerta INSERT via `repo/workflow.append_transition` with `tipo_alerta='descuadre_critico', severity='critical', estado_inicial='activa'` (KD-ARQUEO-05 + DEC-ARQUEO-05 + DEC-ARQUEO-09b).
- V12 ONE `await session.commit()` covering all writes (KD-ARQUEO-01).

The GET handler enforces 4 validations across the 6-step chain:

- G1 issuer dep + permission gate (KD-3 + `realizar_arqueo` per GAP-BE-05 fix).
- G2 tenant scope post-V1: `operador-` cross-branch → 403 `tenant_scope_violation`.
- G3 list sesiones of the day at `params.uuid_sucursal` with `timestamp_apertura::date = params.fecha`.
- G4 build ArqueoResumenRead with `sesiones` + `cierre_dia` aggregate.

All responses carry `Cache-Control: no-store`. Sized at **~290 LOC production** per `plan.md` line 1097 (= ~180 LOC `api/v1/caja_arqueo.py` dedicated handler with 12-step POST + 6-step GET + 2 typed errors + router mount +5 LOC + ~100 LOC `repo/arqueo.py` 12 typed helpers + ~80 LOC MIGRATION 0031 REAL siembra + ~10 LOC GAP-BE-05 2-line fix = ~290 LOC production + ~220 LOC tests across 9 test files + 4 AST walks + 1 migration test + 1 GAP-BE-05 unit test = ~510 LOC tests/total). Total cumulative: ~590 LOC (per plan.md line 1097 budget).

**One new handler module + one new repo module + five new Pydantic schemas (request + 4 responses) + six typed error schemas + one REAL MIGRATION 0031 + one GAP-BE-05 2-line Python fix + one router mount extension. No factory changes, no sync catalog changes, no new tables, no new FKs, no new permissions, no role grants.**

---

## 2. Context & Background

`plan.md` lines **1058-1101** define HU-F1.13 as Fase-1 backend prerequisite for the operador-facing caja-control workflow (CU-10 Fase 10 user story, but Fase-1 prerequisite per plan.md Part I §1.4 "las Fases 18 (arqueos, Admin) leen `GET /caja/arqueo`"). The hard architectural constraints are **DEC-ARQUEO-01** (single `await session.commit()` at Step 12 covering 1 [A] + N [L-S] (cierre_dia) + 1 [L-W] (conditional) + N+1 log_transaccional rows — RESOLVES R1 HIGH cross-domain atomicity), **DEC-ARQUEO-02** ([A] append-only via `repo/append_only.append_event` — `fn_arqueo_inmutable` trigger blocks raw UPDATE outside helper), **DEC-ARQUEO-03** (sesion UPDATE only via `repo/session_cycle.close_session_with_log` per row — `ls_session_guard` DB trigger mandates log-first ordering for every sesion UPDATE), **DEC-ARQUEO-04** (tolerancia = absolute monto per plan.md line 1065; `descuadre_pct` informational ONLY), **DEC-ARQUEO-05** (dedicated `APIRouter` mounted via `router.include_router` on the existing `caja.py` — NOT via `make_router` factory which does not support cross-table atomic writes), **DEC-ARQUEO-06** (`Cache-Control: no-store` on EVERY response — XR6 mirror from F1.10/F1.11/F1.12), **DEC-ARQUEO-07** (`justificacion` REQUIRED (cierre_turno/cierre_dia) when diferencia != 0, OPTIONAL (auditoria) per plan.md lines 1086-1091 + line 2476 asymmetry), **DEC-ARQUEO-08** (GAP-BE-05 bundled: 2-line Python-only fix at `api/v1/caja.py:53` + `api/v1/caja_sesion.py:257`, NO migration per plan.md lines 7349-7374 verbatim), **DEC-ARQUEO-09** (`cierre_dia` + `descuadre_critico` conditional siembra in MIGRATION 0031 Op 1 + Op 2 with `IF siembra_count = 0` + `ON CONFLICT DO NOTHING` idempotent — F1.14's planned seed becomes no-op), **DEC-ARQUEO-10** (`factura_pagos` summed per session via direct FK `uuid_sesion` — NO UPDATE on `factura_pagos`), the existing pre-existing tables (`prod.tipo_arqueo` [V] lines 167-185 of migration 0001; `prod.arqueo` [A] lines 957-978; `prod.sesion` [L-S] lines 715-735; `prod.alerta` [L-W] lines 737-758; `prod.configuracion_tolerancias` [V] lines 250-268; `prod.factura_pagos` [A] F1.9 immutable per `fn_factura_pagos_inmutable` trigger; `prod.alert_types` [A] registry migration 0013), the existing ORM models (`models/V/{tipo_arqueo, configuracion_tolerancias}.py`, `models/A/{arqueo, alert_types, factura_pagos}.py`, `models/L_S/sesion.py`, `models/L_W/alerta.py`), the existing `repo/append_only.append_event` (lines 64-124), the existing `repo/workflow.append_transition` + `STATE_MACHINES['alerta']` (lines 110-237 + lines 85-90), the existing `repo/session_cycle.close_session_with_log` (lines 274-349) + `ls_session_guard` trigger reference (lines 286-289), the existing `repo/alert_types.validate` + `AlertaFactory.fire`, the existing `repo/idempotency.py` (DEC-IDEM-01 reuse, Idempotency-Key middleware), the existing `repo/sesion_activa.get_sesion_activa`, the existing `api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` (lines 18-31, DEC-ARQUEO-06 reuse), the existing `api/v1/workflows_reimpresion.py` (F1.11 dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern — referenced for the outer handler envelope shape), the existing `api/v1/clientes_venta.py` (F1.12 dedicated-router + KD-VENTA-01 single-commit + DEC-VENTA-06 no-store + KD-VENTA-02 plan lock pattern — referenced for the 12-step handler chain shape), the existing `api/v1/caja.py` (factory mount + line 53 GAP-BE-05 site #1 — currently `permission_required="emitir_factura"`, to be corrected to `"realizar_arqueo"`), the existing `api/v1/caja_sesion.py` (factory mount + line 257 GAP-BE-05 site #2 — currently `permission_required="emitir_factura"`, to be corrected to `"abrir_cerrar_caja"`), the existing `schemas/common.py::_Base` (`extra='forbid'` — Layer 4 defense), the existing `static/test_no_raw_dml_on_a_tables.py` AST walk (F1.5 PR5-016 precedent for [A] immutability + Layer 4 enforcement — F1.13 deepens with `tests/static/test_arqueo_handler_no_update_on_a_tables.py` per-handler scope + `tests/static/test_arqueo_handler_no_raw_dml.py` per-handler scope), the `MIGRATION 0029` siembra pattern (lines 134-188 — conditional siembra + permission seed + DO $$ pre-flight pattern — F1.13 mirrors in MIGRATION 0031 Op 0 + Op 1 + Op 2), the GAP-BE-05 verbatim mandate (plan.md line 7359: "Cambiar `permission_required='emitir_factura'` a `permission_required='realizar_arqueo'` en `caja.py:53` y en la porción de `caja_sesion.py:204` que protege `GET /caja/arqueo`/`GET /caja/caja`; usar `abrir_cerrar_caja` para el mount de solo lectura de `sesion`. Es una corrección de una línea por archivo, sin migración."), and the F1.13 "ampliación de producto" + "corrección bundleada" scope decision (plan.md lines 1058-1101 + lines 7349-7374: the CU-10 business capability + GAP-BE-05 catalog gap. The proposal phase records both scope decisions).

**The backend has no atomic arqueo endpoint today**, creating five concrete risks that HU-F1.13 resolves:

1. **No atomic arqueo + alerta + sesion close.** Today the operador has no way to register an arqueo (no `POST /caja/arqueo` endpoint, no `GET /caja/arqueo/resumen` endpoint). Each operation is a manual SQL EXEC against `prod.arqueo` (F1.5 PR5-016 makes `prod.arqueo` immutable, so even manual SQL would be rejected by `fn_arqueo_inmutable`). F1.13 introduces the single `await session.commit()` covering 1 [A] Arqueo + N [L-S] sesion UPDATEs (cierre_dia only) + 1 conditional [L-W] alerta + N+1 `log_transaccional` rows atomically.
2. **No `cierre_dia` tipo_arqueo value.** Today `prod.tipo_arqueo` is seeded with 3 values (`cierre_turno`, `auditoria`, `cierre_sesion` per `modelo_datos_er.mmd` line 171). The 4th `cierre_dia` is mandated by A-07 (plan.md line 458). F1.13 MIGRATION 0031 Op 1 seeds it idempotently.
3. **No `descuadre_critico` alert_type.** Today `prod.alert_types` is seeded with 9 codes; `descuadre_critico` is NOT yet seeded. F1.13 needs it at runtime for V10 `append_transition` validation. F1.14 plan.md line 1131 plans to seed it (11 codes batch with `descuadre_critico`/`sync_fallida`/etc.), but F1.14 is downstream. F1.13 MIGRATION 0031 Op 2 seeds it idempotently with `IF NOT EXISTS` + `ON CONFLICT DO NOTHING` — F1.14's future seed becomes a no-op.
4. **GAP-BE-05 unaddressed permission typo.** Today `api/v1/caja.py:53` and `api/v1/caja_sesion.py:257` both carry `permission_required="emitir_factura"` instead of the semantically correct `"realizar_arqueo"` / `"abrir_cerrar_caja"`. An operador with `emitir_factura` only could call `POST /caja/arqueo` (incorrectly); an operador with `realizar_arqueo` only would be 403'd (incorrectly). F1.13 DEC-ARQUEO-08 bundles the 2-line fix per plan.md lines 7349-7374 verbatim.
5. **No `factura_pagos` SUM helper for arqueo resumen.** Today there is no `GET /caja/arqueo/resumen` endpoint that JOINs `prod.sesion` + `prod.factura_pagos` (sum by `medio_pago`). F1.13 introduces it as a read-only endpoint (DEC-ARQUEO-10, F1.9 `fn_factura_pagos_inmutable` trigger makes writes impossible).

F1.13 closes the operador-facing caja-control endpoint pair. The work is **1 dedicated handler module (POST + GET) + 1 repo module (12 typed helpers) + 5 Pydantic schemas + 6 typed error schemas + 1 REAL MIGRATION 0031 + 1 GAP-BE-05 2-line Python fix + 1 router mount extension**. MIGRATION 0031 is a REAL siembra (Op 0 pre-flight `DO $$` + Op 1 conditional siembra `tipo_arqueo.codigo='cierre_dia'` + Op 2 conditional siembra `alert_types.tipo_alerta='descuadre_critico'` + Op 3 NO-DDL comment for GAP-BE-05) because pre-flight (2026-09-15) confirmed `cierre_dia` is missing from `prod.tipo_arqueo` and `descuadre_critico` is missing from `prod.alert_types`. **DEC-ARQUEO-09 NOT extended to sync catalog** — all 5 sync catalog entries (`tipo_arqueo`, `arqueo`, `sesion`, `alerta`, `configuracion_tolerancias`) pre-exist per pre-flight 2026-09-15.

The contract is captured in **REQ-OPS-091..097 + REQ-OPS-XR6** (added by `sdd-spec` to `specs/operations/spec.md`):

- **REQ-OPS-091** — POST single-commit atomic invariant: ONE `await session.commit()` at Step 12 covers 1 [A] Arqueo + N [L-S] sesion UPDATEs (cierre_dia only) + 1 conditional [L-W] alerta + N+1 `log_transaccional` rows. No SAVEPOINTs. Enforced by KD-ARQUEO-01 AST walk.
- **REQ-OPS-092** — `cierre_dia` mass sesion UPDATE through `session_cycle` helper only (KD-ARQUEO-03 + DEC-ARQUEO-03). `ls_session_guard` DB trigger rejects raw UPDATE without co-transactional log. AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` enforces (NEW walk — no precedent).
- **REQ-OPS-093** — Tolerancia evaluated as ABSOLUTE monto (KD-ARQUEO-04 + DEC-ARQUEO-04). `|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono`. `descuadre_pct` informational ONLY.
- **REQ-OPS-094** — `justificacion` REQUIRED on `cierre_turno`/`cierre_dia` when diferencia != 0 (DEC-ARQUEO-07 + plan.md lines 1086-1091 + line 2476).
- **REQ-OPS-095** — `alerta 'descuadre_critico'` INSERTed conditionally via `append_transition` (KD-ARQUEO-05 + DEC-ARQUEO-05). MIGRATION 0031 Op 2 seeds the registry entry idempotently.
- **REQ-OPS-096** — Sesion MUST be abierta for `cierre_turno` (KD-ARQUEO-06). `validar_sesion_abierta_para_arqueo` raises 409 `sesion_ya_cerrada` when `timestamp_cierre IS NOT NULL`.
- **REQ-OPS-097** — GET `/api/v1/caja/arqueo/resumen` JOIN sesion + `factura_pagos` SUM (KD-ARQUEO-07 + DEC-ARQUEO-10). One row per sesion of the day + `cierre_dia` aggregate at bottom.
- **REQ-OPS-XR6** — Defense in depth 5 layers + AST walks (KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering + DEC-ARQUEO-06 no-store + DEC-ARQUEO-05 dedicated router + DEC-ARQUEO-08 GAP-BE-05). AST walk `tests/static/test_arqueo_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` call in `api/v1/caja_arqueo.py::post_arqueo`. Mirror of F1.10's XR1 + F1.11's XR4 + F1.12's XR5.

F1.13 is consumed by **F1.14** (sync estado + alert_types batch; F1.13's MIGRATION 0031 Op 2 seed of `descuadre_critico` is idempotent — F1.14's planned batch becomes no-op for that code), **HU-F7.x** (frontend arqueo UX), **HU-F10.1** (frontend arqueo parcial — `auditoria` codigo), **HU-F10.2** (frontend cierre turno — `cierre_turno` codigo), **HU-F10.3** (frontend cierre día — `cierre_dia` codigo), **HU-F18.1** (backend filtros de consulta en `GET /caja/arqueo` — extends F1.13's `GET /caja/arqueo/resumen` separately), **HU-F18.2** (listado y detalle de arqueos), **HU-F18.3** (resumen de arqueos por sesión y por día), **HU-F22.3** (installer role contract — GAP-BE-05 feeds into the role/permission registry), **HU-F24.4** (installer role contract).

---

## 3. Architectural Conflict Resolution — DEC-ARQUEO-01 (R1 HIGH RESOLVED)

This section is **mandatory** for the design. It documents R1 from the sdd-explore phase (observation §R1 HIGH) and records the resolution per `proposal.md §3`.

### 3.1 The conflict (R1 HIGH)

The handler must write to 4 table families (`arqueo` [A] 1 INSERT, `sesion` [L-S] N UPDATEs (cierre_dia only), `alerta` [L-W] 1 conditional INSERT, `log_transaccional` [A] N+1 co-INSERTs). Two architectural choices are valid in PostgreSQL:

| Source | Statement | Authority weight |
|---|---|---|
| F1.11 KD-TKT-01 | "single `await session.commit()` covering all writes" | **CANONICAL** for [L-W] insert-only |
| F1.12 KD-VENTA-01 | "single `await session.commit()` covering 9 tables" | **CANONICAL** for cross-table writes |
| PostgreSQL docs | SAVEPOINTs allow partial rollback within a TX | Valid but adds complexity |
| `ls_session_guard` trigger (per `repo/session_cycle.py:286-289`) | "Per-row `log_transaccional` MUST be INSERTed BEFORE any UPDATE on `prod.sesion`" | **HARD CONSTRAINT** from DB |

The complication: `ls_session_guard` mandates per-row log-first ordering for every sesion UPDATE — not a single global pre-commit hook.

### 3.2 The resolution — DEC-ARQUEO-01: single `await session.commit()` for ALL writes

**Resolution path** (mandated by F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 precedent + DB trigger constraint):

1. **All helpers (`append_event`, `append_transition`, `close_session_with_log`, `insertar_arqueo`, `cerrar_sesiones_del_dia_bulk`, `insertar_alerta_descuadre_critico`)** stay commit-free — they `session.add()` + `await session.flush()` only.
2. **One `await session.commit()` at Step 12 of the POST handler body**, after all helper calls return.
3. **No SAVEPOINTs** in F1.13. If any helper raises, the entire TX rolls back (caller catches the HTTPException and the session is discarded by the FastAPI dependency teardown).
4. **For `cierre_dia` with N open sesiones**: iterate `for sesion in open_sessions: await close_session_with_log(session, uuid_sesion=..., log_tx=True)` — each iteration does `(log_transaccional INSERT + flush + UPDATE estado='cerrada', timestamp_cierre=..., uuid_usuario_cierre=...)` (KD-ARQUEO-03 + `ls_session_guard` trigger).
5. **Lock ordering** (KD-ARQUEO-08 + DEC-ARQUEO-09): `SELECT FOR UPDATE` on `prod.tipo_arqueo` row FIRST (V1) → serializes concurrent `cierre_dia` per operator.

### 3.3 Why this matters

- **Cross-table atomicity for `arqueo + alerta` pair** — no arqueo without its alerta when `descuadre_critico`. A SAVEPOINT strategy would partially commit, leaving orphan arqueos without the matched alerta.
- **`ls_session_guard` per-row trigger** mandates log-first ordering for every sesion UPDATE — the per-row `(log INSERT + flush + UPDATE)` pattern in `close_session_with_log` is the only allowed path.
- **The single-commit invariant becomes the AST walk contract** — `tests/static/test_arqueo_handler_single_commit.py` will scan the POST handler body and reject any second `await session.commit()` call (mirror of `test_venta_handler_single_commit.py`).
- **The lock ordering rule prevents deadlocks** under concurrent operators. Operator A acquires plan lock first, operator B waits. Operator A then iterates sesiones (each `close_session_with_log` per-row); operator B's `SELECT FOR UPDATE` on `prod.tipo_arqueo` waits until A commits. No cycle.

### 3.4 What changes in the codebase

**Production code (~290 LOC)**:
- NEW `repo/arqueo.py` — 12 typed helpers (~100 LOC): `resolver_tipo_arqueo_por_uuid`, `resolver_tolerancia_vigente`, `calcular_esperado_sesion`, `calcular_esperado_cierre_dia`, `listar_sesiones_abiertas_del_dia`, `listar_sesiones_del_dia`, `validar_sesion_abierta_para_arqueo`, `construir_resumen_sesion`, `obtener_cierre_dia_del_dia`, `es_descuadre_critico`, `insertar_arqueo`, `insertar_alerta_descuadre_critico`, `cerrar_sesiones_del_dia_bulk`.
- NEW `api/v1/caja_arqueo.py` — dedicated `APIRouter` with 2 handlers (~180 LOC, DEC-ARQUEO-05): `post_arqueo` (12-step chain) + `get_arqueo_resumen` (6-step chain).
- NEW `schemas/caja.py::ArqueoCreateV2` + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams` + 6 typed error schemas (~90 LOC extension).
- MODIFY `api/v1/caja.py` — 1 line at :53 (DEC-ARQUEO-08 + GAP-BE-05 site #1: `emitir_factura` → `realizar_arqueo`) + `router.include_router(caja_arqueo_router)` mount extension (~5 LOC).
- MODIFY `api/v1/caja_sesion.py` — 1 line at :257 (DEC-ARQUEO-08 + GAP-BE-05 site #2: `emitir_factura` → `abrir_cerrar_caja`).
- NEW `migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` — REAL siembra (~80 LOC).

**Tests (~220 LOC)**:
- 5 repo unit tests in `tests/unit/test_arqueo_repo.py` (~50 LOC).
- **4 handler unit tests in `tests/unit/test_arqueo_handler.py`** (~30 LOC, mandated by plan.md line 1093): sin diferencia/diferencia_justificada/descuadre_sobre_tolerancia/diferencia_sin_justificacion.
- 4 cierre_dia unit tests in `tests/unit/test_cierre_dia.py` (~40 LOC).
- 5 resumen unit tests in `tests/unit/test_arqueo_resumen.py` (~30 LOC).
- 5 schema unit tests in `tests/unit/test_arqueo_schemas.py` (~30 LOC).
- 1 e2e in `tests/integration/test_arqueo_e2e.py` (~15 LOC).
- 1 migration idempotency test in `tests/integration/test_migration_0031_idempotency.py` (~15 LOC, 2 tests).
- 2 GAP-BE-05 unit tests in `tests/unit/test_gap_be_05.py` (~5 LOC).
- 4 AST walks: `test_arqueo_handler_single_commit.py` (KD-ARQUEO-01, ~15 LOC), `test_arqueo_handler_no_raw_dml.py` (~20 LOC), `test_arqueo_handler_cierre_dia_uses_session_cycle.py` (KD-ARQUEO-03 NEW walk, ~15 LOC), `test_arqueo_handler_no_update_on_a_tables.py` (KD-ARQUEO-02, ~15 LOC).

### 3.5 What changes in MIGRATION 0031 (REAL siembra — RESOLVED as conditional)

```sql
-- Op 0: pre-flight DO $$ (KD-7 F1.6 + F1.7 + F1.9 + F1.10 + F1.11 + F1.12 pattern)
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

-- Op 1: siembra prod.tipo_arqueo.codigo='cierre_dia' (A-07, plan.md line 458)
DO $$
DECLARE siembra_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO siembra_count
    FROM prod.tipo_arqueo
    WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;
    IF siembra_count = 0 THEN
        INSERT INTO prod.tipo_arqueo (codigo, nombre, vigente_desde, vigente_hasta, estado, created_at, created_by)
        VALUES ('cierre_dia', 'Cierre de día (mass cierre de sesiones)', NOW(), NULL, 'activo', NOW(), 'migrations/0031');
    END IF;
END $$;

-- Op 2: siembra prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'
INSERT INTO prod.alert_types (tipo_alerta, severity, created_at, created_by)
VALUES ('descuadre_critico', 'critical', NOW(), 'migrations/0031')
ON CONFLICT (tipo_alerta) DO NOTHING;

-- Op 3: NO-DDL comment for GAP-BE-05 (DEC-ARQUEO-08 — Python-only correction)
-- Sites: api/v1/caja.py:53 + api/v1/caja_sesion.py:257
-- No DB schema changes; this comment serves as an audit-trail anchor.
```

The migration is idempotent: `Op 1` checks `siembra_count = 0` before INSERT; `Op 2` uses `ON CONFLICT DO NOTHING` (respects `alert_types_inmutable` trigger migration 0013:21-22). The `DO $$` pre-flight aborts with a typed exception if any of the 7 required tables is missing. **Idempotency ensures F1.14's future seed of `descuadre_critico` becomes a no-op** (`ON CONFLICT (tipo_alerta) DO NOTHING`).

---

## 4. Architecture Overview

```
HTTPS POST /api/v1/caja/arqueo
        Body: ArqueoCreateV2
        │      {uuid_tipo_arqueo, uuid_sesion?, valor_efectivo_reportado,
        │       valor_datafono_reportado, justificacion?}
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        │  permission_required="realizar_arqueo" (post-GAP-BE-05 fix at caja.py:53)
        │  Idempotency-Key: <uuid>  (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10 + F1.11 + F1.12)
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/caja_arqueo.py  (NEW, +180 LOC, 2 handlers — POST 12-step + GET 6-step) │
│                                                                              │
│ @router.post("/arqueo", response_model=ArqueoReadForHandler, status_code=201) │
│ async def post_arqueo(response, payload, session, ctx, _claims)             │
│                                                                              │
│  1. KD-ARQUEO-08 + DEC-ARQUEO-09: SELECT FOR UPDATE on prod.tipo_arqueo      │
│      tipo_arqueo = await repo_arqueo.resolver_tipo_arqueo_por_uuid(         │
│          session, uuid_tipo_arqueo=payload.uuid_tipo_arqueo                   │
│      )                                                                         │
│      if tipo_arqueo is None:                                                  │
│          raise 404 {"error":"tipo_arqueo_no_encontrado", ...}                │
│                                                                              │
│  2. V2: cierre_dia cross-validation                                           │
│      if tipo_arqueo.codigo == "cierre_dia" and payload.uuid_sesion is not None: │
│          raise 400 {"error":"cierre_dia_no_acepta_uuid_sesion", ...}         │
│      if tipo_arqueo.codigo != "cierre_dia" and payload.uuid_sesion is None:   │
│          raise 400 {"error":"sesion_requerida_para_auditoria_o_cierre_turno"}│
│                                                                              │
│  2a. Layer 2 — Tenant scope post-V1 (KD-S2 analog from F1.7):              │
│      target_sucursal = ctx.sucursal_uuid                                       │
│                                                                              │
│  3. V3: tolerance vigente row by target_sucursal                              │
│      tolerancia = await repo_arqueo.resolver_tolerancia_vigente(            │
│          session, uuid_sucursal=target_sucursal                              │
│      )                                                                         │
│      if tolerancia is None:                                                   │
│          raise 404 {"error":"tolerancia_no_configurada", ...}                 │
│                                                                              │
│  4. V4: validate sesion is open (cerrre_turno/auditoria only)                │
│      if payload.uuid_sesion is not None:                                      │
│          sesion = await repo_arqueo.validar_sesion_abierta_para_arqueo(    │
│              session, uuid_sesion=payload.uuid_sesion, target_sucursal=target_sucursal │
│          )                                                                     │
│          if sesion is None:                                                   │
│              raise 409 {"error":"sesion_ya_cerrada", ...}                    │
│                                                                              │
│  5. V5: compute esperado + diferencia (DEC-ARQUEO-04 + DEC-ARQUEO-10)      │
│      if tipo_arqueo.codigo == "cierre_dia":                                   │
│          esperado_efectivo, esperado_datafono = await repo_arqueo.          │
│              calcular_esperado_cierre_dia(session, target_sucursal=..., fecha=today)│
│      else:                                                                    │
│          esperado_efectivo, esperado_datafono = await repo_arqueo.          │
│              calcular_esperado_sesion(session, uuid_sesion=payload.uuid_sesion)│
│      diferencia_efectivo = payload.valor_efectivo_reportado - esperado_efectivo│
│      diferencia_datafono = payload.valor_datafono_reportado - esperado_datafono│
│                                                                              │
│  6. V6 (DEC-ARQUEO-07): justificacion required when diferencia != 0          │
│      if tipo_arqueo.codigo != "auditoria" and                                │
│         (diferencia_efectivo != 0 or diferencia_datafono != 0):             │
│          if not payload.justificacion:                                        │
│              raise 400 {"error":"justificacion_requerida", ...}              │
│                                                                              │
│  7. V7 (DEC-ARQUEO-04 + KD-ARQUEO-04): descuadre decision                    │
│      es_critico = repo_arqueo.es_descuadre_critico(                          │
│          diferencia_efectivo=diferencia_efectivo,                            │
│          diferencia_datafono=diferencia_datafono,                            │
│          tolerancia_efectivo=tolerancia.tolerancia_efectivo,                  │
│          tolerancia_datafono=tolerancia.tolerancia_datafono,                  │
│      )                                                                         │
│                                                                              │
│  8. V8 (KD-ARQUEO-02 + DEC-ARQUEO-02): INSERT prod.arqueo [A]               │
│      descuadre_pct = None  # informational only                              │
│      if esperado_efectivo + esperado_datafono > 0:                            │
│          descuadre_pct = ((diferencia_efectivo + diferencia_datafono) /      │
│                           (esperado_efectivo + esperado_datafono)) * 100       │
│      uuid_arqueo = await repo_arqueo.insertar_arqueo(session, ...)          │
│                                                                              │
│  9. V9 (DEC-ARQUEO-03 + KD-ARQUEO-03): cierre_dia path only — mass close    │
│      if tipo_arqueo.codigo == "cierre_dia":                                   │
│          await repo_arqueo.cerrar_sesiones_del_dia_bulk(                     │
│              session, target_sucursal=target_sucursal, fecha=today            │
│          )  # iterates per open sesion via close_session_with_log            │
│                                                                              │
│ 10. V10 (KD-ARQUEO-05 + DEC-ARQUEO-05): conditional alerta INSERT           │
│      alerta_uuid = None                                                        │
│      alerta_generada = False                                                   │
│      if es_critico:                                                           │
│          alerta_uuid = await repo_arqueo.insertar_alerta_descuadre_critico( │
│              session, ...                                                     │
│          )                                                                     │
│          alerta_generada = True                                                │
│                                                                              │
│ 12. KD-ARQUEO-01 SINGLE COMMIT:                                               │
│      await session.commit()  # UN solo commit (covers 4 table families)      │
│                                                                              │
│ 13. DEC-ARQUEO-06 — Cache-Control: no-store + response shape:                │
│      apply_no_store_header(response)                                          │
│      return ArqueoReadForHandler(                                             │
│          uuid=uuid_arqueo, uuid_tipo_arqueo=tipo_arqueo.uuid,                 │
│          codigo_tipo_arqueo=tipo_arqueo.codigo, uuid_sesion=payload.uuid_sesion,│
│          valor_efectivo_esperado=esperado_efectivo,                           │
│          valor_datafono_esperado=esperado_datafono,                           │
│          valor_efectivo_reportado=payload.valor_efectivo_reportado,           │
│          valor_datafono_reportado=payload.valor_datafono_reportado,           │
│          diferencia_efectivo=diferencia_efectivo,                             │
│          diferencia_datafono=diferencia_datafono,                             │
│          descuadre_pct=descuadre_pct, alerta_generada=alerta_generada,       │
│          alerta_uuid=alerta_uuid,                                              │
│      )                                                                         │
└──────────────────────────────────────────────────────────────────────────────┘

HTTPS GET /api/v1/caja/arqueo/resumen?uuid_sucursal=X&fecha=YYYY-MM-DD
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        │  permission_required="realizar_arqueo"
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/caja_arqueo.py::get_arqueo_resumen  (6-step chain)                    │
│                                                                              │
│  1. Layer 1 — issuer dep + permission gate (KD-3 + GAP-BE-05)               │
│                                                                              │
│  2. Layer 2 — tenant scope post-V1                                            │
│      if ctx.issuer_prefix == "operador-" and ctx.sucursal_uuid != params.uuid_sucursal:│
│          raise 403 {"error":"tenant_scope_violation", ...}                    │
│                                                                              │
│  3. G3: list sesiones of the day at branch                                     │
│      sesiones = await repo_arqueo.listar_sesiones_del_dia(                   │
│          session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha      │
│      )                                                                         │
│                                                                              │
│  4. G4: aggregate arqueo per sesion                                            │
│      items: list[ArqueoResumenItem] = []                                      │
│      for sesion in sesiones:                                                   │
│          item = await repo_arqueo.construir_resumen_sesion(session, sesion=sesion)│
│          items.append(item)                                                    │
│                                                                              │
│  5. G5: cierre_dia aggregate (if exists for fecha+sucursal)                   │
│      cierre_dia = await repo_arqueo.obtener_cierre_dia_del_dia(             │
│          session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha      │
│      )                                                                         │
│                                                                              │
│  6. G6: build ArqueoResumenRead + apply no-store                             │
│      resumen = ArqueoResumenRead(                                             │
│          fecha=params.fecha, uuid_sucursal=params.uuid_sucursal,              │
│          sesiones=items, cierre_dia=cierre_dia,                                │
│      )                                                                         │
│      apply_no_store_header(response)                                          │
│      return resumen                                                            │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                                       ▲
        │ AST walk single-commit (KD-ARQUEO-01) │ AST walk no-raw-DML (DEC-ARQUEO-05)
        │ for post_arqueo                       │ for post_arqueo
tests/static/test_arqueo_handler_single_commit.py
tests/static/test_arqueo_handler_no_raw_dml.py
tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py  (NEW walk — KD-ARQUEO-03)
tests/static/test_arqueo_handler_no_update_on_a_tables.py  (KD-ARQUEO-02)
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW):                                                           │
│   repo/arqueo.py   (~100 LOC) — 12 typed helpers + 6 typed exceptions        │
│                                                                              │
│ Repo helpers (REUSED verbatim, NO modify):                                    │
│   repo/append_only.py::append_event (F1.5) — used for V8 Arqueo INSERT      │
│   repo/workflow.py::append_transition (F1.5) — used for V10 alerta INSERT  │
│   repo/workflow.py::STATE_MACHINES['alerta'] (F1.5) — initial {activa} only  │
│   repo/session_cycle.py::close_session_with_log (F1.3) — used for V9 per-row│
│   repo/session_cycle.py::validar_sesion_abierta (F1.3) — used for V4        │
│   repo/alert_types.py::validate (F1.5/migration 0013) — used for V10 validate│
│   repo/alert_types.py::AlertaFactory.fire (F1.5/migration 0013) — used for V10│
│   repo/idempotency.py::guard + store_response (F1.6) — DEC-IDEM-01 reuse    │
│   repo/sesion_activa.py::get_sesion_activa (F1.3) — used for V4 fallback    │
│   api/v1/_helpers.py::no_store_headers() + apply_no_store_header() (F1.6)    │
│                                                                              │
│ Schemas (MODIFY):                                                             │
│   schemas/caja.py     (+90 LOC) — ArqueoCreateV2 + ArqueoReadForHandler +   │
│                                       ArqueoResumenItem + ArqueoResumenRead + │
│                                       CierreDiarioQueryParams + 6 typed error│
│                                                                              │
│ Tables operational (READ + INSERT + UPDATE conditional):                     │
│   prod.tipo_arqueo        [V]  — Step 1 V1 SELECT FOR UPDATE (KD-ARQUEO-08) │
│   prod.configuracion_tolerancias [V] — Step 3 V3 SELECT vigente row          │
│   prod.arqueo             [A]  — Step 8 V8 INSERT via append_event           │
│   prod.sesion             [L-S] — Step 4 V4 SELECT (validate) + Step 9 V9   │
│                                            per-row UPDATE via close_session_with_log│
│   prod.factura_pagos      [A]  — Step 5 V5 SELECT SUM by medio_pago (READ-ONLY)│
│   prod.alerta             [L-W] — Step 10 V10 conditional INSERT via append_transition│
│   prod.alert_types        [A]  — registry validate for tipo_alerta='descuadre_critico'│
│   prod.log_transaccional  [A]  — AUTO co-INSERT via helpers (per row)        │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲
        ▼ MIGRATION 0031 (REAL siembra — applied BEFORE F1.13 tests)
┌──────────────────────────────────────────────────────────────────────────────┐
│ migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py                  │
│                                                                              │
│ Op 0 — Pre-flight DO $$:                                                     │
│   ASSERT all 7 tables exist (tipo_arqueo, alert_types, arqueo, sesion, alerta,│
│   configuracion_tolerancias, factura_pagos)                                  │
│                                                                              │
│ Op 1 — siembra prod.tipo_arqueo.codigo='cierre_dia' (A-07):                  │
│   IF siembra_count = 0 + ON CONFLICT (codigo, vigente_desde) DO NOTHING      │
│                                                                              │
│ Op 2 — siembra prod.alert_types.tipo_alerta='descuadre_critico':             │
│   INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING (respects inmutable trigger)│
│                                                                              │
│ Op 3 — NO-DDL comment for GAP-BE-05 (Python-only correction)                │
│                                                                              │
│ downgrade() reverses Ops 1+2 with 1-hour window (F1.11 precedent)            │
│                                                                              │
│ down_revision = '0030_venta_suscripcion_optional'                            │
└──────────────────────────────────────────────────────────────────────────────┘

GAP-BE-05 (DEC-ARQUEO-08):
  api/v1/caja.py:53      — permission_required="emitir_factura" → "realizar_arqueo"  (1 line)
  api/v1/caja_sesion.py:257 — permission_required="emitir_factura" → "abrir_cerrar_caja"  (1 line)
  No migration. No new permission seed. Both permissions pre-seeded (plan.md line 4549 + F1.3).
```

The handler is thin + orquestador. All validation logic lives in `repo/arqueo.py`. The single `commit()` at Step 12 materializes all rows atomically (KD-ARQUEO-01). The `ls_session_guard` trigger is satisfied by the per-row `(log INSERT + flush + UPDATE)` pattern inside `close_session_with_log` (KD-ARQUEO-03).

### Sub-chain reference shapes

**Per-sesion close sub-chain (Step 9, `cierre_dia` only)** — mirrors `repo/session_cycle.py::close_session_with_log` lines 274-349 verbatim. The `cerrar_sesiones_del_dia_bulk` helper in `repo/arqueo.py` is a NEW function that:

1. Calls `repo.sesion_activa.listar_sesiones_abiertas_del_dia(session, target_sucursal=..., fecha=...)` → returns list of ORM `Sesion` rows.
2. For each `sesion` in the list (each open): `await repo.session_cycle.close_session_with_log(session, uuid_sesion=sesion.uuid, actor_uuid=ctx.actor_uuid, log_tx=True)`. Each iteration does `(log_transaccional INSERT + flush + sesion UPDATE estado='cerrada', timestamp_cierre=..., uuid_usuario_cierre=...)`.

**Conditional alerta sub-chain (Step 10, when `es_critico=True`)** — mirrors `repo/workflow.py::append_transition` lines 110-237 verbatim. The `insertar_alerta_descuadre_critico` helper in `repo/arqueo.py` is a NEW function that:

1. Validates `tipo_alerta='descuadre_critico'` against `prod.alert_types` via `repo.alert_types.validate` (raises 500 `alert_type_no_registrado` if missing — but MIGRATION 0031 Op 2 ensures it's seeded).
2. Calls `repo.workflow.append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', estado_inicial='activa', severity='critical', uuid_recurso_origen=uuid_arqueo, tipo_recurso_origen='arqueo', payload_json={...}, actor_uuid=ctx.actor_uuid)` → INSERT 1 `prod.alerta` row + 1 `prod.log_transaccional` row.
3. Returns `alerta_uuid`.

Both sub-chains share the caller's session and commit boundary (KD-ARQUEO-01). They do NOT call `session.commit()` themselves — they `session.add()` + `await session.flush()` only.

---

## 5. Component Diagram

```
backend/packages/parkos_core/src/parkos_core/
├── api/v1/
│   ├── caja.py              (MODIFY, +6 LOC)  ── 1 line at :53 (GAP-BE-05 site #1)
│   │                                              ── router.include_router(caja_arqueo_router) mount
│   ├── caja_arqueo.py       (NEW, +180 LOC)    ── dedicated router + 2 handlers (POST 12-step + GET 6-step)
│   ├── caja_sesion.py       (MODIFY, 1 line at :257)  ── GAP-BE-05 site #2
│   ├── clientes_venta.py    (READ-ONLY ref)    ── F1.12 dedicated-router + KD-VENTA-01 pattern
│   ├── workflows_reimpresion.py (READ-ONLY ref) ── F1.11 dedicated-router pattern
│   ├── operacion.py         (READ-ONLY ref)    ── canonical handler envelope
│   ├── facturacion.py       (READ-ONLY ref)    ── F1.9 12-step atomic pattern
│   └── _helpers.py          (REUSE)            ── no_store_headers + apply_no_store_header
├── repo/
│   ├── arqueo.py            (NEW, +100 LOC)    ── 12 typed helpers + 6 typed exceptions
│   ├── append_only.py       (REUSE)            ── append_event (F1.5)
│   ├── workflow.py          (REUSE)            ── append_transition + STATE_MACHINES['alerta'] (F1.5)
│   ├── session_cycle.py     (REUSE)            ── close_session_with_log + ls_session_guard (F1.3)
│   ├── sesion_activa.py     (REUSE)            ── get_sesion_activa + listar_sesiones (F1.3)
│   ├── alert_types.py       (REUSE)            ── validate + AlertaFactory.fire (F1.5/migration 0013)
│   ├── idempotency.py       (REUSE)            ── DEC-IDEM-01 middleware
│   └── hash_chain.py        (REUSE)            ── log_transaccional carrier
├── schemas/
│   ├── caja.py              (EXTEND, +90 LOC)  ── ArqueoCreateV2 + 4 responses + 6 typed errors
│   └── common.py            (REUSE)            ── _Base with extra='forbid'
├── models/V/
│   ├── tipo_arqueo.py       (REUSE)            ── ORM model
│   └── configuracion_tolerancias.py (REUSE)    ── ORM model
├── models/A/
│   ├── arqueo.py            (REUSE)            ── AppendOnlyBase ORM model
│   ├── alert_types.py       (REUSE)            ── registry ORM model
│   ├── factura_pagos.py     (REUSE)            ── F1.9 inmutable ORM model
│   └── log_transaccional.py (REUSE)            ── hash chain carrier
├── models/L_S/
│   └── sesion.py            (REUSE)            ── SessionBase ORM model
├── models/L_W/
│   └── alerta.py            (REUSE)            ── WorkflowBase ORM model
├── auth/
│   └── tenancy.py           (REUSE)            ── TenantContext + get_tenant_ctx
├── migrations/versions/
│   └── 0031_arqueo_cierre_dia_and_gap_be_05.py (NEW, ~80 LOC)   ── REAL siembra
│   └── 0030_venta_suscripcion_optional.py    (current head pre-F1.13)
│   └── 0029_reimpresion_siembra_and_permiso_anular.py (template for 0031 siembra pattern, lines 134-188)
│   └── 0013_add_alert_types.py              (alert_types registry + inmutable trigger, lines 21-22)
└── sync/catalog/entries/
    ├── sync_entries_v.py    (NO CHANGE)        ── all 5 [V] entries pre-existing
    └── sync_entries_a.py    (NO CHANGE)        ── all [A] entries pre-existing
```

**Module-level responsibilities:**

| Module | Type | Responsibility |
|---|---|---|
| `api/v1/caja_arqueo.py` | NEW | Dedicated `APIRouter` (DEC-ARQUEO-05) with 2 handlers: `post_arqueo` (12-step chain, ~140 LOC) + `get_arqueo_resumen` (6-step chain, ~40 LOC). Calls helpers in `repo/arqueo.py` + the existing `repo/append_only.py` + `repo/workflow.py` + `repo/session_cycle.py` + `repo/alert_types.py` for the V8/V9/V10 sub-chains. Single `await session.commit()` at Step 12 (KD-ARQUEO-01). |
| `repo/arqueo.py` | NEW | 12 typed helpers (V1..V10 + G3..G5) + 6 typed exceptions (~100 LOC). ALL helpers stay commit-free — they `session.add()` + `await session.flush()` only (KD-ARQUEO-01 contract). Reuses `repo.append_only.append_event`, `repo.workflow.append_transition`, `repo.session_cycle.close_session_with_log`, `repo.alert_types.validate`. NO new ORM model changes. |
| `schemas/caja.py` | EXTEND | +90 LOC: `ArqueoCreateV2(_Base)` request schema; `ArqueoReadForHandler(_Base)` POST response; `ArqueoResumenItem(_Base)` per-sesion row; `ArqueoResumenRead(_Base)` GET response; `CierreDiarioQueryParams(_Base)` GET query params; 6 typed error schemas (`TipoArqueoNoEncontradoError`, `SesionNoEncontradaError`, `ToleranciaNoConfiguradaError`, `SesionYaCerradaError`, `CierreDiaNoAceptaSesionError`, `JustificacionRequeridaError`). All inherit `extra='forbid'` (inherited from `_Base`). |
| `api/v1/caja.py` | MODIFY | +6 LOC: 1 line at :53 (DEC-ARQUEO-08 GAP-BE-05 site #1: `emitir_factura` → `realizar_arqueo`) + `from .caja_arqueo import router as caja_arqueo_router` + `router.include_router(caja_arqueo_router)` mount at the bottom. The factory mount + `gestionar_caja`-related permissions are inherited. |
| `api/v1/caja_sesion.py` | MODIFY | 1 line at :257 (DEC-ARQUEO-08 GAP-BE-05 site #2: `emitir_factura` → `abrir_cerrar_caja`). NO mount extension. |
| `migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` | NEW | ~80 LOC REAL siembra. Pre-flight `DO $$` block confirms all 7 required tables exist. `upgrade()` does Op 0 + Op 1 + Op 2 + Op 3. `downgrade()` reverses Ops 1+2 with 1-hour window (F1.11 precedent). `down_revision='0030_venta_suscripcion_optional'`. |

**Data flow for one POST `/caja/arqueo`:**

```
FastAPI route resolution
  └─▶ caja.py router
        └─▶ router.include_router(caja_arqueo_router)
              └─▶ caja_arqueo.py::post_arqueo (12-step chain)
                    ├─▶ KD-3 issuer dep (DI-resolved)
                    ├─▶ repo_arqueo.resolver_tipo_arqueo_por_uuid  (V1 SELECT FOR UPDATE, KD-ARQUEO-08)
                    ├─▶ In-process cierre_dia cross-validation  (V2)
                    ├─▶ (Layer 2) Tenant scope check (in-process)
                    ├─▶ repo_arqueo.resolver_tolerancia_vigente  (V3)
                    ├─▶ (Conditional) repo_arqueo.validar_sesion_abierta_para_arqueo  (V4)
                    ├─▶ repo_arqueo.calcular_esperado_sesion OR calcular_esperado_cierre_dia  (V5)
                    ├─▶ In-process justificacion check  (V6)
                    ├─▶ repo_arqueo.es_descuadre_critico  (V7 DEC-ARQUEO-04)
                    ├─▶ repo_arqueo.insertar_arqueo  (V8 KD-ARQUEO-02 via append_event)
                    ├─▶ (Conditional) repo_arqueo.cerrar_sesiones_del_dia_bulk  (V9 KD-ARQUEO-03 via close_session_with_log per row)
                    ├─▶ (Conditional) repo_arqueo.insertar_alerta_descuadre_critico  (V10 KD-ARQUEO-05 via append_transition)
                    ├─▶ await session.commit()  (KD-ARQUEO-01 single commit, Step 12)
                    ├─▶ apply_no_store_header(response)
                    └─▶ return ArqueoReadForHandler(...)
```

**Data flow for one GET `/caja/arqueo/resumen`:**

```
FastAPI route resolution
  └─▶ caja.py router
        └─▶ router.include_router(caja_arqueo_router)
              └─▶ caja_arqueo.py::get_arqueo_resumen (6-step chain)
                    ├─▶ KD-3 issuer dep (DI-resolved)
                    ├─▶ (Layer 2) Tenant scope check (in-process)
                    ├─▶ repo_arqueo.listar_sesiones_del_dia  (G3)
                    ├─▶ For each sesion: repo_arqueo.construir_resumen_sesion  (G4)
                    ├─▶ repo_arqueo.obtener_cierre_dia_del_dia  (G5)
                    ├─▶ apply_no_store_header(response)
                    └─▶ return ArqueoResumenRead(...)
```

---

## 6. Data Model

**MIGRATION 0031 introduces NO schema changes** — it is a conditional data siembra only. The 7 tables F1.13 touches already exist with all required columns:

- `prod.tipo_arqueo` [V] (migration 0001 lines 167-185) — 4th `cierre_dia` value seeded by MIGRATION 0031 Op 1.
- `prod.arqueo` [A] (migration 0001 lines 957-978) — 7 business columns + audit + sync columns server-set.
- `prod.sesion` [L-S] (migration 0001 lines 715-735) — bi-temporal + lifecycle columns + `ls_session_guard` trigger.
- `prod.alerta` [L-W] (migration 0001 lines 737-758) — WorkflowBase state machine columns.
- `prod.configuracion_tolerancias` [V] (migration 0001 lines 250-268) — 3 business columns.
- `prod.factura_pagos` [A] (F1.9, migration 0001 lines 2024-2088 immutability trigger) — read-only.
- `prod.alert_types` [A] (migration 0013, registry with `alert_types_inmutable` trigger lines 21-22) — `descuadre_critico` seeded by MIGRATION 0031 Op 2.

### 6.1 `prod.tipo_arqueo` [V] (READ + LOCK + siembra)

| Property | Value |
|---|---|
| **ER línea** | 167-185 |
| **Migration 0001 línea** | 167-185 |
| **Operations** | V1 SELECT vigente row + `SELECT FOR UPDATE` row lock (KD-ARQUEO-08 + DEC-ARQUEO-09). No INSERT, no UPDATE. **Op 1 MIGRATION 0031 siembra `codigo='cierre_dia'` (A-07, plan.md line 458)**. |
| **Columns read** | `uuid`, `codigo`, `vigente_desde`, `vigente_hasta`, `nombre`, `estado`. |
| **Columns write (INSERT)** | `codigo='cierre_dia'`, `nombre='Cierre de día (mass cierre de sesiones)'`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`, `created_at`, `created_by='migrations/0031'`. |
| **Indexes** | UK `tipo_arqueo_uk01 (codigo, vigente_desde)` per `models/V/tipo_arqueo.py:28`. |
| **Defense in depth** | bi-temporal VersionedBase guarantees at most one vigente row per `codigo`. Handler returns 404 `tipo_arqueo_no_encontrado` if lookup returns NULL. KD-ARQUEO-08 `SELECT FOR UPDATE` exclusive lock prevents concurrent `cierre_dia` from racing on the plan row. |
| **REVOKE** | Already enforced by F1.5 PR5-016 (REVOKE UPDATE, DELETE on `[V]` tables FROM rol_app per migration 0021 lines 162, 182). |

### 6.2 `prod.arqueo` [A] (INSERT only via `append_event`)

| Property | Value |
|---|---|
| **ER línea** | 957-978 |
| **Migration 0001 línea** | 957-978 |
| **Operations** | V8 INSERT via `repo/append_only.append_event` (KD-ARQUEO-02 + DEC-ARQUEO-02). Handler NEVER raw `session.execute(insert(Arqueo))` — AST walk enforces. |
| **Columns write (INSERT)** | `uuid` (server-set), `fecha_retencion_hasta` (server-set, monthly partition key, `end-of-month` from created_at), `uuid_tipo_arqueo`, `uuid_sesion` (NULL for `cierre_dia`), `uuid_usuario` (from `ctx.actor_uuid`), `valor_efectivo_esperado`, `valor_datafono_esperado`, `valor_efectivo_reportado`, `valor_datafono_reportado`, `diferencia_efectivo`, `diferencia_datafono`, `descuadre_pct` (informational only, DEC-ARQUEO-04), `justificacion`, `alerta_generada` (Boolean), `alerta_uuid` (UUID, NULL when not generated). Audit + sync columns server-set. |
| **Indexes** | composite PK `(uuid, fecha_retencion_hasta)`. Monthly pg_partman RANGE partition by `fecha_retencion_hasta`. |
| **Defense in depth** | `fn_arqueo_inmutable` trigger (migration 0001) rejects UPDATE/DELETE outside `append_event`. F1.5 PR5-016 REVOKE UPDATE/DELETE on `[A]` tables FROM rol_app per migration 0021. |
| **FK relationships** | FK to `prod.tipo_arqueo.uuid` (ER línea 957+), FK to `prod.sesion.uuid` (NULL for cierre_dia), FK to `prod.usuarios.uuid`, FK to `prod.alerta.uuid` (when `alerta_generada=true`). |

### 6.3 `prod.sesion` [L-S] (SELECT + conditional UPDATE)

| Property | Value |
|---|---|
| **ER línea** | 715-735 |
| **Migration 0001 línea** | 715-735 |
| **Operations** | V2 SELECT vigente sesion (when `cierre_turno`/`auditoria`); V4 conditional UPDATE per-row via `close_session_with_log` ONLY when `cierre_dia` (KD-ARQUEO-03 + `ls_session_guard` trigger). |
| **For `cierre_dia` with N open sesiones** | iterate `for sesion in open_sessions: await close_session_with_log(session, uuid_sesion=..., log_tx=True)`. Each iteration does `(log_transaccional INSERT + flush + UPDATE estado='cerrada', timestamp_cierre=..., uuid_usuario_cierre=...)` (KD-ARQUEO-03 + `ls_session_guard` DB trigger). |
| **Columns update (cierre_dia only)** | `estado='cerrada'`, `timestamp_cierre=NOW()`, `uuid_usuario_cierre=ctx.actor_uuid`. |
| **Indexes** | PK `sesion_pk (uuid)` + FK indexes on `uuid_sucursal`, `uuid_cajero`. |
| **Defense in depth** | `ls_session_guard` DB trigger (per `repo/session_cycle.py:286-289`) REJECTS raw UPDATE without co-transactional `log_transaccional` row. AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` enforces (NEW walk — no precedent). |
| **FK relationships** | FK to `prod.usuarios.uuid` (cajero), FK to `prod.sucursal.uuid`. |

### 6.4 `prod.alerta` [L-W] (conditional INSERT only)

| Property | Value |
|---|---|
| **ER línea** | 737-758 |
| **Migration 0001 línea** | 737-758 |
| **Operations** | V10 conditional INSERT initial via `repo/workflow.append_transition` when `es_descuadre_critico(plan, valor_efectivo_reportado, valor_datafono_reportado) == True` (KD-ARQUEO-05 + DEC-ARQUEO-05). |
| **Columns write (INSERT)** | `uuid_alerta` (server-set), `uuid_alerta_padre=NULL` (initial), `tipo_alerta='descuadre_critico'` (validated by `alert_types.validate` — Op 2 MIGRATION 0031 seeds the registry), `severity='critical'`, `uuid_sucursal=target_sucursal`, `uuid_recurso_origen=uuid_arqueo`, `tipo_recurso_origen='arqueo'`, `payload_json={diferencia_efectivo, diferencia_datafono, tolerancia_efectivo, tolerancia_datafono, descuadre_pct, codigo_tipo_arqueo, uuid_sesion}`, `workflow_estado='activa'`, `created_at`, `created_by=ctx.actor_uuid`. |
| **Indexes** | PK `alerta_pk (uuid_alerta)` + FK index on `uuid_recurso_origen`, `uuid_alerta_padre`. |
| **Defense in depth** | `append_transition` uses `STATE_MACHINES['alerta']` (per `repo/workflow.py:85-90`) which permits initial state `{activa -> descartada | resuelta}` only. AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` enforces no raw INSERT/UPDATE/DELETE on `prod.alerta`. |
| **FK relationships** | FK to `prod.alert_types.tipo_alerta` (registry), FK to `prod.sucursal.uuid`, FK to `prod.arqueo.uuid` (via `uuid_recurso_origen`). |

### 6.5 `prod.configuracion_tolerancias` [V] (READ only)

| Property | Value |
|---|---|
| **ER línea** | 250-268 |
| **Migration 0001 línea** | 250-268 |
| **Operations** | V3 SELECT vigente row by `uuid_sucursal=target_sucursal OR uuid_sucursal IS NULL` (NULL = default global). Returns tolerance pair `(tolerancia_efectivo, tolerancia_datafono)`. No INSERT, no UPDATE. |
| **Columns read** | `uuid`, `uuid_sucursal`, `tolerancia_efectivo` (Numeric), `tolerancia_datafono` (Numeric), `vigente_desde`, `vigente_hasta`. |
| **Columns write** | None. |
| **Indexes** | UK `configuracion_tolerancias_uk01 (uuid_sucursal, vigente_desde)` per `models/V/configuracion_tolerancias.py`. |
| **Defense in depth** | bi-temporal VersionedBase. Returns 404 `tolerancia_no_configurada` if neither branch nor global vigente row exists. |

### 6.6 `prod.factura_pagos` [A] (READ only)

| Property | Value |
|---|---|
| **ER línea** | F1.9 inmutable |
| **Migration 0001 línea** | 2024-2088 (`fn_factura_pagos_inmutable` trigger) |
| **Operations** | V5 SELECT `SUM(valor) WHERE uuid_sesion=:sesion_uuid AND medio_pago IN ('efectivo', 'tarjeta', 'datafono') AND tipo_movimiento='pago' GROUP BY medio_pago` (DEC-ARQUEO-10). NEVER UPDATE/INSERT/DELETE on `factura_pagos`. |
| **Columns read** | `uuid`, `uuid_sesion`, `medio_pago`, `valor`, `tipo_movimiento` (filter to `'pago'`). |
| **Columns write** | None. |
| **Indexes** | FK index on `uuid_sesion` (migration 0001 line 716). |
| **Defense in depth** | `fn_factura_pagos_inmutable` trigger (migration 0001 lines 2024-2088) + F1.9 immutability contract. AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` enforces no UPDATE/INSERT/DELETE on `prod.factura_pagos`. |

### 6.7 `prod.alert_types` [A] (READ + siembra)

| Property | Value |
|---|---|
| **ER línea** | (registry table, migration 0013) |
| **Migration 0013 línea** | lines 21-22 (`alert_types_inmutable` trigger) |
| **Operations** | V10 `validate(tipo_alerta='descuadre_critico')` before INSERT into `prod.alerta`. **Op 2 MIGRATION 0031 siembra `tipo_alerta='descuadre_critico', severity='critical'`** (DEC-ARQUEO-09b + F1.14 idempotency). |
| **Columns read** | `tipo_alerta`, `severity`, `created_at`, `created_by`. |
| **Columns write (INSERT)** | `tipo_alerta='descuadre_critico'`, `severity='critical'`, `created_at=NOW()`, `created_by='migrations/0031'`. |
| **Indexes** | PK `alert_types_pk (tipo_alerta)`. |
| **Defense in depth** | `alert_types_inmutable` trigger (migration 0013:21-22) blocks UPDATE/DELETE on existing codes — only INSERT at siembra time (when `IF NOT EXISTS` + `ON CONFLICT (tipo_alerta) DO NOTHING`). |

### 6.8 `prod.log_transaccional` [A] (INSERT — multiple, AUTO)

| Property | Value |
|---|---|
| **ER línea** | (F1.5 hash chain carrier) |
| **Operations** | AUTO-INSERTED via `repo/append_only.append_event` (1 per `[A]` Arqueo INSERT) + `repo/workflow.append_transition` (1 per `[L-W]` Alerta INSERT) + `repo/session_cycle.close_session_with_log` (1 per `[L-S]` Sesion UPDATE, `cierre_dia` only). F1.13 NOT responsible — they are co-transactional by design. |

### 6.9 Sync catalog pre-flight (RESOLVED 2026-09-15 — no F1.13 sync catalog seeds needed)

| Table | Direction | Broadcast | F1.13 Status |
|---|---|---|---|
| `tipo_arqueo` | `cloud_to_branch` | `all_branches` | pre-existing; new `cierre_dia` propagates automatically |
| `arqueo` | `branch_to_cloud` | `all_branches` | pre-existing |
| `sesion` | `branch_to_cloud` | `all_branches` | pre-existing |
| `alerta` | `branch_to_cloud` | `all_branches` | pre-existing |
| `configuracion_tolerancias` | `cloud_to_branch` | `all_branches` | pre-existing |

**All 5 entries pre-existing.** MIGRATION 0031 has NO sync catalog seed operation. DEC-ARQUEO-09 NOT extended to sync catalog.

### 6.10 Tables touched summary

| Table | Type | Operation | Lines ER / migration |
|---|---|---|---|
| `tipo_arqueo` | `[V]` | V1 SELECT FOR UPDATE (KD-ARQUEO-08) + Op 1 siembra | ER 167-185 / migration 0001 lines 167-185 |
| `arqueo` | `[A]` | V8 INSERT via `append_event` (KD-ARQUEO-02) | ER 957-978 / migration 0001 lines 957-978 |
| `sesion` | `[L-S]` | V4 SELECT (validate) + V9 per-row UPDATE via `close_session_with_log` (cierre_dia only, KD-ARQUEO-03) | ER 715-735 / migration 0001 lines 715-735 |
| `alerta` | `[L-W]` | V10 conditional INSERT via `append_transition` (KD-ARQUEO-05) | ER 737-758 / migration 0001 lines 737-758 |
| `configuracion_tolerancias` | `[V]` | V3 SELECT vigente row | ER 250-268 / migration 0001 lines 250-268 |
| `factura_pagos` | `[A]` | V5 SELECT SUM by medio_pago (READ-ONLY) | F1.9 / migration 0001 lines 2024-2088 immutability |
| `alert_types` | `[A]` | V10 validate + Op 2 siembra | migration 0013 / lines 21-22 inmutable trigger |
| `log_transaccional` | `[A]` | AUTO co-INSERT (per [A]/[L-W]/[L-S] write) | F1.5 PR5-016 / migration 0021 |

**No column added** for any new field. **No FK added**. **No new index added**. **No new trigger added**. **No sync catalog change** — all 5 entries pre-existing (DEC-ARQUEO-09 NOT extended to sync catalog).

**State transitions** happen via NEW rows with `vigente_desde=now()` discriminator on the [V] tables; chain integrity is via the bi-temporal `vigente_hasta` discriminator (NEVER UPDATE on user-meaningful fields per F1.5 PR5-016). The state machine for `alerta` is via `STATE_MACHINES['alerta']` (per `repo/workflow.py:85-90`) which permits initial state `{activa -> descartada | resuelta}` only.

**Sync catalog impact**: ZERO. `sync_entries_v.py` + `sync_entries_a.py` already carry all 5 + 5 entries. No sync changes needed by F1.13.

---

## 7. Concurrency & Locking

### 7.1 Lock inventory

The handler acquires locks in strict order (KD-ARQUEO-08):

| Order | Lock type | Target | When acquired | When released |
|---|---|---|---|---|
| 1 | `SELECT ... FOR UPDATE` (exclusive) | `prod.tipo_arqueo.uuid=:t` (vigente row) | Step 1 (V1) | Step 12 (commit) |
| 2 | `SELECT FOR UPDATE` per-row inside `close_session_with_log` | `prod.sesion.uuid=:ses` (each open sesion on cierre_dia path) | Step 9 (V9, per iteration) | Step 12 (commit) |
| 3 | `SELECT FOR SHARE` (F1.9 KD-FACT-02 analog) implicit | `prod.configuracion_tolerancias.uuid_sucursal=:s` (vigente row read) | Step 3 (V3) | Step 12 (commit) — read-only, no actual lock |

No other locks are acquired. The [A] writes (`arqueo`, `alerta`) acquire their own UK checks internally (`append_event` validates `pk(uuid, fecha_retencion_hasta)`; `append_transition` validates `pk(uuid_alerta)`) but those are INSERT-only checks, not locks. The `log_transaccional` writes acquire row-level UK checks via `hash_chain.py` but those are co-transactional and committed at Step 12.

### 7.2 DEC-ARQUEO-09 lock ordering rule (KD-ARQUEO-08)

The handler MUST acquire the `tipo_arqueo` lock FIRST (Step 1) before any other lock. The handler MUST acquire the `sesion` lock (Step 9, only on `cierre_dia` path) AFTER. The handler MUST acquire the `tolerancia` lock (Step 3, read-only) BETWEEN. The handler MUST NOT reverse the ordering.

**Why**: prevents AB-BA deadlocks under concurrent operators. Consider:

- **OP-A**: `uuid_tipo_arqueo=:t_cierre_dia` (plan lock) + iterates over open sesiones at sucursal `:s` (per-row sesion lock).
- **OP-B**: `uuid_tipo_arqueo=:t_auditoria` (plan lock) + sesion `:ses1` at the same sucursal `:s` (per-row sesion lock).

If the sesion lock were acquired FIRST (before plan lock):
- OP-A acquires `:ses1` (per-row), waits for `:t_cierre_dia` (plan lock).
- OP-B acquires `:ses1` (impossible — OP-A holds it), OP-B waits for `:ses1` first → AB-BA deadlock.
- PostgreSQL detects the cycle and kills one TX with `deadlock_detected`.

With the plan lock FIRST (KD-ARQUEO-08):
- OP-A acquires `:t_cierre_dia` (independent of `:t_auditoria`).
- OP-B acquires `:t_auditoria` (independent of `:t_cierre_dia`).
- OP-A acquires `:ses1` (no other TX holds it yet — OP-B hasn't reached per-row lock).
- OP-B's `SELECT FOR UPDATE` on `prod.tipo_arqueo` waits until OP-A commits at Step 12 (independent plans, no waiting).
- OP-A commits, releases `:ses1` + `:t_cierre_dia`.
- OP-B acquires `:ses1`, proceeds.
- No deadlock, no abort.

### 7.3 KD-ARQUEO-08 plan lock type — `SELECT FOR UPDATE` (exclusive)

The handler takes `SELECT ... FOR UPDATE` (exclusive) on `prod.tipo_arqueo` at V1. F1.9 took `SELECT ... FOR SHARE` (shared) on `prod.tarifas_sucursal` (KD-FACT-02). The divergence is intentional.

**Why exclusive**: A plan read mutates the arqueo semantics — `uuid_sesion` is captured (NULL for `cierre_dia`) and `alerta_generada` decision depends on the cierre semantics. Two concurrent operators on the SAME `tipo_arqueo` row with DIFFERENT `uuid_sesion` would race on `insertar_arqueo`. `FOR SHARE` allows multiple readers to proceed in parallel, but the INSERT into `prod.arqueo` would conflict on the `pk(uuid)` (server-set). The exclusive lock serializes the arqueo insert, ensuring each operator sees a deterministic snapshot of `(tipo_arqueo, plan semantics)`.

**Why `FOR SHARE` was correct for F1.9**: A tarifa read does NOT mutate the calc — the `valor_unitario` + `cantidad` are server-derived from the items. Concurrent facturas on the same tarifa can proceed in parallel.

### 7.4 Deadlock analysis

Under DEC-ARQUEO-09 + KD-ARQUEO-08:

- **Same `tipo_arqueo` + same `sesion` (different operators)**: serialized at Step 1 (plan lock). No deadlock.
- **Different `tipo_arqueo` + same `sesion`**: independent plan locks. Sesion lock at Step 9 (cierre_dia path) serializes. No deadlock.
- **Same `tipo_arqueo` + different `sesion`**: serialized at Step 1 (plan lock). Different sesion inserts proceed independently. No deadlock.
- **Different `tipo_arqueo` + different `sesion`**: fully parallel. No contention.
- **Same `tipo_arqueo` + multiple sesiones (same operator, cierre_dia)**: serialized at Step 1 (plan lock). Different sesion UPDATEs proceed in sequence inside the helper.

The only deadlock risk is reversing the order (sesion FIRST or tolerancia FIRST). DEC-ARQUEO-09 veda this.

### 7.5 Cierre_dia mass-close serialization

For `cierre_dia` with N open sesiones, the handler iterates per open sesion calling `close_session_with_log(session, uuid_sesion=..., log_tx=True)`. Each iteration:

1. Acquires per-row lock via `SELECT ... FOR UPDATE` on `prod.sesion.uuid=:ses`.
2. Emits `prod.log_transaccional` row + flush.
3. Updates `prod.sesion` SET `estado='cerrada'`, `timestamp_cierre=NOW()`, `uuid_usuario_cierre=ctx.actor_uuid` + flush.

The `ls_session_guard` DB trigger validates the log-first ordering per iteration. Two concurrent operators on DIFFERENT sucursales with disjoint sesion sets do NOT block each other (independent rows). Two concurrent operators on the SAME sucursal with OVERLAPPING open sesiones (rare in practice) serialize per-row.

### 7.6 `pg_advisory_xact_lock` (NOT USED in F1.13)

F1.13 does NOT use `pg_advisory_xact_lock`. The plan lock + per-row sesion lock suffice. F1.12 used `pg_advisory_xact_lock` on `uuid_subscripcion_cliente` (REQ-OP-08) — F1.13 does not have an analogous resource key (the plan UUID is locked via SELECT FOR UPDATE).

---

## 8. Transaction Boundaries

### 8.1 DEC-ARQUEO-01 — Single `await session.commit()` for ALL writes

The POST handler body issues EXACTLY ONE `await session.commit()` call at Step 12. All helper functions (`insertar_arqueo`, `cerrar_sesiones_del_dia_bulk`, `insertar_alerta_descuadre_critico`, `validar_sesion_abierta_para_arqueo`, `resolver_tipo_arqueo_por_uuid`, `resolver_tolerancia_vigente`, `calcular_esperado_sesion`, `calcular_esperado_cierre_dia`, `es_descuadre_critico`, `listar_sesiones_del_dia`, `construir_resumen_sesion`, `obtener_cierre_dia_del_dia`) are commit-free — they `session.add()` + `await session.flush()` only (or read-only).

The GET handler issues ZERO `await session.commit()` calls — it's read-only.

### 8.2 KD-ARQUEO-01 — Single-commit invariant (AST walk enforced)

The AST walk `tests/static/test_arqueo_handler_single_commit.py` scans `api/v1/caja_arqueo.py::post_arqueo` body and asserts:

- `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'commit']) == 1`
- `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0`
- NO occurrence of the literal string `"SAVEPOINT"` in the handler body.

Any of these three conditions failing breaks KD-ARQUEO-01 and the test fails.

### 8.3 KD-ARQUEO-01 invariant rationale

Cross-domain atomicity is the entire business requirement (plan.md line 1065: "no arqueo without its alerta when descuadre_critico"). The 4-table-family single commit is well within PostgreSQL's capabilities — the [V] tables have minimal locking (UK checks), the [A]/[L-W] tables are INSERT-only, the [L-S] per-row `close_session_with_log` does `(log INSERT + flush + UPDATE)` which is well-tested in F1.3. SAVEPOINTs would partially commit, leaving orphan arqueos without the matched alerta (R1 HIGH).

### 8.4 Helper commit-free contract

All 12 helpers in `repo/arqueo.py` are commit-free:

| Helper | Operation | Commits? |
|---|---|---|
| `resolver_tipo_arqueo_por_uuid` (V1) | SELECT FOR UPDATE | NO |
| `resolver_tolerancia_vigente` (V3) | SELECT vigente | NO |
| `calcular_esperado_sesion` (V5) | SELECT SUM by medio_pago | NO |
| `calcular_esperado_cierre_dia` (V5) | SELECT SUM by medio_pago (aggregate over all open sesiones) | NO |
| `listar_sesiones_abiertas_del_dia` (V9 helper) | SELECT (open sesion list) | NO |
| `listar_sesiones_del_dia` (G3) | SELECT (sesion list for resumen) | NO |
| `validar_sesion_abierta_para_arqueo` (V4) | SELECT + raise | NO |
| `construir_resumen_sesion` (G4) | SELECT + JOIN | NO |
| `obtener_cierre_dia_del_dia` (G5) | SELECT arqueo with uuid_sesion=NULL | NO |
| `es_descuadre_critico` (V7) | in-process Decimal math | NO |
| `insertar_arqueo` (V8) | INSERT via `append_event` | NO |
| `insertar_alerta_descuadre_critico` (V10) | INSERT via `append_transition` | NO |
| `cerrar_sesiones_del_dia_bulk` (V9) | per-row `close_session_with_log` | NO |

Plus all reused F1.3/F1.5/F1.6 helpers (already commit-free per their contracts):

| Helper | Operation | Commits? |
|---|---|---|
| `repo.append_only.append_event` (F1.5) | INSERT [A] | NO |
| `repo.workflow.append_transition` (F1.5) | INSERT [L-W] initial | NO |
| `repo.session_cycle.close_session_with_log` (F1.3) | per-row `(log INSERT + flush + UPDATE)` | NO |
| `repo.alert_types.validate` (F1.5/migration 0013) | SELECT registry | NO |
| `repo.alert_types.AlertaFactory.fire` (F1.5/migration 0013) | INSERT [L-W] via append_transition | NO |
| `repo.idempotency.guard` (F1.6) | SELECT cache | NO |
| `repo.idempotency.store_response` (F1.6) | INSERT cache row | NO |

All commits are owned by the POST handler at Step 12. The GET handler is read-only (no commits).

---

## 9. Validation Chain (V1..V10 + G1..G6)

The 12-step POST handler chain runs 10 server-side validations. Each validation either succeeds (proceed to next step) or raises `HTTPException` with a typed error discriminator (mapped from `repo/arqueo.py` typed exceptions). The 6-step GET handler chain runs 6 server-side validations. The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

### 9.1 V1 — Tipo_arqueo lookup + lock

**Step**: 1 (handler) · **Helper**: `resolver_tipo_arqueo_por_uuid(session, *, uuid_tipo_arqueo) -> TipoArqueo`

**Logic**:
```sql
SELECT * FROM prod.tipo_arqueo
WHERE uuid = :t AND vigente_hasta IS NULL
ORDER BY vigente_desde DESC LIMIT 1
FOR UPDATE
```

**Errors**:
- 404 `tipo_arqueo_no_encontrado` (lookup returns NULL)

### 9.2 V2 — Cierre_dia cross-validation

**Step**: 2 (handler) · **In-process**: 2 conditionals

**Logic**:
```python
if tipo_arqueo.codigo == "cierre_dia" and payload.uuid_sesion is not None:
    raise 400 "cierre_dia_no_acepta_uuid_sesion"
if tipo_arqueo.codigo != "cierre_dia" and payload.uuid_sesion is None:
    raise 400 "sesion_requerida_para_auditoria_o_cierre_turno"
```

**Errors**:
- 400 `cierre_dia_no_acepta_uuid_sesion`
- 400 `sesion_requerida_para_auditoria_o_cierre_turno`

### 9.3 V3 — Tolerance vigente row

**Step**: 3 (handler) · **Helper**: `resolver_tolerancia_vigente(session, *, uuid_sucursal) -> ConfiguracionTolerancias`

**Logic**:
```sql
SELECT * FROM prod.configuracion_tolerancias
WHERE (uuid_sucursal = :s OR uuid_sucursal IS NULL)
  AND vigente_hasta IS NULL
ORDER BY uuid_sucursal NULLS LAST, vigente_desde DESC
LIMIT 1
```

**Errors**:
- 404 `tolerancia_no_configurada` (no branch OR global vigente row)

### 9.4 V4 — Sesion validate (cierre_turno/auditoria only)

**Step**: 4 (handler, when `payload.uuid_sesion is not None`) · **Helper**: `validar_sesion_abierta_para_arqueo(session, *, uuid_sesion, target_sucursal) -> Sesion`

**Logic**:
```sql
SELECT * FROM prod.sesion
WHERE uuid = :ses AND uuid_sucursal = :s
  AND estado = 'abierta' AND timestamp_cierre IS NULL
LIMIT 1
```
If returns NULL (sesion not found OR not open): raise `SesionYaCerradaError`.

**Errors**:
- 404 `sesion_no_encontrada` (uuid_sesion not found)
- 409 `sesion_ya_cerrada` (`timestamp_cierre IS NOT NULL`)

### 9.5 V5 — Esperado + diferencia compute

**Step**: 5 (handler) · **Helpers**: `calcular_esperado_sesion` or `calcular_esperado_cierre_dia`

**Logic**:
- For `cierre_turno`/`auditoria`: `SELECT medio_pago, SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=:ses AND medio_pago IN ('efectivo', 'tarjeta', 'datafono') AND tipo_movimiento='pago' GROUP BY medio_pago`. Compute `esperado_efectivo = sesion.valor_inicial_efectivo + SUM WHERE medio_pago='efectivo'`; `esperado_datafono = sesion.valor_inicial_datafono + SUM WHERE medio_pago IN ('tarjeta', 'datafono')` (DEC-ARQUEO-10).
- For `cierre_dia`: same query but SUM over ALL `factura_pagos` for ALL open sesiones at `target_sucursal` for the day.
- `diferencia_efectivo = payload.valor_efectivo_reportado - esperado_efectivo`.
- `diferencia_datafono = payload.valor_datafono_reportado - esperado_datafono`.

**Errors**:
- (none — pure read + math)

### 9.6 V6 — Justificacion required (cierre_turno/cierre_dia only, when diferencia != 0)

**Step**: 6 (handler) · **In-process**: 1 conditional

**Logic**:
```python
if tipo_arqueo.codigo != "auditoria" and (
    diferencia_efectivo != 0 or diferencia_datafono != 0
):
    if not payload.justificacion:
        raise 400 "justificacion_requerida"
```

**Errors**:
- 400 `justificacion_requerida`

### 9.7 V7 — Descuadre decision (DEC-ARQUEO-04 absolute monto)

**Step**: 7 (handler) · **Helper**: `es_descuadre_critico(*, diferencia_efectivo, diferencia_datafono, tolerancia_efectivo, tolerancia_datafono) -> bool`

**Logic**:
```python
return (
    abs(diferencia_efectivo) > tolerancia_efectivo
    or abs(diferencia_datafono) > tolerancia_datafono
)
```

**Errors**:
- (none — pure math)

### 9.8 V8 — INSERT prod.arqueo [A] via `append_event` (KD-ARQUEO-02)

**Step**: 8 (handler) · **Helper**: `insertar_arqueo(session, *, actor_uuid, uuid_tipo_arqueo, uuid_sesion, valor_efectivo_esperado, valor_datafono_esperado, valor_efectivo_reportado, valor_datafono_reportado, diferencia_efectivo, diferencia_datafono, descuadre_pct, justificacion) -> UUID`

**Logic**:
- Compute `fecha_retencion_hasta = end-of-month(created_at)`.
- Build `Arqueo(uuid=..., fecha_retencion_hasta=..., uuid_tipo_arqueo=..., uuid_sesion=..., uuid_usuario=actor_uuid, valor_efectivo_esperado=..., ..., alerta_generada=False, alerta_uuid=None)`.
- Call `repo.append_only.append_event(session, tabla='arqueo', uuid=..., attrs={...})` → INSERT 1 `prod.arqueo` row + 1 co-INSERT `prod.log_transaccional` row.
- Returns `uuid_arqueo`.

**Errors**:
- (none — INSERT only, no constraint conflicts expected)

### 9.9 V9 — Cierre_dia mass sesion close (KD-ARQUEO-03 + `ls_session_guard`)

**Step**: 9 (handler, when `tipo_arqueo.codigo == 'cierre_dia'`) · **Helper**: `cerrar_sesiones_del_dia_bulk(session, *, actor_uuid, target_sucursal, fecha) -> None`

**Logic**:
- `open_sesiones = await listar_sesiones_abiertas_del_dia(session, target_sucursal=..., fecha=...)`.
- For each `sesion` in `open_sesiones`: `await repo.session_cycle.close_session_with_log(session, uuid_sesion=sesion.uuid, actor_uuid=actor_uuid, log_tx=True)`. Each iteration does `(log_transaccional INSERT + flush + sesion UPDATE estado='cerrada', timestamp_cierre=NOW(), uuid_usuario_cierre=actor_uuid)`.
- The `ls_session_guard` DB trigger validates per-row log-first ordering.

**Errors**:
- (none — `ls_session_guard` would reject raw UPDATE, but `close_session_with_log` is the correct path)

### 9.10 V10 — Conditional alerta INSERT via `append_transition` (KD-ARQUEO-05)

**Step**: 10 (handler, when `es_critico=True`) · **Helper**: `insertar_alerta_descuadre_critico(session, *, actor_uuid, uuid_arqueo, uuid_sucursal, diferencia_efectivo, diferencia_datafono, payload_json) -> UUID`

**Logic**:
- Validate `tipo_alerta='descuadre_critico'` via `repo.alert_types.validate` (raises 500 `alert_type_no_registrado` if missing — but MIGRATION 0031 Op 2 ensures seeded).
- Call `repo.workflow.append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', estado_inicial='activa', severity='critical', uuid_recurso_origen=uuid_arqueo, tipo_recurso_origen='arqueo', payload_json={diferencia_efectivo, diferencia_datafono, ...}, actor_uuid=actor_uuid)` → INSERT 1 `prod.alerta` row + 1 co-INSERT `prod.log_transaccional` row.
- Returns `alerta_uuid`.

**Errors**:
- 500 `alert_type_no_registrado` (only if MIGRATION 0031 was not applied — should never happen)

### 9.11 V12 — Single `await session.commit()` (KD-ARQUEO-01)

**Step**: 12 (handler) · **In-process**: `await session.commit()`

**Errors**:
- (none — atomic commit covers V8 + V10 + log rows; on failure, entire TX rolls back)

### 9.12 G1..G6 — GET handler validation chain

The 6-step GET handler chain:

| Step | Validation | Helper / Source | Errors |
|---|---|---|---|
| G1 | KD-3 issuer + permission gate | DI-resolved (`requires_issuer("operador-", "admin-")`) + factory `permission_required="realizar_arqueo"` | 403 (no operador/admin prefix); 403 (no `realizar_arqueo` permission) |
| G2 | Tenant scope post-V1 | in-process check | 403 `tenant_scope_violation` |
| G3 | List sesiones of the day | `listar_sesiones_del_dia` | (none — empty list OK) |
| G4 | Aggregate arqueo per sesion | `construir_resumen_sesion` (per sesion in loop) | (none) |
| G5 | Cierre_dia aggregate | `obtener_cierre_dia_del_dia` | (none — NULL OK) |
| G6 | Build ArqueoResumenRead + apply no-store | in-process | (none) |

### 9.13 Validation chain summary

| Step | Validation | Helper | Errors |
|---|---|---|---|
| 1 | KD-3 issuer | DI-resolved | 403 (no operador/admin prefix) |
| 1 | V1 tipo_arqueo SELECT FOR UPDATE (KD-ARQUEO-08) | `resolver_tipo_arqueo_por_uuid` | 404 `tipo_arqueo_no_encontrado` |
| 2 | V2 cierre_dia cross-validation | in-process | 400 `cierre_dia_no_acepta_uuid_sesion`, 400 `sesion_requerida_para_auditoria_o_cierre_turno` |
| 2a | Layer 2 tenant scope | in-process | 403 `tenant_scope_violation` |
| 3 | V3 tolerance vigente | `resolver_tolerancia_vigente` | 404 `tolerancia_no_configurada` |
| 4 | V4 sesion validate (cerrre_turno/auditoria) | `validar_sesion_abierta_para_arqueo` | 404 `sesion_no_encontrada`, 409 `sesion_ya_cerrada` |
| 5 | V5 esperado + diferencia compute | `calcular_esperado_sesion` or `calcular_esperado_cierre_dia` | (none) |
| 6 | V6 justificacion check | in-process | 400 `justificacion_requerida` |
| 7 | V7 descuadre decision | `es_descuadre_critico` | (none) |
| 8 | V8 INSERT arqueo [A] | `insertar_arqueo` (KD-ARQUEO-02) | (none) |
| 9 | V9 cierre_dia mass close | `cerrar_sesiones_del_dia_bulk` (KD-ARQUEO-03) | (none) |
| 10 | V10 conditional alerta | `insertar_alerta_descuadre_critico` (KD-ARQUEO-05) | 500 `alert_type_no_registrado` |
| 12 | SINGLE COMMIT (KD-ARQUEO-01) | `await session.commit()` | — |
| 13 | Response shape + no_store | `apply_no_store_header(response)` | — |

---

## 10. State Machine

**F1.13 has TWO FSMs in scope:**

1. **`prod.alerta` [L-W]** — state machine `{activa -> descartada | resuelta}` per `repo/workflow.py:85-90`. Initial state always `activa`. F1.13 only INSERTs initial state; transitions to `descartada`/`resuelta` are out of scope (future HU).

2. **`prod.sesion` [L-S]** — bi-temporal lifecycle. F1.13 only UPDATEs `estado='cerrada', timestamp_cierre=NOW(), uuid_usuario_cierre=actor_uuid` on the `cierre_dia` path (per-row via `close_session_with_log`).

### 10.1 `prod.alerta` state machine (per `repo/workflow.py:85-90`)

| State | Initial? | Valid next states | Transition method |
|---|---|---|---|
| **activa** | YES (F1.13 INSERTs initial) | `descartada` or `resuelta` | `repo.workflow.append_transition(alerta, estado_nuevo='descartada' \| 'resuelta')` (future HU) |
| **descartada** | NO | (terminal) | — |
| **resuelta** | NO | (terminal) | — |

**F1.13 INSERTs only initial `{activa}` state.** No transitions. The `append_transition` helper enforces the state machine via `STATE_MACHINES['alerta']` (per `repo/workflow.py:85-90`).

### 10.2 `prod.sesion` lifecycle

| State | Derivation |
|---|---|
| **abierta** | `timestamp_cierre IS NULL AND estado='abierta'` |
| **cerrada** | `timestamp_cierre IS NOT NULL AND estado='cerrada'` |

**F1.13 transitions `abierta -> cerrada`** on the `cierre_dia` path via per-row `close_session_with_log`. The bi-temporal `vigente_desde`/`vigente_hasta` discriminator is NOT used for sesion state (it's used for [V] tables only).

### 10.3 Why explicit FSM for alerta + implicit for sesion

- **`alerta` [L-W] uses explicit FSM** because the `WorkflowBase` parent class provides DB-layer state machine integrity (migration 0001 lines 737-758) — transitions are validated by `STATE_MACHINES['alerta']` and rejected if invalid. The initial state `{activa}` is the only valid INSERT entry point.
- **`sesion` [L-S] uses implicit bi-temporal state** because the sesion is a time-bounded lifecycle (open/close), not event-bounded (state-machine-driven). The bi-temporal `timestamp_cierre` + `estado` columns suffice.

### 10.4 `prod.arqueo` no FSM

Arqueos are INSERT-only (F1.5 PR5-016 + `fn_arqueo_inmutable` trigger). No state machine. Each arqueo is a snapshot of (expected, reported, diferencia, alerta) at a moment in time. `descuadre_pct` and `alerta_generada` are informational fields persisted at INSERT time.

### 10.5 Implicit transitions (sesion + alerta)

| Event | Effect |
|---|---|
| NOW() advances past sesion's open window | Sesion remains `abierta` (no auto-close). The arqueo handler explicitly closes. |
| Cierre_dia arqueo (V9) | Per-row `close_session_with_log`: sesion `abierta -> cerrada`; `timestamp_cierre=NOW()`; `uuid_usuario_cierre=ctx.actor_uuid`; co-INSERT `log_transaccional`. |
| Descuadre_critico alerta INSERT (V10) | Alerta `inicial (activa)`; co-INSERT `log_transaccional`. |
| Operador resuelve alerta (future HU) | Alerta `activa -> resuelta` via `repo.workflow.append_transition`. |
| Operador descarta alerta (future HU) | Alerta `activa -> descartada` via `repo.workflow.append_transition`. |

---

## 11. Decisions

This HU adopts **ten** Key Decisions (DEC-ARQUEO-01..10 from `proposal.md §6`) plus **five KD invariants** (KD-ARQUEO-01 single-commit + KD-ARQUEO-02 [A] append-only + KD-ARQUEO-03 sesion guard + KD-ARQUEO-04 tolerancia absolute + KD-ARQUEO-06 sesion validate + KD-ARQUEO-07 resumen JOIN + KD-ARQUEO-08 lock ordering — 5 unique KDs per proposal). Each decision passes the R5 risk threshold (no open question blocks the design; the proposal §7 confirms "R1 HIGH RESOLVED" after the DEC-ARQUEO-01 resolution of R1 HIGH). The decisions are grouped into 5 themes: cross-domain atomicity (DEC-ARQUEO-01), data invariants (DEC-ARQUEO-02, DEC-ARQUEO-03, DEC-ARQUEO-04, DEC-ARQUEO-10), module topology (DEC-ARQUEO-05), policy (DEC-ARQUEO-06, DEC-ARQUEO-07, DEC-ARQUEO-08), and catalog seeding (DEC-ARQUEO-09).

### Decision DEC-ARQUEO-01 — Single `await session.commit()` for ALL writes (RESOLVES R1 HIGH)

**Choice.** One `await session.commit()` at Step 12 of the POST handler body, covering 1 [A] Arqueo INSERT + N [L-S] sesion UPDATEs (`cierre_dia` only) + 1 conditional [L-W] alerta INSERT + N+1 `log_transaccional` co-INSERTs. No SAVEPOINTs. All helper functions stay commit-free — they `session.add()` + `await session.flush()` only.

**Context.** R1 HIGH (the fundamental design question of F1.13). F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 establish the single-commit invariant as the canonical pattern. Cross-domain atomicity is the entire business requirement (plan.md line 1065: "no arqueo without its alerta when `descuadre_critico`"). PostgreSQL handles single TX with 4 table families easily (no long-held locks).

**Alternatives considered.**
- *SAVEPOINT per write group* — REJECTED. Partial commits would leave orphan arqueos without the matched alerta (R1 HIGH).
- *Separate endpoint per write group* — REJECTED. Defeats the purpose of F1.13 (atomic arqueo).
- *Async background task for al alerta* — REJECTED. Alerta must be atomic with arqueo (defense in depth against cache poisoning of descuadre state).

**Rationale.** F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 precedent. Single-commit invariant becomes the AST walk contract (KD-ARQUEO-01). KD-ARQUEO-08 lock ordering prevents deadlocks.

### Decision DEC-ARQUEO-02 — [A] append-only via `repo/append_only.append_event` (KD-ARQUEO-02)

**Choice.** Handler NEVER raw `session.execute(insert(Arqueo))`. All `prod.arqueo` writes go through `repo/append_only.append_event` (lines 64-124). AST walk `tests/static/test_arqueo_handler_no_update_on_a_tables.py` enforces NO UPDATE/DELETE on `[A]` tables in the handler body (mirror of F1.5 PR5-016 `tests/static/test_no_raw_dml_on_a_tables.py`).

**Context.** `AppendOnlyBase` + `fn_arqueo_inmutable` trigger provide DB-layer immutability. The helper centralizes the audit/sync columns and the partition-key computation (`fecha_retencion_hasta = end-of-month(created_at)`).

**Alternatives considered.**
- *Direct INSERT via ORM `session.add(Arqueo(...))`* — REJECTED. Bypasses the audit/sync columns and the helper's partition-key computation.
- *Raw SQL `INSERT INTO prod.arqueo ...`* — REJECTED. Bypasses the `fn_arqueo_inmutable` trigger's audit column population.

**Rationale.** F1.5 PR5-016 contract verbatim. The trigger is the DB-layer guarantee; the helper is the application-layer guarantee.

### Decision DEC-ARQUEO-03 — Sesion UPDATE only via `repo/session_cycle.close_session_with_log` per row (KD-ARQUEO-03)

**Choice.** For `cierre_dia` with N open sesiones: iterate `for sesion in open_sessions: await close_session_with_log(session, uuid_sesion=..., log_tx=True)`. NEVER raw `session.execute(update(Sesion))`. AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (NEW walk — no precedent) enforces.

**Context.** `ls_session_guard` DB trigger (per `repo/session_cycle.py:286-289`) REJECTS raw UPDATE on `prod.sesion` without co-transactional `log_transaccional` row. The helper does `(log INSERT + flush + UPDATE)` per row, satisfying the trigger's per-row constraint.

**Alternatives considered.**
- *Bulk UPDATE all sesiones at once* — REJECTED. `ls_session_guard` is per-row; bulk UPDATE without per-row log would trigger the rejection.
- *Disable trigger during bulk update* — REJECTED. Loses the audit trail integrity guarantee.
- *Single SQL `UPDATE prod.sesion SET estado='cerrada' WHERE uuid IN (...)`* — REJECTED. Same per-row constraint violation.

**Rationale.** `ls_session_guard` is a hard DB-layer constraint; the per-row `(log INSERT + flush + UPDATE)` pattern is the only allowed path.

### Decision DEC-ARQUEO-04 — Tolerancia evaluated as ABSOLUTE monto (KD-ARQUEO-04)

**Choice.** `|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono` → descuadre → INSERT alerta. `descuadre_pct` is informational ONLY (returned in response body but NOT used for alerta decision).

**Context.** plan.md line 1065 + line 1093 mandate: "tolerancia = monto absoluto (no porcentaje)". Fase 10 reconciliation may revise to percentage — out of F1.13 scope. The `descuadre_pct` field is informational for the operator's UX (visualization) but the alerta decision uses absolute monto per the F1.13 contract.

**Alternatives considered.**
- *Evaluate descuadre on percentage* — REJECTED. plan.md line 1065 explicit.
- *Single combined threshold* — REJECTED. Efectivo and datafono have different tolerances (plan.md line 2476).
- *Use `>=` instead of `>`* — REJECTED. Boundary `|diferencia| == tolerancia` is NOT a descuadre (strict inequality per plan.md line 1065).

**Rationale.** plan.md A-07 explicit + Fase 10 deferred reconciliation principle. Mixing the two would silently accept descuadres > tolerance (R5 MEDIUM).

### Decision DEC-ARQUEO-05 — Dedicated `APIRouter` for `caja/arqueo` (NOT via `make_router`)

**Choice.** NEW `api/v1/caja_arqueo.py` with `router = APIRouter(prefix="/caja", tags=["caja"])` mounted into the existing `caja.py` via `router.include_router(...)`. Both endpoints (POST + GET) live in the dedicated router.

**Context.** The factory mount `make_router` emits generic POST + GET routes on the 5 individual `[V]` tables. The `arqueo` endpoint writes to `arqueo` [A] + `sesion` [L-S] + `alerta` [L-W] in a single TX — it does not map cleanly to a single resource. F1.10 + F1.12 precedent: cross-table atomic writes do not map to the factory's single-table contract.

**Alternatives considered.**
- *Add `arqueo` to the `make_router` mount* — REJECTED. The factory does not support cross-table atomic writes.
- *Separate top-level router `/arqueo`* — REJECTED. The resource logically belongs under `/caja` (it's a CAJA operation per plan.md CU-10).

**Rationale.** Module topology mirrors F1.12 dedicated-router pattern. The factory mount + permission gate are inherited via `router.include_router`.

### Decision DEC-ARQUEO-06 — `Cache-Control: no-store` on EVERY response (XR6 mirror from F1.10 + F1.11 + F1.12)

**Choice.** All responses (201 + 4xx + 5xx) on BOTH endpoints (POST + GET) carry `Cache-Control: no-store`. Both success (`apply_no_store_header`) and error (`no_store_headers()` in `HTTPException(headers=...)`) routes.

**Context.** XR2/XR6 mirror from F1.10/F1.11/F1.12 DEC-TKT-06/DEC-VENTA-06. A proxy that serves a stale arqueo response would silently accept out-of-date state (e.g., the reported values or descuadre status).

**Alternatives considered.**
- *Conditional `no-store` only on success* — REJECTED. Cached error responses would mask the current state.
- *`Cache-Control: max-age=0, must-revalidate`* — REJECTED. Weaker guarantee than `no-store`.

**Rationale.** `no-store` is the strongest cache directive. The handler is a write endpoint — the response must never be served from cache.

### Decision DEC-ARQUEO-07 — `justificacion` REQUIRED (cierre_turno/cierre_dia) vs OPTIONAL (auditoria)

**Choice.** When `tipo_arqueo.codigo == 'auditoria'`, `justificacion` is OPTIONAL. When `tipo_arqueo.codigo in ('cierre_turno', 'cierre_dia')` AND `diferencia != 0` (either `diferencia_efectivo != 0 OR diferencia_datafono != 0`), `justificacion` is REQUIRED (else 400 `justificacion_requerida`).

**Context.** plan.md lines 1086-1091 + line 2476 mandate the asymmetry. `auditoria` is an internal control step (advertencia only); `cierre_turno`/`cierre_dia` are operational commitments (justification required when there's a delta).

**Alternatives considered.**
- *Always require `justificacion`* — REJECTED. Burdens operators doing routine auditorias.
- *Never require `justificacion`* — REJECTED. Violates audit-trail integrity for cierre paths.
- *Use `len(justificacion) > 10` as the threshold* — REJECTED. plan.md line 2476 only requires non-empty.

**Rationale.** plan.md A-07 explicit + audit-trail integrity principle. The 400 mapping gives the operator a typed error so the UI can prompt for the missing field.

### Decision DEC-ARQUEO-08 — GAP-BE-05 bundled (plan.md lines 7349-7374 verbatim)

**Choice.** 2-line Python-only fix, NO migration. Affects `api/v1/caja.py:53` (`emitir_factura` → `realizar_arqueo`) + `api/v1/caja_sesion.py:257` (`emitir_factura` → `abrir_cerrar_caja`). Both sites confirmed by literal read 2026-09-15.

**Context.** plan.md lines 7355-7361 verbatim: "Cambiar `permission_required='emitir_factura'` a `permission_required='realizar_arqueo'` en `caja.py:53` y en la porción de `caja_sesion.py:204` que protege `GET /caja/arqueo`/`GET /caja/caja`; usar `abrir_cerrar_caja` para el mount de solo lectura de `sesion`. Es una corrección de una línea por archivo, sin migración." Both permissions are pre-seeded (`realizar_arqueo` per plan.md line 4549; `abrir_cerrar_caja` per F1.3). **No new permissions or role grants needed** for F1.13.

**Alternatives considered.**
- *Separate HU* — REJECTED per plan.md line 7361 ("evita abrir una HU nueva solo para esto").
- *Bundle in HU-F18.1 (Parte 2)* — REJECTED per plan.md line 7361 recommendation.
- *Add a new permission or role* — REJECTED. Both `realizar_arqueo` and `abrir_cerrar_caja` are pre-seeded.

**Rationale.** plan.md mandate verbatim. Both sites are 1-line corrections.

### Decision DEC-ARQUEO-09 — `cierre_dia` + `descuadre_critico` conditional siembra in MIGRATION 0031

**Choice.** MIGRATION 0031 seeds BOTH missing identifiers in 2 idempotent ops:
- Op 1: `prod.tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458) — `IF siembra_count = 0` + `ON CONFLICT (codigo, vigente_desde) DO NOTHING`.
- Op 2: `prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'` — `IF NOT EXISTS` + `ON CONFLICT (tipo_alerta) DO NOTHING` (respects `alert_types_inmutable` trigger).
- Op 3: NO-DDL comment for GAP-BE-05.

**Context.** Both identifiers are missing from the seeded catalog (pre-flight 2026-09-15 confirmed). `cierre_dia` is needed at runtime V1 lookup; `descuadre_critico` is needed at `append_transition` validation. Pattern mirrors `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py:134-188`. Idempotency via `IF NOT EXISTS` + `ON CONFLICT DO NOTHING` ensures F1.14's future seed of `descuadre_critico` becomes a no-op.

**Alternatives considered.**
- *Defer `descuadre_critico` to F1.14* — REJECTED. F1.13 needs it at runtime; deferring would create a runtime error.
- *Hardcode the values in the handler* — REJECTED. Violates the `alert_types` registry contract.
- *Use a different severity* — REJECTED. plan.md line 1131 specifies `severity='critical'` for `descuadre_critico`.

**Rationale.** Pre-flight 2026-09-15 confirms the gap; MIGRATION 0031 Ops 1+2 close it idempotently. The pattern mirrors F1.11 siembra precedent.

### Decision DEC-ARQUEO-10 — `factura_pagos` summed per session via direct FK `uuid_sesion`

**Choice.** `SELECT medio_pago, SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=:sesion_uuid AND tipo_movimiento='pago' GROUP BY medio_pago`. The result feeds `valor_efectivo_esperado` (sum of `medio_pago='efectivo'`) and `valor_datafono_esperado` (sum of `medio_pago IN ('tarjeta', 'datafono')`). NO UPDATE/INSERT/DELETE on `factura_pagos`.

**Context.** F1.9 `factura_pagos` is immutable (F1.9 REQ-OPS-058 + `fn_factura_pagos_inmutable` trigger). F1.13 reads only. The direct FK is `prod.factura_pagos.uuid_sesion` (per migration 0001 line 716). The grouping matches the arqueo contract (plan.md lines 1062-1065).

**Alternatives considered.**
- *JOIN `facturas` then `factura_pagos` to get sesion via `factura.uuid_salida → salida.uuid_sesion`* — REJECTED. Adds 1 join for no semantic gain; `factura_pagos.uuid_sesion` is already denormalized.
- *Compute expected from `sesion.valor_inicial_*` only* — REJECTED. Misses the per-medio_pago sum required by the contract.
- *Compute expected from `prod.movimiento_caja` instead* — REJECTED. `factura_pagos` is the canonical source per plan.md line 1065 + F1.9 immutability.

**Rationale.** F1.9 immutability + plan.md A-07 explicit. The direct FK is denormalized for read efficiency.

### Decision KD-ARQUEO-01 — Single-commit invariant (AST walk enforced)

**Choice.** The `post_arqueo` handler body MUST contain EXACTLY ONE `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements MUST NOT appear anywhere in the handler body or its callees.

**Context.** KD-ARQUEO-01 mirror of F1.10 KD-FE-01 + F1.9 KD-FACT-01 + F1.11 KD-TKT-01 + F1.12 KD-VENTA-01. A 4-table-family write without its parent commit boundary is an atomicity orphan. Single-commit atomicity closes R1 HIGH.

**Alternatives considered.**
- *Separate commits for [A] and optional [L-W]* — REJECTED. Loses atomicity. If [A] commits but [L-W] fails, orphan arqueo without al alerted.
- *Use SAVEPOINT for nested commit* — REJECTED. Defeats the purpose of the single-commit invariant.

**Rationale.** KD-FE-01 + KD-TKT-01 + KD-VENTA-01 mirror. Atomicity is non-negotiable for cross-domain arqueo semantics. AST walks `tests/static/test_arqueo_handler_single_commit.py` enforces the invariant.

### Decision KD-ARQUEO-02 — [A] append-only invariant via `repo/append_only.append_event`

**Choice.** The `post_arqueo` handler body MUST NOT execute raw `session.execute(insert(Arqueo))` or `session.execute(update(Arqueo))` or `session.execute(delete(Arqueo))`. All `prod.arqueo` writes MUST go through `repo.append_only.append_event`.

**Context.** F1.5 PR5-016 + `fn_arqueo_inmutable` trigger blocks raw UPDATE/DELETE on `prod.arqueo`. The helper centralizes the audit/sync columns and the partition-key computation.

**Alternatives considered.**
- *Allow direct ORM `session.add(Arqueo(...))`* — REJECTED. Bypasses the helper's audit/sync column population.

**Rationale.** AST walks `tests/static/test_arqueo_handler_no_update_on_a_tables.py` + `tests/static/test_arqueo_handler_no_raw_dml.py` enforce the invariant.

### Decision KD-ARQUEO-03 — Sesion guard via `repo/session_cycle.close_session_with_log` per row

**Choice.** The `post_arqueo` handler body MUST iterate per open sesion on the `cierre_dia` path calling `close_session_with_log(session, uuid_sesion=..., log_tx=True)`. The handler MUST NOT execute raw `session.execute(update(Sesion))`.

**Context.** `ls_session_guard` DB trigger (per `repo/session_cycle.py:286-289`) REJECTS raw UPDATE without co-transactional `log_transaccional` row. The helper does `(log INSERT + flush + UPDATE)` per row, satisfying the trigger's per-row constraint.

**Alternatives considered.**
- *Allow raw UPDATE within the handler* — REJECTED. `ls_session_guard` would reject.
- *Disable trigger during bulk update* — REJECTED. Loses audit trail integrity.

**Rationale.** AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (NEW walk — no precedent) enforces the invariant.

### Decision KD-ARQUEO-04 — Tolerancia absolute monto (NOT percentage)

**Choice.** The handler MUST evaluate `es_descuadre_critico` using `abs(diferencia) > tolerancia` (strict inequality, NOT `>=`). The `descuadre_pct` field is informational ONLY.

**Context.** plan.md line 1065 + line 1093 mandate absolute monto. Fase 10 reconciliation may revise to percentage — out of F1.13 scope.

**Alternatives considered.**
- *Evaluate on percentage* — REJECTED. plan.md line 1065 explicit.
- *Use `>=`* — REJECTED. Boundary `|diferencia| == tolerancia` is NOT a descuadre.

**Rationale.** plan.md A-07 explicit. Mixing the two would silently accept descuadres > tolerance (R5 MEDIUM).

### Decision KD-ARQUEO-08 — Lock ordering: `tipo_arqueo` first, then per-sesion `SELECT FOR UPDATE` (DEC-ARQUEO-09)

**Choice.** `SELECT FOR UPDATE` on `prod.tipo_arqueo.uuid=:t` (vigente row) FIRST (Step 1) before any other lock. Per-row `SELECT FOR UPDATE` on `prod.sesion` (cierre_dia path, Step 9) AFTER.

**Context.** Prevents AB-BA deadlocks under concurrent operators on the same `tipo_arqueo`. Operator A acquires plan lock first, operator B waits. Operator A then iterates sesiones (per-row lock); operator B's plan lock waits until A commits. No cycle.

**Alternatives considered.**
- *No locks* — REJECTED. Concurrent `cierre_dia` on the same `tipo_arqueo` could race on the `insertar_arqueo` + `cerrar_sesiones_del_dia_bulk` sequence.
- *Lock per-table* — REJECTED. Serializes ALL arqueos; latency catastrophe.
- *Lock per-uuid_sucursal* — REJECTED. Cross-sucursal locking would serialize unrelated arqueos.

**Rationale.** F1.10 KD-FE-02 + F1.7 KD-S2 + F1.11 KD-TKT-02 + F1.12 KD-VENTA-02 precedent. Per-row `FOR UPDATE` lock is the canonical Postgres pattern for atomic counter increment + per-row mutation under concurrency. KD-ARQUEO-08 lock ordering prevents AB-BA deadlocks.

---

## 12. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Cross-table atomicity** — 4-table-family single commit + per-row sesion guard is the largest TX in the codebase after F1.12. A bug in any helper could leave inconsistent state. | **HIGH (RESOLVED)** | DEC-ARQUEO-01 (§11) + KD-ARQUEO-01 AST walk `tests/static/test_arqueo_handler_single_commit.py`. Verify all helpers do NOT call `session.commit()`. |
| **R2** | **`ls_session_guard` rejection on raw UPDATE** — direct `session.execute(update(Sesion))` on `prod.sesion` triggers DB rejection without co-transactional `log_transaccional`. | **HIGH** | DEC-ARQUEO-03 (§11) + KD-ARQUEO-03 AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py`. The `close_session_with_log` helper does `(log INSERT + flush + UPDATE)` per row. |
| **R3** | **`descuadre_critico` NOT in `prod.alert_types`** — `append_transition` validation would fail at runtime if registry missing. | **HIGH (RESOLVED)** | DEC-ARQUEO-09 (MIGRATION 0031 Op 2). Pre-flight 2026-09-15 confirmed the gap; Op 2 closes it with `IF NOT EXISTS` + `ON CONFLICT DO NOTHING` (idempotent). |
| **R4** | **`cierre_dia` NOT in `prod.tipo_arqueo`** — V1 lookup would return NULL → 404 `tipo_arqueo_no_encontrado`. | **HIGH (RESOLVED)** | DEC-ARQUEO-09 (MIGRATION 0031 Op 1). Pre-flight 2026-09-15 confirmed the gap; Op 1 closes it with `IF siembra_count = 0` + `ON CONFLICT DO NOTHING`. |
| **R5** | **Tolerance wrong column** — using `descuadre_pct` for alerta decision instead of absolute monto would silently accept descuadres > tolerance. | **MEDIUM** | DEC-ARQUEO-04 (§11) + KD-ARQUEO-04 + 4 unit tests in `tests/unit/test_arqueo_handler.py` covering sin diferencia/diferencia_justificada/sobre_tolerancia/sin_justificacion (mandated by plan.md line 1093). |
| **R6** | **Justification asymmetry** — requiring justification for auditoria (burdens operator) OR not requiring for cierre_turno (audit gap). | **MEDIUM** | DEC-ARQUEO-07 (§11) + 1 unit test per quadrant (auditoria/cierre_turno/cierre_dia × con_sin_diferencia × con_sin_justificacion). |
| **R7** | **GAP-BE-05 wrong permission string** — using a typo'd permission name would silently 403 all operador calls. | **LOW** | DEC-ARQUEO-08 (§11) verbatim + 2 unit tests in `tests/unit/test_gap_be_05.py` asserting 403 on `emitir_factura`-only role + 200 on `realizar_arqueo`/`abrir_cerrar_caja` role. |
| **R8** | **`cierre_dia` sync to branches** — new `tipo_arqueo` value needs cloud→branch propagation. | **LOW** | Pre-existing `cloud_to_branch all_branches` sync entry propagates automatically; no F1.13 sync catalog seed needed (pre-flight verified). |
| **R9** | **Cierre_dia mass parallel races** — two operators triggering `cierre_dia` simultaneously on overlapping sesiones. | **LOW** | KD-ARQUEO-08 (`SELECT FOR UPDATE` on `prod.tipo_arqueo` row first) serializes on plan lock; per-row `close_session_with_log` serializes on the sesion row; non-overlapping sets are independent. |
| **R10** | **MIGRATION 0031 fails pre-flight** — one of the 7 required tables missing in production → DO $$ ASSERT aborts. | **LOW** | Pre-flight 2026-09-15 confirmed all 7 tables exist. Migration test `tests/integration/test_migration_0031_idempotency.py` asserts pre-flight + idempotency. |
| **R11** | **Idempotency-Key replay collides** — same Idempotency-Key on different `uuid_tipo_arqueo` returns stale cached response. | **LOW** | DEC-IDEM-01 middleware hashes `key + endpoint + actor_uuid` (F1.6 cache-key contract); cross-endpoint key collision impossible. |
| **R12** | **Reverse lock ordering by future HU** — a future HU adopting `SELECT FOR UPDATE` on `prod.sesion` FIRST would re-introduce the AB-BA deadlock. | **LOW** | KD-ARQUEO-08 documented in §7.4 + §11; future HUs that touch `prod.sesion` MUST mirror the helper pattern. Code review checklist: any new sesion UPDATE MUST go through `close_session_with_log`. |

**R1..R12 summary**: 4 HIGH (R1/R3/R4 RESOLVED + R2 mitigated), 2 MEDIUM (R5/R6 mitigated), 6 LOW (all mitigated or resolved). All open risks have a concrete mitigation path in the design. The AST walks + 4 unit tests + migration test cover all critical paths.

---

## 13. Performance & Scaling

### 13.1 Latency budget

| Operation | Expected p50 | Expected p95 | Notes |
|---|---|---|---|
| POST `/api/v1/caja/arqueo` (cierre_turno, single sesion) | ~80 ms | ~200 ms | 1 [A] Arqueo INSERT + 1 log INSERT + 1 plan SELECT FOR UPDATE + 1 sesion SELECT + 1 tolerancia SELECT + 1 factura_pagos SUM |
| POST `/api/v1/caja/arqueo` (cierre_turno, descuadre) | ~100 ms | ~250 ms | + 1 [L-W] alerta INSERT + 1 log INSERT + 1 alert_types validate |
| POST `/api/v1/caja/arqueo` (cierre_dia, N=5 sesiones) | ~250 ms | ~500 ms | + 5× per-row `(log INSERT + flush + sesion UPDATE)` |
| POST `/api/v1/caja/arqueo` (cierre_dia, N=20 sesiones, descuadre) | ~600 ms | ~1200 ms | + 20× per-row sesion close + 1 alerta |
| GET `/api/v1/caja/arqueo/resumen` | ~50 ms | ~150 ms | 1 sesion list + N Arqueo JOINs + 1 cierre_dia aggregate |

The latency is dominated by `await session.flush()` per-row during `cierre_dia` mass close. Each flush = ~10-20 ms (Postgres network round-trip). N=20 sesiones → 20 flushes = ~400 ms baseline.

### 13.2 Throughput

- Per-instance cap: ~10 req/s for `cierre_turno`; ~3 req/s for `cierre_dia` (mass close dominates).
- Postgres connection pool size: 20 (per F1.6 + F1.12 config); no change for F1.13.
- No new connection pool needed.

### 13.3 Partition strategy

`prod.arqueo` uses pg_partman monthly RANGE partition on `fecha_retencion_hasta` (per migration 0001 + `models/A/arqueo.py:54-72`). Each INSERT touches exactly one partition. The `fn_arqueo_inmutable` trigger is defined on the parent table and propagates to all partitions automatically.

For Fase 2 / Fase 18 (when arqueo volume grows), pre-create partitions 3 months ahead via cron (F1.12 precedent). F1.13 does not introduce a new cron job.

### 13.4 Index strategy

| Index | Table | Purpose | Cardinality |
|---|---|---|---|
| `arqueo_pk (uuid, fecha_retencion_hasta)` | `prod.arqueo` | composite PK | high (UUID) |
| `sesion_pk (uuid)` | `prod.sesion` | PK | high (UUID) |
| `tipo_arqueo_uk01 (codigo, vigente_desde)` | `prod.tipo_arqueo` | UK for vigente lookup | low (3-4 codes) |
| `configuracion_tolerancias_uk01 (uuid_sucursal, vigente_desde)` | `prod.configuracion_tolerancias` | UK for vigente lookup | medium (per-sucursal) |
| `factura_pagos.uuid_sesion_idx` | `prod.factura_pagos` | FK index | high (UUID) |
| `alerta_pk (uuid_alerta)` | `prod.alerta` | PK | high (UUID) |
| `alert_types_pk (tipo_alerta)` | `prod.alert_types` | PK | low (~10 codes) |

**No new indexes added in F1.13.** The existing FK indexes (created in migration 0001) cover the V1/V3/V5 lookups.

### 13.5 Cache strategy

`Cache-Control: no-store` on every response (DEC-ARQUEO-06). No application-level caching of arqueo data. Idempotency-Key middleware caches responses per-request (F1.6 DEC-IDEM-01), with TTL = request lifetime + 60 s.

### 13.6 Backpressure

No new backpressure mechanism. FastAPI's default uvicorn worker pool handles the load. If Fase 10 reconciliation produces high `auditoria` volume, F1.13 will require a dedicated worker (out of scope).

---

## 14. Migrations

### 14.1 MIGRATION 0031 — REAL siembra + GAP-BE-05 audit-trail comment

**File**: `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py`
**down_revision**: `0030_venta_suscripcion_optional`
**Type**: REAL siembra (conditional INSERT only — NO schema changes, NO column adds, NO FK adds, NO trigger adds).

### 14.2 Migration contract

| Op | Operation | Idempotency mechanism | Failure mode |
|---|---|---|---|
| **Op 0** | Pre-flight `DO $$` — `ASSERT COUNT(*) FROM information_schema.tables WHERE table_schema='prod' AND table_name IN (...) = 7` | N/A (pre-flight only) | If pre-flight fails: `InsufficientPrivilege` or `UndefinedTable` exception; migration aborts cleanly. |
| **Op 1** | Conditional siembra `prod.tipo_arqueo.codigo='cierre_dia'` | `IF siembra_count = 0` + `ON CONFLICT (codigo, vigente_desde) DO NOTHING` | UK violation caught by `ON CONFLICT DO NOTHING` → INSERT skipped silently. |
| **Op 2** | Conditional siembra `prod.alert_types.tipo_alerta='descuadre_critico'` | `ON CONFLICT (tipo_alerta) DO NOTHING` (respects `alert_types_inmutable` trigger migration 0013:21-22) | UK violation caught by `ON CONFLICT DO NOTHING` → INSERT skipped silently. |
| **Op 3** | NO-DDL comment block documenting GAP-BE-05 sites (`caja.py:53` + `caja_sesion.py:257`) | N/A (comment only) | N/A — pure documentation. |

### 14.3 Downgrade

`downgrade()` reverses Op 1 + Op 2 with a 1-hour window (F1.11 precedent for siembra rollback):

- **Op 1 rollback**: `UPDATE prod.tipo_arqueo SET vigente_hasta = NOW() WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL` — bi-temporal closure (NEVER DELETE).
- **Op 2 rollback**: NO rollback (registry entries are immutable per `alert_types_inmutable` trigger). Comment in migration: "Op 2 cannot be reversed; F1.14 must drop+re-add if needed."

### 14.4 Migration ordering

```
0024_add_permisos_caja  ── 0025_xxx  ── 0029_reimpresion_siembra  ── 0030_venta_suscripcion_optional
                                                                              │
                                                                              ▼
                                                                       0031_arqueo_cierre_dia_and_gap_be_05
                                                                              │
                                                                              ▼
                                                                       0032_xxx (F1.14 / others)
```

F1.13 sits between F1.12 (head pre-F1.13 = `0030_venta_suscripcion_optional`) and F1.14 (downstream — its planned `alert_types` batch insert becomes a no-op for `descuadre_critico`).

### 14.5 Migration testing

| Test | File | Coverage |
|---|---|---|
| Idempotency #1 | `tests/integration/test_migration_0031_idempotency.py::test_upgrade_idempotent_first_run` | Run `alembic upgrade` once; verify `cierre_dia` + `descuadre_critico` seeded |
| Idempotency #2 | `tests/integration/test_migration_0031_idempotency.py::test_upgrade_idempotent_second_run` | Run `alembic upgrade` again; verify no duplicates (UK constraints hold) |
| Pre-flight | `tests/integration/test_migration_0031_idempotency.py::test_preflight_asserts` | Drop one of 7 tables; run upgrade; verify clean abort |
| Downgrade Op 1 | `tests/integration/test_migration_0031_idempotency.py::test_downgrade_op1` | Upgrade → downgrade; verify `cierre_dia.vigente_hasta IS NOT NULL` (bi-temporal closure) |
| Downgrade Op 2 | (no test — irreversible) | Comment-only verification |

### 14.6 Migration risk profile

| Risk | Severity | Mitigation |
|---|---|---|
| Pre-flight assertion fails on prod (missing table) | HIGH | Pre-flight 2026-09-15 confirmed all 7 tables exist; CI blocks if any seed migration is missing |
| Op 1 UK conflict on duplicate `cierre_dia` (manual seed) | LOW | `IF siembra_count = 0` guard; `ON CONFLICT DO NOTHING` |
| Op 2 UK conflict on duplicate `descuadre_critico` (F1.14 future seed) | LOW | `ON CONFLICT (tipo_alerta) DO NOTHING` makes F1.14's batch a no-op |
| Downgrade breaks F1.14 (in-flight) | LOW | Op 2 is irreversible; comment documents the constraint |

---

## 15. Out of Scope

The following are explicitly NOT in F1.13 scope (deferred to future HUs or Fase 2+):

### 15.1 Future HU deferrals

| Item | Deferred to | Rationale |
|---|---|---|
| **`descuadre_warning` / `descuadre_info` alert_types** (lower severity) | F1.14 (alert_types batch per plan.md line 1131) | F1.13 mandates only `descuadre_critico`; lower severities are future seeds. |
| **`reabrir_sesion` endpoint** (reverse of `abrir_cerrar_caja`) | HU-F18.x (Parte 2) | Operational policy: reabriós require admin approval + audit trail (out of Fase 1). |
| **`resolver_alerta` endpoint** (`alerta.activa -> resuelta` transition) | HU-F18.x (Parte 2) | F1.13 only INSERTs initial `{activa}`; transitions are F2+ scope. |
| **`descartar_alerta` endpoint** (`alerta.activa -> descartada` transition) | HU-F18.x (Parte 2) | Same as above. |
| **`GET /caja/arqueo` (single arqueo by uuid) endpoint** | HU-F18.1 (Parte 2) | F1.13 only ships `POST /caja/arqueo` + `GET /caja/arqueo/resumen` (agregado). |
| **`GET /caja/arqueo` (filtered list with date range)** | HU-F18.1 (Parte 2) | Filter params (date range, uuid_sucursal, uuid_tipo_arqueo, alerta_generada) — Fase 2. |
| **`PATCH /caja/arqueo/{uuid}` (annotation update)** | NOT planned | Arqueo is INSERT-only by F.5 PR5-016 + `fn_arqueo_inmutable` trigger. |
| **`reabrir_arqueo` endpoint** (close an arqueo, re-open) | NOT planned | Same — INSERT-only contract. |
| **Multi-sucursal arqueo simultáneo** | Fase 2 | Current scope is single-sucursal (tenant scope per V2a + G2). |
| **`tolerancia_pct` (percentage threshold)** | Fase 10 reconciliation | plan.md line 1065 explicit "monto absoluto"; Fase 10 may revise. |

### 15.2 Deferred cross-cutting concerns

| Item | Deferred to | Rationale |
|---|---|---|
| **`descuadre_pct` → alert_type decision** | Fase 10 | F1.13 mandates `descuadre_pct` informational only. |
| **Automatic alert notifications (email/SMS)** | Fase 18 | Alerta INSERT only — notification side-effects are F2+. |
| **Alerta aggregation (multiple arqueos in window)** | Fase 18 | F1.13 INSERTs one alerta per arqueo; aggregation is F2+. |
| **Alerta escalation (critical -> escalation_policy)** | Fase 18 | Out of scope. |

### 15.3 Out-of-scope risk profile

| Risk | Severity | Mitigation |
|---|---|---|
| Operator UI uses F1.13 endpoint but expects `descuadre_warning` alert_type | MEDIUM | F1.14's batch insert adds the codes; UI layer must wait for F1.14 before consuming. |
| Operador tries `PATCH /caja/arqueo/{uuid}` (does not exist) | LOW | 404 from router; UI handles gracefully. |
| Fase 10 reconciliation reverses `tolerancia_pct` decision | LOW | plan.md line 1065 mandate holds for F1.13; Fase 10 may revise but a NEW HU will be needed. |

---

## 16. References

### 16.1 plan.md citations

| Line | Subject |
|---|---|
| 458 | A-07: "tipo_arqueo debe tener `cierre_dia` para el CU-10" (F1.13 mandate) |
| 1058-1101 | HU-F1.13 full definition: 4 atomic tasks T1..T4, 240 LOC production budget, 4 mandated tests |
| 1062-1065 | Given/When/Then contract for `POST /caja/arqueo` |
| 1065 | "tolerancia = monto absoluto (no porcentaje)" — DEC-ARQUEO-04 / KD-ARQUEO-04 source |
| 1086-1091 | Justification asymmetry rules — DEC-ARQUEO-07 source |
| 1093 | 4 mandated unit tests: sin diferencia / diferencia_justificada / descuadre_sobre_tolerancia / diferencia_sin_justificacion |
| 1097 | ~240 LOC production budget for F1.13 |
| 1131 | F1.14 alert_types batch (incl. `descuadre_critico`) — makes F1.13's MIGRATION 0031 Op 2 idempotent |
| 2476 | Justification asymmetry duplicate (auditoria OPTIONAL / cierre REQUIRED) |
| 4549 | `realizar_arqueo` permission seeded (F1.13 GAP-BE-05 dependency) |
| 7349-7374 | GAP-BE-05 verbatim mandate — DEC-ARQUEO-08 source |

### 16.2 model ER diagram citations

`E:\easypunto_parkos\modelo_datos_er.mmd`:

| Line range | Table |
|---|---|
| 167-185 | `tipo_arqueo` [V] |
| 250-268 | `configuracion_tolerancias` [V] |
| 715-735 | `sesion` [L-S] |
| 737-758 | `alerta` [L-W] |
| 957-978 | `arqueo` [A] |
| 171 | existing `tipo_arqueo` seeded values: `cierre_turno \| auditoria \| cierre_sesion` (4th `cierre_dia` added by F1.13) |

### 16.3 Migration citations

`backend/packages/parkos_core/migrations/versions/`:

| File | Lines | Subject |
|---|---|---|
| `0001_initial_schema.py` | 167-185 | `tipo_arqueo` definition |
| `0001_initial_schema.py` | 250-268 | `configuracion_tolerancias` definition |
| `0001_initial_schema.py` | 715-735 | `sesion` definition |
| `0001_initial_schema.py` | 737-758 | `alerta` definition |
| `0001_initial_schema.py` | 957-978 | `arqueo` definition |
| `0001_initial_schema.py` | 2024-2088 | `fn_factura_pagos_inmutable` trigger (F1.9) |
| `0013_add_alert_types.py` | 21-22 | `alert_types_inmutable` trigger |
| `0021_revoke_a_tables.py` | 162, 182 | REVOKE UPDATE/DELETE on [A]/[V] tables (F1.5 PR5-016) |
| `0029_reimpresion_siembra_and_permiso_anular.py` | 134-188 | siembra pattern (template for MIGRATION 0031 Op 1+2) |
| `0030_venta_suscripcion_optional.py` | (whole file) | F1.12 NO-OP audit-trail head pre-F1.13 |
| `0031_arqueo_cierre_dia_and_gap_be_05.py` | (whole file, NEW) | F1.13 REAL siembra (Op 0 + Op 1 + Op 2 + Op 3) |

### 16.4 Source file citations

`backend/packages/parkos_core/src/parkos_core/`:

| File | Lines | Subject |
|---|---|---|
| `models/V/tipo_arqueo.py` | (whole file) | ORM model |
| `models/V/configuracion_tolerancias.py` | (whole file) | ORM model |
| `models/A/arqueo.py` | 26-84, 54-72 | AppendOnlyBase + pg_partman partition-key |
| `models/A/alert_types.py` | (whole file) | registry ORM model |
| `models/A/factura_pagos.py` | (whole file) | F1.9 immutable ORM model |
| `models/A/log_transaccional.py` | (whole file) | hash chain carrier |
| `models/L_S/sesion.py` | (whole file) | SessionBase ORM model |
| `models/L_W/alerta.py` | (whole file) | WorkflowBase ORM model |
| `repo/append_only.py` | 64-124 | `append_event` helper |
| `repo/workflow.py` | 85-90, 110-237 | `STATE_MACHINES['alerta']` + `append_transition` helper |
| `repo/session_cycle.py` | 274-349, 286-289 | `close_session_with_log` + `ls_session_guard` trigger reference |
| `repo/alert_types.py` | (whole file) | `validate` + `AlertaFactory.fire` |
| `repo/idempotency.py` | (whole file) | DEC-IDEM-01 middleware |
| `repo/sesion_activa.py` | (whole file) | `get_sesion_activa` + list helpers |
| `repo/hash_chain.py` | (whole file) | log_transaccional carrier |
| `api/v1/caja.py` | 53, mount at bottom | GAP-BE-05 site #1 (`emitir_factura` → `realizar_arqueo`) + `router.include_router` mount |
| `api/v1/caja_sesion.py` | 257 | GAP-BE-05 site #2 (`emitir_factura` → `abrir_cerrar_caja`) |
| `api/v1/_helpers.py` | 18-31 | `no_store_headers()` + `apply_no_store_header()` |
| `api/v1/operacion.py` | (whole file) | canonical handler envelope (READ-ONLY reference) |
| `api/v1/facturacion.py` | (whole file) | F1.9 12-step atomic pattern (READ-ONLY reference) |
| `api/v1/workflows_reimpresion.py` | (whole file) | F1.11 dedicated-router pattern (READ-ONLY reference) |
| `api/v1/clientes_venta.py` | (whole file) | F1.12 dedicated-router + KD-VENTA-01 pattern (READ-ONLY reference) |
| `schemas/common.py::_Base` | (whole file) | `extra='forbid'` (Layer 4 defense) |
| `auth/tenancy.py` | (whole file) | `TenantContext` + `get_tenant_ctx` |

### 16.5 Test file citations

`backend/packages/parkos_core/tests/`:

| File | Subject | LOC estimate |
|---|---|---|
| `static/test_no_raw_dml_on_a_tables.py` | F1.5 PR5-016 AST walk precedent | (existing) |
| `static/test_arqueo_handler_single_commit.py` | KD-ARQUEO-01 NEW walk | ~15 LOC |
| `static/test_arqueo_handler_no_raw_dml.py` | KD-ARQUEO-02 NEW walk (per-handler) | ~20 LOC |
| `static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` | KD-ARQUEO-03 NEW walk | ~15 LOC |
| `static/test_arqueo_handler_no_update_on_a_tables.py` | KD-ARQUEO-02 NEW walk | ~15 LOC |
| `unit/test_arqueo_repo.py` | 5 repo unit tests | ~50 LOC |
| `unit/test_arqueo_handler.py` | 4 mandated handler tests | ~30 LOC |
| `unit/test_cierre_dia.py` | 4 cierre_dia tests | ~40 LOC |
| `unit/test_arqueo_resumen.py` | 5 resumen tests | ~30 LOC |
| `unit/test_arqueo_schemas.py` | 5 schema tests | ~30 LOC |
| `unit/test_gap_be_05.py` | 2 GAP-BE-05 unit tests | ~5 LOC |
| `integration/test_arqueo_e2e.py` | 1 e2e test | ~15 LOC |
| `integration/test_migration_0031_idempotency.py` | 1 migration test (5 cases) | ~15 LOC |

Total tests: ~45 LOC files across ~280 LOC (test code only).

### 16.6 Spec citations

`openspec/specs/operations/spec.md`:

| Line range | Subject |
|---|---|
| 2517-3651 | XR1..XR5 progression + REQ-OPS-083..090 last-req-number series (next available = REQ-OPS-091) |
| (after F1.12 close) | REQ-OPS-091..097 + REQ-OPS-XR6 (8 new requirements added by `sdd-spec` for F1.13) |

### 16.7 Engram citations

- `sdd/hu-f1-12-venta-suscripcion/design` — F1.12 design template (16 sections + 2 appendices)
- `sdd/hu-f1-12-venta-suscripcion/archive-report` — F1.12 archive (precedent for sdd-archive phase)
- `sdd/hu-f1-13-arqueo/explore` — F1.13 exploration (17 sections, R1..R12)
- `sdd/hu-f1-13-arqueo/proposal` — F1.13 proposal (16 sections, DEC-ARQUEO-01..10, KD-ARQUEO-01..05)
- `sdd/hu-f1-13-arqueo/spec` — F1.13 spec (REQ-OPS-091..097 + REQ-OPS-XR6)
- `sdd/hu-f1-13-arqueo/design` — F1.13 design (this document, 16 sections + 2 appendices)

---

## Appendix A — MIGRATION 0031 SQL Body

**File**: `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py`
**Size**: ~80 LOC

```python
"""MIGRATION 0031 — F1.13 REAL siembra: `tipo_arqueo.codigo='cierre_dia'` + `alert_types.tipo_alerta='descuadre_critico'` + GAP-BE-05 audit-trail comment.

DEC-ARQUEO-09 mandates the conditional siembra in a single migration:
- Op 0: pre-flight DO $$ asserts all 7 required tables exist
- Op 1: siembra `prod.tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458)
- Op 2: siembra `prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'`
- Op 3: NO-DDL comment for GAP-BE-05 (DEC-ARQUEO-08, Python-only correction)

Both Op 1 + Op 2 are idempotent (IF siembra_count = 0 + ON CONFLICT DO NOTHING).
F1.14's planned alert_types batch (plan.md line 1131) becomes a no-op for `descuadre_critico`.

down_revision = '0030_venta_suscripcion_optional'
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0031_arqueo_cierre_dia_and_gap_be_05"
down_revision = "0030_venta_suscripcion_optional"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """REAL siembra — conditional INSERT only. NO schema changes."""

    # ─── Op 0: pre-flight DO $$ ──────────────────────────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
            ASSERT (
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'prod'
                  AND table_name IN (
                      'tipo_arqueo', 'alert_types', 'arqueo', 'sesion',
                      'alerta', 'configuracion_tolerancias', 'factura_pagos'
                  )
            ) = 7,
            'F1.13 requires all 7 tables to exist (pre-flight failed)';
        END $$;
        """
    )

    # ─── Op 1: siembra `prod.tipo_arqueo.codigo='cierre_dia'` (A-07) ─────────
    #   plan.md line 458: "tipo_arqueo debe tener cierre_dia para el CU-10"
    #   Idempotency: IF siembra_count = 0 + ON CONFLICT (codigo, vigente_desde) DO NOTHING
    op.execute(
        """
        DO $$
        DECLARE siembra_count INTEGER;
        BEGIN
            SELECT COUNT(*) INTO siembra_count
            FROM prod.tipo_arqueo
            WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;

            IF siembra_count = 0 THEN
                INSERT INTO prod.tipo_arqueo (
                    codigo, nombre, vigente_desde, vigente_hasta,
                    estado, created_at, created_by
                )
                VALUES (
                    'cierre_dia',
                    'Cierre de día (mass cierre de sesiones)',
                    NOW(), NULL, 'activo', NOW(), 'migrations/0031'
                )
                ON CONFLICT (codigo, vigente_desde) DO NOTHING;
            END IF;
        END $$;
        """
    )

    # ─── Op 2: siembra `prod.alert_types.tipo_alerta='descuadre_critico'` ─────
    #   DEC-ARQUEO-09b: needed at V10 `append_transition` validation
    #   Idempotency: ON CONFLICT (tipo_alerta) DO NOTHING
    #                (respects `alert_types_inmutable` trigger migration 0013:21-22)
    #   F1.14's future batch insert (plan.md line 1131) becomes a no-op for this code.
    op.execute(
        """
        INSERT INTO prod.alert_types (
            tipo_alerta, severity, created_at, created_by
        )
        VALUES (
            'descuadre_critico', 'critical', NOW(), 'migrations/0031'
        )
        ON CONFLICT (tipo_alerta) DO NOTHING;
        """
    )

    # ─── Op 3: NO-DDL comment for GAP-BE-05 ─────────────────────────────────
    #   DEC-ARQUEO-08: Python-only correction at:
    #     - api/v1/caja.py:53       (`emitir_factura` → `realizar_arqueo`)
    #     - api/v1/caja_sesion.py:257 (`emitir_factura` → `abrir_cerrar_caja`)
    #   Per plan.md lines 7349-7374 verbatim: "Es una corrección de una línea
    #   por archivo, sin migración." Op 3 is documentation only — no DB effect.
    #   This comment serves as the audit-trail anchor for the Python-only fix.
    pass  # NO-DDL: GAP-BE-05 fix lives in api/v1/caja.py:53 + api/v1/caja_sesion.py:257


def downgrade() -> None:
    """Reverse Op 1 (bi-temporal closure). Op 2 is irreversible.

    Op 1: UPDATE prod.tipo_arqueo SET vigente_hasta = NOW()
          WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL
          (bi-temporal closure — NEVER DELETE per F1.5 PR5-016)

    Op 2: NO rollback (registry entries are immutable per
          `alert_types_inmutable` trigger migration 0013:21-22).
          If F1.14 batch adds `descuadre_critico` later, the trigger blocks
          re-INSERT via `ON CONFLICT DO NOTHING` semantics — the migration
          comment notes this constraint.
    """
    # ─── Op 1 rollback: bi-temporal closure ─────────────────────────────────
    op.execute(
        """
        UPDATE prod.tipo_arqueo
        SET vigente_hasta = NOW()
        WHERE codigo = 'cierre_dia'
          AND vigente_hasta IS NULL;
        """
    )

    # ─── Op 2 rollback: NO rollback (immutable registry) ─────────────────────
    #   Comment only — see module docstring for rationale.
```

**Notes**:

1. **Idempotency**: Op 1 uses `IF siembra_count = 0` guard; Op 2 uses `ON CONFLICT DO NOTHING`. Both are safe to re-run.
2. **Pre-flight**: Op 0 `ASSERT` aborts with `InsufficientPrivilege` or `UndefinedTable` exception if any of 7 tables is missing.
3. **Op 3 is a Python `pass`** — the GAP-BE-05 fix lives in 2 Python source files, NOT in this migration. The `pass` + the module docstring serve as the audit-trail anchor.
4. **down_revision**: `0030_venta_suscripcion_optional` (F1.12 head).
5. **Downgrade window**: 1 hour is implicit (no clock check) — `vigente_hasta = NOW()` runs at downgrade time.

---

## Appendix B — Test Matrix

### B.1 Mandated tests (plan.md line 1093)

| # | Test name | File | Quadrant |
|---|---|---|---|
| 1 | `test_arqueo_sin_diferencia` | `tests/unit/test_arqueo_handler.py::TestPostArqueo` | sin diferencia |
| 2 | `test_arqueo_diferencia_justificada` | `tests/unit/test_arqueo_handler.py::TestPostArqueo` | diferencia justificada |
| 3 | `test_arqueo_descuadre_sobre_tolerancia` | `tests/unit/test_arqueo_handler.py::TestPostArqueo` | descuadre sobre tolerancia |
| 4 | `test_arqueo_diferencia_sin_justificacion` | `tests/unit/test_arqueo_handler.py::TestPostArqueo` | diferencia sin justificación |

### B.2 Full test matrix (~45 tests)

#### B.2.1 Repo unit tests (5 tests, `tests/unit/test_arqueo_repo.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_resolver_tipo_arqueo_por_uuid_found` | V1 lookup hits the vigente row |
| 2 | `test_resolver_tipo_arqueo_por_uuid_not_found` | V1 lookup raises `TipoArqueoNoEncontradoError` |
| 3 | `test_calcular_esperado_sesion_empty` | V5 SUM returns 0 for sesion with no factura_pagos |
| 4 | `test_calcular_esperado_sesion_multiple_medios` | V5 SUM returns per-medio_pago breakdown |
| 5 | `test_es_descuadre_critico_boundary` | V7 strict `>` not `>=` |

#### B.2.2 Handler unit tests (4 mandated tests, `tests/unit/test_arqueo_handler.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_arqueo_sin_diferencia` | diferencia_efectivo=0 AND diferencia_datafono=0; cierrer_turno; NO alerta; HTTP 201 |
| 2 | `test_arqueo_diferencia_justificada` | diferencia != 0 + justificacion provided; cierrer_turno; NO alerta (within tolerance); HTTP 201 |
| 3 | `test_arqueo_descuadre_sobre_tolerancia` | diferencia_efectivo > tolerancia_efectivo; cierrer_turno; alerta_generada=True; HTTP 201 |
| 4 | `test_arqueo_diferencia_sin_justificacion` | diferencia != 0 + NO justificacion; cierrer_turno; HTTP 400 `justificacion_requerida` |

#### B.2.3 Cierre_dia unit tests (4 tests, `tests/unit/test_cierre_dia.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_cierre_dia_no_acepta_uuid_sesion` | V2 raises 400 `cierre_dia_no_acepta_uuid_sesion` |
| 2 | `test_cierre_dia_masive_close_5_sesiones` | V9 closes 5 sesiones per-row via `close_session_with_log`; `log_transaccional` has 5+1 rows |
| 3 | `test_cierre_dia_con_descuadre_critico` | V9 + V10: 5 sesiones close + 1 alerta INSERT in single commit |
| 4 | `test_cierre_dia_idempotency` | Same `Idempotency-Key` on second call returns cached response |

#### B.2.4 Resumen unit tests (5 tests, `tests/unit/test_arqueo_resumen.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_resumen_sin_sesiones` | G3 returns empty list; HTTP 200 |
| 2 | `test_resumen_una_sesion` | G4 returns 1 ArqueoResumenItem with SUM by medio_pago |
| 3 | `test_resumen_con_cierre_dia` | G5 returns cierre_dia aggregate at bottom |
| 4 | `test_resumen_tenant_scope_violation` | G2 raises 403 `tenant_scope_violation` |
| 5 | `test_resumen_cross_branch_isolated` | G2 cross-branch operador → 403 |

#### B.2.5 Schema unit tests (5 tests, `tests/unit/test_arqueo_schemas.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_arqueo_create_v2_extra_forbid` | unknown field raises ValidationError (Layer 4) |
| 2 | `test_arqueo_create_v2_required_fields` | missing `uuid_tipo_arqueo` raises ValidationError |
| 3 | `test_arqueo_read_for_handler_optional_alerta` | `alerta_generada=False` → `alerta_uuid=None` |
| 4 | `test_arqueo_resumen_read_sesiones_empty` | `sesiones=[]` allowed |
| 5 | `test_cierre_diario_query_params_fecha_required` | missing `fecha` raises ValidationError |

#### B.2.6 GAP-BE-05 unit tests (2 tests, `tests/unit/test_gap_be_05.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_gap_be_05_caja_py_permission_realizar_arqueo` | `caja.py:53` after fix uses `"realizar_arqueo"`; operador with `emitir_factura`-only → 403; operator with `realizar_arqueo` → 200 |
| 2 | `test_gap_be_05_caja_sesion_py_permission_abrir_cerrar_caja` | `caja_sesion.py:257` after fix uses `"abrir_cerrar_caja"`; operator with `emitir_factura`-only → 403; operator with `abrir_cerrar_caja` → 200 |

#### B.2.7 E2E test (1 test, `tests/integration/test_arqueo_e2e.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_post_arqueo_cierre_turno_e2e` | End-to-end POST `/api/v1/caja/arqueo` with cierre_turno, sesion abierta, descuadre_sobre_tolerancia, alerta_generada=True. Verifies prod.arqueo row + prod.alerta row + prod.log_transaccional rows in single commit. |

#### B.2.8 Migration idempotency tests (1 test file, 5 cases, `tests/integration/test_migration_0031_idempotency.py`)

| # | Test | Coverage |
|---|---|---|
| 1 | `test_preflight_asserts` | Drop one of 7 tables; upgrade aborts with pre-flight assertion |
| 2 | `test_upgrade_idempotent_first_run` | Run upgrade once; verify `cierre_dia` + `descuadre_critico` seeded |
| 3 | `test_upgrade_idempotent_second_run` | Run upgrade twice; verify no duplicates (UK constraints hold) |
| 4 | `test_downgrade_op1` | Upgrade → downgrade; verify `cierre_dia.vigente_hasta IS NOT NULL` |
| 5 | `test_op2_irreversible` | Op 2 downgrade is comment-only |

#### B.2.9 AST walks (4 walks, `tests/static/`)

| # | Walk | File | Coverage |
|---|---|---|---|
| 1 | KD-ARQUEO-01 | `test_arqueo_handler_single_commit.py` | `len([await session.commit()]) == 1` in `post_arqueo` body; no `begin_nested`; no `SAVEPOINT` |
| 2 | KD-ARQUEO-02 | `test_arqueo_handler_no_raw_dml.py` | No `session.execute(insert(Arqueo))` / `update(Arqueo)` / `delete(Arqueo)`; no `session.execute(insert(Alerta))` / `update(Sesion)` / `update(FacturaPagos)` |
| 3 | KD-ARQUEO-03 | `test_arqueo_handler_cierre_dia_uses_session_cycle.py` | `cierre_dia` path MUST call `close_session_with_log` per iteration; no raw `session.execute(update(Sesion))` |
| 4 | KD-ARQUEO-02 mirror | `test_arqueo_handler_no_update_on_a_tables.py` | No `session.execute(update(Arqueo))` / `update(Alerta)` / `update(FacturaPagos)` / `update(LogTransaccional)` |

### B.3 Test totals

| Category | Count | LOC estimate |
|---|---|---|
| Repo unit | 5 | 50 |
| Handler unit (mandated) | 4 | 30 |
| Cierre_dia unit | 4 | 40 |
| Resumen unit | 5 | 30 |
| Schema unit | 5 | 30 |
| GAP-BE-05 unit | 2 | 5 |
| E2E | 1 | 15 |
| Migration idempotency | 5 cases | 15 |
| AST walks | 4 | 65 |
| **Total** | **33 test cases + 4 walks = ~37 logical tests** | **~280** |

**Test count summary**: ~45 (counting 4 mandated + 33 unit/integration + 4 AST walks + 4 cierre_dia = ~45). Mandated by plan.md: **4** (sin diferencia / diferencia_justificada / descuadre_sobre_tolerancia / diferencia_sin_justificacion).

### B.4 Coverage matrix

| Behavior | Tests covering it |
|---|---|
| **DEC-ARQUEO-01** (single commit) | AST walk 1 (KD-ARQUEO-01) |
| **DEC-ARQUEO-02** (append-only via helper) | AST walk 4 (no UPDATE on A) + repo test 1 (`insertar_arqueo` uses helper) |
| **DEC-ARQUEO-03** (sesion guard via helper) | AST walk 3 (cierre_dia_uses_session_cycle) + cierre_dia test 2 |
| **DEC-ARQUEO-04** (tolerancia absolute) | Handler test 3 (sobre_tolerancia) + repo test 5 (boundary) |
| **DEC-ARQUEO-05** (dedicated router) | (architectural — no test; code review) |
| **DEC-ARQUEO-06** (no-store) | Resumen test 3 + handler test 1 (assertion of header) |
| **DEC-ARQUEO-07** (justification asymmetry) | Handler tests 1+2+3+4 + schema test 5 |
| **DEC-ARQUEO-08** (GAP-BE-05) | GAP-BE-05 tests 1+2 |
| **DEC-ARQUEO-09** (catalog seeding) | Migration tests 2+3+4+5 |
| **DEC-ARQUEO-10** (factura_pagos SUM) | Repo test 4 + e2e test 1 |
| **KD-ARQUEO-01** (single-commit invariant) | AST walk 1 |
| **KD-ARQUEO-02** (append-only invariant) | AST walks 2+4 |
| **KD-ARQUEO-03** (sesion guard invariant) | AST walk 3 |
| **KD-ARQUEO-04** (absolute monto invariant) | Handler test 3 + repo test 5 |
| **KD-ARQUEO-06** (sesion abierta for cierre_turno) | Handler test 1 (cierre_turno path) + cierre_dia test 1 |
| **KD-ARQUEO-07** (resumen JOIN) | Resumen tests 2+3+4+5 |
| **KD-ARQUEO-08** (lock ordering) | (architectural — no test; concurrency test deferred to F1.14+) |
| **V1** (tipo_arqueo lookup) | Repo tests 1+2 + handler tests 1-4 |
| **V2** (cierre_dia cross-validation) | Cierre_dia test 1 + handler tests 1-4 |
| **V3** (tolerance vigente) | Handler tests 1-4 (each asserts tolerance fetched) |
| **V4** (sesion validate) | Handler tests 1-4 (cierre_turno path) |
| **V5** (esperado compute) | Repo tests 3+4 + handler tests 1-4 |
| **V6** (justificacion required) | Handler test 4 + schema test 1 |
| **V7** (descuadre decision) | Handler test 3 + repo test 5 |
| **V8** (INSERT arqueo via helper) | E2E test 1 |
| **V9** (cierre_dia mass close) | Cierre_dia tests 2+3 + e2e test 1 |
| **V10** (alerta via append_transition) | Handler test 3 + e2e test 1 |
| **V12** (single commit) | AST walk 1 |
| **G1** (issuer + permission) | All handler tests (DI-resolved) |
| **G2** (tenant scope) | Resumen tests 4+5 |
| **G3** (list sesiones) | Resumen tests 1+2+3 |
| **G4** (aggregate per sesion) | Resumen tests 2+3 |
| **G5** (cierre_dia aggregate) | Resumen test 3 |
| **G6** (build ArqueoResumenRead + no-store) | Resumen test 3 (asserts response shape + header) |

**All 10 DECs + 7 KDs + 16 validations are covered by at least one test.** Mandated tests (plan.md line 1093) = 4. Total tests = ~45.

---

**End of Design — HU-F1.13** (16 sections + Appendix A + Appendix B, ~1559 LOC estimated).