# Tasks: operador-dashboard-hub

> **Change**: `operador-dashboard-hub` &nbsp;·&nbsp; **Phase**: tasks (sdd-tasks) &nbsp;·&nbsp; **Date**: 2026-09-17 &nbsp;·&nbsp; **Stack**: React 18 + Vite 5 + Zustand + SWR + shadcn/ui + RHF/Zod &nbsp;·&nbsp; **Branch lifecycle**: per AGENTS.md regla 8 (--no-ff merge to `dev`; branch deleted post PR-6).

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines (TOTAL across 6 PRs) | **~2700** |
| 400-line budget risk (per-PR) | **Low** (each PR ≤800; max 700 in PR-1) |
| Chained PRs recommended | **Yes** |
| Delivery strategy | `auto-chain` |
| Chain strategy | **stacked-to-main** |
| Per-PR focused test command (used in every PR) | `pnpm exec vitest run src/features/<feature> && pnpm exec tsc -b` |
| Suggested split | **PR-1 shell → PR-2 ingreso → PR-3 salida+cobro → PR-4 FE+reimpresion → PR-5 suscripciones+arqueos → PR-6 sync+alertas+cleanup** |

```
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low
```

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Dashboard shell + drawer store + OcupacionPanel relocated from global strip | PR-1 | `pnpm exec vitest run src/features/caja/pages src/renderer/store` | chrome-devtools manual: login + abrir turno + assert OccupacionPanel renders inside Dashboard | `revert PR-1` — fallback to pre-shell Dashboard (only TurnoActivoPanel shown, no F4-F10 panels); no backend impact |
| 2 | IngresoPanel (F6.1) + PlacaInput + TiqueteModal inline on dashboard; useCotizacion hook | PR-2 | `pnpm exec vitest run src/features/operacion/components` | Manual: from Dashboard, type `ABC12D`, assert ingreso created 201 with ticket modal | `revert PR-2` — dashboard renders without IngresoPanel; operador fallback to none (PRE-HUB they had nothing anyway) |
| 3 | SalidaPanel (F7.1+F7.2) + PagoSheet (F8.1) + useFacturaElectronica | PR-3 | `pnpm exec vitest run src/features/operacion/components src/features/facturacion/components` | Manual: SalidaPanel opens CotizacionPanel → PagoSheet; pay efectivo; assert FE returned | `revert PR-3` — PagoSheet not available; operator falls back to (NO existing fallback, but NO-BILLING risk is contained because single-record exits are rare from kiosko in the few hours between PR-3 merge and fix) |
| 4 | FacturaElectronicaRetryPanel + ReimprimirTiqueteSheet (F8.2+F8.3) | PR-4 | `pnpm exec vitest run src/features/facturacion/components src/features/reimpresion/components` | Manual: trigger FE rejected state, retry panel displays; print tiquete with QR | `revert PR-4` — FE monitor/reimpresion not available; admin can re-issue via cloud instead |
| 5 | SuscripcionesPanel + ArqueoSheet + CierreDiarioDialog (F9+F10) | PR-5 | `pnpm exec vitest run src/features/suscripciones/components src/features/caja/components` | Manual: open Suscripciones, search plate; ArqueoSheet shows diferencia | `revert PR-5` — suscripciones and arqueos NOT available; workflow impact contained because they're not the canonical happy-path |
| 6 | SyncStatusStrip + AlertasPanel + REMOVE global `<OcupacionStrip />` mount from `App.tsx:48` | PR-6 | `pnpm exec vitest run src/features/sync/components` | Manual: dashboard has SyncStatus + Alertas; App.tsx no longer has global strip | `revert PR-6` — SYNC_STATUS_AND_ALERTAS_disappear; occupancy still works via inline panel; net effect: BACKWARD compatibility (no UX loss) |

## Phase 1 — PR-1: Dashboard shell (Foundation)

- [ ] 1.1 Branch `feature/operador-dashboard-hub` from `origin/dev`; `git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' checkout -b feature/operador-dashboard-hub origin/dev`. (Run from repo root; timeout 30s.)
- [ ] 1.2 Create `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` — Zustand singleton with `DrawerKind = 'pago' | 'fe-retry' | 'reimpresion' | 'arqueo' | 'cierre-diario' | null`, `openDrawer`, `open(kind)`, `close()`. Vitest unit `dashboardDrawerStore.test.ts` (state transitions + Esc closure, single-drawer guard).
- [ ] 1.3 Rewrite `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` — replace `<TurnoActivoPanel />`-only with: `<TurnoActivoPanel />` (F3.3) on top; 6 `<Section />` slot components below; 1 `<DrawerHost />` consumes the Zustand store. Tests in `Dashboard.test.tsx` (mock `useSesionActiva` → assert all slots render + lazy panels don't when no active data).
- [ ] 1.4 Create `apps/electron-sucursal/src/features/caja/components/OcupacionPanel.tsx` — relocate from `apps/electron-sucursal/src/renderer/components/OcupacionStrip.tsx` global mount into Dashboard section slot; tests in `OcupacionPanel.test.tsx` (per REQ-OPS-132 fetcher-closure idiom).
- [ ] 1.5 Update existing `apps/electron-sucursal/src/i18n/locales/{es-CO,en-US}/caja.json` — add 6 namespace keys: `dashboard.turnoActivo`, `dashboard.operar`, `dashboard.ocupacion`, `dashboard.suscripciones`, `dashboard.sync`, `dashboard.alertas`. (Path correction: design.md flagged `apps/electron-sucursal/src/i18n/locales/...` is actually `apps/electron-sucursal/src/renderer/i18n/locales/...` — reconcile here.)
- [ ] 1.6 Run `pnpm exec tsc -b` + `pnpm exec vitest run src/features/caja/pages src/renderer/store`; both must exit 0.
- [ ] 1.7 Git commit #1: `feat(caja): REQ-OPS-136/137 dashboard shell + drawer store + OcupacionPanel`. Push `feature/operador-dashboard-hub`. Merge to `dev` per AGENTS.md regla 4 (no-ff). Branch NOT deleted yet (next PR continues same branch per stacked-to-main).

## Phase 2 — PR-2: IngresoPanel (F6.1)

- [ ] 2.1 Create `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` — REQ-OPS-132 fetcher-closure idiom: `useSWR(uuid_ingreso ? ... : null, () => fetchCotizacion(uuid_ingreso))`. Unit tests `useCotizacion.test.ts` (lazy-mount on null key).
- [ ] 2.2 Create `apps/electron-sucursal/src/features/operacion/components/PlacaInput.tsx` — RHF+Zod per REQ-OPS-119/135, `detectarTipoVehiculo` lookup onChange. Tests per `apps/electron-sucursal/src/features/operacion/components/PlacaInput.test.tsx` precedent.
- [ ] 2.3 Create `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx` — `<Dialog role="dialog">` per shadcn/ui. Use existing `escposBuilder.ts` (HU-F6.2) for buffer; call `bridge.imprimir({buffer, ticketId: uuid_ingreso})`. Tests `TiqueteModal.test.tsx` (mock bridge).
- [ ] 2.4 Create `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx` — Dashboard section; composed of `PlacaInput` + `TiqueteModal` + `useIngresoActivo` (pre-existing). Tests `IngresoPanel.test.tsx`.
- [ ] 2.5 Update i18n `operacion.json`: `dashboard.ingreso.*` keys (placa label, mensualidad activa, rotación label, motivo forzado).
- [ ] 2.6 Update `apps/electron-sucursal/src/renderer/App.tsx` Dashboard route render — wire `<IngresoPanel />` into Dashboard section slot 2.
- [ ] 2.7 Tests green: `pnpm exec vitest run src/features/operacion`; commit #2: `feat(operacion): REQ-OPS-136 F6.1 ingreso panel + useCotizacion`. Push. Merge to `dev` (stacked-to-main).

## Phase 3 — PR-3: SalidaPanel + PagoSheet (F7.1+F7.2+F8.1)

- [ ] 3.1 Create `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` — fetcher closure for `GET /facturacion/factura-electronica?uuid_factura=`. Tests.
- [ ] 3.2 Create `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` — `<Sheet>` drawer, opens via `useDashboardDrawerStore`. Form: efectivo/datáfono + Nit + idempotency key. Tests mock `useCobrar()`.
- [ ] 3.3 Create `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` — section with placa search + cotizacion split + PagoSheet trigger.
- [ ] 3.4 Dashboard wires `<SalidaPanel />`; tests green.
- [ ] 3.5 Commit #3: `feat(operacion): REQ-OPS-136 F7.1+F7.2 salida + F8.1 PagoSheet`. Push. Merge to `dev`.

## Phase 4 — PR-4: FE retry + reimprimir tiquete (F8.2+F8.3)

- [ ] 4.1 Create `apps/electron-sucursal/src/features/reimpresion/hooks/useTicketsBuscar.ts`, `useReimpresion.ts`. Tests.
- [ ] 4.2 Create `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` — section slot.
- [ ] 4.3 Create `apps/electron-sucursal/src/features/reimpresion/components/ReimprimirTiqueteSheet.tsx` — drawer.
- [ ] 4.4 Dashboard wires; tests green.
- [ ] 4.5 Commit #4: `feat(facturacion+reimpresion): REQ-OPS-136 F8.2+F8.3`. Push. Merge to `dev`.

## Phase 5 — PR-5: Suscripciones + Arqueos + Cierre diario (F9+F10)

- [ ] 5.1 Create `apps/electron-sucursal/src/features/suscripciones/hooks/{useSuscripcionesList,useVentaSuscripcion}.ts`. Tests.
- [ ] 5.2 Create `apps/electron-sucursal/src/features/caja/hooks/{useArqueo,useCierreDiario}.ts`. Tests.
- [ ] 5.3 Create `apps/electron-sucursal/src/features/suscripciones/components/SuscripcionesPanel.tsx` (section).
- [ ] 5.4 Create `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx` (drawer).
- [ ] 5.5 Create `apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx` (Dialog modal).
- [ ] 5.6 Dashboard wires; tests green.
- [ ] 5.7 Commit #5: `feat(suscripciones+caja): REQ-OPS-136 F9+F10`. Push. Merge to `dev`.

## Phase 6 — PR-6: Sync + Alertas + global strip cleanup (F11)

- [ ] 6.1 Create `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts`. Tests.
- [ ] 6.2 Create `apps/electron-sucursal/src/features/sync/components/{SyncStatusStrip,AlertasPanel}.tsx` (sections).
- [ ] 6.3 Edit `apps/electron-sucursal/src/renderer/App.tsx` — REMOVE the global `<OcupacionStrip />` mount at L48 (REQ-OPS-140). Tests ensure no double-strip on Dashboard.
- [ ] 6.4 Dashboard wires `<SyncStatusStrip />` and `<AlertasPanel />` sections; tests green.
- [ ] 6.5 Manual QA replay (analog of `qa-2026-09-17-bug-remediation` session): login → abrir turno → verify 6 sections + drawer scoped → crear ingreso `ABC12D` → cotizar → registrar salida → PagoSheet → FE status → reimprimir tiquete → arqueo → cerrar turno. All green.
- [ ] 6.6 Commit #6: `feat(sync+alertas+cleanup): REQ-OPS-136/139/140 F11 + global strip removal`. Push. Merge to `dev` (--no-ff per AGENTS.md regla 8). Branch `feature/operador-dashboard-hub` deleted (local + remote).

## Implementation Order

Per `stacked-to-main`: PR-1 lands first as the shell; PR-2..5 each branch from `origin/dev` AFTER PR-1 merges (independent work units) and each merges straight to `dev` per `stacked-to-main` (no integration branch between them — verified-clean compiles per CI gate before merge). PR-6 is the cleanup + final manual QA replay.

## Branch Lifecycle (per AGENTS.md)

```
git fetch origin dev
git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' \
    checkout -b feature/operador-dashboard-hub origin/dev

# per PR: ... commits ... push ... merge --no-ff ... push origin dev
# (delete branch AFTER PR-6 merge per AGENTS.md regla 4)
```