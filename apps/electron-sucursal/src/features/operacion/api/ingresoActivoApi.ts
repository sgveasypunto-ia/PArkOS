/**
 * `ingresoActivoApi.ts` — HTTP layer for the active-ingreso lookup
 * (HU-F6.1, T2).
 *
 * Composes two endpoints to satisfy the active-check capability with
 * ZERO backend change (design.md §Decision: Path 1, spec §Open question):
 *
 *   1. `GET /api/v1/operacion/ingresos?placa=X`
 *      → returns 0..N historical rows for the plate at the current
 *        branch (operator JWT + `X-Sucursal-Context` headers are
 *        applied automatically by `parkosFetch`).
 *
 *   2. `GET /api/v1/operacion/ingresos/{uuid}/estado`
 *      → returns the derived state `{ abierto | cerrado | anulada }`
 *        for each candidate row.
 *
 * The most-recent `abierto` row wins (Path 1 simplification — see
 * design.md §Open Questions: the backend companion `?activo=true`
 * query param is T0b, ~15 LOC, optional follow-up).
 *
 * Precedent verbatim F4.3 `ocupacionApi.ts`:
 *   - `parkosFetch` invariants (F2.2): Bearer token, 401 refresh, 5xx
 *     retry 3x with 300/600/1200ms backoff, no Idempotency-Key on GET.
 *   - No raw `fetch` — every network access goes through `parkosFetch`.
 *   - Zod validation on response: schema mismatch throws `ZodError`.
 *
 * The 404 case (no rows for the plate) returns `[]` via `parkosFetch`'s
 * own 4xx-no-retry policy. The hook downstream treats `[]` as "no active
 * ingreso" without surfacing an error to the operator.
 */
import { z } from 'zod';

import { parkosFetch } from '@parkos/ui-kit/fetch';

/** Backend wire shape — `GET /operacion/ingresos` item per F1.6 archive. */
export const IngresoSchema = z.object({
  uuid: z.string().uuid(),
  uuid_sucursal: z.string().uuid(),
  placa: z.string(),
  fecha_ingreso: z.string(),
  /** DEC-SUC-21: `tipo_entrada` is DERIVED from this nullable FK on the server. */
  uuid_subscripcion_cliente: z.string().uuid().nullable(),
});
export type Ingreso = z.infer<typeof IngresoSchema>;

export const IngresoArraySchema = z.array(IngresoSchema);

/** Derived state returned by `GET /operacion/ingresos/{uuid}/estado` (F1.6). */
export const IngresoEstadoSchema = z.object({
  uuid: z.string().uuid(),
  estado: z.enum(['abierto', 'cerrado', 'anulada']),
});
export type IngresoEstado = z.infer<typeof IngresoEstadoSchema>;

/** Path base — same contract as the rest of the operacion feature (F4.3). */
const INGRESOS_PATH = '/api/v1/operacion/ingresos';

/**
 * `getIngresosByPlaca(placa)` — list 0..N historical rows for the typed
 * plate at the current branch. Pure read; no Idempotency-Key (GET).
 *
 * Empty list (`[]`) is a valid response — `parkosFetch` 4xx policy
 * preserves it (200 OK with `[]` body). The hook treats `length === 0`
 * as `hasActive: false`.
 */
export async function getIngresosByPlaca(placa: string): Promise<Ingreso[]> {
  const params = new URLSearchParams({ placa });
  const raw = await parkosFetch<unknown>(`${INGRESOS_PATH}?${params.toString()}`);
  return IngresoArraySchema.parse(raw);
}

/**
 * `getIngresoEstado(uuid)` — fetch the derived state of a single ingreso.
 * Used by `useIngresoActivo` to resolve the `abierto` filter when the
 * list endpoint returns >0 candidates (Path 1 composition).
 */
export async function getIngresoEstado(uuid: string): Promise<IngresoEstado> {
  const raw = await parkosFetch<unknown>(`${INGRESOS_PATH}/${uuid}/estado`);
  return IngresoEstadoSchema.parse(raw);
}
