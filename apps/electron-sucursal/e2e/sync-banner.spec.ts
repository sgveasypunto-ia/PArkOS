/**
 * e2e/sync-banner.spec.ts — Playwright e2e scenarios for HU-F11.1
 * Sync Banner (REQ-OPS-175).
 *
 * Drift anchors resolved by these tests:
 *   DA-F11.1-5 (30 s poll test) — `page.clock.install({ time: 0 })` +
 *       `page.clock.fastForward(30_000)` per scenario. NO `test.skip`
 *       allowed by design AD-6 (strict_tdd). The hooks are pure SWR
 *       over `parkosFetch`, mockable via `page.route`, so we do not
 *       need Electron-runtime-dependent paths.
 *   DA-F11.1-6 (distinct banners) — scenarios assert that
 *       `<SyncBanner />` and `<LocalApiDownBanner />` carry distinct
 *       roles + aria-labels + i18n namespaces.
 *
 * Scenarios (verbatim tasks.md §C6.1):
 *   1. (a) verde — `lag_seg` bajo, sync dentro ultima hora.
 *   2. (b) amarillo — `lag_seg` por encima del umbral, sin fallos
 *      consecutivos.
 *   3. (c) rojo — sync fallida o `lag_seg > 3600`.
 *   4. (d) LocalApiDownBanner — `consecutiveFailures === 3`, banner
 *      visible con copy distinto.
 *
 * The final block of each scenario runs `@axe-core/playwright` for the
 * WCAG 2.1 AA gate (RNF-022 + DEC-ELEC-07).
 *
 * Sandbox F.6 caveat (verbatim F10.x precedent): the dev-DB + the
 * packaged Electron app are unavailable in this sandbox. CI runs the
 * full suite against the devDep `electron@30.5.1` + a running
 * `parkos-api-sucursal` Docker. Per design AD-6 we MUST NOT use
 * `test.skip` — strict_tdd red bars cannot be skipped, and the
 * scenarios here are pure UI / data-driven (mockable with `page.route`
 * + `page.addInitScript`).
 */
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const TEST_SUCURSAL_UUID = '00000000-0000-0000-0000-000000000001';
const TEST_SYNC_ESTADO_URL = '**/api/v1/sync/estado**';

/**
 * Helper: installs a `window.bridge.apiStatus.get()` stub via the
 * renderer's window so the F2.3 `<StatusBar />` poll path runs in
 * test. Defaults to a healthy response.
 */
async function stubBridgeApiStatus(
  page: Page,
  mode: 'ok' | 'fail' = 'ok',
): Promise<void> {
  await page.addInitScript((m: 'ok' | 'fail') => {
    const w = window as unknown as {
      bridge?: {
        apiStatus?: {
          get: () => Promise<{ ok: boolean; latency_ms: number; code?: number }>;
        };
      };
    };
    w.bridge = w.bridge ?? {};
    w.bridge.apiStatus = {
      get: async () =>
        m === 'fail'
          ? Promise.reject(new Error('bridge offline'))
          : Promise.resolve({ ok: true, latency_ms: 120, code: 200 }),
    };
  }, mode);
}

/**
 * Helper: stubs the auth login + me + sesion endpoints so the page
 * boot path (useAuth) succeeds. Mirrors the F10.x precedent.
 */
async function stubAuth(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'mock-access-token',
        refresh_token: 'mock-refresh-token',
      }),
    }),
  );
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        uuid: 'user-uuid-1',
        email: 'operador@parkos.local',
        sucursal: { uuid: TEST_SUCURSAL_UUID, nombre: 'Sucursal Test' },
        sucursales_permitidas: [{ uuid: TEST_SUCURSAL_UUID, nombre: 'Sucursal Test' }],
        permisos: ['caja:abrir'],
        expires_at: '2099-01-01T00:00:00.000Z',
      }),
    }),
  );
  await page.route('**/caja-sesion/sesion/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        uuid: 'sesion-uuid-1',
        uuid_sucursal: TEST_SUCURSAL_UUID,
        uuid_usuario: 'user-uuid-1',
        estado: 'activa',
      }),
    }),
  );
}

test.describe('HU-F11.1 — Sync Banner (e2e)', () => {
  test('(a) verde: lag_seg bajo, sync dentro ultima hora -> <SyncBanner /> data-state=online', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-09-21T12:00:00Z') });
    await stubAuth(page);
    await stubBridgeApiStatus(page, 'ok');
    await page.route(TEST_SYNC_ESTADO_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: TEST_SUCURSAL_UUID,
          ultima_sync_at: new Date(Date.now() - 5_000).toISOString(),
          lag_seg: 5,
          pendientes: 0,
        }),
      }),
    );

    await page.goto('/caja/abrir-turno');
    // Wait for the SWR initial fetch to resolve and the banner to mount.
    await expect(page.getByTestId('sync-banner')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('sync-banner')).toHaveAttribute('data-state', 'online');
    await expect(page.getByTestId('sync-banner')).toHaveClass(/bg-emerald-500/);

    // Advance SWR by 30s — banner MUST stay green (no state transition).
    await page.clock.fastForward(30_000);
    await expect(page.getByTestId('sync-banner')).toHaveAttribute('data-state', 'online');

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });

  test('(b) amarillo: lag_seg por encima del umbral, sin fallos consecutivos -> <SyncBanner /> data-state=lagging', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-09-21T12:00:00Z') });
    await stubAuth(page);
    await stubBridgeApiStatus(page, 'ok');
    await page.route(TEST_SYNC_ESTADO_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: TEST_SUCURSAL_UUID,
          ultima_sync_at: new Date(Date.now() - 600_000).toISOString(),
          lag_seg: 600,
          pendientes: 0,
        }),
      }),
    );

    await page.goto('/caja/abrir-turno');
    await expect(page.getByTestId('sync-banner')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('sync-banner')).toHaveAttribute('data-state', 'lagging');
    await expect(page.getByTestId('sync-banner')).toHaveClass(/bg-amber-500/);

    // LocalApiDownBanner MUST NOT be in the DOM (consecutiveFailures = 0).
    await expect(page.getByTestId('local-api-down-banner')).toHaveCount(0);

    // Advance 30s — still lagging.
    await page.clock.fastForward(30_000);
    await expect(page.getByTestId('sync-banner')).toHaveAttribute('data-state', 'lagging');

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });

  test('(c) rojo: lag_seg > 3600 -> <SyncBanner /> data-state=offline', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-09-21T12:00:00Z') });
    await stubAuth(page);
    await stubBridgeApiStatus(page, 'ok');
    await page.route(TEST_SYNC_ESTADO_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: TEST_SUCURSAL_UUID,
          ultima_sync_at: new Date(Date.now() - 7_200_000).toISOString(),
          lag_seg: 7200,
          pendientes: 0,
        }),
      }),
    );

    await page.goto('/caja/abrir-turno');
    await expect(page.getByTestId('sync-banner')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId('sync-banner')).toHaveAttribute('data-state', 'offline');
    await expect(page.getByTestId('sync-banner')).toHaveClass(/bg-red-500/);

    // Advance 30s — stays red.
    await page.clock.fastForward(30_000);
    await expect(page.getByTestId('sync-banner')).toHaveAttribute('data-state', 'offline');

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });

  test('(d) LocalApiDownBanner: consecutive_failures = 3 -> banner visible con copy distinto', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-09-21T12:00:00Z') });
    await stubAuth(page);
    // Bridge throws — StatusBar increments consecutiveFailures.
    await stubBridgeApiStatus(page, 'fail');
    await page.route(TEST_SYNC_ESTADO_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: TEST_SUCURSAL_UUID,
          ultima_sync_at: new Date(Date.now() - 5_000).toISOString(),
          lag_seg: 5,
          pendientes: 0,
        }),
      }),
    );

    await page.goto('/caja/abrir-turno');
    // Wait for the 3 poll cycles (3 * 30s = 90s) to accumulate 3 failures.
    await page.clock.fastForward(30_000);
    await page.clock.fastForward(30_000);
    await page.clock.fastForward(30_000);
    await expect(page.getByTestId('local-api-down-banner')).toBeVisible({ timeout: 5_000 });

    const banner = page.getByTestId('local-api-down-banner');
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner).toHaveAttribute('aria-label', 'Estado de API local');
    // Copy is DISTINCT from <SyncBanner /> (DA-F11.1-6 separation).
    const text = await banner.textContent();
    expect(text).toContain('localApiDown.copy');
    expect(text).not.toContain('syncBanner.online');

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });
});
