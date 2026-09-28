/**
 * useConfiguracionTolerancias — unit tests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

vi.mock('../api/configuracionToleranciasApi', () => ({
  listConfiguracionTolerancias: vi.fn(),
  getConfiguracionTolerancias: vi.fn(),
  createConfiguracionTolerancias: vi.fn(),
  updateConfiguracionTolerancias: vi.fn(),
}));

import { listConfiguracionTolerancias } from '../api/configuracionToleranciasApi';
import { useConfiguracionTolerancias } from './useConfiguracionTolerancias';

const mockedList = listConfiguracionTolerancias as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SAMPLE = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: null,
  tolerancia_efectivo: '100.0000',
  tolerancia_datafono: '200.0000',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

beforeEach(() => {
  mockedList.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('useConfiguracionTolerancias', () => {
  it('T1: happy path returns the list', async () => {
    mockedList.mockResolvedValueOnce([SAMPLE]);
    const { result } = renderHook(() => useConfiguracionTolerancias(), { wrapper });
    await waitFor(() => {
      expect(result.current.rows).toHaveLength(1);
    });
    expect(result.current.rows[0]).toEqual(SAMPLE);
  });

  it('T2: no accessToken → no fetch, returns []', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
    const { result } = renderHook(() => useConfiguracionTolerancias(), { wrapper });
    expect(result.current.rows).toEqual([]);
    expect(mockedList).not.toHaveBeenCalled();
  });

  it('T3: 404 (no seed yet) does not retry', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(404, 'no_rows', '/api/v1/.../configuracion-tolerancias'),
    );
    renderHook(() => useConfiguracionTolerancias(), { wrapper });
    await waitFor(() => {
      expect(mockedList).toHaveBeenCalledTimes(1);
    });
  });

  it('T4: 401 → auth store clear', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(401, 'unauthorized', '/api/v1/admin/me'),
    );
    renderHook(() => useConfiguracionTolerancias(), { wrapper });
    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
  });
});
