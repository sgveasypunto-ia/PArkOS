# Design: HU-F4.3 — Ocupación en vivo (frontend)

## Technical Approach

A pure-React organismo on the renderer that polls the existing backend endpoint `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` every 10 s via SWR, with per-fetch `AbortController` cleanup on unmount. The componente is shared (under `src/renderer/components/`, not `src/features/operacion/`) because F4.4 dashboard, F6.x ingreso and F7.x salida will all consume it. The data is **read-only**: the componente never mutates state — all colors, percentages and stale flags are derived from the response payload.

The single source of truth for thresholds lives in `occupancyThresholds.ts`. The single source of truth for the polling cadence lives in `constants.ts`. Both are tiny pure modules with no DOM and no I/O — testable in isolation, immutable across consumers.

## Architecture Decisions

### Decision: Shared Component at `src/renderer/components/OcupacionStrip.tsx` (cross-feature organismo)

**Choice**: Place `<OcupacionStrip />` next to `<StatusBar />` (F2.3) and `<ProtectedRoute />` (F2.1) under `src/renderer/components/`, NOT under `src/features/operacion/components/`.
**Alternatives considered**: Place it under `features/operacion/components/` to mirror Caja/Auth/Catalogos organization; place it in a new `features/operacion/` cross-feature module.
**Rationale**: It is consumed by F4.4 (catalogos dashboard), F6.x (ingreso flow), F7.x (salida flow) — three different features. Putting it inside `features/operacion/components/` would force those consumers to import across feature boundaries (which the F4.1 archive explicitly discourages — see the "no cross-feature imports" precedent). `src/renderer/components/` is the established cross-feature home (verified — `<StatusBar />` lives there and is consumed by App.tsx).
**Path correction**: The orchestrator prompt mentioned `src/components/OcupacionStrip.tsx`. The repo scaffold uses `src/renderer/components/`; honoring the repo convention (apply phase should not move the file after this design is approved).

### Decision: SWR with `refreshInterval: 10_000` + `dedupingInterval: 5_000` (DEC-SUC-11 verbatim)

**Choice**: `useSWR(key, fetcher, { refreshInterval: OPERACION_REFRESH_INTERVAL_MS, dedupingInterval: 5_000, onError, shouldRetryOnError })`.
**Alternatives considered**: A manual `setInterval` with `AbortController`; `useQuery` from React Query; an EventSource/SSE.
**Rationale**: SWR is the único *data fetcher* de lectura del proyecto (DEC-SUC-05). Manual `setInterval` re-implements cache + dedup + focus-revalidation logic that SWR already provides. React Query is not adopted (DEC-SUC-05 again). EventSource/SSE is explicitly descartado por DEC-SUC-11. The 10 s interval matches `RefreshMvOcupacionWorker.DEFAULT_REFRESH_INTERVAL_S` so cliente polling nunca queda stale más de un ciclo de la vista materializada.

### Decision: `AbortController` Per Fetch (not per hook instance)

**Choice**: The hook's fetcher receives the `AbortSignal` from SWR's underlying fetch. The hook's `useEffect` listens to `data`/`error` changes and aborts the previous in-flight signal whenever the SWR key changes.
**Alternatives considered**: Wrap the entire `useSWR` call in a parent `AbortController` (overkill — SWR already handles abort via its internal fetcher); rely on React's automatic cleanup (false — fetch does not auto-cancel on unmount without an explicit signal).
**Rationale**: DEC-SUC-04 verbatim — "un solo refresh automático ante 401 (un segundo 401 consecutivo cierra sesión y redirige a login)" implies a careful async lifecycle. The pattern used by `useSesionActiva` (F3.3) does not cancel explicitly; the unit test there does not exercise unmount during fetch. This HU adds explicit cancellation because the strip is mounted on long-lived dashboards where unmount during fetch is routine (operator navigates away from `/` to `/caja/abrir-turno`).

### Decision: Thresholds as Exported Constants + Pure Function

**Choice**: `occupancyThresholds.ts` exports:
```ts
export const THRESHOLD_YELLOW = 0.7;
export const THRESHOLD_RED = 0.9;
export function classForPorcentaje(p: number): 'green' | 'yellow' | 'red';
```
**Alternatives considered**: Read thresholds from a runtime config (admin-configurable per tenant); inline the logic in the JSX.
**Rationale**: Reading from runtime config would require a new endpoint and a state store — out of scope. Inline JSX would couple the test to the React tree. The pure-function approach matches precedent F4.1's regex constants exported from `placa.ts` and makes the unit test trivial (no React, no MSW, no SWR).

### Decision: Shadcn Semantic Color Tokens, not Hex

**Choice**: The chip uses Tailwind utility classes mapped to shadcn semantic tokens (`bg-green-500`, `bg-amber-500`, `bg-destructive`). The `bg-destructive` token resolves to `hsl(var(--destructive))`, which already exists in `index.css` and is overridable per tenant via the `.tenant-*` class.
**Alternatives considered**: Hardcoded hex (`#10b981`, `#f59e0b`, `#ef4444`); inline `style={{ background: ... }}` strings.
**Rationale**: Hardcoded hex violates the white-label invariant documented in the project AGENTS.md ("NO hex hardcoded — solo tokens semánticos"). Tailwind utility classes are already supported by the project's `tailwind.config.ts` and are the canonical shadcn pattern.

### Decision: Degraded State via `data-stale` Attribute + Icon (no UI removal)

**Choice**: When `useSWR` reports an error after a successful response, the componente keeps the previous `data` rendered (SWR's behavior — `data` persists across errors), sets `data-stale="true"` on the root, and shows `AlertCircle` + tooltip.
**Alternatives considered**: Show an error placeholder that says "ocupación no disponible"; clear the strip and show a skeleton.
**Rationale**: Plan.md:1433 is literal — "el strip conserva el último valor conocido con indicador visual sutil de 'desactualizado', no desaparece". An operator in the middle of a busy shift must not lose situational awareness because the polling endpoint hiccuped for 30 s. Skeleton/placeholder would feel like a regression vs. the previous render.

### Decision: Per-Chip `aria-live="polite"` with `aria-atomic="false"`

**Choice**: Each chip cell carries `aria-live="polite"` and `aria-atomic="false"`. The root container does NOT carry `aria-live` (would re-announce the whole strip on any change).
**Alternatives considered**: One root-level `aria-live` (announces the whole strip on any change — noisy); `aria-live="assertive"` (interrupts the operator — too aggressive).
**Rationale**: `polite` + `atomic-false` per cell matches the operator's mental model — they care about changes to specific tipos, not the whole strip. Precedent: WAI-ARIA Authoring Practices for live regions.

## Data Flow

```
              ┌──────────────────────────────────────────────┐
              │  RefreshMvOcupacionWorker (backend)          │
              │  REFRESH MATERIALIZED VIEW CONCURRENTLY      │
              │  prod.mv_ocupacion_diaria every 10s          │
              └───────────────────┬──────────────────────────┘
                                  │
                                  ▼
                GET /api/v1/operacion/ocupacion?uuid_sucursal=X
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  parkosFetch (F2.2) + Zod schema OcupacionResponse          │
   │  → { uuid_sucursal, items: [{ tipo, cupo_maximo,            │
   │                              activos, disponible }],         │
   │    generado_en }                                            │
   └────────────────────┬────────────────────────────────────────┘
                        │
                        ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  useOcupacion()  SWR hook                                   │
   │  - refreshInterval: 10_000 ms (OPERACION_REFRESH_INTERVAL_MS)│
   │  - dedupingInterval: 5_000 ms                               │
   │  - key: /operacion/ocupacion?uuid_sucursal=X                 │
   │  - onError: log warning, do not clear `data`                │
   │  - shouldRetryOnError: status !== 401, 403, 404             │
   └────────────────────┬────────────────────────────────────────┘
                        │
                        ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  <OcupacionStrip />                                         │
   │  - iterate items                                            │
   │  - per item: <Tooltip><Chip/></Tooltip>                      │
   │  - classForPorcentaje(p) → data-color="green|yellow|red"    │
   │  - if (error && data) data-stale="true" + <AlertCircle/>    │
   │  - aria-live="polite" aria-atomic="false" per chip          │
   └─────────────────────────────────────────────────────────────┘
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/renderer/components/OcupacionStrip.tsx` | Create | Organismo compartido (~90 LOC). SWR + AbortController + thresholds + Tooltip leyenda + stale marker. |
| `apps/electron-sucursal/src/renderer/components/OcupacionStrip.test.tsx` | Create | 4 RTL tests (~140 LOC): render, threshold color, stale marker on error, aria-live per chip. |
| `apps/electron-sucursal/src/features/operacion/api/ocupacionApi.ts` | Create | `parkosFetch` wrapper + Zod schema `OcupacionItemSchema` + `OcupacionResponseSchema` (~50 LOC). |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts` | Create | SWR hook (~70 LOC). |
| `apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.test.ts` | Create | SWR config tests (~110 LOC): refreshInterval=10_000, dedupingInterval=5_000, key null pre-auth, abort on unmount. |
| `apps/electron-sucursal/src/features/operacion/occupancyThresholds.ts` | Create | Pure constants + `classForPorcentaje` (~25 LOC). |
| `apps/electron-sucursal/src/features/operacion/occupancyThresholds.test.ts` | Create | Unit test for the threshold map (~30 LOC). |
| `apps/electron-sucursal/src/features/operacion/constants.ts` | Create | `OPERACION_REFRESH_INTERVAL_MS = 10_000` (~5 LOC). |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modify | Add 6 keys: `ocupacion_titulo`, `ocupacion_legend_green/yellow/red/stale`, `cupo_no_configurado`. |
| `apps/electron-sucursal/e2e/operacion/ocupacion.spec.ts` | Create | 2 tests (~80 LOC): E1 render + value refreshes after simulated new ingreso via `page.route`; A1 axe-core WCAG 2.1 AA scan on the rendered strip. |

## Interfaces / Contracts

```ts
// src/features/operacion/constants.ts
export const OPERACION_REFRESH_INTERVAL_MS = 10_000;

// src/features/operacion/occupancyThresholds.ts
export const THRESHOLD_YELLOW = 0.7;
export const THRESHOLD_RED = 0.9;
export function classForPorcentaje(p: number): 'green' | 'yellow' | 'red';

// src/features/operacion/api/ocupacionApi.ts
import { z } from 'zod';

export const OcupacionItemSchema = z.object({
  uuid_tipo_vehiculo: z.string().uuid(),
  tipo: z.string(),
  cupo_maximo: z.number().int().min(0),
  activos: z.number().int().min(0),
  disponible: z.number().int(),
});
export type OcupacionItem = z.infer<typeof OcupacionItemSchema>;

export const OcupacionResponseSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  items: z.array(OcupacionItemSchema),
  generado_en: z.string().datetime(),
});
export type OcupacionResponse = z.infer<typeof OcupacionResponseSchema>;

export async function getOcupacion(uuid_sucursal: string): Promise<OcupacionResponse>;

// src/features/operacion/hooks/useOcupacion.ts
import useSWR from 'swr';

export interface UseOcupacionReturn {
  data: OcupacionResponse | undefined;
  error: Error | undefined;
  isStale: boolean;        // true cuando hay data + error (SWR conserva el último valor)
  refresh: () => Promise<OcupacionResponse | undefined>;
}
export function useOcupacion(uuid_sucursal: string | null): UseOcupacionReturn;

// src/renderer/components/OcupacionStrip.tsx
export interface OcupacionStripProps {
  uuid_sucursal: string;
}
export function OcupacionStrip(props: OcupacionStripProps): JSX.Element;
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (occupancyThresholds) | Pure function for 8 cases: p=0, 0.5, 0.69, 0.7, 0.85, 0.9, 0.91, 1 | `vitest run src/features/operacion/occupancyThresholds.test.ts` — no mocks |
| Unit (useOcupacion) | SWR key gating (auth), refreshInterval constant, dedupe interval, abort on unmount, stale flag | `vitest run src/features/operacion/hooks/useOcupacion.test.ts` with `vi.mock('swr')` + MSW |
| Unit (OcupacionStrip RTL) | Render with 2 chips, color by threshold, `data-stale="true"` on error, `aria-live` per chip | `vitest run src/renderer/components/OcupacionStrip.test.tsx` with SWR mock |
| E2E | Render strip via `_electron.launch` + `page.route` mock of `/operacion/ocupacion`; assert first paint; switch mock to return higher `activos`; wait ≤10s; assert new text appears | `npx playwright test e2e/operacion/ocupacion.spec.ts` |
| E2E (a11y) | axe-core WCAG 2.1 AA 0 violations on rendered strip | same suite, A1 scenario |

### Strict TDD Note

The orchestrator preflight flagged `strict_tdd: false` (skipped sdd-init refresh). This matches precedent in `src/features/auth/` and `src/features/caja/` — neither uses RED-GREEN-REFACTOR task sequences. Documented here so the apply phase does not introduce RED tasks. Future HUs that want strict TDD should add RED-task siblings explicitly.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary is touched. The renderer is a passive consumer of the local BFF via SWR + `parkosFetch`. The `AbortController` lifecycle is bounded by React's effect cleanup (no process boundary).

## Migration / Rollout

No migration required. No DB schema change. No backend change. The componente ships as a new file; it is mounted by `App.tsx` (or by `Dashboard.tsx` once F4.4 lands — out of scope here). Rollout is the standard Electron auto-update (DEC-SUC-18).

## Open Questions

- **None blocking.** All contracts verified. Backend endpoint mounted. Frontend precedent (F2.3 `<StatusBar />` polling pattern + F4.1 `useTiposVehiculo()` SWR fallback pattern) covers all decisions.
- **Future work**: F4.4 dashboard will mount the strip inside its own layout; F6.x ingreso may want a `compact` variant (chip-only, no legend). Out of scope here.

## i18n Keys (added to `operacion.json`)

```json
{
  "ocupacion_titulo": "Ocupación en vivo",
  "ocupacion_legend_green": "menos del 70% — hay cupo disponible",
  "ocupacion_legend_yellow": "entre 70% y 90% — acercarse al lleno",
  "ocupacion_legend_red": "más del 90% — casi lleno",
  "ocupacion_legend_stale": "dato desactualizado por falla de polling",
  "cupo_no_configurado": "cupo no configurado, contacte al administrador"
}
```
