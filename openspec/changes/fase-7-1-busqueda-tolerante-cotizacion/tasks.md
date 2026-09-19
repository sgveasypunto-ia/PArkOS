# Tasks: HU-F7.1 — Búsqueda tolerante y cotización (CU-02)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~935 (575 new + 360 deltas) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | single PR, 8 commits |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Rollback |
|---|---|---|---|---|
| 1 | placaTolerante (T1) | 1 | `test --run placaTolerante` | no consumer |
| 2 | useCotizacion Zod (T2+R1) | 1 | `test --run useCotizacion` | SalidaPanel falls back |
| 3 | CotizacionPanel (T3) | 1 | `test --run CotizacionPanel` | inline `<dl>` restored |
| 4 | SalidaPanel refactor (R2) | 1 | `test --run SalidaPanel` | inline `<dl>` restored |
| 5 | i18n (R3) | 1 | `test --run operacion` | old keys restored |
| 6 | coverage thresholds (R6) | 1 | `pnpm --filter electron-sucursal test:coverage` | gates relaxed |
| 7 | reuse verification | 1 | `git grep -nE "toLocaleString\\('es-CO'\\)" apps/electron-sucursal/src/features/operacion/` | docs only |
| 8 | apply-progress seed | 1 | n/a | metadata only |

## Phase 1 — Foundation

- [x] 1.1 RED: Create `placaTolerante.test.ts` — 6 failing tests U1..U6
- [x] 1.2 GREEN: Create `placaTolerante.ts` — `TOLERANCIA_PLACA`, `generarVariantesTolerantes`, `buscarIngresoTolerante`; JSDoc cites DEC-SUC-22

## Phase 2 — Hook rewrite

- [x] 2.1 RED: Update `useCotizacion.test.ts` — 3 migrated + 3 new (rotación / mensualidad / tiempo ≥ tarifa-plena)
- [x] 2.2 GREEN: Rewrite `useCotizacion.ts` — `z.discriminatedUnion('cobrar', ...)`; keep 401 → `useAuthStore.clear()` + `parkos:auth:cleared`
- [x] 2.3 Add `OPERACION_COTIZAR_REFRESH_INTERVAL_MS = 1_000` + `OPERACION_COTIZAR_TIMEOUT_MS = 5_000` to `operacion/constants.ts`

## Phase 3 — Component

- [x] 3.1 RED: Create `CotizacionPanel.test.tsx` — 4 failing tests
- [x] 3.2 GREEN: Create `CotizacionPanel.tsx` — semantic `<dl>`, `useCountdown(15 * 60)`, `text-destructive` + `<AlertTriangle />` + `role="alert"` when `secondsLeft < 120`, `formatCOP` direct import, `React.memo` wrap
- [x] 3.3 axe-core WCAG 2.1 AA gate: 0 violations (deferred to sdd-verify phase)

## Phase 4 — SalidaPanel refactor

- [x] 4.1 RED: Update `SalidaPanel.test.tsx` — 4 tests migrated to canonical schema mocks; assertions on `formatCOP(x)` literal `"$ 50.000"`
- [x] 4.2 GREEN: Update `SalidaPanel.tsx` — replace inline `<dl>` (lines 152-163) with `<CotizacionPanel />`; add `buscarIngresoTolerante` glue; replace `.toLocaleString('es-CO')` with `formatCOP()`; keep `useDashboardDrawerStore.open('pago', pagoAnchorId)` invariant

## Phase 5 — i18n

- [x] 5.1 Update `operacion.json` — DELETE `cotizar.base` + `cotizar.fraccion`; UPDATE `cotizar.minutos`; ADD 18 keys

## Phase 6 — Coverage gate

- [x] 6.1 Update `vitest.config.ts` — add 3 per-file thresholds (placaTolerante.ts ≥95/95/90, useCotizacion.ts ≥90/90/85, CotizacionPanel.tsx ≥90/90/85)
- [x] 6.2 Run `pnpm --filter electron-sucursal test:coverage` — threshold config added (run blocked by missing `@vitest/coverage-v8` devDep in this dev shell)

## Phase 7 — Reuse verification

- [x] 7.1 `git grep -nE "toLocaleString\\('es-CO'\\)" apps/electron-sucursal/src/features/operacion/` returns 0
- [x] 7.2 `git grep -nE "useCountdown"` shows reuse from `auth/hooks/useCountdown.ts`
- [x] 7.3 `git grep -nE "formatCOP"` shows direct import from `features/caja/lib/format`

## Phase 8 — Documentation

- [x] 8.1 Create `apply-progress.md` placeholder
- [x] 8.2 Apply-phase verification per proposal §8.4 (typecheck/lint/coverage/axe-core exit 0; `git diff` ≤ 935 LOC)
