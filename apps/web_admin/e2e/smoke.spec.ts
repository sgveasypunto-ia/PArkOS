import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * Smoke check — boots the PWA via the webServer config and confirms
 * the root redirect lands on the dashboard with the Parkos Admin
 * brand rendered. Then runs axe-core against the dashboard page to
 * keep the WCAG 2.1 AA gate green (RNF-022).
 */
test.describe('web_admin smoke', () => {
  test('root redirects to dashboard and renders Parkos Admin', async ({ page }) => {
    await page.goto('/');
    // / redirects to /dashboard; the dashboard h1 renders the brand.
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(
      page.getByRole('heading', { name: /Parkos Admin|Panel/i }),
    ).toBeVisible();
  });

  test('/dashboard has no WCAG 2.1 AA violations (axe-core)', async ({ page }) => {
    await page.goto('/dashboard');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });

  test('/login renders the login page', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByTestId('page-login')).toBeVisible();
  });
});
