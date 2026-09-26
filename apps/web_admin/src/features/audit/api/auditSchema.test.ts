/**
 * `auditSchema.test.ts` -- zod round-trip tests for IT-12.
 */
import { describe, expect, it } from 'vitest';

import { auditLogItemSchema, auditLogListResponseSchema } from './auditSchema';

const SAMPLE_ITEM = {
  uuid: '00000000-0000-0000-0000-000000000001',
  timestamp_evento: '2026-09-26T10:00:00',
  uuid_usuario: '00000000-0000-0000-0000-000000000010',
  uuid_sucursal: '00000000-0000-0000-0000-000000000020',
  uuid_referencia: null,
  accion: 'crear_factura',
  tabla_afectada: 'factura',
  datos_anteriores: null,
  datos_nuevos: { total: 12345 },
  hash_anterior: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
  hash_actual: 'fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210',
};

describe('auditLogItemSchema', () => {
  it('parses a complete payload', () => {
    const r = auditLogItemSchema.safeParse(SAMPLE_ITEM);
    expect(r.success).toBe(true);
  });

  it('parses a payload with all nullable fields null', () => {
    const minimal = {
      uuid: SAMPLE_ITEM.uuid,
      timestamp_evento: SAMPLE_ITEM.timestamp_evento,
      uuid_usuario: null,
      uuid_sucursal: null,
      uuid_referencia: null,
      accion: null,
      tabla_afectada: null,
      datos_anteriores: null,
      datos_nuevos: null,
      hash_anterior: null,
      hash_actual: null,
    };
    const r = auditLogItemSchema.safeParse(minimal);
    expect(r.success).toBe(true);
  });

  it('rejects a malformed uuid', () => {
    const r = auditLogItemSchema.safeParse({ ...SAMPLE_ITEM, uuid: 'not-a-uuid' });
    expect(r.success).toBe(false);
  });
});

describe('auditLogListResponseSchema', () => {
  it('parses an empty list', () => {
    const r = auditLogListResponseSchema.safeParse({ items: [], next_cursor: null });
    expect(r.success).toBe(true);
  });

  it('parses a non-empty list with cursor', () => {
    const r = auditLogListResponseSchema.safeParse({
      items: [SAMPLE_ITEM],
      next_cursor: 'opaque-base64-string',
    });
    expect(r.success).toBe(true);
  });
});
