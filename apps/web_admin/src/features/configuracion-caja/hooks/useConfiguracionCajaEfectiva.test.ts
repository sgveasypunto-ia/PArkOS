/**
 * useConfiguracionCajaEfectiva — unit tests.
 *
 * Mirrors `configuracion-tolerancias/hooks/useConfiguracionTolerancias.test.ts`
 * conventions (SWR + vi.mock on the api module), adapted to the
 * `.../configuracion-caja/efectiva` resolution shape: the api layer
 * returns `null` on a 404 (neither override nor global default
 * configured) instead of throwing — see `configuracionCajaApi.ts`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

vi.mock('../api/configuracionCajaApi', () => ({
  getConfiguracionCajaEfectiva: vi.fn(),
}));

import { getConfiguracionCajaEfectiva } from '../api/configuracionCajaApi';
import { useConfiguracionCajaEfectiva } from './useConfiguracionCajaEfectiva';

const mockedGetEfectiva = getConfiguracionCajaEfectiva as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SUCURSAL = 'cccccccc-1111-1111-1111-111111111111';

const OVERRIDE_ROW = {
  uuid: '22222222-2222-2222-2222-222222222222',
  uuid_sucursal: SUCURSAL,
  base_inicial_sugerida: '100000.0000',
  redondeo: '100',
  denominaciones_permitidas: [1000, 2000, 5000],
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedGetEfectiva.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useConfiguracionCajaEfectiva', () => {
  it('T1: happy path returns the effective row', async () => {
    mockedGetEfectiva.mockResolvedValueOnce(OVERRIDE_ROW);
    const { result } = renderHook(() => useConfiguracionCajaEfectiva(SUCURSAL), { wrapper });
    await waitFor(() => {
      expect(result.current.data).toEqual(OVERRIDE_ROW);
    });
    expect(mockedGetEfectiva).toHaveBeenCalledWith(SUCURSAL);
  });

  it('T2: 404 (ni override ni default global) resuelve a null, sin error', async () => {
    mockedGetEfectiva.mockResolvedValueOnce(null);
    const { result } = renderHook(() => useConfiguracionCajaEfectiva(SUCURSAL), { wrapper });
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeUndefined();
  });

  it('T3: sin uuidSucursal → no fetch', () => {
    const { result } = renderHook(() => useConfiguracionCajaEfectiva(undefined), { wrapper });
    expect(result.current.data).toBeUndefined();
    expect(mockedGetEfectiva).not.toHaveBeenCalled();
  });

  it('T4: error no-404 se propaga', async () => {
    mockedGetEfectiva.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderHook(() => useConfiguracionCajaEfectiva(SUCURSAL), { wrapper });
    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(Error);
    });
  });

  it('T5: refresh() vuelve a pedir el efectivo', async () => {
    mockedGetEfectiva.mockResolvedValueOnce(OVERRIDE_ROW);
    const { result } = renderHook(() => useConfiguracionCajaEfectiva(SUCURSAL), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(OVERRIDE_ROW));

    mockedGetEfectiva.mockResolvedValueOnce(null);
    await result.current.refresh();
    await waitFor(() => expect(result.current.data).toBeNull());
    expect(mockedGetEfectiva).toHaveBeenCalledTimes(2);
  });
});
