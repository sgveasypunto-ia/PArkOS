/**
 * `reclamosSchema.test.ts` — HU-F20.3 wire-contract tests. Mirrors
 * `anulacionesSchema.test.ts`.
 *
 *  - T1: a full row parses (no `fecha_retencion_hasta`/`uuid_usuario`,
 *    unlike anulacion -- see `reclamosSchema.ts`'s docblock).
 *  - T2: the list envelope parses.
 *  - T3: an unknown `estado` value is rejected.
 *  - T4: an unknown `tipo_reclamable` (e.g. the non-existent
 *    `subscripcion`) is rejected -- exactly 3 real values.
 *  - T5: `RECLAMO_TRANSICIONES` only offers the contract's legal
 *    destinations per tip state.
 */
import { describe, expect, it } from 'vitest';

import { RECLAMO_TRANSICIONES, reclamoReadSchema, reclamosListResponseSchema } from './reclamosSchema';

function baseWire(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    uuid: '11111111-1111-1111-1111-111111111111',
    created_at: '2026-09-01T00:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    tipo_reclamable: 'ingreso',
    uuid_reclamable: '33333333-3333-3333-3333-333333333333',
    motivo: 'Cobro duplicado',
    uuid_reclamo_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'recibido',
    ...overrides,
  };
}

describe('reclamosSchema', () => {
  it('T1: parses a full row (no fecha_retencion_hasta / uuid_usuario fields)', () => {
    const parsed = reclamoReadSchema.parse(baseWire());
    expect(parsed.estado).toBe('recibido');
    expect(parsed.tipo_reclamable).toBe('ingreso');
    expect('fecha_retencion_hasta' in parsed).toBe(false);
    expect('uuid_usuario' in parsed).toBe(false);
  });

  it('T2: parses the cursor-paginated list envelope', () => {
    const parsed = reclamosListResponseSchema.parse({
      items: [baseWire({ estado: 'en_investigacion' })],
      next_cursor: null,
    });
    expect(parsed.items).toHaveLength(1);
    expect(parsed.next_cursor).toBeNull();
  });

  it('T3: rejects a stale/unknown estado value (e.g. plan.md\'s "abierto")', () => {
    expect(() => reclamoReadSchema.parse(baseWire({ estado: 'abierto' }))).toThrow();
  });

  it('T4: rejects the non-existent "subscripcion" tipo_reclamable', () => {
    expect(() => reclamoReadSchema.parse(baseWire({ tipo_reclamable: 'subscripcion' }))).toThrow();
  });

  it('T5: RECLAMO_TRANSICIONES only offers the real contract destinations', () => {
    expect(RECLAMO_TRANSICIONES.recibido).toEqual(['en_investigacion']);
    expect(RECLAMO_TRANSICIONES.en_investigacion).toEqual(['resuelto', 'rechazado']);
    expect(RECLAMO_TRANSICIONES.resuelto).toEqual([]);
    expect(RECLAMO_TRANSICIONES.rechazado).toEqual([]);
  });
});
