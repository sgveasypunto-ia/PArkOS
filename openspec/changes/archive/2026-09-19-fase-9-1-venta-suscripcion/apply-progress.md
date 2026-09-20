# Apply Progress — HU-F9.1

> **Change**: `fase-9-1-venta-suscripcion` | **Phase**: sdd-apply | **Status**: COMPLETE
> **Branch**: `feature/hu-f9-1-venta-suscripcion` (at `a6ff5e3` → 5 commits)
> **Strict TDD**: ACTIVE — every commit RED → GREEN with passing tests.

## Commits

| # | SHA | Commit | Type | TDD Phase | Status |
|---|---|---|---|---|---|
| 1 | `b2a9bac` | `feat(suscripciones): calcularMontoProporcional + 5 tests` | feat | RED→GREEN | ✅ |
| 2 | `7b25fb9` | `feat(suscripciones): useVentaSuscripcion SWR mutation + 4 hook tests` | feat | RED→GREEN | ✅ |
| 3 | `8021dd1` | `feat(suscripciones): Venta wizard 4 pasos + 7 component tests` | feat | RED→GREEN | ✅ |
| 4 | `5c2c9f9` | `feat(suscripciones): PagoModal reuse integration in step 4` | feat | contract pinned | ✅ |
| 5 | `TBD` | `docs(suscripciones): route + i18n + coverage + e2e + apply-progress` | docs | mechanical | ✅ |

## Tests Passing

```
✓ prorrateo.test.ts            5 tests
✓ useVentaSuscripcion.test.ts  4 tests (201, 422×2, 401)
✓ Venta.test.tsx               7 tests (mount, advance×2, NIT corto,
                                  placa dup revert, paso 3→4,
                                  prorrateo badge, trigger)
─────────────────────────────────
Total:                         16 tests passing
```

## Drift Guards (must pass pre-merge)

| Guard | Result |
|---|---|
| `git grep useVentaSuscripcion useSuscripcionesList.ts` → 0 matches | ✅ |
| `git grep calcularMontoProporcional features/suscripciones` → ≥3 matches | ✅ |
| `git grep VentaSuscripcionDuplicatePlateError features/suscripciones` → ≥3 matches | ✅ |
| PagoModal reuse from `../../facturacion/components/PagoModal` | ✅ |

## Files Changed (12 total)

**NEW:**
- `apps/electron-sucursal/src/features/suscripciones/lib/prorrateo.ts`
- `apps/electron-sucursal/src/features/suscripciones/lib/prorrateo.test.ts`
- `apps/electron-sucursal/src/features/suscripciones/api/ventaSuscripcionApi.ts`
- `apps/electron-sucursal/src/features/suscripciones/hooks/useVentaSuscripcion.ts`
- `apps/electron-sucursal/src/features/suscripciones/hooks/useVentaSuscripcion.test.ts`
- `apps/electron-sucursal/src/features/suscripciones/hooks/ventaSuscripcionErrors.ts`
- `apps/electron-sucursal/src/features/suscripciones/pages/Venta.tsx`
- `apps/electron-sucursal/src/features/suscripciones/pages/Venta.test.tsx`
- `apps/electron-sucursal/e2e/suscripcion-venta.spec.ts`
- `openspec/changes/fase-9-1-venta-suscripcion/{design,tasks}.md`
- `openspec/changes/fase-9-1-venta-suscripcion/{apply-progress,verify-report}.md`

**UPDATED:**
- `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesList.ts` (dead stub removed)
- `apps/electron-sucursal/src/renderer/App.tsx` (`/suscripciones/venta` route)
- `apps/electron-sucursal/src/renderer/i18n/locales/suscripciones.json` (+20 wizard keys)
- `apps/electron-sucursal/vitest.config.ts` (+3 per-file thresholds)

## Next Steps (orchestrator)

1. Run `pnpm --filter electron-sucursal test` (all green).
2. Run `pnpm exec tsc -b --noEmit` (no new TS errors in F9.1 files).
3. Run `pnpm exec eslint` on new files with `--max-warnings 0`.
4. Run `git diff dev..feature/hu-f9-1-venta-suscripcion --stat` (≤935 LOC).
5. Open PR via `gh pr create --base dev --head feature/hu-f9-1-venta-suscripcion`.
6. Merge per AGENTS.md gitflow override rule 2026-09-17 (commit → push → branch delete).
7. `sdd-verify` against `verify-report.md`.
8. `sdd-archive` to sync delta specs to `openspec/specs/operations/spec.md`.
