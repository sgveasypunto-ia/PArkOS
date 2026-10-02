/**
 * useParametrizacionEfectiva — regression test for the "Hoy" selector bug
 * (QA batch tarifas/cupos, 2026-10-02).
 *
 * BUGFIX: the hook used to call `getParametrizacionEfectiva(uuid, fecha)`
 * with the bare `YYYY-MM-DD` string. The backend's `vigente_en` query
 * param is a `datetime` -- FastAPI/pydantic parses a date-only string as
 * MIDNIGHT, not "now". Selecting "Hoy" therefore asked "what was vigente
 * at 00:00 today" and undercounted anything created later today (e.g. a
 * tarifa created at 17:16 was invisible to a "Hoy" query run at 17:40).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

vi.mock('../api/parametrizacionEfectivaApi', () => ({
  getParametrizacionEfectiva: vi.fn(),
}));

import { getParametrizacionEfectiva } from '../api/parametrizacionEfectivaApi';
import { useParametrizacionEfectiva, formatFechaEfectiva } from './useParametrizacionEfectiva';

const mockedGet = getParametrizacionEfectiva as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SUCURSAL = '22222222-2222-2222-2222-222222222222';

beforeEach(() => {
  mockedGet.mockReset();
  mockedGet.mockResolvedValue({
    tarifasVigentes: 0,
    capacidadVigente: 0,
    resolucionesVigentes: 0,
  });
});

describe('useParametrizacionEfectiva', () => {
  it('PE1: default selection ("Hoy") queries a full timestamp, not a bare date', async () => {
    const before = Date.now();
    renderHook(() => useParametrizacionEfectiva(SUCURSAL), { wrapper });
    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    const after = Date.now();

    const [, vigenteEnArg] = mockedGet.mock.calls[0] as [string, string];
    // Must NOT be the bare `YYYY-MM-DD` the pre-fix code sent (FastAPI
    // parses that as midnight, not "now").
    expect(vigenteEnArg).not.toBe(formatFechaEfectiva(new Date()));
    expect(vigenteEnArg).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    const parsed = new Date(vigenteEnArg).getTime();
    expect(parsed).toBeGreaterThanOrEqual(before);
    expect(parsed).toBeLessThanOrEqual(after);
  });

  it('PE2: a non-today selection keeps the bare-date (midnight) semantics', async () => {
    const { result } = renderHook(() => useParametrizacionEfectiva(SUCURSAL), { wrapper });
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));

    mockedGet.mockClear();
    result.current.setFecha('2020-01-01');
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(1));
    expect(mockedGet.mock.calls[0]?.[1]).toBe('2020-01-01');
  });
});
