/**
 * `useSyncEstado.test.ts` — Strict-TDD RED scaffold for HU-F11.1
 * (REQ-OPS-170 + DA-F11.1-7 schema-drift gate).
 *
 * Drift anchor DA-F11.1-7 is GATING: the current FE Zod schema
 * (`apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts:17-26`)
 * declares fields the backend `SyncEstadoRead` does NOT return
 * (`estado`, `ultimo_error`, `ultima_sync`) AND misses `ultima_sync_at`.
 * The hook FAILS Zod parse against the real backend today.
 *
 * Coverage:
 *   U1: parses the real backend shape (4 fields).
 *   U2: accepts `ultima_sync_at IS NULL` + `lag_seg IS NULL` (never-synced
 *       branch — REQ-OPS-171 "never_synced" badge).
 *   U3: rejects `lag_seg < 0` (Pydantic `int | None` guard).
 *   U4: 401 → `useAuthStore.getState().clear()` + window event.
 *
 * These tests are RED until C2 lands the corrected schema in
 * `useSyncEstado.ts` (lines 17-26 replaced verbatim per AD-1).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock the @parkos/ui-kit/store module so useSyncEstado captures the
// mocked authStore reference. Mirrors the F4.1 / F8.x precedent.
const getStateClearMock = vi.fn();
const useAuthStoreSelectorMock = vi.fn();
const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: { accessToken: string | null }) => unknown) =>
      useAuthStoreSelectorMock(selector),
    { getState: () => ({ clear: getStateClearMock }) },
  ),
}));

vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class ParkosHttpError extends Error {
    public readonly status: number;
    constructor(status: number) {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
    }
  },
}));

// Capture SWR config so each test can assert `key` (null gate),
// `refreshInterval`, `shouldRetryOnError`, and `onError`.
let swrOptions: Record<string, unknown> | undefined;
let swrKey: string | null | undefined;
let swrFetcher: (() => Promise<unknown>) | undefined;

vi.mock('swr', () => ({
  default: (
    key: string | null | undefined,
    fetcher: () => Promise<unknown>,
    options: Record<string, unknown>,
  ) => {
    swrKey = key;
    swrFetcher = fetcher;
    swrOptions = options;
    return { data: undefined, error: undefined, isLoading: false, mutate: vi.fn() };
  },
}));

// Import after mocks so the mocked modules are wired.
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { SyncEstadoSchema, useSyncEstado } from '../hooks/useSyncEstado';

const VALID_UUID = '00000000-0000-0000-0000-000000000001';

beforeEach(() => {
  swrOptions = undefined;
  swrKey = undefined;
  swrFetcher = undefined;
  useAuthStoreSelectorMock.mockReset();
  getStateClearMock.mockReset();
  dispatchEventSpy.mockClear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useSyncEstado — REQ-OPS-170 + DA-F11.1-7 schema alignment', () => {
  it('U1: SyncEstadoSchema parses the real backend SyncEstadoRead shape (4 fields)', () => {
    const body = {
      uuid_sucursal: VALID_UUID,
      ultima_sync_at: '2026-09-21T10:00:00.000Z',
      lag_seg: 42,
      pendientes: 3,
    };
    const parsed = SyncEstadoSchema.parse(body);
    expect(parsed.uuid_sucursal).toBe(VALID_UUID);
    expect(parsed.ultima_sync_at).toBe('2026-09-21T10:00:00.000Z');
    expect(parsed.lag_seg).toBe(42);
    expect(parsed.pendientes).toBe(3);
  });

  it('U2: SyncEstadoSchema accepts ultima_sync_at IS NULL + lag_seg IS NULL (never-synced branch)', () => {
    const body = {
      uuid_sucursal: VALID_UUID,
      ultima_sync_at: null,
      lag_seg: null,
      pendientes: 0,
    };
    const parsed = SyncEstadoSchema.parse(body);
    expect(parsed.ultima_sync_at).toBeNull();
    expect(parsed.lag_seg).toBeNull();
    expect(parsed.pendientes).toBe(0);
  });

  it('U3: SyncEstadoSchema rejects lag_seg < 0 with ZodError (Pydantic int | None guard)', () => {
    const body = {
      uuid_sucursal: VALID_UUID,
      ultima_sync_at: '2026-09-21T10:00:00.000Z',
      lag_seg: -1,
      pendientes: 0,
    };
    expect(() => SyncEstadoSchema.parse(body)).toThrow();
  });

  it('U4: shouldRetryOnError returns false for 401/403/404 (no retry); onError clears auth on 401', () => {
    // Authenticated operator → SWR key built → mock SWR captures options.
    useAuthStoreSelectorMock.mockReturnValue('jwt-abc');

    // Invoke the hook so the mocked useSWR captures options.
    useSyncEstado(VALID_UUID);

    expect(swrOptions).toBeDefined();
    expect(swrKey).toBe(`/sync/estado?uuid_sucursal=${VALID_UUID}`);

    const opts = swrOptions as {
      refreshInterval?: number;
      shouldRetryOnError?: (err: unknown) => boolean;
      onError?: (err: unknown) => void;
    };
    expect(opts.refreshInterval).toBe(30_000);

    const retry = opts.shouldRetryOnError;
    expect(retry).toBeDefined();
    if (!retry) throw new Error('shouldRetryOnError missing');

    const err401 = new ParkosHttpError(401, 'Unauthorized');
    const err403 = new ParkosHttpError(403, 'Forbidden');
    const err404 = new ParkosHttpError(404, 'Not Found');
    const err500 = new ParkosHttpError(500, 'Server Error');
    expect(retry(err401)).toBe(false);
    expect(retry(err403)).toBe(false);
    expect(retry(err404)).toBe(false);
    expect(retry(err500)).toBe(true);

    const onError = opts.onError;
    expect(onError).toBeDefined();
    if (!onError) throw new Error('onError missing');
    onError(err401);
    expect(getStateClearMock).toHaveBeenCalledTimes(1);
    expect(dispatchEventSpy).toHaveBeenCalled();
  });
});
