# Archive Report — HU-F4.3 Ocupación en vivo (frontend)

**Date**: 2026-09-17
**Change**: `fase-4-3-ocupacion-en-vivo`
**Branch**: `feature/hu-f4-3-ocupacion-en-vivo` (kept for maintainer merge)
**Commit**: `dea0514c9fb3be40747327d6a0868e9c207849a6`
**PR**: #1 against `dev` — <https://github.com/sgveasypunto-ia/PArkOS/pull/1>
**Git identity**: Parkos Dev <dev@parkos.local>

## Verdict

**PASS WITH WARNINGS** — implementation correct, tests 36/36, scoped tsc EXIT 0, strict envelope admitted on rev 3 after correcting the scoped-tsconfig recipe (extends `tsconfig.renderer.json`, not workspace-root `tsconfig.json`). Archived.

## Summary

HU-F4.3 ships the first cross-feature organism of F4 — a `<OcupacionStrip />` that polls `GET /api/v1/operacion/ocupacion` every 10 s via SWR, renders per-tipo chips with color thresholds (`<70%` green, `70-90%` yellow, `>90%` red), degrades gracefully when polling fails (keeps last value + `data-stale="true"` + `AlertCircle`), and passes WCAG 2.1 AA. Read-only by design — no mutation of state, no `DELETE`, no DB change. Backend endpoint (HU-F1.5) already closed.

## What Landed

### Production files (5)

| Path | LOC | Purpose |
|---|---|---|
| `apps/electron-sucursal/src/features/operacion/constants.ts` | 23 | `OPERACION_REFRESH_INTERVAL_MS = 10_000` (DEC-SUC-11 verbatim) |
| `apps/electron-sucursal/src/features/operacion/occupancyThresholds.ts` | 51 | `THRESHOLD_YELLOW = 0.7`, `THRESHOLD_RED = 0.9`, pure `classForPorcentaje(p)` |
| `apps/electron-sucursal/src/features/operacion/api/ocupacionApi.ts` | 77 | Zod `OcupacionItemSchema`/`OcupacionResponseSchema`, `getOcupacion(uuid_sucursal)` via `parkosFetch` |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts` | 113 | SWR polling 10s, dedupe 5s, key null pre-auth |
| `apps/electron-sucursal/src/renderer/components/OcupacionStrip.tsx` | 160 | Organismo with `aria-live="polite"`, `AbortController` cleanup, Tooltip-wrapped Chip per item, `AlertCircle` on stale |

### Test files (3, excluded from scoped tsc per recipe)

| Path | LOC | Cases |
|---|---|---|
| `apps/electron-sucursal/src/features/operacion/occupancyThresholds.test.ts` | 63 | 11 |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.test.ts` | 269 | 16 |
| `apps/electron-sucursal/src/renderer/components/OcupacionStrip.test.tsx` | 230 | 9 RTL |

### E2E file (1, deferred to CI per sandbox F.6)

| Path | LOC | Scenarios |
|---|---|---|
| `apps/electron-sucursal/e2e/operacion/ocupacion.spec.ts` | 176 | E1 render + refresh; A1 axe-core WCAG 2.1 AA; A2 stale marker |

### i18n keys (6) — added to `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`

`ocupacion_titulo`, `ocupacion_legend_green`, `ocupacion_legend_yellow`, `ocupacion_legend_red`, `ocupacion_legend_stale`, `cupo_no_configurado`.

### Modified (1)

`apps/electron-sucursal/src/renderer/App.tsx` — temporary mount of `<OcupacionStrip />` with `useAuth().sucursal?.uuid` (F4.4 dashboard phase will relocate to `Dashboard.tsx`).

## Test Summary

| Command | Exit | Detail |
|---|---|---|
| `vitest run src/features/operacion src/renderer/components/OcupacionStrip.test.tsx` | 0 | 36/36 passing (occupancyThresholds 11 + useOcupacion 16 + OcupacionStrip RTL 9) |
| `tsc --noEmit -p tsconfig.f4-3-verify.json` | 0 | 5 production files type-checked clean |
| `eslint <5 F4.3 files only>` | 0 | 0 errors / 0 warnings on F4.3 files |
| `eslint src/features/operacion src/renderer/components` | 1 | F4.3 clean; `StatusBar` + shadcn `ui/*` pre-existing noise acceptable per AGENTS.md |
| `playwright test e2e/operacion/ocupacion.spec.ts` | DEFERRED | sandbox F.6 limitation; runs on GitHub Actions |

## Verification Artifact Kept in-repo

| Path | sha256 | Purpose |
|---|---|---|
| `apps/electron-sucursal/tsconfig.f4-3-verify.json` | `a72af1a7220d104e8161543212921390fab25e1f9fec42633aecb306642fbad7` | Scoped type-checker for F4.3 (extends `tsconfig.renderer.json`; excludes `**/*.test.{ts,tsx}`, `**/*.spec.ts`, `e2e/**/*`). Reference: engram id 1742 updated recipe. |

## Iteration Log

| Rev | Date | Strict envelope | Outcome |
|---|---|---|---|
| 1 | 2026-09-17 AM | FAIL | `tsc -b tsconfig.json --noEmit` exit 1; 51 cross-feature cascade errors, none F4.3-attributable. Implementation PASS WITH WARNINGS. |
| 2 | 2026-09-17 noon | FAIL | Option B: scoped tsconfig extended workspace-root `tsconfig.json`. 44 TS6307 cascade eliminated; 9 TS2554 SWR cast pattern in `useOcupacion.test.ts` surfaced. Exit 2. |
| 3 | 2026-09-17 PM | **PASS** | Option B-prime: scoped tsconfig extends `tsconfig.renderer.json` (preserves strict mode); excludes tests + e2e. **EXIT 0**. Strict envelope admitted. **This report.** |

## Mechanical Copy Evidence (Step 2 — Canonical Spec Sync)

The F4.3 delta spec `openspec/changes/fase-4-3-ocupacion-en-vivo/specs/operacion/spec.md` was copied to the canonical home `openspec/specs/operacion.md` (this is the natural canonical home for F4.3 renderer-side behavior; no prior `operacion.md` existed at the canonical root). The copy was performed via PowerShell `Copy-Item` (no Read → Write through the model).

```
SRC_HASH (SHA256) = 2C5BE3F99989461EF1F832C8BC4E94E00C8AAD0F0FB089656735C8C0C780A20D
DST_HASH (SHA256) = 2C5BE3F99989461EF1F832C8BC4E94E00C8AAD0F0FB089656735C8C0C780A20D
BYTE_IDENTITY     = OK
SRC_BYTES         = 10189
DST_BYTES         = 10189
fc /b SRC DST     = EMPTY_DIFF (byte-identical)
```

No prior `openspec/specs/operacion.md` existed; no stomp of canonical content occurred. The delta is **ADDED Requirements only** — no MODIFIED, REMOVED, or RENAMED entries — so a fresh canonical file matches the Mechanical Copy Contract for delta that IS a full spec for a not-yet-existent canonical.

### Note on path inconsistency (recorded, NOT fixed here)

The F4.1 archive sits at `openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/specs/operations/spec.md` (plural `operations/`), and its canonical `openspec/specs/operations/spec.md` already exists (494 KB). The F4.3 delta uses the singular `operacion/` convention and now creates `openspec/specs/operacion.md` at the canonical root. The F4.3 spec body references `fase-4-1-deteccion-tipo-vehiculo/specs/operacion/spec.md` (singular) which never existed under that exact path — this is a pre-existing inconsistency between F4.1 (operations) and F4.3 (operacion) that this archive does not repair. The two canonical files coexist: `operations/spec.md` (backend, 494 KB, F4.1 + earlier backend deltas) and `operacion.md` (frontend, F4.3 only). Resolving the path inconsistency is left to a future cross-archive reconciliation HU.

## Mechanical Move Evidence (Step 3 — Archive Folder Move)

```
SNAP_ROOT  = C:\Users\mccra\AppData\Local\Temp\sdd-archive-snap-623211644\fase-4-3-ocupacion-en-vivo
DEST       = openspec/changes/archive/2026-09-17-fase-4-3-ocupacion-en-vivo
MOVE       = OK (PowerShell Move-Item)
SOURCE_GONE = True
DEST_EXISTS = True
ADDED_COUNT = 0
REMOVED_COUNT = 0
VERBATIM_DIFF_OUTPUT = EMPTY_DIFF (byte-identical recursive tree)
```

Files compared recursively by SHA256 (snapshot vs. archive destination):

| File | Status |
|---|---|
| `design.md` | byte-identical |
| `proposal.md` | byte-identical |
| `tasks.md` | byte-identical |
| `verify-report.md` | byte-identical |
| `specs/operacion/spec.md` | byte-identical |

The archive-report file (`archive-report.md`) is additive-only and was excluded from the source/destination comparison, per the Mechanical Copy Contract. `git mv` was not used because most change-folder files are working-tree-untracked (`??` per `git status --short`); plain `Move-Item` was the appropriate move primitive. The tracked `tasks.md` will appear as `D` + `??` in `git status` after this move — the maintainer handles git state at PR-merge time per gitflow.

## Follow-ups (Mandatory)

| # | Title | Severity | Scope | Blocking |
|---|---|---|---|---|
| 1 | **Run `e2e/operacion/ocupacion.spec.ts` on GitHub Actions before merge to `dev`** | High | github-actions | Yes |
| 2 | **Relocate `<OcupacionStrip />` from `App.tsx` to `Dashboard.tsx` in F4.4** | Medium | F4.4 | No |
| 3 | **Workspace-cleanup HU: fix SWR test-cast TS2554 pattern (F4.1 + F4.3 both)** | Medium | workspace | No |
| 4 | **Re-verify scoped tsconfig when `tsconfig.renderer.json` evolves** | Low | future-cycles | No |

### Follow-up details

1. **e2e on CI** — `e2e/operacion/ocupacion.spec.ts` must pass on GitHub Actions (`_electron.launch` + axe-core WCAG 2.1 AA + stale marker) before merging PR #1 to `dev`. Failure on CI triggers a re-verify cycle per openspec-convention.
2. **App.tsx mount relocation (F4.4)** — `<OcupacionStrip />` is mounted in `src/renderer/App.tsx` as a temporary integration point for the verify-phase scope; F4.4 dashboard phase relocates it to `Dashboard.tsx`. The temporary mount is functional but architecturally interim.
3. **Workspace-cleanup HU: SWR test-cast pattern** — both `useTiposVehiculo.test.ts:127-185` (F4.1) and `useOcupacion.test.ts:166-244` (F4.3) exhibit TS2554 at the SWR options cast. The F4.3 apply sub-agent mirrored F4.1 INTENTIONALLY with the rule "do NOT try to fix it locally — mirror F4.1 precedent" (engram id 1743). Workspace-cleanup candidate: introduce a typed SWR test wrapper `createMockSwr<T>` OR widen SWR mock-options typing at the SWR type declaration.
4. **Scoped tsconfig refresh** — `apps/electron-sucursal/tsconfig.f4-3-verify.json` extends `tsconfig.renderer.json` (not workspace-root `tsconfig.json`). When F4.x next touches `tsconfig.renderer.json`, re-verify against the updated renderer config; the verification artifact is independent of the workspace build.

## Cross-References

- PR #1: <https://github.com/sgveasypunto-ia/PArkOS/pull/1>
- Verify-report (rev 3, this cycle): `openspec/changes/fase-4-3-ocupacion-en-vivo/verify-report.md`
- Engram id 1738 rev 3 — verify-report (rev 1, rev 2, rev 3)
- Engram id 1742 — scoped-tsconfig recipe (updated 2026-09-17)
- Engram id 1743 — SWR test-cast TS2554 pattern (workspace-class)
- Engram id 1720-1724 — F4.3 planning observations
- Branch state: `feature/hu-f4-3-ocupacion-en-vivo` at commit `dea0514c9fb3be40747327d6a0868e9c207849a6`
- Prior F4 archive for context: `openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/`

## Next Steps (post-archive)

1. Maintainer merges PR #1 from GitHub UI to `dev` (NOT `main` — gitflow rule).
2. Once `dev` moves past `dea0514`, the orchestrator may delete the feature branch and (optionally) re-home the archive to `openspec/changes/archive/2026-09-17-fase-4-3-ocupacion-en-vivo/` is already in place.
3. F4.4 dashboard phase picks up `<OcupacionStrip />` relocation to `Dashboard.tsx`.
4. Workspace-cleanup HU (follow-up #3) opens once a candidate cycles through propose/spec/design.

## Rules Honored

- ✅ Mechanical Copy Contract (shell `Copy-Item` + SHA256 byte-identity + `fc /b` empty diff)
- ✅ Mechanical Move Contract (recursive snapshot + `Move-Item` + recursive SHA256 byte-identity)
- ✅ Spec sync BEFORE archive move
- ✅ Archive folder ISO date prefix `2026-09-17-`
- ✅ Verbatim diff readback output included (Step 2 + Step 3)
- ✅ No `git mv` needed (untracked files); `Move-Item` is the correct primitive per skill's "git mv when tracked, mv otherwise"
- ✅ No destructive delta — F4.3 is ADDED Requirements only
- ✅ Do not delete feature branch; do not invalidate Vite cache; do not touch `plan.md`, `AGENTS.md`, `modelo_datos_er.mmd`
- ✅ Final-state authority: archive reflects the state at close (rev 3 PASS), not intermediate verify-report states (rev 1 FAIL, rev 2 partial)