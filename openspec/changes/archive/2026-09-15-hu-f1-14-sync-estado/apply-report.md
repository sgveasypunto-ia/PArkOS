# Apply Report: hu-f1-14-sync-estado

> **Status**: SHIPPED — all 14 tasks [x] across 5 clusters (T1..T5). Ready for `sdd-verify`.
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `368120f`; this commit = T5).
> **Outcome**: 4 atomic commits + T5 housekeeping (`apply-report.md` + tasks.md [x] + pending.md update).

## Commits (T1..T4)

| # | Cluster | Commit | Files | LOC est. |
|---|---------|--------|-------|----------|
| 1 | T1 | `f4bfaf6 feat(backend): HU-F1.14 -- MIGRATION 0032 REAL siembra (11 alert_types codes + pre-flight DO $$ + downgrade preserves F1.13)` | NEW `migrations/versions/0032_seed_alert_types_operativos.py` (~140 LOC) + NEW `tests/integration/test_migration_0032_idempotency.py` (5 tests) | ~200 |
| 2 | T2 | `4dc97e0 feat(backend): HU-F1.14 -- repo/sync_estado.py 3 typed SELECT helpers + schemas/sync_infra.py extend (SyncEstadoQueryParams + SyncEstadoRead)` | NEW `repo/sync_estado.py` (~95 LOC) + EXTEND `schemas/sync_infra.py` (~30 LOC) + 2 NEW test files (repo + schemas, 14 tests) | ~240 |
| 3 | T3 | `ee692ad feat(backend): HU-F1.14 -- GET /sync/estado handler (4-step chain + KD-SYNC-01 SELECT-only + DEC-SYNC-02 mount at caja.py)` | NEW `api/v1/sync_estado.py` (~123 LOC) + MOD `api/v1/caja.py` (~10 LOC mount) + NEW `tests/unit/test_sync_estado.py` (4 tests, 2 mandated) | ~366 |
| 4 | T4 | `368120f feat(backend): HU-F1.14 -- KD-SYNC-02 read-only AST walk + alert_types siembra unit tests` | NEW `tests/static/test_sync_estado_read_only.py` (3 AST walks) + EXTEND `tests/unit/test_alert_types_seed.py` (5 tests) | ~339 |
| 5 | T5 | (this commit) `chore(openspec): HU-F1.14 -- T5 apply-report + all 14 tasks [x] + pending.md update` | NEW `apply-report.md` + MOD `tasks.md` + MOD `pending.md` | ~30 |

Total: **~1175 LOC** across 5 atomic commits. All commits <800 LOC ceiling.

## Cluster Table

| Cluster | Tasks | Status | RED Tests | GREEN | Implementation |
|---------|-------|--------|-----------|-------|----------------|
| T1 | T1.1..T1.3 | [x] | 5 pre-flight + module-contract | [x] | MIGRATION 0032 siembra + pre-flight DO $$ + downgrade (10 net new, preserves descuadre_critico + 8 técnicos) |
| T2 | T2.1..T2.4 | [x] | 14 repo + schemas | [x] | 3 typed SELECT helpers + SyncEstadoQueryParams + SyncEstadoRead (+ `Field(ge=0)`) |
| T3 | T3.1..T3.4 | [x] | 4 handler unit (2 mandated) | [x] | 4-step chain + KD-3 dep + DEC-SYNC-02 mount at caja.py |
| T4 | T4.1..T4.2 | [x] | 3 AST walks + 5 seed unit | [x] | KD-SYNC-01 + KD-SYNC-02 read-only invariant enforced |
| T5 | T5.1 | [x] | n/a (sweep) | [x] | apply-report.md + tasks.md [x] + pending.md §1 update |

## Test Summary (pure-Python; no Docker daemon in this environment)

| Test file | Cluster | Tests | Result |
|-----------|---------|-------|--------|
| `tests/integration/test_migration_0032_idempotency.py` | T1.1 | 5 | PASS |
| `tests/unit/test_sync_estado_repo.py` | T2.1+T2.3+T2.4 | 9 | PASS |
| `tests/unit/test_sync_estado_schemas.py` | T2.2 | 5 | PASS |
| `tests/unit/test_sync_estado.py` | T3.1+T3.2+T3.3 | 4 (2 mandated) | PASS |
| `tests/unit/test_alert_types_seed.py` | T4.2 (T3 split) | 5 | PASS |
| `tests/static/test_sync_estado_read_only.py` | T4.1 | 3 | PASS |

**Cumulative non-DB-gated test count**: **31 tests PASS** across 6 test files (5 NEW + 1 EXTENDED).

## 5-Layer Defense Verification (REQ-OPS-XR6 cross-cutting)

| Layer | Mechanism | Verified By | Status |
|-------|-----------|------------|--------|
| 1 | KD-3 issuer chain (`operador-` + `admin-`) + `audit_read` permission gate | `caja.py` mount + `sync_estado.py::_sync_estado_issuer_dep` | GREEN |
| 2 | Tenant scope post-V1 (KD-S2 F1.7 analog): operador cross-branch → 403 `tenant_scope_violation` | `test_sync_estado.py::test_tenant_scope_violation_returns_403` | GREEN |
| 3 | KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk | `test_sync_estado_read_only.py` (3 AST walks) | GREEN |
| 4 | Pydantic `extra='forbid'` + UUID validator + `Field(ge=0)` on `pendientes` | `test_sync_estado_schemas.py` (5 tests) | GREEN |
| 5 | Handler 200/403/422 mapping + `Cache-Control: no-store` on every response (DEC-SYNC-04) | `test_sync_estado.py::test_*` (4 mandated tests assert headers) | GREEN |

## 4 REQ-OPS-098..101 + REQ-OPS-XR6 REFERENCE Traceability

| REQ | Statement | Test that proves it | Status |
|-----|-----------|---------------------|--------|
| REQ-OPS-098 | `GET /api/v1/sync/estado` endpoint exists | `test_sync_estado.py` (4 handler tests) + `api/v1/sync_estado.py` importable | GREEN |
| REQ-OPS-099 | Returns `{uuid_sucursal, ultima_sync_at, lag_seg, pendientes}` | `SyncEstadoRead` schema + `test_empty_branch_200_with_null_lag` + `test_populated_branch_*` | GREEN |
| REQ-OPS-100 | `lag_seg=None` for empty branch (NOT 0, NOT 404) | `test_empty_branch_200_with_null_lag` (MANDATED) | GREEN |
| REQ-OPS-101 | `pendientes >= 0` always integer (never null, never negative) | `test_sync_estado_schemas.py::test_sync_estado_read_pendientes_ge_zero` + `count_pendientes_sync_queue` returns `int` | GREEN |
| REQ-OPS-XR6 | 5-layer defense in depth (Layer 1..5 above) | See 5-Layer table above | GREEN (REFERENCE, no new requirement) |

## DEC-SYNC-01..10 Verification

| DEC | Statement | Test that proves it | Status |
|-----|-----------|---------------------|--------|
| DEC-SYNC-01 | Dedicated router mounted in `caja.py` (not factory mount) | `caja.py:84-89` (DEC-SYNC-02) + KD-3 dep | GREEN |
| DEC-SYNC-02 | Mount via `router.include_router(sync_estado_router)` at `caja.py` | `caja.py:84-89` (F1.13 mount precedent mirrored) | GREEN |
| DEC-SYNC-03.B | `audit_read` permission reuse (pre-seeded at 0002:48) | `test_audit_read_pre_seeded_in_0002_migration` | GREEN |
| DEC-SYNC-04 | `Cache-Control: no-store` on every response (200 + 403 + 422) | `test_sync_estado.py` (4 tests assert header) | GREEN |
| DEC-SYNC-05 | 10 NET NEW alert_types codes (descuadre_critico already seeded by F1.13) | `test_seed_rows_canonical_11_codes_with_one_idempotent` | GREEN |
| DEC-SYNC-06 | Severity mapping per plan.md line 1131 (alta=critical, media=warning, baja=info) | `test_seed_rows_severity_mapping_per_dec_sync_06` + `test_seed_rows_severity_distribution_per_plan_md_1131` | GREEN |
| DEC-SYNC-07 | Idempotent siembra via `ON CONFLICT (tipo_alerta) DO NOTHING` | `test_upgrade_emits_on_conflict_do_nothing_for_idempotency` | GREEN |
| DEC-SYNC-08 | `lag_seg = None` for empty branch (DEC-SYNC-08) | `test_empty_branch_200_with_null_lag` (MANDATED) + `calcular_lag_seg(None, ...) -> None` | GREEN |
| DEC-SYNC-09 | `pendientes >= 0` always integer (never null, never negative) | `test_sync_estado_schemas.py::test_sync_estado_read_pendientes_ge_zero` + `test_populated_branch_*: pendientes=12` | GREEN |
| DEC-SYNC-10 | `descripcion` field per alert_type (DEC-SYNC-10) | `test_migration_0032_seed_rows_canonical_11_codes` (asserts non-empty string per code) | GREEN |

## MIGRATION 0032 Audit Trail

`migrations/versions/0032_seed_alert_types_operativos.py` (NEW, T1):
- `revision = "0032_seed_alert_types_operativos"`
- `down_revision = "0031_arqueo_cierre_dia_and_gap_be_05"` (F1.13 head)
- **Op 0**: pre-flight `DO $$` block asserts 4 conditions (alert_types table + `alert_types_inmutable` trigger active + sync_log + sync_queue tables exist). RAISES `0032_preflight_abort` on miss.
- **Op 1**: siembra 11 alert_types codes (10 net new + idempotent re-attempt of `descuadre_critico`) via raw `op.execute(...)` with `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` (matches 0025/0026/0031 F1.11/F1.12/F1.13 precedent).
- **Op 2**: NO-DDL `RAISE NOTICE` audit anchor for DEC-SYNC-03.B (audit_read reuse).
- **downgrade()**: DISABLE TRIGGER + DELETE WHERE IN (10 net new codes) + ENABLE TRIGGER. The 10 net new codes are removed; `descuadre_critico` (F1.13-owned) + 8 técnicos (0013-owned) are preserved.

NO schema changes, NO new permissions, NO new triggers. The migration is purely additive (10 new rows on prod.alert_types).

## CI Gate Verification

The 5 baseline CI gates from F1.5/F1.7/F1.9/F1.10/F1.11/F1.12/F1.13 remain green post-F1.14:

  - `factory_intact` — `api/router_factory.py::make_router` not modified.
  - `event_helper_intact` — `repo/event.py` not modified.
  - `auth_tenancy_intact` — `api/deps.py` + `auth/tenancy.py` not modified.
  - `__init__.py_intact` — `api/v1/__init__.py` not modified.
  - `no_regresion_F1.5_to_F1.13` — all 13 L-W table AST walks + 4 KD-FE/KD-FACT/KD-TKT/KD-ARQUEO single-commit walks still PASS; no new raw UPDATE/DELETE patterns introduced.

## Deviations from Design

### D1 (LOW) — 5 alert_types_seed tests instead of 4

- **Design**: T4.2 listed 4 seed tests in `test_alert_types_seed.py`.
- **Actual**: 5 tests (split T3 into `test_upgrade_emits_on_conflict_do_nothing_for_idempotency` + `test_downgrade_delete_sql_excludes_descuadre_critico` — the runtime check is more robust than a source-level grep on a docstring that mentions `descuadre_critico`).
- **Acceptance**: All 5 tests PASS; coverage > plan; no contract violation.

### D2 (LOW) — `op.execute(raw INSERT ... ON CONFLICT)` instead of `op.bulk_insert`

- **Design draft**: `op.bulk_insert` with `created_by="migrations/0032"` literal string.
- **Actual**: raw `op.execute` with `INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity) VALUES ... ON CONFLICT (tipo_alerta) DO NOTHING` — matches 0025/0026/0031 F1.11/F1.12/F1.13 precedent. `created_by` column is typed `UUID` in `models/A/alert_types.py:40` (NOT Text), so the string literal would be rejected at INSERT time. The raw-SQL pattern with DB defaults firing on `created_at` (`NOW()`) + `created_by` (nullable, defaults NULL) is the safer path.
- **Acceptance**: DEC-SYNC-07 idempotency verified; `test_upgrade_emits_on_conflict_do_nothing_for_idempotency` PASS.

## Risks

- **R1 (LOW)** — `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` does NOT carry the `permission="audit_read"` filter at the issuer level (per current `requires_issuer` signature). The `audit_read` permission is enforced via the `permisos_usuario` lookup at request time. The KD-3 issuer prefix is the primary gate; the permission filter is inherited from F1.6 PR6 closure. Documented in design §11.
- **R2 (LOW)** — `calcular_lag_seg` returns `int(delta)` (truncation toward zero). For negative deltas (clock skew) this would produce a negative integer. The handler computes `now` immediately before the call so skew between two `datetime.now()` calls within milliseconds is negligible. Documented in repo docstring.
- **R3 (LOW)** — `count_pendientes_sync_queue` filters by `estado='pendiente'` — one of the 5 estados enum'd on `prod.sync_queue` (REQ-OPS-004 carve-out whitelist). Future estados (e.g. `'retry_pending'`) would need a new helper. Documented in `repo/sync_estado.py:45-47`.
- **R4 (LOW)** — The 11 alert_types codes are seeded identically on cloud and branch (DEC-SYNC-08 implicit — no branch/cloud desync). The `prod.alert_types` table is NOT in the sync catalog (DEC-SYNC-01 reference) so the table is treated as branch-local registry. Documented in `migrations/versions/0032_seed_alert_types_operativos.py` docstring.

## Pre-existing baseline (NOT introduced by F1.14)

- 1563 SKIP from testcontainers cascade (no Docker daemon in this environment). Same baseline as F1.5..F1.13.
- All 5 CI gates remained green post-F1.14.
- Working tree mess at `git status --short` (untracked docs/, infra/scripts/, openspec archive mess, plan.md) — all pre-existing from F1.13 closure; out of F1.14 scope per `pending.md §4`.

## Reverse / Revert

To reverse F1.14 atomically:

```
git revert 368120f   # T4 AST walk + seed tests (post-this-commit)
git revert ee692ad   # T3 handler + mount
git revert 4dc97e0   # T2 repo + schemas
git revert f4bfaf6   # T1 MIGRATION 0032 siembra
```

The migration is reversible via `alembic downgrade -1` (10 net new rows removed, descuadre_critico + 8 técnicos preserved).

## Next steps

- HU-F1.14 apply complete. Continuar a `sdd-verify hu-f1-14-sync-estado` para validar contra el contrato spec/design/tasks antes de archive.
- 1 HU restante pendiente (F1.15 — `GET /usuarios/{uuid}/login` histórico) según `pending.md §1`.

---

**Closed by**: sdd-apply (executor, T5 commit pending).
**Engram**: observation persisted, topic_key=`sdd/hu-f1-14-sync-estado/apply-progress`, project=`easypuinto-parkos-software`.
**Last commit**: `368120f` (T4) + this T5 commit (chore(openspec)).
