/**
 * `useAlertas.ts` — SWR hook for the alertas panel (HU-F11.2,
 * REQ-OPS-179 + DA-F11.2-5 + DA-F11.2-6 + DA-F11.2-7 + DA-F11.2-10
 * path b).
 *
 * Drift anchors resolved:
 *   - DA-F11.2-5: drops the 8 technical codes via
 *     `BUSINESS_ALERT_CODES` whitelist — `Set.has(...)` O(1) per
 *     row (REQ-OPS-182 perf sanity).
 *   - DA-F11.2-6: 30 s polling cadence on `/workflows/alerta`
 *     (matches F11.1 SyncBanner precedent).
 *   - DA-F11.2-7: derived `openAlertsCount` selector — business
 *     codes + `estado === 'activa'`.
 *   - DA-F11.2-10: path (b) — client-side merge from
 *     `/workflows/alert-types` (refresh 5 min). Path (a) — BE JOIN —
 *     is filed as ABBC-F11.2-BE-1 in `pending-fase-11.md`.
 *
 * SWR key gate on `(uuid_sucursal && accessToken)` — REQ-OPS-132
 * fetcher-closure baseline (F3.1). On 401: `useAuthStore.clear()` +
 * `parkos:auth:cleared` window event (verbatim F11.1 pattern).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError, parkosFetch } from '@parkos/ui-kit/fetch';

import {
  AlertaReadListSchema,
  AlertTypeReadListSchema,
  type AlertaRead,
  type AlertTypeRead,
  type MergedAlerta,
} from '../../../lib/api/schemas/alertas';

import { BUSINESS_ALERT_CODES } from '../constants';

const ALERTA_REFRESH_INTERVAL_MS = 30_000;
const ALERT_TYPES_REFRESH_INTERVAL_MS = 300_000;

async function fetchAlertas(uuid_sucursal: string): Promise<AlertaRead[]> {
  const raw = await parkosFetch<unknown>(
    `/api/v1/workflows/alerta?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}&estado=activa`,
  );
  return AlertaReadListSchema.parse(raw);
}

async function fetchAlertTypes(uuid_sucursal: string): Promise<AlertTypeRead[]> {
  const raw = await parkosFetch<unknown>(
    `/api/v1/workflows/alert-types?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}`,
  );
  return AlertTypeReadListSchema.parse(raw);
}

/**
 * `mergeAlertasWithAlertTypes` — pure selector (testable in isolation):
 *   1. Filter: drop rows whose `tipo_alerta` is not in BUSINESS_ALERT_CODES.
 *   2. Enrich: each surviving row carries `severidad` / `descripcion` /
 *      `mensaje` from `alertTypes[tipo_alerta]`. Rows whose code is
 *      missing from `alertTypes` are dropped silently (ABIERTO-06).
 *   3. Drop technical codes via `console.debug` (NEVER `console.error`).
 */
export function mergeAlertasWithAlertTypes(
  alertas: AlertaRead[],
  alertTypes: AlertTypeRead[],
): MergedAlerta[] {
  const typeByCode = new Map<string, AlertTypeRead>();
  for (const t of alertTypes) {
    typeByCode.set(t.codigo, t);
  }

  const merged: MergedAlerta[] = [];
  for (const a of alertas) {
    const code = a.tipo_alerta;
    if (!code || !BUSINESS_ALERT_CODES.has(code)) {
      // ABIERTO-06: silent drop with `console.debug`. The technical
      // codes are the operator's cloud-side concern; we are the
      // filter authority on the branch.
      if (typeof console !== 'undefined' && typeof console.debug === 'function') {
        console.debug(`[useAlertas] dropping alert code ${code ?? '(null)'}`);
      }
      continue;
    }
    const t = typeByCode.get(code);
    if (!t) {
      if (typeof console !== 'undefined' && typeof console.debug === 'function') {
        console.debug(`[useAlertas] dropping alert code ${code} — not present in alert_types`);
      }
      continue;
    }
    merged.push({
      ...a,
      severidad: t.severidad,
      descripcion: t.descripcion,
      mensaje: t.mensaje,
    });
  }
  return merged;
}

export interface UseAlertasResult {
  data: AlertaRead[] | undefined;
  mergedAlertas: MergedAlerta[];
  openAlertsCount: number;
  error: Error | undefined;
  refresh: () => Promise<unknown>;
}

export function useAlertas(uuid_sucursal: string | null): UseAlertasResult {
  const accessToken = useAuthStore((s) => s.accessToken);
  const gate = uuid_sucursal && accessToken ? uuid_sucursal : null;

  const alertaKey = gate ? `/workflows/alerta?uuid_sucursal=${gate}&estado=activa` : null;
  const typesKey = gate ? `/workflows/alert-types?uuid_sucursal=${gate}` : null;

  const sharedErrorHandler = {
    shouldRetryOnError: (err: unknown) => {
      if (err instanceof ParkosHttpError) {
        return err.status !== 401 && err.status !== 403 && err.status !== 404;
      }
      return true;
    },
    onError: (err: unknown) => {
      if (err instanceof ParkosHttpError && err.status === 401) {
        useAuthStore.getState().clear();
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('parkos:auth:cleared'));
        }
      }
    },
  } as const;

  const { data: alertaData, error: alertaError, mutate: alertaMutate } = useSWR<AlertaRead[]>(
    alertaKey,
    () => fetchAlertas(uuid_sucursal as string),
    {
      refreshInterval: ALERTA_REFRESH_INTERVAL_MS,
      ...sharedErrorHandler,
    },
  );

  const { data: alertTypesData, error: typesError, mutate: typesMutate } = useSWR<AlertTypeRead[]>(
    typesKey,
    () => fetchAlertTypes(uuid_sucursal as string),
    {
      refreshInterval: ALERT_TYPES_REFRESH_INTERVAL_MS,
      ...sharedErrorHandler,
    },
  );

  // Parallel fetch semantics: both useSWR calls are registered in the
  // SAME render tick (the hook body runs once per render). SWR fires
  // both fetchers concurrently — verified by `useAlertas.test.ts` U5.
  const mergedAlertas: MergedAlerta[] =
    alertaData && alertTypesData
      ? mergeAlertasWithAlertTypes(alertaData, alertTypesData)
      : alertaData
        ? alertaData
            .filter((a) => a.tipo_alerta !== null && BUSINESS_ALERT_CODES.has(a.tipo_alerta))
            .map((a) => ({
              ...a,
              severidad: 'media' as const,
              descripcion: a.tipo_alerta ?? '',
              mensaje: a.tipo_alerta ?? '',
            }))
        : [];

  const openAlertsCount = mergedAlertas.filter((a) => a.estado === 'activa').length;

  return {
    data: alertaData,
    mergedAlertas,
    openAlertsCount,
    error: alertaError ?? typesError,
    refresh: async () => {
      await Promise.all([alertaMutate(), typesMutate()]);
    },
  };
}
