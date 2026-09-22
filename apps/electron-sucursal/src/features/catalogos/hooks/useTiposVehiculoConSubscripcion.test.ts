/**
 * Unit tests for `useTiposVehiculoConSubscripcion` (HU-F11.x, REQ-OPS-200).
 *
 * Mocking strategy (precedent F4.1 `useTiposVehiculo.test.ts`):
 *   - Mock `swr` to capture options (deduping, shouldRetryOnError, onError).
 *   - Mock the API + auth store + ParkosHttpError.
 *   - Tests invoke the captured `onError` directly (no need to wait for
 *     async fetcher resolution), which mirrors SWR's real behavior.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const useAuthStoreMock = vi.fn();
const getStateClearMock = vi.fn();
const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(
  () => true,
);

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: { accessToken: string | null }) => unknown) =>
      useAuthStoreMock(selector),
    { getState: () => ({ clear: getStateClearMock }) },
  ),
}));

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class extends Error {
    public readonly status: number;
    constructor(status: number) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

const getTiposVehiculoConSubscripcionMock = vi.fn();
let swrOptions: Record<string, unknown> | undefined;
let swrKey: string | null | undefined;

vi.mock('../api/tiposVehiculoApi', () => ({
  getTiposVehiculoConSubscripcion: (...args: unknown[]) =>
    getTiposVehiculoConSubscripcionMock(...args),
}));

vi.mock('swr', () => ({
  default: (
    key: string | null | undefined,
    _fetcher: () => Promise<unknown>,
    options: Record<string, unknown>,
  ) => {
    swrKey = key;
    swrOptions = options;
    return {
      data: undefined,
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
    };
  },
}));

// Import after mocks so the mocked modules are wired.
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useTiposVehiculoConSubscripcion } from './useTiposVehiculoConSubscripcion';

beforeEach(() => {
  swrOptions = undefined;
  swrKey = undefined;
  useAuthStoreMock.mockReset();
  getStateClearMock.mockReset();
  dispatchEventSpy.mockClear();
});

describe('useTiposVehiculoConSubscripcion (HU-F11.x / REQ-OPS-200)', () => {
  it('T1: SWR key null sin accessToken → tipos=[]', () => {
    useAuthStoreMock.mockReturnValue(null);
    const result = useTiposVehiculoConSubscripcion();
    expect(swrKey).toBeNull();
    expect(result.tipos).toEqual([]);
  });

  it('T2: SWR key con accessToken presente', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useTiposVehiculoConSubscripcion();
    expect(swrKey).toBe('/catalogos/tipos-vehiculo-con-subscripcion');
  });

  it('T3: dedupingInterval = 5min (DEC-F4.1-04 verbatim plan.md:1375)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useTiposVehiculoConSubscripcion();
    expect(swrOptions?.dedupingInterval).toBe(5 * 60 * 1000);
  });

  it('T4: shouldRetryOnError excluye 404 (catálogo sin subscripciones es estado válido)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useTiposVehiculoConSubscripcion();
    const shouldRetry = swrOptions?.shouldRetryOnError as (
      err: unknown,
    ) => boolean;
    expect(shouldRetry(new ParkosHttpError(404))).toBe(false);
    expect(shouldRetry(new ParkosHttpError(500))).toBe(true);
    expect(shouldRetry(new ParkosHttpError(401))).toBe(true);
  });

  it('T5: fallbackData es [] (subset vacío inicial antes del fetch)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useTiposVehiculoConSubscripcion();
    const fallback = swrOptions?.fallbackData as unknown[];
    expect(fallback).toEqual([]);
  });

  it('T6: onError 401 → useAuthStore.getState().clear() + parkos:auth:cleared event', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useTiposVehiculoConSubscripcion();
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(401));
    expect(getStateClearMock).toHaveBeenCalledOnce();
    expect(dispatchEventSpy).toHaveBeenCalledWith(expect.any(Event));
    const event = (dispatchEventSpy.mock.calls[0]?.[0] as Event) ?? null;
    expect(event?.type).toBe('parkos:auth:cleared');
  });

  it('T7: onError 404 → NO clear (defensa redundante vía shouldRetryOnError)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useTiposVehiculoConSubscripcion();
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(404));
    expect(getStateClearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
  });

  it('T8: onError 500 → NO clear, NO event', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useTiposVehiculoConSubscripcion();
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(500));
    expect(getStateClearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
  });

  it('T9: return shape expone { tipos, isLoading, error, refresh }', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    const result = useTiposVehiculoConSubscripcion();
    expect(result).toHaveProperty('tipos');
    expect(result).toHaveProperty('isLoading');
    expect(result).toHaveProperty('error');
    expect(result).toHaveProperty('refresh');
  });
});