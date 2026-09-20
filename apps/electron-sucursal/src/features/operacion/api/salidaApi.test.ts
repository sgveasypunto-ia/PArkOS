/**
 * Unit tests for `salidaApi.ts` Zod mirror (HU-F7.2, REQ-OPS-154).
 *
 * Coverage:
 *   S1: Zod round-trip — canonical `SalidaReadForzado` rotación payload
 *       parses cleanly (shape mirrors F1.7 backend Pydantic at
 *       `backend/.../schemas/operacion.py:392-422`).
 *
 * The HTTP transport is exercised by `parkosFetch`'s own test suite;
 * here we only assert Zod validation against the canonical wire
 * shape. Mirrors `ingresoActivoApi.test.ts` precedent (F6.1).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@parkos/ui-kit/fetch', () => ({
  parkosFetch: vi.fn(),
}));

import { parkosFetch } from '@parkos/ui-kit/fetch';

import { SalidaReadForzadoSchema } from './salidaApi';

const mockFetch = parkosFetch as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});

describe('SalidaReadForzadoSchema — F1.7 wire shape mirror', () => {
  it('S1: rotación canonical payload parses cleanly', () => {
    const wire = {
      uuid: '00000000-0000-0000-0000-0000000000a1',
      uuid_sucursal: '00000000-0000-0000-0000-0000000000a2',
      uuid_ingreso: '00000000-0000-0000-0000-0000000000a3',
      fecha_salida: '2026-09-19T11:00:00Z',
      created_at: '2026-09-19T11:00:00Z',
      created_by: '00000000-0000-0000-0000-0000000000a4',
      sync_status: 'pending',
      sync_timestamp: null,
      sync_attempts: 0,
      tipo_salida: 'ROTACION',
      forzado_en_creacion: false,
      motivo_forzado: null,
      cotizacion_snapshot: {
        cobrar: true,
        subtotal: 41000,
        iva: 7790,
        total: 48790,
        tiempo_minutos: 32.5,
        tarifa_uuid: '00000000-0000-0000-0000-0000000000a5',
        vigente_hasta: '2026-09-19T11:15:00Z',
      },
    };
    const parsed = SalidaReadForzadoSchema.parse(wire);
    expect(parsed.uuid).toBe(wire.uuid);
    expect(parsed.tipo_salida).toBe('ROTACION');
    if (parsed.tipo_salida === 'ROTACION') {
      expect(parsed.cotizacion_snapshot).toBeDefined();
      expect(parsed.cotizacion_snapshot?.total).toBe(48790);
    }
  });
});