/**
 * Regression coverage for the branch-directory SWR key collision
 * (HU-F16 Bug 1) and the per-user assignments N+1 (HU-F16 Bug 2).
 *
 * Bug 1 — eight components read the raw key
 * `'/api/v1/empresa/sucursal?limit=200'` with fetchers returning
 * different shapes: the assignment modal returned the `{ items }`
 * envelope, the other seven returned `Sucursal[]`. SWR caches by key
 * and a second hook on a fresh key never runs its own fetcher, so
 * whichever mounted first decided the shape everyone else read. The
 * user saw `availableBranches.map is not a function`.
 *
 * Bug 2 — the list preloaded every user's assignments, one request per
 * row. The directory hook is the fix for both: one namespaced key, one
 * shape, and assignments loaded only by the modal that needs them.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetchRaw: vi.fn(),
  parkosFetch: vi.fn(),
}));

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';

import {
  DIRECTORIO_KEY,
  useSucursalOptions,
  useSucursalesDirectorio,
} from '../useSucursalesDirectorio';

const mockedRaw = vi.mocked(parkosFetchRaw);

const UUID_A = '83ef5d9f-dd65-47e3-9b13-50deed0f03d3';

// Full `sucursalReadSchema` shape — a partial fixture fails the parse
// and silently yields an empty directory, which is how the first
// version of this test passed for the wrong reason.
const SUCURSAL = {
  uuid: UUID_A,
  nombre: 'Sucursal Norte',
  direccion: 'Calle 100 #10-20',
  telefono: '+57 601 5550000',
  prefijo_nombre: 'NOR',
  ciudad: 'Bogota',
  horario: '24/7',
  uuid_tipo_sucursal: null,
  uuid_empresa: null,
  vigente_desde: '2026-01-01T00:00:00Z',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00Z',
  created_by: null,
  sync_status: null,
};

/** Paginated envelope as `sucursalReadListSchema` expects it. */
function sucursalEnvelope(items: unknown[] | null): unknown {
  return { items, next_cursor: null };
}

function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

/**
 * Per-test SWR cache. Without this, an entry written by one test is
 * still fresh for the next and its fetcher never runs — the same
 * mechanism that made the original collision order-dependent.
 */
function isolatedCache({ children }: { children: ReactNode }) {
  return createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    children,
  );
}

beforeEach(() => {
  mockedRaw.mockReset();
});

describe('useSucursalesDirectorio — shape is stable regardless of mount order', () => {
  it('returns a flat array when the backend answers with the { items } envelope', async () => {
    mockedRaw.mockResolvedValue(okResponse(sucursalEnvelope([SUCURSAL])));

    const { result } = renderHook(() => useSucursalesDirectorio(), {
      wrapper: isolatedCache,
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // The crash was `availableBranches.map is not a function`.
    expect(result.current.error).toBeUndefined();
    expect(Array.isArray(result.current.sucursales)).toBe(true);
    expect(() => result.current.sucursales.map((s) => s.uuid)).not.toThrow();
    expect(result.current.sucursales).toHaveLength(1);
    expect(result.current.sucursales[0]?.uuid).toBe(UUID_A);
  });

  it('collapses a non-array payload to an empty array instead of leaking it', async () => {
    mockedRaw.mockResolvedValue(okResponse(sucursalEnvelope(null)));

    const { result } = renderHook(() => useSucursalesDirectorio(), {
      wrapper: isolatedCache,
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.sucursales).toEqual([]);
  });

  it('uses a namespaced key, so it cannot collide with a raw-URL key', () => {
    expect(DIRECTORIO_KEY).toBe('parkos:sucursales:directorio:v1');
    expect(DIRECTORIO_KEY).not.toBe('/api/v1/empresa/sucursal?limit=200');
  });

  it('projects the { uuid, nombre } shape the selects consume', async () => {
    mockedRaw.mockResolvedValue(okResponse(sucursalEnvelope([SUCURSAL])));

    const { result } = renderHook(() => useSucursalOptions(), {
      wrapper: isolatedCache,
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.options).toEqual([
      { uuid: UUID_A, nombre: 'Sucursal Norte' },
    ]);
  });

  it('serves every consumer from one shared entry (no per-consumer key)', async () => {
    mockedRaw.mockResolvedValue(okResponse(sucursalEnvelope([SUCURSAL])));

    // Both hooks under ONE cache provider — two different consumers,
    // one namespaced key. This is the N+1 the user reported, collapsed
    // to a single request for the branch directory.
    const { result } = renderHook(
      () => ({
        directorio: useSucursalesDirectorio(),
        opciones: useSucursalOptions(),
      }),
      { wrapper: isolatedCache },
    );
    await waitFor(() =>
      expect(result.current.directorio.isLoading).toBe(false),
    );

    expect(mockedRaw).toHaveBeenCalledTimes(1);
    expect(result.current.directorio.sucursales).toHaveLength(1);
    expect(result.current.opciones.options).toHaveLength(1);
  });
});
