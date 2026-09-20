# Tasks — HU-F9.1: Venta de suscripción desde caja (wizard 4 pasos)

> **Change**: `fase-9-1-venta-suscripcion` | **Phase**: sdd-tasks | **HU**: HU-F9.1
> **Mode**: strict TDD (RED → GREEN per commit); **forecast**: ~935 LOC; `size:exception` RATIFIED

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

## Work Units

| Unit | Goal | Focused test command | Rollback |
|---|---|---|---|
| 1 | `calcularMontoProporcional` pure fn + 4 tests | `pnpm test -- --run prorrateo` | Revert; F1.12 unaffected |
| 2 | `useVentaSuscripcion` SWR + 4 hook tests + stub remove | `pnpm test -- --run useVentaSuscripcion` | Revert; F9.2 unaffected |
| 3 | `Venta` wizard + 7 component tests | `pnpm test -- --run Venta` | Revert; PagoModal unaffected |
| 4 | PagoModal reuse in step 4 | `pnpm test -- --run Venta` | Revert; fallback inline |
| 5 | route + i18n + coverage + e2e + apply-progress | `pnpm test:coverage` + e2e + git grep | Revert; metadata only |

All 5 land in **one PR** (`feature/hu-f9-1-venta-suscripcion` → `dev`) per AD5 (`size:exception`).

---

## Phase 1 — Foundation (commits 1-2) [x]

### 1.1 RED + GREEN: prorrateo [x]

**RED** — `prorrateo.test.ts`: T1 `day≤15`→`null`; T2 `day>15`→`(valor/duracion)·restantes`; T3 `valor=30000,dur=30,day=19`→`11000`; T4 `day=30`→`1000`.

**GREEN** — `calcularMontoProporcional(plan, fecha): number | null`. Throws `PlanDuracionDiasInvalidoError` when `duracion_dias <= 0`.

Commit: `feat(suscripciones): calcularMontoProporcional + 4 tests` ✅ commit `b2a9bac`

### 1.2 RED + GREEN: useVentaSuscripcion [x]

**RED** — 4 tests: T1 201→parsed; T2 422 dup-placa→`VentaSuscripcionDuplicatePlateError`; T3 422 tipo-incompatible→typed; T4 401→`useAuthStore.clear()`+event.

**GREEN** — `useSWRMutation('/api/v1/clientes/venta-suscripcion')` + F7.2 `buildIdempotencyKey`. POST body `{cliente, placas, uuid_tipo_subscripcion, fecha_inicio_cobertura, cobrar_ahora, medio_pago?}`. Zod parse on 201; typed errors on 422; 401 logout.

**Drift guard**: delete dead stub `useSuscripcionesList.ts:80-98` (REQ-OPS-177).

Commit: `feat(suscripciones): useVentaSuscripcion SWR mutation + 4 hook tests` ✅ commit `7b25fb9`

---

## Phase 2 — Page (commits 3-4) [x]

### 2.1 RED + GREEN: Venta wizard [x]

**RED** — 7 tests: mount→paso1; paso1→paso2; NIT corto→inline; placa dup→typed; paso3→paso4; prorrateo badge day>15; confirm→trigger called.

**GREEN** — `useState<VentaStepState>` + per-step Zod. Step 2 catches typed errors inline.

Commit: `feat(suscripciones): Venta wizard 4 pasos + 7 component tests` ✅ commit `8021dd1`

### 2.2 Embed PagoModal in step 4 [x]

Step 4 renders `<PagoModal total={mp ?? plan.valor} uuid_ingreso={null} onSubmit={…} />`. On pago 201, wizard closes + navigates to `/suscripciones`.

Commit: `feat(suscripciones): PagoModal reuse integration in step 4` ✅ commit `5c2c9f9`

---

## Phase 3 — Polish (commit 5) [x]

Mechanical: App.tsx `/suscripciones/venta` route; +20 i18n keys; 3 vitest thresholds (prorrateo 95/95/90, hook 90/90/85, page 80/80/75); e2e stub with 4 scenarios; `apply-progress.md` + `verify-report.md` placeholder.

Commit: `docs(suscripciones): route + i18n + coverage + e2e + apply-progress`

---

## Pre-Commit Verification

```bash
pnpm --filter electron-sucursal test -- --run prorrateo useVentaSuscripcion Venta 2>&1 | tail -20
pnpm exec tsc -b --noEmit 2>&1 | grep -E "prorrateo|useVentaSuscripcion|Venta\.tsx"
pnpm exec eslint hooks/useVentaSuscripcion.ts pages/Venta.tsx lib/prorrateo.ts --max-warnings 0
git grep -nE "useVentaSuscripcion" features/suscripciones/hooks/useSuscripcionesList.ts  # MUST be 0
git diff dev..feature/hu-f9-1-venta-suscripcion --stat
```

---

## Drift Guards

| Guard | Command | Expected |
|---|---|---|
| Stub removed | `git grep useVentaSuscripcion useSuscripcionesList.ts` | 0 |
| Prorrateo usage | `git grep calcularMontoProporcional features/suscripciones` | ≥3 |
| Typed error | `git grep VentaSuscripcionDuplicatePlateError features/suscripciones` | ≥3 |
| PagoModal reuse | `git grep "from.*PagoModal" pages/Venta.tsx` | ≥1 |

---

## Out-of-Scope / Deferred

- HU-F9.2 listing + vencimiento banner
- HU-F8.2 FE polling wiring
- Renovación / anulación / cambio de plan mid-cycle (Fase 9.x+)
- Pago mixto (F8.1 §2.2 deferred)

---

**End of tasks — HU-F9.1.**
