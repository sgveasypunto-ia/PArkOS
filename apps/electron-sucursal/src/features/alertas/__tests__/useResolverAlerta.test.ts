/**
 * `useResolverAlerta.test.ts` — Strict-TDD unit coverage for the
 * append-only "marcar revisada" transition (HU-F11.2, REQ-OPS-181 +
 * DEC-SUC-25 + DA-F11.2-2 + DA-F11.2-8 + DA-F11.2-13).
 *
 * Coverage:
 *   R1: payload shape — `uuid_alerta_padre`, `estado: 'resuelta'`
 *       (NEVER 'descartada' — REQ-26 actor check trip), all
 *       required fields present.
 *   R2: SWR cache invalidation on 200 — `mutate(...)` is called
 *       with a matcher targeting `/workflows/alerta` + `estado=activa`.
 *   R3: 403 → `actor_is_target` typed error (defense — we never
 *       emit 'descartada' but the hook surfaces a typed error
 *       anyway for future-proofing).
 *   R4: NEVER records a PUT or PATCH against `/workflows/alerta/*`
 *       (DEC-SUC-25 canon — `prod.alerta` is `[A]`, append-only).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// All mocks are declared with vi.mock factory bodies that do NOT
// reference top-level variables (vi.mock factories are hoisted to
// the top of the file — accessing `let` / `const` here throws
// `Cannot access 'X' before initialization`).
const useAuthStoreSelectorMock = vi.fn();
const mutateMock = vi.fn(async () => undefined);

vi.mock('@parkos/ui-kit/store', () => ({
  useAuthStore: Object.assign(
    (selector: (s: { accessToken: string | null; user?: { uuid?: string | null; sucursal?: { uuid?: string | null } | null } }) => unknown) =>
      useAuthStoreSelectorMock(selector),
    {
      getState: () => ({
        accessToken: 'jwt-abc',
        user: { uuid: '00000000-0000-0000-0000-000000000099', sucursal: { uuid: '00000000-0000-0000-0000-000000000001' } },
      }),
    },
  ),
}));

const parkosFetchMock = vi.fn();
vi.mock('@parkos/ui-kit/fetch', () => ({
  ParkosHttpError: class ParkosHttpError extends Error {
    public readonly status: number;
    public readonly body: string;
    public readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`ParkosHttpError ${status} ${url}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
  parkosFetch: (...args: unknown[]) => parkosFetchMock(...args),
}));

vi.mock('swr', () => ({
  useSWRConfig: () => ({ mutate: mutateMock }),
}));

import { renderHook, act } from '@testing-library/react';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';
import { useResolverAlerta } from '../hooks/useResolverAlerta';

const ALERT_UUID = '00000000-0000-0000-0000-000000000001';

const ALERT = {
  uuid: ALERT_UUID,
  fecha_retencion_hasta: '2031-09-21',
  created_at: '2026-09-21T10:00:00.000Z',
  created_by: null,
  sync_status: null,
  sync_timestamp: null,
  sync_attempts: null,
  uuid_sucursal: '00000000-0000-0000-0000-000000000001',
  uuid_usuario: '00000000-0000-0000-0000-000000000099',
  uuid_arqueo: null,
  tipo_alerta: 'descuadre_critico',
  valor_diferencia_efectivo: null,
  valor_diferencia_datafono: null,
  uuid_alerta_padre: null,
  timestamp_evento: '2026-09-21T10:00:00.000Z',
  vigente_desde: '2026-09-21T10:00:00.000Z',
  vigente_hasta: null,
  estado: 'activa' as const,
};

beforeEach(() => {
  parkosFetchMock.mockReset();
  mutateMock.mockReset();
  useAuthStoreSelectorMock.mockReset();
  useAuthStoreSelectorMock.mockReturnValue('jwt-abc');
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useResolverAlerta — REQ-OPS-181 + DEC-SUC-25 (HU-F11.2)', () => {
  it('R1: payload shape — append-only POST with uuid_alerta_padre + estado: "resuelta" (NEVER descartada)', async () => {
    parkosFetchMock.mockResolvedValue({ ...ALERT, estado: 'resuelta', uuid_alerta_padre: ALERT_UUID });
    const { result } = renderHook(() => useResolverAlerta());

    await act(async () => {
      await result.current.resolve(ALERT);
    });

    expect(parkosFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = parkosFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/workflows/alerta');
    expect(init.method).toBe('POST');
    expect(init.body).toBeDefined();
    const body = JSON.parse(String(init.body));
    expect(body.uuid_alerta_padre).toBe(ALERT_UUID);
    expect(body.estado).toBe('resuelta');
    // DEC-SUC-25 canon — `prod.alerta` is `[A]`, NEVER PATCH / PUT.
    expect(init.method).not.toBe('PUT');
    expect(init.method).not.toBe('PATCH');
  });

  it('R2: SWR cache invalidate on 200 — mutate() called with /workflows/alerta matcher', async () => {
    parkosFetchMock.mockResolvedValue({ ...ALERT, estado: 'resuelta' });
    const { result } = renderHook(() => useResolverAlerta());

    await act(async () => {
      await result.current.resolve(ALERT);
    });

    expect(mutateMock).toHaveBeenCalledTimes(1);
    const matcher = (mutateMock.mock.calls[0] as unknown as [(key: unknown) => boolean])[0];
    expect(matcher('/workflows/alerta?uuid_sucursal=X&estado=activa')).toBe(true);
    expect(matcher('/workflows/alert-types?uuid_sucursal=X')).toBe(false);
    expect(matcher(null)).toBe(false);
  });

  it('R3: 403 → actor_is_target typed error (REQ-26 defense; we never emit descartada but the hook surfaces it)', async () => {
    parkosFetchMock.mockRejectedValue(new ParkosHttpError(403, '{"error":"actor_is_target"}', '/workflows/alerta'));
    const { result } = renderHook(() => useResolverAlerta());

    await act(async () => {
      await result.current.resolve(ALERT);
    });

    expect(result.current.error?.kind).toBe('actor_is_target');
    expect(result.current.isResolving).toBe(false);
  });

  it('R4: every recorded parkosFetch call uses POST (NEVER PUT/PATCH) — DEC-SUC-25 canon', async () => {
    parkosFetchMock.mockResolvedValue({ ...ALERT, estado: 'resuelta' });
    const { result } = renderHook(() => useResolverAlerta());

    await act(async () => {
      await result.current.resolve(ALERT);
    });

    const methods = parkosFetchMock.mock.calls.map((c) => {
      const init = c[1] as RequestInit | undefined;
      return (init?.method ?? 'GET').toUpperCase();
    });
    expect(methods).toEqual(['POST']);
    expect(methods).not.toContain('PUT');
    expect(methods).not.toContain('PATCH');
  });
});
