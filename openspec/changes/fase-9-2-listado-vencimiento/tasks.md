# Tasks: HU-F9.2 Listado y alerta de vencimiento

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~300 (10 files: 7 NEW, 3 MODIFIED) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR — 3 commits, ~220 LOC production code |
| Delivery strategy | single-pr |
| Chain strategy | n/a |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `useSuscripcionesProximasVencer` + 3 tests | PR 1 | `pnpm --filter electron-sucursal test -- --run useSuscripcionesProximasVencer` | typecheck | Revert commit; Dashboard falls back to no banner |
| 2 | `<Listado />` page + 3 component tests | PR 1 | `pnpm --filter electron-sucursal test -- --run Listado` | typecheck | Revert commit; route not registered |
| 3 | Dashboard banner + i18n + route + e2e + apply-progress | PR 1 | `pnpm --filter electron-sucursal test -- --run` + e2e stub + git grep | typecheck | Revert commit; metadata only, hook/page survive |

## Phase 1: Hook (commit 1 — RED → GREEN strict TDD)

- [x] 1.1 RED: write `useSuscripcionesProximasVencer.test.ts` with 3 failing tests (filter excludes vencidas, sort ASC, empty → [])
- [x] 1.2 GREEN: create `lib/constants.ts` with `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7`
- [x] 1.3 GREEN: create `hooks/useSuscripcionesProximasVencer.ts` with SWR polling, filter, sort, 401-clear
- [x] 1.4 REFACTOR: extract pure helper if needed; ensure tests still green
- [x] 1.5 Commit: `feat(suscripciones): useSuscripcionesProximasVencer + 3 tests`

## Phase 2: Page (commit 2 — RED → GREEN strict TDD)

- [x] 2.1 RED: write `Listado.test.tsx` with 3 failing tests (render columns, search filter, empty search)
- [x] 2.2 GREEN: create `pages/Listado.tsx` with DataTable + search input + client-side filter
- [x] 2.3 REFACTOR: pure helper for filter; memoize search
- [x] 2.4 Commit: `feat(suscripciones): Listado page + 3 component tests`

## Phase 3: Polish (commit 3 — mechanical integration)

- [x] 3.1 Add `/suscripciones` route in `App.tsx` wrapped in `<ProtectedRoute>`
- [x] 3.2 Update `Dashboard.tsx` with inline banner + role="alert" + top-5 right sidebar panel
- [x] 3.3 Add 8 i18n keys to `suscripciones.json` (banner, panel title, panel count format, badge vencida, etc.)
- [x] 3.4 Create `e2e/suscripciones-lista.spec.ts` with 2 stub scenarios (gated by `test.skip`)
- [x] 3.5 Add per-file thresholds in `vitest.config.ts` for the 2 new modules (≥90/90/85 standard)
- [x] 3.6 Create `apply-progress.md` with TDD Cycle Evidence table
- [x] 3.7 Create `verify-report.md` placeholder for `sdd-verify` next phase
- [x] 3.8 Commit: `feat(suscripciones): Principal banner + i18n + e2e + apply-progress`

## Phase 4: Pre-commit verification (after all 3 commits)

- [x] 4.1 Run `pnpm --filter electron-sucursal test -- --run useSuscripcionesProximasVencer Listado` → all green
- [x] 4.2 Run `pnpm exec tsc -b --noEmit` filtered to F9.2 files → 0 errors
- [x] 4.3 Run `pnpm exec eslint <new files>` with `--max-warnings 0` → 0
- [x] 4.4 Run `git grep -nE "dias_alerta_pre_vencimiento_override" apps/electron-sucursal/src` → 0 matches (drift guard)
- [x] 4.5 Run `git diff dev..feature/hu-f9-2-listado-vencimiento --stat` → ≤ 800 LOC

## Implementation Order

Phase 1 → Phase 2 → Phase 3 sequential (each builds on prior). Phase 4
verification runs after all three commits are made. Single PR to `dev`
per AGENTS.md gitflow override rule 2026-09-17.

## Next Step

Ready for `sdd-apply`. Workload decision: NOT required (under 400-line
budget, single-pr delivery strategy).
