/**
 * Kiosko e2e (F2.3 — T7, G4/G8).
 *
 * Exercises the PIN unlock + lockout semantics against the packaged
 * Electron app:
 *   E4: kiosko mode + IPC `kiosk:unlock` with wrong PIN keeps the
 *       kiosko window active.
 *   E5: 3 failed unlock attempts trigger the 5-minute lockout; a
 *       fourth call returns `{reason:'lockout', lockoutSecondsRemaining:300}`.
 *   E6: the audit log emitted by `tryUnlockKiosko` contains
 *       `attempt_id`, ISO timestamp, and `success` boolean — and
 *       NEVER the PIN string.
 *
 * NOTE: e2e tests are authored but SKIPPED in this sandbox (F.6 +
 * npm 11.16.0 refuses workspace:* resolution). They will execute in CI
 * matrix (ubuntu-latest / macos-latest / windows-latest).
 */
import { test, expect, _electron as electron } from '@playwright/test';

const RUN_E2E = process.env['PARKOS_RUN_E2E'] === '1';

test.describe('electron-sucursal kiosko', () => {
  test.skip(!RUN_E2E, 'E2E skipped in sandbox F.6 — CI matrix required');

  test('E4: PIN incorrecto no desactiva kiosko', async () => {
    const app = await electron.launch({
      args: ['.'],
      env: { ...process.env, PARKOS_KIOSK_MODE: '1' },
    });
    const appWindow = await app.firstWindow();
    await appWindow.waitForLoadState('domcontentloaded');

    // The renderer invokes bridge.kiosk.unlock via a test-only hook
    // (F3.x replaces this with a proper modal UI). For F2.3 we
    // exercise the IPC channel directly.
    const unlockResult = await app.evaluate((_ipcMain, pin: string) => {
      return new Promise((resolve) => {
        // This arrow function is serialized and executed inside Electron's main
        // process via Playwright's app.evaluate(); a nested function body cannot
        // carry a static ES `import`, so a runtime `require()` is the only valid
        // loading mechanism here.
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { ipcRenderer } = require('electron');
        ipcRenderer.invoke('kiosk:unlock', pin).then(resolve);
      });
    }, '0000');

    expect(unlockResult).toMatchObject({ success: false });

    await expect.poll(async () => appWindow.isVisible()).toBe(true);
    await app.close();
  });

  test('E5: 3 intentos fallidos → lockout 5 minutos', async () => {
    const app = await electron.launch({
      args: ['.'],
      env: { ...process.env, PARKOS_KIOSK_MODE: '1' },
    });
    await app.firstWindow();

    // Three wrong attempts increment the counter; the fourth call
    // must return {reason:'lockout', lockoutSecondsRemaining:300}.
    for (let i = 0; i < 3; i += 1) {
      await app.evaluate(async (_ipcMain, pin: string) => {
        // eslint-disable-next-line @typescript-eslint/no-require-imports -- see note above: required at runtime inside the Electron main-process evaluate() context.
        const { ipcRenderer } = require('electron');
        return ipcRenderer.invoke('kiosk:unlock', pin);
      }, '9999');
    }

    const fourth = await app.evaluate(async (_ipcMain, pin: string) => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- see note above: required at runtime inside the Electron main-process evaluate() context.
      const { ipcRenderer } = require('electron');
      return ipcRenderer.invoke('kiosk:unlock', pin);
    }, '9999');

    expect(fourth).toMatchObject({
      success: false,
      reason: 'lockout',
      lockoutSecondsRemaining: 300,
    });
    await app.close();
  });

  test('E6: audit log kiosko.unlock_attempt contiene attempt_id + timestamp + success (NO PIN)', async () => {
    const app = await electron.launch({
      args: ['.'],
      env: { ...process.env, PARKOS_KIOSK_MODE: '1' },
    });
    await app.firstWindow();

    await app.evaluate(async (_ipcMain, pin: string) => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- see note above: required at runtime inside the Electron main-process evaluate() context.
      const { ipcRenderer } = require('electron');
      return ipcRenderer.invoke('kiosk:unlock', pin);
    }, '1234');

    // Read electron-log main.log via Node fs in the main process.
    const logs = await app.evaluate(async () => {
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- see note above: required at runtime inside the Electron main-process evaluate() context.
      const fs = require('node:fs');
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- see note above: required at runtime inside the Electron main-process evaluate() context.
      const path = require('node:path');
      // eslint-disable-next-line @typescript-eslint/no-require-imports -- see note above: required at runtime inside the Electron main-process evaluate() context.
      const logPath = path.join(require('electron').app.getPath('userData'), 'logs', 'main.log');
      if (!fs.existsSync(logPath)) return '';
      return fs.readFileSync(logPath, 'utf8');
    });

    // Audit invariant: every kiosko.unlock_attempt line carries
    // attempt_id + timestamp + success; the PIN never appears.
    expect(logs).toContain('kiosko.unlock_attempt');
    expect(logs).toContain('attemptId');
    expect(logs).toContain('timestamp');
    expect(logs).toContain('success');
    expect(logs).not.toContain('1234');

    await app.close();
  });
});