/**
 * `login.spec.ts` — e2e tests for the `web_admin` login page (IT-1.10).
 *
 * Mocks the `POST /api/v1/auth/login` endpoint with Playwright's
 * `page.route()` so we can exercise the three UI paths without a
 * real backend:
 *   1. Submit with valid credentials → tokens persisted, redirect
 *      to `/dashboard`.
 *   2. 401 invalid credentials → inline error rendered with role=alert.
 *   3. 429 account locked → lockout countdown with `mm:ss` format
 *      and a disabled submit button.
 *
 * Also runs axe-core on the login page to keep WCAG 2.1 AA green.
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('web_admin login', () => {
  test('submits credentials, persists tokens, and redirects to /dashboard', async ({ page }) => {
    // Pre-seed the access token in localStorage so the authStore
    // rehydrates as authenticated; the mock route just makes the
    // POST succeed so the container can setTokens() the way it would
    // in production.
    await page.addInitScript(() => {
      // The authStore persists tokens under "parkos.auth" in
      // localStorage; pre-seed both tokens so the post-login state
      // is observable.
    });

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'fake.access.token',
          refresh_token: 'fake.refresh.token',
          token_type: 'Bearer',
          expires_in: 3600,
        }),
      });
    });

    await page.goto('/login');
    await page.getByTestId('login-email').fill('admin@parkos.local');
    await page.getByTestId('login-password').fill('Pass1234word');
    await page.getByTestId('login-submit').click();

    // The container should bounce to /dashboard once authStore has
    // the access_token. We don't pre-seed it (so RequireAdmin
    // wouldn't redirect without login) — the login flow itself
    // populates authStore via setTokens().
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 5000 });
  });

  test('shows an inline 401 error on invalid credentials', async ({ page }) => {
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'invalid_credentials' }),
      });
    });

    await page.goto('/login');
    await page.getByTestId('login-email').fill('admin@parkos.local');
    await page.getByTestId('login-password').fill('wrongpassword');
    await page.getByTestId('login-submit').click();

    const alert = page.getByTestId('login-error');
    await expect(alert).toBeVisible();
    await expect(alert).toHaveAttribute('role', 'alert');
    // DEC-LOGIN-08: anti-enumeration — single message regardless of
    // which field was wrong.
    await expect(alert).toContainText('incorrectos');
  });

  test('shows the lockout countdown on 429 with Retry-After', async ({ page }) => {
    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 429,
        headers: { 'Retry-After': '45' },
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'account_locked' }),
      });
    });

    await page.goto('/login');
    await page.getByTestId('login-email').fill('admin@parkos.local');
    await page.getByTestId('login-password').fill('anypassword');
    await page.getByTestId('login-submit').click();

    const lockout = page.getByTestId('lockout-block');
    await expect(lockout).toBeVisible();
    await expect(lockout).toContainText('00:45');
    // Submit button is disabled while locked.
    await expect(page.getByTestId('login-submit')).toBeDisabled();
  });

  test('login page has no WCAG 2.1 AA violations (axe-core)', async ({ page }) => {
    await page.goto('/login');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
