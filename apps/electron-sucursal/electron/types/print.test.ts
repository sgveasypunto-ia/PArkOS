/**
 * Unit tests for `electron/types/print.ts` (HU-F5.1 T4.1).
 *
 * Validates every Zod schema accepts the canonical happy path and
 * rejects the canonical failure paths with the expected Zod issue
 * shape. The bridge surface (`bridge.d.ts`) re-exports the inferred
 * types, so passing these tests guarantees the renderer-facing
 * contract stays in lockstep with the runtime validator.
 */
import { describe, expect, it } from 'vitest';

import {
  printPayloadSchema,
  queueItemSchema,
  queueStatusSchema,
  printResultSchema,
  printerErrorSchema,
} from './print';

describe('printPayloadSchema', () => {
  const happy = {
    buffer: 'AA==',
    ticketId: 't-1',
    cut: false,
  };

  it('accepts the canonical happy path', () => {
    const parsed = printPayloadSchema.parse(happy);
    expect(parsed.buffer).toBe('AA==');
    expect(parsed.ticketId).toBe('t-1');
    expect(parsed.cut).toBe(false);
  });

  it('rejects payloads missing `buffer` with path ["buffer"]', () => {
    const result = printPayloadSchema.safeParse({ ticketId: 't-1', cut: false });
    expect(result.success).toBe(false);
    if (!result.success) {
      const bufferIssue = result.error.issues.find((i) => i.path[0] === 'buffer');
      expect(bufferIssue).toBeDefined();
    }
  });

  it('rejects payloads missing `ticketId`', () => {
    const result = printPayloadSchema.safeParse({ buffer: 'AA==', cut: false });
    expect(result.success).toBe(false);
  });

  it('rejects `uuidRegistro` that is not a UUID with `Invalid uuid`', () => {
    const result = printPayloadSchema.safeParse({
      ...happy,
      uuidRegistro: 'not-a-uuid',
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      const uuidIssue = result.error.issues.find((i) => i.path[0] === 'uuidRegistro');
      expect(uuidIssue?.message).toMatch(/invalid uuid/i);
    }
  });

  it('rejects empty `buffer` (min 1 char)', () => {
    const result = printPayloadSchema.safeParse({ ...happy, buffer: '' });
    expect(result.success).toBe(false);
    if (!result.success) {
      const bufIssue = result.error.issues.find((i) => i.path[0] === 'buffer');
      expect(bufIssue?.message).toMatch(/at least 1|non-empty|min/i);
    }
  });

  it('rejects `vid` above 0xffff with max(0xffff) message', () => {
    const result = printPayloadSchema.safeParse({ ...happy, vid: 0x10000 });
    expect(result.success).toBe(false);
    if (!result.success) {
      const vidIssue = result.error.issues.find((i) => i.path[0] === 'vid');
      expect(vidIssue?.message).toMatch(/less than or equal to|max/i);
    }
  });

  it('accepts optional `cashDrawer` and `vid/pid` when present', () => {
    const parsed = printPayloadSchema.parse({
      ...happy,
      cashDrawer: true,
      vid: 0x04b8,
      pid: 0x0202,
      uuidRegistro: '00000000-0000-4000-8000-000000000001',
    });
    expect(parsed.cashDrawer).toBe(true);
    expect(parsed.vid).toBe(0x04b8);
    expect(parsed.pid).toBe(0x0202);
  });
});

describe('queueItemSchema', () => {
  const item = {
    id: '00000000-0000-4000-8000-000000000001',
    buffer: 'AA==',
    vid: 0x04b8,
    pid: 0x0202,
    ticketId: 't-1',
    attempts: 0,
    nextRetryAt: Date.now() + 5_000,
    addedAt: Date.now(),
    estado: 'pending' as const,
  };

  it('accepts the canonical pending item', () => {
    const parsed = queueItemSchema.parse(item);
    expect(parsed.estado).toBe('pending');
    expect(parsed.attempts).toBe(0);
  });

  it('rejects `attempts` greater than 5', () => {
    const result = queueItemSchema.safeParse({ ...item, attempts: 6 });
    expect(result.success).toBe(false);
  });
});

describe('queueStatusSchema', () => {
  it('accepts the zero-state shape', () => {
    const parsed = queueStatusSchema.parse({
      pending: 0,
      retrying: 0,
      fallido_permanente: 0,
      lastSuccessAt: null,
      lastError: null,
    });
    expect(parsed.pending).toBe(0);
    expect(parsed.lastSuccessAt).toBeNull();
  });
});

describe('printResultSchema', () => {
  it('accepts ok=true with no extras', () => {
    const parsed = printResultSchema.parse({ ok: true, queueId: null });
    expect(parsed.ok).toBe(true);
  });

  it('accepts ok=false with a typed error and queueId', () => {
    const parsed = printResultSchema.parse({
      ok: false,
      error: 'printer_offline',
      queueId: '00000000-0000-4000-8000-000000000001',
    });
    expect(parsed.error).toBe('printer_offline');
  });
});

describe('printerErrorSchema', () => {
  it('accepts every catalogued code', () => {
    for (const code of [
      'bridge_imprimir_invalid_payload',
      'printer_offline',
      'printer_disconnected',
      'print_failed_terminal',
    ] as const) {
      expect(printerErrorSchema.parse(code)).toBe(code);
    }
  });

  it('rejects unknown error codes', () => {
    expect(printerErrorSchema.safeParse('not_a_code').success).toBe(false);
  });
});