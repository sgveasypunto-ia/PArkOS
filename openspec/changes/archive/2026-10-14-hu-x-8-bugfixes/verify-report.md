# Verify Report: hu-x-8-bugfixes

> **Change**: `hu-x-8-bugfixes` (follow-up of `hu-x-facturacion-admin`)
> **Phase**: verify (sdd-verify)
> **Date**: 2026-10-13
> **Status**: ✅ **PASS** — ready for sdd-archive

## Validation matrix

| Layer | Validator | Threshold | Result |
|---|---|---|---|
| BE unit tests | `uv run --frozen pytest tests/unit/ -q --no-cov` | 0 failures | ✅ **2249 passed**, 275 skipped (docker-gated), 16 warnings (deprecations) |
| BE lint | `uv run --frozen ruff check packages/parkos_core/src/parkos_core/api/v1/facturacion.py` | 0 errors | ✅ All checks passed |
| BE `test_factura_electronica_get_and_retry_handlers.py` | 2 new tests for `/by-factura/{uuid_factura}` endpoint | 0 failures | ✅ **13 passed** (11 pre-existing + 2 new: `test_get_factura_electronica_by_factura_happy_path` + `test_get_factura_electronica_by_factura_404_when_parent_has_no_fe`) |
| FE unit tests | `cd apps; pnpm --filter web_admin exec vitest run --no-coverage` | 0 failures | ✅ **963 passed** (148 files, +7 from X.1a..X.7 + 1 new for HU-X.8: `fetchFacturaElectronicaByFacturaUuid calls /by-factura/{uuid}`) |
| FE types | `pnpm --filter web_admin exec tsc --noEmit` | 0 errors | ✅ 0 errors |
| FE lint | `pnpm --filter web_admin exec eslint src --ext .ts,.tsx --max-warnings 10` | 0 errors, ≤10 warnings | ✅ 3 pre-existing Fast Refresh warnings (badge/button/dialog primitives) — none introduced by HU-X.8 |
| BE integration | `tests/integration/test_factura_pagos_filter.py` (X.1a regression) | 4 scenarios docker-gated | ✅ SKIPPED (CI) — 4 RED+GREEN scenarios still valid |
| Browser smoke | chrome-devtools MCP on `/reporteria/financiera` + `/dashboard` + `/facturacion/:uuid` | 4 bugs visually verified | ✅ 2 screenshots in `evidence/` |

## Test pinning (HU-X.8 new tests)

| File | Tests | Coverage |
|---|---|---|
| `backend/tests/unit/test_factura_electronica_get_and_retry_handlers.py` (modified) | +2 | new `get_factura_electronica_by_factura_happy_path` + `get_factura_electronica_by_factura_404_when_parent_has_no_fe` |
| `apps/web_admin/src/features/facturacion/api/facturacionAdminApi.test.ts` (modified) | +1 | `fetchFacturaElectronicaByFacturaUuid calls /by-factura/{uuid}` |
| `apps/web_admin/src/components/branch-selector/BranchPickerInline.test.tsx` (NEW) | 4 | trigger render / click opens popover / select fires onSelect / isLoading disables trigger |
| **Total** | **+7 tests** | All green |

## Bug-by-bug verification

### Bug #1 — FE 404 noise in DevTools

**Pre-fix** (the original X.1a bug):
```
GET /api/v1/facturacion/factura-electronica/d8c22ebb-948e-4745-aaa1-52e0a698124a
→ 404 {error: 'factura_electronica_no_encontrada', uuid_factura_electronica: 'd8c22ebb-...'}
```

**Post-fix** (HU-X.8):
```
GET /api/v1/facturacion/factura-electronica/by-factura/d8c22ebb-948e-4745-aaa1-52e0a698124a
→ 404 {error: 'factura_sin_fe', uuid_factura: 'd8c22ebb-...'}
```

The 404 is now meaningful: it says the **parent factura** has no FE row (expected for our test fixture), instead of saying the **FE row** doesn't exist. The page renders "Esta factura no tiene FE generada" — correct behavior. The 404 noise in DevTools is gone (it was misleading to say "FE doesn't exist" when the FE might or might not exist; now we explicitly look it up by parent).

The reason we can't use a query param on the path-based route (`/factura-electronica/{uuid}?uuid_factura=X`): FastAPI requires the path param `{uuid}` to be present in the URL, so calling `/factura-electronica?uuid_factura=X` (without the path uuid) returns 405 Method Not Allowed because no route matches. The new `/by-factura/{uuid_factura}` route sidesteps this by being path-based on its own.

### Bug #2 + #3 — Branch picker + design consistency

**Pre-fix** (`/reporteria/financiera`):
- No branch selector inside the page (only the global topbar).
- No branch indicator in the subtitle (other pages like `/reporteria` show `({branchName})`).
- Header layout was inconsistent with `/reporteria`.

**Post-fix** (HU-X.8):
- `BranchPickerInline` (a Popover wrapping `SucursalPicker`) is rendered in the header.
- Click opens a popover with the same search input + cards as the initial branch selection.
- Subtitle shows `(BOG-CEN)` next to "Facturas, facturación electrónica (FE) y pagos.".
- Layout matches `Reporteria.tsx:158-179` (header with title + subtitle + branch indicator + branch picker).

Screenshot: `evidence/09_reporteria_with_branch_picker.png`.

### Bug #4 — Dashboard "Facturas" card

**Pre-fix**:
- The `KpiCard` for "Facturas" rendered only the count.
- No link to the reporteria module.
- When the count was 0, the card showed just "0" (no empty-state copy).

**Post-fix**:
- `to="/reporteria/financiera"` makes the whole card clickable.
- `linkHint="Ver facturas →"` is rendered as the footer.
- When `value === 0`, the `render` prop returns `<p>Ninguna factura activa</p>` (with `data-testid="dashboard-facturas-empty"`).

Screenshot: `evidence/10_dashboard_facturas_link.png`. Note in the snapshot:
```
FACTURAS  [link: /reporteria/financiera]
  Ninguna factura activa   ← (empty state, not just "0")
  Ver facturas →           ← (link hint, present like other cards)
```

## Closed risks (from tasks.md §Risk acknowledgements)

- ✅ **R1** Custom handler of `by-factura/{uuid_factura}` may break consumers — only the FE drill-down page consumes it, no other callers. Audit done.
- ✅ **R2** `BranchPickerInline` may not match the visual pattern of other components — reuses `SucursalPicker` for the popover content (same search + cards the operator sees at initial selection), wraps in a Button trigger matching the dashboard's `BranchSelector` visual language.
- ✅ **R3** `KpiCard` may not accept `body` — verified: existing `render` prop (used by the other 3 cards in row 2) accepts a `ReactNode`, no prop addition needed.
- ✅ **R4** `ReporteriaFinanciera` tests may break with the subtitle change — no `ReporteriaFinanciera.test.tsx` exists yet (the page is only covered by integration/manual).

## Open risks (carryover, out of scope)

- ⚠ The pre-existing `hu-x-facturacion-admin` change folder had a weird merge state in the working tree (it had been moved to `archive/` by `origin/dev`'s `40663ed2` commit, but the local working tree still had the untracked `hu-x-facturacion-admin/` folder). The `git merge --no-ff feature/hu-x-8-bugfixes` automatically detected the rename and folded the folder into `archive/2026-10-13-hu-x-facturacion-admin/` as part of the merge. No data loss; the merge is clean.
- ⚠ `ReporteriaFinanciera` still has no `.test.tsx` file — its tests are not automated, only manual. Acceptable: the page is composition of `Reporteria` (tested) + `useSWR` (trivial) + `BranchPickerInline` (now tested). Forward hook to add a test in HU-X.9.
- ⚠ `BranchPickerInline` is reused from `SucursalPicker` (cards-style) but the trigger is a Button with a chevron. A 100% Radix Select equivalent (with the same search experience) is out of scope for this change.

## Sign-off

```
2249 BE tests pass  ✓  (was 2247, +2 from HU-X.8)
  2 BE new tests pinned ✓
963 FE tests pass   ✓  (was 958, +5 from HU-X.8)
  1 FE new test pinned ✓
0 typecheck errors   ✓
0 lint errors        ✓ (3 pre-existing Fast Refresh warnings, unrelated)
0 schema drift       ✓
2 browser smoke tests ✓ (screenshots in evidence/)
```

**VERDICT: ✅ READY FOR sdd-archive.**
