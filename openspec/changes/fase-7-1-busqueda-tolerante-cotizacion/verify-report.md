```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: 28ff5c3c99d0a947b44554d42560130378b0ecb9
verdict: fail
blockers:
  - "5 of 24 F7.1-targeted tests fail at runtime due to missing @testing-library/jest-dom/vitest subpath. Setup file imports the matcher module but vitest cannot register toBeInTheDocument because node_modules/@testing-library/jest-dom/vitest does not exist."
  - "tsconfig.renderer.json does not include src/lib/**/*.ts. The F7.1-introduced src/lib/validation/placaTolerante.ts lives outside the typecheck project boundary. tsc -b emits TS6307 when SalidaPanel.tsx imports it."
critical_findings:
  - "Apply-progress TDD evidence is inaccurate: Commit 3 claims GREEN 4/4 for CotizacionPanel, but only 2/4 pass at re-run time (T1, T2 fail with Invalid Chai property: toBeInTheDocument). Commit 4 claims GREEN 5/5 for SalidaPanel, but only 2/5 pass (S1, S3, S5 fail). The non-toBeInTheDocument tests in both files pass."
  - "REQ-OPS-148 (cotizar.errors.iva_no_configurado banner) has no covering test and no implementation. CotizacionPanel.tsx does not render the banner anywhere."
  - "SalidaPanel.tsx declares onPagoSubmit as a required prop but never uses it (eslint error + TS6133)."
  - "CotizacionPanel.test.tsx and SalidaPanel.test.tsx import * as React from 'react' but never reference React (TS6133)."
  - "useCotizacion.test.ts:112 calls new ParkosHttpError(401) with 1 arg but the upstream type expects 3 args (TS2554)."
requirements:
  completed: 4
  total: 9
scenarios:
  completed: 4
  total: 10
test_command: cd apps/electron-sucursal && npx vitest run placaTolerante useCotizacion CotizacionPanel SalidaPanel
test_exit_code: 1
test_output_hash: sha256:7633931eba01aac055bd764cd2911194c77adf41fc71bd5d014d01d2b121bd39
build_command: cd apps/electron-sucursal && npx tsc -b --noEmit
build_exit_code: 1
build_output_hash: sha256:f7678a8a62d396294526f03ddc9c2256385c9237d3d654b816694ccb033bebc9
```

# Verification Report: HU-F7.1 — Búsqueda tolerante y cotización (CU-02) + schema drift reconciliation

> **Change**: `fase-7-1-busqueda-tolerante-cotizacion`
> **Phase**: sdd-verify
> **Branch**: `feature/hu-f7-1-busqueda-tolerante-cotizacion` (9 commits ahead of `dev`, NOT pushed, NOT merged)
> **Evidence revision**: `28ff5c3c99d0a947b44554d42560130378b0ecb9`
> **Mode**: Strict TDD
> **Verdict**: **FAIL**
> **Date**: 2026-09-19

## Summary

The implementation's CORE LOGIC is sound — all pure-function and hook tests that do not depend on the `@testing-library/jest-dom` matcher pass at runtime (15/15: placaTolerante 9/9, useCotizacion 6/6). However, the strict-tdd-verify gate FAILs on two independent grounds:

1. **Runtime test failures (CRITICAL)**: 5 of 24 F7.1-targeted tests fail because `@testing-library/jest-dom/vitest` does not register matchers. Apply-progress TDD evidence claims GREEN 4/4 for CotizacionPanel and GREEN 5/5 for SalidaPanel; verify-phase re-runs show 2/4 and 2/5 respectively. The failure is environmental (a missing devDependency subpath) but the TDD evidence is inaccurate.
2. **TypeScript project boundary (CRITICAL)**: `tsconfig.renderer.json` does not include `src/lib/**/*.ts`. The F7.1-introduced file `src/lib/validation/placaTolerante.ts` lives outside the typecheck project. `tsc -b --noEmit` reports TS6307 when SalidaPanel.tsx imports from this file.

A remediate session must (a) repair the test environment so `@testing-library/jest-dom` matchers register, (b) add `src/lib/**/*.ts` to `tsconfig.renderer.json` `include`, (c) implement the missing REQ-OPS-148 banner branch in `CotizacionPanel.tsx`, (d) re-run vitest + tsc to confirm GREEN.

## Test Results

| File | Tests | Passed | Failed |
|---|---|---|---|
| placaTolerante.test.ts | 9 | 9 | 0 |
| useCotizacion.test.ts | 6 | 6 | 0 |
| CotizacionPanel.test.tsx | 4 | 2 | 2 (T1, T2 — toBeInTheDocument env issue) |
| SalidaPanel.test.tsx | 5 | 2 | 3 (S1, S3, S5 — toBeInTheDocument env issue) |
| **Total** | **24** | **19** | **5** |

**Failure root cause (all 5)**: `Error: Invalid Chai property: toBeInTheDocument`. Setup file `src/renderer/test-setup.ts:1` imports `@testing-library/jest-dom/vitest`, but the package's vitest subpath is not present in `node_modules/@testing-library/jest-dom/`. The dev shell install is degraded.

**Build evidence**: `tsc -b --noEmit` exits 1. F7.1-introduced errors include:
- TS6307: `src/lib/validation/placaTolerante.ts` outside tsconfig.renderer.json include
- TS6133: `'React' is declared but its value is never read` in CotizacionPanel.test.tsx:14 and SalidaPanel.test.tsx:16
- TS6133: `'onPagoSubmit' is declared but its value is never used` in SalidaPanel.tsx:88
- TS2554: `new ParkosHttpError(401)` arity mismatch at useCotizacion.test.ts:112

**Coverage**: `@vitest/coverage-v8` not installed; per-file thresholds committed in `vitest.config.ts:32-36, 50-54, 56-60` cannot be enforced locally.

**Lint**: 1 error (`onPagoSubmit` unused in SalidaPanel.tsx:88).

## Spec Compliance Matrix

| REQ-OPS | Scenario | Covering test | Status |
|---|---|---|---|
| 143 rotación | CotizacionPanel T1 + SalidaPanel S3 | FAIL (env) |
| 143 mensualidad | CotizacionPanel T2 + SalidaPanel S5 | FAIL (env) |
| 144 typo AB0123 | placaTolerante U2 | PASS |
| 145 401 logout | useCotizacion C3 | PASS |
| 146 countdown threshold | CotizacionPanel T3 | PASS |
| 147 formatCOP | grep + T1 indirect | PARTIAL (grep ✅; T1 fails env) |
| 148 iva_no_configurado banner | NO COVERING TEST | UNTESTED + IMPLEMENTATION MISSING |
| 149 10 tests pass | useCotizacion C4-C6 + SalidaPanel S1-S5 | PARTIAL (6/6 hook pass; 2/5 SalidaPanel pass) |
| 150 per-file coverage | vitest.config.ts | TOOL MISSING |
| 151 variant bounds | placaTolerante U7, U8 | PASS |

**4 of 10 scenarios pass at runtime.**

## Issues Grouped

### CRITICAL

1. **5 of 24 F7.1 tests fail at runtime** — `toBeInTheDocument` matcher not registered. Fix path: repair `@testing-library/jest-dom/vitest` resolution (clean `pnpm install`).
2. **`tsconfig.renderer.json` missing `src/lib/**/*.ts`** — TS6307 on every F7.1 file that imports placaTolerante. Fix path: add to include array.
3. **REQ-OPS-148 implementation gap** — `CotizacionPanel.tsx` does NOT render `cotizar.errors.iva_no_configurado` banner. No test covers 500/iva_no_configurado path. Fix path: implement banner branch + add test C7.

### WARNING

4. `@vitest/coverage-v8` not installed — committed thresholds unverifiable locally.
5. `onPagoSubmit` declared but unused in SalidaPanel.tsx (TS6133 + eslint).
6. `import * as React` unused in CotizacionPanel.test.tsx + SalidaPanel.test.tsx (TS6133).
7. `ParkosHttpError(401)` arity mismatch in useCotizacion.test.ts (TS2554).
8. Apply-progress TDD evidence inaccurate: claims GREEN 4/4 and 5/5 when actually 2/4 and 2/5.

### SUGGESTION

9. Redundant `cleanup()` at CotizacionPanel.test.tsx:103.
10. Pre-existing test environment degraded (31 unrelated failures across the codebase).
11. Pre-existing typecheck errors (60+ errors across non-F7.1 files).

## Deviations Acceptance

| # | Deviation | Verdict |
|---|---|---|
| 1 | U7/U8 fixtures adjusted from `ABC123`/`ABC12O` to `ACDH23`/`ACDH2O` | ACCEPT — DEC-SUC-22 strict position-by-position confusable replacement is faithful |
| 2 | `varianteUsada` = typed input (normalized), `placaReal` = matched placa | ACCEPT — preserves operator UX |
| 3 | Relative paths instead of `@/` aliases | ACCEPT — vitest `@` maps to `./src/renderer`, not `./src`; codebase precedent at LoginForm.tsx:45 |
| 4 (new) | `useCountdown(15 * 60)` lives in SalidaPanel (parent), not in CotizacionPanel (per design §Decision) | ACCEPT — more-correct reading of pure presentational mandate |

## Final Verdict: **FAIL**

**Rationale**: 5 of 24 targeted tests fail at runtime, 1 spec scenario (REQ-OPS-148) has no implementation, tsconfig.renderer.json has a project-boundary gap emitting TS6307.

**Coverage**: 4/10 spec scenarios pass at runtime.

**Recommended next**: `sdd-remediate` in a new session. The implementation's CORE LOGIC is correct — failures are 90% environmental and 10% spec-coverage gaps. A clean install + minor code touch-ups should yield PASS.

## Relevant Files

- `apps/electron-sucursal/src/lib/validation/placaTolerante.ts` — NEW (209 lines, F7.1 T1)
- `apps/electron-sucursal/src/lib/validation/placaTolerante.test.ts` — NEW (165 lines, 9 tests)
- `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` — REWRITE (172 lines, F7.1 T2+R1)
- `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.test.ts` — UPDATE (206 lines, 6 tests)
- `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx` — NEW (182 lines, F7.1 T3)
- `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.test.tsx` — NEW (105 lines, 4 tests)
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` — UPDATE (227 lines, F7.1 R2)
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.test.tsx` — UPDATE (120 lines, 5 tests)
- `apps/electron-sucursal/src/features/operacion/constants.ts` — UPDATE (+25 LOC, F7.1 constants)
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` — UPDATE (i18n migration)
- `apps/electron-sucursal/vitest.config.ts` — UPDATE (3 new per-file thresholds)
- `apps/electron-sucursal/tsconfig.renderer.json` — **NEEDS UPDATE** (missing `src/lib/**/*.ts`)
- `apps/electron-sucursal/src/renderer/test-setup.ts` — needs diagnostic for jest-dom subpath resolution
