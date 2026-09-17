# Exploration: operador-dashboard-hub

> **Change**: `operador-dashboard-hub`
> **Phase**: explore (sdd-explore)
> **Branch**: TBD from `dev`
> **Date**: 2026-09-17
> **Working dir**: `E:\easypunto_parkos`
> **PR target**: `origin/dev`
> **Scope**: Consolidate F4-F10 operator actions into a persistent single dashboard that loads immediately after `POST /caja-sesion/sesiones`. All F4-F11 functionality lives as composable panels/cards inside ONE route — NOT separate routes.

---

## 1. Current state (with file:line citations)

### 1.1 Routing & App shell

**`apps/electron-sucursal/src/renderer/App.tsx:54-86`** — the SPA router today has only 4 routes:

```tsx
<Routes>
  <Route path="/login" element={<Login />} />
  <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
  <Route path="/caja/abrir-turno" element={<ProtectedRoute><AbrirTurno /></ProtectedRoute>} />
  <Route path="/caja/cerrar-turno" element={<ProtectedRoute><CerrarTurno /></ProtectedRoute>} />
  <Route path="*" element={<p role="status">404</p>} />
</Routes>
```

`/`, `/caja/abrir-turno`, `/caja/cerrar-turno` are inside `ProtectedRoute` (`App.tsx:23-57`). `<OcupacionStrip uuid_sucursal={uuid_sucursal} />` is mounted GLOBALLY at `App.tsx:48` for all authenticated routes — TEMPORAL until F4.4 dashboard relocate the component (per `App.tsx:32-39` block-comment).

### 1.2 Dashboard page — currently a thin "TurnoActivoPanel + redirect" container

**`apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx:39-87`**:

- (a) `sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno', { replace: true })` (lines 53-55).
- (b) `sesion !== null` → `<TurnoActivoPanel sesion onCerrarClick={() => navigate('/caja/cerrar-turno')} />` (lines 76-82).
- (c) `isLoading` → `<Skeleton>` (line 60).
- (d) `error !== 404/422` → error + retry (lines 64-72).

There is NO redirect-to-login path in Dashboard itself — auth gating is delegated to `<ProtectedRoute>`. The hook contract (DEC-F3.3-05): `useSesionActiva` returns `null` on 404/422 (operador sin turno is a valid state, not an error) — `useSesionActiva.ts:64-66`.

### 1.3 TurnoActivoPanel — organism that displays the active turno

**`apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx:40-81`** — presentational Card showing UUID, `valor_inicial_efectivo`, `valor_inicial_datafono`, `timestamp_apertura`, observaciones opcional, and a "Cerrar turno" button. NO final values are displayed here — `valor_final_*` lives in `SesionCerrarRequest` (sesionActivaApi.ts:58-62) and is sent on PUT close; the close-side values are stamped in `log_transaccional.datos_nuevos` per `caja_sesion.py:41-60` docstring.

### 1.4 `useSesionActiva()` — SWR key null when no accessToken

**`apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts:52-89`** — key `/caja-sesion/sesion/me`, refresh interval 50min (DEC-SUC-03, `auth.ts:31`), deduping 10s. 401 → defensive logout via `useAuthStore.clear()` + `parkos:auth:cleared` event (lines 67-74).

### 1.5 `useOcupacion()` — SWR hook for live occupancy

**`apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts:73-129`** — fetches `/operacion/ocupacion?uuid_sucursal=X` every 10s (constants.ts), exposes `isStale` flag when `data !== undefined && error !== undefined` (line 121). **REQ-OPS-132 fix (qa-2026-09-17):** closure captures bare UUID for the fetcher, NOT the cache key (lines 89-91) — comment explicitly documents the prior bug and the precedent in `useSesionActiva:55-57` and `useIngresoActivo:67-69`.

### 1.6 `useIngresoActivo(placa)` — SWR hook for active-ingreso pre-flight

**`apps/electron-sucursal/src/features/operacion/hooks/useIngresoActivo.ts:63-103`** — key `/operacion/ingresos?placa=X` (Path 1 client-side most-recent filter — sort by `fecha_ingreso.localeCompare`). Used in `Principal.tsx:83-84` for the auto-redirect on `409 ingreso_activo_existente`.

### 1.7 Catalogos hooks (read-only)

**`useTiposVehiculo.ts`** — `/catalogos/tipos-vehiculo`, fallback hardcoded `{auto, moto}` if API down. **F4.1 shipped.**
**`useTarifasVigentes(uuidTipoVehiculo)`** (`useTarifasVigentes.ts:122-204`) — `/empresa/tarifas-sucursal`, 5min deduping, electron-store cache `parkos.tarifas.cache.v1`, 1h stale threshold. **F4.2 shipped.** Includes bridge access (`window.bridge.tarifasStore.get/set`) — F4.2 two-phase render pattern.

### 1.8 Backend endpoints (all exist; none are missing for the dashboard scope)

| Endpoint | Backend file | HU origin | Status |
|---|---|---|---|
| `GET /api/v1/caja-sesion/sesion/me` | `caja_sesion.py:227-252` | F1.13 (REQ-OPS-027/029) | ✅ shipped |
| `POST /api/v1/caja-sesion/sesiones` | `caja_sesion.py:81-134` | F1.3 (REQ-40) | ✅ shipped |
| `PUT /api/v1/caja-sesion/sesion/{uuid}/cerrar` | `caja_sesion.py:137-164` | F1.13 (REQ-41, SC-42) | ✅ shipped |
| `GET /api/v1/operacion/ocupacion` | `operacion.py:821-908` | F1.5 (REQ-OPS-030/031) | ✅ shipped |
| `POST /api/v1/operacion/ingresos` | `operacion.py:116-540` | F1.6 (11-step chain) | ✅ shipped |
| `GET /api/v1/operacion/ingresos` (filtros) | `operacion.py:612-633` | F1.6 | ✅ shipped |
| `GET /api/v1/operacion/cotizar` | `operacion.py:647-709` | F1.8 (REQ-OPS-022..025) | ✅ shipped |
| `POST /api/v1/operacion/salidas` | `operacion.py:322-545` | F1.7 (REQ-OPS-042..052) | ✅ shipped |
| `POST /api/v1/facturacion/factura` | `facturacion.py:190-...` | F1.9 | ✅ shipped |
| `POST /api/v1/facturacion/factura-pagos` | `facturacion.py:410-...` | F1.9 | ✅ shipped |
| `POST /api/v1/facturacion/factura-electronica` | `facturacion.py:514-...` | F1.10 | ✅ shipped |
| `GET /api/v1/facturacion/factura-electronica/{uuid}` | `facturacion.py:723-...` | F1.10 | ✅ shipped |
| `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` | `facturacion.py:844-...` | F1.10 | ✅ shipped |
| `POST /api/v1/workflows/reimpresion-ticket` | `workflows_reimpresion.py:84-...` | F1.11 | ✅ shipped |
| `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` | `workflows_reimpresion.py:247-...` | F1.11 | ✅ shipped |
| `POST /api/v1/clientes/venta-suscripcion` | `clientes_venta.py:64-...` | F1.12 | ✅ shipped |
| `POST /api/v1/caja/arqueo` | `caja_arqueo.py:67-...` | F1.13 (12-step chain) | ✅ shipped |
| `GET /api/v1/caja/arqueo/resumen` | `caja_arqueo.py:337-...` | F1.13 (T4.1) | ✅ shipped |
| `GET /api/v1/sync/estado` | `sync_estado.py:57-119` | F1.14 (REQ-OPS-098..101) | ✅ shipped |
| `GET /api/v1/workflows/alerta` (HU-F1.1 fix) | `workflows.py:135-142` (factory `make_router`) | F1.1, F11.2 | ✅ shipped |
| `GET /api/v1/workflows/reimpresion-ticket` (list) | `workflows.py:111-118` | F1.11, F8.3 | ✅ shipped |

**Backend is COMPLETE for the dashboard scope.** The frontend integration is the gap.

### 1.9 SesionRead shape — NO `vigente` flag exposed

**`backend/packages/parkos_core/src/parkos_core/schemas/caja.py:178-200`** — `SesionRead` exposes:
```python
uuid, created_at, created_by, sync_status, sync_timestamp, sync_attempts,
valor_inicial_efectivo, valor_inicial_datafono,
uuid_sucursal, uuid_usuario,
timestamp_apertura, timestamp_cierre, uuid_usuario_cierre
```

There is **no derived `vigente` boolean** in the wire schema. The frontend must derive `vigente = timestamp_cierre === null` (the partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023, F1.3) guarantees at most one OPEN row per actor — see `caja_sesion.py:240-244`). The `useSesionActiva` 404 path (`sesionActivaApi.ts:90-99`) already models "no open session" as a first-class state — `sesion === null` means "no active turno".

### 1.10 Routes that DO NOT exist yet but plan.md Fase 4-Fase 11 require

| Path | plan.md location | Endpoint | Frontend pages that exist | Gap |
|---|---|---|---|---|
| `/operacion/ingreso` | plan.md:1500-1561 (F6.1) | `GET/POST /operacion/ingresos` | `operacion/pages/Principal.tsx` (placeholder for HU-F6.1) | ❌ NOT MOUNTED in App.tsx; `Principal.tsx` is F6.1 stub only |
| `/operacion/cotizar` (or `?uuid_ingreso=`) | plan.md:1660-1698 (F7.1) | `GET /operacion/cotizar` | ❌ none | ❌ missing |
| `/operacion/salida` | plan.md:1700-1741 (F7.2) | `POST /operacion/salidas` | ❌ none | ❌ missing (placeholder URL `SALIDA_FLOW_STUB` at `Principal.tsx:55`) |
| `/operacion/salida/mensualidad` | plan.md:1700-1733 (F7.2) | `POST /operacion/salidas/mensualidad` | ❌ none | ❌ missing |
| `/facturacion/factura-electronica/:uuid` | plan.md:1941-1966 (F8.2) | `GET .../{uuid}` | ❌ none | ❌ missing |
| `/facturacion/factura-electronica/:uuid/reintentar` | plan.md:1941-1966 (F8.2) | `POST .../{uuid}/reintentar` | ❌ none | ❌ missing |
| `/reimpresion/tiquete` | plan.md:1969-2009 (F8.3) | `POST /workflows/reimpresion-ticket` | ❌ none (no `features/reimpresion/` folder exists) | ❌ missing |
| `/suscripciones/venta` | plan.md:2018-2060 (F9.1) | `POST /clientes/venta-suscripcion` | ❌ none (no `features/suscripciones/` folder exists) | ❌ missing |
| `/suscripciones/listado` | plan.md:2094-2124 (F9.2) | (no dedicated endpoint — uses `make_router` list) | ❌ none | ❌ missing |
| `/caja/arqueo` | plan.md:2140-2182 (F10.1) | `POST /caja/arqueo` | ❌ none (no `caja/pages/ArqueoParcial.tsx`) | ❌ missing |
| `/caja/cierre-diario` | plan.md:2246-2266 (F10.3) | `POST /caja/arqueo` + `GET /caja/arqueo/resumen` | ❌ none (no `caja/pages/CierreDiario.tsx`) | ❌ missing |
| `/sync/estado` | plan.md:2272-2299 (F11.1) | `GET /sync/estado` | ❌ none (no `features/sync/` folder; no `components/SyncBanner.tsx`) | ❌ missing |
| `/alertas/local` | plan.md:2303-2344 (F11.2) | `GET /workflows/alerta?uuid_sucursal=X&estado=abierta` | ❌ none (no `features/alertas/` folder; no `components/AlertasPanel.tsx`) | ❌ missing |

### 1.11 Features folders present vs absent

| Feature folder | Files present | Notes |
|---|---|---|
| `features/auth/` | Login.tsx, LoginForm.tsx, loginApi.ts, loginSchema.ts, useCountdown.ts | ✅ F3.1 complete |
| `features/caja/` | Dashboard.tsx, AbrirTurno.tsx, CerrarTurno.tsx, TurnoActivoPanel.tsx, AbrirTurnoForm.tsx, CerrarTurnoForm.tsx, sesionActivaApi.ts, useSesionActiva.ts, format.ts, turnoSchema.ts | ✅ F3.3 complete (CerrarTurno placeholder for F10.x) |
| `features/catalogos/` | useTiposVehiculo.ts, useTarifasVigentes.ts, TarifaBadge.tsx | ✅ F4.1, F4.2 hooks shipped; TarifaBadge component exists |
| `features/operacion/` | Principal.tsx (F6.1 stub), PlacaInput.tsx, ForzarIngresoModal.tsx, TiqueteModal.tsx, useOcupacion.ts, useIngresoActivo.ts, ocupacionApi.ts, ingresoApi.ts, ingresoActivoApi.ts, occupancyThresholds.ts | ✅ F4.3 + F6.1 components shipped; NOT mounted in App.tsx |
| `features/facturacion/` | ❌ folder does not exist | entire feature missing |
| `features/reimpresion/` | ❌ folder does not exist | entire feature missing |
| `features/suscripciones/` | ❌ folder does not exist | entire feature missing |
| `features/sync/` | ❌ folder does not exist | entire feature missing |
| `features/alertas/` | ❌ folder does not exist | entire feature missing |
| `renderer/components/` | OcupacionStrip.tsx, StatusBar.tsx, ProtectedRoute.tsx, ui/* (button, card, dialog, dropdown-menu, form, input, popover, select, sheet, skeleton, table, tabs, toast, tooltip, badge) | `sheet` (Drawer) ✅ shadcn primitive available; `tabs` ✅ available |

### 1.12 Hooks inventory — what's reusable, what needs to be created

**Existing & reusable:**
- `useSesionActiva()` (F3.3) → dashboard shell, drives redirect-to-AbrirTurno
- `useOcupacion(uuid_sucursal)` (F4.3) → live strip
- `useIngresoActivo(placa)` (F6.1) → pre-flight for ingreso
- `useTiposVehiculo()` (F4.1) → catalog for PlacaInput
- `useTarifasVigentes(uuidTipoVehiculo)` (F4.2) → catalog for tarifa chip
- `useAuth()` (ui-kit) → user/sucursal/permisos
- `useCountdown()` (auth) → 15min countdown for cotizacion

**Missing hooks that this change needs to CREATE (in the appropriate feature folder):**
| Hook | Endpoint | Feature | Phase |
|---|---|---|---|
| `useCotizacion(uuid_ingreso)` | `GET /operacion/cotizar?uuid_ingreso=X` | operacion | F7.1 (260 LOC) |
| `useCotizacionCountdown(ttlMs=15*60_000)` | n/a (pure) | operacion | F7.1 |
| `useSuscripcionesProximasVencer(uuid_sucursal)` | list via `make_router` factory | suscripciones | F9.2 |
| `useVueltos(total, recibido)` | n/a (pure) | facturacion | F8.1 |
| `useSyncEstado(uuid_sucursal)` | `GET /sync/estado` | sync | F11.1 |
| `useAlertas(uuid_sucursal, estado)` | `GET /workflows/alerta` | alertas | F11.2 |
| `useArqueoResumen(uuid_sucursal, fecha)` | `GET /caja/arqueo/resumen` | caja | F10.3 |
| `useFacturaElectronicaEstado(uuid)` | `GET /facturacion/factura-electronica/{uuid}` | facturacion | F8.2 |

### 1.13 plan.md verbatim citations

| Fase | Citation | Notes |
|---|---|---|
| §0.4 precedent | "Tres HU clave para abrir turno y operar inmediatamente" | establishes single-screen-after-turno precedent |
| L1500-1561 F6.1 | HU-F6.1-T3 `Principal.tsx` orquesta `PlacaInput`, banner tipo detectado, `OcupacionStrip` (Fase 4) | F6.1 page is a STUB today; needs full UX wiring |
| L1660-1698 F7.1 | HU-F7.1-T1..T4: `buscarIngresoTolerante`, `useCotizacion` SWR `refreshInterval:1000`, `CotizacionPanel` con `<dl>` semántico + countdown 15min | tolerance function lives in `lib/validation/placaTolerante.ts` (NOT in `placa.ts`) |
| L1700-1741 F7.2 | `SalidaFlow` (wizard 2 pasos: confirmación con desglose → tiquete) + `SalidaMensualidad` atajo | both pages need to be built |
| L1828-1922 F8.1 | `PagoModal` con vueltos en vivo, voucher manual, FE siempre consumidor final por defecto (NIT `222222222222222`) | pago modal needs RHF + Zod refinement |
| L1941-1966 F8.2 | `FacturaDetalle` page, polling SWR 30s hasta estado terminal, botón reintentar cuando `rechazado` | polling key gate `null` cuando estado terminal |
| L1969-2009 F8.3 | `ReimprimirTiquete` con búsqueda por placa + motivo ≥10 chars; `role="alertdialog"` (consequence of cobro) | distinct from free-immediate E3 reprint |
| L2012-2124 F9.1, F9.2 | `Venta` wizard 4 pasos (cliente → vehículos → plan → pago) + `Listado` DataTable + banner amarillo "Suscripción de esta placa vence en X días" | banner integrates into `Principal.tsx` (F6.1) |
| L2127-2266 F10.1, F10.2, F10.3 | `ArqueoParcial` (no cierra) / `CerrarTurno` (arqueo `cierre_turno`) / `CierreDiario` (arqueo `cierre_dia`, cierra todas las sesiones del día) | three different `tipo_arqueo` codes: `auditoria`/`cierre_turno`/`cierre_dia` |
| L2268-2344 F11.1, F11.2 | `SyncBanner` (3 colores según `lag_seg`) + `AlertasPanel` (lista 11 códigos de negocio, drill-down, marcar revisada = INSERT nueva fila con `uuid_alerta_padre`) | polling 30s; "sin conexión API local" es banner separado (3 fallos consecutivos de `api-status`) |

---

## 2. Affected areas (table)

| Path | Why affected | Expected delta |
|---|---|---|
| `apps/electron-sucursal/src/renderer/App.tsx` | Currently mounts `Dashboard` at `/` only; needs to absorb F6-F11 components OR redirect to new dashboard route | Mount new dashboard route OR refactor existing `Dashboard` into composable dashboard; OcupacionStrip move from App.tsx → dashboard |
| `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` | Currently renders only TurnoActivoPanel; becomes the orchestrator for all panels | Becomes the persistent operator hub; sections for Ingreso, Salida/Cotizar, Pago, FE/Reintentar, Reimprimir, Suscripciones, Arqueo, Cierre Diario, Sync, Alertas |
| `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx` | Currently the only thing rendered on dashboard | Stays as top "turno info" card; receives `vigente` derived from `timestamp_cierre` |
| `apps/electron-sucursal/src/features/operacion/pages/Principal.tsx` | F6.1 stub; never mounted in router today | Either (a) move into Dashboard as `<IngresoPanel>` OR (b) keep as separate route reachable via deep-link from dashboard |
| `apps/electron-sucursal/src/features/facturacion/` | Does not exist | Create: `pages/PagoModal.tsx`, `pages/FacturaDetalle.tsx`, `lib/validation/nit.ts`, `lib/validarNitModulo11.ts`, `hooks/useVueltos.ts`, `hooks/useFacturaElectronica.ts`, `api/facturaApi.ts`, `api/facturaElectronicaApi.ts` |
| `apps/electron-sucursal/src/features/reimpresion/` | Does not exist | Create: `pages/ReimprimirTiquete.tsx`, `api/reimpresionApi.ts` |
| `apps/electron-sucursal/src/features/suscripciones/` | Does not exist | Create: `pages/Venta.tsx` (wizard 4 pasos), `pages/Listado.tsx`, `hooks/useSuscripcionesProximasVencer.ts`, `api/suscripcionesApi.ts` |
| `apps/electron-sucursal/src/features/sync/` | Does not exist | Create: `components/SyncBanner.tsx`, `hooks/useSyncEstado.ts`, `api/syncApi.ts` |
| `apps/electron-sucursal/src/features/alertas/` | Does not exist | Create: `components/AlertasPanel.tsx`, `hooks/useAlertas.ts`, `api/alertasApi.ts` |
| `apps/electron-sucursal/src/features/operacion/pages/SalidaFlow.tsx` | Does not exist | Create: wizard 2 pasos (CotizacionPanel + confirmación) |
| `apps/electron-sucursal/src/features/operacion/pages/SalidaMensualidad.tsx` | Does not exist | Create: atajo sin cobro (HU-F7.2) |
| `apps/electron-sucursal/src/features/operacion/hooks/useCotizacion.ts` | Does not exist | Create: SWR with `refreshInterval: 1000` while panel open, countdown 15min |
| `apps/electron-sucursal/src/features/operacion/components/CotizacionPanel.tsx` | Does not exist | Create: `<dl>` semántico + countdown |
| `apps/electron-sucursal/src/features/operacion/lib/validation/placaTolerante.ts` | Does not exist | Create: `buscarIngresoTolerante` con `O↔0`/`I↔1`/`B↔8` (DEC-SUC-22 — EXCLUSIVA de Fase 7) |
| `apps/electron-sucursal/src/features/caja/pages/ArqueoParcial.tsx` | Does not exist | Create: form + diferencia en vivo (informativa % / determinante monto absoluto) |
| `apps/electron-sucursal/src/features/caja/pages/CierreDiario.tsx` | Does not exist | Create: resumen por sesión + form |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Has F6.1 keys; needs F7+ keys | Add: `cotizar.*`, `salida.*`, `facturacion.*` (already separate file) |
| `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` | Exists but empty-ish | Populate: `pago.*`, `fe.*`, `reimprimir.*` |
| `apps/electron-sucursal/src/renderer/i18n/locales/sync.json` | Exists but empty-ish | Populate: `banner.*`, `lag.*` |
| `openspec/specs/` | Specs for F4-F11 exist (catalogos, operacion, facturacion, etc.); dashboard spec is new | Add: `dashboard-operador.md` capturing the IA (panel hierarchy + drawer flows) |
| `openspec/specs/operations/spec.md` | F6.1 spec exists | Add § for F7.1/F7.2/F7.3 if not present |
| `openspec/scripts/check_schema_match.py` | Validator covers 49 tables | No DB change → no migration → unchanged |

---

## 3. Approaches considered

### Approach A — Single-route dashboard with composable sections (RECOMMENDED)

Replace `/` (current `Dashboard`) with a persistent hub that contains all F4-F11 functionality as composable cards/sections. Modals (`PagoModal`, `ForzarIngresoModal`, `TiqueteModal`, `ReimprimirTiquete`) and the `AlertDialog` flow mount on demand via `<Sheet>` (right-side drawer, already in shadcn primitives at `renderer/components/ui/sheet.tsx`).

| Pros | Cons |
|---|---|
| Cleanest UX for kiosko (plan.md §0.2 + §0.4 precedent "pantalla principal") — operator never leaves the hub | Big PR — 7+ features touched; needs careful sub-component design to avoid scroll overload |
| Single source of truth for `sesion` (drives every panel's enabled state via single `useSesionActiva()` consumer) | Cumulative LOC >800 → auto-chain trigger per `config.yaml rules.tasks` (must chain into 3-5 PRs) |
| Native to react-router (the `/` route already exists) — no new routing infrastructure | Each section must declare its own SWR scope (avoid 20-request waterfalls on mount) |
| Matches plan.md §0.2 "los organismos sí conocen el dominio" — organisms can compose freely | Requires new folder scaffolding (facturacion, reimpresion, suscripciones, sync, alertas) |
| One mount of `OcupacionStrip` (move from App.tsx:48 into dashboard) — no longer global pollution on `/caja/abrir-turno` | |

**Effort: High** (4-6 chained PRs, ~300-800 LOC each).

### Approach B — Tabbed dashboard (shadcn `Tabs` primitive)

Use `renderer/components/ui/tabs.tsx` (already exists) to mount a tabs strip with one tab per Fase (Ingreso / Salida / Cobro / FE / Reimprimir / Suscripciones / Caja / Sync). Each tab is its own feature page.

| Pros | Cons |
|---|---|
| Native shadcn primitive (zero infrastructure cost) | Multiple clicks to switch between frecuente flows (e.g., operator finishes ingreso → switches to salida tab → enters plate) |
| Lower scroll pressure on a single page | Tab IA is rigid — what if a flow crosses tabs (e.g., Salida ends in Cobro)? |
| Clear visual IA for first-time operators | Plan.md §0.4 explicitly favors single-screen UX over tab navigation |

**Effort: Medium**.

### Approach C — Single-route dashboard with right-side Sheet drawers for modal flows

Same as A, but multi-step flows (PagoModal, FE reintentar, Reimprimir, Arqueo) mount in a `<Sheet side="right">` instead of centered Dialog. The main view stays uncluttered.

| Pros | Cons |
|---|---|
| Main view uncluttered; drawers preserve the live turno context (kiosk pattern) | Complex state: which drawer is open + which UUID is threaded through |
| Matches "kiosko pattern" — never lose context | `<Sheet>` animations on a 2-min flow may feel sluggish vs instant modal |
| Existing shadcn primitive | |

**Effort: Medium-High**.

---

## 4. Recommendation

**Pick Approach A (single-route dashboard with composable sections), with Approach C's `<Sheet>` drawers reserved for the multi-step modal flows (Pago, FE reintentar, Reimprimir, Arqueo).**

### Rationale

1. **Plan.md §0.4 precedent** — "Tres HU clave para abrir turno y operar inmediatamente" already implies the single-screen-after-turno UX. The current `<Dashboard />` (F3.3) is the placeholder for this exact hub; F4.3+F4.4 were the planned home of the dashboard relocate. The plan also references `Principal.tsx` (Fase 6.1, F9.2 banner integration) as the operator's home — same concept.

2. **No new routing infrastructure** — the `/` route already exists and is mounted with `<ProtectedRoute>`. The work is *evolution*, not introduction.

3. **Backend is COMPLETE for the entire dashboard scope** (see §1.8). 21 endpoints are shipped. This change is **pure frontend integration**, not a backend deliverable — the only backend changes needed (if any) are zero-LOC contract confirmations and possibly a tiny derivation if `SesionRead` should grow a `vigente` boolean (current workaround: derive `vigente = timestamp_cierre === null` client-side).

4. **Approach C's `<Sheet>` drawers are a free win** — they already exist in `renderer/components/ui/sheet.tsx`. Use them for PagoModal, ForzarIngresoModal (already in `Principal.tsx`), TiqueteModal (already in `Principal.tsx`), FacturaDetalle, ReimprimirTiquete. The main dashboard view stays focused on the operator's "what's happening now" cards (turno info + sync banner + alertas panel + ocupación strip + PlacaInput for ingreso at the top).

5. **Chained PR strategy** — the 400-line review budget (per `config.yaml rules.tasks`) forces chained PRs. Suggested chain:

   | PR | Scope | Approx LOC |
   |---|---|---|
   | PR1 — `dashboard-shell` | New `/dashboard` route (alias of `/` for now); Dashboard container with TurnoActivoPanel + OcupacionStrip + 3 placeholder slots; i18n keys | ~250 |
   | PR2 — `operacion-salida` | `useCotizacion`, `CotizacionPanel`, `SalidaFlow`, `SalidaMensualidad`, `placaTolerante.ts`; integrates F7.1+F7.2 panels | ~700 (auto-chain) |
   | PR3 — `facturacion-pago-fe` | `facturacion/` folder: `PagoModal`, `nit.ts` validation, `useVueltos`, `FacturaDetalle`, `useFacturaElectronica`; F8.1+F8.2 panels | ~700 (auto-chain) |
   | PR4 — `reimpresion-suscripciones` | `reimpresion/` + `suscripciones/` folders; F8.3 + F9.1 + F9.2 (incl. banner integration) | ~700 (auto-chain) |
   | PR5 — `caja-arquo-sync-alertas` | `ArqueoParcial`, `CierreDiario`, `SyncBanner`, `AlertasPanel`, F10.1+F10.3+F11.1+F11.2 panels | ~700 (auto-chain) |
   | PR6 — `cleanup-route-deprecate` | Remove `/caja/cerrar-turno` standalone (becomes a drawer), remove redundant routes from `App.tsx`, simplify `Dashboard.test.tsx` | ~250 |

6. **No DB / migration work needed** — confirmed: backend endpoints unchanged. The audit-first data model is unaffected. The only DB-level concern is the `vigente` derivation: prefer client-side (`timestamp_cierre === null`) over a backend column add (would trigger a 4NF pass).

7. **Existing hooks (`useOcupacion`, `useIngresoActivo`, `useTiposVehiculo`, `useTarifasVigentes`) compose cleanly** — they all share the `(uuid_sucursal, accessToken)` gate pattern. New hooks should mirror this exactly.

---

## 5. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Scope explosion** — 7+ Fases touched, 21 endpoints integrated, 5 new feature folders | High | High | Chained PRs (PR1-PR6, see §4.5); each PR has autonomous scope + own verification; PR1 establishes the shell before any feature lands |
| **UX regression** — operators trained on F6.1 separate route (`Principal.tsx` was the F6.1 standalone intent) | Medium | Medium | Keep `Principal.tsx` reachable as deep-link `/operacion/ingreso`; the dashboard renders it as a panel, not a replacement route. The redirect target for `409 ingreso_activo_existente` stays `/operacion/salida?...`. |
| **Cumulative LOC >800 = auto-chain trigger** | High (certain) | Medium | Explicit chained PR plan in §4.5; each PR ≤800 LOC; gitflow branch strategy (target `dev`, never `main`) |
| **Sync lag if dashboard polls too aggressively** — 5+ SWR hooks polling every 10s/30s simultaneously | Medium | Medium | Audit each hook's `refreshInterval` (per existing pattern in `useOcupacion.ts:93-94`); share SWR keys where possible (e.g., single `useSyncEstado` consumer, not per-component refetch); consider `dedupingInterval` ≥ refresh interval |
| **RADIUS cost — 20+ requests per render** if all panels mount at once | Medium | Medium | Lazy-mount expensive panels: only mount `CotizacionPanel` when an active `uuid_ingreso` is selected; only mount `FacturaDetalle` when a `uuid_factura` is in flight; keep static panels (sync banner, alertas, ocupación) always mounted |
| **Modal/drawer state leakage** — multiple flows open at once if state isn't disciplined | Medium | Medium | Single `useDashboardStore` (Zustand, ui-kit pattern) holding `openDrawer: 'pago' \| 'fe-reintentar' \| 'reimprimir' \| 'arqueo' \| null` + `drawerContext: { uuid?: string }`; only one drawer open at a time |
| **i18n coverage** — `facturacion.json`, `sync.json` are sparse | Low | Medium | New locales JSON files populated per PR (PR3 for facturacion, PR5 for sync); never inline Spanish strings in components (per `engram/protocol` artifact language contract) |
| **WCAG 2.1 AA regression** — new cards/drawers must pass axe-core | Medium | High | Each PR runs `@axe-core/playwright` smoke test; existing `StatusBar.test.tsx` + `OcupacionStrip.test.tsx` patterns to mirror; semantic `<dl>` in `CotizacionPanel` per plan.md:1677 |
| **No physical DELETE violation** — none of the dashboards trigger API writes that could be mistaken for delete | n/a | n/a | All dashboard flows are C+Q+U (Consulta / Inserción / Actualización) per canon AGENTS.md; no DELETE endpoints exist or are added |
| **Tenant scope leak** — admin- token vs operador- token cross-tenant | Low | Critical | All hooks inherit SWR key gate pattern; backend handlers already enforce 403 `tenant_scope_violation` (see `operacion.py:166-175` for ingreso); no special handling needed in the dashboard |

---

## 6. Open questions

1. **Does the dashboard route replace `/` outright, OR is `/` kept as a "redirect-if-no-turno" stub and a NEW `/dashboard` (or `/operar`) route is the hub?**
   - Today `/` is `Dashboard` which redirects to `/caja/abrir-turno` when there's no session. Plan.md F3.3 DEC-F3.3-05 mandates this redirect. If we keep that behavior, the dashboard at `/` only ever renders for active-session users.
   - **Recommendation**: keep `/` = Dashboard. The redirect-when-no-session semantics naturally turns the dashboard into "hub during open turno". No new route needed.

2. **Are AbrirTurno and CerrarTurno pages kept as standalone routes, OR merged into the dashboard as drawers?**
   - Today `/caja/abrir-turno` and `/caja/cerrar-turno` are standalone routes (`App.tsx:65-79`).
   - **Recommendation**: keep both reachable as deep links (`/caja/abrir-turno` is still the no-session entry; `/caja/cerrar-turno` becomes a Sheet drawer triggered by TurnoActivoPanel's "Cerrar turno" button). The dashboard handles both via the same `<ProtectedRoute>` chain.

3. **Should HU-F12.1 ("Mi turno" KPI panel) be a panel inside this dashboard, OR deferred to its own change?**
   - Plan.md Fase 12 (L2348-2357) defines `Mi turno` panel: KPIs (ingresos count, salidas count, total cobrado, desglose por medio de pago).
   - **Recommendation**: include it as a panel inside the dashboard (TurnoActivoPanel can grow a "Resumen" section, OR a new `<MiTurnoPanel>` slot). Plan.md scope says Fase 12 is a "subset of CU-09" — it's small enough to ship with PR1 or PR6.

4. **¿Soporte para múltiples turnos abiertos simultáneos?**
   - Canon AGENTS.md: "branch-pinned, single sesion per actor per sucursal" enforced by `prod.uq_prod_sesion_one_active_per_user` (migration 0023, F1.3). N/A — the system cannot represent this state. No action needed.

5. **¿Reporte histórico del turno (Fase 12.2+)?**
   - Out of this change's scope. Plan.md Fase 12 explicitly says "subset de CU-09" — historical reports are admin-side. Defer.

6. **¿Drawer vs Dialog for PagoModal?**
   - Both are valid. **Recommendation**: `<Sheet>` (right side) for PagoModal because it preserves context (the operator can see the turno info while filling the payment); `<Dialog>` (centered) for TiqueteModal (full-screen tiquete needs focus). ReimprimirTiquete — `<AlertDialog>` per plan.md:1983 (consequence of cobro).

7. **¿Idempotency-Key header for all dashboard POSTs?**
   - Yes, per F2.2 precedent + plan.md:1509 (F6.1 mandates Idempotency-Key for `POST /operacion/ingresos`). Existing `parkosFetch` wrapper handles this automatically for all POSTs except `/auth/login` (see `sesionActivaApi.ts:15-17`). No new work needed; the dashboard just calls the existing `*Api.ts` wrappers.

8. **¿The `vigente` flag in `SesionRead` — add to backend schema, or derive client-side?**
   - **Recommendation**: derive client-side (`sesion.timestamp_cierre === null`) to avoid a migration + a 4NF pass. The SesionRead schema already exposes `timestamp_cierre` (`schemas/caja.py:199`); the dashboard component can compute `vigente` in a one-liner memo.

9. **¿SyncBanner and AlertasPanel are global (mounted in App.tsx) OR dashboard-scoped?**
   - Plan.md:2284 says `SyncBanner` is a top-level component with polling. Plan.md:2333 says `AlertasPanel` is a panel.
   - **Recommendation**: keep `OcupacionStrip` dashboard-scoped (move from App.tsx:48 to dashboard); `SyncBanner` and `AlertasPanel` are dashboard sections. Nothing in App.tsx besides `<StatusBar />` (status of `api-status`, F2.3) — DEC-UPD-12.

---

## 7. Ready for proposal

**YES** — the change is well-bounded:

- Backend is COMPLETE (21 endpoints shipped; see §1.8 table).
- Frontend scope is well-defined (5 new feature folders + 1 dashboard orchestrator).
- Hooks pattern is established (`useOcupacion`, `useIngresoActivo`, `useTarifasVigentes` are the templates).
- i18n infrastructure is in place (`facturacion.json` + `sync.json` locales exist, just sparse).
- No DB migration; no audit-first risk; no schema change; no DELETE concern.
- Chained PR plan exists (PR1-PR6, §4.5).
- All open questions (§6) have a recommended default the orchestrator can confirm or override.

**Next phase**: `sdd-propose` — formal proposal capturing the IA (panel hierarchy + drawer flows + chained PR plan) and the rollback strategy.

---

## Appendix A — Files that exist today, mapped to plan.md citations

```
apps/electron-sucursal/src/renderer/App.tsx:54-86       ← F3.3 routes
apps/electron-sucursal/src/renderer/components/ProtectedRoute.tsx        ← F3.1 auth guard
apps/electron-sucursal/src/renderer/components/OcupacionStrip.tsx         ← F4.3 (currently global at App.tsx:48)
apps/electron-sucursal/src/features/auth/pages/Login.tsx                 ← F3.1
apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx             ← F3.3 (the hub, currently thin)
apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx             ← F3.3
apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx           ← F3.3 (placeholder for F10.2)
apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx ← F3.3
apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts        ← F3.3
apps/electron-sucursal/src/features/operacion/pages/Principal.tsx         ← F6.1 (stub; not mounted)
apps/electron-sucursal/src/features/operacion/components/{PlacaInput,ForzarIngresoModal,TiqueteModal}.tsx ← F6.1
apps/electron-sucursal/src/features/operacion/hooks/useOcupacion.ts       ← F4.3
apps/electron-sucursal/src/features/operacion/hooks/useIngresoActivo.ts  ← F6.1
apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts  ← F4.1
apps/electron-sucursal/src/features/catalogos/hooks/useTarifasVigentes.ts ← F4.2
apps/electron-sucursal/src/features/catalogos/components/TarifaBadge.tsx ← F4.2
apps/ui-kit/src/hooks/useAuth.ts                                          ← F3.1
apps/ui-kit/src/hooks/useAuth.test.ts                                     ← F3.1
```

## Appendix B — Backend endpoints (cross-reference table)

| Endpoint | Backend file | HU | Method | Authz |
|---|---|---|---|---|
| `/api/v1/auth/login` | `auth.py:148` | F3.1 | POST | public |
| `/api/v1/auth/refresh` | `auth.py:310` | F3.1 | POST | refresh-token |
| `/api/v1/auth/logout` | `auth.py:352` | F3.1 | POST | bearer |
| `/api/v1/auth/me` | `auth.py:419` | F3.1 | GET | bearer |
| `/api/v1/catalogos/tipos-vehiculo` | `catalogos.py:96` | F4.1 | GET | bearer |
| `/api/v1/empresa/tarifas-sucursal` | `empresa.py:176` | F4.2 | GET | bearer |
| `/api/v1/operacion/ocupacion` | `operacion.py:821` | F4.3, F1.5 | GET | operador-,admin- |
| `/api/v1/operacion/ingresos` | `operacion.py:116, 612` | F6.1, F1.6 | GET, POST | operador-,admin- |
| `/api/v1/operacion/ingresos/{uuid}` | `operacion.py:548` | F6.1 | GET | operador-,admin- |
| `/api/v1/operacion/ingresos/{uuid}/estado` | `operacion.py:565` | F6.1 | GET | operador-,admin- |
| `/api/v1/operacion/cotizar` | `operacion.py:647` | F7.1, F1.8 | GET | operador-,admin- |
| `/api/v1/operacion/salidas` | `operacion.py:322` | F7.2, F1.7 | POST | operador-,admin- |
| `/api/v1/operacion/salidas/mensualidad` | (TBD — verify in `operacion.py`) | F7.2 | POST | operador-,admin- |
| `/api/v1/facturacion/factura` | `facturacion.py:190` | F8.1, F1.9 | POST | operador-,admin- |
| `/api/v1/facturacion/factura-pagos` | `facturacion.py:410` | F8.1, F1.9 | POST | operador-,admin- |
| `/api/v1/facturacion/factura-electronica` | `facturacion.py:514` | F8.1, F1.10 | POST | operador-,admin- |
| `/api/v1/facturacion/factura-electronica/{uuid}` | `facturacion.py:723` | F8.2, F1.10 | GET | operador-,admin- |
| `/api/v1/facturacion/factura-electronica/{uuid}/reintentar` | `facturacion.py:844` | F8.2, F1.10 | POST | operador-,admin- |
| `/api/v1/workflows/reimpresion-ticket` | `workflows.py:111` + `workflows_reimpresion.py:84` | F8.3, F1.11 | POST, GET (list) | operador-,admin- + reimprimir_ticket |
| `/api/v1/workflows/reimpresion-ticket/{uuid}/anular` | `workflows_reimpresion.py:247` | F8.3, F1.11 | POST | operador-,admin- + reimprimir_ticket |
| `/api/v1/workflows/alerta` | `workflows.py:135` | F11.2, F1.1 | GET | operador-,admin- + registrar_alerta |
| `/api/v1/clientes/venta-suscripcion` | `clientes_venta.py:64` | F9.1, F1.12 | POST | operador-,admin- |
| `/api/v1/clientes/...` (list) | `clientes.py:40` | F9.2 | GET | operador-,admin- |
| `/api/v1/caja/arqueo` | `caja_arqueo.py:67` | F10.1-F10.3, F1.13 | POST | operador-,admin- + realizar_arqueo |
| `/api/v1/caja/arqueo/resumen` | `caja_arqueo.py:337` | F10.3, F1.13 | GET | operador-,admin- + realizar_arqueo |
| `/api/v1/caja-sesion/sesiones` | `caja_sesion.py:81` | F3.3, F1.3 | POST | operador-,admin- + abrir_cerrar_caja |
| `/api/v1/caja-sesion/sesion/{uuid}/cerrar` | `caja_sesion.py:137` | F3.3, F1.13 | PUT | operador-,admin- + abrir_cerrar_caja |
| `/api/v1/caja-sesion/sesion/me` | `caja_sesion.py:227` | F3.3, F1.13 | GET | operador-,admin- + abrir_cerrar_caja |
| `/api/v1/caja-sesion/arqueos/{uuid}/diferencias` | `caja_sesion.py:167` | F10.x, F1.13 | GET | operador-,admin- |
| `/api/v1/sync/estado` | `sync_estado.py:57` | F11.1, F1.14 | GET | operador-,admin- + audit_read |

> **Note**: `clientes.py:40` exposes `prefix="/clientes"` — the listing for F9.2 uses the standard `make_router` factory mounted resources (similar to `workflows.py:111-142`); verify the exact GET endpoint in `clientes.py` at apply time.

## Appendix C — i18n keys available today

| Locale | Keys present | Keys needed |
|---|---|---|
| `caja.json` | abrir, cerrar, montoInicial/Final, diferencia, arqueo, movimiento, ingreso, egreso, motivo, abrirTurno, valorInicialEfectivo/Datafono, observaciones, sesionYaAbierta/Cerrada, irAlTurno, cerrarTurno, turnoCerradoExito, confirmarCierre, turnoActivo | turnoVigenteLabel, arqueoParcial, cierreDiario |
| `operacion.json` | ingreso, salida, placa, tipo, tarifa, total, registrar, imprimir, anular, confirmar, placa_formato_invalido, ocupacion_*, cupo_no_configurado, tiquete_entrada_*, ingreso_*, motivo_forzado_*, tarifa_vigente_*, subscripcion_inactiva_*, network_error, error_* | cotizar.*, salidaFlow.*, salidaMensualidad.*, suscripcionProximaVencer.* |
| `facturacion.json` | (sparse — empty-ish) | pago.*, vuelto, voucher, feConDatos, nitLabel, dvLabel, facturaConsumidorFinal, reintentarFE, facturacionError.* |
| `sync.json` | (sparse — empty-ish) | banner.*, lagVerde/Amarillo/Rojo, sinConexionApiLocal |
| `common.json` | (presumed common) | loading, error, retry |
| `errors.json` | (presumed common errors) | network, server, unknown |
| `auth.json` | (F3.1 keys) | — |

> **i18n is NOT a blocker** — keys can be added per PR as panels are introduced.

---

**End of exploration. Artifact persisted to Engram as `sdd/operador-dashboard-hub/explore` (architecture) and `openspec/changes/operador-dashboard-hub/exploration.md` (hybrid mode). Next phase: `sdd-propose`.**
