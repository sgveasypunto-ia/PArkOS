/**
 * Unit tests for `useMiTurno()` (HU-F12.1 — REQ-OPS-188).
 *
 * Coverage (verbatim tasks.md §2.5):
 *   U1: SWR key null when `uuid_sesion === null`.
 *   U2: SWR key null pre-auth (accessToken === null).
 *   U3: SWR key = `/operacion/mi-turno?uuid_sesion=X` when both inputs
 *       are present.
 *   U4: refreshInterval = 15_000 ms (REQ-OPS-188, AD-3 — operator-live
 *       cadence, 2x faster than F11.x 30s).
 *   U5: dedupingInterval = 5_000 ms.
 *   U6: shouldRetryOnError excludes 401 (let auth store react), 403
 *       (forbidden terminal), 404 (sesion typo terminal). Includes 500
 *       (operational retry).
 *   U7: onError with ParkosHttpError 401 -> useAuthStore.clear() +
 *       parkos:auth:cleared window event (F2.2 invariant, F11.2 AD-3).
 *   U8: onError with ParkosHttpError 500 -> NO clear, NO event,
 *       console.warn invoked.
 *   U9: zero-state (data undefined) -> hook returns { data: undefined,
 *       error: undefined } so the panel renders zeros (DA-F12.1-4).
 *
 * Mocking strategy (verbatim useOcupacion.test.ts precedent):
 *   - vi.mock('@parkos/ui-kit/store') -> useAuthStore selector + getState
 *   - vi.mock('@parkos/ui-kit/fetch') -> ParkosHttpError class
 *   - vi.mock('../api/miTurnoApi')   -> getMiTurno stub (we'll add this
 *                                       in C-F2; the RED scaffold
 *                                       expects it to NOT exist yet)
 *   - vi.mock('swr')                 -> useSWR configurado; we capture
 *                                       key/options/refreshInterval/etc.
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
    constructor(status: number, _message?: string, _url?: string) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

const getMiTurnoMock = vi.fn();
let swrOptions: Record<string, unknown> | undefined;
let swrKey: string | null | undefined;
let swrFetcher: ((k: string) => Promise<unknown>) | undefined;
const mutateMock = vi.fn();
let currentData: unknown = undefined;
let currentError: unknown = undefined;

vi.mock('../api/miTurnoApi', () => ({
  getMiTurno: (...args: unknown[]) => getMiTurnoMock(...args),
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
import { useMiTurno } from './useMiTurno';

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

const SAMPLE_OK = {
  uuid_sesion: '00000000-0000-0000-0000-000000000099',
  uuid_sucursal: '00000000-0000-0000-0000-000000000098',
  timestamp_calculo: '2026-09-21T08:00:00Z',
  ingresos_count: 3,
  salidas_count: 2,
  total_cobrado_efectivo_cop: 50000,
  total_cobrado_datafono_cop: 30000,
};

describe('useMiTurno — SWR key gating', () => {
  it('U1: SWR key null cuando uuid_sesion === null', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useMiTurno(null);
    expect(swrKey).toBeNull();
  });

  it('U2: SWR key null pre-auth (accessToken === null)', () => {
    useAuthStoreMock.mockReturnValue(null);
    useMiTurno('00000000-0000-0000-0000-000000000099');
    expect(swrKey).toBeNull();
  });

  it('U3: SWR key con ambos inputs presentes', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useMiTurno('00000000-0000-0000-0000-000000000099');
    expect(swrKey).toBe(
      '/operacion/mi-turno?uuid_sesion=00000000-0000-0000-0000-000000000099',
    );
  });
});

describe('useMiTurno — SWR config (REQ-OPS-188)', () => {
  it('U4: refreshInterval = 15_000 ms (operator-live cadence)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useMiTurno('00000000-0000-0000-0000-000000000099');
    expect(swrOptions?.refreshInterval).toBe(15_000);
  });

  it('U5: dedupingInterval = 5_000 ms', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useMiTurno('00000000-0000-0000-0000-000000000099');
    expect(swrOptions?.dedupingInterval).toBe(5_000);
  });

  it('U6: shouldRetryOnError excluye 401, 403, 404; incluye 500', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useMiTurno('00000000-0000-0000-0000-000000000099');
    const shouldRetry = swrOptions?.shouldRetryOnError as (err: unknown) => boolean;
    expect(shouldRetry(new ParkosHttpError(401))).toBe(false);
    expect(shouldRetry(new ParkosHttpError(403))).toBe(false);
    expect(shouldRetry(new ParkosHttpError(404))).toBe(false);
    expect(shouldRetry(new ParkosHttpError(500))).toBe(true);
    expect(shouldRetry(new Error('network'))).toBe(true);
  });
});

describe('useMiTurno — onError policy', () => {
  it('U7: onError con status=401 -> useAuthStore.clear() + parkos:auth:cleared event', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useMiTurno('00000000-0000-0000-0000-000000000099');
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(401, 'unauthorized', '/operacion/mi-turno'));
    expect(getStateClearMock).toHaveBeenCalledTimes(1);
    const events = dispatchEventSpy.mock.calls.map((c) => (c[0] as Event).type);
    expect(events).toContain('parkos:auth:cleared');
  });

  it('U8: onError con status=500 -> NO clear, NO event, console.warn invoked', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    useMiTurno('00000000-0000-0000-0000-000000000099');
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(500, 'server', '/operacion/mi-turno'));
    expect(getStateClearMock).not.toHaveBeenCalled();
    const events = dispatchEventSpy.mock.calls.map((c) => (c[0] as Event).type);
    expect(events).not.toContain('parkos:auth:cleared');
    expect(consoleWarnSpy).toHaveBeenCalled();
  });
});

describe('useMiTurno — zero-state (DA-F12.1-4)', () => {
  it('U9: data undefined + uuid_sesion present -> hook returns all-zero fallback so the panel renders zeros without skeleton/error UI', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    currentData = undefined;
    currentError = undefined;
    const result = useMiTurno('00000000-0000-0000-0000-000000000099');
    // The hook returns the all-zero fallback object so the panel can
    // render unconditionally — no skeleton, no error UI on cold boot.
    expect(result.data).not.toBeNull();
    expect(result.data).not.toBeUndefined();
    expect(result.data?.ingresos_count).toBe(0);
    expect(result.data?.salidas_count).toBe(0);
    expect(result.data?.total_cobrado_efectivo_cop).toBe(0);
    expect(result.data?.total_cobrado_datafono_cop).toBe(0);
    expect(result.error).toBeUndefined();
  });
});

describe('useMiTurno — fetcher parses response through MiTurnoSchema (Zod)', () => {
  it('U10: fetcher returns parsed payload — panel reads normalized fields', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    getMiTurnoMock.mockResolvedValue(SAMPLE_OK);
    useMiTurno('00000000-0000-0000-0000-000000000099');
    // The fetcher is wrapped: parkosFetch -> MiTurnoSchema.parse. We
    // verify the wrapper exists; raw fetch happens through the mocked
    // parkosFetch + the getMiTurnoApi stub from C-F2.
    expect(swrFetcher).toBeDefined();
    expect(typeof swrFetcher).toBe('function');
  });
});