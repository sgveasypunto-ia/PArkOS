# Tasks: HU-F4.1 Vehicle Type Detection

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~400 (with ≥30% buffer vs the 100-LOC plan estimate, accounting for tests + import scaffolding + i18n + the full hook surface that the plan underestimated) |
| 400-line budget risk | Low |
| 800-line review budget | Low — single PR fits comfortably |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (not triggered) |
| Decision needed before apply | No |
| Chained PRs recommended | No |
| Chain strategy | pending |
| 400-line budget risk | Low |

### Implementation state note

The implementation files already exist on the workspace as discovered during planning (`placa.ts`, `placa.test.ts`, `useTiposVehiculo.ts`). The apply phase must verify the on-disk state matches this spec/design before merging. Tasks below describe both the as-built surface and the residual gaps (tests for the SWR hook, the API wrapper, the i18n key).

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | F4.1 complete | PR 1 (single) | `cd apps\electron-sucursal; npx vitest run src/lib/validation/placa.test.ts src/features/catalogos/hooks/useTiposVehiculo.test.ts` | Manual: launch Electron dev shell, type `ABC123` / `ABC12D` / `ABCD12` in ingreso form, observe detection + inline error | Delete the 4 new files + revert i18n key; no DB migration, no backend change |

## Phase 1: Foundation — Validation Primitive

- [x] 1.1 Verify `apps/electron-sucursal/src/lib/validation/placa.ts` exists with `REGEX_AUTO`, `REGEX_MOTO`, and `detectarTipoVehiculo()`. If missing, create it (76 LOC pattern per `design.md` Interfaces section). **VERIFIED** — file present, 76 LOC, exports all three.
- [x] 1.2 Verify JSDoc on `placa.ts` cross-references `backend/.../operacion.py:215-277` (defense in depth XR6 layer 4 contract). **VERIFIED** — JSDoc line 14 explicit cross-reference.
- [x] 1.3 Verify normalization order is `trim() → toUpperCase() → replace(/\s+/g, '')`. Refuse any function with a tolerance parameter (DEC-SUC-22 verbatim). **VERIFIED** — line 72.

## Phase 2: Foundation — Pure Function Tests

- [x] 2.1 Verify `apps/electron-sucursal/src/lib/validation/placa.test.ts` exists with the 8 verbatim test cases U1..U8 from `plan.md:1381`. **VERIFIED** — all 8 cases present (lines 25-57).
- [x] 2.2 If a test is missing, ADD it (no test must be deleted). **VERIFIED** — no missing tests; no deletions.
- [x] 2.3 Run `vitest run src/lib/validation/placa.test.ts` from `apps\electron-sucursal\` — must exit 0. **PASS** — 8/8 tests, exit 0 (log: `C:\Users\mccra\AppData\Local\Temp\opencode\f4-1-vitest.log`).

## Phase 3: Catalog API Wrapper

- [x] 3.1 Create `apps/electron-sucursal/src/features/catalogos/api/tiposVehiculoApi.ts` exporting the typed `TipoVehiculo` interface and `getTiposVehiculo()` with `parkosFetch`, 404→`[]`, defensive `tipo: null` filter. **VERIFIED** — file present (71 LOC), all four requirements met (lines 43-49 interface, line 61 function, line 66 404 catch, line 64 null filter).
- [x] 3.2 File MUST NOT use `fetch` directly — only `parkosFetch` (DEC-SUC-04 invariant). **VERIFIED** — line 32 imports `parkosFetch` from `@parkos/ui-kit/fetch`; no direct `fetch` calls.

## Phase 4: Catalog SWR Hook

- [x] 4.1 Verify `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` exists with the SWR hook, hardcoded fallback `{auto, moto}`, and `isFromFallback` flag. **VERIFIED** — file present (133 LOC), SWR hook line 100, HARDCODED_CATALOG lines 61-76, `isFromFallback` line 131.
- [x] 4.2 Verify `dedupingInterval: 5 * 60 * 1000` is set. **VERIFIED** — line 49 constant + line 108 applied.
- [x] 4.3 Verify `shouldRetryOnError` excludes 404. **VERIFIED** — lines 110-111.
- [x] 4.4 Verify `onError` with `status === 401` calls `useAuthStore.getState().clear()` and dispatches `'parkos:auth:cleared'` event. **VERIFIED** — lines 112-119.
- [x] 4.5 Verify SWR key is `accessToken ? '/catalogos/tipos-vehiculo' : null` (gate against 401 noise pre-login). **VERIFIED** — lines 47 + 104.

## Phase 5: Hook Tests

- [x] 5.1 Verify `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.test.ts` exists. **VERIFIED** — file present (211 LOC), 11 tests covering: U7 SWR key null sin token, U7b SWR key con accessToken, U8 fetcher wiring, U10 dedupingInterval, U11/U11b/U11c onError 401/500/404, fallbackData reference, return shape, refresh Promise wrap.
- [x] 5.2 Run `vitest run src/features/catalogos/hooks/useTiposVehiculo.test.ts` from `apps\electron-sucursal\` — must exit 0. **PASS** — 11/11 tests, exit 0 (same log).

## Phase 6: i18n Key

- [x] 6.1 Add `operacion.placa_formato_invalido` key to `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` with literal text: `"Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)"`. **VERIFIED** — line 12 of `operacion.json` contains the verbatim string.
- [x] 6.2 Confirm `operacion.json` parses without JSON errors. **VERIFIED** — file parses, key present. (Note: working copy contains additional F4.3 keys appended after the F4.1 key — out of scope for F4.1, but the F4.1 key remains intact.)

## Phase 7: Local Verification

- [x] 7.1 From `apps\electron-sucursal\`, run `npx vitest run src/lib/validation/placa.test.ts src/features/catalogos/hooks/useTiposVehiculo.test.ts` — must exit 0. **PASS** — 19/19 tests across 2 files, exit 0 (log: `C:\Users\mccra\AppData\Local\Temp\opencode\f4-1-vitest.log`).
- [x] 7.2 From `apps\electron-sucursal\`, run `npx tsc --noEmit` — must exit 0 (no TS regressions). **PASS** — exit 0, no TS errors (log: `C:\Users\mccra\AppData\Local\Temp\opencode\f4-1-tsc.log`).
- [x] 7.3 From `apps\electron-sucursal\`, run `npx eslint src/lib/validation src/features/catalogos` — must exit 0. **PASS** — exit 0, no lint errors (log: `C:\Users\mccra\AppData\Local\Temp\opencode\f4-1-eslint.log`).
- [ ] 7.4 Manual smoke (Electron dev shell): type `ABC123`, `ABC12D`, `ABCD12` in the ingreso form and confirm detection + inline error message. **DEFERRED-env** per F.6 sandbox precedent — F4.1 does not ship a UI component (forward F6.1 `<PlacaInput>`); unit tests cover the deterministic detection logic.

## Phase 8: PR Creation

- [x] 8.1 Create branch `feature/hu-f4-1-deteccion-tipo-vehiculo` from `dev` (gitflow — never direct to `main`). **DONE** — branch created from dev, no diff vs dev.
- [x] 8.2 Configure git author: `git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' ...`. **N/A** — no commits made (no diff to commit).
- [x] 8.3 Conventional Commit `feat(operacion): HU-F4.1 deteccion tipo vehiculo por placa` with body referencing `Refs: HU-F4.1` and the plan.md lines 1359-1388. **SKIPPED** — F4.1 work already on dev in commits `9810841` + `a6ddd5a` (archived 2026-09-16). No new diff vs dev to commit. Both prior commits honor conventional commits format + `Parkos Dev <dev@parkos.local>` author + 0 Co-authored-by trailers (per archive-report §3 ledger).
- [x] 8.4 Push branch and open PR against `dev` (NOT `main`). **PARTIAL** — branch pushed to origin successfully, but `gh pr create --base dev` rejected with `GraphQL: No commits between dev and feature/hu-f4-1-deteccion-tipo-vehiculo (createPullRequest)` (no diff vs dev). PR-creation-deferred because F4.1 is already on dev.
- [x] 8.5 After merge, delete the feature branch (local + remote) and run `git fetch --prune origin`. **DONE** — empty branch deleted locally + remotely (`git push origin --delete` + `git branch -D`); no `git fetch --prune` needed since no other branches were touched.