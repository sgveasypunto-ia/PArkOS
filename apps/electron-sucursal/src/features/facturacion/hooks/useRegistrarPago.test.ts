/**
 * Tests for `useRegistrarPago` SWR mutation hook (HU-F8.1 + HU-F8.4,
 * REQ-OPS-167).
 *
 * Coverage (4 tests):
 *   P1: trigger → 201 → returns parsed `FacturaRead` with the
 *       enriched 22-field shape (post-HU-F8.4); the parser enforces
 *       the discriminator by `medio_pago` and the new
 *       `uuid_salida` requirement (BE↔FE fix, 2026-09-23).
 *   P2: trigger in-flight → `isMutating=true` observable between the
 *       fetch start and the 201 response.
 *   P3: 401 → `useAuthStore.getState().clear()` + `parkos:auth:cleared`
 *       event (preserved F3.1 invariant; mirrors `useRegistrarSalida`).
 *   P4: doble trigger with same body → SAME Idempotency-Key SHA-256
 *       header on both calls (server-side `IdempotencyKeyMiddleware`
 *       F1.6 dedups the second POST).
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

import { useRegistrarPago } from './useRegistrarPago';
import { useAuthStore } from '@parkos/ui-kit/store';

const UUID_SALIDA = '00000000-0000-0000-0000-0000000000aa';
const UUID_FACTURA = '00000000-0000-0000-0000-0000000000bb';

/**
 * FacturaRead mirror for HU-F8.4 enriched response (22 fields).
 * The mock has the minimum required fields; the display projection
 * fields are omitted where Zod allows nullable.
 */
const facturaEfectivoRead = {
  uuid: UUID_FACTURA,
  uuid_sucursal: '00000000-0000-0000-0000-0000000000a2',
  uuid_ingreso: '00000000-0000-0000-0000-0000000000c1',
  uuid_salida: UUID_SALIDA,
  created_at: '2026-09-19T11:00:00Z',
  subtotal: 41000,
  descuento: 0,
  total: 41000,
  uuid_cliente: null,
  items: [
    {
      uuid: '00000000-0000-0000-0000-0000000000d1',
      tipo: 'servicio',
      concepto: 'Parqueo 1h',
      cantidad: 1,
      valor_unitario: 41000,
      subtotal: 41000,
    },
  ],
  estado: 'emitida',
  medio_pago: 'efectivo',
  monto_recibido_cents: null,
  vuelto_cents: null,
  voucher: null,
  numero_recibo: 'sucursal-20260919-000001',
  cliente: null,
  datos_sucursal: {
    razon_social: 'Parkos Test',
    nit: '900.123.456-7',
    direccion: 'Calle 123',
    ciudad: 'Bogota',
    telefono: '+57 1 2345678',
    horario: 'L-V 8-18',
    regimen: 'comun',
  },
  datos_vehiculo: {
    placa: 'ABC123',
    uuid_tipo_vehiculo: null,
    fecha_ingreso: '2026-09-19T10:00:00Z',
    fecha_salida: '2026-09-19T11:00:00Z',
    minutos: 60,
  },
  impuestos: [
    {
      uuid: '00000000-0000-0000-0000-0000000000e1',
      uuid_impuesto: null,
      nombre_impuesto: 'IVA',
      codigo_impuesto: '01',
      base_calculo: 41000,
      porcentaje_aplicado: 0,
      valor: 0,
    },
  ],
  pagos: [],
  factura_electronica: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

describe('useRegistrarPago — HU-F8.4 (FE consumidor final + Idempotency-Key)', () => {
  it('P1: trigger → 201 → returns parsed FacturaRead with FE consumidor final default', async () => {
    mockFetch.mockResolvedValueOnce(facturaEfectivoRead);

    const { result } = renderHook(() => useRegistrarPago());

    let data: unknown;
    await act(async () => {
      data = await result.current.trigger({
        uuid_salida: UUID_SALIDA,
        medio_pago: 'efectivo',
        items: [{ tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 41000 }],
        subtotal: 34454,
        total: 41000,
      });
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0]?.[0]).toBe('/api/v1/facturacion/factura');
    expect(mockFetch.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
    });
    expect((data as { uuid: string }).uuid).toBe(UUID_FACTURA);
    expect((data as { medio_pago: string }).medio_pago).toBe('efectivo');
    expect((data as { numero_recibo: string }).numero_recibo).toMatch(
      /^sucursal-\d{8}-\d{6}$/,
    );
    expect(result.current.isMutating).toBe(false);
  });

  it('P2: trigger in-flight → isMutating=true observable during the POST', async () => {
    let resolveFn: (v: unknown) => void = () => undefined;
    const pending = new Promise<unknown>((res) => {
      resolveFn = res;
    });
    mockFetch.mockReturnValueOnce(pending);

    const { result } = renderHook(() => useRegistrarPago());

    let triggerPromise: Promise<unknown> = Promise.resolve();
    act(() => {
      triggerPromise = result.current.trigger({
        uuid_salida: UUID_SALIDA,
        medio_pago: 'efectivo',
        items: [{ tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 41000 }],
        subtotal: 34454,
        total: 41000,
      });
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.isMutating).toBe(true);

    await act(async () => {
      resolveFn(facturaEfectivoRead);
      await triggerPromise;
    });
    expect(result.current.isMutating).toBe(false);
  });

  it('P3: 401 → useAuthStore.clear() + parkos:auth:cleared event', async () => {
    const dispatched: string[] = [];
    const origDispatch = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((event: Event) => {
      dispatched.push(event.type);
      origDispatch(event);
    }) as typeof window.dispatchEvent;

    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(401, '{"error":"token_expired"}', '/api/v1/facturacion/factura'),
    );

    const { result } = renderHook(() => useRegistrarPago());

    await act(async () => {
      await result.current
        .trigger({
          uuid_salida: UUID_SALIDA,
          medio_pago: 'efectivo',
          items: [{ tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 41000 }],
          subtotal: 34454,
          total: 41000,
        })
        .catch(() => undefined);
    });

    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
  });

  it('P4: doble trigger with same body → SAME Idempotency-Key header (server dedup)', async () => {
    mockFetch.mockResolvedValue(facturaEfectivoRead);

    const { result } = renderHook(() => useRegistrarPago());

    await act(async () => {
      await result.current.trigger({
        uuid_salida: UUID_SALIDA,
        medio_pago: 'efectivo',
        items: [{ tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 41000 }],
        subtotal: 34454,
        total: 41000,
      });
    });
    await act(async () => {
      await result.current.trigger({
        uuid_salida: UUID_SALIDA,
        medio_pago: 'efectivo',
        items: [{ tipo: 'servicio', concepto: 'Servicio de parqueo', cantidad: 1, valor_unitario: 41000 }],
        subtotal: 34454,
        total: 41000,
      });
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const headers1 = (mockFetch.mock.calls[0]?.[1] as { headers: Record<string, string> }).headers;
    const headers2 = (mockFetch.mock.calls[1]?.[1] as { headers: Record<string, string> }).headers;
    expect(headers1['Idempotency-Key']).toMatch(/^[a-f0-9]{64}$/);
    expect(headers1['Idempotency-Key']).toBe(headers2['Idempotency-Key']);
  });
});