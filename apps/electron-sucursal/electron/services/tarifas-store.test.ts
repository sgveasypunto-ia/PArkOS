/**
 * Unit tests for `electron/services/tarifas-store.ts` (HU-F4.2 — T1.3).
 *
 * RED → GREEN → REFACTOR coverage:
 *   TS1: round-trip set → get returns the original JSON verbatim.
 *   TS2: get on a missing key returns `null` (cold-start semantics).
 *   TS3: set + delete → get returns `null` (delete is destructive).
 *   TS4: set + get with non-string stored value coerces via JSON.stringify.
 *
 * Mocking strategy (precedent F2.3 `kiosko.test.ts`):
 *   - Construct a small in-memory `StoreLike` backed by `Map<string, unknown>`.
 *   - No Electron mocks needed; this is a pure-function service.
 */
import { describe, it, expect } from 'vitest';

import { readTarifasValue, writeTarifasValue, removeTarifasValue } from './tarifas-store';
import type { StoreLike } from './kiosko';

function makeStore(initial: Record<string, unknown> = {}): StoreLike & {
  readonly data: Map<string, unknown>;
} {
  const data = new Map<string, unknown>(Object.entries(initial));
  return {
    data,
    get: (key: string) => (data.has(key) ? data.get(key) : null),
    set: (key: string, value: unknown) => {
      if (value === undefined) {
        data.delete(key);
      } else {
        data.set(key, value);
      }
    },
  };
}

describe('tarifas-store service', () => {
  it('TS1: round-trip set → get returns the original JSON verbatim', () => {
    const store = makeStore();
    const snapshot = JSON.stringify({
      items: [{ uuid: 'uuid-auto', valor: 8000 }],
      fetchedAt: 1_700_000_000_000,
    });
    writeTarifasValue(store, 'parkos.tarifas.cache.v1', snapshot);
    expect(readTarifasValue(store, 'parkos.tarifas.cache.v1')).toBe(snapshot);
  });

  it('TS2: get on a missing key returns `null` (cold-start semantics)', () => {
    const store = makeStore();
    expect(readTarifasValue(store, 'parkos.tarifas.cache.v1')).toBeNull();
  });

  it('TS3: set + delete → get returns `null`', () => {
    const store = makeStore();
    writeTarifasValue(store, 'parkos.tarifas.cache.v1', '{"items":[]}');
    expect(readTarifasValue(store, 'parkos.tarifas.cache.v1')).not.toBeNull();
    removeTarifasValue(store, 'parkos.tarifas.cache.v1');
    expect(readTarifasValue(store, 'parkos.tarifas.cache.v1')).toBeNull();
  });

  it('TS4: get coerces non-string stored values via JSON.stringify', () => {
    const store = makeStore({ 'parkos.tarifas.cache.v1': { items: [], count: 0 } });
    const result = readTarifasValue(store, 'parkos.tarifas.cache.v1');
    expect(typeof result).toBe('string');
    expect(JSON.parse(result as string)).toEqual({ items: [], count: 0 });
  });

  it('TS5: delete on a missing key is a no-op (does not throw)', () => {
    const store = makeStore();
    expect(() => removeTarifasValue(store, 'parkos.tarifas.cache.v1')).not.toThrow();
    expect(readTarifasValue(store, 'parkos.tarifas.cache.v1')).toBeNull();
  });
});
