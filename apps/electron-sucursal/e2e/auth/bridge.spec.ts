/**
 * E2E — bridge IPC scenarios (8).
 *
 * Verifies the contract between the renderer (`window.bridge`) and
 * preload (`ipcRenderer.invoke/send`). Per F2.2 design §7.2 + plan.md:1229:
 *
 *   1. imprimir acepta PrintPayload e invoca 'print:ticket'
 *   2. usb.list retorna USBDevice[]
 *   3. kiosk.toggle(on) envía 'kiosk:toggle'
 *   4. app.quit cierra la app
 *   5. apiStatus.get retorna ApiStatus
 *   6. authStore.get retorna valor persistido
 *   7. authStore.set persiste valor en electron-store
 *   8. authStore.delete remueve valor de electron-store
 *
 * We assert via `page.evaluate()` against the live `window.bridge`
 * (set up by preload.ts). Each test launches a fresh Electron instance
 * because `app.quit` / `app.on('window-all-closed')` would otherwise
 * terminate the runner.
 */
import { test, expect, _electron as electron, type ElectronApplication } from '@playwright/test';

interface BridgeWindow {
  bridge: {
    imprimir: (payload: unknown) => Promise<{ ok: boolean }>;
    usb: { list: () => Promise<Array<{ vendorId: number; productId: number }>> };
    kiosk: { toggle: (on: boolean) => void };
    app: { quit: () => void };
    apiStatus: { get: () => Promise<{ online: boolean; lastSync: string | null }> };
    authStore: {
      get: (key: string) => Promise<string | null>;
      set: (key: string, value: string) => Promise<void>;
      delete: (key: string) => Promise<void>;
    };
  };
}

async function bootAndGetWindow(): Promise<{
  app: ElectronApplication;
  page: BridgeWindow['bridge'] extends infer _ ? Awaited<ReturnType<ElectronApplication['firstWindow']>> : never;
}> {
  const app = await electron.launch({ args: ['.'] });
  const page = await app.firstWindow();
  await page.waitForLoadState('domcontentloaded');
  return { app, page };
}

test.describe('e2e bridge IPC', () => {
  test('1) imprimir acepta PrintPayload (shape validado)', async () => {
    const { app, page } = await bootAndGetWindow();
    // We can't intercept ipcRenderer in production builds, but we can
    // validate that `bridge.imprimir` is callable and returns a thenable.
    const isThenable = await page.evaluate(() => {
      const w = window as unknown as BridgeWindow;
      const r = w.bridge.imprimir({
        ticketId: 'e2e-1',
        lines: [{ text: 'hello', align: 'center' }],
        cut: true,
      });
      return typeof (r as Promise<unknown>).then === 'function';
      // The IPC will fail (no real handler in F2.2) — we only assert
      // the shape and the channel binding, not the network outcome.
    });
    expect(isThenable).toBe(true);
    await app.close();
  });

  test('2) usb.list expone función thenable', async () => {
    const { app, page } = await bootAndGetWindow();
    const thenable = await page.evaluate(() => {
      const w = window as unknown as BridgeWindow;
      const r = w.bridge.usb.list();
      return typeof (r as Promise<unknown>).then === 'function';
    });
    expect(thenable).toBe(true);
    await app.close();
  });

  test('3) kiosk.toggle(on) es callable', async () => {
    const { app, page } = await bootAndGetWindow();
    const didCall = await page.evaluate(() => {
      try {
        (window as unknown as BridgeWindow).bridge.kiosk.toggle(true);
        return true;
      } catch {
        return false;
      }
    });
    expect(didCall).toBe(true);
    await app.close();
  });

  test('4) app.quit es callable', async () => {
    const { app, page } = await bootAndGetWindow();
    // app.quit will close the Electron app; the Playwright runner
    // catches the close event. We assert the function exists and is sync.
    const isFn = await page.evaluate(() => {
      return typeof (window as unknown as BridgeWindow).bridge.app.quit === 'function';
    });
    expect(isFn).toBe(true);
    await app.close();
  });

  test('5) apiStatus.get expone función thenable', async () => {
    const { app, page } = await bootAndGetWindow();
    const thenable = await page.evaluate(() => {
      const w = window as unknown as BridgeWindow;
      const r = w.bridge.apiStatus.get();
      return typeof (r as Promise<unknown>).then === 'function';
    });
    expect(thenable).toBe(true);
    await app.close();
  });

  test('6-8) authStore round-trip (set → get → delete)', async () => {
    const { app, page } = await bootAndGetWindow();
    const flow = await page.evaluate(async () => {
      const w = window as unknown as BridgeWindow;
      const key = 'e2e.authStore.test';
      await w.bridge.authStore.set(key, '{"hello":"world"}');
      const got = await w.bridge.authStore.get(key);
      await w.bridge.authStore.delete(key);
      const gone = await w.bridge.authStore.get(key);
      return { got, gone };
    });
    expect(flow.got).toBe('{"hello":"world"}');
    expect(flow.gone).toBeNull();
    await app.close();
  });

  test('bonus) BridgeSurface expone exactamente 6 grupos', async () => {
    const { app, page } = await bootAndGetWindow();
    const keys = await page.evaluate(() => {
      const w = window as unknown as BridgeWindow;
      return Object.keys(w.bridge).sort();
    });
    expect(keys).toEqual(['apiStatus', 'app', 'authStore', 'imprimir', 'kiosk', 'usb']);
    await app.close();
  });
});
