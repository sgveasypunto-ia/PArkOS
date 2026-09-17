# Proposal: operador-dashboard-hub

## Intent

The operator opens a turno, lands on `/`, and sees only `<TurnoActivoPanel>` (Dashboard.tsx:39-87). All F6-F11 actions live on routes that don't exist — `Principal.tsx` is an F6.1 stub, `features/{facturacion,reimpresion,suscripciones,sync,alertas}/` folders don't exist. The dashboard must absorb ALL F4-F11 actions into one persistent workspace mounted at `/` from `POST /caja-sesion/sesiones` until cierre.

## Scope

### In Scope (6 chained PRs per `auto-chain`; sdd-tasks finalizes split)

| PR | Scope |
|---|---|
| 1 | `<Dashboard>` restructure; `<OcupacionStrip>` global → per-dashboard panel; `<Sheet>`/`<Dialog>` infra; `useDashboardDrawerStore` (Zustand); `ProtectedRoute` simplify |
| 2 | `<PlacaInput>` + `<IngresoActivoPanel>` + `<TiqueteModal>` inline; `useCotizacion`, `useIngresoActivo` per REQ-OPS-132 |
| 3 | `<BuscarPlacaDialog>` + `<CotizacionPanel>` + `<PagoSheet>` (FE consumidor-final NIT default) |
| 4 | `<FacturaElectronicaRetryPanel>` + `<ReimprimirTiqueteSheet>` |
| 5 | `<SuscripcionesPanel>` + `<ArqueoSheet>` + `<CierreDiarioDialog>` |
| 6 | `<SyncStatusStrip>` relocated; `<AlertasPanel>`; remove global `<OcupacionStrip>` from `App.tsx:48` |

### Out of Scope (deferred)
- Backend migrations (none — 21 endpoints audited live); printer HW fallback per F5.2; multi-turno (canon); SWR keys without active ingreso (lazy-mount only).

## Capabilities

### New Capabilities
None — backend unchanged; pure FE integration.

### Modified Capabilities
- **`operations`** (`openspec/specs/operations/spec.md`): Add REQ-OPS-136..140 covering dashboard IA consistency, composable-section contract, drawer state machine, panel lazy-mount policy, sync-strip relocation. New hooks inherit REQ-OPS-132 fetcher-closure idiom.

## Approach

Keep `/` as the hub; do NOT introduce new routes. Dashboard becomes an orchestrator of composable sections + drawers (`<Sheet>` for Pago/FE/Reimprimir/Arqueo, `<Dialog>` for TiqueteModal). `useDashboardDrawerStore` (Zustand) holds `openDrawer: 'pago' | 'fe-retry' | 'reimpresion' | 'arqueo' | null` + `drawerContext: { uuid? }`. Backend is hands-off: 21 endpoints audited; no alembic, no schema drift. New SWR hooks mirror `useOcupacion:73-129` (cache key opaque + UUID in closure). `SesionRead.vigente` derived client-side as `timestamp_cierre === null` — avoids a 4NF pass.

## Affected Areas

| Path | Delta |
|---|---|
| `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` | Orchestrator for 6+ sections |
| `apps/electron-sucursal/src/renderer/App.tsx` | Remove global `<OcupacionStrip>` (L48) |
| `apps/electron-sucursal/src/features/{facturacion,reimpresion,suscripciones,sync,alertas}/` | CREATE 5 folders |
| `apps/electron-sucursal/src/features/operacion/pages/Principal.tsx` | Refactor as `<OcupacionPanel>` section |
| `apps/electron-sucursal/src/i18n/locales/{es-CO,en-US}/{caja,facturacion,reimpresion,suscripciones,sync}.json` | CREATE/populate namespaces |
| 8 SWR hooks across new folders | CREATE per REQ-OPS-132: `useCotizacion`, `useCotizacionCountdown`, `useVueltos`, `useFacturaElectronica`, `useSuscripcionesProximasVencer`, `useSyncEstado`, `useAlertas`, `useArqueoResumen` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| PR-1 >800 LOC (shell + panel + store + i18n) | High | `work-unit-commits` sub-decompose; split dashboard IA → PR-1.a, drawer store → PR-1.b if still >800 |
| Auto-chain triggers with no chain strategy | Med | sdd-tasks presents `stacked-to-main` vs `feature-branch-chain` |
| F6.1 UX regression / refresh storm / `SesionRead.vigente` missing | Low–Med | Keep `Principal.tsx` deep-link + same hooks; lazy-mount `<CotizacionPanel>`/`<ArqueoSheet>`; derive `vigente = timestamp_cierre === null` |

## Rollback Plan

Each PR is independently revertible via `git revert <merge-sha>` — backend untouched, no schema impact, no `alembic downgrade`. If PR-2/3/4 cascade UX regression, surgical rollback reverts the offending PR; remaining flows still work. Sesión routing stays canonical F3.3: `POST /caja-sesion/sesiones` → 201 → navigate `/`. plan.md §0.2 ("terminal operativo de una sede") is the design premise — fulfilled.

## Dependencies

- `qa-2026-09-17-bug-remediation` (commits `22823c2..5f58a11` on `dev`) landed. Bugs 1-7 (AuthUser.uuid, useOcupacion fetcher, MV, lowercase catalog, sesion.observaciones, PUT cerrar observaciones_cierre, idempotency_keys.fecha_retencion_hasta) VERIFIED green.

## Success Criteria

- [ ] Manual happy path: login → abrir turno → dashboard (OcupacionPanel + TarifaStrip + SyncStrip) → crear ingreso → cotizar → registrar salida + PagoSheet → reimprimir tiquete → hacer arqueo → cerrar turno
- [ ] All 6 PRs merged to `dev` under per-PR LOC budget (≤800); vitest green on `src/features/{caja,operacion,facturacion,reimpresion,suscripciones,sync}`
- [ ] `tsc -b` exits 0 on changed files (no NEW errors); no `git revert` of merged PR requires `alembic downgrade`
