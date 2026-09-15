/**
 * Unit tests for `postLogin` (F3.1 — T2, DEC-F3.1-03/04/05/08).
 *
 * TDD strict RED → GREEN → REFACTOR coverage:
 *   U1: 200 OK → retorna `TokenPair` parseado.
 *   U2: 401 → throws `InvalidCredentialsError` (DEC-F3.1-08 anti-enumeración).
 *   U3: 429 + Retry-After → throws `AccountLockedError(retryAfterSeconds)`.
 *   U4: 5xx → throws `ParkosHttpError` (fallback genérico F2.2).
 *   U5: request lleva `credentials:'include'` + Content-Type JSON.
 *
 * Mocking strategy: `vi.spyOn(global, 'fetch')` (no MSW 2.x — design §2.8
 * confirma que MSW no está en deps y F2.2 precedent usa `vi.spyOn(fetch)`).
 */
import { describe, it, expect, vi, afterEach } from 'vitest';

import { ParkosHttpError } from '@parkos/ui-kit/fetch';

import {
  postLogin,
  InvalidCredentialsError,
  AccountLockedError,
} from './loginApi';

function mockFetchOnce(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
    text: async () => JSON.stringify(body),
    url: '/api/v1/auth/login',
  } as unknown as Response;
}

describe('postLogin', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('U1: 200 OK retorna TokenPair parseado', async () => {
    const tokenPair = {
      access_token: 'a-1',
      refresh_token: 'r-1',
      token_type: 'Bearer',
      expires_in: 3600,
    };
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce(tokenPair, 200, { 'Content-Type': 'application/json' }),
    );

    const pair = await postLogin('op@test.co', 'password1234');

    expect(pair).toEqual(tokenPair);
    expect(pair.access_token).toBe('a-1');
    expect(pair.expires_in).toBe(3600);
  });

  it('U2: 401 throws InvalidCredentialsError', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce({ error: 'invalid_credentials' }, 401),
    );

    await expect(postLogin('op@test.co', 'wrong-pass-1234')).rejects.toBeInstanceOf(
      InvalidCredentialsError,
    );
  });

  it('U3: 429 + Retry-After throws AccountLockedError con retryAfterSeconds', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce(
        { error: 'account_locked', retry_after_seconds: 600 },
        429,
        { 'Retry-After': '600' },
      ),
    );

    try {
      await postLogin('op@test.co', 'wrong-pass-1234');
      expect.fail('expected AccountLockedError');
    } catch (err) {
      expect(err).toBeInstanceOf(AccountLockedError);
      expect((err as AccountLockedError).retryAfterSeconds).toBe(600);
    }
  });

  it('U3b: 429 sin Retry-After header → retryAfterSeconds = 0', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce({ error: 'account_locked' }, 429),
    );

    try {
      await postLogin('op@test.co', 'wrong-pass-1234');
      expect.fail('expected AccountLockedError');
    } catch (err) {
      expect(err).toBeInstanceOf(AccountLockedError);
      expect((err as AccountLockedError).retryAfterSeconds).toBe(0);
    }
  });

  it('U4: 500 throws ParkosHttpError', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce({ error: 'server_error' }, 500),
    );

    await expect(postLogin('op@test.co', 'password1234')).rejects.toBeInstanceOf(
      ParkosHttpError,
    );
  });

  it('U5: request lleva credentials:include + Content-Type JSON + body JSON', async () => {
    const spy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        mockFetchOnce(
          { access_token: 'a', refresh_token: 'r', token_type: 'Bearer', expires_in: 3600 },
          200,
        ),
      );

    await postLogin('op@test.co', 'password1234');

    expect(spy).toHaveBeenCalledTimes(1);
    const [url, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/auth/login');
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(init.body).toBe(JSON.stringify({ email: 'op@test.co', password: 'password1234' }));
  });

  it('U5b: 422 validation_error throws ParkosHttpError (fallback)', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      mockFetchOnce({ error: 'validation_error' }, 422),
    );

    await expect(postLogin('op@test.co', 'short')).rejects.toBeInstanceOf(ParkosHttpError);
  });
});