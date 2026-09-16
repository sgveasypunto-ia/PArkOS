# Delta Spec: hu-f1-15-login-historico

> **Change**: `hu-f1-15-login-historico` · **Phase**: spec (sdd-spec) · **HU**: HU-F1.15 — `GET /api/v1/usuarios/{uuid}/login` (KD-3 operador+admin) — histórico paginado por cursor (gap huérfano de auditoría de seguridad, **ÚLTIMA HU de Fase 1 Parte I**)
> **Date**: 2026-09-15 · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `7cc613f`) · **PR target**: `origin/dev`
> **Canonical spec**: REQ-OPS-001..101 + REQ-OPS-XR1..XR6 baseline (post-F1.14 merge at commit `7cc613f`)
> **This delta**: REQ-OPS-102..105 (4 new REQs) — XR6 already exists at `operations/spec.md:3951`; F1.15 REFERENCES it but does NOT create a new XR (per orchestrator mandate)

---

# Delta Spec — HU-F1.15: `GET /api/v1/usuarios/{uuid}/login` (KD-3 operador+admin) — histórico paginado por cursor (gap huérfano de auditoría)

> **Change**: `hu-f1-15-login-historico`
> **Target spec**: `openspec/specs/operations/spec.md` (will append 4 new REQs on archive: REQ-OPS-102..105 — REQ-OPS-XR6 already exists from F1.13 at line 3951)
> **Phase**: spec (sdd-spec)
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F1.15 (Fase-1 prerequisites — backend; **Última HU de Fase 1 Parte I** per `pending.md` row 15 + `plan.md` lines 1137-1155)
> **Inputs**: `openspec/changes/hu-f1-15-login-historico/proposal.md` (~770 LOC, 16 sections, DEC-LOGIN-01..10, KD-LOGIN-01..02, 7 risks R1..R7 — 4 RESOLVED, pre-flight 15/15 PASS), `openspec/changes/hu-f1-15-login-historico/exploration.md` (17 sections, ~770 LOC, DEC-LOGIN-01..10 mandate, R1..R7 risks), `plan.md` lines 1137-1155 (HU-F1.15 definition, 2 atomic tasks T1..T2, 2 tests mandated at line 1149, 70 LOC production budget at line 1151, response shape `{items, next_cursor}` per canonical list contract at line 1154, `estado ∈ {exitoso, fallido, cerrado}` per line 1143 verbatim), `plan.md` line 613 (HU-F1.2 shares `prod.login` as the audit table for lockout writes), `plan.md` lines 7571-7574 (F1 endpoint table row 2391 — duplicate-resource note: Parte 1 F1.15 + Parte 2 F16.1/F16.5 — same resource, built once, shared backend), `plan.md` lines 610-617 (F1.2 story, shares `prod.login`), `modelo_datos_er.mmd` blocks `usuarios` [V] (lines 7-50) + `login` [L-S] (lines 558-573), `migrations/versions/0001_initial_schema.py` lines 511-523 (login table), 1247-1255 (FK `fk_login_uuid_usuario`), 2203-2214 (trigger `login_ls_session_guard`), 2533-2541 (audit+set_vigente_inicial triggers), 2777-2788 (enqueue_sync trigger), `migrations/versions/0002_seed_permisos_canonicos.py` lines 39-56 (`CANONICAL_PERMISOS` includes `audit_read` at line 48 — pre-seeded per DEC-LOGIN-09.B), `migrations/versions/0021_least_privilege_and_immutability_contract.py:206` (`_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")`), `migrations/versions/0032_seed_alert_types_operativos.py` (F1.14 head, Op 2 `audit_read` reuse anchor at line 185), `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (Login ORM, FK `usuarios`), `backend/packages/parkos_core/src/parkos_core/models/V/usuarios.py` (Usuarios ORM), `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:49-146` (`record_login` write helper — F1.15 NEVER calls it; only references the table it writes to), `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py:79-162` (cursor pagination precedent — `ORDER BY vigente_desde DESC, uuid ASC` + `cursor_encode/cursor_decode`), `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:127-227` (factory `list_endpoint` pattern — `next_cursor` encoding + `read_list_schema` shape), `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py:18-31` (`no_store_headers` + `apply_no_store_header` — DEC-LOGIN-05), `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base), `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory — KD-3 dep), `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx` — Layer 2 dep, KD-S2 F1.7 analog), `tests/static/{test_sync_estado_read_only,test_arqueo_handler_single_commit,test_no_raw_dml_on_ls_tables}.py` (AST walk precedents — F1.15 needs the `ls_tables` variant for KD-LOGIN-02), `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 EXISTS from F1.13 — F1.15 references it but does NOT create a new XR), `openspec/specs/operations/spec.md` line 4034-4041 (REQ-OPS-100 empty-branch precedent at F1.14 — DEC-LOGIN-08 mirror), `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/specs/operations/spec.md` (canonical Given/When/Then/And format precedent, 4 REQs REQ-OPS-098..101 + XR6 reference, ~485 LOC — this delta mirrors its structure section-by-section).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `7cc613f`, F1.14 closed) · **PR target**: `origin/dev`.
> **Note on DEC-LOGIN-09.B (permission gate)**: `audit_read` is pre-seeded at `0002_seed_permisos_canonicos.py:48`. F1.15 adopts Option B (reuse `audit_read` — cross-cutting read-only). No patch to existing migration (Option A rejected — would break downstream PRs that depend on exact 16-row count). No scope creep into MIGRATION 0033 (Option C rejected — mixes DDL index with permissions).
> **Note on DEC-LOGIN-03 (tenant scope)**: Propose phase audited F1.7 KD-S2 + F1.13 KD-ARQUEO-08 + REQ-OPS-XR6 Layer 2 precedents and adopted Option A — `operador-` JWT filters `prod.login` rows by `uuid_sucursal = ctx.sucursal_uuid` (own-branch login history only); `admin-` JWT bypasses and sees ALL branches.

---

## Purpose

HU-F1.15 closes the **read-only operator+admin diagnostic endpoint** for the already-shipped `prod.login` [L-S] table (5 business columns `uuid_usuario`, `uuid_sucursal`, `timestamp_evento`, `timestamp_cierre`, `estado ∈ {exitoso, fallido, cerrado}` per `models/L_S/login.py:33-74` + `modelo_datos_er.mmd:558-573`), the `prod.usuarios` [V] table (FK target, `models/V/usuarios.py`), the `prod.permisos` [V] + `prod.permisos_usuario` [V] tables (Layer 1 permission gate), and `prod.sucursal` [V] (Layer 2 tenant scope). The change exposes one read endpoint (`GET /api/v1/usuarios/{uuid}/login`) that performs exactly **1 SELECT query** against `prod.login` (via `repo/login_historico.listar_intentos_paginado`), returning a `LoginHistoricoListResponse(items, next_cursor)` envelope to drive operator/admin diagnostic on lockouts or suspicious access (HU-F1.2 shares `prod.login` per `plan.md` line 613). MIGRATION 0033 (`0033_login_historic_index.py`) is REAL DDL — a composite index `prod.idx_login_uuid_usuario_evento ON prod.login (uuid_usuario, timestamp_evento DESC)` via `CREATE INDEX CONCURRENTLY` (production safety, avoids table lock during index build, mirrors F1.x CONCURRENTLY precedent at `0011_add_seq_lookup_indexes.py:62`). NO data seeds (the table is pre-populated by F1.2 lockout writes via `repo/session_cycle.py:49-146`). NO new permissions (DEC-LOGIN-09.B — `audit_read` reuse only). NO new cross-cutting requirement (XR6 is canonical from F1.13 at `operations/spec.md:3951`; F1.15 references it via REQ-OPS-105).

The 4 new REQ-OPS-NNN (REQ-OPS-102..105) extend the `operational` capability already consolidated in `openspec/specs/operations/spec.md`. REQ-OPS-001..101 + REQ-OPS-XR1..XR6 remain unchanged. **No new XR is created**: REQ-OPS-105 explicitly references the existing F1.13 REQ-OPS-XR6 at `operations/spec.md:3951`.

---

## ADDED Requirements

### REQ-OPS-102 — `GET /api/v1/usuarios/{uuid}/login` SELECT-only contract (KD-LOGIN-01 + KD-LOGIN-02)

**Source**: HU-F1.15 (DEC-LOGIN-01 + DEC-LOGIN-02 + DEC-LOGIN-09.B + KD-LOGIN-01 + KD-LOGIN-02) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler `get_login_historico` in the NEW dedicated router `api/v1/usuarios_login.py` (mounted at FastAPI app-level under `/usuarios` prefix — sibling of `auth.py`, NOT nested in `caja.py` per DEC-LOGIN-01.A separation-of-concerns rationale: `auth.py:69` is POST-mutating-only and adding a GET for login history there would couple read-of-history with the login write path; Parte 2's `api/v1/usuarios.py` will EXTEND this router without collision) MUST be a READ-ONLY endpoint that returns HTTP 200 with body `LoginHistoricoListResponse(items, next_cursor)` per the canonical `{items, next_cursor}` envelope (`api/router_factory.py:227`). The handler MUST execute exactly **1 SELECT query** against `prod.login` via `repo/login_historico.listar_intentos_paginado(session, uuid_usuario, cursor, limit, tenant_ctx)`. The handler MUST NOT execute any `UPDATE`, `INSERT`, or `DELETE` statements on `prod.login` (KD-LOGIN-01 — preserves the `_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` whitelist at `0021_least_privilege_and_immutability_contract.py:206` and the [L-S] immutability invariant). The handler MUST NOT call `await session.commit()` (GET is naturally idempotent). The handler MUST NOT append any row in `prod.log_operaciones` or any `[A]` audit table. The response MUST include `Cache-Control: no-store` (DEC-LOGIN-05, XR6 mirror).

KD-3 issuer chain `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-LOGIN-02 — operador needs own-branch lockout diagnostic; admin needs cross-branch security audit). Permission gate `audit_read` (DEC-LOGIN-09.B, pre-seeded per `0002_seed_permisos_canonicos.py:48` — same audit domain as F1.14's `GET /sync/estado` per F1.14 DEC-SYNC-03.B precedent). Path param `uuid: UUID` (Pydantic validator; required). Query params `limit: int = 10` (ge=1, le=100 validators per DEC-LOGIN-04) + `cursor: str | None = None`. Response items MUST be ordered by `timestamp_evento DESC, uuid ASC` (most recent first per `plan.md` line 1143 verbatim). Each item MUST have exactly 5 fields: `uuid` (UUID), `timestamp_evento` (ISO 8601 naive UTC datetime), `timestamp_cierre` (ISO 8601 naive UTC datetime or null), `estado` (`Literal["exitoso", "fallido", "cerrado"]` — the REAL [L-S] lifecycle value per DEC-LOGIN-10; NEVER a synthetic boolean `activo`), `uuid_sucursal` (UUID or null).

**Rationale**: Operator/admin diagnostic on "why is user X locked out" or "did user Y just authenticate" is the gap huérfano per `plan.md` line 1139 + `pending.md` row 15. F1.15 surfaces this without adding a UI surface (UI deferred to Fase 11+). The dedicated router resolves the Parte 1 vs Parte 2 endpoint-ownership conflict (DEC-LOGIN-01 — both F1.15 and HU-F16.1/F16.5 propose the same URL per `plan.md` lines 7571-7574; F1.15 ships the minimal slice, Parte 2 extends). KD-LOGIN-02 AST walk `tests/static/test_login_historico_read_only.py` enforces the read-only invariant at static-parse time — defense in depth against accidental drift to a write path. Mirrors the F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 + F1.14 KD-SYNC-02 pattern.

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:69` (POST-mutating-only rationale for DEC-LOGIN-01.A — dedicated router); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — DEC-LOGIN-05); `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (verbatim ORM model — 5 business columns + FK + audit mixin); `backend/packages/parkos_core/src/parkos_core/models/V/usuarios.py` (Usuarios ORM — F1.15 reads `uuid` only for optional existence check); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:49-146` (`record_login` write helper — F1.15 NEVER calls it; only references the table it writes to); `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py:79-162` (cursor pagination precedent — `list_tarifas_vigentes`); `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:127-227` (cursor pagination + `{items, next_cursor}` envelope pattern — DEC-LOGIN-04 + DEC-LOGIN-07); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 511-523 (login table), 2203-2214 (`login_ls_session_guard` trigger), 2533-2541 (audit+set_vigente_inicial triggers), 2777-2788 (`login_enqueue_sync` trigger — none fire on F1.15's read path); `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py:206` (`_NARROW_UPDATE_LS_TABLES["login"]` whitelist — KD-LOGIN-02 enforces); `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py:48` (`audit_read` pre-seeded — DEC-LOGIN-09.B); `tests/static/{test_sync_estado_read_only,test_arqueo_handler_single_commit,test_no_raw_dml_on_ls_tables}.py` (AST walk precedents); F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 + F1.14 KD-SYNC-02 (AST walk precedents for KD-LOGIN-02).

**Scenario 1: Happy path — populated user returns 200 with exact DESC ordering**
- **Given** a KD-3 issuer session (`operador-` or `admin-` JWT) with `audit_read` permission granted via `prod.permisos_usuario`
- **And** a path `uuid` (valid Pydantic UUID format) that has 5 rows in `prod.login` with `timestamp_evento` spanning 60-300 seconds before NOW() and mixed `estado ∈ {exitoso, fallido, cerrado}`
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked with `limit=10` and no cursor
- **Then** the handler MUST execute exactly **1 SELECT query** against `prod.login` via `repo/login_historico.listar_intentos_paginado`
- **And** MUST NOT execute any `UPDATE`, `INSERT`, or `DELETE` on `prod.login` (KD-LOGIN-01)
- **And** MUST NOT call `await session.commit()`
- **And** the response MUST be `200 OK` with `Cache-Control: no-store` and body `LoginHistoricoListResponse{items: [5 LoginIntentoItem], next_cursor: <base64-encoded JSON of last item's (timestamp_evento, uuid) pair>}`
- **And** the 5 items MUST be ordered by `(timestamp_evento DESC, uuid ASC)` (most recent first per `plan.md` line 1143 verbatim).

**Scenario 2: Empty user (zero rows) — 200 with `items=[]`, NEVER 404**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` (valid Pydantic UUID) that has **ZERO** rows in `prod.login` (either the user does not exist OR exists but never authenticated)
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked
- **Then** the response MUST be `200 OK` (NOT 404 — anti-enumeration per DEC-LOGIN-08, mirroring F1.2 R-F1.2-10 / R-F1.2-11 rationale)
- **And** the body MUST be `LoginHistoricoListResponse{items: [], next_cursor: null}`
- **And** the response MUST carry `Cache-Control: no-store`.

**Scenario 3: Cursor pagination — second page resumes EXACTLY at the next boundary**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` with 12 rows in `prod.login` ordered by `(timestamp_evento DESC, uuid ASC)`
- **And** the first page (no cursor) returned 10 items + a non-null `next_cursor` (the base64-encoded JSON of item #10's `(timestamp_evento, uuid)` pair per `router_factory.py:185-200`)
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?limit=10&cursor=<that next_cursor>`
- **Then** the handler MUST execute the `WHERE` clause `(timestamp_evento < cursor_ts) OR (timestamp_evento = cursor_ts AND uuid > cursor_uuid)` (DEC-LOGIN-04 mirror of `api/router_factory.py:185-200`)
- **And** MUST return EXACTLY the remaining 2 items in DESC order — no row repeated, no row skipped
- **And** `next_cursor` MUST be `null` (last page).

**Scenario 4: AST walk — handler source contains NO `update`/`delete` on `Login` and NO `commit`**
- **Given** the source file `api/v1/usuarios_login.py` containing `get_login_historico` handler
- **When** `tests/static/test_login_historico_read_only.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert ZERO occurrences of `update(Login)` or `delete(Login)` or `session.execute(text("UPDATE prod.login"))` or `session.execute(text("DELETE FROM prod.login"))` in the handler body (KD-LOGIN-01 + KD-LOGIN-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body (GET is naturally commit-free).

---

### REQ-OPS-103 — Cursor pagination invariants + empty-user contract (DEC-LOGIN-04 + DEC-LOGIN-07 + DEC-LOGIN-08 + DEC-LOGIN-10)

**Source**: HU-F1.15 (DEC-LOGIN-04 + DEC-LOGIN-07 + DEC-LOGIN-08 + DEC-LOGIN-10) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given a successful or empty-user response from `GET /api/v1/usuarios/{uuid}/login`, the response shape MUST enforce the following invariants:

- **Ordering**: Items MUST be ordered by `(timestamp_evento DESC, uuid ASC)`. The `DESC` matches `plan.md` line 1143 verbatim ("los intentos más recientes primero"); the `uuid ASC` secondary key is the canonical tie-breaker for same-second INSERTs (e.g., F1.2 lockout writes batch multiple failed attempts at the same instant — pagination correctness requires the tie-breaker).
- **Cursor encoding**: `next_cursor` MUST encode the LAST item's `(timestamp_evento_iso, uuid_str)` pair as base64-encoded JSON (mirrors `api/router_factory.py:127-140` verbatim — `cursor_encode`/`cursor_decode` helpers reused). The `next_cursor` field MUST be `null` iff there are NO more rows after the current page (handler uses `LIMIT N+1` then slices to N to detect presence — DEC-LOGIN-04 mirror of `router_factory.py:185-200`).
- **Limit bounds**: `limit: int = 10` (default per `plan.md` line 1143 verbatim) with Pydantic validators `ge=1, le=100`. Out-of-range values MUST raise 422 before the handler body runs.
- **Item shape**: Each `LoginIntentoItem` MUST have exactly 5 fields, with no extras: `uuid` (UUID, required), `timestamp_evento` (ISO 8601 naive UTC datetime, required), `timestamp_cierre` (ISO 8601 naive UTC datetime or `null`, nullable for open sessions), `estado` (`Literal["exitoso", "fallido", "cerrado"]` — DEC-LOGIN-10 — the REAL [L-S] lifecycle value, NEVER a synthetic boolean `activo`), `uuid_sucursal` (UUID or `null`, nullable FK to `prod.sucursal`).
- **Envelope**: `LoginHistoricoListResponse{items: list[LoginIntentoItem], next_cursor: str | None}`. NO `activo`, NO `count`, NO `total`, NO `has_more` in F1.15 — the canonical `{items, next_cursor}` shape per `router_factory.py:227` is forward-compatible with Parte 2's HU-F16.1/F16.5 added filtros (`?activo=`) and closure action (`POST /usuarios/{uuid}/login/{login_uuid}/cerrar`) without breaking F1.15's response (DEC-LOGIN-07).
- **Empty-user contract**: ZERO `prod.login` rows for the requested `uuid` MUST return `200 OK` with `items=[]` and `next_cursor=null` — NEVER `404` (DEC-LOGIN-08 anti-enumeration). Mirrors F1.2 R-F1.2-10 / R-F1.2-11 rationale: returning `404` for an unknown `uuid_usuario` would let an attacker enumerate valid user UUIDs by comparing `404` vs `200`. F1.15 returns `200` with empty items regardless of whether the user exists, has zero login rows, or has only cross-branch rows (operador Layer 2 filter — DEC-LOGIN-03.A returns no rows → `items=[]`).
- **Malformed cursor**: A `cursor` value that fails base64 decode or fails JSON parse or is missing the `timestamp_evento` / `uuid` keys or has invalid types MUST return `400 Bad Request` with body `{"error": "cursor_invalid"}` and `Cache-Control: no-store`. NEVER `500` (typed exception handler converts decode errors to `CursorInvalidError`).
- **Cache-Control**: EVERY response (200, 400, 403, 422) MUST carry `Cache-Control: no-store` (DEC-LOGIN-05). XR6 Layer 5 mirror from F1.10..F1.14.
- **Pydantic redaction**: Response body MUST NEVER include `pgcode`, `pgerror`, `pgmessage`, or any PostgreSQL error internals. `extra='forbid'` (inherited from `schemas/common.py::_Base`) blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`, `activo`.

**Rationale**: Stable cursor pagination under concurrent INSERTs (F1.2 lockout writes from `record_login` may add rows during pagination — cursor pagination tolerates this; offset pagination would shift rows). The 3-value `estado` domain is the canonical truth per `plan.md` line 1143 verbatim; introducing a synthetic `activo` boolean would create a derived field that requires UI to interpret (`activo=True` → `cerrado OR exitoso`?). The anti-enumeration `200 + items=[]` contract prevents user UUID discovery via response code differential analysis.

**Source**: `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:127-140` (`cursor_encode` / `cursor_decode` / `Cursor` dataclass — DEC-LOGIN-04 reuse); `api/router_factory.py:185-200` (LIMIT N+1 + slice-to-N next_cursor detection — DEC-LOGIN-04 mirror); `api/router_factory.py:227` (`{items, next_cursor}` envelope — DEC-LOGIN-07); `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py:79-162` (cursor pagination helper precedent — `ORDER BY vigente_desde DESC, uuid ASC`); `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (verbatim ORM model — 5 business columns + state enum); `backend/packages/parkos_core/src/parkos_core/auth.py:239-246` (`fallido`), `:260-266` (`exitoso`), `:352-393` (`cerrado`) — `estado` lifecycle sources; `plan.md` line 1143 verbatim ("cada uno con su `estado` real (`exitoso|fallido|cerrado`) — nunca un campo booleano `activo`, que no existe en el dominio real de `login.estado`"); `plan.md` lines 7571-7574 (Parte 2 forward-compatibility — DEC-LOGIN-07); DEC-LOGIN-08 (anti-enumeration rationale mirrors F1.2 R-F1.2-10 / R-F1.2-11); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base).

**Scenario 1: `limit + cursor` pagination — `next_cursor` non-null iff more rows exist**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` with EXACTLY 15 rows in `prod.login` ordered by `(timestamp_evento DESC, uuid ASC)`
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?limit=10`
- **Then** the response MUST contain AT MOST 10 items
- **And** MUST include a non-null `next_cursor` (base64 JSON of the 10th item's `(timestamp_evento, uuid)` pair — DEC-LOGIN-04 LIMIT N+1 detection)
- **And** MUST include `Cache-Control: no-store`.

**Scenario 2: Cursor resume — subsequent page resumes EXACTLY at the next `(timestamp_evento, uuid)` boundary**
- **Given** the response from Scenario 1: 10 items + `next_cursor=C1`
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?limit=10&cursor=C1`
- **Then** the handler MUST execute the `WHERE` clause `(timestamp_evento < cursor_ts) OR (timestamp_evento = cursor_ts AND uuid > cursor_uuid)`
- **And** MUST return EXACTLY 5 items (the remaining rows)
- **And** MUST include `next_cursor=null` (last page)
- **And** NO row from the first page MUST be repeated; NO row from the 15 total MUST be skipped.

**Scenario 3: Empty user (zero rows) — 200 with `items=[]`, NEVER 404**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` (valid Pydantic UUID) that has ZERO `prod.login` rows
- **When** the handler is invoked (with or without `limit`/`cursor`)
- **Then** the response MUST be `200 OK` with `items=[]` and `next_cursor=null`
- **And** MUST NEVER be `404 Not Found` (anti-enumeration per DEC-LOGIN-08)
- **And** MUST carry `Cache-Control: no-store`.

**Scenario 4: Malformed cursor — 400 with `cursor_invalid`, NEVER 500**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` with rows in `prod.login`
- **When** the client invokes `GET /api/v1/usuarios/{uuid}/login?cursor=<malformed>` (e.g., not base64, base64 of `{}`, base64 of `{"timestamp_evento": "garbage"}`)
- **Then** the response MUST be `400 Bad Request` with body `{"error": "cursor_invalid"}`
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NEVER be `500 Internal Server Error` (typed exception handler converts decode errors to `CursorInvalidError`).

---

### REQ-OPS-104 — Empty-user 200 response + response-time parity + anti-enumeration (DEC-LOGIN-08)

**Source**: HU-F1.15 (DEC-LOGIN-08) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When `prod.login` contains ZERO rows for the requested path `uuid` (regardless of whether the user exists in `prod.usuarios`, has zero login rows, or has only rows from branches the operador cannot see via the Layer 2 filter per DEC-LOGIN-03.A), the handler `get_login_historico` MUST return `200 OK` with body `LoginHistoricoListResponse{items: [], next_cursor: null}` and `Cache-Control: no-store` — NEVER `404 Not Found`. The response time MUST be identical (within ±5%) to a populated-user query on the same `uuid` (no extra DB roundtrip for a separate `prod.usuarios` existence check; the FK existence of zero `prod.login` rows IS the existence check).

The audit log MUST record the attempt (KD-LOGIN-02 SELECT-only still permits structured log emission for security audit; the handler MUST NOT log `prod.login` rows themselves — only the request metadata: actor UUID, target UUID, timestamp, response size). The pgcode / internal error code MUST NEVER appear in the response body, headers, or info+ logs (XR6 Layer 5 redaction).

**Rationale**: Same rationale as F1.2 `GET /auth/me` R-F1.2-10 + R-F1.2-11 (anti-enumeration by response code differential). Returning `404` for an unknown `uuid_usuario` would let an attacker enumerate valid user UUIDs by comparing `404` vs `200`. The response-time parity constraint prevents a SECOND enumeration vector: an attacker who measures response time could distinguish "user exists but zero rows" from "user does not exist" if the handler issued an extra DB roundtrip for an existence check. By relying on the FK existence of zero `prod.login` rows as the implicit existence check, the handler runs exactly the same query (1 SELECT) for both cases, and the response time is identical. KD-LOGIN-02 AST walk still applies to the empty path (no UPDATE/DELETE/COMMIT).

**Source**: F1.2 R-F1.2-10 / R-F1.2-11 (anti-enumeration rationale — `openspec/specs/operations/spec.md` REQ-OPS-029 mirror); `openspec/specs/operations/spec.md` line 4034-4041 (REQ-OPS-100 empty-branch precedent at F1.14 — DEC-LOGIN-08 mirror); `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (Login ORM FK to `prod.usuarios`); `backend/packages/parkos_core/src/parkos_core/models/V/usuarios.py` (Usuarios ORM — F1.15 reads `uuid` only for optional existence check; SKIPPED per DEC-LOGIN-08); KD-LOGIN-02 AST walk `tests/static/test_login_historico_read_only.py` (extends to the empty path).

**Scenario 1: Zero rows for an EXISTING user (user exists but never authenticated) — 200 with `items=[]`**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` that EXISTS in `prod.usuarios` (FK row present) but has ZERO rows in `prod.login`
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked
- **Then** the response MUST be `200 OK` with `LoginHistoricoListResponse{items: [], next_cursor: null}`
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NOT be `404 Not Found` (the user exists; this is a zero-data response, not a missing-resource response).

**Scenario 2: Zero rows for an UNKNOWN user (anti-enumeration) — 200 indistinguishable from Scenario 1**
- **Given** a KD-3 issuer session with `audit_read` permission
- **And** a path `uuid` that does NOT exist in `prod.usuarios` (FK row absent) AND has ZERO rows in `prod.login`
- **When** the handler `GET /api/v1/usuarios/{uuid}/login` is invoked
- **Then** the response MUST be `200 OK` with `LoginHistoricoListResponse{items: [], next_cursor: null}`
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NOT be `404 Not Found` (anti-enumeration — same response shape as Scenario 1 prevents UUID discovery).

**Scenario 3: Response time parity — zero-row response time within ±5% of populated-row response time**
- **Given** two identical KD-3 issuer sessions with `audit_read` permission
- **And** path `uuid_a` with ZERO `prod.login` rows
- **And** path `uuid_b` with 100 `prod.login` rows
- **When** both handlers are invoked with the same `limit=10` query
- **Then** the wall-clock response time for `uuid_a` MUST be within ±5% of the response time for `uuid_b` (no extra DB roundtrip for `prod.usuarios` existence check — DEC-LOGIN-08 evidence-of-no-distinguishable-side-channel)
- **And** the audit log MUST record the attempt for BOTH requests (actor UUID, target UUID, timestamp, response size)
- **And** the audit log MUST NOT include the `prod.login` row contents themselves (KD-LOGIN-02 SELECT-only invariant extends to log emission).

---

### REQ-OPS-105 — XR6 cross-cutting defense in depth (REFERENCE to existing REQ-OPS-XR6)

**Source**: HU-F1.15 (DEC-LOGIN-01 + DEC-LOGIN-02 + DEC-LOGIN-03 + DEC-LOGIN-05 + DEC-LOGIN-09.B + KD-LOGIN-02) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Given that REQ-OPS-XR6 already exists at `openspec/specs/operations/spec.md:3951` from F1.13, F1.15's `GET /api/v1/usuarios/{uuid}/login` endpoint MUST satisfy all 5 defense-in-depth layers defined in REQ-OPS-XR6, applied as follows:

- **Layer 1 (KD-3 issuer chain + permission gate)** — NEW dedicated router `api/v1/usuarios_login.py` declares `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-LOGIN-02 — same KD-3 chain as F1.14 `sync_estado.py`). Permission gate is `audit_read` (DEC-LOGIN-09.B, pre-seeded per `0002_seed_permisos_canonicos.py:48`). Operador with `audit_read` reads own-branch login history (DEC-LOGIN-03.A); admin cross-branch.
- **Layer 2 (Tenant scope post-V1)** — After resolving `ctx.sucursal_uuid` from the JWT, if `ctx.issuer_prefix == "operador-"` AND `tenant_ctx.sucursal_uuid is not None`, the SQL query MUST be filtered by `login.uuid_sucursal = ctx.sucursal_uuid` at the SQL layer (DEC-LOGIN-03.A — own-branch audit history only). Cross-branch login history is implicitly NOT returned to operador (no rows match the filter → `items=[]`). Admin (`admin-`) bypasses Layer 2 and sees ALL branches. KD-S2 analog from F1.7. The filter is applied at SQL layer via `repo/login_historico.listar_intentos_paginado` — NOT a Python-side post-filter (which would leak row metadata).
- **Layer 3 (KD-LOGIN-01 SELECT-only + KD-LOGIN-02 read-only AST walk)** — The handler invokes ONLY the 1 typed SELECT helper from `repo/login_historico.py` (read-only path). The AST walk `tests/static/test_login_historico_read_only.py` enforces NO `session.execute(update(Login))`, `session.execute(delete(Login))`, `session.execute(text("UPDATE prod.login"))`, `session.execute(text("DELETE FROM prod.login"))`, and NO `await session.commit()` in the handler body. Mirrors F1.10 REQ-OPS-XR1 + F1.11 REQ-OPS-XR4 + F1.12 REQ-OPS-XR5 + F1.13 REQ-OPS-XR6 + F1.14 KD-SYNC-02.
- **Layer 4 (Pydantic `extra='forbid'` + UUID required + `Literal[estado]` + limit validators)** — `LoginHistoricoQueryParams(_Base)` + `LoginIntentoItem(_Base)` + `LoginHistoricoListResponse(_Base)` inherit `extra='forbid'` from `schemas/common.py::_Base` (blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`, `activo`). `uuid: UUID` is required (Pydantic validator, 422 on malformed). `estado: Literal["exitoso", "fallido", "cerrado"]` enforces the 3-value domain at the type level (DEC-LOGIN-10). `limit: int = 10` with `ge=1, le=100` validators (DEC-LOGIN-04). `cursor: str | None = None` (base64-encoded JSON from previous page's next_cursor).
- **Layer 5 (Handler 200/422/403/400 mapping + `Cache-Control: no-store`)** — Every response (200 + 4xx + 5xx) on `GET /api/v1/usuarios/{uuid}/login` carries `Cache-Control: no-store`. Success: `apply_no_store_header(response)`. Error: `HTTPException(headers=no_store_headers())`. Typed exceptions map as follows: `UuidUsuarioInvalidError` → 422 `uuid_usuario_invalid` (Pydantic validator, Layer 4); `CursorInvalidError` → 400 `cursor_invalid` (base64 decode failure, Layer 4); `TenantScopeViolationError` → 403 `tenant_scope_violation` (handler Layer 2, enforced via SQL filter — DEC-LOGIN-03.A); `PermissionDeniedError` → 403 `permission_denied` (`require_permission` Layer 1). The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

F1.15 MUST NOT create a new cross-cutting requirement (XR). REQ-OPS-XR6 is canonical and applies to F1.15 by reference. `openspec/changes/hu-f1-15-login-historico/design.md` §13 (Cross-Cutting Requirements) MUST reference REQ-OPS-XR6 and the 5 layer mapping above. `openspec/changes/hu-f1-15-login-historico/tasks.md` §10 (Test Plan) MUST include the `test_login_historico_read_only.py` AST walk as a Layer 3 verification step.

**Rationale**: XR6 is the canonical defense-in-depth contract for cross-cutting concerns. Creating a new XR (XR7) for F1.15 would duplicate the 5-layer contract and fragment the review surface. By referencing XR6, F1.15 inherits the testable invariants (AST walks, `extra='forbid'`, `Cache-Control: no-store`, KD-3 issuer chain, permission gate) without redefining them. Each layer is independently testable; failure of any one layer is contained by the other four (defense in depth principle). The Layer 2 SQL-side filter (DEC-LOGIN-03.A) prevents operator cross-branch data leaks while preserving the same canonical response shape as admin — no client-side discriminator needed.

**Source**: `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 canonical from F1.13); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header` — Layer 5 helper); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base); `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory — Layer 1 dep); `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx` — Layer 2 dep); F1.7 KD-S2 (Layer 2 precedent); F1.9 REQ-OPS-058 (factura_pagos immutability); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); F1.12 REQ-OPS-XR5 (5-layer defense precedent); F1.13 REQ-OPS-XR6 (caja-specific 5-layer defense precedent at `operations/spec.md:3951`); F1.14 KD-SYNC-02 (read-only AST walk precedent for `sync_estado`); `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py:48` (`audit_read` pre-seeded — DEC-LOGIN-09.B Layer 1 anchor).

**Scenario 1: operador with `audit_read` + own branch — 200 OK (Layer 1 + Layer 2 PASS)**
- **Given** an operador role granted `audit_read` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching at least one `prod.login.uuid_sucursal` for the requested `uuid`
- **When** the operador invokes `GET /api/v1/usuarios/{uuid}/login?limit=10`
- **Then** Layer 1 MUST pass (KD-3 issuer `operador-` accepted + `audit_read` permission granted)
- **And** Layer 2 MUST pass (own-branch SQL filter `login.uuid_sucursal = ctx.sucursal_uuid` — DEC-LOGIN-03.A)
- **And** Layer 3 MUST execute exactly 1 SELECT query against `prod.login` (KD-LOGIN-01)
- **And** Layer 4 MUST validate the Pydantic schema (`uuid` is a valid UUID, no extra fields)
- **And** Layer 5 MUST return `200 OK` with `Cache-Control: no-store`.

**Scenario 2: operador with `audit_read` + NO own-branch rows (cross-branch only) — 200 with `items=[]` (Layer 2 filter applied at SQL layer)**
- **Given** an operador role granted `audit_read` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`)
- **And** the requested `uuid` has `prod.login` rows ONLY in branches DIFFERENT from `:s_other` (no `uuid_sucursal = :s_other` matches)
- **When** the operador invokes `GET /api/v1/usuarios/{uuid}/login`
- **Then** Layer 1 MUST pass (issuer + permission OK)
- **And** Layer 2 MUST apply the SQL filter `login.uuid_sucursal = :s_other` — NO cross-branch rows returned
- **And** the response MUST be `200 OK` with `LoginHistoricoListResponse{items: [], next_cursor: null}` (anti-enumeration, DEC-LOGIN-08)
- **And** MUST carry `Cache-Control: no-store`
- **And** MUST NOT be `403 tenant_scope_violation` (the user exists; only the branch filter excludes the rows — same as the empty-user contract).

**Scenario 3: operador with `audit_read` DENIED (no permission grant) — 403 `permission_denied` (Layer 1 short-circuits)**
- **Given** an operador role WITHOUT `audit_read` permission (only `emitir_factura` granted)
- **When** the operador invokes `GET /api/v1/usuarios/{uuid}/login`
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first)
- **And** NO DB queries MUST execute (handler body unreachable).

**Scenario 4: admin with `audit_read` — 200 OK with cross-branch rows (Layer 2 bypassed)**
- **Given** an admin role granted `audit_read` permission via `prod.permisos_usuario`
- **And** the requested `uuid` has `prod.login` rows across MULTIPLE branches
- **When** the admin invokes `GET /api/v1/usuarios/{uuid}/login`
- **Then** Layer 1 MUST pass (KD-3 issuer `admin-` accepted + `audit_read` permission granted)
- **And** Layer 2 MUST be bypassed (admin bypasses the `uuid_sucursal` filter per DEC-LOGIN-03.A — sees ALL branches)
- **And** the response MUST be `200 OK` with all rows from all branches in `(timestamp_evento DESC, uuid ASC)` order
- **And** MUST carry `Cache-Control: no-store`.

**Scenario 5: All responses (200 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `GET /api/v1/usuarios/{uuid}/login` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `200 OK`
- **And** MUST be present on `400 cursor_invalid` / `403 tenant_scope_violation` / `403 permission_denied` / `422 uuid_usuario_invalid`
- **And** MUST be present on any uncaught 5xx (defense in depth)
- **And** the response body MUST NOT contain `pgcode`, `pgerror`, or `pgmessage` keys (XR6 Layer 5 redaction).

**Scenario 6: Read-only AST walk — handler source contains ZERO UPDATE/DELETE on `Login` and ZERO `commit`**
- **Given** the source file `api/v1/usuarios_login.py` containing `get_login_historico`
- **When** `tests/static/test_login_historico_read_only.py` runs
- **Then** the AST walk MUST assert ZERO occurrences of `update(Login)` or `delete(Login)` or `session.execute(text("UPDATE prod.login"))` or `session.execute(text("DELETE FROM prod.login"))` in the handler body (KD-LOGIN-01 + KD-LOGIN-02)
- **And** MUST assert ZERO occurrences of `await session.commit()` in the handler body (GET is naturally commit-free).

---

## Cross-Cutting Requirements

F1.15 applies the existing F1.10..F1.13 XR1..XR6 defense-in-depth pattern by REFERENCE (no new XR created):

- **REQ-OPS-XR1 (mirror F1.10)** — KD-3 issuer chain `requires_issuer("operador-", "admin-")` on dedicated `usuarios_login.py` router (DEC-LOGIN-02). NOT in F1.15's `auth.py` to preserve the POST-mutating-only separation of concerns (DEC-LOGIN-01.A — `auth.py:69` line).

- **REQ-OPS-XR2 (mirror F1.10..F1.14)** — `Cache-Control: no-store` header on all responses from `GET /api/v1/usuarios/{uuid}/login` (200, 400, 403, 422, 5xx). Helpers from `api/v1/_helpers.py` lines 18-31 reused verbatim (DEC-LOGIN-05).

- **REQ-OPS-XR3 (mirror F1.10..F1.14)** — READ-ONLY invariant: NO `INSERT`/`UPDATE`/`DELETE` on `prod.login` from the handler. AST walk `tests/static/test_login_historico_read_only.py` enforces the invariant for `get_login_historico` (KD-LOGIN-02). Mirrors F1.10 KD-FE-01 + F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 + F1.13 KD-ARQUEO-01 + F1.14 KD-SYNC-01 AST walk precedent.

- **REQ-OPS-XR4 (mirror F1.11..F1.13)** — Read-only invariant on `[L-S]` tables (the read endpoint MUST NOT touch `[L-S]` tables at all — stronger than F1.11's "insert-only" wording for `[A]` tables). NO `INSERT`/`UPDATE`/`DELETE` on `prod.login` or any other `[L-S]` table outside `repo/login_historico.py` SELECT helpers. The `_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` whitelist at `0021_least_privilege_and_immutability_contract.py:206` only allows UPDATE of those 2 columns via `repo/session_cycle.py::record_login`; F1.15 reads existing rows only.

- **REQ-OPS-XR5 (mirror F1.12..F1.13)** — NEW `KD-LOGIN-02` AST walk `tests/static/test_login_historico_read_only.py` — enforces that `get_login_historico` is READ-ONLY (NO UPDATE/DELETE on `Login`, NO `await session.commit()`). Mirrors `test_sync_estado_read_only.py` shape from F1.14.

- **REQ-OPS-XR6 (REFERENCE — already exists from F1.13 at `operations/spec.md:3951`)** — F1.15's 5-layer defense-in-depth contract: KD-3 issuer chain + `audit_read` permission gate (Layer 1) + tenant scope post-V1 with SQL-side filter for operador own-branch (Layer 2 — DEC-LOGIN-03.A) + KD-LOGIN-01 SELECT-only + KD-LOGIN-02 read-only AST walk (Layer 3) + Pydantic `extra='forbid'` + UUID required + `Literal[estado]` + limit validators (Layer 4) + handler 200/422/403/400 mapping + `Cache-Control: no-store` (Layer 5). F1.15 references REQ-OPS-XR6 by inclusion (5 layers applied verbatim, see REQ-OPS-105) — NO new XR created.

---

## MODIFIED Requirements

None (F1.15 is purely additive; no existing REQ modified).

---

## REMOVED Requirements

None.

---

## Out of Scope

- **UI integration (Fase 11+ consumer)** — no Fase-2/Fase-3 screen depends on this endpoint today (`plan.md` line 1139 verbatim: "Desbloquea: ninguna pantalla obligatoria de esta parte"). If a future operator diagnostic UI surfaces this data, it lives in Fase 11+ consumer scope.
- **`POST /usuarios/{uuid}/login/{login_uuid}/cerrar`** (HU-F16.1/F16.5 Parte 2) — closure action on a single login row. Parte 2 owns. F1.15 is read-only.
- **`?activo=` filter** (Parte 2 F16.1/F16.5) — `activo` does not exist in `prod.login.estado` domain per `plan.md` line 1143. Parte 2 may introduce this synthetic derived field if their UI requires it.
- **`?fecha_desde=&fecha_hasta=` date range filter** (F18.1 Parte 2) — out of F1.15 scope; future addition.
- **Login attempt statistics (`COUNT(*)` aggregations)** — F18.2 Parte 2.
- **Real-time WebSocket subscription to login events** (Fase 14+) — Fase 14 owns push-based notifications.
- **Admin impersonation "login as user X"** — HU-F19.x Parte 2 admin domain, out of F1.15 scope.
- **`?uuid_sucursal=` filter for branch-scoped history** — F18.3 Parte 2. F1.15 applies the Layer 2 filter server-side (DEC-LOGIN-03.A) — operador NEVER sees cross-branch data via a query param.

---

## Definition of Done (entire HU-F1.15)

- [ ] NEW dedicated router `api/v1/usuarios_login.py` (~50 LOC) mounted at FastAPI app-level under `/usuarios` prefix (DEC-LOGIN-01.A — sibling of `auth.py`, NOT nested in `caja.py`).
- [ ] `GET /api/v1/usuarios/{uuid}/login` handler with 8-step chain (Steps 1-8) covering REQ-OPS-102 + REQ-OPS-103 + REQ-OPS-104 + REQ-OPS-105 contracts.
- [ ] NEW `repo/login_historico.py` (~30 LOC) with helpers `listar_intentos_paginado`, `encode_next_cursor`, `decode_cursor_or_none` (all SELECT-only).
- [ ] NEW `schemas/usuarios.py` (~25 LOC) with `LoginHistoricoQueryParams` + `LoginIntentoItem` + `LoginHistoricoListResponse` (canonical `{items, next_cursor}` envelope per `router_factory.py:227`).
- [ ] MIGRATION 0033 applied: REAL DDL composite index — Op 0 pre-flight DO $$ + Op 1 `CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento ON prod.login (uuid_usuario, timestamp_evento DESC)`.
- [ ] All 4 new REQ-OPS-102..105 implemented + verified.
- [ ] REQ-OPS-XR6 5-layer defense + 1 new AST walk PASS (no new XR created).
- [ ] ~5 test files + 1 AST walk + 1 migration test PASS:
  - `tests/unit/test_login_historico.py` (~30 LOC, **2 tests mandated by `plan.md` line 1149**)
  - `tests/unit/test_login_historico_repo.py` (~15 LOC, 3 helpers)
  - `tests/static/test_login_historico_read_only.py` (~15 LOC, KD-LOGIN-02 AST walk)
  - `tests/integration/test_migration_0033_index.py` (~10 LOC, 1 test)
- [ ] `Cache-Control: no-store` verified on 200 / 400 / 403 / 422 / 5xx responses.
- [ ] KD-LOGIN-01 SELECT-only invariant verified per handler via AST walk.
- [ ] KD-LOGIN-02 read-only invariant verified per handler via AST walk (NO UPDATE/DELETE/COMMIT).
- [ ] Tenant scope post-V1 verified (operador own-branch SQL filter; cross-branch rows NOT returned).
- [ ] Permission gate verified (`audit_read` granted → 200, denied → 403 `permission_denied`).
- [ ] Empty-user contract verified (zero rows → 200 with `items=[]` + `next_cursor=null`, NOT 404).
- [ ] Cursor pagination invariants verified (next_cursor non-null iff more rows; resume at exact boundary; malformed cursor → 400).
- [ ] Response-time parity verified (empty-user within ±5% of populated-user — anti-enumeration side-channel).
- [ ] MIGRATION 0033 composite index verified (`pg_indexes` catalog + DESC order honored on 100-row probe).
- [ ] No new permission seeded (DEC-LOGIN-09.B — `audit_read` reuse only).
- [ ] No AI attribution in commits (no `Co-authored-by:`, no AI trailers).

---

## References

- `openspec/changes/hu-f1-15-login-historico/proposal.md` (~770 LOC, 16 sections, DEC-LOGIN-01..10, KD-LOGIN-01..02, 7 risks R1..R7 — 4 RESOLVED at propose phase)
- `openspec/changes/hu-f1-15-login-historico/exploration.md` (17 sections, ~770 LOC, R1..R7 risks, pre-flight 15/15 PASS, DEC-LOGIN-03 audit resolved Option A, DEC-LOGIN-09 audit resolved Option B)
- `plan.md` lines 1137-1155 (HU-F1.15 definition, 2 atomic tasks T1..T2, 2 tests mandated at line 1149, 70 LOC production budget at line 1151, response shape `{items, next_cursor}` at line 1154, `estado ∈ {exitoso, fallido, cerrado}` per line 1143 verbatim)
- `plan.md` lines 7571-7574 (F1 endpoint table row 2391 — duplicate-resource note: Parte 1 F1.15 + Parte 2 F16.1/F16.5 — same resource, built once, shared backend; recommendation to build as part of Parte 2 router `usuarios.py`)
- `plan.md` lines 610-617 (F1.2 story, shares `prod.login` as the audit table for lockout writes)
- `plan.md` line 2391 (F1 endpoint table — `GET /usuarios/{uuid}/login` proposed by Parte 1 AND Parte 2 — DEC-LOGIN-01 + DEC-LOGIN-07)
- `modelo_datos_er.mmd` lines 7-50 (`usuarios` [V]), lines 558-573 (`login` [L-S])
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py:511-523` (login table), 1247-1255 (FK `fk_login_uuid_usuario`), 2203-2214 (trigger `login_ls_session_guard`), 2533-2541 (audit+set_vigente_inicial triggers), 2777-2788 (enqueue_sync trigger)
- `backend/packages/parkos_core/migrations/versions/0002_seed_permisos_canonicos.py:39-56` (`CANONICAL_PERMISOS` with `audit_read` at line 48 — DEC-LOGIN-09.B)
- `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py:206` (`_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` — the post-F1.1 immutability whitelist)
- `backend/packages/parkos_core/migrations/versions/0032_seed_alert_types_operativos.py` (F1.14 head — DEC-LOGIN-09.B audit_read reuse anchor at line 185)
- `backend/packages/parkos_core/migrations/versions/0011_add_seq_lookup_indexes.py:62` (CONCURRENTLY precedent for index migration — DEC-LOGIN-06)
- `backend/packages/parkos_core/src/parkos_core/models/L_S/login.py:33-74` (verbatim ORM model — `uuid`, `timestamp_evento`, `timestamp_cierre`, `estado ∈ {exitoso, fallido, cerrado}`, `uuid_sucursal`)
- `backend/packages/parkos_core/src/parkos_core/models/V/usuarios.py` (Usuarios ORM — F1.15 reads `uuid` only for optional existence check)
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:49-146` (`record_login` write helper — F1.15 NEVER calls it; only references the table it writes to)
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py:79-162` (`list_tarifas_vigentes` — cursor pagination helper precedent)
- `backend/packages/parkos_core/src/parkos_core/api/router_factory.py:127-227` (cursor pagination + `{items, next_cursor}` envelope pattern — DEC-LOGIN-04 + DEC-LOGIN-07)
- `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py:69` (POST-mutating-only rationale for DEC-LOGIN-01.A — dedicated router)
- `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py:18-31` (`no_store_headers` + `apply_no_store_header` — DEC-LOGIN-05)
- `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'` — Layer 4 base)
- `backend/packages/parkos_core/src/parkos_core/auth/jwt_issuer_guard.py` (`requires_issuer` factory — KD-3 dep)
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`get_tenant_ctx` — Layer 2 dep, KD-S2 F1.7 analog)
- `backend/packages/parkos_core/src/parkos_core/auth.py:239-246` (`fallido`), `:260-266` (`exitoso`), `:352-393` (`cerrado`) — `estado` lifecycle sources
- `tests/static/{test_sync_estado_read_only,test_arqueo_handler_single_commit,test_no_raw_dml_on_ls_tables}.py` (AST walk precedents — F1.15 needs the `ls_tables` variant for KD-LOGIN-02)
- `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 already exists from F1.13 — F1.15 references, does NOT create new)
- `openspec/specs/operations/spec.md` line 4034-4041 (REQ-OPS-100 empty-branch precedent at F1.14 — DEC-LOGIN-08 mirror)
- `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/exploration.md` (F1.14 17-section exploration — DEC-SYNC-03.B audit_read reuse precedent at §6.6)
- `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/specs/operations/spec.md` (canonical Given/When/Then/And format precedent, 4 REQs REQ-OPS-098..101 + REQ-OPS-XR6 reference, ~485 LOC — this delta mirrors its structure section-by-section)

---

## Cross-Cutting Notes

- **DEC-LOGIN-09 resolved**: `audit_read` (pre-seeded at `0002_seed_permisos_canonicos.py:48`) is the canonical permission gate. No new permission, no patch to existing migration, no scope creep into MIGRATION 0033.
- **DEC-LOGIN-03 resolved**: Option A adopted — `operador-` JWT filters `prod.login` rows by `uuid_sucursal = ctx.sucursal_uuid` at SQL layer (own-branch audit history only). `admin-` JWT bypasses and sees ALL branches. Mirrors F1.7 KD-S2 + F1.13 KD-ARQUEO-08 + REQ-OPS-XR6 Layer 2 precedent.
- **DEC-LOGIN-01 resolved**: NEW dedicated `api/v1/usuarios_login.py` router mounted at FastAPI app-level (sibling of `auth.py`). Parte 2's HU-F16.1/F16.5 will EXTEND this router — no collision because Parte 2 adds DIFFERENT routes (`POST /usuarios/{uuid}/login/{login_uuid}/cerrar`, `?activo=` filter) on the same `/usuarios/{uuid}/login` path.
- **XR6 reference**: REQ-OPS-XR6 from F1.13 at `operations/spec.md:3951` applies to F1.15 by inclusion. F1.15 references REQ-OPS-XR6 in §13 of design.md and §10 of tasks.md (no new XR created).
- **DEC-LOGIN-08 anti-enumeration**: 200 with `items=[]` (NOT 404) for any zero-row case — mirrors F1.2 R-F1.2-10 / R-F1.2-11 rationale. Response-time parity constraint (±5%) prevents a SECOND enumeration vector via timing differential analysis.
- **`prod.login` [L-S] immutability whitelist**: `_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` at `0021:206` only allows UPDATE of those 2 columns via `repo/session_cycle.py::record_login`. F1.15 reads existing rows only — the whitelist is preserved (handler never invokes UPDATE; AST walk enforces).
- **`prod.login` triggers**: `login_ls_session_guard` (`migration 0001:2203-2214`) + `login_audit_columns` (`2533-2534`) + `login_set_vigente_inicial` (`2538-2539`) + `login_enqueue_sync` (`2777-2788`) — none fire on F1.15's read path (no INSERT/UPDATE).
- **Parte 2 forward compatibility (DEC-LOGIN-07)**: F1.15's `{items, next_cursor}` envelope does NOT include `activo`, `count`, `total`, or `has_more` — only the canonical shape per `router_factory.py:227`. Parte 2 may add NEW query params (`?activo=`) without changing F1.15's response. F1.15 MUST NOT lock the response shape.

---

**End of delta spec — HU-F1.15.**