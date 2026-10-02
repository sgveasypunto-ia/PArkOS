/**
 * `anulacionesSchema.test.ts` — HU-F20.3 wire-contract tests.
 *
 *  - T1: a full row parses.
 *  - T2: the list envelope (`{items, next_cursor}`) parses.
 *  - T3: an unknown `estado` value is rejected (closed enum -- the real
 *    names, NOT `plan.md`'s stale `solicitada/aprobada/ejecutada`).
 *  - T4: `ANULACION_TRANSICIONES` only offers the contract's legal
 *    destinations per tip state.
 */
import { describe, expect, it } from 'vitest';

import {
  ANULACION_TRANSICIONES,
  anulacionReadSchema,
  anulacionesListResponseSchema,
} from './anulacionesSchema';

function baseWire(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    uuid: '11111111-1111-1111-1111-111111111111',
    fecha_retencion_hasta: '2027-09-01',
    created_at: '2026-09-01T00:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    tipo_anulable: 'ingreso',
    uuid_ingreso: '33333333-3333-3333-3333-333333333333',
    uuid_salida: null,
    uuid_usuario: '44444444-4444-4444-4444-444444444444',
    motivo: 'Placa duplicada',
    uuid_anulacion_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'iniciada',
    ...overrides,
  };
}

describe('anulacionesSchema', () => {
  it('T1: parses a full row', () => {
    const parsed = anulacionReadSchema.parse(baseWire());
    expect(parsed.estado).toBe('iniciada');
    expect(parsed.tipo_anulable).toBe('ingreso');
    expect(parsed.motivo).toBe('Placa duplicada');
  });

  it('T2: parses the cursor-paginated list envelope', () => {
    const parsed = anulacionesListResponseSchema.parse({
      items: [baseWire({ estado: 'autorizada' })],
      next_cursor: null,
    });
    expect(parsed.items).toHaveLength(1);
    expect(parsed.next_cursor).toBeNull();
  });

  it('T3: rejects a stale/unknown estado value (e.g. plan.md\'s "solicitada")', () => {
    expect(() => anulacionReadSchema.parse(baseWire({ estado: 'solicitada' }))).toThrow();
  });

  it('T4: ANULACION_TRANSICIONES only offers the real contract destinations', () => {
    expect(ANULACION_TRANSICIONES.iniciada).toEqual(['autorizada', 'rechazada']);
    expect(ANULACION_TRANSICIONES.autorizada).toEqual(['ejecutada', 'rechazada']);
    expect(ANULACION_TRANSICIONES.ejecutada).toEqual([]);
    expect(ANULACION_TRANSICIONES.rechazada).toEqual([]);
  });
});
