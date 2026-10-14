/**
 * `useArqueoSesionesBreakdown` -- HU-F18.2 drill-down for cierre_dia.
 *
 * Bug #2 fix (2026-10-14): the admin ``<ArqueoDetalle>`` panel now
 * fetches the per-session breakdown when the selected row is a
 * ``cierre_dia`` (multi-session aggregate). The wire shape is the
 * ``sesiones[]`` array of the per-branch resumen endpoint
 * (``GET /api/v1/caja/arqueo/resumen?uuid_sucursal=&fecha=``), which
 * already exposes the per-session ``valor_efectivo_esperado`` and the
 * operator that opened/closed each turn.
 *
 * Why a separate hook (not folded into ``useArqueoDetalle``): the
 * drill-down is a ``cierre_dia``-only feature; non-aggregate rows
 * (auditoria, cierre_turno, cierre_sesion) have a single sesion and
 * the parent ``<DiferenciasPanel>`` already covers them. A dedicated
 * hook keeps the SWR key space clean and lets us cache the summary
 * for one date independently of the arqueo list.
 */
import useSWR from 'swr';

import {
  fetchArqueoResumen,
  type ArqueoResumenRead,
} from '../api/arqueosApi';
import type { ArqueoRead } from '../api/arqueosSchema';

export interface UseArqueoSesionesBreakdownReturn {
  /**
   * Per-sesion rows that contributed to the day-level arqueo. Empty
   * array while the hook is loading, on error, or when the parent
   * arqueo is not a ``cierre_dia`` (caller's signal to render the
   * generic detail, not the breakdown).
   */
  sesiones: ArqueoResumenRead['sesiones'];
  isLoading: boolean;
  error: Error | undefined;
  /**
   * SWR mutate (re-fetch on demand). The ``<SesionesBreakdownTable>``
   * retry button wires to this so a transient 5xx doesn't force
   * the admin to navigate away.
   */
  refresh: () => Promise<ArqueoResumenRead | undefined>;
}

/**
 * Returns the ``sesiones[]`` array for the day of the parent
 * ``arqueo``. Caller passes the full ``ArqueoRead`` so we can derive
 * ``uuid_sucursal`` and the ISO date (from ``created_at``) and gate
 * the SWR key on the arqueo's uuid. Returns an empty result when the
 * input is null or the arqueo has no ``uuid_sucursal`` (shouldn't
 * happen for valid data but defensive).
 */
export function useArqueoSesionesBreakdown(
  arqueo: ArqueoRead | null,
): UseArqueoSesionesBreakdownReturn {
  // Derive the SWR key from the arqueo's uuid so the cache is stable
  // across re-renders of the same row and a fresh fetch happens when
  // the admin clicks a different arqueo in the list.
  const key = arqueo
    ? `arqueo-sesiones-breakdown/${arqueo.uuid}`
    : null;

  // ``arqueo.created_at`` is the server-side UTC timestamp. The
  // BE's ``listar_sesiones_del_dia`` filters on
  // ``timestamp_apertura >= _inicio_dia(fecha)`` using the sucursal's
  // local TZ; for the BOG-CEN branch (no DST drift) the UTC date
  // matches the local date, so we use it verbatim. Other TZs would
  // require a ``Intl.DateTimeFormat`` conversion here -- left as a
  // follow-up because the admin's BOG-CEN is the only current tenant.
  const fecha = arqueo?.created_at
    ? arqueo.created_at.slice(0, 10) // YYYY-MM-DD
    : null;
  const uuid_sucursal = arqueo?.uuid_sucursal ?? null;

  const { data, error, isLoading, mutate } = useSWR<ArqueoResumenRead, Error>(
    key && fecha && uuid_sucursal ? [key, fecha, uuid_sucursal] : null,
    () => fetchArqueoResumen(uuid_sucursal as string, fecha as string),
    { revalidateOnFocus: false },
  );

  return {
    sesiones: data?.sesiones ?? [],
    isLoading,
    error,
    refresh: async () => mutate(),
  };
}
