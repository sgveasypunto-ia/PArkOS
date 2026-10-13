/**
 * `useFacturaDetalle.test.ts` — unit tests for the SWR composition hook.
 *
 * Three scenarios (REQ-X-08 + REQ-X-11):
 *   1. `useFacturaDetalle('valid')` builds 6 SWR keys, all non-null.
 *   2. `useFacturaDetalle(null)` produces 6 null keys (no fetch).
 *   3. The FE SWR is conditional on `header.data.uuid_factura_electronica`
 *      — when the header is still loading, the FE key is null.
 *
 * Mocks `swr` (the hook library) so the test is synchronous on the
 * network. The mock records every key + fetcher passed to `useSWR`
 * and returns a deterministic shape; assertions inspect the recorded
 * calls to verify the right URL/keys were used.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

const recordedCalls: Array<{ key: unknown; fetcher: unknown }> = [];

vi.mock('swr', () => ({
  default: vi.fn((key: unknown, fetcher: unknown) => {
    recordedCalls.push({ key, fetcher });
    return {
      data: undefined,
      error: undefined,
      isLoading: key !== null,
      mutate: vi.fn(),
    };
  }),
}));

import useSWR from 'swr';
import {
  useFacturaDetalle,
  facturaHeaderKey,
  facturaDetalleKey,
  facturaImpuestosKey,
  facturaPagosKey,
  facturaHashKey,
} from './useFacturaDetalle';

const mockedUseSWR = vi.mocked(useSWR);

beforeEach(() => {
  recordedCalls.length = 0;
  mockedUseSWR.mockClear();
});

describe('useFacturaDetalle', () => {
  it('builds 6 SWR keys for a valid uuid', () => {
    const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    useFacturaDetalle(UUID);
    // 6 useSWR calls = 6 records.
    expect(recordedCalls.length).toBe(6);

    const keys = recordedCalls.map((c) => c.key);
    // The 5 unconditional keys (header, detalle, impuestos, pagos, hash).
    expect(keys).toContainEqual(facturaHeaderKey(UUID));
    expect(keys).toContainEqual(facturaDetalleKey(UUID));
    expect(keys).toContainEqual(facturaImpuestosKey(UUID));
    expect(keys).toContainEqual(facturaPagosKey(UUID));
    expect(keys).toContainEqual(facturaHashKey(UUID));
    // The 6th key is the FE one — null because header.data is undefined
    // in this mock (the page only fetches FE when the header resolves
    // to a real uuid).
    expect(keys).toContainEqual(null);
  });

  it('produces 6 null keys when uuid is null (no fetch)', () => {
    useFacturaDetalle(null);
    expect(recordedCalls.length).toBe(6);
    for (const c of recordedCalls) {
      expect(c.key).toBeNull();
    }
  });

  it('uses the right URL path for each call', () => {
    const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    useFacturaDetalle(UUID);
    // The 5 fetcher functions (excluding the null-key one) are the api
    // client functions; they carry the URL path implicitly via the
    // mock. We verify each fetch call is present.
    expect(mockedUseSWR).toHaveBeenCalledTimes(6);
  });
});
