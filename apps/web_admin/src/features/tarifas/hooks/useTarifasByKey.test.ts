/**
 * useTarifasByKey — unit tests (vitest + @testing-library/react renderHook).
 *
 * Pins:
 *   1. Happy path: the fetcher is called with the right query params.
 *   2. Empty key (no accessToken) → no fetch fires, returns [].
 *   3. 401 → useAuthStore cleared + 'parkos:auth:cleared' event dispatched.
 *   4. 404 → no retry (valid state: admin has not seeded this key yet).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import type * as FetchModule from '@parkos/ui-kit/fetch';

vi.mock('@parkos/ui-kit/fetch', async () => {
  const actual = await vi.importActual<typeof FetchModule>('@parkos/ui-kit/fetch');
  return {
    ...actual,
    parkosFetchRaw: vi.fn(),
  };
});

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';
import { listTarifasByKey } from '../api/tarifasApi';
import { useTarifasByKey } from './useTarifasByKey';

vi.mock('../api/tarifasApi', () => ({
  listTarifasByKey: vi.fn(),
  listTarifas: vi.fn(),
  getTarifa: vi.fn(),
  createTarifa: vi.fn(),
  updateTarifa: vi.fn(),
}));

const mockedListByKey = listTarifasByKey as ReturnType<typeof vi.fn>;
const mockedFetchRaw = parkosFetchRaw as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SUCURSAL = '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6';
const SAMPLE_VERSION = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: SUCURSAL,
  uuid_tipo_vehiculo: null,
  uuid_tipo_tarifa: null,
  valor: '1500.0000',
  valor_plena: '2000.0000',
  vigente_desde: '2026-09-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedListByKey.mockReset();
  mockedFetchRaw.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('useTarifasByKey', () => {
  it('A1: happy path returns the version chain from the by-key endpoint', async () => {
    mockedListByKey.mockResolvedValueOnce([SAMPLE_VERSION]);
    const { result } = renderHook(
      () => useTarifasByKey(SUCURSAL, null, null),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.versiones).toHaveLength(1);
    });
    expect(result.current.versiones[0]).toEqual(SAMPLE_VERSION);
    expect(result.current.isLoading).toBe(false);
    expect(mockedListByKey).toHaveBeenCalledWith({
      sucursal: SUCURSAL,
      tipo_vehiculo: null,
      tipo_tarifa: null,
    });
  });

  it('A2: no accessToken → no fetch, returns []', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
    const { result } = renderHook(
      () => useTarifasByKey(SUCURSAL, null, null),
      { wrapper },
    );
    expect(result.current.versiones).toEqual([]);
    expect(mockedListByKey).not.toHaveBeenCalled();
  });

  it('A3: 404 (no seed for this key yet) does not retry', async () => {
    mockedListByKey.mockRejectedValueOnce(
      new ParkosHttpError(404, 'tarifa_no_encontrada', '/api/v1/empresa/tarifas-sucursal/by-key'),
    );
    const { result } = renderHook(
      () => useTarifasByKey(SUCURSAL, null, null),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(ParkosHttpError);
    });
    // SWR's default is 5 retries with exponential backoff; we set
    // shouldRetryOnError(false) for 404, so exactly 1 call.
    expect(mockedListByKey).toHaveBeenCalledTimes(1);
  });

  it('A4: 401 triggers auth store clear and parkos:auth:cleared event', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    mockedListByKey.mockRejectedValueOnce(
      new ParkosHttpError(401, 'unauthorized', '/api/v1/admin/me'),
    );
    renderHook(() => useTarifasByKey(SUCURSAL, null, null), { wrapper });
    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
    const cleared = dispatchSpy.mock.calls.some(
      (call) => (call[0] as Event).type === 'parkos:auth:cleared',
    );
    expect(cleared).toBe(true);
    dispatchSpy.mockRestore();
  });
});
