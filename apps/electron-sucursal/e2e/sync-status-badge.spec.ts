/**
 * e2e/sync-status-badge.spec.ts — Playwright e2e scenarios for HU-F11.1
 * Sync status indicator (REQ-OPS-175, realineado 2026-09-24).
 *
 * F11.1 realineado (REQ-OPS-171, AD-3/AD-4/AD-5) por directiva del
 * operador: la funcionalidad dejó de ser un `<SyncBanner />` global
 * (franja arriba de toda la app, por encima incluso del navbar del
 * Dashboard) y ahora vive como el badge `dashboard-online` del header
 * del Dashboard, con el detalle real en un tooltip Radix (hover/focus).
 * Reemplaza el antiguo `e2e/sync-banner.spec.ts`.
 *
 * Drift anchors resolved by these tests:
 *   DA-F11.1-5 (30 s poll test) — `page.clock.install({ time: 0 })` +
 *       `page.clock.fastForward(30_000)` per scenario. NO `test.skip`
 *       allowed by design AD-6 (strict_tdd). The hooks are pure SWR
 *       over `parkosFetch`, mockable via `page.route`, so we do not
 *       need Electron-runtime-dependent paths.
 *   DA-F11.1-6 (distinct banners) — scenarios assert that the sync
 *       badge tooltip and `<LocalApiDownBanner />` carry distinct
 *       roles + aria-labels + i18n namespaces.
 *
 * Scenarios (verbatim tasks.md §C6.1, adaptadas al badge/tooltip):
 *   1. (a) verde — `lag_seg` bajo, sync dentro ultima hora.
 *   2. (b) amarillo — `lag_seg` por encima del umbral, sin fallos
 *      consecutivos.
 *   3. (c) rojo — sync fallida o `lag_seg > 3600`.
 *   4. (d) LocalApiDownBanner — `consecutiveFailures === 3`, banner
 *      visible con copy distinto (sin relación con el badge de sync).
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
 * boot path (useAuth) succeeds. Mirrors the F10.x precedent. The
 * sesion stub carries the FULL `SesionRead` shape (not just `estado`)
 * so `<Dashboard />` renders its hub instead of redirecting to
 * `/caja/abrir-turno` — needed now that the sync indicator only lives
 * inside the Dashboard header, not as a global banner.
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
        valor_inicial_efectivo: 50000,
        valor_inicial_datafono: 0,
        timestamp_apertura: '2026-09-24T08:00:00Z',
        timestamp_cierre: null,
      }),
    }),
  );
}

test.describe('HU-F11.1 — Sync status badge en el navbar (e2e)', () => {
  test('(a) verde: lag_seg bajo, sync dentro ultima hora -> badge data-state=online + tooltip', async ({ page }) => {
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

    await page.goto('/');
    // Wait for the SWR initial fetch to resolve and the badge to reflect it.
    const badge = page.getByTestId('dashboard-online');
    await expect(badge).toBeVisible({ timeout: 5_000 });
    await expect(badge).toHaveAttribute('data-state', 'online');

    // Hover reveals the real-state tooltip (Radix, RNF-022 WCAG 2.1 AA).
    await badge.hover();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText('Sincronización al día');

    // Advance SWR by 30s — badge MUST stay green (no state transition).
    await page.clock.fastForward(30_000);
    await expect(badge).toHaveAttribute('data-state', 'online');

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });

  test('(b) amarillo: lag_seg por encima del umbral, sin fallos consecutivos -> badge data-state=lagging + tooltip', async ({ page }) => {
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

    await page.goto('/');
    const badge = page.getByTestId('dashboard-online');
    await expect(badge).toBeVisible({ timeout: 5_000 });
    await expect(badge).toHaveAttribute('data-state', 'lagging');

    await badge.hover();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText('Sincronización con retraso');
    await expect(tooltip).toContainText('600s');

    // LocalApiDownBanner MUST NOT be in the DOM (consecutiveFailures = 0).
    await expect(page.getByTestId('local-api-down-banner')).toHaveCount(0);

    // Advance 30s — still lagging.
    await page.clock.fastForward(30_000);
    await expect(badge).toHaveAttribute('data-state', 'lagging');

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });

  test('(c) rojo: lag_seg > 3600 -> badge data-state=offline + tooltip', async ({ page }) => {
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

    await page.goto('/');
    const badge = page.getByTestId('dashboard-online');
    await expect(badge).toBeVisible({ timeout: 5_000 });
    await expect(badge).toHaveAttribute('data-state', 'offline');

    await badge.hover();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText('Sin sincronización con la nube');

    // Advance 30s — stays red.
    await page.clock.fastForward(30_000);
    await expect(badge).toHaveAttribute('data-state', 'offline');

    // WCAG 2.1 AA gate.
    const a11y = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(a11y.violations).toEqual([]);
  });

  test('(d) LocalApiDownBanner: consecutive_failures = 3 -> banner visible con copy distinto del badge de sync', async ({ page }) => {
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

    await page.goto('/');
    // Wait for the 3 poll cycles (3 * 30s = 90s) to accumulate 3 failures.
    await page.clock.fastForward(30_000);
    await page.clock.fastForward(30_000);
    await page.clock.fastForward(30_000);
    await expect(page.getByTestId('local-api-down-banner')).toBeVisible({ timeout: 5_000 });

    const banner = page.getByTestId('local-api-down-banner');
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner).toHaveAttribute('aria-label', 'Estado de API local');
    // Copy is DISTINCT from the sync badge tooltip (DA-F11.1-6 separation).
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
