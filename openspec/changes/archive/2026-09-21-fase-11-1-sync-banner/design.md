# Archived Design: HU-F11.1 Sync Banner

> **RECONSTRUCTED 2026-09-21 during sdd-archive phase** (see archive-report.md §3). Original was untracked and lost during the mechanical-copy step. Substantive content matches what landed at merge SHA `4021d3d`.

## Architecture decisions (6)

| # | Decision | Rationale |
|---|---|---|
| **AD-1** | Separate `<LocalApiDownBanner />` (not a variant of `<SyncBanner />`) | DA-F11.1-6 HIGH — distinct role (`alert` vs `status`), distinct aria-live (`assertive` vs `polite`), distinct copy, distinct i18n keys. Component composition > conditional rendering inside one component. |
| **AD-2** | `apiStatusStore` exposed as the single source of truth for API health | DA-F11.1-2 MED — StatusBar must consume the same counter; dual read drifts. Counter + threshold constant colocated in the store module. |
| **AD-3** | `SyncEstadoSchema` aligned to BE `SyncEstadoRead` 4 fields only (no `estado`, no `ultimo_error`, no `ultima_sync`) | DA-F11.1-7 HIGH GATING — FE is wrong on 4 axes. Strict Zod parse with explicit field list prevents drift back. |
| **AD-4** | Verbatim F2.3 `StatusBar.tsx` L90-100 pattern for announce-on-transition (lastAnnouncedState ref + 2 s debounce) | DA-F11.1-4 LOW — established pattern, no aria-live spam. lastAnnouncedState is a STATE not a REF so DOM reflects announced value on same render frame. |
| **AD-5** | `page.clock.install({time:0}) + page.clock.fastForward(30_000)` for SWR poll tests | DA-F11.1-5 MED — Playwright 1.45+ API; test runs deterministically without real 30s wait. NO `test.skip` allowed (strict_tdd). |
| **AD-6** | Strict-TDD with RED tests landing BEFORE any source change in T1 | DA-F11.1-8 MED — 3 test files (useSyncEstado, SyncStatusStrip, apiStatusStore) are the source-of-truth; existing substrate edited to satisfy them. |

## File changes (13)

### Created
1. `apps/electron-sucursal/src/state/apiStatusStore.ts` (NEW)
2. `apps/electron-sucursal/src/components/SyncBanner.tsx` (NEW)
3. `apps/electron-sucursal/src/components/LocalApiDownBanner.tsx` (NEW)
4. `apps/electron-sucursal/src/renderer/i18n/locales/sync.json` (NEW — `syncBanner.*` + `localApiDownBanner.*` keys)
5. `apps/electron-sucursal/e2e/sync-banner.spec.ts` (NEW — 4 scenarios + axe-core)

### Created (tests)
7. `apps/electron-sucursal/src/state/apiStatusStore.test.ts` (RED then GREEN)
8. `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.test.ts` (RED then GREEN)
9. `apps/electron-sucursal/src/features/sync/components/SyncStatusStrip.test.tsx` (RED then GREEN)

### Modified
10. `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts` — Zod schema swap (REQ-OPS-170)
11. `apps/electron-sucursal/src/features/sync/components/SyncStatusStrip.tsx` — color mapping + announce-on-transition (REQ-OPS-171)
12. `apps/electron-sucursal/src/renderer/App.tsx` — mount `<SyncBanner />` + `<LocalApiDownBanner />` adjacent to `<StatusBar />` (REQ-OPS-174)
13. `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` — rewire to `apiStatusStore` (REQ-OPS-173 + DA-F11.1-2)

## Test plan

| Layer | Test type | Files |
|---|---|---|
| Unit | vitest + vi.useFakeTimers | 3 test files (21 focused tests) |
| E2E | playwright + page.clock + axe-core | 1 spec (4 scenarios + WCAG gate) |

## Forecast

~1,110 LOC across 13 files. Actual: +1,312 net LOC under 2,000 meta-budget.

---

## Recovery context

This reconstructed design was created during sdd-archive to preserve the archive structure after the original file was lost during a destructive mechanical-copy operation. The 6 ADs and 13 file changes match what landed at merge SHA `4021d3d`; the wording is paraphrased from the launch prompt because the original was untracked and only existed on disk.