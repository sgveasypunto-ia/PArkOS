/**
 * `clientesApi.test.ts` — renewal client (PT-3), server-computed
 * `puede_renovar`/`dias_restantes` in the subscription schema, and the
 * "Consumidor final" helper.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetchRaw: vi.fn(),
  parkosFetch: vi.fn(),
}));

import { parkosFetchRaw } from '@parkos/ui-kit/fetch';

import {
  ClientesApiError,
  isConsumidorFinal,
  renovacionInputSchema,
  renovarSubscripcion,
  subscripcionClienteSchema,
} from './clientesApi';

const mockedRaw = vi.mocked(parkosFetchRaw);
const UUID = '22222222-2222-4222-8222-222222222222';

function ok(body: unknown, status = 201): Response {
  return { ok: true, status, json: async () => body, text: async () => '' } as Response;
}
function fail(status: number, body: unknown): Response {
  return { ok: false, status, json: async () => body, text: async () => JSON.stringify(body) } as Response;
}

const RESPUESTA = {
  uuid_subscripcion_anterior: UUID,
  uuid_subscripcion: '33333333-3333-4333-8333-333333333333',
  uuid_cliente: '11111111-1111-4111-8111-111111111111',
  uuid_sucursal: '44444444-4444-4444-8444-444444444444',
  uuid_tipo_subscripcion: '55555555-5555-4555-8555-555555555555',
  uuid_vehiculos: ['66666666-6666-4666-8666-666666666666'],
  placas: ['ABC123'],
  fecha_inicio_cobertura: '2026-10-07',
  fecha_vencimiento: '2026-11-05',
  dias_restantes: 30,
  renovacion_anticipada: true,
  ventana_renovacion_dias: 10,
  valor_total_plan: '30000.00',
  total_con_iva: '35700.00',
  uuid_factura: '77777777-7777-4777-8777-777777777777',
  uuid_factura_electronica: null,
  factura_electronica_error: null,
  factura: { numero: 'F-1' },
};

describe('renovarSubscripcion', () => {
  beforeEach(() => mockedRaw.mockReset());

  it('POSTs to /clientes/subscripciones/{uuid}/renovar with the caller Idempotency-Key and no plates', async () => {
    mockedRaw.mockResolvedValue(ok(RESPUESTA));
    const res = await renovarSubscripcion(UUID, { medio_pago: 'efectivo' }, 'key-123');

    expect(res.uuid_subscripcion).toBe(RESPUESTA.uuid_subscripcion);
    expect(res.placas).toEqual(['ABC123']);
    const [url, init] = mockedRaw.mock.calls[0] as [string, Record<string, unknown>];
    expect(url).toBe(`/api/v1/clientes/subscripciones/${UUID}/renovar`);
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('key-123');
    // The shared wrapper must not overwrite the per-attempt key with its body hash.
    expect(init.skipIdempotencyKey).toBe(true);
    expect(JSON.parse(String(init.body))).toEqual({ medio_pago: 'efectivo', referencia: null });
  });

  it('sends the referencia for datáfono and defaults medio_pago to efectivo', async () => {
    mockedRaw.mockResolvedValue(ok(RESPUESTA));
    await renovarSubscripcion(UUID, { medio_pago: 'datafono', referencia: ' V-1 ' }, 'k');
    expect(JSON.parse(String((mockedRaw.mock.calls[0]?.[1] as { body: string }).body))).toEqual({
      medio_pago: 'datafono',
      referencia: 'V-1',
    });

    mockedRaw.mockClear();
    await renovarSubscripcion(UUID, {}, 'k');
    expect(JSON.parse(String((mockedRaw.mock.calls[0]?.[1] as { body: string }).body)).medio_pago).toBe(
      'efectivo',
    );
  });

  it('refuses datáfono without referencia before hitting the network', async () => {
    await expect(renovarSubscripcion(UUID, { medio_pago: 'datafono' }, 'k')).rejects.toThrow();
    expect(mockedRaw).not.toHaveBeenCalled();
  });

  it('surfaces the typed backend error (409 suscripcion_no_renovable)', async () => {
    mockedRaw.mockResolvedValue(
      fail(409, { detail: { error: 'suscripcion_no_renovable', dias_restantes: 25 } }),
    );
    const e = await renovarSubscripcion(UUID, {}, 'k').catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ClientesApiError);
    expect((e as ClientesApiError).status).toBe(409);
    expect((e as ClientesApiError).code).toBe('suscripcion_no_renovable');
    expect((e as ClientesApiError).detail.dias_restantes).toBe(25);
  });
});

describe('renovacionInputSchema', () => {
  it('requires referencia only for datafono', () => {
    expect(renovacionInputSchema.safeParse({ medio_pago: 'tarjeta' }).success).toBe(true);
    expect(renovacionInputSchema.safeParse({ medio_pago: 'datafono', referencia: '' }).success).toBe(false);
    expect(renovacionInputSchema.safeParse({ medio_pago: 'cheque' }).success).toBe(false);
  });
});

describe('subscripcionClienteSchema', () => {
  const base = {
    uuid: UUID,
    uuid_cliente: null,
    uuid_sucursal: null,
    uuid_tipo_subscripcion: null,
    fecha_inicio_cobertura: '2026-10-01',
    fecha_vencimiento: '2026-10-30',
    dias_alerta_pre_vencimiento: 7,
    vigente_desde: '2026-10-01T00:00:00',
    vigente_hasta: null,
    estado: 'activo',
    created_at: '2026-10-01T00:00:00',
    created_by: null,
    sync_status: null,
  };

  it('parses the server-computed dias_restantes / puede_renovar', () => {
    const r = subscripcionClienteSchema.parse({ ...base, dias_restantes: 4, puede_renovar: true });
    expect(r.dias_restantes).toBe(4);
    expect(r.puede_renovar).toBe(true);
  });

  it('still parses rows from a server that does not send them', () => {
    expect(subscripcionClienteSchema.parse(base).puede_renovar).toBeUndefined();
  });
});

describe('isConsumidorFinal', () => {
  it('matches the standard billing client by its identification number', () => {
    expect(isConsumidorFinal({ numero_identificacion: '222222222222' })).toBe(true);
    expect(isConsumidorFinal({ numero_identificacion: ' 222222222222 ' })).toBe(true);
    expect(isConsumidorFinal({ numero_identificacion: '1000000001' })).toBe(false);
    expect(isConsumidorFinal({ numero_identificacion: null })).toBe(false);
  });
});
