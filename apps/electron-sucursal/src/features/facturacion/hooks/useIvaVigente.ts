/**
 * `useIvaVigente()` — HU-F8.3 (bugfix 2026-09-25).
 *
 * SWR preview of the vigente `prod.impuestos` IVA percentage
 * (`codigo='IVA'`), so `<ReimprimirTiquete />` can split a
 * with-tax price (the configured `costos_servicios.costo`) into
 * `subtotal`/`iva` BEFORE posting to `/facturacion/factura-servicio`.
 *
 * Mirrors `useCostoServicioVigente.ts` verbatim (same GET-then-pick-
 * vigente-row pattern, same generic `make_router` C+Q mount).
 *
 * Formula mirrors `repo/factura.py::crear_factura_impuesto_iva` /
 * the PL/pgSQL `calcular_cotizacion` convention (DEC-FACT-03): the
 * configured price IS the total the customer pays; `iva = round(total
 * * porcentaje, 2)` and `subtotal = total - iva` — NOT a division-based
 * extraction. Reusing this exact formula (instead of a different one)
 * keeps every factura in the system consistent.
 */
import useSWR from 'swr';
import { z } from 'zod';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const ImpuestoSchema = z.object({
  uuid: z.string().uuid(),
  codigo: z.string().nullable(),
  porcentaje: z.coerce.number().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
});
const ImpuestosListSchema = z.object({
  items: z.array(ImpuestoSchema),
});

const PATH = '/api/v1/catalogos/impuestos';

async function fetchIvaVigente(): Promise<number | null> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `${PATH}?codigo=${encodeURIComponent('IVA')}&estado=activo`,
  );
  const { items } = ImpuestosListSchema.parse(raw);
  const vigente = items
    .filter((row) => row.vigente_hasta === null)
    .sort((a, b) => b.vigente_desde.localeCompare(a.vigente_desde))[0];
  return vigente?.porcentaje ?? null;
}

export interface UseIvaVigenteReturn {
  /** Fracción (ej. 0.19), no porcentaje entero. `null` mientras carga o si no hay IVA configurado. */
  porcentaje: number | null;
  isLoading: boolean;
  error: Error | undefined;
}

export function useIvaVigente(enabled: boolean): UseIvaVigenteReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = enabled && accessToken ? PATH : null;

  const { data, isLoading, error } = useSWR<number | null>(
    key,
    fetchIvaVigente,
    {
      dedupingInterval: 5_000,
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && (err.status === 401 || err.status === 404)),
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
    porcentaje: data ?? null,
    isLoading,
    error: error as Error | undefined,
  };
}
