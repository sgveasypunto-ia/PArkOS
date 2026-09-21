# Archived Tasks: HU-F11.1 Sync Banner

> **RECONSTRUCTED 2026-09-21 during sdd-archive phase** (see archive-report.md §3). Original was untracked and lost during the mechanical-copy step. The 6 commits below match the actual SHAs in the git log of `dev` at the time of archive (merge SHA `4021d3d`).

## Commits (6 atomic + 1 fixup + 1 merge)

| # | SHA | Subject | Tests added | LOC |
|---|---|---|---|---|
| **C1** | `da80675` | test(sync-banner): RED scaffold for useSyncEstado + apiStatusStore (T1) | 8 RED | +243/-52 |
| **C2** | `6f41509` | feat(caja-banner): GREEN apiStatusStore + Zod schema (T2) | 8 GREEN | +187/-98 |
| **C3** | `6c71a32` | test(sync-banner): RED tests for SyncBanner + LocalApiDownBanner (T3) | 6 RED | +192/-0 |
| **C4** | `95dad3a` | feat(caja-banner): GREEN SyncBanner + LocalApiDownBanner (T4) | 6 GREEN | +243/-0 |
| **C5** | `1639b7b` | feat(caja-banner): mount sync banners above StatusBar + rewire (T5) | — | +187/-3 |
| **C6** | `1a3a2a3` | docs(sdd): F11.1 apply-progress final SHA + drift anchor closure (T6) | — | +313/-0 |
| **fixup** | `46e283c` | fix(sync): correct SyncStatusStrip test import path | — | +1/-1 |
| **merge** | `4021d3d` | merge: feature/hu-f11-1-sync-banner → dev | — | — |

**Total delta vs `dev`**: +1,365/-53 = **+1,312 net LOC** (under 2,000 meta-budget).

## Task list (from original tasks.md — reconstructed)

- [x] **T1** (C1) — RED: scaffold tests for `useSyncEstado` Zod parse + `apiStatusStore` counter; freeze the contract from BE `SyncEstadoRead`
- [x] **T2** (C2) — GREEN: implement `apiStatusStore` Zustand store with `LOCAL_API_DOWN_THRESHOLD = 3` constant + swap `useSyncEstado` Zod schema
- [x] **T3** (C3) — RED: tests for `<SyncBanner />` color states + announce-on-transition + `<LocalApiDownBanner />` 3-strike mount/unmount
- [x] **T4** (C4) — GREEN: implement `<SyncBanner />` (CVA color strip + announce debounce) + `<LocalApiDownBanner />` (role=alert + distinct copy + distinct i18n keys)
- [x] **T5** (C5) — mount both banners in `App.tsx` adjacent to `<StatusBar />` + rewire `<StatusBar />` to `apiStatusStore` + add `sync.json` locale
- [x] **T6** (C6) — write Playwright `e2e/sync-banner.spec.ts` with 4 scenarios (verde / amarillo / rojo / LocalApiDown) + axe-core gate + finalize `apply-progress.md`
- [x] **fixup** — correct `SyncStatusStrip.test.tsx` import path
- [x] **merge** — merge `feature/hu-f11-1-sync-banner` → `dev` (merge SHA `4021d3d`)

## Drift resolution (per edge)

| Anchor | Resolved in |
|---|---|
| DA-F11.1-1 (HIGH — StatusBar overlap) | C4 (REQ-OPS-172 separate component) |
| DA-F11.1-2 (MED — dual read) | C5 (StatusBar rewire) |
| DA-F11.1-3 (MED — threshold storage) | C2 (LOCAL_API_DOWN_THRESHOLD constant) |
| DA-F11.1-4 (LOW — aria-live spam) | C4 (F2.3 verbatim pattern) |
| DA-F11.1-5 (MED — 30 s poll test) | C6 (page.clock.install + fastForward) |
| DA-F11.1-6 (HIGH — distinct banners) | C4 (2 separate components) |
| DA-F11.1-7 (HIGH GATING — schema drift) | C2 (Zod schema swap) |
| DA-F11.1-8 (MED — untested substrate) | C1 + C3 (RED tests first) |

## Verification results (per verify-report.md)

- 12/12 scenarios COMPLIANT
- 8/8 drift anchors RESOLVED
- 21/21 unit tests GREEN on F11.1 files (apiStatusStore 4 + useSyncEstado 4 + SyncStatusStrip 1 + SyncBanner 6 + LocalApiDownBanner 6)
- Full suite regression baseline unchanged from F10.3 (11 failures / 17 failing tests, all pre-existing)
- e2e suite fully written with NO `test.skip` per AD-6 (CI-bound)
- DA-F11.1-7 GATING closed: SyncEstadoSchema aligned to 4 BE fields
- 0 CRITICAL, 0 WARNING, 2 SUGGESTION (R-CARRY-1 thresholds drift + REQ-OPS-173 letter selector)

---

## Recovery context

This reconstructed tasks.md was created during sdd-archive to preserve the archive structure after the original file was lost during a destructive mechanical-copy operation. The 6 commits + 1 fixup + 1 merge match the actual SHAs in git; the 6 task entries match the implementation sequence in apply-progress.md (also preserved).