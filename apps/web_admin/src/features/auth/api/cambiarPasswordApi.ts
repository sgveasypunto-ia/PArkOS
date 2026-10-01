/**
 * `cambiarPasswordApi.ts` — POST /api/v1/auth/cambiar-password
 * (HU-F16 must-change enforcement, migration 0065).
 *
 * The operator authenticates against a temporary credential issued by
 * ``POST /admin/usuarios/{uuid}/reset-password``; the login handler
 * returns a 5-minute JWT with ``purpose='must_change'`` instead of the
 * normal pair. This module exchanges that temp token + a new password
 * for the regular TokenPair (with branch scope attached and the
 * ``parkos_session`` cookie set as a side-effect of the BE handler).
 *
 * Errors are deliberately narrow: 401 with ``detail.invalid_temporary_token``
 * when the token is malformed, expired, or not a must-change token. The
 * ``CambiarPasswordForm`` surfaces that as a single message ("the
 * temporary credential expired; please log in again") and the operator
 * starts over from the normal LoginForm.
 */
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import type { LoginResponse } from './loginApi';

const PATH = '/api/v1/auth/cambiar-password';

export class InvalidTemporaryTokenError extends Error {
  override readonly name = 'InvalidTemporaryTokenError';
}

/**
 * Exchange a temporary credential for a normal TokenPair.
 *
 * Throws:
 *   - `InvalidTemporaryTokenError` on 401 (expired, malformed, or a
 *     non-must-change token -- all three collapse into the same UX).
 *   - The underlying `ParkosHttpError` on any other 4xx/5xx -- treated
 *     as a generic retryable error.
 *
 * Returns the same `LoginResponse` shape as ``postLogin``, but with
 * ``must_change_password=false`` and a real access/refresh pair --
 * the caller can stash these and redirect to ``nextPath`` as if it
 * had just logged in normally.
 */
export async function postCambiarPassword(
  temporaryToken: string,
  newPassword: string,
): Promise<LoginResponse> {
  let response: Response;
  try {
    response = await fetch(PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ temporary_token: temporaryToken, new_password: newPassword }),
    });
  } catch (networkError) {
    throw new ParkosHttpError(
      0,
      networkError instanceof Error ? networkError.message : 'network_error',
      PATH,
    );
  }

  if (response.status === 401) {
    throw new InvalidTemporaryTokenError();
  }

  if (!response.ok) {
    let bodyText = '';
    try {
      bodyText = await response.text();
    } catch {
      /* ignore */
    }
    throw new ParkosHttpError(response.status, bodyText, PATH);
  }

  return (await response.json()) as LoginResponse;
}