import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

/**
 * Vite config — renderer process only.
 *
 * The main and preload processes are bundled separately by `esbuild-main.mjs`
 * (target node20, format cjs, external:electron) per DEC-ELEC-03. The renderer
 * is a regular SPA loaded by Electron's BrowserWindow.
 */
export default defineConfig({
  // Relative asset paths (not Vite's default `/` root-relative) - the
  // packaged app loads index.html via `file://` (electron/main.ts's
  // `loadFile`, non-dev branch), where a root-relative `src="/assets/..."`
  // resolves against the filesystem root, not the HTML file's own
  // directory. Confirmed against the real built dist/renderer/index.html:
  // every `<script src="/assets/...">`/`<link href="/assets/...">` was
  // absolute, so the bundle never loaded - packaged window showed a blank/
  // black screen with the default Electron menu (main.ts never got the
  // chance to render anything, no JS ran) while `pnpm dev` (served over
  // http://localhost:5173, where root-relative paths are fine) worked.
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src/renderer'),
      '@shared': path.resolve(__dirname, './src/shared'),
    },
  },
  root: '.',
  server: {
    port: 5173,
    strictPort: true,
    // Dev proxy: reenvía /api/* al backend api-sucursal en Docker.
    // parkosFetch usa paths relativos (`/api/v1/...`) y los resuelve
    // contra el origin del Vite dev server (:5173). Sin este proxy
    // el navegador haría la petición a localhost:5173/api/... que no
    // existe. El backend ya está corriendo en Docker como
    // `parkos-api-sucursal` mapeado a host port 8100.
    proxy: {
      '/api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        secure: false,
      },
      // parkosFetch en useAuth llama `/auth/me` (sin prefijo /api/v1) y otros
      // endpoints siguen el mismo patrón. Proxy catch-all para que el browser
      // reciba la respuesta del backend real, no el index.html de Vite.
      '/auth': {
        target: 'http://localhost:8100/api/v1',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: 'dist/renderer',
    emptyOutDir: true,
  },
});
