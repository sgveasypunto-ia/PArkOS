# Tasks: HU-F4.3 — Ocupación en vivo (frontend)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~240 (90 strip + 50 api + 70 hook + 25 thresholds + 5 constants + 6 keys i18n; tests +80) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR — 240 LOC fits well under the 800 LOC review budget and the 400 LOC guard. The slice is end-to-end (constants → thresholds → api → hook → component → tests) and atomically revertible. |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a (single PR) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a (single PR)
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Ship `<OcupacionStrip />` + hook + api + thresholds + tests end-to-end | PR 1 | `cd apps/electron-sucursal && npx vitest run src/features/operacion src/renderer/components/OcupacionStrip.test.tsx` | e2e `npx playwright test e2e/operacion/ocupacion.spec.ts` with `_electron.launch` | Delete the 8 new files + revert i18n key add — branch compiles, no other consumer depends on this slice (F4.4/F6.x/F7.x ship later). |

## Phase 1: Foundation — Pure Modules (no React, no I/O)

- [x] 1.1 Create `apps/electron-sucursal/src/features/operacion/constants.ts` exporting `OPERACION_REFRESH_INTERVAL_MS = 10_000` (verbatim DEC-SUC-11, in sync with backend `RefreshMvOcupacionWorker.DEFAULT_REFRESH_INTERVAL_S = 10`).
- [x] 1.2 Create `apps/electron-sucursal/src/features/operacion/occupancyThresholds.ts` exporting `THRESHOLD_YELLOW = 0.7`, `THRESHOLD_RED = 0.9`, and the pure function `classForPorcentaje(p: number): 'green' | 'yellow' | 'red'` (handles `p === 0.7` → yellow, `p === 0.9` → red, `p === 0` → green, `p > 1` → red as KD-6 valid negative for `cupo_no_configurado`).
- [x] 1.3 Create `apps/electron-sucursal/src/features/operacion/occupancyThresholds.test.ts` with 8 cases covering the boundary map (p=0, 0.5, 0.69, 0.7, 0.85, 0.9, 0.91, 1.5).
- [x] 1.4 Add 6 i18n keys to `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`: `ocupacion_titulo`, `ocupacion_legend_green`, `ocupacion_legend_yellow`, `ocupacion_legend_red`, `ocupacion_legend_stale`, `cupo_no_configurado`.

## Phase 2: Core — API + Hook

- [x] 2.1 Create `apps/electron-sucursal/src/features/operacion/api/ocupacionApi.ts` with Zod `OcupacionItemSchema`, `OcupacionResponseSchema`, types `OcupacionItem`, `OcupacionResponse`, and async `getOcupacion(uuid_sucursal: string): Promise<OcupacionResponse>` using `parkosFetch` from `@parkos/ui-kit/fetch` against `/api/v1/operacion/ocupacion?uuid_sucursal=...`.
- [x] 2.2 Create `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts` exporting `UseOcupacionReturn { data, error, isStale, refresh }` and `useOcupacion(uuid_sucursal: string | null)`. SWR config: `refreshInterval: OPERACION_REFRESH_INTERVAL_MS`, `dedupingInterval: 5_000`, key `null` when `uuid_sucursal` is `null` or `accessToken` is missing. `onError` logs warning via `console.warn` (does NOT `clear()` auth store — 401 still propagates normally). `shouldRetryOnError` excludes 401 (let auth store react), 403, 404.
- [x] 2.3 Create `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.test.ts` covering: refreshInterval=10_000, dedupingInterval=5_000, key null pre-auth, `isStale=true` when error follows a successful response.

## Phase 3: Component — OcupacionStrip Organismo

- [x] 3.1 Create `apps/electron-sucursal/src/renderer/components/OcupacionStrip.tsx` (~90 LOC). Props `{ uuid_sucursal: string }`. Renders a root `<div role="status" data-testid="ocupacion-strip">` with the strip title from i18n, then iterates `data.items` and renders one `<Tooltip><Chip/></Tooltip>` per item. Each chip shows `<Tipo>: <activos>/<cupo_maximo>` with `data-color` from `classForPorcentaje(activos/cupo_maximo)` and `aria-live="polite"`, `aria-atomic="false"`. On `isStale === true`, sets `data-stale="true"` on root and renders `<AlertCircle />` from `lucide-react` next to the title with tooltip `ocupacion_legend_stale`.
- [x] 3.2 Add `AbortController` cleanup: subscribe to the SWR fetcher's abort signal in a `useEffect` keyed on `uuid_sucursal`; on cleanup (or prop change) call `controller.abort()`. Document the pattern in the JSDoc.
- [x] 3.3 Create `apps/electron-sucursal/src/renderer/components/OcupacionStrip.test.tsx` with 4 RTL scenarios: render with 2 chips (Auto 23/50 → green, Moto 1/5 → green), threshold color change (mock returns Auto 40/50 → yellow), `data-stale="true"` after error (mock fetcher rejects after first success), aria-live per chip (assert `aria-live="polite"` + `aria-atomic="false"` on the Auto cell).
- [x] 3.4 Mount `<OcupacionStrip uuid_sucursal={...} />` from `useAuthStore` (`useAuthStore((s) => s.user?.sucursal?.uuid)`) in `src/renderer/App.tsx` (or in `Dashboard.tsx` once F4.4 lands — out of scope here; for the apply verification we mount in App.tsx temporarily and note as a follow-up for F4.4 to relocate).

## Phase 4: E2E + A11y

- [x] 4.1 Create `apps/electron-sucursal/e2e/operacion/ocupacion.spec.ts` with E1 scenario: launch `_electron`, mock `GET /api/v1/operacion/ocupacion` to return `{ items: [{ tipo: 'Auto', cupo_maximo: 50, activos: 23 }] }`, assert `Auto: 23/50` chip visible with `data-color="green"`; switch mock to return `activos: 47`, wait 12 s (one polling cycle + buffer), assert new text + `data-color="red"`.
- [x] 4.2 Add A1 scenario to the same spec: after E1 renders, scan with `AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()`; expect `violations` to be empty.
- [x] 4.3 Add A2 scenario: mock endpoint to fail with 500; wait 12 s; assert strip keeps `Auto: 23/50` text + `data-stale="true"` + `AlertCircle` icon visible.

## Phase 5: Verification (per apply, not here)

> Implementation will be exercised in the apply phase. This tasks.md focuses on the build/test work; verification belongs to sdd-verify.

## Implementation Order

Phase 1 first (pure modules + tests + i18n). Phase 2 (api + hook + tests). Phase 3 (component + tests + App.tsx mount). Phase 4 (e2e + a11y). The order matters because Phase 3's RTL tests depend on Phase 2's hook, which depends on Phase 1's constants.

## Local Verify Command

```powershell
cd apps\electron-sucursal
npx vitest run src/features/operacion src/renderer/components/OcupacionStrip.test.tsx
npx playwright test e2e/operacion/ocupacion.spec.ts
```

## Notes

- **No backend change.** HU-F1.5 already closed (`openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/archive-report.md`).
- **No `DELETE` / mutation.** DEC-SUC-11 + A-04. The componente is read-only by design — `cupo_maximo - activos` is computed server-side; the renderer never invents a `disponible` column.
- **No nuevos permisos.** `operacion:read` is in the catalog seeded by F1.2 (verify in apply phase before assuming).
- **Path correction vs. orchestrator prompt**: the prompt mentioned `src/components/OcupacionStrip.tsx`. The repo scaffold uses `src/renderer/components/`; honor the precedent (`<StatusBar />` F2.3 lives there).
