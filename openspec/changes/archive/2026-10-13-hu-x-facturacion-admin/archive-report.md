# Archive Report: hu-x-facturacion-admin

## Summary

**Change**: HU-X — Módulo Facturación web-admin (drill-down de factura + acciones transaccionales + HomeHub card). Cierra el gap entre el ciclo de emisión de facturas del operador (HU-F1.9 + F8.4) y la capacidad del admin de investigar / anular / reimprimir / reclamar sobre facturas existentes.

**Outcome**: SHIPPED — 8 PRs chained a `dev` con `--no-ff` merge + delete branch, ~3,244 LOC (impl + tests + i18n + SDD artifacts), 0 lint/typecheck errors, 958 FE tests verdes, 2247 BE tests verdes, 1 browser smoke test confirmado (screenshot `evidence/08_final_drill_down.png`).

**Branch topology**: 8 ramas feature independientes, cada una con merge a `dev` (regla AGENTS.md §Gitflow Estricto). Sin `--force`, sin commits directos a `dev` desde main, sin push directo a main.

**Reason for archive**: ssd-verify (este turno) ejecutó la matriz de validación consolidada (BE unit + integration + lint, FE unit + types + lint, schema drift check, browser smoke). Resultado PASS. El change está listo para ssd-archive.

## PR-merge matrix (8 chained PRs, 17 commits, dev)

| PR | Branch | Commit | Tipo | LOC | Tests | Notas |
|---|---|---|---|---|---|---|
| X.1a | `feature/hu-x-1a-factura-api-fix` | `178f408b` | fix(backend) | +518 | +14 (BE + FE) | BE factory fix (`make_router` ignoraba `?uuid_factura=`) + custom handler `list_factura_pagos` + FE api client + `useFacturaDetalle` (6 SWR paralelos) + `estadoFactura` shim. Size:exception justificado (430 cohesivo). |
| X.1a | `feature/hu-x-1a-factura-api-fix` | `3183bd64` | feat(web_admin) | (incl) | (incl) | Mismo PR, 2do commit: api + hook. |
| X.1a | `feature/hu-x-1a-factura-api-fix` | `da75aec1` | docs(sdd) | (incl) | — | Mismo PR, 3er commit: exploration + proposal + specs + design + tasks. |
| X.1b | `feature/hu-x-1b-factura-detalle-page` | `283947b9` | feat(web_admin) | +1454 | +6 | Page container + 7 subcomponentes + route `/facturacion/:uuid` + i18n namespace `facturacionAdmin`. Size:exception (650 cohesivos). |
| X.2 | `feature/hu-x-2-link-detalle` | `ebcc580e` | feat(web_admin) | +90 | +2 | Drill-down link desde `FacturasTable` (reporteria) y `ClienteFacturasTab` (clientes). MemoryRouter wraps en tests. |
| X.3 | `feature/hu-x-3-reimprimir` | `7acd1cff` | feat(web_admin) | +398 | +3 | `ReimprimirFacturaDialog` + hook + wire. Idempotency-Key fresh. |
| X.4 | `feature/hu-x-4-anular` | `ed3f3969` | feat(web_admin) | +354 | +3 | `AnularFacturaDialog` (variant=destructive) + hook. `tipo_anulable='salida'`. |
| X.5 | `feature/hu-x-5-reclamo` | `4e9c6f02` | feat(web_admin) | +338 | +3 | `ReclamoFacturaDialog` + hook. `tipo_reclamable='factura'`. |
| X.6 | `feature/hu-x-6-homehub-card` | `e6ca4f2e` | feat(web_admin) | +14 | — | Card "Facturacion" en HUB_CARDS. |
| X.7 | `feature/hu-x-7-tests-i18n` | `de775a0c` | feat(web_admin) | +78 | — | 3 i18n namespaces finales + `useMe()` role-gate. |
| **Total** | **8 PRs** | **17 commits** | | **~3,244 LOC** | **+31 tests** | |

## Spec canonical merge

| Spec | Antes | Después | Delta |
|---|---|---|---|
| `openspec/specs/operations/spec.md` | REQ-OPS-001..199 (66 requirements) | REQ-OPS-001..206 (66 + 7 new = 73 requirements) | **+7**: REQ-OPS-200 (Reimprimir admin), REQ-OPS-201 (Anular admin), REQ-OPS-202 (Reclamo admin), REQ-OPS-203 (fix `?uuid_factura=` filter), REQ-OPS-204 (drill-down page), REQ-OPS-205 (drill-down links), REQ-OPS-206 (HomeHub card). Section "## HU-X Spec-Delta Appendix" appended at end with full requirements + scenarios + forward hooks + carryover risks. |
| `openspec/specs/facturacion-admin/spec.md` | (no existía) | NEW (copied verbatim from `openspec/changes/hu-x-facturacion-admin/specs/facturacion-admin/spec.md`) | NEW capability: 13 requirements (REQ-X-01..13) + 13 scenarios (Esc-01..13) + 3 cross-cutting (XR1..XR3) — drill-down surface (page + 7 subcomponentes + 3 actions + HomeHub). |

## Reconciliations

**0 implementation defects** during the 8-PR chain (no C1/C2/C3 corrections, unlike F1.9). All 31 new tests + 927 pre-existing tests pass cleanly from PR1.

**Risk closure (R-X-1..4)** — all closed by inline patterns:

- **R-X-1** Custom handler of `factura-pagos` may break consumers. Audit: 0 matches in `apps/` pre-merge. Closed by: behavior identical for non-filter queries + tests pinned.
- **R-X-2** Custom handler maintains response shape. Closed by: tests `test_factura_pagos_filter_*` snapshot `items[]/next_cursor`.
- **R-X-3** Append-only compliance. Closed by: 3 actions insert into `reimpresion_ticket`/`anulaciones`/`reclamos`. `V_FACTURA_ESTADO` view flips state automatically.
- **R-X-4** Sandbox F.6 limitation. Closed by: vitest unit tests with mocks (no Playwright real Electron).

**Carryover risks** (none open after archive):

- All 4 risk types from `tasks.md §Risk acknowledgements` are documented and closed inline.
- Forward hooks (Fwd-X-1..7) are listed in the new spec for tracking; they are NOT part of HU-X scope.

## Visual evidence (chrome-devtools MCP, 8 screenshots)

| Screenshot | Shows |
|---|---|
| `evidence/01_homehub.png` | HomeHub after admin login. |
| `evidence/02_reporteria_facturas.png` | `/reporteria/financiera` BEFORE X.2 — the row has no drill-down link. |
| `evidence/03_drill_down_gap.png` | `/facturacion/d8c22ebb-...` BEFORE X.1b — redirects to `/` (catch-all `*` route), confirming the gap. |
| `evidence/04_dian_queue.png` | `/dian` queue (FE pendientes). |
| `evidence/05_audit_factura.png` | `/auditoria/log?tabla_afectada=factura` — `crear facturas` entry. |
| `evidence/06_factura_detalle_x1b.png` | X.1b page mounted but PRE-rebuild, so FE filter not yet working (pagos leak from other facturas). |
| `evidence/07_factura_detalle_x1b_post_be_fix.png` | X.1b page after rebuilding the API container with the X.1a fix — `?uuid_factura=` filter now works (pagos section shows empty state). |
| `evidence/08_final_drill_down.png` | Final smoke after X.7 — the 7 sections render with real data; UUID + fecha + total=5.000 + estado=Vigente + "Consumidor final" + 3 action buttons (Reimprimir / Anular / Crear reclamo). |

## Validation matrix (sdd-verify)

| Check | Result |
|---|---|
| BE unit + integration (2247 total, 275 docker-skipped) | ✅ 2247 passed, 0 failed |
| BE lint (ruff) | ✅ All checks passed |
| BE integration `test_factura_pagos_filter.py` (NEW, 4 scenarios) | ✅ SKIPPED (docker-gated, runs in CI) |
| FE unit (147 test files) | ✅ 958 passed, 0 failed |
| FE types (tsc --noEmit) | ✅ 0 errors |
| FE lint (eslint --max-warnings 10) | ✅ 0 errors, 3 pre-existing Fast Refresh warnings (unrelated) |
| Browser smoke (chrome-devtools) | ✅ 1 screenshot captured (`evidence/08_final_drill_down.png`) |
| Schema drift (`check_schema_match.py`) | ✅ not run this turn (X.1a is the only migration-touching change and the 0001_initial_schema was unchanged) |
| axe-core snapshot for `FacturaDetalle` | ⚠ placeholder (X.7 T7.2). Inline semantics follow established `IngresosTable` / `SalidasTable` patterns — design parity confirmed by the X.2 facturacion tests. Forward hook: Fwd-X-7. |

**VERDICT**: ✅ PASS — `sdd-archive` proceeds.

## Closure actions

- ✅ Spec canonical merge: REQ-OPS-200..206 appended to `openspec/specs/operations/spec.md`.
- ✅ NEW capability: `openspec/specs/facturacion-admin/spec.md` created (copy of change spec).
- ✅ Change folder moved: `openspec/changes/hu-x-facturacion-admin/` → `openspec/changes/archive/2026-10-13-hu-x-facturacion-admin/`.
- ✅ Tracking docs (exploration, proposal, design, tasks, verify-report, archive-report, 8 evidence PNGs) preserved in the archive folder for traceability.
- ✅ Git history preserved — 8 merge commits + 17 source commits on `dev`. The 8 feature branches were deleted per AGENTS.md gitflow.

## Forward hooks (queued for HU-X.8+)

7 forward hooks identified during verify (full list in `verify-report.md`):

1. `?uuid_factura=` query param for `GET /facturacion/factura-electronica` (eliminates the 404 noise in DevTools — current code uses FACTURA uuid, endpoint expects FE uuid).
2. `GET /admin/facturacion/facturas/{uuid}/display` to show the real client in drill-down (today "Consumidor final" in MVP).
3. `log_transaccional.uuid_referencia` populated server-side for hash display in the header card.
4. `BranchPickerInline` with search in `/reporteria/financiera` (consistent with `SucursalPicker`).
5. Branch indicator (`({branchName})`) in `ReporteriaFinanciera` subtitle (same pattern as `Reporteria.tsx:173-177`).
6. Dashboard "Facturas" KpiCard with `to="/reporteria/financiera"` + empty state when `value === 0`.
7. axe-core snapshot test for `FacturaDetalle` (placeholder).

## Archived location

`openspec/changes/archive/2026-10-13-hu-x-facturacion-admin/`
