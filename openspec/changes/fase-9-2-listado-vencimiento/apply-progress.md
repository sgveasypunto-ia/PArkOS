# Apply Progress — HU-F9.2

> **Change**: `fase-9-2-listado-vencimiento` | **Phase**: sdd-apply | **Status**: COMPLETE
> **Branch**: `feature/hu-f9-2-listado-vencimiento` (at `<TBD>` → 3 commits)
> **Strict TDD**: ACTIVE — every commit RED → GREEN with passing tests.
> **Divergence noted**: `Principal.tsx` does not exist on `dev`; F9.2 banner integration lives in `Dashboard.tsx` (the actual F6.x hub file on `dev`).

## Commits

| # | SHA | Commit | Type | TDD Phase | Status |
|---|---|---|---|---|---|
| 1 | `d85d505` | `feat(suscripciones): useSuscripcionesProximasVencer + 3 tests` | feat | RED→GREEN | ✅ |
| 2 | `b1e9b8b` | `feat(suscripciones): Listado page + 3 component tests` | feat | RED→GREEN | ✅ |
| 3 | `7c05808` | `feat(suscripciones): Principal banner + i18n + e2e + apply-progress` | mechanical | integration | ✅ |

## Tests Passing

```
✓ useSuscripcionesProximasVencer.test.ts    3 tests (filter excludes vencidas, sort ASC, empty [])
✓ Listado.test.tsx                          3 tests (5-col render, search filter, empty shows all)
─ Venta.test.tsx (F9.1, untouched)           7 tests
─ prorrateo.test.ts (F9.1, untouched)        5 tests
─ useVentaSuscripcion.test.ts (F9.1)        4 tests
─────────────────────────────────────────
Total:                                       22 tests passing (3+3 F9.2 NEW + 16 F9.1 untouched)
```

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `useSuscripcionesProximasVencer.test.ts` | Hook | N/A (new) | ✅ Written | ✅ Passed (3/3) | ✅ 3 cases | ✅ None needed |
| 2.1 | `Listado.test.tsx` | Component | N/A (new) | ✅ Written | ✅ Passed (3/3) | ✅ 3 cases | ✅ None needed |
| 3.1-3.7 | `e2e/suscripciones-lista.spec.ts` | E2E stub | N/A (new) | N/A (gated STUB) | ⏭ Scheduled runtime | ➖ Pending | ➖ N/A |

Test Summary:
- **Total tests written (F9.2 NEW)**: 6 (3 hook + 3 component) + 2 e2e stubs
- **Total tests passing**: 6/6 NEW, 16/16 F9.1 untouched
- **Layers used**: Hook (1 module), Component (1 module)
- **Approval tests (refactoring)**: None — no refactoring tasks in F9.2
- **Pure functions created**: `computeProximasVencer(rows, now)`, `filterListado(rows, query)`, `diasRestantes(fecha, now)`

## Drift Guards (must pass pre-merge)

| Guard | Result |
|---|---|
| `git grep -nE "dias_alerta_pre_vencimiento_override" apps/electron-sucursal/src` → 0 matches | ✅ PASS (0) |
| `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` is the sole source | ✅ |
| Existing `useSuscripcionesList.ts` (F9.1 read-only SWR query) untouched | ✅ |
| `useVentaSuscripcion.ts` / `Venta.tsx` / `ventaSuscripcionApi.ts` (F9.1) untouched | ✅ |

## Files Changed (10 total)

**NEW:**
- `apps/electron-sucursal/src/features/suscripciones/lib/constants.ts`
- `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.ts`
- `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.test.ts`
- `apps/electron-sucursal/src/features/suscripciones/pages/Listado.tsx`
- `apps/electron-sucursal/src/features/suscripciones/pages/Listado.test.tsx`
- `apps/electron-sucursal/e2e/suscripciones-lista.spec.ts`
- `openspec/changes/fase-9-2-listado-vencimiento/{proposal,specs/operacion,design,tasks,apply-progress,verify-report}.md`

**MODIFIED:**
- `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (banner + top-5 panel — see divergence note)
- `apps/electron-sucursal/src/renderer/App.tsx` (`/suscripciones` route)
- `apps/electron-sucursal/src/renderer/i18n/locales/suscripciones.json` (+14 keys)
- `apps/electron-sucursal/vitest.config.ts` (+2 per-file coverage thresholds)

## Pre-merge Verification Results

| Check | Result |
|---|---|
| `pnpm exec vitest run useSuscripcionesProximasVencer` | ✅ 3/3 |
| `pnpm exec vitest run Listado` | ✅ 3/3 |
| `pnpm exec vitest run suscripciones` (full feature) | ✅ 22/22 |
| `pnpm exec tsc -b --noEmit` filtered to F9.2 files | ✅ 0 new errors (pre-existing electron/ errors confirmed pre-dev via `git stash` baseline) |
| `pnpm exec eslint <new files>` with `--max-warnings 0` | ⏭ Pending orchestrator step |
| `git grep dias_alerta_pre_vencimiento_override apps/electron-sucursal/src` | ✅ 0 matches |
| `git diff dev..feature/hu-f9-2-listado-vencimiento --stat` | ✅ Under 800 LOC |

## Divergence Disclosure

`Principal.tsx` is referenced by plan.md line 2122 as the integration target for
the F9.2 banner. That file does NOT exist on `dev` (verified via
`Test-Path ...\Principal.tsx` returning `False`). The actual F6.x hub on `dev`
is `Dashboard.tsx` at `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx`.
F9.2 integrates the banner + top-5 panel into `Dashboard.tsx`, which is the
canonical target for any F6.x hub work. The plan.md reference is stale naming;
the test IDs (`dashboard-vencimiento-banner`, `dashboard-vencimiento-panel`,
`dashboard-vencimiento-panel-count`, `dashboard-vencimiento-panel-list`,
`dashboard-vencimiento-item-{placa}`) preserve the spec contract regardless
of file name.

## ABIERTO-05 Status

CLOSED-as-DEFAULT for F9.2. The override per-suscripción capability is
**out of scope** for this PR; the drift guard at the orchestration layer
prevents accidental reintroduction of an override field. Follow-up PR
would add a column to `subscripciones_cliente` and a per-row input in the
F9.1 wizard step 3.

## Next Steps (orchestrator)

1. Run `pnpm exec eslint` on all F9.2 NEW files with `--max-warnings 0`.
2. Open PR via `gh pr create --base dev --head feature/hu-f9-2-listado-vencimiento`.
3. Merge per AGENTS.md gitflow override rule 2026-09-17 (commit → push → branch delete).
4. `sdd-verify` against `verify-report.md`.
5. `sdd-archive` to sync delta specs to `openspec/specs/operations/spec.md`.
