/**
 * e2e/suscripcion-venta.spec.ts — Playwright e2e scenarios for
 * HU-F9.1 wizard 4 pasos. Mirrors `e2e/pago.spec.ts` shape.
 *
 * Scenarios (per plan.md:2047-2052):
 *   1. cliente nuevo: creates `clientes` + `vehiculos` +
 *      `subscripciones_cliente` in 1 TX
 *   2. cliente existente: reuses the `clientes` row
 *   3. plan `mismo_tipo_vehiculo=true` + placas mixed tipos → 422
 *      `tipo_vehiculo_incompatible`
 *   4. placa con suscripción vigente → 422
 *      `suscripcion_duplicada_placa`
 *
 * Status: STUB. The e2e suite is gated by the live backend at
 * runtime; the unit/component coverage is the verification gate for
 * F9.1 PR-1. A live backend runbook lives at
 * `openspec/changes/fase-9-1-venta-suscripcion/verify-report.md`
 * (PENDING orchestrator validation).
 */
import { test, expect } from '@playwright/test';

test.describe('HU-F9.1 — Venta de suscripción desde caja', () => {
  test.skip('cliente nuevo → 1 TX across 3 tables', async ({ page }) => {
    // Stub: navigate to /suscripciones/venta and complete the wizard.
    await page.goto('/suscripciones/venta');
    // step 1: cliente
    await page.getByTestId('venta-cliente-nit').fill('900123456');
    await page.getByTestId('venta-cliente-nombre').fill('ACME S.A.S.');
    await page.getByTestId('venta-paso-1-siguiente').click();
    // step 2: placa
    await page.getByTestId('venta-placa-input').fill('ABC123');
    await page.getByTestId('venta-paso-2-siguiente').click();
    // step 3: plan
    await page
      .getByTestId('venta-plan-select')
      .fill('00000000-0000-0000-0000-0000000000a1');
    await page.getByTestId('venta-paso-3-siguiente').click();
    // step 4: confirm pago stub
    await page.getByTestId('pago-confirmar').click();
    // expectation: navigate to /suscripciones
    await expect(page).toHaveURL(/\/suscripciones$/);
  });

  test.skip('cliente existente → reuse row', async ({ page }) => {
    // Stub: same wizard, but the backend reuses the existing cliente
    // (auto-fill on step 1 via NIT lookup). The wizard should still
    // submit successfully.
    await page.goto('/suscripciones/venta');
    // Auto-fill is not yet wired in this PR-1 — operator types
    // cliente data manually. Same flow as scenario 1.
    await page.getByTestId('venta-cliente-nit').fill('900123456');
    await page.getByTestId('venta-cliente-nombre').fill('ACME');
    await page.getByTestId('venta-paso-1-siguiente').click();
    await page.getByTestId('venta-placa-input').fill('DEF456');
    await page.getByTestId('venta-paso-2-siguiente').click();
    await page
      .getByTestId('venta-plan-select')
      .fill('00000000-0000-0000-0000-0000000000a2');
    await page.getByTestId('venta-paso-3-siguiente').click();
    await page.getByTestId('pago-confirmar').click();
    await expect(page).toHaveURL(/\/suscripciones$/);
  });

  test.skip('mixed tipos → 422 tipo_vehiculo_incompatible', async ({ page }) => {
    // Stub: 2 placas of different format (ABC123 + XYZ12A), plan with
    // mismo_tipo_vehiculo=true. Backend rejects with 422.
    await page.goto('/suscripciones/venta');
    await page.getByTestId('venta-cliente-nit').fill('900999111');
    await page.getByTestId('venta-cliente-nombre').fill('MIXED');
    await page.getByTestId('venta-paso-1-siguiente').click();
    // step 2: only one placa allowed in the wizard stub
    await page.getByTestId('venta-placa-input').fill('ABC123');
    await page.getByTestId('venta-paso-2-siguiente').click();
    await page
      .getByTestId('venta-plan-select')
      .fill('00000000-0000-0000-0000-0000000000a3');
    await page.getByTestId('venta-paso-3-siguiente').click();
    await page.getByTestId('pago-confirmar').click();
    // expectation: revert to paso 2 with inline error
    await expect(page.getByTestId('venta-placa-error')).toBeVisible();
    await expect(page.getByTestId('venta-paso-2')).toBeVisible();
  });

  test.skip('placa vigente → 422 suscripcion_duplicada_placa', async ({ page }) => {
    // Stub: placa `ABC123` already has an active subscription at this
    // branch. Backend rejects with 422.
    await page.goto('/suscripciones/venta');
    await page.getByTestId('venta-cliente-nit').fill('900222333');
    await page.getByTestId('venta-cliente-nombre').fill('DUP');
    await page.getByTestId('venta-paso-1-siguiente').click();
    await page.getByTestId('venta-placa-input').fill('ABC123');
    await page.getByTestId('venta-paso-2-siguiente').click();
    await page
      .getByTestId('venta-plan-select')
      .fill('00000000-0000-0000-0000-0000000000a4');
    await page.getByTestId('venta-paso-3-siguiente').click();
    await page.getByTestId('pago-confirmar').click();
    await expect(page.getByTestId('venta-placa-error')).toBeVisible();
    await expect(page.getByTestId('venta-paso-2')).toBeVisible();
  });
});
