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
    // Exclude Playwright e2e specs (they live in `e2e/` and run under
    // `pnpm exec playwright test`, not Vitest).
    exclude: ['**/e2e/**', '**/node_modules/**', '**/dist/**'],
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
        // HU-F7.3 (REQ-OPS-158..160) — pure renderer-side ESC/POS byte
        // composition. Tightened to 19-CU-15S + 15-CU-15SM fields +
        // dynamic header + QR + logo markers (DEC-SUC-26..28). Per the
        // preflight budget review: ≥85/85/80 (lower than the >90% strict
        // mode because the builder has 4 typed bodies — some EOpcode
        // branches are defensive by design).
        'src/lib/print/escposBuilder.ts': {
          lines: 85,
          functions: 85,
          branches: 80,
        },
        // HU-F8.1 (BR7 / DEC-SUC-29) — pure DIAN módulo-11 NIT
        // verification with strict 16-prime-weight vector. ≥95/95/90
        // because the function has minimal branching (just length
        // validation + the modulo walk + DV comparison) — easy to
        // cover exhaustively.
        'src/lib/validation/nit.ts': {
          lines: 95,
          functions: 95,
          branches: 90,
        },
        // HU-F8.1 (REQ-OPS-167) — SWR mutation hook with 401 clear +
        // Idempotency-Key SHA-256 closure + Zod discriminated-union
        // response parse. ≥90/90/85 mirrors `useRegistrarSalida.ts`
        // precedent (F7.2) — both are POST mutations with the same
        // 401-handling and idempotency invariants.
        'src/features/facturacion/hooks/useRegistrarPago.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F8.3 (REQ-OPS-173) — SWR mutation hook with motivo Zod
        // pre-validation + Idempotency-Key SHA-256 + 401 auth-clear.
        // Mirrors useRegistrarPago precedent.
        'src/features/facturacion/hooks/useReimprimir.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F8.3 (REQ-OPS-174) — SWR mutation hook with motivo_anulacion
        // Zod + INSERT-only chain invariant + Idempotency-Key SHA-256.
        'src/features/facturacion/hooks/useAnularReimpresion.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F8.3 (REQ-OPS-171) — page composing useReimprimir +
        // useAnularReimpresion with alertdialog + RHF + Zod. Lower
        // threshold because the page renders 2 dialogs + a success
        // card (some unreachable branches when result===null).
        'src/features/facturacion/pages/ReimprimirTiquete.tsx': {
          lines: 80,
          functions: 80,
          branches: 75,
        },
        // HU-F9.1 (REQ-OPS-178) — pure A-09 prorrateo mirror. ≥95/95/90
        // because the function has 3 branches (day≤15 → null, day>15
        // with positive duracion, day>15 with duracion≤0 → throw) and
        // the date arithmetic is easy to cover exhaustively.
        'src/features/suscripciones/lib/prorrateo.ts': {
          lines: 95,
          functions: 95,
          branches: 90,
        },
        // HU-F9.1 (REQ-OPS-177 + REQ-OPS-179) — SWR mutation hook with
        // 401 clear + Idempotency-Key SHA-256 closure + 3 typed error
        // subclasses (422 mapping). ≥90/90/85 mirrors useRegistrarPago
        // precedent (F8.1) — both are POST mutations with the same
        // 401-handling and idempotency invariants.
        'src/features/suscripciones/hooks/useVentaSuscripcion.ts': {
          lines: 90,
          functions: 90,
          branches: 85,
        },
        // HU-F9.1 (REQ-OPS-176) — page composing useVentaSuscripcion +
        // PagoModal (F8.1) with 4-step wizard + per-step Zod. Lower
        // threshold because the page renders 4 conditional steps and
        // embeds PagoModal (which has its own coverage).
        'src/features/suscripciones/pages/Venta.tsx': {
          lines: 80,
          functions: 80,
          branches: 75,
        },
      },
    },
  },
});
