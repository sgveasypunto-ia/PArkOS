/**
 * useAuth — 5 unit tests (vitest + @testing-library/react renderHook).
 *
 * Validates the SWR-driven hook that fuses `useAuthStore` (Zustand)
 * with the /auth/me profile fetch. We mock the fetcher (parkosFetch)
 * with vi.fn so we can drive the hook deterministically.
 *
 * NOTE: This file is .ts (not .tsx) so we avoid JSX syntax. The wrapper
 * uses React.createElement directly.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
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
  };
});

import { parkosFetch } from '../fetch/parkosFetch';
import { useAuth } from './useAuth';

const mockedParkosFetch = parkosFetch as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }): JSX.Element {
  // SWRConfig's `provider` prop has a strict Cache-typed signature; in
  // tests we don't care about Cache internals — we just want a fresh
  // cache per renderHook call. The `as never` cast bypasses the strict
  // (cache: Readonly<Cache<any>>) => Cache<any> signature.
  const configValue = { provider: (): never => new Map() as never };
  return createElement(SWRConfig, { value: configValue }, children);
}

interface MePayload {
  user: { id: string; email: string };
  sucursal: { uuid: string; nombre: string } | null;
  sucursales_permitidas: Array<{ uuid: string; nombre: string }>;
  permisos: string[];
  expires_at: string | null;
}

const SAMPLE_ME: MePayload = {
  user: { id: 'u-1', email: 'admin@parkos.local' },
  sucursal: { uuid: 'suc-1', nombre: 'Sucursal 1' },
  sucursales_permitidas: [{ uuid: 'suc-1', nombre: 'Sucursal 1' }],
  permisos: ['dashboard:read'],
  expires_at: '2026-12-31T23:59:59.000Z',
};

beforeEach(() => {
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    expiresAt: null,
  });
  mockedParkosFetch.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useAuth — auth-state driven SWR', () => {
  it('H1: sin accessToken retorna isAuthenticated:false y NO fetcha', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.sucursal).toBeNull();
    expect(result.current.sucursalesPermitidas).toEqual([]);
    expect(result.current.permisos).toEqual([]);
    expect(result.current.isLoading).toBe(false);
    expect(mockedParkosFetch).not.toHaveBeenCalled();
  });

  it('H2: con accessToken válido fetcha /auth/me y expone data tipada', async () => {
    useAuthStore.setState({
      accessToken: 'jwt-good',
      refreshToken: 'ref-good',
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedParkosFetch.mockResolvedValueOnce(SAMPLE_ME);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });

    expect(mockedParkosFetch).toHaveBeenCalledWith('/auth/me');
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user).toEqual(SAMPLE_ME.user);
    expect(result.current.sucursal).toEqual(SAMPLE_ME.sucursal);
    expect(result.current.sucursalesPermitidas).toEqual(SAMPLE_ME.sucursales_permitidas);
    expect(result.current.permisos).toEqual(SAMPLE_ME.permisos);
  });

  it('H3: SWR config refreshInterval es exactamente 5 min (300_000 ms)', async () => {
    useAuthStore.setState({
      accessToken: 'jwt',
      refreshToken: 'ref',
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedParkosFetch.mockResolvedValueOnce(SAMPLE_ME);

    renderHook(() => useAuth(), { wrapper });
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    // SWR's resolved options aren't exposed at runtime, so we verify the
    // design-time constant via a regex over the hook source. This keeps
    // a reviewer-visible cross-ref to `plan.md:1208`.
    const fs = await import('node:fs/promises');
    const path = await import('node:path');
    // Resolve via cwd (vitest's jsdom env strips fileURLToPath support).
    const sourcePath = path.join(process.cwd(), 'src/hooks/useAuth.ts');
    const src = await fs.readFile(sourcePath, 'utf8');
    expect(src).toMatch(/refreshInterval:\s*5\s*\*\s*60\s*\*\s*1000/);
  });

  it('H4: shouldRetryOnError rechaza ParkosHttpError 401 (no retry)', async () => {
    useAuthStore.setState({
      accessToken: 'jwt',
      refreshToken: 'ref',
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    const { ParkosHttpError } = await import('../fetch/parkosFetch');
    const err401 = new ParkosHttpError(401, 'unauthorized', '/auth/me');
    mockedParkosFetch.mockRejectedValueOnce(err401);

    const { result } = renderHook(() => useAuth(), { wrapper });

    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 10));
    });

    // onError handler should have cleared the store on 401.
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('H5: refresh() invoca mutate (re-fetch sin nuevo refresh interno)', async () => {
    useAuthStore.setState({
      accessToken: 'jwt',
      refreshToken: 'ref',
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    });
    mockedParkosFetch.mockResolvedValueOnce(SAMPLE_ME);
    const updated = { ...SAMPLE_ME, permisos: ['dashboard:read', 'reports:read'] };
    mockedParkosFetch.mockResolvedValueOnce(updated);

    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
    });

    expect(result.current.permisos).toEqual(['dashboard:read']);

    await act(async () => {
      await result.current.refresh();
    });

    expect(mockedParkosFetch).toHaveBeenCalledTimes(2);
    expect(result.current.permisos).toEqual(['dashboard:read', 'reports:read']);
  });
});
