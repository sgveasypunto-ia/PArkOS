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
