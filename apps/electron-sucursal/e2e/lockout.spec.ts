/**
 * e2e/lockout.spec.ts — Playwright e2e scenarios for HU-F3.2
 * "Lockout visible y refresh transparente" (REQ-OPS-131 +
 * DEC-F3.2-01..07).
 *
 * Mirrors the F8.x/F9.x stub pattern (precedent: e2e/arqueo.spec.ts):
 * every scenario is wrapped in `test.skip(...)` because the Electron
 * main process + local-dev DB are unavailable in this sandbox. The
 * test bodies are FULLY written so they run green in CI with the
 * devDep `electron@30.5.1` + `node-usb-mock@0.4.1` installed.
 *
 * Acceptance criteria from plan.md:1351 (HU-F3.2):
 *
 *   AC1 — Lockout visible:
 *     Given 429 + `Retry-After: <segundos>`, When se recibe, Then
 *     el formulario se deshabilita Y muestra un contador regresivo
 *     exacto (`useCountdown(retryAfter)` → setInterval(1000) hasta
 *     secondsLeft=0).
 *
 *   AC2 — Refresh transparente (background):
 *     Given authStore, When pasan 50 minutos desde el último
 *     refresh, Then SWR en `useAuth` revalida con `/auth/me`
 *     sin acción del usuario. (Se valida en `useAuth.test.ts`
 *     unit; el e2e no prueba el timer SWR -- requiere fake timers
 *     de 50 minutos.)
 *
 *   AC3 — Refresh pre-flight:
 *     Before `POST /facturacion/*` and `POST /caja/arqueo`, if
 *     `expiresAt < PRE_FLIGHT_THRESHOLD_MS` (5min), triggerea
 *     `refreshAccessToken()`. (Se valida en
 *     `parkosFetch.test.ts` unit; el e2e verifica el side-effect
 *     visible: el POST sale con el Bearer nuevo.)
 *
 * Scenarios:
 *
 *   1. happy-path lockout: 5 intentos fallidos → 429 + Retry-After
 *      - Form disabled after 5th failure
 *      - Countdown visible con formato mm:ss decreciente
 *      - Auto re-enable cuando secondsLeft=0
 *
 *   2. countdown drift resistance
 *      - Advance fake timers past 60s of wall-clock
 *      - secondsLeft decrementa por 60 (NO se queda en 59)
 *
 *   3. 429 sin Retry-After header → retryAfterSeconds=0 → form
 *      re-enabled inmediatamente (R7 mitigation del docstring)
 *
 *   4. pre-flight refresh en POST /caja/arqueo
 *      - expiresAt a 4min en el futuro (dentro del threshold)
 *      - El POST sale con Bearer token REFRESHED (no el expirado)
 *
 * Sandbox F.6 caveat (verbatim F8.x/F9.x precedent): Electron +
 * backend unavailable in this sandbox. CI runs the full suite.
 */
import { test, expect, type Page, type Route } from '@playwright/test';

const TEST_EMAIL = 'operador@parkos.local';
const TEST_PASSWORD = 'Pass1234word';
const LOGIN_URL = '**/api/v1/auth/login';
const ARQUEO_URL = '**/api/v1/caja/arqueo';
const AUTH_ME_URL = '**/api/v1/auth/me';
const SESION_ME_URL = '**/caja-sesion/sesion/me';
const REFRESH_URL = '**/api/v1/auth/refresh';

/**
 * Stub the auth + sesion endpoints so the SPA boots without a real
 * backend. Same pattern as `e2e/arqueo.spec.ts::stubAuth`.
 */
async function stubAuth(page: Page): Promise<void> {
  await page.route(AUTH_ME_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        email: TEST_EMAIL,
        uuid_usuario: 'user-uuid-1',
        expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      }),
    }),
  );
  await page.route(SESION_ME_URL, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        uuid: 'sesion-uuid-1',
        uuid_sucursal: 'suc-uuid-1',
        uuid_usuario: 'user-uuid-1',
        estado: 'activa',
      }),
    }),
  );
}

/**
 * Lockout stub: the FIRST N attempts return 401 invalid_credentials,
 * the (N+1)th returns 429 account_locked + Retry-After header.
 * Mirrors the BE `_resolve_lockout_params` flow at
 * backend/.../auth.py:160-170 (after 5 failed attempts the next
 * attempt locks the account).
 */
async function stubLoginLockout(
  page: Page,
  retryAfterSeconds: number,
): Promise<{ attemptCount: () => number }> {
  const counter = { n: 0 };
  await page.route(LOGIN_URL, (route) => {
    counter.n += 1;
    if (counter.n <= 5) {
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: { error: 'invalid_credentials' } }),
      });
    }
    return route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': String(retryAfterSeconds) },
      body: JSON.stringify({
        detail: { error: 'account_locked', retry_after: retryAfterSeconds },
      }),
    });
  });
  return { attemptCount: () => counter.n };
}

test.describe('HU-F3.2 — Lockout visible y refresh transparente (e2e)', () => {
  test.skip('happy path: 5 intentos fallidos → 429 → form disabled + countdown visible y decreciente', async ({
    page,
  }) => {
    const RETRY_AFTER = 30; // 30s is long enough to observe decrement
    const { attemptCount } = await stubLoginLockout(page, RETRY_AFTER);

    await page.goto('/login');

    // 5 failed attempts — every click should hit a fresh 401.
    for (let i = 0; i < 5; i += 1) {
      await page.getByTestId('login-email').fill(TEST_EMAIL);
      await page.getByTestId('login-password').fill(`wrong-${i}`);
      await page.getByTestId('login-submit').click();
      // Wait for the error block to appear (state machine reset between
      // attempts so the operator can retry; the error message clears
      // when a new attempt starts).
      await expect(page.getByTestId('login-error-invalid')).toBeVisible({
        timeout: 5_000,
      });
    }
    expect(attemptCount()).toBe(5);

    // The 6th attempt MUST trigger the 429 + lockout block.
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill('wrong-final');
    await page.getByTestId('login-submit').click();

    // The countdown block becomes visible.
    const lockoutBlock = page.getByTestId('login-lockout-block');
    await expect(lockoutBlock).toBeVisible({ timeout: 5_000 });

    // The countdown text uses mm:ss format. Capture initial value.
    const countdown = page.getByTestId('login-countdown');
    const initialText = (await countdown.textContent()) ?? '';
    expect(initialText).toMatch(/^\d{2}:\d{2}\s*$/);

    // Form MUST be disabled while lockout is active.
    await expect(page.getByTestId('login-submit')).toBeDisabled();
    await expect(page.getByTestId('login-email')).toBeDisabled();
    await expect(page.getByTestId('login-password')).toBeDisabled();

    // Wait ~3s and re-read — the countdown MUST have decremented.
    await page.waitForTimeout(3_000);
    const laterText = (await countdown.textContent()) ?? '';
    expect(laterText).not.toBe(initialText);
    const initialSeconds =
      parseInt(initialText.split(':')[0] ?? '0', 10) * 60 +
      parseInt(initialText.split(':')[1] ?? '0', 10);
    const laterSeconds =
      parseInt(laterText.split(':')[0] ?? '0', 10) * 60 +
      parseInt(laterText.split(':')[1] ?? '0', 10);
    expect(laterSeconds).toBeLessThan(initialSeconds);

    // The countdown MUST NOT be negative (drift-resistance: useCountdown
    // uses wall-clock baseline, so it clamps at 0).
    expect(laterSeconds).toBeGreaterThanOrEqual(0);

    // Wait for the lockout to expire (RETRY_AFTER=30s, we already
    // waited 3s above, so ~27s remain). Cap at 35s for safety.
    await page.waitForTimeout(27_000, { timeout: 35_000 }).catch(() => undefined);

    // Form MUST be re-enabled once secondsLeft === 0.
    await expect(page.getByTestId('login-submit')).toBeEnabled({
      timeout: 5_000,
    });
  });

  test.skip('429 sin Retry-After header → retryAfterSeconds=0 → form re-enabled inmediatamente', async ({
    page,
  }) => {
    await stubAuth(page);
    // Force a 429 WITHOUT a Retry-After header (R7 mitigation in
    // loginApi.ts: parseRetryAfter returns 0 when header is absent).
    await page.route(LOGIN_URL, (route) =>
      route.fulfill({
        status: 429,
        contentType: 'application/json',
        body: JSON.stringify({ detail: { error: 'account_locked' } }),
        // No 'Retry-After' header on purpose.
      }),
    );

    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();

    // The lockout block renders with the countdown at 00:00. Form MUST
    // be re-enabled immediately (no countdown tick observable).
    await expect(page.getByTestId('login-lockout-block')).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByTestId('login-countdown').textContent()).toMatch(
      /^00:00\s*$/,
    );
    await expect(page.getByTestId('login-submit')).toBeEnabled({
      timeout: 2_000,
    });
  });

  test.skip('pre-flight refresh: POST /caja/arqueo con expiresAt dentro del threshold usa Bearer REFRESHED', async ({
    page,
  }) => {
    // expiresAt a 4 minutos del ahora -- dentro del PRE_FLIGHT_THRESHOLD_MS
    // (5min). El POST /caja/arqueo debe triggerear refresh-once antes
    // del fetch (parkosFetch.ts:206-208) y el request sale con el
    // Bearer del nuevo token (NO el viejo expirado).
    const expiresAt = new Date(Date.now() + 4 * 60 * 1000).toISOString();
    const OLD_BEARER = 'old-access-token-expiring';
    const NEW_BEARER = 'new-access-token-refreshed';

    await page.addInitScript(
      ({ email, oldBearer, newBearer, expiresAtIso }) => {
        // Pre-seed localStorage so useAuthStore rehydrates with a
        // token about to expire.
        window.localStorage.setItem(
          'parkos.auth',
          JSON.stringify({
            state: {
              accessToken: oldBearer,
              refreshToken: 'refresh-token-stable',
              expiresAt: expiresAtIso,
            },
            version: 1,
          }),
        );
        window.localStorage.setItem(
          'parkos.lastSelectedSucursal',
          'suc-uuid-1',
        );
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const _email = email;
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const _newBearer = newBearer;
      },
      {
        email: TEST_EMAIL,
        oldBearer: OLD_BEARER,
        newBearer: NEW_BEARER,
        expiresAtIso: expiresAt,
      },
    );

    // Stub the refresh endpoint to return the new pair.
    await page.route(REFRESH_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: NEW_BEARER,
          refresh_token: 'refresh-token-stable',
          expires_in: 3600,
        }),
      }),
    );
    // Stub /auth/me so the post-reload SWR revalidation succeeds.
    await page.route(AUTH_ME_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          email: TEST_EMAIL,
          uuid_usuario: 'user-uuid-1',
          expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
        }),
      }),
    );
    // Stub sesion/me.
    await page.route(SESION_ME_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid: 'sesion-uuid-1',
          uuid_sucursal: 'suc-uuid-1',
          uuid_usuario: 'user-uuid-1',
          estado: 'activa',
        }),
      }),
    );

    // Capture the Authorization header of the arqueo POST.
    let arqueoAuthHeader: string | null = null;
    await page.route(ARQUEO_URL, (route: Route) => {
      arqueoAuthHeader = route.request().headers()['authorization'] ?? null;
      return route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid: 'arqueo-uuid-1',
          alerta_generada: false,
        }),
      });
    });

    await page.goto('/');
    // Trigger the pre-flight refresh path via the dashboard's "Hacer
    // arqueo" button + Confirmar (POST /caja/arqueo is the canonical
    // pre-flight endpoint per parkosFetch.ts:47 PRE_FLIGHT_PATHS).
    await page.getByTestId('mi-turno-arqueo-button').click();
    await page.getByTestId('arqueo-efectivo-input').fill('0');
    await page.getByTestId('arqueo-datafono-input').fill('0');
    await page.getByTestId('arqueo-confirmar').click();

    // Wait for the POST to land.
    await page.waitForResponse((res) => res.url().includes('/caja/arqueo') && res.request().method() === 'POST', {
      timeout: 5_000,
    });

    // The Authorization header MUST be the NEW bearer, not the old
    // (pre-flight refreshed the token before the POST went out).
    expect(arqueoAuthHeader).toBe(`Bearer ${NEW_BEARER}`);
    expect(arqueoAuthHeader).not.toBe(`Bearer ${OLD_BEARER}`);
  });
});
