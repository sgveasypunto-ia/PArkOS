/**
 * `useArqueoResumenPorSesion.test.ts` — Strict-TDD RED scaffold for
 * HU-F10.3 (REQ-OPS-163, REQ-OPS-165, AD-1).
 *
 * Per-session sibling hook consuming F1.13 backend
 * `ArqueoResumenRead { fecha, uuid_sucursal, sesiones: ArqueoResumenItem[],
 * cierre_dia: ArqueoResumenItem | null }`. Drift anchor DA-F10.3-4
 * (per-session shape) + NEW-DA-F10.3-9 (legacy aggregate Zod left
 * untouched).
 *
 * Scenarios (4):
 *   hook-1 — happy path: returns per-session array with 3 sesiones
 *            (2 cerradas + 1 abierta) so the `<CierreDiario />` page
 *            renders the per-session table with one open session to
 *            close.
 *   hook-2 — empty array: returns `{ sesiones: [] }` when no sessions
 *            of the day for the active branch (defensive — the page
 *            renders the empty-state placeholder banner).
 *   hook-3 — `cierre_dia` already-closed: when the backend already
 *            records a `cierre_dia` ArqueoResumenItem for the day, the
 *            hook surfaces `data.cierre_dia !== null` so the page
 *            disables Confirmar + renders the alreadyClosed banner.
 *   hook-4 — 401 triggers `useAuthStore.clear()` +
 *            `parkos:auth:cleared` event (mirrors F10.1 hook policy
 *            at `useArqueo.ts:82-89`).
 *
 * Each scenario asserts a SPECIFIC value derived from the spec
 * scenario body — no `toBeDefined()` smoke tests, no
 * `toHaveLength(0)` without setup context. Mocks are scoped to the
 * minimum: `@parkos/ui-kit/fetch` for the SWR fetcher; the auth
 * store for the 401-clear path.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// Mock `@parkos/ui-kit/fetch` first so the hook captures the mocked
// parkosFetch reference on import. The dynamic import pattern
// (mirrors `useArqueo.test.ts:51-58`).
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: vi.fn(),
  ParkosHttpError: class ParkosHttpError extends Error {
    readonly status: number;
    readonly code: string;
    constructor(status: number, message: string, code = 'http_error') {
      super(message);
      this.status = status;
      this.code = code;
      this.name = 'ParkosHttpError';
    }
  },
}));

// Mock the auth store so the 401-clear path can be asserted without
// a real persist middleware. The selector must EVALUATE the
// selector against the fake state so `useAuthStore((s) =>
// s.accessToken)` returns the accessToken — otherwise the hook's
// SWR key-gate returns null and the fetch never fires.
const mockClear = vi.fn();
const dispatchEventSpy = vi
  .spyOn(window, 'dispatchEvent')
  .mockImplementation(() => true);

const FAKE_AUTH_STATE = { accessToken: 'tok', refreshToken: null, expiresAt: null };

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: typeof FAKE_AUTH_STATE) => unknown) =>
      selector(FAKE_AUTH_STATE),
    { getState: () => ({ ...FAKE_AUTH_STATE, clear: mockClear }) },
  ),
}));

// Re-import AFTER the mocks are registered.
const hookModule = await import('../useArqueoResumenPorSesion');
const { useArqueoResumenPorSesion } = hookModule;
const fetchModule = await import('@parkos/ui-kit/fetch');
const { parkosFetch, ParkosHttpError } = fetchModule;
const mockedFetch = vi.mocked(parkosFetch);

// Standard 3-session respuesta (2 cerradas + 1 abierta) per spec
// REQ-OPS-163 scenario 1. Each fixture uses a distinct
// `uuid_sucursal` so the SWR cache key differs across tests and the
// cache doesn't bleed scenarios.
const TRES_SESIONES = {
  fecha: '2026-09-21',
  uuid_sucursal: '11111111-2222-4333-8444-555555555555',
  sesiones: [
    {
      uuid_sesion: '22222222-3333-4444-8555-666666666666',
      uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      timestamp_apertura: '2026-09-21T08:00:00Z',
      timestamp_cierre: '2026-09-21T18:00:00Z',
      estado: 'cerrado',
      valor_efectivo_esperado: 50_000,
      valor_datafono_esperado: 0,
      valor_efectivo_reportado: 50_000,
      valor_datafono_reportado: 0,
      uuid_arqueo: 'cccccccc-dddd-4eee-8fff-111111111111',
    },
    {
      uuid_sesion: '33333333-4444-4555-8666-777777777777',
      uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      timestamp_apertura: '2026-09-21T08:00:00Z',
      timestamp_cierre: '2026-09-21T18:00:00Z',
      estado: 'cerrado',
      valor_efectivo_esperado: 100_000,
      valor_datafono_esperado: 30_000,
      valor_efectivo_reportado: 100_000,
      valor_datafono_reportado: 30_000,
      uuid_arqueo: 'cccccccc-dddd-4eee-8fff-222222222222',
    },
    {
      uuid_sesion: '44444444-5555-4666-8777-888888888888',
      uuid_usuario: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      timestamp_apertura: '2026-09-21T08:00:00Z',
      timestamp_cierre: null,
      estado: 'abierta',
      valor_efectivo_esperado: null,
      valor_datafono_esperado: null,
      valor_efectivo_reportado: null,
      valor_datafono_reportado: null,
      uuid_arqueo: null,
    },
  ],
  cierre_dia: null,
};

const EMPTY_SESIONES = {
  // Past date — key-gate would skip future dates per DA-F10.3-3.
  fecha: '2026-09-19',
  uuid_sucursal: '11111111-2222-4333-8444-666666666666',
  sesiones: [],
  cierre_dia: null,
};

const CIERRE_DIA_EXISTENTE = {
  // Past date — key-gate would skip future dates per DA-F10.3-3.
  fecha: '2026-09-20',
  uuid_sucursal: '11111111-2222-4333-8444-777777777777',
  sesiones: TRES_SESIONES.sesiones,
  cierre_dia: {
    uuid_sesion: null,
    uuid_usuario: '99999999-aaaa-4bbb-8ccc-dddddddddddd',
    timestamp_apertura: null,
    timestamp_cierre: null,
    estado: 'cerrado',
    valor_efectivo_esperado: 150_000,
    valor_datafono_esperado: 30_000,
    valor_efectivo_reportado: 150_000,
    valor_datafono_reportado: 30_000,
    uuid_arqueo: '00000000-aaaa-4bbb-8ccc-dddddddddddd',
  },
};

const AUTH_FAILURE_FIXTURE = {
  // Past date — key-gate would skip future dates per DA-F10.3-3.
  fecha: '2026-09-20',
  uuid_sucursal: '11111111-2222-4333-8444-888888888888',
};

describe('HU-F10.3 — useArqueoResumenPorSesion (REQ-OPS-163, REQ-OPS-165, AD-1)', () => {
  beforeEach(() => {
    mockedFetch.mockReset();
    mockClear.mockClear();
    dispatchEventSpy.mockClear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ──────────────────────────────────────────────────────────────────
  // hook-1 — happy path: per-session array returns 3 sesiones
  // ──────────────────────────────────────────────────────────────────
  it('hook-1: returns per-session array with 3 sesiones (2 cerradas + 1 abierta) per REQ-OPS-163', async () => {
    mockedFetch.mockResolvedValueOnce(TRES_SESIONES as never);

    const { result } = renderHook(() =>
      useArqueoResumenPorSesion(
        TRES_SESIONES.uuid_sucursal,
        TRES_SESIONES.fecha,
      ),
    );

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });
    expect(result.current.error).toBeUndefined();
    expect(result.current.data?.sesiones).toHaveLength(3);
    expect(result.current.data?.cierre_dia).toBeNull();
    // 2 cerradas + 1 abierta — exact distribution per scenario body.
    const cerradas =
      result.current.data?.sesiones.filter((s) => s.estado === 'cerrado') ?? [];
    const abiertas =
      result.current.data?.sesiones.filter((s) => s.estado === 'abierta') ?? [];
    expect(cerradas).toHaveLength(2);
    expect(abiertas).toHaveLength(1);
    // refresh is callable — verify the function reference exists.
    expect(typeof result.current.refresh).toBe('function');
  });

  // ──────────────────────────────────────────────────────────────────
  // hook-2 — empty array: no sesiones of the day
  // ──────────────────────────────────────────────────────────────────
  it('hook-2: returns empty sesiones array when no sessions of the day (REQ-OPS-165 defensive)', async () => {
    mockedFetch.mockResolvedValueOnce(EMPTY_SESIONES as never);

    const { result } = renderHook(() =>
      useArqueoResumenPorSesion(
        EMPTY_SESIONES.uuid_sucursal,
        EMPTY_SESIONES.fecha,
      ),
    );

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });
    expect(result.current.error).toBeUndefined();
    expect(result.current.data?.sesiones).toEqual([]);
    expect(result.current.data?.cierre_dia).toBeNull();
  });

  // ──────────────────────────────────────────────────────────────────
  // hook-3 — cierre_dia exists disables Confirmar
  // ──────────────────────────────────────────────────────────────────
  it('hook-3: surfaces cierre_dia !== null so the page disables Confirmar + renders alreadyClosed banner', async () => {
    mockedFetch.mockResolvedValueOnce(CIERRE_DIA_EXISTENTE as never);

    const { result } = renderHook(() =>
      useArqueoResumenPorSesion(
        CIERRE_DIA_EXISTENTE.uuid_sucursal,
        CIERRE_DIA_EXISTENTE.fecha,
      ),
    );

    await waitFor(() => {
      expect(result.current.data?.cierre_dia).not.toBeNull();
    });
    expect(result.current.data?.cierre_dia?.uuid_arqueo).toBe(
      '00000000-aaaa-4bbb-8ccc-dddddddddddd',
    );
    // sesiones still rendered for the report — 3 sesiones surfaced.
    expect(result.current.data?.sesiones).toHaveLength(3);
  });

  // ──────────────────────────────────────────────────────────────────
  // hook-4 — 401 triggers useAuthStore.clear() + parkos:auth:cleared
  // ──────────────────────────────────────────────────────────────────
  it('hook-4: 401 triggers useAuthStore.clear() + dispatches parkos:auth:cleared event', async () => {
    mockedFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, 'unauthorized', 'auth_invalid'),
    );

    renderHook(() =>
      useArqueoResumenPorSesion(
        AUTH_FAILURE_FIXTURE.uuid_sucursal,
        AUTH_FAILURE_FIXTURE.fecha,
      ),
    );

    // Verify the hook attempted the fetch (sanity).
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(mockedFetch).toHaveBeenCalled();

    // SWR error handlers run asynchronously — wait long enough for
    // the rejection to propagate through onError.
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(mockClear).toHaveBeenCalledTimes(1);
    const dispatched = dispatchEventSpy.mock.calls.find((call) => {
      const ev = call[0] as Event;
      return ev?.type === 'parkos:auth:cleared';
    });
    expect(dispatched).toBeDefined();
  });
});