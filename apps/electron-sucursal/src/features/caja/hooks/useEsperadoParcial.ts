/**
 * `useEsperadoParcial.ts` -- efectivo esperado del turno para el arqueo
 * PARCIAL (auditoria).
 *
 * El esperado lo calcula el servidor (`calcular_esperado_sesion`: base +
 * cobros en efectivo - reversos), el mismo valor que `POST /caja/arqueo`
 * registra. Antes la pantalla usaba solo la base y mostraba un faltante falso.
 *
 * SOLO para el arqueo parcial. El cierre de turno es a conteo ciego y NO debe
 * usar este hook (ver `useRequiereJustificacion`).
 */
import useSWR from 'swr';
import { z } from 'zod';

import { parkosFetch } from '@parkos/ui-kit/fetch';
import { useAuthStore } from '@parkos/ui-kit/store';

// Pydantic serializa Decimal como string en JSON.
const EsperadoParcialSchema = z
  .object({ valor_efectivo_esperado: z.coerce.number() })
  .strict();

export function useEsperadoParcial(uuid_sesion: string | null): {
  esperadoEfectivo: number | undefined;
  error: Error | undefined;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const key =
    uuid_sesion && accessToken
      ? `/caja/arqueo/esperado-parcial?uuid_sesion=${encodeURIComponent(uuid_sesion)}`
      : null;

  const { data, error } = useSWR<{ valor_efectivo_esperado: number }>(
    key,
    async () => {
      const raw = await parkosFetch<unknown>(`/api/v1${key}`);
      return EsperadoParcialSchema.parse(raw);
    },
    // Un cobro nuevo cambia el esperado: nunca servir un valor viejo.
    { dedupingInterval: 0, revalidateOnFocus: true },
  );

  return {
    esperadoEfectivo: data?.valor_efectivo_esperado,
    error: error as Error | undefined,
  };
}
