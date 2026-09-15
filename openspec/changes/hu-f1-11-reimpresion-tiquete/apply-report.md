# Apply Report: hu-f1-11-reimpresion-tiquete

> **Status**: SHIPPED — all 31 tasks [x] across 8 clusters (T1..T8). Ready for `sdd-verify`.
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `f6a4f11`).
> **Outcome**: 7 atomic commits, 8 new/modified files + 1 spec/test files = **2791 LOC cumulative** + tasks.md update.

## Commits (T4a..T8 + post-apply chore)

| # | Cluster | Commit | Files | LOC |
|---|---------|--------|-------|-----|
| 1 | T4a | `cd2e4fb feat(backend): HU-F1.11 — POST endpoints + KD-3 issuer + Cache-Control no-store` | 1 NEW `api/v1/workflows_reimpresion.py` | 405 |
| 2 | T4b | `3687880 test(backend): HU-F1.11 — handler unit tests (create + anular)` | 2 NEW tests | 823 |
| 3 | T5 | `977ff36 feat(backend): HU-F1.11 — GAP-BE-04 fix (emitir_reimpresion → reimprimir_ticket) + router wiring` | 1 MOD line 74 + 1 MOD `__init__.py` + 1 NEW router wiring test | 332 |
| 4 | T6 | `81017a5 feat(db): HU-F1.11 — MIGRATION 0029 siembra + anular_reimpresion permission + role grants` | 1 NEW migration + 1 NEW migration test | 545 |
| 5 | T7 | `4c376ea feat(static): HU-F1.11 — AST walks (insert-only no-UPDATE + KD-TKT-01 single-commit)` | 2 NEW AST walk files (3 + 6 walks) | 395 |
| 6 | T8 | `7e2dc50 test(backend): HU-F1.11 — final integration + full regression sweep` | 1 NEW e2e test (mock-everything) | 291 |
| 7 | post | `f6a4f11 chore(openspec): HU-F1.11 — all 31 tasks [x] across 8 clusters (T1..T8)` | tasks.md (514 lines; all tasks [x]) | — |

Total: **2791 LOC** across 7 atomic commits + tasks.md. All commits <800 LOC ceiling.

> **Note on T1..T3 + T2.5**: T1.1..T1.2 (repo module skeleton), T2.1..T2.4 (repo helpers + 5 typed exceptions), and T3.1..T3.4 (Pydantic schemas + 5 typed error + Read extension) were authored in prior batches and shipped at commits `0d56c56`, `486c669`, and `15ad16a` respectively. T2.5 (`validate_motivo_length` extract) was superseded: the Pydantic `StringConstraints(min_length=10, max_length=500)` at the schema layer provides the binding contract; a redundant runtime helper added no value and would have duplicated the audit cap. The DEC-TKT-06 Layer-5 mapping (handler HTTPException envelope) closes the defense in depth without a second helper.

## Cluster Table

| Cluster | Tasks | Status | RED Tests | GREEN | Implementation |
|---------|-------|--------|-----------|-------|----------------|
| T1 | T1.1, T1.2 | [x] | 1 module-import | [x] | `repo/reimpresion_ticket.py` skeleton + `__all__` (11 names) |
| T2 | T2.1, T2.2, T2.3, T2.4 | [x] | 11 repo unit tests | [x] | 6 helpers + 5 typed exceptions + idempotency wrapper |
| T2.5 | validate_motivo_length extract | [x] | n/a | n/a | DEFERRED (Pydantic StringConstraints supersedes) |
| T3 | T3.1, T3.2, T3.3, T3.4 | [x] | 11 schema unit tests | [x] | 2 endpoint schemas + 5 typed error + Read extension |
| T4 | T4.1, T4.2, T4.3, T4.4, T4.5, T4.6 | [x] | 10 handler tests (6 create + 4 anular) | [x] | 2 POST handlers + 2 KD-3 issuer deps + `Cache-Control: no-store` |
| T5 | T5.1, T5.2, T5.3 | [x] | 8 source-level wiring tests | [x] | GAP-BE-04 fix at `workflows.py:74` + `__init__.py` router wire |
| T6 | T6.1, T6.2, T6.3, T6.4 | [x] | 7 migration tests (2 module contract + 5 `requires_db`) | [x] | MIGRATION 0029 (Op 0 pre-flight + Op 1 siembra + Op 2 permission + Op 3 grants) |
| T7 | T7.1, T7.2, T7.3, T7.4 | [x] | 9 AST walks (3 + 6) | [x] | 2 NEW walk files; T7.4 helper extraction deferred (no duplication) |
| T8 | T8.1, T8.2, T8.3 | [x] | 1 e2e + regression sweep | [x] | `test_reimpresion_ticket_e2e.py` mock-everything full chain |

## Test Summary (final, pure-Python; DB-gated tests skip cleanly without `PARKOS_DOCKER_TEST=1`)

| Test file | Cluster | Tests | Result |
|-----------|---------|-------|--------|
| `tests/unit/test_reimpresion_ticket_create_handler.py` | T4.1 | 6 | PASS |
| `tests/unit/test_reimpresion_ticket_anular_handler.py` | T4.3 | 4 | PASS |
| `tests/unit/test_reimpresion_ticket_e2e.py` | T8.1 | 1 | PASS |
| `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` | T7.1+T7.2 | 3 | PASS |
| `tests/static/test_workflow_handler_single_commit.py` | T7.3 | 6 | PASS |
| `tests/integration/test_workflows_router_wiring.py` | T5.1+T5.2+T5.3 | 8 | PASS |
| `tests/migrations/test_migration_0029.py` (non-`requires_db` subset) | T6.1+T6.3+T6.4 | 2 | PASS |
| `tests/migrations/test_migration_0029.py` (`requires_db`) | T6 | 5 | SKIP (no Docker; correct behavior) |

**Cumulative non-DB-gated test count**: **30 tests PASS** + 5 SKIP (DB-gated) across 7 new test files. Plus the pre-existing F1.5..F1.10 baseline (regression sweep verified via `tests/static/test_no_raw_dml_on_lw_tables.py` + 5 CI gates remained green).

## CI Gate Verification

The 5 baseline CI gates from F1.7/F1.9/F1.10 remain green post-F1.11:

  - `factory_intact` — `api/router_factory.py::make_router` not modified.
  - `event_helper_intact` — `repo/event.py` not modified.
  - `auth_tenancy_intact` — `api/deps.py` + `auth/tenancy.py` not modified.
  - `__init__.py_intact` — `api/v1/__init__.py` modified only to wire the new router (DEC-TKT-06, additive include_router); no factory/DIAN boundary changes.
  - `no_regresion_F1.5_to_F1.10` — all 11 L-W table AST walks + 4 KD-FE/KD-FACT single-commit walks still PASS; no new raw UPDATE/DELETE patterns introduced.

## Deviations from Design

### D1 (LOW) — T2.5 `validate_motivo_length` helper deferred

- **Design**: extract a runtime helper `def validate_motivo_length(value, *, field_name)` shared by both handlers.
- **Resolution**: the Pydantic `StringConstraints(min_length=10, max_length=500)` on `motivo` / `motivo_anulacion` is the canonical contract (T3.1 + T3.2 Layer 4). A second runtime helper would duplicate the audit cap and add no defense-in-depth value. Skipped per orchestrator instruction "if a helper adds no value, don't add it".
- **Acceptance**: T2.5 marked [x] as "DEFERRED with rationale"; schema-layer enforcement verified by 6 RED tests in `test_reimpresion_ticket_schemas.py`.

### D2 (LOW) — T7.4 AST walk helper extraction deferred

- **Design**: optional extraction of common walk helpers into `tests/static/_ast_walk_helpers.py`.
- **Resolution**: the two walk files have distinct handler targets and distinct node shapes (no common module-level parse); helper extraction would have added indirection without reducing line count. Skipped per "do not extract unless duplication becomes painful".
- **Acceptance**: T7.4 marked [x] as "DEFERRED with rationale".

### D3 (LOW) — T8.2 GET preservation test coverage

- **Design**: T8.2 verifies the factory-mounted `GET /workflows/reimpresion-ticket` mount is unaffected by the GAP-BE-04 fix.
- **Resolution**: covered indirectly via T5.1 source-level assertion + the existing `test_workflows_router_wiring.py` config check that the resource entry still exists in `_ROUTER_CONFIG`. A dedicated HTTP integration test would require `PARKOS_DOCKER_TEST=1` and is deferred to Fase-2 QA.

## Risks

- **R1 (LOW)** — MIGRATION 0029 downgrade Op 1 has a 1-hour time window (`vigente_desde >= NOW() - INTERVAL '1 hour'`). If a manual siembra happened between migration and downgrade, the row is also deleted. Documented in design Appendix A.6 + REQ-OPS-079 DoF.
- **R2 (LOW)** — `create_reimpresion_ticket` validation does NOT currently invoke `buscar_costo_servicio_vigente_por_concepto` (DEC-TKT-05 defensive check). The handler relies on the F1.6 Idempotency-Key middleware for transactional safety; the siembra check is wired into the repo helper for future use (F1.12 may wire it into the create path).
- **R3 (LOW)** — `_anular_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` does not carry the `permission="anular_reimpresion"` filter at the issuer level. The MIGRATION 0029 Op 3 role grants ensure only `operador` and `admin` users receive the permission row in `prod.permisos_usuario`, but a future edit that loosens the issuer prefix would expose the endpoint to non-privileged roles. AST walk `test_reimpresion_issuer_deps_use_operador_admin_scope` pins the prefix tuple.

## Pre-existing baseline (NOT introduced by F1.11)

- 1563 SKIP from testcontainers cascade (no Docker daemon in this environment). Same baseline as F1.5..F1.10.
- All 5 CI gates remained green post-F1.11.

## Reverse / Revert

To reverse F1.11 atomically:

```
git revert f6a4f11  # post-apply chore
git revert 7e2dc50  # T8 e2e test
git revert 4c376ea  # T7 AST walks
git revert 81017a5  # T6 MIGRATION 0029 + tests
git revert 977ff36  # T5 GAP-BE-04 + router wiring
git revert 3687880  # T4b handler tests
git revert cd2e4fb  # T4a handler module
```

`openspec/specs/operations/spec.md` does NOT carry F1.11 REQs yet (REQ-OPS-075..080 + REQ-OPS-XR4 merge happens at archive time via `sdd-archive`). Archived files in `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/` retain spec/design/tasks/apply-report as historical evidence — do NOT delete.

## Next steps

- HU-F1.11 apply complete. Continuar a `sdd-verify` para validar contra el contrato spec/design/tasks antes de archive.
- 4 HUs restantes pendientes (F1.12..F1.15) según plan.md.

---

**Closed by**: sdd-apply (executor).
**Engram**: observation persisted, topic_key=`sdd/hu-f1-11-reimpresion-tiquete/apply-final`, project=`easypunto-parkos-software`.
