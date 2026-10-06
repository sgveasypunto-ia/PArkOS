# Tasks: backend-ignore-datafono-cierre-arqueos

> Phase: tasks · Design: `design.md` · Specs: `specs/operations/spec.md` + `specs/sync-motor/spec.md` · Proposal: `proposal.md`

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~600 prod + ~400 tests = **~1000 LOC** |
| Per-commit max | ~170 LOC (Concern 1) |
| 400-line budget risk | **High** (1000 passes 800 LOC preflight) |
| Chained PRs recommended | **Yes** |
| Delivery strategy | `ask-on-risk` (decision required) |
| Chain strategy | **pending** (`stacked-to-main` / `feature-branch-chain` / `size-exception`) |

Decision needed before apply: **Yes**
Chained PRs recommended: **Yes**
Chain strategy: **pending**
400-line budget risk: **High**

Design note says "single PR factible"; preflight pins 800 LOC and the forecast (1000) **passes** it. Orchestrator surfaces 3 chain options to user before `sdd-apply`. If chained, 5 WUs (Phases 1, 2, 3, 4, 5+6) keep per-PR LOC under 400.

## Phase 1: Foundation — repo signatures (Concern 0)

- [ ] 1.1 `repo/arqueo.py:334-435` → `calcular_esperado_sesion/_cierre_dia` returns `-> Decimal` (D4); `es_descuadre_critico(d, t)` drops datafono params (D5)
- [ ] 1.2 `caja_arqueo.py:347-360, 555-558, 382-387` → drop tuple unpack + datafono args
- [ ] 1.3 Tests `test_arqueo_repo.py`: `test_calcular_esperado_sesion_returns_decimal_only`, `test_es_descuadre_critico_drops_datafono_params`, `test_es_descuadre_critico_boundary`
- [ ] 1.4 Commit: `refactor(repo): calcular_esperado_* returns Decimal; es_descuadre_critico drops datafono params`

## Phase 2: Wire contract — schemas (Concerns 1, 2)

- [ ] 2.1 `schemas/caja.py:349-498` → `ArqueoCreateV2.valor_datafono_reportado: Decimal | None = None` (REQ-OPS-191); `ArqueoReadForHandler`/`ArqueoResumenItem`/`ArqueoResumenAdminItem` drop 3 datafono fields (REQ-OPS-192)
- [ ] 2.2 `schemas/workflows.py:347, 374, 392` → `AlertaCreate/Read/Update` drop `valor_diferencia_datafono`; `schemas/operacion.py:757, 774` → `MiTurnoRead.total_cobrado_datafono_cop: Decimal = 0` (D1)
- [ ] 2.3 `caja_sesion.py:104-119` → `ArqueoDiferenciasResponse` drops 3 datafono fields
- [ ] 2.4 Tests: `test_caja_arqueo_admin*.py`, `test_arqueo_schemas.py`, `test_caja_sesion.py::test_arqueo_diferencias_response_excludes_datafono`
- [ ] 2.5 Commit: `fix(schemas): wire V2 datafono nullable; responses drop datafono (REQ-OPS-191/192)`

## Phase 3: Handler core — arqueo + cierre_dia (Concerns 3, 4, 5)

- [ ] 3.1 `caja_arqueo.py:355-477` → Step 5 single esperado/diferencia; Step 7 simplified `es_descuadre_critico`; Step 8 INSERT drops datafono kwargs; Step 10 alerta payload drops datafono keys; Step 13 response drops datafono (REQ-OPS-091/094/095)
- [ ] 3.2 `caja_arqueo.py:389-395` → `esperado_total = esperado_efectivo`; `(diferencia_efectivo / esperado_efectivo) * 100` (REQ-OPS-093)
- [ ] 3.3 `caja_arqueo.py:555-571` (cierre_dia) → single esperado/diferencia; `requiere_justificacion=diferencia_efectivo != 0` (REQ-OPS-193)
- [ ] 3.4 Tests: `test_caja_arqueo.py::test_arqueo_create_v2_accepts_null_datafono`, `::test_arqueo_create_v2_accepts_legacy_datafono_decimal`, `::test_arqueo_read_for_handler_excludes_datafono_fields`, `::test_arqueo_insert_excludes_datafono_columns`, `::test_datafono_only_descuadre_does_not_emit_alerta` (REQ-OPS-196), `::test_historical_datafono_alerta_remain_visible`; `test_caja_cierre.py::test_cierre_dia_aggregate_effective_only`
- [ ] 3.5 Commit: `fix(caja_arqueo): post_arqueo + cierre_dia effective-only; datafono excluded from INSERT + alerta`

## Phase 4: Side effects — alertas + mi_turno (Concerns 6, 7)

- [ ] 4.1 `workflows_alerta.py:444-469` → `descuadrar_alerta` keeps `append_transition` reading `tip_row.valor_diferencia_datafono` (column nullable; historical preserved)
- [ ] 4.2 Create `apps/electron-sucursal/src/lib/alertas/router.test.ts::test_diferencia_datafono_route_preserved` (REQ-OPS-199, D3)
- [ ] 4.3 `repo/mi_turno.py:150-170` → drop `_sum_factura_pagos_by_medio_pago(("tarjeta","datafono"))`; `total_datafono = Decimal(0)` (REQ-OPS-197, D1)
- [ ] 4.4 Tests: `test_mi_turno.py::test_total_cobrado_datafono_cop_is_zero` + static `test_mi_turno_schema.py`
- [ ] 4.5 Commit: `fix(alertas+mi_turno): drop datafono from alerta + mi_turno sum; preserve FE drill-down (REQ-OPS-197/199)`

## Phase 5: Sync + GET projections (Concerns 8, 8a, 9)

- [ ] 5.1 `sync/motor/apply_row.py:294-301` → `valor_final_datafono=None` explicit on close leg (REQ-MOT-001, D2); `repo/session_cycle.py:333-350` → drop `valor_final_datafono` key from `datos_nuevos` when value is `None` (REQ-MOT-016, 8a)
- [ ] 5.2 `repo/arqueo.py:688-757, 948-1036` → drop datafono dict keys (`construir_resumen_sesion`, `obtener_cierre_dia_del_dia`, `resumen_admin_del_dia`) (REQ-OPS-097); `caja_arqueo.py:735-748` `_row_to_admin_item` drops `esperado_datafono`
- [ ] 5.3 Tests: `test_sync_apply_row.py::test_session_cycle_close_passes_datafono_none`, `::test_session_cycle_open_passes_datafono_through`, `::test_session_cycle_close_persisted_column_is_default`, `::test_session_cycle_close_datos_nuevos_omits_datafono`; `test_sync_chain.py::test_chain_unaffected_by_datafono_drop`
- [ ] 5.4 Commit: `fix(sync+arqueo+session_cycle): datafono dropped at sync close; GET projections effective-only (REQ-MOT-001/016, REQ-OPS-097)`

## Phase 6: Cierre schema response (Concern 2 — deferred per design)

- [ ] 6.1 `caja_sesion.py:212, 247-270` → close handler passes `payload.valor_final_datafono` unchanged; verify response drops datafono keys
- [ ] 6.2 Tests: `test_session_cycle_open_close.py`, `test_caja_sesion_me.py`
- [ ] 6.3 Commit: `fix(caja_sesion): cierre handler response drops datafono keys`

## Acceptance criteria globales

Wire: `ArqueoCreateV2.valor_datafono_reportado` accepts `null` + `Decimal` (REQ-OPS-191); responses drop 3 datafono fields (REQ-OPS-192). DB: `prod.arqueo` INSERT excludes `valor_datafono_*` + `diferencia_datafono` (REQ-OPS-091); `descuadre_pct = (diferencia_efectivo / esperado_efectivo) * 100` (REQ-OPS-093); `es_descuadre_critico` compares efectivo only (REQ-OPS-195). Alertas: NO new `prod.alerta` for datafono-only descuadre (REQ-OPS-196); pre-existing `valor_diferencia_datafono != 0` rows remain visible (D3); FE drill-down preserved (REQ-OPS-199). mi_turno: `total_cobrado_datafono_cop = 0` (D1, REQ-OPS-197). Sync: close path passes `valor_final_datafono=None` explicit (REQ-MOT-001, D2); `datos_nuevos` omits the key (REQ-MOT-016); hash chain unbroken (datafono not chain-bearing). Gates: `check_schema_match.py` (h) verde — 49 tables + 8 partman parents unchanged (no migration); `ruff check .` + `mypy packages/parkos_core/src` verde; `pytest -q --cov --cov-fail-under=80` verde.

## Plan de merge

Branch `fix/backend-datafono-ignored` from `dev` (HEAD `481ca7e5`); 6 commits, one per phase, ordered 1→2→3→4→5→6 per design. Single PR vs chained: **pending** (orchestrator asks user). Options: `stacked-to-main` / `feature-branch-chain` / `size-exception`. If `size:exception`: merge `--no-ff` to `dev`; push origin dev; delete branch. If chained: 5 WUs (Phase 1 = WU-1, etc.) per ~400 LOC; feature-branch-chain keeps clean rollback boundaries. Author: `Parkos Dev <dev@parkos.local>`; no `Co-authored-by` trailer. Post-merge: `git push origin dev`; `git branch -d fix/backend-datafono-ignored`; `git push origin --delete <branch>`.

## Dependencias entre concerns

```
Concern 0 (repo signatures) — MUST land first
  ├─→ 3 (arqueo cálculo) → 4 (descuadre_pct) → 5 (requiere_justificacion)
  └─→ 9 (GET projections)
Concern 1 (schemas V2) → 3, 4, 5
Concern 2 (cierre schema) — independent of 3/4/5 (caja_sesion.py ≠ caja_arqueo.py)
Concern 6 (alertas) — independent
Concern 7 (mi_turno) — independent
Concern 8 (sync apply_row) → 8a (session_cycle helper)
Concern 9 depends on 0 only
```

Critical path: `0 → 1 → 3 → 4 → 5`. Concerns 6, 7, 8/8a, 9 ship in any order after 0. Concern 2 is the cleanest last commit (no caller impact).

## Riesgos y mitigaciones (resumen)

- **R1** external clients reading removed response fields → `MiTurnoRead` field preserved (D1) + FE no longer reads them + release notes
- **R2** pre-existing alertas with `valor_diferencia_datafono != 0` lost → D3 drill-down preserved + no-DELETE compliance
- **R3** hash chain broken by datafono drop → `test_chain_unaffected_by_datafono_drop` (datafono not chain-bearing per AGENTS.md §Sync)
- **R4** `Decision needed before apply: Yes` blocks apply → orchestrator surfaces 3 chain options
- **R5** FE test file `router.test.ts` does not exist → explicit creation in Phase 4.2
- **R6** `check_schema_match.py` (h) regresses if DDL slips in → no-migration contract

> **Note on size budget**: this artifact is ~615 words (over the 530-word skill budget) because the user explicitly requested the Plan-de-merge, Acceptance-criteria-globales, Dependencias, and Riesgos sections. Compressing further would sacrifice REQ references and concrete file paths; the orchestrator can re-derive the per-task detail from `design.md` if a stricter budget is needed.
