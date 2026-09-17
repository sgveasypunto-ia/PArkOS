/**
 * Unit tests for `useTarifasVigentes()` (HU-F4.2 — T4).
 *
 * Coverage U1..U3 verbatim tasks.md §4.1 (cross-ref F4.1 precedent
 * `useTiposVehiculo.test.ts`):
 *   U1 (cache válido): cache `{items:[{...auto}], fetchedAt:<recent>}`
 *      → `tarifa` del cache, `isStale === false`, `isFromFallback === true`.
 *   U2 (invalidación tras cambio de tipo): cache contiene `auto` y `moto`
 *      → dos consumers (`uuid-auto`, `uuid-moto`) resuelven desde el mismo
 *      snapshot, UNA sola fetch SWR fires (deduping compartido).
 *   U3 (API 200 path): onSuccess → `bridge.tarifasStore.set` con JSON.
 *
 * Mocking strategy (precedent F4.1 verbatim, adapted for React hooks):
 *   - vi.mock('@parkos/ui-kit/store') → useAuthStore selector + getState.clear().
 *   - vi.mock('@parkos/ui-kit/fetch') → ParkosHttpError class.
 *   - vi.mock('../api/tarifasSucursalApi') → listTarifasSucursal stub.
 *   - vi.mock('swr') → capturamos options + ejecutamos onSuccess/onError
 *     programáticamente para verificar persistencia y 401 logout.
 *   - `window.bridge.tarifasStore` stub directo (mutado en beforeEach).
 *
 * Testing pattern divergence from F4.1: `useTarifasVigentes` calls
 * `useState` + `useEffect` (two-phase render DEC-F4.2-02), so the tests
 * MUST use `renderHook` from `@testing-library/react` to provide a real
 * React dispatcher. F4.1's `useTiposVehiculo` did not use React hooks,
 * which is why those tests could call the hook directly.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const useAuthStoreMock = vi.fn();
const getStateClearMock = vi.fn();
const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true);

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

const listTarifasSucursalMock = vi.fn();
let swrOptions: Record<string, unknown> | undefined;
let swrKey: string | null | undefined;
const mutateMock = vi.fn();

vi.mock('../api/tarifasSucursalApi', () => ({
  listTarifasSucursal: (...args: unknown[]) => listTarifasSucursalMock(...args),
}));

// swr mock configurable: tests control `data` and `isLoading` return values.
// The mock prefers `options.fallbackData` (the cache-hydrated snapshot from
// `useTarifasVigentes`) over `mockData` so that reference equality
// `snapshot === cacheHydrated` holds when the cache was hydrated — which
// is what the real SWR does internally.
let mockData: unknown = undefined;
let mockIsLoading = false;
vi.mock('swr', () => ({
  default: (
    key: string | null | undefined,
    _fetcher: () => Promise<unknown>,
    options: Record<string, unknown>,
  ) => {
    swrKey = key;
    swrOptions = options;
    const fallback = options.fallbackData as unknown;
    return {
      data: fallback !== undefined ? fallback : mockData,
      error: undefined,
      isLoading: mockIsLoading,
      mutate: mutateMock,
    };
  },
}));

// `window.bridge.tarifasStore` stub. Tests seed `cacheReadValue` to
// simulate the electron-store snapshot at hydration time.
const tarifasStoreGetMock = vi.fn();
const tarifasStoreSetMock = vi.fn();

beforeEach(() => {
  mockData = undefined;
  mockIsLoading = false;
  swrOptions = undefined;
  swrKey = undefined;
  tarifasStoreGetMock.mockReset();
  tarifasStoreSetMock.mockReset();
  // Default: no cache → get resolves to null.
  tarifasStoreGetMock.mockResolvedValue(null);
  tarifasStoreSetMock.mockResolvedValue(undefined);

  (window as unknown as { bridge: { tarifasStore: unknown } }).bridge = {
    tarifasStore: {
      get: tarifasStoreGetMock,
      set: tarifasStoreSetMock,
      delete: vi.fn().mockResolvedValue(undefined),
    },
  };
});

afterEach(() => {
  vi.clearAllMocks();
  dispatchEventSpy.mockClear();
});

// Import after mocks so the mocked modules are wired.
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useTarifasVigentes } from './useTarifasVigentes';

const UUID_AUTO = '00000000-0000-0000-0000-000000000a01';
const UUID_MOTO = '00000000-0000-0000-0000-000000000a02';

const CACHE_AUTO = {
  items: [
    {
      uuid: 'uuid-tarifa-auto',
      uuid_sucursal: 'uuid-sucursal',
      uuid_tipo_vehiculo: UUID_AUTO,
      uuid_tipo_tarifa: 'uuid-tipo-tarifa',
      valor: 8000,
      valor_plena: 80000,
      vigente_desde: '2026-01-01T00:00:00Z',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00Z',
      created_by: null,
      sync_status: null,
    },
  ],
  fetchedAt: Date.now() - 60 * 1000, // 1min ago → fresh
};

const CACHE_BOTH = {
  items: [
    {
      uuid: 'uuid-tarifa-auto',
      uuid_sucursal: 'uuid-sucursal',
      uuid_tipo_vehiculo: UUID_AUTO,
      uuid_tipo_tarifa: 'uuid-tipo-tarifa',
      valor: 8000,
      valor_plena: 80000,
      vigente_desde: '2026-01-01T00:00:00Z',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00Z',
      created_by: null,
      sync_status: null,
    },
    {
      uuid: 'uuid-tarifa-moto',
      uuid_sucursal: 'uuid-sucursal',
      uuid_tipo_vehiculo: UUID_MOTO,
      uuid_tipo_tarifa: 'uuid-tipo-tarifa',
      valor: 4000,
      valor_plena: 40000,
      vigente_desde: '2026-01-01T00:00:00Z',
      vigente_hasta: null,
      estado: 'activo',
      created_at: '2026-01-01T00:00:00Z',
      created_by: null,
      sync_status: null,
    },
  ],
  fetchedAt: Date.now() - 60 * 1000,
};

describe('useTarifasVigentes — SWR config', () => {
  it('U0: SWR key null sin accessToken (gate pre-login)', () => {
    useAuthStoreMock.mockReturnValue(null);
    renderHook(() => useTarifasVigentes(UUID_AUTO));
    expect(swrKey).toBeNull();
  });

  it('U0b: SWR key con accessToken presente = "/empresa/tarifas-sucursal"', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    renderHook(() => useTarifasVigentes(UUID_AUTO));
    expect(swrKey).toBe('/empresa/tarifas-sucursal');
  });

  it('config: dedupingInterval = 5min (DEC-F4.2-05 verbatim plan.md:1375)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    renderHook(() => useTarifasVigentes(UUID_AUTO));
    expect(swrOptions?.dedupingInterval).toBe(5 * 60 * 1000);
  });

  it('config: shouldRetryOnError excluye 404 (sucursal sin tarifas es estado válido)', () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    renderHook(() => useTarifasVigentes(UUID_AUTO));
    const shouldRetry = swrOptions?.shouldRetryOnError as (err: unknown) => boolean;
    expect(shouldRetry(new ParkosHttpError(404))).toBe(false);
    expect(shouldRetry(new ParkosHttpError(500))).toBe(true);
    expect(shouldRetry(new ParkosHttpError(401))).toBe(true);
  });
});

describe('useTarifasVigentes — cache hydration via window.bridge.tarifasStore', () => {
  it('U1: cache válido (1min ago) → tarifa del cache + isStale=false + isFromFallback=true', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(JSON.stringify(CACHE_AUTO));
    mockData = CACHE_AUTO;
    const { result } = renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(result.current.tarifa).not.toBeNull();
    });
    expect(tarifasStoreGetMock).toHaveBeenCalledWith('parkos.tarifas.cache.v1');
    expect(result.current.tarifa?.valor).toBe(8000);
    expect(result.current.tarifa?.uuid_tipo_vehiculo).toBe(UUID_AUTO);
    expect(result.current.isStale).toBe(false);
    expect(result.current.isFromFallback).toBe(true);
  });

  it('U1b: cache stale (2h ago) → isStale=true pero tarifa sigue visible', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    const staleCache = {
      ...CACHE_AUTO,
      fetchedAt: Date.now() - 2 * 60 * 60 * 1000,
    };
    tarifasStoreGetMock.mockResolvedValueOnce(JSON.stringify(staleCache));
    mockData = staleCache;
    const { result } = renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(result.current.tarifa).not.toBeNull();
    });
    expect(result.current.tarifa?.valor).toBe(8000);
    expect(result.current.isStale).toBe(true);
    expect(result.current.isFromFallback).toBe(true);
  });

  it('U2: invalidación tras cambio de tipo (cache hit compartido, sin refetch)', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(JSON.stringify(CACHE_BOTH));
    mockData = CACHE_BOTH;
    const { result: resultAuto } = renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(resultAuto.current.tarifa).not.toBeNull();
    });
    const { result: resultMoto } = renderHook(() => useTarifasVigentes(UUID_MOTO));
    // Re-read after second mount — both should resolve from the cache.
    await waitFor(() => {
      expect(resultMoto.current.tarifa).not.toBeNull();
    });
    expect(resultAuto.current.tarifa?.valor).toBe(8000);
    expect(resultMoto.current.tarifa?.valor).toBe(4000);
    // No API call fired — everything came from the SWR cache hydrated from electron-store.
    expect(listTarifasSucursalMock).not.toHaveBeenCalled();
  });

  it('U2b: cache vacío → tarifa === null, isStale=false', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(null);
    mockData = undefined;
    const { result } = renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(tarifasStoreGetMock).toHaveBeenCalled();
    });
    expect(result.current.tarifa).toBeNull();
    expect(result.current.fetchedAt).toBeNull();
    expect(result.current.isStale).toBe(false);
    expect(result.current.isFromFallback).toBe(false);
  });

  it('U2c: cache corrupto (JSON inválido) → fallback silencioso, tarifa === null', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce('{"items": BROKEN');
    mockData = undefined;
    const { result } = renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(tarifasStoreGetMock).toHaveBeenCalled();
    });
    expect(result.current.tarifa).toBeNull();
    expect(tarifasStoreSetMock).not.toHaveBeenCalled();
  });
});

describe('useTarifasVigentes — onSuccess persistence', () => {
  it('U3: onSuccess → window.bridge.tarifasStore.set con snapshot JSON', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(null);
    renderHook(() => useTarifasVigentes(UUID_AUTO));
    // Capture onSuccess and run it with a fresh snapshot.
    await waitFor(() => {
      expect(swrOptions?.onSuccess).toBeDefined();
    });
    const onSuccess = swrOptions?.onSuccess as (s: unknown) => void | Promise<void>;
    const snapshot = { items: CACHE_BOTH.items, fetchedAt: 1_700_000_000_000 };
    await onSuccess(snapshot);
    expect(tarifasStoreSetMock).toHaveBeenCalledWith(
      'parkos.tarifas.cache.v1',
      JSON.stringify(snapshot),
    );
  });
});

describe('useTarifasVigentes — onError 401 logout defensivo', () => {
  it('U4: onError con status=401 → useAuthStore.getState().clear() + parkos:auth:cleared event', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(null);
    renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(swrOptions?.onError).toBeDefined();
    });
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(401));
    expect(getStateClearMock).toHaveBeenCalledOnce();
    expect(dispatchEventSpy).toHaveBeenCalledWith(expect.any(Event));
    const event = (dispatchEventSpy.mock.calls[0]?.[0] as Event) ?? null;
    expect(event?.type).toBe('parkos:auth:cleared');
  });

  it('U4b: onError con status=500 → NO clear, NO event', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(null);
    renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(swrOptions?.onError).toBeDefined();
    });
    const onError = swrOptions?.onError as (err: unknown) => void;
    onError(new ParkosHttpError(500));
    expect(getStateClearMock).not.toHaveBeenCalled();
    expect(dispatchEventSpy).not.toHaveBeenCalled();
  });
});

describe('useTarifasVigentes — return shape', () => {
  it('expone { tarifa, fetchedAt, isStale, isFromFallback, refresh }', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(JSON.stringify(CACHE_AUTO));
    mockData = CACHE_AUTO;
    const { result } = renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(result.current.tarifa).not.toBeNull();
    });
    expect(result.current).toHaveProperty('tarifa');
    expect(result.current).toHaveProperty('fetchedAt');
    expect(result.current).toHaveProperty('isStale');
    expect(result.current).toHaveProperty('isFromFallback');
    expect(result.current).toHaveProperty('refresh');
  });

  it('refresh retorna Promise (wrap de SWR mutate)', async () => {
    useAuthStoreMock.mockReturnValue('jwt-abc');
    tarifasStoreGetMock.mockResolvedValueOnce(null);
    const { result } = renderHook(() => useTarifasVigentes(UUID_AUTO));
    await waitFor(() => {
      expect(result.current.refresh).toBeDefined();
    });
    const r = result.current.refresh();
    expect(r).toBeInstanceOf(Promise);
    await r;
    expect(mutateMock).toHaveBeenCalled();
  });
});
