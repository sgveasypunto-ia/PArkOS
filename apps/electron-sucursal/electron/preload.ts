import { contextBridge, ipcRenderer } from 'electron';

/**
 * Preload — exposes a typed bridge to the renderer via contextBridge.
 *
 * F2.2 expanded the F2.1 empty placeholder with the 8-method whitelist
 * defined in `bridge.d.ts` (DEC-FETCH-08 + R4 mitigation). F5.1 grew
 * that surface to 11 methods by attaching two helpers to `imprimir`
 * without changing its call signature. F4.2 (2026-09-17 closure) adds
 * `tarifasStore` (3 methods) for the electron-store cache layer that
 * backs the `useTarifasVigentes` SWR `fallbackData` on cold start.
 *
 *   imprimir               → ipcRenderer.invoke('print:ticket', payload)
 *   imprimir.getQueue      → ipcRenderer.invoke('print:queue:get')
 *   imprimir.onStatus      → subscribe/unsubscribe to 'print:status'
 *   usb.list               → ipcRenderer.invoke('usb:list')
 *   kiosk.toggle(on)       → ipcRenderer.send('kiosk:toggle', on)
 *   app.quit()             → ipcRenderer.send('app:quit')
 *   apiStatus.get()        → ipcRenderer.invoke('api:status')
 *   authStore.get          → ipcRenderer.invoke('auth-store:get', key)
 *   authStore.set          → ipcRenderer.invoke('auth-store:set', key, value)
 *   authStore.delete       → ipcRenderer.invoke('auth-store:delete', key)
 *   tarifasStore.get       → ipcRenderer.invoke('tarifas-store:get', key)
 *   tarifasStore.set       → ipcRenderer.invoke('tarifas-store:set', key, value)
 *   tarifasStore.delete    → ipcRenderer.invoke('tarifas-store:delete', key)
 *
 * CRITICAL — explicit whitelist, NO spread. Spreading `ipcRenderer`
 * would expose every IPC channel + listener API to the renderer, which
 * is an Electron anti-pattern (`contextIsolation` would be meaningless).
 * Each method is declared individually so code review can audit the
 * surface and `preload.contract.test.ts` enforces the shape in CI.
 *
 * F5.1 — `imprimir` is built with `Object.assign(fn, helpers)` so the
 * F2.2 call site `bridge.imprimir(payload)` keeps working while the
 * additional helpers (`getQueue`, `onStatus`) hang off the same
 * identifier. This is the pattern Electron itself uses for native
 * classes that need both an entry function and helpers.
 */
function buildImprimir(): {
  (payload: unknown): Promise<unknown>;
  getQueue: () => Promise<unknown>;
  onStatus: (handler: (event: unknown) => void) => () => void;
} {
  const callFn = (payload: unknown): Promise<unknown> =>
    ipcRenderer.invoke('print:ticket', payload);
  const getQueue = (): Promise<unknown> => ipcRenderer.invoke('print:queue:get');
  const onStatus = (handler: (event: unknown) => void): (() => void) => {
    const listener = (_e: unknown, payload: unknown): void => handler(payload);
    ipcRenderer.on('print:status', listener);
    return () => ipcRenderer.off('print:status', listener);
  };
  return Object.assign(callFn, { getQueue, onStatus });
}

contextBridge.exposeInMainWorld('bridge', {
  imprimir: buildImprimir(),

  usb: {
    list: () => ipcRenderer.invoke('usb:list'),
  },

  kiosk: {
    toggle: (on) => ipcRenderer.send('kiosk:toggle', on),
  },

  app: {
    quit: () => ipcRenderer.send('app:quit'),
  },

  apiStatus: {
    get: () => ipcRenderer.invoke('api:status'),
  },

  authStore: {
    get: (key) => ipcRenderer.invoke('auth-store:get', key),
    set: (key, value) => ipcRenderer.invoke('auth-store:set', key, value),
    delete: (key) => ipcRenderer.invoke('auth-store:delete', key),
  },

  tarifasStore: {
    get: (key) => ipcRenderer.invoke('tarifas-store:get', key),
    set: (key, value) => ipcRenderer.invoke('tarifas-store:set', key, value),
    delete: (key) => ipcRenderer.invoke('tarifas-store:delete', key),
  },
});