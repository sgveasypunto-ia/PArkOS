/**
 * `useCotizacion.ts` — SWR hook for the live price quote (HU-F7.1).
 *
 * Polls `GET /api/v1/operacion/cotizar?uuid_ingreso=X` while an active
 * ingreso is selected. The polling cadence is the F7.1 design §Decision
 * choice — 1 s while the panel is open, dropped to `null` (no fetch)
 * as soon as the parent unmounts or the operator clears the plate.
 *
 * Canonical wire shape (F1.8 archive, REQ-OPS-022..025):
 *   `CotizarFacturacion` (`cobrar: true`) | `CotizarMensualidad`
 *   (`cobrar: false`), discriminated on `cobrar`. Mirrors verbatim the
 *   backend Pydantic at `backend/.../schemas/operacion.py:142-201`.
 *
 * Apply-time deviation T-HU-F1.8-7: `tiempo_minutos` is `z.number()`
 * (NOT `z.number().int()`) because the PL/pgSQL function returns float
 * from `EXTRACT(EPOCH FROM ...)/60.0`. The Pydantic schema accepts
 * `int | float` for the same reason.
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
 *
 * 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event dispatch
 * (preserved invariant from current impl lines 96-105; F3.1
 * REQ-OPS-107..110).
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { z } from 'zod';

import {
  OPERACION_COTIZAR_REFRESH_INTERVAL_MS,
  OPERACION_COTIZAR_TIMEOUT_MS,
} from '../constants';

/**
 * `cotizar: true` variant — full fiscal breakdown (F1.8 archive,
 * REQ-OPS-022). Mirrors backend `CotizarFacturacion` at
 * `backend/.../schemas/operacion.py:142-172`.
 */
export const CotizarFacturacionSchema = z.object({
  cobrar: z.literal(true),
  /**
   * REGRESSION fix (2026-09-22, directiva del operador): los campos
   * monetarios (``subtotal``, ``iva``, ``total``) llegan como
   * **string** desde el backend, no number. La razón: el PL/pgSQL
   * ``prod.calcular_cotizacion`` los calcula con tipo
   * ``numeric(18,4)`` y al serializar a jsonb Python los emite
   * como string para preservar precisión (evita el rounding a float
   * de doble precisión, que es lo que rompería los cobros en
   * valores grandes). El schema original exigía ``z.number()`` y
   * rompía el parseo → ``useCotizacion`` quedaba en polling failed
   * con ZodError. Aceptamos ``number | string`` y normalizamos a
   * number via ``Number()`` para el render (el redondeo de centavos
   * ya está hecho en el PL/pgSQL).
   *
   * Nota: este bug existía LATENTE antes del fix de migration 0046
   * (COALESCE fecha_ingreso) — el flujo de salida siempre había
   * retornado 500 con NULL en los campos, así que el FE nunca veía
   * un payload estructurado y el bug del schema no se manifestaba.
   * El COALESCE reveló el problema; este PR lo corrige.
   */
  subtotal: z.union([z.number(), z.string()]).transform((v) =>
    typeof v === 'number' ? v : Number(v),
  ),
  iva: z.union([z.number(), z.string()]).transform((v) =>
    typeof v === 'number' ? v : Number(v),
  ),
  total: z.union([z.number(), z.string()]).transform((v) =>
    typeof v === 'number' ? v : Number(v),
  ),
  /**
   * Apply-time deviation T-HU-F1.8-7: NOT `z.number().int()`. The
   * PL/pgSQL function returns float from `EXTRACT(EPOCH FROM
   * fecha_ingreso - NOW()) / 60.0` (sub-second precision, e.g.
   * `89.0025`). Also accept string for parity with the monetary
   * fields (defense in depth — el backend puede serializar este
   * float como string en algunas versiones del driver).
   */
  tiempo_minutos: z.union([z.number(), z.string()]).transform((v) =>
    typeof v === 'number' ? v : Number(v),
  ),
  tarifa_uuid: z.string().uuid(),
  /** ISO 8601 string from JSON; the renderer uses this for the countdown. */
  vigente_hasta: z.string(),
  /**
   * REGRESSION fix (2026-09-22): el backend incluye ``motivo: null``
   * en el payload de rotación (no es un sub-extension concept — solo
   * que el PL/pgSQL lo emite siempre). El schema estricto lo
   * rechaza. Aceptar como nullable optional para mantener
   * compatibilidad con la rotation path (``motivo=null``) y la
   * segunda‑placa path (``motivo='segunda_placa_misma_mensualidad'``).
   */
  motivo: z.string().nullable().optional(),
});

/**
 * `cobrar: false` variant — short-circuit for an active monthly
 * subscription (F1.8 archive, REQ-OPS-023). Mirrors backend
 * `CotizarMensualidad` at `backend/.../schemas/operacion.py:175-190`.
 */
export const CotizarMensualidadSchema = z.object({
  cobrar: z.literal(false),
  motivo: z.literal('mensualidad_vigente'),
});

/**
 * F1.8 canonical discriminated union (REQ-OPS-022..025). Discriminator
 * is the `cobrar` field — TS exhaustive narrowing inside
 * `<CotizacionPanel />`: `if (data.cobrar === true)` triggers the full
 * fiscal branch, `else` triggers the mensualidad banner.
 */
export const CotizacionSchema = z.discriminatedUnion('cobrar', [
  CotizarFacturacionSchema,
  CotizarMensualidadSchema,
]);
export type Cotizacion = z.infer<typeof CotizacionSchema>;
export type CotizarFacturacion = z.infer<typeof CotizarFacturacionSchema>;
export type CotizarMensualidad = z.infer<typeof CotizarMensualidadSchema>;

export interface UseCotizacionReturn {
  data: Cotizacion | undefined;
  error: Error | undefined;
  refresh: () => Promise<Cotizacion | undefined>;
}

/**
 * Fetcher — receives the bare UUID; SWR key is opaque and used only
 * for cache identity (per the established `useOcupacion` precedent).
 *
 * Uses an `AbortController` with `OPERACION_COTIZAR_TIMEOUT_MS` to
 * cancel the fetch if the backend is hung.
 */
async function fetchCotizacion(
  uuid_ingreso: string,
  signal: AbortSignal,
): Promise<Cotizacion> {
  // Lazy import to keep the test mock boundary clean (matches the
  // `parkosFetch` import boundary in operacion/*Api.ts).
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/operacion/cotizar?uuid_ingreso=${encodeURIComponent(uuid_ingreso)}`,
    { signal },
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
    () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(
        () => controller.abort(),
        OPERACION_COTIZAR_TIMEOUT_MS,
      );
      return fetchCotizacion(uuid_ingreso as string, controller.signal).finally(
        () => clearTimeout(timeoutId),
      );
    },
    {
      refreshInterval: OPERACION_COTIZAR_REFRESH_INTERVAL_MS,
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
