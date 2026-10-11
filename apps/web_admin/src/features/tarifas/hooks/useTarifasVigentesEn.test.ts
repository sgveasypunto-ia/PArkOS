/**
 * useTarifasVigentesEn — unit tests (vitest + renderHook).
 *
 * Unlike useTarifasByKey (which uses listTarifasByKey + parkosFetchRaw),
 * this hook talks to the dedicated HU-F1.4 endpoint via raw ``fetch``
 * because the dedicated handler emits the envelope directly. We mock
 * ``window.fetch`` instead of the api layer.
 *
 * Pins: happy path with vigente_en, 404 no-retry, 401 logout.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

import { useAuthStore } from '@parkos/ui-kit/store';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import { useTarifasVigentesEn } from './useTarifasVigentesEn';

const mockedFetch = vi.fn();
vi.stubGlobal('fetch', mockedFetch);

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SUCURSAL = '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6';
const SAMPLE = {
  uuid: '11111111-1111-1111-1111-111111111111',
  uuid_sucursal: SUCURSAL,
  uuid_tipo_vehiculo: null,
  uuid_tipo_tarifa: null,
  valor: '1500.0000',
  valor_plena: '2000.0000',
  vigente_desde: '2026-09-01T00:00:00Z',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-09-01T00:00:00Z',
  created_by: null,
  sync_status: 'sincronizado',
};

function okResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function errorResponse(status: number): Response {
  return new Response(JSON.stringify({ detail: { error: 'err' } }), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

beforeEach(() => {
  mockedFetch.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('useTarifasVigentesEn', () => {
  it('C1: happy path parses the envelope and returns items', async () => {
    mockedFetch.mockResolvedValueOnce(okResponse({ items: [SAMPLE], next_cursor: null }));
    const { result } = renderHook(
      () => useTarifasVigentesEn(SUCURSAL, '2026-09-15T12:00:00Z'),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.tarifas).toHaveLength(1);
    });
    expect(result.current.tarifas[0]).toEqual(SAMPLE);
    const calledUrl = mockedFetch.mock.calls[0]?.[0] as string | undefined;
    expect(calledUrl).toBeDefined();
    // URLSearchParams encodes `:` as %3A — compare on the encoded form.
    expect(calledUrl).toContain('vigente_en=2026-09-15T12%3A00%3A00Z');
    expect(calledUrl).toContain('/api/v1/empresa/tarifas-sucursal?');
  });

  it('C2: no vigente_en query param omits the param (server default)', async () => {
    mockedFetch.mockResolvedValueOnce(okResponse({ items: [SAMPLE], next_cursor: null }));
    renderHook(() => useTarifasVigentesEn(SUCURSAL, null), { wrapper });
    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalled();
    });
    const calledUrl = mockedFetch.mock.calls[0]?.[0] as string | undefined;
    expect(calledUrl).toBeDefined();
    expect(calledUrl).not.toContain('vigente_en=');
  });

  it('C3: 404 (no tarifas yet) returns []', async () => {
    mockedFetch.mockResolvedValueOnce(errorResponse(404));
    const { result } = renderHook(
      () => useTarifasVigentesEn(SUCURSAL, '2026-09-15T12:00:00Z'),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.tarifas).toEqual([]);
    });
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it('C4: 401 triggers auth store clear', async () => {
    mockedFetch.mockResolvedValueOnce(errorResponse(401));
    renderHook(() => useTarifasVigentesEn(SUCURSAL, null), { wrapper });
    await waitFor(() => {
      expect(useAuthStore.getState().accessToken).toBeNull();
    });
  });

  it('C5: 500 surfaces the ParkosHttpError to the consumer', async () => {
    mockedFetch.mockResolvedValueOnce(errorResponse(500));
    const { result } = renderHook(
      () => useTarifasVigentesEn(SUCURSAL, null),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.error).toBeInstanceOf(ParkosHttpError);
    });
  });
});
