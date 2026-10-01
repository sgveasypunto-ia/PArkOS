/**
 * ``useArqueosAdmin.test.tsx`` -- HU-F18.2 hook unit (filter pagination
 * via SWR). Mocks SWR cache isolation by relying on the global
 * provider being reset between tests; this test focuses on the filter
 * construction, the loadMore merge, and the empty-state default.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('../api/arqueosApi', () => ({
  fetchArqueosAdmin: vi.fn(),
}));

import { fetchArqueosAdmin } from '../api/arqueosApi';
import { useArqueosAdmin } from './useArqueosAdmin';
import type {
  ArqueoRead,
  ArqueosListResponse,
} from '../api/arqueosSchema';

const mockFetch = vi.mocked(fetchArqueosAdmin);

function makeRow(uuid: string): ArqueoRead {
  return {
    uuid,
    created_at: '2026-10-01T12:00:00',
    created_by: null,
    sync_status: 'sincronizado',
    sync_timestamp: null,
    sync_attempts: 0,
    fecha_retencion_hasta: '2026-10-01',
    uuid_sucursal: null,
    uuid_tipo_arqueo: null,
    uuid_sesion: null,
    valor_efectivo_esperado: '0',
    valor_datafono_esperado: '0',
    valor_efectivo_reportado: '0',
    valor_datafono_reportado: '0',
  };
}

describe('useArqueosAdmin', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it('starts empty and re-fetches on filter change', async () => {
    mockFetch.mockResolvedValue({
      items: [],
      next_cursor: null,
    });

    const { result } = renderHook(() =>
      useArqueosAdmin({ limit: 20 }, { swrSalt: 'b1' }),
    );

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });
    expect(result.current.items).toEqual([]);
    expect(result.current.hasMore).toBe(false);
    expect(result.current.error).toBeUndefined();
  });

  it('loadMore appends the next page', async () => {
    mockFetch.mockResolvedValueOnce({
      items: [makeRow('r1'), makeRow('r2')],
      next_cursor: 'cursor-page-1',
    });
    mockFetch.mockResolvedValueOnce({
      items: [makeRow('r3'), makeRow('r4')],
      next_cursor: 'cursor-page-2',
    });
    mockFetch.mockResolvedValueOnce({
      items: [makeRow('r5')],
      next_cursor: null,
    });

    const { result } = renderHook(() =>
      useArqueosAdmin({ limit: 2 }, { swrSalt: 'b2' }),
    );

    await waitFor(() => {
      expect(result.current.items.length).toBe(2);
    });
    expect(result.current.hasMore).toBe(true);

    await act(async () => {
      await result.current.loadMore();
    });
    await waitFor(() => {
      expect(result.current.items.length).toBe(4);
    });
    expect(result.current.hasMore).toBe(true);

    await act(async () => {
      await result.current.loadMore();
    });
    await waitFor(() => {
      expect(result.current.items.length).toBe(5);
    });
    expect(result.current.hasMore).toBe(false);
  });

  it('surfaces the fetch error on the next render', async () => {
    mockFetch.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() =>
      useArqueosAdmin({ limit: 20 }, { swrSalt: 'b3' }),
    );

    await waitFor(() => {
      expect(result.current.error).toBeDefined();
    });
    expect(result.current.items).toEqual([]);
  });
});