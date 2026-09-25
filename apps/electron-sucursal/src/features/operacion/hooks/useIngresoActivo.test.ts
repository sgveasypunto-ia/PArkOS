/**
 * Unit tests for `useIngresoActivo` SWR shape (HU-F6.1, T4).
 *
 * The hook is a thin SWR wrapper around `getIngresosByPlaca`. We extract
 * the SWR options directly from the hook call and exercise the
 * `shouldRetryOnError` + `onError` callbacks in isolation, mirroring
 * the F4.1 `useTiposVehiculo.test.ts` precedent. The end-to-end SWR
 * lifecycle (revalidation, deduping, focus-revalidate) is exercised
 * by SWR's own suite.
 *
 * Precedent verbatim F4.1 `useTiposVehiculo.test.ts`:
 *   - `useSWR` is mocked; the test reaches into the captured options
 *     and asserts the callbacks directly.
 *   - 401 → `useAuthStore.clear()` + `parkos:auth:cleared` event.
 *   - 404 / 5xx → SWR does NOT clear auth.
 */
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useAuthStore } from '@parkos/ui-kit/store';

import type { Ingreso } from '../api/ingresoActivoApi';
import { pickLatest, useIngresoActivo } from './useIngresoActivo';

interface SwrOptions {
  shouldRetryOnError?: (err: unknown) => boolean;
  onError?: (err: unknown) => void;
}

// Spy lives outside React's scope — it is invoked from inside the
// mocked useSWR module, not from a hook. The eslint-plugin-react-hooks
// rule flags any function starting with `use` as a hook, so we keep
// the variable name as `useSwrSpyStorage` (no `use` prefix) and
// reference it directly from the mock factory below.
const useSwrSpyStorage = vi.fn();

vi.mock('swr', () => ({
  default: (...args: unknown[]) => {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useSwrSpyStorage(...args);
    return {
      data: undefined,
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    };
  },
  useSWR: (...args: unknown[]) => {
    useSwrSpyStorage(...args);
    return {
      data: undefined,
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    };
  },
}));

vi.mock('../api/ingresoActivoApi', () => ({
  getIngresosByPlaca: vi.fn(),
}));

beforeEach(() => {
  useSwrSpyStorage.mockReset();
  useAuthStore.setState({
    accessToken: 'jwt-test',
    expiresAt: null,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function captureOptions(): SwrOptions {
  renderHook(() => useIngresoActivo('ABC123'));
  const lastCall = useSwrSpyStorage.mock.calls.at(-1);
  if (!lastCall) throw new Error('useSWR not called');
  // SWR's third positional arg is the options object.
  return (lastCall[2] as SwrOptions | undefined) ?? {};
}

describe('useIngresoActivo SWR options', () => {
  it('exposes a shouldRetryOnError that excludes 401, 403, 404', () => {
    const opts = captureOptions();
    expect(typeof opts.shouldRetryOnError).toBe('function');
    if (!opts.shouldRetryOnError) throw new Error('missing');
    expect(opts.shouldRetryOnError(new ParkosHttpError(401, '', ''))).toBe(false);
    expect(opts.shouldRetryOnError(new ParkosHttpError(403, '', ''))).toBe(false);
    expect(opts.shouldRetryOnError(new ParkosHttpError(404, '', ''))).toBe(false);
    expect(opts.shouldRetryOnError(new ParkosHttpError(500, '', ''))).toBe(true);
    expect(opts.shouldRetryOnError(new Error('network'))).toBe(true);
  });

  it('on 401: clears the auth store + dispatches parkos:auth:cleared', () => {
    const opts = captureOptions();
    if (!opts.onError) throw new Error('missing onError');
    const dispatchSpy = vi.fn();
    vi.spyOn(window, 'dispatchEvent').mockImplementation((event) => {
      dispatchSpy(event.type);
      return true;
    });
    opts.onError(new ParkosHttpError(401, '', '/operacion/ingresos'));
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(dispatchSpy).toHaveBeenCalledWith('parkos:auth:cleared');
  });

  it('on 404: does NOT clear auth', () => {
    const clearSpy = vi.fn();
    const originalClear = useAuthStore.getState().clear;
    useAuthStore.setState({
      clear: ((...args: unknown[]) => {
        clearSpy(...args);
        return (originalClear as (...a: unknown[]) => unknown)(...args);
      }) as typeof originalClear,
    });
    const opts = captureOptions();
    if (!opts.onError) throw new Error('missing onError');
    opts.onError(new ParkosHttpError(404, '', '/operacion/ingresos'));
    expect(clearSpy).not.toHaveBeenCalled();
    useAuthStore.setState({ clear: originalClear });
  });

  it('on 5xx: does NOT clear auth', () => {
    const clearSpy = vi.fn();
    const originalClear = useAuthStore.getState().clear;
    useAuthStore.setState({
      clear: ((...args: unknown[]) => {
        clearSpy(...args);
        return (originalClear as (...a: unknown[]) => unknown)(...args);
      }) as typeof originalClear,
    });
    const opts = captureOptions();
    if (!opts.onError) throw new Error('missing onError');
    opts.onError(new ParkosHttpError(500, '', '/operacion/ingresos'));
    expect(clearSpy).not.toHaveBeenCalled();
    useAuthStore.setState({ clear: originalClear });
  });

  it('passes a SWR key gated by placa + accessToken', () => {
    renderHook(() => useIngresoActivo('ABC123'));
    const lastCall = useSwrSpyStorage.mock.calls.at(-1);
    const key = lastCall?.[0] as string | null;
    expect(key).toBe('/api/v1/operacion/ingresos?placa=ABC123');
  });

  it('passes a null SWR key when placa is null (skip pre-typed fetch)', () => {
    renderHook(() => useIngresoActivo(null));
    const lastCall = useSwrSpyStorage.mock.calls.at(-1);
    const key = lastCall?.[0] as string | null;
    expect(key).toBeNull();
  });

  it('passes a null SWR key when accessToken is missing (cold boot pre-login)', () => {
    useAuthStore.setState({ accessToken: null });
    renderHook(() => useIngresoActivo('ABC123'));
    const lastCall = useSwrSpyStorage.mock.calls.at(-1);
    const key = lastCall?.[0] as string | null;
    expect(key).toBeNull();
  });
});

describe('pickLatest', () => {
  function makeIngreso(overrides: Partial<Ingreso>): Ingreso {
    return {
      uuid: '00000000-0000-0000-0000-000000000001',
      uuid_sucursal: '00000000-0000-0000-0000-000000000002',
      placa: 'ABC123',
      fecha_ingreso: '2026-09-20T10:00:00.000Z',
      uuid_subscripcion_cliente: null,
      ...overrides,
    };
  }

  it('returns null for an empty/undefined list', () => {
    expect(pickLatest(undefined)).toBeNull();
    expect(pickLatest([])).toBeNull();
  });

  it('picks the row with the most recent fecha_ingreso', () => {
    const older = makeIngreso({
      uuid: 'older',
      fecha_ingreso: '2026-09-20T10:00:00.000Z',
    });
    const newer = makeIngreso({
      uuid: 'newer',
      fecha_ingreso: '2026-09-22T08:00:00.000Z',
    });
    expect(pickLatest([older, newer])?.uuid).toBe('newer');
    expect(pickLatest([newer, older])?.uuid).toBe('newer');
  });

  // BUGFIX regression: `fecha_ingreso` is nullable for historical rows
  // (REGRESSION fix 2026-09-22, migration 0046 backward compat). The
  // comparator used to call `.localeCompare` unconditionally and threw
  // on the first `null` row it encountered.
  it('does not throw when fecha_ingreso is null, and ranks a dated row above a null one', () => {
    const sinFecha = makeIngreso({ uuid: 'sin-fecha', fecha_ingreso: null });
    const conFecha = makeIngreso({
      uuid: 'con-fecha',
      fecha_ingreso: '2026-09-22T08:00:00.000Z',
    });
    expect(() => pickLatest([sinFecha, conFecha])).not.toThrow();
    expect(pickLatest([sinFecha, conFecha])?.uuid).toBe('con-fecha');
    expect(pickLatest([conFecha, sinFecha])?.uuid).toBe('con-fecha');
  });

  it('does not throw when every row has fecha_ingreso: null', () => {
    const a = makeIngreso({ uuid: 'a', fecha_ingreso: null });
    const b = makeIngreso({ uuid: 'b', fecha_ingreso: null });
    expect(() => pickLatest([a, b])).not.toThrow();
    expect(pickLatest([a, b])).not.toBeNull();
  });
});
