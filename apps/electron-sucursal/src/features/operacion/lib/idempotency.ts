/**
 * `idempotency.ts` — Idempotency-Key per USER ACTION for every mutating
 * call the branch renderer makes with an explicit header.
 *
 * Why not a content hash: the backend `IdempotencyKeyMiddleware` persists
 * and replays the stored response for the same key (+ same body) within
 * 24h. A key derived only from `method|path|body` therefore made a NEW,
 * legitimate action replay an OLD result (exit -> annul -> exit again got
 * the annulled salida back; exit -> re-enter the same plate replayed the
 * old ingreso). Same pattern as `parkosFetch`'s per-call nonce.
 *
 * Contract of `withActionIdempotencyKey(args, run)`:
 *   - Generates ONE random key when the action starts and passes it to
 *     `run`. Transport-level retries inside `run` (parkosFetch 5xx / 408 /
 *     network / 401-refresh) re-use the header it was given, so they stay
 *     deduplicated by the backend.
 *   - While an identical action (same method, path and canonical body) is
 *     still IN FLIGHT, concurrent callers (double click) share the SAME
 *     key, so the backend dedupes them to one row.
 *   - When the action settles (success OR error) the key is released: the
 *     next trigger — a new click, or a deliberate retry after a visible
 *     failure — gets a NEW key.
 */
import { canonicalJSON } from './canonicalJson';

export interface ActionIdempotencyArgs {
  method: string;
  path: string;
  body: unknown;
}

interface InFlight {
  key: string;
  refs: number;
}

const inFlight = new Map<string, InFlight>();

/** 64 lowercase hex chars (same shape `parkosFetch` produces). */
function newActionKey(): string {
  if (typeof crypto.randomUUID === 'function') {
    return (crypto.randomUUID() + crypto.randomUUID()).replace(/-/g, '');
  }
  return Array.from(crypto.getRandomValues(new Uint8Array(32)))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export async function withActionIdempotencyKey<T>(
  args: ActionIdempotencyArgs,
  run: (idempotencyKey: string) => Promise<T>,
): Promise<T> {
  const material = `${args.method.toUpperCase()}|${args.path}|${canonicalJSON(args.body)}`;
  // No `await` between lookup and insert: two synchronous double-click
  // triggers must observe each other.
  let entry = inFlight.get(material);
  if (entry === undefined) {
    entry = { key: newActionKey(), refs: 0 };
    inFlight.set(material, entry);
  }
  entry.refs += 1;
  try {
    return await run(entry.key);
  } finally {
    entry.refs -= 1;
    if (entry.refs === 0 && inFlight.get(material) === entry) {
      inFlight.delete(material);
    }
  }
}

async function sha256Hex(input: string): Promise<string> {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Key for flows whose UI OWNS the attempt id (e.g. the renewal panel keeps
 * one `intentoId` across network/5xx failures and rotates it after a
 * definitive answer). The same `attemptId` always yields the same key, a
 * new `attemptId` a new one; the id must be a per-attempt random value.
 */
export async function attemptIdempotencyKey(
  args: ActionIdempotencyArgs & { attemptId: string },
): Promise<string> {
  return sha256Hex(
    `${args.method.toUpperCase()}|${args.path}|${canonicalJSON(args.body)}|${args.attemptId}`,
  );
}
