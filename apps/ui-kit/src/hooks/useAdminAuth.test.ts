/**
 * useAdminAuth — unit tests (vitest + @testing-library/react renderHook).
 *
 * The load-bearing assertions here are the logout ones. The server call
 * is best-effort and the local clear is unconditional, so the tests pin
 * the failure modes that would otherwise trap an operator in a session
 * they asked to end: a 204 body, a 400 from the missing
 * `X-Sucursal-Context` header, and a hard network failure.
 *
 * NOTE: .ts (not .tsx) — the wrapper uses React.createElement directly.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { createElement, type ReactNode } from 'react';

import { useAuthStore } from '../store/authStore';

vi.mock('../fetch/parkosFetch', async () => {
  const actual = await vi.importActual<typeof import('../fetch/parkosFetch')>(
    '../fetch/parkosFetch',
  );
  return {
    ...actual,
    parkosFetch: vi.fn(),
    parkosFetchRaw: vi.fn(),
  };
});

import { parkosFetch, parkosFetchRaw } from '../fetch/parkosFetch';
import { logoutAdmin, useAdminAuth, ADMIN_LOGOUT_PATH } from './useAdminAuth';

const mockedFetch = parkosFetch as ReturnType<typeof vi.fn>;
const mockedFetchRaw = parkosFetchRaw as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

const SAMPLE_ME = {
  actor_uuid: '786dc647-3a23-4aaa-af68-a2ecc48331d6',
  email: 'admin@parkos.local',
  rol: 'admin',
  sucursales_permitidas: ['2049f2cd-b2a8-4e45-9d19-31fa87eb67c6'],
  permissions: ['admin_usuarios', 'audit_read', 'config_sucursal'],
};

beforeEach(() => {
  mockedFetch.mockReset();
  mockedFetchRaw.mockReset();
  useAuthStore.setState({ accessToken: 'tok', refreshToken: 'ref', expiresAt: null });
});

afterEach(() => {
  useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
});

describe('useAdminAuth — profile normalization', () => {
  it('A1: maps /admin/me onto the shared identity shape', async () => {
    mockedFetch.mockResolvedValue(SAMPLE_ME);
    const { result } = renderHook(() => useAdminAuth(), { wrapper });
    await vi.waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.user?.uuid).toBe(SAMPLE_ME.actor_uuid);
    expect(result.current.user?.email).toBe('admin@parkos.local');
    expect(result.current.rol).toBe('admin');
    expect(result.current.permisos).toEqual(SAMPLE_ME.permissions);
  });

  it('A2: exposes branches as bare UUIDs (no fabricated SucursalItem)', async () => {
    mockedFetch.mockResolvedValue(SAMPLE_ME);
    const { result } = renderHook(() => useAdminAuth(), { wrapper });
    await vi.waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.sucursalUuids).toEqual(SAMPLE_ME.sucursales_permitidas);
  });

  it('A3: no token → no fetch, empty profile, not authenticated', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, expiresAt: null });
    const { result } = renderHook(() => useAdminAuth(), { wrapper });

    expect(mockedFetch).not.toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.permisos).toEqual([]);
    expect(result.current.user).toBeNull();
  });

  it('A4: 401 → clears the store and fires parkos:auth:cleared', async () => {
    const { ParkosHttpError } = await vi.importActual<
      typeof import('../fetch/parkosFetch')
    >('../fetch/parkosFetch');
    mockedFetch.mockRejectedValue(new ParkosHttpError(401, 'nope', '/api/v1/admin/me'));
    const seen: string[] = [];
    const listener = (e: Event): void => {
      seen.push(e.type);
    };
    window.addEventListener('parkos:auth:cleared', listener);

    renderHook(() => useAdminAuth(), { wrapper });
    await vi.waitFor(() => expect(seen.length).toBeGreaterThan(0));

    expect(useAuthStore.getState().accessToken).toBeNull();
    window.removeEventListener('parkos:auth:cleared', listener);
  });
});

describe('logoutAdmin — best-effort server call, unconditional local clear', () => {
  it('L1: a 204 must not throw (parkosFetchRaw, not parkosFetch)', async () => {
    mockedFetchRaw.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(logoutAdmin()).resolves.toBeUndefined();

    expect(mockedFetchRaw).toHaveBeenCalledWith(ADMIN_LOGOUT_PATH, { method: 'POST' });
    // Guards the specific regression: parkosFetch() would res.json() a
    // bodyless 204 and throw.
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it('L2: 400 from the missing X-Sucursal-Context header still logs out', async () => {
    mockedFetchRaw.mockResolvedValue(new Response(null, { status: 400 }));
    await logoutAdmin();

    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
  });

  it('L3: hard network failure still clears local credentials', async () => {
    mockedFetchRaw.mockRejectedValue(new Error('offline'));
    await expect(logoutAdmin()).resolves.toBeUndefined();

    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('L4: fires parkos:auth:cleared so the router can redirect', async () => {
    mockedFetchRaw.mockResolvedValue(new Response(null, { status: 204 }));
    const seen: string[] = [];
    const listener = (e: Event): void => {
      seen.push(e.type);
    };
    window.addEventListener('parkos:auth:cleared', listener);

    await logoutAdmin();

    expect(seen).toContain('parkos:auth:cleared');
    window.removeEventListener('parkos:auth:cleared', listener);
  });
});
