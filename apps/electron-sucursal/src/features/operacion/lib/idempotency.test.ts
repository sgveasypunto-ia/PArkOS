/**
 * Unit tests for `withActionIdempotencyKey`.
 *
 * The Idempotency-Key identifies ONE user action (one submit attempt), not
 * the request content. The backend replays the stored response for the same
 * key within 24h, so a content-derived key replays an old result for a new,
 * legitimate action (exit -> annul -> exit again; exit -> re-enter).
 *
 * Contract:
 *   I1: a key is 64 lowercase hex chars.
 *   I2: concurrent (in-flight) calls with the same content share ONE key
 *       (double click), independent of property order.
 *   I3: once the action settles (success OR failure) the next call with
 *       the same content gets a NEW key.
 *   I4: different content / path never shares a key.
 */
import { describe, expect, it } from 'vitest';

import { withActionIdempotencyKey } from './idempotency';

const ARGS = {
  method: 'POST',
  path: '/api/v1/operacion/salidas',
  body: { uuid_ingreso: '00000000-0000-0000-0000-000000000001' },
};

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('withActionIdempotencyKey', () => {
  it('I1: key is 64 hex chars', async () => {
    const key = await withActionIdempotencyKey(ARGS, async (k) => k);
    expect(key).toMatch(/^[a-f0-9]{64}$/);
  });

  it('I2: in-flight duplicates (double click) share one key, order-independent', async () => {
    const gate = deferred<void>();
    const seen: string[] = [];
    const run = async (k: string) => {
      seen.push(k);
      await gate.promise;
    };
    const p1 = withActionIdempotencyKey({ ...ARGS, body: { a: 1, b: 2 } }, run);
    const p2 = withActionIdempotencyKey({ ...ARGS, body: { b: 2, a: 1 } }, run);
    gate.resolve();
    await Promise.all([p1, p2]);
    expect(seen).toHaveLength(2);
    expect(seen[0]).toBe(seen[1]);
  });

  it('I3: after success the same content gets a NEW key', async () => {
    const k1 = await withActionIdempotencyKey(ARGS, async (k) => k);
    const k2 = await withActionIdempotencyKey(ARGS, async (k) => k);
    expect(k1).not.toBe(k2);
  });

  it('I3b: after a failure the same content gets a NEW key', async () => {
    let first = '';
    await expect(
      withActionIdempotencyKey(ARGS, async (k) => {
        first = k;
        throw new Error('boom');
      }),
    ).rejects.toThrow('boom');
    const second = await withActionIdempotencyKey(ARGS, async (k) => k);
    expect(second).not.toBe(first);
  });

  it('I4: different body or path never shares a key', async () => {
    const gate = deferred<void>();
    const seen: string[] = [];
    const run = async (k: string) => {
      seen.push(k);
      await gate.promise;
    };
    const p1 = withActionIdempotencyKey(ARGS, run);
    const p2 = withActionIdempotencyKey({ ...ARGS, body: { uuid_ingreso: 'otro' } }, run);
    const p3 = withActionIdempotencyKey({ ...ARGS, path: '/otra/ruta' }, run);
    gate.resolve();
    await Promise.all([p1, p2, p3]);
    expect(new Set(seen).size).toBe(3);
  });
});
