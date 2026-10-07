/**
 * Gating de `useTarifaByUuid`: ninguna request para uuid vacio / nulo /
 * nil (`00000000-...`). Se mockea `swr` para inspeccionar la key.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const swrKeys: Array<string | null> = [];

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: { accessToken: string | null }) => unknown) =>
      selector({ accessToken: 'tok' }),
    { getState: () => ({ clear: vi.fn() }) },
  ),
}));
vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class extends Error {
    status = 0;
  },
}));
vi.mock('../api/tarifasSucursalApi', () => ({
  getTarifaSucursalByUuid: vi.fn(),
}));
vi.mock('swr', () => ({
  default: (key: string | null) => {
    swrKeys.push(key);
    return { data: undefined, error: undefined, isLoading: false, mutate: vi.fn() };
  },
}));

import { useTarifaByUuid } from './useTarifaByUuid';

const REAL = '00000000-0000-0000-0000-0000000000aa';
const NIL = '00000000-0000-0000-0000-000000000000';

describe('useTarifaByUuid — gating de la key SWR', () => {
  beforeEach(() => {
    swrKeys.length = 0;
  });

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['cadena vacia', ''],
    ['espacios', '   '],
    ['uuid nil', NIL],
  ])('%s → key null (sin request)', (_label, value) => {
    renderHook(() => useTarifaByUuid(value as string | null));
    expect(swrKeys.at(-1)).toBeNull();
  });

  it('uuid real → key con el uuid', () => {
    renderHook(() => useTarifaByUuid(REAL));
    expect(swrKeys.at(-1)).toBe(`/empresa/tarifas-sucursal/${REAL}`);
  });
});
