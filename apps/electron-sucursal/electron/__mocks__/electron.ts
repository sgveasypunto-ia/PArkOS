/**
 * Test stub for the `electron` module.
 *
 * Vitest's vite resolver aliases `electron` to this file (see
 * `vitest.config.ts`). We expose vi.fn()-backed spies for
 * `contextBridge.exposeInMainWorld`, `ipcRenderer.invoke`,
 * `ipcRenderer.send`, `ipcRenderer.on`, and `ipcRenderer.off` so
 * contract tests can assert on the bridge surface that preload.ts
 * produces.
 *
 * This file is ONLY loaded in tests; production code never sees it
 * because esbuild bundles the real `electron` module as external.
 */
import { vi } from 'vitest';

export const contextBridge = {
  exposeInMainWorld: vi.fn(),
};

export const ipcRenderer = {
  invoke: vi.fn(),
  send: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
};