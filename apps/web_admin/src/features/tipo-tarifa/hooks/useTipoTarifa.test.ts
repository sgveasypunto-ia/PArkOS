/**
 * useTipoTarifa — unit tests (mirrors useTiposVehiculo.test.ts).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

vi.mock('../api/tipoTarifaApi', () => ({
  listTipoTarifa: vi.fn(),
  getTipoTarifa: vi.fn(),
  createTipoTarifa: vi.fn(),
  updateTipoTarifa: vi.fn(),
}));

import { listTipoTarifa } from '../api/tipoTarifaApi';
import { useTipoTarifa } from './useTipoTarifa';

const mockedList = listTipoTarifa as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SAMPLE = {
  uuid: '11111111-1111-1111-1111-111111111111',
  tipo: 'hora',
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

describe('useTipoTarifa', () => {
  it('T1: happy path', async () => {
    mockedList.mockResolvedValueOnce([SAMPLE]);
    const { result } = renderHook(() => useTipoTarifa(), { wrapper });
    await waitFor(() => {
      expect(result.current.tipos).toEqual([SAMPLE]);
    });
    expect(result.current.isFromFallback).toBe(false);
  });

  it('T2: no accessToken → HARDCODED_CATALOG', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
    const { result } = renderHook(() => useTipoTarifa(), { wrapper });
    expect(result.current.tipos).toHaveLength(4);
    expect(result.current.tipos.map((t) => t.tipo)).toEqual([
      'hora',
      'fraccion',
      'plena',
      'nocturna',
    ]);
    expect(result.current.isFromFallback).toBe(true);
    expect(mockedList).not.toHaveBeenCalled();
  });

  it('T3: 503 → isFromFallback=true', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(503, 'service_unavailable', '/api/v1/.../tipo-tarifa'),
    );
    const { result } = renderHook(() => useTipoTarifa(), { wrapper });
    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(ParkosHttpError);
    });
    expect(result.current.isFromFallback).toBe(true);
  });

  it('T4: 401 → auth store clear', async () => {
    mockedList.mockRejectedValueOnce(
      new ParkosHttpError(401, 'unauthorized', '/api/v1/admin/me'),
    );
    renderHook(() => useTipoTarifa(), { wrapper });
    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
  });
});
