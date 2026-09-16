import { test, expect, _electron as electron } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

/**
 * Scaffold smoke — boots the built Electron app and verifies:
 *   1. The window renders with title "Parkos Sucursal" and the
 *      `<h1>Parkos Sucursal</h1>` heading is visible (RNF-022 baseline).
 *   2. The root route has zero WCAG 2.1 AA violations when audited
 *      by axe-core (RNF-022 + DEC-ELEC-07 from day one).
 *
 * These tests target the packaged Electron app at `out/main.js`. The
 * CI workflow builds before invoking Playwright (`npm run build:main`
 * then `npm run build:renderer`).
 */
test.describe('electron-sucursal scaffold', () => {
  test('app launches and renders Parkos Sucursal', async () => {
    const app = await electron.launch({ args: ['.'] });
    const appWindow = await app.firstWindow();
    await expect(appWindow).toHaveTitle(/Parkos Sucursal/i);
    await expect(
      appWindow.getByRole('heading', { name: /Parkos Sucursal/i }),
    ).toBeVisible();
    await app.close();
  });

  test('root route has no WCAG 2.1 AA violations (axe-core)', async () => {
    const app = await electron.launch({ args: ['.'] });
    const appWindow = await app.firstWindow();
    await appWindow.waitForLoadState('domcontentloaded');

    const results = await new AxeBuilder({ page: appWindow })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
    await app.close();
  });
});
