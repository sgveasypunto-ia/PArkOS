/**
 * Unit tests for `electron/services/auth-store.ts`.
 *
 * Mirrors the `tarifas-store.test.ts` structure (same in-memory `StoreLike`,
 * same TS1-TS5 coverage) so the two namespaces stay behaviourally consistent.
 * The one test specific to this module asserts the property the pairing flow
 * depends on: a JWT survives the round-trip byte-for-byte.
 *
 * Regression under test: `main.ts` never registered the `auth-store:*`
 * handlers, so `PairingWizard.tsx`'s `authStore.set('parkos.sync_jwt', ...)`
 * invoked a channel nobody handled and the credential was lost.
 */
import { describe, it, expect } from 'vitest';

import { readAuthValue, writeAuthValue, removeAuthValue } from './auth-store';
import type { StoreLike } from './kiosko';

/**
 * In-memory `StoreLike` that mirrors electron-store v8 semantics faithfully:
 * `set(key, undefined)` THROWS exactly like the real library, and removal
 * only works through `delete`. The previous mock treated `undefined` as a
 * delete, which is why a broken removal shipped green — the double had to
 * lie about the contract to hide the bug.
 */
function makeStore(initial: Record<string, unknown> = {}): StoreLike & {
  readonly data: Map<string, unknown>;
} {
  const data = new Map<string, unknown>(Object.entries(initial));
  return {
    data,
    get: (key: string) => (data.has(key) ? data.get(key) : null),
    set: (key: string, value: unknown) => {
      if (value === undefined) {
        throw new Error('Use `delete()` to clear values');
      }
      data.set(key, value);
    },
    delete: (key: string) => {
      data.delete(key);
    },
  };
}

describe('auth-store service', () => {
  it('AS1: round-trip set → get returns the original value verbatim', () => {
    const store = makeStore();
    const jwt = 'eyJhbGciOiJSUzI1NiJ9.eyJpc3MiOiJzeW5jLWFnZW50In0.c2ln';
    writeAuthValue(store, 'parkos.sync_jwt', jwt);
    expect(readAuthValue(store, 'parkos.sync_jwt')).toBe(jwt);
  });

  it('AS2: get on a missing key returns `null` (unpaired cold start)', () => {
    const store = makeStore();
    expect(readAuthValue(store, 'parkos.sync_jwt')).toBeNull();
  });

  it('AS3: set + delete → get returns `null`', () => {
    const store = makeStore();
    writeAuthValue(store, 'parkos.sync_jwt', 'token');
    expect(readAuthValue(store, 'parkos.sync_jwt')).not.toBeNull();
    removeAuthValue(store, 'parkos.sync_jwt');
    expect(readAuthValue(store, 'parkos.sync_jwt')).toBeNull();
  });

  it('AS4: get coerces non-string stored values via JSON.stringify', () => {
    const store = makeStore({ 'parkos.sync_jwt': { issuer: 'sync-agent' } });
    const result = readAuthValue(store, 'parkos.sync_jwt');
    expect(typeof result).toBe('string');
    expect(JSON.parse(result as string)).toEqual({ issuer: 'sync-agent' });
  });

  it('AS5: delete on a missing key is a no-op (does not throw)', () => {
    const store = makeStore();
    expect(() => removeAuthValue(store, 'parkos.sync_jwt')).not.toThrow();
    expect(readAuthValue(store, 'parkos.sync_jwt')).toBeNull();
  });

  it('AS6: the auth namespace does not collide with the tarifas namespace', () => {
    const store = makeStore();
    writeAuthValue(store, 'parkos.sync_jwt', 'jwt');
    writeAuthValue(store, 'parkos.tarifas.cache.v1', '{"items":[]}');
    removeAuthValue(store, 'parkos.sync_jwt');
    expect(readAuthValue(store, 'parkos.sync_jwt')).toBeNull();
    expect(readAuthValue(store, 'parkos.tarifas.cache.v1')).toBe('{"items":[]}');
  });
});
