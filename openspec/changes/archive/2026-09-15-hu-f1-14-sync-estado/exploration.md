# Exploration: HU-F1.14 — `GET /sync/estado` + siembra 11 alert_types de negocio (19 totales)

> **Phase**: explore (sdd-explore) · **Status**: ready for `sdd-propose`
> **HU ID**: HU-F1.14 (Fase-1 prerequisites — backend, Fase-11 unlocking)
> **Inputs**: `plan.md` lines 1105-1133 (120 LOC, 3 atomic tasks T1..T3), `plan.md` lines 4155-4201 (HU-F19.4 mirror — Part-II's parallel siembra), `plan.md` line 429 (DEC-SUC-14 — 19 totales, 8 técnicos + 11 negocio), `plan.md` line 459 (A-08 — severidad join-only), `plan.md` lines 2275-2291 (HU-F11.1 SyncBanner), `plan.md` lines 2305-2325 (HU-F11.2 AlertasPanel), `modelo_datos_er.mmd` blocks `sync_log` [A] lines 1027-1047, `sync_queue` [A] lines 981-1002, `alert_types` [A] lines 1101-1114; `migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (F1.13 head, REAL siembra with `descuadre_critico` in Op 2), `migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger + REVOKE/GRANT), `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (conditional siembra pattern); `api/v1/sync_router.py` (existing `/sync/*` — sync-agent- issuer), `repo/alert_types.py` (validate + AlertaFactory), `models/A/sync_log.py`, `models/A/sync_queue.py`, `schemas/sync_infra.py`, `infra/scripts/seed_alert_types.py`; F1.13 archive at `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/exploration.md` (17-section structure verbatim mirror).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `83b5dfa`, F1.13 just closed) · **PR target**: `origin/dev`.

---

## 1. Title & Goal

**Title**: "`GET /sync/estado` (KD-3 operador) + siembra idempotente de los 11 `alert_types` de negocio en `prod.alert_types` (8 técnicos pre-existentes + 11 nuevos = 19 totales)"

**Goal**: Deliver one new read endpoint + one conditional siembra migration that unlocks Fase 11 (SyncBanner + AlertasPanel):

- **`GET /api/v1/sync/estado?uuid_sucursal=X`** — returns `{uuid_sucursal, ultima_sync_at, lag_seg, pendientes}` computed by:
  1. `ultima_sync_at = MAX(prod.sync_log.timestamp_evento WHERE uuid_sucursal=X)`.
  2. `lag_seg = (NOW() - ultima_sync_at).total_seconds()` if `ultima_sync_at IS NOT NULL`, else `None`.
  3. `pendientes = SELECT count(*) FROM prod.sync_queue WHERE uuid_sucursal=X AND estado='pendiente'`.
  Consumer: HU-F11.1 `SyncBanner` (polling 30s, verde/amarillo/rojo umbrales from CU-14).

- **MIGRATION 0032 siembra 11 alert_types de negocio** — `prod.alert_types.tipo_alerta` ∈ `{descuadre_critico, sync_fallida, capacidad_agotada, capacidad_agotada_forzado, evento_no_procesado, impresora_caida, fe_error_toppoint, numeracion_toppoint_agotada, cache_desactualizado, arqueo_pendiente_24h, suscripcion_proxima_vencer}`. Severity per plan.md line 1131 (DEC-SYNC-06):
  - `critical` (alta): `descuadre_critico` (already seeded by F1.13 0031 Op 2 — `ON CONFLICT DO NOTHING`), `sync_fallida`, `evento_no_procesado`, `impresora_caida`, `fe_error_toppoint`, `numeracion_toppoint_agotada`.
  - `warning` (media): `capacidad_agotada`, `capacidad_agotada_forzado`, `arqueo_pendiente_24h`, `suscripcion_proxima_vencer`.
  - `info` (baja): `cache_desactualizado`.
  Idempotent — same `alert_types_inmutable` trigger precedent (0013:21-22).

**Defense in depth (5 layers — XR6 mirror)**: (a) KD-3 issuer chain `requires_issuer("operador-", "admin-")` + permission gate (DEC-SYNC-03); (b) tenant scope post-V1 (KD-S2 F1.7 analog); (c) SELECT-only AST walk (KD-SYNC-02); (d) Pydantic `extra='forbid'`; (e) handler 422/403/404 + `Cache-Control: no-store` (DEC-SYNC-04).

**Scope**: ~120 LOC production + ~80 LOC tests + ~70 LOC MIGRATION 0032 (REAL siembra) = ~270 LOC cumulative.

---

## 2. Context & Background

- **F1.13 just closed** (commit `83b5dfa`). Migration head = `0031_arqueo_cierre_dia_and_gap_be_05` (REAL siembra, Op 2 = `descuadre_critico`).
- **`prod.alert_types` exists** ([A] registry, migration 0013 lines 1-169). Business-key PK `tipo_alerta` (TEXT). `alert_types_inmutable` trigger (lines 21-22, 132-147) — `BEFORE UPDATE OR DELETE` raises `'ALERT_TYPES_INMUTABLE'`, `ERRCODE = '42501'`. REVOKE pattern: `REVOKE UPDATE, DELETE FROM rol_app` + `GRANT SELECT, INSERT TO rol_app` (lines 129-130).
- **`prod.alert_types` seeded status pre-F1.14**: 8 técnicos from 0013 (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) + 1 from F1.13 MIGRATION 0031 Op 2 (`descuadre_critico`) = **9 pre-F1.14**. F1.14 adds 10 net new = **19 final**.
- **`prod.sync_queue` exists** ([A] carved-out, models/A/sync_queue.py:41-99).5 estados: `pendiente|en_progreso|exitoso|fallido|descartado`. `uuid_sucursal` nullable UUID.
- **`prod.sync_log` exists** ([A], models/A/sync_log.py:29-72). Composite PK `uuid + fecha_retencion_hasta`, monthly pg_partman. `uuid_sucursal` + `timestamp_evento` (DateTime naive UTC) + 4 counter columns + `duracion_ms`.
- **Mount path tension — RESOLVED in §3 (DEC-SYNC-01)**: existing `api/v1/sync_router.py` is `/sync/*` with `sync-agent-` issuer (sync transport, not operador). F1.14 introduces `GET /sync/estado` for operador. Resolution: dedicated `api/v1/sync_estado.py` with KD-3 dep, mounted under same `/sync` prefix — FastAPI dispatches by exact path.
- **Helper modules REUSE**: `repo/alert_types.validate` (lines 30-48); `api/v1/_helpers.apply_no_store_header` (F1.13 precedent); `auth/tenancy.get_tenant_ctx` (F1.7 KD-S2 analog); `api/v1/deps.requires_issuer`.
- **Critical accounting correction (DEC-SYNC-05)**: plan.md line 4157 says "8 rows seeded today, all infra/DIAN" — slightly stale. The actual pre-F1.14 count is 9 (8 + `descuadre_critico` from F1.13 MIGRATION 0031 Op 2). F1.14 adds 10 net new (the 11 from plan.md minus `descuadre_critico` which is `ON CONFLICT DO NOTHING`). Final total: **19**.
- **A-08 (plan.md line 459)**: `alerta.severidad` is JOIN-only via `alert_types.severity`. F1.14's siembra guarantees the JOIN succeeds for the 11 business codes (no "—" placeholder in operator UI).
- **Permission inventory**: NO existing `consultar_estado_sync` permission in `0002_seed_permisos_canonicos.py` — DEC-SYNC-03 decision deferred to propose phase (see §6.6).

### 2.1 Critical Architectural Conflict — Issuer chain conflict on `/sync` prefix (RESOLVED in §3)

Two distinct consumers on the `/sync/*` namespace:
- **Sync transport layer** (`sync_router.py`): 7 endpoints, all `sync-agent-` JWT (sync workers only).
- **Operator UI layer** (F1.14 new): `GET /sync/estado`, KD-3 `operador-`+`admin-` JWT (operator banner polling).

Resolution: dedicated router file with KD-3 dep, mounted under same prefix — FastAPI dispatches by exact path.

---

## 3. Architectural Conflict Resolution — DEC-SYNC-01 + KD-SYNC-01

### 3.1 The conflict (R1 MEDIUM)

Two distinct auth chains needed on `/sync/*`:
| Source | Issuer | Consumer | Path |
|---|---|---|---|
| `sync_router.py` (existing) | `sync-agent-` | `job-sync-sucursal` worker | `/sync/{hello,pair,push,pull,heartbeat,rotate-jwt,events}` |
| F1.14 new | `operador-`+`admin-` | HU-F11.1 `SyncBanner` (operador) | `/sync/estado` |

If mounted in the same router, the dep chain rejects one or the other depending on order.

### 3.2 The resolution — DEC-SYNC-01: Dedicated `api/v1/sync_estado.py` router with KD-3 dep

1. **NEW** `api/v1/sync_estado.py` with `APIRouter(prefix="/sync", tags=["sync"])` and `_issuer_dep = requires_issuer("operador-", "admin-")`.
2. Single handler `GET /sync/estado` with `_issuer_dep` dependency.
3. **Mount from `api/v1/caja.py`** (DEC-SYNC-02 — precedent: F1.13's `router.include_router(caja_arqueo_router)` at line 86).
4. Handler is **READ-ONLY** (SELECT on `sync_log` + `sync_queue`) — NO writes, NO commits, NO log rows (KD-SYNC-02).

### 3.3 Why this matters

- HU-F11.1 `SyncBanner` polls with operador JWT — cannot mint sync-agent JWT.
- Sync transport worker (`job-sync-sucursal`) MUST NOT hit `/sync/estado` — path not in its call list (verified in `sync_router.py` docstring: 7 endpoints listed, none is `/estado`).
- Two routers with same prefix but different deps is a precedent (every endpoint in the codebase mounts under its own prefix).

---

## 4. Affected Areas

### 4.1 Files READ (existing infrastructure — F1.14 reuse, NO modifications)

- `migrations/versions/0001_initial_schema.py` (sync_log/sync_queue blocks), `0013_add_alert_types.py` (registry + REVOKE/GRANT + trigger + idempotent seed), `0029_reimpresion_siembra_and_permiso_anular.py` (conditional siembra pattern), `0030_venta_suscripcion_optional.py` (F1.12 NO-OP), `0031_arqueo_cierre_dia_and_gap_be_05.py` (F1.13 head, Op 2 `descuadre_critico`).
- `models/A/{sync_log, sync_queue, alert_types}.py` (verbatim ORM models).
- `repo/{alert_types, append_only, sync_queue}.py` (helpers).
- `schemas/sync_infra.py` (EXTEND with 2 new shapes).
- `api/v1/{_helpers, sync_router, caja}.py` (mount patterns + no-store helpers).
- `auth/{jwt_issuer_guard, tenancy}.py` (KD-3 + tenant scope).
- `infra/scripts/seed_alert_types.py` (psycopg `ON CONFLICT` precedent — keep `SEED_ROWS` in sync with MIGRATION 0032).
- `tests/static/check_sync_queue_carveout.py` (REQ-OPS-004 AST walk precedent).

### 4.2 Files WRITTEN (F1.14 implementation)

- `repo/sync_estado.py` (NEW, ~30 LOC) — 3 typed SELECT helpers: `get_ultima_sync_at(session, uuid_sucursal)`, `calcular_lag_seg(ultima_sync_at, now)`, `count_pendientes_sync_queue(session, uuid_sucursal)`.
- `schemas/sync_infra.py` (EXTEND, +40 LOC) — `SyncEstadoQueryParams` (~15 LOC) + `SyncEstadoRead` (~20 LOC, nullable `lag_seg`).
- `api/v1/sync_estado.py` (NEW, ~80 LOC) — dedicated `APIRouter` with `GET /sync/estado` (4-step handler). Mounted from `api/v1/caja.py` (DEC-SYNC-02).
- `migrations/versions/0032_seed_alert_types_operativos.py` (NEW, ~70 LOC, REAL siembra) — Op 0 pre-flight + Op 1 siembra 11 NEW alert_types (idempotent) + Op 2 optional permission (DEC-SYNC-03.C).

### 4.3 Test files (NEW)

- `tests/unit/test_sync_estado.py` (~30 LOC, **2 mandated by plan.md line 1126**): empty branch / populated branch.
- `tests/unit/test_alert_types_seed.py` (~40 LOC, **19 codes, no duplicates** — plan.md line 1126 mandate).
- `tests/static/test_sync_estado_read_only.py` (~20 LOC, KD-SYNC-02 AST walk).
- `tests/integration/test_migration_0032_idempotency.py` (~20 LOC, 2 tests).

### 4.4 Cumulative LOC

- Production: ~150 LOC (vs plan 120 = +25%)
- Tests: ~110 LOC across 4 files
- Migration: ~70 LOC (REAL siembra)
- Total: ~330 LOC

---

## 5. Regulatory / Business Rules

- **CU-14 + CU-07**: F1.14 is the **backend unlock** (UI is Fase 11).
- **A-08 (plan.md line 459)**: severity JOIN-only — F1.14's siembra guarantees the JOIN succeeds.
- **DEC-SUC-14 (plan.md line 429)**: 19 totales, 8 técnicos + 11 de negocio, **coexisten sin reemplazar**. Los 8 técnicos NO se muestran al operador (ABIERTO-06).
- **Sync transport immutability**: `sync_log` is `[A]` insert-only — handler MUST NOT `UPDATE`/`DELETE` (KD-SYNC-02 AST walk).
- **sync_queue carve-out** (REQ-OPS-004): `UPDATE`/`DELETE` only via `repo/sync_queue` whitelisted columns — F1.14 NEVER mutates `sync_queue`.
- **Idempotency of siembra**: `ON CONFLICT (tipo_alerta) DO NOTHING` respects `alert_types_inmutable` trigger (0013:21-22).
- **Cloud + branch**: alert_types seeded **identically** on both (0013:11-13 — no role/deploy distinction). MIGRATION 0032 follows.
- **CU-07 BR3**: `evento_no_procesado` detector lives in `job-sync-sucursal` (NOT F1.14 scope) — F1.14 only seeds the registry entry so the detector CAN fire alerts.

---

## 6. Existing Infrastructure

### 6.1 Tables (5+ exist; F1.14 needs only DATA seeds + 1 SELECT)

- `prod.alert_types` [A] — UK via PK `tipo_alerta` (TEXT). 9 rows seeded pre-F1.14. **Add 10 net new.**
- `prod.sync_log` [A] — composite PK, monthly partitioned. SELECT only.
- `prod.sync_queue` [A] carved-out — composite PK, monthly partitioned. SELECT only.
- `prod.sucursal` [V] — for tenant scope check.
- `prod.permisos` [V] — for permission gate (DEC-SYNC-03).

### 6.2 ORM models (all exist, reuse)

- `models/A/sync_log.py:29-72` — `SyncLog` (uuid_sucursal nullable UUID, timestamp_evento DateTime naive UTC, 4 counter columns).
- `models/A/sync_queue.py:41-99` — `SyncQueue` (uuid_sucursal nullable UUID, estado 5 values, 4 whitelisted columns).
- `models/A/alert_types.py` — `AlertTypes` (PK tipo_alerta TEXT).
- `models/V/permisos.py` — `Permisos` for permission gate.

### 6.3 Repo helpers — REUSE only (no NEW write helpers)

**REUSE**: `repo/alert_types.validate`; `repo/sync_queue` whitelist constants; `auth/tenancy.get_tenant_ctx`; `api/v1/_helpers.apply_no_store_header`.

**NEW** (`repo/sync_estado.py`, ~30 LOC): 3 typed SELECT helpers.

**GAPS closed by F1.14**: `GET /sync/estado` endpoint does NOT exist; the 10 missing alert_types for CU-14 business layer.

### 6.4 Schemas — REUSE + EXTEND

**REUSE**: `schemas/common.py::_Base` (Pydantic `extra='forbid'`).

**EXTEND** (`schemas/sync_infra.py`, +40 LOC): `SyncEstadoQueryParams` + `SyncEstadoRead`.

### 6.5 Sync catalog entries — VERIFY PRE-FLIGHT (RESOLVED 2026-09-15)

`alert_types`, `sync_queue`, `sync_log` are **out-of-catalog** (per ER lines 976, 1096, 1111 — `sync_status: "no usado — tabla out-of-catalog, nunca replicada"`). NO F1.14 sync_catalog seeds needed. MIGRATION 0032 contains NO `INSERT INTO prod.sync_catalog`.

### 6.6 Permisos — DECISION DEFERRED (DEC-SYNC-03)

`consultar_estado_sync` permission does NOT yet exist. Three options:
- **A**: Patch `0002_seed_permisos_canonicos.py` — LOW likelihood (plan.md budgets 120 LOC, no permisos migration).
- **B** (preferred): Reuse existing read-only permission already granted to `operador`+`admin` (e.g., `consultar_caja` or `ver_sucursal`).
- **C** (alternate): Bundle new permission in MIGRATION 0032 Op 0 — 5 extra LOC. Trade-off: scope creep.

**F1.14 cannot ship without a permission gate** — propose phase must audit `0002_seed_permisos_canonicos.py` and pick A/B/C.

---

## 7. Tables Touched

- 7.1 `prod.alert_types` [A] — READ + siembra (Op 1 of 0032, idempotent `ON CONFLICT DO NOTHING`).
- 7.2 `prod.sync_log` [A] — SELECT only (`MAX(timestamp_evento) WHERE uuid_sucursal=X`, KD-SYNC-02).
- 7.3 `prod.sync_queue` [A] carved-out — SELECT only (`count(*) WHERE uuid_sucursal=X AND estado='pendiente'`, KD-SYNC-02).
- 7.4 `prod.permisos` [V] — conditional INSERT (DEC-SYNC-03.C only).
- 7.5 `prod.permisos_usuario` [V] — conditional INSERT (DEC-SYNC-03.C only).

---

## 8. Endpoints Proposed

### 8.1 `GET /api/v1/sync/estado` (HU-F1.14-T2)

- Issuer dep: `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-SYNC-01).
- Permission: `consultar_estado_sync` OR equivalent read-only (DEC-SYNC-03 TBD).
- Query params: `uuid_sucursal: UUID` (required, Pydantic validator).
- Response (200): `SyncEstadoRead` with `uuid_sucursal`, `ultima_sync_at` (ISO-8601 naive UTC or `null`), `lag_seg` (int or `null`), `pendientes` (int ≥ 0).
- Status codes: 200; 422 missing/invalid `uuid_sucursal`; 403 `tenant_scope_violation` / `permission_denied`.
- Headers: `Cache-Control: no-store` ALWAYS (DEC-SYNC-04).
- **NO idempotency key** — GET is naturally idempotent.

**Example contract**:
```jsonc
// 200 OK
{
  "uuid_sucursal": "…",
  "ultima_sync_at": "2026-09-15T15:58:00Z",
  "lag_seg": 120,
  "pendientes": 3
}

// Empty branch (no sync_log rows yet) — 200 OK, NOT 404
{
  "uuid_sucursal": "…",
  "ultima_sync_at": null,
  "lag_seg": null,
  "pendientes": 0
}
```

---

## 9. Decisions

### 9.1 DEC-SYNC-01 — Dedicated `api/v1/sync_estado.py` router with KD-3 dep (RESOLVES R1 MEDIUM)

NEW `api/v1/sync_estado.py`. Mounted under same `/sync` prefix as `sync_router.py` but with `requires_issuer("operador-", "admin-")`. FastAPI's path-based dispatch routes the exact path `/sync/estado` to this new router.

### 9.2 DEC-SYNC-02 — Mount point: `api/v1/caja.py` (NOT a NEW `_sync_mounts.py`)

`caja.py` already has `router.include_router(caja_arqueo_router)` precedent (F1.13 line 86). F1.14 mounts via the same pattern. Alternative (`_sync_mounts.py`) is over-engineering for 1 endpoint.

### 9.3 DEC-SYNC-03 — Permission gate decision (DEFERRED to propose)

See §6.6. Options A (patch `0002`), B (reuse existing), C (bundle in MIGRATION 0032). Propose phase picks based on `0002_seed_permisos_canonicos.py` audit.

### 9.4 DEC-SYNC-04 — `Cache-Control: no-store` on EVERY response (XR6 mirror)

Reuses `api/v1/_helpers.apply_no_store_header`.

### 9.5 DEC-SYNC-05 — Net 10 new alert_types added (NOT 11)

F1.13 MIGRATION 0031 Op 2 already seeded `descuadre_critico`. MIGRATION 0032 includes all 11 codes with `ON CONFLICT DO NOTHING` (idempotent). Net new: 10. Final total: 19 (8 técnicos + 1 F1.13 + 10 F1.14).

### 9.6 DEC-SYNC-06 — Siembra severity mapping per plan.md line 1131

DB column `severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical'))` (migration 0013:119). Plan.md's "alta/media/baja" maps: alta→critical, media→warning, baja→info.

### 9.7 DEC-SYNC-07 — Idempotent siembra via `ON CONFLICT DO NOTHING`

Same pattern as F1.13 Op 2. `alert_types_inmutable` trigger MUST remain enabled (no temporary disable for siembra — only for explicit `DELETE` in downgrade).

### 9.8 DEC-SYNC-08 — `lag_seg = None` when `ultima_sync_at IS NULL`

Handler returns `null` for `lag_seg` when no `sync_log` rows. NOT `0` (misleadingly implies "freshly synced"). NOT `inf` (Pydantic serialization issues).

### 9.9 DEC-SYNC-09 — `pendientes` always returns `int ≥ 0`

`SELECT count(*)` ALWAYS returns 0 for empty result set. Handler MUST NOT return `null` for `pendientes`.

### 9.10 DEC-SYNC-10 — `descripcion` field per alert_type from plan.md lines 2311-2323

Each of the 11 codes gets a `descripcion` field seeded alongside `severity`. Plan.md provides canonical descriptions. Mirror in MIGRATION 0032's `_SEED_ROWS` tuple. Also update `infra/scripts/seed_alert_types.py::SEED_ROWS` to keep operational re-seed in sync.

---

## 10. Risks (10 rows)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Issuer chain conflict on `/sync` prefix | MEDIUM (RESOLVED) | DEC-SYNC-01 + dedicated router |
| R2 | `sync_log`/`sync_queue` mutation by handler | LOW | KD-SYNC-02 AST walk `test_sync_estado_read_only.py` |
| R3 | `lag_seg = None` confusion in client UI | LOW | DEC-SYNC-08 + docstring |
| R4 | 11 vs 10 alert_types accounting | MEDIUM (RESOLVED) | DEC-SYNC-05 explicit + test_alert_types_seed.py asserts 19 total |
| R5 | Permission gate missing | MEDIUM | DEC-SYNC-03 A/B/C options, propose phase decides |
| R6 | Severity mismatches plan.md wording | LOW | DEC-SYNC-06 verbatim + test asserts exact severity |
| R7 | `alert_types_inmutable` trigger blocks migration | LOW | DEC-SYNC-07 `ON CONFLICT DO NOTHING` |
| R8 | Cloud/branch desync after siembra | LOW | Same migration runs on both (0013 precedent) |
| R9 | UUID format wrong on `uuid_sucursal` | LOW | Pydantic UUID validator + 422 on malformed |
| R10 | Tenant scope bypass (operador cross-branch) | LOW | KD-S2 F1.7 analog: `get_tenant_ctx().can_access(uuid_sucursal)` at Step 2 |

---

## 11. Defense in Depth (5 layers — XR6 mirror)

| Layer | Mechanism | Source |
|---|---|---|
| 1 | KD-3 issuer chain + permission gate | handler Layer 1 |
| 2 | Tenant scope post-V1 (`get_tenant_ctx()`) | handler Layer 2 |
| 3 | KD-SYNC-01 SELECT-only (NO UPDATE/DELETE on sync_log/sync_queue) | AST walk |
| 4 | Pydantic `extra='forbid'` + UUID required + nullable `lag_seg` | `_Base` |
| 5 | 422/403/404 mapping + `Cache-Control: no-store` | handler Layer 5 |

Typed exception → HTTP mapping: 4 typed errors (`uuid_sucursal_invalid`, `permission_denied`, `tenant_scope_violation`, `internal_error`). pgcode NEVER in response body.

---

## 12. Pre-Flight Verification (16 checks)

| # | Check | Source | Result |
|---|---|---|---|
| 1 | `prod.alert_types` exists | migration 0013:115-126 | PASS |
| 2 | `prod.sync_log` exists | migration 0001:1027-1047 + models/A/sync_log.py:29 | PASS |
| 3 | `prod.sync_queue` exists | migration 0001:981-1002 + models/A/sync_queue.py:41 | PASS |
| 4 | `prod.sucursal` exists | F1.7 closed | PASS |
| 5 | `prod.permisos` exists | migration 0002 | PASS |
| 6 | Migration head = `0031` | `git log --oneline -1 83b5dfa` | PASS |
| 7 | `alert_types_inmutable` trigger active | migration 0013:143-147 | PASS |
| 8 | `descuadre_critico` alert_type seeded | migration 0031 Op 2 | PASS (already) |
| 9 | 8 alert_types técnicos seeded | migration 0013:67-108 | PASS |
| 10 | `sync_log.uuid_sucursal` is nullable UUID | models/A/sync_log.py:47-50 | PASS |
| 11 | `sync_queue.estado` accepts 'pendiente' | models/A/sync_queue.py:80 | PASS |
| 12 | `sync_queue` carve-out whitelist enforced | REQ-OPS-004 + check_sync_queue_carveout.py | PASS |
| 13 | F1.13 archive completed | `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/` exists | PASS |
| 14 | HU-F11.1 SyncBanner consumer exists | plan.md lines 2275-2291 | PASS |
| 15 | HU-F11.2 AlertasPanel consumer exists | plan.md lines 2305-2325 | PASS |
| 16 | A-08 severity JOIN pattern | plan.md line 459 + DEC-SUC-25 | PASS |

**Result**: 16/16 PASS. Pre-flight gate **PASS** (no known-MISSING to close; MIGRATION 0032 is the 10 net-new rows).

---

## 13. Test Plan (4 files)

- `test_sync_estado.py` (~30 LOC, **2 mandated by plan.md line 1126**): empty branch (no sync_log rows → `ultima_sync_at=None`) / populated branch (5 sync_log rows + 12 pending sync_queue → exact `lag_seg` math).
- `test_alert_types_seed.py` (~40 LOC, plan.md-mandated): 19 codes present, no duplicates, exact severity match for all 11 business codes.
- `test_sync_estado_read_only.py` (~20 LOC, AST walk, KD-SYNC-02): handler MUST NOT contain `UPDATE` or `DELETE` for `SyncLog` or `SyncQueue`.
- `test_migration_0032_idempotency.py` (~20 LOC, 2 tests): re-run on already-migrated DB → 0 net change + downgrade + re-upgrade cycle works.

---

## 14. Out of Scope (F2.x+)

UI integration (Fase 11 HU-F11.1/F11.2) · detection jobs that CREATE the alerts (every 5 min for `capacidad_agotada`, every 1h for `evento_no_procesado`/`arqueo_pendiente_24h`, CU-01/02/03 for `suscripcion_proxima_vencer`) · `/admin/sync/estado` (HU-F19.1, Part-II — different prefix, admin scope) · `evento_no_procesado` detector (lives in `job-sync-sucursal`) · `cache_desactualizado` detector (Fase 11) · HU-F19.4 (Part-II parallel siembra, same 11 codes — careful sequencing).

---

## 15. Sync Catalog — pre-flight verification (RESOLVED 2026-09-15)

`alert_types`, `sync_queue`, `sync_log` are **out-of-catalog** (per ER lines 976, 1096, 1111). NO F1.14 sync_catalog seeds needed. MIGRATION 0032 contains NO `INSERT INTO prod.sync_catalog`.

---

## 16. Proposed Cluster Decomposition (4 clusters)

- **T1**: MIGRATION 0032 siembra (10 net new alert_types + pre-flight) (~70 LOC)
- **T2**: `repo/sync_estado.py` 3 helpers + schemas extend (~70 LOC)
- **T3**: `GET /sync/estado` 4-step handler + router mount (~80 LOC)
- **T4**: 4 test files + 1 AST walk + 1 migration test (~110 LOC)

**Total: ~330 LOC** (production 150 + tests 110 + migration 70).

---

## 17. Next Recommended Phase

**Phase**: `sdd-propose hu-f1-14-sync-estado` (17-section proposal at `openspec/changes/hu-f1-14-sync-estado/proposal.md`).

**Pre-propose verification status** (completed 2026-09-15):
1. Static pre-flight 16/16 PASS.
2. Issuer conflict RESOLVED via DEC-SYNC-01.
3. 11 vs 10 accounting RESOLVED via DEC-SYNC-05.
4. Permission gate DEC-SYNC-03 deferred to propose phase (A/B/C audit needed).
5. Sync catalog out-of-catalog → no entries needed.
6. Sync transport worker path list verified — `/sync/estado` NOT in worker call list.

**Key inputs for propose phase**: DEC-SYNC-01..10 (10 decisions, §9); KD-SYNC-01..02 (2 invariants); XR6 + REQ-OPS-098..101 (~4 new REQs + XR6 mirror); 4-cluster decomposition T1..T4; MIGRATION 0032 REAL siembra (10 net new); permission gate decision (DEC-SYNC-03 A/B/C).

**Key precedent mirrors** (to cite verbatim in proposal):
- `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/exploration.md` (17-section structure verbatim).
- `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (MIGRATION 0031 Op 2 `descuadre_critico` siembra = the IDPOTENT pattern to mirror for MIGRATION 0032).
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py` (dedicated router pattern — KD-3 dep + `_helpers.apply_no_store_header` reuse).
- `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` (REVOKE/GRANT + trigger + idempotent INSERT pattern).
- `infra/scripts/seed_alert_types.py` (psycopg `ON CONFLICT` precedent — keep `SEED_ROWS` in sync with MIGRATION 0032).

---

**End of exploration.**
