# Delta Spec: hu-f1-13-arqueo

> **Change**: `hu-f1-13-arqueo` · **Phase**: spec (sdd-spec) · **HU**: HU-F1.13 — `POST /api/v1/caja/arqueo` + `GET /api/v1/caja/arqueo/resumen` + GAP-BE-05
> **Date**: 2026-09-15 · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a328957`) · **PR target**: `origin/dev`
> **Canonical spec**: REQ-OPS-001..082 baseline + REQ-OPS-083..090 + REQ-OPS-XR5 (F1.12)
> **This delta**: REQ-OPS-091..097 + REQ-OPS-XR6

---

# Delta Spec — HU-F1.13: Endpoints arqueo (POST + GET resumen) + siembra `tipo_arqueo.cierre_dia` + corrección bundleada GAP-BE-05

> **Change**: `hu-f1-13-arqueo`
> **Target spec**: `openspec/specs/operations/spec.md` (will append 8 new REQs on archive: REQ-OPS-091..097 + REQ-OPS-XR6)
> **Phase**: spec (sdd-spec)
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F1.13 (Fase-1 prerequisites — backend; GAP-BE-05 bundled in-scope per plan.md lines 7349-7374)
> **Inputs**: `openspec/changes/hu-f1-13-arqueo/proposal.md` (~67 KB, 16 sections, DEC-ARQUEO-01..10, KD-ARQUEO-01..05, 12 risks R1..R12, MIGRATION 0031 REAL siembra plan, 6-cluster decomposition T1..T5 + T-GAP-BE-05), `openspec/changes/hu-f1-13-arqueo/exploration.md` (~29 KB, 17 sections, pre-flight 18/20 PASS + 2 known-MISSING closed by 0031 Ops 1+2), `plan.md` lines 1058-1101 (CU-10 source of truth, 240 LOC production, 4 atomic tasks T1..T4, 4 tests mandated at line 1093), `plan.md` lines 7349-7374 (GAP-BE-05 verbatim mandate), `modelo_datos_er.mmd` blocks `tipo_arqueo` [V] line 167-185, `configuracion_tolerancias` [V] line 250-268, `sesion` [L-S] line 715-735, `alerta` [L-W] line 737-758, `arqueo` [A] line 957-978, `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 167-185 (`tipo_arqueo`), 250-268 (`configuracion_tolerancias`), 715-735 (`sesion`), 737-758 (`alerta`), 957-978 (`arqueo`), `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22), `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 head template for siembra pattern, lines 134-188), `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP audit trail head pre-F1.13), `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 53 (GAP-BE-05 site #1 confirmed), `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2 confirmed), `backend/packages/parkos_core/src/parkos_core/models/V/{tipo_arqueo, configuracion_tolerancias}.py`, `backend/packages/parkos_core/src/parkos_core/models/A/{arqueo, alert_types, factura_pagos}.py`, `backend/packages/parkos_core/src/parkos_core/models/L_S/sesion.py`, `backend/packages/parkos_core/src/parkos_core/models/L_W/alerta.py`, `backend/packages/parkos_core/src/parkos_core/repo/{append_only, workflow, session_cycle, sesion_activa, alert_types, idempotency}.py`, `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` (no_store helpers lines 18-31), `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'`), `openspec/specs/operations/spec.md` (last REQ-OPS-NNN vigente: **REQ-OPS-090 + XR5** after the merge of HU-F1.12 in commit `a328957`), `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/specs/operations/spec.md` (canonical Given/When/Then/And format precedent, 8 REQs REQ-OPS-083..090 + XR5).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a328957`) · **PR target**: `origin/dev`.
> **Note on DEC-ARQUEO-09**: sync catalog pre-flight 2026-09-15 confirmed all 5 sync catalog entries pre-exist (`sync_entries_v.py` + `sync_entries_a.py`). MIGRATION 0031 is a REAL siembra (Op 1 + Op 2 conditional) + NO-DDL comment for GAP-BE-05 (Op 3) — no sync seed operation. Idempotent via `IF NOT EXISTS` + `ON CONFLICT DO NOTHING` so F1.14's planned seed of `descuadre_critico` becomes a no-op after F1.13.

---

## Purpose

HU-F1.13 closes the **operador-facing caja-control endpoint pair** on top of the already-shipped `prod.tipo_arqueo` [V] (3 existing values: `cierre_turno | auditoria | cierre_sesion` per `modelo_datos_er.mmd` line 171; 4th `cierre_dia` added by F1.13 siembra), `prod.arqueo` [A] (AppendOnlyBase composite PK `uuid + fecha_retencion_hasta` per `models/A/arqueo.py:26-84`), `prod.sesion` [L-S] (SessionBase + `ls_session_guard` trigger per `repo/session_cycle.py:286-289`), `prod.alerta` [L-W] (WorkflowBase state machine `{activa -> descartada | resuelta}` per `repo/workflow.py:85-90`), `prod.configuracion_tolerancias` [V], `prod.factura_pagos` [A] (F1.9 immutable), and `prod.alert_types` (registry, 9 codes seeded; `descuadre_critico` added by F1.13 siembra). The change exposes one transactional endpoint (`POST /api/v1/caja/arqueo`) that performs a single `await session.commit()` covering 1 [A] Arqueo INSERT + N [L-S] sesion UPDATEs (cierre_dia path only) + 1 [L-W] alerta INSERT (conditional) + N+1 `log_transaccional` co-INSERTs, plus one read endpoint (`GET /api/v1/caja/arqueo/resumen`) that joins `prod.sesion` + `prod.factura_pagos` + `prod.arqueo` to surface a daily cierre_dia aggregate. GAP-BE-05 (DEC-ARQUEO-08) is bundled in-scope per plan.md lines 7349-7374 verbatim mandate: 2-line Python-only permission correction at `api/v1/caja.py:53` (`emitir_factura` → `realizar_arqueo`) and `api/v1/caja_sesion.py:257` (`emitir_factura` → `abrir_cerrar_caja`), NO migration required.

The 8 new REQ-OPS-NNN (REQ-OPS-091..097 + REQ-OPS-XR6) extend the `operational` capability already consolidated in `openspec/specs/operations/spec.md`. REQ-OPS-001..090 + XR1..XR5 remain unchanged.

---

## ADDED Requirements

### REQ-OPS-091 — POST `/api/v1/caja/arqueo` single-commit atomicity (KD-ARQUEO-01 + DEC-ARQUEO-01)

**Source**: HU-F1.13 (KD-ARQUEO-01 + DEC-ARQUEO-01) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler `post_arqueo` in `api/v1/caja_arqueo.py` MUST execute exactly ONE `await session.commit()` at the END of the request body (Step 12 of the 12-step chain), covering all 4 table families in a single TX: (1) one `prod.arqueo` [A] INSERT via `repo/append_only.append_event` (KD-ARQUEO-02), (2) N `prod.sesion` [L-S] UPDATEs when `tipo_arqueo.codigo == 'cierre_dia'` via `repo/session_cycle.close_session_with_log` per row (KD-ARQUEO-03 + `ls_session_guard` trigger), (3) one conditional `prod.alerta` [L-W] INSERT initial via `repo/workflow.append_transition` when `|diferencia_efectivo| > tolerancia_efectivo OR |diferencia_datafono| > tolerancia_datafono` (KD-ARQUEO-04 + KD-ARQUEO-05), (4) N+1 `prod.log_transaccional` [A] co-INSERTs auto-emitted by the helpers. The handler MUST NOT use `session.begin_nested()` or `SAVEPOINT`. All helper functions (`insertar_arqueo`, `cerrar_sesiones_del_dia_bulk`, `insertar_alerta_descuadre_critico`) MUST stay commit-free — they `session.add()` + `await session.flush()` only. On any helper raise, the entire TX MUST roll back (no SAVEPOINT partial commits). The response MUST return `201 Created` with `Cache-Control: no-store`.

**Rationale**: Cross-domain atomicity for the `arqueo + alerta` pair is the entire business requirement — no arqueo without its alerta when `descuadre_critico` is true. A SAVEPOINT strategy would partially commit, leaving orphan arqueos without the matched alerta. The `ls_session_guard` per-row DB trigger mandates log-first ordering for every sesion UPDATE — the per-row `(log INSERT + flush + UPDATE)` pattern in `close_session_with_log` is the only allowed path inside the outer TX. The single-commit invariant becomes the AST walk contract `tests/static/test_arqueo_handler_single_commit.py` (mirror of `tests/static/test_venta_handler_single_commit.py`).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/append_only.py` lines 64-124 (`append_event` commit-free contract); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition` commit-free); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` lines 274-349 (`close_session_with_log` + `ls_session_guard` trigger lines 286-289); F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 (single-commit precedents).

**Scenario 1: Happy path — all writes succeed in 1 commit, all rows visible post-response**
- **Given** an `operador-` issuer with `realizar_arqueo` permission and `ctx.sucursal_uuid=:s`
- **And** a vigente `prod.tipo_arqueo` row with `codigo='cierre_turno'`, `vigente_hasta IS NULL`
- **And** a vigente `prod.sesion` row `:ses` with `uuid_sucursal=:s`, `estado='abierta'`, `timestamp_cierre IS NULL`
- **And** a vigente `prod.configuracion_tolerancias` row with `uuid_sucursal=:s`, `tolerancia_efectivo=100`, `tolerancia_datafono=200`
- **And** an `ArqueoCreateV2` payload with `uuid_tipo_arqueo=<uuid for cierre_turno>`, `uuid_sesion=<:ses>`, `valor_efectivo_reportado=148000`, `valor_datafono_reportado=320000`, `justificacion=null` (sin diferencia)
- **When** the handler reaches Step 12 and calls `await session.commit()` exactly once
- **Then** exactly one `prod.arqueo` row MUST be visible (uuid matches response)
- **And** exactly one `prod.log_transaccional` row MUST be visible (auto-co-inserted by `append_event`)
- **And** `prod.sesion` MUST be UNCHANGED (UPDATE not required for `cierre_turno` without descuadre; Step 9 only runs on `cierre_dia`)
- **And** NO `prod.alerta` row MUST be visible (descuadre_critico did NOT trigger — diferencia == 0)
- **And** the response MUST be `201 Created` with `ArqueoReadForHandler` carrying `alerta_generada=false`, `alerta_uuid=null` + `Cache-Control: no-store`.

**Scenario 2: Mid-flight failure — any helper raise rolls back the entire TX**
- **Given** the same valid payload but Step 9 (cierre_dia path) raises `SesionNoEncontradaError` because the sesion was deleted mid-flight by a concurrent TX
- **When** the handler catches the exception and returns `404 sesion_no_encontrada`
- **Then** `await session.commit()` MUST NOT be called (KD-ARQUEO-01)
- **And** the entire TX MUST be rolled back — ZERO `prod.arqueo`, ZERO `prod.log_transaccional` rows MUST exist after the rollback
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 3: AST walk — handler source contains EXACTLY ONE `await session.commit()` call**
- **Given** the source file `api/v1/caja_arqueo.py` containing `post_arqueo` handler
- **When** `tests/static/test_arqueo_handler_single_commit.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1` (exactly one `await session.commit()` call)
- **And** MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0` (no SAVEPOINT)
- **And** MUST assert NO occurrence of the literal string `"SAVEPOINT"` in the handler body (defense in depth).

---

### REQ-OPS-092 — `cierre_dia` mass sesion UPDATE through `session_cycle` helper only (KD-ARQUEO-03 + DEC-ARQUEO-03)

**Source**: HU-F1.13 (KD-ARQUEO-03 + DEC-ARQUEO-03) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
For `tipo_arqueo.codigo == 'cierre_dia'` with `uuid_sesion=null` and N open sesiones at `ctx.sucursal_uuid`, the handler MUST execute Step 9 by iterating per open sesion and calling `repo.session_cycle.close_session_with_log(session, uuid_sesion=<uuid>, log_tx=True)` for each one. The handler MUST NOT execute raw `session.execute(update(Sesion))` or `session.execute(text("UPDATE prod.sesion ..."))` — the `ls_session_guard` DB trigger (per `repo/session_cycle.py:286-289`) REJECTS direct UPDATE without co-transactional `log_transaccional` row. Each `close_session_with_log` iteration MUST perform `(log_transaccional INSERT + flush + sesion UPDATE estado='cerrada', timestamp_cierre=...)` inside the outer TX. The `ls_session_guard` DB trigger MUST NOT reject any iteration. The AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` MUST PASS (NEW walk — no precedent; mirrors `test_venta_handler_no_raw_dml.py` shape).

**Rationale**: `ls_session_guard` per-row DB trigger mandates log-first ordering for every sesion UPDATE — bulk UPDATE without per-row log would trigger the rejection. The `close_session_with_log` helper is the only allowed path. The new AST walk locks the contract at static-parse time (defense in depth against accidental drift).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` lines 274-349 (`close_session_with_log` + `ls_session_guard` reference lines 286-289); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (trigger definition); `tests/static/test_no_raw_dml_on_ls_tables.py` (F1.5 PR5-016 precedent for [L-S] AST walks).

**Scenario 1: `cierre_dia` + 3 open sesiones — all 3 closed via `close_session_with_log`**
- **Given** a `cierre_dia` `ArqueoCreateV2` payload with `uuid_tipo_arqueo=<uuid for cierre_dia>`, `uuid_sesion=null`
- **And** 3 open `prod.sesion` rows `:ses1`, `:ses2`, `:ses3` at `ctx.sucursal_uuid=:s` with `estado='abierta'`, `timestamp_cierre IS NULL`
- **When** the handler Step 9 invokes `repo_arqueo.cerrar_sesiones_del_dia_bulk(session, target_sucursal=:s, fecha=<today>)`
- **Then** the helper MUST iterate per open sesion and call `close_session_with_log(session, uuid_sesion=<each>, log_tx=True)` exactly 3 times
- **And** each iteration MUST emit one `prod.log_transaccional` row + one `prod.sesion` UPDATE inside the outer TX
- **And** the final state MUST be `prod.sesion[ses1].estado='cerrada'`, `prod.sesion[ses2].estado='cerrada'`, `prod.sesion[ses3].estado='cerrada'` with `timestamp_cierre` set to NOW()
- **And** NO `prod.sesion` row MUST remain in `estado='abierta'` at `ctx.sucursal_uuid=:s` for the day after the commit.

**Scenario 2: `cierre_dia` + 2 cerradas + 1 abierta — only the open sesion is closed**
- **Given** 3 `prod.sesion` rows where `:ses1` and `:ses2` already have `estado='cerrada'`, `timestamp_cierre=<yesterday>`, and `:ses3` has `estado='abierta'`, `timestamp_cierre IS NULL`
- **And** a `cierre_dia` payload
- **When** the handler Step 9 invokes `cerrar_sesiones_del_dia_bulk`
- **Then** the helper MUST iterate over the single open sesion `:ses3` only
- **And** MUST call `close_session_with_log(session, uuid_sesion=<:ses3>, log_tx=True)` exactly 1 time (NOT 3)
- **And** `:ses1` and `:ses2` MUST remain UNCHANGED (no UPDATE applied, no log row emitted).

**Scenario 3: AST walk — `post_arqueo` for `cierre_dia` calls `close_session_with_log`, NOT raw UPDATE**
- **Given** the source file `api/v1/caja_arqueo.py` containing `post_arqueo` handler
- **When** `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` runs
- **Then** the AST walk MUST detect at least one call to `close_session_with_log(...)` inside the `if tipo_arqueo.codigo == 'cierre_dia':` branch (KD-ARQUEO-03)
- **And** MUST assert NO occurrence of `update(Sesion)` or `text("UPDATE prod.sesion ...")` or `session.execute(update(Sesion))` anywhere in the handler body
- **And** MUST assert that within the `cierre_dia` branch the literal string `"UPDATE prod.sesion"` does NOT appear.

---

### REQ-OPS-093 — Tolerancia evaluated as ABSOLUTE monto (KD-ARQUEO-04 + DEC-ARQUEO-04)

**Source**: HU-F1.13 (KD-ARQUEO-04 + DEC-ARQUEO-04) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST evaluate `es_descuadre_critico(diferencia_efectivo, diferencia_datafono, tolerancia_efectivo, tolerancia_datafono)` by computing `abs(diferencia_efectivo) > tolerancia_efectivo OR abs(diferencia_datafono) > tolerancia_datafono`. The comparison MUST use the **absolute monto**, NOT a percentage. The `descuadre_pct` field (computed as `((diferencia_efectivo + diferencia_datafono) / (esperado_efectivo + esperado_datafono)) * 100` when esperado > 0, else `None`) MUST be returned in the response body as **informational only** and MUST NOT participate in the alerta decision. plan.md line 1065 mandates: "tolerancia = monto absoluto (no porcentaje)". The Fase 10 reconciliation may revise to percentage — out of F1.13 scope.

**Rationale**: plan.md line 1065 + line 1093 explicit mandate. Fase 10 owns the percentage reconciliation. Mixing the two would silently accept descuadres > tolerance (R5). The `descuadre_pct` field is informational for the operator's UX (visualization) but the alerta decision uses absolute monto per the F1.13 contract.

**Source**: `plan.md` line 1065 (tolerancia = monto absoluto), line 1093 (4 mandated unit tests); `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::es_descuadre_critico` (NEW helper, pure function); `backend/packages/parkos_core/src/parkos_core/schemas/caja.py::ArqueoReadForHandler.descuadre_pct` (informational marker).

**Scenario 1: `|diferencia| < tolerancia` — NO descuadre alerta**
- **Given** a sesion with `valor_efectivo_esperado=100000` and `valor_efectivo_reportado=100050`
- **And** `tolerancia_efectivo=100`, `tolerancia_datafono=200`
- **When** the handler Step 7 invokes `es_descuadre_critico(diferencia_efectivo=50, diferencia_datafono=0, tolerancia_efectivo=100, tolerancia_datafono=200)`
- **Then** the helper MUST compute `abs(50)=50 > 100 → False` AND `abs(0)=0 > 200 → False` → return `False`
- **And** the handler MUST NOT call `insertar_alerta_descuadre_critico` (Step 10 SKIPPED)
- **And** the response MUST include `alerta_generada=false`, `alerta_uuid=null` AND `descuadre_pct=0.05` (informational only).

**Scenario 2: `|diferencia| > tolerancia` — alerta generated**
- **Given** the same sesion but `valor_efectivo_reportado=100150`
- **And** `tolerancia_efectivo=100`
- **When** the handler Step 7 invokes `es_descuadre_critico(diferencia_efectivo=150, diferencia_datafono=0, tolerancia_efectivo=100, tolerancia_datafono=200)`
- **Then** the helper MUST compute `abs(150)=150 > 100 → True` → return `True`
- **And** Step 10 MUST call `insertar_alerta_descuadre_critico` via `append_transition` (REQ-OPS-095)
- **And** the response MUST include `alerta_generada=true`, `alerta_uuid=<uuid>`.

**Scenario 3: `|diferencia| == tolerancia` — boundary, NO alerta**
- **Given** `valor_efectivo_reportado=100100`, `tolerancia_efectivo=100` → `|diferencia_efectivo|=100`
- **When** the handler Step 7 invokes `es_descuadre_critico(diferencia_efectivo=100, diferencia_datafono=0, tolerancia_efectivo=100, tolerancia_datafono=200)`
- **Then** the helper MUST compute `abs(100)=100 > 100 → False` (strict inequality)
- **And** the handler MUST NOT generate alerta (`>` not `>=`)
- **And** `descuadre_pct` MUST appear in response body (informational, not decision-driving).

---

### REQ-OPS-094 — `justificacion` REQUIRED on `cierre_turno`/`cierre_dia` when diferencia != 0 (DEC-ARQUEO-07)

**Source**: HU-F1.13 (DEC-ARQUEO-07) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST validate the request body at Step 6: when `tipo_arqueo.codigo in ('cierre_turno', 'cierre_dia')` AND (`diferencia_efectivo != 0` OR `diferencia_datafono != 0`) AND `payload.justificacion is None` (or empty string), the handler MUST raise `HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store_headers())`. When `tipo_arqueo.codigo == 'auditoria'` with diferencia != 0, the handler MUST accept the request without `justificacion` (advertencia only — not bloqueante per plan.md lines 1086-1091 + line 2476 mandate).

**Rationale**: plan.md line 2476 asymmetry. `auditoria` is an internal control step (advertencia only); `cierre_turno`/`cierre_dia` are operational commitments (justification required when there is a delta). The 400 mapping gives the operator a typed error so the UI can prompt for the missing field.

**Source**: `plan.md` lines 1086-1091 + line 2476 (justification asymmetry mandate); `backend/packages/parkos_core/src/parkos_core/schemas/caja.py::ArqueoCreateV2.justificacion` (`str | None = None`); `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py::post_arqueo` Step 6.

**Scenario 1: `cierre_turno` + diferencia != 0 + justificacion=null → 400 `justificacion_requerida`**
- **Given** a `cierre_turno` `ArqueoCreateV2` with `valor_efectivo_reportado=148050` (esperado=148000, diferencia_efectivo=50, != 0)
- **And** `justificacion=null` (omitted from payload)
- **When** the handler Step 6 validates the body
- **Then** it MUST raise `HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store_headers())`
- **And** the response MUST carry `Cache-Control: no-store`
- **And** NO `prod.arqueo` row MUST be INSERTed (Step 6 short-circuits before Step 8)
- **And** NO `prod.alerta` row MUST be INSERTed.

**Scenario 2: `auditoria` + diferencia != 0 + justificacion=null → ACCEPTED (advertencia)**
- **Given** an `auditoria` `ArqueoCreateV2` with `valor_efectivo_reportado=148050` (diferencia_efectivo=50)
- **And** `justificacion=null`
- **When** the handler Step 6 validates the body
- **Then** it MUST NOT raise (DEC-ARQUEO-07 asymmetry — auditoria is advertencia only)
- **And** the handler MUST proceed to Step 7 (es_descuadre_critico) → Step 8 (INSERT arqueo)
- **And** the response MUST be `201 Created` with `ArqueoReadForHandler` carrying `alerta_generada` per the tolerance check.

**Scenario 3: `cierre_dia` + diferencia != 0 + justificacion=null → 400 `justificacion_requerida`**
- **Given** a `cierre_dia` `ArqueoCreateV2` with the aggregated day having diferencia != 0
- **And** `justificacion=null`
- **When** the handler Step 6 validates the body
- **Then** it MUST raise `HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store_headers())`
- **And** NO `prod.sesion` row MUST be UPDATEd (Step 6 short-circuits before Step 9).

---

### REQ-OPS-095 — `alerta 'descuadre_critico'` INSERTed conditionally via `append_transition` (KD-ARQUEO-05 + DEC-ARQUEO-05)

**Source**: HU-F1.13 (KD-ARQUEO-05 + DEC-ARQUEO-05) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
When Step 7 evaluates `es_descuadre_critico == True`, the handler MUST call `repo_arqueo.insertar_alerta_descuadre_critico(session, actor_uuid=ctx.actor_uuid, uuid_arqueo=<uuid_arqueo>, uuid_sucursal=target_sucursal, diferencia_efectivo=<diff_e>, diferencia_datafono=<diff_d>, payload_json={...})` at Step 10. The helper MUST internally call `repo.workflow.append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', estado_inicial='activa', ...)` — NOT raw `session.execute(insert(Alerta))`. The `append_transition` helper MUST validate `tipo_alerta='descuadre_critico'` against `prod.alert_types` (MIGRATION 0031 Op 2 seeded this entry idempotently). The `alerta_generada=true` + `alerta_uuid=<uuid>` MUST appear in the `201 Created` response body. The AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` MUST NOT detect raw INSERT/UPDATE on `prod.alerta`.

**Rationale**: `WorkflowBase` provides DB-layer state machine integrity (initial state `{activa -> descartada | resuelta}` only). `append_transition` centralizes the audit/sync columns. Raw INSERT bypasses the state machine guard and the audit/sync column computation. MIGRATION 0031 Op 2 seeds `descuadre_critico` into `prod.alert_types` with `ON CONFLICT DO NOTHING` (idempotent — F1.14's planned seed becomes no-op).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition` + `STATE_MACHINES['alerta']` lines 85-90); `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22); `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (NEW, MIGRATION 0031 Op 2 seeds `descuadre_critico`).

**Scenario 1: `|diferencia_efectivo| > tolerancia_efectivo` → alerta INSERTed via `append_transition`**
- **Given** Step 7 evaluated `es_descuadre_critico == True` (REQ-OPS-093 Scenario 2)
- **And** `prod.alert_types` has the row `('descuadre_critico', 'critical')` seeded by MIGRATION 0031 Op 2
- **When** the handler Step 10 invokes `insertar_alerta_descuadre_critico(...)`
- **Then** the helper MUST call `repo.workflow.append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', estado_inicial='activa', severity='critical', uuid_recurso_origen=<uuid_arqueo>, tipo_recurso_origen='arqueo', payload_json={...})`
- **And** exactly one `prod.alerta` row MUST be visible after the commit (uuid matches response `alerta_uuid`)
- **And** the response MUST include `alerta_generada=true` + `alerta_uuid=<uuid>`.

**Scenario 2: `|diferencia| <= tolerancia` → NO alerta INSERTed**
- **Given** Step 7 evaluated `es_descuadre_critico == False` (REQ-OPS-093 Scenario 1)
- **When** the handler Step 10 checks `if es_critico:`
- **Then** the handler MUST NOT call `insertar_alerta_descuadre_critico` (the if-branch is SKIPPED)
- **And** ZERO `prod.alerta` rows MUST exist after the commit
- **And** the response MUST include `alerta_generada=false` + `alerta_uuid=null`.

**Scenario 3: AST walk — no raw INSERT/UPDATE on `prod.alerta` in handler body**
- **Given** the source file `api/v1/caja_arqueo.py` containing `post_arqueo`
- **When** `tests/static/test_arqueo_handler_no_raw_dml.py` runs
- **Then** the AST walk MUST assert NO occurrence of `session.execute(insert(Alerta))` or `session.execute(text("INSERT INTO prod.alerta ..."))` or `update(Alerta)` in the handler body
- **And** MUST assert that `append_transition` (or a helper wrapping it) is the ONLY path that inserts into `prod.alerta`.

---

### REQ-OPS-096 — Sesion MUST be abierta for `cierre_turno` (KD-ARQUEO-06)

**Source**: HU-F1.13 (KD-ARQUEO-06) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When `tipo_arqueo.codigo == 'cierre_turno'` (or `'auditoria'`) AND `payload.uuid_sesion is not None`, the handler MUST validate at Step 4 that the referenced `prod.sesion` row has `estado='abierta'` AND `timestamp_cierre IS NULL`. The handler MUST call `repo_arqueo.validar_sesion_abierta_para_arqueo(session, uuid_sesion=<uuid>, target_sucursal=ctx.sucursal_uuid)` which returns the sesion object when open OR raises `SesionYaCerradaError` when `timestamp_cierre IS NOT NULL`. The handler MUST map `SesionYaCerradaError` to `HTTPException(409, {"error": "sesion_ya_cerrada", "uuid_sesion": str(payload.uuid_sesion)}, headers=no_store_headers())`. For `cierre_dia`, the sesion validation is SKIPPED (the request carries `uuid_sesion=null` per DEC-ARQUEO-03 — the helper iterates ALL open sesiones for the day). The AST walk MUST enforce that `validar_sesion_abierta_para_arqueo` is called BEFORE any INSERT into `prod.arqueo`.

**Rationale**: A sesion that has already been closed (`timestamp_cierre IS NOT NULL`) cannot be closed or audited again — the arqueo would create a duplicate or contradictory record. The 409 mapping gives the operator a typed error pointing at the offending sesion.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::validar_sesion_abierta` (F1.3/F1.5 precedent, reused); `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::validar_sesion_abierta_para_arqueo` (NEW wrapper, raises `SesionYaCerradaError`).

**Scenario 1: `cierre_turno` + sesion abierta → OK**
- **Given** a `cierre_turno` `ArqueoCreateV2` with `uuid_sesion=<:ses>`
- **And** `prod.sesion[:ses]` has `estado='abierta'`, `timestamp_cierre IS NULL`
- **When** the handler Step 4 invokes `validar_sesion_abierta_para_arqueo(session, uuid_sesion=<:ses>, target_sucursal=:s)`
- **Then** the helper MUST return the sesion object (not raise)
- **And** the handler MUST proceed to Step 5 (compute esperado + diferencia).

**Scenario 2: `cierre_turno` + sesion already cerrada → 409 `sesion_ya_cerrada`**
- **Given** `prod.sesion[:ses]` has `estado='cerrada'`, `timestamp_cierre='2026-09-14T18:30:00Z'`
- **And** a `cierre_turno` `ArqueoCreateV2` with `uuid_sesion=<:ses>`
- **When** the handler Step 4 invokes `validar_sesion_abierta_para_arqueo`
- **Then** the helper MUST raise `SesionYaCerradaError(uuid_sesion=<:ses>)`
- **And** the handler MUST translate to `HTTPException(409, {"error": "sesion_ya_cerrada", "uuid_sesion": "<:ses>"}, headers=no_store_headers())`
- **And** NO `prod.arqueo` row MUST be INSERTed (Step 4 short-circuits before Step 8).

**Scenario 3: `auditoria` + sesion abierta → OK (auditoria also requires sesion validate)**
- **Given** an `auditoria` `ArqueoCreateV2` with `uuid_sesion=<:ses>`
- **And** `prod.sesion[:ses]` has `estado='abierta'`
- **When** the handler Step 4 invokes `validar_sesion_abierta_para_arqueo`
- **Then** the helper MUST return the sesion object (auditoria is an internal control — applies to the open sesion too)
- **And** the handler MUST proceed to Step 5.

---

### REQ-OPS-097 — GET `/api/v1/caja/arqueo/resumen` JOIN sesion + `factura_pagos` SUM (KD-ARQUEO-07 + DEC-ARQUEO-10)

**Source**: HU-F1.13 (KD-ARQUEO-07 + DEC-ARQUEO-10) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler `get_arqueo_resumen` in `api/v1/caja_arqueo.py` MUST execute a read query (Step 3 + Step 4) that returns one row per `prod.sesion` of the day at `params.uuid_sucursal` with `timestamp_apertura::date = params.fecha`. For each sesion, the row MUST compute `valor_efectivo_esperado = sesion.valor_inicial_efectivo + COALESCE((SELECT SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=sesion.uuid AND medio_pago='efectivo' AND tipo_movimiento='pago'), 0)` and `valor_datafono_esperado = sesion.valor_inicial_datafono + COALESCE((SELECT SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=sesion.uuid AND medio_pago IN ('tarjeta', 'datafono') AND tipo_movimiento='pago'), 0)`. The query MUST NOT execute any UPDATE/INSERT/DELETE on `prod.factura_pagos` (F1.9 immutability, KD-ARQUEO-08 read-only). If a `cierre_dia` arqueo exists for `(uuid_sucursal, fecha)`, it MUST appear in the `cierre_dia` aggregate field at the bottom of the response. The response MUST be `200 OK` with `Cache-Control: no-store` (DEC-ARQUEO-06).

**Rationale**: F1.9 `prod.factura_pagos` is immutable (F1.9 REQ-OPS-058 + `fn_factura_pagos_inmutable` trigger migration 0001 lines 2024-2088). F1.13 reads only via the direct FK `prod.factura_pagos.uuid_sesion` (migration 0001 line 716). The grouping matches the arqueo contract (plan.md lines 1062-1065).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::listar_sesiones_del_dia`, `repo/arqueo.py::construir_resumen_sesion`, `repo/arqueo.py::obtener_cierre_dia_del_dia` (NEW helpers); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 716 (`factura_pagos.uuid_sesion` FK), lines 2024-2088 (`fn_factura_pagos_inmutable` trigger); F1.9 REQ-OPS-058 (`factura_pagos` immutability precedent).

**Scenario 1: Resumen con 1 sesion + 1 arqueo → 1 item con totales calculados**
- **Given** a GET `?uuid_sucursal=<:s>&fecha=2026-09-15`
- **And** 1 `prod.sesion` row `:ses` at `:s` with `timestamp_apertura::date='2026-09-15'`, `valor_inicial_efectivo=50000`, `valor_inicial_datafono=0`
- **And** 2 `prod.factura_pagos` rows for `:ses`: `(medio_pago='efectivo', valor=30000, tipo_movimiento='pago')` and `(medio_pago='tarjeta', valor=20000, tipo_movimiento='pago')`
- **And** 1 `prod.arqueo` row for `:ses` (cierre_turno or auditoria)
- **When** the handler Step 3 + Step 4 execute the read query
- **Then** the response MUST include exactly 1 `ArqueoResumenItem` for `:ses`
- **And** the item MUST have `valor_efectivo_esperado = 50000 + 30000 = 80000` AND `valor_datafono_esperado = 0 + 20000 = 20000`
- **And** `cierre_dia` MUST be `null` (no cierre_dia arqueo for this date).

**Scenario 2: Resumen con cierre_dia existente → aggregate al fondo**
- **Given** 3 sesiones at `:s` for `fecha='2026-09-15'`
- **And** 1 `cierre_dia` arqueo row with `uuid_sucursal=:s`, `uuid_sesion=null`, `fecha_retencion_hasta IN ('2026-09-15', ...)`
- **When** the handler Step 4 invokes `obtener_cierre_dia_del_dia(session, uuid_sucursal=:s, fecha='2026-09-15')`
- **Then** the response MUST include 3 items in `sesiones[]` AND 1 item in `cierre_dia` (the aggregate arqueo row)
- **And** the `cierre_dia` item MUST have `uuid_sesion=null` (because `cierre_dia` carries `uuid_sesion=null` per DEC-ARQUEO-03).

**Scenario 3: Resumen con día vacío → 200 con `sesiones=[]`, `cierre_dia=null`**
- **Given** a GET `?uuid_sucursal=<:s>&fecha=2026-09-15`
- **And** ZERO `prod.sesion` rows at `:s` for that date AND ZERO `cierre_dia` arqueos
- **When** the handler Step 3 invokes `listar_sesiones_del_dia`
- **Then** the helper MUST return `[]` (empty list, NOT 404)
- **And** the response MUST be `200 OK` with `{"fecha": "2026-09-15", "uuid_sucursal": "<:s>", "sesiones": [], "cierre_dia": null}` + `Cache-Control: no-store`.

---

### REQ-OPS-XR6 — Defense in depth: 5 layers + AST walks (mirror XR1..XR5)

**Source**: HU-F1.13 (KD-ARQUEO-01 + KD-ARQUEO-08 + DEC-ARQUEO-05 + DEC-ARQUEO-06 + DEC-ARQUEO-08) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
F1.13 MUST apply the F1.10 + F1.11 + F1.12 defense-in-depth pattern (5 layers), each independently testable, with failure of any one layer contained by the other four:
- **Layer 1 — KD-3 issuer chain + permission gate**: `_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")` (FastAPI dependency) + permission `realizar_arqueo` (after GAP-BE-05 fix at `api/v1/caja.py:53` — DEC-ARQUEO-08). For `caja_sesion.py:257` permission `abrir_cerrar_caja` (after GAP-BE-05 fix at site #2). Branch operator with `realizar_arqueo` performs arqueo; admin cross-branch.
- **Layer 2 — Tenant scope post-V1**: After resolving `target_sucursal` from `ctx.sucursal_uuid` (V1 in POST) or from `params.uuid_sucursal` (in GET), if `ctx.issuer_prefix == "operador-"` AND `(ctx.sucursal_uuid is None OR target_sucursal != ctx.sucursal_uuid)`, return `403 tenant_scope_violation` with `Cache-Control: no-store`. Admin (`admin-`) bypasses. KD-S2 analog from F1.7.
- **Layer 3 — KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering**: AST walk `tests/static/test_arqueo_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` in the `post_arqueo` body. `SELECT FOR UPDATE` on `prod.tipo_arqueo` (Step 1) precedes all other locks (REQ-OPS-091 Scenario 1, KD-ARQUEO-08 deadlock prevention). AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` enforces `close_session_with_log` usage on the `cierre_dia` path (REQ-OPS-092 Scenario 3). AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` enforces no raw INSERT/UPDATE/DELETE on `[A]`/`[V]` tables outside the `repo/arqueo.py` helpers.
- **Layer 4 — Pydantic `extra='forbid'` + numeric Decimal + UUID required**: `ArqueoCreateV2(_Base)` + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams` inherit `extra='forbid'` from `schemas/common.py::_Base` (blocks client smuggling of `uuid_usuario`, `fecha_retencion_hasta`, `alerta_generada`, `alerta_uuid`, `descuadre_pct`, `created_at`, `created_by` — all server-derived). Numeric `valor_efectivo_reportado`/`valor_datafono_reportado` use `Decimal` with `ge=0`. UUID fields required where mandated (REQ-OPS-096 sesion validate).
- **Layer 5 — Handler 422/409/404/403/400 mapping + `Cache-Control: no-store`**: Every response (201 + 4xx + 5xx) on BOTH endpoints carries `Cache-Control: no-store`. Success: `apply_no_store_header(response)`. Error: `HTTPException(headers=no_store_headers())`. Typed exceptions (`TipoArqueoNoEncontradoError` 404, `SesionNoEncontradaError` 404, `ToleranciaNoConfiguradaError` 404, `SesionYaCerradaError` 409, `CierreDiaNoAceptaSesionError` 400, `JustificacionRequeridaError` 400, `TenantScopeViolationError` 403, `PermissionDeniedError` 403, `IdempotencyKeyRequiredError` 400, `IdempotencyConflictError` 409) map to the typed bodies documented in `schemas/caja.py` §9.3. The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

**Rationale**: Defense in depth against accidental drift in any single layer. The AST walk is the F1.10 XR1 + F1.11 XR4 + F1.12 XR5 mirror for F1.13. The 5-layer pattern is the canonical backend invariant for multi-table atomic writes (F1.9 KD-FACT-01, F1.10 KD-FE-01, F1.11 KD-TKT-01, F1.12 KD-VENTA-01, F1.13 KD-ARQUEO-01).

**Source**: F1.9 REQ-OPS-058 (factura_pagos immutability precedent); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); F1.12 REQ-OPS-XR5 (5-layer defense precedent); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'`); `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 53 (GAP-BE-05 site #1) + `api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2).

**Scenario 1: operador with `realizar_arqueo` + own branch — OK**
- **Given** an operador role granted `realizar_arqueo` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching the operator's branch
- **And** a valid `ArqueoCreateV2` payload (sin diferencia, justificacion optional for auditoria)
- **When** the operador POSTs `/api/v1/caja/arqueo`
- **Then** the request MUST pass Layer 1 (KD-3 issuer chain + permission gate) AND Layer 2 (tenant scope) AND reach the handler body
- **And** MUST return `201 Created` on the happy path with `Cache-Control: no-store`.

**Scenario 2: operador with `emitir_factura` only (pre-GAP-BE-05 behavior) — 403 `permission_denied`**
- **Given** an operador role granted `emitir_factura` permission (NOT `realizar_arqueo`)
- **When** the operador POSTs `/api/v1/caja/arqueo` (after GAP-BE-05 fix applied to `caja.py:53`)
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first)
- **And** NO DB writes MUST occur (handler body unreachable).

**Scenario 3: operador with `realizar_arqueo` + DIFFERENT branch — 403 `tenant_scope_violation`**
- **Given** an operador role granted `realizar_arqueo` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`, but the request's resolved target sucursal is `:s_target != :s_other`)
- **When** the operador POSTs `/api/v1/caja/arqueo`
- **Then** Layer 2 MUST reject with `403 Forbidden` and body `{"error": "tenant_scope_violation"}` and `Cache-Control: no-store`
- **And** NO DB writes MUST occur (handler body unreachable).

**Scenario 4: All responses (201 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `POST /api/v1/caja/arqueo` or `GET /api/v1/caja/arqueo/resumen` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `201 Created`
- **And** MUST be present on `400 idempotency_key_required` / `400 cierre_dia_no_acepta_uuid_sesion` / `400 justificacion_requerida` / `403 tenant_scope_violation` / `403 permission_denied` / `404 tipo_arqueo_no_encontrado` / `404 sesion_no_encontrada` / `404 tolerancia_no_configurada` / `409 sesion_ya_cerrada` / `409 idempotency_conflict` / `422 missing_query_params`
- **And** MUST be present on any uncaught 5xx (defense-in-depth).

**Scenario 5: GAP-BE-05 unit test — `caja_arqueo` endpoint requires `realizar_arqueo` not `emitir_factura`**
- **Given** the source file `api/v1/caja.py` at line 53
- **When** `tests/unit/test_gap_be_05.py::test_caja_arqueo_endpoint_requires_realizar_arqueo_not_emitir_factura` runs
- **Then** the test MUST assert `permission_required="realizar_arqueo"` is the bound permission
- **And** a role granted `emitir_factura` only MUST receive `403 permission_denied` on POST `/api/v1/caja/arqueo`
- **And** a role granted `realizar_arqueo` only MUST receive `201 Created` on the happy path.

**Scenario 6: GAP-BE-05 unit test — `caja_sesion` mount requires `abrir_cerrar_caja` not `emitir_factura`**
- **Given** the source file `api/v1/caja_sesion.py` at line 257
- **When** `tests/unit/test_gap_be_05.py::test_caja_sesion_endpoint_requires_abrir_cerrar_caja_not_emitir_factura` runs
- **Then** the test MUST assert `permission_required="abrir_cerrar_caja"` is the bound permission
- **And** a role granted `emitir_factura` only MUST receive `403 permission_denied` on `GET /api/v1/caja/sesion/...`
- **And** a role granted `abrir_cerrar_caja` only MUST pass through.

---

## Cross-Cutting Requirements

The following XR requirements reaffirm F1.10's XR1..XR3 + F1.11's XR4 + F1.12's XR5 (issuer chain, tenant scope, idempotency, cache-control, AST walks) and the new XR6 specific to F1.13:

- **REQ-OPS-XR1 (mirror F1.9 + F1.10 + F1.11 + F1.12)** — Defense in depth: 5 layers. Layer (a) KD-3 issuer chain `requires_issuer("operador-", "admin-")`; Layer (b) permission check `realizar_arqueo` (post-GAP-BE-05 fix at `caja.py:53` — DEC-ARQUEO-08) and `abrir_cerrar_caja` (post-GAP-BE-05 fix at `caja_sesion.py:257`); Layer (c) tenant scope post-V1 — `operador-` issuer forbidden from cross-branch `target_sucursal != ctx.sucursal_uuid` (KD-S2 analog from F1.7); Layer (d) KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering (REQ-OPS-091 + REQ-OPS-092); Layer (e) handler 422/409/404/403/400 mapping. Each layer independently tested; failure of any one layer MUST be contained by the other 4.

- **REQ-OPS-XR2 (mirror F1.9 + F1.10 + F1.11 + F1.12)** — `Cache-Control: no-store` header on all responses from `POST /api/v1/caja/arqueo` + `GET /api/v1/caja/arqueo/resumen` (201, 400, 403, 404, 409, 422, 5xx).

- **REQ-OPS-XR3 (mirror F1.10 + F1.11 + F1.12)** — KD-ARQUEO-01 single `await session.commit()` invariant per handler body. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements MUST NOT appear. AST walk `tests/static/test_arqueo_handler_single_commit.py` enforces the invariant for `post_arqueo`.

- **REQ-OPS-XR4 (mirror F1.11 + F1.12)** — Insert-only invariant AST walk on `[A]` tables (`prod.arqueo`, `prod.alerta` initial state, `prod.factura_pagos` read-only). NO raw UPDATE/INSERT/DELETE on `[A]` tables outside `repo/append_only.py` + `repo/workflow.py` helpers. AST walk `tests/static/test_arqueo_handler_no_raw_dml.py` + `tests/static/test_arqueo_handler_no_update_on_a_tables.py` enforce the invariant.

- **REQ-OPS-XR5 (mirror F1.12)** — NEW `cierre_dia` AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (KD-ARQUEO-03) — enforces that `post_arqueo` for `cierre_dia` codigo calls `repo.session_cycle.close_session_with_log` (NOT direct `session.execute(update(Sesion))`). No precedent exists; this is a new walk mirror of `test_venta_handler_no_raw_dml.py` shape.

- **REQ-OPS-XR6 (NEW for F1.13)** — F1.13 defense-in-depth 5-layer contract: KD-3 issuer chain + `realizar_arqueo`/`abrir_cerrar_caja` permission gate (Layer 1) + tenant scope post-V1 (Layer 2) + KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering (Layer 3) + Pydantic `extra='forbid'` + Decimal precision + UUID required (Layer 4) + handler 422/409/404/403/400 mapping + `Cache-Control: no-store` on every response (Layer 5). Includes GAP-BE-05 bundled correction (DEC-ARQUEO-08).

---

## Definition of Done (entire HU-F1.13)

- [ ] New module `api/v1/caja_arqueo.py` mounted under `/caja` prefix via `router.include_router(caja_arqueo_router)` in `api/v1/caja.py` (DEC-ARQUEO-05).
- [ ] `POST /api/v1/caja/arqueo` handler with 12-step chain (Steps 1-12) covering all 7 REQ-OPS-091..097 contracts + XR6 Layer 5.
- [ ] `GET /api/v1/caja/arqueo/resumen` handler with 6-step chain covering REQ-OPS-097 contract.
- [ ] New `repo/arqueo.py` (~100 LOC) with helpers `resolver_tipo_arqueo_por_uuid`, `resolver_tolerancia_vigente`, `calcular_esperado_sesion`, `calcular_esperado_cierre_dia`, `listar_sesiones_abiertas_del_dia`, `listar_sesiones_del_dia`, `validar_sesion_abierta_para_arqueo`, `construir_resumen_sesion`, `obtener_cierre_dia_del_dia`, `es_descuadre_critico`, `insertar_arqueo`, `insertar_alerta_descuadre_critico`, `cerrar_sesiones_del_dia_bulk`.
- [ ] Pydantic schemas `ArqueoCreateV2` + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams` + 6 typed error schemas appended to `schemas/caja.py` (§9.1, §9.2, §9.3).
- [ ] MIGRATION 0031 applied: REAL siembra — Op 0 pre-flight DO $$ + Op 1 siembra `prod.tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458) + Op 2 siembra `prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'` + Op 3 NO-DDL comment for GAP-BE-05.
- [ ] GAP-BE-05 bundled: `api/v1/caja.py:53` `emitir_factura` → `realizar_arqueo` + `api/v1/caja_sesion.py:257` `emitir_factura` → `abrir_cerrar_caja` (DEC-ARQUEO-08).
- [ ] All 7 new REQ-OPS-091..097 implemented + verified.
- [ ] REQ-OPS-XR6 5-layer defense + 4 AST walks PASS.
- [ ] ~9 test files + 4 AST walks + 1 GAP-BE-05 unit test + 1 migration test PASS:
  - `tests/unit/test_arqueo_repo.py` (~50 LOC, 5 tests)
  - `tests/unit/test_arqueo_handler.py` (~30 LOC, **4 tests mandated by plan.md line 1093**)
  - `tests/unit/test_cierre_dia.py` (~40 LOC, 2 tests)
  - `tests/unit/test_arqueo_resumen.py` (~30 LOC, 3 tests)
  - `tests/static/test_arqueo_handler_single_commit.py` (~15 LOC, KD-ARQUEO-01 walk)
  - `tests/static/test_arqueo_handler_no_raw_dml.py` (~20 LOC, KD-ARQUEO-02 walk)
  - `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (~15 LOC, KD-ARQUEO-03 NEW walk)
  - `tests/static/test_arqueo_handler_no_update_on_a_tables.py` (~15 LOC, KD-ARQUEO-02 walk)
  - `tests/integration/test_migration_0031_idempotency.py` (~15 LOC, 2 tests)
  - `tests/unit/test_gap_be_05.py` (~5 LOC, 2 GAP-BE-05 tests)
- [ ] `Cache-Control: no-store` verified on 201 / 400 / 403 / 404 / 409 / 422 / 5xx responses.
- [ ] KD-ARQUEO-01 single-commit invariant verified per handler via AST walk.
- [ ] KD-ARQUEO-03 sesion guard verified per handler via AST walk.
- [ ] KD-ARQUEO-08 lock ordering verified (tipo_arqueo row before all other locks) via integration test.
- [ ] Tenant scope post-V1 verified (operador- cross-branch → 403 `tenant_scope_violation`).
- [ ] Tolerancia = absolute monto verified (boundary cases `==` tolerance → no alerta).
- [ ] Justification asymmetry verified (cierre_turno+cierre_dia+diferencia+sin_justificacion → 400; auditoria+diferencia+sin_justificacion → OK).
- [ ] `Idempotency-Key` HTTP header supported (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10 + F1.11 + F1.12).
- [ ] No AI attribution in commits (no `Co-authored-by:`, no AI trailers).

---

## References

- `openspec/changes/hu-f1-13-arqueo/proposal.md` (~67 KB, 16 sections, DEC-ARQUEO-01..10, KD-ARQUEO-01..05, 12 risks R1..R12, MIGRATION 0031 REAL siembra, ~590 LOC cumulative scope)
- `openspec/changes/hu-f1-13-arqueo/exploration.md` (~29 KB, 17 sections, R1..R12 risks, pre-flight 18/20 PASS)
- `plan.md` lines 1058-1101 (HU-F1.13 definition, 4 atomic tasks T1..T4, 4 tests mandated at line 1093, 240 LOC budget)
- `plan.md` lines 7349-7374 (GAP-BE-05 verbatim mandate + bundle recommendation)
- `plan.md` line 458 (A-07 `cierre_dia` siembra)
- `plan.md` line 1065 (tolerancia = monto absoluto)
- `plan.md` lines 1086-1091 + line 2476 (justificacion asymmetry)
- `plan.md` line 4549 (`realizar_arqueo` permission seeded)
- `modelo_datos_er.mmd` line 167-185 (`tipo_arqueo` [V]), line 250-268 (`configuracion_tolerancias` [V]), line 715-735 (`sesion` [L-S]), line 737-758 (`alerta` [L-W]), line 957-978 (`arqueo` [A])
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 167-185 (`tipo_arqueo`), 250-268 (`configuracion_tolerancias`), 715-735 (`sesion`), 737-758 (`alerta`), 957-978 (`arqueo`), 2024-2088 (inmutability triggers)
- `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22)
- `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 head template for siembra pattern, lines 134-188)
- `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP audit-trail head pre-F1.13)
- `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (NEW, MIGRATION 0031 REAL siembra — Op 1 `cierre_dia` + Op 2 `descuadre_critico` + Op 3 NO-DDL GAP-BE-05 anchor)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 53 (GAP-BE-05 site #1 confirmed)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2 confirmed)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py` (NEW, dedicated router, ~180 LOC production)
- `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`)
- `backend/packages/parkos_core/src/parkos_core/models/V/{tipo_arqueo, configuracion_tolerancias}.py`
- `backend/packages/parkos_core/src/parkos_core/models/A/{arqueo, alert_types, factura_pagos}.py`
- `backend/packages/parkos_core/src/parkos_core/models/L_S/sesion.py`
- `backend/packages/parkos_core/src/parkos_core/models/L_W/alerta.py`
- `backend/packages/parkos_core/src/parkos_core/repo/{append_only, workflow, session_cycle, sesion_activa, alert_types, idempotency, hash_chain}.py`
- `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py` (NEW, ~100 LOC, 12 typed helpers)
- `backend/packages/parkos_core/src/parkos_core/schemas/caja.py` (EXTEND, +90 LOC — ArqueoCreateV2 + ArqueoReadForHandler + ArqueoResumenItem + ArqueoResumenRead + CierreDiarioQueryParams + 6 typed error schemas)
- `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` base class)
- `openspec/specs/operations/spec.md` (90 REQs REQ-OPS-001..090 + XR1..XR5 merged post-F1.12 — target for REQ-OPS-091..097 + XR6 merge on archive)
- `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/specs/operations/spec.md` (canonical Given/When/Then/And format precedent; 8 REQs REQ-OPS-083..090 + XR5)

---

**End of delta spec — HU-F1.13.**