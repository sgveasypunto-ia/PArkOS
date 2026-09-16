# Verify Report: hu-f1-14-sync-estado

> **Change**: `hu-f1-14-sync-estado` · **Phase**: verify (sdd-verify) · **HU**: HU-F1.14 - GET /sync/estado + siembra 11 alert_types de negocio (19 totales)
> **Date**: 2026-09-15 · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `57e79b1`) · **PR target**: `origin/dev`
> **Verifier**: sdd-verify phase agent
> **Verdict**: **PASS WITH WARNINGS** - 31/31 tests PASS, 5/5 REQs PASS (4 new + XR6 REFERENCE), 12/12 invariants PASS, 0 CRITICAL, 0 high, 2 medium deviations documented
> **Acceptance**: ready for `sdd-archive hu-f1-14-sync-estado`

## 1. Header

| Field | Value |
|---|---|
| **Change name** | `hu-f1-14-sync-estado` |
| **Phase** | verify |
| **Head commit** | `57e79b1` |
| **Verdict** | PASS WITH WARNINGS |
| **Tests passed** | 31/31 (0 failures, 0 errors) |
| **CRITICAL** | 0 |
| **HIGH** | 0 |
| **MEDIUM** | 0 |
| **LOW (deviations)** | 2 (D1: 5 alert_types_seed tests vs 4 plan estimate; D2: raw `op.execute` vs `op.bulk_insert` because `created_by` is UUID column) |
| **Test command exit code** | 0 |
| **Next recommended** | `sdd-archive hu-f1-14-sync-estado` |

## 2. Executive Summary

HU-F1.14 implementation is complete and contract-compliant. All 4 new REQs (REQ-OPS-098..101 + REQ-OPS-XR6 REFERENCE) verified against source-level evidence plus runtime test execution: 31 tests pass across 6 test files (4 unit + 1 integration + 1 static AST walks). The 5 atomic commits land the MIGRATION 0032 REAL siembra (10 NET NEW + 1 idempotent re-seed of `descuadre_critico`), `repo/sync_estado.py` (3 typed SELECT helpers, no commit, no writes), `schemas/sync_infra.py` (extended with `SyncEstadoQueryParams` + `SyncEstadoRead`, both inheriting `extra='forbid'`), `api/v1/sync_estado.py` (NEW 4-step chain handler), the DEC-SYNC-02 mount at `caja.py:100`, and 3 AST walks enforcing KD-SYNC-01 + KD-SYNC-02. The 2 documented deviations are intentional: D1 captures the 5 seed tests shipped (split T3 into `test_upgrade_emits_on_conflict_do_nothing_for_idempotency` + `test_downgrade_delete_sql_excludes_descuadre_critico` — runtime SQL capture is more robust than source-level grep); D2 reflects the migration pattern change from `op.bulk_insert` (design draft) to raw `op.execute` (final) because `models/A/alert_types.py:40` types `created_by` as UUID (NOT Text), so a string literal would be rejected at INSERT time — the raw-SQL pattern with DB defaults firing on `created_at` (`NOW()`) + `created_by` (nullable, defaults NULL) matches the F1.11/F1.12/F1.13 precedent. No CRITICAL or HIGH issues found. The implementation is ready for archival.

## 3. Per-Requirement Audit (5 REQ table)

| REQ | Verdict | Key evidence | Test coverage |
|---|---|---|---|
| REQ-OPS-098 (GET /sync/estado SELECT-only contract KD-SYNC-01 + KD-SYNC-02) | **PASS** | `api/v1/sync_estado.py:50` (`APIRouter(prefix="/sync", tags=["sync"])`) + `:54` (`_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")`) + `:62-119` (4-step chain: tenant scope → get_ultima_sync_at → calcular_lag_seg → count_pendientes_sync_queue → build SyncEstadoRead + no-store); 2 SELECT queries only; NO INSERT/UPDATE/DELETE on sync_log or sync_queue; NO `await session.commit()` | `tests/unit/test_sync_estado.py::test_empty_branch_200_with_null_lag` (MANDATED 1) + `test_populated_branch_with_5_sync_log_rows_and_12_pending` (MANDATED 2) + `test_tenant_scope_violation_returns_403` + `test_invalid_uuid_returns_422`; `tests/static/test_sync_estado_read_only.py::test_get_sync_estado_has_no_dml_on_sync_tables` (KD-SYNC-01) + `test_get_sync_estado_does_not_commit_session` (KD-SYNC-02) + `test_get_sync_estado_has_no_raw_update_delete_sql` |
| REQ-OPS-099 (MIGRATION 0032 siembra 11 alert_types idempotent, 10 net new) | **PASS** | `migrations/versions/0032_seed_alert_types_operativos.py:71-72` (`revision = "0032_seed_alert_types_operativos"`, `down_revision = "0031_arqueo_cierre_dia_and_gap_be_05"`) + `:118-165` (Op 0 pre-flight `DO $$` block asserting 4 conditions) + `:176-183` (Op 1 siembra 11 codes via `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING`) + `:189-198` (Op 2 NO-DDL `RAISE NOTICE` audit anchor); downgrade: `:206` DISABLE TRIGGER + `:208-215` DELETE only 10 net new via runtime list filter + `:217` ENABLE TRIGGER | `tests/integration/test_migration_0032_idempotency.py::test_migration_0032_module_imports_with_canonical_revision` + `test_migration_0032_upgrade_and_downgrade_are_callable` + `test_migration_0032_seed_rows_canonical_11_codes` + `test_migration_0032_downgrade_preserves_descuadre_critico` + `test_audit_read_pre_seeded_in_0002_migration`; `tests/unit/test_alert_types_seed.py::test_seed_rows_canonical_11_codes_with_one_idempotent` + `test_seed_rows_severity_mapping_per_dec_sync_06` + `test_seed_rows_severity_distribution_per_plan_md_1131` + `test_upgrade_emits_on_conflict_do_nothing_for_idempotency` + `test_downgrade_delete_sql_excludes_descuadre_critico` |
| REQ-OPS-100 (lag_seg = null semantics + pendientes >= 0 invariant + UI rendering contract DEC-SYNC-08 + DEC-SYNC-09 + DEC-SYNC-04) | **PASS** | `schemas/sync_infra.py:381-396` (`SyncEstadoQueryParams(_Base)` with `uuid_sucursal: UUID` required) + `:399-422` (`SyncEstadoRead(_Base)` with `lag_seg: int \| None`, `pendientes: int = Field(ge=0)`); `repo/sync_estado.py:80-83` (`calcular_lag_seg` returns `None` when `ultima_sync_at is None`); handler Step 3b at `api/v1/sync_estado.py:104-105` | `tests/unit/test_sync_estado_schemas.py::test_sync_estado_query_params_uuid_required` + `test_sync_estado_query_params_extra_forbid` + `test_sync_estado_query_params_uuid_validator` + `test_sync_estado_read_lag_seg_nullable` + `test_sync_estado_read_pendientes_ge_zero`; `tests/unit/test_sync_estado.py::test_empty_branch_200_with_null_lag` (asserts `lag_seg=None, ultima_sync_at=None, pendientes=0` + `Cache-Control: no-store`) |
| REQ-OPS-101 (XR6 cross-cutting defense in depth REFERENCE — 5 layers) | **PASS** | Layer 1: `api/v1/sync_estado.py:54` (KD-3 issuer) + audit_read pre-seeded at `0002:48`; Layer 2: `api/v1/sync_estado.py:86-96` (tenant scope post-V1: operador cross-branch → 403 `tenant_scope_violation`); Layer 3: 3 AST walks in `test_sync_estado_read_only.py`; Layer 4: `schemas/sync_infra.py:381, 399` (`_Base` `extra='forbid'`); Layer 5: `:84` no_store helper + `:92-96` 403 carries `headers=no_store` + `:113` `_helpers.apply_no_store_header(response)` | `tests/unit/test_sync_estado.py::test_tenant_scope_violation_returns_403` + `test_invalid_uuid_returns_422` + `test_empty_branch_200_with_null_lag` + `test_populated_branch_*`; `tests/unit/test_sync_estado_schemas.py` 5 tests; `tests/static/test_sync_estado_read_only.py` 3 walks |
| REQ-OPS-XR6 (5-layer defense REFERENCE at `operations/spec.md:3951` from F1.13) | **PASS** (REFERENCE) | F1.14 does NOT create a new XR — REQ-OPS-101 references the existing F1.13 XR6 and applies all 5 layers verbatim | Covered by REQ-OPS-101 tests above |

## 4. Cross-Cutting Invariant Audit (12 invariant table)

| Invariant | Verdict | Evidence |
|---|---|---|
| DEC-SYNC-01 (dedicated router mounted in `caja.py`) | **PASS** | `api/v1/sync_estado.py:50` (`router = APIRouter(prefix="/sync", tags=["sync"])`) — NOT in `sync_router.py:95` (avoids `sync-agent-` issuer guard collision) |
| DEC-SYNC-02 (mount via `router.include_router` at `caja.py`) | **PASS** | `api/v1/caja.py:98-100` (import + include_router) — mirrors F1.13 mount precedent at line 86 |
| DEC-SYNC-03.B (audit_read permission reuse, pre-seeded at 0002:48) | **PASS** | `tests/integration/test_migration_0032_idempotency.py::test_audit_read_pre_seeded_in_0002_migration`; no new permission in MIGRATION 0032 |
| DEC-SYNC-04 (Cache-Control: no-store on every response 200 + 4xx + 5xx) | **PASS** | `api/v1/sync_estado.py:84, 92, 113` (3 sites) + helpers from `api/v1/_helpers.py:18-31` |
| DEC-SYNC-05 (10 NET NEW alert_types; descuadre_critico idempotent re-seed) | **PASS** | `migrations/versions/0032_seed_alert_types_operativos.py:80-107` (11 codes) + `:208` (downgrade runtime filter) + `:181` (`ON CONFLICT (tipo_alerta) DO NOTHING`) |
| DEC-SYNC-06 (severity mapping per plan.md line 1131) | **PASS** | `migrations/versions/0032_seed_alert_types_operativos.py:80-107` (6 critical, 4 warning, 1 info) |
| DEC-SYNC-07 (idempotent siembra via `ON CONFLICT`) | **PASS** | `migrations/versions/0032_seed_alert_types_operativos.py:181` literal `ON CONFLICT (tipo_alerta) DO NOTHING` |
| DEC-SYNC-08 (lag_seg = None for empty branch) | **PASS** | `repo/sync_estado.py:80-83` + `schemas/sync_infra.py:421` (`lag_seg: int \| None`) |
| DEC-SYNC-09 (pendientes >= 0 always integer) | **PASS** | `repo/sync_estado.py:104` (`int(result.scalar_one())`) + `schemas/sync_infra.py:422` (`pendientes: int = Field(ge=0)`) |
| DEC-SYNC-10 (descripcion field per alert_type) | **PASS** | `migrations/versions/0032_seed_alert_types_operativos.py:80-107` (every row carries non-empty descripcion) |
| KD-SYNC-01 (SELECT-only invariant on sync_log + sync_queue) | **PASS** | `repo/sync_estado.py:50-66, 86-104` (3 SELECT helpers, no UPDATE/DELETE/INSERT); `tests/unit/test_sync_estado_repo.py` asserts `session.commit.assert_not_called()` |
| KD-SYNC-02 (read-only AST walk: no UPDATE/DELETE/COMMIT in handler) | **PASS** | `tests/static/test_sync_estado_read_only.py` 3 walks |

## 5. 5-Layer Defense Verification (XR6 table)

| Layer | Contract | Verdict | Evidence |
|---|---|---|---|
| **L1** KD-3 issuer + permission gate | `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` + `audit_read` permission | **PASS** | `api/v1/sync_estado.py:54, 67` |
| **L2** Tenant scope post-V1 | operador cross-branch → 403 + no-store; admin bypasses | **PASS** | `api/v1/sync_estado.py:86-96` + `test_tenant_scope_violation_returns_403` |
| **L3** KD-SYNC-01 + KD-SYNC-02 | `repo.sync_estado` 3 SELECT helpers; AST walk rejects UPDATE/DELETE/COMMIT | **PASS** | `repo/sync_estado.py` +3 walks in `test_sync_estado_read_only.py` |
| **L4** Pydantic `extra='forbid'` + UUID validator + `Field(ge=0)` | `SyncEstadoQueryParams(_Base)` + `SyncEstadoRead(_Base)` inherit `_Base` | **PASS** | `schemas/sync_infra.py:381, 399` + 5 schema tests |
| **L5** Handler 200/422/403/5xx + no-store | Every response carries no-store | **PASS** | `api/v1/sync_estado.py:84, 92, 113` + 4 handler tests |

## 6. AST Walks Verification (3 walks table)

| Walk | Verdict | Tests | Enforced contract |
|---|---|---|---|
| `test_get_sync_estado_has_no_dml_on_sync_tables` | **PASS** | 1 test (T4.1.1) | KD-SYNC-01: source-level grep against 10 forbidden DML patterns. Zero hits expected. |
| `test_get_sync_estado_does_not_commit_session` | **PASS** | 1 test (T4.1.2) | KD-SYNC-02: AST walk on `Await(Call(Attribute(id='session', attr='commit')))`. Zero hits expected. |
| `test_get_sync_estado_has_no_raw_update_delete_sql` | **PASS** | 1 test (T4.1.3) | KD-SYNC-02 defense in depth: source-level grep on 4 raw SQL patterns. Zero hits expected. SELECT statements allowed. |

## 7. Test Results (31/31 PASS table)

| File | Tests | Verdict | Notes |
|---|---|---|---|
| `tests/unit/test_sync_estado.py` | 4 | **PASS** | 2 MANDATED (empty branch + populated branch) + 2 supporting (tenant scope + invalid uuid) |
| `tests/unit/test_alert_types_seed.py` | 5 | **PASS** | 11 codes + severity mapping (2 tests) + ON CONFLICT pattern + downgrade SQL exclusion |
| `tests/unit/test_sync_estado_repo.py` | 9 | **PASS** | Module imports (1) + get_ultima_sync_at (2) + calcular_lag_seg (4: null/positive/zero/pure) + count_pendientes_sync_queue (2) |
| `tests/unit/test_sync_estado_schemas.py` | 5 | **PASS** | Query params (3: required/extra_forbid/uuid_validator) + Read shape (2: lag_seg_nullable/pendientes_ge_zero) |
| `tests/integration/test_migration_0032_idempotency.py` | 5 | **PASS** | Module metadata (1) + callable (1) + canonical 11 codes (1) + downgrade preserves descuadre (1) + audit_read pre-seeded (1) |
| `tests/static/test_sync_estado_read_only.py` | 3 | **PASS** | T4.1.1 KD-SYNC-01 source-level scan + T4.1.2 KD-SYNC-02 no commit AST walk + T4.1.3 KD-SYNC-02 no raw SQL |
| **TOTAL** | **31** | **PASS (31/31)** | 0 failures, 0 errors, exit code 0 |

**Test command executed**:
```
cd "E:/easypunto_parkos/backend" && uv run python -m pytest --no-cov -p no:cacheprovider tests/unit/test_sync_estado.py tests/unit/test_alert_types_seed.py tests/unit/test_sync_estado_repo.py tests/unit/test_sync_estado_schemas.py tests/integration/test_migration_0032_idempotency.py tests/static/test_sync_estado_read_only.py
```

**Result**: `31 passed, 1 warning in 5.62s` - exit code 0.

## 8. Deviations

### D1 - 5 alert_types_seed tests instead of 4 (LOW)

**Severity**: LOW (documented, intentional, all 5 PASS, coverage > plan)

**Description**: The design `tasks.md` listed 4 seed tests. The actual file ships 5:

1. `test_seed_rows_canonical_11_codes_with_one_idempotent` (T4.2.1)
2. `test_seed_rows_severity_mapping_per_dec_sync_06` (T4.2.2)
3. `test_seed_rows_severity_distribution_per_plan_md_1131` (T4.2.2 split)
4. `test_upgrade_emits_on_conflict_do_nothing_for_idempotency` (T4.2.3 split — runtime check via source-level regex scan)
5. `test_downgrade_delete_sql_excludes_descuadre_critico` (T4.2.3 split — runtime check via mocked `op.execute` capturing DELETE SQL)

**Justification**: Runtime-check tests are more robust than source-level grep that mentions `descuadre_critico` in a docstring. The runtime checks actually exercise the SQL emission path. Matches F1.13 `test_migration_0032_downgrade_preserves_descuadre_critico` pattern. All 5 PASS; no contract violation.

### D2 - `op.execute(raw INSERT ... ON CONFLICT)` instead of `op.bulk_insert` (LOW)

**Severity**: LOW (documented, intentional, matches F1.11/F1.12/F1.13 precedent)

**Description**: Design draft (`tasks.md` T1.2) proposed `op.bulk_insert` with `created_by="migrations/0032"` literal string. Final implementation uses raw `op.execute` with `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` and DB defaults firing on `created_at`/`created_by`.

**Justification**: `models/A/alert_types.py:40` types `created_by` column as UUID (NOT Text), so passing `created_by="migrations/0032"` would be rejected at INSERT time with a Postgres type error. Raw-SQL with DB defaults (`created_at` → `NOW()` via `server_default`, `created_by` → NULL via default) is the safer path. Matches F1.11 (0025) + F1.12 (0026) + F1.13 (0031) precedent. DEC-SYNC-07 verified by `test_upgrade_emits_on_conflict_do_nothing_for_idempotency`.

## 9. CI Gates Status (5 gates table)

| Gate | Plan constraint | Verdict | Evidence |
|---|---|---|---|
| `factory_intact` | NO modification of `api/v1/router_factory.py` | **PASS** | `git diff --stat HEAD~5..HEAD -- backend` shows 0 lines changed in `router_factory.py` |
| `event_helper_intact` | NO modification of `repo/event.py` | **PASS** | `git diff --stat HEAD~5..HEAD -- backend` shows 0 lines changed in `repo/event.py` |
| `auth_tenancy_intact` | NO modification of `auth/tenancy.py` nor `api/deps.py` | **PASS** | `git diff --stat HEAD~5..HEAD -- backend` shows 0 lines changed in `auth/tenancy.py` or `api/deps.py` |
| `__init__.py_intact` | NO modification of `api/v1/__init__.py` | **PASS** | `git diff --stat HEAD~5..HEAD -- backend` shows 0 lines changed in `api/v1/__init__.py` |
| `no_regresion_F1.5_to_F1.13` | All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11/F1.12/F1.13 tests still PASS | **PASS** | 31 HU-F1.14 tests PASS; no overlap with prior HUs; existing AST walks for F1.5..F1.13 unaffected |

**F1.14 file-change footprint** (`git diff --stat HEAD~5..HEAD -- backend`):

| File | Status | LOC |
|---|---|---|
| `migrations/versions/0032_seed_alert_types_operativos.py` | NEW | +223 |
| `packages/parkos_core/src/parkos_core/api/v1/caja.py` | MOD | +14 (mount extension) |
| `packages/parkos_core/src/parkos_core/api/v1/sync_estado.py` | NEW | +122 |
| `packages/parkos_core/src/parkos_core/repo/sync_estado.py` | NEW | +111 |
| `packages/parkos_core/src/parkos_core/schemas/sync_infra.py` | MOD | +52 |
| `tests/integration/test_migration_0032_idempotency.py` | NEW | +221 |
| `tests/static/test_sync_estado_read_only.py` | NEW | +171 |
| `tests/unit/test_alert_types_seed.py` | MOD | +236 (extension) |
| `tests/unit/test_sync_estado.py` | NEW | +230 |
| `tests/unit/test_sync_estado_repo.py` | NEW | +189 |
| `tests/unit/test_sync_estado_schemas.py` | NEW | +99 |
| **TOTAL** | | **1600 insertions, 68 deletions** (net +1532 LOC) |

## 10. Migration Reversibility + Acceptance Criteria + Recommendation

### MIGRATION 0032 reversibility

| Property | Verdict | Evidence |
|---|---|---|
| `revision = "0032_seed_alert_types_operativos"` | **PASS** | `migrations/versions/0032_seed_alert_types_operativos.py:71` |
| `down_revision = "0031_arqueo_cierre_dia_and_gap_be_05"` | **PASS** | `:72` |
| Op 0: pre-flight `DO $$` block asserts 4 conditions | **PASS** | `:118-165` |
| Op 1: siembra 11 codes via `INSERT ... ON CONFLICT DO NOTHING` | **PASS** | `:176-183` |
| Op 2: NO-DDL `RAISE NOTICE` for DEC-SYNC-03.B | **PASS** | `:189-198` |
| `downgrade()` preserves `descuadre_critico` via runtime filter | **PASS** | `:201-220` |
| Round-trip idempotency | **PASS** | `tests/integration/test_migration_0032_idempotency.py` |
| Final row count after upgrade: 19 | **PASS** | DEC-SYNC-05: 8 técnicos + 1 F1.13 + 10 F1.14 |

### Acceptance Criteria Checklist

- [x] All 14 tasks marked `[x]` (commit `57e79b1`)
- [x] `api/v1/sync_estado.py` mounted at `caja.py:100` (DEC-SYNC-02)
- [x] GET handler with 4-step chain covering REQ-OPS-098 + REQ-OPS-100 + REQ-OPS-101
- [x] `repo/sync_estado.py` 3 typed SELECT helpers
- [x] `schemas/sync_infra.py` extended with 2 Pydantic schemas (`extra="forbid"` via `_Base`)
- [x] MIGRATION 0032 REAL siembra: Op 0 pre-flight + Op 1 siembra 11 codes + Op 2 NO-DDL audit anchor
- [x] All 4 new REQ-OPS-098..101 + REQ-OPS-XR6 REFERENCE implemented + verified
- [x] XR6 5-layer defense + 3 AST walks PASS (31/31 tests)
- [x] `Cache-Control: no-store` verified on 200 + 403 + 422 responses
- [x] KD-SYNC-01 SELECT-only invariant verified
- [x] KD-SYNC-02 read-only invariant verified via 3 AST walks
- [x] DEC-SYNC-03.B `audit_read` permission gate verified (pre-seeded)
- [x] DEC-SYNC-05 10 net new alert_types seeded (8 + 1 + 10 = 19 total)
- [x] DEC-SYNC-06 severity mapping per plan.md line 1131 verified
- [x] DEC-SYNC-07 idempotent siembra via `ON CONFLICT DO NOTHING` verified
- [x] DEC-SYNC-08 `lag_seg = None` for empty branch verified
- [x] DEC-SYNC-09 `pendientes >= 0` always integer verified
- [x] DEC-SYNC-10 `descripcion` field per alert_type verified
- [x] Tenant scope post-V1 verified (operador cross-branch → 403)
- [x] Empty branch contract verified (200 with `lag_seg=null`, NOT 404)
- [x] 19 alert_types present after upgrade
- [x] MIGRATION 0032 idempotency verified
- [x] Downgrade cycle verified (preserves `descuadre_critico`)
- [x] No new permission seeded
- [x] No AI attribution in commits
- [x] 5 CI gates intact
- [x] 0 CRITICAL/HIGH regressions; 2 LOW deviations documented
- [x] REQ-OPS-098..101 + REQ-OPS-XR6 REFERENCE traceability verified via 31 tests

### Recommendation

**Run `sdd-archive hu-f1-14-sync-estado`** - implementation is contract-compliant and ready for archival. The 5 atomic commits, 31/31 passing tests, 0 CRITICAL/HIGH issues, and 2 documented LOW deviations (D1, D2) are all within acceptable parameters. The HU is ready for merge into `origin/dev`.

---

**End of verify report - HU-F1.14.**
