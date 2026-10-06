import { Buffer as BufferPolyfill } from 'buffer';

import type { ApiStatus, BridgeSurface } from '../../../electron/bridge';

/**
 * Browser-mode shim for `window.bridge` (installer "lite").
 *
 * The real bridge is exposed by `electron/preload.ts`. The lite installer
 * serves the renderer with plain Vite in a regular browser, where there is
 * no preload, so every `window.bridge.*` call would throw. This shim is
 * installed ONLY when `window.bridge` is undefined (see `main.tsx`), so the
 * Electron build is never affected.
 *
 *   - authStore / tarifasStore -> localStorage (auth keeps the same flat
 *     keys as the ui-kit authStore fallback so both paths agree).
 *   - imprimir                 -> no-op, resolves `{ ok: true }` (no printer).
 *   - config.getApiOrigin      -> '' (same-origin; Vite proxies /api, /auth).
 *   - apiStatus                -> real probe of `/health` (proxied by Vite).
 */
const TARIFAS_PREFIX = 'parkos.browser.tarifas.';

type FetchLike = (input: string, init?: RequestInit) => Promise<{ ok: boolean; status: number }>;

export function createBrowserBridge(
  storage: Storage,
  fetchFn: FetchLike = (input, init) => fetch(input, init),
): BridgeSurface {
  const imprimir = Object.assign(
    async () => ({ ok: true, queueId: null }),
    {
      getQueue: async () => ({
        pending: 0,
        retrying: 0,
        fallido_permanente: 0,
        lastSuccessAt: null,
        lastError: null,
      }),
      onStatus: () => () => undefined,
    },
  );

  return {
    imprimir: imprimir as unknown as BridgeSurface['imprimir'],
    usb: { list: async () => [] },
    kiosk: { toggle: () => undefined },
    app: { quit: () => undefined },
    apiStatus: {
      get: async (): Promise<ApiStatus> => {
        const started = Date.now();
        try {
          const res = await fetchFn('/health', { cache: 'no-store' });
          return { ok: res.ok, latency_ms: Date.now() - started, code: res.status };
        } catch {
          return { ok: false, latency_ms: -1 };
        }
      },
    },
    config: { getApiOrigin: async () => '' },
    authStore: {
      get: async (key) => storage.getItem(key),
      set: async (key, value) => storage.setItem(key, value),
      delete: async (key) => storage.removeItem(key),
    },
    tarifasStore: {
      get: async (key) => storage.getItem(TARIFAS_PREFIX + key),
      set: async (key, value) => storage.setItem(TARIFAS_PREFIX + key, value),
      delete: async (key) => storage.removeItem(TARIFAS_PREFIX + key),
    },
  };
}

/** Installs the shim on `win` only when no real bridge is present. */
export function installBrowserBridge(
  win: { bridge?: unknown },
  storage: Storage,
): boolean {
  if (typeof win.bridge !== 'undefined') return false;
  win.bridge = createBrowserBridge(storage);
  return true;
}

/**
 * The ESC/POS builders (`lib/print/escposBuilder.ts`) call the global
 * `Buffer`, which only exists in Node/tests. In a plain browser every
 * print path threw ("No se pudo imprimir el tiquete"), so define it from
 * the `buffer` package when missing. Returns true when it installed it.
 */
export function installBufferPolyfill(win: { Buffer?: unknown }): boolean {
  if (typeof win.Buffer !== 'undefined') return false;
  win.Buffer = BufferPolyfill;
  return true;
}
