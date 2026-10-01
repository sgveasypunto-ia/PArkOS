/**
 * `useTiposVehiculo()` — SWR hook para el catálogo de tipos de vehículo.
 *
 * Port del hook de ``apps/electron-sucursal/src/features/catalogos/hooks/
 * useTiposVehiculo.ts`` (HU-F4.1) — la diferencia es que acá usamos
 * ``parkosFetchRaw`` en lugar de un fetcher SWR propio (el hook de
 * electron usa ``getTiposVehiculo`` que ya envuelve parkosFetch).
 *
 * DEC-F4.1-04: deduping 5min, sin refreshInterval activo (catálogo
 * reference data, no realtime).
 *
 * DEC-F4.1-05: fallback hardcoded con sentinels UUID
 * ``00000000-0000-0000-0000-00000000000X`` (NO randomUUID — son
 * sentinels de FALLBACK, no IDs reales para sync). Degradación
 * explícita si la API está down: NUNCA pantalla rota.
 *
 * The 5 canonical tipos match the seed in migration
 * 0062_canonical_tipos_vehiculo (carro, moto, bicicleta, patineta,
 * otro). Backend enforces ``tipos_vehiculo_max_reached`` on the 6th
 * POST so the catalog never exceeds 5 active rows in production.
 *
 * 401 → useAuthStore.clear() + dispatch ``parkos:auth:cleared``
 * (logout defensivo, precedent F3.3).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { listTiposVehiculo, type TipoVehiculo } from '../api/tiposVehiculoApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

const HARDCODED_CATALOG: TipoVehiculo[] = [
  {
    uuid: '00000000-0000-0000-0000-000000000001',
    tipo: 'carro',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000002',
    tipo: 'moto',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000003',
    tipo: 'bicicleta',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000004',
    tipo: 'patineta',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-000000000005',
    tipo: 'otro',
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];

export interface UseTiposVehiculoReturn {
  tipos: TipoVehiculo[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<TipoVehiculo[] | undefined>;
  /** True cuando SWR está mostrando ``HARDCODED_CATALOG``. */
  isFromFallback: boolean;
}

export function useTiposVehiculo(): UseTiposVehiculoReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<TipoVehiculo[]>(
    accessToken ? '/api/v1/catalogos/tipos-vehiculo' : null,
    () => listTiposVehiculo({ limit: 200 }),
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
