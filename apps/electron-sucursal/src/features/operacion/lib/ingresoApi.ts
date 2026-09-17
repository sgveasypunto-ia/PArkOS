/**
 * `ingresoApi.ts` — POST mutation for `ingreso` rows (HU-F6.1, T3).
 *
 * The Idempotency-Key header is derived per DEC-SUC-04 from a SHA-256
 * digest of `method | path | canonicalJSON(body)`. We compute the
 * digest on the renderer so two retries — operator double-press,
 * network 5xx → parkosFetch retry — carry the same header and the
 * backend's idempotency middleware (PR2) returns the same response.
 *
 * `parkosFetch` ALSO computes its own `Idempotency-Key` (F2.2
 * `idempotencyKey(method, url, body)` inside `parkosFetch.ts:110-123`)
 * for every mutational request. We deliberately use the SAME shape
 * here — SHA-256 of `method|path|JSON.stringify(body|null)` — so that
 * `ingresoApi.postIngreso()` and `parkosFetch`'s internal key are
 * byte-identical. This means:
 *   - If the caller doesn't override `skipIdempotencyKey`, our explicit
 *     `Idempotency-Key` header here is byte-identical to what
 *     `parkosFetch` would compute itself.
 *   - We forward it via `init.headers` to make the contract explicit
 *     at the call site — easier to reason about and easier to test.
 *
 * The spec requires 3 scenarios:
 *   - Operator double-press (500ms apart): same Idempotency-Key.
 *   - Body mutation (operator edits `observaciones`): different key.
 *   - Network retry (5xx): same key — `parkosFetch` re-fires with the
 *     same headers, our key is stable, server returns the same `uuid`.
 */
import { parkosFetch, ParkosHttpError } from '@parkos/ui-kit/fetch';
import { z } from 'zod';

import { canonicalJSON } from './canonicalJson';

/** Mutation payload accepted by `POST /api/v1/operacion/ingresos`. */
export const PostIngresoPayloadSchema = z.object({
  placa: z.string().regex(/^[A-Z]{3}[0-9]{3}$|^[A-Z]{3}[0-9]{2}[A-Z]$/),
  uuid_tipo_vehiculo: z.string().uuid(),
  observaciones: z.string().max(500).optional(),
  forzado: z.boolean().optional(),
});
export type PostIngresoPayload = z.infer<typeof PostIngresoPayloadSchema>;

/** Server response shape — `tipo_entrada` is derived server-side (DEC-SUC-21). */
export const PostIngresoResponseSchema = z.object({
  uuid_ingreso: z.string().uuid(),
  tipo_entrada: z.enum(['MENSUALIDAD', 'ROTACION']),
  /** DEC-SUC-21: nullable for rotación, non-null for mensualidad. */
  uuid_subscripcion_cliente: z.string().uuid().nullable(),
});
export type PostIngresoResponse = z.infer<typeof PostIngresoResponseSchema>;

/** Path matches F1.6 backend contract. */
const POST_PATH = '/api/v1/operacion/ingresos';

/**
 * `deriveIdempotencyKey(payload)` — SHA-256 hex digest of
 * `POST|/api/v1/operacion/ingresos|<canonicalJSON(payload)>`. Exposed
 * (not just used internally) so callers can test/inspect the key
 * without going through the network.
 *
 * We use the Web Crypto API (`crypto.subtle.digest`) — available in
 * modern browsers and Node 16+ via `globalThis.crypto`. The previous
 * implementation used `crypto.subtle.digest` directly; we keep that
 * dependency because SHA-256 is the spec-mandated hash for the
 * Idempotency-Key contract.
 */
export async function deriveIdempotencyKey(
  payload: PostIngresoPayload,
): Promise<string> {
  const material = `POST|${POST_PATH}|${canonicalJSON(payload)}`;
  const enc = new TextEncoder();
  const bytes = enc.encode(material);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * `postIngreso(payload)` — POST the mutation with the canonical
 * Idempotency-Key. Returns the parsed `PostIngresoResponse` on 201.
 *
 * Errors propagate as `ParkosHttpError` for `Principal.tsx` to branch on:
 *   - 409 `ingreso_activo_existente`  → transparent redirect (spec).
 *   - 422 `motivo_forzado_requerido`  → opens `ForzarIngresoModal`.
 *   - 422 `motivo_forzado_insuficiente` → inline modal error.
 *   - 401 / 403 / 5xx → handled by `parkosFetch` (refresh + retry).
 */
export async function postIngreso(
  payload: PostIngresoPayload,
): Promise<PostIngresoResponse> {
  const key = await deriveIdempotencyKey(payload);
  const raw = await parkosFetch<unknown>(POST_PATH, {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: {
      'Idempotency-Key': key,
    },
  });
  try {
    return PostIngresoResponseSchema.parse(raw);
  } catch (err) {
    // Surface Zod parse failures with the raw payload so debugging
    // doesn't require reproducing the call. The base ParkosHttpError
    // carries a truncated body so we throw a richer wrapper.
    throw new ParkosHttpError(
      500,
      `postIngreso response failed Zod validation: ${String(err)}`,
      POST_PATH,
    );
  }
}
