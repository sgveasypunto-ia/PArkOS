/**
 * Preload contract test — validates `preload.ts` exposes exactly the
 * 14 methods declared in `bridge.d.ts` (DEC-FETCH-08 + R4 mitigation).
 * Post-F4.2 closure (2026-09-17) the surface grew to 7 groups / 14 methods.
 *
 * Vitest aliases the `electron` module to `./__mocks__/electron.ts`
 * (see `vitest.config.ts`), so `preload.ts` calls the stub's
 * `contextBridge.exposeInMainWorld` / `ipcRenderer.invoke` / `send`
 * spies. The contract test asserts:
 *   1. Exactly the 7 top-level groups are present (no spread, no extras).
 *   2. `imprimir` is an OBJECT (callable + helpers per F5.1) and the
 *      helpers route to the correct channels.
 *   3. The raw `ipcRenderer` handle is NOT exposed.
 *   4. `tarifasStore` routes to the IPC handlers wired in `main.ts`
 *      (F4.2 closure — was previously missing; this test is the regression guard).
 */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { vi } from 'vitest';

import { contextBridge, ipcRenderer } from '../__mocks__/electron';

const exposeSpy = contextBridge.exposeInMainWorld as ReturnType<typeof vi.fn>;
const invokeSpy = ipcRenderer.invoke as ReturnType<typeof vi.fn>;
const sendSpy = ipcRenderer.send as ReturnType<typeof vi.fn>;
const onSpy = ipcRenderer.on as ReturnType<typeof vi.fn>;
const offSpy = ipcRenderer.off as ReturnType<typeof vi.fn>;

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
  onSpy.mockClear();
  offSpy.mockClear();
});

describe('preload bridge contract', () => {
  it('exposes exactly the 7 top-level groups (no spread, no extras)', () => {
    expect(Object.keys(exposed).sort()).toEqual(
      ['apiStatus', 'app', 'authStore', 'imprimir', 'kiosk', 'tarifasStore', 'usb'].sort(),
    );
  });

  it('tarifasStore.get routes to tarifas-store:get with the key verbatim', () => {
    const tarifasStore = exposed.tarifasStore as {
      get: (k: string) => Promise<unknown>;
      set: (k: string, v: string) => Promise<unknown>;
      delete: (k: string) => Promise<unknown>;
    };
    void tarifasStore.get('parkos.tarifas.cache.v1:suc-1');
    expect(invokeSpy).toHaveBeenCalledWith(
      'tarifas-store:get',
      'parkos.tarifas.cache.v1:suc-1',
    );
  });

  it('tarifasStore.set routes to tarifas-store:set with (key, value) verbatim', () => {
    const tarifasStore = exposed.tarifasStore as {
      set: (k: string, v: string) => Promise<unknown>;
    };
    void tarifasStore.set('k', '{"items":[]}');
    expect(invokeSpy).toHaveBeenCalledWith('tarifas-store:set', 'k', '{"items":[]}');
  });

  it('tarifasStore.delete routes to tarifas-store:delete with the key verbatim', () => {
    const tarifasStore = exposed.tarifasStore as {
      delete: (k: string) => Promise<unknown>;
    };
    void tarifasStore.delete('parkos.tarifas.cache.v1:suc-1');
    expect(invokeSpy).toHaveBeenCalledWith(
      'tarifas-store:delete',
      'parkos.tarifas.cache.v1:suc-1',
    );
  });

  it('exposes `imprimir` as an object with callable + getQueue + onStatus (F5.1)', () => {
    const imprimir = exposed.imprimir as {
      (p: unknown): Promise<unknown>;
      getQueue: () => Promise<unknown>;
      onStatus: (h: (event: unknown) => void) => () => void;
    };
    // F5.1: `imprimir` is no longer a plain function — it's an Object.assign(fn, helpers).
    expect(typeof imprimir).toBe('function');
    expect(typeof imprimir.getQueue).toBe('function');
    expect(typeof imprimir.onStatus).toBe('function');
  });

  it('`imprimir(payload)` invokes print:ticket with the payload verbatim', () => {
    const imprimir = exposed.imprimir as (p: unknown) => Promise<unknown>;
    void imprimir({ buffer: 'AA==', ticketId: 't-1', cut: true });
    expect(invokeSpy).toHaveBeenCalledWith('print:ticket', {
      buffer: 'AA==',
      ticketId: 't-1',
      cut: true,
    });
  });

  it('`imprimir.getQueue()` invokes print:queue:get', () => {
    const imprimir = exposed.imprimir as { getQueue: () => Promise<unknown> };
    void imprimir.getQueue();
    expect(invokeSpy).toHaveBeenCalledWith('print:queue:get');
  });

  it('`imprimir.onStatus(handler)` registers on print:status and returns an unsubscribe', () => {
    const imprimir = exposed.imprimir as {
      onStatus: (h: (event: unknown) => void) => () => void;
    };
    const handler = (_e: unknown): void => undefined;
    const unsubscribe = imprimir.onStatus(handler);
    expect(onSpy).toHaveBeenCalledWith('print:status', expect.any(Function));
    expect(typeof unsubscribe).toBe('function');
    unsubscribe();
    expect(offSpy).toHaveBeenCalledWith('print:status', expect.any(Function));
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