/**
 * `miTurnoApi.ts` — HTTP layer for the per-turn aggregate endpoint
 * (HU-F12.1, frontend consumer of the BE `GET /api/v1/operacion/mi-turno`).
 *
 * Backend contract (REQ-OPS-184):
 *   - `GET /api/v1/operacion/mi-turno?uuid_sesion=X`
 *   - Returns the 7-field `MiTurnoRead` Pydantic, parsed here through
 *     `MiTurnoSchema` (Zod) before returning.
 *   - Permission `operacion:read` (seeded by F1.2); the BE issuer
 *     guard (`requires_issuer("operador-", "admin-")`) handles the
 *     JWT-level check.
 *   - Tenant scope: BE resolves `Sesion.uuid_sucursal` server-side
 *     (REQ-OPS-185) and rejects cross-branch with 403 — the FE does
 *     NOT need to send `uuid_sucursal`.
 *   - Response headers: `Cache-Control: no-store` (R-A6 mitigation).
 *
 * No raw `fetch` — every network access goes through `parkosFetch`.
 * No Idempotency-Key (GET read idempotent, RFC 7231 §4.2.1).
 */
import { parkosFetch } from '@parkos/ui-kit/fetch';

import { MiTurnoSchema } from '../../../lib/api/schemas/mi-turno';

/** Path — backend contract is REQ-OPS-184 + REQ-OPS-189. */
const MI_TURNO_PATH = '/api/v1/operacion/mi-turno';

/**
 * `GET /api/v1/operacion/mi-turno?uuid_sesion=X`.
 *
 * Errors propagate as `ParkosHttpError` (parkosFetch wraps everything):
 *   - 200 OK -> parsed `MiTurnoSchema` payload.
 *   - 401 -> parkosFetch handle401 Mutex refresh-once; if still 401,
 *           `useAuthStore.clear()` is fired by the hook's onError.
 *   - 403 -> propagated as-is (sesion_cross_branch_forbidden, terminal).
 *   - 404 -> propagated as-is (sesion_not_found, terminal).
 *   - 5xx -> retried 3x by parkosFetch, then propagated.
 */
export async function getMiTurno(uuid_sesion: string): Promise<unknown> {
  const params = new URLSearchParams({ uuid_sesion });
  const raw = await parkosFetch<unknown>(`${MI_TURNO_PATH}?${params.toString()}`);
  return MiTurnoSchema.parse(raw);
}