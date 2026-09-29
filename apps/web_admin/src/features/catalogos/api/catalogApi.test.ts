/**
 * `catalogApi.test.ts` — regression coverage for the body serialization bug
 * that produced `[object Object]` in the wire payload.
 *
 * Root cause: `createCatalogVersion`/`updateCatalogVersion` were passing
 * `payload as unknown as BodyInit` — a plain object that fetch couldn't
 * serialize. Pydantic received `'{}'` / `'[object Object]'` and replied
 * 422 Unprocessable. The fix is `JSON.stringify(payload)` plus explicit
 * `Content-Type: application/json` headers.
 *
 * This test pins the wire contract:
 *   - `body` MUST be a JSON string, never a plain object
 *   - `Content-Type` MUST be `application/json`
 *   - Method MUST match the HTTP verb
 *
 * If anyone re-introduces the cast, this test fails immediately.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/fetch', () => ({
  parkosFetch: vi.fn(),
}));

import { parkosFetch } from '@/lib/fetch';
import {
  createCatalogVersion,
  listCatalog,
  updateCatalogVersion,
} from './catalogApi';

const mockedFetch = vi.mocked(parkosFetch);

beforeEach(() => {
  mockedFetch.mockReset();
});

describe('catalogApi — wire contract', () => {
  it('createCatalogVersion: body MUST be a JSON.stringify string with Content-Type application/json', async () => {
    mockedFetch.mockResolvedValueOnce({ uuid: 'new-uuid' });

    await createCatalogVersion('tipo-persona', { tipo: 'natural' });

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockedFetch.mock.calls[0]!;
    expect(url).toBe('/api/v1/catalogos/tipo-persona');
    expect(init?.method).toBe('POST');

    const headers = init?.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');

    const body = init?.body;
    expect(typeof body).toBe('string');
    expect(body).not.toBe('[object Object]');
    expect(JSON.parse(body as string)).toEqual({ tipo: 'natural' });
  });

  it('updateCatalogVersion: body MUST be a JSON.stringify string with Content-Type application/json', async () => {
    mockedFetch.mockResolvedValueOnce({ uuid: 'uuid-1' });

    await updateCatalogVersion('impuestos', 'uuid-1', {
      codigo: 'IVA-19',
      porcentaje: 19,
    });

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockedFetch.mock.calls[0]!;
    expect(url).toBe('/api/v1/catalogos/impuestos/uuid-1');
    expect(init?.method).toBe('PUT');

    const headers = init?.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');

    const body = init?.body;
    expect(typeof body).toBe('string');
    expect(JSON.parse(body as string)).toEqual({
      codigo: 'IVA-19',
      porcentaje: 19,
    });
  });

  it('createCatalogVersion: serializes boolean fields correctly (no quote-wrapping)', async () => {
    mockedFetch.mockResolvedValueOnce({ uuid: 'uuid-2' });

    await createCatalogVersion('tipo-subscripciones', {
      tipo: 'mensual',
      mismo_tipo_vehiculo: true,
    });

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    const body = mockedFetch.mock.calls[0]![1]?.body as string;
    expect(body).not.toContain('"true"');
    expect(body).not.toContain('"false"');
    expect(JSON.parse(body)).toEqual({
      tipo: 'mensual',
      mismo_tipo_vehiculo: true,
    });
  });

  it('listCatalog: GET sin body', async () => {
    mockedFetch.mockResolvedValueOnce({ items: [] });

    await listCatalog('tipo-persona');

    expect(mockedFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockedFetch.mock.calls[0]!;
    expect(url).toBe('/api/v1/catalogos/tipo-persona');
    expect(init?.method).toBe('GET');
    expect(init?.body).toBeUndefined();
  });
});
