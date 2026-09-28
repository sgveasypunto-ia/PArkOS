/**
 * useCantidadByKey — unit tests (vitest + renderHook).
 *
 * Same pattern as useTarifasByKey.test.ts: pins happy path, empty
 * key, 404 no-retry, 401 logout.
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

vi.mock('../api/cuposApi', () => ({
  listCupos: vi.fn(),
  listCuposByKey: vi.fn(),
  getCupo: vi.fn(),
  createCupo: vi.fn(),
  updateCupo: vi.fn(),
}));

import { listCuposByKey } from '../api/cuposApi';
import { useCantidadByKey } from './useCantidadByKey';

const mockedListByKey = listCuposByKey as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SUCURSAL = '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6';
const SAMPLE = {
  uuid: '22222222-2222-2222-2222-222222222222',
  uuid_sucursal: SUCURSAL,
  uuid_tipo_vehiculo: null,
  cantidad: 50,
  vigente_desde: '2026-09-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedListByKey.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('useCantidadByKey', () => {
  it('B1: happy path returns the version chain', async () => {
    mockedListByKey.mockResolvedValueOnce([SAMPLE]);
    const { result } = renderHook(() => useCantidadByKey(SUCURSAL, null), { wrapper });
    await waitFor(() => {
      expect(result.current.versiones).toHaveLength(1);
    });
    expect(result.current.versiones[0]).toEqual(SAMPLE);
    expect(mockedListByKey).toHaveBeenCalledWith({ sucursal: SUCURSAL, tipo_vehiculo: null });
  });

  it('B2: no accessToken → no fetch, returns []', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
    const { result } = renderHook(() => useCantidadByKey(SUCURSAL, null), { wrapper });
    expect(result.current.versiones).toEqual([]);
    expect(mockedListByKey).not.toHaveBeenCalled();
  });

  it('B3: 404 (no seed for this key yet) does not retry', async () => {
    mockedListByKey.mockRejectedValueOnce(
      new ParkosHttpError(404, 'cantidad_no_encontrada', '/api/v1/.../by-key'),
    );
    renderHook(() => useCantidadByKey(SUCURSAL, null), { wrapper });
    await waitFor(() => {
      expect(mockedListByKey).toHaveBeenCalledTimes(1);
    });
  });

  it('B4: 401 triggers auth store clear', async () => {
    mockedListByKey.mockRejectedValueOnce(
      new ParkosHttpError(401, 'unauthorized', '/api/v1/admin/me'),
    );
    renderHook(() => useCantidadByKey(SUCURSAL, null), { wrapper });
    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
  });
});
