import { describe, expect, it, vi, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import type * as EnvioDianApiModule from '../api/envioDianApi';

vi.mock('../api/envioDianApi', async () => {
  const actual = await vi.importActual<typeof EnvioDianApiModule>('../api/envioDianApi');
  return { ...actual, fetchEnvioDianList: vi.fn() };
});

import { fetchEnvioDianList } from '../api/envioDianApi';
import { useEnvioDianChain } from './useEnvioDianChain';
import type { EnvioDianRead } from '../api/envioDianSchema';

const mockedFetch = fetchEnvioDianList as ReturnType<typeof vi.fn>;

const SUCURSAL = '22222222-2222-2222-2222-222222222222';

function envio(overrides: Partial<EnvioDianRead> = {}): EnvioDianRead {
  return {
    uuid: '00000000-0000-0000-0000-000000000000',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: SUCURSAL,
    uuid_factura_electronica: '33333333-3333-3333-3333-333333333333',
    uuid_resolucion_facturacion: null,
    payload: null,
    respuesta_proveedor: null,
    cufe: null,
    uuid_envio_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'pendiente',
    ...overrides,
  };
}

describe('useEnvioDianChain', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('returns a single-element chain when the tip has no parent', async () => {
    const tip = envio({ uuid: 'tip', uuid_envio_padre: null });
    const { result } = renderHook(() => useEnvioDianChain(tip));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.chain.map((r) => r.uuid)).toEqual(['tip']);
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it('walks uuid_envio_padre backwards across one page, oldest first', async () => {
    const root = envio({ uuid: 'root', estado: 'rechazado', uuid_envio_padre: null });
    const retry1 = envio({ uuid: 'retry1', estado: 'rechazado', uuid_envio_padre: 'root' });
    const tip = envio({ uuid: 'tip', estado: 'pendiente', uuid_envio_padre: 'retry1' });

    mockedFetch.mockResolvedValue({
      items: [tip, retry1, root],
      next_cursor: null,
    });

    const { result } = renderHook(() => useEnvioDianChain(tip));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.chain.map((r) => r.uuid)).toEqual(['root', 'retry1', 'tip']);
    expect(mockedFetch).toHaveBeenCalledWith(
      expect.objectContaining({ uuid_sucursal: SUCURSAL }),
    );
  });

  it('asks for EVERY row (solo_tip=false): the listing defaults to the last row per document', async () => {
    const root = envio({ uuid: 'root', uuid_envio_padre: null });
    const tip = envio({ uuid: 'tip', uuid_envio_padre: 'root' });
    mockedFetch.mockResolvedValue({ items: [tip, root], next_cursor: null });

    const { result } = renderHook(() => useEnvioDianChain(tip));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockedFetch).toHaveBeenCalledWith(expect.objectContaining({ solo_tip: false }));
  });

  it('pages forward when the parent is not on the first page', async () => {
    const root = envio({ uuid: 'root', uuid_envio_padre: null });
    const tip = envio({ uuid: 'tip', uuid_envio_padre: 'root' });

    mockedFetch
      .mockResolvedValueOnce({ items: [tip], next_cursor: 'cursor-2' })
      .mockResolvedValueOnce({ items: [root], next_cursor: null });

    const { result } = renderHook(() => useEnvioDianChain(tip));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.chain.map((r) => r.uuid)).toEqual(['root', 'tip']);
    expect(mockedFetch).toHaveBeenCalledTimes(2);
  });

  it('stops gracefully (no crash) when the parent is never found', async () => {
    const tip = envio({ uuid: 'tip', uuid_envio_padre: 'missing-parent' });
    mockedFetch.mockResolvedValue({ items: [], next_cursor: null });

    const { result } = renderHook(() => useEnvioDianChain(tip));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.chain.map((r) => r.uuid)).toEqual(['tip']);
    expect(result.current.error).toBeUndefined();
  });

  it('surfaces a fetch error without throwing into the render path', async () => {
    const tip = envio({ uuid: 'tip', uuid_envio_padre: 'root' });
    mockedFetch.mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => useEnvioDianChain(tip));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.chain).toEqual([]);
  });

  it('returns an empty chain for a null tip', () => {
    const { result } = renderHook(() => useEnvioDianChain(null));
    expect(result.current.chain).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });
});
