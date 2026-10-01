/**
 * `useSucursalDetalle` — SWR hook for a single branch (HU-F15.1,
 * `/sucursales/:uuid`).
 *
 * Mirrors `features/usuarios/hooks/useUsuario.ts`'s shape exactly
 * (uuid-keyed SWR, `undefined` key when no uuid yet so the fetcher never
 * runs with a bad argument).
 */
import useSWR from 'swr';

import { getSucursal } from '../api/sucursalesApi';
import type { Sucursal } from '../api/sucursalSchema';

export interface UseSucursalDetalleReturn {
  sucursal: Sucursal | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Sucursal | undefined>;
}

export function useSucursalDetalle(uuid: string | undefined): UseSucursalDetalleReturn {
  const { data, error, isLoading, mutate } = useSWR<Sucursal>(
    uuid ? `sucursal-detalle-${uuid}` : null,
    () => getSucursal(uuid!),
  );

  return {
    sucursal: data,
    isLoading,
    error,
    refresh: async () => mutate(),
  };
}
