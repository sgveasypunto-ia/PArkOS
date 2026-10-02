/**
 * `pairingApi.ts` — HTTP client for the admin pairing-token + revoke-
 * sync endpoints (HU-F19.3 "Pairing de sucursales").
 *
 * Endpoints consumed (all require permission `gestionar_dian`, already
 * seeded server-side; mounted on `api_admin`):
 *
 * - `POST /api/v1/admin/pairing-tokens`                      -- issue
 * - `GET  /api/v1/admin/pairing-tokens/{uuid}`                -- read status
 * - `POST /api/v1/admin/pairing-tokens/{uuid}/revoke`         -- revoke (idempotent)
 * - `POST /api/v1/admin/sucursales/{uuid}/revoke-sync`        -- revoke a live sync credential (idempotent)
 *
 * Four typed errors surfaced from the backend, mirroring the
 * `SucursalDeshabilitarBloqueadoError` / `cuposApi.ts` convention of
 * parsing the `{ detail: { error, ... } }` body shape into a friendly
 * Spanish `Error` subclass instead of a generic 4xx message:
 *
 *   - `InvalidTtlHoursError` (422 `invalid_ttl_hours`)
 *   - `PairingTokenRateLimitedError` (429 `pairing_token_rate_limited`
 *     -- confirmed from source + tests: this response carries NO
 *     retry-after/reset timestamp anywhere, so the message is a static
 *     policy statement, never a fabricated countdown)
 *   - `TenantScopeViolationError` (403 `tenant_scope_violation`)
 *   - `PairingTokenNotFoundError` (404 `not_found`)
 */
import { parkosFetchRaw } from '@parkos/ui-kit/fetch';

import {
  pairingTokenIssueResponseSchema,
  pairingTokenReadSchema,
  MAX_TTL_HOURS,
  type PairingTokenIssueResponse,
  type PairingTokenRead,
} from './pairingSchema';

const jsonHeaders = {
  Accept: 'application/json',
  'Content-Type': 'application/json',
};

function detailOf(bodyText: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(bodyText) as unknown;
    if (typeof parsed === 'object' && parsed !== null && 'detail' in parsed) {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === 'object' && detail !== null) {
        return detail as Record<string, unknown>;
      }
    }
  } catch {
    // Not JSON (or shape mismatch) -- callers fall back to a static message.
  }
  return null;
}

/** 422 `invalid_ttl_hours` -- `ttl_hours` outside the backend's 1..168 bound. */
export class InvalidTtlHoursError extends Error {
  constructor(bodyText: string) {
    const detail = detailOf(bodyText);
    const backendDetail = typeof detail?.detail === 'string' ? detail.detail : null;
    super(
      `El TTL ingresado no es válido${backendDetail ? ` (${backendDetail})` : ''}. Debe estar entre 1 y ${MAX_TTL_HOURS} horas.`,
    );
    this.name = 'InvalidTtlHoursError';
  }
}

/**
 * 429 `pairing_token_rate_limited` -- 6th pairing-token request in the
 * rolling hour for this admin (limit confirmed server-side: 5/hour).
 * The response body carries no retry-after/reset timestamp (checked
 * against the backend source + its tests), so this message is a
 * static policy statement rather than a fabricated countdown.
 */
export class PairingTokenRateLimitedError extends Error {
  constructor() {
    super(
      'Alcanzaste el límite de 5 tokens de pairing por hora para este administrador. Esperá un momento antes de generar otro.',
    );
    this.name = 'PairingTokenRateLimitedError';
  }
}

/** 403 `tenant_scope_violation`. */
export class TenantScopeViolationError extends Error {
  constructor() {
    super('No tenés acceso a este recurso en este tenant.');
    this.name = 'TenantScopeViolationError';
  }
}

/** 404 `not_found` -- the pairing-token uuid does not exist (or isn't yours). */
export class PairingTokenNotFoundError extends Error {
  constructor(uuid: string) {
    super(`El token de pairing ${uuid} no existe o ya no está disponible.`);
    this.name = 'PairingTokenNotFoundError';
  }
}

export interface IssuePairingTokenInput {
  uuidSucursal?: string | null;
  ttlHours: number;
}

export async function issuePairingToken(
  input: IssuePairingTokenInput,
): Promise<PairingTokenIssueResponse> {
  const res = await parkosFetchRaw('/api/v1/admin/pairing-tokens', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({
      uuid_sucursal: input.uuidSucursal ?? null,
      ttl_hours: input.ttlHours,
    }),
  });

  if (res.ok) {
    return pairingTokenIssueResponseSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 422) throw new InvalidTtlHoursError(bodyText);
  if (res.status === 429) throw new PairingTokenRateLimitedError();
  if (res.status === 403) throw new TenantScopeViolationError();
  throw new Error(
    `pairingApi: POST /admin/pairing-tokens -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}

export async function getPairingToken(uuid: string): Promise<PairingTokenRead> {
  const res = await parkosFetchRaw(`/api/v1/admin/pairing-tokens/${uuid}`, {
    method: 'GET',
    headers: jsonHeaders,
  });
  if (res.ok) {
    return pairingTokenReadSchema.parse(await res.json());
  }
  const bodyText = await res.text();
  if (res.status === 404) throw new PairingTokenNotFoundError(uuid);
  if (res.status === 403) throw new TenantScopeViolationError();
  throw new Error(
    `pairingApi: GET /admin/pairing-tokens/${uuid} -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}

export async function revokePairingToken(uuid: string): Promise<void> {
  const res = await parkosFetchRaw(`/api/v1/admin/pairing-tokens/${uuid}/revoke`, {
    method: 'POST',
    headers: jsonHeaders,
  });
  if (res.ok) return; // 204, idempotent -- revoking twice is still success.
  const bodyText = await res.text();
  if (res.status === 404) throw new PairingTokenNotFoundError(uuid);
  if (res.status === 403) throw new TenantScopeViolationError();
  throw new Error(
    `pairingApi: POST /admin/pairing-tokens/${uuid}/revoke -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}

export interface RevokeSucursalSyncInput {
  jwtKid: string;
  jwtUuid: string;
}

/**
 * Revokes an already-paired device's live sync credential. This is a
 * DIFFERENT artifact from a pairing token -- there is no backend
 * lookup to auto-discover a branch's current `jwt_kid`/`jwt_uuid`, so
 * the admin must know/paste them (e.g. from audit logs). Manual/
 * advanced action by design.
 */
export async function revokeSucursalSync(
  uuidSucursal: string,
  input: RevokeSucursalSyncInput,
): Promise<void> {
  const res = await parkosFetchRaw(`/api/v1/admin/sucursales/${uuidSucursal}/revoke-sync`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ jwt_kid: input.jwtKid, jwt_uuid: input.jwtUuid }),
  });
  if (res.ok) return; // 204, idempotent.
  const bodyText = await res.text();
  if (res.status === 403) throw new TenantScopeViolationError();
  if (res.status === 422) {
    throw new Error(
      `Datos inválidos para revocar la sincronización: ${bodyText.slice(0, 200)}`,
    );
  }
  throw new Error(
    `pairingApi: POST /admin/sucursales/${uuidSucursal}/revoke-sync -> ${res.status}: ${bodyText.slice(0, 200)}`,
  );
}
