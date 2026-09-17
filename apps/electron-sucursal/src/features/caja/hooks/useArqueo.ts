/**
 * `useArqueo.ts` — SWR hook for arqueo state (HU-F10.1).
 *
 * Mutation-only — arqueo is a write action (`POST /caja/arqueo`).
 * The hook exposes a `submit` function and a `resumen` getter
 * (`GET /caja/arqueo/resumen`) for the cierre-diario panel.
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
      tipo_arqueo: 'auditoria' | 'cierre_turno' | 'cierre_dia';
      efectivo_contado_cop: number;
      datafono_contado_cop: number;
      observaciones?: string;
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
 * `useCierreDiario` — full-day cierre helper. Chains arqueo per
 * session + resumen fetch.
 */
export function useCierreDiario() {
  const { submit } = useArqueo();
  return {
    async ejecutar(payload: {
      uuid_sesion: string;
      efectivo_contado_cop: number;
      datafono_contado_cop: number;
      observaciones?: string;
    }): Promise<{ uuid: string }> {
      return submit({
        ...payload,
        tipo_arqueo: 'cierre_dia',
      });
    },
  };
}