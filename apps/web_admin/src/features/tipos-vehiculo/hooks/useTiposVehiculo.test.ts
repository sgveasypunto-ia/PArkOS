/**
 * useTiposVehiculo — unit tests.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

vi.mock('../api/tiposVehiculoApi', () => ({
  listTiposVehiculo: vi.fn(),
  getTipoVehiculo: vi.fn(),
  createTipoVehiculo: vi.fn(),
  updateTipoVehiculo: vi.fn(),
}));

import { listTiposVehiculo } from '../api/tiposVehiculoApi';
import { useTiposVehiculo } from './useTiposVehiculo';

const mockedList = listTiposVehiculo as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SAMPLE = {
  uuid: '11111111-1111-1111-1111-111111111111',
  tipo: 'carro',
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

describe('useTiposVehiculo', () => {
  it('T1: happy path returns the API list', async () => {
    mockedList.mockResolvedValueOnce([SAMPLE]);
    const { result } = renderHook(() => useTiposVehiculo(), { wrapper });
    await waitFor(() => {
      expect(result.current.tipos).toEqual([SAMPLE]);
    });
    expect(result.current.isFromFallback).toBe(false);
    expect(mockedList).toHaveBeenCalledWith({ limit: 200 });
  });

  it('T2: no accessToken → fallback (HARDCODED_CATALOG) without fetch', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
    const { result } = renderHook(() => useTiposVehiculo(), { wrapper });
    expect(result.current.tipos).toHaveLength(2);
    expect(result.current.tipos[0]?.tipo).toBe('carro');
    expect(result.current.tipos[1]?.tipo).toBe('moto');
    expect(result.current.isFromFallback).toBe(true);
    expect(mockedList).not.toHaveBeenCalled();
  });

  it('T3: API 5xx → isFromFallback=true (sentinel compare)', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(503, 'service_unavailable', '/api/v1/.../tipos-vehiculo'),
    );
    const { result } = renderHook(() => useTiposVehiculo(), { wrapper });
    // SWR will retry; the fallback is shown once an error is set.
    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(ParkosHttpError);
    });
    // fallbackData is `HARDCODED_CATALOG`, so data === fallback → isFromFallback true.
    expect(result.current.isFromFallback).toBe(true);
  });

  it('T4: 401 triggers auth store clear', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(401, 'unauthorized', '/api/v1/admin/me'),
    );
    renderHook(() => useTiposVehiculo(), { wrapper });
    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
  });
});
