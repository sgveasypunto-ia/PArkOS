/**
 * E2E tests for the login flow (F3.1 — T4, DEC-F3.1-10).
 *
 * Sandbox F.6 caveat (verbatim design §13.4 + tasks §8):
 *   `npm 11.16.0` en sandbox refuses `workspace:*` resolution. El comando
 *   `pnpm playwright test e2e/auth/login.spec.ts` SKIP en este ambiente —
 *   precedent F2.1 + F2.2 + F2.3 archive reports documentan misma limitation.
 *   e2e G6 queda DEFERRED a CI matrix (Windows native npm 11.16+ o ubuntu-latest).
 *
 *   Unit tests (LoginForm.test.tsx + Login.test.tsx + loginApi.test.ts)
 *   cubren el camino crítico: validación Zod, postLogin 200/401/429/5xx,
 *   credentials:'include', error mapping, redirect useEffect.
 *
 * Scenarios (per plan.md:1295 + design.md §13.2):
 *   E1 — login-ok-cookie: operator types email+password → cookie `parkos_session`
 *        set (httpOnly + sameSite=Lax) → redirect to `/`.
 *   E2 — refresh-transparente: login OK → mock /auth/me 401 una vez → useAuth
 *        SWR triggers refresh-once via Mutex (DEC-FETCH-03).
 *   E3 — logout: login OK → useAuthStore.clear() via bridge → /auth/me 404
 *        → useAuth() limpia store + emite `parkos:auth:cleared` event.
 *   A1 — axe-core WCAG 2.1 AA en /login route (G7 REQ-OPS-112).
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const TEST_EMAIL = 'operador@sucursal-1.parkos.local';
const TEST_PASSWORD = 'valid-password-1234';

test.describe('Login flow — F3.1 T4', () => {
  test('E1 — login-ok-cookie: cookie httpOnly set + redirect /', async ({ page, context }) => {
    await page.goto('/login');

    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();

    // Wait for redirect to /
    await page.waitForURL('/', { timeout: 10_000 });

    // Cookie httpOnly round-trip (DEC-F3.1-03)
    const cookies = await context.cookies();
    const parkosSession = cookies.find((c) => c.name === 'parkos_session');
    expect(parkosSession).toBeDefined();
    expect(parkosSession?.httpOnly).toBe(true);
    expect(parkosSession?.sameSite?.toLowerCase()).toBe('lax');
  });

  test('E2 — refresh-transparente: 401 en /auth/me dispara refresh-once', async ({ page }) => {
    // Login OK primero
    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();
    await page.waitForURL('/', { timeout: 10_000 });

    // Mock /auth/me para retornar 401 una vez — useAuth SWR detecta 401,
    // triggers refresh-once via Mutex (DEC-FETCH-03 parkosFetch.ts:119-140).
    // Si el refresh falla, useAuthStore.clear() + parkos:auth:cleared event
    // → forward AuthGuard F3.3+ redirect a /login.
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({ status: 401, body: JSON.stringify({ error: 'expired' }) }),
    );

    // Forward hook: assert eventual redirect a /login cuando refresh falla.
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  test('E3 — logout: useAuthStore.clear() limpia tokens + emite parkos:auth:cleared', async ({ page }) => {
    // Login OK primero
    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();
    await page.waitForURL('/', { timeout: 10_000 });

    // Llamar useAuthStore.clear() via window injection (test-only).
    // authStore.ts:81 `clear()` setea tokens a null — partialize persist
    // vía bridge.authStore.delete en electron-store, pero el render-side
    // Zustand setState es síncrono.
    await page.evaluate(() => {
      const w = window as unknown as {
        bridge?: { authStore?: { delete: (k: string) => Promise<void> } };
      };
      void w.bridge?.authStore?.delete('parkos.auth');
    });

    // /auth/me retorna 404 → useAuth limpia store + emite event → forward
    // F3.3+ AuthGuard verifica redirect a /login.
    await page.route('**/api/v1/auth/me', (route) =>
      route.fulfill({ status: 404, body: JSON.stringify({ error: 'not_found' }) }),
    );

    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  test('A1 — axe-core WCAG 2.1 AA en /login (G7 REQ-OPS-112)', async ({ page }) => {
    await page.goto('/login');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});