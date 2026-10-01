/**
 * `useResolucionesSucursal` — SWR hook for the HU-F15.3 "Resoluciones" tab.
 *
 * `GET /api/v1/empresa/resolucion-facturacion` has no server-side
 * `uuid_sucursal` filter (REQ-X3 dedicated router), so this hook filters
 * the returned `items` client-side — same convention as
 * `parametrizacionEfectivaApi.ts::countVigentes` and
 * `useParametrizacionEfectiva.ts`. The 404-as-empty-list translation for
 * the cloud-only resource already happens inside
 * `resolucionFacturacionApi.ts::listResolucionesFacturacion`, so this hook
 * never needs to special-case a 404 itself — an empty `items` array is
 * indistinguishable from (and handled the same as) "branch deploy without
 * DIAN root".
 */
import useSWR from 'swr';

import { listResolucionesFacturacion } from '../api/resolucionFacturacionApi';
import type { ResolucionFacturacion } from '../api/resolucionFacturacionSchema';

export interface UseResolucionesSucursalReturn {
  resoluciones: ResolucionFacturacion[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<ResolucionFacturacion[] | undefined>;
}

// Stable empty-array fallback. `data ?? []` would allocate a NEW array
// literal on every render while `data` is still `undefined` (i.e. the
// whole loading phase), which breaks referential equality for any caller
// that depends on `resoluciones` in a `useEffect` dependency array (see
// `ResolucionesDIAN.tsx`) — that would re-fire the effect on every render
// during loading, which (since the effect's own state update triggers a
// re-render) becomes a tight render loop. A single shared reference avoids
// that entirely.
const EMPTY_RESOLUCIONES: ResolucionFacturacion[] = [];

export function useResolucionesSucursal(
  uuidSucursal: string | undefined,
): UseResolucionesSucursalReturn {
  const key = uuidSucursal ? `resoluciones-facturacion-${uuidSucursal}` : null;

  const { data, error, isLoading, mutate } = useSWR(key, async () => {
    const page = await listResolucionesFacturacion({ limit: 200 });
    return page.items.filter((item) => item.uuid_sucursal === uuidSucursal);
  });

  return {
    resoluciones: data ?? EMPTY_RESOLUCIONES,
    isLoading,
    error,
    refresh: async () => mutate(),
  };
}
