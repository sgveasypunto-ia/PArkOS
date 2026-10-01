/**
 * `useTarifasByKey()` — SWR hook que recorre la cadena bi-temporal de
 * versiones de una tarifa por business key (sucursal, tipo_vehiculo,
 * tipo_tarifa), reemplazando el agujero histórico del factory
 * ``GET /{uuid}/history`` que filtra por uuid y pierde la versión
 * nueva del close+insert (PR-C v2 fills that gap).
 *
 * Patrón copy-paste de ``useTiposVehiculo`` (apps/electron-sucursal,
 * HU-F4.1):
 *
 * - DEC-F4.1-04: ``dedupingInterval: 5min`` para catálogos reference
 *   data. Sin ``refreshInterval`` activo — la tarifa cambia cuando el
 *   admin publica un PUT, no en tiempo real.
 * - 401 → ``useAuthStore.getState().clear()`` + dispatch
 *   ``parkos:auth:cleared`` (logout defensivo; precedent F3.3).
 * - 404 (UUID desconocido del by-key) NO reintenta — estado válido
 *   cuando el admin aún no publicó nada para esa key.
 *
 * El parámetro ``sucursal`` es requerido (la key sin sucursal no tiene
 * sentido). ``tipo_vehiculo`` y ``tipo_tarifa`` son opcionales porque
 * el factory y el helper ``list_tarifas_vigentes`` aceptan ambos como
 * NULL.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { listTarifasByKey, type Tarifa } from '../api/tarifasApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseTarifasByKeyReturn {
  versiones: Tarifa[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Tarifa[] | undefined>;
}

export function useTarifasByKey(
  sucursal: string | null,
  tipo_vehiculo?: string | null,
  tipo_tarifa?: string | null,
): UseTarifasByKeyReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const key =
    accessToken && sucursal
      ? ['/api/v1/empresa/tarifas-sucursal/by-key', sucursal, tipo_vehiculo ?? null, tipo_tarifa ?? null]
      : null;

  const { data, error, isLoading, mutate } = useSWR<Tarifa[]>(
    key,
    async () => {
      if (!sucursal) return [];
      return listTarifasByKey({ sucursal, tipo_vehiculo, tipo_tarifa });
    },
    {
      dedupingInterval: DEDUPING_INTERVAL_MS,
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
    versiones: data ?? [],
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? [];
    },
  };
}
