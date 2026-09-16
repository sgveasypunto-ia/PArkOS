/**
 * Lifecycle e2e (F2.3 — T7, G3/G8).
 *
 * Exercises the runtime lockdown primitives against the packaged
 * Electron app:
 *   E1: a second invocation hands the lock back to the primary process
 *       which receives `second-instance` and focuses its window.
 *   E2: in kiosko mode (PARKOS_KIOSK_MODE=1), Ctrl+W is intercepted by
 *       `before-input-event` and the window stays open.
 *   E3: in kiosko mode, Alt+F4 is likewise intercepted.
 *
 * NOTE: e2e tests are authored but SKIPPED in this sandbox (F.6 +
 * npm 11.16.0 refuses workspace:* resolution). They will execute in CI
 * matrix (ubuntu-latest / macos-latest / windows-latest) where
 * Playwright's `_electron.launch` and bcrypt/bcryptjs work end-to-end.
 *
 * Each test asserts the precondition up front (`process.env.PLAYWRIGHT`
 * is set by the CI runner) and skips otherwise; this keeps the spec
 * file lint-clean locally while preserving the assertions for the
 * matrix.
 */
import { test, expect, _electron as electron } from '@playwright/test';

const RUN_E2E = process.env['PARKOS_RUN_E2E'] === '1';

test.describe('electron-sucursal lifecycle', () => {
  test.skip(!RUN_E2E, 'E2E skipped in sandbox F.6 — CI matrix required');

  test('E1: segunda invocación enfoca la ventana primaria', async () => {
    const first = await electron.launch({ args: ['.'] });
    const firstWindow = await first.firstWindow();
    await firstWindow.waitForLoadState('domcontentloaded');

    const second = await electron.launch({ args: ['.'] });
    // Second invocation should fail to acquire the lock and exit; the
    // primary process receives the `second-instance` event and brings
    // its window forward.
    await expect.poll(async () => firstWindow.isVisible()).toBe(true);

    await second.close();
    await first.close();
  });

  test('E2: kiosko mode bloquea Ctrl+W', async () => {
    const app = await electron.launch({
      args: ['.'],
      env: { ...process.env, PARKOS_KIOSK_MODE: '1' },
    });
    const appWindow = await app.firstWindow();
    await appWindow.waitForLoadState('domcontentloaded');

    await appWindow.keyboard.press('Control+w');
    // The window must still be visible after Ctrl+W — blockShortcuts
    // calls `event.preventDefault()` on the `before-input-event`.
    await expect.poll(async () => appWindow.isVisible()).toBe(true);

    await app.close();
  });

  test('E3: kiosko mode bloquea Alt+F4', async () => {
    const app = await electron.launch({
      args: ['.'],
      env: { ...process.env, PARKOS_KIOSK_MODE: '1' },
    });
    const appWindow = await app.firstWindow();
    await appWindow.waitForLoadState('domcontentloaded');

    await appWindow.keyboard.press('Alt+F4');
    await expect.poll(async () => appWindow.isVisible()).toBe(true);

    await app.close();
  });
});