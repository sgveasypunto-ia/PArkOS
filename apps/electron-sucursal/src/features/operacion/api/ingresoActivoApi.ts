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
  /**
   * REGRESSION fix (2026-09-22, directiva del operador): ``placa`` can be
   * ``null`` for no-placa ingresos (HU-INGRESO-SIN-PLACA, REQ-OPS-194) —
   * the no-placa flow INSERTs a ``consecutivo`` but no ``placa``. The
   * original schema required ``z.string()`` which broke the parse for
   * no-placa rows; relaxed to ``.nullable()``.
   */
  placa: z.string().nullable(),
  /**
   * REGRESSION fix (2026-09-22, directiva del operador): ``fecha_ingreso``
   * can be ``null`` for historical ingresos that were INSERTed before the
   * handler fix landed (PR companion of migration 0046 — bug abierto
   * #2009, Engram). The migration adds defense in depth via
   * ``COALESCE(fecha_ingreso, created_at)`` in the PL/pgSQL cotizacion,
   * but the wire shape itself can still surface ``null`` to clients that
   * list historical rows. The handler fix (PR companion, ``operacion.py::
   * create_ingreso``) now stamps ``fecha_ingreso`` on INSERT so new rows
   * are populated — the nullability here is backward compatibility only.
   */
  fecha_ingreso: z.string().nullable(),
  /** DEC-SUC-21: `tipo_entrada` is DERIVED from this nullable FK on the server. */
  uuid_subscripcion_cliente: z.string().uuid().nullable(),
  /**
   * HU-F8.3 (reimpresión, directiva del operador 2026-09-25): necesario
   * para reconstruir el tiquete de entrada al reimprimir un ingreso
   * histórico (no viene de `PostIngresoResponse`, sino de esta búsqueda).
   */
  consecutivo: z.string().nullable().optional(),
  uuid_tipo_vehiculo: z.string().uuid().nullable().optional(),
});
export type Ingreso = z.infer<typeof IngresoSchema>;

export const IngresoArraySchema = z.array(IngresoSchema);

/** Derived state returned by `GET /operacion/ingresos/{uuid}/estado` (F1.6). */
export const IngresoEstadoSchema = z.object({
  /**
   * REGRESSION fix (2026-09-22, directiva del operador): el backend
   * retorna el campo como ``uuid_ingreso`` (matches the canonical BE
   * response field name in ``IngresoEstadoResponse``, see
   * ``backend/.../schemas/operacion.py:106-119``). El schema FE exigía
   * ``uuid`` y rompía el parseo — el operador veía "No se pudo
   * obtener la cotización" al tipear una placa con ingreso ya
   * cerrado (caso típico: TST999). El bug se manifestaba porque
   * ``SalidaPanel`` tenía un try/catch alrededor de ``getIngresoEstado``
   * que silenciaba el ZodError y caía al flujo normal (que también
   * falla porque el ingreso está cerrado → /cotizar 404).
   *
   * ``fecha_ingreso`` y ``uuid_sucursal`` son opcionales porque el FE
   * no los consume; ``.passthrough()`` permite que el BE agregue
   * campos en el futuro sin romper el cliente.
   */
  uuid_ingreso: z.string().uuid(),
  estado: z.enum(['abierto', 'cerrado', 'anulada']),
  fecha_ingreso: z.string().nullable().optional(),
  uuid_sucursal: z.string().uuid().nullable().optional(),
}).passthrough();
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
 * `getIngresosByConsecutivo(consecutivo)` — historical lookup by cupo
 * (HU-F8.3, directiva del operador 2026-09-25). Mirrors
 * `getIngresosByPlaca`: exact match, includes closed ingresos, no
 * `activo` filter — needed so reimpresión can find a no-placa vehicle
 * whose ticket already registered salida días atrás.
 */
export async function getIngresosByConsecutivo(consecutivo: string): Promise<Ingreso[]> {
  const params = new URLSearchParams({ consecutivo });
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
