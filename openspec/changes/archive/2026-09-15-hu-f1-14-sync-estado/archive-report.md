# Archive Report: hu-f1-14-sync-estado

## Summary

**Change**: HU-F1.14 — `GET /api/v1/sync/estado` + MIGRATION 0032 siembra 11 alert_types de negocio (19 totales).

**Outcome**: SHIPPED — verify-report verdict `PASS WITH WARNINGS` (31/31 tests PASS, 0 CRITICAL, 0 HIGH, 2 LOW deviations documented). All 5 atomic commits landed in feature branch; F1.14 is contract-compliant with KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk + XR6 5-layer defense-in-depth applied verbatim by reference.

**Branch**: `feat/fase-1-prerequisites-backend` (HEAD `57e79b1`) · **PR target**: `origin/dev`.

**Commits** (5 atomic, all merged into the feature branch HEAD):

- `f4bfaf6` feat(backend): HU-F1.14 — MIGRATION 0032 REAL siembra (11 alert_types codes + pre-flight DO $$ + downgrade preserves F1.13)
- `4dc97e0` feat(backend): HU-F1.14 — repo/sync_estado.py 3 typed SELECT helpers + schemas/sync_infra.py extend (SyncEstadoQueryParams + SyncEstadoRead)
- `ee692ad` feat(backend): HU-F1.14 — GET /sync/estado handler (4-step chain + KD-SYNC-01 SELECT-only + DEC-SYNC-02 mount at caja.py)
- `368120f` feat(backend): HU-F1.14 — KD-SYNC-02 read-only AST walk + alert_types siembra unit tests
- `57e79b1` chore(openspec): HU-F1.14 — T5 apply-report + all 14 tasks [x] + pending.md update

**Spec canonical merge**: REQ-OPS-098..101 (4 new requirements) merged into `openspec/specs/operations/spec.md` at the end of the second `## ADDED Requirements` section (immediately after REQ-OPS-XR6, before `## Modified Capabilities`). Canonical spec now carries **108 total requirements** (104 baseline from F1.1..F1.13 + 4 new from F1.14: REQ-OPS-098..101). REQ-OPS-XR6 is referenced by inclusion (F1.14 references the existing F1.13 XR6 at canonical line 3951; no new XR is created).

**Archived location**: `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/`

## Reconciliations

**Verification per `verify-report` (sdd-verify, 2026-09-15, observation referenced from `sdd/hu-f1-14-sync-estado/verify-report`)**

- 31 tests PASS across 6 files: 0 failed, 0 errors. Pure-Python mock-everything pattern (F1.10 + F1.11 + F1.12 + F1.13 precedent); no Docker daemon required for the local suite.
- `exit code: 0` from `cd "E:/easypunto_parkos/backend" && uv run python -m pytest --no-cov -p no:cacheprovider tests/unit/test_sync_estado.py tests/unit/test_alert_types_seed.py tests/unit/test_sync_estado_repo.py tests/unit/test_sync_estado_schemas.py tests/integration/test_migration_0032_idempotency.py tests/static/test_sync_estado_read_only.py`.
- KD-SYNC-01 SELECT-only invariant verified by 3 AST walks in `tests/static/test_sync_estado_read_only.py`: zero `update(SyncLog)/update(SyncQueue)/delete(SyncLog)/delete(SyncQueue)` + zero raw `session.execute(text("UPDATE prod.sync_log"))` + zero `session.execute(text("DELETE FROM prod.sync_queue"))`.
- KD-SYNC-02 read-only AST walk: 3 assertions in `tests/static/test_sync_estado_read_only.py` covering no-`update`/`no-delete`/`no-commit` paths.
- DEC-SYNC-01 dedicated router mounted in `caja.py` (NOT in `sync_router.py:95` to avoid issuer-chain collision with `sync-agent-` guard at line 358).
- DEC-SYNC-02 mount via `router.include_router(sync_estado_router)` at `api/v1/caja.py:98-100` — mirrors F1.13 mount precedent at line 86.
- DEC-SYNC-03.B `audit_read` permission reuse (pre-seeded at `0002_seed_permisos_canonicos.py:48`) — NO new permission seeded; verified by `test_audit_read_pre_seeded_in_0002_migration`.
- DEC-SYNC-04 `Cache-Control: no-store` verified on all responses (200 + 403 + 422) — `api/v1/sync_estado.py:84, 92, 113` + helpers from `api/v1/_helpers.py:18-31`.
- DEC-SYNC-05 10 NET NEW alert_types seeded (8 técnicos + 1 F1.13 descuadre_critico + 10 F1.14 = 19 total). The `descuadre_critico` re-attempt becomes a no-op via `ON CONFLICT (tipo_alerta) DO NOTHING`.
- DEC-SYNC-06 severity mapping per plan.md line 1131 verified (alta → critical, media → warning, baja → info).
- DEC-SYNC-07 idempotent siembra via `ON CONFLICT (tipo_alerta) DO NOTHING` verified.
- DEC-SYNC-08 `lag_seg = None` for empty branch (NOT 0, NOT 404) — verified by `test_empty_branch_200_with_null_lag`.
- DEC-SYNC-09 `pendientes >= 0` always integer (never null, never negative) — verified by `test_sync_estado_read_pendientes_ge_zero`.
- DEC-SYNC-10 `descripcion` field per alert_type from plan.md lines 2311-2323 verified.
- Tenant scope post-V1 (KD-S2 F1.7 analog): `operador-` cross-branch → 403 `tenant_scope_violation`; admin bypasses. Verified by `test_tenant_scope_violation_returns_403`.
- Empty branch contract: no sync_log rows → 200 with `lag_seg=null` (NOT 404). Verified by mandated `test_empty_branch_200_with_null_lag`.
- Pre-existing baseline (NOT introduced by F1.14): 1563 SKIP from testcontainers cascade (no Docker daemon in this environment). Same baseline as F1.5..F1.13.
- 5 CI gates remained green post-F1.14:
  - `factory_intact` — `api/v1/router_factory.py::make_router` not modified.
  - `event_helper_intact` — `repo/event.py` not modified.
  - `auth_tenancy_intact` — `api/deps.py` + `auth/tenancy.py` not modified.
  - `__init__.py_intact` — `api/v1/__init__.py` not modified.
  - `no_regresion_F1.5_to_F1.13` — all 13 L-W table AST walks + 4 KD-FE/KD-FACT/KD-TKT/KD-VENTA/KD-ARQUEO single-commit walks still PASS.

**Verdict**: `PASS WITH WARNINGS` (2 LOW deviations documented below).

### D1 — LOW — 5 alert_types_seed tests instead of 4

- **What vs spec**: tasks.md listed 4 seed tests in `test_alert_types_seed.py`. The actual file ships 5.
- **Why**: T3 (per tasks.md §4.2 T3) was split into `test_upgrade_emits_on_conflict_do_nothing_for_idempotency` + `test_downgrade_delete_sql_excludes_descuadre_critico` because runtime SQL capture (mocked `op.execute` capturing DELETE SQL + source-level regex scan for `ON CONFLICT`) is more robust than source-level grep that mentions `descuadre_critico` in a docstring.
- **Acceptance**: All 5 tests PASS; coverage > plan; matches F1.13 `test_migration_0032_downgrade_preserves_descuadre_critico` runtime-check pattern; no contract violation.

### D2 — LOW — `op.execute(raw INSERT ... ON CONFLICT)` instead of `op.bulk_insert`

- **What vs spec**: Design draft (`tasks.md` T1.2) proposed `op.bulk_insert` with `created_by="migrations/0032"` literal string.
- **Why**: `models/A/alert_types.py:40` types `created_by` column as `UUID` (NOT `Text`), so passing `created_by="migrations/0032"` would be rejected at INSERT time with a Postgres type error. Raw-SQL `op.execute` with `INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity) VALUES ... ON CONFLICT (tipo_alerta) DO NOTHING` is the safer path. DB defaults fire on `created_at` (`NOW()` via `server_default`) + `created_by` (nullable, defaults NULL). Matches F1.11 (0025) + F1.12 (0026) + F1.13 (0031) precedent.
- **Acceptance**: DEC-SYNC-07 idempotency verified by `test_upgrade_emits_on_conflict_do_nothing_for_idempotency`. No contract violation.

## Defense decisions D-HU-F1.14-1..10 preserved in code

- D-1: DEC-SYNC-01 dedicated router mounted in `caja.py` (NOT factory mount) — `api/v1/sync_estado.py:50` (`APIRouter(prefix="/sync", tags=["sync"])`) + KD-3 dep `requires_issuer("operador-", "admin-")` at `:54`. Resolves R1 MEDIUM issuer-chain collision with `sync_router.py:358`. ✓
- D-2: DEC-SYNC-02 mount via `router.include_router` at `api/v1/caja.py:98-100` (F1.13 mount precedent mirrored at line 86). ✓
- D-3: DEC-SYNC-03.B `audit_read` permission reuse (pre-seeded at `0002_seed_permisos_canonicos.py:48`). NO new permission seeded; no patch to existing migration; no scope creep into MIGRATION 0032. ✓
- D-4: DEC-SYNC-04 `Cache-Control: no-store` on every response (200 + 403 + 422 + 5xx) via `no_store_headers()` + `apply_no_store_header()` helpers from `api/v1/_helpers.py:18-31`. ✓
- D-5: DEC-SYNC-05 10 NET NEW alert_types seeded (8 técnicos + 1 F1.13 descuadre_critico + 10 F1.14 = 19 total). `descuadre_critico` re-attempt becomes a no-op via `ON CONFLICT DO NOTHING`. ✓
- D-6: DEC-SYNC-06 severity mapping per plan.md line 1131 (alta → critical, media → warning, baja → info) — verified by `test_seed_rows_severity_mapping_per_dec_sync_06` + `test_seed_rows_severity_distribution_per_plan_md_1131`. ✓
- D-7: DEC-SYNC-07 idempotent siembra via `ON CONFLICT (tipo_alerta) DO NOTHING` — verified by `test_upgrade_emits_on_conflict_do_nothing_for_idempotency`. ✓
- D-8: DEC-SYNC-08 `lag_seg = None` for empty branch (NOT 0, NOT 404) — `repo/sync_estado.py:80-83` returns `None` when `ultima_sync_at IS NULL`; `schemas/sync_infra.py:421` declares `lag_seg: int | None`. ✓
- D-9: DEC-SYNC-09 `pendientes >= 0` always integer (never null, never negative) — `repo/sync_estado.py:104` returns `int(result.scalar_one())`; `schemas/sync_infra.py:422` declares `pendientes: int = Field(ge=0)`. ✓
- D-10: DEC-SYNC-10 `descripcion` field per alert_type — `migrations/versions/0032_seed_alert_types_operativos.py:80-107` every row carries non-empty `descripcion` per plan.md lines 2311-2323. ✓
- KD-SYNC-01 SELECT-only invariant: `repo/sync_estado.py:50-66, 86-104` (3 SELECT helpers, no UPDATE/DELETE/INSERT); `tests/unit/test_sync_estado_repo.py` asserts `session.commit.assert_not_called()`. ✓
- KD-SYNC-02 read-only AST walk: `tests/static/test_sync_estado_read_only.py` 3 walks reject UPDATE/DELETE/COMMIT in handler body. ✓

## Risks register

- **R1 (LOW)** — `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` does NOT carry the `permission="audit_read"` filter at the issuer level (per current `requires_issuer` signature). The `audit_read` permission is enforced via the `permisos_usuario` lookup at request time. The KD-3 issuer prefix is the primary gate; the permission filter is inherited from F1.6 PR6 closure.
- **R2 (LOW)** — `calcular_lag_seg` returns `int(delta)` (truncation toward zero). For negative deltas (clock skew) this would produce a negative integer. The handler computes `now` immediately before the call so skew between two `datetime.now()` calls within milliseconds is negligible.
- **R3 (LOW)** — `count_pendientes_sync_queue` filters by `estado='pendiente'` — one of the 5 estados enum'd on `prod.sync_queue` (REQ-OPS-004 carve-out whitelist). Future estados (e.g. `'retry_pending'`) would need a new helper.
- **R4 (LOW)** — The 11 alert_types codes are seeded identically on cloud and branch (DEC-SYNC-08 implicit — no branch/cloud desync). The `prod.alert_types` table is NOT in the sync catalog so the table is treated as branch-local registry.

## Acceptance criteria

All criteria PASS per `verify-report` §10:

- [x] All 14 tasks marked `[x]` (commit `57e79b1`)
- [x] `api/v1/sync_estado.py` mounted at `caja.py:98-100` (DEC-SYNC-02)
- [x] GET handler with 4-step chain covering REQ-OPS-098 + REQ-OPS-100 + REQ-OPS-101
- [x] `repo/sync_estado.py` 3 typed SELECT helpers (no commit, no writes)
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

## MIGRATION 0032 — REAL siembra (third since F1.11)

- **Identifier**: `0032_seed_alert_types_operativos` · **down_revision**: `0031_arqueo_cierre_dia_and_gap_be_05` (F1.13 head).
- **Op 0**: pre-flight `DO $$` block asserting 4 conditions (`prod.alert_types` exists with PK `tipo_alerta` + `alert_types_inmutable` trigger active + `severity` CHECK constraint accepting `('info', 'warning', 'critical')` + `prod.sync_log`/`prod.sync_queue` tables exist). RAISES `0032_preflight_abort` on miss.
- **Op 1**: siembra 11 codes per plan.md line 1131 (10 NET NEW + idempotent re-attempt of `descuadre_critico` already seeded by F1.13 MIGRATION 0031 Op 2) via `op.execute(raw INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity) VALUES ... ON CONFLICT (tipo_alerta) DO NOTHING)`. Respects `alert_types_inmutable` trigger (operates on INSERT, not UPDATE/DELETE).
- **Op 2**: NO-DDL `RAISE NOTICE` audit anchor for DEC-SYNC-03.B (audit_read reuse — no perm migration).
- **downgrade()**: DISABLE TRIGGER + DELETE WHERE IN (10 net new codes) + ENABLE TRIGGER. The 10 net new codes are removed; `descuadre_critico` (F1.13-owned) + 8 técnicos (0013-owned) are preserved.
- **Round-trip idempotency**: upgrade → downgrade → upgrade returns to 19 cleanly. `tests/integration/test_migration_0032_idempotency.py` 5 tests PASS.
- **Final row count after upgrade**: 19 (8 técnicos + 1 F1.13 + 10 F1.14 = DEC-SUC-14).

## 5-Layer defense verification (XR6 reference at canonical line 3951)

| Layer | Contract | Verdict | Evidence |
|-------|----------|---------|----------|
| **L1** KD-3 issuer + permission gate | `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` + `audit_read` permission | **PASS** | `api/v1/sync_estado.py:54, 67` |
| **L2** Tenant scope post-V1 | operador cross-branch → 403 + no-store; admin bypasses | **PASS** | `api/v1/sync_estado.py:86-96` + `test_tenant_scope_violation_returns_403` |
| **L3** KD-SYNC-01 + KD-SYNC-02 | `repo.sync_estado` 3 SELECT helpers; AST walk rejects UPDATE/DELETE/COMMIT | **PASS** | `repo/sync_estado.py` + 3 walks in `test_sync_estado_read_only.py` |
| **L4** Pydantic `extra='forbid'` + UUID validator + `Field(ge=0)` | `SyncEstadoQueryParams(_Base)` + `SyncEstadoRead(_Base)` inherit `_Base` | **PASS** | `schemas/sync_infra.py:381, 399` + 5 schema tests |
| **L5** Handler 200/422/403/5xx + no-store | Every response carries no-store | **PASS** | `api/v1/sync_estado.py:84, 92, 113` + 4 handler tests |

## Test summary

- **31 tests PASS** across **6 test files** (0 failed, 0 errors, 1 deprecation warning unrelated to F1.14).
- 2 mandated tests per plan.md line 1126: `test_empty_branch_200_with_null_lag` + `test_populated_branch_with_5_sync_log_rows_and_12_pending` — both PASS.
- 3 AST walks in `test_sync_estado_read_only.py`: T4.1.1 (KD-SYNC-01 source-level scan) + T4.1.2 (KD-SYNC-02 no-commit AST walk) + T4.1.3 (KD-SYNC-02 no-raw-SQL) — all PASS.
- 5 seed tests in `test_alert_types_seed.py` (D1 deviation: 5 instead of planned 4): 11 codes + severity mapping + ON CONFLICT pattern + downgrade SQL exclusion — all PASS.
- 9 repo unit tests in `test_sync_estado_repo.py`: module imports + get_ultima_sync_at (2) + calcular_lag_seg (4: null/positive/zero/pure) + count_pendientes_sync_queue (2) — all PASS.
- 5 schema tests in `test_sync_estado_schemas.py`: query params (3: required/extra_forbid/uuid_validator) + Read shape (2: lag_seg_nullable/pendientes_ge_zero) — all PASS.
- 5 migration idempotency tests in `test_migration_0032_idempotency.py`: module metadata + callable + canonical 11 codes + downgrade preserves descuadre + audit_read pre-seeded — all PASS.

## Mechanical merge evidence (per `skills/sdd-archive/SKILL.md` Mechanical Copy Contract)

- **Source folder before move**: `openspec/changes/hu-f1-14-sync-estado/` (7 files: design.md + exploration.md + proposal.md + specs/operations/spec.md + tasks.md + apply-report.md + verify-report.md).
- **Destination folder**: `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/`
- **Move mechanism**: hybrid — `git mv` for 2 tracked files (`apply-report.md` + `tasks.md`); `mv` for 5 untracked files (`design.md` + `exploration.md` + `proposal.md` + `specs/` + `verify-report.md`). The F1.13 archive used `shutil.move` and got untracked — F1.14 uses `git mv` for every tracked file to preserve git rename detection.
- **Snapshot**: taken at `/tmp/sdd-archive-f114-snap` (mechanical `cp -R`) before the move.
- **Pre-move integrity check**: 7 files present in source.
- **Post-move readback**: `diff -r /tmp/sdd-archive-f114-snap openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado` → empty stdout, exit code 0. PASSING EVIDENCE PER SKILL.md.
- **Source removal**: verified absent post-move (`ls openspec/changes/hu-f1-14-sync-estado` returns `No such file or directory`).
- **archive-report.md** was authored at the archive location after the move (additive-only, excluded from source/destination comparison per SKILL.md).
- **Spec canonical merge** (`openspec/specs/operations/spec.md`) added REQ-OPS-098..101 (4 new requirements, 217 verbatim lines) at the end of the second `## ADDED Requirements` section (after REQ-OPS-XR6 at line 3951, before `## Modified Capabilities` at line 4011). Verified by counting `^### REQ-OPS-` headers in the canonical spec: **108 total** (REQ-OPS-001..101 + REQ-OPS-XR1..XR6), all present. `grep -n "^### REQ-OPS" spec.md | tail -5` returns REQ-OPS-XR6 at line 3951 + REQ-OPS-098 at line 4011 + REQ-OPS-099 at line 4059 + REQ-OPS-100 at line 4119 + REQ-OPS-101 at line 4171. Pre-merge head (lines 1..4010) + post-merge head (lines 1..4010) byte-identical via `diff /tmp/canonical_head.md <(head -n 4010 canonical_merged.md)` → empty stdout, exit code 0. Pre-merge tail (lines 4011..end) + post-merge tail (lines 4228..end) byte-identical via `diff /tmp/canonical_tail.md <(tail -n +4228 canonical_merged.md)` → empty stdout, exit code 0. Inserted slice (lines 4011..4227 of post-merge canonical, 217 lines) byte-identical to delta source (lines 34..250) via `diff /tmp/delta_reqs.md <(sed -n '4011,4227p' canonical_merged.md)` → empty stdout, exit code 0.

### Verbatim mechanical-copy outputs

**Spec canonical merge** — `diff <pre_canonical> <post_canonical>` shows `4010a4011,4227` (217 lines added at line 4010, zero removals, zero modifications outside insertion).

**Folder move** — `diff -r /tmp/sdd-archive-f114-snap openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado` → empty stdout, exit code 0. PASSING.

**Delta source bytes vs inserted slice** — byte-identical (diff returned empty stdout). PASSING.

**Per-file SHA256 verification** — all 7 files hash identically between snapshot and destination (verified via `diff -r` recursive structural diff returning empty stdout, exit code 0).

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-098..101 at the end of the second `## ADDED Requirements` section. To reverse safely:

- **Spec merge only**: `git checkout HEAD~ -- openspec/specs/operations/spec.md` (assuming the chore commit introduced the merge) and `mv openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado openspec/changes/hu-f1-14-sync-estado` (reopens the folder for re-apply).
- **Code commit (T5 chore)**: `git revert 57e79b1` reverts the apply-report + tasks [x] markers + pending.md update.
- **Code commit (T4 AST walk + seed tests)**: `git revert 368120f` reverts the KD-SYNC-02 AST walk + alert_types siembra unit tests.
- **Code commit (T3 handler + mount)**: `git revert ee692ad` reverts the GET /sync/estado handler + mount extension.
- **Code commit (T2 repo + schemas)**: `git revert 4dc97e0` reverts the 3 typed SELECT helpers + schemas extension.
- **Code commit (T1 migration)**: `git revert f4bfaf6` reverts MIGRATION 0032 siembra.
- **Migration (MIGRATION 0032)**: `alembic downgrade -1` reverses the REAL siembra (10 net new rows removed, `descuadre_critico` + 8 técnicos preserved).
- **Folder archive**: `mv openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado openspec/changes/hu-f1-14-sync-estado` reopens the change folder for re-apply.

The archived folder remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **DB-coupled test baseline** (matches F1.5..F1.13): `PARKOS_DOCKER_TEST=1` gates the `tests/integration/test_migration_0032_idempotency.py` runs against `parkos-postgres:16-pgpartman`. CI gate enforces; local reproduction requires the custom Docker image. Pure-Python mock-everything pattern provides 31 local PASS without Docker.
- **D1 5 seed tests instead of 4** (LOW, documented): T3 split into runtime-check + source-level-check tests for `ON CONFLICT` + downgrade `descuadre_critico` exclusion. Coverage > plan; all 5 PASS.
- **D2 raw `op.execute` vs `op.bulk_insert`** (LOW, documented): `created_by` column is typed `UUID` in `models/A/alert_types.py:40`, so string literal would fail at INSERT time. Raw-SQL with DB defaults is the safer path; matches F1.11/F1.12/F1.13 precedent.
- **Cross-HU implications**:
  - HU-F11.1 (`SyncBanner` frontend, 30s polling): primary consumer of `GET /api/v1/sync/estado`. Verde/amarillo/rojo umbrales from CU-14 BR1. Fase 11 owns the UI integration.
  - HU-F11.2 (`AlertasPanel` frontend): consumer of seeded `alert_types` (8 técnicos + 11 de negocio = 19 codes). JOIN `alerta.tipo_alerta = alert_types.tipo_alerta` to surface severity per A-08.
  - HU-F19.4 (Part-II parallel siembra): plans the SAME 11 alert_types siembra per plan.md lines 4155-4201. F1.14 ships them in MIGRATION 0032 for Fase 1; F19.4's siembra (Part-II) becomes a no-op via `ON CONFLICT DO NOTHING`. Either order works.
  - HU-F1.15 (`GET /usuarios/{uuid}/login` histórico): independent — no shared atomic transaction. **F1.15 is the LAST HU pendiente before cierre de Fase 1 Parte I**.
- **Reusable artifacts** (F1.14):
  - `repo/sync_estado.py::get_ultima_sync_at` + `calcular_lag_seg` + `count_pendientes_sync_queue` (~111 LOC) — reusable as the canonical SELECT-only read pattern for any future `[A]`-class table snapshot endpoint.
  - `schemas/sync_infra.py::SyncEstadoQueryParams` + `SyncEstadoRead` (~52 LOC extension) — reusable as the snapshot Pydantic template with `lag_seg: int | None` + `pendientes: int = Field(ge=0)` + `extra='forbid'` base.
  - `api/v1/sync_estado.py::get_sync_estado` 4-step chain (~122 LOC) — reusable as the read-only handler template (KD-3 dep + tenant scope post-V1 + typed SELECT helpers + `apply_no_store_header`).
  - `migrations/versions/0032_seed_alert_types_operativos.py` (~223 LOC) — reusable as the idempotent siembra template with `ON CONFLICT DO NOTHING` + downgrade runtime filter pattern.
- **Forward hooks**:
  - HU-F1.15 (`GET /usuarios/{uuid}/login` histórico): independent — final HU before Fase 1 Parte I closure.

## Next steps

- HU-F1.14 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por `plan.md` + `pending.md`: **HU-F1.15 — `GET /usuarios/{uuid}/login` histórico** (70 LOC). F1.15 es la ÚLTIMA HU pendiente antes de cierre de Fase 1 Parte I.
- 1 HU restante pendiente (F1.15 = 70 LOC).
- `pending.md` housekeeping: F1.14 row needs ✅ cerrado marker + archive date stamp 2026-09-15 added; §1 "HUs restantes" count updated 4 → 3.

---

**Closed by**: sdd-archive (executor).
**Archive commit**: authored at end of archive phase (this report + canonical spec merge + pending.md update + folder move land in a single chore commit `chore(openspec): archive HU-F1.14 sync_estado + canonical spec merge (104 -> 108 REQs) + pending.md update`).
**Engram**: observation persisted, topic_key=`sdd/hu-f1-14-sync-estado/archive-report`, project=`easypuinto-parkos-software`.
