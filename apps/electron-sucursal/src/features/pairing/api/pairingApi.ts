/**
 * `pairingApi.ts` — HTTP layer for the branch's first-boot pairing
 * (IT-2.8, REQ-OP-15).
 *
 * NO auth header — the plaintext pairing-token IS the credential
 * (matches `backend/.../sync_router.py::_PairRequest` semantics).
 *
 * Endpoints consumed:
 *   - POST /api/v1/sync/pair  → 201 { sync_jwt, expires_at, uuid_sucursal }
 *                                  410 pairing_token_consumed | _expired | _not_found
 *                                  422 malformed body
 *
 * The response JWT is a long-lived `sync-agent-` token (30 days) that
 * the kiosk then persists via the electron-store bridge under
 * `parkos.sync_jwt`. The first-boot wizard stores it there and the
 * app boots normally on subsequent launches.
 */
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

const PAIR_PATH = '/api/v1/sync/pair';

export interface BranchInfo {
  hostname?: string;
  os?: string;
  version?: string;
  endpoint_url?: string;
}

export interface PairRequest {
  pairing_token: string;
  uuid_sucursal: string;
  branch_info?: BranchInfo;
}

export interface PairResponse {
  sync_jwt: string;
  expires_at: string;
  uuid_sucursal: string;
}

export class PairingTokenInvalidError extends Error {
  override readonly name = 'PairingTokenInvalidError';
  /** Server-given reason: consumed / expired / not_found. */
  constructor(public readonly reason: string) {
    super(`Pairing token invalid: ${reason}`);
  }
}

export async function postPair(request: PairRequest): Promise<PairResponse> {
  let response: Response;
  try {
    response = await fetch(PAIR_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
  } catch (networkError) {
    throw new ParkosHttpError(
      0,
      networkError instanceof Error ? networkError.message : 'network_error',
      PAIR_PATH,
    );
  }

  if (response.status === 410) {
    let body: Record<string, unknown> = {};
    try {
      body = (await response.json()) as Record<string, unknown>;
    } catch {
      /* ignore */
    }
    const reason = typeof body['error'] === 'string' ? body['error'] : 'consumed';
    throw new PairingTokenInvalidError(reason);
  }

  if (!response.ok) {
    let bodyText = '';
    try {
      bodyText = await response.text();
    } catch {
      /* ignore */
    }
    throw new ParkosHttpError(response.status, bodyText, PAIR_PATH);
  }

  return (await response.json()) as PairResponse;
}
