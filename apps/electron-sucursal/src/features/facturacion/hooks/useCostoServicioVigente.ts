/**
 * `useCostoServicioVigente(concepto)` — HU-F8.3 (ajuste 2026-09-25).
 *
 * SWR preview of the vigente `prod.costos_servicios` row for a given
 * `concepto` (e.g. `'reimpresion'`), so `<ReimprimirTiquete />` can
 * show the amount to charge (and feed `<PagoModal total_cop={...}>`)
 * BEFORE the operator commits to the cobro — mirrors how salida
 * always cotiza before opening `<PagoModal>`.
 *
 * `GET /api/v1/catalogos/costos-servicios?concepto=X&estado=activo`
 * (generic `make_router` C+Q mount, `catalogos.py`) can return more
 * than one historical row for the same concepto; the vigente row is
 * the one with `vigente_hasta === null`, picked client-side (mirrors
 * the backend guard `buscar_costo_servicio_vigente_por_concepto`,
 * which does the same `WHERE vigente_hasta IS NULL AND estado='activo'
 * ORDER BY vigente_desde DESC` server-side — this hook is a PREVIEW,
 * the backend POST re-resolves and snapshots the authoritative value).
 */
import useSWR from 'swr';
import { z } from 'zod';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const CostoServicioSchema = z.object({
  uuid: z.string().uuid(),
  concepto: z.string().nullable(),
  costo: z.coerce.number().nullable(),
  vigente_desde: z.string(),
  vigente_hasta: z.string().nullable(),
  estado: z.string(),
});
const CostosServiciosListSchema = z.object({
  items: z.array(CostoServicioSchema),
});

const PATH = '/api/v1/catalogos/costos-servicios';

async function fetchCostoVigente(concepto: string): Promise<number | null> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `${PATH}?concepto=${encodeURIComponent(concepto)}&estado=activo`,
  );
  const { items } = CostosServiciosListSchema.parse(raw);
  const vigente = items
    .filter((row) => row.vigente_hasta === null)
    .sort((a, b) => b.vigente_desde.localeCompare(a.vigente_desde))[0];
  return vigente?.costo ?? null;
}

export interface UseCostoServicioVigenteReturn {
  /** `null` mientras carga o si no hay costo configurado para el concepto. */
  costo: number | null;
  isLoading: boolean;
  error: Error | undefined;
}

export function useCostoServicioVigente(
  concepto: string | null,
): UseCostoServicioVigenteReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = concepto && accessToken ? `${PATH}?concepto=${concepto}` : null;

  const { data, isLoading, error } = useSWR<number | null>(
    key,
    () => fetchCostoVigente(concepto as string),
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
    costo: data ?? null,
    isLoading,
    error: error as Error | undefined,
  };
}
