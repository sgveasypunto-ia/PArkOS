import { contextBridge, ipcRenderer } from 'electron';

/**
 * Preload — exposes a typed bridge to the renderer via contextBridge.
 *
 * F2.2 expands the F2.1 empty placeholder with the 8-method whitelist
 * defined in `bridge.d.ts` (DEC-FETCH-08 + R4 mitigation):
 *
 *   imprimir          → ipcRenderer.invoke('print:ticket', payload)
 *   usb.list          → ipcRenderer.invoke('usb:list')
 *   kiosk.toggle(on)  → ipcRenderer.send('kiosk:toggle', on)
 *   app.quit()        → ipcRenderer.send('app:quit')
 *   apiStatus.get()   → ipcRenderer.invoke('api:status')
 *   authStore.get     → ipcRenderer.invoke('auth-store:get', key)
 *   authStore.set     → ipcRenderer.invoke('auth-store:set', key, value)
 *   authStore.delete  → ipcRenderer.invoke('auth-store:delete', key)
 *
 * CRITICAL — explicit whitelist, NO spread. Spreading `ipcRenderer`
 * would expose every IPC channel + listener API to the renderer, which
 * is an Electron anti-pattern (`contextIsolation` would be meaningless).
 * Each method is declared individually so code review can audit the
 * surface and `preload.contract.test.ts` enforces the shape in CI.
 */
contextBridge.exposeInMainWorld('bridge', {
  imprimir: (payload) => ipcRenderer.invoke('print:ticket', payload),

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
});
