/**
 * `useTarifasVigentes()` — SWR hook para el catálogo de tarifas vigentes
 * por sucursal (HU-F4.2 — T3, segundo hook genuinely reusable del feature
 * `catalogos`).
 *
 * Forward consumers (no F4.2 scope, pero el hook los habilita):
 *   - F4.3 `<OcupacionStrip>` puede usar `useTarifasVigentes` para mostrar
 *     la tarifa de cada tipo de vehículo al lado del chip de ocupación.
 *   - F6.1 `<PlacaInput>` consume `detectarTipoVehiculo()` (F4.1) + este
 *     hook para mostrar la tarifa aplicable después de detectar el tipo.
 *   - F7.x cotizador de salida consume la misma instancia de SWR cache.
 *   - F11.x sync UI invalida cache con `mutate(key)` post-sync.
 *
 * DEC-F4.2-01 verbatim (cache key + electron-store namespace):
 * el snapshot hidratado al first-paint vive bajo
 * `parkos.tarifas.cache.v1` en `electron-store`. El IPC bridge group
 * `tarifasStore: { get, set, delete }` (F4.2 — T1) expone esa key al
 * renderer; aquí leemos y escribimos vía `window.bridge.tarifasStore`.
 *
 * DEC-F4.2-02 verbatim (two-phase render): el primer render retorna
 * `tarifa: null` (badge oculto). Un `useEffect` lee `tarifasStore.get`
 * async y, si está presente, llama `setCacheHydrated(...)` para
 * sembrar `fallbackData`. El segundo render muestra el valor cacheado.
 * El operador NUNCA ve un número sin corroborar durante la hidratación
 * (riesgo abierto en design.md §Data Flow, mitigado por badge-hidden rule).
 *
 * DEC-F4.2-04 verbatim (404 → empty state): `shouldRetryOnError` excluye
 * 404 (sucursal sin tarifas — estado válido, NO retry spam). El handler
 * `tarifasSucursalApi.ts:listTarifasSucursal` ya convierte 404 a
 * `{items:[], next_cursor:null}`.
 *
 * DEC-F4.2-05 verbatim (5min deduping): `dedupingInterval: 5 * 60 * 1000`
 * — catálogos reference data, NO `refreshInterval`. 5min vs los 10s de
 * `useSesionActiva` (F3.3) refleja que la sesión puede cambiar de
 * estado durante el turno, mientras que el catálogo NO.
 *
 * DEC-F4.2-06 verbatim (1h stale threshold): `isStale` se deriva
 * client-side como `Date.now() - fetchedAt > 60 * 60 * 1000`. Cuando
 * `true`, `<TarifaBadge>` muestra el stale-mark + aria-describedby
 * (DEC-SUC-10 WCAG 2.1 AA, F4.2 — T5).
 *
 * Documented refinement (client-side filter on `uuid_tipo_vehiculo`):
 * el hook fetcha TODOS los vigentes para la sucursal y filtra en JS.
 * El handler backend `empresa.py:179-213` NO expone `uuid_tipo_vehiculo`
 * como query param; el helper acepta el filtro pero la firma del
 * handler no lo wirea. Para catálogos <50 rows la operación es O(n)
 * despreciable. Follow-up PR puede agregar el query param al handler.
 *
 * Defense in depth XR6 layer 5 (retry-budget, F2.2 invariant preserved):
 * NO extiende `PRE_FLIGHT_PATHS` — `/empresa/*` GET read idempotente
 * NO requiere pre-flight gate (DEC-SUC-03 + F3.2 verbatim).
 *
 * Precedente verbatim F4.1 `useTiposVehiculo` + F3.3 `useSesionActiva`:
 *   - SWR key `accessToken ? '/empresa/tarifas-sucursal' : null` (gate
 *     contra 401 noise pre-login — cold boot sin token).
 *   - `shouldRetryOnError` excluye 404.
 *   - `onError` con `status === 401` dispara `useAuthStore.clear()` +
 *     `window.dispatchEvent(new Event('parkos:auth:cleared'))` (logout
 *     defensivo, forward hook AuthGuard F4.x+).
 */
import useSWR from 'swr';
import { useEffect, useState } from 'react';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  listTarifasSucursal,
  type TarifaSucursalRead,
} from '../api/tarifasSucursalApi';

/** Cache key — debe matchear el namespace electron-store F4.2 (T1). */
const CACHE_KEY = 'parkos.tarifas.cache.v1';
/** SWR key — path-only (sin query) para deduping compartido entre consumers. */
const SWR_KEY = '/empresa/tarifas-sucursal';
/** DEC-F4.2-05: 5min para catálogos reference data (plan.md:1375 verbatim). */
const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;
/** DEC-F4.2-06: stale threshold 1h — marca "tarifa cacheada" en UI. */
const STALE_THRESHOLD_MS = 60 * 60 * 1000;

/**
 * Snapshot persistido en `parkos.tarifas.cache.v1`.
 * `items` es el `TarifasSucursalRead[]` completo (no solo el filtrado)
 * para que un cambio de `uuid_tipo_vehiculo` no fuerce refetch.
 */
interface TarifasCacheSnapshot {
  items: TarifaSucursalRead[];
  fetchedAt: number;
}

/** Tipo expuesto al consumidor — alias de `TarifaSucursalRead`. */
export type TarifaVigente = TarifaSucursalRead;

export interface UseTarifasVigentesReturn {
  /** Tarifa para el `uuid_tipo_vehiculo` dado, o `null` si no hay match. */
  tarifa: TarifaVigente | null;
  /** Epoch ms del último fetch exitoso; `null` si nunca se fetcheó. */
  fetchedAt: number | null;
  /** `true` cuando `Date.now() - fetchedAt > 1h` (caché expirada). */
  isStale: boolean;
  /** `true` cuando la UI está mostrando el snapshot del electron-store
   *  (cache offline) en lugar del fetch fresco del backend. */
  isFromFallback: boolean;
  /** Forzar revalidación contra la API (SWR `mutate`). */
  refresh: () => Promise<void>;
}

/**
 * Hook SWR para la tarifa vigente de un tipo de vehículo en la sucursal
 * del operador.
 *
 * Two-phase render (DEC-F4.2-02): primer render `tarifa === null` (badge
 * oculto). `useEffect` post-mount lee `parkos.tarifas.cache.v1` y siembra
 * `fallbackData`. Segundo render muestra el valor cacheado sin esperar
 * a la red. SWR revalida en background; en `onSuccess` persiste el nuevo
 * snapshot en `electron-store`.
 *
 * NO `refreshInterval` activo — `dedupingInterval` 5min evita refetch
 * entre consumers concurrentes. Próximo refresh al cerrar/abrir turno
 * o al expirar el deduping window.
 */
export function useTarifasVigentes(uuidTipoVehiculo: string): UseTarifasVigentesReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [cacheHydrated, setCacheHydrated] = useState<TarifasCacheSnapshot | null>(null);

  // DEC-F4.2-02: two-phase render — hydrate electron-store cache into
  // `fallbackData` on mount. First render shows `tarifa === null` (badge
  // hidden); second render shows the cached value.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const raw = await window.bridge.tarifasStore.get(CACHE_KEY);
      if (cancelled) return;
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as TarifasCacheSnapshot;
          if (
            parsed &&
            Array.isArray(parsed.items) &&
            typeof parsed.fetchedAt === 'number'
          ) {
            setCacheHydrated(parsed);
          }
        } catch {
          /* corrupt cache — ignore and start fresh */
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const { data, isLoading, mutate } = useSWR<TarifasCacheSnapshot>(
    accessToken ? SWR_KEY : null,
    async () => {
      const res = await listTarifasSucursal();
      return { items: res.items, fetchedAt: Date.now() };
    },
    {
      fallbackData: cacheHydrated ?? undefined,
      dedupingInterval: DEDUPING_INTERVAL_MS,
      // 404 = sucursal sin tarifas configuradas — estado válido, NO retry.
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && err.status === 404),
      onSuccess: async (snapshot) => {
        await window.bridge.tarifasStore.set(
          CACHE_KEY,
          JSON.stringify(snapshot),
        );
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

  // Client-side filter (documented refinement vs AC literal — see header).
  const snapshot = data;
  const tarifa =
    snapshot?.items.find((t) => t.uuid_tipo_vehiculo === uuidTipoVehiculo) ?? null;
  const fetchedAt = snapshot?.fetchedAt ?? null;
  const isStale =
    fetchedAt !== null && Date.now() - fetchedAt > STALE_THRESHOLD_MS;
  // Fallback visible cuando el snapshot actual coincide con el cache hydrated
  // Y no hay un fetch fresco en curso (data estable).
  const isFromFallback =
    snapshot !== undefined && snapshot === cacheHydrated && !isLoading;

  return {
    tarifa,
    fetchedAt,
    isStale,
    isFromFallback,
    refresh: async () => {
      await mutate();
    },
  };
}
