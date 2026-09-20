# Tasks: HU-F8.3 — Reimpresión de tiquete con costo (FE)

> **Change**: `fase-8-3-reimpresion-tiquete-costo`
> **Phase**: tasks (sdd-tasks)
> **Branch**: `feature/hu-f8-3-reimpresion-tiquete-costo` off `dev` at `3d0e2e8`
> **Delivery strategy**: `single-pr` (no `size:exception`)

---

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~325 LOC |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (5 commits) |
| Delivery strategy | single-pr |
| Chain strategy | n/a |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `escposBuilder.build('reimpresion')` bold marca + 3 byte-level tests | PR 1 | `pnpm --filter electron-sucursal test -- --run escposBuilder.reimpresion` | typecheck | Revert commit; existing F1.11 stub restored |
| 2 | `useReimprimir` mutation + 3 hook tests | PR 1 | `pnpm --filter electron-sucursal test -- --run useReimprimir` | typecheck | Revert commit; hook stub restored |
| 3 | `useAnularReimpresion` mutation + 2 hook tests | PR 1 | `pnpm --filter electron-sucursal test -- --run useAnularReimpresion` | typecheck | Revert commit; hook stub restored |
| 4 | `ReimprimirTiquete` page (alertdialog) + 5 component tests | PR 1 | `pnpm --filter electron-sucursal test -- --run ReimprimirTiquete` | typecheck | Revert commit; page unmounted |
| 5 | App.tsx route + i18n + per-file coverage + e2e stub + apply-progress | PR 1 | `pnpm --filter electron-sucursal test:coverage` + e2e + git grep | typecheck | Revert commit; metadata only |

---

## Phase 1 — Foundation (commits 1-3)

- [x] 1.1 RED + GREEN: `escposBuilder.reimpresion.test.ts` with 3 byte-presence tests + update `escposBuilder.ts` to wrap inner body with `escBoldOn()`/`escBoldOff()` + sello with accent + subline `--- COPIA AUTORIZADA ---`
- [x] 1.2 RED + GREEN: `useReimprimir.test.ts` with 3 hook tests (201 happy, motivo<10 Zod, 401 auth-clear) + new `useReimprimir.ts` (SWR mutation + Idempotency-Key + Zod mirror of F1.11 `ReimpresionTicketRead`)
- [x] 1.3 RED + GREEN: `useAnularReimpresion.test.ts` with 2 hook tests (201 INSERT-only chain, motivo_anulacion<10 Zod) + new `useAnularReimpresion.ts`

## Phase 2 — Page (commit 4)

- [x] 2.1 RED + GREEN: `ReimprimirTiquete.tsx` (page with placa search + motivo textarea + alertdialog + success card anular) + 5 component tests

## Phase 3 — Polish (commit 5)

- [x] 3.1 Add `/facturacion/reimprimir` route in `App.tsx` under `<ProtectedRoute>` (mirror F8.2 line 65-72)
- [x] 3.2 Add 13 i18n keys to `facturacion.json` (`reimprimir.tipo.*`, `reimprimir.alertdialog.*`, `reimprimir.errors.*`, `reimprimir.success.*`, `reimprimir.anular.*`, `reimprimir.placa.label`)
- [x] 3.3 Create `e2e/reimpresion.spec.ts` with 3 stub scenarios (entrada / salida / motivo corto blocked)
- [x] 3.4 Create `apply-progress.md` + `verify-report.md` placeholder

---

**End of tasks — HU-F8.3.**
