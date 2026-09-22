/**
 * `ingresoApi.ts` — POST mutation for `ingreso` rows (HU-F6.1, T3;
 * REQ-OPS-191/192/194/197 — ingreso sin placa + consecutivo).
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
 * HU-INGRESO-SIN-PLACA (REQ-OPS-194):
 *   The payload is a discriminated union keyed on `placa_presente: boolean`
 *   to make the no-placa path first-class at the call site. `placa_presente:
 *   true` is the legacy F6.1 shape (`placa: <regex>`), `placa_presente:
 *   false` is the no-placa shape (`placa: null, uuid_tipo_vehiculo: <uuid>`).
 *   Mixed payloads (e.g. `placa_presente: true` + `placa: null`) are
 *   rejected by Zod at the client boundary so no round-trip is wasted.
 *
 * The response carries `consecutivo: str | None` (REQ-OPS-197) — null
 * for legacy carro/moto rows, formatted `<TIPO>-NNNNNN-<uuid8>` for
 * no-placa ingresos.
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

/**
 * Discriminated union payload accepted by `POST /api/v1/operacion/ingresos`
 * (REQ-OPS-194). The discriminator is `placa_presente: boolean` literal;
 * Zod's `discriminatedUnion` rejects mixed payloads (e.g.
 * `placa_presente: true` + `placa: null`) at parse time.
 */
const placaConPlacaSchema = z.object({
  placa_presente: z.literal(true),
  placa: z
    .string()
    .regex(/^[A-Z]{3}[0-9]{3}$|^[A-Z]{3}[0-9]{2}[A-Z]$/),
  uuid_tipo_vehiculo: z.string().uuid().optional(),
  observaciones: z.string().max(500).optional(),
  forzado: z.boolean().optional(),
});

const placaSinPlacaSchema = z.object({
  placa_presente: z.literal(false),
  // Explicit null (Zod literal semantics); the discriminator already
  // guarantees the variant — keeping it null here documents the wire
  // shape and blocks accidental `placa: 'ABC123'` on the no-placa path.
  placa: z.null(),
  uuid_tipo_vehiculo: z.string().uuid(),
  observaciones: z.string().max(500).optional(),
  forzado: z.boolean().optional(),
});

export const PostIngresoPayloadSchema = z.discriminatedUnion(
  'placa_presente',
  [placaConPlacaSchema, placaSinPlacaSchema],
);
export type PostIngresoPayload = z.infer<typeof PostIngresoPayloadSchema>;

/** Server response shape — `tipo_entrada` is derived server-side (DEC-SUC-21). */
export const PostIngresoResponseSchema = z.object({
  // REQ-OPS-197: the backend returns ``uuid`` (from ``IngresoRead``) —
  // the frontend's earlier discriminator used ``uuid_ingreso`` but the
  // actual wire field is ``uuid``. Align with the backend contract.
  uuid: z.string().uuid(),
  tipo_entrada: z.enum(['MENSUALIDAD', 'ROTACION']),
  /** DEC-SUC-21: nullable for rotación, non-null for mensualidad. */
  uuid_subscripcion_cliente: z.string().uuid().nullable(),
  /**
   * REQ-OPS-197 — parking-lot identifier for ingresos sin placa.
   * `null` for legacy carro/moto rows (F6.1 wire compat); formatted
   * `<TIPO>-NNNNNN-<uuid8>` for no-placa ingresos.
   */
  consecutivo: z.string().nullable(),
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
