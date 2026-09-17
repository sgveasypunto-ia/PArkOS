/**
 * `ocupacionApi.ts` — HTTP layer for the occupancy endpoint
 * (HU-F4.3 — frontend consumer of HU-F1.5 backend).
 *
 * Backend (HU-F1.5, READ ONLY, archive `2026-09-14-hu-f1-5-mv-ocupacion-diaria`):
 *   - `GET /api/v1/operacion/ocupacion?uuid_sucursal=X`
 *   - Returns the materialized view `prod.mv_ocupacion_diaria` snapshot.
 *   - Permission `operacion:read` (seeded by F1.2).
 *   - Response shape (`schemas/operacion.py:205-...`):
 *     `{ uuid_sucursal, items: [{ uuid_tipo_vehiculo, tipo, cupo_maximo,
 *                                  activos, disponible }], generado_en }`.
 *
 * DEC-SUC-11 + A-04 verbatim: `disponible` is ALWAYS `cupo_maximo - activos`,
 * computed server-side by `repo/ocupacion.py::get_ocupacion_puros_activos()`.
 * The renderer NEVER invents or recomputes a mutable `disponible` column.
 * The schema declares the field because the wire format carries it; the
 * chip displays `activos / cupo_maximo` per spec.
 *
 * `parkosFetch` invariants (F2.2):
 *   - Bearer token from `authStore` (automatic).
 *   - 401 once-refresh via `refreshAccessToken()` Mutex.
 *   - 5xx/408 retry up to 3 with backoff 300/600/1200ms.
 *   - No Idempotency-Key (GET read idempotent, RFC 7231 §4.2.1).
 *
 * No raw `fetch` — every network access goes through `parkosFetch`.
 * No pre-flight gate extension — `/operacion/*` GET read idempotent does
 * not require the pre-flight round-trip (DEC-SUC-03 + F3.2 verbatim).
 */
import { z } from 'zod';

import { parkosFetch } from '@parkos/ui-kit/fetch';

/** Path — backend contract is REQ-OPS-030 + REQ-OPS-031. */
const OCUPACION_PATH = '/api/v1/operacion/ocupacion';

/**
 * Per-tipo occupancy item. The wire shape carries `disponible` (computed
 * server-side, never re-derived in the client). The client renders
 * `activos / cupo_maximo` per spec — `disponible` is exposed for forward
 * F4.4 dashboards that may want to show remaining capacity, but the chip
 * itself never reads `disponible` directly.
 */
export const OcupacionItemSchema = z.object({
  uuid_tipo_vehiculo: z.string().uuid(),
  tipo: z.string(),
  cupo_maximo: z.number().int().min(0),
  activos: z.number().int().min(0),
  disponible: z.number().int(),
});
export type OcupacionItem = z.infer<typeof OcupacionItemSchema>;

export const OcupacionResponseSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  items: z.array(OcupacionItemSchema),
  generado_en: z.string(),
});
export type OcupacionResponse = z.infer<typeof OcupacionResponseSchema>;

/**
 * GET /api/v1/operacion/ocupacion?uuid_sucursal=X.
 *
 * Errors propagate as `ParkosHttpError` (parkosFetch wraps everything):
 *   - 200 OK → parsed `OcupacionResponse` (Zod-validated).
 *   - 401 → parkosFetch handle401 Mutex refresh-once; if still 401,
 *           `useAuthStore.clear()` is fired by the hook's onError.
 *   - 5xx / network → retried 3x by parkosFetch, then propagated.
 *   - 403 → propagated as-is.
 *   - 404 → propagated as-is (sucursal UUID typo or unconfigured tenant);
 *           `shouldRetryOnError` in the hook excludes 404 to avoid spam.
 */
export async function getOcupacion(uuid_sucursal: string): Promise<OcupacionResponse> {
  const params = new URLSearchParams({ uuid_sucursal });
  const raw = await parkosFetch<unknown>(
    `${OCUPACION_PATH}?${params.toString()}`,
  );
  return OcupacionResponseSchema.parse(raw);
}