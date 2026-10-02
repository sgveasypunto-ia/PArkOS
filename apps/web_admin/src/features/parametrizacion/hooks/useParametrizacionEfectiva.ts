/**
 * `useParametrizacionEfectiva` — HU-F15.1 BR4 shared hook.
 *
 * Resolves the "what was vigente on date X" counts (tarifas, capacidad,
 * resoluciones) for one branch, driven by the `vigente_en` state owned
 * here and rendered via `<ParametrizacionEfectivaSelector />`. Exported
 * from `features/parametrizacion/` (not nested under `sucursales/` or
 * `tarifas/`) so later Fase 15 HUs can reuse both the hook and the
 * selector in their own tabs without a cross-feature import.
 */
import { useCallback, useMemo, useState } from 'react';
import useSWR from 'swr';

import {
  getParametrizacionEfectiva,
  type ParametrizacionEfectivaCounts,
} from '../api/parametrizacionEfectivaApi';

/** `YYYY-MM-DD` in LOCAL time (not `toISOString()`, which is UTC and can
 * roll the date back/forward a day near midnight for non-UTC operators). */
export function formatFechaEfectiva(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export interface UseParametrizacionEfectivaReturn {
  /** Current selection, always a valid `YYYY-MM-DD` string. */
  fecha: string;
  /** Replace the selection (validates: ignores empty/malformed input). */
  setFecha: (value: string) => void;
  /** Reset the selection to today. */
  resetAHoy: () => void;
  counts: ParametrizacionEfectivaCounts | undefined;
  isLoading: boolean;
  error: Error | undefined;
}

export function useParametrizacionEfectiva(
  uuidSucursal: string | undefined,
): UseParametrizacionEfectivaReturn {
  const [fecha, setFechaState] = useState<string>(() => formatFechaEfectiva(new Date()));

  const setFecha = useCallback((value: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return;
    setFechaState(value);
  }, []);

  const resetAHoy = useCallback(() => {
    setFechaState(formatFechaEfectiva(new Date()));
  }, []);

  const key = useMemo(
    () => (uuidSucursal ? `parametrizacion-efectiva-${uuidSucursal}-${fecha}` : null),
    [uuidSucursal, fecha],
  );

  const { data, error, isLoading } = useSWR(key, () => {
    // BUGFIX (QA batch tarifas/cupos, 2026-10-02): the backend's
    // `vigente_en` is a `datetime` -- sending the bare `YYYY-MM-DD`
    // `fecha` made FastAPI/pydantic parse it as MIDNIGHT (naive = UTC),
    // not "now". Selecting "Hoy" therefore asked "what was vigente at
    // 00:00 today" instead of "what is vigente right now", undercounting
    // (or omitting entirely) any row whose `vigente_desde` falls later
    // today but before the real current instant. For "hoy" specifically
    // we must send the actual current timestamp; a past/future date
    // keeps its existing midnight-of-that-day semantics (unaffected by
    // this bug report, out of scope to redefine here).
    const vigenteEn =
      fecha === formatFechaEfectiva(new Date()) ? new Date().toISOString() : fecha;
    return getParametrizacionEfectiva(uuidSucursal!, vigenteEn);
  });

  return {
    fecha,
    setFecha,
    resetAHoy,
    counts: data,
    isLoading,
    error,
  };
}
