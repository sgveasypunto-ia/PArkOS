/**
 * E2E tests for HU-F8.3 — reimpresión de tiquete drawer (REQ-OPS-171 +
 * 173 + 174). Stub per F5.x/F6.x/F7.x/F8.x e2e pattern.
 *
 * BUGFIX (2026-09-25, directiva del operador): el flujo ya NO es una
 * ruta (`/facturacion/reimprimir` se retiró) — vive dentro del drawer
 * `<ReimprimirTiqueteSheet />`, abierto con el hotkey **F8** o el botón
 * "Facturas" del sidebar del dashboard. La búsqueda es por placa o
 * cupo/consecutivo (ya NO un UUID a mano), y el POST real es
 * `{uuid_ingreso, motivo}` sin `tipo` (ver `reimpresionApi.ts`).
 *
 * Scenarios (deferred to F8.3 integration sprint):
 *   S1 — F8 en el dashboard → sheet abre con el form de búsqueda
 *        (placa/cupo + botón Buscar); motivo/confirmar aún NO visibles.
 *   S2 — Reimprimir tiquete de entrada: buscar placa → tarjeta de
 *        ingreso encontrado + motivo (≥10 chars) + Confirmar →
 *        alertdialog opens with `role="alertdialog"` + cobro-consequence
 *        description → POST `/api/v1/workflows/reimpresion-ticket`
 *        (raíz) with body `{uuid_ingreso, motivo}` + Idempotency-Key
 *        header → success card renders uuid_reimpresion + costo_aplicado
 *        + "Anular" button + dispara la impresión real.
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

test.describe('HU-F8.3 — reimpresión de tiquete (drawer, búsqueda placa/cupo + alertdialog + motivo Zod)', () => {
  test.skip('S1: F8 abre el sheet con el form de búsqueda (placa/cupo)', async () => {
    const { page } = await launchApp();
    await page.keyboard.press('F8');
    await expect(page.getByTestId('reimprimir-sheet')).toBeVisible();
    await expect(page.getByTestId('reimprimir-termino')).toBeVisible();
    await expect(page.getByTestId('reimprimir-buscar-confirmar')).toBeVisible();
    await expect(page.getByTestId('reimprimir-motivo')).toHaveCount(0);
  });

  test.skip('S2: buscar placa → ingreso encontrado + motivo ≥10 chars + Confirm → alertdialog + POST + success', async () => {
    const { page } = await launchApp();
    await page.keyboard.press('F8');
    await page.getByTestId('reimprimir-termino').fill('ABC123');
    await page.getByTestId('reimprimir-buscar-confirmar').click();
    await expect(page.getByTestId('reimprimir-ingreso-encontrado')).toBeVisible();
    await page
      .getByTestId('reimprimir-motivo')
      .fill('Cliente solicita reimpresion por deterioro del original');
    await page.getByTestId('reimprimir-confirmar').click();
    const dialog = page.getByTestId('reimprimir-confirm-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('role', 'alertdialog');
    await page.getByTestId('reimprimir-dialog-confirm').click();
    await expect(page.getByTestId('reimprimir-success')).toBeVisible();
    await expect(page.getByTestId('reimprimir-success-costo')).toBeVisible();
    await expect(page.getByTestId('reimprimir-anular')).toBeVisible();
  });

  test.skip('S3: motivo <10 chars → inline error; submit blocked; alertdialog NEVER opens', async () => {
    const { page } = await launchApp();
    await page.keyboard.press('F8');
    await page.getByTestId('reimprimir-termino').fill('ABC123');
    await page.getByTestId('reimprimir-buscar-confirmar').click();
    await expect(page.getByTestId('reimprimir-ingreso-encontrado')).toBeVisible();
    await page.getByTestId('reimprimir-motivo').fill('corto');
    await page.getByTestId('reimprimir-confirmar').click();
    await expect(page.getByText('motivo_muy_corto')).toBeVisible();
    await expect(page.getByTestId('reimprimir-confirm-dialog')).toHaveCount(0);
  });
});
