/**
 * `pairingSchema.test.ts` -- unit tests for the zod schema (IT-2.8).
 */
import { describe, expect, it } from 'vitest';

import { pairingRequestSchema } from './pairingSchema';

describe('pairingRequestSchema', () => {
  it('accepts a minimal valid request', () => {
    const r = pairingRequestSchema.safeParse({
      pairing_token: 'eyJ...',
      uuid_sucursal: '00000000-0000-0000-0000-0000000000b1',
    });
    expect(r.success).toBe(true);
  });

  it('rejects an empty pairing_token', () => {
    const r = pairingRequestSchema.safeParse({
      pairing_token: '',
      uuid_sucursal: '00000000-0000-0000-0000-0000000000b1',
    });
    expect(r.success).toBe(false);
  });

  it('rejects a non-UUID uuid_sucursal', () => {
    const r = pairingRequestSchema.safeParse({
      pairing_token: 'eyJ...',
      uuid_sucursal: 'not-a-uuid',
    });
    expect(r.success).toBe(false);
  });

  it('rejects a missing uuid_sucursal', () => {
    const r = pairingRequestSchema.safeParse({
      pairing_token: 'eyJ...',
    });
    expect(r.success).toBe(false);
  });
});
