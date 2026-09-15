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
  },
  build: {
    outDir: 'dist/renderer',
    emptyOutDir: true,
  },
});
