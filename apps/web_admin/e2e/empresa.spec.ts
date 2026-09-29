/**
 * `empresa.spec.ts` — e2e tests for the Empresa singleton page
 * (HU-F15.2 de `plan.md:3558`).
 *
 *   E1: el admin post-login ve la card Empresa en HomeHub y al
 *       clickearla aterriza en /empresa con el tab "Datos" activo.
 *   E2: el tab "Bitácora" muestra el placeholder de integración
 *       pendiente con Fase 20.
 *   E3: el form "Datos" muestra el error inline de NIT módulo 11
 *       cuando se tipea un DV incorrecto, y deshabilita el submit.
 *   E4: la página /empresa no monta el AdminChrome (es global,
 *       no branch-scoped — pineado por App.test.tsx "mounts
 *       TopNav but NOT AdminChrome on /empresa").
 *   E5: axe-core WCAG 2.1 AA sin violaciones.
 *
 * Patrón de mocks: `page.route()` intercepta el backend real
 * (`/api/v1/empresa/empresa`) para que la SPA resuelva el SWR
 * con un payload controlado. Igual que `login.spec.ts` y
 * `seleccionar-sucursal.spec.ts`.
 */
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const EMPRESA_UUID = '00000000-0000-0000-0000-00000000c0ee';

const SAMPLE_EMPRESA = {
  uuid: EMPRESA_UUID,
  nombre: 'Parkos S.A.S.',
  nit: '123456789-6',
  mensaje_bienvenida: 'Bienvenido.',
  mensaje_salida: 'Hasta pronto.',
  regimen: 'comun',
  vigente_desde: '2026-01-01T00:00:00',
  vigente_hasta: null,
  estado: 'activo',
  created_at: '2026-01-01T00:00:00',
  created_by: null,
  sync_status: 'sincronizado',
};

async function mockEmpresaApi(
  page: Page,
  payload: typeof SAMPLE_EMPRESA | null = SAMPLE_EMPRESA,
): Promise<void> {
  await page.route('**/api/v1/empresa/empresa**', async (route) => {
    const url = route.request().url();
    if (url.endsWith('/empresa') || url.includes('/empresa?')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: payload === null ? [] : [payload],
          next_cursor: null,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    });
  });
}

test.describe('web_admin /empresa', () => {
  test('E1: la card Empresa en HomeHub navega a /empresa con tab Datos activo', async ({ page }) => {
    await mockEmpresaApi(page);
    await page.goto('/');
    const card = page.getByTestId('home-hub-card-empresa');
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute('href', '/empresa');
    await card.click();
    await expect(page).toHaveURL(/\/empresa$/);
    const tab = page.getByTestId('empresa-tab-datos');
    await expect(tab).toHaveAttribute('data-state', 'active');
  });

  test('E2: el tab Bitácora muestra el placeholder de integración pendiente', async ({ page }) => {
    await mockEmpresaApi(page);
    await page.goto('/empresa');
    await page.getByTestId('empresa-tab-bitacora').click();
    await expect(page.getByTestId('empresa-bitacora-placeholder')).toBeVisible();
    await expect(page.getByTestId('empresa-bitacora-placeholder')).toContainText(/Fase 20/);
  });

  test('E3: NIT con DV incorrecto muestra error inline y deshabilita el submit', async ({ page }) => {
    await mockEmpresaApi(page);
    await page.goto('/empresa');
    const nit = page.getByTestId('empresa-datos-nit');
    await nit.fill('123456789-9');
    const error = page.getByTestId('empresa-datos-nit-error');
    await expect(error).toBeVisible();
    await expect(error).toContainText(/DV inválido/i);
    const submit = page.getByTestId('empresa-datos-submit');
    await expect(submit).toBeDisabled();
  });

  test('E4: /empresa no monta el AdminChrome (es global, no branch-scoped)', async ({ page }) => {
    await mockEmpresaApi(page);
    await page.goto('/empresa');
    await expect(page.getByTestId('admin-chrome')).toHaveCount(0);
    await expect(page.getByTestId('chrome-sucursal-selector')).toHaveCount(0);
    await expect(page.getByTestId('topnav')).toBeVisible();
  });

  test('E5: /empresa no tiene violaciones WCAG 2.1 AA (axe-core)', async ({ page }) => {
    await mockEmpresaApi(page);
    await page.goto('/empresa');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
