/**
 * Unit tests for `useTiposVehiculoSinPlaca` (REQ-OPS-196, HU-INGRESO-SIN-PLACA).
 *
 * Filters `useTiposVehiculo()` to tipos that have NO placa regex:
 *   - Keep: `bicicleta`, `patineta`.
 *   - Exclude: `carro`, `moto`.
 *
 * The hook is a thin projection over `useTiposVehiculo()`, so we mock
 * `useSWR` (via `vi.mock`) to feed the catalog directly. Three scenarios
 * cover the membership + empty-state branches.
 */
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TipoVehiculo } from '../api/tiposVehiculoApi';

const useSWRMock = vi.fn();

vi.mock('swr', () => ({
  default: (...args: unknown[]) => useSWRMock(...args),
}));

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: vi.fn((selector: (s: { accessToken: string | null }) => unknown) =>
    selector({ accessToken: 'test-token' }),
  ),
}));

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class ParkosHttpError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

// Import AFTER mocks so the hook's module-level references pick up
// the mocked `swr` default export.
import { useTiposVehiculoSinPlaca } from './useTiposVehiculoSinPlaca';

function makeTipo(overrides: Partial<TipoVehiculo>): TipoVehiculo {
  return {
    uuid: '00000000-0000-0000-0000-000000000000',
    tipo: 'carro',
    vigente_desde: '2026-01-01T00:00:00Z',
    vigente_hasta: null,
    estado: 'activo',
    ...overrides,
  };
}

describe('useTiposVehiculoSinPlaca (REQ-OPS-196)', () => {
  beforeEach(() => {
    useSWRMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('test_filter_excludes_carro_moto', () => {
    useSWRMock.mockReturnValue({
      data: [
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000001', tipo: 'carro' }),
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000002', tipo: 'moto' }),
      ],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    const { result } = renderHook(() => useTiposVehiculoSinPlaca());
    expect(result.current.tipos).toHaveLength(0);
    expect(result.current.tipos.map((t) => t.tipo)).not.toContain('carro');
    expect(result.current.tipos.map((t) => t.tipo)).not.toContain('moto');
  });

  it('test_filter_includes_bicicleta_patineta', () => {
    useSWRMock.mockReturnValue({
      data: [
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000001', tipo: 'carro' }),
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000002', tipo: 'moto' }),
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000003', tipo: 'bicicleta' }),
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000004', tipo: 'patineta' }),
      ],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    const { result } = renderHook(() => useTiposVehiculoSinPlaca());
    expect(result.current.tipos).toHaveLength(2);
    expect(result.current.tipos.map((t) => t.tipo).sort()).toEqual([
      'bicicleta',
      'patineta',
    ]);
  });

  it('test_filter_empty_when_catalog_only_has_placa_tipos (HARDCODED_CATALOG fallback)', () => {
    // When the API is down, `useTiposVehiculo()` returns the F4.1
    // HARDCODED_CATALOG `{carro, moto}` sentinel. The filter result is
    // empty → `<IngresoSinPlacaPanel>` renders the degraded-UX message.
    useSWRMock.mockReturnValue({
      data: [
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000001', tipo: 'carro' }),
        makeTipo({ uuid: '00000000-0000-0000-0000-000000000002', tipo: 'moto' }),
      ],
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    });

    const { result } = renderHook(() => useTiposVehiculoSinPlaca());
    expect(result.current.tipos).toHaveLength(0);
    expect(result.current.isFromFallback).toBe(false);
  });
});
