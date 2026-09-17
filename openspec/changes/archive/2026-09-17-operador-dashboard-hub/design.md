# Design: operador-dashboard-hub

> **Change**: `operador-dashboard-hub` &nbsp;·&nbsp; **Phase**: design (sdd-design) &nbsp;·&nbsp; **Branch**: TBD from `dev` &nbsp;·&nbsp; **Date**: 2026-09-17 &nbsp;·&nbsp; **Forecast**: 2500-3500 LOC across 6 chained PRs (PR-1..PR-6); per-PR budget 800 LOC.

## Technical Approach

Convert `Dashboard.tsx:39-87` from a thin `<TurnoActivoPanel />` redirect into an orchestrator composing six dashboard sections (OcupacionPanel, OperacionPanel, CajaPanel, FacturacionPanel, ReimpresionPanel, SuscripcionesPanel, SyncStatusStrip) plus one singleton drawer slot driven by Zustand `useDashboardDrawerStore`. Multi-step flows mount as `<Sheet side="right">` (shadcn primitive at `renderer/components/ui/sheet.tsx`); `TiqueteModal`/`CierreDiarioDialog` stay centered. Drawer triggers carry `data-anchor-for="<kind>"` so `Esc`/close restores focus per REQ-OPS-138. Backend is hands-off: 21 endpoints audited (`exploration.md §1.8`). `SesionRead.vigente` derived client-side as `timestamp_cierre === null` — no migration, no 4NF pass. `<OcupacionStrip />` mount at `App.tsx:48` (F4.3 "TEMPORAL") removed in PR-6 when its inline sibling mounts, killing duplicate polling. New SWR hooks mirror REQ-OPS-132 fetcher-closure precedent at `useOcupacion.ts:73-129`.

> **Path correction vs `proposal.md`**: i18n locales live at `renderer/i18n/locales/{caja,facturacion,sync,operacion,...}.json` (flat namespace files, no `locales/{es-CO,en-US}/` split). sdd-tasks should add `reimpresion.json` + `suscripciones.json` to the same flat layout. en-US split deferred to a future i18n PR.

## Architecture Decisions

### Decision D1 — Route strategy: enrich `/` vs new route

**Choice**: Enrich existing `/` (currently `<TurnoActivoPanel />`) by composing new panels into the same Dashboard component. No new route. No redirect.
**Alternatives**: (a) New route `/operar` redirecting from `/` — 2-step nav breaks keyboard-only kiosk. (b) Keep `/` + swap on `<DashboardHUB />` — doubles route surface.
**Rationale**: per `plan.md §0.2` "una sola sede por instalación" — single-route workspace is canonical. `Dashboard.tsx` already implements post-turno landing (`useSesionActiva` redirect L53-55). Enrichment keeps `<ProtectedRoute />` (App.tsx:23-57) unchanged, no URL drift.

### Decision D2 — Drawer state machine: Zustand vs `useState` lift vs URL hash

**Choice**: New Zustand `useDashboardDrawerStore` (singleton, single field `openDrawer: DrawerKind | null`).
**Alternatives**: (a) `useState` lifted to `Dashboard` — multi-section collaboration breaks. (b) URL hash `?drawer=pago` — pollutes history (5-10 clicks/turn).
**Rationale**: Zustand is canonical (`plan.md §0.2` "Zustand solo para estado de UI local efímero"). Single field makes REQ-OPS-138 single-drawer guard trivial. URL deep-link deferred to F12.

### Decision D3 — Lazy-mount threshold: SWR key gate vs always-mount + internal guard

**Choice**: Each lazy-mountee uses `useXxx<T>(uuid_yyy: string | null)` SWR-key gating. Composing section renders `<></>` until hook returns non-null `data`.
**Alternatives**: (a) Always-mount + `if (!data) return null` — fetch still issued on cold render. (b) `<Outlet />` swap — adds routing to state-pure feat.
**Rationale**: SWR's documented `key=null` skip per `useOcupacion.ts:42-50` (UI stable via `data?.items ?? []`). Cross-ref REQ-OPS-139 cold-Dashboard scenario.

### Decision D4 — Sync-strip relocation: dedicated `<SyncStatusStrip />` vs PROP extension

**Choice**: New `<SyncStatusStrip />` panel inside Dashboard (PR-6) polling `GET /sync/estado` per F11.1 via `useSyncEstado`. `<OcupacionStrip />` global mount at `App.tsx:48` REMOVED in PR-6 only.
**Alternatives**: (a) Extend `<OcupacionStrip />` with sync prop — breaks container/presentational split. (b) Replace global with `<SyncStrip/>` doing both — couples concerns and mismatched cadences (oc: 10s; sync: 30s).
**Rationale**: `App.tsx:32-39` "mount TEMPORAL" comment already approved. Independence allows per-panel `<ErrorBoundary />` containment per REQ-OPS-137.

### Decision D5 — Translation namespaces: extend existing vs add 3 more

**Choice**: EXTEND flat locale files at `renderer/i18n/locales/{caja,facturacion,operacion,sync,...}.json`. CREATE `reimpresion.json` + `suscripciones.json` per PR-4/PR-5.
**Alternatives**: (a) Single `dashboard.json` — loses per-feature isolation. (b) Lazy-load chunks — premature for 7-9 namespaces.
**Rationale**: Canon at `renderer/i18n/index.ts`; flat namespace-per-feature IS established (verified directory listing). en-US split deferred.

## Data Flow

```
                                  ┌── /caja-sesion/sesion/me (one-shot) ─┐
[operador] ─── /login ─── abrir-turno-form ─── POST /sesiones 201 ──────────┤
                                              │                          ▼
                                              │               Dashboard.tsx (enriched)
                                              │                          │
                                              │              ┌───────────┼───────────┬─────────┐
                                              │              │           │           │         │
                                              │      ┌───────┴────┐ ┌─────┴─────┐ ┌───┴────┐ ┌───┴────┐
                                              │  ┌───┤ Ocupacion  │ │ Operacion │ │ Caja   │ │ Sync   │
                                              │  │ useOcupacion │ │ useIngreso│ │(arqueo)│ │useSync │
                                              │  └──────────────┘ │ Activo,   │ └────────┘ └────────┘
                                              │      pol 10s       │ useCotiza │
                                              │                    │ cion      │
                                              │                    └──────────┘
                                              │           ▲                ▲
                                              │  useDashboardDrawerStore   useDashboardDrawerStore
                                              │   (Zustand singleton)     (Zustand singleton)
                                              ▼
                                          Sheets (one at a time):
                                              PagoSheet | FE-RetrySheet
                                              ArqueoSheet | ReimpresionSheet
                                              CierreDiarioDialog
```

## File Changes

| PR | File | Action | Description |
|---|---|---|---|
| PR-1 | `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` | Rewrite | Orchestrator: 6 section slots + 1 drawer slot + store consumer |
| PR-1 | `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` (NEW) | CREATE | Zustand `openDrawer` singleton |
| PR-1 | `apps/electron-sucursal/src/features/caja/components/OcupacionPanel.tsx` (NEW) | CREATE | Inlined from global strip (`OcupacionStrip.tsx:70-160` rehosted) |
| PR-2 | `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx` (NEW) | CREATE | F6.1 inline panel; reuses `PlacaInput.tsx`, `TiqueteModal.tsx` |
| PR-2 | `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` (NEW) | CREATE | REQ-OPS-132 idiom (key=null when no `uuid_ingreso`) |
| PR-3 | `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (NEW) | CREATE | F7.1+F7.2 inline panel |
| PR-3 | `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (NEW) | CREATE | F8.1 drawer (FE consumidor-final NIT `222222222222222` default) |
| PR-3 | `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` (NEW) | CREATE | REQ-OPS-132 |
| PR-4 | `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` (NEW) | CREATE | F8.2 inline |
| PR-4 | `apps/electron-sucursal/src/features/reimpresion/components/ReimprimirTiqueteSheet.tsx` (NEW) | CREATE | F8.3 drawer |
| PR-4 | `apps/electron-sucursal/src/features/reimpresion/hooks/{useTicketsBuscar,useReimpresion}.ts` (NEW) | CREATE | per REQ-OPS-132 |
| PR-4 | `apps/electron-sucursal/src/renderer/i18n/locales/reimpresion.json` (NEW) | CREATE | F8.3 keys |
| PR-5 | `apps/electron-sucursal/src/features/suscripciones/components/SuscripcionesPanel.tsx` (NEW) | CREATE | F9.2 inline |
| PR-5 | `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx` (NEW) | CREATE | F10.1 drawer |
| PR-5 | `apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx` (NEW) | CREATE | F10.3 modal |
| PR-5 | `apps/electron-sucursal/src/features/caja/hooks/{useArqueo,useCierreDiario}.ts` (NEW) | CREATE | per REQ-OPS-132 |
| PR-5 | `apps/electron-sucursal/src/renderer/i18n/locales/suscripciones.json` (NEW) | CREATE | F9.x keys |
| PR-6 | `apps/electron-sucursal/src/renderer/components/SyncStatusStrip.tsx` (NEW) | CREATE | F11.1 inline |
| PR-6 | `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts` (NEW) | CREATE | REQ-OPS-132 |
| PR-6 | `apps/electron-sucursal/src/features/sync/components/AlertasPanel.tsx` (NEW) | CREATE | F11.2 inline |
| PR-6 | `apps/electron-sucursal/src/renderer/App.tsx` | Modify | Remove global `<OcupacionStrip />` mount (L48); remove block-comment L32-L39 |

> Implementation order is `sdd-tasks`'s call. PR-6 is NOT sub-split (see Open Question a).

## Interfaces / Contracts

```ts
// apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts
import { create } from 'zustand';
import type { UseBoundStore, StoreApi } from 'zustand';

export type DrawerKind =
  | 'pago'
  | 'fe-retry'
  | 'reimpresion'
  | 'arqueo'
  | 'cierre-diario'
  | null;

interface DashboardDrawerState {
  openDrawer: DrawerKind;
  lastAnchorId: string | null;
  open(kind: Exclude<DrawerKind, null>, anchorId: string): void;
  close(): void;
}

export const useDashboardDrawerStore: UseBoundStore<StoreApi<DashboardDrawerState>> =
  create<DashboardDrawerState>((set) => ({
    openDrawer: null,
    lastAnchorId: null,
    open: (kind, anchorId) => set({ openDrawer: kind, lastAnchorId: anchorId }),
    close: () => set({ openDrawer: null }),
  }));
```

```ts
// apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx (signature change)
export function Dashboard(): JSX.Element {
  const { sesion } = useSesionActiva();
  const { openDrawer, close } = useDashboardDrawerStore();
  // ...composes <OcupacionPanel />, <OperacionPanel />, ...
}
```

```ts
// apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts
export function useCotizacion(
  uuid_ingreso: string | null,
): SWRResponse<CotizacionResponse> {
  // REQ-OPS-132 fetcher-closure idiom: key=null skips fetch
  return useSWR(
    uuid_ingreso ? `/operacion/cotizar?uuid_ingreso=${uuid_ingreso}` : null,
    (key: string) => operacionApi.cotizar(key.split('uuid_ingreso=')[1]!),
    { refreshInterval: 1000, revalidateOnFocus: false },
  );
}
```

All sheets/dialogs MUST render only when `openDrawer === '<kind>'`, carry `aria-modal="true"`, and on close invoke `close()` then `document.getElementById(lastAnchorId)?.focus()`.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Vitest unit | Each `<*Panel />` / `<*Sheet />` with mock hooks | new `src/features/<feature>/components/__tests__/*.test.tsx` per PR (precedent: `AbrirTurno.test.tsx`) |
| Vitest unit | Drawer state machine (`useDashboardDrawerStore`) | state transition matrix: 5 kinds → open/close cycles; assert single-drawer invariant |
| Vitest unit | Focus-restore on Esc | jsdom + `data-anchor-for`: assert `document.activeElement === triggerEl` after `close()` |
| Vitest unit | Lazy-mount policy (`useCotizacion`, `useFacturaElectronica`, `useArqueo`) | assert SWR key `null` → no `fetch` issued (mock `parkosFetch`) |
| Vitest smoke | `render(<Dashboard />)` with mocked `useSesionActiva` returning `{sesion: <stub>}` | assert 6 sections mount + lazy panels DO NOT mount |
| Vitest a11y | Each new panel/sheet via `@axe-core/react` | violations 0 before PR merge |
| Manual E2E | Full happy path (Success Criteria) | after PR-6: login → abrir → `ABC12D` → cotizar → pagar → reimprimir → cerrar |

## Threat Matrix

**`N/A`** — DB DDL + form validation + SWR fetcher closures ONLY. No SPA routing delta (enrich existing `/`; no new routes), no shell, no subprocess, no VCS/PR automation, no executable-file classification, no process integration. Per `sdd-design/references/threat-matrix.md` §route/shell/process criteria, threat matrix is not applicable. Hooks inherit existing `parkosFetch` + Idempotency-Key middleware (`sesionActivaApi.ts:15-17`).

## Migration / Rollout

No migration (backend untouched). Per AGENTS.md regla 4 + 8: per-PR chained merge to `dev` (PR-1 → PR-2 → PR-3 → PR-4 → PR-5 → PR-6). Manual QA replay after PR-6 (analog of `qa-2026-09-17-bug-remediation`): same happy-path script. Surgical `git revert <merge-sha>` of any PR in PR-2..PR-5 keeps the rest working.

## Open Questions

- (a) `<OcupacionStrip />` removal same PR-6 as inline mount, or PR-6.a + PR-6.b? **Recommend SAME PR** — coupled; cold-render would briefly show TWO strips polling the same endpoint. (`App.tsx:32-39` block-comment already marks global as "TEMPORAL".)
- (b) HU-F12.1 "Mi turno" as inline `<MiTurnoPanel />` (PR-5) or separate route `/mi-turno`? **Recommend SEPARATE route** — drill-down, invoked ≤1× per turno.
- (c) `Principal.tsx` (F6.1 stub, unmounted) — keep deep-link `/operacion/ingreso` (per `exploration.md §6.2`) or absorb into dashboard? Affects whether `Principal.tsx` is kept as wrapper or refactored into `<IngresoPanel />` only.

---

**End of design. Artifact persisted to Engram as `sdd/operador-dashboard-hub/design` (architecture, scope=project, capture_prompt=false) and `openspec/changes/operador-dashboard-hub/design.md` (hybrid). Next phase: `sdd-tasks`.**
