/**
 * `useTipoArqueoPorCodigo.ts` — SWR hook that resolves a ``codigo``
 * (e.g. ``'auditoria'``, ``'cierre_turno'``) into its UUID via
 * ``GET /api/v1/catalogos/tipo-arqueo``.
 *
 * The BE handler at `api/v1/caja_arqueo.py:77` resolves the
 * ``payload.uuid_tipo_arqueo`` (UUID, NOT codigo) against
 * ``prod.tipo_arqueo`` and branches on the resolved row's
 * ``tipo_arqueo.codigo`` for the cierre_dia / auditoria discrimination
 * logic. The FE used to send ``tipo_arqueo: 'auditoria'`` (a string
 * codigo) which the BE V2 schema rejects via ``extra='forbid'``.
 *
 * F11.3 follow-up: introduce this hook so callers (ArqueoParcial,
 * CerrarTurnoForm, etc.) can resolve a codigo to its UUID before
 * submit. Mirrors the F1.17 ``useTiposSubscripciones`` hook
 * (apps/electron-sucursal/src/features/suscripciones/hooks/useTiposSubscripciones.ts)
 * -- same SWR deduping policy, same 401 clear-on-error semantics,
 * same Bearer auth chain.
 */
import useSWR from 'swr';
import { z } from 'zod';

import { parkosFetch, ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAuthStore } from '@parkos/ui-kit/store';

export const TipoArqueoPorCodigoSchema = z
  .object({
    uuid: z.string().uuid(),
    codigo: z.string().nullable(),
    nombre: z.string().nullable(),
    descripcion: z.string().nullable(),
    vigente_desde: z.string().optional(),
    vigente_hasta: z.string().nullable().optional(),
    estado: z.string().optional(),
    created_at: z.string().optional(),
    created_by: z.string().nullable().optional(),
    sync_status: z.string().nullable().optional(),
  })
  // NOT .strict() -- the catalogo GET returns the full audit + bi-temporal
  // columns; we only need uuid+codigo for the arqueo submit. The
  // V2 BE rejects unknown fields on the WRITE side (ArqueoCreateV2),
  // not on the read side.
  ;
export type TipoArqueoPorCodigo = z.infer<typeof TipoArqueoPorCodigoSchema>;

const TipoArqueoListSchema = z.object({
  items: z.array(TipoArqueoPorCodigoSchema),
  next_cursor: z.string().nullable().optional(),
});

/**
 * Resolve a ``codigo`` (e.g. ``'auditoria'``) to its catalog row.
 *
 * @param codigo The business codigo to look up. When `null`, the hook
 *   is gated off (no fetch).
 *
 * @returns `{ uuid, codigo, nombre, descripcion }` of the matching row
 *   when found, `undefined` while loading, `null` when no matching
 *   row exists in the current-version catalog. Errors propagate via
 *   SWR's error channel (the parent renders an error state).
 */
export function useTipoArqueoPorCodigo(
  codigo: 'auditoria' | 'cierre_turno' | 'cierre_sesion' | 'cierre_dia' | null,
): {
  data: TipoArqueoPorCodigo | undefined;
  uuid: string | undefined;
  error: Error | undefined;
} {
  const accessToken = useAuthStore((s) => s.accessToken);

  // Fetch the full list once and filter client-side. The catalogo
  // GET supports a `codigo` filter, but the F1.13 list_endpoint does
  // NOT wire filters in the factory mount -- it returns ALL current
  // rows (vigente_hasta IS NULL). Filtering on the FE side is fine
  // since the type_arqueo catalog is small (~9 rows total).
  const key =
    codigo && accessToken ? `/catalogos/tipo-arqueo?limit=200` : null;

  const { data, error } = useSWR<{ uuid: string; codigo: string | null }>(
    key,
    async () => {
      const raw = await parkosFetch<unknown>(`/api/v1${key}`);
      const parsed = TipoArqueoListSchema.parse(raw);
      const row = parsed.items.find((it) => it.codigo === codigo);
      if (!row) {
        throw new Error(`tipo_arqueo con codigo='${codigo}' no existe en el catálogo.`);
      }
      return row;
    },
    {
      dedupingInterval: 60_000, // catalog rows change at most once per F1.x migration
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
    data: data as TipoArqueoPorCodigo | undefined,
    uuid: data?.uuid,
    error: error as Error | undefined,
  };
}
