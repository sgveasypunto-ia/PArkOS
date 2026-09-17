# Tasks: HU-F4.2 — Tarifas vigentes (frontend)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~180 (3 new renderer files + 3 IPC diffs + 1 test file + format fixtures reuse) |
| 800-line review budget | Low — single PR fits comfortably (the cache pre-flight ruled out chained PRs) |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (not triggered) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | F4.2 complete | PR 1 (single) | `cd apps\electron-sucursal; npx vitest run src/features/caja/lib/format.test.ts src/features/catalogos/hooks/useTarifasVigentes.test.ts && npx vitest run electron/__tests__/preload.contract.test.ts` | Manual: launch Electron dev shell, open ingreso form, observe `TarifaBadge` after detection; cut the API mid-flight and reload — confirm cache fallback + stale mark after 1h simulated by tampering with `electron-store` | Delete the 3 new renderer files + revert the 3 IPC files; wipe `parkos.tarifas.cache.v1` from electron-store on next boot; no DB migration, no backend change |

## Phase 1: IPC Bridge Group — `tarifasStore`

- [x] 1.1 Extend `apps/electron-sucursal/electron/bridge.d.ts` `BridgeSurface` interface with `tarifasStore: { get(key: string): Promise<string | null>; set(key: string, value: string): Promise<void>; delete(key: string): Promise<void>; }`. Update the JSDoc group-count comment at line 11 from "6 groups, 8 methods" to "7 groups, 11 methods" — confirm the new totals in the comment match the literal count.
- [x] 1.2 Extend `apps/electron-sucursal/electron/preload.ts` `contextBridge.exposeInMainWorld('bridge', ...)` call with the `tarifasStore` group, mapping `get/set/delete` to `ipcRenderer.invoke('tarifas-store:get/set/delete', ...)`. Mirror the `authStore` block at lines 43-47.
- [x] 1.3 Extend `apps/electron-sucursal/electron/main.ts` `registerIpcHandlers` with 3 `ipcMain.handle` for `tarifas-store:get/set/delete` backed by the same `electron-store` instance that backs `kiosko` (use the existing `StoreLike` from `./services/kiosko` or extract a named `electronStore` from the existing `store` const at line 82). Add a unit test `electron/services/tarifas-store.test.ts` confirming round-trip `set → get` and that `delete` makes `get` return `null`.
- [x] 1.4 Update `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` expected group list (line 42) from `['apiStatus','app','authStore','imprimir','kiosk','usb']` to `['apiStatus','app','authStore','imprimir','kiosk','tarifasStore','usb']`. Add the 3 channel-invocation assertions (lines 99-116 pattern) for `tarifas-store:get/set/delete`.

## Phase 2: Catalog API Wrapper

- [x] 2.1 Create `apps/electron-sucursal/src/features/catalogos/api/tarifasSucursalApi.ts` exporting:
  - `interface TarifaSucursalRead { uuid, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, valor, valor_plena, vigente_desde, vigente_hasta, estado, created_at, created_by, sync_status }` matching backend `schemas/empresa.py:265-280`.
  - `interface TarifasSucursalReadList { items, next_cursor }`.
  - `export async function listTarifasSucursal(vigenteEn: Date = new Date(), cursor?: string): Promise<TarifasSucursalReadList>` that calls `parkosFetch<TarifasSucursalReadList>('/api/v1/empresa/tarifas-sucursal?vigente_en=<iso>&cursor=...')`.
  - MUST capture `404` and return `{ items: [], next_cursor: null }` (sucursal sin tarifas configuradas es estado válido).
  - MUST NOT use `fetch` directly — only `parkosFetch` (DEC-SUC-04 invariant).
- [x] 2.2 JSDoc must cross-reference `backend/.../api/v1/empresa.py:179-213` and `repo/tarifas_vigencia.py::list_tarifas_vigentes` (defense in depth XR6 layer 4 — same convention as `tiposVehiculoApi.ts:1-31`).

## Phase 3: SWR Hook — `useTarifasVigentes`

- [x] 3.1 Create `apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.ts` exporting:
  - `useTarifasVigentes(uuidTipoVehiculo: string): { tarifa, fetchedAt, isStale, isFromFallback, refresh }`.
  - SWR key: `accessToken ? '/empresa/tarifas-sucursal' : null` (gate against 401 noise pre-login — same as `useTiposVehiculo`).
  - `dedupingInterval: 5 * 60 * 1000` (DEC-F4.1-04 verbatim, applies to catálogos reference data).
  - `shouldRetryOnError: err => !(err instanceof ParkosHttpError && err.status === 404)` (404 is valid empty state).
  - `onSuccess: snapshot => window.bridge.tarifasStore.set('parkos.tarifas.cache.v1', JSON.stringify(snapshot))`.
  - `onError: err => if (401) useAuthStore.getState().clear() + dispatch('parkos:auth:cleared')` (precedent F4.1 verbatim).
  - Two-phase render via `useEffect`: `tarifasStore.get('parkos.tarifas.cache.v1')` → `setCacheHydrated(snapshot)` → SWR sees `fallbackData`. First render: `tarifa === null` (badge hidden). Second render: cached value visible.
  - Client-side filter: `tarifa = snapshot.items.find(t => t.uuid_tipo_vehiculo === uuidTipoVehiculo) ?? null`.
  - `isStale: fetchedAt !== null && Date.now() - fetchedAt > 60 * 60 * 1000`.
- [x] 3.2 Constants MUST be module-level: `CACHE_KEY = 'parkos.tarifas.cache.v1'`, `SWR_KEY = '/empresa/tarifas-sucursal'`, `DEDUPING_INTERVAL_MS = 5*60*1000`, `STALE_THRESHOLD_MS = 60*60*1000`.

## Phase 4: Hook Tests

- [x] 4.1 Create `apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.test.ts` mirroring `useTiposVehiculo.test.ts` mocking pattern (vi.mock `swr`, `@parkos/ui-kit/store`, `@parkos/ui-kit/fetch`, `../api/tarifasSucursalApi`, and `window.bridge.tarifasStore`). Cover at minimum:
  - **U1 (cache válido)**: `bridge.tarifasStore.get` returns `{items:[{...auto}], fetchedAt:<now>}`, no API call yet → `tarifa` from cache, `isStale === false`, `isFromFallback === true`.
  - **U2 (invalidación tras cambio de tipo)**: cache contains both `auto` and `moto` rows; render `useTarifasVigentes('uuid-auto')` then `useTarifasVigentes('uuid-moto')` — both resolve from cache, only ONE SWR fetch fires.
  - **U3 (optional but recommended)**: API 200 path → `bridge.tarifasStore.set` called with the snapshot JSON; `isFromFallback === false` once `data !== cacheHydrated`.
- [x] 4.2 Add the 2 formatCOP fixtures verbatim in `apps/electron-sucursal/src/features/caja/lib/format.test.ts` if missing (plan.md T2 verbatim fixtures — `formatCOP(8000) === '$ 8.000'`, `formatCOP(1234567) === '$ 1.234.567'`). The existing file already has these per `grep` of `format.test.ts:15-29`; verify and add the missing one(s) if any.

## Phase 5: Presentational Badge — `<TarifaBadge>`

- [x] 5.1 Create `apps/electron-sucursal/src/features/catalogos/components/TarifaBadge.tsx` exporting a pure presentational component:
  - Props: `{ tarifa: TarifaVigente | null, fetchedAt: number | null, isStale: boolean }`.
  - Returns `null` when `tarifa === null` (the hook handles the badge hidden state during hydration).
  - Renders `formatCOP(Number(tarifa.valor))` from `apps/electron-sucursal/src/features/caja/lib/format` (DIRECT import — no copy).
  - When `isStale === true`: renders a stale-mark line `"Tarifa cacheada — verifica con el supervisor"` (es-CO literal, no i18n extraction this phase) AND a visually-hidden `<span id="tarifa-stale-help" className="sr-only">` with the WCAG help text; the wrapping `<div>` receives `aria-describedby="tarifa-stale-help"`.
  - The `<div>` MUST NOT have `role="status"` for the value text (only the stale-mark line gets `role="status"`).
- [x] 5.2 JSDoc cross-references `apps/electron-sucursal/src/lib/validation/placa.ts` (F4.1) for the upstream detection function; the badge consumes the F4.1 detection + F4.2 lookup but does NOT depend on F4.1 directly (single-direction dep: TarifaBadge ← useTarifasVigentes ← tarifa values, no placa import).

## Phase 6: Local Verification

- [ ] 6.1 From `apps\electron-sucursal\`, run `npx vitest run src/features/caja/lib/format.test.ts src/features/catalogos/hooks/useTarifasVigentes.test.ts electron/__tests__/preload.contract.test.ts` — must exit 0.
- [ ] 6.2 From `apps\electron-sucursal\`, run `npx tsc --noEmit` — must exit 0 (no TS regressions; verifies the `bridge.tarifasStore` typings are correct in `global.d.ts`).
- [ ] 6.3 From `apps\electron-sucursal\`, run `npx eslint src/features/catalogos electron` — must exit 0.
- [ ] 6.4 Manual smoke (Electron dev shell): type `ABC123` in ingreso form, observe `<TarifaBadge>` rendering with `formatCOP(valor)`. Cut the network mid-flight and reload — confirm cache fallback + stale mark after manually tampering with `parkos.tarifas.cache.v1` to set `fetchedAt: Date.now() - 2 * 60 * 60 * 1000`.

## Phase 7: PR Creation

- [ ] 7.1 Create branch `feature/hu-f4-2-tarifas-vigentes` from `dev` (gitflow — never direct to `main`).
- [ ] 7.2 Configure git author: `git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' ...`.
- [ ] 7.3 Conventional Commit `feat(catalogos): HU-F4.2 tarifas vigentes con cache offline` with body referencing `Refs: HU-F4.2` and the plan.md lines 1392-1420. Cite DEC-SUC-12 + A-02 in the body. NO `Co-authored-by` trailers.
- [ ] 7.4 Push branch and open PR against `dev` (NOT `main`). The PR body MUST include:
  - The preflight summary ("HU-F4.2 done — TarifaBadge + useTarifasVigentes + IPC tarifasStore + formatCOP reuse").
  - The risk note about `uuid_tipo_vehiculo` client-side filter (documented refinement vs the AC literal endpoint signature; follow-up PR may add the param to the dedicated handler).
  - Confirmation that no backend change is included (HU-F1.4 closed).
- [ ] 7.5 After merge, delete the feature branch (local + remote) and run `git fetch --prune origin`. Do NOT invalidate Vite cache unless the merge touched `package.json` deps (it does not for this change).