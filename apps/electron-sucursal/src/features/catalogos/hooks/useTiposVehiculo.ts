/**
 * `useTiposVehiculo()` — SWR hook para el catálogo de tipos de vehículo
 * (HU-F4.1, T2 — primer hook genuinely reusable del feature `catalogos`).
 *
 * Forward consumers (no F4.1 scope, pero el hook los habilita):
 *   - F4.2 `useTarifasVigentes` peer hook (mismo pattern, electron-store).
 *   - F4.3 `<OcupacionStrip>` itera sobre tipos del catálogo.
 *   - F6.1 `<PlacaInput>` consume `detectarTipoVehiculo()` + este hook.
 *   - F11.x sync UI invalida cache con `mutate(key)` post-sync.
 *
 * DEC-F4.1-04 verbatim (plan.md:1375): `dedupingInterval: 5 * 60 * 1000`
 * — catálogos reference data, NO `refreshInterval` (cambian raramente,
 * el operador no espera actualización en tiempo real). 5min vs los 10s
 * de `useSesionActiva` (F3.3) refleja que la sesión puede cambiar de
 * estado durante el turno, mientras que el catálogo NO.
 *
 * DEC-F4.1-05 verbatim (plan.md:1375): `fallbackData: HARDCODED_CATALOG`
 * con `{auto, moto}` + UUIDs sentinels LITERALES (NO `crypto.randomUUID()`
 * — son sentinels de FALLBACK, no IDs reales para sync). Degradación
 * explícita si la API está down — NUNCA pantalla rota.
 *
 * DEC-F4.1-06 verbatim: `isFromFallback: boolean` flag derivado por
 * comparación de REFERENCIA (`data === HARDCODED_CATALOG`, NO deep-equal).
 * Forward F4.3 + F6.x pueden mostrar `<Tooltip>` "usando datos locales"
 * cuando `isFromFallback === true`.
 *
 * Precedente verbatim F3.3 `useSesionActiva` (REQ-OPS-120):
 *   - SWR key `accessToken ? '/catalogos/tipos-vehiculo' : null`
 *     (gate contra 401 noise pre-login — cold boot sin token).
 *   - `shouldRetryOnError` excluye 404 (catálogo vacío válido).
 *   - `onError` con `status === 401` dispara `useAuthStore.clear()` +
 *     `window.dispatchEvent(new Event('parkos:auth:cleared'))`
 *     (precedent F3.3 — logout defensivo, forward hook AuthGuard F4.x+).
 *
 * Defense in depth XR6 layer 5 (retry-budget, F2.2 invariant preserved):
 * NO extiende `PRE_FLIGHT_PATHS` — `/catalogos/*` GET read idempotente
 * NO requiere pre-flight gate (DEC-SUC-03 + F3.2 verbatim).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { getTiposVehiculo, type TipoVehiculo } from '../api/tiposVehiculoApi';

/** SWR key — debe matchear el path backend para deduping compartido. */
const TIPOS_VEHICULO_KEY = '/catalogos/tipos-vehiculo';
/** DEC-F4.1-04: 5min para catálogos reference data (plan.md:1375 verbatim). */
const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

/**
 * Fallback hardcoded `{auto, moto}` con UUIDs sentinels literales
 * (DEC-F4.1-05 — NO `crypto.randomUUID()`). Sentinels son identificadores
 * de FALLBACK, no IDs reales para sync. Inline en este módulo para
 * cohesión con el hook que la usa (no archivo separado).
 *
 * Shape matchea `TipoVehiculo` (backend `TiposVehiculoRead`). Las fechas
 * son fijas (no se actualizan en runtime) porque este fallback es
 * estático entre builds.
 */
const HARDCODED_CATALOG: TipoVehiculo[] = [
  {
    uuid: '00000000-0000-0000-0000-000000000001',
    tipo: 'carro',
    vigente_desde: '2026-01-01T00:00:00Z',
    vigente_hasta: null,
    estado: 'activo',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000002',
    tipo: 'moto',
    vigente_desde: '2026-01-01T00:00:00Z',
    vigente_hasta: null,
    estado: 'activo',
  },
];

export interface UseTiposVehiculoReturn {
  tipos: TipoVehiculo[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<TipoVehiculo[] | undefined>;
  /** True cuando SWR está mostrando `HARDCODED_CATALOG` (API down o no auth). */
  isFromFallback: boolean;
}

/**
 * Hook SWR para el catálogo de tipos de vehículo.
 *
 * DEGRADACIÓN EXPLÍCITA: si la API falla (5xx, network) o si el operador
 * no está autenticado (key null), el hook retorna `HARDCODED_CATALOG` y
 * `isFromFallback: true`. Consumers futuros (F4.3 + F6.x) pueden mostrar
 * `<Tooltip>` "usando datos locales" en función de ese flag.
 *
 * NO `refreshInterval` activo — `dedupingInterval` 5min evita refetch
 * entre consumers concurrentes (`<PlacaInput>` F6.1 + `<OcupacionStrip>`
 * F4.3 + futuras pantallas). Próximo refresh al cerrar/abrir turno o
 * al expirar el deduping window.
 */
export function useTiposVehiculo(): UseTiposVehiculoReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<TipoVehiculo[]>(
    accessToken ? TIPOS_VEHICULO_KEY : null,
    () => getTiposVehiculo(),
    {
      fallbackData: HARDCODED_CATALOG,
      dedupingInterval: DEDUPING_INTERVAL_MS,
      // 404 = catálogo vacío (sucursal nueva) — estado válido, no retry.
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && err.status === 404),
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

  return {
    tipos: data ?? HARDCODED_CATALOG,
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? HARDCODED_CATALOG;
    },
    isFromFallback: data === undefined || data === HARDCODED_CATALOG,
  };
}
