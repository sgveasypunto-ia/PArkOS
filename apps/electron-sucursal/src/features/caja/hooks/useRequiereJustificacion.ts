/**
 * `useRequiereJustificacion.ts` — SWR hook for the HU-F10.2 follow-up
 * conteo-ciego pre-flight (bugfix 2026-10-01).
 *
 * Replaces the client-side `difTotal` heuristic in `<CerrarTurnoForm>`
 * (which compared the operator's reported count against
 * `sesion.valor_inicial_*` and gave a false negative whenever the
 * session had any transactions — the real esperado is
 * `inicial + SUM(factura_pagos)`, server-side only, DEC-ARQUEO-10) with
 * a live call to `GET /caja/arqueo/requiere-justificacion`, which runs
 * the SAME Step 5/6 diferencia check the real `POST /caja/arqueo` will
 * run on submit.
 *
 * Conteo ciego (plan.md HU-F10.2): the endpoint returns ONLY the
 * boolean verdict — the esperado amounts themselves never reach the
 * client, not even over the wire. This hook must not be changed to
 * request or surface those amounts.
 */
import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { z } from 'zod';

import { parkosFetch, ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAuthStore } from '@parkos/ui-kit/store';

const RequiereJustificacionSchema = z
  .object({ requiere_justificacion: z.boolean() })
  .strict();

/** Debounce window (ms) before a changed count triggers a network call.
 * SWR only dedupes IDENTICAL keys within `dedupingInterval` — a
 * changing reported value is a NEW key on every keystroke, so the
 * debounce lives here, not in the SWR config. */
const DEBOUNCE_MS = 400;

/**
 * @param uuid_sesion Active sesion uuid, or `null` to disable the fetch.
 * @param valorEfectivoReportado Operator's in-progress efectivo count.
 * @param valorDatafonoReportado Operator's in-progress datáfono count.
 *
 * @returns `requiereJustificacion`: `true`/`false` once the backend has
 *   answered for the current (debounced) counts, `undefined` while
 *   loading or disabled. Callers MUST treat `undefined` as "assume a
 *   difference" (conservative) — NOT as `false` — so the UI never
 *   enables the close button on a stale/absent answer.
 */
export function useRequiereJustificacion(
  uuid_sesion: string | null,
  valorEfectivoReportado: number,
  valorDatafonoReportado: number,
): {
  requiereJustificacion: boolean | undefined;
  error: Error | undefined;
} {
  const accessToken = useAuthStore((s) => s.accessToken);

  const [debounced, setDebounced] = useState({
    efectivo: valorEfectivoReportado,
    datafono: valorDatafonoReportado,
  });
  useEffect(() => {
    const id = setTimeout(() => {
      setDebounced({ efectivo: valorEfectivoReportado, datafono: valorDatafonoReportado });
    }, DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [valorEfectivoReportado, valorDatafonoReportado]);

  const key =
    uuid_sesion && accessToken
      ? `/caja/arqueo/requiere-justificacion?uuid_sesion=${encodeURIComponent(uuid_sesion)}&valor_efectivo_reportado=${debounced.efectivo}&valor_datafono_reportado=${debounced.datafono}`
      : null;

  const { data, error } = useSWR<{ requiere_justificacion: boolean }>(
    key,
    async () => {
      const raw = await parkosFetch<unknown>(`/api/v1${key}`);
      return RequiereJustificacionSchema.parse(raw);
    },
    {
      dedupingInterval: DEBOUNCE_MS,
      shouldRetryOnError: (err) => {
        if (err instanceof ParkosHttpError) {
          return (
            err.status !== 401 &&
            err.status !== 403 &&
            err.status !== 404 &&
            err.status !== 409
          );
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
    requiereJustificacion: data?.requiere_justificacion,
    error: error as Error | undefined,
  };
}
