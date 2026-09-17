# Proposal: HU-F4.2 — Tarifas vigentes (frontend)

## Intent

The operador must see the tarifa aplicable to the detected vehicle type, always the one currently in force at the exact moment of the query. Today the renderer has no hook to surface a tarifa; the only thing exposed in this surface is `useTiposVehiculo` (F4.1) and the kiosk-box formatters in `caja/lib/format.ts`. HU-F4.2 ships the client-side counterpart of the server-side HU-F1.4 (`GET /empresa/tarifas-sucursal?vigente_en=<ahora>`) — the cliente MUESTRA el valor, nunca lo calcula (DEC-SUC-12 verbatim).

This HU closes the operator-facing slice of catálogos (F4.1 = tipos de vehículo, F4.2 = tarifas, F4.3 = ocupación en vivo). It is the second reusable primitive of the `catalogos` feature.

## Scope

### In Scope

- New API wrapper `apps/electron-sucursal/src/features/catalogos/api/tarifasSucursalApi.ts` (`parkosFetch` against `GET /api/v1/empresa/tarifas-sucursal?vigente_en=...`).
- New SWR hook `apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.ts` with `dedupingInterval: 5*60*1000` and `fallbackData` hydrated from `electron-store` key `parkos.tarifas.cache.v1`.
- Presentational component `apps/electron-sucursal/src/features/catalogos/components/TarifaBadge.tsx` — shows `formatCOP(valor)`, marks "stale" if `fetchedAt > 1h`, wires `aria-describedby` for the stale mark (WCAG 2.1 AA / DEC-SUC-10).
- Reuse of the shipped `formatCOP` (`apps/electron-sucursal/src/features/caja/lib/format.ts`); no new formatter module — the plan.md T2 wording is informational and the existing function already matches the exact fixtures (`"$ 8.000"`, `"$ 1.234.567"`).
- Bridge IPC surface extension: `tarifasStore: { get, set, delete }` in `electron/bridge.d.ts` + `preload.ts` + `main.ts` (mirroring the existing `authStore` group; `auth-store:*` channels are already wired by F2.2 — the new group uses `tarifas-store:*` to keep namespaces clean).
- 4 unit tests (2 hook + 2 formatter fixtures). Plan.md T4 already constrains to the literal fixtures and the two hook cases (cache válido, invalidación tras cambio de tipo).

### Out of Scope

- Any backend change. `GET /api/v1/empresa/tarifas-sucursal?vigente_en=...` already exists (HU-F1.4, `backend/.../api/v1/empresa.py:179-213` + `repo/tarifas_vigencia.py::list_tarifas_vigentes`). HU-F1.4 is **closed**.
- CRUD of tarifas (Alta/Baja/Modificación de `tarifas_sucursal`). That is a Parte II / Admin-only story; out of scope for the operador Electron.
- Server-side calculation of the full cotización. The cliente receives `valor`/`valor_plena` and only displays them (DEC-SUC-12). El cálculo de tiempo de tarifa plena (`(valor_plena / valor) * unidad_minutos`, A-02) NO es responsabilidad del cliente.
- Persisting the tarifa value to IndexedDB. Only `electron-store` per DEC-SUC-05 ("electron-store para cache persistente entre reinicios").
- Any change to `tipos_vehiculo` (F4.1) or the ocupacion view (F4.3).

## Capabilities

### New Capabilities

- `catalogos`: cliente-side tarifa vigente surface for the operador — SWR hook + presentational badge + IPC bridge group for `electron-store` cache hydration.

### Modified Capabilities

- None. The backend capability `operations::REQ-OPS-019..020` (HU-F1.4 bi-temporal endpoint) is unchanged — F4.2 consumes it read-only.

## Approach

SWR hook reads from `parkos.tarifas.cache.v1` synchronously (via the new `tarifasStore.get` IPC channel) to seed `fallbackData` so the first paint shows a value even when the API is down. SWR then revalidates in the background and on success overwrites both the SWR cache and the `electron-store` entry (`onSuccess` → `tarifasStore.set`). Two consumers at minimum: the IngresoForm preview (F6.1 forward) and the Salida cotizador (F7.x forward). The `<TarifaBadge>` is presentational only — it receives `tarifa` + `fetchedAt` and computes the stale flag client-side.

The `vigente_en=<ahora>` filter is set client-side as the current UTC ISO-8601; HU-F1.4 honors it server-side. The dedicated handler returns the bi-temporal vigentes for the operator's branch (paginated `limit=50` covers the typical <20-row catalog; if the page exceeds 50 the hook falls back to a follow-up fetch with `next_cursor`). Filter by `uuid_tipo_vehiculo` happens client-side — the dedicated handler does NOT expose that query param (server-side filter exists in `TarifasSucursalFilter` and the helper, but the handler wires only `vigente_en`). Client-side filter on a paginated small set is consistent with the F4.1 `useTiposVehiculo` precedent (full catalog → consumer filters).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/features/catalogos/api/tarifasSucursalApi.ts` | New | `parkosFetch` wrapper. Reads `GET /api/v1/empresa/tarifas-sucursal?vigente_en=...`. Defensive filter of rows with `valor: null`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.ts` | New | SWR hook with `dedupingInterval: 5*60*1000`, `fallbackData: tarifasCacheSnapshot` (hydrated from `tarifasStore.get` at first paint via `useEffect`), and an `isFromFallback` flag. |
| `apps/electron-sucursal/src/features/catalogos/components/TarifaBadge.tsx` | New | Presentational badge. `aria-describedby` pointing to a hidden `id="tarifa-stale-help"` element when `fetchedAt > 1h`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.test.ts` | New | 2 tests: (a) cache válido sin red muestra fallback + stale false; (b) invalidación tras cambio de tipo. |
| `apps/electron-sucursal/electron/bridge.d.ts` | Modified | Adds `tarifasStore: { get(key), set(key, value), delete(key) }`. |
| `apps/electron-sucursal/electron/preload.ts` | Modified | Adds `tarifasStore: { get, set, delete }` invoking `tarifas-store:*` IPC channels. |
| `apps/electron-sucursal/electron/main.ts` | Modified | Adds `ipcMain.handle('tarifas-store:get', ...)`, `'tarifas-store:set'`, `'tarifas-store:delete'` backed by `electron-store`. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Client-side filter on `uuid_tipo_vehiculo` deviates from the AC literal endpoint signature (`?uuid_tipo_vehiculo=X&vigente_en=<ahora>`). | Low | Backend HU-F1.4 returns `TarifasSucursalRead[]` paginated by vigente; for a branch the catalog is small (<50 rows). Client-side filter on `uuid_tipo_vehiculo` returns the same value the AC describes; documented as a refinement gap, not a contract change. Follow-up PR may add the query param to the dedicated handler. |
| `electron-store` read at first paint is async (IPC) → flicker between "empty" and "cached". | Low | `fallbackData` accepts a synchronous shape; we hydrate via `useState` + `useEffect` so the FIRST render shows `null` (badge hidden) and the SECOND render shows the cached value. UI rule: if `tarifa === null`, badge hidden — not "stale" — to avoid the operator seeing a wrong number during hydration. |
| Stale-mark UX confusion — operador cannot tell if the value is wrong or just old. | Medium | i18n key `catalogos.tarifa_desactualizada` literal: "Tarifa cacheada — verifica con el supervisor". Clear copy, supervisor-friendly tone. |
| Reusing `formatCOP` from `caja/lib/format.ts` couples catalogos to caja's internal folder layout. | Low | Plan.md T2 wording is informational; F3.3 JSDoc already flags the function as F4.x+ forward-compatible (`formatCOP` is pure currency, not caja-specific). If F4.x+ needs a neutral home, relocation is a 1-PR follow-up — not in scope for this HU. |

## Rollback Plan

Delete `apps/electron-sucursal/src/features/catalogos/api/tarifasSucursalApi.ts`, `hooks/useTarifasVigentes.ts`, `components/TarifaBadge.tsx`, and `hooks/useTarifasVigentes.test.ts`. Revert the three IPC files (`bridge.d.ts`, `preload.ts`, `main.ts`) to remove the `tarifasStore` group. Wipe the `parkos.tarifas.cache.v1` key from electron-store on next boot (no DB migration, no backend change, no other consumer depends on this surface yet — F4.3/OcupacionStrip ships later).

## Dependencies

- `parkosFetch` (`@parkos/ui-kit/fetch`) — already shipped (F2.x).
- `useAuthStore` (`@parkos/ui-kit/store`) — already shipped (F2.2).
- `formatCOP` (`apps/electron-sucursal/src/features/caja/lib/format.ts`) — already shipped (F3.3).
- Backend endpoint `GET /api/v1/empresa/tarifas-sucursal?vigente_en=...` — already shipped (HU-F1.4, `backend/.../api/v1/empresa.py:179-213`). **HU-F1.4 closed.** Not a blocker.

## Success Criteria

- [ ] `vitest run src/features/catalogos/hooks/useTarifasVigentes.test.ts` exits 0 (2 hook tests).
- [ ] `vitest run src/features/caja/lib/format.test.ts` exits 0 (2 formatCOP fixture tests: `$ 8.000`, `$ 1.234.567`).
- [ ] `<TarifaBadge>` renders the cached value on cold start when `api-sucursal` is down; after 1h shows the stale mark with `aria-describedby` set.
- [ ] `electron/preload.contract.test.ts` passes with the new `tarifasStore` group in the surface.
- [ ] No file outside `openspec/changes/fase-4-2-tarifas-vigentes/` and Engram was modified.
- [ ] No `react-i18next` key required for v1 (badge copies are inline literals — es-CO only); F8+ may extract to i18n if a third locale is requested.