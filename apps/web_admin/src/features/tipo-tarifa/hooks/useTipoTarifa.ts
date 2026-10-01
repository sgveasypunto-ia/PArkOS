/**
 * `useTipoTarifa()` — SWR hook para el catálogo de tipos de tarifa
 * (``hora | fraccion | plena | nocturna``).
 *
 * Same pattern as ``useTiposVehiculo``. Includes the hardcoded
 * fallback so the operator UI never renders a broken dropdown on API
 * outage.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { listTipoTarifa, type TipoTarifa } from '../api/tipoTarifaApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

const HARDCODED_CATALOG: TipoTarifa[] = [
  {
    uuid: '00000000-0000-0000-0000-000000000010',
    tipo: 'hora',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000011',
    tipo: 'fraccion',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000012',
    tipo: 'plena',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000013',
    tipo: 'nocturna',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];

export interface UseTipoTarifaReturn {
  tipos: TipoTarifa[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<TipoTarifa[] | undefined>;
  isFromFallback: boolean;
}

export function useTipoTarifa(): UseTipoTarifaReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<TipoTarifa[]>(
    accessToken ? '/api/v1/catalogos/tipo-tarifa' : null,
    () => listTipoTarifa({ limit: 200 }),
    {
      fallbackData: HARDCODED_CATALOG,
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
