/**
 * `groupAlertas.test.ts` -- BR3 grouping contract.
 *
 *  - T1: a unique tuple yields a single-item group.
 *  - T2: a repeated `(tipo_alerta, uuid_sucursal, día)` tuple groups its
 *    rows together, in first-seen order.
 *  - T3: grouping NEVER drops rows -- flattening every group's `items`
 *    reproduces the original array length (and, item-for-item, its
 *    uuids) regardless of grouping.
 *  - T4: a different `día` (derived from `timestamp_evento`) keeps two
 *    otherwise-identical tuples in separate groups.
 */
import { describe, expect, it } from 'vitest';

import { buildAlertaGroups, diaOf } from './groupAlertas';
import type { AlertaRead } from '../api/alertasSchema';

function alerta(overrides: Partial<AlertaRead>): AlertaRead {
  return {
    uuid: '11111111-1111-1111-1111-111111111111',
    fecha_retencion_hasta: '2027-09-01',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    uuid_usuario: null,
    uuid_arqueo: null,
    tipo_alerta: 'descuadre_critico',
    valor_diferencia_efectivo: null,
    valor_diferencia_datafono: null,
    uuid_alerta_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'abierta',
    severity: 'critical',
    ...overrides,
  };
}

describe('buildAlertaGroups', () => {
  it('T1: a unique tuple yields one group with a single item', () => {
    const items = [alerta({ uuid: 'a' }), alerta({ uuid: 'b', tipo_alerta: 'otro_tipo' })];
    const groups = buildAlertaGroups(items);
    expect(groups).toHaveLength(2);
    expect(groups[0]!.items).toHaveLength(1);
    expect(groups[1]!.items).toHaveLength(1);
  });

  it('T2: a repeated tuple groups rows together, first-seen order', () => {
    const items = [
      alerta({ uuid: 'a' }),
      alerta({ uuid: 'other-tuple', tipo_alerta: 'otro_tipo' }),
      alerta({ uuid: 'b' }), // same (tipo_alerta, uuid_sucursal, día) as 'a'
    ];
    const groups = buildAlertaGroups(items);
    expect(groups).toHaveLength(2);
    expect(groups[0]!.items.map((i) => i.uuid)).toEqual(['a', 'b']);
    expect(groups[1]!.items.map((i) => i.uuid)).toEqual(['other-tuple']);
  });

  it('T3: never drops rows -- flattening reproduces the original set', () => {
    const items = [
      alerta({ uuid: 'a' }),
      alerta({ uuid: 'b' }),
      alerta({ uuid: 'c', tipo_alerta: 'otro_tipo' }),
      alerta({ uuid: 'd' }),
    ];
    const groups = buildAlertaGroups(items);
    const flattened = groups.flatMap((g) => g.items).map((i) => i.uuid);
    expect(flattened.sort()).toEqual(items.map((i) => i.uuid).sort());
    expect(flattened).toHaveLength(items.length);
  });

  it('T4: a different día keeps otherwise-identical tuples apart', () => {
    const items = [
      alerta({ uuid: 'a', timestamp_evento: '2026-09-01T08:00:00' }),
      alerta({ uuid: 'b', timestamp_evento: '2026-09-02T08:00:00' }),
    ];
    const groups = buildAlertaGroups(items);
    expect(groups).toHaveLength(2);
  });

  it('diaOf falls back to created_at when timestamp_evento is null', () => {
    const item = alerta({ timestamp_evento: null, created_at: '2026-09-05T10:00:00' });
    expect(diaOf(item)).toBe('2026-09-05');
  });
});
