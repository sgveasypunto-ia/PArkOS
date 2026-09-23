/**
 * `useTarifaByUuid(uuid)` — SWR hook para el detalle de UNA tarifa
 * vigente (HU-F1.4 / CU-02, directiva del operador 2026-09-22).
 *
 * El endpoint de cotizacion (``GET /operacion/cotizar``) retorna
 * ``tarifa_uuid`` (el UUID de la fila aplicada) pero NO el detalle.
 * Antes de este PR, el FE solo podía mostrar el UUID crudo en
 * ``<CotizacionPanel />``. Este hook hace un lookup
 * ``getTarifaSucursalByUuid(uuid)`` y expone el detalle completo
 * (``valor``, ``valor_plena``, ``vigente_desde``, ``vigente_hasta``,
 * ``estado``) para que el UI muestre el desglose legible de la
 * tarifa aplicada.
 *
 * Comportamiento:
 *   - SWR key `/empresa/tarifas-sucursal/{uuid}` (gated por accessToken).
 *   - Deduping 5min (mismo que `useTarifasVigentes`, catálogos reference
 *     data — no ``refreshInterval``).
 *   - 404 → `data: null` (no retry, tarifa puede haber sido cerrada;
 *     el panel hace fallback al UUID como antes).
 *   - 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (defensa
 *     estándar F2.2).
 *
 * Precedente: ``useTarifasVigentes`` (F4.2 — T3, mismo feature). El
 * shape de retorno es deliberadamente paralelo para que el llamador
 * pueda tratar ambos hooks de la misma manera.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { getTarifaSucursalByUuid, type TarifaSucursalRead } from '../api/tarifasSucursalApi';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseTarifaByUuidReturn {
  /** Tarifa aplicable al uuid; `null` mientras carga o si 404. */
  tarifa: TarifaSucursalRead | null;
  /** `true` mientras el primer fetch está en curso. */
  isLoading: boolean;
  /** `Error` si el fetch falló con !=404. */
  error: Error | undefined;
  /** Forzar revalidación contra la API (SWR `mutate`). */
  refresh: () => Promise<void>;
}

/**
 * Hook SWR para el detalle de UNA tarifa por uuid.
 *
 * Devuelve `{ tarifa, isLoading, error, refresh }`. `tarifa === null`
 * durante el fetch inicial y cuando el backend retorna 404 (fila
 * cerrada o uuid mal tipeado). El llamador debe hacer fallback al
 * UUID cuando `tarifa === null && !isLoading && !error`.
 */
export function useTarifaByUuid(uuid: string | null): UseTarifaByUuidReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid && accessToken
    ? `/empresa/tarifas-sucursal/${uuid}`
    : null;

  const { data, error, isLoading, mutate } = useSWR<TarifaSucursalRead | null>(
    key,
    async () => {
      if (uuid === null) return null;
      try {
        return await getTarifaSucursalByUuid(uuid);
      } catch (err) {
        if (err instanceof ParkosHttpError && err.status === 404) {
          // 404 = tarifa cerrada / uuid no existe. Estado válido para
          // el UI: el llamador hace fallback al UUID. NO retry.
          return null;
        }
        throw err;
      }
    },
    {
      dedupingInterval: DEDUPING_INTERVAL_MS,
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
        console.warn('[useTarifaByUuid] fetch failed', err);
      },
    },
  );

  return {
    tarifa: data ?? null,
    isLoading,
    error,
    refresh: async () => {
      await mutate();
    },
  };
}