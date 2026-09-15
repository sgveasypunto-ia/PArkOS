/**
 * E2E tests for the lockout countdown flow (F3.2 — T4, DEC-F3.2-05 + DEC-F3.2-09).
 *
 * Sandbox F.6 caveat (verbatim design §13.4 + tasks §8):
 *   `npm 11.16.0` en sandbox refuses `workspace:*` resolution. El comando
 *   `pnpm playwright test e2e/auth/lockout.spec.ts` SKIP en este ambiente —
 *   precedent F2.1 + F2.2 + F2.3 + F3.1 archive reports documentan misma limitation.
 *   e2e G6 queda DEFERRED a CI matrix (Windows native npm 11.16+ o ubuntu-latest).
 *
 *   Unit tests (useCountdown.test.ts + LoginForm.test.tsx + Login.test.tsx)
 *   cubren el camino crítico: countdown baseline, cleanup, onComplete,
 *   drift resistance, form disabled, auto re-enable al llegar a 0.
 *
 * Scenarios (per plan.md:1315 + design.md §13.2):
 *   E1 — countdown-display: 4 intentos fallidos → 429 con `Retry-After` →
 *        assert `<p data-testid="login-countdown">` visible + texto
 *        `\d{2}:\d{2}` + form `disabled` (DEC-F3.2-09 — e2e usa 4 intentos
 *        para velocidad; backend default es 5 per auth.py:225 — verifica
 *        FLOW, no número exacto).
 *   E2 — countdown-decrements: countdown display decrece cada ~1000ms vía
 *        polling assertion.
 *   E3 — countdown-re-enable: mock countdown 2s + `waitForTimeout(3000)` +
 *        assert form re-enabled (submit NOT disabled, countdown display
 *        ya no visible).
 *   A1 — axe-core WCAG 2.1 AA en countdown state (G7 REQ-OPS-118 F3.2).
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const TEST_EMAIL = 'operador@sucursal-1.parkos.local';
const TEST_PASSWORD = 'valid-password-1234';

test.describe('Lockout countdown flow — F3.2 T4', () => {
  test('E1 — countdown-display: 4 intentos fallidos → 429 → countdown visible + form disabled', async ({ page }) => {
    let attempts = 0;
    const maxAttempts = 4;
    await page.route('**/api/v1/auth/login', (route) => {
      attempts++;
      if (attempts >= maxAttempts) {
        route.fulfill({
          status: 429,
          headers: { 'Retry-After': '300' },
          body: JSON.stringify({ detail: 'too_many_attempts' }),
        });
      } else {
        route.fulfill({
          status: 401,
          body: JSON.stringify({ detail: 'invalid_credentials' }),
        });
      }
    });

    await page.goto('/login');

    // Submit maxAttempts-1 invalid credentials
    for (let i = 0; i < maxAttempts - 1; i++) {
      await page.getByTestId('login-email').fill(TEST_EMAIL);
      await page.getByTestId('login-password').fill(`wrong-pass-${i}`);
      await page.getByTestId('login-submit').click();
      // Wait for either error alert or next state
      await page.waitForTimeout(100);
    }

    // The 4th attempt triggers 429 → countdown visible
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill('valid-password-1234');
    await page.getByTestId('login-submit').click();

    // Countdown display visible
    const countdown = page.getByTestId('login-countdown');
    await expect(countdown).toBeVisible({ timeout: 5_000 });
    await expect(countdown).toHaveAttribute('role', 'status');
    await expect(countdown).toHaveAttribute('aria-live', 'polite');

    // Format mm:ss (e.g., 05:00 for Retry-After=300)
    const text = (await countdown.textContent()) ?? '';
    expect(text).toMatch(/\d{2}:\d{2}/);

    // Form disabled during countdown (DEC-F3.2-02)
    const emailInput = page.getByTestId('login-email');
    const passwordInput = page.getByTestId('login-password');
    const submitButton = page.getByTestId('login-submit');
    await expect(emailInput).toBeDisabled();
    await expect(passwordInput).toBeDisabled();
    await expect(submitButton).toBeDisabled();
    await expect(submitButton).toHaveAttribute('aria-disabled', 'true');
  });

  test('E2 — countdown-decrements: display decrece cada ~1000ms', async ({ page }) => {
    // Single 429 attempt with 60s Retry-After
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 429,
        headers: { 'Retry-After': '60' },
        body: JSON.stringify({ detail: 'too_many_attempts' }),
      }),
    );

    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();

    const countdown = page.getByTestId('login-countdown');
    await expect(countdown).toBeVisible({ timeout: 5_000 });

    // Capture initial text (should be ~00:60 formatted as 01:00)
    const initial = (await countdown.textContent()) ?? '';
    expect(initial).toMatch(/\d{2}:\d{2}/);

    // Wait ~2500ms and re-read
    await page.waitForTimeout(2500);
    const after = (await countdown.textContent()) ?? '';
    expect(after).toMatch(/\d{2}:\d{2}/);

    // Extract seconds from both and verify decrement
    const initialSeconds = parseInt(initial.match(/\d{2}/)?.[0] ?? '0', 10) * 60 +
      parseInt(initial.match(/:\d{2}/)?.[0].replace(':', '') ?? '0', 10);
    const afterSeconds = parseInt(after.match(/\d{2}/)?.[0] ?? '0', 10) * 60 +
      parseInt(after.match(/:\d{2}/)?.[0].replace(':', '') ?? '0', 10);

    expect(afterSeconds).toBeLessThan(initialSeconds);
  });

  test('E3 — countdown-re-enable: countdown llega a 0 → form re-habilitado', async ({ page }) => {
    // Single 429 attempt with 2s Retry-After (short for fast test)
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 429,
        headers: { 'Retry-After': '2' },
        body: JSON.stringify({ detail: 'too_many_attempts' }),
      }),
    );

    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();

    const countdown = page.getByTestId('login-countdown');
    await expect(countdown).toBeVisible({ timeout: 5_000 });

    // Wait for countdown to expire (2s + buffer)
    await page.waitForTimeout(3000);

    // Form re-enabled: submit NOT disabled
    const submitButton = page.getByTestId('login-submit');
    await expect(submitButton).toBeEnabled();

    // Countdown display removed (post-isExpired state)
    await expect(countdown).not.toBeVisible();
  });

  test('A1 — axe-core WCAG 2.1 AA en countdown state (G7 REQ-OPS-118 F3.2)', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route) =>
      route.fulfill({
        status: 429,
        headers: { 'Retry-After': '300' },
        body: JSON.stringify({ detail: 'too_many_attempts' }),
      }),
    );

    await page.goto('/login');
    await page.getByTestId('login-email').fill(TEST_EMAIL);
    await page.getByTestId('login-password').fill(TEST_PASSWORD);
    await page.getByTestId('login-submit').click();

    // Wait for countdown to render
    await expect(page.getByTestId('login-countdown')).toBeVisible({ timeout: 5_000 });

    // Axe-core scan with WCAG 2.1 AA tags
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});
