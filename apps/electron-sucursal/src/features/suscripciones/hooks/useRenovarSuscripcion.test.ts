/**
 * `useRenovarSuscripcion.test.ts` — renewal mutation hook (PT-3).
 *
 *   T1: 201 -> parsed response; POST to /clientes/subscripciones/{uuid}/renovar
 *       with the body {medio_pago, referencia} and an Idempotency-Key.
 *   T2: the SAME attempt id yields the SAME key (retry = replay); a NEW attempt
 *       id yields a new key (and `skipIdempotencyKey` protects it).
 *   T3: datafono without voucher is rejected BEFORE the network.
 *   T4: every documented error code maps to a typed `RenovacionError`
 *       (the retired renovacion_fuera_de_ventana falls back to the generic message).
 *   T5: 401 -> auth cleared + event.
 *   T6: 5xx keeps the attempt open (`esDefinitivo` false), 4xx closes it.
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

import { useAuthStore } from '@parkos/ui-kit/store';

import { RenovacionError, renovacionErrorMessage } from './renovacionErrors';
import { useRenovarSuscripcion } from './useRenovarSuscripcion';

const UUID_SUB = '00000000-0000-0000-0000-0000000000a1';
const ID = (n: number): string => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;

const FACTURA = {
  uuid: ID(50),
  created_at: '2026-10-06T10:00:00Z',
  uuid_sucursal: ID(2),
  uuid_ingreso: null,
  uuid_salida: null,
  subtotal: '800000.00',
  descuento: '0.00',
  total: '952000.00',
  uuid_cliente: ID(3),
  items: [],
  estado: 'pagada',
  medio_pago: 'efectivo',
  monto_recibido_cents: null,
  vuelto_cents: null,
  voucher: null,
  numero_recibo: 'suc-20261006-000001',
  cliente: null,
  datos_sucursal: {
    razon_social: 'Sede',
    nit: null,
    direccion: null,
    ciudad: null,
    telefono: null,
    horario: null,
    regimen: null,
  },
  datos_vehiculo: null,
  impuestos: [],
  pagos: [],
  factura_electronica: null,
  factura_electronica_error: 'numeracion_agotada',
  factura_electronica_pendiente: true,
};

const RESPUESTA = {
  uuid_subscripcion_anterior: UUID_SUB,
  uuid_subscripcion: ID(60),
  uuid_cliente: ID(3),
  uuid_sucursal: ID(2),
  uuid_tipo_subscripcion: ID(4),
  uuid_vehiculos: [ID(5)],
  placas: ['ABC123'],
  fecha_inicio_cobertura: '2026-10-08',
  fecha_vencimiento: '2026-11-07',
  dias_restantes: 32,
  renovacion_anticipada: true,
  ventana_renovacion_dias: 10,
  valor_total_plan: '800000.00',
  total_con_iva: '952000.00',
  uuid_factura: ID(50),
  uuid_factura_electronica: null,
  factura_electronica_error: 'numeracion_agotada',
  factura_electronica_pendiente: true,
  factura: FACTURA,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetch.mockReset();
});

const headersOf = (i: number): Record<string, string> =>
  (mockFetch.mock.calls[i]?.[1] as { headers: Record<string, string> }).headers;

describe('useRenovarSuscripcion — PT-3', () => {
  it('T1: 201 -> parsed response; correct path, body and Idempotency-Key', async () => {
    mockFetch.mockResolvedValueOnce(RESPUESTA);
    const { result } = renderHook(() => useRenovarSuscripcion());

    let data: Awaited<ReturnType<typeof result.current.trigger>> | undefined;
    await act(async () => {
      data = await result.current.trigger({
        uuid_subscripcion: UUID_SUB,
        medio_pago: 'efectivo',
        referencia: null,
        intentoId: 'intento-1',
      });
    });

    expect(mockFetch.mock.calls[0]?.[0]).toBe(
      `/api/v1/clientes/subscripciones/${UUID_SUB}/renovar`,
    );
    const init = mockFetch.mock.calls[0]?.[1] as { method: string; body: string };
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ medio_pago: 'efectivo', referencia: null });
    expect(headersOf(0)['Idempotency-Key']).toMatch(/^[0-9a-f]{64}$/);
    // Decimal strings are coerced; FE pending flag survives.
    expect(data?.total_con_iva).toBe(952000);
    expect(data?.factura?.factura_electronica_pendiente).toBe(true);
    expect(data?.factura_electronica_error).toBe('numeracion_agotada');
  });

  it('T2: same attempt id -> same key; new attempt id -> new key', async () => {
    mockFetch.mockResolvedValue(RESPUESTA);
    const { result } = renderHook(() => useRenovarSuscripcion());
    const base = { uuid_subscripcion: UUID_SUB, medio_pago: 'efectivo' as const, referencia: null };
    await act(async () => {
      await result.current.trigger({ ...base, intentoId: 'A' });
    });
    await act(async () => {
      await result.current.trigger({ ...base, intentoId: 'A' });
    });
    await act(async () => {
      await result.current.trigger({ ...base, intentoId: 'B' });
    });
    expect(headersOf(0)['Idempotency-Key']).toBe(headersOf(1)['Idempotency-Key']);
    expect(headersOf(2)['Idempotency-Key']).not.toBe(headersOf(0)['Idempotency-Key']);
    expect((mockFetch.mock.calls[0]?.[1] as { skipIdempotencyKey?: boolean }).skipIdempotencyKey).toBe(
      true,
    );
  });

  it('T3: datafono without voucher is rejected before the network', async () => {
    const { result } = renderHook(() => useRenovarSuscripcion());
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger({
          uuid_subscripcion: UUID_SUB,
          medio_pago: 'datafono',
          referencia: null,
          intentoId: 'A',
        });
      } catch (e) {
        caught = e;
      }
    });
    expect(caught).toBeDefined();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('T3b: datafono with voucher sends it as `referencia`', async () => {
    mockFetch.mockResolvedValueOnce(RESPUESTA);
    const { result } = renderHook(() => useRenovarSuscripcion());
    await act(async () => {
      await result.current.trigger({
        uuid_subscripcion: UUID_SUB,
        medio_pago: 'datafono',
        referencia: 'V-123',
        intentoId: 'A',
      });
    });
    const init = mockFetch.mock.calls[0]?.[1] as { body: string };
    expect(JSON.parse(init.body)).toEqual({ medio_pago: 'datafono', referencia: 'V-123' });
  });

  const CASES: Array<[number, string]> = [
    [400, 'idempotency_key_requerido'],
    [400, 'voucher_requerido'],
    [400, 'missing_sucursal_context'],
    [403, 'permission_denied'],
    [404, 'subscripcion_no_encontrada'],
    [409, 'suscripcion_no_renovable'],
    [409, 'plan_no_vigente'],
    [409, 'idempotency_key_conflict'],
    [422, 'placa_con_suscripcion_vigente'],
    [422, 'suscripcion_sin_vehiculos'],
    [422, 'vehiculo_no_resuelto'],
    [422, 'cantidad_maxima_excedida'],
    [422, 'tipo_vehiculo_incompatible'],
    [422, 'plan_duracion_dias_invalido'],
    [422, 'voucher_datafono_duplicado'],
    [500, 'iva_no_configurado'],
  ];

  it.each(CASES)('T4: %i %s -> typed RenovacionError with a Spanish message', async (status, code) => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        status,
        JSON.stringify({
          detail: { error: code, dias_restantes: 25, ventana_dias: 10, placa: 'ABC123' },
        }),
        'x',
      ),
    );
    const { result } = renderHook(() => useRenovarSuscripcion());
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger({
          uuid_subscripcion: UUID_SUB,
          medio_pago: 'efectivo',
          referencia: null,
          intentoId: 'A',
        });
      } catch (e) {
        caught = e;
      }
    });
    expect(caught).toBeInstanceOf(RenovacionError);
    expect((caught as RenovacionError).code).toBe(code);
    const msg = renovacionErrorMessage(caught, (_k, o) => String(o?.defaultValue ?? _k));
    expect(msg.length).toBeGreaterThan(10);
    expect(msg).not.toContain(code);
  });

  it('T4b: the retired renovacion_fuera_de_ventana code maps to the generic message', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(
        409,
        JSON.stringify({
          detail: { error: 'renovacion_fuera_de_ventana', dias_restantes: 25, ventana_dias: 10 },
        }),
        'x',
      ),
    );
    const { result } = renderHook(() => useRenovarSuscripcion());
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.trigger({
          uuid_subscripcion: UUID_SUB,
          medio_pago: 'efectivo',
          referencia: null,
          intentoId: 'A',
        });
      } catch (e) {
        caught = e;
      }
    });
    const err = caught as RenovacionError;
    expect(err.code).toBe('desconocido');
    expect(renovacionErrorMessage(err, (_k, o) => String(o?.defaultValue ?? _k))).not.toContain(
      'Todavía no se puede renovar',
    );
  });

  it('T5: 401 -> auth cleared + parkos:auth:cleared', async () => {
    const dispatched: string[] = [];
    const orig = window.dispatchEvent.bind(window);
    window.dispatchEvent = ((e: Event) => {
      dispatched.push(e.type);
      return orig(e);
    }) as typeof window.dispatchEvent;
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(new ParkosHttpError(401, '{}', 'x'));
    const { result } = renderHook(() => useRenovarSuscripcion());
    await act(async () => {
      await result
        .current.trigger({
          uuid_subscripcion: UUID_SUB,
          medio_pago: 'efectivo',
          referencia: null,
          intentoId: 'A',
        })
        .catch(() => undefined);
    });
    expect(useAuthStore.getState().clear).toHaveBeenCalledTimes(1);
    expect(dispatched).toContain('parkos:auth:cleared');
    window.dispatchEvent = orig;
  });

  it('T6: 4xx is definitive for the attempt; a generic 5xx is rethrown as transport error', async () => {
    const { ParkosHttpError } = await import('@parkos/ui-kit/fetch');
    mockFetch.mockRejectedValueOnce(
      new ParkosHttpError(409, JSON.stringify({ detail: { error: 'plan_no_vigente' } }), 'x'),
    );
    mockFetch.mockRejectedValueOnce(new ParkosHttpError(503, 'unavailable', 'x'));
    const { result } = renderHook(() => useRenovarSuscripcion());
    const args = {
      uuid_subscripcion: UUID_SUB,
      medio_pago: 'efectivo' as const,
      referencia: null,
      intentoId: 'A',
    };
    let first: unknown;
    let second: unknown;
    await act(async () => {
      first = await result.current.trigger(args).catch((e: unknown) => e);
    });
    await act(async () => {
      second = await result.current.trigger(args).catch((e: unknown) => e);
    });
    expect((first as RenovacionError).esDefinitivo).toBe(true);
    expect(second).not.toBeInstanceOf(RenovacionError);
    expect((second as { status: number }).status).toBe(503);
  });
});
