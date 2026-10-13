# Tasks: hu-x-8-bugfixes

> **Change**: `hu-x-8-bugfixes`
> **Phase**: tasks (sdd-tasks)
> **Date**: 2026-10-13
> **PR strategy**: 1 PR `feature/hu-x-8-bugfixes` con 4 commits temáticos. ~350 LOC total, dentro del budget 400.

| # | Scope | LOC | Commit message |
|---|---|---|---|
| T1 | BE: query param `?uuid_factura=` en `GET /facturacion/factura-electronica` | +30 + 30 tests | `fix(backend): HU-X.8 — GET /facturacion/factura-electronica acepta ?uuid_factura=` |
| T2 | FE: api `fetchFacturaElectronicaByFacturaUuid` + `useFacturaDetalle` usa la nueva función | +30 + 20 tests | `fix(web_admin): HU-X.8 — useFacturaDetalle usa uuid_factura en lugar de FE uuid` |
| T3 | FE: `BranchPickerInline` componente + `ReporteriaFinanciera` indicador de branch + `ReporteriaFinanciera.test` actualizado | +160 + 30 tests | `feat(web_admin): HU-X.8 — BranchPickerInline con search para ReporteriaFinanciera` |
| T4 | FE: dashboard card Facturas con `to` + `linkHint` + body de empty state | +30 + 10 tests | `feat(web_admin): HU-X.8 — dashboard Facturas card con link a /reporteria/financiera` |
| **Total** | 4 commits | **~350 LOC** | |

Decision needed before apply: No (plan ya aprobado).
Chained PRs recommended: No (1 PR, cohesivo).
Chain strategy: 1 PR.
400-line budget risk: Low (350 < 400).
