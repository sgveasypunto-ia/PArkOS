# Delta Spec — `operations` for change `operador-dashboard-hub`

> Pure ADDED delta. Source canon: REQ-OPS-131..135 (qa-2026-09-17). Extends to REQ-OPS-136..140. RFC 2119: MUST / SHALL / SHOULD / MAY.

---

## ADDED Requirements

### Requirement: REQ-OPS-136 — Dashboard IA consistency

The Dashboard at `/` SHALL be the operator's persistent workspace from `POST /caja-sesion/sesiones` (201, REQ-OPS-119) until `PUT /caja-sesion/sesion/{uuid}/cerrar` (200). The SPA MUST `navigate('/')` on 201. `vigente` MUST be derived client-side as `timestamp_cierre === null` from `SesionRead`. `<ProtectedRoute />` MUST route `sesion === null` to `/caja/abrir-turno`, `sesion !== null` to `/`.

#### Scenario: Dashboard loads post-turno
- **Given** the operador submits `POST /caja-sesion/sesiones` (REQ-OPS-119 payload)
- **When** the response returns 201
- **Then** the SPA MUST `navigate('/')` and render `<TurnoActivoPanel />`
- **And** `<Sidebar />` MUST show `user.email` + `sucursal.uuid`.

#### Scenario: Dashboard redirects pre-turno
- **Given** an authenticated operador with `sesion === null`
- **When** `<ProtectedRoute />` resolves `useSesionActiva()`
- **Then** it MUST route to `/caja/abrir-turno`; with `sesion !== null` MUST route to `/`.

---

### Requirement: REQ-OPS-137 — Composable-section contract

The Dashboard MUST compose N `<FeaturePanel>` instances. Each panel MUST expose `data-testid="dashboard-section-<feature>"` and SHALL accept one optional `onDrawerOpen: (kind: DrawerKind) => void` prop. Panels MUST be pure container/presentational per plan.md §0.2. Hooks MUST live under `features/<feature>/hooks/`, never inside the panel.

#### Scenario: Section lazy-mount
- **Given** the Dashboard renders 6+ sections and no active `uuid_ingreso`
- **When** `<CotizacionPanel />` is idle
- **Then** it MUST NOT issue `GET /operacion/cotizar` until mounted; MUST mount at most once per active flow (F7.1).

#### Scenario: Panel refresh independence
- **Given** `<OcupacionPanel />` polls at `refreshInterval: 10_000` (REQ-OPS-030/132) and `<SyncStatusStrip />` polls `GET /sync/estado` every 30 s
- **When** one SWR cycle fails
- **Then** the failure MUST NOT cascade; per-panel `<ErrorBoundary />` MUST contain it.

---

### Requirement: REQ-OPS-138 — Drawer state machine

Drawers SHALL open via `useDashboardDrawerStore` (Zustand) with `openDrawer: 'pago' | 'fe-retry' | 'reimpresion' | 'arqueo' | 'cierre-diario' | null`. Exactly one drawer MUST be open. `Close` or `Esc` MUST close the active drawer; closing MUST restore DOM focus via `data-anchor-for="<drawer-kind>"`.

#### Scenario: Single-drawer guard
- **Given** `<PagoSheet />` is open (state `pago`)
- **When** the operador clicks the "Reimprimir tiquete" trigger
- **Then** Pago MUST close AND Reimpresion MUST open
- **And** no two drawers MUST be visible at once.

#### Scenario: Esc key closure
- **Given** any drawer is open
- **When** the operador presses `Esc`
- **Then** the drawer MUST close and `document.activeElement` MUST equal the trigger with `data-anchor-for="<drawer-kind>"`.

---

### Requirement: REQ-OPS-139 — Panel lazy-mount policy

Panels requiring non-trivial HTTP load (Cotizacion, Arqueo, FE-retry, Reimpresion) MUST lazy-mount only when their `use*` SWR trigger is truthy (`uuid_ingreso`, `uuid_arqueo`, `uuid_factura_electronica`, `uuid_ticket`). Prevents the 5+ polling-SWR refresh storm.

#### Scenario: Cold Dashboard has 0 panel fetches
- **Given** a fresh Dashboard with no active `uuid_ingreso`, no pending FE retries, no `uuid_arqueo`
- **When** the SPA cold-mounts
- **Then** the only network calls MUST be `<OcupacionStrip />` (REQ-OPS-030), `<SyncStatusStrip />`, and `GET /caja-sesion/sesion/me` (REQ-OPS-027)
- **And** `<CotizacionPanel />`, `<PagoSheet />`, `<ArqueoSheet />`, `<ReimprimirTiqueteSheet />`, `<FacturaElectronicaRetryPanel />` MUST be unmounted.

#### Scenario: Cotizacion lazy-mount on active ingreso
- **Given** a cold Dashboard with `<CotizacionPanel />` idle and `ABC12D` typed in `<PlacaInput />`
- **When** `useIngresoActivo(uuid_ingreso || null)` (F6.1) resolves a non-null UUID
- **Then** `<CotizacionPanel />` MUST mount and `useCotizacion(uuid_ingreso)` MUST start polling per REQ-OPS-132.

---

### Requirement: REQ-OPS-140 — Sync-strip relocation

The global `<OcupacionStrip />` at `renderer/App.tsx:48` (F4.3 "mount TEMPORAL") MUST be removed for an in-dashboard `<OcupacionPanel />`. `<SyncStatusStrip />` MUST poll `GET /sync/estado` per F11.1, reusing `useSyncEstado` (REQ-OPS-132 fetcher-closure).

#### Scenario: App.tsx global strip removed
- **Given** PR-6 of the chain is merged
- **When** the SPA inspects `App.tsx`
- **Then** `<OcupacionStrip />` MUST be absent at line 48 and any successor global mount removed; `useOcupacion()` MUST be invoked only from `<OcupacionPanel />`.

#### Scenario: Inline panel matches global-strip baseline
- **Given** the Dashboard with `<OcupacionPanel />` mounted
- **When** `useOcupacion()` returns `{items: [{tipo: 'carro', activos: 1, cupo_maximo: 0, disponible: -1}]}` (REQ-OPS-030)
- **Then** the panel MUST render the same chip text as the previous global strip.