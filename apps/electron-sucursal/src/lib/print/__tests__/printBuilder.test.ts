/**
 * Unit tests for `printBuilder.ts::buildEntradaPayloadFromResponse()`.
 *
 * BUGFIX (found while wiring the "Tipo: ROTACIÓN/MENSUALIDAD" ticket
 * field, operator request): `esMensualidad` used to be derived from a
 * `cliente !== null` parameter, but both production call sites
 * (`IngresoPanel.tsx` / `Principal.tsx`) ALWAYS passed `cliente=null`
 * ("cliente metadata not threaded into ESC/POS payload yet" — a
 * separate, unfinished feature). The printed tiquete therefore NEVER
 * showed "MENSUALIDAD" in production, regardless of the vehicle's
 * actual subscription. The fix reads `response.tipo_entrada` (the
 * server-derived, authoritative DEC-SUC-21 field) instead; the dead
 * `cliente` parameter was removed from the signature entirely.
 */
import { describe, it, expect } from 'vitest';

import { buildEntradaPayloadFromResponse } from '../printBuilder';
import type { PostIngresoResponse } from '../../../features/operacion/lib/ingresoApi';

function makeResponse(overrides?: Partial<PostIngresoResponse>): PostIngresoResponse {
  return {
    uuid: '00000000-0000-4000-8000-000000000001',
    tipo_entrada: 'ROTACION',
    uuid_subscripcion_cliente: null,
    consecutivo: null,
    ...overrides,
  };
}

describe('buildEntradaPayloadFromResponse — esMensualidad source of truth', () => {
  it('esMensualidad=true when response.tipo_entrada === "MENSUALIDAD"', () => {
    const response = makeResponse({
      tipo_entrada: 'MENSUALIDAD',
      uuid_subscripcion_cliente: '00000000-0000-4000-8000-000000000099',
    });
    const payload = buildEntradaPayloadFromResponse(response, 'ABC123', {});
    expect(payload.esMensualidad).toBe(true);
  });

  it('esMensualidad=false when response.tipo_entrada === "ROTACION"', () => {
    const response = makeResponse({ tipo_entrada: 'ROTACION' });
    const payload = buildEntradaPayloadFromResponse(response, 'ABC123', {});
    expect(payload.esMensualidad).toBe(false);
  });
});
