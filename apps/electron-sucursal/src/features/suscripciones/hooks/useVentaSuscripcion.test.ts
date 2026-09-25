/**
 * Tests for `useVentaSuscripcion` SWR mutation hook (HU-F9.1,
 * REQ-OPS-177 + REQ-OPS-179).
 *
 * Composition mirrors `useRegistrarSalida` (F7.2) and
 * `useRegistrarPago` (F8.1) — same `useSWRMutation` shape, same
 * F7.2 `buildIdempotencyKey` SHA-256 closure, same 401 auth-clear
 * invariant (REQ-OPS-107..110 preserved from F3.1).
 *
 * Coverage (4 hook tests):
 *   T1: 201 → returns parsed `VentaSuscripcionRead` with
 *       `uuid_subscripcion`.
 *   T2: 422 `suscripcion_duplicada_placa` → throws
 *       `VentaSuscripcionDuplicatePlateError`.
 *   T3: 422 `tipo_vehiculo_incompatible` → throws
 *       `VentaSuscripcionTipoIncompatibleError`.
 *   T4: 401 → `useAuthStore.getState().clear()` +
 *       `parkos:auth:cleared` event (F3.1 invariant preserved).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@parkos/ui-kit/store', () => {
  const state = { accessToken: 'tok-abc', clear: vi.fn() };
  return {
    useAuthStore: Object.assign(
      (sel: (s: typeof state) => unknown) => sel(state),
      { getState: () => state },
    ),
  };
});

const mockFetch = vi.fn();
vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: (...args: unknown[]) => mockFetch(...args),
  ParkosHttpError: class extends Error {
    public readonly status: number;
    public readonly body: string;
    constructor(status: number, body = '') {
      super(`ParkosHttpError ${status}`);
      this.name = 'ParkosHttpError';
      this.status = status;
      this.body = body;
    }
  },
}));

import { act, renderHook } from '@testing-library/react';

import {
  useVentaSuscripcion,
  VentaSuscripcionDuplicatePlateError,
  VentaSuscripcionTipoIncompatibleError,
} from './useVentaSuscripcion';
import { useAuthStore } from '@parkos/ui-kit/store';

const UUID_PLAN = '00000000-0000-0000-0000-0000000000a1';
const UUID_SUBSCRIPCION = '00000000-0000-0000-0000-0000000000b1';
const UUID_CLIENTE = '00000000-0000-0000-0000-0000000000c1';
const UUID_FACTURA = '00000000-0000-0000-0000-0000000000d1';

const UUID_SUCURSAL = '00000000-0000-0000-0000-0000000000f1';

// BUGFIX (2026-09-25): `VentaSuscripcionReadSchema` is `.strict()` and
// mirrors the FULL backend `VentaSuscripcionResponse` shape (11 fields,
// not the 5 this fixture used to carry) -- a mock missing any of them
// masked the real bug (every successful sale threw a `ZodError` because
// the backend always sends `uuid_sucursal`/`fecha_vencimiento`/etc.).
const happyResponse = {
  uuid_subscripcion: UUID_SUBSCRIPCION,
  uuid_cliente: UUID_CLIENTE,
  uuid_vehiculos: ['00000000-0000-0000-0000-0000000000e1'],
  uuid_sucursal: UUID_SUCURSAL,
  fecha_inicio_cobertura: '2026-09-19',
  fecha_vencimiento: '2026-10-19',
  valor_total_plan: 30000,
  monto_prorrateado: 11000,
  uuid_factura: UUID_FACTURA,
  uuid_factura_electronica: null,
  uuid_envio_dian: null,
  factura: null,
  factura_electronica_error: null,
};

const inputBase = {
  // BUGFIX (2026-09-25): the wire contract (`VentaSuscripcionCreate.
  // cliente`) has no `nit` field -- `tipo_identificador`/
  // `numero_identificacion` (mirrors the same fix already applied to
  // `Venta.tsx`'s `buildVentaPayload`). This fixture used the stale
  // shape, which `tsc -b` flags as a TS2345 on every `trigger(inputBase)`
  // call below.
  cliente: {
    tipo_identificador: 'NIT' as const,
    numero_identificacion: '900123456',
    nombre: 'ACME',
    email: null,
  },
  placas: ['ABC123'],
  uuid_tipo_subscripcion: UUID_PLAN,
  fecha_inicio_cobertura: '2026-09-19',
  cobrar_ahora: true,
  medio_pago: 'efectivo' as const,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useVentaSuscripcion — REQ-OPS-177 + REQ-OPS-179', () => {
  it('T1: 201 → returns parsed VentaSuscripcionRead with uuid_subscripcion', async () => {
    mockFetch.mockResolvedValueOnce(happyResponse);

    const { result } = renderHook(() => useVentaSuscripcion());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger(inputBase);
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe(
      '/api/v1/clientes/venta-suscripcion',
    );
    expect((data as { uuid_subscripcion: string }).uuid_subscripcion).toBe(
      UUID_SUBSCRIPCION,
    );
    expect(result.current.isMutating).toBe(false);
  });

  it('T2: 422 suscripcion_duplicada_placa → throws VentaSuscripcionDuplicatePlateError', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        422,
        JSON.stringify({
          detail: { error: 'suscripcion_duplicada_placa', placa: 'ABC123' },
        }),
        '/api/v1/clientes/venta-suscripcion',
      ),
    );

    const { result } = renderHook(() => useVentaSuscripcion());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(inputBase);
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(VentaSuscripcionDuplicatePlateError);
    expect((caught as { placa: string }).placa).toBe('ABC123');
    expect((caught as { status: number }).status).toBe(422);
  });

  it('T3: 422 tipo_vehiculo_incompatible → throws VentaSuscripcionTipoIncompatibleError', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        422,
        JSON.stringify({
          detail: {
            error: 'tipo_vehiculo_incompatible',
            tipos_encontrados: ['uuid_tipo_auto', 'uuid_tipo_moto'],
          },
        }),
        '/api/v1/clientes/venta-suscripcion',
      ),
    );

    const { result } = renderHook(() => useVentaSuscripcion());

    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger(inputBase);
      } catch (e) {
        caught = e;
      }
    });

    expect(caught).toBeInstanceOf(VentaSuscripcionTipoIncompatibleError);
    expect((caught as { tipos_encontrados: string[] }).tipos_encontrados).toEqual([
      'uuid_tipo_auto',
      'uuid_tipo_moto',
    ]);
    expect((caught as { status: number }).status).toBe(422);
  });

  it('T4: 401 → useAuthStore.clear() + parkos:auth:cleared event (REQ-OPS-107..110)', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, '{"error":"token_expired"}', '/api/v1/clientes/venta-suscripcion'),
    );

    const { result } = renderHook(() => useVentaSuscripcion());

    await act(async () => {
      await result.current.trigger(inputBase).catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });
});
