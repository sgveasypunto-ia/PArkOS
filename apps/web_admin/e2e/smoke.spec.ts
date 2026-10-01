import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

import { seedAuth, mockAuxiliaryEndpoints } from './helpers/seedAuth';

const ADMIN_TOKEN = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0LWFkbWluIn0.fake';
const BRANCH_NORTE = '22222222-2222-2222-2222-222222222222';

const ADMIN_ME = {
  actor_uuid: '11111111-1111-1111-1111-111111111111',
  email: 'admin@parkos.test',
  rol: 'admin',
  sucursales_permitidas: [BRANCH_NORTE],
  permissions: ['config_catalogo', 'audit_read'],
};

const SUCURSALES = {
  items: [{ uuid: BRANCH_NORTE, nombre: 'Sucursal Norte', prefijo_nombre: 'BOG-NOR' }],
  next_cursor: null,
};

const DASHBOARD = {
  uuid_sucursal: BRANCH_NORTE,
  fecha: '2026-09-04T12:00:00',
  ingresos_count: 5,
  ingresos_monto_total: 0,
  facturas_emitidas_count: 3,
  facturas_electronicas_count: 3,
  open_alertas_count: 0,
  sync_health: { last_sync_at: null, lag_seconds: null, queue_depth: 0 },
};

/**
 * Smoke check — boots the PWA via the webServer config and confirms
 * the brand renders. Then runs axe-core against the dashboard page to
 * keep the WCAG 2.1 AA gate green (RNF-022).
 *
 * PR1 of the web_admin redesign added the branch gate: with a valid
 * persisted selection we land directly on `/dashboard`. Without one,
 * the picker forces a stop. This spec seeds the selection so the gate
 * is satisfied and the original smoke behaviour survives.
 */
test.describe('web_admin smoke', () => {
  test.beforeEach(async ({ context }) => {
    await context.route('**/api/v1/admin/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ADMIN_ME),
      }),
    );
    await context.route('**/api/v1/sucursales', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SUCURSALES),
      }),
    );
    await context.route('**/api/v1/admin/sucursales/**/dashboard', (route) => {
      const url = new URL(route.request().url());
      const headerUuid =
        route.request().headers()['x-sucursal-context'] ??
        route.request().headers()['X-Sucursal-Context'];
      const expected = url.pathname.split('/').slice(-2, -1)[0];
      if (headerUuid !== expected) {
        return route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'x_sucursal_context_mismatch' }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...DASHBOARD, uuid_sucursal: headerUuid }),
      });
    });

    await mockAuxiliaryEndpoints(context);
    await seedAuth(context, {
      accessToken: ADMIN_TOKEN,
      branchUuid: BRANCH_NORTE,
    });
  });

  test('root renders the hub', async ({ page }) => {
    // The branch-gate redirect (/ -> /dashboard) is what makes
    // "root renders the hub" the wrong assertion once a branch is
    // persisted. Seed the auth token alone (no branch) so / falls
    // through to the global route group that renders HomeHub.
    await page.addInitScript((token: string) => {
      window.localStorage.setItem(
        'parkos.auth',
        JSON.stringify({
          state: { accessToken: token, refreshToken: 'r', expiresAt: '2099-01-01T00:00:00Z' },
          version: 1,
        }),
      );
    }, ADMIN_TOKEN);
    await page.goto('/');
    await expect(page.getByTestId('home-hub')).toBeVisible();
  });

  test('/dashboard renders with no WCAG 2.1 AA violations (axe-core)', async ({
    page,
  }) => {
    await page.goto('/dashboard');
    await expect(page.getByTestId('page-dashboard')).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });

  test('/login renders the login page', async ({ page }) => {
    // The auth-seeded beforeEach already lands the admin session, so
    // /login redirects to / via the post-login Navigate. Wipe the
    // auth envelope so the Login container renders instead.
    await page.addInitScript(() => {
      window.localStorage.removeItem('parkos.auth');
      window.localStorage.removeItem('parkos.lastSelectedSucursal');
    });
    await page.goto('/login');
    await expect(page.getByTestId('page-login')).toBeVisible();
  });
});
