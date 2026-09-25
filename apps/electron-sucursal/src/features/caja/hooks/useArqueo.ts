/**
 * `useArqueo.ts` — SWR hook for arqueo state (HU-F10.1).
 *
 * Mutation-only — arqueo is a write action (`POST /caja/arqueo`).
 * The hook exposes a `submit` function and a `resumen` getter
 * (`GET /caja/arqueo/resumen`) for the cierre-diario panel.
 *
 * F11.3 follow-up: the FE used to send ``tipo_arqueo: 'auditoria'``
 * (a string codigo) which the BE V2 schema rejects via
 * ``extra='forbid'``. The handler at api/v1/caja_arqueo.py:77 expects
 * ``uuid_tipo_arqueo`` (UUID). Callers (ArqueoParcial, CerrarTurnoForm)
 * now resolve the codigo via ``useTipoArqueoPorCodigo`` and pass the
 * UUID directly. This hook accepts the UUID shape only.
 */
import { z } from 'zod';

export const ArqueoResumenSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  fecha: z.string(),
  total_efectivo_cop: z.number().int().nonnegative(),
  total_datafono_cop: z.number().int().nonnegative(),
  diferencia_cop: z.number().int(),
  sesiones_cerradas: z.number().int().nonnegative(),
});
export type ArqueoResumen = z.infer<typeof ArqueoResumenSchema>;

async function fetchResumen(uuid_sucursal: string, fecha: string): Promise<ArqueoResumen> {
  const { parkosFetch } = await import('@parkos/ui-kit/fetch');
  const raw = await parkosFetch<unknown>(
    `/api/v1/caja/arqueo/resumen?uuid_sucursal=${encodeURIComponent(uuid_sucursal)}&fecha=${encodeURIComponent(fecha)}`,
  );
  return ArqueoResumenSchema.parse(raw);
}

export function useArqueo() {
  return {
    async submit(payload: {
      uuid_sesion: string;
      uuid_tipo_arqueo: string;  // F11.3: UUID, not codigo string
      valor_efectivo_reportado: number;
      valor_datafono_reportado: number;
      justificacion?: string;
    }): Promise<{ uuid: string }> {
      const { parkosFetch } = await import('@parkos/ui-kit/fetch');
      const raw = await parkosFetch<unknown>(
        '/api/v1/caja/arqueo',
        { method: 'POST', body: JSON.stringify(payload) },
      );
      const parsed = z.object({ uuid: z.string().uuid() }).parse(raw);
      return parsed;
    },
    fetchResumen,
  };
}

/**
 * `useArqueoResumen` — SWR wrapper for the cierre-diario resumen.
 * Key gate: `null` when uuid_sucursal is empty.
 */
import useSWR from 'swr';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export function useArqueoResumen(
  uuid_sucursal: string | null,
  fecha: string | null,
): {
  data: ArqueoResumen | undefined;
  error: Error | undefined;
  refresh: () => Promise<ArqueoResumen | undefined>;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key = uuid_sucursal && fecha && accessToken
    ? `/caja/arqueo/resumen?uuid_sucursal=${uuid_sucursal}&fecha=${fecha}`
    : null;

  const { data, error, mutate } = useSWR<ArqueoResumen>(
    key,
    () => fetchResumen(uuid_sucursal as string, fecha as string),
    {
      dedupingInterval: 10_000,
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
        }
      },
    },
  );

  return {
    data,
    error,
    refresh: async () => mutate(),
  };
}

/**
 * NOTE (housekeeping, 2026-09-25): `useCierreDiario()` — the legacy
 * full-day cierre helper this module used to export — was removed
 * here. It was already `@deprecated` (superseded by
 * `runCierreDiarioChain` in `pages/cierreDiarioChain.ts`, REQ-OPS-166),
 * had ZERO real callers (`CierreDiarioDialog.tsx` calls `useArqueo()`
 * directly; `CierreDiario.tsx` explicitly documents "NO
 * useCierreDiario() legacy helper"), and its only remaining call site
 * was `pages/__tests__/CierreDiario.test.tsx`'s `vi.mock(...)`-based
 * test-double — never the real implementation. Its `submit({ ...payload,
 * tipo_arqueo: 'cierre_dia' })` call also no longer matched
 * `useArqueo().submit`'s F11.3 `uuid_tipo_arqueo` (UUID) contract
 * (`cierreDiarioChain.ts`'s own comment calls it "the buggy
 * useCierreDiario() helper"), so removing genuinely-dead, already-
 * documented-broken code is the root-cause fix rather than repairing
 * a field name only to keep shipping unreachable, deprecated code.
 */

/**
 * Re-export the F10.3 sibling SWR hook for tree-shaking convenience.
 * F10.1 callers continue using the legacy `useArqueoResumen` aggregate
 * hook unchanged (NEW-DA-F10.3-9 regression guard).
 */
export { useArqueoResumenPorSesion } from './useArqueoResumenPorSesion';