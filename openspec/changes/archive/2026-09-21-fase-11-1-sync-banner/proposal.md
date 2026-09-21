# Archived Proposal: HU-F11.1 Sync Banner

> **RECONSTRUCTED 2026-09-21 during sdd-archive phase**: this file was inadvertently destroyed during the mechanical-copy step of `sdd-archive`. The substantive proposal content is preserved in Engram observation #1925 (F11.1 verify-report PASS — captured the full Drift Anchor resolutions) and in the persisted diff against `dev` at merge SHA `4021d3d`. The proposal below is reconstructed from the orchestrator's launch prompt metadata + Engram observations; it is not byte-identical to the original but preserves the intent.

## Proposal summary (HU-F11.1 SyncBanner)

| Field | Value |
|---|---|
| Change | `fase-11-1-sync-banner` |
| Phase | Fase 11 — Operational telemetry and alerts (HU-F11.1 of 2) |
| CU | CU-07 (vista del operador) |
| Base spec | `openspec/specs/operations/spec.md` |
| Gap | Substrate (`useSyncEstado` + `SyncStatusStrip`) ships untested (DA-F11.1-8); FE schema drift vs BE `SyncEstadoRead` (DA-F11.1-7 GATING). |
| Status | DELTA — 7 ADDED requirements (REQ-OPS-170..176). |
| Drift anchors | 8 (DA-F11.1-1..8); all RESOLVED. |
| Author | Parkos Dev <dev@parkos.local> |

## Intent

Close two HIGH-priority drift anchors on the FE sync telemetry substrate: (a) the schema mismatch between the FE Zod schema for `GET /sync/estado` and the BE `SyncEstadoRead` response, and (b) the fact that `useSyncEstado` + `SyncStatusStrip` ship with zero tests. Land strict-TDD red tests first, then implementation, then axe-core WCAG 2.1 AA verification.

## Scope

### IN scope
- `apps/electron-sucursal/src/state/apiStatusStore.ts` (NEW — Zustand store with `consecutiveFailures` counter)
- `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts` (MODIFIED — Zod schema aligned to BE `SyncEstadoRead`)
- `apps/electron-sucursal/src/features/sync/components/SyncStatusStrip.tsx` (MODIFIED — color mapping + announce-on-transition)
- `apps/electron-sucursal/src/components/SyncBanner.tsx` (NEW — top-of-page color strip)
- `apps/electron-sucursal/src/components/LocalApiDownBanner.tsx` (NEW — separate component on 3 consecutive failures)
- `apps/electron-sucursal/src/renderer/App.tsx` (MODIFIED — mount banners above StatusBar)
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (MODIFIED — rewire to apiStatusStore)
- `apps/electron-sucursal/src/renderer/i18n/locales/sync.json` (NEW — distinct keys for SyncBanner + LocalApiDownBanner)
- `apps/electron-sucursal/e2e/sync-banner.spec.ts` (NEW — Playwright 4 scenarios + axe-core)
- 3 vitest unit test files: `useSyncEstado.test.ts`, `SyncStatusStrip.test.tsx`, `apiStatusStore.test.ts`

### OUT of scope (deferred)
- F11.2 AlertasPanel — separate SDD cycle
- BE schema changes — none required (FE is wrong on 4 axes; F11.1 fixes FE only)
- F12.x observability / Prometheus export

## Approach

Strict TDD: RED tests land in T1 of apply, then GREEN implementation. The Zod schema is aligned to BE `SyncEstadoRead` first (DA-F11.1-7 GATING), then `apiStatusStore` is built (REQ-OPS-173), then `<SyncBanner />` (REQ-OPS-171) and `<LocalApiDownBanner />` (REQ-OPS-172) consume both. StatusBar re-routing through the store is the final in-PR step (REQ-OPS-173 + DA-F11.1-2). Playwright e2e uses `page.clock.install + fastForward(30_000)` per DA-F11.1-5 — NO `test.skip` allowed.

## Drift anchors (8 RESOLVED — full table in `specs/spec.md`)

| Anchor | Severity | Resolution |
|---|---|---|
| DA-F11.1-1 | HIGH | Distinct banner copy + role + aria-label (REQ-OPS-172) |
| DA-F11.1-2 | MED | StatusBar → apiStatusStore single source (REQ-OPS-173) |
| DA-F11.1-3 | MED | Explicit `LOCAL_API_DOWN_THRESHOLD = 3` constant (REQ-OPS-173) |
| DA-F11.1-4 | LOW | F2.3 StatusBar.tsx L90-100 pattern verbatim (REQ-OPS-171) |
| DA-F11.1-5 | MED | `page.clock.install + fastForward` (REQ-OPS-175) |
| DA-F11.1-6 | HIGH | 2 SEPARATE components (REQ-OPS-171 + REQ-OPS-172) |
| DA-F11.1-7 | HIGH GATING | SyncEstadoSchema aligned to BE (REQ-OPS-170) |
| DA-F11.1-8 | MED | RED tests land before source (REQ-OPS-176) |

## Forecast

~1,110 LOC across 13 files. Under 2,000 LOC meta-budget (Fase 11+ ratificado 2026-09-21). Actual: +1,312 net LOC, +1,365/-53. 7 atomic commits + 1 merge.

## Author override

Every commit authored as `Parkos Dev <dev@parkos.local>`. Zero `Co-authored-by` trailers (per AGENTS.md canon).

---

## Recovery context

This reconstructed proposal was created during sdd-archive to preserve the archive structure after the original file was lost during a destructive mechanical-copy operation. The substantive content matches what the merge SHA `4021d3d` delivered; the wording is paraphrased from the launch prompt + Engram #1925 because the original was untracked and only existed on disk.