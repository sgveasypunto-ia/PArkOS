/**
 * `useCotizacion.ts` — SWR hook for the live price quote (HU-F7.1).
 *
 * Polls `GET /api/v1/operacion/cotizar?uuid_ingreso=X` while an active
 * ingreso is selected. The polling cadence is the design §Decision D3
 * choice — 1 s while the panel is open, dropped to `null` (no fetch)
 * as soon as the parent unmounts or the operator clears the plate.
 *
 * REQ-OPS-132 fetcher-closure idiom (precedent F4.3 useOcupacion):
 * the SWR fetcher receives the bare UUID, NOT the cache key. SWR's
 * convention is that the key is opaque (used only for cache identity);
 * the fetcher is invoked with the actual payload argument. Mirrors
 * `useSesionActiva.ts:55-57` and `useIngresoActivo.ts:67-69`.
 *
 * SWR key gating — `null` when `uuid_ingreso === null`. The Dashboard
 * uses this hook inside `<CotizacionPanel />` (PR-3), so the cold
 * Dashboard does NOT issue a `/cotizar` fetch — REQ-OPS-139.
 *
 * `shouldRetryOnError` excludes 401 (auth store reacts), 403 (forbidden
 * is terminal), and 404 (closed ingreso no longer has a quote).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { z } from 'zod';

/**
 * Cotización wire shape (F1.8 archive). The backend computes the
 * quote server-side based on the ingreso's `fecha_ingreso` +
 * `uuid_tarifa_vigente`; the client renders the breakdown as a
 * semantic `<dl>` per plan.md:1677 (HU-F7.1-T3).
 */
export const CotizacionSchema = z.object({
  uuid_ingreso: z.string().uuid(),
  uuid_tarifa_vigente: z.string().uuid(),
  minutos_transcurridos: z.number().int().nonnegative(),
  /** Base price for the elapsed minutes (COP integer). */
  base_cop: z.number().int().nonnegative(),
  /** Fractional hour (top-up bucket) in COP. */
  fraccion_cop: z.number().int().nonnegative(),
  /** Total a cobrar (COP integer). */
  total_cop: z.number().int().nonnegative(),
  /** ISO 8601 timestamp the quote was computed. */
  generado_en: z.string(),
});
export type Cotizacion = z.infer<typeof CotizacionSchema>;

const QUOTE_REFRESH_INTERVAL_MS = 1_000;

export interface UseCotizacionReturn {
  data: Cotizacion | undefined;
  error: Error | undefined;
  refresh: () => Promise<Cotizacion | undefined>;
}

/**
 * Fetcher — receives the bare UUID; SWR key is opaque and used only
 * for cache identity (per the established `useOcupacion` precedent).
 */
async function fetchCotizacion(uuid_ingreso: string): Promise<Cotizacion> {
  // Lazy import to keep the test mock boundary clean (matches the
  // `parkosFetch` import boundary in operacion/*Api.ts).
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/operacion/cotizar?uuid_ingreso=${encodeURIComponent(uuid_ingreso)}`,
  );
  return CotizacionSchema.parse(raw);
}

/**
 * Hook SWR para consultar la cotización viva del ingreso.
 *
 * Returns `{ data, error, refresh }`. `data` is `undefined` until the
 * first fetch resolves; `error` is `undefined` when the key is `null`.
 */
export function useCotizacion(uuid_ingreso: string | null): UseCotizacionReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid_ingreso && accessToken
    ? `/operacion/cotizar?uuid_ingreso=${uuid_ingreso}`
    : null;

  const { data, error, mutate } = useSWR<Cotizacion>(
    key,
    () => fetchCotizacion(uuid_ingreso as string),
    {
      refreshInterval: QUOTE_REFRESH_INTERVAL_MS,
      revalidateOnFocus: false,
      shouldRetryOnError: (err) => {
        if (err instanceof ParkosHttpError) {
          return err.status !== 401 && err.status !== 403 && err.status !== 404;
        }
        return true;
      },
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('parkos:auth:cleared'));
          }
          return;
        }
        console.warn('[useCotizacion] polling failed', err);
      },
    },
  );

  return {
    data,
    error,
    refresh: async () => mutate(),
  };
}