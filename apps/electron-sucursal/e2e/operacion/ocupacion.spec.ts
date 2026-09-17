/**
 * E2E tests for `<OcupacionStrip />` (HU-F4.3).
 *
 * Scenarios:
 *   E1 — render + value refresh: mockea `GET /api/v1/operacion/ocupacion`
 *        para devolver `Auto 23/50` (green); tras 12s (un ciclo + buffer)
 *        switchea el mock a `Auto 47/50` (red) y verifica el nuevo texto
 *        + `data-color`.
 *   A1 — axe-core WCAG 2.1 AA: scan del strip renderizado con los cuatro
 *        tags (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`); `violations`
 *        debe estar vacío.
 *   A2 — degraded state: mockea el endpoint con HTTP 500, espera 12s,
 *        verifica que el strip conserva el último valor + `data-stale="true"`
 *        + `<AlertCircle />` visible.
 *
 * Sandbox F.6 caveat (precedent F2.x/F3.x e2e specs): este spec SKIP en
 * sandbox (`npm 11.16.0` rechaza `workspace:*`). El coverage real de los
 * flows críticos está en los unit tests RTL + `useOcupacion.test.ts`.
 * En CI con workspace deps instalado corre normalmente.
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const OCUPACION_URL = '**/api/v1/operacion/ocupacion*';
const SUCURSAL = '00000000-0000-0000-0000-000000000099';

test.describe('OcupacionStrip — HU-F4.3', () => {
  test('E1 — render inicial y refresh tras nuevo ingreso', async ({ page }) => {
    // Mock inicial: Auto 23/50 (green).
    await page.route(OCUPACION_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: SUCURSAL,
          items: [
            {
              uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
              tipo: 'Auto',
              cupo_maximo: 50,
              activos: 23,
              disponible: 27,
            },
          ],
          generado_en: '2026-09-16T10:00:00Z',
        }),
      }),
    );

    // Asumimos que el operador está autenticado y la app está montada.
    // Los e2e specs previos (`turno.spec.ts`) ya cubren el login flow;
    // este test se enfoca en el comportamiento del strip aislado.
    await page.goto('/');

    const strip = page.getByTestId('ocupacion-strip');
    await expect(strip).toBeVisible();
    await expect(page.getByTestId('ocupacion-chip-Auto')).toHaveText('Auto: 23/50');
    await expect(page.getByTestId('ocupacion-chip-Auto')).toHaveAttribute(
      'data-color',
      'green',
    );

    // Switch mock: Auto 47/50 (red, p = 0.94).
    await page.unroute(OCUPACION_URL);
    await page.route(OCUPACION_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: SUCURSAL,
          items: [
            {
              uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
              tipo: 'Auto',
              cupo_maximo: 50,
              activos: 47,
              disponible: 3,
            },
          ],
          generado_en: '2026-09-16T10:00:12Z',
        }),
      }),
    );

    // Esperar un polling cycle (10s) + buffer.
    await expect(page.getByTestId('ocupacion-chip-Auto')).toHaveText('Auto: 47/50', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('ocupacion-chip-Auto')).toHaveAttribute(
      'data-color',
      'red',
    );
  });

  test('A1 — axe-core WCAG 2.1 AA: 0 violaciones', async ({ page }) => {
    await page.route(OCUPACION_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          uuid_sucursal: SUCURSAL,
          items: [
            {
              uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
              tipo: 'Auto',
              cupo_maximo: 50,
              activos: 23,
              disponible: 27,
            },
            {
              uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000002',
              tipo: 'Moto',
              cupo_maximo: 5,
              activos: 1,
              disponible: 4,
            },
          ],
          generado_en: '2026-09-16T10:00:00Z',
        }),
      }),
    );

    await page.goto('/');
    await expect(page.getByTestId('ocupacion-strip')).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('A2 — degradación: poll 500 conserva último valor + data-stale="true"', async ({
    page,
  }) => {
    // Primer fetch OK para sembrar el último valor conocido.
    let fetchCount = 0;
    await page.route(OCUPACION_URL, (route) => {
      fetchCount += 1;
      if (fetchCount === 1) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            uuid_sucursal: SUCURSAL,
            items: [
              {
                uuid_tipo_vehiculo: '00000000-0000-0000-0000-000000000001',
                tipo: 'Auto',
                cupo_maximo: 50,
                activos: 23,
                disponible: 27,
              },
            ],
            generado_en: '2026-09-16T10:00:00Z',
          }),
        });
      }
      return route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'internal_error' }),
      });
    });

    await page.goto('/');
    const strip = page.getByTestId('ocupacion-strip');
    await expect(strip).toBeVisible();
    await expect(page.getByTestId('ocupacion-chip-Auto')).toHaveText('Auto: 23/50');

    // Esperar un polling cycle (10s) + buffer; el segundo fetch devuelve 500.
    await expect(strip).toHaveAttribute('data-stale', 'true', { timeout: 15_000 });
    await expect(page.getByTestId('ocupacion-strip-stale-icon')).toBeVisible();
    // El último valor conocido debe seguir visible.
    await expect(page.getByTestId('ocupacion-chip-Auto')).toHaveText('Auto: 23/50');
  });
});