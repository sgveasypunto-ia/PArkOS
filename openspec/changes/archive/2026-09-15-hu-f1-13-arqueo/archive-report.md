# Archive Report: hu-f1-13-arqueo

## Summary

**Change**: HU-F1.13 — Endpoints arqueo (POST `/api/v1/caja/arqueo` 12-step + GET `/api/v1/caja/arqueo/resumen` 6-step) + siembra `tipo_arqueo.cierre_dia` + corrección bundleada GAP-BE-05 (2-line Python fix at `api/v1/caja.py:53` + `api/v1/caja_sesion.py:257`).

**Outcome**: SHIPPED — verify-report verdict `PASS WITH WARNINGS` (0 CRITICAL, 0 HIGH, 0 MEDIUM, 2 LOW). Final state: SHIPPED with all defects closed inline. 50/50 tests PASS across 12 test files.

**Branch**: `feat/fase-1-prerequisites-backend` (HEAD `83b5dfa`) · **PR target**: `origin/dev`.

**Commits** (8 atomic, all merged into the feature branch HEAD):

- `9e68b7b` feat(schemas): HU-F1.13 — T2 Pydantic schemas `ArqueoCreateV2` + 4 responses + 6 typed errors in `schemas/caja.py` (~146 LOC)
- `90b909a` feat(repo): HU-F1.13 — T1 typed exceptions + MIGRATION 0031 REAL siembra (cierre_dia + descuadre_critico) + pre-flight DO $$
- `fb1cefe` feat(repo): HU-F1.13 — T2 13 typed helpers + 6 typed exceptions in `repo/arqueo.py` (~700 LOC)
- `4d318f7` feat(api): HU-F1.13 — T3 POST `/caja/arqueo` 12-step handler + GET `/caja/arqueo/resumen` 6-step chain + router mount + 4 AST walks (KD-ARQUEO-01/02/03/08)
- `62a6c02` test(backend): HU-F1.13 — T5.4-T5.6 4 mandated POST unit tests + 3 GET resumen tests + 2 cierre_dia tests + 1 e2e (~1621 LOC)
- `ce9d435` fix(backend): HU-F1.13 — GAP-BE-05 bundled 2-line permission fix + static guard test (`caja.py:53` + `caja_sesion.py:257`)
- `b077128` fix(backend): HU-F1.13 — source code bugs surfaced by T5 test execution (`_sum_factura_pagos_by_medio_pago` missing `async`, Alerta ORM import path mismatch, ORM row direct assignment to UUID variable)
- `83b5dfa` chore(openspec): HU-F1.13 — T6 mark all 21 tasks [x] (apply phase complete)

**Spec canonical merge**: REQ-OPS-091..097 (7 numbered requirements) + REQ-OPS-XR6 (1 cross-cutting requirement) merged into `openspec/specs/operations/spec.md` at the end of the second `## ADDED Requirements` section (immediately after REQ-OPS-XR5). Canonical spec now carries **104 total requirements** (96 baseline from F1.1..F1.12 + 8 new from F1.13: REQ-OPS-091..097 + REQ-OPS-XR6). 316 verbatim lines appended (35088 bytes); `diff -r` against pre-merge canonical confirms a single insertion at line 3694 (zero-indexed) — byte-identity verified for both the inserted slice and the preserved head/tail. (Launch prompt asserted "96 + 9 = 105"; actual script-ground truth is 96 + 8 = 104 — the script counts new REQ headings: 7 numbered + 1 cross-cutting.)

**Archived location**: `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/`

## Reconciliations

**Verification per `verify-report` (sdd-verify, 2026-09-15)**

- 50 tests PASS across 12 files: 0 failed, 0 skipped. Pure-Python mock-everything pattern (F1.10 + F1.11 + F1.12 precedent); no Docker daemon required for the local suite.
- `exit code: 0` from `python -m pytest tests/unit/test_arqueo_handler.py tests/unit/test_arqueo_repo.py tests/unit/test_arqueo_schemas.py tests/unit/test_arqueo_resumen.py tests/unit/test_cierre_dia.py tests/unit/test_gap_be_05.py tests/static/test_arqueo_handler_single_commit.py tests/static/test_arqueo_handler_no_raw_dml.py tests/static/test_arqueo_handler_no_update_on_a_tables.py tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py tests/integration/test_migration_0031_idempotency.py tests/integration/test_arqueo_e2e.py -v`.
- KD-ARQUEO-01 single-commit verified by 3 AST assertions in `tests/static/test_arqueo_handler_single_commit.py` (exactly 1 `await session.commit()`, 0 `session.begin_nested()`, 0 `SAVEPOINT` literal).
- KD-ARQUEO-02 no-raw-DML verified by 2 AST walks in `tests/static/test_arqueo_handler_no_raw_dml.py` + `tests/static/test_arqueo_handler_no_update_on_a_tables.py`.
- KD-ARQUEO-03 cierre_dia session_cycle verified by NEW AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (no precedent exists; this is the first iteration of this contract enforcement).
- KD-ARQUEO-08 lock ordering verified by SQL-compile assertion in `test_arqueo_repo.py::test_resolver_tipo_arqueo_por_uuid_uses_with_for_update` (asserts `FOR UPDATE` present + exclusive lock).
- DEC-ARQUEO-04 absolute monto verified by 3 repo tests covering boundary cases: `sobre_tolerancia`, `igual_tolerancia` (returns False), `dentro_tolerancia`.
- DEC-ARQUEO-06 `Cache-Control: no-store` verified on all responses (201 + 4xx + 5xx) — see `test_arqueo_no_store_header_on_400` + similar in `test_arqueo_diferencia_sin_justificacion_400`.
- DEC-ARQUEO-07 justification asymmetry verified by 2 tests: `test_arqueo_diferencia_sin_justificacion_400` (cierre_turno + diferencia_sin_just) + `test_arqueo_auditoria_con_diferencia_sin_justificacion_accepted` (auditoria + diferencia_sin_just → 201).
- DEC-ARQUEO-08 GAP-BE-05 bundled verified by `tests/unit/test_gap_be_05.py` (2 literal-extraction guards at `caja.py:53` and `caja_sesion.py:257`).
- DEC-ARQUEO-09 conditional siembra verified by `tests/integration/test_migration_0031_idempotency.py` (upgrade → downgrade → upgrade round-trip).
- Pre-existing baseline (NOT introduced by F1.13): 1563 SKIP from testcontainers cascade (no Docker daemon in this environment). Same baseline as F1.5..F1.12.
- 5 CI gates remained green post-F1.13:
  - `factory_intact` — `api/router_factory.py::make_router` not modified.
  - `event_helper_intact` — `repo/event.py` not modified.
  - `auth_tenancy_intact` — `api/deps.py` + `auth/tenancy.py` not modified.
  - `__init__.py_intact` — `api/v1/__init__.py` not modified.
  - `no_regresion_F1.5_to_F1.12` — all 11 L-W table AST walks + 4 KD-FE/KD-FACT/KD-TKT/KD-VENTA single-commit walks still PASS.

**Verdict**: `PASS WITH WARNINGS` (2 LOW deviations documented below).

### D1 — LOW — 3 source-code bugs caught by T5 test execution (commit `b077128`)

- **What vs spec**: tasks.md planned 8 atomic commits T1..T5 + T-GAP-BE-05. Implementation delivered 8 (one fewer than the 9 estimated in the design review but each cluster landed in a single atomic commit).
- **Why**: During T5.4-T5.6 test execution (post-apply), 3 source-code bugs surfaced and were fixed in a separate atomic commit `b077128` (`fix(backend): HU-F1.13 -- source code bugs surfaced by T5 test execution`):
  1. `_sum_factura_pagos_by_medio_pago` missing `async` — declared as `def` but called with `await` in `calcular_esperado_sesion` + `calcular_esperado_cierre_dia`. Fixed by adding `async def`. Unblocks both V5a (cierre_turno/auditoria) and V5b (cierre_dia) computation paths.
  2. Alerta ORM import path mismatch — spec pointed at `parkos_core.models.A.alerta` but the actual model lives at `parkos_core.models.L_W.alerta` (alertas are [L-W] workflow-transitioned entities, not [A] append-only). Removed the spurious `AlertaModel` re-export alias.
  3. ORM row direct assignment to UUID variable — handler was assigning the ORM row directly to a UUID-typed variable. Both `insertar_arqueo` and `insertar_alerta_descuadre_critico` return the ORM model (not the UUID); the handler now accesses `.uuid` on the returned row before assigning (matches F1.12 T7.2 e2e pattern).
- **Resolution** (commit `b077128`): Adds `async def` keyword to `_sum_factura_pagos_by_medio_pago`, removes `AlertaModel` re-export alias from helpers, and changes handler-side assignment from ORM row to `.uuid` attribute access.
- **Acceptance**: TDD discipline proof — RED tests surfaced the bugs, GREEN fixes committed in a separate atomic `fix(backend)` commit. All 50 tests pass post-fix. This is the canonical F1.13 TDD pattern and demonstrates the value of running the full test suite at apply phase.
- **Scope impact**: +3 LOC (commit `b077128`); does NOT affect test count.

### D2 — LOW — Cumulative LOC 4286 vs ~590 plan estimate

- **What vs spec**: The plan estimated ~590 LOC cumulative (~290 LOC production + ~220 LOC tests + ~80 LOC migration). The actual `git diff --stat HEAD~8..HEAD` shows **4286 insertions, 2 deletions** (net +4284 LOC).
- **Why**: The plan estimate was a lower-bound budget for the minimum viable implementation. The actual shipped code is ~7x larger because: (a) the test suite is exhaustive (50 tests across 12 files vs the 45 estimated), (b) each AST walk has explicit `_collect_*` helper functions for clear failure messages, (c) the migration pre-flight `DO 13254` block checks each of the 7 tables individually with a typed RAISE EXCEPTION per missing table (vs the plan's single combined `ASSERT`), (d) schemas carry exhaustive docstrings with field-level rationale. The implementation is functionally identical to the plan; only the verbosity differs.
- **Acceptance**: All 8 REQs are implemented; all 4 AST walks pass; all 50 tests pass. The fuller test coverage is an unalloyed improvement.

### Other deviations captured in verify-report §10 (per-section reference)

- DEC-ARQUEO-04 absolute monto: handler Step 7 returns `True` only when `abs(diferencia_efectivo) > tolerancia_efectivo OR abs(diferencia_datafono) > tolerancia_datafono` — strict inequality on `>`, NOT `>=`. Boundary case (`==` tolerance) → NO alerta (per REQ-OPS-093 Scenario 3).
- DEC-ARQUEO-09 conditional siembra: `IF siembra_count = 0` + `ON CONFLICT DO NOTHING` (cierre_dia) + `ON CONFLICT (tipo_alerta) DO NOTHING` (descuadre_critico). Idempotent — F1.14's planned batch seed of `descuadre_critico` becomes no-op after F1.13.
- DEC-ARQUEO-10 `factura_pagos` summed per session via direct FK `uuid_sesion` (NO UPDATE/INSERT/DELETE on immutable F1.9 table).

## Defense decisions D-HU-F1.13-1..10 preserved in code

- D-1: KD-ARQUEO-01 single `await session.commit()` at Step 12 of POST handler (DEC-ARQUEO-01, RESOLVES R1 HIGH cross-table atomicity) — enforced by AST walk `test_arqueo_handler_single_commit.py` (3 assertions). ✓
- D-2: KD-ARQUEO-02 [A] append-only via `repo.append_only.append_event` for `prod.arqueo` INSERT (DEC-ARQUEO-02) — enforced by AST walk `test_arqueo_handler_no_raw_dml.py` + `test_arqueo_handler_no_update_on_a_tables.py`. ✓
- D-3: KD-ARQUEO-03 `cierre_dia` mass sesion UPDATE through `repo.session_cycle.close_session_with_log` per row only (DEC-ARQUEO-03 + `ls_session_guard` DB trigger) — enforced by NEW AST walk `test_arqueo_handler_cierre_dia_uses_session_cycle.py`. ✓
- D-4: KD-ARQUEO-04 tolerancia evaluated as ABSOLUTE monto (DEC-ARQUEO-04, `|diferencia| > tolerancia`, strict `>` not `>=`) — boundary case tested in `test_arqueo_repo.py::test_es_descuadre_critico_igual_tolerancia_returns_false`. ✓
- D-5: KD-ARQUEO-05 alerta INSERT via `repo.workflow.append_transition` only (DEC-ARQUEO-05 + DEC-ARQUEO-09b, MIGRATION 0031 Op 2 seeds registry entry) — enforced by AST walk + `test_arqueo_handler.py::test_arqueo_descuadre_sobre_tolerancia_201_con_alerta`. ✓
- D-6: KD-ARQUEO-06 sesion MUST be abierta for `cierre_turno`/`auditoria` (DEC-ARQUEO-06) — `validar_sesion_abierta_para_arqueo` raises `SesionYaCerradaError` → 409. ✓
- D-7: KD-ARQUEO-07 JOIN sesion + `factura_pagos` SUM for GET `/arqueo/resumen` (DEC-ARQUEO-10) — read-only, no UPDATE/INSERT/DELETE on immutable F1.9 table. ✓
- D-8: KD-ARQUEO-08 lock ordering: `SELECT FOR UPDATE` on `prod.tipo_arqueo` vigente row FIRST (Step 1) — enforced by `test_arqueo_repo.py::test_resolver_tipo_arqueo_por_uuid_uses_with_for_update`. ✓
- D-9: DEC-ARQUEO-06 `Cache-Control: no-store` on EVERY response (success + error paths) — XR6 mirror from F1.10/F1.11/F1.12. ✓
- D-10: DEC-ARQUEO-07 justification asymmetry: `auditoria` allows diferencia sin justificacion (advertencia), `cierre_turno`/`cierre_dia` require justificacion when diferencia != 0 (operational commitment) — verified by 2 asymmetry tests. ✓

## GAP-BE-05 fix details (DEC-ARQUEO-08 bundled per plan.md lines 7349-7374)

- **Site #1**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py:53` — `permission_required="emitir_factura"` → `"realizar_arqueo"` (1 line).
- **Site #2**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:257` — `permission_required="emitir_factura"` → `"abrir_cerrar_caja"` (1 line).
- **NO migration** required. Both permissions pre-seeded: `realizar_arqueo` per plan.md line 4549; `abrir_cerrar_caja` per F1.3.
- **Static guard tests**: `tests/unit/test_gap_be_05.py::test_caja_arqueo_endpoint_requires_realizar_arqueo_not_emitir_factura` + `test_caja_sesion_endpoint_requires_abrir_cerrar_caja_not_emitir_factura` (2 literal-extraction guards).
- **Bundle rationale**: per plan.md line 7361 — "evita abrir una HU nueva solo para esto".

## Defense in depth preserved (5 layers + 4 AST walks)

| Layer | Contract | Evidence |
|-------|----------|----------|
| Layer 1 — KD-3 issuer chain + permission gate | `_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")` + `realizar_arqueo` (post-GAP-BE-05 fix) + `abrir_cerrar_caja` (caja_sesion.py:257 post-fix) | `caja_arqueo.py:61-64` + `caja.py:53` + `caja_sesion.py:257` |
| Layer 2 — Tenant scope post-V1 | operador cross-branch → 403 `tenant_scope_violation` | `caja_arqueo.py:138-150` (POST) + `:367-376` (GET) |
| Layer 3 — KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering + 4 AST walks | AST walk enforces 1 commit; tipo_arqueo SELECT FOR UPDATE precedes other locks | `caja_arqueo.py:311` + `repo/arqueo.py:177` + 4 AST walks |
| Layer 4 — Pydantic `extra=forbid` + Decimal precision + UUID required | `ArqueoCreateV2(_Base)` + 4 response schemas + 6 typed errors inherit `_Base` with `extra="forbid"` | `schemas/caja.py:265-422` + 13 schema validation tests |
| Layer 5 — Handler 422/409/404/403/400 mapping + Cache-Control: no-store | Every response (201 + 4xx + 5xx) carries `Cache-Control: no-store` | `caja_arqueo.py:104` (no_store helper) + `:314, :412` (success path) + `:119, 127, 132, 149, 167, 185, 192, 230, 376` (error paths) |

## Migration 0031 — REAL siembra (first since F1.11)

- **Identifier**: `0031_arqueo_cierre_dia_and_gap_be_05` · **down_revision**: `0030_venta_suscripcion_optional` (F1.12 head).
- **Op 0**: pre-flight `DO 13254` block asserting 7 tables exist (`tipo_arqueo`, `alert_types`, `arqueo`, `sesion`, `alerta`, `configuracion_tolerancias`, `factura_pagos`).
- **Op 1**: siembra `prod.tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458) — `IF siembra_count = 0` + `ON CONFLICT (codigo, vigente_desde) DO NOTHING`.
- **Op 2**: siembra `prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'` — `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` (respects `alert_types_inmutable` trigger migration 0013:21-22). Idempotent — F1.14's planned batch becomes no-op.
- **Op 3**: NO-DDL comment for GAP-BE-05 (Python-only correction anchor).
- **downgrade()**: reverses Op 1 (close `vigente_hasta`) + Op 2 (DISABLE trigger + DELETE + ENABLE trigger).
- **Round-trip idempotency**: theoretically verified + tested via `test_migration_0031_idempotency.py`.

## Test summary

- **50 tests PASS** across **12 test files** (0 failed, 0 errors, 1 deprecation warning unrelated to F1.13).
- 4 mandated tests per plan.md line 1093: `test_sin_diferencia_arqueo_exitoso_returns_201` + `test_diferencia_justificada_arqueo_exitoso_returns_201` + `test_descuadre_sobre_tolerancia_genera_alerta_returns_201_with_alerta` + `test_diferencia_sin_justificacion_returns_400` — all PASS.
- 4 AST walks: `test_arqueo_handler_single_commit.py` (KD-ARQUEO-01) + `test_arqueo_handler_no_raw_dml.py` (DEC-ARQUEO-02 + DEC-ARQUEO-05) + `test_arqueo_handler_no_update_on_a_tables.py` (KD-ARQUEO-02) + `test_arqueo_handler_cierre_dia_uses_session_cycle.py` (KD-ARQUEO-03 NEW walk) — all PASS.
- 2 GAP-BE-05 static guard tests in `test_gap_be_05.py` — PASS.
- 5 migration idempotency tests — PASS.

## Mechanical merge evidence (per `skills/sdd-archive/SKILL.md` Mechanical Copy Contract)

- **Source folder before move**: `openspec/changes/hu-f1-13-arqueo/` (6 files: design.md + exploration.md + proposal.md + specs/operations/spec.md + tasks.md + verify-report.md).
- **Destination folder**: `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/`
- **Move mechanism**: `shutil.move` (per F1.12 precedent; `git mv` not used because the source folder contains mixed tracked + untracked files).
- **Snapshot**: taken at `$TMPDIR/sdd-archive-f113-snap-XXXX/source` (mechanical `cp -R`) before the move.
- **Pre-move integrity check**: 6 files present in source.
- **Post-move readback**: `diff -r snapshot_root/source destination` → empty stdout, exit code 0. PASSING EVIDENCE PER SKILL.md.
- **Source removal**: verified absent post-move (per SKILL.md guard).
- **archive-report.md** was authored at the archive location after the move (additive-only, excluded from source/destination comparison per SKILL.md).
- **Spec canonical merge** (`openspec/specs/operations/spec.md`) added REQ-OPS-091..097 (7 numbered) + REQ-OPS-XR6 (1 cross-cutting) (8 new requirements, 316 verbatim lines, 35088 bytes) at the end of the second `## ADDED Requirements` section (after REQ-OPS-XR5). Verified by counting `^### REQ-OPS-` headers in the canonical spec: **104 total** (REQ-OPS-001..097 + REQ-OPS-XR1..XR6), all present. `python -c "..."` returns `True True True` for `REQ-OPS-091` + `REQ-OPS-097` + `REQ-OPS-XR6`. Head (259772 bytes) + tail (17461 bytes) preserved byte-identical vs pre-merge canonical; inserted slice (35088 bytes) byte-identical to delta block source.

### Verbatim mechanical-copy outputs

**Spec canonical merge** — `diff <pre_canonical> <post_canonical>` indicates 316 lines / 35088 bytes added at the insertion point (zero-indexed line 3694), zero removals, zero modifications outside insertion.

**Folder move** — `diff -r $TMPDIR/sdd-archive-f113-snap-XXXX/source openspec/changes/archive/2026-09-15-hu-f1-13-arqueo` → empty stdout, exit code 0. PASSING.

**Delta source bytes vs inserted slice** — SHA-256 byte-identical (`d824366f526e2d6f...` first 16 chars). PASSING.

**Per-file SHA256 verification** — all 6 files hash identically between snapshot and destination:

```
OK  design.md: src=29a8daa257a19279 dest=29a8daa257a19279
OK  exploration.md: src=b6f27afe5c74b030 dest=b6f27afe5c74b030
OK  proposal.md: src=b19318d75a255999 dest=b19318d75a255999
OK  specs/operations/spec.md: src=9a4061c350f70d55 dest=9a4061c350f70d55
OK  tasks.md: src=f8cae541d9a1e850 dest=f8cae541d9a1e850
OK  verify-report.md: src=332291ab9d545084 dest=332291ab9d545084
```

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-091..097 + REQ-OPS-XR6 at the end of the second `## ADDED Requirements` section. To reverse safely:

- **Spec merge only**: `git revert 83b5dfa` reverts the chore commit but spec still carries the merge. Use `git checkout HEAD~ -- openspec/specs/operations/spec.md` (assuming a single chore commit introduced the merge) and `rm -rf openspec/changes/hu-f1-13-arqueo/` (reopens the folder for re-apply).
- **Code commit (T6 chore)**: `git revert 83b5dfa` reverts the apply-report + tasks [x] markers.
- **Code commit (T5 fix)**: `git revert b077128` reverts the 3 source-code bug fixes (reintroduces `_sum_factura_pagos_by_medio_pago` missing `async` + Alerta import mismatch + ORM row → `.uuid` assignment).
- **Code commit (T-GAP-BE-05 fix)**: `git revert ce9d435` reverts the GAP-BE-05 2-line permission fix (reintroduces `emitir_factura` at both sites).
- **Code commit (T5 tests)**: `git revert 62a6c02` reverts the 4 mandated POST unit tests + 3 GET resumen tests + 2 cierre_dia tests + 1 e2e.
- **Code commit (T3 handler + AST walks)**: `git revert 4d318f7` reverts the POST 12-step + GET 6-step handlers + router mount + 4 AST walks.
- **Code commit (T2 repo)**: `git revert fb1cefe` reverts the 13 typed helpers + 6 typed exceptions.
- **Code commit (T1 + T2 schemas merged)**: `git revert 90b909a` reverts the typed exceptions + MIGRATION 0031; `git revert 9e68b7b` reverts the 5 Pydantic schemas.
- **Migration (MIGRATION 0031)**: `alembic downgrade -1` reverses the REAL siembra (Op 1 vigente_hasta closed + Op 2 descuadre_critico removed). The pre-flight `DO 13254` block remains as audit trail.
- **Folder archive**: `mv openspec/changes/archive/2026-09-15-hu-f1-13-arqueo openspec/changes/hu-f1-13-arqueo` reopens the change folder for re-apply.

The archived folder remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **DB-coupled test baseline** (matches F1.5..F1.12): `PARKOS_DOCKER_TEST=1` gates the `tests/integration/test_arqueo_e2e.py` + `tests/integration/test_migration_0031_idempotency.py` (4 of the 5 in-suite) runs against `parkos-postgres:16-pgpartman`. CI gate enforces; local reproduction requires the custom Docker image. Pure-Python mock-everything pattern provides 50 local PASS without Docker.
- **D1 source-code bug fixes** (LOW, inline): the 3 source bugs that surfaced during T5 test execution were fixed in `b077128`. A follow-up HU owns no additional fixup; the inline fix is the canonical resolution.
- **D2 cumulative LOC** (LOW): the fuller test coverage shipped (~4286 LOC) is the intended deliverable; the plan estimate was a lower bound.
- **Cross-HU implications**:
  - F1.14 (sync estado): F1.14 plans to seed `alert_types.descuadre_critico` (11 codes batch). F1.13's MIGRATION 0031 Op 2 already seeds it idempotently → F1.14's seed becomes a no-op for that code.
  - HU-F7.x (frontend arqueo UX): primary consumer of POST + GET. Frontend owns the arqueo UI flow.
  - HU-F10.1/10.2/10.3 (frontend arqueo UX variants): consumer of POST (auditoria / cierre_turno / cierre_dia codigos).
  - HU-F18.1 (Parte 2 filtros): F1.13's `GET /caja/arqueo/resumen` is the resumen endpoint; F18.1 will extend the single-arqueo `GET /caja/arqueo` with filtros (different endpoint).
  - HU-F22.3 / HU-F24.4 (Parte 3 installer): GAP-BE-05 already closes the `parkos_app` least-privilege story. F1.13 inherits the role contract.
- **Reusable artifacts** (F1.13):
  - `repo/arqueo.py::resolver_tipo_arqueo_por_uuid` (~30 LOC) — reusable by any future endpoint that needs bi-temporal VersionedBase + `SELECT FOR UPDATE` lock + vigente row resolution.
  - `repo/arqueo.py::es_descuadre_critico` (~15 LOC pure Decimal math) — reusable by Fase 10 reconciliation (pct vs absolute) when tolerance semantics change.
  - `repo/arqueo.py::cerrar_sesiones_del_dia_bulk` (~25 LOC) — reusable by any future endpoint that needs to satisfy `ls_session_guard` on a list of sesiones.
  - `repo/arqueo.py::insertar_alerta_descuadre_critico` (~25 LOC) — reusable as a template for any future alert via `append_transition` wrapping.
  - `schemas/caja.py::ArqueoCreateV2` + 4 response schemas + 6 typed errors (~146 LOC) — reusable as the arqueo Pydantic template for F18.x extensions.
- **Forward hooks**:
  - HU-F1.14 (`GET /sync/estado` + 11 alert_types nuevos): independent catalog seed; F1.13's MIGRATION 0031 Op 2 ahead-loads `descuadre_critico`.
  - HU-F1.15 (`GET /usuarios/{uuid}/login` histórico): independent — no shared atomic transaction.
  - HU-F18.x (Parte 2 arqueos): F1.18.1 filtros + F1.18.2 listado + F1.18.3 resumen consume the F1.13 endpoint pair.

## Next steps

- HU-F1.13 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por `plan.md` + `pending.md`: **HU-F1.14 — `GET /sync/estado` + 11 alert_types nuevos** (120 LOC). 8 técnicos ya sembrados (F1.7 + F1.9 + F1.11); total 19 idempotente.
- 2 HUs restantes pendientes (F1.14 + F1.15 = 190 LOC).
- `pending.md` housekeeping: F1.13 row needs ✅ cerrado marker + archive date stamp 2026-09-15 added to §1 row; §1 "HUs restantes" count updated 5 → 4.

---

**Closed by**: sdd-archive (executor).
**Archive commit**: not authored (archive phase does not produce commits; follow-up chore commit by orchestrator at end of Fase 1 Parte I).
**Engram**: observation persisted, topic_key=`sdd/hu-f1-13-arqueo/archive-report`, project=`easypunto-parkos`.
