# Verify Report — HU-F9.1

> **Change**: `fase-9-1-venta-suscripcion` | **Phase**: sdd-verify | **Status**: PENDING orchestrator validation
> **Branch**: `feature/hu-f9-1-venta-suscripcion`

## Verification gate (pre-merge)

| # | Gate | Status |
|---|---|---|
| 1 | `pnpm --filter electron-sucursal test` exits 0 | [ ] PENDING |
| 2 | `pnpm --filter electron-sucursal typecheck` exits 0 | [ ] PENDING |
| 3 | `pnpm --filter electron-sucursal lint` exits 0 | [ ] PENDING |
| 4 | `pnpm --filter electron-sucursal test:coverage` meets per-file thresholds (3 new entries) | [ ] PENDING |
| 5 | `git diff dev..feature/hu-f9-1-...` ≤ 935 LOC | [ ] PENDING |
| 6 | Drift guard: stub removed from `useSuscripcionesList.ts:80-98` | [x] DONE (commit 2) |
| 7 | Drift guard: `calcularMontoProporcional` ≥3 references in `features/suscripciones` | [x] DONE (lib + Venta caller + test) |
| 8 | Drift guard: `VentaSuscripcionDuplicatePlateError` ≥3 references | [x] DONE (hook def + Venta render + test) |
| 9 | PagoModal reuse contract: Venta step 4 renders `<PagoModal ... onSubmit={…} />` | [x] DONE (commit 3) |
| 10 | F8.1 PagoModal + 5 PagoModal tests still pass (no shared component touched) | [ ] PENDING |
| 11 | F9.2 `SuscripcionesPanel` unaffected (still lists subscriptions) | [ ] PENDING |
| 12 | `git grep useVentaSuscripcion useSuscripcionesList.ts` returns 0 | [x] DONE |

## Per-File Thresholds

| File | Threshold | Lines | Functions | Branches |
|---|---|---|---|---|
| `prorrateo.ts` | 95 / 95 / 90 | [ ] | [ ] | [ ] |
| `useVentaSuscripcion.ts` | 90 / 90 / 85 | [ ] | [ ] | [ ] |
| `Venta.tsx` | 80 / 80 / 75 | [ ] | [ ] | [ ] |

## Test Counts

| Suite | Tests | Status |
|---|---|---|
| `prorrateo.test.ts` | 5 | [x] 5/5 passing |
| `useVentaSuscripcion.test.ts` | 4 | [x] 4/4 passing |
| `Venta.test.tsx` | 7 | [x] 7/7 passing |
| `e2e/suscripcion-venta.spec.ts` | 4 (stubs) | [ ] PENDING backend live |

## Verdict

PASS verdict: PENDING orchestrator validation.

## Rollback Plan

Per-commit revert (each commit compiles + tests independently):
1. `git revert <commit-sha>` per commit — no DB migration, no backend change.
2. Full branch revert restores `useSuscripcionesList.ts` stub + deletes all F9.1 files.

## Post-merge (per AGENTS.md gitflow override rule 2026-09-17)

1. `git checkout dev` + `git merge --ff-only feature/hu-f9-1-venta-suscripcion`.
2. `git push origin dev`.
3. `git branch -d feature/hu-f9-1-venta-suscripcion` + `git push origin --delete`.
4. Vite cache invalidation: kill port 5173 + restart with `--force`.
5. Engram `mem_save` of canonical wizard composition + useVentaSuscripcion mirror + prorrateo client-side helper + stub removal decisions.
6. F9.2 developer notification: `useSuscripcionesList.ts` no longer exposes `useVentaSuscripcion`; the F9.2 listing file is now read-only SWR query.
