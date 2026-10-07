import { describe, expect, it } from 'vitest';

import { buildEnvioDianCounts } from './envioDianCounts';
import { ENVIO_DIAN_ESTADOS, type EnvioDianRead } from '../api/envioDianSchema';

function envio(overrides: Partial<EnvioDianRead> = {}): EnvioDianRead {
  return {
    uuid: '11111111-1111-1111-1111-111111111111',
    created_at: '2026-09-01T08:00:00',
    created_by: null,
    sync_status: null,
    sync_timestamp: null,
    sync_attempts: null,
    uuid_sucursal: '22222222-2222-2222-2222-222222222222',
    uuid_factura_electronica: '33333333-3333-3333-3333-333333333333',
    uuid_resolucion_facturacion: null,
    payload: null,
    respuesta_proveedor: null,
    cufe: null,
    uuid_envio_padre: null,
    timestamp_evento: '2026-09-01T08:00:00',
    vigente_desde: '2026-09-01T08:00:00',
    vigente_hasta: null,
    estado: 'pendiente',
    ...overrides,
  };
}

describe('buildEnvioDianCounts', () => {
  it('returns zero for every known estado on an empty list', () => {
    const counts = buildEnvioDianCounts([]);
    for (const estado of ENVIO_DIAN_ESTADOS) {
      expect(counts[estado]).toBe(0);
    }
  });

  it('tallies items by estado', () => {
    const items = [
      envio({ uuid: 'a', estado: 'rechazado' }),
      envio({ uuid: 'b', estado: 'rechazado' }),
      envio({ uuid: 'c', estado: 'pendiente' }),
      envio({ uuid: 'd', estado: 'aceptado' }),
    ];
    const counts = buildEnvioDianCounts(items);
    expect(counts.rechazado).toBe(2);
    expect(counts.pendiente).toBe(1);
    expect(counts.aceptado).toBe(1);
    expect(counts.enviado).toBe(0);
    expect(counts.ack).toBe(0);
    expect(counts.error).toBe(0);
    expect(counts.timeout).toBe(0);
    expect(counts.en_proceso).toBe(0);
  });

  it("counts the dispatcher's in-flight 'activo' rows as en_proceso", () => {
    // envio_dian is append-only: a dispatch in flight is a row with
    // estado 'activo' (not yet submitted) or 'en_proceso'; both are "in progress".
    const counts = buildEnvioDianCounts([
      envio({ uuid: 'a', estado: 'activo' }),
      envio({ uuid: 'b', estado: 'en_proceso' }),
      envio({ uuid: 'c', estado: 'timeout' }),
    ]);
    expect(counts.en_proceso).toBe(2);
    expect(counts.timeout).toBe(1);
    const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
    expect(total).toBe(3);
  });

  it('ignores a null or unknown estado defensively instead of throwing', () => {
    const items = [
      envio({ uuid: 'a', estado: null }),
      envio({ uuid: 'b', estado: 'algo_no_documentado' }),
      envio({ uuid: 'c', estado: 'enviado' }),
    ];
    const counts = buildEnvioDianCounts(items);
    expect(counts.enviado).toBe(1);
    const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
    expect(total).toBe(1);
  });
});
