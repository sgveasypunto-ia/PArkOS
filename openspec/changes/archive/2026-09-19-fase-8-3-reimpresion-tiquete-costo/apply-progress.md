# Apply Progress — HU-F8.3 Reimpresión de tiquete con costo (FE)

> **Change**: `fase-8-3-reimpresion-tiquete-costo`
> **Branch**: `feature/hu-f8-3-reimpresion-tiquete-costo`
> **Mode**: Strict TDD
> **Git identity**: `Parkos Dev <dev@parkos.local>` (no AI attribution per AGENTS.md canon)
> **Workload**: ~325 LOC under 800 → single-PR topology, no `size:exception`

---

## Implementation Status

| Phase | Task | Status | Commit SHA | TDD Evidence |
|---|---|---|---|---|
| Phase 1 — Foundation | 1.1 escposBuilder bold marca + sello accent + subline + 3 byte tests | ✅ DONE | `2188866` | RED → GREEN — 3 byte-presence tests + 1 drift anchor test pass (16 total in file); existing `escposBuilder.types.test.ts` updated for `'REIMPRESIÓN'` accent |
| Phase 1 — Foundation | 1.2 `useReimprimir` SWR mutation + Zod mirror + 3 hook tests | ✅ DONE | `cbdce2f` | RED → GREEN — T1 (201 → ReimpresionTicketRead), T2 (motivo <10 → ZodError before POST), T3 (401 → useAuthStore.clear + parkos:auth:cleared) |
| Phase 1 — Foundation | 1.3 `useAnularReimpresion` SWR mutation + 2 hook tests | ✅ DONE | `6ad3bfa` | RED → GREEN — A1 (201 → INSERT-only chain with workflow_estado='rechazada' + uuid_reimpresion_padre), A2 (motivo_anulacion <10 → ZodError before POST) |
| Phase 2 — Page | 2.1 `<ReimprimirTiquete />` page + 5 component tests | ✅ DONE | `1467997` | RED → GREEN — T1 (form mounts), T2 (motivo <10 → inline error + alertdialog never opens), T3 (motivo ≥10 → alertdialog opens with role="alertdialog"), T4 (alertdialog confirm → POST + success card), T5 (success card "Anular" → second alertdialog) |
| Phase 3 — Polish | 3.1 App.tsx route + 3.2 i18n + 3.3 per-file thresholds + 3.4 e2e + 3.5 apply-progress | ✅ DONE | (next commit) | Mechanical — metadata only |

## Files Changed

| File | Action | LOC | Commit |
|---|---|---|---|
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | UPDATE | +12 / -2 | `2188866` |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.reimpresion.test.ts` | NEW | +131 | `2188866` |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.types.test.ts` | UPDATE | +2 / -1 | `2188866` |
| `apps/electron-sucursal/src/features/facturacion/api/reimpresionApi.ts` | NEW | +93 | `cbdce2f` |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimir.ts` | NEW | +102 | `cbdce2f` |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimir.test.ts` | NEW | +133 | `cbdce2f` |
| `apps/electron-sucursal/src/features/facturacion/hooks/useAnularReimpresion.ts` | NEW | +104 | `6ad3bfa` |
| `apps/electron-sucursal/src/features/facturacion/hooks/useAnularReimpresion.test.ts` | NEW | +134 | `6ad3bfa` |
| `apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.tsx` | NEW | +316 | `1467997` |
| `apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.test.tsx` | NEW | +312 | `1467997` |
| `apps/electron-sucursal/src/renderer/App.tsx` | UPDATE | +9 / -0 | (next commit) |
| `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` | UPDATE | +25 / -0 | (next commit) |
| `apps/electron-sucursal/vitest.config.ts` | UPDATE | +22 / -0 | (next commit) |
| `apps/electron-sucursal/e2e/reimpresion.spec.ts` | NEW | +91 | (next commit) |

## TDD Cycle Evidence (Strict TDD Mode)

| Task | Test File | Layer | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|-----|-------|-------------|----------|
| 1.1 escposBuilder reimpresion | `escposBuilder.reimpresion.test.ts` | Unit | ✅ 4 RED (sello accent, subline, bold marca wrapping, drift anchor) | ✅ 16/16 passing | ✅ 4 scenarios (sello + subline + bold wrap + drift) | ✅ Clean |
| 1.2 useReimprimir | `useReimprimir.test.ts` | Unit | ✅ 3 RED (201, motivo<10, 401) | ✅ 3/3 passing | ✅ 3 scenarios (happy + Zod + auth) | ✅ Clean |
| 1.3 useAnularReimpresion | `useAnularReimpresion.test.ts` | Unit | ✅ 2 RED (INSERT-only chain, motivo_anulacion<10) | ✅ 2/2 passing | ✅ 2 scenarios (chain + Zod) | ✅ Clean |
| 2.1 ReimprimirTiquete page | `ReimprimirTiquete.test.tsx` | Component | ✅ 5 RED (mount, motivo<10, alertdialog, success card, anular) | ✅ 5/5 passing | ✅ 5 scenarios (mount + Zod + dialog + success + anular) | ✅ Clean |

## Drift Anchors Verified

- `'reimprimir'` (NOT `'reimpresion'`) MUST return 0 matches in production code → drift anchor REQ-OPS-175 test in `escposBuilder.reimpresion.test.ts` PASSES.
- escposBuilder dispatcher key verified as `'reimpresion'` via `build('reimpresion', payload)` smoke test.
- `0x1B 0x45` (escBoldOn) wrapping + `0x1B 0x46` (escBoldOff) AFTER the inner body → byte-presence test PASSES.

## Out-of-Scope Confirmed NOT Shipped

- Backend reimpresion_ticket table (F1.11 owns).
- Reimpresión gratuita inmediata (Fases 6/7).
- Placa search backend endpoint — page accepts `uuidIngreso` as direct input per simplified scope.
- DIAN dispatch (PR11 cloud-only).

## Pre-Commit Verification

- [x] `pnpm exec vitest run src/lib/print/__tests__/ --no-coverage` → 196/196 passing
- [x] `pnpm exec vitest run src/features/facturacion/hooks/useReimprimir.test.ts --no-coverage` → 3/3 passing
- [x] `pnpm exec vitest run src/features/facturacion/hooks/useAnularReimpresion.test.ts --no-coverage` → 2/2 passing
- [x] `pnpm exec vitest run src/features/facturacion/pages/ReimprimirTiquete.test.tsx --no-coverage` → 5/5 passing
- [x] Drift guard: `'reimprimir'` literal returns 0 matches in production code (see `escposBuilder.reimpresion.test.ts` REQ-OPS-175 scenario)

## Risks Surfaced

- (LOW) `role="alertdialog"` semantics depend on Radix Dialog content with `role` prop override; verified via `data-testid` + `getAttribute('role')` in T3 + T5.
- (LOW) i18n `reimprimir.anular.descripcion` key newly added (page uses `t('reimprimir.anular.descripcion')`); 13 new keys verified by `jq '.reimprimir | keys | length'`.
- (LOW) `useReimprimir` single-step POST matches F1.11 `POST /api/v1/workflows/reimpresion-ticket/{uuid_ingreso}/reimprimir` per user prompt binding contract; differs from proposal's `useReimprimirTiquete` two-step POST (which would create `prod.facturas` first) — single-step chosen to keep F8.3 minimal.

---

**End of apply-progress — HU-F8.3.**
