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
    coverage: {
      provider: 'v8',
      thresholds: {
        // HU-F4.1 (T1) — función pura de detección de placa
        'src/lib/validation/placa.ts': {
          lines: 95,
          functions: 95,
          branches: 90,
        },
        // HU-F7.1 (T1) — pure tolerant placa search + variant generator
        'src/lib/validation/placaTolerante.ts': {
          lines: 95,
          functions: 95,
          branches: 90,
        },
        // HU-F4.1 (T2) — typed wrapper HTTP con 404 → []
        'src/features/catalogos/api/tiposVehiculoApi.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F4.1 (T2) — SWR hook con fallback hardcoded + 401 clear
        'src/features/catalogos/hooks/useTiposVehiculo.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F7.1 (T2+R1) — SWR hook con Zod discriminated union + 401 clear
        'src/features/operacion/hooks/useCotizacion.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F7.1 (T3) — presentational panel con dos ramas de render
        'src/features/operacion/components/CotizacionPanel.tsx': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F7.2 (I1) — SWR mutation hook con 401/409 handling + Idempotency-Key
        'src/features/operacion/hooks/useRegistrarSalida.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F7.2 (I2) — pure SHA-256 closure over canonicalJson (RFC 8785)
        'src/features/operacion/lib/idempotency.ts': {
          lines: 95,
          functions: 95,
          branches: 90,
        },
      },
    },
  },
});
