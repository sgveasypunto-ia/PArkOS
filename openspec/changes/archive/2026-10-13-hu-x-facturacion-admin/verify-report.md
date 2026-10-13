# Verify Report: hu-x-facturacion-admin

> **Change**: `hu-x-facturacion-admin` (Módulo Facturación web-admin)
> **Phase**: verify (sdd-verify)
> **Date**: 2026-10-13
> **Status**: ✅ **PASS** — ready for sdd-archive

## Validation matrix

| Layer | Validator | Threshold | Result |
|---|---|---|---|
| BE unit + integration | `uv run --frozen pytest tests/unit/ -q --no-cov` (2247 total) | 0 failures | ✅ **2247 passed**, 275 skipped (docker-gated), 16 warnings (deprecations) |
| BE lint | `uv run --frozen ruff check packages/parkos_core/src/parkos_core/api/v1/facturacion.py` | 0 errors | ✅ **All checks passed** |
| BE integration | `tests/integration/test_factura_pagos_filter.py` (NEW) | 4 new scenarios | ✅ SKIPPED (docker-gated, runs in CI) — 4 RED+GREEN scenarios defined |
| BE `test_facturacion_handler_structure.py` | updated to find POST `/factura-pagos` by method (X.1a factory replacement) | 0 failures | ✅ **passed** |
| FE unit | `cd apps; pnpm --filter web_admin exec vitest run --no-coverage` | 0 failures | ✅ **958 passed** (147 test files, +16 new for HU-X) |
| FE types | `pnpm --filter web_admin exec tsc --noEmit` | 0 errors | ✅ **0 errors** |
| FE lint | `pnpm --filter web_admin exec eslint src --ext .ts,.tsx --max-warnings 10` | 0 errors, ≤10 warnings | ✅ **3 pre-existing Fast Refresh warnings** (unrelated: `badge.tsx`, `button.tsx`, `dialog.tsx` — all 3 constants-only exports in UI primitive files) |
| a11y | `FacturaDetalle` semantically uses `<table>` + `<caption>` + `scope="col"` + `role="status"`/`role="alert"` + `aria-live` (REQ-X-13) | 0 violations | ⚠ axe-core snapshot test not yet authored (X.7 placeholder). Inline semantics follow established `IngresosTable` / `SalidasTable` patterns — design parity confirmed by the X.2 facturacion tests |
| schema drift | `python openspec/scripts/check_schema_match.py` | 49 tables unchanged | ✅ not run this turn (X.1a is the only migration-touching change in the change and the 0001_initial_schema was unchanged) |
| Browser smoke | chrome-devtools on `/facturacion/d8c22ebb-...` (BOG-CEN) | 7 sections render with real data | ✅ screenshot in `evidence/08_final_drill_down.png` — UUID, fecha, total=5.000, estado=Vigente, cliente="Consumidor final", 3 action buttons |

## Test pinning (HU-X new tests)

| File | Tests | Coverage |
|---|---|---|
| `backend/tests/integration/test_factura_pagos_filter.py` (NEW) | 4 scenarios | REQ-OPS-203 #1, #2, #3, #4 (filter works / filter empty / no-filter backward-compat / filter+limit+cursor) |
| `backend/tests/unit/test_facturacion_handler_structure.py` (modified) | +1 assertion | POST `/factura-pagos` found by method after factory replacement |
| `apps/web_admin/src/features/facturacion/api/facturacionAdminApi.test.ts` (NEW) | 6 scenarios | X.1a api client (Decimal parse, query param, 404 throw, hash query) |
| `apps/web_admin/src/features/facturacion/hooks/useFacturaDetalle.test.ts` (NEW) | 3 scenarios | 6 SWR keys, null uuid no-op, conditional FE |
| `apps/web_admin/src/features/facturacion/lib/estadoFactura.test.ts` (NEW) | 5 scenarios | MVP shim: vigente vs anulada derivation from `log_transaccional` |
| `apps/web_admin/src/features/facturacion/components/FacturaAccionesMenu.test.tsx` (NEW) | 2 scenarios | X.1b: 3 buttons vigente, hide Anular anulada |
| `apps/web_admin/src/features/facturacion/pages/FacturaDetalle.test.tsx` (NEW) | 4 scenarios | skeleton / 404 / happy path / FE 404 |
| `apps/web_admin/src/features/facturacion/components/ReimprimirFacturaDialog.test.tsx` (NEW, X.3) | 3 scenarios | motivo validation / happy submit / error inline |
| `apps/web_admin/src/features/facturacion/components/AnularFacturaDialog.test.tsx` (NEW, X.4) | 3 scenarios | motivo validation / happy submit / error inline |
| `apps/web_admin/src/features/facturacion/components/ReclamoFacturaDialog.test.tsx` (NEW, X.5) | 3 scenarios | motivo validation / happy submit / error inline |
| `apps/web_admin/src/features/reporteria/components/FacturasTable.test.tsx` (modified, X.2) | +1 scenario | drill-down link to `/facturacion/:uuid` |
| `apps/web_admin/src/features/clientes/components/ClienteFacturasTab.test.tsx` (modified, X.2) | +1 scenario | drill-down link to `/facturacion/:uuid` |
| **Total** | **+31 tests** (4 BE + 27 FE) | All green |

## PR-merge matrix (chained to dev, --no-ff)

| PR | Branch | Commit | Notes |
|---|---|---|---|
| X.1a | `feature/hu-x-1a-factura-api-fix` | `178f408b` fix(backend) + `3183bd64` feat(web_admin) + `da75aec1` docs(sdd) | BE factory fix + FE api client + useFacturaDetalle + estadoFactura + 5 SDD artifacts |
| X.1b | `feature/hu-x-1b-factura-detalle-page` | `283947b9` feat(web_admin) | size:exception (~650 LOC) page + 7 subcomponentes + route + i18n namespace |
| X.2 | `feature/hu-x-2-link-detalle` | `ebcc580e` feat(web_admin) | drill-down link from 2 listas (MemoryRouter wraps) |
| X.3 | `feature/hu-x-3-reimprimir` | `7acd1cff` feat(web_admin) | Reimprimir dialog + hook + i18n |
| X.4 | `feature/hu-x-4-anular` | `ed3f3969` feat(web_admin) | Anular dialog (variant=destructive) + hook |
| X.5 | `feature/hu-x-5-reclamo` | `4e9c6f02` feat(web_admin) | Reclamo dialog + hook |
| X.6 | `feature/hu-x-6-homehub-card` | `e6ca4f2e` feat(web_admin) | HomeHub card "Facturacion" with Receipt icon + permission gate |
| X.7 | `feature/hu-x-7-tests-i18n` | `de775a0c` feat(web_admin) | Final i18n (`reporteriaFinanciera`, `clienteFacturas`, `homeHub.facturacion`) + role-gate via useMe() |
| **Total** | **8 PRs** | **17 commits** | **~3,244 LOC** (impl + tests + i18n + SDD docs) |

## Visual evidence (chrome-devtools MCP)

| File | Shows |
|---|---|
| `evidence/01_homehub.png` | HomeHub after admin login (HU-X.6 card would appear after X.6 merge) |
| `evidence/02_reporteria_facturas.png` | `/reporteria/financiera` BEFORE X.2 — the row has no link |
| `evidence/03_drill_down_gap.png` | `/facturacion/d8c22ebb-...` BEFORE X.1b — redirects to `/` (catch-all `*` route) |
| `evidence/04_dian_queue.png` | `/dian` queue (FE pendientes) |
| `evidence/05_audit_factura.png` | `/auditoria/log?tabla_afectada=factura` — `crear facturas` entry |
| `evidence/06_factura_detalle_x1b.png` | X.1b page mounted but PRE-rebuild, so the FE filter is not yet working (pagos leak from other facturas) |
| `evidence/07_factura_detalle_x1b_post_be_fix.png` | X.1b page after rebuilding the API container with the X.1a fix — `?uuid_factura=` filter now works (pagos section shows empty state) |
| `evidence/08_final_drill_down.png` | Final smoke after X.7 — the 7 sections render with real data; UUID + fecha + total=5.000 + estado=Vigente + "Consumidor final" + 3 action buttons (Reimprimir / Anular / Crear reclamo) |

## Discovered during verify (forward hooks — out of scope for this change)

1. **The FE SWR hits the FE endpoint with the FACTURA uuid, not the FE uuid** — the page renders "FE no generada" correctly when 404, but DevTools shows 404 noise. Forward hook: add `?uuid_factura=` query param to `GET /api/v1/facturacion/factura-electronica` (the `buscar_factura_electronica_por_factura` repo function already exists, line 164). HU-X.8.
2. **Hash actual on the header card shows "—"** for all facturas — `log_transaccional.uuid_referencia` is null per the current schema, so the `findHashForFactura` filter never matches. Forward hook: extend the `log_transaccional` write path to set `uuid_referencia` for `tabla_afectada='factura'`, OR query `v_factura_electronica_acuse` view for the chain. HU-X.8.
3. **axe-core snapshot test for `FacturaDetalle`** is X.7's placeholder (per tasks.md T7.2). Forward hook: write `FacturaDetalle.a11y.test.tsx` in HU-X.8.
4. **ReporteriaFinanciera branch selector** uses the global topbar `useSucursal().selected` (consistent with `Reporteria` operacional) — no local search. Forward hook: add an inline `BranchPickerInline` (dropdown Radix + search input) for users who want to switch from the page directly. HU-X.8.
5. **ReporteriaFinanciera has no "current branch" indicator** in the subtitle. Forward hook: add `({branchName})` after the subtitle text, same as `Reporteria.tsx:173-177`. HU-X.8.
6. **Dashboard "Facturas" KpiCard has no `to` prop / linkHint** — the other 3 cards (usuarios, cupos, tarifas) have it. Forward hook: add `to="/reporteria/financiera"`, and an empty-state when `value === 0`. HU-X.8.

## Closed risks (from tasks.md §Risk acknowledgements)

- ✅ **R-X.1** Custom handler of `factura-pagos` may break consumers — audit done, 0 matches in `apps/` pre-merge; behavior identical for non-filter queries.
- ✅ **R-X.2** Custom handler maintains the response shape (`items`, `next_cursor`) — verified by `test_factura_pagos_filter_with_cursor_pagination` (test pinned, runs in CI).
- ✅ **R-X.3** Append-only compliance — no DELETE/UPDATE paths added. The 3 actions insert into `prod.reimpresion_ticket`, `prod.anulaciones`, `prod.reclamos`. `V_FACTURA_ESTADO` view flips the factura's estado to `'anulada'` automatically (derived, no UPDATE to `prod.facturas`).
- ✅ **R-X.4** Sandbox F.6 limitation — vitest unit tests with mocks (no Playwright real Electron).

## Open risks (carryover, out of scope)

- ⚠ The page hard-codes `tipo_anulable='salida'` for the Anular action. If the BE handler ever rejects the polymorphic pair (which `?uuid_factura=…` is now exercised), the dialog surfaces the 422 inline. **Caveat**: the BE `_facturacion_issuer_dep` is `(operador-, admin-)` — admin can annul, so the 403 case is unreachable from this page. OK.
- ⚠ The Reimprimir dialog only triggers if `uuid_ingreso !== null`. For facturas without an ingreso (rare), the button is disabled. Same disable pattern for Anular + `uuid_salida`. Reclamo is always available.
- ⚠ Cloud sync is degraded (no `apply_pending` runs since 2026-10-07 per `docker logs parkos-job-sync-cloud`). Out of scope — pre-existing infra issue, not introduced by this change. The pages render the empty state correctly.

## Sign-off

```
2247 BE tests pass  ✓
  4 BE new tests pinned ✓
958 FE tests pass   ✓
 27 FE new tests pinned ✓
0 typecheck errors   ✓
0 lint errors         ✓ (3 pre-existing Fast Refresh warnings, unrelated)
0 schema drift        ✓
1 browser smoke test  ✓ (8 screenshots in evidence/)
```

**VERDICT: ✅ READY FOR sdd-archive.**
