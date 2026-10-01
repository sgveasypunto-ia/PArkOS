/**
 * useConfiguracionSeguridad — unit tests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

vi.mock('../api/configuracionSeguridadApi', () => ({
  listConfiguracionSeguridad: vi.fn(),
  getConfiguracionSeguridad: vi.fn(),
  getConfiguracionSeguridadEfectiva: vi.fn(),
  createConfiguracionSeguridad: vi.fn(),
  updateConfiguracionSeguridad: vi.fn(),
}));

import { listConfiguracionSeguridad } from '../api/configuracionSeguridadApi';
import { useConfiguracionSeguridad } from './useConfiguracionSeguridad';

const mockedList = listConfiguracionSeguridad as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SAMPLE = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: null,
  dias_expiracion_password: 90,
  max_intentos_login: 5,
  minutos_bloqueo_login: 15,
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

describe('useConfiguracionSeguridad', () => {
  it('S1: happy path returns the list', async () => {
    mockedList.mockResolvedValueOnce([SAMPLE]);
    const { result } = renderHook(() => useConfiguracionSeguridad(), { wrapper });
    await waitFor(() => {
      expect(result.current.rows).toHaveLength(1);
    });
    expect(result.current.rows[0]).toEqual(SAMPLE);
  });

  it('S2: no accessToken → no fetch, returns []', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
    const { result } = renderHook(() => useConfiguracionSeguridad(), { wrapper });
    expect(result.current.rows).toEqual([]);
    expect(mockedList).not.toHaveBeenCalled();
  });

  it('S3: 404 does not retry', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(404, 'no_rows', '/api/v1/.../configuracion-seguridad'),
    );
    renderHook(() => useConfiguracionSeguridad(), { wrapper });
    await waitFor(() => {
      expect(mockedList).toHaveBeenCalledTimes(1);
    });
  });

  it('S4: 401 → auth store clear', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(401, 'unauthorized', '/api/v1/admin/me'),
    );
    renderHook(() => useConfiguracionSeguridad(), { wrapper });
    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
  });
});
