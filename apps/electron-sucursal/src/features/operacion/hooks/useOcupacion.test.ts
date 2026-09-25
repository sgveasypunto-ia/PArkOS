/**
 * Unit tests for `useOcupacion()` (HU-F4.3 — T2).
 *
 * Coverage (verbatim tasks.md §2.3):
 *   U-O1: SWR key null when `uuid_sucursal === null`.
 *   U-O2: SWR key null when `accessToken === null` (pre-auth cold boot).
 *   U-O3: SWR key = `/operacion/ocupacion?uuid_sucursal=X` when both
 *         inputs are present.
 *   U-O4: `refreshInterval` = `OPERACION_REFRESH_INTERVAL_MS` (10_000 ms).
 *   U-O5: `dedupingInterval` = `OPERACION_DEDUPING_INTERVAL_MS` (5_000 ms).
 *   U-O6: `shouldRetryOnError` excludes 401 (let auth store react),
 *         excludes 403 (forbidden terminal), excludes 404 (sucursal typo
 *         terminal). Includes 500 (operational retry).
 *   U-O7: `onError` with `ParkosHttpError 401` → `useAuthStore.clear()` +
 *         `parkos:auth:cleared` window event.
 *   U-O8: `onError` with `ParkosHttpError 500` → NO clear, NO event,
 *         `console.warn` invoked.
 *   U-O9: `isStale` is `true` when `data !== undefined && error !== undefined`.
 *
 * Mocking strategy (precedent F4.1 `useTiposVehiculo.test.ts` verbatim):
 *   - vi.mock('@parkos/ui-kit/store') → useAuthStore selector + getState.
 *   - vi.mock('@parkos/ui-kit/fetch') → ParkosHttpError class.
 *   - vi.mock('../api/ocupacionApi') → getOcupacion stub.
 *   - vi.mock('swr') → useSWR configurado; capturamos `key` y `options`
 *     para inspeccionar `refreshInterval`, `dedupingInterval`,
 *     `shouldRetryOnError`, `onError`. Devolvemos un objeto shape
 *     `{ data, error, mutate }` que el test puede retocar por caso.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';

const useAuthStoreMock = vi.fn();
const getStateClearMock = vi.fn();
const dispatchEventSpy = vi
  .spyOn(window, 'dispatchEvent')
  .mockImplementation(() => true);
const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

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
    constructor(status: number, _body?: string, _url?: string) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

const getOcupacionMock = vi.fn();
let swrOptions: Record<string, unknown> | undefined;
let swrKey: string | null | undefined;
const mutateMock = vi.fn();
let currentData: unknown = undefined;
let currentError: unknown = undefined;
let swrFetcher: ((k: string) => Promise<unknown>) | undefined;

vi.mock('../api/ocupacionApi', () => ({
  getOcupacion: (...args: unknown[]) => getOcupacionMock(...args),
}));

vi.mock('swr', () => ({
  default: (
    key: string | null | undefined,
    fetcher: (k: string) => Promise<unknown>,
    options: Record<string, unknown>,
  ) => {
    swrKey = key;
    swrFetcher = fetcher;
    swrOptions = options;
    return {
      get data() {
        return currentData;
      },
      get error() {
        return currentError;
      },
      mutate: mutateMock,
    };
  },
}));

// Import after mocks so the mocked modules are wired.
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useOcupacion } from './useOcupacion';
import type { OcupacionResponse } from '../api/ocupacionApi';

beforeEach(() => {
  swrOptions = undefined;
  swrKey = undefined;
  swrFetcher = undefined;
  currentData = undefined;
  currentError = undefined;
});

afterEach(() => {
  vi.clearAllMocks();
  dispatchEventSpy.mockClear();
  consoleWarnSpy.mockClear();
});

const SAMPLE_OK: OcupacionResponse = {
  uuid_sucursal: '00000000-0000-0000-0000-000000000099',
  items: [
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
      tipo: 'Auto',
      cupo_maximo: 50,
      activos: 23,
      disponible: 27,
    },
    {
      uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002',
      tipo: 'Moto',
      cupo_maximo: 5,
      activos: 1,
      disponible: 4,
    },
  ],
  generado_en: '2026-09-16T10:00:00Z',
};

describe('useOcupacion — SWR key gating', () => {
  it('U-O1: SWR key null cuando uuid_sucursal === null', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion(null);
    expect(swrKey).toBeNull();
  });

  it('U-O2: SWR key null pre-auth (accessToken === null)', () => {
    useAuthStoreMock.mockReturnValue(null);
    useOcupacion('suc-uuid-1');
    expect(swrKey).toBeNull();
  });

  it('U-O3: SWR key con ambos inputs presentes', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('00000000-0000-0000-0000-000000000099');
    expect(swrKey).toBe(
      '/operacion/ocupacion?uuid_sucursal=00000000-0000-0000-0000-000000000099',
    );
  });
});

describe('useOcupacion — SWR config', () => {
  it('U-O4: refreshInterval = 10_000 (DEC-SUC-11 verbatim)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    expect(swrOptions?.refreshInterval).toBe(10_000);
  });

  it('U-O5: dedupingInterval = 5_000 (DEC-SUC-11 verbatim)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    expect(swrOptions?.dedupingInterval).toBe(5_000);
  });

  it('U-O6: shouldRetryOnError excluye 401, 403, 404; incluye 500', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    const shouldRetry = swrOptions?.shouldRetryOnError as (err: unknown) => boolean;
    expect(
      shouldRetry(new ParkosHttpError(401, 'unauthorized', '/operacion/ocupacion')),
    ).toBe(false);
    expect(
      shouldRetry(new ParkosHttpError(403, 'forbidden', '/operacion/ocupacion')),
    ).toBe(false);
    expect(
      shouldRetry(new ParkosHttpError(404, 'not_found', '/operacion/ocupacion')),
    ).toBe(false);
    expect(
      shouldRetry(new ParkosHttpError(500, 'server_error', '/operacion/ocupacion')),
    ).toBe(true);
    expect(shouldRetry(new Error('network'))).toBe(true);
  });
});

describe('useOcupacion — onError policy', () => {
  it('U-O7: onError con status=401 → useAuthStore.clear() + parkos:auth:cleared event', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(401, 'unauthorized', '/operacion/ocupacion'));
    expect(getStateClearMock).toHaveBeenCalledOnce();
    expect(dispatchEventSpy).toHaveBeenCalledWith(expect.any(Event));
    const event = (dispatchEventSpy.mock.calls[0]?.[0] as Event) ?? null;
    expect(event?.type).toBe('parkos:auth:cleared');
  });

  it('U-O8a: onError con status=500 → NO clear, NO event; console.warn invoked', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(500, 'server_error', '/operacion/ocupacion'));
    expect(getStateClearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
    expect(consoleWarnSpy).toHaveBeenCalled();
  });

  it('U-O8b: onError con status=403 → NO clear, NO event (terminal)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(403, 'forbidden', '/operacion/ocupacion'));
    expect(getStateClearMock).not.toHaveBeenCalled();
    expect(consoleWarnSpy).toHaveBeenCalled();
  });

  it('U-O8c: onError con status=404 → NO clear, NO event (terminal)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(404, 'not_found', '/operacion/ocupacion'));
    expect(getStateClearMock).not.toHaveBeenCalled();
    expect(consoleWarnSpy).toHaveBeenCalled();
  });

  it('U-O8d: onError con network error → NO clear; console.warn invoked', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useOcupacion('suc-uuid-1');
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new TypeError('NetworkError'));
    expect(getStateClearMock).not.toHaveBeenCalled();
    expect(consoleWarnSpy).toHaveBeenCalled();
  });
});

describe('useOcupacion — isStale flag', () => {
  it('U-O9a: isStale=false cuando no hay data', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    currentData = undefined;
    currentError = undefined;
    const result = useOcupacion('suc-uuid-1');
    expect(result.isStale).toBe(false);
  });

  it('U-O9b: isStale=false cuando hay data sin error', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    currentData = SAMPLE_OK;
    currentError = undefined;
    const result = useOcupacion('suc-uuid-1');
    expect(result.isStale).toBe(false);
  });

  it('U-O9c: isStale=true cuando hay data Y error (SWR conserva último valor)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    currentData = SAMPLE_OK;
    currentError = new ParkosHttpError(500, 'server_error', '/operacion/ocupacion');
    const result = useOcupacion('suc-uuid-1');
    expect(result.isStale).toBe(true);
  });
});

describe('useOcupacion — return shape', () => {
  it('expone { data, error, isStale, refresh }', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    const result = useOcupacion('suc-uuid-1');
    expect(result).toHaveProperty('data');
    expect(result).toHaveProperty('error');
    expect(result).toHaveProperty('isStale');
    expect(result).toHaveProperty('refresh');
  });

  it('refresh retorna Promise (wrap de SWR mutate)', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    mutateMock.mockResolvedValueOnce(SAMPLE_OK);
    const result = useOcupacion('suc-uuid-1');
    const r = result.refresh();
    expect(r).toBeInstanceOf(Promise);
    await r;
    expect(mutateMock).toHaveBeenCalled();
  });
});

describe('useOcupacion — fetcher-closure contract (REQ-OPS-132 / U-O10)', () => {
  it('U-O10: fetcher closure receives the raw UUID, NOT the SWR cache key', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    getOcupacionMock.mockResolvedValueOnce(SAMPLE_OK);

    // Mount: this captures the SWR fetcher in swrFetcher (see mocked SWR above).
    useOcupacion('suc-uuid-1');

    expect(swrFetcher).toBeDefined();
    expect(typeof swrFetcher).toBe('function');

    // Invoke the fetcher directly with the cache key — REQ-OBS-132
    // says the fetcher must IGNORE that arg and use the closure
    // capture (the bare UUID).
    const result = await swrFetcher!(
      '/operacion/ocupacion?uuid_sucursal=suc-uuid-1',
    );

    // The fetcher must have invoked getOcupacion with 'suc-uuid-1'
    // (the raw UUID, NOT the key with the ?...query string).
    expect(getOcupacionMock).toHaveBeenCalledTimes(1);
    expect(getOcupacionMock.mock.calls[0]?.[0]).toBe('suc-uuid-1');
    // Belt-and-braces: the first arg has NO '?' (no query-string leak).
    expect(String(getOcupacionMock.mock.calls[0]?.[0])).not.toContain('?');
    expect(result).toEqual(SAMPLE_OK);
  });

  it('U-O10b: fetcher closure uses the uuid_sucursal captured at hook-call time', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    getOcupacionMock.mockResolvedValueOnce(SAMPLE_OK);

    // Mount the hook with one UUID, then trigger the fetcher with
    // an entirely different cache-key string — the closure capture
    // wins.
    useOcupacion('first-uuid');
    expect(swrFetcher).toBeDefined();
    await swrFetcher!('/operacion/ocupacion?uuid_sucursal=DIFFERENT');

    expect(getOcupacionMock.mock.calls[0]?.[0]).toBe('first-uuid');
  });
});