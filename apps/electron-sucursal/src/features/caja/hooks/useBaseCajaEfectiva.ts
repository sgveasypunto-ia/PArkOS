/**
 * `useBaseCajaEfectiva(uuidSucursal)` — SWR hook de la base de caja de la sucursal.
 *
 * `base === null` con `isLoading === false` significa "sin base configurada":
 * el formulario de apertura cae a la entrada manual (el backend conserva el
 * valor del cliente solo en ese caso).
 */
import useSWR from 'swr';

import { getBaseCajaEfectiva } from '../api/configuracionCajaApi';

export interface UseBaseCajaEfectivaReturn {
  base: number | null;
  isLoading: boolean;
  error: Error | undefined;
}

export function useBaseCajaEfectiva(uuidSucursal: string | undefined): UseBaseCajaEfectivaReturn {
  const { data, error, isLoading } = useSWR<number | null>(
    uuidSucursal ? `/configuracion-caja/efectiva/${uuidSucursal}` : null,
    () => getBaseCajaEfectiva(uuidSucursal as string),
    { dedupingInterval: 10 * 1000, shouldRetryOnError: false },
  );

  return { base: data ?? null, isLoading, error };
}
