# Tasks: HU-F8.2 — FacturaDetalle FE status + reintento

> Change: `fase-8-2-factura-detalle-fe` | Strict TDD: ACTIVE
> Base: `dev @ 4c969a5` (F8.1 merged) | Forecast ~300 LOC | Branch: `feature/hu-f8-2-factura-detalle-fe`

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `useFacturaElectronica` terminal-state polling + 3 tests (F1/F2 existing + F4/F5 new) | PR 1 | `pnpm --filter electron-sucursal test -- --run useFacturaElectronica` | typecheck | Revert commit; F8.1 polling (constant 30s) restored |
| 2 | `useReintentarFE` useSWRMutation + 3 tests (201, 409 numeracion_agotada, 401) | PR 1 | `pnpm --filter electron-sucursal test -- --run useReintentarFE` | typecheck | Revert commit; FacturaElectronicaRetryPanel reverts to inline `parkosFetch` |
| 3 | `<FacturaDetalle />` routed page + 5 component tests | PR 1 | `pnpm --filter electron-sucursal test -- --run FacturaDetalle` | typecheck | Revert commit; route not registered (404 fallback) |
| 4 | PagoSheet navigate-after-201 + App.tsx route + i18n + e2e stub + apply-progress | PR 1 | `pnpm --filter electron-sucursal test -- --run PagoSheet` | typecheck | Revert commit; F8.1 stays as-is |

## Phase 1 — Hooks (commits 1-2)

- [x] 1.1 RED extend `hooks/useFacturaElectronica.test.ts` with F4 + F5 + F6 (computeRefreshInterval direct — pendiente=30_000, aceptado=0, rechazado=0); all three fail with `computeRefreshInterval is not a function`.
- [x] 1.2 GREEN update `hooks/useFacturaElectronica.ts`: export `computeRefreshInterval(latest)`; `refreshInterval: computeRefreshInterval` callback form. Add `TERMINAL_STATES = new Set(['aceptado','rechazado'])`. 6/6 tests pass.
- [x] 1.3 RED create `hooks/useReintentarFE.test.ts` with 3 failing tests (R1 201 returns `{uuid_envio, estado:'pendiente', uuid_envio_padre}` + mutate cache; R2 409 numeracion_agotada → `NumeracionAgotadaError`; R3 401 → `useAuthStore.clear` + event).
- [x] 1.4 GREEN create `hooks/useReintentarFE.ts`: `useSWRMutation(POST_PATH_PREFIX, mutateFn)`. `mutateFn` builds Idempotency-Key (F7.2 `buildIdempotencyKey`), POSTs via `parkosFetch`, maps 401 → `handle401()` (clears auth + event), maps 409 → `NumeracionAgotadaError`, awaits `globalMutate('/facturacion/factura-electronica/${uuid}')` before resolving. Mirrors `useRegistrarSalida.ts:73-101`. 3/3 tests pass.
- [x] 1.5 (skipped per F8.2 4-commit plan) `FacturaElectronicaRetryPanel.tsx` refactor deferred to F8.3 — page uses `useReintentarFE` directly; panel keeps inline `parkosFetch` for Dashboard mount contexts.
- [x] 1.6 (skipped per F8.2 4-commit plan) Same as 1.5.

## Phase 2 — Page + wiring (commits 3-4)

- [x] 2.1 RED create `pages/FacturaDetalle.test.tsx` with 5 failing tests (T1 pendiente, T2 aceptado + cufe, T3 rechazado + reintentar button, T4 click reintentar → trigger called with uuid, T5 `NumeracionAgotadaError` → banner role="alert").
- [x] 2.2 GREEN create `pages/FacturaDetalle.tsx`: `useParams<{uuid:string}>()`; uses `useFacturaElectronica` + `useReintentarFE` directly (no panel mount — avoids double-button); renders "Reintentar" button (only on `rechazado`, disabled while `isMutating`) + banner with `role="alert"` (only when `NumeracionAgotadaError` caught). 5/5 tests pass.
- [x] 2.3 UPDATE `components/PagoSheet.tsx`: import `useNavigate`; after `await trigger(post)`, narrow `result.factura_electronica` defensively via `typeof` (handles `z.unknown()`); `if (fe && typeof fe === 'object' && typeof fe.uuid === 'string') navigate('/factura-electronica/' + fe.uuid);` BEFORE `deferredSafePrint`. Existing 5 PagoSheet tests still pass (mocked via `vi.mock('react-router-dom')`).
- [x] 2.4 UPDATE `renderer/App.tsx`: import `<FacturaDetalle />` from `../features/facturacion/pages/FacturaDetalle`; add `<Route path="/factura-electronica/:uuid" element={<ProtectedRoute><FacturaDetalle /></ProtectedRoute>} />` BEFORE the `*` 404 fallback.
- [x] 2.5 UPDATE `renderer/i18n/locales/facturacion.json`: add `fe.estado_dian.{pendiente|enviado|aceptado|rechazado}` (nested) + `fe.errors.numeracion_agotada` = "Numeración agotada. Contactar proveedor.". Keep existing flat `fe.aceptado|rechazado|pendiente` for backward compat with the panel.
- [x] 2.6 NEW `e2e/fe.spec.ts`: 3 stub scenarios (estado visible, polling active+stops on terminal via fake timers, reintentar button → POST + cache mutated). Mirrors F8.1 `e2e/pago.spec.ts` stub format.
- [x] 2.7 NEW `openspec/changes/fase-8-2-factura-detalle-fe/apply-progress.md`: per-commit status table; `verify-report.md` placeholder (filled by sdd-verify). All phases `[x]`.

## Pre-Commit Verification

```bash
cd E:/easypunto_parkos/apps/electron-sucursal
pnpm test -- --run useFacturaElectronica useReintentarFE FacturaDetalle PagoSheet 2>&1 | tail -20
pnpm exec tsc -b --noEmit 2>&1 | grep -E "useFacturaElectronica|useReintentarFE|FacturaDetalle" | head -10
pnpm exec eslint src/features/facturacion/hooks/useFacturaElectronica.ts src/features/facturacion/hooks/useReintentarFE.ts src/features/facturacion/pages/FacturaDetalle.tsx --max-warnings 0
```

## Pre-merge gate

- `pnpm typecheck` exits 0
- `pnpm test -- --run useFacturaElectronica useReintentarFE FacturaDetalle PagoSheet` passes 16 tests (3+3+5+5 + integration)
- `pnpm lint` exits 0 (`--max-warnings 0`)
- `pnpm test:e2e fe.spec.ts` passes 3 stubs (sandbox F.6 caveat per F8.1)
- `git diff --stat` ≤ 800 LOC (forecast ~300)
- All 4 phases marked `[x]` in this file + `apply-progress.md` present
