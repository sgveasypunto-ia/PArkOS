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

/**
 * Type-guard for the ``seedAuth`` helper: ``Page`` and
 * ``BrowserContext`` overlap on most methods but the helper needs to
 * distinguish them to refuse ``transient`` branch scopes that target a
 * single page (the init script must outlive navigations).
 */
function isPage(target: BrowserContext | Page): target is Page {
  return typeof (target as Page).goto === 'function';
}

const AUTH_KEY = 'parkos.auth';
const BRANCH_KEY = 'parkos.lastSelectedSucursal';
const AUTH_VERSION = 1;

export interface SeedAuthOptions {
  accessToken: string;
  refreshToken?: string;
  /** ISO 8601 UTC. Defaults to 24 hours from now. */
  expiresAt?: string;
  /**
   * Branch uuid for the gate.
   *
   * ``persistent`` (default): the branch is planted via
   * ``addInitScript`` so every navigation (including ``page.reload()``)
   * re-seeds it. Safe for tests that do not modify the branch
   * mid-test.
   *
   * ``transient``: the branch is planted via ``page.evaluate`` AFTER
   * the first navigation completes, so a subsequent reload that the
   * user changes the branch on (the persistence-under-test scenario)
   * is not silently overwritten. Required by the branch-selector
   * reload spec.
   */
  branchUuid?: string;
  branchScope?: 'persistent' | 'transient';
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
  const branchScope = options.branchScope ?? 'persistent';

  // Branch goes through a separate channel so that ``transient``
  // scopes can plant it AFTER the first navigation completes — an
  // ``addInitScript`` would re-seed it on every reload and silently
  // overwrite whatever the test was trying to verify.
  if (branchScope === 'transient') {
    if (options.branchUuid === undefined) {
      throw new Error(
        'seedAuth: branchScope="transient" requires branchUuid',
      );
    }
    if (isPage(target)) {
      throw new Error(
        'seedAuth: branchScope="transient" must use a BrowserContext; '
          + 'the helper needs to attach to context.addInitScript so the '
          + 'plant survives page.evaluate across navigation.',
      );
    }
    await seedBranchTransient(
      target as BrowserContext,
      options.branchUuid,
    );
  }

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
      // When branchScope="transient" the branch is seeded separately
      // by ``seedBranchTransient`` — pass null here so this init
      // script does NOT clobber the test's writes on reload.
      branch:
        branchScope === 'persistent'
          ? options.branchUuid ?? null
          : null,
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

/**
 * Plant a branch uuid that survives exactly ONE navigation, not
 * every reload. Used together with ``seedAuth({branchScope: 'transient'})``
 * — the auth init script writes the token (every navigation), the
 * branch init script writes the branch ONLY if localStorage is empty
 * for that key, so the test's later writes via ``page.evaluate`` or
 * ``BranchSelector.onChange`` survive ``page.reload()``.
 *
 * Why this shape: reload re-runs every ``addInitScript``. A counter
 * on ``window`` cannot survive reload (the window is recreated), so
 * a "first-write-only" counter loses its memory at reload and would
 * re-plant. Reading the existing localStorage value, on the other
 * hand, persists across reload — the SPA's own ``setSelected`` wrote
 * it, and the helper does not overwrite an existing value.
 *
 * Tradeoff: this ONLY works for the branch-selection key, where the
 * helper's "if empty, plant Norte" is the right behaviour. It would
 * NOT work for a key the test expects to mutate freely (because the
 * helper would silently overwrite the test's mutation on the next
 * navigation). The branch-scope parameter is named to make that
 * intent obvious.
 */
async function seedBranchTransient(
  context: BrowserContext,
  branchUuid: string,
): Promise<void> {
  await context.addInitScript(
    ({ key, uuid }: { key: string; uuid: string }) => {
      if (window.localStorage.getItem(key) !== null) return;
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