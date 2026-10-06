import { describe, it, expect, vi, beforeEach } from 'vitest';

import { createBrowserBridge, installBrowserBridge, installBufferPolyfill } from './browserBridge';

function memoryStorage(): Storage {
  const m = new Map<string, string>();
  return {
    get length() {
      return m.size;
    },
    clear: () => m.clear(),
    getItem: (k) => (m.has(k) ? (m.get(k) as string) : null),
    key: (i) => Array.from(m.keys())[i] ?? null,
    removeItem: (k) => void m.delete(k),
    setItem: (k, v) => void m.set(k, String(v)),
  };
}

describe('browserBridge (modo navegador, sin Electron)', () => {
  let storage: Storage;
  beforeEach(() => {
    storage = memoryStorage();
  });

  it('installBrowserBridge instala el bridge solo si window.bridge no existe', () => {
    const win = {} as { bridge?: unknown };
    expect(installBrowserBridge(win as never, storage)).toBe(true);
    expect(win.bridge).toBeDefined();

    const real = { real: true };
    const win2 = { bridge: real } as { bridge?: unknown };
    expect(installBrowserBridge(win2 as never, storage)).toBe(false);
    expect(win2.bridge).toBe(real);
  });

  it('tarifasStore persiste get/set/delete en el storage con prefijo propio', async () => {
    const b = createBrowserBridge(storage);
    expect(await b.tarifasStore.get('k')).toBeNull();
    await b.tarifasStore.set('k', 'v');
    expect(await b.tarifasStore.get('k')).toBe('v');
    expect(storage.getItem('k')).toBeNull();
    await b.tarifasStore.delete('k');
    expect(await b.tarifasStore.get('k')).toBeNull();
  });

  it('authStore usa las mismas claves planas que el fallback de ui-kit', async () => {
    const b = createBrowserBridge(storage);
    await b.authStore.set('parkos.auth', 'x');
    expect(storage.getItem('parkos.auth')).toBe('x');
    expect(await b.authStore.get('parkos.auth')).toBe('x');
    await b.authStore.delete('parkos.auth');
    expect(storage.getItem('parkos.auth')).toBeNull();
  });

  it('imprimir es un no-op que resuelve ok con helpers getQueue/onStatus', async () => {
    const b = createBrowserBridge(storage);
    const res = await b.imprimir({} as never);
    expect(res.ok).toBe(true);
    expect(res.queueId).toBeNull();
    const q = await b.imprimir.getQueue();
    expect(q.pending).toBe(0);
    const off = b.imprimir.onStatus(() => undefined);
    expect(typeof off).toBe('function');
    expect(() => off()).not.toThrow();
  });

  it('config.getApiOrigin devuelve cadena vacia (same-origin via proxy de Vite)', async () => {
    expect(await createBrowserBridge(storage).config.getApiOrigin()).toBe('');
  });

  it('usb.list devuelve lista vacia y kiosk/app no lanzan', async () => {
    const b = createBrowserBridge(storage);
    expect(await b.usb.list()).toEqual([]);
    expect(() => b.kiosk.toggle(true)).not.toThrow();
    expect(() => b.app.quit()).not.toThrow();
  });

  it('apiStatus.get sondea /health y reporta ok segun el HTTP status', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    const b = createBrowserBridge(storage, fetchFn as never);
    const s = await b.apiStatus.get();
    expect(fetchFn).toHaveBeenCalledWith('/health', expect.anything());
    expect(s.ok).toBe(true);
    expect(s.code).toBe(200);
    expect(s.latency_ms).toBeGreaterThanOrEqual(0);
  });

  it('apiStatus.get reporta caido (ok false, latency -1) si fetch falla', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error('net'));
    const b = createBrowserBridge(storage, fetchFn as never);
    const s = await b.apiStatus.get();
    expect(s).toEqual({ ok: false, latency_ms: -1 });
  });
});

describe('installBufferPolyfill (el builder ESC/POS usa Buffer, ausente en el navegador)', () => {
  it('define Buffer solo si no existe y permite armar un buffer ESC/POS', () => {
    const target = {} as { Buffer?: unknown };
    expect(installBufferPolyfill(target)).toBe(true);
    const B = target.Buffer as typeof Buffer;
    expect(B.concat([B.from([0x1b, 0x40]), B.from('hola', 'utf8')]).toString('base64')).toBe(
      Buffer.from([0x1b, 0x40, 0x68, 0x6f, 0x6c, 0x61]).toString('base64'),
    );

    const real = { real: true };
    const withBuffer = { Buffer: real };
    expect(installBufferPolyfill(withBuffer)).toBe(false);
    expect(withBuffer.Buffer).toBe(real);
  });
});
