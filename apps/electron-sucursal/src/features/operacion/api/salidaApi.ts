/**
 * `salidaApi.ts` — Zod mirror of F1.7 `SalidaReadForzado` + thin wrapper
 * around `parkosFetch` for `POST /api/v1/operacion/salidas` (HU-F7.2,
 * REQ-OPS-154).
 *
 * Mirrors `ingresoActivoApi.ts` precedent (F6.1): no raw `fetch`,
 * Zod validation on response, schema mismatch throws.
 *
 * The canonical wire shape lives at
 * `backend/.../schemas/operacion.py:392-422` (F1.7 archive). Field
 * `cotizacion_snapshot` is OPTIONAL (None for `MENSUALIDAD`,
 * populated for `ROTACION`); we mirror that exactly.
 */
import { z } from 'zod';

import { parkosFetch } from '@parkos/ui-kit/fetch';

import { CotizarFacturacionSchema, CotizarMensualidadSchema } from '../hooks/useCotizacion';

export const SalidaReadForzadoSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid().nullable(),
  uuid_ingreso: z.string().uuid().nullable(),
  fecha_salida: z.string().nullable(),
  created_at: z.string(),
  created_by: z.string().uuid().nullable(),
  sync_status: z.string().nullable(),
  sync_timestamp: z.string().nullable(),
  sync_attempts: z.number().int().nullable(),
  tipo_salida: z.enum(['ROTACION', 'MENSUALIDAD']),
  forzado_en_creacion: z.boolean(),
  motivo_forzado: z.string().nullable(),
  // MIGRATION 0050 (operator directive 2026-09-24): populated for
  // MENSUALIDAD too (as CotizarMensualidad, full breakdown + discount
  // concept) — `<SalidaMensualidad />` needs it to build the discount
  // factura. `null` only on a V2/V5 forced-exit bypass.
  cotizacion_snapshot: z
    .union([CotizarFacturacionSchema, CotizarMensualidadSchema])
    .nullable(),
});
export type SalidaReadForzado = z.infer<typeof SalidaReadForzadoSchema>;

const POST_PATH = '/api/v1/operacion/salidas';

export interface PostSalidaPayload {
  uuid_ingreso: string;
}

/**
 * `postSalida(payload)` — POST with the canonical Idempotency-Key
 * (header set via `parkosFetch`'s internal idempotency helper, which
 * hashes `method|path|JSON.stringify(body)` — same shape as the
 * F6.1 `ingresoApi.deriveIdempotencyKey` precedent).
 *
 * Returns the parsed `SalidaReadForzado` on 201. Errors propagate as
 * `ParkosHttpError` so callers can branch on the status:
 *   - 401 → useAuthStore.clear() + parkos:auth:cleared (handled by
 *     `useRegistrarSalida` wrapper; this fn is the raw HTTP layer).
 *   - 409 `salida_duplicada` → ParkosHttpError(409) carrying the
 *     typed error body — `useRegistrarSalida` parses it into
 *     `SalidaDuplicadaError`.
 */
export async function postSalida(
  payload: PostSalidaPayload,
): Promise<SalidaReadForzado> {
  const raw = await parkosFetch<unknown>(POST_PATH, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return SalidaReadForzadoSchema.parse(raw);
}