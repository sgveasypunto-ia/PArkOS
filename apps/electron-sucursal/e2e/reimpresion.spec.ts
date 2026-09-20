/**
 * E2E tests for HU-F8.3 — ReimprimirTiquete page (REQ-OPS-171 + 173 + 174).
 * Stub per F5.x/F6.x/F7.x/F8.x e2e pattern.
 *
 * Scenarios (deferred to F8.3 integration sprint):
 *   S1 — Navigate to `/facturacion/reimprimir` → page mounts with the
 *        3-input form (uuid_ingreso + tipo radio + motivo textarea).
 *   S2 — Reimprimir tiquete de entrada: motivo (≥10 chars) + tipo=entrada
 *        + Confirm → alertdialog opens with `role="alertdialog"` +
 *        cobro-consequence description → POST `/api/v1/workflows/
 *        reimpresion-ticket/{uuid_ingreso}/reimprimir` with body
 *        `{motivo, tipo}` + Idempotency-Key header → success card
 *        renders uuid_reimpresion + motivo + "Anular" button.
 *   S3 — motivo <10 chars → inline Zod error visible; Confirm
 *        submit blocked; alertdialog NEVER opens; NO POST fires.
 *
 * Sandbox F.6 caveat (precedent F2.x/F3.x/F7.x/F8.x e2e specs): the
 * Electron main process + printer hardware are unavailable in this
 * sandbox. The spec asserts the SPA boot path + the dispatcher wiring
 * via the test harness; the actual print byte stream is verified in
 * unit tests under `lib/print/escposBuilder.reimpresion.test.ts`.
 */
import { test, expect } from '@playwright/test';
import type { ElectronApplication, Page } from '@playwright/test';
import { _electron as electron } from '@playwright/test';
import path from 'node:path';

const APP_ROOT = path.resolve(__dirname, '..');

async function launchApp(): Promise<{ app: ElectronApplication; page: Page }> {
  const app = await electron.launch({
    args: [path.join(APP_ROOT, 'out', 'main.js')],
    cwd: APP_ROOT,
  });
  const page = await app.firstWindow();
  return { app, page };
}

test.describe('HU-F8.3 — ReimprimirTiquete page (alertdialog + motivo Zod + tipo selector)', () => {
  test.skip('S1: page mounts with uuid_ingreso + tipo + motivo form', async () => {
    const { page } = await launchApp();
    await page.goto('http://localhost:5173/facturacion/reimprimir');
    await expect(page.getByTestId('reimprimir-tiquete-page')).toBeVisible();
    await expect(page.getByTestId('reimprimir-uuid')).toBeVisible();
    await expect(page.getByTestId('reimprimir-tipo-entrada')).toBeVisible();
    await expect(page.getByTestId('reimprimir-tipo-salida')).toBeVisible();
    await expect(page.getByTestId('reimprimir-motivo')).toBeVisible();
    await expect(page.getByTestId('reimprimir-confirmar')).toBeVisible();
  });

  test.skip('S2: motivo ≥10 chars + Confirm → alertdialog + POST + success card', async () => {
    const { page } = await launchApp();
    await page.goto('http://localhost:5173/facturacion/reimprimir');
    await page.getByTestId('reimprimir-uuid').fill('00000000-0000-0000-0000-000000000001');
    await page.getByTestId('reimprimir-tipo-entrada').check();
    await page
      .getByTestId('reimprimir-motivo')
      .fill('Cliente solicita reimpresion por deterioro del original');
    await page.getByTestId('reimprimir-confirmar').click();
    const dialog = page.getByTestId('reimprimir-confirm-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('role', 'alertdialog');
    await page.getByTestId('reimprimir-dialog-confirm').click();
    await expect(page.getByTestId('reimprimir-success')).toBeVisible();
    await expect(page.getByTestId('reimprimir-anular')).toBeVisible();
  });

  test.skip('S3: motivo <10 chars → inline error; submit blocked; alertdialog NEVER opens', async () => {
    const { page } = await launchApp();
    await page.goto('http://localhost:5173/facturacion/reimprimir');
    await page.getByTestId('reimprimir-uuid').fill('00000000-0000-0000-0000-000000000001');
    await page.getByTestId('reimprimir-tipo-entrada').check();
    await page.getByTestId('reimprimir-motivo').fill('corto');
    await page.getByTestId('reimprimir-confirmar').click();
    await expect(page.getByText('motivo_muy_corto')).toBeVisible();
    await expect(page.getByTestId('reimprimir-confirm-dialog')).toHaveCount(0);
  });
});
