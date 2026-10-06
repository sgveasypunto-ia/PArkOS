import { installBrowserBridge, installBufferPolyfill } from './lib/browserBridge';

/**
 * Side-effect module, imported FIRST in `main.tsx`: in a plain browser
 * (lite installer, no Electron preload) it installs the `window.bridge`
 * shim before any other module reads it. Inside Electron the preload has
 * already defined `window.bridge`, so this is a no-op.
 */
if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
  installBrowserBridge(window, localStorage);
  installBufferPolyfill(window);
}
