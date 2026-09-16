/**
 * Preload contract test — validates `preload.ts` exposes exactly the
 * 8 methods declared in `bridge.d.ts` (DEC-FETCH-08 + R4 mitigation).
 *
 * Vitest aliases the `electron` module to `./__mocks__/electron.ts`
 * (see `vitest.config.ts`), so `preload.ts` calls the stub's
 * `contextBridge.exposeInMainWorld` / `ipcRenderer.invoke` / `send`
 * spies. The contract test asserts:
 *   1. Exactly the 6 top-level groups are present (no spread, no extras).
 *   2. Each method invokes the correct IPC channel with the correct args.
 *   3. The raw `ipcRenderer` handle is NOT exposed.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { contextBridge, ipcRenderer } from '../__mocks__/electron';

const exposeSpy = contextBridge.exposeInMainWorld as ReturnType<typeof vi.fn>;
const invokeSpy = ipcRenderer.invoke as ReturnType<typeof vi.fn>;
const sendSpy = ipcRenderer.send as ReturnType<typeof vi.fn>;

let exposed: Record<string, unknown> = {};

beforeAll(async () => {
  // Import preload ONCE so the top-level `exposeInMainWorld` call runs
  // exactly once. We capture the exposed surface for the test suite.
  exposeSpy.mockImplementation((name: unknown, api: unknown) => {
    if (name === 'bridge') {
      exposed = api as Record<string, unknown>;
    }
  });
  await import('../preload');
});

beforeEach(() => {
  invokeSpy.mockClear();
  sendSpy.mockClear();
});

describe('preload bridge contract', () => {
  it('exposes exactly the 6 top-level groups (no spread, no extras)', () => {
    expect(Object.keys(exposed).sort()).toEqual(
      ['apiStatus', 'app', 'authStore', 'imprimir', 'kiosk', 'usb'].sort(),
    );
  });

  it('exposes `imprimir(payload)` and invokes print:ticket', () => {
    const imprimir = exposed.imprimir as (p: unknown) => Promise<unknown>;
    expect(typeof imprimir).toBe('function');
    void imprimir({ ticketId: 't-1', lines: [], cut: true });
    expect(invokeSpy).toHaveBeenCalledWith('print:ticket', {
      ticketId: 't-1',
      lines: [],
      cut: true,
    });
  });

  it('exposes `usb.list()` and invokes usb:list', () => {
    const usb = exposed.usb as { list: () => Promise<unknown> };
    expect(typeof usb.list).toBe('function');
    void usb.list();
    expect(invokeSpy).toHaveBeenCalledWith('usb:list');
  });

  it('exposes `kiosk.toggle(on)` and sends kiosk:toggle', () => {
    const kiosk = exposed.kiosk as { toggle: (on: boolean) => void };
    expect(typeof kiosk.toggle).toBe('function');
    kiosk.toggle(true);
    expect(sendSpy).toHaveBeenCalledWith('kiosk:toggle', true);
  });

  it('exposes `app.quit()` and sends app:quit', () => {
    const app = exposed.app as { quit: () => void };
    expect(typeof app.quit).toBe('function');
    app.quit();
    expect(sendSpy).toHaveBeenCalledWith('app:quit');
  });

  it('exposes `apiStatus.get()` and invokes api:status', () => {
    const apiStatus = exposed.apiStatus as { get: () => Promise<unknown> };
    expect(typeof apiStatus.get).toBe('function');
    void apiStatus.get();
    expect(invokeSpy).toHaveBeenCalledWith('api:status');
  });

  it('apiStatus.get retorna ApiStatus shape F2.3 (ok / latency_ms / code?)', () => {
    const apiStatus = exposed.apiStatus as { get: () => Promise<unknown> };
    // F2.3 shape per DEC-UPD-12: {ok, latency_ms, code?}.
    invokeSpy.mockResolvedValueOnce({ ok: true, latency_ms: 42, code: 200 });
    return apiStatus.get().then((status) => {
      expect(status).toMatchObject({
        ok: expect.any(Boolean),
        latency_ms: expect.any(Number),
      });
      expect(typeof (status as { code?: number }).code === 'undefined' ||
        typeof (status as { code?: number }).code === 'number').toBe(true);
    });
  });

  it('exposes `authStore.get/set/delete` invoking the matching channels', () => {
    const authStore = exposed.authStore as {
      get: (k: string) => Promise<string | null>;
      set: (k: string, v: string) => Promise<void>;
      delete: (k: string) => Promise<void>;
    };
    expect(typeof authStore.get).toBe('function');
    expect(typeof authStore.set).toBe('function');
    expect(typeof authStore.delete).toBe('function');

    void authStore.get('parkos.auth');
    expect(invokeSpy).toHaveBeenLastCalledWith('auth-store:get', 'parkos.auth');

    void authStore.set('parkos.auth', '{}');
    expect(invokeSpy).toHaveBeenLastCalledWith('auth-store:set', 'parkos.auth', '{}');

    void authStore.delete('parkos.auth');
    expect(invokeSpy).toHaveBeenLastCalledWith('auth-store:delete', 'parkos.auth');
  });

  it('does NOT leak the raw ipcRenderer handle (whitelist-only)', () => {
    expect((exposed as Record<string, unknown>).ipcRenderer).toBeUndefined();
    expect((exposed as Record<string, unknown>).contextBridge).toBeUndefined();
  });
});
