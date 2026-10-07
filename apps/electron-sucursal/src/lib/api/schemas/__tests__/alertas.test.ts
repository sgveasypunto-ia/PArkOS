/**
 * `alertas.test.ts` — Strict-TDD RED scaffold for HU-F11.2
 * (REQ-OPS-177 + REQ-OPS-180 + DA-F11.2-1 + DA-F11.2-9 + DA-F11.2-14).
 *
 * The schema codifies 18 BE fields from
 * `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py:328-353`,
 * the canonical `estado` enum `Literal["abierta", "en_revision", "resuelta"]`
 * (DA-F11.2-9 corrected: the backend never had `activa`, and
 * `GET /workflows/alerta?estado=activa` answers 422), and `datos_nuevos: z.record(z.unknown()).
 * nullable().optional()` so the schema parses today's BE response
 * (DA-F11.2-14 — column is not yet exposed).
 *
 * Coverage:
 *   S1 (U1): canonical state `abierta` parses + carries 18 fields + drops
 *       display fields (`severidad`, `descripcion`, `mensaje`).
 *   S2 (U2): legacy `estado: "abierta"` REJECTED with ZodError.
 *   S3 (U3): `datos_nuevos` is optional today (BE omits it) AND accepted
 *       when present (`uuid_ingreso` drill-down path for
 *       `capacidad_agotada_forzado`).
 *   S4 (U4): 18-field count + `strict()` rejects unknown field
 *       (`legacy_msg` from a hypothetical BE drift).
 *
 * RED until C2 lands `lib/api/schemas/alertas.ts` (F11.1 stub at
 * `features/sync/hooks/useSyncEstado.ts:90-146` is deleted in C6 — the
 * new module is the canonical home for the schema).
 */
import { describe, it, expect } from 'vitest';

import { AlertaSchema, AlertaReadListSchema } from '../alertas';

const VALID_UUID = '00000000-0000-0000-0000-000000000001';

const BASE_ROW = {
  uuid: VALID_UUID,
  fecha_retencion_hasta: '2031-09-21',
  created_at: '2026-09-21T10:00:00.000Z',
  created_by: null,
  sync_status: null,
  sync_timestamp: null,
  sync_attempts: null,
  uuid_sucursal: VALID_UUID,
  uuid_usuario: null,
  uuid_arqueo: null,
  tipo_alerta: 'descuadre_critico',
  valor_diferencia_efectivo: null,
  valor_diferencia_datafono: null,
  uuid_alerta_padre: null,
  timestamp_evento: '2026-09-21T10:00:00.000Z',
  vigente_desde: '2026-09-21T10:00:00.000Z',
  vigente_hasta: null,
  estado: 'abierta' as const,
};

describe('AlertaSchema — REQ-OPS-177 + REQ-OPS-180 (HU-F11.2)', () => {
  it('S1: canonical state `abierta` parses; the 18 BE fields are preserved (no display fields)', () => {
    const parsed = AlertaSchema.parse(BASE_ROW);
    expect(parsed.estado).toBe('abierta');
    expect(parsed.uuid).toBe(VALID_UUID);
    expect(parsed.tipo_alerta).toBe('descuadre_critico');
    // The 18-field contract: the parsed object MUST NOT carry display
    // fields (severidad / descripcion / mensaje). Those live on the
    // separate `alert_types` GET endpoint (REQ-OPS-179 path b).
    expect('severidad' in parsed).toBe(false);
    expect('descripcion' in parsed).toBe(false);
    expect('mensaje' in parsed).toBe(false);
    // Object.keys count is exactly 18 — defense in depth against BE drift.
    expect(Object.keys(parsed)).toHaveLength(18);
  });

  it('S2: legacy `estado: "activa"` is REJECTED with ZodError (DA-F11.2-9 GATING)', () => {
    const legacy = { ...BASE_ROW, estado: 'activa' };
    expect(() => AlertaSchema.parse(legacy)).toThrow();
  });

  it('S2b: the real backend vocabulary parses (abierta | en_revision | resuelta)', () => {
    for (const estado of ['abierta', 'en_revision', 'resuelta']) {
      expect(AlertaSchema.parse({ ...BASE_ROW, estado }).estado).toBe(estado);
    }
  });

  it('S2c: `valor_diferencia_datafono` was removed from the BE wire schema -- both shapes parse', () => {
    const { valor_diferencia_datafono: _drop, ...sinDatafono } = BASE_ROW;
    expect(() => AlertaSchema.parse(sinDatafono)).not.toThrow();
  });

  it('S2d: the per-alert `severity` the backend sends is accepted (strict schema must not reject the whole list)', () => {
    for (const severity of ['critical', 'warning', 'info', null]) {
      expect(AlertaSchema.parse({ ...BASE_ROW, severity }).severity).toBe(severity);
    }
  });

  it('S3a: `datos_nuevos` is OPTIONAL — schema parses a BE row that omits the field today (DA-F11.2-14)', () => {
    // Today's BE response does NOT include `datos_nuevos` on the alert
    // row. The schema MUST succeed against that payload; the .optional()
    // default lets `datos_nuevos: undefined` flow through.
    const parsed = AlertaSchema.parse(BASE_ROW);
    expect('datos_nuevos' in parsed ? parsed.datos_nuevos : undefined).toBeUndefined();
    // Round-trip the same row through the array parser to mirror the
    // real /workflows/alerta response shape.
    const list = AlertaReadListSchema.parse([BASE_ROW]);
    expect(list).toHaveLength(1);
    expect(list[0]?.estado).toBe('abierta');
  });

  it('S3b: `datos_nuevos: { uuid_ingreso: "Z" }` parses typed as Record<string, unknown> | null | undefined', () => {
    const enriched = {
      ...BASE_ROW,
      tipo_alerta: 'capacidad_agotada_forzado',
      datos_nuevos: { uuid_ingreso: 'Z' },
    };
    const parsed = AlertaSchema.parse(enriched);
    expect(parsed.datos_nuevos).toEqual({ uuid_ingreso: 'Z' });
    if (!parsed.datos_nuevos) throw new Error('datos_nuevos missing');
    expect((parsed.datos_nuevos as Record<string, unknown>).uuid_ingreso).toBe('Z');
  });

  it('S4: unknown fields are rejected by `strict()` (defense against BE schema drift)', () => {
    const drifted = { ...BASE_ROW, legacy_msg: 'fortune cookie from a phantom column' };
    expect(() => AlertaSchema.parse(drifted)).toThrow();
  });
});
