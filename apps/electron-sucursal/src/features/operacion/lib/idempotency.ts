/**
 * `idempotency.ts` — SHA-256 Idempotency-Key closure for the
 * `POST /api/v1/operacion/salidas` mutation (HU-F7.2, REQ-OPS-155).
 *
 * `buildIdempotencyKey({method, path, body})` returns a hex digest of
 * `METHOD|<path>|<canonicalJSON(body)>` — property-order-independent
 * (RFC 8785 normalization via the F7.1 `canonicalJson` helper).
 *
 * Two consecutive calls with the same `{method, path, body}` triple
 * MUST return identical digests. Mirrors `ingresoApi.ts::deriveIdempotencyKey`
 * precedent (F6.1, DEC-SUC-04).
 *
 * The backend `IdempotencyKeyMiddleware` (F1.6 PR2) caches by header
 * for 24h; re-submission within that window returns the cached
 * 201 without re-INSERT. The renderer-side hash is an OPTIMIZATION
 * for the happy path (same client re-click) — the server-side cache
 * always falls back to a body-bytes hash on cache miss (see proposal
 * §6 R5).
 */
import { canonicalJSON } from './canonicalJson';

export interface BuildIdempotencyKeyArgs {
  method: string;
  path: string;
  body: unknown;
}

async function sha256Hex(input: string): Promise<string> {
  const enc = new TextEncoder();
  const bytes = enc.encode(input);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Pure async function: SHA-256 hex of `METHOD|<path>|<canonicalJSON(body)>`.
 * Property-order-independent via `canonicalJSON` (RFC 8785).
 */
export async function buildIdempotencyKey(
  args: BuildIdempotencyKeyArgs,
): Promise<string> {
  const material = `${args.method.toUpperCase()}|${args.path}|${canonicalJSON(args.body)}`;
  return sha256Hex(material);
}