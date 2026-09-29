import useSWR from 'swr';
import { listSucursales } from '../api/sucursalesApi';
import type { Sucursal } from '../api/sucursalSchema';

export function useSucursales() {
  const { data, error, isLoading, mutate } = useSWR<Sucursal[]>(
    'sucursales',
    () => listSucursales({ limit: 200 }),
  );

  return {
    sucursales: data ?? [],
    isLoading,
    error,
    mutate,
  };
}
