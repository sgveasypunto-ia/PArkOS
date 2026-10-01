/**
 * seleccionar-sucursal.spec.ts — Acceptance spec for the branch gate
 * introduced in PR1 of the web_admin redesign.
 *
 * The contract this spec owes the rest of the SPA:
 *   1. After login, an admin with multiple permitted branches is dropped
 *      on `/seleccionar-sucursal`, never on `/dashboard` directly.
 *   2. The picker lists every permitted branch (no extra branches from
 *      the directory that are not in the JWT claim).
 *   3. Clicking a card writes `parkos.lastSelectedSucursal` to
 *      `localStorage` AND navigates to `/dashboard`.
 *   4. The chrome badge reopens `/seleccionar-sucursal` to switch.
 *   5. axe-core is clean on `/seleccionar-sucursal`.
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

import { seedAuth, mockAuxiliaryEndpoints } from './helpers/seedAuth';

const ADMIN_TOKEN = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0LWFkbWluIn0.fake';
const BRANCH_NORTE = '22222222-2222-2222-2222-222222222222';
const BRANCH_SUR = '33333333-3333-3333-3333-333333333333';

const ADMIN_ME = {
  actor_uuid: '11111111-1111-1111-1111-111111111111',
  email: 'admin@parkos.test',
  rol: 'admin',
  sucursales_permitidas: [BRANCH_NORTE, BRANCH_SUR],
  permissions: ['config_catalogo', 'audit_read'],
};

const SUCURSALES = {
  items: [
    { uuid: BRANCH_NORTE, nombre: 'Sucursal Norte', prefijo_nombre: 'BOG-NOR', regimen: 'comun' },
    { uuid: BRANCH_SUR, nombre: 'Sucursal Sur', prefijo_nombre: 'BOG-SUR', regimen: 'comun' },
  ],
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

test.describe('Branch gate (/seleccionar-sucursal)', () => {
  test.beforeEach(async ({ page: _page, context }) => {
    await context.route('**/api/v1/admin/me', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ADMIN_ME),
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
    await seedAuth(context, { accessToken: ADMIN_TOKEN });
    await context.route('**/api/v1/sucursales', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SUCURSALES),
      }),
    );
  });

  test('drops the admin on the picker when no branch is selected', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/seleccionar-sucursal$/);
    await expect(page.getByTestId('sucursal-picker')).toBeVisible();
  });

  test('renders one card per permitted branch', async ({ page }) => {
    await page.goto('/seleccionar-sucursal');
    await expect(page.getByTestId('sucursal-picker')).toBeVisible();
    await expect(
      page.getByRole('button', { name: /Sucursal Norte/ }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /Sucursal Sur/ }),
    ).toBeVisible();
  });

  test('selecting a card writes the UUID to localStorage and navigates to /dashboard', async ({
    page,
  }) => {
    await page.goto('/seleccionar-sucursal');
    await page
      .getByRole('button', { name: /Sucursal Sur/ })
      .click();

    await expect(page).toHaveURL(/\/dashboard$/);

    const persisted = await page.evaluate(() =>
      window.localStorage.getItem('parkos.lastSelectedSucursal'),
    );
    expect(persisted).toBe(BRANCH_SUR);
  });

  test('the chrome badge opens the picker to switch branches', async ({ page }) => {
    await page.goto('/dashboard');
    // First the picker forces a choice; pick Norte.
    await page
      .getByRole('button', { name: /Sucursal Norte/ })
      .click();
    await expect(page).toHaveURL(/\/dashboard$/);

    await page.getByTestId('chrome-sucursal-selector').click();
    await expect(page).toHaveURL(/\/seleccionar-sucursal$/);
  });

  test('a stale persisted UUID is ignored and the picker shows again', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem('parkos.lastSelectedSucursal', 'revoked-uuid');
    });
    await page.goto('/dashboard');
    await expect(page).toHaveURL(/\/seleccionar-sucursal$/);

    const persisted = await page.evaluate(() =>
      window.localStorage.getItem('parkos.lastSelectedSucursal'),
    );
    expect(persisted).toBeNull();
  });

  test('picker page has no WCAG 2.1 AA violations (axe-core)', async ({ page }) => {
    await page.goto('/seleccionar-sucursal');
    await expect(page.getByTestId('sucursal-picker')).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
