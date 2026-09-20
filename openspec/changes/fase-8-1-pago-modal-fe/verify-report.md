# Verify Report: HU-F8.1 — Pago modal (efectivo/datáfono) con FE

> **Status**: pending — placeholder. The `sdd-verify` phase will populate this file with the byte-level + behavioural + integration test results that prove the implementation matches `proposal.md` / `specs/operacion.md` / `design.md`.

## Planned verify scope

| Test layer | Command | Expected |
|------------|---------|----------|
| Unit (nit) | `pnpm test -- --run src/lib/validation/nit.test.ts` | 5/5 |
| Unit (useRegistrarPago) | `pnpm test -- --run src/features/facturacion/hooks/useRegistrarPago.test.ts` | 4/4 |
| Unit (escposBuilder.recibo) | `pnpm test -- --run src/lib/print/__tests__/escposBuilder.recibo.test.ts` | 4/4 + 12 existing |
| Unit (PagoModal) | `pnpm test -- --run src/features/facturacion/components/PagoModal.test.tsx` | 5/5 |
| Unit (PagoSheet regression) | `pnpm test -- --run src/features/facturacion/components/PagoSheet.test.tsx` | 5/5 |
| Typecheck | `pnpm exec tsc -b --noEmit` | 0 errors |
| Lint | `pnpm exec eslint src/lib/validation/nit.ts src/features/facturacion/hooks/useRegistrarPago.ts src/features/facturacion/components/PagoModal.tsx src/features/facturacion/components/PagoSheet.tsx src/lib/print/escposBuilder.ts --max-warnings 0` | 0 errors |
| Coverage | `pnpm test:coverage` | nit ≥95/95/90, useRegistrarPago ≥90/90/85 |
| E2E stub | `pnpm exec playwright test e2e/pago.spec.ts` | 6/6 stubs pass |
| Drift guard (DEC-SUC-28) | `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` | 0 matches |
| Drift guard (idempotency SHA-256) | `grep -r 'Idempotency-Key' apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` | 1 match (correct) |
| Drift guard (consumidor final) | `grep -r '222222222222222' apps/electron-sucursal/src/features/facturacion` | 2 matches (PagoModal default + PagoSheet fallback) |

## Sign-off

- [ ] Orchestrator: verify report populated
- [ ] Orchestrator: archive delta specs synced
- [ ] Session close: merge to `dev` + delete feature branch
- [ ] GitHub: PR opened (deferred to session-close merge step per AGENTS.md §8)