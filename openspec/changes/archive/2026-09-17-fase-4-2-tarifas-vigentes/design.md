# Design: HU-F4.2 — Tarifas vigentes (frontend)

## Technical Approach

Cliente-side surface mirroring HU-F1.4. SWR hook with `fallbackData` hydrated from `electron-store` via a new IPC bridge group (`tarifasStore`), so the first paint shows a cached value when the local `api-sucursal` is unreachable. Presentational `<TarifaBadge>` is the only consumer-facing artifact — receives `tarifa` + `fetchedAt`, derives `isStale` client-side. `formatCOP` is reused (no new formatter).

## Architecture Decisions

### Decision: IPC bridge group `tarifasStore` (parallel to `authStore`)

**Choice**: Add `tarifasStore: { get, set, delete }` to `window.bridge`, mapped to IPC channels `tarifas-store:get/set/delete`, backed by the existing `electron-store` instance in the main process.

**Alternatives considered**:
- Reuse the `authStore` group (passing non-`parkos.auth` keys through it). Rejected: namespace pollution; the bridge surface documents semantic groups, and `authStore` is reserved for JWT tokens.
- Direct `window.electronAPI` exposure. Rejected: violates DEC-FETCH-08 (whitelist-only bridge, no `ipcRenderer` spread).
- IndexedDB persistence. Rejected: DEC-SUC-05 reserves IndexedDB for sync queues; `electron-store` is the cross-restart cache for catálogos.

**Rationale**: Mirrors the existing `authStore` pattern 1:1 (`preload.ts:43-47` → `main.ts` handler), keeps renderer code identical (`@parkos/ui-kit/store/authStore.ts:36-53` adapter shape), no new infrastructure. Adds 3 IPC channels in the whitelist — surfaced in `electron/__tests__/preload.contract.test.ts`.

### Decision: Sync `fallbackData` via two-phase render

**Choice**: First render of `useTarifasVigentes()` returns `tarifa: null` (badge hidden); an `useEffect` reads `tarifasStore.get('parkos.tarifas.cache.v1')` and, if present, calls `mutate(snapshot)` to seed `fallbackData`. Second render shows the cached value.

**Alternatives considered**:
- Block the first render until `tarifasStore.get` resolves (Suspense). Rejected: SWR v2 + Suspense doubles the boilerplate for a single key; the cache hit is a cold-start-only optimization.
- Read the cache synchronously at module top-level. Rejected: IPC is async; a synchronous read would require a preloaded `electron-store` value into a JS module, which the existing `authStore` does NOT do (it relies on `persist` middleware re-hydration).
- Return `tarifa: <stale-cache>` from the start. Rejected: violates the spec — operator must never see an uncorroborated number during the hydration window.

**Rationale**: Two-phase render + `tarifa === null` (badge hidden) is the simplest contract that honors both "no pantalla vacía when cache exists" (plan.md AC) AND "no number during hydration" (spec). Operator UX: badge appears within ≤100ms after `useEffect` on the same tick — perceptually instant.

### Decision: Client-side filter on `uuid_tipo_vehiculo`

**Choice**: The hook fetches `GET /api/v1/empresa/tarifas-sucursal?vigente_en=<now>` (returns ALL vigentes for the branch) and filters the array in JS to find the row matching `uuid_tipo_vehiculo`.

**Alternatives considered**:
- Add `?uuid_tipo_vehiculo=X` as a query param on the dedicated handler. Rejected for v1: the plan.md AC specifies that exact signature, but the backend HU-F1.4 handler (`empresa.py:179-213`) does NOT wire `uuid_tipo_vehiculo` to the handler signature (the helper accepts it via `TarifasSucursalFilter`, but the handler binds only `vigente_en`). Adding the param is a backend change out of F4.2 scope; documented as a follow-up risk.
- Two API calls (one for auto, one for moto). Rejected: duplicates traffic; SWR dedupes by key.

**Rationale**: For a single branch the dataset is <50 rows; client-side filter is O(n) on a paginated list — negligible. Matches the F4.1 `useTiposVehiculo` precedent (full catalog → consumer filters). The result the operator sees is identical to what `?uuid_tipo_vehiculo=X` would return.

## Data Flow

```
TarifaBadge (props: uuidTipoVehiculo)
    │
    └─ useTarifasVigentes(uuidTipoVehiculo)
         │
         ├─[first render]─ useAuthStore.getState().accessToken → SWR key
         │                  fallbackData: null (tarifa === null → badge hidden)
         │
         ├─[useEffect post-mount]─ bridge.tarifasStore.get('parkos.tarifas.cache.v1')
         │                          └─ if present → mutate(snapshot)
         │                          └─ re-render: tarifa = <cache hit>
         │
         ├─[SWR fetch]─ parkosFetch('/api/v1/empresa/tarifas-sucursal?vigente_en=<now>')
         │              └─ 200 → filter by uuid_tipo_vehiculo → tarifa = match
         │              └─ onSuccess → bridge.tarifasStore.set('parkos.tarifas.cache.v1', { items, fetchedAt: Date.now() })
         │              └─ 5xx / network → keep cache → tarifa = <cache or null>
         │
         └─[TarifaBadge render]
              ├─ tarifa === null    → hidden (no value to display)
              ├─ isStale === true   → render value + "Tarifa cacheada — verifica con el supervisor" badge + aria-describedby="tarifa-stale-help"
              └─ isStale === false  → render value + plain badge
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/features/catalogos/api/tarifasSucursalApi.ts` | Create | `parkosFetch` wrapper. Reads `GET /api/v1/empresa/tarifas-sucursal?vigente_en=<now-utc>`. Defensive filter of rows with `valor: null`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.ts` | Create | SWR hook with `dedupingInterval: 5*60*1000`, two-phase render, `isStale` derived from `Date.now() - fetchedAt > 3600_000`. |
| `apps/electron-sucursal/src/features/catalogos/components/TarifaBadge.tsx` | Create | Presentational. Receives `tarifa: TarifaVigente | null` and `fetchedAt: number | null`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.test.ts` | Create | 2 hook tests + 2 formatCOP fixtures (re-exported from `caja/lib/format.test.ts` is acceptable OR co-located if reviewer prefers; we co-locate to keep the file standalone). |
| `apps/electron-sucursal/electron/bridge.d.ts` | Modify | Adds `tarifasStore: { get(key), set(key, value), delete(key) }`. |
| `apps/electron-sucursal/electron/preload.ts` | Modify | Adds `tarifasStore` invoking `tarifas-store:*` IPC channels. |
| `apps/electron-sucursal/electron/main.ts` | Modify | Adds 3 `ipcMain.handle` for `tarifas-store:get/set/delete` backed by the same `electron-store` instance. |

## Interfaces / Contracts

```typescript
// apps/electron-sucursal/src/features/catalogos/api/tarifasSucursalApi.ts
import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

export interface TarifaSucursalRead {
  uuid: string;
  uuid_sucursal: string | null;
  uuid_tipo_vehiculo: string | null;
  uuid_tipo_tarifa: string | null;
  valor: number | null;        // NUMERIC(18,4) → JS number via parkosFetch JSON.parse
  valor_plena: number | null;
  vigente_desde: string;       // ISO-8601
  vigente_hasta: string | null;
  estado: string;
  created_at: string;
  created_by: string | null;
  sync_status: string | null;
}

export interface TarifasSucursalReadList {
  items: TarifaSucursalRead[];
  next_cursor: string | null;
}

const TARIFAS_PATH = '/api/v1/empresa/tarifas-sucursal';

export async function listTarifasSucursal(
  vigenteEn: Date = new Date(),
  cursor?: string,
): Promise<TarifasSucursalReadList> {
  const params = new URLSearchParams({ vigente_en: vigenteEn.toISOString() });
  if (cursor) params.set('cursor', cursor);
  try {
    return await parkosFetch<TarifasSucursalReadList>(
      `${TARIFAS_PATH}?${params.toString()}`,
    );
  } catch (err) {
    if (err instanceof ParkosHttpError && err.status === 404) {
      return { items: [], next_cursor: null };
    }
    throw err;
  }
}
```

```typescript
// apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.ts
import useSWR from 'swr';
import { useEffect, useState } from 'react';
import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { listTarifasSucursal, type TarifaSucursalRead } from '../api/tarifasSucursalApi';

const CACHE_KEY = 'parkos.tarifas.cache.v1';
const SWR_KEY = '/empresa/tarifas-sucursal';
const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;
const STALE_THRESHOLD_MS = 60 * 60 * 1000;

interface TarifasCacheSnapshot {
  items: TarifaSucursalRead[];
  fetchedAt: number;
}

export interface TarifaVigente extends TarifaSucursalRead {}

export interface UseTarifasVigentesReturn {
  tarifa: TarifaVigente | null;
  fetchedAt: number | null;
  isStale: boolean;
  isFromFallback: boolean;
  refresh: () => Promise<void>;
}

export function useTarifasVigentes(uuidTipoVehiculo: string): UseTarifasVigentesReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [cacheHydrated, setCacheHydrated] = useState<TarifasCacheSnapshot | null>(null);

  // Two-phase render: hydrate electron-store cache into fallbackData on mount.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const raw = await window.bridge.tarifasStore.get(CACHE_KEY);
      if (cancelled) return;
      if (raw) {
        try {
          setCacheHydrated(JSON.parse(raw) as TarifasCacheSnapshot);
        } catch { /* corrupt cache — ignore */ }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const { data, error, isLoading, mutate } = useSWR<TarifasCacheSnapshot>(
    accessToken ? SWR_KEY : null,
    async () => {
      const res = await listTarifasSucursal();
      return { items: res.items, fetchedAt: Date.now() };
    },
    {
      fallbackData: cacheHydrated ?? undefined,
      dedupingInterval: DEDUPING_INTERVAL_MS,
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && err.status === 404),
      onSuccess: async (snapshot) => {
        await window.bridge.tarifasStore.set(CACHE_KEY, JSON.stringify(snapshot));
      },
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
        }
      },
    },
  );

  const snapshot = data;
  const tarifa = snapshot?.items.find((t) => t.uuid_tipo_vehiculo === uuidTipoVehiculo) ?? null;
  const fetchedAt = snapshot?.fetchedAt ?? null;
  const isStale = fetchedAt !== null && Date.now() - fetchedAt > STALE_THRESHOLD_MS;
  const isFromFallback = snapshot === cacheHydrated && !isLoading;

  return {
    tarifa,
    fetchedAt,
    isStale,
    isFromFallback,
    refresh: async () => { await mutate(); },
  };
}
```

```typescript
// apps/electron-sucursal/src/features/catalogos/components/TarifaBadge.tsx
import { formatCOP } from '../../../caja/lib/format';
import type { TarifaVigente } from '../hooks/useTarifasVigentes';

const STALE_HELP_ID = 'tarifa-stale-help';

export interface TarifaBadgeProps {
  tarifa: TarifaVigente | null;
  fetchedAt: number | null;
  isStale: boolean;
}

export function TarifaBadge({ tarifa, fetchedAt, isStale }: TarifaBadgeProps) {
  if (tarifa === null) return null;

  const ariaProps = isStale
    ? { 'aria-describedby': STALE_HELP_ID }
    : {};

  return (
    <div className="tarifa-badge" {...ariaProps}>
      <span className="tarifa-badge__value">{formatCOP(Number(tarifa.valor))}</span>
      {isStale && (
        <span className="tarifa-badge__stale-mark" role="status">
          Tarifa cacheada — verifica con el supervisor
        </span>
      )}
      {isStale && (
        <span id={STALE_HELP_ID} className="sr-only">
          La tarifa mostrada fue obtenida hace más de una hora y el sistema no ha
          podido confirmar el valor actual. Pida al supervisor que confirme el
          monto antes de cobrar.
        </span>
      )}
    </div>
  );
}
```

```typescript
// apps/electron-sucursal/electron/bridge.d.ts (diff)
export interface BridgeSurface {
  // ... existing methods ...
  tarifasStore: {
    get(key: string): Promise<string | null>;
    set(key: string, value: string): Promise<void>;
    delete(key: string): Promise<void>;
  };
}
```

```typescript
// apps/electron-sucursal/electron/preload.ts (diff)
contextBridge.exposeInMainWorld('bridge', {
  // ... existing groups ...
  tarifasStore: {
    get: (key) => ipcRenderer.invoke('tarifas-store:get', key),
    set: (key, value) => ipcRenderer.invoke('tarifas-store:set', key, value),
    delete: (key) => ipcRenderer.invoke('tarifas-store:delete', key),
  },
});
```

```typescript
// apps/electron-sucursal/electron/main.ts (diff inside registerIpcHandlers)
ipcMain.handle('tarifas-store:get', (_e, key: string) =>
  tarifasStore.get(key).then((v) => (typeof v === 'string' ? v : v == null ? null : JSON.stringify(v))),
);
ipcMain.handle('tarifas-store:set', (_e, key: string, value: string) =>
  tarifasStore.set(key, value),
);
ipcMain.handle('tarifas-store:delete', (_e, key: string) =>
  tarifasStore.delete(key),
);
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit (hook) | cache válido, invalidación tras cambio de tipo | vi.mock the `bridge.tarifasStore` adapter + vi.mock `swr`. Same pattern as `useTiposVehiculo.test.ts`. |
| Unit (formatter fixtures) | `formatCOP(8000) === "$ 8.000"` and `formatCOP(1234567) === "$ 1.234.567"` | Re-run `src/features/caja/lib/format.test.ts` (already ships the fixtures — they pass verbatim). |
| Bridge contract | `tarifasStore` group exposed + invokes `tarifas-store:*` channels | Extend `electron/__tests__/preload.contract.test.ts` with 4 new assertions (group presence + 3 channel invokes). |
| WCAG | `<TarifaBadge>` stale state has `aria-describedby` linked to the help text | Add an axe-core assertion in the badge's RTL test (snapshot test in `hooks/useTarifasVigentes.test.ts` not necessary — the helper pattern is "snapshot=helper" pattern, badge test runs separately if needed). |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The only process boundary is the IPC `tarifas-store:*` channels (handled by the existing whitelist pattern at `electron/preload.ts:24-47`), which `preload.contract.test.ts` enforces in CI.

## Migration / Rollout

No migration required. All artifacts are additive:
- New IPC channels added to the bridge whitelist (no rename).
- New electron-store key `parkos.tarifas.cache.v1` is created lazily on first SWR success (no pre-seed).
- No DB migration. No backend change. No i18n key extraction (es-CO literals inline).

Rollback: delete the 3 new renderer files + revert the 3 IPC files. No data migration in reverse (the `parkos.tarifas.cache.v1` key becomes orphan but inert).

## Open Questions

None. The HU-F1.4 endpoint contract is fixed (`vigente_en` only on the dedicated handler; client-side `uuid_tipo_vehiculo` filter is the documented refinement). The bridge pattern is precedent (`authStore`). `formatCOP` is shipped.

## Strict TDD Note

Per session preflight, `strict_tdd: false` for this change (contingent on a deferred `sdd-init` refresh). The apply phase will write tests alongside the implementation (RED → GREEN in the same commit per task), not strictly RED-first. The 2 hook tests + 2 formatter fixtures are still required by plan.md T4.

## Reused Code Inventory

| Source | Where | Reused as |
|--------|-------|-----------|
| `formatCOP` | `apps/electron-sucursal/src/features/caja/lib/format.ts:31` | Direct import in `<TarifaBadge>`. No copy-paste. |
| `useAuthStore` | `@parkos/ui-kit/store` | Access-token gate + 401 logout handler (precedent F4.1). |
| `parkosFetch` | `@parkos/ui-kit/fetch` | HTTP wrapper (precedent F4.1). |
| `ParkosHttpError` | `@parkos/ui-kit/fetch` | 401 / 404 / 5xx discrimination (precedent F4.1). |
| SWR dedupingInterval 5min | plan.md:1375 (F4.1 DEC verbatim) | Same constant for F4.2 catálogos. |
| Bridge preload pattern | `electron/preload.ts:24-47` | Mirrored 1:1 for `tarifasStore`. |
| Bridge `authStore` group | `electron/bridge.d.ts:75-82` | Mirrored type shape for `tarifasStore`. |