/**
 * tarifasApi — regression test for `listTarifasByKey`'s response shape.
 *
 * QA batch tarifas/cupos: `GET /tarifas-sucursal/by-key` returns a bare
 * JSON array (`response_model=list[TarifasSucursalRead]`), but
 * `listTarifasByKey` used to parse it with `tarifaReadListEnvelopeSchema`
 * (expects `{items: [...], next_cursor}`). Every real call threw a
 * ZodError, silently swallowed by SWR into `versiones: []` -- "Ver
 * histórico" always rendered "Sin versiones registradas." even when the
 * backend had real version rows (confirmed live via chrome-devtools).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type * as FetchModule from '@parkos/ui-kit/fetch';

vi.mock('@parkos/ui-kit/fetch', async () => {
  const actual = await vi.importActual<typeof FetchModule>('@parkos/ui-kit/fetch');
  return {
    ...actual,
    parkosFetchRaw: vi.fn(),
  };
});

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';
import { useAuthStore } from '@parkos/ui-kit/store';
import { listTarifasByKey } from './tarifasApi';

const mockedFetchRaw = parkosFetchRaw as ReturnType<typeof vi.fn>;

const SAMPLE = {
  uuid: 'bbbbbbbb-1111-1111-1111-111111111111',
  uuid_sucursal: '22222222-2222-2222-2222-222222222222',
  uuid_tipo_vehiculo: 'cccccccc-1111-1111-1111-111111111111',
  uuid_tipo_tarifa: '12e3886a-7059-47ee-bdb2-aa5fb1272bea',
  valor: '3000.0000',
  valor_plena: null,
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: null,
};

beforeEach(() => {
  mockedFetchRaw.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('listTarifasByKey', () => {
  it('parses the bare array the backend actually returns (not an {items} envelope)', async () => {
    mockedFetchRaw.mockResolvedValueOnce(
      new Response(JSON.stringify([SAMPLE]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const result = await listTarifasByKey({ sucursal: SAMPLE.uuid_sucursal! });
    expect(result).toHaveLength(1);
    expect(result[0]?.uuid).toBe(SAMPLE.uuid);
  });
});
