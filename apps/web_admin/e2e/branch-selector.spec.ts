/**
 * branch-selector.spec.ts — T-PR10-13 acceptance spec.
 *
 * Verifies the three behaviours the BranchSelector + SucursalContext
 * contract owes the rest of the admin shell:
 *
 *   1. Both permitted branches are rendered in the dropdown (admin with
 *      two claims.sucursales_permitidas entries sees two options).
 *   2. Switching sends `X-Sucursal-Context: <new uuid>` on the next
 *      dashboard fetch (REQ-X2 wire-through).
 *   3. The selected UUID persists in `localStorage` across reload.
 *
 * The dashboard endpoint is mocked via Playwright route interception so
 * the spec runs without a real cloud. axe-core coverage lives in
 * `smoke.spec.ts`; this spec is functional behaviour.
 */
import { test, expect } from '@playwright/test';

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
    { uuid: BRANCH_NORTE, nombre: 'Sucursal Norte' },
    { uuid: BRANCH_SUR, nombre: 'Sucursal Sur' },
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

test.describe('BranchSelector integration', () => {
  test.beforeEach(async ({ page, context }) => {
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

    await context.addInitScript((token: string) => {
      window.localStorage.setItem('parkos.auth.token', token);
    }, ADMIN_TOKEN);
  });

  test('renders both permitted branches', async ({ page }) => {
    await page.goto('/dashboard');
    // Radix Select trigger renders as role=combobox.
    await expect(
      page.getByRole('combobox', { name: /sucursal/i }),
    ).toBeVisible();
    await page.getByRole('combobox', { name: /sucursal/i }).click();
    await expect(page.getByRole('option', { name: 'Sucursal Norte' })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Sucursal Sur' })).toBeVisible();
  });

  test('switching changes X-Sucursal-Context on the next dashboard fetch', async ({
    page,
    context,
  }) => {
    const observed: string[] = [];
    context.on('request', (req) => {
      if (req.url().includes('/admin/sucursales/') && req.url().includes('/dashboard')) {
        const header = req.headers()['x-sucursal-context'];
        if (header) observed.push(header);
      }
    });

    await page.goto('/dashboard');
    // Wait for the initial dashboard fetch (first permitted branch).
    await expect.poll(() => observed.length).toBeGreaterThanOrEqual(1);

    await page.getByRole('combobox', { name: /sucursal/i }).click();
    await page.getByRole('option', { name: 'Sucursal Sur' }).click();

    // After the switch, the SWR invalidator triggers a re-fetch with
    // the new X-Sucursal-Context header.
    await expect
      .poll(() => observed.includes(BRANCH_SUR), { timeout: 5_000 })
      .toBe(true);
  });

  test('localStorage persists the selection across reload', async ({ page }) => {
    await page.goto('/dashboard');
    await page.getByRole('combobox', { name: /sucursal/i }).click();
    await page.getByRole('option', { name: 'Sucursal Sur' }).click();

    await expect
      .poll(() =>
        page.evaluate(() => window.localStorage.getItem('parkos.lastSelectedSucursal')),
      )
      .toBe(BRANCH_SUR);

    await page.reload();

    const persisted = await page.evaluate(() =>
      window.localStorage.getItem('parkos.lastSelectedSucursal'),
    );
    expect(persisted).toBe(BRANCH_SUR);
  });
});
