/**
 * `ingresoApi.ts` — POST mutation for `ingreso` rows (HU-F6.1, T3;
 * REQ-OPS-191/192/194/197 — ingreso sin placa + consecutivo).
 *
 * The Idempotency-Key header identifies ONE operator action (see
 * `withActionIdempotencyKey`): a double-press while the request is in flight
 * and parkosFetch transport retries share one key (the backend dedupes them);
 * a NEW submit — e.g. re-entering a plate that already left — gets a fresh key
 * so the backend never replays the previous ingreso.
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
 */
import { parkosFetch, ParkosHttpError } from '@parkos/ui-kit/fetch';
import { z } from 'zod';

import { withActionIdempotencyKey } from './idempotency';

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
  const raw = await withActionIdempotencyKey(
    { method: 'POST', path: POST_PATH, body: payload },
    (key) =>
      parkosFetch<unknown>(POST_PATH, {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: {
          'Idempotency-Key': key,
        },
      }),
  );
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
