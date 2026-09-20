/**
 * `useFacturaElectronica.ts` — SWR hook for the electronic-invoice
 * status poll (HU-F8.2).
 *
 * Polls `GET /api/v1/facturacion/factura-electronica/{uuid}` every 30s
 * (per plan.md:1941-1966 §F8.2 polling cadence) until the document
 * reaches a terminal state (`aceptado | rechazado`). The hook returns
 * `data: undefined` once the polling stops — consumers can mount the
 * retry panel via `data.estado_dian === 'rechazado'`.
 *
 * REQ-OPS-132 fetcher-closure idiom — the SWR fetcher receives the bare
 * UUID, NOT the cache key. Same precedent as `useOcupacion` and
 * `useCotizacion`.
 *
 * SWR key gating — `null` when `uuid === null`. The Dashboard's
 * `<FacturaElectronicaRetryPanel />` (PR-4) only issues a fetch when
 * the operator selects a pending FE retry; cold Dashboard has 0
 * fetches (REQ-OPS-139).
 *
 * `shouldRetryOnError` excludes 401 (auth store reacts), 403 (forbidden
 * is terminal), and 404 (uuid no longer exists).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { z } from 'zod';

/**
 * Factura electrónica wire shape (F1.10 archive). Estado DIAN is the
 * canonical terminal/non-terminal signal.
 */
export const FacturaElectronicaEstadoSchema = z.object({
  uuid_factura_electronica: z.string().uuid(),
  uuid_factura: z.string().uuid(),
  estado_dian: z.enum(['pendiente', 'aceptado', 'rechazado', 'no_enviado']),
  /** Optional: DIAN provider's last response payload (cufe + motivo). */
  respuesta_proveedor: z
    .object({
      cufe: z.string().optional(),
      motivo: z.string().optional(),
      reportado_en: z.string().optional(),
    })
    .nullable()
    .optional(),
  actualizado_en: z.string(),
});
export type FacturaElectronicaEstado = z.infer<typeof FacturaElectronicaEstadoSchema>;

const FE_REFRESH_INTERVAL_MS = 30_000;

/**
 * Terminal FE states per F1.10 DEC-FE-04 — both `aceptado` and
 * `rechazado` are terminal. `pendiente` and `no_enviado` keep polling.
 * HU-F8.2 REQ-OPS-166 terminal-gating polling.
 */
const TERMINAL_STATES: ReadonlySet<'aceptado' | 'rechazado'> = new Set([
  'aceptado',
  'rechazado',
]);

/**
 * SWR `refreshInterval` callback. SWR treats `0` as "do not poll" — the
 * next mutation (e.g. `useReintentarFE.trigger()`'s `mutate()`) re-engages
 * polling because the new chain tip is `pendiente`.
 */
export function computeRefreshInterval(
  latest: Pick<FacturaElectronicaEstado, 'estado_dian'> | undefined,
): number {
  if (!latest) return FE_REFRESH_INTERVAL_MS;
  return TERMINAL_STATES.has(latest.estado_dian as 'aceptado' | 'rechazado')
    ? 0
    : FE_REFRESH_INTERVAL_MS;
}

export interface UseFacturaElectronicaReturn {
  data: FacturaElectronicaEstado | undefined;
  error: Error | undefined;
  refresh: () => Promise<FacturaElectronicaEstado | undefined>;
}

async function fetchFE(uuid: string): Promise<FacturaElectronicaEstado> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/facturacion/factura-electronica/${uuid}`,
  );
  return FacturaElectronicaEstadoSchema.parse(raw);
}

/**
 * Hook SWR para consultar el estado DIAN de una factura electrónica.
 *
 * Returns `{ data, error, refresh }`. `data` is `undefined` until the
 * first fetch resolves; `error` is `undefined` when the key is `null`.
 */
export function useFacturaElectronica(
  uuid: string | null,
): UseFacturaElectronicaReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid && accessToken
    ? `/facturacion/factura-electronica/${uuid}`
    : null;

  const { data, error, mutate } = useSWR<FacturaElectronicaEstado>(
    key,
    () => fetchFE(uuid as string),
    {
      refreshInterval: computeRefreshInterval,
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
        console.warn('[useFacturaElectronica] polling failed', err);
      },
    },
  );

  return {
    data,
    error,
    refresh: async () => mutate(),
  };
}