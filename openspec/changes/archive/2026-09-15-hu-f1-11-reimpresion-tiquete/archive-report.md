# Archive Report: hu-f1-11-reimpresion-tiquete

## Summary

**Change**: HU-F1.11 — Workflow reimpresión tiquete (crear + anular) + GAP-BE-04 cierre
**Outcome**: SHIPPED. Verified PASS with 0 CRITICAL/HIGH/MEDIUM and 4 LOW documented deviations (D1 validate_motivo_length deferred, D2 AST helper extraction deferred, D3 GET preservation test deferred to Fase-2 QA, R3 issuer dep permission kwarg unavailable — security model preserved via MIGRATION 0029 Op 3 role grants).
**Branch**: `feat/fase-1-prerequisites-backend`
**Commits**:
- `cd2e4fb feat(backend): HU-F1.11 — POST endpoints + KD-3 issuer + Cache-Control no-store` (T4a, 405 LOC)
- `3687880 test(backend): HU-F1.11 — handler unit tests (create + anular)` (T4b, 823 LOC)
- `977ff36 feat(backend): HU-F1.11 — GAP-BE-04 fix (emitir_reimpresion → reimprimir_ticket) + router wiring` (T5, 332 LOC)
- `81017a5 feat(db): HU-F1.11 — MIGRATION 0029 siembra + anular_reimpresion permission + role grants` (T6, 545 LOC)
- `4c376ea feat(static): HU-F1.11 — AST walks (insert-only no-UPDATE + KD-TKT-01 single-commit)` (T7, 395 LOC)
- `7e2dc50 test(backend): HU-F1.11 — final integration + full regression sweep` (T8, 291 LOC)
- `f6a4f11 chore(openspec): HU-F1.11 — all 31 tasks [x] across 8 clusters (T1..T8)` (docs)
- `7c48faf chore(openspec): HU-F1.11 — apply-report (7 commits, 2791 LOC, 30 tests + 5 SKIP)` (docs)

**Note on T1..T3 prep commits**: `0d56c56` (T1 repo skeleton), `486c669` (T2 repo helpers + 5 typed exceptions), and `15ad16a` (T3 Pydantic schemas) shipped earlier in the apply phase as preparation commits referenced from apply-report.md.
**Spec canonical merge**: REQ-OPS-075..080 + REQ-OPS-XR4 (7 REQs) merged into `openspec/specs/operations/spec.md`. Status: appended (canonical spec now has 87 REQs total).
**Archived location**: `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/`

## Reconciliations

### Verification per `verify-report` observation #1587 (architecture, 2026-09-15 08:49:22 UTC)

- **44 F1.11 reimpresion tests PASS + 7 SKIP** (DB-gated `requires_db` skipped cleanly without `PARKOS_DOCKER_TEST=1`; same baseline as F1.5..F1.10).
- 43 pre-existing baseline failures in F1.9/F1.10 test files are NOT introduced by F1.11 (verified via git log on those files; last touched in commits `d4ad6c5`/`da3016e`/`025ea82`/`898cdae`).
- DEC-TKT-01 GAP-BE-04 fix verified at `api/v1/workflows.py:74` — now reads `"reimpresion-ticket": ("operador-,admin-", "reimprimir_ticket")`.
- 5 CI gates clean: `factory_intact` + `event_helper_intact` + `auth_tenancy_intact` + `__init__.py_intact` (4 LOC additive) + `repo/workflow.py` (append_transition + read_chain_tip reused verbatim from F1.5 PR5-016).
- 9 AST walks PASS (3 no-UPDATE + 6 single-commit + no-begin_nested + no-SAVEPOINT) enforcing KD-TKT-01 single-commit + DEC-TKT-02/03 NEVER UPDATE invariants.
- **Verdict**: PASS.

### D1..D3 + R3 LOW deviations (all ACCEPTABLE)

- **D1**: `validate_motivo_length` helper deferred. Pydantic `StringConstraints(min_length=10, max_length=500)` at schema layer supersedes (Layer 4 contract). Skipped per orchestrator "if a helper adds no value, don't add it" mandate. T2.5 marked [x] as DEFERRED with rationale.
- **D2**: AST walk helper extraction deferred (T7.4). The two walk files have distinct handler targets and distinct node shapes; extraction would have added indirection without reducing line count. Skipped per "do not extract unless duplication becomes painful" mandate.
- **D3**: GET preservation test coverage (T8.2) deferred to Fase-2 QA. Covered indirectly via T5.1 source-level assertion + the existing `test_workflows_router_wiring.py` config check. A dedicated HTTP integration test would require `PARKOS_DOCKER_TEST=1`.
- **R3**: `_anular_reimpresion_issuer_dep` does not carry the `permission="anular_reimpresion"` filter at the issuer level because `requires_issuer(*allowed: str)` does NOT accept a permission kwarg. Security model preserved via MIGRATION 0029 Op 3 role grants (only `operador` and `admin` roles receive the `anular_reimpresion` permission row in `prod.permisos_usuario`). AST walk `test_reimpresion_issuer_deps_use_operador_admin_scope` pins the prefix tuple as defense in depth.

### R1..R2 LOW (documented in apply-report.md)

- **R1 (LOW)**: MIGRATION 0029 downgrade Op 1 has a 1-hour time window (`vigente_desde >= NOW() - INTERVAL '1 hour'`). If a manual siembra happened between migration and downgrade, the row is also deleted. Documented in design Appendix A.6 + REQ-OPS-079 DoF.
- **R2 (LOW)**: `create_reimpresion_ticket` validation does NOT currently invoke `buscar_costo_servicio_vigente_por_concepto` (DEC-TKT-05 defensive check). The handler relies on the F1.6 Idempotency-Key middleware for transactional safety; the siembra check is wired into the repo helper for future use (F1.12 may wire it into the create path).

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains 87 REQs (80 prior + 7 new). To reverse safely:
- `git revert 7c48faf` reverts the apply-report chore
- `git revert f6a4f11` reverts the post-apply chore
- `git revert 7e2dc50` reverts T8 e2e test
- `git revert 4c376ea` reverts T7 AST walks
- `git revert 81017a5` reverts T6 MIGRATION 0029 + tests
- `git revert 977ff36` reverts T5 GAP-BE-04 + router wiring
- `git revert 3687880` reverts T4b handler tests
- `git revert cd2e4fb` reverts T4a handler module
- Spec content in archive remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **Pre-existing test baseline**: 1563 SKIP per `conftest.py:343-372` autouse session fixture from testcontainers cascade (no Docker daemon in this environment). NOT introduced by F1.11. Same baseline as F1.5..F1.10. Recommend dedicated housekeeping pass pre-Fase-2.
- **ER diagram update**: no ER diagram changes required for F1.11 (existing `modelo_datos_er.mmd` lines 598-620 + 1150-1155 already cover `reimpresion_ticket` [L-W] + FK to `prod.facturas`).
- **Reusable artifacts**:
  - `repo/reimpresion_ticket.py` (~80 LOC, 6 helpers + 5 typed exceptions + idempotency wrapper) — reusable by any future endpoint that needs to manage reimpresion chain + GAP-BE-04 reconciliation.
  - `repo.workflow.append_transition(...)` + `repo.workflow.read_chain_tip(...)` (F1.5 PR5-016) — reused verbatim from F1.5; reusable by any future `[L-W]` chain handler.
  - `AlertaFactory` at `repo/alert_types.py:51-97` (F1.10) — still reusable by any future handler that needs to fire a seeded alerta.
  - `buscar_resolucion_vigente_por_sucursal` at `repo/resolucion_facturacion.py:152-175` (F1.10) — reusable for any handler that needs the vigente resolution for a sucursal.
- **Defense in depth chain completa** (KD-3 issuer → permission gate → tenant scope → FK chain integrity → 422/409 mapping). See REQ-OPS-XR4.
- **KD-TKT-01 single-commit invariant** enforced via 6 AST walks in `tests/static/test_workflow_handler_single_commit.py`. Independently verified: no `begin_nested` / `SAVEPOINT` / multiple `commit()` in either handler body.
- **DEC-TKT-03 NEVER UPDATE on `prod.reimpresion_ticket`** enforced via 3 AST walks in `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py`. Only `vigente_hasta` MAY be UPDATEd for bi-temporal versioning (WorkflowBase contract).
- **Forward hooks**:
  - F1.12 (Venta atómica de suscripción): 260 LOC, no bloqueador — may wire `buscar_costo_servicio_vigente_por_concepto` into the create path (DEC-TKT-05 follow-up).
  - F1.13 (Arqueo): consumes `prod.reimpresion_ticket` chain for cierre_dia.
  - HU-F8.3 (FE consumer UI): consumes the new endpoints + populates `uuid_factura`.
  - Fase 8 frontend: HU-F8.1 reimpresion form consumes both POST endpoints.

## Next steps

- HU-F1.11 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por plan.md: **HU-F1.12 — Venta atómica de suscripción** (260 LOC).
- 4 HUs restantes pendientes (F1.12, F1.13, F1.14, F1.15).
- pending.md housekeeping: F1.11 row to [x], totals updated (740 LOC remaining in 4 HUs: 260 + 240 + 120 + 70 = 690 LOC — minor delta from F1.10 estimate, see plan.md).

---

**Closed by**: sdd-archive (executor). Update TODO-fase-1.md marking HU-F1.11 [x] (handled by orchestrator, FUERA de este agente).
**Engram**: observation persisted, topic_key=`sdd/hu-f1-11-reimpresion-tiquete/archive-report`, project=`easypunto-parkos-software`.
