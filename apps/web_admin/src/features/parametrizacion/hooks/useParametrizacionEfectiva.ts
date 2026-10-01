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

  const { data, error, isLoading } = useSWR(key, () =>
    getParametrizacionEfectiva(uuidSucursal!, fecha),
  );

  return {
    fecha,
    setFecha,
    resetAHoy,
    counts: data,
    isLoading,
    error,
  };
}
