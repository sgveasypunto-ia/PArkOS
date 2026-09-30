/**
 * `seedAuth.ts` — Plant the auth + branch-selection state in the
 * browser before navigation. Replaces the ad-hoc
 * ``localStorage.setItem('parkos.auth.token', ...)`` pattern that the
 * F2.2 auth store (Zustand + persist) silently broke: the real store
 * reads its envelope from ``parkos.auth`` under the
 * ``{ state, version }`` shape, NOT a flat token string.
 *
 * Wire shape that survived: ``localStorage["parkos.auth"] ===
 * JSON.stringify({ state: { accessToken, refreshToken, expiresAt },
 * version: 1 })``. The ``expiresAt`` ISO 8601 is derived server-side
 * from ``expires_in * 1000``; we pin a value 24 hours in the future
 * so the dashboard never has to refresh mid-test. ``refreshToken`` is
 * a non-empty string because the ``parkosFetch`` 401-refresh path (we
 * do not exercise it in E2E) would otherwise attempt the call with
 * ``null``.
 *
 * Branch selection lives in a separate ``parkos.lastSelectedSucursal``
 * key (T-PR10-12 requirement §10.4). The BranchSelector + RequireSucursal
 * gate both read it on hydration.
 *
 * ``seedBranchContext`` writes ONLY the branch key (no auth), for tests
 * that focus on the picker flow (login.spec.ts exercises the unauthenticated
 * path; a full login round-trip is out of scope for the helper).
 */
import type { BrowserContext, Page } from '@playwright/test';

const AUTH_KEY = 'parkos.auth';
const BRANCH_KEY = 'parkos.lastSelectedSucursal';
const AUTH_VERSION = 1;

export interface SeedAuthOptions {
  accessToken: string;
  refreshToken?: string;
  /** ISO 8601 UTC. Defaults to 24 hours from now. */
  expiresAt?: string;
  /** Branch uuid for the gate. */
  branchUuid?: string;
}

/**
 * Seed the Zustand auth envelope + optional branch selection in the
 * browser's localStorage before any page navigates.
 *
 * Pass ``context.addInitScript(seedAuthScript, options)`` so the seed
 * runs in the page's own context on every navigation; passing
 * ``page.evaluate(seedAuthScript, options)`` is fragile (race with
 * the React hydration that reads the store on mount).
 */
export async function seedAuth(
  target: BrowserContext | Page,
  options: SeedAuthOptions,
): Promise<void> {
  const expiresAt =
    options.expiresAt ??
    new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
  const refreshToken = options.refreshToken ?? 'refresh-token-fixture';

  await target.addInitScript(
    ({
      key,
      payload,
      branchKey,
      branch,
    }: {
      key: string;
      payload: string;
      branchKey: string;
      branch: string | null;
    }) => {
      window.localStorage.setItem(key, payload);
      if (branch !== null) {
        window.localStorage.setItem(branchKey, branch);
      }
    },
    {
      key: AUTH_KEY,
      payload: JSON.stringify({
        state: {
          accessToken: options.accessToken,
          refreshToken,
          expiresAt,
        },
        version: AUTH_VERSION,
      }),
      branchKey: BRANCH_KEY,
      branch: options.branchUuid ?? null,
    },
  );
}

/**
 * Seed ONLY the branch selection. For tests that drive the unauthenticated
 * flow (the login redirect requires the picker NOT to be satisfied).
 */
export async function seedBranchSelection(
  target: BrowserContext | Page,
  branchUuid: string,
): Promise<void> {
  await target.addInitScript(
    ({ key, uuid }: { key: string; uuid: string }) => {
      window.localStorage.setItem(key, uuid);
    },
    { key: BRANCH_KEY, uuid: branchUuid },
  );
}

/** Auth + branch selectors for typed fixtures. */
export const SEED_AUTH_KEYS = {
  auth: AUTH_KEY,
  branch: BRANCH_KEY,
} as const;

/**
 * Mock the auxiliary endpoints the SPA fires on almost every page
 * load so a 401 from any one of them doesn't tear the whole
 * session down (parkosFetch's 401-refresh-clear pipeline ends the
 * admin's login on a single unauthorized response — see
 * apps/ui-kit/src/store/authStore.ts::onError).
 *
 * This is the defensive net: per-spec handlers cover the endpoints
 * they actually assert against, and this helper ensures anything
 * else (catalogos, tarifa counts, the cups/billetes/admin/users
 * lazy fetches that fire after first paint) returns an empty
 * success response so the SPA doesn't redirect to /login.
 *
 * Adding a new SPA endpoint that triggers an unmocked 401 is the
 * fastest way to lose a test session: if you find one, add the
 * mock here rather than chasing the symptom in CI.
 */
export async function mockAuxiliaryEndpoints(
  context: BrowserContext,
): Promise<void> {
  // Catalog list endpoints: empty list shape (the same envelope
  // every catalog endpoint returns). If a new catalog endpoint is
  // added and the SPA fires it on first paint, the catch-all below
  // catches it.
  await context.route('**/api/v1/catalogos/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], next_cursor: null }),
    }),
  );
  await context.route('**/api/v1/empresa/sucursal*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [],
        next_cursor: null,
      }),
    }),
  );
  // The refresh endpoint: parkosFetch handles 401 by calling
  // refreshAccessToken and retrying with the new token (attempt=2).
  // On the SECOND 401 it gives up and returns the original res —
  // crucially WITHOUT calling authStore.clear(). Returning a 200 with
  // a fresh fake token here short-circuits the clear path: parkosFetch
  // sees a "successful refresh", retries the original call with the
  // fake token, the route-mocked endpoint responds 200 again (mock
  // ignores the header), the page gets its data, and the session
  // stays alive. Without this 401 the clear kills the admin's
  // session on the first unmocked endpoint.
  await context.route('**/api/v1/auth/refresh', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'refreshed-fake-token',
        refresh_token: 'refreshed-fake-refresh',
        expires_in: 3600,
      }),
    }),
  );
}