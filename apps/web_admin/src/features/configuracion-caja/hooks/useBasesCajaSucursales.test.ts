/**
 * `useBasesCajaSucursales()` — each branch carries its own base, else inherits the default.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

const listMock = vi.fn();
const createMock = vi.fn();
const updateMock = vi.fn();

vi.mock('../api/configuracionCajaApi', () => ({
  listConfiguracionCaja: (...a: unknown[]) => listMock(...a),
  createConfiguracionCaja: (...a: unknown[]) => createMock(...a),
  updateConfiguracionCaja: (...a: unknown[]) => updateMock(...a),
}));

import { useBasesCajaSucursales } from './useBasesCajaSucursales';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const C = '33333333-3333-4333-8333-333333333333';

function fila(uuid: string, sucursal: string | null, base: string | null, vigenteHasta: string | null = null) {
  return {
    uuid,
    uuid_sucursal: sucursal,
    base_inicial_sugerida: base,
    redondeo: '100',
    denominaciones_permitidas: [1000, 2000],
    vigente_desde: '2026-10-01T00:00:00',
    vigente_hasta: vigenteHasta,
    estado: vigenteHasta === null ? 'activo' : 'inactivo',
    created_at: '2026-10-01T00:00:00',
    created_by: null,
    sync_status: null,
  };
}

const wrapper = ({ children }: { children: ReactNode }) =>
  createElement(SWRConfig, { value: { provider: () => new Map(), dedupingInterval: 0 } }, children);

beforeEach(() => {
  vi.clearAllMocks();
  listMock.mockResolvedValue([
    fila('r-a-old', A, '40000.0000', '2026-10-05T00:00:00'), // closed version: ignored
    fila('r-a', A, '50000.0000'),
    fila('r-b', B, '80000.0000'),
    fila('r-global', null, '60000.0000'),
  ]);
  createMock.mockResolvedValue({});
  updateMock.mockResolvedValue({});
});

describe('useBasesCajaSucursales', () => {
  it('cada sucursal tiene su base; la que no, hereda el default global', async () => {
    const { result } = renderHook(() => useBasesCajaSucursales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.baseDe(A)).toEqual({ base: '50000.0000', origen: 'propia' });
    expect(result.current.baseDe(B)).toEqual({ base: '80000.0000', origen: 'propia' });
    expect(result.current.baseDe(C)).toEqual({ base: '60000.0000', origen: 'global' });
    expect(result.current.baseGlobal).toBe('60000.0000');
  });

  it('sin default ni override la sucursal queda sin configurar', async () => {
    listMock.mockResolvedValue([fila('r-a', A, '50000.0000')]);
    const { result } = renderHook(() => useBasesCajaSucursales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.baseDe(C)).toEqual({ base: null, origen: 'sin_configurar' });
    expect(result.current.baseGlobal).toBeNull();
  });

  it('guardar sobre una sucursal con base propia actualiza esa fila (close+insert en el backend)', async () => {
    const { result } = renderHook(() => useBasesCajaSucursales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await result.current.guardar(A, 70000);

    expect(updateMock).toHaveBeenCalledWith(
      'r-a',
      expect.objectContaining({
        uuid_sucursal: A,
        base_inicial_sugerida: '70000',
        redondeo: '100',
        denominaciones_permitidas: ['1000', '2000'],
      }),
    );
    expect(createMock).not.toHaveBeenCalled();
  });

  it('guardar sobre una sucursal sin base propia crea su override (no toca el default)', async () => {
    const { result } = renderHook(() => useBasesCajaSucursales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await result.current.guardar(C, 90000);

    expect(createMock).toHaveBeenCalledWith(
      expect.objectContaining({ uuid_sucursal: C, base_inicial_sugerida: '90000' }),
    );
    expect(updateMock).not.toHaveBeenCalled();
  });

  it('guardar con null edita el default global', async () => {
    const { result } = renderHook(() => useBasesCajaSucursales(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await result.current.guardar(null, 65000);

    expect(updateMock).toHaveBeenCalledWith(
      'r-global',
      expect.objectContaining({ uuid_sucursal: null, base_inicial_sugerida: '65000' }),
    );
  });
});
