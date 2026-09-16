# Exploration: HU-F1.15 — `GET /usuarios/{uuid}/login` histórico (gap huérfano)

> **Phase**: explore (sdd-explore) · **Status**: ready for `sdd-propose`
> **HU ID**: HU-F1.15 (Fase-1 prerequisites — backend, **Última HU de Fase 1 Parte I**)
> **Inputs**: `plan.md` lines 1137-1155 (70 LOC, 2 atomic tasks T1..T2, gap huérfano de auditoría de seguridad), `plan.md` line 613 (HU-F1.2 share de migración de índice), `plan.md` lines 2388-2394 (F1 endpoint table row 2391), `plan.md` lines 7571-7574 (duplicate-resource note: Parte 1 F1.15 + Parte 2 F16.1/F16.5 — mismo recurso, construir una sola vez, backend compartido), `plan.md` lines 610-617 (F1.2 story, comparte `prod.login` como tabla de auditoría); `openspec/changes/archive/fase-1-prerequisites-backend/prompts/pending.md` §1 row 15 (gap huérfano, 70 LOC, ningún bloqueador); `openspec/specs/operations/spec.md` 108 REQs (last: REQ-OPS-101 from F1.14 + REQ-OPS-XR6 canonical defense-in-depth at line 3951); `modelo_datos_er.mmd` blocks `usuarios` [V] (lines 7-50) + `login` [L-S] (lines 558-573); `migrations/versions/0001_initial_schema.py` lines 511-523 (login table), 1247-1255 (FK `fk_login_uuid_usuario`), 2203-2214 (trigger `login_ls_session_guard`), 2533-2541 (audit+set_vigente_inicial triggers), 2777-2788 (enqueue_sync trigger); `migrations/versions/0002_seed_permisos_canonicos.py:48` (`audit_read` pre-seeded); `migrations/versions/0021_least_privilege_and_immutability_contract.py:206` (`_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")`); `migrations/versions/0032_seed_alert_types_operativos.py` (F1.14 head, Op 2 `audit_read` reuse anchor); `models/L_S/login.py:33-74` (Login ORM, FK `usuarios`); `models/V/usuarios.py` (Usuarios ORM); `repo/session_cycle.py:49-146` (`record_login` write helper — F1.15 REUSE only via the existing `prod.login` rows, NEVER calls it); `repo/tarifas_vigencia.py:79-162` (`list_tarifas_vigentes` cursor-pagination precedent — `ORDER BY vigente_desde DESC, uuid ASC` + `cursor_encode/cursor_decode`); `api/router_factory.py:140-227` (factory `list_endpoint` pattern — `next_cursor` encoding + `read_list_schema` shape); `api/v1/_helpers.py:18-31` (`no_store_headers` + `apply_no_store_header`); `schemas/common.py::_Base` (`extra='forbid'`); `auth/jwt_issuer_guard.requires_issuer` + `auth/tenancy.get_tenant_ctx`; F1.14 archive at `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/exploration.md` (17-section structure verbatim mirror).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `7cc613f`, F1.14 just closed) · **PR target**: `origin/dev`.

---

## 1. Title & Goal

**Title**: "`GET /api/v1/usuarios/{uuid}/login` (KD-3 operador+admin) — histórico paginado por cursor de los intentos de autenticación del usuario (gap huérfano de auditoría)"

**Goal**: Deliver one new read endpoint on top of the already-shipped `prod.login` [L-S] table that closes an audit gap surfaced without an ID in any prior document:

- **`GET /api/v1/usuarios/{uuid}/login?limit=10&cursor=...`** — returns `{items, next_cursor}` per the canonical list contract (`api/router_factory.py:206-227`), with:
1. Items ordered by `timestamp_evento DESC` (most recent first, per plan.md line 1143 verbatim: "los intentos más recientes primero").
  2. Each item is a `LoginIntentoItem` shape: `{uuid, timestamp_evento, timestamp_cierre, estado ∈ {exitoso, fallido, cerrado}, uuid_sucursal}`.
  3. The `estado` field is **the real [L-S] lifecycle value** (`exitoso|fallido|cerrado` per `models/L_S/login.py:64-67` + `modelo_datos_er.mmd:567`) — NEVER a synthetic boolean `activo` (which does not exist in this domain, plan.md line 1143 verbatim).
  4. `cursor` encodes the LAST item's `(timestamp_evento, uuid)` pair (DEC-LOGIN-04, mirroring `router_factory.py:185-200`).
  5. Empty branch (`uuid_usuario` exists but ZERO `prod.login` rows): `200 OK` with `items=[]` and `next_cursor=None` (NOT 404 — REQ-OPS-100 empty-branch precedent at `spec.md:4034-4041`).
  6. Consumer gap: NO Fase-2/Fase-3 screen depends on this endpoint today (plan.md line 1139: "Desbloquea: ninguna pantalla obligatoria de esta parte"). It exists purely to surface diagnostic data when an operator/admin investigates "why is user X locked out?" or "did user Y just authenticate?".

**Defense in depth (5 layers — XR6 mirror)**: (a) KD-3 issuer chain `requires_issuer("operador-", "admin-")` + permission gate `audit_read` (DEC-LOGIN-01, DEC-LOGIN-02); (b) tenant scope post-V1 — operador own-branch only, admin cross-branch (DEC-LOGIN-03 — TBD per §9); (c) KD-LOGIN-01 SELECT-only AST walk (KD-LOGIN-02 read-only invariant); (d) Pydantic `extra='forbid'` (DEC-LOGIN-04); (e) handler 422/403/404 mapping + `Cache-Control: no-store` on EVERY response (DEC-LOGIN-05).

**Scope**: ~70 LOC production + ~50 LOC tests + ~25 LOC MIGRATION 0033 (CREATE INDEX CONCURRENTLY on `(uuid_usuario, timestamp_evento DESC)`) = ~145 LOC cumulative.

---

## 2. Context & Background

- **F1.14 just closed** (commit `7cc613f`, archive `2026-09-15-hu-f1-14-sync-estado/`). Migration head = `0032_seed_alert_types_operativos` (F1.14 REAL siembra, 10 net new alert_types). F1.15 will be **MIGRATION `0033_login_historic_index.py`** (REAL DDL — index only, no data seeds; the smallest migration of Fase 1 Parte I).
- **`prod.login` exists** ([L-S], migration 0001:511-523, `SessionBase`). 5 business columns: `uuid_usuario` (FK → `prod.usuarios.uuid`, nullable), `uuid_sucursal` (FK → `prod.sucursal.uuid`, nullable), `timestamp_evento` (DateTime naive UTC), `timestamp_cierre` (DateTime naive UTC), `estado ∈ {exitoso, fallido, cerrado}` (String(16), nullable). The `estado` column is **NOT** in migration 0001's CREATE TABLE — it was added by a later migration; the `_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` whitelist at `0021_least_privilege_and_immutability_contract.py:206` is the post-F1.1 immutability contract for the table.
- **`prod.usuarios` exists** ([V], migration 0001 lines 7-50, bi-temporal `VersionedBase`). UK `usuarios_uk01(cedula, vigente_desde)` per ER block. `email` is also UK (per `auth.py:179-184`). F1.15 reads `prod.usuarios.uuid` only to validate the path param — no SELECT required if the FK index does the join.
- **`prod.login` triggers active** (per migration 0001):
  - `login_ls_session_guard` (line 2203-2214): `BEFORE UPDATE ON prod.login` — fires when `estado` or `timestamp_cierre` changes without a `log_transaccional` row. F1.15 does NOT UPDATE, so this is irrelevant.
  - `login_audit_columns` (line 2533-2534): sets `created_at`/`created_by` on INSERT. F1.15 does NOT INSERT.
  - `login_set_vigente_inicial` (line 2538-2539): sets `vigente_desde`/`vigente_hasta` on INSERT. F1.15 does NOT INSERT.
  - `login_enqueue_sync` (line 2777-2788): `AFTER INSERT` enqueues to `sync_queue`. F1.15 does NOT INSERT.
- **`prod.login` indexes**: Only the implicit index created by FK `fk_login_uuid_usuario` (migration 0001:1247-1255) on `uuid_usuario`. **No composite index** on `(uuid_usuario, timestamp_evento DESC)` exists today. The pagination query at production scale (a single operator with 1000s of login rows over months) would degrade to a sort on disk without the composite index. **DEC-LOGIN-06** mandates MIGRATION 0033 to add `prod.idx_login_uuid_usuario_evento` via `CREATE INDEX CONCURRENTLY`.
- **Mount path tension — RESOLVED in §3 (DEC-LOGIN-01)**: per plan.md line 7571-7574, the `GET /usuarios/{uuid}/login` endpoint is proposed INDEPENDENTLY by Parte 1 (F1.15) and Parte 2 (HU-F16.1/F16.5), but "se construye una sola vez, backend compartido". F1.15 ships the minimal backend slice (read-only cursor list); Parte 2 will extend the same router with filtros `?activo=&cursor=&limit=` and the closure action `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` (plan.md line 7572). The Parte 2 router file `api/v1/usuarios.py` does NOT exist today (HU-F16.1 deferred). **F1.15 picks the lowest-friction mount point**: extend the existing `api/v1/auth.py` (DEC-LOGIN-01.B, primary) or a NEW dedicated `api/v1/usuarios_login.py` file (DEC-LOGIN-01.A). See §3 + §9.
- **Helper modules REUSE**: `auth/jwt_issuer_guard.requires_issuer` (KD-3, F1.14 line); `auth/tenancy.get_tenant_ctx` (Layer 2, F1.7 KD-S2 analog); `api/v1/_helpers.apply_no_store_header` + `no_store_headers` (Layer 5, F1.13 precedent); `schemas/common.py::_Base` (`extra='forbid'`, Layer 4); cursor encode/decode helpers at `api/router_factory.py:127-140` (Layer 4 cursor pagination).
- **Permission inventory** (per `0002_seed_permisos_canonicos.py:39-56`): `audit_read` is pre-seeded (line 48). F1.15 REUSES `audit_read` per F1.14 DEC-SYNC-03.B precedent (the gap huérfano is the same audit domain as `GET /sync/estado`).
- **Critical accounting correction (DEC-LOGIN-07)**: plan.md line 7571-7574 establishes that this endpoint is **proposed by both Parte 1 (F1.15) and Parte 2 (F16.1/F16.5)**. F1.15 ships only the read-list slice; Parte 2 will add `?activo=` filter + closure action. **F1.15 MUST NOT lock the response shape** in a way that blocks Parte 2's extension — the canonical `{items, next_cursor}` envelope (per `router_factory.py:227`) is already extensible, so DEC-LOGIN-04 adopts it verbatim.
- **The "gap huérfano" framing** (plan.md line 1139, pending.md row 15): the endpoint closes a security audit gap with no prior ID in `plan.md`/ER/SPECS. It is NOT on any CU/critical-path; it is the smallest deliverable of Fase 1 Parte I.

### 2.1 Critical Architectural Conflict — Endpoint ownership across Parte 1 vs Parte 2 (RESOLVED in §3)

Two consumers claim the same `GET /usuarios/{uuid}/login` resource:
- **F1.15 (Parte 1 — Sucursal)**: minimal read-only list (this HU).
- **HU-F16.1/F16.5 (Parte 2 — Admin)**: full router with filtros + closure action.

Resolution: F1.15 ships the minimal slice into a NEW dedicated router `api/v1/usuarios_login.py` (DEC-LOGIN-01.A — preferred over extending `auth.py` because `auth.py` is POST-mutating-only and adding a GET there would couple read-of-history with the login write). Parte 2 will EXTEND that router (or refactor it into the broader `api/v1/usuarios.py` per their plan). The `{items, next_cursor}` envelope is forward-compatible with Parte 2's added filtros.

---

## 3. Architectural Conflict Resolution — DEC-LOGIN-01 + KD-LOGIN-01

### 3.1 The conflict (R1 LOW)

Two HU units claim the same `GET /usuarios/{uuid}/login` URL:
- F1.15 (Parte 1, this HU).
- HU-F16.1/F16.5 (Parte 2, deferred).

If F1.15 mounts into `auth.py` or into a generic `make_router` factory, Parte 2 will either (a) re-mount over the same path (collision), or (b) have to refactor F1.15's mount into their own file (scope creep). Either way, one of the two HUs is reshaped.

### 3.2 The resolution — DEC-LOGIN-01: NEW dedicated `api/v1/usuarios_login.py` router

1. **NEW** `api/v1/usuarios_login.py` with `APIRouter(prefix="/usuarios", tags=["usuarios"])` and `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")`.
2. Single handler `GET /usuarios/{uuid}/login` with `_login_historico_issuer_dep` dependency.
3. **Mount at FastAPI app-level** (DEC-LOGIN-01.A — sibling of `auth.py`), NOT in `caja.py` (wrong domain) or `auth.py` (POST-mutating-only per `auth.py:69` line `router = APIRouter(prefix="/auth", tags=["auth"])` and the existing handlers are all POST). The cleanest mount is at the FastAPI app-level (`api/v1/__init__.py` or wherever the top-level `app` is constructed — same place `auth.py` is mounted) so the router is a sibling of `auth.py`, not nested.
4. Handler is **READ-ONLY** (single SELECT on `prod.login` + optional users existence check) — NO writes, NO commits, NO log rows (KD-LOGIN-01).

### 3.3 Why this matters

- Parte 2's `api/v1/usuarios.py` (deferred) will EXTEND or RENAME `api/v1/usuarios_login.py` — no collision because Parte 2 adds DIFFERENT routes (`POST /usuarios/{uuid}/login/{login_uuid}/cerrar`, `?activo=` filter) on the same `/usuarios/{uuid}/login` path.
- `auth.py` stays focused on credential exchange (POST/login, POST/refresh, POST/logout, GET/me — the only GET is the operator's own profile, which is auth-domain by definition).
- Cursor pagination precedent (`api/router_factory.py:180-227`) is already a generic pattern; F1.15 mirrors the (order_col, uuid ASC) ordering on `(timestamp_evento DESC, uuid ASC)` with cursor encoded on the same fields.

---

## 4. Affected Areas

### 4.1 Files READ (existing infrastructure — F1.15 reuse, NO modifications)

- `migrations/versions/0001_initial_schema.py` (lines 511-523 login table, 1247-1255 FK, 2203-2214 trigger, 2533-2541 audit triggers, 2777-2788 enqueue_sync trigger).
- `migrations/versions/0002_seed_permisos_canonicos.py` (`audit_read` pre-seeded at line 48).
- `migrations/versions/0021_least_privilege_and_immutability_contract.py:206` (`_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")`).
- `migrations/versions/0032_seed_alert_types_operativos.py` (F1.14 head, Op 2 `audit_read` reuse anchor at line 185).
- `models/L_S/login.py:33-74` (Login ORM — 5 columns).
- `models/V/usuarios.py` (Usuarios ORM — F1.15 reads `uuid` only for existence check; optional).
- `repo/session_cycle.py:49-146` (`record_login` — F1.15 NEVER calls it; only references the table it writes to).
- `repo/tarifas_vigencia.py:79-162` (cursor pagination precedent — `list_tarifas_vigentes`).
- `api/router_factory.py:140-227` (factory `list_endpoint` pattern — `next_cursor` + `read_list_schema`).
- `api/v1/_helpers.py:18-31` (`no_store_headers` + `apply_no_store_header`).
- `schemas/common.py::_Base` (`extra='forbid'`).
- `auth/jwt_issuer_guard.requires_issuer` (KD-3 dep).
- `auth/tenancy.get_tenant_ctx` (Layer 2 dep).
- `tests/static/{test_sync_estado_read_only,test_arqueo_handler_single_commit,test_no_raw_dml_on_ls_tables}.py` (AST walk precedents — F1.15 needs the `ls_tables` variant).

### 4.2 Files WRITTEN (F1.15 implementation)

- `repo/login_historico.py` (NEW, ~30 LOC) — 3 typed helpers: `listar_intentos_paginado(session, uuid_usuario, cursor, limit)` (main cursor paginated SELECT), `decode_cursor_or_none(cursor)` (thin wrapper around existing `cursor_decode`), `encode_cursor_or_none(timestamp_evento, uuid)` (thin wrapper around existing `cursor_encode`).
- `schemas/usuarios.py` (NEW, ~25 LOC) — `LoginHistoricoQueryParams` (~10 LOC: `uuid: UUID` path + `limit: int = 10` query with `ge=1, le=100` validators + `cursor: str | None`) + `LoginIntentoItem` (~10 LOC: `uuid`, `timestamp_evento`, `timestamp_cierre`, `estado ∈ {exitoso, fallido, cerrado}`, `uuid_sucursal`) + `LoginHistoricoListResponse` (~5 LOC: `{items, next_cursor}` envelope).
- `api/v1/usuarios_login.py` (NEW, ~50 LOC) — dedicated `APIRouter` with `GET /usuarios/{uuid}/login` (8-step handler, all READ). Mounted at the FastAPI app-level via `api/v1/__init__.py` or equivalent (DEC-LOGIN-01.A).
- `migrations/versions/0033_login_historic_index.py` (NEW, ~25 LOC, REAL DDL) — `CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento ON prod.login (uuid_usuario, timestamp_evento DESC)` + drop in downgrade. **No data seeds** (the table is pre-populated by F1.2 lockout writes).

### 4.3 Test files (NEW)

- `tests/unit/test_login_historico.py` (~30 LOC, **2 mandated by plan.md line 1149**): empty user (zero `prod.login` rows → `items=[]` + `next_cursor=None`, NOT 404) / populated user (5 rows → ordered DESC + correct `next_cursor` encoded).
- `tests/static/test_login_historico_read_only.py` (~15 LOC, KD-LOGIN-01 AST walk): handler MUST NOT contain `update(Login)` or `delete(Login)` or `await session.commit()`.
- `tests/integration/test_migration_0033_index.py` (~10 LOC, 1 test): index exists after upgrade + DESC order is honored.

### 4.4 Cumulative LOC

- Production: ~70 LOC (matches plan 70 = 100% match, exact).
- Tests: ~55 LOC across 3 files.
- Migration: ~25 LOC (REAL DDL, smallest migration of Fase 1 Parte I).
- Total: ~150 LOC (slightly above plan 70 due to migration + tests, but plan 70 is "production" only).

---

## 5. Regulatory / Business Rules

- **CU-03 BR1** (operator monitoring): admin/operador diagnose "user X locked out" or "user Y suspicious access" via `prod.login` history. F1.15 surfaces this without adding a UI surface (UI deferred to Fase 11+).
- **Audit immutability** (per `0021_least_privilege_and_immutability_contract.py:206`): `_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` — handler MUST NOT UPDATE these columns. KD-LOGIN-01 + KD-LOGIN-02 enforces read-only via AST walk.
- **`fn_login_ls_session_guard()`** (migration 0001:2181-2200): `BEFORE UPDATE` validates a co-transactional `log_transaccional` row exists. F1.15 does NOT trigger this trigger (no UPDATE path).
- **Sync replication**: `prod.login` is `[L-S] branch→cloud` per `modelo_datos_er.mmd:572-573` (`sync_status: pendiente | sincronizado | error`). F1.15 reads replicated rows on cloud (operador is always on cloud for `/auth/me`-like operations; for branch operators, the local `prod.login` rows are the source). The endpoint does NOT care about sync state — both node types serve the query locally.
- **Estado semantics** (plan.md line 1143 verbatim): `estado ∈ {exitoso, fallido, cerrado}` — `cerrado` is set by `POST /auth/logout` (auth.py:352-393), `exitoso` by successful POST `/auth/login` (auth.py:260-266), `fallido` by failed POST `/auth/login` (auth.py:239-246). **NEVER** a synthetic boolean `activo` (which does not exist in the domain — plan.md explicitly rejects it).
- **DEC-SUC-14** (plan.md line 429, 108 REQs canonical): NOT applicable — `login` is auth-domain, not sync-domain. F1.15 is OUT-OF-CATALOG for sync (no `INSERT INTO prod.sync_catalog`).
- **No new permissions**: `audit_read` pre-seeded (line 48 of `0002_seed_permisos_canonicos.py`). F1.15 REUSES per F1.14 DEC-SYNC-03.B precedent.
- **No role grants required**: existing `permisos_usuario` rows that grant `audit_read` to `operador`+`admin` already cover F1.15. Propose phase MUST verify the existing grants (see §6.6).

---

## 6. Existing Infrastructure

### 6.1 Tables (2 exist; F1.15 needs only 1 DDL index + 1 SELECT)

- `prod.login` [L-S] — composite PK + 5 columns + FK to `prod.usuarios` + FK to `prod.sucursal` + 4 triggers (ls_session_guard, audit_columns, set_vigente_inicial, enqueue_sync). F1.15 **adds a composite index** via MIGRATION 0033.
- `prod.usuarios` [V] — bi-temporal `VersionedBase`. F1.15 reads `uuid` to validate the path param (optional — could rely on FK existence of the login rows themselves; if ZERO login rows, return empty list 200, do NOT 404 — DEC-LOGIN-08).
- `prod.permisos` [V] — for permission gate (`audit_read`, pre-seeded).
- `prod.permisos_usuario` [V] — for role-permission grants (existing).

### 6.2 ORM models (all exist, reuse)

- `models/L_S/login.py:33-74` — `Login` (5 business columns + session mixin).
- `models/V/usuarios.py` — `Usuarios` for optional existence check.

### 6.3 Repo helpers — REUSE only (no NEW write helpers)

**REUSE** (read-only helpers F1.15 needs):
- `api/router_factory.py:127-140` — `cursor_decode` / `cursor_encode` / `Cursor` dataclass (or extract to a shared module if private).
- `api/v1/_helpers.py:18-31` — `no_store_headers` + `apply_no_store_header`.
- `auth/jwt_issuer_guard.requires_issuer` — KD-3 dep.
- `auth/tenancy.get_tenant_ctx` — Layer 2 dep.

**NEW** (`repo/login_historico.py`, ~30 LOC): 3 typed helpers wrapping the SELECT + cursor decode/encode. Mirrors `repo/tarifas_vigencia.py:79-162` structure (helper returns `(rows, next_cursor)`; handler builds response from helper output).

**GAPS closed by F1.15**: `GET /usuarios/{uuid}/login` endpoint does NOT exist; no way to surface `prod.login` history without raw SQL access.

### 6.4 Schemas — NEW + REUSE

**REUSE**: `schemas/common.py::_Base` (Pydantic `extra='forbid'`).

**NEW** (`schemas/usuarios.py`, ~25 LOC): `LoginHistoricoQueryParams` + `LoginIntentoItem` + `LoginHistoricoListResponse` (envelope `{items, next_cursor}` per `router_factory.py:227`).

### 6.5 Sync catalog entries — VERIFY PRE-FLIGHT (RESOLVED 2026-09-15)

`login` is **[L-S] branch→cloud** (ER lines 572-573) and OUT-OF-CATALOG for sync catalog inserts (no sync_catalog row governs it — replicated via the global catalog replication logic, not per-table). **NO F1.15 sync_catalog seeds needed.** MIGRATION 0033 contains NO `INSERT INTO prod.sync_catalog`.

### 6.6 Permisos — DECISION DEFERRED (DEC-LOGIN-09)

`audit_read` permission is pre-seeded (`0002_seed_permisos_canonicos.py:48`). F1.14 DEC-SYNC-03.B REUSED this permission for `GET /sync/estado` without adding new permissions or role grants. F1.15 MUST audit the existing `permisos_usuario` grants to confirm `operador`+`admin` already hold `audit_read` (propose phase):

- **A**: Patch `permisos_usuario` grants if missing — UNLIKELY because F1.14's `audit_read` reuse would have failed otherwise.
- **B** (preferred, mirror F1.14 DEC-SYNC-03.B): Reuse `audit_read` as-is. No migration, no role grant changes.

**F1.15 cannot ship without a permission gate** — propose phase MUST verify the existing grants before declaring F1.15 complete.

---

## 7. Tables Touched

- 7.1 `prod.login` [L-S] — SELECT only (paginated by `(uuid_usuario, timestamp_evento DESC)` per cursor, KD-LOGIN-01). **READ of existing rows**.
- 7.2 `prod.login` [L-S] — DDL: ADD INDEX `prod.idx_login_uuid_usuario_evento` via MIGRATION 0033 (`CREATE INDEX CONCURRENTLY`).
- 7.3 `prod.usuarios` [V] — SELECT optional (existence check; or skip if login FK existence suffices — DEC-LOGIN-08, return 200 empty for non-existent user, NOT 404 to avoid enumeration).
- 7.4 `prod.permisos` [V] — READ only (permission gate lookup).
- 7.5 `prod.permisos_usuario` [V] — READ only (role grant lookup).

**No writes, no log rows, no INSERT/UPDATE/DELETE on any table from the handler.**

---

## 8. Endpoints Proposed

### 8.1 `GET /api/v1/usuarios/{uuid}/login` (HU-F1.15-T1)

- Issuer dep: `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-LOGIN-01).
- Permission: `audit_read` (DEC-LOGIN-09.B, pre-seeded per F1.14 DEC-SYNC-03.B precedent).
- Path param: `uuid: UUID` (Pydantic validator; required).
- Query params: `limit: int = 10` (ge=1, le=100, DEC-LOGIN-04), `cursor: str | None = None`.
- Response (200): `LoginHistoricoListResponse` with `items: list[LoginIntentoItem]` + `next_cursor: str | None`.
- Status codes: 200; 422 missing/invalid `uuid`; 403 `tenant_scope_violation` / `permission_denied`; 400 `cursor_invalid` (malformed base64).
- Headers: `Cache-Control: no-store` ALWAYS (DEC-LOGIN-05).
- **NO idempotency key** — GET is naturally idempotent.
- **NO 404** for unknown `uuid` — return 200 with `items=[]` (DEC-LOGIN-08, anti-enumeration — same R-F1.2-10 / R-F1.2-11 rationale).

**Example contract**:
```jsonc
// 200 OK — populated user (most recent first)
{
  "items": [
    {
      "uuid": "...",
      "timestamp_evento": "2026-09-15T15:58:00",
      "timestamp_cierre": "2026-09-15T16:30:00",
      "estado": "cerrado",
      "uuid_sucursal": "..."
    },
    {
      "uuid": "...",
      "timestamp_evento": "2026-09-15T15:55:00",
      "timestamp_cierre": null,
      "estado": "fallido",
      "uuid_sucursal": null
    }
  ],
  "next_cursor": "eyJ0aW1lc3RhbXBfZXZlbnRvIjoi..."
}

// Empty user (no login rows) — 200 OK, NOT 404 (DEC-LOGIN-08)
{
  "items": [],
  "next_cursor": null
}
```

---

## 9. Decisions

### 9.1 DEC-LOGIN-01 — Dedicated `api/v1/usuarios_login.py` router with KD-3 dep (RESOLVES R1 LOW)

NEW `api/v1/usuarios_login.py` with `APIRouter(prefix="/usuarios", tags=["usuarios"])` and `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")`. Mounted at the FastAPI app-level (sibling of `auth.py`). Parte 2's `api/v1/usuarios.py` (deferred, HU-F16.1/F16.5) will EXTEND or RENAME this router — no collision because Parte 2 adds DIFFERENT routes on the same prefix.

**Alternatives rejected**:
- DEC-LOGIN-01.A REJECTED: Mount in `auth.py` — couples read-of-history with the login write path (POST/login), violating separation of concerns.
- DEC-LOGIN-01.B REJECTED: Mount in `caja.py` — wrong domain (cash vs auth).
- DEC-LOGIN-01.C REJECTED: Use `make_router` factory — factory is single-table contract (read or write one [V] table); `prod.login` is [L-S] with cursor pagination semantics that don't map to the factory's read-list shape (factory reads `vigente_hasta IS NULL` for [V], `prod.login` has no bi-temporal `vigente_hasta` in the same sense — `vigente_hasta` on `Login` is the session end per `models/L_S/login.py:60-63`, NOT the [V] versioning column).

### 9.2 DEC-LOGIN-02 — KD-3 issuer chain `requires_issuer("operador-", "admin-")`

Same as F1.14 (`sync_estado.py`). Operador with own-branch tenant scope (Layer 2); admin cross-branch.

### 9.3 DEC-LOGIN-03 — Tenant scope post-V1 (Layer 2 — DEFERRED to propose)

Per F1.7 KD-S2 analog:
- **operador** with `audit_read`: can read `prod.login` rows where `uuid_usuario=:u` AND `login.uuid_sucursal = ctx.sucursal_uuid` (own-branch login history). Cross-branch login history requires admin.
- **admin** with `audit_read`: can read ALL `prod.login` rows for ANY `uuid_usuario`, regardless of branch.

**Open question** (see §18): does operador require same-branch matching (`uuid_sucursal` filter), or any user (no branch filter)? Two options:
- **A** (preferred, mirror F1.13/F1.14): operador must filter by `ctx.sucursal_uuid` — handler returns 200 with `items=[]` if the user has no login rows from operador's branch.
- **B**: operador reads ALL branches (cross-branch reading is allowed for audit). NOT recommended — defeats the Layer 2 invariant.

Propose phase picks A vs B.

### 9.4 DEC-LOGIN-04 — Cursor pagination via `(timestamp_evento DESC, uuid ASC)` + `cursor_encode/cursor_decode`

Cursor encodes the LAST item's `(timestamp_evento_iso, uuid_str)` pair. Mirrors `router_factory.py:185-200` exactly:
- `ORDER BY timestamp_evento DESC, uuid ASC` (DESC because most recent first per plan.md line 1143).
- `WHERE` clause for cursor pagination: `(timestamp_evento < cursor_ts) OR (timestamp_evento = cursor_ts AND uuid > cursor_uuid)`.
- `LIMIT N+1` then slice to N to detect `next_cursor` presence.
- Limit bounds: `1..100` (Pydantic validators, default `10` per plan.md line 1143).

### 9.5 DEC-LOGIN-05 — `Cache-Control: no-store` on EVERY response (XR6 mirror)

Reuses `api/v1/_helpers.apply_no_store_header` (success) + `HTTPException(headers=no_store_headers())` (errors).

### 9.6 DEC-LOGIN-06 — MIGRATION 0033 `CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento` on `prod.login (uuid_usuario, timestamp_evento DESC)`

Without this index, the cursor pagination at scale (1000+ login rows per user over months) degrades to a sort-on-disk. Migration uses `CONCURRENTLY` to avoid table lock (matches `0011_add_seq_lookup_indexes.py` precedent at line 62). Downgrade uses `DROP INDEX CONCURRENTLY`.

### 9.7 DEC-LOGIN-07 — `{items, next_cursor}` envelope forward-compatible with Parte 2

Per `router_factory.py:227` precedent. Parte 2's HU-F16.1/F16.5 will add `?activo=` filter and closure action `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` (plan.md line 7572) — both can co-exist on the same router without breaking F1.15's response shape.

### 9.8 DEC-LOGIN-08 — Empty `prod.login` rows → 200 with `items=[]`, NOT 404 (anti-enumeration)

Same rationale as F1.2 `GET /auth/me` R-F1.2-10: returning 404 for an unknown `uuid_usuario` would let an attacker enumerate valid user UUIDs by comparing 404 vs 200. F1.15 returns 200 with empty items regardless of whether the user exists, has zero login rows, or has rows from other branches only.

### 9.9 DEC-LOGIN-09 — Permission gate = `audit_read` (DEC-SYNC-03.B reuse)

`audit_read` pre-seeded per `0002_seed_permisos_canonicos.py:48`. F1.14 reused it for `GET /sync/estado`; F1.15 reuses the same permission. **NO new permissions, NO role grant changes.** Propose phase MUST verify existing grants (audit `permisos_usuario` rows for `operador`+`admin` having `audit_read` granted).

### 9.10 DEC-LOGIN-10 — Response item shape: `estado` is the real lifecycle value, NEVER a boolean `activo`

Per plan.md line 1143 verbatim: "cada uno con su `estado` real (`exitoso|fallido|cerrado`) — nunca un campo booleano `activo`, que no existe en el dominio real de `login.estado`." The Pydantic schema `LoginIntentoItem.estado: Literal["exitoso", "fallido", "cerrado"]` enforces the 3-value domain at the type level.

---

## 10. Risks (7 rows)

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Endpoint ownership conflict with Parte 2 (HU-F16.1/F16.5) | LOW (RESOLVED) | DEC-LOGIN-01 dedicated router + DEC-LOGIN-07 forward-compatible envelope |
| R2 | `prod.login` UPDATE/DELETE by handler | LOW | KD-LOGIN-01 AST walk `test_login_historico_read_only.py` |
| R3 | Performance: 1000+ login rows per user, no index → sort-on-disk | MEDIUM | DEC-LOGIN-06 MIGRATION 0033 `CREATE INDEX CONCURRENTLY` |
| R4 | Cursor pagination race (rows INSERT while paginating) | LOW | Cursor is opaque; client re-fetches with newest cursor if `next_cursor` returns 0 rows |
| R5 | 404 leaks user existence (anti-enumeration) | MEDIUM (RESOLVED) | DEC-LOGIN-08 always 200 + empty items |
| R6 | `audit_read` permission not granted to operador/admin | MEDIUM | DEC-LOGIN-09 + propose phase audit of `permisos_usuario` |
| R7 | `estado` column nullable → Pydantic serialization issues | LOW | DEC-LOGIN-10 `Literal[...]` + nullable handling at schema level |

---

## 11. Defense in Depth (5 layers — XR6 mirror)

| Layer | Mechanism | Source |
|---|---|---|
| 1 | KD-3 issuer chain (`operador-`+`admin-`) + `audit_read` permission gate | handler Layer 1 |
| 2 | Tenant scope post-V1 (`get_tenant_ctx()`) — operador own-branch, admin cross-branch (DEC-LOGIN-03) | handler Layer 2 |
| 3 | KD-LOGIN-01 SELECT-only (NO UPDATE/DELETE on `Login`) | AST walk `test_login_historico_read_only.py` |
| 4 | Pydantic `extra='forbid'` + UUID required + limit validators + `estado: Literal[...]` | `_Base` |
| 5 | 422/403/400 mapping + `Cache-Control: no-store` | handler Layer 5 |

Typed exception → HTTP mapping: 5 typed errors (`uuid_usuario_invalid`, `cursor_invalid`, `permission_denied`, `tenant_scope_violation`, `internal_error`). pgcode NEVER in response body.

---

## 12. Pre-Flight Verification (15 checks)

| # | Check | Source | Result |
|---|---|---|---|
| 1 | `prod.login` exists | migration 0001:511-523 + models/L_S/login.py:33 | PASS |
| 2 | `prod.usuarios` exists | migration 0001:7-50 + models/V/usuarios.py | PASS |
| 3 | `prod.permisos` exists | migration 0002 | PASS |
| 4 | `prod.permisos_usuario` exists | migration 0001 + 0002 | PASS |
| 5 | Migration head = `0032` | `git log --oneline -1 7cc613f` | PASS |
| 6 | `audit_read` permission seeded | migration 0002:48 | PASS |
| 7 | `login_ls_session_guard` trigger active | migration 0001:2203-2214 | PASS |
| 8 | `login_audit_columns` trigger active | migration 0001:2533-2534 | PASS |
| 9 | `login_set_vigente_inicial` trigger active | migration 0001:2538-2539 | PASS |
| 10 | `login_enqueue_sync` trigger active | migration 0001:2777-2788 | PASS |
| 11 | FK `fk_login_uuid_usuario` exists | migration 0001:1247-1255 | PASS |
| 12 | `_NARROW_UPDATE_LS_TABLES["login"]` whitelist | migration 0021:206 | PASS |
| 13 | `no_store_headers` + `apply_no_store_header` exist | api/v1/_helpers.py:18-31 | PASS |
| 14 | `cursor_encode/cursor_decode` reusable | api/router_factory.py:127-140 | PASS |
| 15 | F1.14 archive completed | `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/` exists | PASS |

**Result**: 15/15 PASS. Pre-flight gate **PASS** (no known-MISSING; MIGRATION 0033 is the index-only add).

**1 KNOWN-MISSING** (will be closed by MIGRATION 0033):
- Composite index `(uuid_usuario, timestamp_evento DESC)` on `prod.login` (DEC-LOGIN-06).

---

## 13. Test Plan (3 files + 1 AST walk + 1 migration test)

- `test_login_historico.py` (~30 LOC, **2 mandated by plan.md line 1149**): empty user (zero `prod.login` rows → 200 with `items=[]` + `next_cursor=None`) / populated user (5 rows → exact DESC ordering + correct `next_cursor` encoded + `estado ∈ {exitoso, fallido, cerrado}` typed).
- `test_login_historico_read_only.py` (~15 LOC, AST walk, KD-LOGIN-01): handler MUST NOT contain `update(Login)` or `delete(Login)` or `await session.commit()` or any raw `text("UPDATE prod.login")`.
- `test_migration_0033_index.py` (~10 LOC, 1 test): index exists after upgrade + DESC order honored on a 100-row probe.

**Note**: `test_login_historico.py` is the **only** file that consumes `prod.login` rows. Existing lockout tests at F1.2 (`test_auth_lockout.py` and siblings — verify via `git grep "def test.*login"` in `tests/unit/`) should NOT regress because F1.15 only adds a SELECT endpoint + an index.

---

## 14. Out of Scope (F2.x+)

UI integration (Fase 11+ consumer) · `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` (HU-F16.1/F16.5 Parte 2) · `?activo=` filter (Parte 2) · `?fecha_desde=&fecha_hasta=` date range filter (F18.1 Parte 2) · login attempt statistics (`COUNT(*)` aggregations, F18.2) · real-time WebSocket subscription to login events (Fase 14+) · admin impersonation "login as user X" (HU-F19.x Parte 2 admin domain) · `?uuid_sucursal=` filter for branch-scoped history (F18.3).

---

## 15. Sync Catalog — pre-flight verification (RESOLVED 2026-09-15)

`prod.login` is **[L-S] branch→cloud** (ER lines 572-573). NO F1.15 sync_catalog seeds needed (the table is replicated via the global catalog replication logic, not per-table). MIGRATION 0033 contains NO `INSERT INTO prod.sync_catalog`.

---

## 16. Proposed Cluster Decomposition (4 clusters)

- **T1**: MIGRATION 0033 `CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento` + pre-flight (~25 LOC)
- **T2**: `repo/login_historico.py` 3 helpers + `schemas/usuarios.py` 3 schemas (~55 LOC)
- **T3**: `GET /usuarios/{uuid}/login` 8-step handler + dedicated router mount (~50 LOC)
- **T4**: 3 test files + 1 AST walk + 1 migration test (~55 LOC)

**Total: ~185 LOC** (production 70 + tests 55 + migration 25 + schemas 25 + helpers 30 — plan's 70 LOC production matches exactly).

---

## 17. Next Recommended Phase

**Phase**: `sdd-propose hu-f1-15-login-historico` (17-section proposal at `openspec/changes/hu-f1-15-login-historico/proposal.md`).

**Pre-propose verification status** (completed 2026-09-15):
1. Static pre-flight 15/15 PASS.
2. Endpoint ownership conflict RESOLVED via DEC-LOGIN-01.
3. Performance index gap identified → MIGRATION 0033 (DEC-LOGIN-06).
4. Anti-enumeration 404 leak RESOLVED via DEC-LOGIN-08.
5. Tenant scope DEC-LOGIN-03 A/B audit deferred to propose phase.
6. Permission gate DEC-LOGIN-09 verification deferred to propose phase (audit `permisos_usuario` grants).
7. Sync catalog out-of-catalog → no entries needed.
8. Parte 2 collision avoided via DEC-LOGIN-07 forward-compatible envelope.

**Key inputs for propose phase**: DEC-LOGIN-01..10 (10 decisions, §9); KD-LOGIN-01..02 (2 invariants); REQ-OPS-102..105 (4 candidate REQs — SELECT-only contract + cursor pagination invariants + empty-user 200 + XR6 REFERENCE); 4-cluster decomposition T1..T4; MIGRATION 0033 REAL DDL (composite index only); permission gate audit (DEC-LOGIN-09).

**Key precedent mirrors** (to cite verbatim in proposal):
- `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/exploration.md` (17-section structure verbatim — this file's template).
- `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`).
- `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'`).
- `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:127-227` (cursor pagination + `{items, next_cursor}` envelope pattern).
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py:79-162` (`list_tarifas_vigentes` — cursor pagination helper precedent).
- `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory — Layer 1 dep).
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx` — Layer 2 dep).
- `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (verbatim ORM model).
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py:511-523` (login table).
- `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py:48` (`audit_read` pre-seeded).

---

**End of exploration.**
