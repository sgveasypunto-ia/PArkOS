/**
 * `useTarifasVigentesEn()` — SWR hook que devuelve la lista de tarifas
 * vigentes en un instante dado (``vigente_en`` query param, default
 * ``datetime.now(UTC)`` server-side). Es el read-side del cotizador
 * ``prod.calcular_cotizacion`` — el cliente MUESTRA el valor, no lo
 * calcula (DEC-SUC-12 verbatim; A-02 tiempo_tar_plena server-side only).
 *
 * Patrón copy-paste de ``useTarifasByKey``. Sin fallback hardcoded —
 * la lista vigente es lo que se muestra al operador, y un fallback
 * estático induciría a error de cálculo de cotización.
 *
 * El handler dedicado HU-F1.4 en ``backend/.../api/v1/empresa.py``
 * (``list_tarifas_sucursal_vigente_en``) filtra por el predicado
 * bi-temporal canónico (``vigente_desde <= :v AND
 * (vigente_hasta IS NULL OR vigente_hasta > :v) AND estado = 'activo'``).
 *
 * ``sucursal`` es opcional — sin sucursal el endpoint devuelve las
 * tarifas de TODAS las sucursales (útil para vistas admin cross-branch
 * como "tarifas vigentes globales ahora mismo"). El factory emite
 * ``{items, next_cursor}`` y parseamos con ``tarifaReadListEnvelopeSchema``.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  tarifaReadListEnvelopeSchema,
  type Tarifa,
} from '../api/tarifaSchema';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseTarifasVigentesEnReturn {
  tarifas: Tarifa[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<Tarifa[] | undefined>;
}

export function useTarifasVigentesEn(
  sucursal: string | null,
  vigenteEn?: string | null,
): UseTarifasVigentesEnReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const key = accessToken
    ? ['tarifas-vigentes-en', sucursal, vigenteEn ?? null]
    : null;

  const { data, error, isLoading, mutate } = useSWR<Tarifa[]>(
    key,
    async () => {
      const params = new URLSearchParams();
      if (vigenteEn !== undefined && vigenteEn !== null) {
        params.set('vigente_en', vigenteEn);
      }
      const qs = params.toString();
      const url = `/api/v1/empresa/tarifas-sucursal${qs ? `?${qs}` : ''}`;
      const res = await fetch(url, {
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) {
        if (res.status === 404) return [];
        throw new ParkosHttpError(res.status, await res.text(), url);
      }
      const json = (await res.json()) as unknown;
      return tarifaReadListEnvelopeSchema.parse(json).items;
    },
    {
      dedupingInterval: DEDUPING_INTERVAL_MS,
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && err.status === 404),
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
    tarifas: data ?? [],
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? [];
    },
  };
}
