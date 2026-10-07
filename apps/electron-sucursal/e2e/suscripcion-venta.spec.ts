/**
 * e2e/suscripcion-venta.spec.ts — Playwright e2e scenarios for the
 * subscription sale wizard (HU-F9.1; PT-1 back navigation, PT-2 plans by
 * vehicle type, PT-3 renewal). Mirrors `e2e/pago.spec.ts` shape.
 *
 * Wizard (6 steps): cliente -> tipo de vehículo -> plan -> cantidad ->
 * placas -> pago. Test ids: `venta-paso-N`, `venta-paso-N-siguiente`,
 * `venta-tipo-vehiculo-<uuid>`, `venta-plan-<uuid>`, `venta-cantidad-input`,
 * `venta-placa-input-<i>`, `venta-volver`.
 *
 * Status: STUBS gated by the live backend (the unit/component coverage in
 * `Venta.test.tsx` / `SuscripcionesSheet.test.tsx` is the verification gate;
 * the coordinator verifies visually against the deployed stack).
 */
import { test, expect } from '@playwright/test';

const TIPO_CARRO = '00000000-0000-0000-0000-00000000aa02';
const TIPO_MOTO = '00000000-0000-0000-0000-00000000aa01';
const PLAN_CARRO = '00000000-0000-0000-0000-0000000000a1';

async function hastaPlacas(
  page: import('@playwright/test').Page,
  tipo: string,
  plan: string,
  nit: string,
): Promise<void> {
  await page.getByTestId('venta-cliente-numero').fill(nit);
  await page.getByTestId('venta-cliente-nombre').fill('ACME S.A.S.');
  await page.getByTestId('venta-paso-1-siguiente').click();
  await page.getByTestId(`venta-tipo-vehiculo-${tipo}`).click();
  await page.getByTestId('venta-paso-2-siguiente').click();
  await page.getByTestId(`venta-plan-${plan}`).click();
  await page.getByTestId('venta-paso-3-siguiente').click();
  await page.getByTestId('venta-cantidad-input').fill('1');
  await page.getByTestId('venta-paso-4-siguiente').click();
}

test.describe('HU-F9.1 — Venta de suscripción desde caja', () => {
  test.skip('cliente nuevo -> 6 pasos -> cobro -> recibo con estado de FE', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('sidebar-suscripciones').click();
    await page.getByTestId('suscripciones-sheet-nueva-venta').click();
    await hastaPlacas(page, TIPO_CARRO, PLAN_CARRO, '900123456');
    await page.getByTestId('venta-placa-input-0').fill('ABC123');
    await page.getByTestId('venta-paso-5-siguiente').click();
    await page.getByTestId('pago-confirmar').click();
    await expect(page.getByTestId('factura-display-modal')).toBeVisible();
    await expect(page.getByTestId('factura-display-fe')).toBeVisible();
  });

  test.skip('PT-2: tipo moto -> solo planes de moto (y los de tipo cualquiera)', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('sidebar-suscripciones').click();
    await page.getByTestId('suscripciones-sheet-nueva-venta').click();
    await page.getByTestId('venta-cliente-numero').fill('900123456');
    await page.getByTestId('venta-cliente-nombre').fill('ACME');
    await page.getByTestId('venta-paso-1-siguiente').click();
    await page.getByTestId(`venta-tipo-vehiculo-${TIPO_MOTO}`).click();
    await page.getByTestId('venta-paso-2-siguiente').click();
    await expect(page.getByTestId(`venta-plan-${PLAN_CARRO}`)).toHaveCount(0);
  });

  test.skip('PT-1: "Volver" retrocede un paso conservando los datos (nunca al dashboard)', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('sidebar-suscripciones').click();
    await page.getByTestId('suscripciones-sheet-nueva-venta').click();
    await hastaPlacas(page, TIPO_CARRO, PLAN_CARRO, '900123456');
    await page.getByTestId('venta-volver').click();
    await expect(page.getByTestId('venta-paso-4')).toBeVisible();
    await expect(page.getByTestId('venta-cantidad-input')).toHaveValue('1');
    await page.getByTestId('venta-volver').click();
    await expect(page.getByTestId('venta-paso-3')).toBeVisible();
  });

  test.skip('placa con suscripción vigente -> 422 suscripcion_duplicada_placa -> vuelve a placas', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('sidebar-suscripciones').click();
    await page.getByTestId('suscripciones-sheet-nueva-venta').click();
    await hastaPlacas(page, TIPO_CARRO, PLAN_CARRO, '900222333');
    await page.getByTestId('venta-placa-input-0').fill('ABC123');
    await page.getByTestId('venta-paso-5-siguiente').click();
    await page.getByTestId('pago-confirmar').click();
    await expect(page.getByTestId('venta-placas-error')).toBeVisible();
    await expect(page.getByTestId('venta-paso-5')).toBeVisible();
  });

  test.skip('PT-3: "Renovar" solo con <=10 días; renueva sin pedir placas y muestra recibo', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('sidebar-suscripciones').click();
    await page.getByTestId(/suscripciones-renovar-/).first().click();
    await expect(page.getByTestId('renovar-placas')).toBeVisible();
    await page.getByTestId('renovar-confirmar').click();
    await expect(page.getByTestId('factura-display-modal')).toBeVisible();
  });
});
