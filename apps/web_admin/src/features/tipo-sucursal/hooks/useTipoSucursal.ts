/**
 * `useTipoSucursal()` — SWR hook para el catálogo de tipos de sucursal.
 *
 * Mirror de `useTiposVehiculo` y `useTipoTarifa`. Sentinels UUID
 * deterministas en `HARDCODED_CATALOG` para que la UI nunca muestre
 * pantalla rota si la API cae (mismo patrón DEC-F4.1-05 del hook
 * de tipos de vehiculo).
 *
 * Solo se consume en lectura desde `web_admin` (auto-fill de
 * `sucursal.uuid_tipo_sucursal` al crear). El CRUD del catalogo se
 * siembra por Alembic (migration 0060), no por UI.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { listTipoSucursal, type TipoSucursal } from '../api/tipoSucursalApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

const HARDCODED_CATALOG: TipoSucursal[] = [
  {
    uuid: '00000000-0000-0000-0000-00000000c001',
    codigo: 'propia',
    nombre: 'Sucursal propia',
    descripcion:
      'Sucursal operada directamente por el propietario del parqueo.',
    caracteristicas: null,
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
  {
    uuid: '00000000-0000-0000-0000-00000000c002',
    codigo: 'sucursal',
    nombre: 'Sucursal franquiciada',
    descripcion:
      'Sucursal franquiciada o tercerizada que comparte marca pero operacion independiente.',
    caracteristicas: null,
    vigente_desde: '2026-01-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-01-01T00:00:00',
    created_by: null,
    sync_status: 'sincronizado',
  },
];

export interface UseTipoSucursalReturn {
  tipos: TipoSucursal[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<TipoSucursal[] | undefined>;
  isFromFallback: boolean;
}

export function useTipoSucursal(): UseTipoSucursalReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<TipoSucursal[]>(
    accessToken ? '/api/v1/catalogos/tipo-sucursal' : null,
    () => listTipoSucursal({ limit: 200 }),
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
