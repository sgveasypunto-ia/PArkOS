/**
 * `useSucursalesDirectorio.ts` — single source of truth for the branch
 * directory (list of all branches visible to the current admin).
 *
 * Why this hook exists
 * --------------------
 * Eight call sites used to read the SAME raw SWR key
 * (`'/api/v1/empresa/sucursal?limit=200'`) while registering fetchers
 * that returned DIFFERENT shapes:
 *
 * - `AdminUsuarioSucursalesManager` returned the raw envelope
 *   `{ items: [...] }` (via `parkosFetchRaw`)
 * - the other seven returned a plain `Sucursal[]` (via `listSucursales`)
 *
 * SWR's cache is global and keyed by the key string alone, and a second
 * hook bound to an already-fresh key does NOT run its own fetcher — it
 * just reads whatever the first hook wrote. Whichever mounted first
 * decided the shape everyone else got:
 *
 * - manager first -> `UsuariosList` read `{ items: [...] }` and
 *   `availableBranches.map` threw "is not a function"
 *   (`AdminUsuarioForm.tsx:206`)
 * - list first -> the manager read `[]` silently (a plain array has no
 *   `.items`, so `data?.items ?? []` collapsed to an empty list and the
 *   assignment modal offered zero branches)
 *
 * The key is namespaced with a `parkos:` prefix and a version suffix so
 * it can never collide with a raw URL, and the fetcher normalises to
 * `Sucursal[]` unconditionally.
 */

import { useMemo } from 'react';
import useSWR from 'swr';

import type { BranchOption } from '@/components/branch-selector/BranchSelector';

import { listSucursales } from '../api/sucursalesApi';
import type { Sucursal } from '../api/sucursalSchema';

/**
 * Namespaced on purpose — see the module docblock. Bump on shape change.
 * Exported so the regression suite can assert the key that replaced the
 * colliding raw-URL key.
 */
export const DIRECTORIO_KEY = 'parkos:sucursales:directorio:v1';

const DEFAULT_LIMIT = 200;

export interface UseSucursalesDirectorioReturn {
  sucursales: Sucursal[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<void>;
}

export function useSucursalesDirectorio(
  limit: number = DEFAULT_LIMIT,
): UseSucursalesDirectorioReturn {
  const { data, error, isLoading, mutate } = useSWR<Sucursal[]>(
    DIRECTORIO_KEY,
    async () => {
      const items = await listSucursales({ limit });
      return Array.isArray(items) ? items : [];
    },
    { revalidateOnFocus: false, keepPreviousData: true },
  );

  return {
    sucursales: Array.isArray(data) ? data : [],
    isLoading,
    error,
    refresh: async () => {
      await mutate();
    },
  };
}

export interface UseSucursalOptionsReturn {
  sucursales: Sucursal[];
  options: BranchOption[];
  isLoading: boolean;
  error: Error | undefined;
}

/**
 * Same cache entry, projected to the `{ uuid, nombre }` shape the
 * selects and forms consume. Replaces the four copies of the same
 * `.map((s) => ({ uuid: s.uuid, nombre: s.nombre }))` that existed
 * alongside the colliding key.
 */
export function useSucursalOptions(
  limit: number = DEFAULT_LIMIT,
): UseSucursalOptionsReturn {
  const { sucursales, isLoading, error } = useSucursalesDirectorio(limit);

  const options = useMemo<BranchOption[]>(
    () => sucursales.map((s) => ({ uuid: s.uuid, nombre: s.nombre })),
    [sucursales],
  );

  return { sucursales, options, isLoading, error };
}
