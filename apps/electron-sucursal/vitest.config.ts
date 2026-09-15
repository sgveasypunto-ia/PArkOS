import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src/renderer'),
      '@shared': path.resolve(__dirname, './src/shared'),
      // The Electron main-process module isn't installed in this app's
      // node_modules at test time; alias it to a tiny stub that the
      // preload contract test inspects via `vi.mocked()`.
      electron: path.resolve(__dirname, './electron/__mocks__/electron.ts'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/renderer/test-setup.ts'],
    css: false,
  },
});
