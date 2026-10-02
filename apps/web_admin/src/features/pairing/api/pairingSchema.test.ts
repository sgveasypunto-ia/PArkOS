/**
 * `pairingSchema.test.ts` -- HU-F19.3 pairing-token Zod schemas.
 *
 * Covers:
 *  - ttlHours bounds on the form schema (0 fails, 1 ok, 168 ok, 169 fails).
 *  - `pairingTokenReadSchema` parses a realistic fixture and never
 *    surfaces a `pairing_token_hash` field (the backend strips it; the
 *    schema must not declare it at all).
 */
import { describe, expect, it } from 'vitest';

import {
  MAX_TTL_HOURS,
  pairingTokenIssueFormSchema,
  pairingTokenIssueResponseSchema,
  pairingTokenReadSchema,
} from './pairingSchema';

describe('MAX_TTL_HOURS', () => {
  it('is 168 (7 days), matching the backend MAX_TTL_HOURS', () => {
    expect(MAX_TTL_HOURS).toBe(168);
  });
});

describe('pairingTokenIssueFormSchema', () => {
  it('rejects ttlHours = 0', () => {
    expect(pairingTokenIssueFormSchema.safeParse({ ttlHours: 0 }).success).toBe(false);
  });

  it('accepts ttlHours = 1 (lower bound)', () => {
    expect(pairingTokenIssueFormSchema.safeParse({ ttlHours: 1 }).success).toBe(true);
  });

  it('accepts ttlHours = 168 (upper bound)', () => {
    expect(pairingTokenIssueFormSchema.safeParse({ ttlHours: 168 }).success).toBe(true);
  });

  it('rejects ttlHours = 169 (above the upper bound)', () => {
    const result = pairingTokenIssueFormSchema.safeParse({ ttlHours: 169 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.message).toBe(
        'El TTL no puede superar 168 horas (7 días).',
      );
    }
  });

  it('rejects a non-integer ttlHours', () => {
    expect(pairingTokenIssueFormSchema.safeParse({ ttlHours: 12.5 }).success).toBe(false);
  });
});

describe('pairingTokenIssueResponseSchema', () => {
  it('parses the 201 issue response shape', () => {
    const fixture = {
      token: 'plaintext-pairing-token-once',
      pairing_token_uuid: '11111111-1111-1111-1111-111111111111',
      pairing_token_hash: 'sha256:deadbeef',
      expires_at: '2026-09-02T00:00:00',
      uuid_sucursal: '22222222-2222-2222-2222-222222222222',
      ttl_hours: 24,
    };
    expect(pairingTokenIssueResponseSchema.parse(fixture)).toEqual(fixture);
  });

  it('accepts uuid_sucursal = null (tenant-wide token)', () => {
    const fixture = {
      token: 'plaintext-pairing-token-once',
      pairing_token_uuid: '11111111-1111-1111-1111-111111111111',
      pairing_token_hash: 'sha256:deadbeef',
      expires_at: '2026-09-02T00:00:00',
      uuid_sucursal: null,
      ttl_hours: 24,
    };
    expect(pairingTokenIssueResponseSchema.safeParse(fixture).success).toBe(true);
  });
});

describe('pairingTokenReadSchema', () => {
  const fixture = {
    uuid: '11111111-1111-1111-1111-111111111111',
    fecha_retencion_hasta: '2027-09-01T00:00:00',
    created_at: '2026-09-01T00:00:00',
    created_by: '22222222-2222-2222-2222-222222222222',
    uuid_sucursal: '33333333-3333-3333-3333-333333333333',
    expires_at: '2026-09-02T00:00:00',
    used: false,
    used_at: null,
    revoked_at: null,
    revoked_by: null,
  };

  it('parses a realistic fixture successfully', () => {
    const parsed = pairingTokenReadSchema.parse(fixture);
    expect(parsed.uuid).toBe(fixture.uuid);
    expect(parsed.used).toBe(false);
  });

  it('never surfaces pairing_token_hash, even if the server sent it', () => {
    const withHash = { ...fixture, pairing_token_hash: 'sha256:leak-should-be-stripped' };
    const parsed = pairingTokenReadSchema.parse(withHash);
    expect('pairing_token_hash' in parsed).toBe(false);
  });

  it('parses a used + revoked terminal state', () => {
    const terminal = {
      ...fixture,
      used: true,
      used_at: '2026-09-01T10:00:00',
      revoked_at: '2026-09-01T11:00:00',
      revoked_by: '22222222-2222-2222-2222-222222222222',
    };
    expect(pairingTokenReadSchema.safeParse(terminal).success).toBe(true);
  });
});
