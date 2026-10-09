/**
 * `pairingLocalState.test.ts` — covers the localStorage helpers used
 * by `<Pairing />` to bridge BR4 (no list-pairing-tokens endpoint).
 *
 * 2026-10-08: added the 404-eviction test, pairing the new
 * `deleteLocalRecord` helper with the page-level behaviour asserted
 * in `Pairing.test.tsx`.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  deleteLocalRecord,
  getLastTokenUuid,
  setLastTokenUuid,
} from './pairingLocalState';

const STORAGE_KEY = 'easypunto.pairing.lastToken.v1';

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
});

describe('pairingLocalState', () => {
  it('returns null for a sucursal with no record', () => {
    expect(getLastTokenUuid('aaaaaaaa-0000-0000-0000-000000000000')).toBeNull();
  });

  it('round-trips set → get for a sucursal', () => {
    const suc = '11111111-1111-1111-1111-111111111111';
    const token = 'bbbbbbbb-0000-0000-0000-000000000001';
    setLastTokenUuid(suc, token);
    expect(getLastTokenUuid(suc)).toBe(token);
  });

  it('keeps sibling records when setting a new one', () => {
    const sucA = 'aaaaaaaa-0000-0000-0000-00000000000a';
    const sucB = 'bbbbbbbb-0000-0000-0000-00000000000b';
    setLastTokenUuid(sucA, 'token-a');
    setLastTokenUuid(sucB, 'token-b');
    expect(getLastTokenUuid(sucA)).toBe('token-a');
    expect(getLastTokenUuid(sucB)).toBe('token-b');
  });

  it('deleteLocalRecord removes one entry, leaves siblings intact', () => {
    const sucA = 'aaaaaaaa-0000-0000-0000-00000000000a';
    const sucB = 'bbbbbbbb-0000-0000-0000-00000000000b';
    setLastTokenUuid(sucA, 'token-a');
    setLastTokenUuid(sucB, 'token-b');

    deleteLocalRecord(sucA);
    expect(getLastTokenUuid(sucA)).toBeNull();
    expect(getLastTokenUuid(sucB)).toBe('token-b');
  });

  it('deleteLocalRecord is a no-op when the entry does not exist', () => {
    // Should not throw, should not corrupt the map.
    deleteLocalRecord('cccccccc-0000-0000-0000-00000000000c');
    expect(window.localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('deleteLocalRecord tolerates malformed JSON in localStorage (no throw)', () => {
    // Defensive: a hand-edited localStorage entry should not crash
    // the page; the helpers swallow JSON.parse failures in readMap.
    window.localStorage.setItem(STORAGE_KEY, 'not-json');
    expect(() => deleteLocalRecord('anything')).not.toThrow();
    expect(getLastTokenUuid('anything')).toBeNull();
  });
});
