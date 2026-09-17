/**
 * `canonicalJson.ts` — deterministic JSON serialisation for Idempotency-Key
 * derivation (HU-F6.1, DEC-SUC-04).
 *
 * The Idempotency-Key header MUST be stable across re-submissions that
 * carry the same logical body. JavaScript's default `JSON.stringify`
 * does NOT guarantee key ordering — `{a:1,b:2}` and `{b:2,a:1}` both
 * serialise to the same bytes in V8, but V8 reserves the right to
 * reorder object keys in future versions (ECMAScript does not pin the
 * order). A canonical form removes that risk.
 *
 * `canonicalJSON(value)` produces a deterministic JSON string with:
 *   - Object keys sorted alphabetically at every nesting level.
 *   - `undefined` values stripped from objects (matches the F2.2
 *     convention used by `parkosFetch`'s default `JSON.stringify`).
 *   - `null` preserved (semantic value, not a missing key).
 *   - Arrays preserve order (order is semantic for our payloads).
 *   - Primitives pass through `JSON.stringify`'s own encoding so the
 *     output is valid JSON when fed back through `JSON.parse`.
 *
 * The function is pure: no I/O, no `Date.now()`, no `Math.random()`.
 * Two calls with structurally equal inputs return the SAME string —
 * SHA-256 of that string is the canonical Idempotency-Key prefix.
 *
 * NOT used for HTTP wire encoding — `parkosFetch` keeps using
 * `JSON.stringify(init.body)` for the actual request body. This
 * module is ONLY for the Idempotency-Key derivation in `ingresoApi.ts`.
 */
export function canonicalJSON(value: unknown): string {
  return JSON.stringify(sortKeys(value));
}

function sortKeys(value: unknown): unknown {
  if (value === null || typeof value !== 'object') {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((entry) => sortKeys(entry));
  }
  // Plain object: drop undefined values, sort the remaining keys.
  const obj = value as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  const keys = Object.keys(obj)
    .filter((k) => obj[k] !== undefined)
    .sort();
  for (const k of keys) {
    out[k] = sortKeys(obj[k]);
  }
  return out;
}
