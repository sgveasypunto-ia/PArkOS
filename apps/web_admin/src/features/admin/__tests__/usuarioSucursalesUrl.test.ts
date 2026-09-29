/**
 * Regression coverage for the malformed branch-assignment URL
 * (HU-F16 Bug 3).
 *
 * Root cause: SWR invokes the fetcher as `fetcher(key)`.
 * `useAdminUsuarioSucursales` passed the bare `listAdminUsuarioSucursales`
 * reference, so the `uuid` parameter received the whole SWR key — the
 * complete resource URL — and the request went out as
 *
 *   /api/v1/admin/usuarios//api/v1/admin/usuarios/<uuid>/sucursales/sucursales
 *
 * which the backend answers with a 404 and no explanation.
 *
 * The fix is the closure in the hook plus `assertUuid` at the API
 * boundary, so any future key/uuid mixup fails loudly at the source
 * instead of silently producing a doubled path.
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
  asignarAdminUsuarioSucursal,
  desasignarAdminUsuarioSucursal,
  listAdminUsuarioSucursales,
} from '../api/adminUsuariosApi';
import { useAdminUsuarioSucursales } from '../hooks/useAdminUsuarioSucursales';

const mockedRaw = vi.mocked(parkosFetchRaw);

const UUID_A = '83ef5d9f-dd65-47e3-9b13-50deed0f03d3';
const UUID_B = '4f9c1a20-1111-4222-8333-444455556666';

const ASIGNACION = {
  uuid: 'a1b2c3d4-0000-4000-8000-000000000001',
  uuid_usuario: UUID_B,
  uuid_sucursal: UUID_A,
  vigente_desde: '2026-09-01T00:00:00Z',
  vigente_hasta: null,
  estado: 'activo',
  nombre: 'Sucursal Norte',
};

function okResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

function requestedUrls(): string[] {
  return mockedRaw.mock.calls.map((call) => String(call[0]));
}

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

describe('assignment URLs are built from bare UUIDs', () => {
  beforeEach(() => {
    mockedRaw.mockResolvedValue(okResponse(ASIGNACION));
  });

  it('sends exactly one /sucursales segment when assigning', async () => {
    await asignarAdminUsuarioSucursal(UUID_B, UUID_A);

    expect(requestedUrls()).toEqual([
      `/api/v1/admin/usuarios/${UUID_B}/sucursales`,
    ]);
  });

  it('sends exactly one /sucursales/<uuid> segment when unassigning', async () => {
    await desasignarAdminUsuarioSucursal(UUID_B, UUID_A);

    expect(requestedUrls()).toEqual([
      `/api/v1/admin/usuarios/${UUID_B}/sucursales/${UUID_A}`,
    ]);
  });

  it('rejects a URL-shaped uuid loudly instead of building a doubled path', async () => {
    // Exactly the value SWR used to hand the fetcher as `uuid`.
    const keyAsUuid = `/api/v1/admin/usuarios/${UUID_B}/sucursales`;

    await expect(listAdminUsuarioSucursales(keyAsUuid)).rejects.toThrow(
      /must be a bare UUID/,
    );
    expect(mockedRaw).not.toHaveBeenCalled();
  });

  it('rejects a URL-shaped uuid on assign and unassign too', async () => {
    const keyAsUuid = `/api/v1/admin/usuarios/${UUID_B}/sucursales`;

    await expect(asignarAdminUsuarioSucursal(keyAsUuid, UUID_A)).rejects.toThrow(
      /must be a bare UUID/,
    );
    await expect(
      desasignarAdminUsuarioSucursal(UUID_B, keyAsUuid),
    ).rejects.toThrow(/must be a bare UUID/);
    expect(mockedRaw).not.toHaveBeenCalled();
  });
});

describe('the SWR fetcher receives the uuid, not the key', () => {
  beforeEach(() => {
    mockedRaw.mockResolvedValue(okResponse([ASIGNACION]));
  });

  it('requests the plain resource URL when the hook mounts', async () => {
    const { result } = renderHook(() => useAdminUsuarioSucursales(UUID_B), {
      wrapper: isolatedCache,
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.asignaciones).toHaveLength(1);
    expect(requestedUrls()).toEqual([
      `/api/v1/admin/usuarios/${UUID_B}/sucursales`,
    ]);
    // The literal shape the user saw in DevTools.
    expect(requestedUrls()[0]).not.toContain('/sucursales/sucursales');
    expect(requestedUrls()[0]).not.toContain('//api');
  });

  it('fetches one user once, on a single canonical URL', async () => {
    const { result } = renderHook(() => useAdminUsuarioSucursales(UUID_B), {
      wrapper: isolatedCache,
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.asignaciones).toHaveLength(1);
    expect(mockedRaw).toHaveBeenCalledTimes(1);
  });

  it('does not fire when there is no user', async () => {
    const { result } = renderHook(() => useAdminUsuarioSucursales(null), {
      wrapper: isolatedCache,
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.asignaciones).toBeUndefined();
    expect(mockedRaw).not.toHaveBeenCalled();
  });
});
