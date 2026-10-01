/**
 * ``useArqueosResumenAdmin`` -- SWR hook for the HU-F18.3 admin
 * cross-branch resumen por día.
 *
 * Single SWR key per date; no cursor pagination because the resumen
 * returns the full per-branch list for the day (the count of vigente
 * ``prod.sucursal`` rows is bounded -- typically <50, never enough
 * to justify pagination).
 */
import { useMemo } from 'react';
import useSWR from 'swr';

import { fetchResumenAdmin } from '../api/arqueosApi';
import type {
  ArqueoResumenAdminRead,
} from '../api/arqueosSchema';

export interface UseArqueosResumenAdminReturn {
  resumen: ArqueoResumenAdminRead | null;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<ArqueoResumenAdminRead | undefined>;
}

export interface UseArqueosResumenAdminOptions {
  /** Optional suffix for test isolation (avoids SWR cache pollution
   * across tests). */
  swrSalt?: string;
}

export function useArqueosResumenAdmin(
  fecha: string | null,
  options: UseArqueosResumenAdminOptions = {},
): UseArqueosResumenAdminReturn {
  const { swrSalt } = options;
  const swrKey = useMemo(() => {
    if (!fecha) return null;
    const base = `admin-arqueo-resumen/${fecha}`;
    return swrSalt !== undefined ? `${base}&_=${swrSalt}` : base;
  }, [fecha, swrSalt]);

  const fetcher = async (): Promise<ArqueoResumenAdminRead> => {
    if (!fecha) throw new Error('fecha required');
    return fetchResumenAdmin(fecha);
  };

  const { data, error, isLoading, mutate } = useSWR<
    ArqueoResumenAdminRead,
    Error
  >(swrKey, fetcher, {
    revalidateOnFocus: false,
    // The resumen endpoint's response is keyed on the date; SWR's
    // deduping at the cache level means a stale `data` from a previous
    // test would mask a freshly-returned loading state in the next.
    // Setting ``keepPreviousData: false`` (default) ensures we get
    // a re-fetch + loading transition on each test.
    keepPreviousData: false,
  });

  return {
    resumen: data ?? null,
    isLoading,
    error,
    refresh: async () => mutate(),
  };
}