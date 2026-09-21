# Proposal: HU-F12.1 — Panel "Mi turno"

## Intent

Operador wants a turn-scoped KPI summary (ingresos / salidas / total cobrado por medio de pago) on the main screen — without leaving the page. The current Dashboard shows branch-wide occupancy (F1.5 `OcupacionPanel`) but does NOT surface the operator's own turno aggregates; F10.2 only aggregates at cierre. This HU ships a read-only panel backed by a new backend aggregate endpoint and a SWR-driven FE component. Subset of CU-09 reportería local mínima (plan.md L2352-2375).

## Scope

### In Scope
- Backend `GET /operacion/mi-turno?uuid_sesion=X` — read-only aggregator over `prod.sesion`, `prod.ingreso`, `prod.salidas`, `prod.factura_pagos` (all read-only, no writes).
- Backend Pydantic `MiTurnoRead` schema (uuid_sesion, uuid_sucursal, ingresos_count, salidas_count, total_cobrado_efectivo_cop, total_cobrado_datafono_cop, timestamp_calculo).
- Backend repo helper `parkos_core.repo.mi_turno.calcular_resumen_mi_turno(session, uuid_sesion)`.
- FE SWR hook `useMiTurno(uuid_sesion)` with `refreshInterval: 15_000`.
- FE component `MiTurnoPanel` (shadcn `Card` KPI strip) + i18n keys.
- Mount on Dashboard right sidebar, above `<OcupacionPanel />`.
- "Cerrar turno" navigation button (`navigate('/caja/cerrar-turno')`).
- e2e `e2e/mi-turno.spec.ts` (2 scenarios, `test.skip` per F10.2/F11.x sandbox precedent).

### Out of Scope
- Historical turno comparison (multi-turn), per-day breakdown (F10.3 owns), alerts on turno anomalies (F11.2 owns).
- Any write to `ingreso`/`salidas`/`factura_pagos` (all read-only; bi-temporal canon preserved).
- New i18n locales (es-CO only; en-US/pt-BR deferred).

## Capabilities

### New Capabilities
- `operacion-mi-turno`: per-turn KPI aggregation (ingresos count, salidas count, total cobrado by medio_pago) for the operator's active `uuid_sesion`.

### Modified Capabilities
- `operations`: delta — new REQ-OPS-184..188 covering read-only aggregation contract, polling cadence, zero-state rendering, and tenant scoping.

## Approach

- **Backend**: thin `GET /operacion/mi-turno` handler in `api/v1/operacion.py` (router already exists at `/operacion` prefix — extend, don't create new router). New `repo/mi_turno.py::calcular_resumen_mi_turno` mirrors `repo/arqueo.py::_sum_factura_pagos_by_medio_pago` (existing SUM pattern) but keyed by `Sesion.uuid`. `ingreso`/`salidas` counts derived from `Sesion` open-window JOIN (`fecha_ingreso >= timestamp_apertura AND (timestamp_cierre IS NULL OR fecha_ingreso <= timestamp_cierre)`); `factura_pagos` SUM uses `uuid_sesion` directly. Tenant scope: `operador-` pinned to `ctx.sucursal_uuid` (KD-3, F1.5 precedent); handler resolves `Sesion.uuid_sucursal` server-side, ignores any `uuid_sesion` that doesn't match. `Cache-Control: no-store` (F1.3/F1.5/F1.8 precedent).
- **Frontend**: SWR hook `useMiTurno(uuid_sesion)` — `parkosFetch` + Zod schema + 401-handler (F11.1/F11.2 precedent). `refreshInterval: 15_000` (faster than F11.x 30s — operator's live turn). Mount inside `Dashboard.tsx` right sidebar above `<OcupacionPanel />` via `<MiTurnoPanel uuid_sesion={sesion?.uuid} />`. Zero-state renders all-zero KPIs (no error, no skeleton-on-zero). "Cerrar turno" inline Button → `navigate('/caja/cerrar-turno')`.
- **Tests**: backend pytest (testcontainers Postgres) — `test_calcular_resumen_mi_turno` with fixture `sesion_with_ingresos_y_pagos` (add to `tests/integration/conftest.py`). FE vitest + RTL — `MiTurnoPanel.test.tsx` (loading / zero / non-zero / 401). Playwright e2e (sandbox-skipped per F9.x precedent).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/.../api/v1/operacion.py` | Modified | Add `GET /mi-turno` handler |
| `backend/.../schemas/operacion.py` | Modified | Add `MiTurnoRead` schema |
| `backend/.../repo/mi_turno.py` | New | Read-only aggregator helper |
| `backend/.../tests/integration/conftest.py` | Modified | Add `sesion_with_ingresos_y_pagos` fixture |
| `apps/.../features/operacion/api/miTurnoApi.ts` | New | Zod schema + `getMiTurno` fetcher |
| `apps/.../features/operacion/hooks/useMiTurno.ts` | New | SWR hook |
| `apps/.../features/operacion/components/MiTurnoPanel.tsx` | New | KPI strip + Cerrar turno button |
| `apps/.../features/caja/pages/Dashboard.tsx` | Modified | Mount `<MiTurnoPanel />` in right sidebar |
| `apps/.../renderer/i18n/locales/operacion.json` | Modified | Add `miTurno.*` keys (es-CO) |
| `apps/electron-sucursal/e2e/mi-turno.spec.ts` | New | 2 scenarios (KPIs visible, close-button) |

## Risks (drift anchors for spec phase)

| ID | Likelihood | Detail | Mitigation |
|----|------------|--------|------------|
| DA-F12.1-1 | High | Pydantic response shape (`MiTurnoRead`) — naming must match FE Zod | Spec phase codifies both shapes; Zod schema mirrors field-for-field (F11.1/F11.2 precedent) |
| DA-F12.1-2 | High | Tenant scope: handler MUST resolve `Sesion.uuid_sucursal` server-side and reject cross-branch `uuid_sesion` even if token permits | Spec REQ-OPS-185 enforces lookup-then-403; static test asserts `uuid_sesion` not honored unless it belongs to ctx branch |
| DA-F12.1-3 | Med | Polling cadence 15s faster than F11.x (30s) — needs justification; SWR dedupe required | Spec REQ-OPS-186 documents 15s; design.md AD-3 explains operator-live UX; `dedupingInterval: 5_000` reuses F6.1 pattern |
| DA-F12.1-4 | Med | Zero-state must render zeros, not errors | Spec REQ-OPS-187: backend always returns 200 with zero counts; FE renders `0` for all KPIs |
| DA-F12.1-5 | Med | "Cerrar turno" button reuse vs new — F10.2 has close logic; F12.1 owns only the *navigation trigger* | Button calls `navigate('/caja/cerrar-turno')`; no business logic (close is F10.2's `useSesionActiva().cerrarSesion`) |
| DA-F12.1-6 | Med | Backend stub detection — `operacion.py` router exists but no `/mi-turno` endpoint; confirmed via codegraph + read | New handler appended to existing `operacion.py` (don't create new router) |
| DA-F12.1-7 | Low | i18n keys: `miTurno.titulo`, `miTurno.kpis.{ingresos,salidas,totalCobrado,efectivo,datafono}`, `miTurno.cerrarTurno` | Add to `operacion.json` only (es-CO); other locales deferred |
| DA-F12.1-8 | Med | Test fixture: `tests/integration/conftest.py` likely lacks session-with-pagos fixture | Add `sesion_with_ingresos_y_pagos` factory fixture (mirrors F1.13 pattern) |
| DA-F12.1-9 | Med | FE Zod MUST match backend Pydantic exactly (F11.1 DA-F11.1-7 / F11.2 DA-F11.2-9 closed) | Drift table in spec phase locks both shapes; static test compares keys |
| DA-F12.1-10 | Low | `useArqueoResumenPorSesion` overlap — F10.3 (cierre_diario) ≠ F12.1 (current-turn-only); pattern reuse only | Helper names distinct (`useMiTurno` vs `useArqueoResumenPorSesion`) |

## Rollback Plan

Revert commits; remove `/operacion/mi-turno` route; remove `<MiTurnoPanel />` mount in Dashboard (revert one-line addition). No schema change, no migration, no `[A]` row written — fully reversible at the route/component boundary. No data loss.

## Dependencies

- F10.2 `useSesionActiva().sesion.uuid` provides the `uuid_sesion` for the hook.
- F10.2 `/caja/cerrar-turno` route already mounted in `App.tsx` (F10.2 closure).
- F11.x SWR + Zod + parkosFetch pattern (F11.1/F11.2 substrate).
- Backend `repo/arqueo.py` `_sum_factura_pagos_by_medio_pago` SUM pattern (F1.13 substrate).
- Backend `repo/session_cycle` + `models.L_S.sesion.Sesion` ORM (F1.13/F1.14 substrate).

## Success Criteria

- [ ] `GET /operacion/mi-turno?uuid_sesion=X` returns 200 with 6 fields; 403 on cross-branch; 404 on unknown session.
- [ ] Backend pytest: ≥10 scenarios covering happy path / zero state / cross-branch 403 / closed-session window / medio_pago breakdown.
- [ ] Backend coverage ≥80% for new module.
- [ ] FE vitest: ≥6 scenarios (loading / zero / non-zero / 401 / 5xx / polling).
- [ ] e2e `mi-turno.spec.ts`: 2 scenarios (KPIs visible after login; Cerrar-turno button navigates to `/caja/cerrar-turno`). Both `test.skip(...)` per sandbox F.6 precedent.
- [ ] axe-core WCAG 2.1 AA: zero violations on `<MiTurnoPanel />`.
- [ ] Ruff + mypy + ts-strict + ESLint green; no new linter debt.
