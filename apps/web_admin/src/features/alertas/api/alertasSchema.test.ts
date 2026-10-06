/**
 * `alertasSchema.test.ts` — HU-F19.5 wire-contract tests.
 *
 *  - T1: a full list item (severity carried, non-null) parses.
 *  - T2: BR4 — `severity: null` parses (no `alert_types` row for `tipo_alerta`).
 *  - T3: the list envelope (`{items, next_cursor}`) parses.
 *  - T4: the detail read (no `severity` field at all on the wire) parses
 *    via `alertaDetailReadSchema`.
 *  - T5: an unknown `estado` value is rejected (closed enum).
 */
import { describe, expect, it } from 'vitest';

import {
  alertaDetailReadSchema,
  alertaReadSchema,
  alertasListResponseSchema,
} from './alertasSchema';

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
    uuid_usuario: '33333333-3333-3333-3333-333333333333',
    uuid_arqueo: null,
    tipo_alerta: 'descuadre_critico',
    valor_diferencia_efectivo: '1500.00',
    valor_diferencia_datafono: '0.00',
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'abierta',
    ...overrides,
  };
}

describe('alertasSchema', () => {
  it('T1: parses a list item with a non-null severity', () => {
    const parsed = alertaReadSchema.parse(baseWire({ severity: 'critical' }));
    expect(parsed.severity).toBe('critical');
    expect(parsed.estado).toBe('abierta');
  });

  it('T2 (BR4): parses severity: null (tipo_alerta has no alert_types row)', () => {
    const parsed = alertaReadSchema.parse(baseWire({ severity: null }));
    expect(parsed.severity).toBeNull();
  });

  it('T3: parses the cursor-paginated list envelope', () => {
    const parsed = alertasListResponseSchema.parse({
      items: [baseWire({ severity: 'warning' })],
      next_cursor: null,
    });
    expect(parsed.items).toHaveLength(1);
    expect(parsed.next_cursor).toBeNull();
  });

  it('T4: parses the single-item detail read with severity absent entirely', () => {
    const wire = baseWire();
    delete (wire as { severity?: unknown }).severity;
    const parsed = alertaDetailReadSchema.parse(wire);
    expect(parsed.severity).toBeUndefined();
  });

  it('T6: reads legacy `estado: "activo"` rows as `abierta` instead of failing the inbox', () => {
    const parsed = alertasListResponseSchema.parse({
      items: [baseWire({ estado: 'activo', severity: 'critical' })],
      next_cursor: null,
    });
    expect(parsed.items[0]?.estado).toBe('abierta');
  });

  it('T7: parses an item without `valor_diferencia_datafono` (cash-only backend)', () => {
    const wire = baseWire({ severity: 'critical' });
    delete wire.valor_diferencia_datafono;
    const parsed = alertaReadSchema.parse(wire);
    expect(parsed.valor_diferencia_datafono).toBeUndefined();
  });

  it('T5: rejects an unknown estado value', () => {
    expect(() => alertaReadSchema.parse(baseWire({ severity: null, estado: 'cancelada' }))).toThrow();
  });
});
