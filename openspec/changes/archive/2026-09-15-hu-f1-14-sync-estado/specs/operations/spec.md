# Delta Spec: hu-f1-14-sync-estado

> **Change**: `hu-f1-14-sync-estado` · **Phase**: spec (sdd-spec) · **HU**: HU-F1.14 — `GET /api/v1/sync/estado` + MIGRATION 0032 siembra 11 alert_types de negocio (19 totales)
> **Date**: 2026-09-15 · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `83b5dfa`) · **PR target**: `origin/dev`
> **Canonical spec**: REQ-OPS-001..090 + REQ-OPS-091..097 + REQ-OPS-XR6 baseline (post-F1.13 merge at commit `83b5dfa`)
> **This delta**: REQ-OPS-098..101 (4 new REQs) — XR6 already exists at `operations/spec.md:3951`; F1.14 REFERENCES it but does NOT create a new XR (per orchestrator mandate)

---

# Delta Spec — HU-F1.14: `GET /sync/estado` (KD-3 operador) + MIGRATION 0032 siembra 10 net new alert_types de negocio (19 totales)

> **Change**: `hu-f1-14-sync-estado`
> **Target spec**: `openspec/specs/operations/spec.md` (will append 4 new REQs on archive: REQ-OPS-098..101 — REQ-OPS-XR6 already exists from F1.13 at line 3951)
> **Phase**: spec (sdd-spec)
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F1.14 (Fase-1 prerequisites — backend; Fase-11 unlocking per plan.md lines 1105-1133)
> **Inputs**: `openspec/changes/hu-f1-14-sync-estado/proposal.md` (~770 LOC, 16 sections, DEC-SYNC-01..10, KD-SYNC-01..02, 10 risks R1..R10 — 4 RESOLVED, pre-flight 16/16 PASS), `openspec/changes/hu-f1-14-sync-estado/exploration.md` (17 sections, ~770 LOC, DEC-SYNC-01..10 audit complete, DEC-SYNC-03 resolved Option B), `plan.md` lines 1105-1133 (HU-F1.14 definition, 3 atomic tasks T1..T3, 2 tests mandated at line 1126, 120 LOC budget, severity mapping at line 1131), `plan.md` line 429 (DEC-SUC-14: 19 totales, 8 técnicos + 11 de negocio coexisten), `plan.md` line 459 (A-08 severity JOIN pattern preserved via siembra), `plan.md` lines 2311-2323 (canonical descriptions per alert_type — DEC-SYNC-10), `modelo_datos_er.mmd` blocks `sync_log` [A] lines 1027-1047, `sync_queue` [A] lines 981-1002, `alert_types` [A] lines 1101-1114, `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` lines 169-175 (F1.13 head, `descuadre_critico` ALREADY seeded by Op 2 — `ON CONFLICT DO NOTHING` will make F1.14's re-seed a no-op), `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22, REVOKE/GRANT lines 129-130, idempotent INSERT precedent lines 67-108), `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 conditional siembra pattern lines 134-188), `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` lines 9-49 (docstring listing 7 endpoints — `/estado` NOT in list, no collision), line 95 (router declaration), line 358 (`sync-agent-` issuer guard), `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 86 (F1.13 mount precedent: `router.include_router(caja_arqueo_router)` — DEC-SYNC-02), `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — DEC-SYNC-04), `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory, KD-3 dep), `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx`, KD-S2 F1.7 analog — Layer 2), `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py` lines 30-48 (validate + AlertaFactory), `backend/packages/parkos_core/src/parkos_core/models/A/{sync_log, sync_queue, alert_types}.py`, `backend/packages/parkos_core/src/parkos_core/schemas/sync_infra.py` (EXTEND with 2 new shapes: `SyncEstadoQueryParams` + `SyncEstadoRead`), `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py` lines 39-56 (`CANONICAL_PERMISOS` includes `audit_read` at line 48 — pre-seeded per DEC-SYNC-03.B), `tests/static/check_sync_queue_carveout.py` (REQ-OPS-004 AST walk precedent for KD-SYNC-02), `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 EXISTS from F1.13 — F1.14 references it but does NOT create a new XR), `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/specs/operations/spec.md` (canonical Given/When/Then/And format precedent, 8 REQs REQ-OPS-091..097 + REQ-OPS-XR6, ~485 LOC).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `83b5dfa`, F1.13 closed) · **PR target**: `origin/dev`.
> **Note on DEC-SYNC-05 (net new accounting)**: pre-F1.14 `prod.alert_types` count is **9** (8 técnicos from 0013 + 1 `descuadre_critico` from F1.13 MIGRATION 0031 Op 2 lines 169-175). F1.14's MIGRATION 0032 includes all 11 plan.md line 1131 codes with `ON CONFLICT (tipo_alerta) DO NOTHING`. `descuadre_critico` re-attempt becomes a no-op via the conflict clause. Net new: **10**. Final total: **19** (DEC-SUC-14 + DEC-SYNC-05).
> **Note on DEC-SYNC-03.B (permission gate)**: `audit_read` is pre-seeded at `0002_seed_permisos_canonicos.py:48`. F1.14 adopts Option B (reuse `audit_read` — cross-cutting read-only). No patch to existing migration (Option A rejected — would break downstream PRs that depend on exact 16-row count). No scope creep into MIGRATION 0032 (Option C rejected — mixes table seeds with permissions).

---

## Purpose

HU-F1.14 closes the **read-only operator-facing sync state endpoint** + the **`alert_types` registry completion for Fase 11** on top of the already-shipped `prod.sync_log` [A] (composite PK `uuid + fecha_retencion_hasta`, monthly pg_partman per `models/A/sync_log.py:29-72`), `prod.sync_queue` [A] carved-out (5 estados `pendiente|en_progreso|exitoso|fallido|descartado` per `models/A/sync_queue.py:41-99`), `prod.alert_types` [A] registry (PK `tipo_alerta` TEXT, `alert_types_inmutable` trigger per migration 0013:21-22), `prod.permisos` [V] (audit_read pre-seeded at 0002:48), and `prod.sucursal` [V] (Layer 2 tenant scope). The change exposes one read endpoint (`GET /api/v1/sync/estado`) that performs exactly 2 SELECT queries (one against `prod.sync_log`, one against `prod.sync_queue`), returning a `SyncEstadoRead` snapshot to drive HU-F11.1 `SyncBanner` (polling 30s, verde/amarillo/rojo umbrales from CU-14). MIGRATION 0032 (`0032_seed_alert_types_operativos.py`) is a REAL siembra of 10 NET NEW alert_types (the 11 from plan.md line 1131 minus `descuadre_critico` which is already seeded by F1.13 MIGRATION 0031 Op 2 and becomes a no-op via `ON CONFLICT DO NOTHING`), bringing the total to **19 codes** (8 técnicos + 1 F1.13 + 10 F1.14).

The 4 new REQ-OPS-NNN (REQ-OPS-098..101) extend the `operational` capability already consolidated in `openspec/specs/operations/spec.md`. REQ-OPS-001..097 + REQ-OPS-XR1..XR6 remain unchanged. **No new XR is created**: REQ-OPS-101 explicitly references the existing F1.13 REQ-OPS-XR6 at `operations/spec.md:3951`.

---

## ADDED Requirements

### REQ-OPS-098 — `GET /api/v1/sync/estado` SELECT-only contract (KD-SYNC-01 + KD-SYNC-02)

**Source**: HU-F1.14 (DEC-SYNC-01 + DEC-SYNC-02 + KD-SYNC-01 + KD-SYNC-02) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler `get_sync_estado` in the NEW dedicated router `api/v1/sync_estado.py` (mounted under `/sync` prefix via `router.include_router(sync_estado_router)` in `api/v1/caja.py` per DEC-SYNC-02 — F1.13 mount precedent at `caja.py:86`) MUST be a READ-ONLY endpoint that returns HTTP 200 with body `SyncEstadoRead(uuid_sucursal, ultima_sync_at, lag_seg, pendientes)`. The handler MUST execute exactly **2 SELECT queries**: one against `prod.sync_log` (computing `MAX(timestamp_evento) WHERE uuid_sucursal=X` via `repo_sync_estado.get_ultima_sync_at(session, uuid_sucursal)`) and one against `prod.sync_queue` (computing `count(*) WHERE uuid_sucursal=X AND estado='pendiente'` via `repo_sync_estado.count_pendientes_sync_queue(session, uuid_sucursal)`). The handler MUST NOT execute any `UPDATE`, `INSERT`, or `DELETE` statements on `sync_log` or `sync_queue` (KD-SYNC-01). The handler MUST NOT call `await session.commit()` (GET is naturally idempotent). The handler MUST NOT append any row in `prod.log_operaciones` or any `[A]` audit table. The response MUST include `Cache-Control: no-store` (DEC-SYNC-04).

**Rationale**: HU-F11.1 `SyncBanner` polls every 30 seconds with `operador-` JWT. A read-only path preserves the `[A]` invariant on `sync_log` (append-only via AppendOnlyBase + `fn_sync_log_inmutable` trigger) and the REQ-OPS-004 carve-out on `sync_queue`. KD-SYNC-02 AST walk `tests/static/test_sync_estado_read_only.py` enforces the read-only invariant at static-parse time — defense in depth against accidental drift to a write path. The dedicated router with `requires_issuer("operador-", "admin-")` resolves the issuer-chain conflict on `/sync` prefix (DEC-SYNC-01 — `sync_router.py:358` rejects non-`sync-agent-` issuers, so the new endpoint MUST live in a separate router file to reach operador JWTs).

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` lines 9-49 (docstring listing 7 endpoints — `/estado` NOT in list, no collision), line 95 (`APIRouter(prefix="/sync")`), line 358 (`sync-agent-` issuer guard); `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 86 (F1.13 mount precedent); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`); `backend/packages/parkos_core/src/parkos_core/models/A/{sync_log, sync_queue}.py` (verbatim ORM models); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (`fn_sync_log_inmutable` trigger); F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 (AST walk precedents).

**Scenario 1: Happy path — populated branch returns 200 with exact lag + count**
- **Given** an `operador-` JWT with `audit_read` permission (DEC-SYNC-03.B) and `ctx.sucursal_uuid=:s` matching the request target
- **And** `prod.sync_log` contains 5 rows for `uuid_sucursal=:s` with `timestamp_evento` spanning 60-300 seconds before NOW()
- **And** `prod.sync_queue` contains 12 rows for `uuid_sucursal=:s` with `estado='pendiente'`
- **And** `MAX(timestamp_evento)` over those 5 rows resolves to a single value `t_max`
- **When** the operator invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** the handler MUST execute exactly 2 SELECT queries against `prod.sync_log` and `prod.sync_queue`
- **And** MUST NOT execute any UPDATE, INSERT, or DELETE on either table
- **And** MUST NOT call `await session.commit()`
- **And** the response MUST be `200 OK` with `SyncEstadoRead{uuid_sucursal=:s, ultima_sync_at=t_max, lag_seg=NOW_seconds - t_max_seconds (±1s tolerance), pendientes=12}`
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 2: Empty branch — no sync_log rows returns 200 with null lag, NOT 404**
- **Given** an `operador-` JWT with `audit_read` permission and `ctx.sucursal_uuid=:s`
- **And** `prod.sync_log` contains **ZERO** rows for `uuid_sucursal=:s` (branch has never synced)
- **And** `prod.sync_queue` contains ZERO rows for `uuid_sucursal=:s`
- **When** the operator invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** the handler MUST return `200 OK` (NOT 404 — branch exists, just no sync activity, DEC-SYNC-08)
- **And** the response body MUST be `SyncEstadoRead{uuid_sucursal=:s, ultima_sync_at=null, lag_seg=null, pendientes=0}` (NOT lag_seg=0, NOT lag_seg=infinity)
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 3: Empty sync_queue only — populated sync_log, zero pendientes**
- **Given** an `operador-` JWT with `audit_read` permission and `ctx.sucursal_uuid=:s`
- **And** `prod.sync_log` contains 3 rows for `uuid_sucursal=:s`
- **And** `prod.sync_queue` contains **ZERO** rows for `uuid_sucursal=:s`
- **When** the operator invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** the response MUST be `200 OK` with `lag_seg` computed from `t_max` AND `pendientes=0` (integer, NOT null, NOT negative — DEC-SYNC-09)
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 4: AST walk — handler source contains NO `update`/`delete` on SyncLog/SyncQueue and NO `commit`**
- **Given** the source file `api/v1/sync_estado.py` containing `get_sync_estado` handler
- **When** `tests/static/test_sync_estado_read_only.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert ZERO occurrences of `update(SyncLog)` or `update(SyncQueue)` or `delete(SyncLog)` or `delete(SyncQueue)` or `session.execute(text("UPDATE prod.sync_log"))` or `session.execute(text("DELETE FROM prod.sync_queue"))` in the handler body (KD-SYNC-01 + KD-SYNC-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body (GET is naturally commit-free).

---

### REQ-OPS-099 — MIGRATION 0032 siembra 11 alert_types de negocio (idempotent, 10 net new) (DEC-SYNC-05 + DEC-SYNC-06 + DEC-SYNC-07)

**Source**: HU-F1.14 (DEC-SYNC-05 + DEC-SYNC-06 + DEC-SYNC-07 + DEC-SYNC-10) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
MIGRATION 0032 (`0032_seed_alert_types_operativos.py`, `down_revision='0031_arqueo_cierre_dia_and_gap_be_05'`) MUST apply an idempotent siembra of the 11 business alert_types codes per plan.md line 1131 against `prod.alert_types` ([A] registry, migration 0013 lines 1-169). The seed MUST use `ON CONFLICT (tipo_alerta) DO NOTHING` for idempotency — `alert_types_inmutable` trigger (migration 0013:21-22) MUST remain enabled throughout the INSERT path (it only blocks BEFORE UPDATE OR DELETE, not INSERT — DEC-SYNC-07). The pre-F1.14 state MUST be preserved: 8 técnicos from migration 0013 (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) + 1 from F1.13 MIGRATION 0031 Op 2 (`descuadre_critico`, lines 169-175 of `0031_arqueo_cierre_dia_and_gap_be_05.py`) = 9 pre-existing rows. The F1.14 re-seed of `descuadre_critico` MUST become a no-op via `ON CONFLICT DO NOTHING` (DEC-SYNC-05). Net new rows MUST be **10** (NOT 11). Final total: **19** (8 técnicos + 1 F1.13 + 10 F1.14 — DEC-SUC-14).

Severity mapping MUST follow plan.md line 1131 verbatim, mapped to the DB CHECK constraint values (DEC-SYNC-06): `alta` → `critical` (applied to `descuadre_critico`, `sync_fallida`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`), `media` → `warning` (applied to `capacidad_agotada`, `capacidad_agotada_forzado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`), `baja` → `info` (applied to `cache_desactualizado`). Each row MUST include a `descripcion` field per plan.md lines 2311-2323 (DEC-SYNC-10).

**Rationale**: Fase 11 (HU-F11.2 AlertasPanel) JOINs `alerta.tipo_alerta = alert_types.tipo_alerta` to surface severity (A-08). Without the siembra, the JOIN returns null for these 11 codes and the operator UI shows "—" placeholder. `alert_types_inmutable` is the immutability contract — disabling it for re-seed would violate KD-3 (no migration may bypass DB-layer immutability). The `ON CONFLICT DO NOTHING` clause is atomic (no SELECT-then-INSERT race) and respects the trigger (it operates on INSERT, not UPDATE/DELETE).

**Source**: `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` lines 169-175 (F1.13 head, Op 2 `descuadre_critico` siembra precedent — DEC-ARQUEO-09b); `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` lines 21-22 (`alert_types_inmutable` trigger), lines 67-108 (idempotent INSERT precedent), lines 119 (severity CHECK constraint), lines 129-130 (REVOKE/GRANT); `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` lines 134-188 (conditional siembra pattern); `plan.md` line 429 (DEC-SUC-14: 19 totales), line 459 (A-08 severity JOIN), lines 2311-2323 (canonical descriptions per code); `modelo_datos_er.mmd` lines 1101-1114 (`alert_types` [A]).

**Scenario 1: Upgrade applied on fresh DB after F1.13 head — net 10 rows added, total 19**
- **Given** the DB at migration head `0031_arqueo_cierre_dia_and_gap_be_05` with `prod.alert_types` containing exactly **9** rows (8 técnicos + `descuadre_critico`)
- **When** `alembic upgrade head` applies MIGRATION 0032
- **Then** the pre-flight `DO $$` Op MUST verify `prod.alert_types` exists with PK `tipo_alerta` AND the `alert_types_inmutable` trigger is active AND the `severity` column has CHECK constraint accepting `('info', 'warning', 'critical')`
- **And** the siembra MUST INSERT all 11 codes per plan.md line 1131 (including the `descuadre_critico` re-attempt)
- **And** the `descuadre_critico` re-attempt MUST be silently absorbed by `ON CONFLICT DO NOTHING` (zero error, zero new row)
- **And** exactly **10** net new rows MUST be visible (1+1+1+1+1+1+1+1+1+1 for `sync_fallida`, `capacidad_agotada`, `capacidad_agotada_forzado`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, `cache_desactualizado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`)
- **And** the final total MUST be **19** rows (`SELECT COUNT(*) FROM prod.alert_types` = 19)
- **And** the `alert_types_inmutable` trigger MUST remain ENABLED after the upgrade (the `DISABLE TRIGGER`/`ENABLE TRIGGER` pair only appears in `downgrade()`).

**Scenario 2: Upgrade idempotency — re-running on already-migrated DB is a clean no-op**
- **Given** the DB already at migration head `0032_seed_alert_types_operativos` with `prod.alert_types` containing **19** rows
- **When** `alembic upgrade head` is invoked again (idempotency check)
- **Then** the siembra MUST execute `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` for all 11 codes
- **And** ZERO new rows MUST be added (count remains 19)
- **And** the trigger MUST NOT raise (the conflict path is silent)
- **And** NO error MUST be emitted.

**Scenario 3: Severity exact match per plan.md line 1131**
- **Given** MIGRATION 0032 has just been applied to a fresh DB
- **When** `SELECT tipo_alerta, severity FROM prod.alert_types WHERE tipo_alerta IN (...)` runs against the 11 business codes
- **Then** the mapping MUST be exact per DEC-SYNC-06:
  - `descuadre_critico` → `critical`
  - `sync_fallida` → `critical`
  - `evento_no_procesado` → `critical`
  - `impresora_caida` → `critical`
  - `fe_error_toppoint` → `critical`
  - `numeracion_toppoint_agotada` → `critical`
  - `capacidad_agotada` → `warning`
  - `capacidad_agotada_forzado` → `warning`
  - `arqueo_pendiente_24h` → `warning`
  - `suscripcion_proxima_vencer` → `warning`
  - `cache_desactualizado` → `info`
- **And** the `severity` column MUST satisfy the CHECK constraint for every row (no `alta`/`media`/`baja` neutral-Spanish values).

**Scenario 4: Downgrade removes only the 10 F1.14 net new rows (NOT `descuadre_critico`)**
- **Given** the DB at head `0032_seed_alert_types_operativos` with 19 rows
- **When** `alembic downgrade -1` executes MIGRATION 0032's `downgrade()`
- **Then** the `ALTER TABLE prod.alert_types DISABLE TRIGGER alert_types_inmutable` MUST precede the DELETE (trigger blocks DELETE by default — migration 0013:21-22)
- **And** the DELETE MUST target only the 10 F1.14 net new codes (`sync_fallida`, `capacidad_agotada`, `capacidad_agotada_forzado`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, `cache_desactualizado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`)
- **And** the DELETE MUST NOT touch `descuadre_critico` (owned by F1.13 MIGRATION 0031 Op 2 lines 169-175)
- **And** the DELETE MUST NOT touch any of the 8 técnicos (owned by MIGRATION 0013)
- **And** after the DELETE + `ENABLE TRIGGER`, `prod.alert_types` MUST contain exactly **9** rows (8 técnicos + `descuadre_critico`).
- **And** after `alembic upgrade head` is invoked again, `prod.alert_types` MUST contain **19** rows again (the cycle round-trips cleanly).

---

### REQ-OPS-100 — `lag_seg = null` semantics + `pendientes >= 0` invariant + UI rendering contract (DEC-SYNC-08 + DEC-SYNC-09)

**Source**: HU-F1.14 (DEC-SYNC-08 + DEC-SYNC-09 + DEC-SYNC-04) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given a successful `GET /api/v1/sync/estado` response, the response shape MUST enforce the following invariants:
- `ultima_sync_at: datetime | None` — nullable ISO-8601 naive UTC datetime. `None` semantically means "branch has never synced" (NOT 0, NOT a sentinel date).
- `lag_seg: int | None` — nullable integer. `None` when `ultima_sync_at IS NULL` (DEC-SYNC-08). When non-null, MUST equal `int((NOW() - ultima_sync_at).total_seconds())` (positive integer >= 0).
- `pendientes: int` — non-nullable integer >= 0 (DEC-SYNC-09). `SELECT count(*)` ALWAYS returns 0 for empty result set; the handler MUST NOT return `null`.

The HU-F11.1 `SyncBanner` operator UI MUST render the response per the following contract:
- `lag_seg = null` → "NEVER SYNCED" banner state (NOT "freshly synced", NOT error, NOT 404).
- `lag_seg = 0..30` → VERDE (green, fresh sync).
- `lag_seg = 31..300` → AMARILLO (yellow, degraded).
- `lag_seg > 300` → ROJO (red, stale).
- `pendientes >= 100` → inline alert badge rendered (DEC-SYNC-09 high-pile indicator).

The response body MUST NEVER include `pgcode`, `pgerror`, `pgmessage`, or any PostgreSQL error internals. The response MUST ALWAYS include `Cache-Control: no-store` header (DEC-SYNC-04).

**Rationale**: Returning `lag_seg = 0` for an empty branch would falsely reassure the operator that the sync is fresh — semantically wrong. Returning `None` forces the UI to handle the "never synced" state explicitly via the NEVER SYNCED banner. `count(*)` is by definition `>= 0`; returning `null` would force the client to special-case the empty result, which the SQL aggregate already handles. The pgcode/pgerror redaction is XR6 Layer 5 (defense in depth — prevents leaking schema internals via error responses).

**Source**: `backend/packages/parkos_core/src/parkos_core/schemas/sync_infra.py` (NEW `SyncEstadoRead(_Base)` with `lag_seg: int | None`, `ultima_sync_at: datetime | None`, `pendientes: int`); `backend/packages/parkos_core/src/parkos_core/repo/sync_estado.py` (NEW `calcular_lag_seg(ultima_sync_at, now)` helper returns `None` when `ultima_sync_at IS None`); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` base class); `plan.md` lines 2275-2291 (HU-F11.1 SyncBanner consumer — 30s polling, verde/amarillo/rojo umbrales from CU-14 BR1); `plan.md` lines 2305-2325 (HU-F11.2 AlertasPanel consumer); DEC-FE-06 / DEC-TKT-06 / DEC-VENTA-06 / DEC-ARQUEO-06 (XR6 `Cache-Control: no-store` precedent).

**Scenario 1: `lag_seg = None` renders as NEVER SYNCED banner (NOT verde, NOT 0)**
- **Given** the operator UI receives `SyncEstadoRead{uuid_sucursal=:s, ultima_sync_at=null, lag_seg=null, pendientes=0}`
- **When** the SyncBanner renders the state
- **Then** the banner MUST display "NEVER SYNCED" (or equivalent localized label — DEC-SYNC-08)
- **And** MUST NOT display VERDE (green) state (lag_seg=null ≠ lag_seg=0)
- **And** MUST NOT display an error indicator (the response is 200, not 4xx/5xx).

**Scenario 2: `lag_seg = 120` renders as AMARILLO, `lag_seg = 600` as ROJO, `lag_seg = 5` as VERDE**
- **Given** three successive poll responses: `lag_seg=5`, `lag_seg=120`, `lag_seg=600`
- **When** the SyncBanner renders each state
- **Then** the `lag_seg=5` banner MUST display VERDE (green — within 0-30s threshold)
- **And** the `lag_seg=120` banner MUST display AMARILLO (yellow — within 31-300s threshold)
- **And** the `lag_seg=600` banner MUST display ROJO (red — > 300s threshold).

**Scenario 3: `pendientes = 0` MUST NOT be null; `pendientes >= 100` MUST render badge**
- **Given** `SyncEstadoRead{pendientes=0}` (empty sync_queue) and `SyncEstadoRead{pendientes=247}` (large pile)
- **When** the SyncBanner + AlertasPanel render the state
- **Then** the `pendientes=0` case MUST render with no badge and no error
- **And** the `pendientes=247` case MUST render an inline alert badge (DEC-SYNC-09 high-pile indicator)
- **And** `pendientes` MUST NEVER be `null` in the response body (count(*) invariant — DEC-SYNC-09).

**Scenario 4: Response NEVER includes pgcode/pgerror/pgmessage; ALWAYS includes `Cache-Control: no-store`**
- **Given** any response from `GET /api/v1/sync/estado` (200 or 4xx, success or failure)
- **When** the response is emitted
- **Then** the response body MUST NOT contain the keys `pgcode`, `pgerror`, or `pgmessage` (XR6 Layer 5 redaction)
- **And** the response MUST include the `Cache-Control: no-store` header on every status code (200, 403, 422 — DEC-SYNC-04).

---

### REQ-OPS-101 — XR6 cross-cutting defense in depth (REFERENCE to existing REQ-OPS-XR6)

**Source**: HU-F1.14 (DEC-SYNC-01 + DEC-SYNC-03.B + DEC-SYNC-04 + KD-SYNC-02) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given that REQ-OPS-XR6 already exists at `openspec/specs/operations/spec.md:3951` from F1.13, F1.14's `GET /api/v1/sync/estado` endpoint MUST satisfy all 5 defense-in-depth layers defined in REQ-OPS-XR6, applied as follows:

- **Layer 1 (KD-3 issuer chain + permission gate)** — NEW dedicated router `api/v1/sync_estado.py` declares `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")`. Permission gate is `audit_read` (DEC-SYNC-03.B, pre-seeded per `0002_seed_permisos_canonicos.py:48`). Branch operator with `audit_read` reads sync status; admin cross-branch.
- **Layer 2 (Tenant scope post-V1)** — After resolving `target_sucursal` from `params.uuid_sucursal`, if `ctx.issuer_prefix == "operador-"` AND `(ctx.sucursal_uuid is None OR target_sucursal != ctx.sucursal_uuid)`, return `403 tenant_scope_violation` with `Cache-Control: no-store`. Admin (`admin-`) bypasses. KD-S2 analog from F1.7.
- **Layer 3 (KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk)** — The handler invokes ONLY the 3 typed SELECT helpers from `repo/sync_estado.py` (read-only path). The AST walk `tests/static/test_sync_estado_read_only.py` enforces NO `session.execute(update(SyncLog))`, `session.execute(update(SyncQueue))`, `session.execute(delete(SyncLog))`, `session.execute(delete(SyncQueue))`, and NO `await session.commit()` in the handler body. Mirrors F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6.
- **Layer 4 (Pydantic `extra='forbid'` + UUID required + nullable `lag_seg`)** — `SyncEstadoQueryParams(_Base)` + `SyncEstadoRead(_Base)` inherit `extra='forbid'` from `schemas/common.py::_Base` (blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`). `uuid_sucursal: UUID` is required. `lag_seg: int | None` (nullable, DEC-SYNC-08). `ultima_sync_at: datetime | None` (nullable). `pendientes: int` (non-nullable, DEC-SYNC-09).
- **Layer 5 (Handler 200/422/403 mapping + `Cache-Control: no-store`)** — Every response (200 + 4xx + 5xx) on `GET /api/v1/sync/estado` carries `Cache-Control: no-store`. Typed exceptions map as follows: `UuidSucursalInvalidError` → 422 `uuid_sucursal_invalid` (Pydantic validator, Layer 4); `TenantScopeViolationError` → 403 `tenant_scope_violation` (handler Layer 2); `PermissionDeniedError` → 403 `permission_denied` (`require_permission` Layer 1). The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

F1.14 MUST NOT create a new cross-cutting requirement (XR). REQ-OPS-XR6 is canonical and applies to F1.14 by reference. `openspec/changes/hu-f1-14-sync-estado/design.md` §13 (Cross-Cutting Requirements) MUST reference REQ-OPS-XR6 and the 5 layer mapping above. `openspec/changes/hu-f1-14-sync-estado/tasks.md` §10 (Test Plan) MUST include the `test_sync_estado_read_only.py` AST walk as a Layer 3 verification step.

**Rationale**: XR6 is the canonical defense-in-depth contract for cross-cutting concerns. Creating a new XR (XR7) for F1.14 would duplicate the 5-layer contract and fragment the review surface. By referencing XR6, F1.14 inherits the testable invariants (AST walks, `extra='forbid'`, `Cache-Control: no-store`) without redefining them. Each layer is independently testable; failure of any one layer is contained by the other four (defense in depth principle).

**Source**: `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 canonical from F1.13); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — Layer 5 helper); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base); `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory — Layer 1 dep); `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx` — Layer 2 dep); F1.9 REQ-OPS-058 (factura_pagos immutability); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); F1.12 REQ-OPS-XR5 (5-layer defense precedent); F1.13 REQ-OPS-XR6 (caja-specific 5-layer defense precedent at `operations/spec.md:3951`).

**Scenario 1: operador with `audit_read` + own branch — 200 OK (Layer 1 + Layer 2 PASS)**
- **Given** an operador role granted `audit_read` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching the request's `params.uuid_sucursal`
- **When** the operador invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** Layer 1 MUST pass (KD-3 issuer `operador-` accepted + `audit_read` permission granted)
- **And** Layer 2 MUST pass (own-branch tenant scope)
- **And** Layer 3 MUST execute exactly 2 SELECT queries (KD-SYNC-01)
- **And** Layer 4 MUST validate the Pydantic schema (`uuid_sucursal` is a valid UUID, no extra fields)
- **And** Layer 5 MUST return `200 OK` with `Cache-Control: no-store`.

**Scenario 2: operador with `audit_read` + DIFFERENT branch — 403 `tenant_scope_violation` (Layer 2 short-circuits)**
- **Given** an operador role granted `audit_read` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`, but the request target is `:s_target != :s_other`)
- **When** the operador invokes `GET /api/v1/sync/estado?uuid_sucursal=:s_target`
- **Then** Layer 1 MUST pass (issuer + permission OK)
- **And** Layer 2 MUST reject with `403 Forbidden` and body `{"error": "tenant_scope_violation"}` and `Cache-Control: no-store`
- **And** NO SELECT queries MUST execute against `prod.sync_log` / `prod.sync_queue` (Layer 2 short-circuits before Layer 3).

**Scenario 3: operador with `audit_read` DENIED (no permission grant) — 403 `permission_denied` (Layer 1 short-circuits)**
- **Given** an operador role WITHOUT `audit_read` permission (only `emitir_factura` granted)
- **When** the operador invokes `GET /api/v1/sync/estado?uuid_sucursal=:s`
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first)
- **And** NO DB queries MUST execute (handler body unreachable).

**Scenario 4: All responses (200 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `GET /api/v1/sync/estado` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `200 OK`
- **And** MUST be present on `403 tenant_scope_violation` / `403 permission_denied` / `422 uuid_sucursal_invalid`
- **And** MUST be present on any uncaught 5xx (defense in depth).
- **And** the response body MUST NOT contain `pgcode`, `pgerror`, or `pgmessage` keys.

**Scenario 5: Read-only AST walk — handler source contains ZERO UPDATE/DELETE on SyncLog/SyncQueue and ZERO `commit`**
- **Given** the source file `api/v1/sync_estado.py` containing `get_sync_estado`
- **When** `tests/static/test_sync_estado_read_only.py` runs
- **Then** the AST walk MUST assert ZERO occurrences of `update(SyncLog)` or `update(SyncQueue)` or `delete(SyncLog)` or `delete(SyncQueue)` or `session.execute(text("UPDATE prod.sync_log"))` or `session.execute(text("DELETE FROM prod.sync_queue"))` in the handler body (KD-SYNC-01 + KD-SYNC-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body.

---

## Cross-Cutting Requirements

F1.14 applies the existing F1.10..F1.13 XR1..XR6 defense-in-depth pattern by REFERENCE (no new XR created):

- **REQ-OPS-XR1 (mirror F1.10)** — KD-3 issuer chain `requires_issuer("operador-", "admin-")` on dedicated `sync_estado.py` router (DEC-SYNC-01). NOT in F1.14's main router (`sync_router.py`) to avoid collision with the `sync-agent-` issuer guard at line 358.

- **REQ-OPS-XR2 (mirror F1.10..F1.13)** — `Cache-Control: no-store` header on all responses from `GET /api/v1/sync/estado` (200, 403, 422, 5xx). Helpers from `api/v1/_helpers.py` lines 18-31 reused verbatim.

- **REQ-OPS-XR3 (mirror F1.10..F1.13)** — READ-ONLY invariant: NO `INSERT`/`UPDATE`/`DELETE` on `prod.sync_log` or `prod.sync_queue` from the handler. AST walk `tests/static/test_sync_estado_read_only.py` enforces the invariant for `get_sync_estado`.

- **REQ-OPS-XR4 (mirror F1.11..F1.13)** — Insert-only invariant on `[A]` tables (the read endpoint MUST NOT touch `[A]` tables at all — stronger than F1.11's "insert-only" wording). NO `INSERT`/`UPDATE`/`DELETE` on `sync_log`, `sync_queue`, `alert_types` (other than MIGRATION 0032), or any other `[A]` table outside `repo/sync_estado.py` SELECT helpers.

- **REQ-OPS-XR5 (mirror F1.12..F1.13)** — NEW `KD-SYNC-02` AST walk `tests/static/test_sync_estado_read_only.py` (KD-SYNC-02) — enforces that `get_sync_estado` is READ-ONLY (NO UPDATE/DELETE on `SyncLog`/`SyncQueue`, NO `await session.commit()`). Mirrors `test_arqueo_handler_no_raw_dml.py` shape from F1.13.

- **REQ-OPS-XR6 (REFERENCE — already exists from F1.13 at `operations/spec.md:3951`)** — F1.14's 5-layer defense-in-depth contract: KD-3 issuer chain + `audit_read` permission gate (Layer 1) + tenant scope post-V1 (Layer 2) + KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk (Layer 3) + Pydantic `extra='forbid'` + UUID required + nullable `lag_seg` (Layer 4) + handler 200/422/403 mapping + `Cache-Control: no-store` (Layer 5). F1.14 references REQ-OPS-XR6 by inclusion (5 layers applied verbatim, see REQ-OPS-101) — NO new XR created.

---

## Definition of Done (entire HU-F1.14)

- [ ] NEW dedicated router `api/v1/sync_estado.py` (~80 LOC) mounted under `/sync` prefix via `router.include_router(sync_estado_router)` in `api/v1/caja.py` (DEC-SYNC-01 + DEC-SYNC-02).
- [ ] `GET /api/v1/sync/estado` handler with 4-step chain (Steps 1-4) covering REQ-OPS-098 + REQ-OPS-100 + REQ-OPS-101 contracts.
- [ ] NEW `repo/sync_estado.py` (~30 LOC) with helpers `get_ultima_sync_at`, `calcular_lag_seg`, `count_pendientes_sync_queue` (all SELECT-only).
- [ ] Pydantic schemas `SyncEstadoQueryParams` + `SyncEstadoRead` appended to `schemas/sync_infra.py`.
- [ ] MIGRATION 0032 applied: REAL siembra — Op 0 pre-flight DO $$ + Op 1 siembra 11 alert_types codes (10 net new + idempotent re-attempt of `descuadre_critico`) + Op 2 NO-DDL audit anchor for DEC-SYNC-03.B.
- [ ] All 4 new REQ-OPS-098..101 implemented + verified.
- [ ] REQ-OPS-XR6 5-layer defense + 1 new AST walk PASS (no new XR created).
- [ ] ~5 test files + 1 AST walk + 1 migration test PASS:
  - `tests/unit/test_sync_estado.py` (~30 LOC, **2 tests mandated by plan.md line 1126**)
  - `tests/unit/test_alert_types_seed.py` (~40 LOC, **19 codes plan.md-mandated**)
  - `tests/unit/test_sync_estado_repo.py` (~10 LOC, 3 helpers)
  - `tests/static/test_sync_estado_read_only.py` (~20 LOC, KD-SYNC-02 AST walk)
  - `tests/integration/test_migration_0032_idempotency.py` (~20 LOC, 2 tests)
- [ ] `Cache-Control: no-store` verified on 200 / 403 / 422 / 5xx responses.
- [ ] KD-SYNC-01 SELECT-only invariant verified per handler via AST walk.
- [ ] KD-SYNC-02 read-only invariant verified per handler via AST walk (NO UPDATE/DELETE/COMMIT).
- [ ] Tenant scope post-V1 verified (operador cross-branch → 403 `tenant_scope_violation`).
- [ ] Permission gate verified (`audit_read` granted → 200, denied → 403 `permission_denied`).
- [ ] Empty branch contract verified (no sync_log rows → 200 with `lag_seg=null`, NOT 404).
- [ ] Severity mapping verified (DEC-SYNC-06 verbatim per plan.md line 1131).
- [ ] 19 alert_types present after upgrade (8 técnicos + 1 F1.13 + 10 F1.14 — DEC-SYNC-05).
- [ ] MIGRATION 0032 idempotency verified (re-running upgrade head on migrated DB → no net change).
- [ ] Downgrade cycle verified (downgrade -1 → 9 rows; upgrade head → 19 rows round-trip).
- [ ] No new permission seeded (DEC-SYNC-03.B — `audit_read` reuse only).
- [ ] No AI attribution in commits (no `Co-authored-by:`, no AI trailers).

---

## References

- `openspec/changes/hu-f1-14-sync-estado/proposal.md` (~770 LOC, 16 sections, DEC-SYNC-01..10, KD-SYNC-01..02, 10 risks R1..R10 — 4 RESOLVED at propose phase)
- `openspec/changes/hu-f1-14-sync-estado/exploration.md` (~770 LOC, 17 sections, R1..R10 risks, pre-flight 16/16 PASS, DEC-SYNC-03 audit resolved Option B)
- `plan.md` lines 1105-1133 (HU-F1.14 definition, 3 atomic tasks T1..T3, 2 tests mandated at line 1126, 120 LOC budget, severity mapping at line 1131)
- `plan.md` line 429 (DEC-SUC-14: 19 totales, 8 técnicos + 11 de negocio coexisten)
- `plan.md` line 459 (A-08 severity JOIN-only via `alert_types.severity`)
- `plan.md` lines 2275-2291 (HU-F11.1 SyncBanner consumer — 30s polling, verde/amarillo/rojo umbrales from CU-14 BR1)
- `plan.md` lines 2305-2325 (HU-F11.2 AlertasPanel consumer)
- `plan.md` lines 2311-2323 (canonical descriptions per alert_type — DEC-SYNC-10)
- `plan.md` lines 4155-4201 (HU-F19.4 mirror for Part-II parallel siembra — referenced, out of F1.14 scope)
- `modelo_datos_er.mmd` lines 981-1002 (`sync_queue` [A]), lines 1027-1047 (`sync_log` [A]), lines 1101-1114 (`alert_types` [A])
- `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` lines 169-175 (F1.13 head, Op 2 `descuadre_critico` siembra precedent — DEC-ARQUEO-09b)
- `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22, 132-147; REVOKE/GRANT lines 129-130; idempotent INSERT precedent lines 67-108)
- `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` lines 134-188 (conditional siembra pattern)
- `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py` lines 39-56 (`CANONICAL_PERMISOS` includes `audit_read` at line 48 — DEC-SYNC-03.B)
- `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` line 95 (router declaration), line 358 (`sync-agent-` issuer guard), lines 9-49 (docstring listing 7 endpoints — `/estado` NOT in list)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` line 86 (F1.13 mount precedent: `router.include_router(caja_arqueo_router)` — DEC-SYNC-02)
- `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — DEC-SYNC-04)
- `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory, KD-3 dep)
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx`, KD-S2 F1.7 analog — Layer 2)
- `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py` lines 30-48 (validate + AlertaFactory)
- `backend/packages/parkos_core/src/parkos_core/models/A/{sync_log, sync_queue, alert_types}.py` (verbatim ORM models)
- `backend/packages/parkos_core/src/parkos_core/schemas/sync_infra.py` (EXTEND with 2 new shapes: `SyncEstadoQueryParams` + `SyncEstadoRead`)
- `infra/scripts/seed_alert_types.py` (psycopg `ON CONFLICT` precedent — keep `SEED_ROWS` in sync with MIGRATION 0032 per DEC-SYNC-10)
- `tests/static/check_sync_queue_carveout.py` (REQ-OPS-004 AST walk precedent for KD-SYNC-02)
- `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 already exists from F1.13 — F1.14 references, does NOT create new)
- `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/specs/operations/spec.md` (canonical Given/When/Then/And format precedent, 8 REQs REQ-OPS-091..097 + REQ-OPS-XR6, ~485 LOC — this delta mirrors its structure section-by-section)

---

## Cross-Cutting Notes

- **A-08 (plan.md line 459)**: `alerta.severidad` is JOIN-only via `alert_types.severity`. F1.14's siembra guarantees the JOIN succeeds for the 11 business codes (no "—" placeholder in operator UI for Fase 11 HU-F11.2 AlertasPanel).
- **DEC-SUC-14 (plan.md line 429)**: 19 totales (8 técnicos + 1 F1.13 + 10 F1.14), coexisten sin reemplazar.
- **DEC-SYNC-03 resolved**: `audit_read` (pre-seeded at `0002_seed_permisos_canonicos.py:48`) is the canonical permission gate. No new permission, no patch to existing migration, no scope creep into MIGRATION 0032.
- **DEC-SYNC-05**: 10 net new (NOT 11) — `descuadre_critico` already seeded by F1.13 MIGRATION 0031 Op 2 lines 169-175. The `ON CONFLICT (tipo_alerta) DO NOTHING` clause makes the re-seed a clean no-op.
- **XR6 reference**: REQ-OPS-XR6 from F1.13 at `operations/spec.md:3951` applies to F1.14 by inclusion. F1.14 references REQ-OPS-XR6 in §13 of design.md and §10 of tasks.md (no new XR created).
- **HU-F19.4 cross-implication**: F19.4 plans the SAME 11 alert_types siembra (plan.md lines 4155-4201). F1.14 ships them in MIGRATION 0032 for Fase 1; F19.4's siembra (Part-II) becomes a no-op via `ON CONFLICT DO NOTHING`. Either order works.

---

**End of delta spec — HU-F1.14.**
