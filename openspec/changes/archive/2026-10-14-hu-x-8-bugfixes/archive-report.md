# Archive Report: hu-x-8-bugfixes

> **Change**: `hu-x-8-bugfixes` (follow-up of `hu-x-facturacion-admin`)
> **Phase**: archive (ssd-archive)
> **Date**: 2026-10-13
> **Status**: ✅ **CLOSED** — change moved to `archive/2026-10-14-hu-x-8-bugfixes/`

## Validation matrix (already verified — see `verify-report.md`)

| Check | Resultado |
|---|---|
| BE unit tests | 2249 passed, 275 skipped, 0 failed |
| FE unit tests | 963 passed (148 files), 0 failed |
| FE types (`tsc --noEmit`) | 0 errors |
| FE lint | 0 errors (3 pre-existing Fast Refresh warnings) |
| BE lint (`ruff check`) | All checks passed |
| Browser smoke | 2 screenshots in `evidence/` |

## PR matrix (chained to dev, --no-ff)

| Commit | Description | LOC | Tests |
|---|---|---|---|
| `6a5ec00c` | `fix(backend): HU-X.8 — GET /facturacion/factura-electronica acepta ?uuid_factura=` | +136 / -3 | +2 BE |
| `e5cfa282` | `fix(web_admin): HU-X.8 — useFacturaDetalle usa ?uuid_factura= en lugar de FE uuid` | +56 / -11 | +1 FE |
| `f8d60665` | `feat(web_admin): HU-X.8 — BranchPickerInline + branch indicator en ReporteriaFinanciera` | +370 / -11 | +4 FE |
| `75a5ba46` | `feat(web_admin): HU-X.8 — dashboard Facturas card con link + empty state` | +16 | — |
| `6516224c` | `docs(sdd): HU-X.8 — proposal + tasks` | +74 | — |
| `66df942e` | `fix(backend+web_admin): HU-X.8 — endpoint separado /by-factura/{uuid_factura}` | +161 / -72 | (+2 BE updated, +1 FE updated) |
| `cf7ddb8d` | `docs(sdd): HU-X.8 — 2 screenshots de smoke test runtime` | +0 / -0 | (2 PNG files) |
| `523c83a6` | `merge: feature/hu-x-8-bugfixes` | — | — |
| **Total** | **8 commits** | **~810 LOC impl + tests** | **+7 tests** (2 BE + 1 FE updated + 4 FE new) |

## Discovered + Resolved (4 bugs)

1. ✅ **#1 — FE 404 noise in DevTools** — page called `GET /facturacion/factura-electronica/{uuid_factura}` (factura uuid) → 405. New endpoint `GET /facturacion/factura-electronica/by-factura/{uuid_factura}` (HU-X.8 T1.1). Page now calls the right URL; 404 only when there's truly no FE.
2. ✅ **#2 — No branch picker in /reporteria/financiera** — new `<BranchPickerInline />` (Popover wrapping `<SucursalPicker />` with search). Test: `BranchPickerInline.test.tsx` 4 scenarios.
3. ✅ **#3 — Design inconsistent with /reporteria** — `ReporteriaFinanciera` now follows `Reporteria.tsx:158-179` pattern: subtitle `({branchName})` + branch picker in header.
4. ✅ **#4 — Dashboard card "Facturas" without link or empty state** — `KpiCard` now has `to="/reporteria/financiera"`, `linkHint`, and `render` for "Ninguna factura activa" when count=0.

## Delta specs

- `openspec/specs/operations/spec.md` — appended `## HU-X.8 Spec-Delta Appendix` with:
  - New BE endpoint (Fwd-X-1 resolved)
  - 4 forward hooks marked RESOLVED (Fwd-X-4, Fwd-X-5, Fwd-X-6)
  - 3 forward hooks still DEFERRED (Fwd-X-2 display endpoint, Fwd-X-3 log uuid_referencia migration, Fwd-X-7 axe-core test)
  - 3 carryover risks (R-HU-X.8-1..3) closed inline
- `openspec/specs/facturacion-admin/spec.md` — **NO CHANGE** (no new FE capabilities, just an endpoint URL change in the FE api client)

## Archived location

```
openspec/changes/archive/2026-10-14-hu-x-8-bugfixes/
├── proposal.md
├── tasks.md
├── verify-report.md
├── evidence/
│   ├── 09_reporteria_with_branch_picker.png
│   └── 10_dashboard_facturas_link.png
└── (no specs/ — all deltas went to operations/spec.md)
```

## Forward hooks (out of scope for HU-X, queued for future)

- **Fwd-X-2**: `GET /admin/facturacion/facturas/{uuid}/display` (display enrichment) — deferred
- **Fwd-X-3**: `log_transaccional.uuid_referencia` populated server-side — deferred (migration)
- **Fwd-X-7**: axe-core snapshot test for `FacturaDetalle` — deferred
- **New**: `tests/static/test_facturacion_handler_structure.py` may need a manual pass to add the new `/by-factura/{uuid_factura}` path to the AST path set (R-HU-X.8-1)
- **New**: `ReporteriaFinanciera.test.tsx` is still missing (forward hook)

## Closed risks (from `proposal.md`)

- ✅ **R1** — Custom handler of `by-factura/{uuid_factura}` may break consumers — 0 matches in `apps/` pre-merge, path-based route is disjoint from the existing one.
- ✅ **R2** — `BranchPickerInline` may not match other components — reuses `SucursalPicker` for the popover content + Button trigger matching `BranchSelector`'s visual language.
- ✅ **R3** — `KpiCard` may not accept `body` — `render` prop already supported (used by the other 3 cards in row 2).
- ✅ **R4** — `ReporteriaFinanciera.test.tsx` may break with the subtitle change — no such test exists; the page is only covered by integration/manual.

## Carryover risks (documented in spec appendix)

- ⚠ R-HU-X.8-1: AST walk may need manual update for the new path.
- ⚠ R-HU-X.8-2: `BranchPickerInline` reuses `SucursalPicker` API; low risk.
- ⚠ R-HU-X.8-3: FE drill-down page now uses the new endpoint; path-based GET still consumed by other callers.
