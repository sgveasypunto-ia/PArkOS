/**
 * `facturacionAdminApi.test.ts` — unit tests for the HU-X API client.
 *
 * Pure unit tests (no DB, no MSW). The 4 scenarios mirror the wire
 * drift cases the schema is designed to catch:
 *
 *   1. `fetchFacturaByUuid` parses BE response (Decimal as string).
 *   2. `fetchFacturaPagos` adds `?uuid_factura=...` to the query.
 *   3. `fetchFacturaElectronicaByUuid` throws `FacturacionHttpError` on 404.
 *   4. `findHashForFactura` matches the right `uuid_referencia` from a list.
 *
 * Mocks `parkosFetchRaw` (from `@/lib/fetch`) so the test stays
 * synchronous on the network and we can exercise both the happy path
 * and the 404 path deterministically.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('@/lib/fetch', () => ({
  parkosFetchRaw: vi.fn(),
  ParkosHttpError: class ParkosHttpError extends Error {
    readonly status: number;
    constructor(status: number, message?: string) {
      super(message ?? `ParkosHttpError: ${status}`);
      this.status = status;
    }
  },
}));

import { parkosFetchRaw } from '@/lib/fetch';
import {
  FacturacionHttpError,
  fetchFacturaByUuid,
  fetchFacturaDetalle,
  fetchFacturaElectronicaByUuid,
  fetchFacturaImpuestos,
  fetchFacturaPagos,
  fetchFacturaHash,
  findHashForFactura,
} from './facturacionAdminApi';

const mockedFetch = vi.mocked(parkosFetchRaw);

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function err(status: number, bodyText: string): Response {
  return new Response(bodyText, { status });
}

beforeEach(() => {
  mockedFetch.mockReset();
});

describe('facturacionAdminApi', () => {
  it('fetchFacturaByUuid parses BE response (Decimal as string)', async () => {
    const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    mockedFetch.mockResolvedValueOnce(
      ok({
        uuid: UUID,
        created_at: '2026-10-13T00:27:57.610779',
        created_by: '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6',
        sync_status: null,
        sync_timestamp: null,
        sync_attempts: null,
        fecha_retencion_hasta: '2026-10-13',
        uuid_sucursal: '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6',
        uuid_ingreso: '923a9426-98d2-4143-93e4-5317ce21b3a1',
        uuid_salida: 'e15c3918-0e1f-4a47-b127-6938c1298a79',
        subtotal: '5000.0000', // BE serializes Decimal as string (Bug 23).
        descuento: '0',
        total: '5000.0000',
      }),
    );
    const data = await fetchFacturaByUuid(UUID);
    expect(data.uuid).toBe(UUID);
    expect(data.subtotal).toBe(5000);
    expect(data.descuento).toBe(0);
    expect(data.total).toBe(5000);
    expect(data.uuid_ingreso).toBe('923a9426-98d2-4143-93e4-5317ce21b3a1');
  });

  it('fetchFacturaPagos adds ?uuid_factura=... to the query', async () => {
    const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    mockedFetch.mockResolvedValueOnce(
      ok({
        items: [
          {
            uuid: '11111111-1111-1111-1111-111111111111',
            created_at: '2026-10-13T00:27:57.610779',
            created_by: '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6',
            sync_status: null,
            sync_timestamp: null,
            sync_attempts: null,
            fecha_retencion_hasta: '2026-10-13',
            uuid_sucursal: '2049f2cd-b2a8-4e45-9d19-31fa87eb67c6',
            uuid_factura: UUID,
            uuid_sesion: 'fc67e1c5-8e08-41c0-8a52-796c4813e62b',
            medio_pago: 'efectivo',
            valor: '5000.0000',
            referencia: null,
            tipo_movimiento: 'pago',
            uuid_pago_revertido: null,
            timestamp_evento: '2026-10-13T00:27:57.610779',
          },
        ],
        next_cursor: null,
      }),
    );
    const data = await fetchFacturaPagos(UUID);
    expect(data.items).toHaveLength(1);
    expect(data.items[0].uuid_factura).toBe(UUID);
    expect(data.items[0].valor).toBe(5000);
    // Verify the URL the client sent.
    const calledUrl = mockedFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain(`uuid_factura=${UUID}`);
  });

  it('fetchFacturaDetalle and fetchFacturaImpuestos use the right URL', async () => {
    const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    mockedFetch.mockResolvedValueOnce(ok({ items: [], next_cursor: null }));
    await fetchFacturaDetalle(UUID);
    expect((mockedFetch.mock.calls[0][0] as string)).toContain(
      `/factura-detalle?uuid_factura=${UUID}`,
    );
    mockedFetch.mockResolvedValueOnce(ok({ items: [], next_cursor: null }));
    await fetchFacturaImpuestos(UUID);
    expect((mockedFetch.mock.calls[1][0] as string)).toContain(
      `/factura-impuestos?uuid_factura=${UUID}`,
    );
  });

  it('fetchFacturaElectronicaByUuid throws FacturacionHttpError on 404', async () => {
    const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    mockedFetch.mockResolvedValueOnce(
      err(404, '{"detail":{"error":"factura_electronica_no_encontrada"}}'),
    );
    let caught: unknown;
    try {
      await fetchFacturaElectronicaByUuid(UUID);
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(FacturacionHttpError);
    expect((caught as FacturacionHttpError).status).toBe(404);
  });

  it('fetchFacturaHash queries /admin/log-transaccional with limit=20', async () => {
    const UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    mockedFetch.mockResolvedValueOnce(ok({ items: [], next_cursor: null }));
    await fetchFacturaHash(UUID);
    const calledUrl = mockedFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/admin/log-transaccional');
    expect(calledUrl).toContain('tabla_afectada=factura');
    expect(calledUrl).toContain('limit=20');
  });

  it('findHashForFactura matches the right uuid_referencia', () => {
    const FACTURA_UUID = 'd8c22ebb-948e-4745-aaa1-52e0a698124a';
    const OTHER_UUID = '11111111-1111-1111-1111-111111111111';
    const list = {
      items: [
        {
          uuid: '22222222-2222-2222-2222-222222222222',
          timestamp_evento: '2026-10-13T00:30:00',
          uuid_usuario: null,
          uuid_sucursal: null,
          uuid_referencia: OTHER_UUID,
          accion: 'login',
          tabla_afectada: 'login',
          hash_anterior: null,
          hash_actual: 'aaaa',
        },
        {
          uuid: '33333333-3333-3333-3333-333333333333',
          timestamp_evento: '2026-10-13T00:27:57',
          uuid_usuario: null,
          uuid_sucursal: null,
          uuid_referencia: FACTURA_UUID,
          accion: 'crear',
          tabla_afectada: 'facturas',
          hash_anterior: null,
          hash_actual: 'bbbb-this-is-the-hash-we-want',
        },
      ],
      next_cursor: null,
    };
    expect(findHashForFactura(FACTURA_UUID, list)).toBe(
      'bbbb-this-is-the-hash-we-want',
    );
    expect(findHashForFactura('non-existent', list)).toBeNull();
  });
});
