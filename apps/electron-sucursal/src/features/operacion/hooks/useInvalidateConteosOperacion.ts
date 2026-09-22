/**
 * `useInvalidateConteosOperacion.ts` — SWR cache invalidator for the
 * live count panels (HU-F6.x + HU-F7.x + HU-F12.1).
 *
 * Panel/endpoint matrix that this hook invalidates after a mutation:
 *
 *   1. `/operacion/mi-turno?uuid_sesion=X`
 *      → `<MiTurnoPanel />` (right sidebar) — ingresos_count / salidas_count
 *   2. `/operacion/ocupacion?uuid_sucursal=X`
 *      → `<OcupacionPanel />` (right sidebar Inventario card)
 *   3. `/operacion/ingresos?uuid_sucursal=X`
 *      → `<VehiculosDentroList />` (left main column "Vehículos dentro")
 *
 * Why the hook exists
 * -------------------
 * All three panels use SWR with `refreshInterval` (15s for mi-turno,
 * 10s for ocupacion/ingresos) — but the operator expects to see the
 * count change IMMEDIATELY after an ingreso or salida (directiva del
 * operador 2026-09-22). Polling alone leaves a visible lag where the
 * panel keeps showing the pre-mutation number until the next tick.
 *
 * `useSWRConfig().mutate(matcher)` invalidates the SWR cache for any
 * key that matches the predicate and triggers an immediate re-fetch on
 * the next render. The same pattern is used by `useResolverAlerta`
 * (DA-F11.2-8) — invalidating only the keys we own avoids stomping on
 * unrelated caches.
 *
 * Note: the `<OcupacionPanel />` data ultimately comes from
 * `prod.mv_ocupacion_diaria`. Even with the SWR cache cleared, the MV
 * lags BE-side until either the `RefreshMvOcupacionWorker` (10s
 * cadence) wakes up OR `prod.refresh_mv_ocupacion_diaria()` is called
 * by the BE handler (security-definer function — separate fix in the
 * BE). The two layers compose: this hook ensures the FE never waits
 * an extra 10s once the BE returns fresh data; the BE-side refresh
 * ensures the MV itself is fresh immediately after the mutation.
 *
 * Why the matcher accepts both the original and the cached form
 * --------------------------------------------------------------
 * `useIngresoActivo` uses key
 * `/api/v1/operacion/ingresos?placa=...` while `useIngresosActivos`
 * (Dashboard) uses `/api/v1/operacion/ingresos?uuid_sucursal=...`.
 * Matching on `'/operacion/ingresos'` catches BOTH so the panel that
 * lists every active ingreso re-fetches regardless of which key the
 * active page mounted.
 */
import { useCallback } from 'react';
import { useSWRConfig } from 'swr';

export interface InvalidateConteosInput {
  uuid_sucursal: string | null;
  /**
   * Optional — when provided, also invalidates the per-turn cache.
   * Pass `null` when called from a context that does not have a
   * sesion (e.g. an anonymous POST). The hook short-circuits in
   * that case (F12.1 zero-state per REQ-OPS-188).
   */
  uuid_sesion: string | null;
}

/**
 * Returns a stable callback that invalidates the three SWR keys
 * involved in the live count panels. Call it AFTER the mutation
 * succeeds (201 for ingreso / salida, or after PagoSheet 201).
 */
export function useInvalidateConteosOperacion(): (
  input: InvalidateConteosInput,
) => Promise<void> {
  const { mutate } = useSWRConfig();

  return useCallback(
    async ({ uuid_sucursal, uuid_sesion }: InvalidateConteosInput) => {
      // Build matchers ONCE — `mutate(matcher)` re-evaluates per key.
      const matchers: Array<(key: unknown) => boolean> = [];

      if (uuid_sucursal !== null) {
        const suc = uuid_sucursal;
        matchers.push(
          (key) =>
            typeof key === 'string' && key.includes(`/operacion/ocupacion?uuid_sucursal=${suc}`),
          (key) =>
            typeof key === 'string' && key.includes(`/operacion/ingresos?uuid_sucursal=${suc}`),
          (key) =>
            // Catch the alternative key shape (per-placa lookup) — same
            // canonical path prefix, different query string.
            typeof key === 'string' && key.includes('/api/v1/operacion/ingresos') && key.includes(suc),
        );
      }

      if (uuid_sesion !== null) {
        const ses = uuid_sesion;
        matchers.push(
          (key) =>
            typeof key === 'string' &&
            key.includes(`/operacion/mi-turno?uuid_sesion=${ses}`),
        );
      }

      if (matchers.length === 0) {
        // Nothing to invalidate — caller passed all-null context. Exit
        // silently; the panels fall back to their zero-state until the
        // next poll. Should not happen in practice but defensive.
        return;
      }

      // `mutate(undefined, undefined, { revalidate: true })` with a
      // matcher predicate revalidates every key whose matcher returns
      // true. SWR runs each matcher against the cached key; the call
      // is fire-and-forget (no awaited promise per matching key).
      await Promise.all(
        matchers.map((matcher) =>
          mutate(matcher, undefined, { revalidate: true }),
        ),
      );
    },
    [mutate],
  );
}
