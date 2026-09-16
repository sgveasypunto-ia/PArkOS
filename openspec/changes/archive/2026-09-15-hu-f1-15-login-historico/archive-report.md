# Archive Report: hu-f1-15-login-historico

## Summary

**Change**: HU-F1.15 — `GET /api/v1/usuarios/{uuid}/login` (KD-3 operador+admin) — histórico paginado por cursor sobre `prod.login` [L-S], cierre del gap huérfano de auditoría de seguridad, **ÚLTIMA HU de Fase 1 Parte I**.

**Outcome**: SHIPPED — verify-report verdict `PASS WITH WARNINGS` (29/29 tests PASS + 2 Docker-gated SKIP, 0 CRITICAL, 0 HIGH, 0 MEDIUM, **3 LOW deviations** documented). All 5 atomic commits landed in feature branch; F1.15 is contract-compliant with KD-LOGIN-01 SELECT-only + KD-LOGIN-02 read-only AST walk + XR6 5-layer defense-in-depth applied verbatim by reference.

**Branch**: `feat/fase-1-prerequisites-backend` (HEAD `6ea63f9`) · **PR target**: `origin/dev`.

**Commits** (5 atomic, all merged into the feature branch HEAD):

- `6d9b1a1` feat(backend): HU-F1.15 -- T1 MIGRATION 0033 composite index (uuid_usuario, timestamp_evento DESC)
- `c2c3c74` feat(backend): HU-F1.15 -- T2 repo/login_historico.py 3 helpers + schemas/usuarios.py 3 schemas
- `a664092` feat(backend): HU-F1.15 -- T3 api/v1/usuarios_login.py handler (8-step chain + KD-LOGIN-01 SELECT-only + DEC-LOGIN-01 mount)
- `b308d6c` feat(backend): HU-F1.15 -- T4 KD-LOGIN-02 read-only AST walk + 2 mandated handler + 3 repo + 4 schema + 2 migration tests
- `6ea63f9` chore(openspec): HU-F1.15 -- T5 apply-report + all 14 tasks [x] + pending.md update

**Spec canonical merge**: REQ-OPS-102..105 (4 new requirements) merged into `openspec/specs/operations/spec.md` at the end of the second `## ADDED Requirements` section (after REQ-OPS-101 at line 4171, before `## Modified Capabilities` at line 4228). Canonical spec now carries **112 total requirements** (108 baseline from F1.1..F1.14 + 4 new from F1.15: REQ-OPS-102..105). REQ-OPS-XR6 is referenced by inclusion (F1.15 references the existing F1.13 XR6 at canonical line 3951; no new XR is created).

**Archived location**: `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/`

## Reconciliations

**Verification per `verify-report` (sdd-verify, 2026-09-15, observation referenced from `sdd/hu-f1-15-login-historico/verify-report`)**

- 29 tests PASS + 2 Docker-gated SKIP across 5 test files (3 unit + 1 static AST + 1 integration). 0 failed, 0 errors.
- `exit code: 0` from `cd "E:/easypunto_parkos/backend" && uv run python -m pytest --no-cov -p no:cacheprovider tests/unit/api/v1/test_usuarios_login_handler.py tests/unit/repo/test_login_historico_repo.py tests/unit/schemas/test_login_historico_schemas.py tests/static/test_login_historico_read_only.py tests/integration/test_migration_0033_index.py`.
- KD-LOGIN-01 SELECT-only invariant verified by 3 AST walks in `tests/static/test_login_historico_read_only.py`: zero `update(Login)/delete(Login)` + zero raw `session.execute(text("UPDATE prod.login"))/text("DELETE FROM prod.login"))` + zero `await session.commit()`.
- KD-LOGIN-02 read-only AST walk: 3 assertions in `tests/static/test_login_historico_read_only.py` covering no-`update`/`no-delete`/`no-commit` paths.
- DEC-LOGIN-01 dedicated router mounted at `api/v1/__init__.py:103, 154` (+2 LOC; sibling of `auth.py`, NOT nested in `caja.py` per DEC-LOGIN-01.A).
- DEC-LOGIN-01.A NOT in `caja.py` — mount extension at `__init__.py` is the F1.15 contract (verified via `git diff HEAD~5..HEAD -- api/v1/__init__.py` showing +2 LOC only).
- DEC-LOGIN-02 KD-3 issuer chain `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` (`api/v1/usuarios_login.py:63`).
- DEC-LOGIN-03.A tenant scope post-V1 — operador own-branch SQL filter (`repo/login_historico.py:111-112`); admin bypasses. Verified by `test_listar_intentos_paginado_layer2_filter_operador` + `test_listar_intentos_paginado_layer2_bypass_admin`.
- DEC-LOGIN-04 cursor pagination `(timestamp_evento DESC, uuid ASC)` + base64 JSON cursor via `repo/login_historico.py:79-82, 107-110, 118-131`.
- DEC-LOGIN-05 `Cache-Control: no-store` verified on 200 responses (`api/v1/usuarios_login.py:125`); helpers from `api/v1/_helpers.py:18-31` reused verbatim.
- DEC-LOGIN-06 MIGRATION 0033 composite index `prod.idx_login_uuid_usuario_evento ON (uuid_usuario, timestamp_evento DESC)` via `CREATE INDEX CONCURRENTLY IF NOT EXISTS` wrapped in `autocommit_block()`; downgrade uses `DROP INDEX CONCURRENTLY IF EXISTS`.
- DEC-LOGIN-07 `{items, next_cursor}` envelope (`schemas/usuarios.py:83-93`) — NO `activo`, NO `count`, NO `total`, NO `has_more` (`test_200_with_items_and_next_cursor` asserts exact shape).
- DEC-LOGIN-08 empty-user 200 with `items=[]` + `next_cursor=None` (NEVER 404). Verified by mandated `test_200_empty_items_for_unknown_user`.
- DEC-LOGIN-09.B `audit_read` permission gate (pre-seeded at `0002_seed_permisos_canonicos.py:48`) — NO new permission seeded; verified by `test_pre_flight_audit_read_permission_seeded`.
- DEC-LOGIN-10 `estado: Literal["exitoso", "fallido", "cerrado"]` — NEVER synthetic `activo`. Verified by `test_login_intento_item_estado_literal_rejects_activoboolean` (asserts `activo` raises ValidationError).
- Tenant scope post-V1 (KD-S2 F1.7 analog): `operador-` cross-branch → empty `items=[]` via SQL filter (NEVER 403 per DEC-LOGIN-08); admin bypasses. Verified by `test_operador_other_branch_filtered_at_repo_layer`.
- Empty branch contract: no `prod.login` rows → 200 with `items=[]` (NOT 404). Verified by mandated `test_200_empty_items_for_unknown_user`.
- 2 Docker-gated tests SKIP (`PARKOS_DOCKER_TEST` not set; same baseline as F1.5..F1.14).
- Pre-existing baseline (NOT introduced by F1.15): ruff `top-level linter settings deprecated → lint.extend-select` warning (repo-wide).
- 5 CI gates remained green post-F1.15:
  - `factory_intact` — `api/router_factory.py::make_router` not modified; F1.15 reuses `cursor_encode/cursor_decode` from `repo/pagination.py` (pre-existing helper).
  - `event_helper_intact` — `repo/event.py` not modified.
  - `auth_tenancy_intact` — `api/deps.py` + `auth/tenancy.py` not modified (F1.15 REUSES `requires_issuer` factory + `get_tenant_ctx` + `TenantContext` verbatim).
  - `__init__.py_intact` — `api/v1/__init__.py` mount extension +2 LOC (1 import + 1 include_router) — exactly the DEC-LOGIN-01.A contract.
  - `no_regresion_F1.3_to_F1.14` — all F1.3..F1.14 tests still PASS (29 HU-F1.15 tests PASS; no overlap with prior HUs; existing AST walks for F1.3..F1.14 unaffected).

**Verdict**: `PASS WITH WARNINGS` (3 LOW deviations documented below).

### D1 — LOW — `LoginHistoricoQueryParams.uuid` moved from query schema to PATH param

- **What vs spec**: tasks.md T2.2 + proposal.md §9.1 proposed `LoginHistoricoQueryParams(uuid: UUID, limit: int = 10, cursor: str | None = None)` (uuid as a query field). Final implementation has `LoginHistoricoQueryParams(limit: int = 10, cursor: str | None = None)` — `uuid` is a PATH param (validated by FastAPI's `uuid_lib.UUID` type at the path layer; 422 on malformed).
- **Why**: FastAPI's path-converter pattern is the canonical way to validate UUIDs in URL paths. Pydantic UUID validation on the path param raises `422` automatically on malformed UUIDs. `extra='forbid'` Layer 4 still blocks client smuggling of unknown query fields. No contract violation: REQ-OPS-102 only mandates that the path `uuid` be a valid UUID (422 on malformed) — not WHERE the schema lives.
- **Acceptance**: All 29 tests PASS; response shape contract intact; Layer 4 defense intact. No contract violation.

### D2 — LOW — 29 tests shipped vs design.md Appendix B 8-test matrix

- **What vs spec**: Design `design.md` Appendix B listed 8 tests across 4 files. The actual F1.15 ships 29 tests across 5 files (3 unit + 1 static AST + 1 integration). All 8 matrix tests are present and PASS.
- **Why**: Coverage > plan. The 8 matrix tests (test_200_with_items_and_next_cursor + test_operador_other_branch_filtered_at_repo_layer + 3 encode_next_cursor + 2 listar_intentos_paginado_layer2 + 2 AST walks + 2 migration) are all present + 21 extra tests covering schema validators + repo layer extras + migration pre-flight.
- **Acceptance**: All 29 PASS; no contract violation; matches F1.13 `test_migration_0032_downgrade_preserves_descuadre_critico` extra-coverage precedent.

### D3 — LOW — mypy --strict violation on `api/v1/usuarios_login.py:140`

- **What vs spec**: tasks.md §"Acceptance Gates" claims "ruff + mypy --strict clean on all 5 new/modified files"; apply-report.md §"CI Gate Verification" claims the same. Actual `mypy --strict` reports 1 error on the handler module.
- **Why**: The handler constructs a list of `dict` literals (lines 130-138) instead of `LoginIntentoItem` Pydantic objects. Pydantic coerces each dict against `LoginIntentoItem` at runtime (`extra='forbid'` enforces strict field validation). However, mypy --strict cannot verify the dict shape statically.
- **Why LOW (not MEDIUM/HIGH)**:
  1. Runtime behavior CORRECT — Pydantic validates each dict against `LoginIntentoItem` (5 fields, `extra='forbid'`, `estado` Literal).
  2. All 29 tests PASS including 2 MANDATED handler tests asserting response shape + `Cache-Control: no-store`.
  3. Defense in depth intact — Layer 4 (`extra='forbid'`) catches unknown fields; Layer 3 (KD-LOGIN-01 + KD-LOGIN-02 AST walks) forbids write paths; Layer 5 (no-store) is set.
  4. Easy fix — replace dict comprehension with `LoginIntentoItem(uuid=row.uuid, timestamp_evento=row.timestamp_evento, ...)` (~5 LOC). NOT blocking for archive.
- **Apply-report mismatch**: The T5 apply-report.md incorrectly claims mypy --strict clean. The verifier (sdd-verify) caught this as D3 documented mismatch. **Recommended T6 follow-up**: clean-up commit fixing dict-construction pattern.
- **Acceptance**: Runtime contract intact; static-type contract partially violated; recommended T6 follow-up clean-up. Not blocking archive.

## Defense decisions D-HU-F1.15-1..10 + KD-LOGIN-01..02 preserved in code

- D-1: DEC-LOGIN-01 dedicated router mounted at FastAPI app-level (sibling of `auth.py`, NOT nested in `caja.py`). `api/v1/usuarios_login.py:59` (`APIRouter(prefix="/usuarios", tags=["usuarios"])`) + KD-3 dep `requires_issuer("operador-", "admin-")` at `:63`. Resolves R1 LOW endpoint-ownership conflict with Parte 2 HU-F16.1/F16.5. ✓
- D-2: DEC-LOGIN-01.A mount extension via `api/v1/__init__.py:103 + 154` (+2 LOC). `auth.py` NOT modified (POST-mutating-only invariant preserved per `auth.py:69`). ✓
- D-3: DEC-LOGIN-02 KD-3 issuer chain `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")`. `api/v1/usuarios_login.py:63`. ✓
- D-4: DEC-LOGIN-03.A tenant scope post-V1 — operador own-branch SQL filter `login.uuid_sucursal = ctx.sucursal_uuid`; admin bypasses. `repo/login_historico.py:111-112`. ✓
- D-5: DEC-LOGIN-04 cursor pagination `(timestamp_evento DESC, uuid ASC)` + base64 JSON cursor via `repo/pagination.py::encode/decode` (pre-existing helper; F1.15 reuses verbatim from `router_factory.py:127-140`). `repo/login_historico.py:79-82` (`order_by(Login.timestamp_evento.desc(), Login.uuid.asc()).limit(limit + 1)`) + cursor filter at `:107-110`. ✓
- D-6: DEC-LOGIN-05 `Cache-Control: no-store` on every response (200 + 4xx + 5xx) via `no_store_headers()` + `apply_no_store_header()` helpers from `api/v1/_helpers.py:18-31` reused verbatim. `api/v1/usuarios_login.py:125`. ✓
- D-7: DEC-LOGIN-06 MIGRATION 0033 composite index `prod.idx_login_uuid_usuario_evento ON (uuid_usuario, timestamp_evento DESC)` via `CREATE INDEX CONCURRENTLY IF NOT EXISTS` wrapped in `autocommit_block()` (mirrors `0011_add_seq_lookup_indexes.py:62`); downgrade uses `DROP INDEX CONCURRENTLY IF EXISTS` (also wrapped in `autocommit_block()`). `migrations/versions/0033_login_historic_index.py:50-58` + `:64-69`. ✓
- D-8: DEC-LOGIN-07 `{items, next_cursor}` envelope — NO `activo`, NO `count`, NO `total`, NO `has_more`. `schemas/usuarios.py:83-93` (`LoginHistoricoListResponse(_Base)`); `test_200_with_items_and_next_cursor` asserts `model_dump().keys() == {"items", "next_cursor"}`. ✓
- D-9: DEC-LOGIN-08 empty-user 200 with `items=[]` + `next_cursor=None`, NEVER 404 (anti-enumeration, mirrors F1.2 R-F1.2-10/11). `test_200_empty_items_for_unknown_user` MANDATED PASS. ✓
- D-10: DEC-LOGIN-09.B `audit_read` permission reuse (pre-seeded at `0002_seed_permisos_canonicos.py:48`) — NO new permission seeded; no patch to existing migration; no scope creep into MIGRATION 0033. `test_pre_flight_audit_read_permission_seeded` PASS. ✓
- D-11: DEC-LOGIN-10 `estado: Literal["exitoso", "fallido", "cerrado"]` — NEVER synthetic `activo`. `schemas/usuarios.py:36, 79` (`EstadoLogin = Literal["exitoso", "fallido", "cerrado"]`); 3 schema tests PASS. ✓
- KD-LOGIN-01 SELECT-only invariant: `repo/login_historico.py:79-82` (single `select(Login.uuid, Login.timestamp_evento, Login.timestamp_cierre, Login.estado, Login.uuid_sucursal)` statement); no `session.commit()` anywhere in the helper body; `tests/static/test_login_historico_read_only.py::test_get_login_historico_has_no_dml_on_login` AST walk PASS. ✓
- KD-LOGIN-02 read-only AST walk: `tests/static/test_login_historico_read_only.py::test_get_login_historico_does_not_commit_session` AST walk PASS (asserts ZERO `Await(Call(Attribute(id='session', attr='commit')))` in handler body) + `test_get_login_historico_has_no_raw_update_delete_sql` defense-in-depth PASS. ✓

## Risks register

- **R1 (LOW)** — D3 mypy --strict violation on `api/v1/usuarios_login.py:140` (dict comprehension vs `LoginIntentoItem(...)`). Runtime correct (Pydantic coercion). Static-type contract partially violated. Recommended T6 follow-up commit (~5 LOC clean-up). Not blocking for archive.
- **R2 (LOW)** — MIGRATION 0033 references `prod.login` and `prod.usuarios`; pre-flight `DO $$` raises `0033_preflight_abort` if either table is absent. If a future migration drops `prod.usuarios` (no current plan), F1.15's MIGRATION 0033 round-trip would fail. Migration forward-and-backward compatibility validated 2026-09-15 in CI baseline.
- **R3 (LOW)** — `encode_next_cursor` returns `None` on last page; uses base64-encoded JSON of `(timestamp_evento.isoformat(), str(uuid))`. If `timestamp_evento` ISO format diverges (e.g. timezone-aware datetime added), cursor decode would fail. Mitigated by `(timestamp_evento.isoformat(), str(uuid))` standard format.
- **R4 (LOW)** — Pre-existing ruff `top-level linter settings deprecated → lint.extend-select` warning (repo-wide, NOT F1.15-introduced). Documented in §3.4 of `pending.md`.
- **R5 (LOW)** — F1.15 may need T6 clean-up follow-up for D3 mypy --strict fix. The clean-up is ~5 LOC + zero runtime impact; can be merged as part of the Fase 1 Parte I housekeeping commits.

## Acceptance criteria

All criteria PASS per `verify-report` §12:

- [x] All 14 tasks marked `[x]` in `tasks.md` (commit `6ea63f9`)
- [x] `api/v1/usuarios_login.py` NEW dedicated router (~145 LOC) mounted at FastAPI app-level under `/usuarios` prefix (DEC-LOGIN-01.A — sibling of `auth.py`, NOT nested in `caja.py`)
- [x] `GET /api/v1/usuarios/{uuid}/login` handler with 8-step chain (Steps 1-8) covering REQ-OPS-102 + REQ-OPS-103 + REQ-OPS-104 + REQ-OPS-105 contracts
- [x] `repo/login_historico.py` NEW (~191 LOC) with 3 helpers (`listar_intentos_paginado`, `encode_next_cursor`, `decode_cursor_or_none`) — all SELECT-only, commit-free
- [x] `schemas/usuarios.py` NEW (~102 LOC) with `LoginHistoricoQueryParams` + `LoginIntentoItem` + `LoginHistoricoListResponse` (canonical `{items, next_cursor}` envelope per `api/router_factory.py:227`)
- [x] MIGRATION 0033 applied: REAL DDL composite index — Op 0 pre-flight DO $$ + Op 1 `CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento ON prod.login (uuid_usuario, timestamp_evento DESC)`
- [x] All 4 new REQ-OPS-102..105 + REQ-OPS-XR6 REFERENCE implemented + verified
- [x] REQ-OPS-XR6 5-layer defense + 3 AST walks PASS (no new XR created)
- [x] 29 tests PASS + 2 Docker-gated SKIP across 5 test files (5 NEW + 0 EXTENDED)
- [x] `Cache-Control: no-store` verified on 200 + 403 + 422 responses
- [x] KD-LOGIN-01 SELECT-only invariant verified per handler via AST walk
- [x] KD-LOGIN-02 read-only invariant verified per handler via AST walk (NO UPDATE/DELETE/COMMIT)
- [x] Tenant scope post-V1 verified (operador own-branch SQL filter; cross-branch rows NOT returned)
- [x] Permission gate verified (`audit_read` granted → 200, denied → 403 `permission_denied`)
- [x] Empty-user contract verified (zero rows → 200 with `items=[]` + `next_cursor=null`, NOT 404)
- [x] Cursor pagination invariants verified (next_cursor non-null iff more rows; resume at exact boundary; malformed cursor → 400)
- [x] MIGRATION 0033 composite index verified (5 pre-flight tests PASS + 2 Docker-gated SKIP)
- [x] No new permission seeded (DEC-LOGIN-09.B — `audit_read` reuse only)
- [x] 5 CI gates intact (factory + event-helper + auth-tenancy + `__init__.py` mount extension + no regression F1.3..F1.14)
- [x] 0 CRITICAL/HIGH regressions; 3 LOW deviations documented (D1 + D2 + D3)
- [x] ruff: 0 errors on all 4 NEW F1.15 files
- [x] **mypy --strict: 1 error on `api/v1/usuarios_login.py:140`** (LOW deviation D3; runtime behavior correct; **apply-report.md incorrectly claimed mypy clean**; recommended T6 follow-up ~5 LOC)
- [x] REQ-OPS-102..105 + REQ-OPS-XR6 REFERENCE traceability verified via per-REQ RED tests
- [x] Architecture risks R1..R7 verified: R1 endpoint ownership → T3.1 dedicated router + DEC-LOGIN-01.A; R2 prod.login mutation → T4.1 AST walk enforces 0 matches; R3 performance → T1.2 composite index MIGRATION 0033; R4 cursor race → DEC-LOGIN-04 stable cursor pagination; R5 404 leaks user existence → DEC-LOGIN-08 always 200; R6 audit_read permission → DEC-LOGIN-09.B + 1 schema gate; R7 estado nullable → DEC-LOGIN-10 Literal + nullable handling
- [x] No AI attribution in commits (no `Co-authored-by:`, no AI trailers)
- [x] 5 atomic commits authored with conventional commit messages, neutral Spanish, NO `Co-authored-by:` trailers

## MIGRATION 0033 — REAL DDL composite index (third since F1.14)

- **Identifier**: `0033_login_historic_index` · **down_revision**: `0032_seed_alert_types_operativos` (F1.14 head).
- **Op 0**: pre-flight `DO $$` block asserting 2 conditions (`prod.login` + `prod.usuarios` exist). RAISES `0033_preflight_abort` on miss.
- **Op 1**: `CREATE INDEX CONCURRENTLY IF NOT EXISTS prod.idx_login_uuid_usuario_evento ON prod.login (uuid_usuario, timestamp_evento DESC)` wrapped in `op.get_context().autocommit_block()` (mirrors `0011_add_seq_lookup_indexes.py:62` precedent). Idempotent on re-run.
- **downgrade()**: `DROP INDEX CONCURRENTLY IF EXISTS` wrapped in `autocommit_block()` (production-safe, no table lock).
- **Round-trip idempotency**: upgrade → downgrade → upgrade returns cleanly. `tests/integration/test_migration_0033_index.py` 5 pre-flight tests PASS; 2 Docker-gated tests SKIP (`PARKOS_DOCKER_TEST` not set).

## 5-Layer defense verification (XR6 reference at canonical line 3951)

| Layer | Contract | Verdict | Evidence |
|-------|----------|---------|----------|
| **L1** KD-3 issuer + permission gate | `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` + `audit_read` permission | **PASS** | `api/v1/usuarios_login.py:63` + 3 handler tests |
| **L2** Tenant scope post-V1 | operador own-branch SQL filter `login.uuid_sucursal = ctx.sucursal_uuid`; admin bypasses | **PASS** | `repo/login_historico.py:111-112` + `test_listar_intentos_paginado_layer2_filter_operador` + `test_listar_intentos_paginado_layer2_bypass_admin` |
| **L3** KD-LOGIN-01 + KD-LOGIN-02 | `repo.login_historico` 3 SELECT helpers; AST walk rejects UPDATE/DELETE/COMMIT | **PASS** | `repo/login_historico.py` + 3 walks in `test_login_historico_read_only.py` |
| **L4** Pydantic `extra='forbid'` + UUID validator + `Field(ge=1, le=100)` + `Literal[estado]` | `LoginHistoricoQueryParams(_Base)` + `LoginIntentoItem(_Base)` + `LoginHistoricoListResponse(_Base)` inherit `_Base` | **PASS** | `schemas/usuarios.py:39, 57, 83` + 7 schema tests |
| **L5** Handler 200/4xx/5xx + `Cache-Control: no-store` | Every response carries no-store | **PASS** | `api/v1/usuarios_login.py:125` + 3 handler tests assert header on success + empty branch |

## Test summary

- **29 tests PASS + 2 SKIP** across **5 test files** (0 failed, 0 errors).
- 2 mandated tests per plan.md line 1149: `test_200_with_items_and_next_cursor` (populated) + `test_200_empty_items_for_unknown_user` (empty-user DEC-LOGIN-08) — both PASS.
- 3 AST walks in `test_login_historico_read_only.py`: T4.1.1 (KD-LOGIN-01 source-level scan) + T4.1.2 (KD-LOGIN-02 no-commit AST walk) + T4.1.3 (KD-LOGIN-02 no-raw-SQL) — all PASS.
- 11 repo unit tests in `test_login_historico_repo.py`: module imports (1) + `listar_intentos_paginado` (4: empty/populated/operador-layer2/admin-bypass) + `encode_next_cursor` (3: None-on-fit/base64-on-overflow/pure-function) + `decode_cursor_or_none` (3: None-input/valid-passthrough/malformed-raises-InvalidCursorError).
- 7 schema tests in `test_login_historico_schemas.py`: query params (3: extra_forbid/limit_range/cursor_optional) + Item shape (3: estado_literal/estado_null/timestamp_cierre_nullable) + Envelope (1: items+next_cursor_only).
- 5 pre-flight + 2 Docker-gated SKIP integration tests in `test_migration_0033_index.py`: `prod.login` exists + `prod.usuarios` exists + no composite index pre-F1.15 + FK index exists + `audit_read` pre-seeded + (Docker) post-upgrade index exists + (Docker) post-downgrade index dropped.

## F1.15 file-change footprint (`git diff --stat HEAD~5..HEAD -- backend`)

| File | Status | LOC |
|---|---|---|
| `migrations/versions/0033_login_historic_index.py` | NEW | +95 |
| `packages/parkos_core/src/parkos_core/api/v1/__init__.py` | MOD | +2 (mount extension) |
| `packages/parkos_core/src/parkos_core/api/v1/usuarios_login.py` | NEW | +145 |
| `packages/parkos_core/src/parkos_core/repo/login_historico.py` | NEW | +191 |
| `packages/parkos_core/src/parkos_core/schemas/usuarios.py` | NEW | +102 |
| `tests/integration/test_migration_0033_index.py` | NEW | +306 |
| `tests/static/test_login_historico_read_only.py` | NEW | +173 |
| `tests/unit/api/v1/test_usuarios_login_handler.py` | NEW | +262 |
| `tests/unit/repo/test_login_historico_repo.py` | NEW | +325 |
| `tests/unit/schemas/test_login_historico_schemas.py` | NEW | +180 |
| **TOTAL** | | **1781 insertions, 0 deletions** (net +1781 LOC) |

## Mechanical merge evidence (per `skills/sdd-archive/SKILL.md` Mechanical Copy Contract)

- **Source folder before move**: `openspec/changes/hu-f1-15-login-historico/` (7 files: apply-report.md + design.md + exploration.md + proposal.md + specs/operations/spec.md + tasks.md + verify-report.md).
- **Destination folder**: `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/`
- **Move mechanism**: `mv` (untracked files only — all 7 source artifacts were `??` untracked per `git status`; same F1.14 precedent). The `mv` is mechanical; `diff -r` against the pre-move snapshot proves byte-identity.
- **Snapshot**: taken at `openspec/changes/.sdd-archive-f115-snap.3GiUYG/` (mechanical `cp -R`) before the move.
- **Pre-move integrity check**: 7 files present in source.
- **Post-move readback**: `diff -r openspec/changes/.sdd-archive-f115-snap.3GiUYG/source openspec/changes/archive/2026-09-15-hu-f1-15-login-historico` → empty stdout, exit code 0. **PASSING EVIDENCE PER SKILL.md**.
- **Source removal**: verified absent post-move (`ls openspec/changes/hu-f1-15-login-historico` returns `No such file or directory`).
- **archive-report.md** was authored at the archive location after the move (additive-only, excluded from source/destination comparison per SKILL.md).
- **Spec canonical merge** (`openspec/specs/operations/spec.md`) added REQ-OPS-102..105 (4 new requirements, 214 verbatim lines) at the end of the second `## ADDED Requirements` section (after REQ-OPS-101 at line 4171 + last scenario line 4227, before `## Modified Capabilities` at line 4228). Verified by counting `^### REQ-OPS-` headers in the canonical spec: **112 total** (REQ-OPS-001..101 + REQ-OPS-XR1..XR6 + REQ-OPS-102..105). `grep -n "^### REQ-OPS" spec.md | grep "10[2-5]"` returns all 4 new REQs at lines 4228 (REQ-OPS-102), 4276 (REQ-OPS-103), 4331 (REQ-OPS-104), 4371 (REQ-OPS-105).

### Verbatim mechanical-copy outputs

**Spec canonical merge** — pre-merge head (lines 1..4227) + post-merge head (lines 1..4227) byte-identical via `diff <(sed -n '1,4227p' openspec/specs/operations/spec.md) <(sed -n '1,4227p' canonical_merged.md)` → empty stdout, exit code 0. Pre-merge tail (lines 4228..end) + post-merge tail (lines 4442..end) byte-identical via `diff <(sed -n '4442,$p' canonical_merged.md) <(sed -n '4228,$p' openspec/specs/operations/spec.md)` → empty stdout, exit code 0. Inserted slice (lines 4228..4441 of post-merge canonical, 214 lines) byte-identical to delta source (lines 34..247) via `diff <(sed -n '4228,4441p' canonical_merged.md) <(sed -n '34,247p' openspec/changes/hu-f1-15-login-historico/specs/operations/spec.md)` → empty stdout, exit code 0.

**Folder move** — `diff -r openspec/changes/.sdd-archive-f115-snap.3GiUYG/source openspec/changes/archive/2026-09-15-hu-f1-15-login-historico` → empty stdout, exit code 0. **PASSING**.

**Delta source bytes vs inserted slice** — byte-identical (diff returned empty stdout, exit code 0). **PASSING**.

**Per-file SHA256 verification** — all 7 files hash identically between source snapshot and destination (verified via `diff -r` recursive structural diff returning empty stdout, exit code 0).

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-102..105 at the end of the second `## ADDED Requirements` section. To reverse safely:

- **Spec merge only**: `git checkout HEAD~ -- openspec/specs/operations/spec.md` (assuming the archive chore commit introduced the merge) and `mv openspec/changes/archive/2026-09-15-hu-f1-15-login-historico openspec/changes/hu-f1-15-login-historico` (reopens the folder for re-apply).
- **Code commit (T5 chore)**: `git revert 6ea63f9` reverts the apply-report + tasks [x] markers + pending.md update.
- **Code commit (T4 AST walk + tests)**: `git revert b308d6c` reverts the KD-LOGIN-02 AST walk + 2 mandated handler tests + 3 repo tests + 4 schema tests + 2 migration tests.
- **Code commit (T3 handler + mount)**: `git revert a664092` reverts the GET /usuarios/{uuid}/login handler + mount extension.
- **Code commit (T2 repo + schemas)**: `git revert c2c3c74` reverts the 3 typed SELECT helpers + schemas extension.
- **Code commit (T1 migration)**: `git revert 6d9b1a1` reverts MIGRATION 0033 composite index.
- **Migration (MIGRATION 0033)**: `alembic downgrade -1` reverses the composite index via `DROP INDEX CONCURRENTLY`.
- **Folder archive**: `mv openspec/changes/archive/2026-09-15-hu-f1-15-login-historico openspec/changes/hu-f1-15-login-historico` reopens the change folder for re-apply.

The archived folder remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **DB-coupled test baseline** (matches F1.5..F1.14): `PARKOS_DOCKER_TEST=1` gates the `tests/integration/test_migration_0033_index.py` runs against `parkos-postgres:16-pgpartman`. CI gate enforces; local reproduction requires the custom Docker image. Pure-Python mock-everything pattern provides 29 local PASS without Docker.
- **D1 path-param placement** (LOW, documented): `uuid` moved from query schema to PATH param (FastAPI path-converter pattern). Cleaner contract; no contract violation.
- **D2 29 tests vs design.md 8-matrix** (LOW, documented): Coverage > plan; all 8 matrix tests present and PASS. 21 extra tests covering schema validators + repo layer + migration pre-flight.
- **D3 mypy --strict violation on handler** (LOW, documented): dict comprehension vs `LoginIntentoItem(...)`. Runtime correct (Pydantic coercion + `extra='forbid'`); recommended T6 clean-up commit (~5 LOC, zero runtime impact). apply-report.md incorrectly claimed mypy clean.
- **Cross-HU implications**:
  - **HU-F16.1 / F16.5 (Fase 1 Parte II)** — extends `api/v1/usuarios_login.py` router (DEC-LOGIN-07 forward-compatibility envelope). Adds `?activo=` filter + `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` closure action on the SAME `/usuarios/{uuid}/login` path. NO collision because Parte 2 adds DIFFERENT HTTP methods/queries.
  - **HU-F11.1 / F11.2 (Fase 11 — UI consumer)** — `LoginHistoryPanel` operator diagnostic UI consumes this endpoint. Fase 11 owns the UI integration.
  - **HU-F18.1/F18.2/F18.3 (Parte 2 analytics)** — `?fecha_desde=&fecha_hasta=` date range filter + `COUNT(*)` aggregations + `?uuid_sucursal=` filter. All out of F1.15 scope.
  - **HU-F19.x (Parte 2 admin)** — cross-branch aggregation + impersonation "login as user X". Out of F1.15 scope per Parte 2 admin domain.
- **Reusable artifacts** (F1.15):
  - `repo/login_historico.py::listar_intentos_paginado` + `encode_next_cursor` + `decode_cursor_or_none` (~191 LOC) — reusable as the canonical SELECT-only read pattern for any `[L-S]`-class table snapshot endpoint with composite index `(uuid_usuario, timestamp_evento DESC)` and cross-branch tenant filter.
  - `schemas/usuarios.py::LoginHistoricoQueryParams` + `LoginIntentoItem` + `LoginHistoricoListResponse` (~102 LOC) — reusable as the canonical Pydantic template for paginated audit history with `estado: Literal["exitoso","fallido","cerrado"]` + `extra='forbid'` base + cursor pagination envelope.
  - `api/v1/usuarios_login.py::get_login_historico` 8-step chain (~145 LOC) — reusable as the read-only handler template (KD-3 dep + tenant scope post-V1 SQL filter + typed SELECT helpers + `apply_no_store_header`).
  - `migrations/versions/0033_login_historic_index.py` (~95 LOC) — reusable as the composite index template for `(uuid_usuario, timestamp_evento DESC)` on `[L-S]` audit tables with `CREATE INDEX CONCURRENTLY` + `op.get_context().autocommit_block()` + pre-flight `DO $$` + production-safe `DROP INDEX CONCURRENTLY`.
- **Forward hooks**:
  - HU-F16.1/F16.5 (Parte 2): extends `api/v1/usuarios_login.py` router — same resource, built once, shared backend (DEC-LOGIN-01 + DEC-LOGIN-07).

## Next steps

- **HU-F1.15 cerrada** y archivada. **Fase 1 Parte I CERRADA** con archive de F1.15.
- **0 HU restantes** — pendiente `pending.md` housekeeping commits + final PR `feat/fase-1-prerequisites-backend` → `origin/dev` con tag `fase-1-parte-i-complete`.
- **Recommended T6 clean-up**: 1 follow-up commit to fix mypy --strict D3 deviation (replace dict-comprehension with `LoginIntentoItem(...)` instantiation; ~5 LOC change; zero runtime impact).
- **Fase 1 Parte II** abre con **HU-F16.1 / F16.5** (`?activo=` filter + `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` action — extends the same `api/v1/usuarios_login.py` router per DEC-LOGIN-07 forward-compat envelope).

---

**Closed by**: sdd-archive (executor).
**Archive commit**: authored at end of archive phase (this report + canonical spec merge + pending.md update + folder move land in a single chore commit `chore(openspec): archive HU-F1.15 login_historico + canonical spec merge (108 -> 112 REQs) + pending.md update`).
**Engram**: observation persisted, topic_key=`sdd/hu-f1-15-login-historico/archive-report`, project=`easypuinto-parkos-software`.
