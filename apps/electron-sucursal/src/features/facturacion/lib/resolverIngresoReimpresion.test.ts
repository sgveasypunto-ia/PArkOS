import { beforeEach, describe, expect, it, vi } from 'vitest';

import { parkosFetch } from '@parkos/ui-kit/fetch';

import { resolverIngresoReimpresion } from './resolverIngresoReimpresion';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: vi.fn(),
}));

const mockFetch = parkosFetch as ReturnType<typeof vi.fn>;

const ingresoConPlaca = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: '22222222-2222-2222-2222-222222222222',
  placa: 'ABC123',
  fecha_ingreso: '2026-09-17T10:00:00Z',
  uuid_subscripcion_cliente: null,
};

const ingresoSinPlaca = {
  uuid: '33333333-3333-3333-3333-333333333333',
  uuid_sucursal: '22222222-2222-2222-2222-222222222222',
  placa: null,
  fecha_ingreso: '2026-09-17T10:00:00Z',
  uuid_subscripcion_cliente: null,
  consecutivo: 'BICICLETA-000001-aaaaaaaa',
};

beforeEach(() => {
  mockFetch.mockReset();
});

describe('resolverIngresoReimpresion', () => {
  it('returns "found" when only the placa lookup matches', async () => {
    mockFetch.mockImplementation(async (path: string) => {
      if (path.includes('placa=')) return [ingresoConPlaca];
      return [];
    });
    const result = await resolverIngresoReimpresion('ABC123');
    expect(result).toEqual({ kind: 'found', ingreso: ingresoConPlaca });
  });

  it('returns "found" when only the consecutivo (cupo) lookup matches', async () => {
    mockFetch.mockImplementation(async (path: string) => {
      if (path.includes('consecutivo=')) return [ingresoSinPlaca];
      return [];
    });
    const result = await resolverIngresoReimpresion('BICICLETA-000001-aaaaaaaa');
    expect(result).toEqual({ kind: 'found', ingreso: ingresoSinPlaca });
  });

  it('returns "none" when neither lookup matches', async () => {
    mockFetch.mockResolvedValue([]);
    const result = await resolverIngresoReimpresion('NOEXISTE');
    expect(result).toEqual({ kind: 'none', termino: 'NOEXISTE' });
  });

  it('returns "none" for a blank term without calling the API', async () => {
    const result = await resolverIngresoReimpresion('   ');
    expect(result).toEqual({ kind: 'none', termino: '' });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('returns "multiple" when both a placa and a consecutivo candidate match', async () => {
    mockFetch.mockImplementation(async (path: string) => {
      if (path.includes('placa=')) return [ingresoConPlaca];
      if (path.includes('consecutivo=')) return [ingresoSinPlaca];
      return [];
    });
    const result = await resolverIngresoReimpresion('AMBIGUO');
    expect(result.kind).toBe('multiple');
    if (result.kind === 'multiple') {
      expect(result.candidatos).toHaveLength(2);
    }
  });
});
