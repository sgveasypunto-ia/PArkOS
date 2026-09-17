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

import { useIngresoActivo } from './useIngresoActivo';

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
    user: null,
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
