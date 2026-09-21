# Archive Report — HU-F11.1 (SyncBanner)

> SDD closure document for the sdd-archive phase of HU-F11.1.
> Format follows the F10.1 / F10.2 / F10.3 archive-report precedent (Fase 10 closure marker at Engram #1916).

## 1. Change summary

| Field | Value |
|---|---|
| Change | `fase-11-1-sync-banner` |
| HU | HU-F11.1 (CU-07 vista del operador — banner de sincronización) |
| Phase | Fase 11 — Operational telemetry and alerts (1 of 2) |
| Archive date | 2026-09-21 |
| Archived to | `openspec/changes/archive/2026-09-21-fase-11-1-sync-banner/` |
| Author | `Parkos Dev <dev@parkos.local>` (zero `Co-authored-by` trailers) |
| Final state on `dev` | merge SHA `4021d3d` |
| Verdict | **PASS** — 0 CRITICAL, 0 WARNING, 2 SUGGESTION (spec-delta follow-ups; non-blocking) |

## 2. Spec delta synced

REQ-OPS-170..176 (7 ADDED requirements) merged into `openspec/specs/operations/spec.md` after REQ-OPS-169. The file grew from 7,267 to 7,441 lines (+174 lines = 1 blank separator + 173 F11.1 delta lines). Mechanical append via PowerShell `Add-Content` with `-Encoding UTF8` (the established F10.3 precedent for the CRLF-base + LF-delta boundary).

| REQ | Title | Status |
|---|---|---|
| REQ-OPS-170 | `useSyncEstado` Zod schema matches BE `SyncEstadoRead` (DA-F11.1-7 GATING) | ✅ synced |
| REQ-OPS-171 | `<SyncBanner />` top-of-page color strip with derived state | ✅ synced |
| REQ-OPS-172 | `<LocalApiDownBanner />` separate component on 3 consecutive failures | ✅ synced |
| REQ-OPS-173 | `apiStatusStore` Zustand store with `consecutiveFailures` counter | ✅ synced |
| REQ-OPS-174 | Global mount in `App.tsx` | ✅ synced |
| REQ-OPS-175 | `e2e/sync-banner.spec.ts` with 4 scenarios + axe-core | ✅ synced |
| REQ-OPS-176 | RED tests for `useSyncEstado` + `SyncStatusStrip` close the untested-substrate gap (DA-F11.1-8) | ✅ synced |

Drift table (8/8 RESOLVED) + validation matrix + risk acknowledgements (R-RES-1..4) + forward hooks (F11.2, F12.x, WebSocket migration) all synced verbatim.

## 3. Operational incident — mechanical-copy error during archive move

> **CRITICAL — read this before relying on the archived files for traceability.**

### Timeline

1. `git mv openspec/changes/fase-11-1-sync-banner openspec/changes/archive/2026-09-21-fase-11-1-sync-banner` succeeded for the only TRACKED file (`apply-progress.md` — the `R  apply-progress.md -> apply-progress.md` rename shows in `git status`).
2. The other 6 files (proposal.md, design.md, tasks.md, verify-report.md, specs/spec.md, apply-progress.md itself) were **untracked** — they only existed on disk.
3. The archive move script created a recursive snapshot of the source folder (now empty after the `git mv`), then attempted to mirror it into the destination via `robocopy /MIR`.
4. Because the source snapshot was empty, `robocopy /MIR` interpreted the destination as "extra files" and **DELETED the apply-progress.md** that `git mv` had just placed there. The remaining untracked files were also already gone (they never made it into the snapshot because they weren't on disk at the moment the snapshot was taken — the source was empty by then).
5. Recovery:
   - `apply-progress.md` was restored from the git index via `git checkout-index --force -- openspec/changes/archive/2026-09-21-fase-11-1-sync-banner/apply-progress.md` (12,952 bytes, byte-identical to the merge SHA `4021d3d` content).
   - `specs/spec.md` was reconstructed verbatim from the in-session Read content (the orchestrator had read the full 173-line file in this session).
   - `proposal.md`, `design.md`, `tasks.md`, `verify-report.md` were reconstructed from the orchestrator's launch prompt + Engram observation #1925 (`sdd/fase-11-1-sync-banner/verify-report`) + the actual commit SHAs in `git log`. These files are NOT byte-identical to the originals but preserve the substantive content.

### Root cause

The sdd-archive skill's mechanical-copy contract mandates a snapshot of the source folder BEFORE the move. In this case the source was already partially emptied by `git mv`, so the snapshot was of an empty folder, and `robocopy /MIR` then cleaned up the destination. The contract's `diff -r` verification step then had nothing to compare against — the `diff -r` returned "no differences" because both sides were empty.

### Mitigation (forward hook)

For future sdd-archive runs on changes that mix tracked + untracked files, the snapshot must be taken BEFORE `git mv`, not after. The correct ordering:

```bash
# 1. Snapshot FIRST (before any move)
snapshot_root="$(mktemp -d "${TMPDIR:-/tmp}/sdd-archive.XXXXXX")"
cp -R "openspec/changes/{change-name}" "$snapshot_root/source"

# 2. git mv (only the tracked files move)
git mv "openspec/changes/{change-name}" "openspec/changes/archive/{date}-{change-name}"

# 3. Filesystem cp the untracked files (NOT robocopy /MIR which is destructive)
cp -R "$snapshot_root/source/." "openspec/changes/archive/{date}-{change-name}/"

# 4. Remove the now-empty source
rmdir "openspec/changes/{change-name}"

# 5. diff -r verification
diff -r "$snapshot_root/source" "openspec/changes/archive/{date}-{change-name}"
```

This is recorded as a hardening follow-up for the sdd-archive skill itself (R-ARCH-1 in `pending-fase-11.md`).

## 4. Apply progress — final SHAs

| Commit | SHA | Subject |
|---|---|---|
| C1 (T1) | `da80675` | test(sync-banner): RED scaffold for useSyncEstado + apiStatusStore |
| C2 (T2) | `6f41509` | feat(caja-banner): GREEN apiStatusStore + Zod schema |
| C3 (T3) | `6c71a32` | test(sync-banner): RED tests for SyncBanner + LocalApiDownBanner |
| C4 (T4) | `95dad3a` | feat(caja-banner): GREEN SyncBanner + LocalApiDownBanner |
| C5 (T5) | `1639b7b` | feat(caja-banner): mount sync banners above StatusBar + rewire |
| C6 (T6) | `1a3a2a3` | docs(sdd): F11.1 apply-progress final SHA + drift anchor closure |
| fixup | `46e283c` | fix(sync): correct SyncStatusStrip test import path |
| merge | `4021d3d` | merge: feature/hu-f11-1-sync-banner → dev |

**Total delta vs `dev`**: +1,365/-53 = **+1,312 net LOC** (under 2,000 meta-budget per commit `cee0784` ratified 2026-09-21). **No `size:exception` required.**

## 5. Verify-report findings

- 12/12 scenarios COMPLIANT
- 8/8 drift anchors RESOLVED (DA-F11.1-7 GATING closed)
- 21/21 unit tests GREEN on F11.1 files
- Full suite regression baseline unchanged from F10.3 (11 failures / 17 failing tests, all pre-existing)
- e2e suite fully written with NO `test.skip` per AD-6 (CI-bound)
- 0 CRITICAL, 0 WARNING, 2 SUGGESTION

Both SUGGESTIONs carried into `pending-fase-11.md` as spec-delta follow-ups:

1. **R-CARRY-1** — REQ-OPS-171 thresholds drift: spec prose has `300/3600/100` while ratified D2 impl uses `60/3600/5/100`. Non-blocking; spec delta to reconcile.
2. **REQ-OPS-173 letter** — selector shape: spec says `online: boolean` field; impl derives via `selectApiStatusDown(state) === false`. Functionally equivalent; spec delta to reconcile the letter.

## 6. Branch cleanup

- `feature/hu-f11-1-sync-banner` — local: present (delete after housekeeping commit lands); remote: tracked (orchestrator will close via GitHub after `dev` reaches the merge)
- No fix branches
- No stashed work related to F11.1

## 7. Final state on `dev`

- HEAD: `4021d3d` (merge of `feature/hu-f11-1-sync-banner` into `dev`)
- Files: `apps/electron-sucursal/src/{state/apiStatusStore.ts, components/{SyncBanner,LocalApiDownBanner}.tsx, features/sync/{hooks/useSyncEstado.ts, components/SyncStatusStrip.tsx}, renderer/{App.tsx, components/StatusBar.tsx, i18n/locales/sync.json}}`; `apps/electron-sucursal/e2e/sync-banner.spec.ts`
- Tests: 21 focused unit + 4 e2e + axe-core
- Spec: `openspec/specs/operations/spec.md` lines 7267-7441 (Phase 11 / F11.1 section)
- Size: +1,312 net LOC under 2,000 meta-budget

## 8. F11.1 HAND-OFF to F11.2 (AlertasPanel)

### Substrate ready for F11.2 (carries from F11.1)

- `apps/electron-sucursal/src/state/apiStatusStore.ts` — exposes `consecutiveFailures`, `lastFailureIso`, `isMounted`, `incrementFailure()`, `reset()`, `selectApiStatusDown()`. F11.2 MAY consume this to suppress alert rendering while `consecutiveFailures >= 3` (per F11.1 REQ-OPS-173 forward hook).
- `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts` — SWR with `refreshInterval: 30_000`. F11.2 alerts panel MAY use the same SWR polling pattern.
- `apps/electron-sucursal/src/renderer/App.tsx` — banner mount pattern. F11.2 alerts panel MAY mount adjacent to `<SyncBanner />`.
- `openspec/specs/operations/spec.md` — REQ-OPS-170..176 baseline for F11.2's REQ-OPS-177+ additions.

### Artifacts to create fresh for F11.2

- `openspec/changes/fase-11-2-alertas-panel/proposal.md`
- `openspec/changes/fase-11-2-alertas-panel/specs/spec.md`
- `openspec/changes/fase-11-2-alertas-panel/design.md`
- `openspec/changes/fase-11-2-alertas-panel/tasks.md`
- `openspec/changes/fase-11-2-alertas-banner/verify-report.md`
- `openspec/changes/fase-11-2-alertas-panel/apply-progress.md`
- (later) `openspec/changes/archive/2026-MM-DD-fase-11-2-alertas-panel/`

### Next free spec gap

REQ-OPS-177 onwards (next free number after REQ-OPS-176).

### F11.2 expected content (per plan.md + ABIERTO-06)

- 11 business alerts visible (`sync_state`, `capacity`, `pricing`, `subscription`, etc.)
- 8 technical alerts hidden from UI but logged (sync infrastructure: `hash_chain_anomaly`, `dian_rechazada`, etc.)
- DEC-SUC-25 append-only "marcar revisada" pattern (no UPDATE/DELETE on `alerta`)
- Mount next to `<SyncBanner />` in `App.tsx`
- Spec number range: REQ-OPS-177..~190

## 9. Recommended next cycle

**F11.2 (AlertasPanel)**: launch `sdd-propose` with `change=fase-11-2-alertas-panel`. Reuse `apiStatusStore` from F11.1 (shared substrate) + the `useSyncEstado` SWR polling pattern. New change folder: `openspec/changes/fase-11-2-alertas-panel/`. Spec delta continues at REQ-OPS-177.

## 10. Engram observation

This closure is persisted as `sdd/fase-11-1-sync-banner/archive-report` (Engram topic_key). See Engram observation for the machine-readable closure marker.

**F11.1 closure marker**: F11.1 closed — REQ-OPS-170..176 landed in spec; meta-budget 2000 holds; 2 spec-delta follow-ups (R-CARRY-1 thresholds + REQ-OPS-173 selector); operational incident §3 (mechanical-copy error) recorded for future hardening.