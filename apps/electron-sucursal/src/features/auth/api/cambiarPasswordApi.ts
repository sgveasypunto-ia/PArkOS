/**
 * `cambiarPasswordApi.ts` -- POST /api/v1/auth/cambiar-password
 * (HU-F16 must-change enforcement, migration 0065).
 *
 * Espejo de ``apps/web_admin/src/features/auth/api/cambiarPasswordApi.ts``.
 * Se duplica (no se comparte en @parkos/ui-kit) por el mismo motivo que
 * ``loginApi.ts`` no se comparte -- F2.1 deferred la capa compartida al
 * paquete de UI para evitar arrastrar ``@parkos/ui-kit`` antes de que
 * tenga tests de verdad.
 *
 * El operador autenticado contra una credencial temporal la canjea aquí
 * por la TokenPair normal (con scope de sucursal + cookie ``parkos_session``
 * side-effect del handler). 401 con ``detail.invalid_temporary_token``
 * significa que el token expiró o no es de must-change -- el frontend lo
 * manda de vuelta al login normal.
 */
import { ParkosHttpError, resolveRequestUrl } from '@parkos/ui-kit/fetch';

import type { LoginResponse } from './loginApi';

const PATH = '/api/v1/auth/cambiar-password';

export class InvalidTemporaryTokenError extends Error {
  override readonly name = 'InvalidTemporaryTokenError';
}

export async function postCambiarPassword(
  temporaryToken: string,
  newPassword: string,
): Promise<LoginResponse> {
  const res = await fetch(resolveRequestUrl(PATH), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ temporary_token: temporaryToken, new_password: newPassword }),
  });

  if (!res.ok) {
    if (res.status === 401) {
      throw new InvalidTemporaryTokenError();
    }
    throw new ParkosHttpError(res.status, await res.text().catch(() => ''), res.url);
  }

  return (await res.json()) as LoginResponse;
}