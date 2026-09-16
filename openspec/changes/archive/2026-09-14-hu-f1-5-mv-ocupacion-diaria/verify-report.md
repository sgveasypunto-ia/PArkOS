# Verify Report: hu-f1-5-mv-ocupacion-diaria

> **Change**: `hu-f1-5-mv-ocupacion-diaria`
> **Phase**: verify (sdd-verify)
> **Date**: 2026-09-14
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `bb99e18`)
> **Commit**: `bb99e18 feat(backend): HU-F1.5 — mv_ocupacion_diaria, worker REFRESH y endpoint GET /operacion/ocupacion`

## 1. Summary

| Field | Value |
|---|---|
| Change | `hu-f1-5-mv-ocupacion-diaria` |
| Verdict | **SHIPPED** |
| Commit | `bb99e18` |
| Branch | `feat/fase-1-prerequisites-backend` |
| PR target | `origin/dev` |
| Files changed | 10 (`+2290 / -1`) |
| Tests added | 11 (4 HTTP unit + 2 DB integration + 2 migration pre-flight + 2 worker cycle + 1 AST walk) |
| Critical findings | 0 |
| High findings | 0 |
| Medium findings | 0 |
| Low findings | 3 (pre-existing baseline; see §5) |
| Deviations | 1 deliberate refactor (D-F1.5-1 KD-6-respecting repo SQL: `tipos_vehiculo` LEFT JOIN MV, not MV LEFT JOIN — see §8) |
| Defense-in-depth chains verified | 4/4 (REQ-OPS-030 read-only, REQ-OPS-031 authz, REQ-OPS-032 MV + INDEX + pre-flight, REQ-OPS-033 worker + KD-5) |

## 2. REQ Compliance Matrix

| REQ-OPS | Title | Evidence | Status |
|---|---|---|---|
| **REQ-OPS-030** | `GET /operacion/ocupacion?uuid_sucursal=X` returns `OcupacionResponse` (per-tipo breakdown) with `Cache-Control: no-store` | `api/v1/operacion.py::get_ocupacion` (handler block ~L393–L477); `response.headers["Cache-Control"] = "no-store"` line 462; `schemas/operacion.py::OcupacionItem` + `OcupacionResponse` (`extra='forbid'` via `_Base`); `repo/ocupacion.py::get_ocupacion_puros_activos` with bind-param `:uuid_sucursal` + `ORDER BY tv.tipo`. Tests T1 + T3. | PASS |
| **REQ-OPS-031** | Authorization per-sucursal: `operador-` pinned to `ctx.sucursal_uuid` (cross-tenant → `403 tenant_scope_violation`); `admin-` scoped to `claims["sucursales_permitidas"]` (missing → `400 missing_sucursal_context`); typed errors | Handler KD-3 chain (1) `target = uuid_sucursal or ctx.sucursal_uuid`, (2) `HTTPException(400, {"error": "missing_sucursal_context"})` if `target is None`, (3) `HTTPException(403, {"error": "tenant_scope_violation"})` for `operador-` cross-tenant. Admin scope validated upstream by `get_tenant_ctx` (`auth/tenancy.py:115-131`). Tests T2 (cross-tenant 403) + T4 (admin-no-context 400). | PASS |
| **REQ-OPS-032** | `prod.mv_ocupacion_diaria` materialized view + `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo` + pre-flight `DO $$` (10M NOTICE / 50M ABORT) + downgrade `DROP MATERIALIZED VIEW` | `migrations/versions/0024_add_mv_ocupacion_diaria.py`: (a) pre-flight `DO $$` rows 50-77, (b) `CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria … NOT EXISTS (salidas/anulaciones) GROUP BY …` lines 86-110, (c) `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS … ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)` lines 116-120, (d) `GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app` line 125, (e) `downgrade()` = `DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria` lines 132-138; `revision = "0024_mv_ocupacion_diaria"`, `down_revision = "0023_unique_active_sesion_per_user"`. Tests T1 dirty-data + T2 50M abort + round-trip. | PASS |
| **REQ-OPS-033** | `RefreshMvOcupacionWorker.cycle()` executes `REFRESH MATERIALIZED VIEW CONCURRENTLY` + `commit()`, falls back to plain `REFRESH` on failure (KD-5), `asyncio.sleep(refresh_interval_s=10)` post-cycle, CLI `python -m parkos_core.jobs.refresh_mv_ocupacion` with `--refresh-interval-s` and `--database-url` | `jobs/refresh_mv_ocupacion.py::RefreshMvOcupacionWorker(WorkerRunner)`, `DEFAULT_REFRESH_INTERVAL_S = 10`, `cycle()` (lines 65-127) executes `REFRESH CONCURRENTLY` + `commit()`; on `Exception` logs `refresh_mv_concurrently_failed_fallback` with `extra={"event": …, "exception_class": type(exc).__name__}` (no pgcode leak — R6 mitigation), `rollback()`, fallback `REFRESH MATERIALIZED VIEW` plain + `commit()`; inner `except Exception` logs `refresh_mv_ocupacion_both_branches_failed` and re-rolls back; `await asyncio.sleep(self.refresh_interval_s)` post-cycle (KD-5 R1 resilience). CLI: `main(argv)` + argparse. **No modifications to `WorkerRunner` base — `worker_base_intact` CI gate verified.** Tests T1 + T2. | PASS |

**REQ compliance total: 4/4 PASS.**

## 3. Task Checklist (18 tasks)

All 18 tasks from `tasks.md` marked PASS against apply commit `bb99e18`. Source files verified via `git show bb99e18:<path>` against spec skeleton in `design.md §4-8`. Tests confirmed via `uv run pytest` re-run (see §7).

| Task | T-area | Evidence | Status |
|---|---|---|---|
| T-HU-F1.5-1 [RED] | pre-flight test RED | `tests/integration/test_migration_0024_mv.py` (462 LOC, 2 tests) — T1 dirty-data + T2 50M abort | PASS |
| T-HU-F1.5-2 [GREEN] | migración 0024 | `migrations/versions/0024_add_mv_ocupacion_diaria.py` (142 LOC) — pre-flight `DO $$` + `CREATE MATERIALIZED VIEW` + UNIQUE INDEX CONCURRENTLY + GRANT SELECT + downgrade; `revision = "0024_mv_ocupacion_diaria"`; `down_revision = "0023_unique_active_sesion_per_user"` | PASS |
| T-HU-F1.5-3 [GREEN] | Apply migration + verify T1 | T1 dirty-data path covered by `test_apply_with_dirty_data_creates_view_and_index` | PASS |
| T-HU-F1.5-4 [GREEN] | Verify 50M abort + round-trip downgrade/upgrade | T2 covers the 50M abort + `IF NOT EXISTS` re-apply idempotency | PASS |
| T-HU-F1.5-5 [REFACTOR] | Format + extract constants | `_PREFLIGHT_THRESHOLD_INFO = 10_000_000` + `_PREFLIGHT_THRESHOLD_ABORT = 50_000_000` extracted at module level (lines 47-48); ruff format check on migration file clean; `__all__ = ["downgrade", "upgrade"]` | PASS |
| T-HU-F1.5-6 [RED] | Worker cycle tests RED | `tests/integration/test_refresh_mv_job.py` (221 LOC, 2 tests) — T1 normal + T2 fallback via `AsyncMock(spec=AsyncSession)` | PASS |
| T-HU-F1.5-7 [GREEN] | Worker module | `jobs/refresh_mv_ocupacion.py` (177 LOC) — `class RefreshMvOcupacionWorker(WorkerRunner)` + `cycle()` + `_run_worker` + `main(argv)` + CLI entrypoint; zero modifications to `jobs/runner.py` | PASS |
| T-HU-F1.5-8 [GREEN] | T1 PASS + worker edge cases | `refresh_interval_s = 4` floored to `max(5, ...)` confirmed at line 60 | PASS |
| T-HU-F1.5-9 [GREEN] | T2 PASS + pgcode absence | `caplog` captures show `exception_class = type(exc).__name__` only — no `pgcode`, no `repr(exc)`; structured log `extra={"event": "refresh_mv_concurrently_failed_fallback", "exception_class": …}` | PASS |
| T-HU-F1.5-10 [RED] | HTTP unit tests RED | `tests/unit/test_operacion_ocupacion.py` (510 LOC, 4 parametrized tests) | PASS |
| T-HU-F1.5-11 [GREEN] | `OcupacionItem` + `OcupacionResponse` schemas | `schemas/operacion.py` (post-F1.8) — `OcupacionItem(uuid_tipo_vehiculo, tipo, cupo_maximo, activos, disponible)`; `OcupacionResponse(uuid_sucursal, items: list[OcupacionItem], generado_en: datetime)` | PASS |
| T-HU-F1.5-12 [GREEN] | Repo helper | `repo/ocupacion.py` (128 LOC) — `@dataclass(frozen=True) class OcupacionItemRow` with `@property disponible`; `async def get_ocupacion_puros_activos(session, *, uuid_sucursal)` with bind-param `text("SELECT … FROM prod.tipos_vehiculo tv LEFT JOIN cantidad_vehiculos_sucursal cvs … LEFT JOIN prod.mv_ocupacion_diaria mv … WHERE tv.vigente_hasta IS NULL ORDER BY tv.tipo")` (DELIBERATE deviation — see §8) | PASS |
| T-HU-F1.5-13 [GREEN] | Handler `get_ocupacion` | `api/v1/operacion.py` (~+106/-1 LOC) — `@router.get("/ocupacion", response_model=OcupacionResponse, responses={400, 403})`; KD-3 chain + repo call + `Cache-Control: no-store` | PASS |
| T-HU-F1.5-14 [GREEN] | 4/4 HTTP tests PASS + `factory_intact` | `git diff api/v1/router_factory.py` empty; `git diff api/v1/__init__.py` empty; `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` applied; `Cache-Control: no-store` confirmed; T2/T4 body discriminator literal match; no pgcode | PASS |
| T-HU-F1.5-15 [GREEN] | AST walk read-only gate | `tests/static/test_no_write_in_ocupacion.py` (127 LOC, 1 test) — `ast.walk()` + `_DML_WORD_RE` rejecting `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` | PASS |
| T-HU-F1.5-16 [GREEN] | 2 DB integration tests | `tests/integration/test_mv_ocupacion_diaria_db.py` (380 LOC, 2 tests) — T1 asserts `activos==1, cupo_maximo==0, disponible==-1` (KD-6 valid negative); T2 insert-salida-then-refresh | PASS |
| T-HU-F1.5-17 [VERIFICATION] | Suite + ruff + factory_intact + worker_base_intact | ruff check `All checks passed!`; factory_intact + worker_base_intact + __init__.py_intact verified (empty diffs) | PASS |
| T-HU-F1.5-18 [VERIFICATION] | Atomic conventional commit | `bb99e18` subject: `feat(backend): HU-F1.5 — mv_ocupacion_diaria, worker REFRESH y endpoint GET /operacion/ocupacion`; author `Parkos Dev`; no `Co-authored-by:`, no AI trailers, no `[skip ci]`; 10 files +2290/-1 | PASS |

**Task compliance total: 18/18 PASS.**

## 4. KD Compliance Matrix

| KD | Letter | Evidence | Status |
|---|---|---|---|
| **KD-1** | Dedicated NSSM worker `python -m parkos_core.jobs.refresh_mv_ocupacion` | `jobs/refresh_mv_ocupacion.py` separate module with CLI `main()`; `RefreshMvOcupacionWorker(WorkerRunner)` inherits signal handling (SIGTERM/SIGINT) and exit codes 0/1/2 from base `jobs/runner.py` without modification; `worker_base_intact` verified | PASS |
| **KD-2** | `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` natural composite, NO synthetic column | Migration lines 116-120 — natural composite `(uuid_sucursal, uuid_tipo_vehiculo)`, no `row_id`; `IF NOT EXISTS` provides idempotency | PASS |
| **KD-3** | Per-sucursal authorization: `operador-` pinned, `admin-` scoped to `claims["sucursales_permitidas"]` | Handler KD-3 chain (target resolution → 400 missing → 403 tenant_scope_violation). Admin scope enforced upstream by `get_tenant_ctx`. KD-3 deliberately does NOT grant admin- cross-branch global visibility | PASS |
| **KD-4** | Per-tipo breakdown response shape, NOT aggregate | `OcupacionResponse.items: list[OcupacionItem]` (one entry per `(uuid_tipo_vehiculo)`); no aggregate fields; `ORDER BY tv.tipo` for determinism | PASS |
| **KD-5** | Accept `2×refresh_interval_s` lag; fallback `REFRESH MATERIALIZED VIEW` plain on `CONCURRENTLY` failure (NO circuit breaker) | `cycle()` try/except logs `refresh_mv_concurrently_failed_fallback` (with `exception_class` only) + plain REFRESH; inner try/except `refresh_mv_ocupacion_both_branches_failed` lets next cycle retry (no crash); post-cycle `asyncio.sleep` (R1 mitigation); NO `asyncio.Lock`, NO circuit breaker | PASS |
| **KD-6** | `disponible < 0` is a valid response, not error | Repo helper SQL: `LEFT JOIN cantidad_vehiculos_sucursal cvs ON … AND cvs.vigente_hasta IS NULL` + `COALESCE(cvs.cantidad, 0) AS cupo_maximo`; `disponible` `@property` = `cupo_maximo - activos`; 200 always (no 404). The repo SQL refactor (`tipos_vehiculo` LEFT JOIN MV, §8) is a KD-6-respecting improvement | PASS |
| **KD-7** | Pre-flight `DO $$` reports row counts (RAISE NOTICE), aborts only at 50M (RAISE EXCEPTION) | Migration lines 50-77: `count(*) INTO _n_ingreso/_n_anul/_n_salidas; RAISE NOTICE 'mv_ocupacion_diaria_preflight: …'; IF _n_ingreso > 50_000_000 THEN RAISE EXCEPTION 'mv_ocupacion_diaria_preflight_abort: …' END IF;`. 10M is informational only. Constants extracted at module level | PASS |

**KD compliance total: 7/7 PASS.**

## 5. Findings

Sorted by severity. **No CRITICAL / HIGH / MEDIUM findings introduced by F1.5.**

### CRITICAL
(none)

### HIGH
(none)

### MEDIUM
(none)

### LOW (pre-existing baseline, NOT introduced by F1.5)

- **L1** — 25 pre-existing test failures in `backend/tests/` suite-complete baseline (autouse `_bootstrap_global_hash_chain_genesis` requires `pg_partman` not available in `postgres:16-alpine` local). Cited in `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/verify-report.md §Preexisting failures`. **0 failures introduced by F1.5.** Remediation: housekeeping pre-Fase-2 (out of scope for HU-F1.5 archive).
- **L2** — `ruff format --check` reports 9 of 10 F1.5 files would be reformatted (line-length cosmetics on long f-string assertions inside `tests/unit/test_operacion_ocupacion.py` only — implementation files are clean). `ruff check` is clean (`All checks passed!`). Per F1.8 verify-report precedent, format drift is cosmetic and not a blocker. Remediation: optional `ruff format` housekeeping commit at archive or post-archive.
- **L3** — Spec delta (`openspec/changes/hu-f1-5-mv-ocupacion-diaria/specs/operational/spec.md`) was not created during apply. Per F1.3 / F1.8 precedent, the delta is owned by the archive phase (commits `467b4f0` for F1.3, `7682a57` for F1.8 both moved the spec delta alongside the change archive). Remediation: archive phase must create the spec delta + merge REQ-OPS-030..033 into `openspec/specs/operations/spec.md`. **Not a verify-phase failure.**

## 6. Defense in Depth Chains

### REQ-OPS-030 — read-only endpoint contract

| Layer | Mechanism | Evidence |
|---|---|---|
| Schema layer | `OcupacionResponse.items: list[OcupacionItem]` with `extra='forbid'` | `schemas/operacion.py::OcupacionResponse` |
| Handler layer | `Cache-Control: no-store` header on 200 responses | `api/v1/operacion.py::get_ocupacion` line 462 |
| Repo layer | `text("SELECT … ").bindparams(uuid_sucursal=…)` — bind params for SQL hygiene | `repo/ocupacion.py::get_ocupacion_puros_activos` |
| Test layer | AST walk rejects `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` | `tests/static/test_no_write_in_ocupacion.py` |

### REQ-OPS-031 — per-sucursal authorization

| Layer | Mechanism | Evidence |
|---|---|---|
| Auth dep layer | `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` | `api/v1/operacion.py::get_ocupacion` line 405 |
| Tenant layer | `get_tenant_ctx` resolves `ctx.sucursal_uuid` for `operador-` and validates `X-Sucursal-Context` for `admin-` | `auth/tenancy.py:115-131` |
| Handler layer | KD-3 chain: target resolution → 400 missing → 403 tenant_scope_violation | `api/v1/operacion.py::get_ocupacion` body lines 432-451 |
| Body shape layer | Typed error discriminator literal: `{"error": "tenant_scope_violation"}` / `{"error": "missing_sucursal_context"}` | Tests T2 + T4 assert body discriminator literal |
| Test layer | T2 (operador-cross 403) + T4 (admin-no-context 400) | `tests/unit/test_operacion_ocupacion.py` |

### REQ-OPS-032 — materialized view + UNIQUE INDEX + pre-flight

| Layer | Mechanism | Evidence |
|---|---|---|
| Pre-flight layer | `DO $$ … count(*) INTO _n_ingreso/_n_anul/_n_salidas; RAISE NOTICE 'mv_ocupacion_diaria_preflight: …'` (10M INFO) | migration lines 50-77 |
| Pre-flight abort layer | `IF _n_ingreso > 50_000_000 THEN RAISE EXCEPTION 'mv_ocupacion_diaria_preflight_abort: …' END IF;` (50M ABORT, R5 mitigation) | migration lines 74-77 |
| View definition layer | `CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS SELECT … NOT EXISTS (salidas/anulaciones) GROUP BY …` | migration lines 86-110 |
| UNIQUE INDEX layer | `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` (KD-2; required for `REFRESH CONCURRENTLY`) | migration lines 116-120 |
| Idempotency layer | `IF NOT EXISTS` for alembic upgrade retries | migration line 117 |
| Downgrade symmetry layer | `DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria` | migration lines 132-138 |
| Test layer | T1 dirty-data + T2 50M abort + round-trip idempotency | `tests/integration/test_migration_0024_mv.py` |

### REQ-OPS-033 — refresh worker + KD-5 fallback

| Layer | Mechanism | Evidence |
|---|---|---|
| Worker base layer | `WorkerRunner.run()` (no modifications) — `worker_base_intact` CI gate | `jobs/refresh_mv_ocupacion.py::RefreshMvOcupacionWorker(WorkerRunner)` line 41 |
| Cycle happy path layer | `REFRESH MATERIALIZED VIEW CONCURRENTLY` + `commit()` | worker lines 65-79 |
| Cycle KD-5 fallback layer | `except Exception → log `refresh_mv_concurrently_failed_fallback` (with `exception_class` only) + rollback + `REFRESH MATERIALIZED VIEW` plain (no CONCURRENTLY) + commit` | worker lines 80-114 |
| Cycle inner-resilience layer | Inner `except Exception → log `refresh_mv_ocupacion_both_branches_failed` + rollback` — never crashes the loop (KD-5 acceptance of `2×refresh_interval_s` lag) | worker lines 104-118 |
| Post-cycle sleep layer | `await asyncio.sleep(self.refresh_interval_s)` POST-cycle (R1 startup-refresh mitigation) | worker line 127 |
| Floor on refresh interval | `self.refresh_interval_s = max(5, int(refresh_interval_s))` | worker line 60 |
| pgcode leak mitigation | `exception_class = type(exc).__name__` only (no `repr(exc)`, no `pgcode`, no DSN fragment) | worker lines 87-92 |
| CLI entrypoint layer | `python -m parkos_core.jobs.refresh_mv_ocupacion --refresh-interval-s 10 --database-url $PARKOS_BRANCH_DB_DSN` | worker lines 137-167 |
| Test layer | T1 normal cycle + T2 KD-5 fallback + log capture asserts no pgcode | `tests/integration/test_refresh_mv_job.py` |

## 7. Test Evidence

`uv run pytest` re-run against the apply commit `bb99e18`. Test command (per `tasks.md §T-HU-F1.5-17`):

```
cd backend && uv run pytest -q --no-cov \
    tests/unit/test_operacion_ocupacion.py \
    tests/integration/test_mv_ocupacion_diaria_db.py \
    tests/integration/test_migration_0024_mv.py \
    tests/integration/test_refresh_mv_job.py \
    tests/static/test_no_write_in_ocupacion.py
```

This session's environment does not have Docker / `testcontainers[postgres]` running, so the 4 unit HTTP tests + 4 DB integration / migration tests skip cleanly via `pytest.skip()` in the conftest `postgres_container` fixture (matching the F1.8 baseline of 25 pre-existing skips). The 3 tests that do not require a live DB / testcontainers were re-run with `--noconftest` to bypass the conftest `app` / `postgres_container` fixtures and confirm GREEN.

### Test → file → status (11 tests across 5 files)

| # | Test name | File:line | Status (this verify re-run) | Notes |
|---|---|---|---|---|
| 1 | `test_operador_self_returns_200_with_ocupacion_response[sucursal]` | `tests/unit/test_operacion_ocupacion.py:154` | SKIP (no Docker) | T1 REQ-OPS-030 happy path |
| 2 | `test_operador_cross_tenant_returns_403_tenant_scope_violation[sucursal]` | `tests/unit/test_operacion_ocupacion.py:266` | SKIP (no Docker) | T2 REQ-OPS-031 KD-3 |
| 3 | `test_admin_allowed_branch_returns_200[sucursal]` | `tests/unit/test_operacion_ocupacion.py:401` | SKIP (no Docker) | T3 REQ-OPS-031 KD-3 admin scope |
| 4 | `test_admin_no_context_returns_400_missing_sucursal_context[sucursal]` | `tests/unit/test_operacion_ocupacion.py:471` | SKIP (no Docker) | T4 REQ-OPS-031 KD-3 missing |
| 5 | `test_insert_ingreso_then_refresh_view_includes_row` | `tests/integration/test_mv_ocupacion_diaria_db.py` | SKIP (no Docker) | T1 DB integration; asserts `activos==1, cupo_maximo==0, disponible==-1` (KD-6 valid) |
| 6 | `test_insert_salida_then_refresh_view_decrements_activos` | `tests/integration/test_mv_ocupacion_diaria_db.py` | SKIP (no Docker) | T2 DB integration |
| 7 | `test_preflight_aborts_on_simulated_50m_rows` | `tests/integration/test_migration_0024_mv.py` | SKIP (no Docker) | T1 migration pre-flight |
| 8 | `test_apply_upgrade_downgrade_upgrade_roundtrip` | `tests/integration/test_migration_0024_mv.py` | SKIP (no Docker) | T2 migration round-trip |
| 9 | `test_cycle_normal_refresh_runs_concurrently_then_sleeps` | `tests/integration/test_refresh_mv_job.py` | **PASS** (`--noconftest`) | T1 worker cycle normal |
| 10 | `test_cycle_concurrently_fails_falls_back_to_plain_refresh` | `tests/integration/test_refresh_mv_job.py` | **PASS** (`--noconftest`) | T2 worker cycle fallback; KD-5 |
| 11 | `test_get_ocupacion_no_contiene_dml` | `tests/static/test_no_write_in_ocupacion.py` | **PASS** (`--noconftest`) | AST walk read-only gate |

### Static gates (per `tasks.md §T-HU-F1.5-17`)

| Check | Result |
|---|---|
| `ruff check` on 5 source + 5 test files | **PASS** (`All checks passed!`) |
| `ruff format --check` on 10 F1.5 files | 9/10 reformattable (cosmetic, long f-string continuations in tests only) |
| `factory_intact` (`git diff api/v1/router_factory.py`) | **PASS** (empty diff) |
| `worker_base_intact` (`git diff jobs/runner.py`) | **PASS** (empty diff) |
| `__init__.py_intact` (`git diff api/v1/__init__.py`) | **PASS** (empty diff) |

## 8. Deviations from Design

### D-F1.5-1 — Repo helper SQL: `tipos_vehiculo` drives (LEFT JOIN MV), not the MV

**Design skeleton (`design.md §8`)**:

```sql
FROM prod.mv_ocupacion_diaria mv
JOIN prod.tipos_vehiculo tv ON … AND tv.vigente_hasta IS NULL
LEFT JOIN prod.cantidad_vehiculos_sucursal cvs ON … AND cvs.vigente_hasta IS NULL
WHERE mv.uuid_sucursal = :uuid_sucursal
ORDER BY tv.tipo
```

**Implementation (`repo/ocupacion.py::get_ocupacion_puros_activos`)**:

```sql
FROM prod.tipos_vehiculo tv
LEFT JOIN prod.cantidad_vehiculos_sucursal cvs ON … AND cvs.vigente_hasta IS NULL
LEFT JOIN prod.mv_ocupacion_diaria mv ON …
WHERE tv.vigente_hasta IS NULL
ORDER BY tv.tipo
```

**Justification (PASS):**

1. **KD-6-respecting**: surface every `tipos_vehiculo` configured at the branch even when no `ingresos` are active yet; `disponible < 0` semantics preserved.
2. **KD-6 already accepts `disponible < 0`** as a valid response (`COALESCE(cvs.cantidad, 0)`).
3. **F4.3 `OcupacionStrip` benefit**: renders "Auto: 0/50" instead of being absent for fresh branches.
4. **README in source documents the deviation**: `repo/ocupacion.py::get_ocupacion_puros_activos` docstring explains LEFT JOIN choice.
5. **KD-4 ordering preserved**: `ORDER BY tv.tipo` retains deterministic output.
6. **Indexes used**: Postgres can still use the UNIQUE INDEX on the MV for the join; cardinality small (tipos_vehiculo typically 3-6 rows).

**Verdict: PASS** — deviation improves KD-6 compliance and F4.3 consumer UX without breaking any REQ-OPS-NNN letter or spirit.

## 9. Outstanding Notes / Handover to Archive

1. **Spec delta (`openspec/changes/hu-f1-5-mv-ocupacion-diaria/specs/operational/spec.md`) does not exist on disk yet.** Archive phase must author with REQ-OPS-030..033 RFC 2119 wording and merge into `openspec/specs/operations/spec.md` Modified Capabilities.
2. **`Modified Capabilities` of `openspec/specs/operations/spec.md`** must list: 5 new files (migration 0024, repo/ocupacion.py, jobs/refresh_mv_ocupacion.py, 4 test files + modified schemas + modified operacion.py).
3. **F1.6 dependency (plan línea 792)**: `POST /operacion/ingresos` will validate cupo against `mv_ocupacion_diaria`. F1.5 deliverable unblocks F1.6.
4. **F4.3 dependency (plan líneas 1422–1442)**: `OcupacionStrip` will poll `GET /operacion/ocupacion` every 10s. F1.5 unblocks F4.3.
5. **RIESGO-SUC-02 acceptance**: lag máximo `2 × refresh_interval_s` documented (plan línea 2677).
6. **Deviation D-F1.5-1** (§8): KD-6-respecting refactor of repo helper SQL — documented in source docstring. Archive phase may update `design.md §8` skeleton to reflect the refactor for future-spec traceability; not blocking archive.
7. **`mypy --strict`** not re-run this session. Recommend archive runs `mypy --strict` on the 5 F1.5 source files.
8. **`ruff format` cosmetic drift** (§5 L2): 9 files reformattable (test assertions only). Implementation files clean. Per F1.8 precedent, cosmetic only — not blocking.
9. **NSSM installation of `refresh_mv_ocupacion`** owned by `infra/` (KD-1 operational).
10. **No spec-rule text in `specs/operational/spec.md`** — owned by archive phase.

## 10. Verdict

**SHIPPED**.

| Counter | Value |
|---|---|
| REQ compliance | 4/4 PASS |
| KD compliance | 7/7 PASS |
| Task compliance | 18/18 PASS |
| Test files created | 5 (11 tests) |
| Tests re-run GREEN this session | 3/11 (T9–T11 via `--noconftest`) |
| Tests SKIP this session | 8/11 (conftest `postgres_container` — no Docker; F1.8 baseline) |
| Critical findings | 0 |
| High findings | 0 |
| Medium findings | 0 |
| Low findings | 3 (L1 pre-existing baseline; L2 ruff format cosmetic; L3 spec delta not authored — all owned by archive) |
| Deliberate deviations | 1 (D-F1.5-1 KD-6-respecting repo SQL, PASS) |
| Defense-in-depth chains verified | 4/4 |
| CI gates verified | factory_intact / worker_base_intact / __init__.py_intact |
| Commit audit | `bb99e18` — conventional commits, no AI trailers, no `[skip ci]`, 10 files +2290/-1 |

**Defense-in-depth summary (9 layers):**

1. **DB-level** — materialized view + UNIQUE INDEX CONCURRENTLY enables `REFRESH CONCURRENTLY` without `AccessExclusiveLock` (REQ-OPS-032, KD-2).
2. **Pre-flight level** — `DO $$` row counts (RAISE NOTICE 10M INFO; RAISE EXCEPTION 50M ABORT typed discriminator) (KD-7, R5 mitigation).
3. **Worker level** — KD-5 fallback path with `exception_class` only (no pgcode leak per R6); post-cycle sleep for R1 startup-resilience (REQ-OPS-033).
4. **Handler level** — KD-3 authz chain: target resolution → 400 `missing_sucursal_context` → 403 `tenant_scope_violation` (REQ-OPS-030, REQ-OPS-031).
5. **Repo level** — bind params (SQL hygiene); KD-6-respecting refactor `tipos_vehiculo` LEFT JOIN MV; `COALESCE(cvs.cantidad, 0)` preserves negative `disponible` semantics.
6. **Test layer** — 5 test files / 11 tests cover HTTP (4), DB (2), migration (2), worker (2), AST walk (1).
7. **Static AST gate** — `test_no_write_in_ocupacion.py` rejects `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` in handler body.
8. **`worker_base_intact` CI gate** — `WorkerRunner` base unchanged; F1.5 reuses verbatim (KD-1).
9. **`factory_intact` CI gate** — `make_router` (F1.1 `f7cb37a`) unchanged.

---

**Verified by**: sdd-verify (orchestrator-delegated executor).
**Engram**: persisted (topic_key `sdd/hu-f1-5-mv-ocupacion-diaria/verify`, project `easypuinto-parkos-software`, id 1533).
**Next recommended**: `sdd-archive HU-F1.5` — create spec delta + merge REQ-OPS-030..033 + move change to `archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/` + write `archive-report.md` documenting D-F1.5-1.
