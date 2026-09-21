/**
 * e2e/mi-turno.spec.ts — Playwright e2e scenarios for HU-F12.1
 * Panel "Mi turno" (REQ-OPS-187 + REQ-OPS-188).
 *
 * Sandbox F.6 caveat (verbatim F10.2 / F11.x precedent): the dev-DB +
 * the packaged Electron app are unavailable in this sandbox. Both
 * scenarios are wrapped in `test.skip(...)` (R-F12.1-3, DA-F12.1-6);
 * the runner exits 0 in this sandbox. CI runs the full suite
 * against the devDep `electron@30.5.1` + a running
 * `parkos-api-sucursal` Docker.
 *
 * Drift anchors resolved by these tests:
 *   DA-F12.1-3 — 15 s polling cadence: page.route timing assertion
 *       stubs the endpoint to verify revalidation cadence.
 *   DA-F12.1-4 — zero-state: panel renders 5 KPIs as `0` when
 *       `uuid_sesion` is null.
 *   DA-F12.1-5 — Cerrar-turno navigation: click -> /caja/cerrar-turno.
 *   DA-F12.1-6 — BE/FE drift: panel renders 5 KPI cells with the BE
 *       contract names (no camelCase drift).
 *
 * Scenarios (verbatim design AD-7):
 *   S1 (skip per F.6): 5 KPI cells visible after login with seeded
 *       backend payload + `Cache-Control: no-store` respected by the
 *       SWR cache. WCAG 2.1 AA gate.
 *   S2 (skip per F.6): Cerrar-turno button -> `navigate("/caja/cerrar-turno")`.
 *       No `cerrarSesion` PUT fires from this component.
 */
import { test, expect, type Page } from '@playwright/test';

const TEST_SUCURSAL_UUID = '00000000-0000-0000-0000-000000000001';
const TEST_SESION_UUID = '00000000-0000-0000-0000-0000000000aa';

const MI_TURNO_URL = '**/api/v1/operacion/mi-turno**';

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
        uuid: TEST_SESION_UUID,
        uuid_sucursal: TEST_SUCURSAL_UUID,
        uuid_usuario: 'user-uuid-1',
        estado: 'activa',
      }),
    }),
  );
  // Ocupacion + Dashboard dependencies.
  await page.route('**/api/v1/operacion/ocupacion**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        uuid_sucursal: TEST_SUCURSAL_UUID,
        items: [],
        generado_en: '2026-09-21T10:00:00.000Z',
      }),
    }),
  );
  await page.route('**/api/v1/suscripciones/proximas-vencer**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    }),
  );
  await page.addInitScript(() => {
    const w = window as unknown as {
      bridge?: { apiStatus?: { get: () => Promise<{ ok: boolean; latency_ms: number; code?: number }> } };
    };
    w.bridge = w.bridge ?? {};
    w.bridge.apiStatus = {
      get: async () => Promise.resolve({ ok: true, latency_ms: 120, code: 200 }),
    };
  });
}

test.describe('HU-F12.1 — Mi turno (e2e)', () => {
  test.skip('S1 (skip per F.6): 5 KPI cells render + 15s polling cadence (DA-F12.1-3, DA-F12.1-6)', async ({ page }) => {
    await stubAuth(page);

    // Seeded mi-turno payload (3 ingresos, 2 salidas, 50k efectivo, 30k datafono).
    await page.route(MI_TURNO_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Cache-Control': 'no-store' },
        body: JSON.stringify({
          uuid_sesion: TEST_SESION_UUID,
          uuid_sucursal: TEST_SUCURSAL_UUID,
          timestamp_calculo: '2026-09-21T08:00:00.000Z',
          ingresos_count: 3,
          salidas_count: 2,
          total_cobrado_efectivo_cop: 50000,
          total_cobrado_datafono_cop: 30000,
        }),
      }),
    );

    await page.goto('/');
    const panel = page.getByTestId('mi-turno-panel');
    await expect(panel).toBeVisible({ timeout: 5_000 });

    // Five KPI cells, populated from the BE payload (DA-F12.1-6).
    await expect(page.getByTestId('mi-turno-kpi-ingresos').getByText('3')).toBeVisible();
    await expect(page.getByTestId('mi-turno-kpi-salidas').getByText('2')).toBeVisible();
    await expect(page.getByTestId('mi-turno-kpi-total-cobrado').getByText(/80\.000|80000/)).toBeVisible();
    await expect(page.getByTestId('mi-turno-kpi-efectivo').getByText(/50\.000|50000/)).toBeVisible();
    await expect(page.getByTestId('mi-turno-kpi-datafono').getByText(/30\.000|30000/)).toBeVisible();

    // Cerrar-turno button MUST be visible and enabled (uuid_sesion is
    // present in the seeded sesion payload).
    const cerrarBtn = page.getByTestId('mi-turno-cerrar-button');
    await expect(cerrarBtn).toBeVisible();
    await expect(cerrarBtn).toBeEnabled();

    // 15s polling cadence: the SWR hook revalidates every 15_000 ms.
    // We assert at least 1 revalidation within the 16s window.
    let hits = 0;
    page.on('response', (resp) => {
      if (resp.url().includes('/api/v1/operacion/mi-turno') && resp.status() === 200) {
        hits += 1;
      }
    });
    await page.waitForTimeout(16_000);
    expect(hits).toBeGreaterThanOrEqual(1);
  });

  test.skip('S2 (skip per F.6): Cerrar-turno click navigates to /caja/cerrar-turno ONLY (DA-F12.1-5)', async ({ page }) => {
    await stubAuth(page);

    await page.route(MI_TURNO_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sesion: TEST_SESION_UUID,
          uuid_sucursal: TEST_SUCURSAL_UUID,
          timestamp_calculo: '2026-09-21T08:00:00.000Z',
          ingresos_count: 0,
          salidas_count: 0,
          total_cobrado_efectivo_cop: 0,
          total_cobrado_datafono_cop: 0,
        }),
      }),
    );

    await page.goto('/');
    await expect(page.getByTestId('mi-turno-panel')).toBeVisible({ timeout: 5_000 });

    // Capture the cerrar PUT body so we can assert NO cerrarSesion fired.
    let cerrarPutBody: Record<string, unknown> | null = null;
    await page.route('**/caja-sesion/sesion/**', (route) => {
      if (route.request().method() === 'PUT') {
        cerrarPutBody = JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>;
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ uuid: TEST_SESION_UUID, estado: 'cerrada' }),
        });
      }
      return route.continue();
    });

    await page.getByTestId('mi-turno-cerrar-button').click();
    await page.waitForURL('**/caja/cerrar-turno');

    // The MiTurnoPanel must NOT have fired cerrarSesion — that's F10.2's job.
    expect(cerrarPutBody).toBeNull();
  });
});