/**
 * e2e/suscripciones-lista.spec.ts — Playwright e2e scenarios for
 * HU-F9.2 (listado + banner de vencimiento). Mirrors
 * `e2e/suscripcion-venta.spec.ts` (F9.1) shape.
 *
 * Scenarios (per plan.md:2099-2102):
 *   1. /suscripciones route loads + DataTable visible.
 *   2. Banner appears on dashboard when there are suscripciones
 *      próximas a vencer (gated by stub backend fixture).
 *
 * Status: STUB. The e2e suite is gated by the live backend at
 * runtime; the unit/component coverage is the verification gate
 * for F9.2 PR-1. A live backend runbook lives at
 * `openspec/changes/fase-9-2-listado-vencimiento/verify-report.md`
 * (PENDING orchestrator validation).
 */
import { test, expect } from '@playwright/test';

test.describe('HU-F9.2 — Listado y alerta de vencimiento próximo', () => {
  test.skip('lista visible en /suscripciones con búsqueda cliente-side', async ({ page }) => {
    await page.goto('/suscripciones');
    await expect(page.getByTestId('listado-search-input')).toBeVisible();
    await expect(page.getByTestId('listado-table')).toBeVisible();
  });

  test.skip('banner aparece en dashboard cuando hay suscripciones por vencer', async ({ page }) => {
    await page.goto('/');
    // The dashboard exposes a role="alert" banner; we use the
    // explicit test-id anchor for stability across i18n.
    await expect(page.getByTestId('dashboard-vencimiento-banner')).toBeVisible();
    await expect(page.getByTestId('dashboard-vencimiento-panel')).toBeVisible();
  });
});
