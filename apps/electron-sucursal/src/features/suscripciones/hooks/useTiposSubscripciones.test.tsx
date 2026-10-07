/**
 * `useTiposSubscripciones` — plan catalog filtered by vehicle type (PT-2).
 *
 *   T1: with a vehicle type -> `?uuid_sucursal=..&uuid_tipo_vehiculo=..`.
 *   T2: `undefined` type (legacy callers) -> no `uuid_tipo_vehiculo` param.
 *   T3: `null` type (not chosen yet) -> SWR key gated, NO fetch (never show
 *       plans of the wrong type).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@parkos/ui-kit/store', () => {
  const state = { accessToken: 'tok-abc', clear: vi.fn() };
  return {
    useAuthStore: Object.assign(
      (sel: (s: typeof state) => unknown) => sel(state),
      { getState: () => state },
    ),
  };
});

const mockFetch = vi.fn();
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: unknown[]) => mockFetch(...args),
  ParkosHttpError: class extends Error {
    public readonly status: number;
    constructor(status: number) {
      super(`ParkosHttpError ${status}`);
      this.status = status;
    }
  },
}));

import type { ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';

import { useTiposSubscripciones } from './useTiposSubscripciones';

const wrapper = ({ children }: { children: ReactNode }): JSX.Element => (
  <SWRConfig value={{ provider: () => new Map() }}>{children}</SWRConfig>
);

const PLAN = {
  uuid: '00000000-0000-0000-0000-0000000000a1',
  tipo: 'MENSUAL_MOTO',
  valor: '30000.00',
  duracion_dias: 30,
  cantidad_maxima_vehiculos: 1,
  mismo_tipo_vehiculo: true,
  uuid_tipo_vehiculo: '00000000-0000-0000-0000-00000000aa01',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useTiposSubscripciones — PT-2', () => {
  it('T1: requests only plans of the chosen vehicle type', async () => {
    mockFetch.mockResolvedValueOnce({ items: [PLAN], next_cursor: null });
    const { result } = renderHook(
      () => useTiposSubscripciones('suc-1', '00000000-0000-0000-0000-00000000aa01'),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockFetch.mock.calls[0]?.[0]).toBe(
      '/api/v1/catalogos/tipo-subscripciones?uuid_sucursal=suc-1&uuid_tipo_vehiculo=00000000-0000-0000-0000-00000000aa01',
    );
    expect(result.current.data?.[0]?.uuid_tipo_vehiculo).toBe('00000000-0000-0000-0000-00000000aa01');
  });

  it('T2: undefined type keeps the unfiltered URL', async () => {
    mockFetch.mockResolvedValueOnce({ items: [], next_cursor: null });
    const { result } = renderHook(() => useTiposSubscripciones('suc-1'), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/catalogos/tipo-subscripciones?uuid_sucursal=suc-1');
  });

  it('T3: null type -> no fetch at all', async () => {
    renderHook(() => useTiposSubscripciones('suc-1', null), { wrapper });
    await new Promise((r) => setTimeout(r, 0));
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
