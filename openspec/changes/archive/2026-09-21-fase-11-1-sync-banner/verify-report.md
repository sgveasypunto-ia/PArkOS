# Archived Verify Report: HU-F11.1 Sync Banner

> **RECONSTRUCTED 2026-09-21 during sdd-archive phase** (see archive-report.md §3). Original was untracked and lost during the mechanical-copy step. The verdict, scenarios, drift anchors, and carry-overs below match what landed at merge SHA `4021d3d` and are mirrored in Engram observation #1925 (`sdd/fase-11-1-sync-banner/verify-report`, 2026-09-21 11:33:01).

## Verdict

**PASS** — 0 CRITICAL, 0 WARNING, 2 SUGGESTION (both spec-delta follow-ups; no regressions).

## Scenarios (12/12 COMPLIANT)

| Scenario | REQ | Status |
|---|---|---|
| Parses real backend response shape | REQ-OPS-170 | COMPLIANT |
| Accepts never-synced branch (`ultima_sync_at IS NULL`) | REQ-OPS-170 | COMPLIANT |
| Rejects `lag_seg < 0` (Pydantic `int \| None` guard) | REQ-OPS-170 | COMPLIANT |
| Green for in-window sync | REQ-OPS-171 | COMPLIANT |
| Distinct badge for never-synced branch | REQ-OPS-171 | COMPLIANT |
| Renders after 3 consecutive failures | REQ-OPS-172 | COMPLIANT |
| Hides after one success | REQ-OPS-172 | COMPLIANT |
| Counter increments on failure | REQ-OPS-173 | COMPLIANT |
| Counter resets on success | REQ-OPS-173 | COMPLIANT |
| Both banners present on `/caja/abrir-turno` | REQ-OPS-174 | COMPLIANT |
| Yellow state without API failures | REQ-OPS-175 | COMPLIANT |
| All three test files exist and pass | REQ-OPS-176 | COMPLIANT |

## Drift anchors (8/8 RESOLVED)

| Anchor | Severity | Status |
|---|---|---|
| DA-F11.1-1 (StatusBar overlap) | HIGH | RESOLVED (REQ-OPS-172 distinct component) |
| DA-F11.1-2 (dual read) | MED | RESOLVED (REQ-OPS-173 StatusBar rewire) |
| DA-F11.1-3 (threshold storage) | MED | RESOLVED (REQ-OPS-173 LOCAL_API_DOWN_THRESHOLD = 3) |
| DA-F11.1-4 (aria-live spam) | LOW | RESOLVED (REQ-OPS-171 F2.3 verbatim pattern) |
| DA-F11.1-5 (30s poll test) | MED | RESOLVED (REQ-OPS-175 page.clock + fastForward) |
| DA-F11.1-6 (distinct banners) | HIGH | RESOLVED (REQ-OPS-171 + REQ-OPS-172) |
| DA-F11.1-7 (FE schema drift) | HIGH GATING | RESOLVED (REQ-OPS-170 SyncEstadoSchema aligned) |
| DA-F11.1-8 (untested substrate) | MED | RESOLVED (REQ-OPS-176 RED tests first) |

## Unit tests (21/21 GREEN on F11.1 files)

| File | Tests | Status |
|---|---|---|
| `apiStatusStore.test.ts` | 4 | GREEN |
| `useSyncEstado.test.ts` | 4 | GREEN |
| `SyncStatusStrip.test.tsx` | 1 | GREEN |
| `SyncBanner.test.tsx` | 6 | GREEN |
| `LocalApiDownBanner.test.tsx` | 6 | GREEN |

Full suite regression baseline unchanged from F10.3 (11 failures / 17 failing tests, all pre-existing baseline carries: StatusBar.tsx rules-of-hooks from F2.3, StatusBar.test.tsx L14 "bridge not in include", 48 lint errors / 11 test failures / docs/*.png untracked). All out of scope per session instruction.

## e2e suite (4 scenarios + axe-core, NO test.skip)

| Scenario | Status |
|---|---|
| (a) verde — `lag_seg` bajo, sync dentro ultima hora | written, CI-bound |
| (b) amarillo — `lag_seg` por encima del umbral, sin fallos consecutivos | written, CI-bound |
| (c) rojo — sync fallida o `lag_seg > 3600` OR `consecutiveFailures >= 3` | written, CI-bound |
| (d) LocalApiDownBanner — `consecutiveFailures === 3`, banner visible con copy distinto | written, CI-bound |
| axe-core WCAG 2.1 AA gate (RNF-022) | written, CI-bound |

Per AD-6 (strict_tdd), NO `test.skip` allowed. Uses `page.clock.install({time:0}) + page.clock.fastForward(30_000)` per DA-F11.1-5.

## Findings

### 0 CRITICAL
### 0 WARNING
### 2 SUGGESTION (both spec-delta follow-ups; non-blocking)

1. **R-CARRY-1 — REQ-OPS-171 thresholds drift**: spec prose says `lag_seg < 300` (online) / `300 <= lag_seg < 3600` (lagging) / `lag_seg >= 3600` (offline) / `pendientes < 100` (online) / `1 <= pendientes < 100` (lagging) / `pendientes >= 100` (offline). The ratified D2 thresholds in the implementation are `60 / 3600 / 5 / 100` (i.e., online=60s, lagging=5 pending, offline=3600s/100 pending). Spec REQ-OPS-171 numbers are the wrong way around: the spec has `300` where D2 says `60` for `online`, and `100` where D2 says `5` for `lagging`. Carries to pending-fase-11.md as spec-delta follow-up.
2. **REQ-OPS-173 letter — selector**: spec prose says `apiStatusStore` MUST expose `{ online: boolean, consecutiveFailures, lastFailureIso }`. Implementation exposes `consecutiveFailures` + `lastFailureIso` + `isMounted` and derives `online` via the selector `selectApiStatusDown(state) === false`. Functionally equivalent (down = `consecutiveFailures >= 3`); spec delta to reconcile the letter.

Both are non-blocking and tracked in `pending-fase-11.md` for a future spec-delta.

## Pre-existing baseline carries (out of scope per session instruction)

- `StatusBar.tsx` rules-of-hooks violation from F2.3
- `StatusBar.test.tsx` L14 "bridge not in include"
- 48 lint errors in `apps/electron-sucursal/src/` (residue)
- 11 test failures / 17 failing tests in the full suite (pre-existing, not F11.1-introduced)
- `docs/*.png` untracked working-tree artifacts
- `.git/rebase-merge/` leftover from F10.1 prior session

## Verdict summary

**PASS** — F11.1 closes on `dev` at merge SHA `4021d3d`. REQ-OPS-170..176 are all compliant; the 8 drift anchors are resolved (DA-F11.1-7 GATING closed). +1,312 net LOC under 2,000 meta-budget; no `size:exception` required. The 2 SUGGESTION-level follow-ups (R-CARRY-1 thresholds + REQ-OPS-173 letter) carry to `pending-fase-11.md` as spec-delta items.

---

## Recovery context

This reconstructed verify-report was created during sdd-archive to preserve the archive structure after the original file was lost during a destructive mechanical-copy operation. The verdict, scenarios, drift anchors, unit/e2e counts, and the 2 SUGGESTION findings match what is recorded in Engram observation #1925 (`sdd/fase-11-1-sync-banner/verify-report`).