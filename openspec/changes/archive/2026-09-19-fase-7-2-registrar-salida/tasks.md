# Tasks: HU-F7.2 — Registrar salida (rotación + mensualidad) — UI integration

> Change: `fase-7-2-registrar-salida` | Strict TDD: ACTIVE
> Base: `dev @ f45b347` | Forecast ~410 LOC

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `useRegistrarSalida` SWR mutation + 3 hook tests | PR 1 | `pnpm --filter electron-sucursal test -- --run useRegistrarSalida` | typecheck | Revert commit; CotizacionPanel still works without confirmation |
| 2 | `buildIdempotencyKey` pure fn + 2 unit tests + AST drift guard | PR 1 | `pnpm --filter electron-sucursal test -- --run idempotency` | grep | Revert commit; SHA-256 helper unused |
| 3 | `salidaApi.ts` Zod mirror + 1 integration test | PR 1 | `pnpm --filter electron-sucursal test -- --run salidaApi` | typecheck | Revert commit; api layer unused |
| 4 | `SalidaFlow` + `SalidaMensualidad` pages + composition in SalidaPanel | PR 1 | `pnpm --filter electron-sucursal test -- --run Salida` | typecheck | Revert commit; SalidaPanel falls back to F7.1 |
| 5 | `salida_duplicada` 409 UI handling + 1 hook test | PR 1 | `pnpm --filter electron-sucursal test -- --run SalidaDuplicada` | typecheck | Revert commit; 409 propagates as throw |
| 6 | i18n keys migration | PR 1 | `pnpm --filter electron-sucursal test -- --run operacion` | typecheck | Revert commit; keys default |
| 7 | Per-file coverage thresholds | PR 1 | `pnpm --filter electron-sucursal test:coverage` | lint | Revert commit; gate relaxed |
| 8 | `e2e/salida.spec.ts` (3 scenarios) | PR 1 | `pnpm --filter electron-sucursal test:e2e salida` | e2e harness | Revert commit; spec deleted |
| 9 | `apply-progress` + `verify-report` seed | PR 1 | n/a | n/a | Revert commit; metadata only |

## Phase 1 — Foundation (commits 1–3)

- [x] 1.1 RED `hooks/__tests__/useRegistrarSalida.test.ts`: 3 failing tests.
- [x] 1.2 GREEN `hooks/useRegistrarSalida.ts`: `useSWRMutation`; `Idempotency-Key`; 401 → `useAuthStore.clear()` + event.
- [x] 1.3 RED `lib/__tests__/idempotency.test.ts`: 2 tests.
- [x] 1.4 GREEN `lib/idempotency.ts`: pure `buildIdempotencyKey` SHA-256 (Web Crypto).
- [x] 1.5 RED `api/__tests__/salidaApi.test.ts`: 1 Zod round-trip test.
- [x] 1.6 GREEN `api/salidaApi.ts`: Zod mirror of `SalidaReadForzado`; composes `parkosFetch`.

## Phase 2 — UI composition (commit 4)

- [x] 2.1 RED `pages/__tests__/SalidaFlow.test.tsx` + `SalidaMensualidad.test.tsx`: 3 failing tests.
- [x] 2.2 GREEN `pages/SalidaFlow.tsx`: wizard over `<CotizacionPanel />`; routes by `response.tipo_salida`.
- [x] 2.3 GREEN `pages/SalidaMensualidad.tsx`: 1-screen atajo; fires `bridge.imprimir` envelope.
- [x] 2.4 REFACTOR `components/SalidaPanel.tsx` (+20): compose `SalidaFlow`/`SalidaMensualidad` inline.
- [x] 2.5 REFACTOR `components/SalidaSheet.tsx` (+5): pass `uuid_ingreso` through.

## Phase 3 — Error handling (commit 5)

- [x] 3.1 RED extend `useRegistrarSalida.test.ts`: `salida_duplicada` test (mocked 409).
- [x] 3.2 GREEN add `SalidaDuplicadaError`; wire 409 → typed error.
- [x] 3.3 REFACTOR inline banner in `SalidaFlow.tsx` (REQ-OPS-156).

## Phase 4 — i18n (commit 6)

- [x] 4.1 Update `renderer/i18n/locales/operacion.json`: add `cotizar.errors.salida_duplicada`, `cotizar.errors.cotizacion_expirada`, `cotizar.confirmar_salida` (es-CO).

## Phase 5 — Coverage gate (commit 7)

- [x] 5.1 Update `vitest.config.ts`: per-file thresholds — `useRegistrarSalida.ts` ≥90/90/85, `idempotency.ts` ≥95/95/90.

## Phase 6 — E2E (commit 8)

- [x] 6.1 Create `e2e/salida.spec.ts`: 3 Playwright scenarios + `bridge.imprimir` spy.
- [x] 6.2 Add AST drift guard to lint: `salidas/mensualidad` + `mensualidad_no_vigente` MUST exit 0 matches (REQ-OPS-155).

## Phase 7 — Documentation (commit 9)

- [x] 7.1 Create `apply-progress.md` (work-unit commit table).
- [x] 7.2 Create placeholder `verify-report.md` (filled by sdd-verify).

Pre-merge gate: `pnpm lint`, `typecheck`, `test:coverage` exit 0; `test:e2e salida` passes 3 scenarios; AST drift guards 0 matches; `git diff` ≤ 800 LOC.
