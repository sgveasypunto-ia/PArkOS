/**
 * `useConfiguracionCajaEfectiva()` — SWR hook for the resolved
 * `configuracion_caja` effective value of one branch (HU-F15.5).
 *
 * Thin SWR wrapper over `getConfiguracionCajaEfectiva`: `data === null`
 * means the `.../efectiva` route 404'd (neither an override nor a
 * global default exists yet) — a modeled state, not an error. `data`
 * `undefined` means "still loading" (or no `uuidSucursal` yet).
 */
import useSWR from 'swr';

import { getConfiguracionCajaEfectiva, type ConfiguracionCaja } from '../api/configuracionCajaApi';

export interface UseConfiguracionCajaEfectivaReturn {
  data: ConfiguracionCaja | null | undefined;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<ConfiguracionCaja | null | undefined>;
}

export function useConfiguracionCajaEfectiva(
  uuidSucursal: string | undefined,
): UseConfiguracionCajaEfectivaReturn {
  const { data, error, isLoading, mutate } = useSWR<ConfiguracionCaja | null>(
    uuidSucursal ? `configuracion-caja-efectiva-${uuidSucursal}` : null,
    () => getConfiguracionCajaEfectiva(uuidSucursal as string),
  );

  return {
    data,
    isLoading,
    error,
    refresh: () => mutate(),
  };
}
