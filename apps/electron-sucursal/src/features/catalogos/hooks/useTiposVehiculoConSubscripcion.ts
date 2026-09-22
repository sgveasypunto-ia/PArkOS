/**
 * `useTiposVehiculoConSubscripcion()` — SWR hook para el subset de
 * ``tipos_vehiculo`` cubierto por al menos un ``tipo_subscripciones``
 * vigente (HU-F11.x / REQ-OPS-200).
 *
 * Consumido por el dropdown de override de tipo en ``<IngresoPanel />``
 * — el operador puede cambiar el tipo detectado por regex cuando el
 * regex matchea pero la placa está en un subset donde el plan permite
 * override (ej. placa con formato CARRO + suscripción MOTO en el
 * mismo branch).
 *
 * Mismas reglas que ``useTiposVehiculo()``:
 *   - SWR key null sin accessToken (gate pre-login).
 *   - 5min dedupingInterval (catalog reference data).
 *   - 401 → logout defensivo.
 *   - 404 → fallbackData ``[]`` (sin subscripciones configuradas).
 *   - 5xx / network → fallbackData ``[]`` + NO propaga error (el
 *     dropdown simplemente queda vacío; el server igual rechaza con
 *     422 si el operador elige uno no suscrito).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  getTiposVehiculoConSubscripcion,
  type TipoVehiculo,
} from '../api/tiposVehiculoApi';

const TIPOS_VEHICULO_CON_SUBSCRIPCION_KEY =
  '/catalogos/tipos-vehiculo-con-subscripcion';

const DEDUPING_INTERVAL_MS = 5 * 60 * 1000;

export interface UseTiposVehiculoConSubscripcionReturn {
  tipos: TipoVehiculo[];
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<TipoVehiculo[] | undefined>;
}

export function useTiposVehiculoConSubscripcion(): UseTiposVehiculoConSubscripcionReturn {
  const accessToken = useAuthStore((s) => s.accessToken);

  const { data, error, isLoading, mutate } = useSWR<TipoVehiculo[]>(
    accessToken ? TIPOS_VEHICULO_CON_SUBSCRIPCION_KEY : null,
    () => getTiposVehiculoConSubscripcion(),
    {
      fallbackData: [],
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
    tipos: data ?? [],
    isLoading,
    error,
    refresh: async () => {
      const result = await mutate();
      return result ?? [];
    },
  };
}