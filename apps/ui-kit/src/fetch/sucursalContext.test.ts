import { afterEach, describe, expect, it } from 'vitest';

import {
  SUCURSAL_STORAGE_KEY,
  decodeJwtClaims,
  syncSucursalContextFromAccessToken,
} from './sucursalContext';

function jwt(payload: Record<string, unknown>): string {
  const enc = (o: unknown): string =>
    btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${enc({ alg: 'RS256' })}.${enc(payload)}.sig`;
}

afterEach(() => window.localStorage.clear());

describe('sucursalContext', () => {
  it('decodes claims and tolerates malformed tokens', () => {
    expect(decodeJwtClaims(jwt({ iss: 'admin-x', sucursal: 's1' }))).toEqual({
      iss: 'admin-x',
      sucursal: 's1',
    });
    expect(decodeJwtClaims('garbage')).toBeNull();
    expect(decodeJwtClaims('a.%%%.c')).toBeNull();
  });

  it('stores the sucursal claim for admin- tokens', () => {
    const out = syncSucursalContextFromAccessToken(jwt({ iss: 'admin-k', sucursal: 'suc-1' }));
    expect(out).toBe('suc-1');
    expect(window.localStorage.getItem(SUCURSAL_STORAGE_KEY)).toBe('suc-1');
  });

  it('removes a stale value for operador- tokens', () => {
    window.localStorage.setItem(SUCURSAL_STORAGE_KEY, 'old');
    const out = syncSucursalContextFromAccessToken(jwt({ iss: 'operador-k', sucursal: 'suc-1' }));
    expect(out).toBeNull();
    expect(window.localStorage.getItem(SUCURSAL_STORAGE_KEY)).toBeNull();
  });

  it('does not store when an admin token has no sucursal claim', () => {
    expect(syncSucursalContextFromAccessToken(jwt({ iss: 'admin-k' }))).toBeNull();
    expect(window.localStorage.getItem(SUCURSAL_STORAGE_KEY)).toBeNull();
  });
});
