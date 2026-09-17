/**
 * `useIngresoActivo(placa)` — SWR hook for the active-ingreso lookup
 * (HU-F6.1, T4).
 *
 * Path 1 composition (design.md §Decision: Path 1 — zero backend
 * change): the hook calls `getIngresosByPlaca(placa)` and resolves the
 * `latestIngreso` client-side by sorting on `fecha_ingreso` descending.
 * For now, `hasActive === (latestIngreso !== undefined)` — the
 * backend-side `?activo=true` companion (T0b, ~15 LOC) is the precise
 * fix; F6.1 ships the client-side simplification per the design's
 * "Path 1 simplification documented in design §Open Questions".
 *
 * Shape mirrors F4.3 `useOcupacion` + F4.1 `useTiposVehiculo`:
 *   - SWR key gated by `(placa, accessToken)`: returns `null` when
 *     either is missing — SWR treats `null` keys as "skip" so we do
 *     NOT fire requests pre-login or with empty placa.
 *   - `shouldRetryOnError` excludes 401/403/404 — auth store reacts
 *     to 401, 403/404 are terminal.
 *   - `onError` 401 → `useAuthStore.clear()` + `parkos:auth:cleared`
 *     (F2.2 precedent — defensive logout).
 *
 * Note on the F6.1 spec error catalog: `409 ingreso_activo_existente`
 * is the backend's authoritative source for the redirect — that error
 * comes from `POST /operacion/ingresos`, NOT from this read. The hook
 * here is a PRE-FLIGHT convenience: it lets the UI redirect before the
 * POST is attempted. When the POST eventually fires, the 409 remains
 * authoritative (per spec §Open question "Path 1 false-negative").
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { getIngresosByPlaca, type Ingreso } from '../api/ingresoActivoApi';

const DEDUPING_INTERVAL_MS = 5_000;

export interface IngresoActivoState {
  /** True when the most-recent row exists for the plate (Path 1 heuristic). */
  hasActive: boolean;
  /** Most-recent row by `fecha_ingreso`, or `null` if list is empty. */
  latestIngreso: Ingreso | null;
  isLoading: boolean;
  error: Error | undefined;
  /** Manual SWR revalidation — useful after a successful POST that closes the row. */
  refresh: () => Promise<Ingreso[] | undefined>;
}

function buildKey(
  placa: string | null,
  accessToken: string | null,
): string | null {
  if (!placa) return null;
  if (!accessToken) return null;
  return `/api/v1/operacion/ingresos?placa=${encodeURIComponent(placa)}`;
}

/**
 * SWR hook returning the most-recent `Ingreso` for the typed plate.
 * Empty list → `hasActive: false`. 401 → defensive logout (F2.2
 * precedent). Other errors propagate to the page via `error`.
 */
export function useIngresoActivo(placa: string | null): IngresoActivoState {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = buildKey(placa, accessToken);

  const { data, error, isLoading, mutate } = useSWR<Ingreso[]>(
    key,
    () => getIngresosByPlaca(placa as string),
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
        console.warn('[useIngresoActivo] fetch failed', err);
      },
    },
  );

  // Path 1 simplification: client-side sort on `fecha_ingreso` DESC.
  // ISO 8601 strings sort lexicographically the same way they sort
  // chronologically — no Date conversion needed.
  const latestIngreso = pickLatest(data);

  return {
    hasActive: latestIngreso !== null,
    latestIngreso,
    isLoading,
    error,
    refresh: async () => mutate(),
  };
}

function pickLatest(rows: Ingreso[] | undefined): Ingreso | null {
  if (!rows || rows.length === 0) return null;
  // `[...rows].sort()` avoids mutating the SWR-cached array.
  const sorted = [...rows].sort((a, b) =>
    b.fecha_ingreso.localeCompare(a.fecha_ingreso),
  );
  return sorted[0] ?? null;
}
