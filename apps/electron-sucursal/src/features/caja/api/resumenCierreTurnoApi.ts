/**
 * `resumenCierreTurnoApi.ts` — HTTP layer for the post-close turn summary
 * (PT-5): `GET /api/v1/operacion/mi-turno/resumen-cierre?uuid_sesion=X`.
 *
 * Read-only, additive endpoint (MiTurnoRead is untouched). The BE pins the
 * sesion to the caller's branch AND to the operator that owns it, so the
 * FE sends only `uuid_sesion`. Called BEFORE the logout of the closing
 * flow — the bearer token must still be in the auth store.
 *
 * No raw `fetch`: everything goes through `parkosFetch` (Authorization,
 * 401 refresh-once). GET → no Idempotency-Key.
 */
import { parkosFetch } from '@parkos/ui-kit/fetch';

import {
  ResumenCierreTurnoSchema,
  type ResumenCierreTurnoRead,
} from '../../../lib/api/schemas/resumen-cierre-turno';

const RESUMEN_CIERRE_PATH = '/api/v1/operacion/mi-turno/resumen-cierre';

export async function getResumenCierreTurno(
  uuid_sesion: string,
): Promise<ResumenCierreTurnoRead> {
  const params = new URLSearchParams({ uuid_sesion });
  const raw = await parkosFetch<unknown>(`${RESUMEN_CIERRE_PATH}?${params.toString()}`);
  return ResumenCierreTurnoSchema.parse(raw);
}
