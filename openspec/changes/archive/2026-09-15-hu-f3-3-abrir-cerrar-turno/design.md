# Design — HU-F3.3 Abrir y cerrar turno (caja-sesion con valor_inicial_efectivo/datafono + arqueo inline placeholder + redirect según sesión activa)

> **Change**: `hu-f3-3-abrir-cerrar-turno` · **Folder**: `openspec/changes/hu-f3-3-abrir-cerrar-turno/`
> **Phase**: design (sdd-design) · **Status**: ready for `sdd-tasks`
> **HU ID**: HU-F3.3 (Fase 3 — tercera HU; Autenticación y turno de caja, primer consumer transversal de `caja-sesion`)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-3-turno` (HEAD `fde9850`, F3.1 archivado 2026-09-15 con 7 REQ-OPS-106..112; F3.2 archivado 2026-09-15 con 6 REQ-OPS-113..118; F3.3 commitea sobre la misma rama per `pending.md:6`) · **PR target**: `origin/dev`
> **Inputs**: `proposal.md` (~843 LOC, 16 secciones, 12 DEC-F3.3-01..12, DEC-F3.3-08 + DEC-F3.3-12 verdict DELTA, 6 new REQ-OPS-119..124 user-facing), `specs/operations/spec.md` (paralelo — materializado con 6 REQ-OPS-119..124 + 4 acceptance scenarios AC-1..AC-5), `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/design.md` (precedente verbatim ~1890 LOC — layout canónico clonado 1:1 con adaptación al scope caja-sesion), `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/design.md` (precedente F3.1 — Container/Presentational split + Zod verbatim pattern), `apps/electron-sucursal/src/features/auth/{pages/Login.tsx:1-90 (container F3.1+F3.2 — Login recibe MODIFY F3.3 T5 para ?closed=true detection), hooks/useCountdown.ts:1-67 (F3.2 shipped — F3.3 NO modifica; CONTAINER pattern reusable)}`, `apps/ui-kit/src/{fetch/parkosFetch.ts (F2.2+F3.2 — Idempotency-Key auto + handle401 Mutex), store/authStore.ts (F2.2 — clear() borra tokens vía IPC), hooks/useAuth.ts (F2.2+F3.2 — refreshInterval 50min verbatim)}`, `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:73-243 (POST /sesiones + PUT /sesion/{uuid}/cerrar + GET /sesion/me — routes ya shipped F1.3+F1.13 READ ONLY)`, `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:188-356 (open_session + close_session_with_log + SesionAlreadyActive mapping 23505 → 409 + SessionNotFoundError 351-352 → 404)`, `docs/01-requisitos/no-funcionales.md:126 (RNF-022 WCAG 2.1 AA)`, `plan.md:1327-1352 (HU-F3.3 verbatim, 260 LOC, 5 tareas atómicas T1..T5)`, `plan.md:418 (DEC-SUC-03 — "Refresh transparente cada 50 minutos y antes de escrituras críticas")`, `pending.md §1 row 3 (F3.3 = 260 LOC, depende F3.1)`, `pending.md §5 (forward hooks F4/F5/F6/F7/F8/F10/F11/F12 — F3.3 es gating transversal)`, `openspec/changes/hu-f3-3-abrir-cerrar-turno/exploration.md` (input de explore phase — Engram #1684, ~580 LOC, 18 secciones, 10 DEC-F3.3-01..10, 8 riesgos R1..R8, 6 acceptance gates G1..G6, 5 atomic tasks T1..T5, pre-flight 10/10 PASS + 0 KNOWN-MISSING).
> **Language**: español neutro profesional · **Conventional commits**: `feat(caja)` / `feat(auth)` / `test(electron)` — sin Co-authored-by.

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F3.3 |
| **Fase** | 3 (Autenticación y turno de caja — tercera HU; gating transversal para F4.x+) |
| **Change name** | `hu-f3-3-abrir-cerrar-turno` |
| **Folder** | `openspec/changes/hu-f3-3-abrir-cerrar-turno/` |
| **State** | design ready |
| **Branch** | `feat/fase-3-turno` (HEAD `fde9850`) |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | sdd-explore + sdd-propose + sdd-spec (paralelo) |
| **Próximo phase** | sdd-tasks |
| **DEC ratified** | 12 DEC-F3.3-01..12 (DEC-F3.3-08 + DEC-F3.3-12 verdict DELTA — F3.3 ES user-facing) |
| **REQ-OPS range** | REQ-OPS-119..124 (6 new requirements, continuación monotónica post F3.2 REQ-OPS-118) |
| **LOC target** | ~530 producción + ~250 tests + ~20 configs/JSDoc = **~800 LOC total** |
| **Conventional commits** | `feat(caja)` / `feat(auth)` / `test(electron)` — sin Co-authored-by |

---

## 1. Contexto técnico

### 1.1 AS-IS verificado (estado actual F3.1 + F3.2 archivados)

F3.1 archivado 2026-09-15 entrega `POST /auth/login` + `useAuth` SWR + `LoginForm` container/presentational + RHF+Zod + i18n namespace `auth.json` (15 keys) + 7 REQ-OPS-106..112. F3.2 archivado 2026-09-15 entrega `useCountdown` hook reusable + lockout visible + refresh transparente 50min (`REFRESH_INTERVAL_MS = 50 * 60 * 1000` heredado de DEC-SUC-03 plan.md:418) + pre-flight gate en `parkosFetch.ts` (`PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/`) + 6 REQ-OPS-113..118. La `apps/electron-sucursal/src/renderer/App.tsx:27-30` tiene `<Route path="/" element={null} />` + `<Route path="/login" element={<Login />} />`. **Ningún flujo operativo puede correr sin turno abierto** — el operador autenticado llega al Dashboard `/` y encuentra una pantalla vacía.

F3.3 entrega el flujo end-to-end de apertura y cierre de turno (`caja-sesion`) sin tocar backend (ya shipped por F1.3 + F1.13). Los hooks/SWR patterns, primitives (shadcn/ui F2.1), i18n (F2.1 DEC-ELEC-06 un namespace por bounded context → namespace `caja`), auth-store (`useAuthStore` F2.2) y `parkosFetch` (F2.2+F3.2) están listos para consumo.

**Inputs verificados**:

- `apps/electron-sucursal/src/features/auth/pages/Login.tsx:1-90` — container F3.1+F3.2 (RHF + Zod + useAuth + setTokens + postLogin + errorState + countdown reset). F3.3 T5 MODIFICA para detectar `?closed=true` query param.
- `apps/electron-sucursal/src/features/auth/hooks/useCountdown.ts:1-67` — F3.2 hook shipped (`Date.now()` baseline + `setInterval(1000)` + cleanup + onComplete callback). F3.3 NO lo modifica; sí lo referencia como patrón container/presentational + reuse cross-feature.
- `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` — 15 keys + 5 validation sub-keys (F3.1 + F3.2). F3.3 NO agrega keys aquí — agrega a `caja.json`.
- `apps/electron-sucursal/src/renderer/i18n/locales/caja.json:1-12` — 10 keys pre-existentes (F2.1). F3.3 agrega 12 keys turno (DEC-F3.3-06 namespace pre-existente).
- `apps/electron-sucursal/src/renderer/App.tsx:1-40` — F3.1+F3.2 router placeholder con `<Route path="/" element={null} />`. F3.3 T4 MODIFICA para registrar rutas `/`, `/caja/abrir-turno`, `/caja/cerrar-turno`.
- `apps/ui-kit/src/store/authStore.ts` — F2.2 primitive (`accessToken` + `refreshToken` + `expiresAt` + `setTokens` atómico + `clear()` borra tokens vía IPC `bridge.authStore.delete` + `refreshAccessToken` Mutex singleton). F3.3 consume `clear()` post-cierre (DEC-F3.3-03).
- `apps/ui-kit/src/fetch/parkosFetch.ts` — F2.2+F3.2 primitive (Idempotency-Key auto SHA-256 para POST `/caja-sesion/*` skip `/auth/login`; `handle401` Mutex refresh-once). F3.3 consume; **NO modifica** `PRE_FLIGHT_PATHS` per DEC-F3.3-10 — `/caja-sesion/*` NO es critical-path DEC-SUC-03.
- `apps/ui-kit/src/hooks/useAuth.ts` — F2.2+F3.2 (`refreshInterval: REFRESH_INTERVAL_MS = 50min`). F3.3 NO modifica; consume `useAuth().user.sucursal.uuid` + `useAuth().user.id`.
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:73-243` — READ ONLY consumer anchors: `POST /sesiones` (open), `PUT /sesion/{uuid}/cerrar` (close), `GET /sesion/me` (active check). Ya shipped F1.3 + F1.13.
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:188-356` — READ ONLY: `open_session` + `close_session_with_log` + `SesionAlreadyActive` mapping 23505 → 409 + `SessionNotFoundError` 351-352 → 404.

### 1.2 Gap UX que F3.3 cierra

Cuatro pain points UX rompen la promesa "kiosko desatendido" del `plan.md:418` (DEC-SUC-03):

1. **Pain #1 — Sin turno, no hay operación**: operador termina login, ve Dashboard `/` con `element={null}` (App.tsx:28). No sabe qué hacer. F3.3 entrega `<Dashboard>` con redirect automático según sesión activa.
2. **Pain #2 — 409 `sesion_already_active` genérico**: la partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023) garantiza BD-level rejection. F3.3 frontend mapea 409 a UX "Ya tenés un turno abierto" + botón "Ir al turno".
3. **Pain #3 — CerrarTurno sin logout produce estado inconsistente**: si operador cierra turno pero queda logged-in, kiosko queda weird. F3.3 implementa `useAuthStore.clear()` post-200 (logout implícito per DEC-F3.3-03).
4. **Pain #4 — Arqueo completo bloquea F3.3 indefinitely**: F10.x entrega arqueo completo con tolerancia + justificación + alerta. F3.3 entrega `CerrarTurno` placeholder con form simple de `valor_final_*` + `PUT /sesion/{uuid}/cerrar` per DEC-F3.3-06.

### 1.3 TO-BE resumido (entregables end-to-end verificables)

1. **`useSesionActiva()` hook SWR** (T1 ~80 LOC + ~60 tests): signature `{ sesion, isLoading, error, refresh }` con SWR key `accessToken ? '/caja-sesion/sesion/me' : null`, `refreshInterval: REFRESH_INTERVAL_MS = 50min` (F3.2 heredado), `dedupingInterval: 10s`, `shouldRetryOnError` excl 404, `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event (F2.2 invariant preserved).
2. **`sesionActivaApi` typed wrappers** (T1 ~25 LOC + ~40 tests): `getSesionActiva(): Promise<SesionRead|null>` (404 → null), `abrirSesion(payload: SesionCreate): Promise<SesionRead>` (POST + 409 mapping `SesionAlreadyActiveError extends ParkosHttpError`), `cerrarSesion(uuid, payload): Promise<SesionRead>` (PUT + 404 mapping `SesionAlreadyClosedError`).
3. **`AbrirTurno` page + `AbrirTurnoForm`** (T2 ~120 LOC + ~80 tests): container con RHF+Zod (`valor_inicial_efectivo: z.number().min(0)`, `valor_inicial_datafono: z.number().min(0)`, `observaciones: z.string().optional()`) + presentational con `<Input type="number" inputMode="decimal" step="0.01">` (DEC-F3.3-02 teclado numérico mobile) + submit POST `/caja-sesion/sesiones`. 409 → mensaje "ya tenés un turno abierto" + botón "Ir al turno".
4. **`CerrarTurno` page + `CerrarTurnoForm` placeholder** (T3 ~100 LOC + ~60 tests): container con RHF+Zod (`valor_final_efectivo/datafono ≥0` + `observaciones_cierre` opcional) + presentational con resumen del turno (timestamp apertura + valores iniciales via `formatCOP`) + submit PUT `/caja-sesion/sesion/{uuid}/cerrar`. 200 → `useAuthStore.clear()` + `navigate('/login?closed=true')`. 404 → "ya está cerrada" + redirect login.
5. **`Dashboard` page + `TurnoActivoPanel` organism** (T4 ~60 LOC + ~50 tests): Dashboard consume `useSesionActiva()` y decide redirect según estado (replace para evitar back-button infinite loop). `TurnoActivoPanel` renderiza resumen (uuid + timestamp apertura via `formatDistanceToNow` + valores iniciales via `formatCOP` + observaciones opcional) + botón "Cerrar turno".
6. **`Login` `?closed=true` detection** (T5 ~10 LOC + ~10 tests): MODIFY `Login.tsx` para detectar `useLocation().search.includes('closed=true')` + renderizar `<p role="status" aria-live="polite" data-testid="turno-cerrado-exito">{t('caja.turnoCerradoExito')}</p>` arriba del form (sin reemplazar form, F3.1 F3.2 intactos).
7. **i18n keys turno en `caja.json`**: 12 keys agregadas: `abrirTurno`, `cerrarTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `valorFinalEfectivo`, `valorFinalDatafono`, `observaciones`, `sesionYaAbierta`, `sesionYaCerrada`, `turnoCerradoExito`, `confirmarCierre`, `irAlTurno`, `turnoActivo`.

### 1.4 Hard constraints (mirrored from `plan.md:1327-1352` verbatim)

- `POST /caja-sesion/sesiones` con `valor_inicial_efectivo` + `valor_inicial_datafono` (decimales ≥0). Si ya hay sesión abierta para el usuario → 409 `sesion_ya_abierta` con mensaje claro.
- `GET /caja-sesion/sesion/me` resuelve dashboard con resumen del turno cuando hay sesión abierta. NO redirige a AbrirTurno.
- Cierre de turno con `tipo_arqueo='cierre_turno'` + `PUT /caja-sesion/sesion/{uuid}/cerrar` → 200 + redirect a login con `?closed=true`.
- Validación Zod: `z.object({ valor_inicial_efectivo: z.number().min(0), valor_inicial_datafono: z.number().min(0), observaciones: z.string().optional() })`.
- Componentes: `AbrirTurno` (page, `inputMode="decimal"`), `CerrarTurno` (page, placeholder), `useSesionActiva` (hook SWR), `TurnoActivoPanel` (organism), `Dashboard` (container).
- e2e: `e2e/caja/turno.spec.ts` — abrir, intentar un segundo → 409, cerrar, ver resumen, axe-core A1.

### 1.5 No-objetivos (cross-ref proposal §3.2 / exploration §17)

- Backend cambios — endpoints + permission `abrir_cerrar_caja` (GAP-BE-05 fix site #2) + partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023) + trigger `ls_session_guard` ya shipped F1.3 + F1.13. F3.3 NO modifica backend.
- Arqueo completo (Fase 10) — `CerrarTurno.tsx` es placeholder. NO consume `POST /caja/arqueo` (Fase 10 HU-F10.x entrega flujo completo con tolerancia + justificación + alerta `descuadre_critico`) per DEC-F3.3-06.
- Sync de sesion cerrada — `prod.sesion` [L-S] ya está en `sync_catalog` branch→cloud per F1.13 §6.5 verified. F3.3 NO toca sync catalog.
- Reverso de pagos — `factura_pagos` [A] con `tipo_movimiento = 'pago | reverso'` — fuera scope F3.3 (forward F5.x).
- AuthGuard component — F3.3 NO crea `<AuthGuard>` que envuelve `<Routes>` excepto `/login`. Forward hook F3.x+ intercepta `parkos:auth:cleared` → `navigate('/login?next=...')`.
- Logout button UI explícito — F3.3 hace `useAuthStore.clear()` post-cierre de turno (logout implícito per DEC-F3.3-03).
- Multi-sucursal selector — JWT ya pinea sucursal (single-branch kiosko per DEC-F3.1-04). F3.3 lee `useAuth().user.sucursal.uuid` directamente.
- Edición post-apertura de valores iniciales — `SesionUpdate` Pydantic schema permite late corrections (caja_sesion.py:218-238), pero F3.3 NO expone UI — read-only en CerrarTurno y TurnoActivoPanel.
- `useCountdown` para "tiempo restante de turno" — F3.3 muestra `timestamp_apertura` formateado (`formatDistanceToNow` con `date-fns`). NO countdown regresivo.
- Toast notifications post-cierre — `?closed=true` + `<p role="status">` es suficiente UX para F3.3. Forward F11.x usa shadcn Toast component.
- Permisos granulares por acción — backend ya emite 403 si `permisos[]` no incluye `abrir_cerrar_caja`. F3.3 NO agrega client-side permission gating (Defense in depth XR6 — backend source of truth).
- Idempotency-Key manual en apertura — `parkosFetch` ya genera SHA-256 de `method|path|body` para POST `/caja-sesion/*` (skip `/auth/login` only). F3.3 NO requiere override.
- Suscripciones + ingresos recurrentes — CU-06 fuera Fase 3 (F9.x).
- Reportes CU-09 — F12.x consume `useSesionActiva` post-F3.3.
- Extensión de `PRE_FLIGHT_PATHS` — F3.3 NO modifica `parkosFetch.ts`. `/caja-sesion/*` no es critical-path per DEC-F3.3-10 + DEC-SUC-03.
- A11y biblioteca externa — axe-core via `@axe-core/playwright` F2.1 baseline. NO nueva dep.

---

## 2. Arquitectura propuesta

### 2.1 Tree delta (target)

```
apps/electron-sucursal/
├── src/
│   ├── features/
│   │   ├── auth/                                   ← F3.1+F3.2 baseline (F3.3 MODIFY T5)
│   │   │   └── pages/
│   │   │       └── Login.tsx                       ← MODIFY (+5 LOC — detecta ?closed=true + <p role="status">)
│   │   └── caja/                                   ← NEW feature folder T1+T2+T3+T4
│   │       ├── api/
│   │       │   ├── sesionActivaApi.ts              ← NEW (~25 LOC — getSesionActiva + abrirSesion + cerrarSesion + typed errors)
│   │       │   ├── sesionActivaApi.test.ts         ← NEW (~40 LOC — U5..U8)
│   │       │   └── schemas/
│   │       │       └── turnoSchema.ts              ← NEW (~10 LOC — Zod abrir/cerrar schemas)
│   │       ├── hooks/
│   │       │   ├── useSesionActiva.ts              ← NEW (~40 LOC — SWR key null + refresh 50min + 404 null + 401 clear)
│   │       │   └── useSesionActiva.test.ts         ← NEW (~40 LOC — U1..U4)
│   │       ├── components/
│   │       │   ├── AbrirTurnoForm.tsx              ← NEW (~50 LOC presentational)
│   │       │   ├── CerrarTurnoForm.tsx             ← NEW (~40 LOC presentational placeholder)
│   │       │   ├── TurnoActivoPanel.tsx            ← NEW (~30 LOC organism)
│   │       │   └── TurnoActivoPanel.test.tsx       ← NEW (~25 LOC snapshot/render)
│   │       └── pages/
│   │           ├── AbrirTurno.tsx                  ← NEW (~70 LOC container)
│   │           ├── AbrirTurno.test.tsx             ← NEW (~50 LOC — U9..U11)
│   │           ├── CerrarTurno.tsx                 ← NEW (~60 LOC container)
│   │           ├── CerrarTurno.test.tsx            ← NEW (~40 LOC — U12..U14)
│   │           ├── Dashboard.tsx                   ← NEW (~30 LOC container redirect)
│   │           └── Dashboard.test.tsx              ← NEW (~25 LOC — U15..U17)
│   └── renderer/
│       ├── App.tsx                                 ← MODIFY (+10 LOC — registra rutas /, /caja/abrir-turno, /caja/cerrar-turno)
│       └── i18n/locales/caja.json                  ← MODIFY (+12 keys)
└── e2e/
    └── caja/
        └── turno.spec.ts                           ← NEW (~80 LOC — E1..E3 + A1 axe-core SKIPPED-env per Sandbox F.6)

apps/ui-kit/                                         ← NO modificar (F3.3 consume primitives F2.2+F3.2)
```

**MODIFY total**: 3 archivos (`Login.tsx` + `App.tsx` + `caja.json`) = ~25 LOC delta production + 12 keys i18n.
**NEW total**: 14 archivos (~530 LOC production + ~250 LOC tests + 1 e2e).
**Total impact**: 17 archivos = ~800 LOC total (production + tests + e2e + configs).

### 2.2 Data flow + SWR/Zustand boundaries

```
┌─────────────────── Renderer (React 18 + SWR + Zustand + RHF + Zod + shadcn/ui) ─────────────────┐
│                                                                                                │
│   <App> (F3.1/F3.2, MODIFY F3.3 T4 — registra 3 rutas caja)                                   │
│   ├── <StatusBar />                                                                            │
│   └── <main>                                                                                   │
│       └── <Routes>                                                                             │
│           ├── <Route path="/" element={<Dashboard />}>            ◄── NEW F3.3 T4              │
│           ├── <Route path="/login" element={<LoginPage />}>       (F3.1+F3.2 + MODIFY F3.3 T5)│
│           ├── <Route path="/caja/abrir-turno"   element={<AbrirTurno />} />   ◄── NEW T2        │
│           ├── <Route path="/caja/cerrar-turno"  element={<CerrarTurno />} />  ◄── NEW T3        │
│           └── <Route path="*" element={<NotFound />} />                                          │
│                                                                                                │
│   <Dashboard>  (NEW container T4)                                                              │
│   ├── useSesionActiva() → { sesion, isLoading, error, refresh }                                │
│   ├── useEffect([sesion, isLoading, error])                                                    │
│   │     → if (!sesion && !isLoading && !error) navigate('/caja/abrir-turno', { replace: true }) │
│   ├── if (sesion) → render <TurnoActivoPanel sesion onCerrarClick={() => navigate(...)} />     │
│   └── if (error && status !== 404) → <Alert destructive> + <Button onClick={refresh}>Retry     │
│                                                                                                │
│   <AbrirTurno>  (NEW container T2)                                                             │
│   ├── useAuth() → user.sucursal.uuid + user.id                                                 │
│   ├── useForm<{valor_inicial_efectivo, valor_inicial_datafono, observaciones}> + zodResolver   │
│   ├── onSubmit(data) → sesionActivaApi.abrirSesion(payload)                                    │
│   │     → 200 → navigate('/') + useSesionActiva SWR re-fetch                                   │
│   │     → 409 SesionAlreadyActiveError → <FormMessage role="alert"> + <Button>Ir al turno</>    │
│   └── <AbrirTurnoForm form onSubmit isSubmitting error />                                      │
│                                                                                                │
│   <CerrarTurno>  (NEW container T3)                                                            │
│   ├── useSesionActiva() → sesion.uuid                                                          │
│   ├── useForm<{valor_final_efectivo, valor_final_datafono, observaciones_cierre}> + zodResolver │
│   ├── onSubmit(data) → sesionActivaApi.cerrarSesion(sesion.uuid, payload)                      │
│   │     → 200 → useAuthStore.clear() + dispatchEvent('parkos:auth:cleared') +                   │
│   │              navigate('/login?closed=true', { replace: true })                             │
│   │     → 404 SesionAlreadyClosedError → <FormMessage> + navigate('/login')                    │
│   └── <CerrarTurnoForm form onSubmit isSubmitting error sesion onCancel={navigate('/')} />     │
│                                                                                                │
│   <Login>  (F3.1+F3.2 MODIFY F3.3 T5)                                                          │
│   ├── useLocation() → search.includes('closed=true')                                           │
│   ├── {showClosedNotice && <p role="status" aria-live="polite" data-testid="turno-cerrado-exito">│
│   │                              {t('caja.turnoCerradoExito')}</p>}                              │
│   └── <LoginForm form onSubmit isSubmitting error onLockoutExpired />                          │
│                                                                                                │
└────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                     │ parkosFetch (F2.2 + F3.2 Idempotency-Key auto + handle401 Mutex)
                                     │ GET  /api/v1/caja-sesion/sesion/me       (SWR key '/caja-sesion/sesion/me')
                                     │ POST /api/v1/caja-sesion/sesiones        (200 OK + 409 sesion_already_active)
                                     │ PUT  /api/v1/caja-sesion/sesion/{uuid}/cerrar (200 OK + 404 sesion_not_found)
                                     ▼
┌─────────────────────────── Main Process (Electron 30, IPC bridge F2.2+F2.3) ────────────────────┐
│                                                                                                │
│   bridge.authStore.{get,set,delete} ──► electron-store (persist JWT)                          │
│                                                                                                │
└────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                     │ HTTPS + cookie httpOnly (F2.2+F3.1 invariant preserved)
                                     ▼
┌────────────────────────── Backend FastAPI (HU-F1.3 + HU-F1.13 shipped) ─────────────────────────┐
│                                                                                                │
│   POST /api/v1/caja-sesion/sesiones                                                           │
│   ├── 200 OK ──► SesionRead{uuid, uuid_sucursal, uuid_usuario, valor_inicial_*,               │
│   │                timestamp_apertura, timestamp_cierre: null}                                │
│   └── 409 Conflict ──► SesionAlreadyActiveError (migration 0023 partial unique index)         │
│                                                                                                │
│   PUT /api/v1/caja-sesion/sesion/{uuid}/cerrar                                                │
│   ├── 200 OK ──► SesionRead{timestamp_cierre: NOW} + log_transaccional INSERT                 │
│   └── 404 Not Found ──► SessionNotFoundError (DEC-F3.3-07: REST semantics, NO 409)             │
│                                                                                                │
│   GET /api/v1/caja-sesion/sesion/me                                                           │
│   ├── 200 OK ──► SesionRead{uuid, valor_inicial_*, timestamp_apertura, ...}                   │
│   └── 404 Not Found ──► sesion_no_active (operador sin turno es estado válido)                │
│                                                                                                │
└────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                     │ useSesionActiva SWR + parkosFetch consume
                                     ▼
┌──────────────────────────── ui-kit (apps/ui-kit/src/) ─────────────────────────────────────────┐
│                                                                                                │
│   parkosFetch.ts  (F2.2+F3.2 READ-ONLY, F3.3 consume)                                          │
│   ├── Idempotency-Key auto SHA-256 (skip /auth/login only)                                    │
│   ├── handle401 Mutex refresh-once (DEC-FETCH-03 invariant preserved)                          │
│   └── PRE_FLIGHT_PATHS sin cambios (DEC-F3.3-10: /caja-sesion/* NO es critical-path)           │
│                                                                                                │
│   useAuth.ts  (F2.2+F3.2 READ-ONLY, F3.3 consume)                                             │
│   └── refreshInterval: REFRESH_INTERVAL_MS = 50min (DEC-F3.3-04 alinea con F3.2)              │
│                                                                                                │
│   authStore.ts  (F2.2 READ-ONLY, F3.3 consume)                                                 │
│   ├── accessToken / refreshToken / expiresAt (ISO 8601)                                       │
│   ├── setTokens(access, refresh, expiresIn) → atomic update                                    │
│   ├── clear() → all 3 → null                                                               │
│   └── refreshAccessToken() ──► Mutex singleton (F2.2 DEC-FETCH-03)                             │
│                                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Principios arquitectónicos

1. **Hook SWR reusable primero** (DEC-F3.3-04): `useSesionActiva(): { sesion, isLoading, error, refresh }` exportable cross-feature (F4.x+ consumers). Key null sin token + refresh 50min + dedupingInterval 10s + shouldRetryOnError excl 404 + onError 401 clear.
2. **Container/Presentational split preservado** (F3.1 DEC-F3.1-02): `<AbrirTurno>` container orquesta RHF+Zod+useAuth+useNavigate+sesionActivaApi; `<AbrirTurnoForm>` presentational recibe `{form, onSubmit, isSubmitting, error}` via props. Idéntico pattern F3.1 `Login` + `LoginForm`.
3. **`inputMode="decimal"` + `type="number"` + `step="0.01"`** (DEC-F3.3-02): teclado numérico mobile + WCAG 2.1 AA compliant. Backend NUMERIC(18,4) acepta hasta 4 decimales; UI kiosko limita a 2.
4. **`useAuthStore.clear()` post-cierre turno** (DEC-F3.3-03): logout implícito atómico post-200. Borra accessToken/refreshToken/expiresAt vía IPC `bridge.authStore.delete` per F2.2. Dispatch `parkos:auth:cleared` window event (forward hook AuthGuard F3.x+).
5. **Redirect `/` según sesión activa** (DEC-F3.3-05): Dashboard consume `useSesionActiva()` y decide atómicamente. `replace: true` previene back-button infinite loop. Skeleton durante `isLoading`.
6. **`CerrarTurno` placeholder** (DEC-F3.3-06): form simple `valor_final_*` + `observaciones_cierre`. NO consume `POST /caja/arqueo` (Fase 10 entrega flujo completo con tolerancia + justificación + alerta).
7. **404 vs 409 mapping en cierre** (DEC-F3.3-07): backend emite 404 `SessionNotFoundError` per REST semantics (NO 409). F3.3 frontend mapea 404 a UX "esta sesión ya está cerrada" + redirect login. Mismo efecto UX que 409 desde perspectiva operador.
8. **`?closed=true` query param** (DEC-F3.3-09): `<Login>` detecta `useLocation().search.includes('closed=true')` + renderiza `<p role="status" aria-live="polite">` arriba del form (sin reemplazar, F3.1 F3.2 intactos). WCAG 2.1 AA compliant (mismo pattern F3.2 countdown).
9. **i18n namespace `caja` consolidado** (DEC-F3.3-06): 10 keys pre-existentes (F2.1) + 12 keys turno nuevas. NO nuevo namespace. Un namespace por bounded context (F2.1 DEC-ELEC-06).
10. **No extensión de `PRE_FLIGHT_PATHS`** (DEC-F3.3-10): `/caja-sesion/*` NO es critical-path DEC-SUC-03. `handle401` retry-once cubre. YAGNI — F3.3 NO modifica `parkosFetch.ts`. Forward extensibility via DEC-F3.2-10 precedent.
11. **Defense in depth XR6** (cross-ref `operations/spec.md:3951`): F3.3 suma capa 4 contract (Zod local + backend Pydantic + 6 REQ-OPS-119..124) + capa 3 a11y (WCAG axe-core 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel + Login `?closed=true`). NO crea REQ-OPS-XR7 — F2.x NO-OP precedent verbatim NO aplica (F3.3 ES user-facing).
12. **Idempotency-Key automático preservado** (F2.2 invariant): `parkosFetch` ya genera SHA-256 de `method|path|body` para POST `/caja-sesion/*`. F3.3 NO requiere override.
13. **Mutex singleton preserved** (F2.2 DEC-FETCH-03 invariant): `useAuthStore.clear()` post-cierre turn NO toca Mutex `refreshAccessToken`. Forward `handle401` paths funcionan idéntico.
14. **Formato moneda colombiana** (DEC-F3.3-05 i18n): `formatCOP` helper con `Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 })`. Sin decimales para efectivo/datáfono kiosko (DB persiste NUMERIC(18,4)).
15. **`formatDistanceToNow` para timestamp legible** (DEC-F3.3-05): kiosko UX legible "hace 2 horas" en vez de timestamp ISO crudo. `date-fns/locale/es` para es-CO.

---

## 3. Atomic tasks — diseño detallado (T1..T5)

### T1 — `useSesionActiva` SWR hook + `sesionActivaApi` typed wrappers (~80 prod + ~60 tests = ~140 LOC)

**Propósito**: Proveer el hook reusable para consultar sesión activa y los wrappers typed para abrir/cerrar turno. F3.3 primer consumer; F4.x+ (catálogos, facturación, ingreso/salida/cobro/FE/suscripciones, arqueos completos, reportería) consumen `useSesionActiva` para scoped queries.

**Files**:
- `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts` (NEW ~25 LOC)
- `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.test.ts` (NEW ~40 LOC — U5..U8)
- `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` (NEW ~40 LOC)
- `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.test.ts` (NEW ~40 LOC — U1..U4)

**Acceptance criteria**:
- U1: SWR key null sin token → `sesion: null, isLoading: false, error: undefined` (no fetcher call).
- U2: SWR fetch OK con sesión activa → `sesion: SesionRead` poblado.
- U3: SWR 404 → `sesion: null, error: undefined` (operador sin turno es estado válido).
- U4: SWR 401 → `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')`.
- U5: `getSesionActiva()` 200 → `SesionRead`.
- U6: `getSesionActiva()` 404 → `null` (NO lanza error).
- U7: `abrirSesion()` 409 → throw `SesionAlreadyActiveError(status=409, code='sesion_already_active')`.
- U8: `cerrarSesion()` 200 OK → `SesionRead`.

**Decisiones clave**: SWR `refreshInterval: REFRESH_INTERVAL_MS = 50min` (F3.2 DEC-SUC-03 verbatim), `dedupingInterval: 10s` evita refetch simultáneo (Dashboard + CerrarTurno consumen en paralelo), `shouldRetryOnError: (err) => err?.status !== 404`. `SesionAlreadyActiveError` y `SesionAlreadyClosedError` extienden `ParkosHttpError` de ui-kit. Types `SesionRead`, `SesionCreate`, `SesionCerrarRequest` derivados de backend Pydantic schemas (F1.3 + F1.13 READ ONLY).

**Precedentes**: F3.1 `useAuth` (F2.2 baseline) + F3.2 REQ-OPS-117 (refresh 50min verbatim).

### T2 — `AbrirTurno` page + `AbrirTurnoForm` (~100 prod + ~80 tests = ~180 LOC)

**Propósito**: Formulario de apertura de turno con 3 campos decimales (valor inicial efectivo + datáfono + observaciones opcionales). Submit POST `/caja-sesion/sesiones`. 409 mapeado a UX "ya tenés un turno abierto" + botón "Ir al turno".

**Files**:
- `apps/electron-sucursal/src/features/caja/api/schemas/turnoSchema.ts` (NEW ~10 LOC — Zod schemas abrir/cerrar compartidos)
- `apps/electron-sucursal/src/features/caja/components/AbrirTurnoForm.tsx` (NEW ~50 LOC presentational)
- `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx` (NEW ~70 LOC container)
- `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.test.tsx` (NEW ~50 LOC — U9..U11)

**Acceptance criteria**:
- U9: Submit OK con `valor_inicial_efectivo: 50000`, `valor_inicial_datafono: 0`, `observaciones: 'Apertura'` → POST 200 → `navigate('/')`.
- U10: POST 409 `sesion_already_active` → `<FormMessage role="alert">Ya tenés un turno abierto</FormMessage>` + `<Button>Ir al turno</Button>`.
- U11: Validación Zod rechaza `valor_inicial_efectivo: -100` → `<FormMessage>` inline error → NO invoca `parkosFetch`.

**Decisiones clave**: Container lee `useAuth().user.sucursal.uuid` + `useAuth().user.id` y los envía como `uuid_sucursal` + `uuid_usuario` en el payload (single-branch kiosko per DEC-F3.1-04). Presentational recibe `{form, onSubmit, isSubmitting, error}` via props (F3.1 DEC-F3.1-02 pattern verbatim). `<Input type="number" inputMode="decimal" step="0.01">` DEC-F3.3-02 teclado numérico mobile + WCAG compliant. Zod schema verbatim plan.md:1338.

**Precedentes**: F3.1 `Login.tsx` + `LoginForm.tsx` container/presentational split verbatim.

### T3 — `CerrarTurno` page + `CerrarTurnoForm` placeholder + Login `?closed=true` detection (~100 prod + ~60 tests = ~160 LOC)

**Propósito**: Formulario placeholder de cierre de turno con 3 campos decimales (valor final efectivo + datáfono + observaciones_cierre opcionales). Submit PUT `/caja-sesion/sesion/{uuid}/cerrar`. 200 → `useAuthStore.clear()` + `navigate('/login?closed=true')`. 404 → "ya está cerrada" + redirect login. Adicionalmente MODIFICAR `<Login>` para detectar `?closed=true` y renderizar feedback `<p role="status">`.

**Files**:
- `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx` (NEW ~40 LOC presentational placeholder con resumen turno + form + Cancel button)
- `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` (NEW ~60 LOC container)
- `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.test.tsx` (NEW ~40 LOC — U12..U14)
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY +5 LOC — detecta `?closed=true` + render `<p role="status">`)
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (MODIFY +5 LOC — U18 Login detecta `?closed=true`)

**Acceptance criteria**:
- U12: Submit OK con `valor_final_efectivo: 75000`, `valor_final_datafono: 25000` → PUT 200 → `useAuthStore.clear()` spy called + `dispatchEvent('parkos:auth:cleared')` fires + `navigate('/login?closed=true', { replace: true })`.
- U13: PUT 404 `sesion_not_found` → `<FormMessage role="alert">Esta sesión ya está cerrada</FormMessage>` + `navigate('/login')`.
- U14: Cancel button → `navigate('/')` sin invocar `cerrarSesion`.
- U18: Login mount con `?closed=true` → `<p role="status" data-testid="turno-cerrado-exito">` visible arriba del form; sin `?closed=true` → NO visible.

**Decisiones clave**: Container lee `sesion.uuid` via `useSesionActiva()`. Atomico post-200: `useAuthStore.getState().clear()` + `dispatchEvent('parkos:auth:cleared')` + `navigate('/login?closed=true', { replace: true })`. `<CerrarTurnoForm>` lee `sesion` via props (presentational, no SWR). Resumen arriba del form: uuid + timestamp apertura (formatDistanceToNow) + valor inicial efectivo/datafono (formatCOP) + observaciones. Fase 10 entrega flujo completo con tolerancia + justificación + alerta.

**Precedentes**: F3.1 `Login` redirect post-cierre + F3.2 logout pattern (F2.2 `clear()`) + shadcn `<Form>` primitives F2.1.

### T4 — `Dashboard` page + `TurnoActivoPanel` organism + rutas en App.tsx (~40 prod + ~50 tests = ~90 LOC)

**Propósito**: Página `/` que consume `useSesionActiva()` y decide redirect según estado. Renderiza `<TurnoActivoPanel>` con resumen legible del turno abierto. Modificar `App.tsx` para registrar 3 rutas (`/`, `/caja/abrir-turno`, `/caja/cerrar-turno`).

**Files**:
- `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx` (NEW ~30 LOC organism)
- `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.test.tsx` (NEW ~25 LOC)
- `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (NEW ~30 LOC container redirect)
- `apps/electron-sucursal/src/features/caja/pages/Dashboard.test.tsx` (NEW ~25 LOC — U15..U17)
- `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY +10 LOC — registra rutas)

**Acceptance criteria**:
- U15: Operador sin sesión activa → `navigate('/caja/abrir-turno', { replace: true })` en primer render con `sesion === null && !isLoading && !error`.
- U16: Operador con sesión activa → renderiza `<TurnoActivoPanel>` con resumen + botón "Cerrar turno" → `navigate('/caja/cerrar-turno')`.
- U17: SWR 500 u otro error distinto a 404 → `<Alert variant="destructive">` + `<Button onClick={refresh}>Retry</Button>`.

**Decisiones clave**: Decision tree atómica en `useEffect([sesion, isLoading, error])` para evitar loops infinitos. Skeleton durante `isLoading` (NO flash de "sesión no iniciada"). `replace: true` previene back-button infinite loop. `TurnoActivoPanel` puramente presentational — recibe `sesion` + `onCerrarClick` via props. Heading `<CardTitle>` (shadcn → `<h3>` semántico) + contraste ≥4.5:1 via CSS tokens F2.1.

**Precedentes**: F3.1 `<Login>` redirect post-login transaccional pattern (DEC-F3.1-07) + shadcn Card primitives F2.1.

### T5 — e2e turno scenario + axe-core A1 (SKIPPED-env per Sandbox F.6) (~80 LOC e2e)

**Propósito**: Escenarios e2e completos del flujo abrir → 409 → cerrar → feedback post-cierre. axe-core A1 test para WCAG 2.1 AA compliance. **SKIPPED-env per Sandbox F.6** — npm 11.16.0 refuses `workspace:*` resolution (F2.1 + F2.2 + F2.3 + F3.1 + F3.2 archive precedent). Documentado como deviation D-env en verify-report.

**Files**:
- `apps/electron-sucursal/e2e/caja/turno.spec.ts` (NEW ~80 LOC — E1 + E2 + E3 + A1)

**Acceptance criteria**:
- E1: Login → redirect automático a `/caja/abrir-turno` → submit OK → redirect a `/` con `TurnoActivoPanel` visible.
- E2: Intentar POST `/caja-sesion/sesiones` con sesión ya abierta → 409 → mensaje "ya tenés un turno abierto" + botón "Ir al turno".
- E3: `navigate('/caja/cerrar-turno')` → submit OK → 200 → redirect a `/login?closed=true` con `<p role="status">` visible.
- A1: axe-core 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel + Login `?closed=true` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa`.

**Decisiones clave**: SKIPPED-env per F3.2 precedent — unit tests (vitest sobre hooks + components mockeando SWR + parkosFetch) cubren camino crítico. Verify-report documenta D-env deviation.

**Precedentes**: F3.2 `e2e/auth/lockout.spec.ts` (A1 axe-core pattern verbatim).

---

## 4. Componentes nuevos (atomic design placement)

### 4.1 Mapeo atomic design

| Componente | Tipo | Capa | Atomic placement | Path |
|---|---|---|---|---|
| `useSesionActiva` | Hook (logic) | Logic | Hooks layer (F3.1 verbatim) | `features/caja/hooks/useSesionActiva.ts` |
| `sesionActivaApi` | Service (data) | Data | API layer (F3.1 verbatim) | `features/caja/api/sesionActivaApi.ts` |
| `turnoSchema` | Schema (validation) | Data | Schemas co-located (F3.1 verbatim) | `features/caja/api/schemas/turnoSchema.ts` |
| `AbrirTurnoForm` | Presentational | Atoms/Molecules | Form molecule (shadcn `<Form>` wrap) | `features/caja/components/AbrirTurnoForm.tsx` |
| `CerrarTurnoForm` | Presentational | Molecules | Form molecule + Card summary | `features/caja/components/CerrarTurnoForm.tsx` |
| `TurnoActivoPanel` | Organism | Organisms | Card composition with shadcn Card | `features/caja/components/TurnoActivoPanel.tsx` |
| `AbrirTurno` | Page container | Pages | Container orchestrates RHF + parkosFetch + navigate | `features/caja/pages/AbrirTurno.tsx` |
| `CerrarTurno` | Page container | Pages | Container orchestrates RHF + parkosFetch + AuthStore.clear | `features/caja/pages/CerrarTurno.tsx` |
| `Dashboard` | Page container | Pages | Container orchestrates useSesionActiva + navigate | `features/caja/pages/Dashboard.tsx` |

### 4.2 `AbrirTurnoForm` props interface

```typescript
// apps/electron-sucursal/src/features/caja/components/AbrirTurnoForm.tsx (T2)
import type { UseFormReturn } from 'react-hook-form';
import type { AbrirTurnoInput } from '../api/schemas/turnoSchema';

export interface AbrirTurnoFormProps {
  form: UseFormReturn<AbrirTurnoInput>;
  onSubmit: (data: AbrirTurnoInput) => Promise<void>;
  isSubmitting: boolean;
  error: AbrirTurnoErrorState | null;
}

export type AbrirTurnoErrorState =
  | { kind: 'sesion_already_active' }
  | { kind: 'network' }
  | null;
```

### 4.3 `CerrarTurnoForm` props interface

```typescript
// apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx (T3)
import type { UseFormReturn } from 'react-hook-form';
import type { CerrarTurnoInput } from '../api/schemas/turnoSchema';
import type { SesionRead } from '../api/sesionActivaApi';

export interface CerrarTurnoFormProps {
  form: UseFormReturn<CerrarTurnoInput>;
  onSubmit: (data: CerrarTurnoInput) => Promise<void>;
  isSubmitting: boolean;
  error: CerrarTurnoErrorState | null;
  sesion: SesionRead;             // presentational lee resumen via props
  onCancel: () => void;           // navigate('/')
}

export type CerrarTurnoErrorState =
  | { kind: 'sesion_already_closed' }
  | { kind: 'network' }
  | null;
```

### 4.4 `TurnoActivoPanel` props interface

```typescript
// apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx (T4)
import type { SesionRead } from '../api/sesionActivaApi';

export interface TurnoActivoPanelProps {
  sesion: SesionRead;
  onCerrarClick: () => void;       // wired al navigate('/caja/cerrar-turno') desde Dashboard
}
```

### 4.5 `useSesionActiva` hook signature

```typescript
// apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts (T1)
import type { SesionRead } from '../api/sesionActivaApi';

export interface UseSesionActivaReturn {
  sesion: SesionRead | null;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<SesionRead | undefined>;
}

/**
 * Hook SWR para consultar sesión de caja activa del operador autenticado.
 *
 * DEC-F3.3-04: key null sin token + refresh 50min + 404 null + 401 clear.
 * Mismo pattern F3.1 useAuth (F2.2 baseline) + F3.2 REQ-OPS-117 refresh verbatim.
 *
 * Forward extensibilidad: F4.x+ consumen este hook para scoped queries per
 * sesion.uuid_sucursal + sesion.uuid_usuario. Gating transversal CU operativas.
 */
export function useSesionActiva(): UseSesionActivaReturn;
```

### 4.6 `sesionActivaApi` typed wrappers signatures

```typescript
// apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts (T1)
import type { SesionRead, SesionCreate, SesionCerrarRequest } from './types';

/**
 * GET /caja-sesion/sesion/me
 * Retorna null si 404 (operador sin turno es estado válido, NO error).
 */
export function getSesionActiva(): Promise<SesionRead | null>;

/**
 * POST /caja-sesion/sesiones
 * Mapea 409 → SesionAlreadyActiveError (status=409, code='sesion_already_active').
 */
export function abrirSesion(payload: SesionCreate): Promise<SesionRead>;

/**
 * PUT /caja-sesion/sesion/{uuid}/cerrar
 * Mapea 404 → SesionAlreadyClosedError (status=404, code='sesion_not_found').
 */
export function cerrarSesion(uuid: string, payload: SesionCerrarRequest): Promise<SesionRead>;

export class SesionAlreadyActiveError extends ParkosHttpError {
  readonly name = 'SesionAlreadyActiveError';
  readonly code = 'sesion_already_active';
}

export class SesionAlreadyClosedError extends ParkosHttpError {
  readonly name = 'SesionAlreadyClosedError';
  readonly code = 'sesion_not_found';
}
```

### 4.7 Zod schemas (shared validation contract)

```typescript
// apps/electron-sucursal/src/features/caja/api/schemas/turnoSchema.ts (T2/T3)

export const abrirTurnoSchema = z.object({
  uuid_sucursal: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  valor_inicial_efectivo: z.number().min(0),
  valor_inicial_datafono: z.number().min(0),
  observaciones: z.string().optional(),
});
export type AbrirTurnoInput = z.infer<typeof abrirTurnoSchema>;

export const cerrarTurnoSchema = z.object({
  valor_final_efectivo: z.number().min(0),
  valor_final_datafono: z.number().min(0),
  observaciones_cierre: z.string().optional(),
});
export type CerrarTurnoInput = z.infer<typeof cerrarTurnoSchema>;
```

### 4.8 formatCOP + formatDistanceToNow helpers

```typescript
// apps/electron-sucursal/src/features/caja/lib/format.ts (NEW ~10 LOC)

const copFormatter = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export function formatCOP(value: number): string {
  return copFormatter.format(value);
}

export { formatDistanceToNow } from 'date-fns';
export { es } from 'date-fns/locale';
```

**Uso en `TurnoActivoPanel`**: `formatDistanceToNow(new Date(sesion.timestamp_apertura), { locale: es, addSuffix: true })` → "hace 2 horas" para kiosko UX legible.

---

## 5. i18n keys (namespaces auth + caja)

### 5.1 Namespace `caja.json` (F2.1 baseline + F3.3 delta = 22 keys total)

**Pre-existente (F2.1, 10 keys)**: `abrir`, `cerrar`, `montoInicial`, `montoFinal`, `diferencia`, `arqueo`, `movimiento`, `ingreso`, `egreso`, `motivo`.

**Nuevas F3.3 (12 keys)**: `abrirTurno`, `cerrarTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `valorFinalEfectivo`, `valorFinalDatafono`, `observaciones`, `sesionYaAbierta`, `sesionYaCerrada`, `turnoCerradoExito`, `confirmarCierre`, `irAlTurno`, `turnoActivo`.

```json
// apps/electron-sucursal/src/renderer/i18n/locales/caja.json (F3.3 MODIFY, +12 keys)
{
  "abrir": "Abrir caja",
  "cerrar": "Cerrar caja",
  "montoInicial": "Monto inicial",
  "montoFinal": "Monto final",
  "diferencia": "Diferencia",
  "arqueo": "Arqueo",
  "movimiento": "Movimiento",
  "ingreso": "Ingreso",
  "egreso": "Egreso",
  "motivo": "Motivo",
  "abrirTurno": "Abrir turno",
  "cerrarTurno": "Cerrar turno",
  "valorInicialEfectivo": "Valor inicial efectivo",
  "valorInicialDatafono": "Valor inicial datáfono",
  "valorFinalEfectivo": "Valor final efectivo",
  "valorFinalDatafono": "Valor final datáfono",
  "observaciones": "Observaciones",
  "sesionYaAbierta": "Ya tenés un turno abierto",
  "sesionYaCerrada": "Esta sesión ya está cerrada",
  "turnoCerradoExito": "Turno cerrado exitosamente",
  "confirmarCierre": "Confirmar cierre",
  "irAlTurno": "Ir al turno",
  "turnoActivo": "Turno activo"
}
```

### 5.2 Convenciones (DEC-F3.3-06 + F2.1 DEC-ELEC-06)

- **Un namespace por bounded context** (F2.1 DEC-ELEC-06): turno = `caja`. NO `caja.turno` (namespace plano).
- **Keys en `camelCase`**. Mensajes en español neutro profesional.
- **`turnoCerradoExito` consumido en `<Login>` con prefijo namespace explícito**: `t('caja:turnoCerradoExito')` (forward-compatible con namespace alias).
- **`{{time}}` i18next interpolation** XSS-safe (F3.2 R10 mitigation pattern): aunque F3.3 NO tiene keys con interpolación temporal, el pattern queda disponible para Fase 10.
- **No crear `auth.json` keys nuevas**: `turnoCerradoExito` vive en `caja.json` por consistencia con namespace `caja` (turno es bounded context caja, no auth).

---

## 6. Error handling & edge cases

### 6.1 Matriz de errores F3.3

| Origen | Status / Tipo | Error class | UI behavior | Anchor |
|---|---|---|---|---|
| Backend | 200 OK (apertura) | (success) | `navigate('/')` + SWR re-fetch automático | REQ-OPS-119 S1 |
| Backend | 409 `sesion_already_active` | `SesionAlreadyActiveError` | `<FormMessage role="alert">{t('caja.sesionYaAbierta')}</FormMessage>` + `<Button>Ir al turno</Button>` (`navigate('/')`) | REQ-OPS-119 S2, DEC-F3.3-01 |
| Backend | 200 OK (cierre) | (success) | `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` + `navigate('/login?closed=true', { replace: true })` | REQ-OPS-122 S1, DEC-F3.3-03 |
| Backend | 404 `sesion_not_found` (cierre) | `SesionAlreadyClosedError` | `<FormMessage role="alert">{t('caja.sesionYaCerrada')}</FormMessage>` + `navigate('/login')` | REQ-OPS-122 S2, DEC-F3.3-07 |
| Backend | 200 OK (GET `/sesion/me`) | (success) | SWR cachea `SesionRead` | REQ-OPS-120 S2 |
| Backend | 404 (GET `/sesion/me`) | (404 null'd en fetcher) | SWR retorna `sesion: null, error: undefined` (operador sin turno es estado válido) | REQ-OPS-120 S3 |
| Backend | 401 (GET `/sesion/me`) | `ParkosHttpError(401)` | SWR `onError` dispara `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` | REQ-OPS-120 S4, F2.2 invariant |
| Validación Zod | `valor_inicial_efectivo < 0` | Zod resolver error | `<FormMessage>` inline error + NO invoca `parkosFetch` | REQ-OPS-119 S3 |
| Validación Zod | `valor_final_efectivo < 0` | Zod resolver error | `<FormMessage>` inline error + NO invoca `parkosFetch` | REQ-OPS-122 S3 |
| SWR | Tab inactive + sleep (drift) | (recalc per tick via revalidateOnFocus) | SWR `revalidateOnFocus: true` (F2.2 baseline) | F2.2 invariant |
| Red | Network failure (apertura/cierre) | `ParkosHttpError(network)` | `<FormMessage role="alert">{t('errors:serverError')}</FormMessage>` | F2.2 pattern |
| RHF | Form submit mid-submit | (button disabled via `isSubmitting`) | `<Button disabled>` previene doble submit | F3.1 pattern |
| Browser | Cancel button click | (no error) | `navigate('/')` sin invocar `cerrarSesion` | REQ-OPS-122 S4 |
| Auth state | `accessToken` expira mid-flow | `useAuthStore.clear()` post-cierre | F3.3 logout implícito limpia tokens vía IPC | DEC-F3.3-03 |

### 6.2 Edge cases cubiertos

- **Operador kiosko llega al terminal sin turno**: Dashboard lee `sesion === null` → `navigate('/caja/abrir-turno')` (replace). Sin flash de pantalla vacía (Skeleton durante `isLoading`).
- **Operador intenta abrir segundo turno**: 409 → mensaje claro + botón "Ir al turno" → navega a `/` que renderiza `<TurnoActivoPanel>` con el turno activo.
- **Operador cierra turno desde dos pestañas (race condition)**: primera pestaña cierra OK (200 + `useAuthStore.clear()`). Segunda pestaña intenta cerrar → 404 `SessionNotFoundError` → "ya está cerrada" + redirect login (sin `?closed=true`).
- **Operador cierra turno pero navega manualmente a `/` post-redirect**: `useSesionActiva` retorna `sesion: null` (token cleared) → Dashboard redirect a `/caja/abrir-turno`. Operador ve "abrir turno" en vez de pantalla vacía.
- **`accessToken` expira durante `useSesionActiva` polling**: SWR `onError` 401 → `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` (forward hook AuthGuard F3.x+ que redirige a `/login`).
- **Network failure durante submit**: `<FormMessage role="alert">` + form re-habilitado (RHF `form.formState.isSubmitting` toggle). Operador reintenta manualmente.
- **Operador sin `useAuth().user.sucursal`**: Form submit falla validación Zod (`uuid_sucursal: z.string().uuid()`) → `<FormMessage>` inline error. Operador ve "debes estar autenticado" sin request al backend.
- **Multi-tab open**: F2.3 single-instance lock (DEC-UPD-07) previene multi-tab kiosko. Si ocurre, cada tab tiene su propio `useAuthStore` state (Zustand in-memory). Cross-tab sync NO es scope F3.3.

### 6.3 Comportamiento `useAuthStore.clear()` post-cierre turno (DEC-F3.3-03)

```typescript
// apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx (T3)
const handleCloseSuccess = useCallback((sesionCerrada: SesionRead) => {
  // Atómico: clear tokens + dispatch event + navigate.
  // El orden importa — clear primero para que el redirect NO encuentre
  // useSesionActiva activo (key null sin token).
  useAuthStore.getState().clear();                  // IPC bridge.authStore.delete (F2.2)
  window.dispatchEvent(new Event('parkos:auth:cleared'));  // forward hook AuthGuard F3.x+
  navigate('/login?closed=true', { replace: true });  // replace previene back-button
}, [navigate]);
```

**Invariant F2.2 preserved**: `useAuthStore.clear()` borra accessToken + refreshToken + expiresAt atómicamente (Zustand `set` síncrono). Si 401 caller llega mid-clear, `handle401` lee `accessToken === null` y NO triggerea refresh.

---

## 7. Testing strategy (unit + e2e SKIPPED-env per Sandbox F.6)

### 7.1 Vitest unit (mockeando fetch global + SWR)

**`useSesionActiva.test.ts`** (NEW F3.3 T1, ~40 LOC, 4 tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U1 | SWR key null sin token — hook retorna `sesion: null` sin fetch | `mockUseAuthStoreToken(null) + renderHook(useSesionActiva) → expect(sesion).toBeNull(); expect(fetchMock).not.toHaveBeenCalled()` |
| U2 | SWR fetch OK — hook retorna `sesion: SesionRead` poblado | `mock200('/caja-sesion/sesion/me', sesionMock) + renderHook(useSesionActiva) → expect(sesion).toEqual(sesionMock)` |
| U3 | SWR 404 — hook retorna `sesion: null, error: undefined` | `mock404('/caja-sesion/sesion/me') + renderHook(useSesionActiva) → expect(sesion).toBeNull(); expect(error).toBeUndefined()` |
| U4 | SWR 401 — `useAuthStore.clear()` + `parkos:auth:cleared` event | `mock401('/caja-sesion/sesion/me') + spyOn(useAuthStore.getState(), 'clear') + spyOn(window, 'dispatchEvent') + renderHook(useSesionActiva) → waitFor(() => expect(clearSpy).toHaveBeenCalledOnce())` |

**`sesionActivaApi.test.ts`** (NEW F3.3 T1, ~40 LOC, 4 tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U5 | `getSesionActiva()` 200 → `SesionRead` | `mock200('/caja-sesion/sesion/me', sesionMock) + await getSesionActiva() → expect(result).toEqual(sesionMock)` |
| U6 | `getSesionActiva()` 404 → `null` (NO lanza error) | `mock404('/caja-sesion/sesion/me') + await getSesionActiva() → expect(result).toBeNull()` |
| U7 | `abrirSesion()` 409 → throw `SesionAlreadyActiveError` | `mock409('/caja-sesion/sesiones', {error:'sesion_already_active'}) + await abrirSesion(payload) → expect(err).toBeInstanceOf(SesionAlreadyActiveError); expect(err.status).toBe(409); expect(err.code).toBe('sesion_already_active')` |
| U8 | `cerrarSesion()` 200 OK → `SesionRead` con `timestamp_cierre` poblado | `mock200('/caja-sesion/sesion/uuid/cerrar', sesionCerradaMock) + await cerrarSesion(uuid, payload) → expect(result.timestamp_cierre).not.toBeNull()` |

**`AbrirTurno.test.tsx`** (NEW F3.3 T2, ~50 LOC, 3 tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U9 | Form submit OK → 200 → `navigate('/')` | `mock200('/caja-sesion/sesiones', sesionMock) + userEvent.type(submit) + waitFor(navigateSpy).toHaveBeenCalledWith('/')` |
| U10 | Submit con sesión ya abierta → 409 → `<FormMessage role="alert">` + botón "Ir al turno" | `mock409('/caja-sesion/sesiones', {error:'sesion_already_active'}) + expect(getByRole('alert')).toHaveTextContent('Ya tenés un turno abierto'); expect(getByText('Ir al turno')).toBeInTheDocument()` |
| U11 | Validación Zod rechaza `valor_inicial_efectivo: -100` → `<FormMessage>` inline + NO `parkosFetch` | `userEvent.type(-100) + expect(getByText(/debe ser/i)).toBeInTheDocument(); expect(POST_sesiones_spy).not.toHaveBeenCalled()` |

**`CerrarTurno.test.tsx`** (NEW F3.3 T3, ~40 LOC, 3 tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U12 | Form submit OK → 200 → `useAuthStore.clear()` + `dispatchEvent` + `navigate('/login?closed=true', {replace:true})` | `mock200 + spyOn(clear) + spyOn(dispatchEvent) + userEvent.click(submit) + waitFor → expect(clearSpy).toHaveBeenCalledOnce(); expect(dispatchEventSpy).toHaveBeenCalledWith('parkos:auth:cleared'); expect(navigateSpy).toHaveBeenCalledWith('/login?closed=true', {replace:true})` |
| U13 | PUT 404 → `<FormMessage>` + `navigate('/login')` | `mock404('/caja-sesion/sesion/uuid/cerrar') + expect(getByText('Esta sesión ya está cerrada')) + expect(navigateSpy).toHaveBeenCalledWith('/login')` |
| U14 | Cancel button → `navigate('/')` sin invocar `cerrarSesion` | `userEvent.click(cancelButton) + expect(navigateSpy).toHaveBeenCalledWith('/'); expect(cerrarSesion_spy).not.toHaveBeenCalled()` |

**`Dashboard.test.tsx`** (NEW F3.3 T4, ~25 LOC, 3 tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U15 | Operador sin sesión activa → `navigate('/caja/abrir-turno', {replace:true})` | `mockUseSesionActiva({sesion: null, isLoading: false, error: undefined}) + render(<Dashboard/>) + waitFor → expect(navigateSpy).toHaveBeenCalledWith('/caja/abrir-turno', {replace:true})` |
| U16 | Operador con sesión activa → renderiza `<TurnoActivoPanel>` con resumen + botón cerrar | `mockUseSesionActiva({sesion: sesionMock, ...}) + expect(getByText('Turno activo')).toBeInTheDocument(); expect(getByRole('button', {name: 'Cerrar turno'}))` |
| U17 | SWR 500 error → `<Alert destructive>` + retry button | `mockUseSesionActiva({error: new ParkosHttpError(500), sesion: null, ...}) + expect(getByRole('alert')).toBeInTheDocument(); expect(getByRole('button', {name: /retry/i}))` |

**`TurnoActivoPanel.test.tsx`** (NEW F3.3 T4, ~25 LOC, render tests):

| # | Escenario | Aserción clave |
|---|---|---|
| U-T1 | Renderiza uuid + timestamp + valores iniciales + botón cerrar | `render(<TurnoActivoPanel sesion={sesionMock} onCerrarClick={vi.fn()}/>) + expect(getByText(sesionMock.uuid)) + expect(getByText(/hace 2 horas/i)) + expect(getByText(/\$ 50.000/)) + expect(getByRole('button', {name: 'Cerrar turno'}))` |
| U-T2 | Omite bloque Observaciones cuando `sesion.observaciones === null` | `render(<TurnoActivoPanel sesion={{...sesionMock, observaciones: null}}/>) + expect(queryByText(/Observaciones/i)).toBeNull()` |
| U-T3 | Click en botón cerrar invoca `onCerrarClick` callback | `const onCerrarClick = vi.fn() + userEvent.click(getByRole('button', {name: 'Cerrar turno'})) + expect(onCerrarClick).toHaveBeenCalledOnce()` |

**`Login.test.tsx`** (MODIFY F3.3 T5, +1 test):

| # | Escenario | Aserción clave |
|---|---|---|
| U18 | Login mount con `?closed=true` → `<p role="status" data-testid="turno-cerrado-exito">` visible arriba del form | `render(<MemoryRouter initialEntries={['/login?closed=true']}><Login/></MemoryRouter>) + expect(getByTestId('turno-cerrado-exito')).toBeInTheDocument(); expect(getByTestId('turno-cerrado-exito')).toHaveTextContent('Turno cerrado exitosamente')` |

### 7.2 Playwright e2e (`_electron.launch` — SKIPPED-env per Sandbox F.6)

**`apps/electron-sucursal/e2e/caja/turno.spec.ts`** (NEW F3.3 T5, ~80 LOC, 4 scenarios):

| # | Escenario |
|---|---|
| E1 | **abrir-turno-happy-path**: login + redirect automático a `/caja/abrir-turno` + submit OK → redirect a `/` con `TurnoActivoPanel` visible + timestamp "hace 0 minutos" |
| E2 | **sesion-already-active-409**: setup estado con sesión activa + `page.goto('/caja/abrir-turno')` + submit → mensaje "ya tenés un turno abierto" + botón "Ir al turno" |
| E3 | **cerrar-turno-happy-path**: setup estado con sesión activa + `page.goto('/caja/cerrar-turno')` + submit OK → redirect a `/login?closed=true` con `<p role="status">` visible |
| A1 | **axe-core-wcag-2.1-aa**: 4 sub-tests con axe-core 0 violaciones en (a) AbrirTurno normal, (b) AbrirTurno 409, (c) CerrarTurno normal, (d) Login `?closed=true`. Tags `wcag2a, wcag2aa, wcag21a, wcag21aa` |

### 7.3 Sandbox F.6 caveat

Per F2.1 + F2.2 + F2.3 + F3.1 + F3.2 archive precedent, las e2e (`turno.spec.ts`) corren en sandbox F.6 con npm 11.16.0 que refuses `workspace:*` resolution. F3.3 e2e va a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. Unit tests (vitest sobre `useSesionActiva.ts` + `sesionActivaApi.ts` + pages mockeando SWR + parkosFetch) cubren el camino crítico.

### 7.4 Cobertura thresholds

```typescript
// apps/electron-sucursal/vitest.config.ts (extracto — F2.1+F3.1+F3.2 baseline, F3.3 agrega thresholds)

coverage: {
  provider: 'v8',
  thresholds: {
    // ... existing F2.1+F3.1+F3.2 thresholds ...
    'src/features/caja/hooks/useSesionActiva.ts':      { lines: 90, functions: 90, branches: 85 },
    'src/features/caja/api/sesionActivaApi.ts':        { lines: 85, functions: 85, branches: 80 },
    'src/features/caja/pages/AbrirTurno.tsx':          { lines: 80, functions: 80, branches: 75 },
    'src/features/caja/pages/CerrarTurno.tsx':         { lines: 80, functions: 80, branches: 75 },
    'src/features/caja/pages/Dashboard.tsx':           { lines: 80, functions: 80, branches: 75 },
    'src/features/caja/components/TurnoActivoPanel.tsx': { lines: 80, functions: 80, branches: 75 },
  }
}
```

---

## 8. Accessibility (WCAG 2.1 AA — axe-core)

### 8.1 Cobertura axe-core F3.3

`AbrirTurno` + `CerrarTurno` + `TurnoActivoPanel` + Login `?closed=true` feedback deben pasar axe-core scan con 0 violaciones. Cobertura específica:

| Criterio WCAG 2.1 AA | Implementación | Test |
|---|---|---|
| 1.3.1 Info and Relationships | `<FormLabel htmlFor>` + `<FormControl id>` asociados via `useFormField()` (shadcn `form.tsx`) | axe-core auto-detect |
| 1.4.3 Contrast (Minimum) | shadcn tokens + Card shadcn primitives (background/foreground ≥4.5:1) | axe-core auto-detect |
| 3.3.1 Error Identification | `<FormMessage role="alert">` con Zod errors + `<p role="status" aria-live="polite">` post-cierre feedback | axe-core + vitest `getByRole('alert')` + `getByRole('status')` |
| 3.3.2 Labels or Instructions | `<FormLabel>` con texto `t('caja.valorInicialEfectivo')` / etc. | axe-core auto-detect |
| 4.1.2 Name, Role, Value | `aria-invalid={!!error}` en `<FormControl>` + `aria-disabled` en `<Button>` | axe-core auto-detect |
| 4.1.3 Status Messages | `<p role="status" aria-live="polite">` post-cierre anuncia cambios sin interrumpir (mismo pattern F3.2 countdown precedent) | axe-core + e2e A1 |
| 2.1.1 Keyboard | Tab order secuencial: valor efectivo → valor datáfono → observaciones → submit (o cancel → submit en CerrarTurno) | vitest `userEvent.tab()` |
| 2.4.7 Focus Visible | shadcn `Input` + `Button` tienen focus ring via `focus-visible:ring-2` | axe-core + manual |

### 8.2 `aria-live="polite"` pattern (R6 mitigation, F3.2 verbatim)

```tsx
// apps/electron-sucursal/src/features/auth/pages/Login.tsx (F3.3 MODIFY T5)
{search.includes('closed=true') && (
  <p
    role="status"
    aria-live="polite"
    data-testid="turno-cerrado-exito"
  >
    {t('caja:turnoCerradoExito')}
  </p>
)}
```

- `aria-live="polite"` anuncia cambios cuando el screen reader idle (NO interruptivo).
- NO `aria-live="assertive"` — feedback NO debe interrumpir al operador en otra tarea.
- WCAG 2.1 AA compliant: patrón idéntico a F3.2 countdown precedent.

### 8.3 `aria-disabled` pattern en botón submit (F3.1 verbatim)

```tsx
// apps/electron-sucursal/src/features/caja/components/AbrirTurnoForm.tsx (T2)
<Button
  type="submit"
  disabled={form.formState.isSubmitting}
  aria-disabled={form.formState.isSubmitting}
  data-testid="abrir-turno-submit"
>
  {form.formState.isSubmitting ? t('common:loading') : t('caja:abrirTurno')}
</Button>
```

- `disabled` HTML attr previene submit + visual greyed-out.
- `aria-disabled` anuncia estado a screen readers (algunos SR no leen `disabled` consistentemente).

### 8.4 axe-core e2e test (SKIPPED-env, documentado en verify-report)

```typescript
// apps/electron-sucursal/e2e/caja/turno.spec.ts (NEW F3.3 T5, A1 test — SKIPPED-env)

test('A1: axe-core WCAG 2.1 AA 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel + Login ?closed=true', async ({ page }) => {
  await page.goto('/caja/abrir-turno');
  await expect(page.getByTestId('abrir-turno-submit')).toBeVisible();

  const accessibilityScanResults = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(accessibilityScanResults.violations).toEqual([]);
});
```

**Requisito RNF-022 WCAG 2.1 AA**: cobertura mandatory en 4 estados (AbrirTurno normal + AbrirTurno 409 + CerrarTurno normal + Login `?closed=true`).

---

## 9. Performance budget

### 9.1 SWR refresh 50min vs 5min baseline

- Baseline F2.2: 12 refreshes/hora por sesión activa de `useSesionActiva` (key `/caja-sesion/sesion/me` con 50min refresh per F3.2 DEC-SUC-03).
- F3.3: ~1.2 refreshes/hora por sesión activa. ~30KB bandwidth/refresh = ~36KB/hora.
- **Ahorro**: ~90% menos requests a `/caja-sesion/sesion/me` (mismo ratio que F3.2 useAuth).

### 9.2 SWR dedupingInterval 10s

- Múltiples componentes consumen `useSesionActiva()` en paralelo (Dashboard + CerrarTurno + TurnoActivoPanel). Sin deduping, cada uno triggerea fetch independiente.
- `dedupingInterval: 10 * 1000` (10s) deduplica fetches concurrentes — UNA sola request cada 10s máximo.
- Trade-off: si la sesión cambia (apertura/cierre), `mutate()` del container invalida cache → próximo consumer fetcha inmediatamente (no espera dedupingInterval).

### 9.3 Form submit latency budget

- `<AbrirTurno>` submit happy path:
  1. Zod resolver validation: ~1-5ms.
  2. `parkosFetch` POST `/caja-sesion/sesiones`: ~50-150ms p95 (F2.2 benchmark).
  3. SWR `mutate('/caja-sesion/sesion/me')` re-fetch (opcional): ~50-100ms p95.
  4. `navigate('/')` render: ~5-20ms.
  - **Total budget**: ~100-300ms p95. Aceptable para kiosko UX.
- `<CerrarTurno>` submit happy path:
  1. Zod resolver: ~1-5ms.
  2. `parkosFetch` PUT: ~50-150ms p95.
  3. `useAuthStore.clear()` IPC: ~5-20ms.
  4. `dispatchEvent('parkos:auth:cleared')`: ~1ms.
  5. `navigate('/login?closed=true')` render: ~5-20ms.
  - **Total budget**: ~70-200ms p95. Aceptable.

### 9.4 `formatDistanceToNow` overhead

- Single computation per render of `<TurnoActivoPanel>` (1 instance per Dashboard mount).
- ~0.1ms CPU cost. Insignificante.

### 9.5 `formatCOP` formatter

- `Intl.NumberFormat` constructor: ~1ms first call, cached per-instance.
- `formatCOP(value)`: ~0.05ms per call.
- `<TurnoActivoPanel>` renders 2 `formatCOP` calls (efectivo + datáfono) + `<CerrarTurnoForm>` renders 2 más (mismos valores). Total: 4 calls per Dashboard/CerrarTurno mount. ~0.2ms overhead. Insignificante.

### 9.6 Memory footprint

- `useSesionActiva` SWR cache: ~500B por sesión activa (`SesionRead` JSON serialized).
- `<TurnoActivoPanel>` state: 0 (puramente presentational).
- `sesionActivaApi` typed errors: ~50B por class definition.
- **Total**: ~550B adicional en memoria por sesión activa. Insignificante.

### 9.7 Network requests per turno

- Login (F3.1) → POST `/auth/login`: 1 request.
- Apertura turno (F3.3) → POST `/caja-sesion/sesiones`: 1 request.
- Dashboard poll → GET `/caja-sesion/sesion/me` cada 50min: ~1.2 requests/hora.
- Operacion activa (F4.x+) → múltiples POSTs (facturación, ingreso, cobro, FE): ~5-20 requests/turno (forward hook F4-F8).
- Cierre turno (F3.3) → PUT `/caja-sesion/sesion/{uuid}/cerrar`: 1 request.
- **Total F3.3**: 3 requests propios (apertura + dashboard poll + cierre) + 0 pre-flight (DEC-F3.3-10).

---

## 10. Security (CSRF, XSS, idempotency)

### 10.1 Defense in depth (5 capas, F3.3 contribution)

| Layer | Mechanism | Source | F3.3 contribution |
|---|---|---|---|
| 1 auth | JWT Bearer (F2.2) + cookie httpOnly SameSite=Lax (F1.2) + bcrypt (F1.2) | `useAuth.ts` + `authStore.ts` + backend `auth.py` | NO custom auth (heredado) |
| 2 engineering | TS strict + noUncheckedIndexedAccess + ESLint flat (F2.1) | tsconfig.* + eslint.config.js | `useSesionActiva.ts` + `sesionActivaApi.ts` + `AbrirTurno`/`CerrarTurno`/`Dashboard` heredan |
| 3 a11y | axe-core WCAG 2.1 AA (RNF-022) + FormField aria-invalid + FormMessage role=alert + `<p role="status">` post-cierre | `@axe-core/playwright` + shadcn `form.tsx` + F3.3 feedback | ADD axe-core A1 test 4 estados |
| 4 contract | Zod local form (F3.3) + backend Pydantic (F1.3 + F1.13) + 6 new REQ-OPS-119..124 (DEC-F3.3-11) + typed errors `SesionAlreadyActiveError`/`SesionAlreadyClosedError` | `@hookform/resolvers/zod` + `schemas/caja_sesion.py` + `operations/spec.md` delta | ADD 6 new REQ-OPS-119..124 al spec canónico |
| 5 retry-budget | parkosFetch retry 5xx + 401 refresh-once (F2.2) + pre-flight gate (F3.2 — NO extension F3.3 per DEC-F3.3-10) | parkosFetch.ts + DEC-FETCH-02/03 | NO extension (kiosko UX permite 401 retry visible) |

### 10.2 CSRF mitigation (F2.2 + F3.1 invariant preserved)

- Cookie httpOnly `parkos_session` con `SameSite=Lax` (F1.2 backend) bloquea cross-site form submissions.
- Bearer JWT en `Authorization` header para requests `parkosFetch` (F2.2).
- F3.3 NO agrega endpoints públicos — `POST /caja-sesion/sesiones` + `PUT /caja-sesion/sesion/{uuid}/cerrar` requieren `accessToken` válido (backend `abrir_cerrar_caja` permission per F1.13 GAP-BE-05 fix).
- Atacante sin sesión válida no puede CSRF abrir/cerrar turno.

### 10.3 XSS mitigation (F3.2 invariant preserved)

- `React 18` JSX escapa automáticamente interpolaciones (`{sesion.observaciones}` → HTML-safe).
- i18next interpolation `{{time}}` XSS-safe (F3.2 R10 mitigation pattern verbatim).
- `<Input type="number" inputMode="decimal">` NO acepta texto (browser bloquea), previene XSS via observaciones field.
- `dangerouslySetInnerHTML` NO usado en F3.3.
- `formatCOP` retorna string formateada (sin user input).

### 10.4 Idempotency-Key automático (F2.2 invariant preserved)

- `parkosFetch.ts` genera SHA-256 de `method|path|body` como `Idempotency-Key` header para POST `/caja-sesion/*` (skip `/auth/login` only).
- F3.3 apertura turno: si operador hace doble-click en submit, segundo POST recibe mismo `Idempotency-Key` → backend retorna 200 OK cached o 409 `sesion_already_active`.
- F3.3 cierre turno: mismo pattern. Doble-click "Confirmar cierre" no duplica cierre.
- **F3.3 NO requiere override** del Idempotency-Key — F2.2 ya lo provee.

### 10.5 Permission gating (Defense in depth XR6)

- Backend ya emite 403 si `permisos[]` no incluye `abrir_cerrar_caja` (F1.13 GAP-BE-05 fix).
- F3.3 NO agrega client-side permission gating — backend es source of truth.
- Forward hook: si F4.x+ requiere client-side permission check, exportar `usePermisos()` desde `useAuth()` y agregar `<ProtectedRoute perm="abrir_cerrar_caja">` wrapping.

### 10.6 No exposure de datos sensibles en URL params (F3.2 R11 mitigation)

- `?closed=true` query param NO expone `uuid_sesion`, `valor_inicial_*`, ni datos del operador.
- Mantiene history clean (browser history, server logs sin info sensible).
- Atacante no puede inferir estado de sesión via URL.

### 10.7 Atomic state updates (F2.2 invariant preserved)

- `useAuthStore.setTokens` (F2.2) actualiza 3 keys simultáneamente en Zustand `set` síncrono. NO race condition con `useSesionActiva` SWR que lee `accessToken`.
- `useAuthStore.clear()` post-cierre turno (F3.3) borra atómicamente — sin estado intermedio "logged-in sin turno".
- `clear()` invoca IPC `bridge.authStore.delete` (F2.2) — persistencia en electron-store se borra atómicamente.

---

## 11. Observability

### 11.1 Structured logging (F2.1 baseline, F3.3 consume)

- `parkosFetch` emite `console.info` con `[parkosFetch]` prefix per request (F2.1 baseline).
- F3.3 NO agrega logging custom — consume el baseline.
- Forward hook: si F11.x requiere structured logging para analytics, agregar `Sentry.captureException(err)` en `sesionActivaApi` catches.

### 11.2 Error tracking (forward hook F11.x)

- `SesionAlreadyActiveError` + `SesionAlreadyClosedError` + `ParkosHttpError(401)` se loggean automáticamente por `parkosFetch` baseline.
- F3.3 NO captura errors con Sentry — F11.x sync UI + reportería es responsable.

### 11.3 Métricas de uso (forward hook F12.x reportería)

- F3.3 modelo de datos `prod.sesion` [L-S] provee métricas nativas en backend (timestamp_apertura, timestamp_cierre, valor_inicial_*, valor_final_*).
- F12.x consume via `useSesionActiva` + queries a `prod.sesion_v_resumen` (forward view).
- F3.3 NO consume analytics — solo emite eventos via `parkosFetch` (F2.1 baseline).

### 11.4 Window events (F2.2 invariant preserved)

- F3.3 dispatch `new Event('parkos:auth:cleared')` post-cierre turno (forward hook AuthGuard F3.x+).
- F3.3 NO consume `parkos:auth:cleared` events (eso es responsabilidad de `<AuthGuard>` forward).
- `parkos:auth:cleared` event listener count = 0 en F3.3 — forward extensibility.

### 11.5 i18n locale switching (F2.1 DEC-ELEC-06)

- F3.3 keys en namespace `caja.json` (es-CO default + en-US + pt-BR forward).
- F3.3 NO implementa locale switcher — F4.x+ UI feature.
- Tests asumen `es-CO` default; en-US + pt-BR son stubs F2.1 baseline.

---

## 12. Migration / rollback plan

### 12.1 F3.3 entrega

**Cluster C1** (5 atomic tasks T1..T5) en orden mandatory con paralelismo donde aplica:

```
T1 — useSesionActiva hook + sesionActivaApi typed wrappers + 8 unit tests (U1..U8)
   ↓ (T1 provee hook reusable + API typed)
(T2 || T3 || T4) — AbrirTurno page+form (T2) || CerrarTurno page+form + Login MODIFY (T3) || Dashboard+TurnoActivoPanel+App.tsx (T4)
   ↓ (T2+T3+T4 proveen UI completa)
T5 — e2e turno.spec.ts (E1+E2+E3+A1) + Login U18 test
   ↓ (T5 provee e2e green gate + Login feedback)
archive — mover change folder a archive/, actualizar pending.md §1 row F3.3 → ✅
```

T2, T3, T4 son parcialmente independientes (todos consumen T1) — pueden ejecutarse en paralelo si el executor lo permite. Recomendación secuencial por dependencia: T1 → T4 (Dashboard wire App.tsx) → T2 (AbrirTurno independiente) → T3 (CerrarTurno + Login MODIFY) → T5.

### 12.2 Forward hooks (Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.x** (AuthGuard component) | `<AuthGuard>` intercepta `parkos:auth:cleared` event → `navigate('/login?next=...')` | F3.3 dispatch event verbatim |
| **HU-F3.x** (Logout button UI) | Botón dedicado invoca `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` + `navigate('/login')` | F3.3 pattern reusable |
| **HU-F4.x** (catálogos + ocupación) | `useSesionActiva()` para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario` | F3.3 export hook desde `features/caja/hooks` |
| **HU-F5.x** (facturación) | `useSesionActiva()` + pre-flight gate automático (`/facturacion/*` ya cubierto F3.2) | F3.3 hook reusable; F3.2 pre-flight inherit |
| **HU-F6.x** (ingreso vehicular) | `useSesionActiva()` + `sesion.uuid` para FK en `ingreso` | F3.3 hook + SesionRead.uuid |
| **HU-F7.x** (salida + cálculo) | `useSesionActiva()` para validar sesión activa pre-cálculo | F3.3 hook |
| **HU-F8.x** (cobro + FE) | `useSesionActiva()` + pre-flight gate (ya cubierto F3.2) | F3.3 hook + F3.2 pre-flight |
| **HU-F9.x** (suscripciones) | `useSesionActiva()` para suscripciones recurrentes | F3.3 hook |
| **HU-F10.x** (arqueos completos) | `CerrarTurno` placeholder → flujo completo con `POST /caja/arqueo` + tolerancia + justificación + alerta `descuadre_critico` | F3.3 marca placeholder, F10.x completa |
| **HU-F11.x** (sync UI + alertas) | `useSesionActiva()` para alertas per-turno + shadcn Toast component para post-cierre | F3.3 hook + forward toast |
| **HU-F12.x** (reportería) | `useSesionActiva()` + queries a `prod.sesion_v_resumen` view | F3.3 hook |

### 12.3 Rollout strategy

- **Branch**: `feat/fase-3-turno` (HEAD `fde9850`).
- **PR target**: `origin/dev`.
- **Merge order**: F3.3 merge a `dev` post-F3.1 + F3.2 (ambas archivadas 2026-09-15). F4.x+ depende de F3.3 hook + components.
- **Feature flag**: NO. F3.3 es consumer directo de infra shipped F2.1+F2.2+F3.1+F3.2. Cero toggle runtime.
- **Sandbox**: F3.3 e2e puede SKIP en sandbox F.6 (npm 11.16.0 refuses workspace:*) — documentado como D-env en verify-report. Unit tests cubren el camino crítico.
- **Local dev**: e2e verdes en Windows native con npm 11.16+ (per F2.1+F2.2+F2.3+F3.1+F3.2 archive precedent).

### 12.4 Rollback plan

Si F3.3 merge causa regresión en F3.1 (Login) o F3.2 (lockout countdown):

1. **Revert PR en `dev`** — `git revert <merge-commit-sha>`. Cero impacto en F1.x + F2.x + F3.1 + F3.2 (F3.3 es ADDITIVE: 14 NEW archivos + 3 MODIFY pequeños + 12 i18n keys).
2. **Selective rollback** — si solo un componente rompe, revertir commit individual:
   - `git revert <T1-commit>` revierte `useSesionActiva` + `sesionActivaApi` (T1). F3.3 entero bloqueado — sin hook, T2-T5 no funcionan.
   - `git revert <T4-commit>` revierte Dashboard + App.tsx. Operador kiosko ve pantalla vacía (regresión temporal a pre-F3.3 behavior).
3. **Forward compatibility** — F3.3 NO es prerequisite de F3.1 ni F3.2 (F3.1+F3.2 archivadas independientemente). Rollback F3.3 NO afecta login + lockout.

### 12.5 Pendiente post-archive

- `pending.md` §1 row F3.3 → marcar ✅ cerrado.
- `docs/02-arquitectura/decisiones-tecnicas.md` → agregar DEC-F3.3-01..12 resumen (cross-ref `proposal.md` §4).
- `openspec/CHANGELOG.md` → entrada "2026-09-15 — HU-F3.3 abrir/cerrar turno archived (6 new REQ-OPS-119..124 user-facing)".
- `openspec/specs/operations/spec.md` post-archive → REQ-OPS vigente = 001..124 (124 total).

### 12.6 Resoluciones de open questions (verificación cruzada)

Las inconsistencias detectadas en `exploration.md` §1 están cerradas en `proposal.md` §16:

- **Q1** (arqueo inline vs completo): DEC-F3.3-06 — `CerrarTurno` placeholder + Fase 10 completa (atomic split).
- **Q2** (404 vs 409 mapping en cierre): DEC-F3.3-07 — backend emite 404 `SessionNotFoundError` (REST semantics); frontend mapea a UX "ya está cerrada". Sin cambio backend.
- **Q3** (`?closed=true` feedback mechanism): DEC-F3.3-09 — `<p role="status" aria-live="polite">` arriba del form. Simple + WCAG compliant + zero boilerplate. Forward F11.x usa shadcn Toast.
- **Q4** (extensión `PRE_FLIGHT_PATHS`): DEC-F3.3-10 — YAGNI. `/caja-sesion/*` NO es critical-path DEC-SUC-03. `handle401` cubre.

0 KNOWN-MISSING. F3.3 ready for `sdd-tasks`.

---

## 13. Open questions

Cero open questions en esta fase. Las 4 inconsistencias (Q1..Q4) están cerradas en `proposal.md` §4 con DEC-F3.3-06 + DEC-F3.3-07 + DEC-F3.3-09 + DEC-F3.3-10. Forward extensibility documented en §12.2.

---

## Apéndice A — TS mockups (KEEP COMPACT: 6 archivos, 5-30 LOC cada uno)

### A.1 `useSesionActiva.ts` (~30 LOC target — T1)

```typescript
import useSWR from 'swr';
import { useAuthStore } from '@parkos/ui-kit/store';
import { parkosFetch, ParkosHttpError } from '@parkos/ui-kit/fetch';
import { getSesionActiva, type SesionRead } from '../api/sesionActivaApi';
import { REFRESH_INTERVAL_MS } from '@parkos/ui-kit/hooks';

export function useSesionActiva(): {
  sesion: SesionRead | null;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<SesionRead | undefined>;
} {
  const accessToken = useAuthStore((s) => s.accessToken);
  const { data, error, isLoading, mutate } = useSWR<SesionRead | null>(
    accessToken ? '/caja-sesion/sesion/me' : null,
    () => getSesionActiva(),
    {
      refreshInterval: REFRESH_INTERVAL_MS,            // F3.2 verbatim 50min
      dedupingInterval: 10 * 1000,                    // dedupe parallel consumers
      shouldRetryOnError: (err) => (err as ParkosHttpError)?.status !== 404,
      onError: (err) => {
        if ((err as ParkosHttpError)?.status === 401) {
          useAuthStore.getState().clear();
          window.dispatchEvent(new Event('parkos:auth:cleared'));
        }
      },
    },
  );
  const normalizedError = (error as ParkosHttpError)?.status === 404 ? undefined : error;
  return { sesion: data ?? null, isLoading, error: normalizedError, refresh: mutate };
}
```

### A.2 `sesionActivaApi.ts` (~25 LOC target — T1)

```typescript
import { parkosFetch, ParkosHttpError } from '@parkos/ui-kit/fetch';

export interface SesionRead {
  uuid: string;
  uuid_sucursal: string;
  uuid_usuario: string;
  valor_inicial_efectivo: number;
  valor_inicial_datafono: number;
  timestamp_apertura: string;
  timestamp_cierre: string | null;
  observaciones?: string | null;
}
export interface SesionCreate {
  uuid_sucursal: string;
  uuid_usuario: string;
  valor_inicial_efectivo: number;
  valor_inicial_datafono: number;
  observaciones?: string;
}
export interface SesionCerrarRequest {
  valor_final_efectivo: number;
  valor_final_datafono: number;
  observaciones_cierre?: string;
}

export class SesionAlreadyActiveError extends ParkosHttpError {
  readonly name = 'SesionAlreadyActiveError';
  readonly code = 'sesion_already_active' as const;
}
export class SesionAlreadyClosedError extends ParkosHttpError {
  readonly name = 'SesionAlreadyClosedError';
  readonly code = 'sesion_not_found' as const;
}

export async function getSesionActiva(): Promise<SesionRead | null> {
  try { return await parkosFetch<SesionRead>('/caja-sesion/sesion/me'); }
  catch (err) { if ((err as ParkosHttpError)?.status === 404) return null; throw err; }
}
export const abrirSesion = (p: SesionCreate): Promise<SesionRead> =>
  parkosFetch<SesionRead>('/caja-sesion/sesiones', { method: 'POST', body: p });
export const cerrarSesion = (uuid: string, p: SesionCerrarRequest): Promise<SesionRead> =>
  parkosFetch<SesionRead>(`/caja-sesion/sesion/${uuid}/cerrar`, { method: 'PUT', body: p });
```

### A.3 `Dashboard.tsx` container (~25 LOC target — T4)

```typescript
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useSesionActiva } from '../hooks/useSesionActiva';
import { TurnoActivoPanel } from '../components/TurnoActivoPanel';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

export function Dashboard(): JSX.Element {
  const { sesion, isLoading, error, refresh } = useSesionActiva();
  const navigate = useNavigate();
  const { t } = useTranslation(['caja', 'common']);

  useEffect(() => {
    if (!sesion && !isLoading && !error) {
      navigate('/caja/abrir-turno', { replace: true });   // DEC-F3.3-05
    }
  }, [sesion, isLoading, error, navigate]);

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (error && (error as ParkosHttpError).status !== 404) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{t('errors:serverError')}</AlertDescription>
        <Button onClick={() => refresh()}>{t('common:retry')}</Button>
      </Alert>
    );
  }
  if (sesion) {
    return <TurnoActivoPanel sesion={sesion} onCerrarClick={() => navigate('/caja/cerrar-turno')} />;
  }
  return null;  // redirect will fire
}
```

### A.4 `TurnoActivoPanel.tsx` organism (~22 LOC target — T4)

```typescript
import { useTranslation } from 'react-i18next';
import { formatDistanceToNow } from 'date-fns';
import { es } from 'date-fns/locale';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { formatCOP } from '../lib/format';
import type { SesionRead } from '../api/sesionActivaApi';

export function TurnoActivoPanel({ sesion, onCerrarClick }: { sesion: SesionRead; onCerrarClick: () => void }): JSX.Element {
  const { t } = useTranslation('caja');
  return (
    <Card>
      <CardHeader><CardTitle>{t('turnoActivo')}</CardTitle></CardHeader>
      <CardContent>
        <p><strong>UUID:</strong> {sesion.uuid}</p>
        <p><strong>{t('valorInicialEfectivo')}:</strong> {formatCOP(sesion.valor_inicial_efectivo)}</p>
        <p><strong>{t('valorInicialDatafono')}:</strong> {formatCOP(sesion.valor_inicial_datafono)}</p>
        <p><strong>Apertura:</strong> {formatDistanceToNow(new Date(sesion.timestamp_apertura), { locale: es, addSuffix: true })}</p>
        {sesion.observaciones && <p><strong>{t('observaciones')}:</strong> {sesion.observaciones}</p>}
      </CardContent>
      <CardFooter><Button onClick={onCerrarClick}>{t('cerrarTurno')}</Button></CardFooter>
    </Card>
  );
}
```

### A.5 `AbrirTurnoForm.tsx` presentational (~22 LOC target — T2)

```typescript
import { useTranslation } from 'react-i18next';
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage, FormDescription } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import type { UseFormReturn } from 'react-hook-form';
import type { AbrirTurnoInput } from '../api/schemas/turnoSchema';

export function AbrirTurnoForm({ form, onSubmit, isSubmitting, error }: {
  form: UseFormReturn<AbrirTurnoInput>;
  onSubmit: (data: AbrirTurnoInput) => Promise<void>;
  isSubmitting: boolean;
  error: { kind: 'sesion_already_active' } | { kind: 'network' } | null;
}): JSX.Element {
  const { t } = useTranslation('caja');
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} noValidate aria-labelledby="abrir-turno-title">
        <h1 id="abrir-turno-title">{t('abrirTurno')}</h1>
        <FormField control={form.control} name="valor_inicial_efectivo"
          render={({ field }) => (<FormItem><FormLabel>{t('valorInicialEfectivo')}</FormLabel>
            <FormControl><Input type="number" inputMode="decimal" step="0.01" {...field} /></FormControl>
            <FormMessage /></FormItem>)} />
        <FormField control={form.control} name="valor_inicial_datafono"
          render={({ field }) => (<FormItem><FormLabel>{t('valorInicialDatafono')}</FormLabel>
            <FormControl><Input type="number" inputMode="decimal" step="0.01" {...field} /></FormControl>
            <FormMessage /></FormItem>)} />
        <FormField control={form.control} name="observaciones"
          render={({ field }) => (<FormItem><FormLabel>{t('observaciones')}</FormLabel>
            <FormControl><Input {...field} /></FormControl><FormDescription>Opcional</FormDescription><FormMessage /></FormItem>)} />
        {error?.kind === 'sesion_already_active' && (
          <>
            <FormMessage role="alert">{t('sesionYaAbierta')}</FormMessage>
            <Button type="button" onClick={() => window.location.assign('/')}>{t('irAlTurno')}</Button>
          </>
        )}
        <Button type="submit" disabled={isSubmitting} aria-disabled={isSubmitting}
          data-testid="abrir-turno-submit">{isSubmitting ? t('common:loading') : t('abrirTurno')}</Button>
      </form>
    </Form>
  );
}
```

### A.6 `CerrarTurno.tsx` container (~22 LOC target — T3)

```typescript
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';
import { useCallback } from 'react';
import { cerrarTurnoSchema, type CerrarTurnoInput } from '../api/schemas/turnoSchema';
import { cerrarSesion, SesionAlreadyClosedError, ParkosHttpError } from '../api/sesionActivaApi';
import { useSesionActiva } from '../hooks/useSesionActiva';
import { useAuthStore } from '@parkos/ui-kit/store';
import { CerrarTurnoForm } from '../components/CerrarTurnoForm';

export function CerrarTurno(): JSX.Element {
  const { sesion } = useSesionActiva();
  const navigate = useNavigate();
  const form = useForm<CerrarTurnoInput>({ resolver: zodResolver(cerrarTurnoSchema),
    defaultValues: { valor_final_efectivo: 0, valor_final_datafono: 0 } });

  const handleSuccess = useCallback(() => {
    useAuthStore.getState().clear();                       // DEC-F3.3-03
    window.dispatchEvent(new Event('parkos:auth:cleared'));
    navigate('/login?closed=true', { replace: true });
  }, [navigate]);

  const onSubmit = form.handleSubmit(async (values) => {
    if (!sesion) return;
    try { await cerrarSesion(sesion.uuid, values); handleSuccess(); }
    catch (err) {
      if (err instanceof SesionAlreadyClosedError) navigate('/login');
      else if ((err as ParkosHttpError)?.status === 401) handleSuccess();
    }
  });
  if (!sesion) return null;
  return <CerrarTurnoForm form={form} onSubmit={onSubmit}
    isSubmitting={form.formState.isSubmitting} error={null} sesion={sesion} onCancel={() => navigate('/')} />;
}
```

### A.7 `Login.tsx` MODIFY delta (+5 LOC — T5)

```diff
 // apps/electron-sucursal/src/features/auth/pages/Login.tsx (F3.1+F3.2 baseline, F3.3 MODIFY)

 import { useNavigate } from 'react-router-dom';
+import { useLocation } from 'react-router-dom';

 export function Login(): JSX.Element {
   const navigate = useNavigate();
+  const location = useLocation();
+  const showClosedNotice = location.search.includes('closed=true');
   const { isAuthenticated, isLoading, user } = useAuth();
   // ... F3.1+F3.2 state verbatim ...

   return (
+    <>
+      {showClosedNotice && (
+        <p role="status" aria-live="polite" data-testid="turno-cerrado-exito">
+          {t('caja:turnoCerradoExito')}
+        </p>
+      )}
       <LoginForm
         form={form}
         onSubmit={onSubmit}
         isSubmitting={form.formState.isSubmitting}
         error={errorState}
         onLockoutExpired={handleLockoutExpired}
       />
+    </>
   );
 }
```

### A.8 `App.tsx` MODIFY delta (+10 LOC — T4)

```diff
 // apps/electron-sucursal/src/renderer/App.tsx (F3.1+F3.2 baseline, F3.3 MODIFY)

 import { StatusBar } from './components/StatusBar';
 import { Login } from '../features/auth/pages/Login';
+import { Dashboard } from '../features/caja/pages/Dashboard';
+import { AbrirTurno } from '../features/caja/pages/AbrirTurno';
+import { CerrarTurno } from '../features/caja/pages/CerrarTurno';

 export default function App() {
   return (
     <>
       <StatusBar />
       <main lang="es-CO">
         <h1>{t('appName')}</h1>
-        <p>{t('bootstrapNotice')}</p>
         <Routes>
-          <Route path="/" element={null} />
+          <Route path="/" element={<Dashboard />} />
           <Route path="/login" element={<Login />} />
+          <Route path="/caja/abrir-turno" element={<AbrirTurno />} />
+          <Route path="/caja/cerrar-turno" element={<CerrarTurno />} />
           <Route path="*" element={<p role="status">{t('error', { defaultValue: '404' })}</p>} />
         </Routes>
       </main>
     </>
   );
 }
```

---

## Apéndice B — config deltas (3 configs)

### B.1 `vitest.config.ts` (apps/electron-sucursal)

F3.3 agrega coverage thresholds para los nuevos archivos `useSesionActiva` + `sesionActivaApi` + `AbrirTurno` + `CerrarTurno` + `Dashboard` + `TurnoActivoPanel`. Sin cambios estructurales.

```diff
   // apps/electron-sucursal/vitest.config.ts
   coverage: {
     provider: 'v8',
     thresholds: {
       // ... existing F2.1+F3.1+F3.2 thresholds ...
+      'src/features/caja/hooks/useSesionActiva.ts':         { lines: 90, functions: 90, branches: 85 },
+      'src/features/caja/api/sesionActivaApi.ts':           { lines: 85, functions: 85, branches: 80 },
+      'src/features/caja/pages/AbrirTurno.tsx':             { lines: 80, functions: 80, branches: 75 },
+      'src/features/caja/pages/CerrarTurno.tsx':            { lines: 80, functions: 80, branches: 75 },
+      'src/features/caja/pages/Dashboard.tsx':              { lines: 80, functions: 80, branches: 75 },
+      'src/features/caja/components/TurnoActivoPanel.tsx': { lines: 80, functions: 80, branches: 75 },
     }
   }
```

### B.2 `package.json` (apps/electron-sucursal)

F3.3 **NO requiere nuevas dependencias**. Todo el stack ya está en `package.json` per F2.1+F2.2+F3.1+F3.2 baseline (`react@^18.3.1` + `react-router-dom@^6.27.0` + `react-hook-form@^7.53.0` + `zod@^3.23.0` + `swr` + `date-fns` + `vitest` + `@testing-library/react` + `@axe-core/playwright` + `i18next` + `react-i18next`).

```diff
   "dependencies": {
-    // F2.1 + F2.2 + F3.1 + F3.2 stack (sin cambios)
+    // F2.1 + F2.2 + F3.1 + F3.2 stack + F3.3 useSesionActiva + caja (NO requiere nuevas deps)
   }
```

### B.3 `tsconfig.renderer.json`

F3.3 **NO requiere cambios**. `useSesionActiva.ts` + `sesionActivaApi.ts` + `AbrirTurno.tsx` + `CerrarTurno.tsx` + `Dashboard.tsx` + `TurnoActivoPanel.tsx` usan imports existentes (`useState`/`useEffect` from `react`, `useSWR` from `swr`, shadcn primitives). Strict mode + `noUncheckedIndexedAccess` + `noImplicitOverride` heredados de F2.1+F3.1+F3.2.

```diff
   // Sin cambios — F3.3 hereda paths y strict mode de F2.1+F2.2+F3.1+F3.2
```

---

## CHANGELOG

- (2026-09-15) F3.3 design phase complete — 13 secciones + 2 apéndices verbatim clonando layout F3.2 1:1, ~880 LOC total. 12 DEC-F3.3-01..12 documentados (cross-ref `proposal.md` §4 + `exploration.md` §7). DEC-F3.3-08 + DEC-F3.3-12 verdict **DELTA** (F3.3 ES user-facing: AbrirTurno form + CerrarTurno form + useSesionActiva SWR + TurnoActivoPanel + Dashboard redirect + 409/404 UX mapping + logout implícito post-200 + ?closed=true feedback + WCAG 2.1 AA compliance). 5 acceptance gates G1..G5 mapeados a tests (G1 useSesionActiva+sesionActivaApi U1-U8, G2 AbrirTurno U9-U11, G3 CerrarTurno U12-U14, G4 Dashboard+TurnoActivoPanel U15-U17+T1-T3, G5 e2e E1-E3+A1 + Login U18). 6 REQ-OPS-119..124 coverage (REQ-OPS-119 AbrirTurno POST 409 UX, REQ-OPS-120 useSesionActiva SWR, REQ-OPS-121 TurnoActivoPanel organism, REQ-OPS-122 CerrarTurno PUT 404 UX + logout implícito, REQ-OPS-123 Dashboard redirect, REQ-OPS-124 ?closed=true feedback + WCAG axe-core). Arquitectura: `<Dashboard>` container (NEW T4 useSesionActiva + useEffect redirect replace) + `<TurnoActivoPanel>` organism (NEW T4 shadcn Card + formatCOP + formatDistanceToNow) + `<AbrirTurno>` container (NEW T2 RHF+Zod+useAuth+parkosFetch) + `<AbrirTurnoForm>` presentational (NEW T2 inputMode=decimal + FormMessage+Ir al turno button) + `<CerrarTurno>` container (NEW T3 useSesionActiva + cerrarSesion + useAuthStore.clear post-200 + navigate ?closed=true) + `<CerrarTurnoForm>` presentational (NEW T3 placeholder + resumen turno + Cancel button) + `useSesionActiva` hook NEW (T1 SWR key null + refresh 50min F3.2 verbatim + dedupingInterval 10s + shouldRetryOnError 404 + onError 401 clear) + `sesionActivaApi` typed wrappers NEW (T1 parkosFetch raw + 404→null + 409/404 mapping SesionAlreadyActiveError/SesionAlreadyClosedError) + `Login.tsx` MODIFY T5 (+5 LOC ?closed=true detection + role=status aria-live=polite) + `App.tsx` MODIFY T4 (+10 LOC registra 3 rutas caja + Dashboard reemplaza element={null}) + `caja.json` MODIFY T2+T3+T4+T5 (+12 keys turno) + `vitest.config.ts` MODIFY (+6 thresholds coverage). 8 TS mockups en Appendix A (useSesionActiva + sesionActivaApi + Dashboard + TurnoActivoPanel + AbrirTurnoForm + CerrarTurno + Login modify delta + App.tsx modify delta) + 3 configs delta en Appendix B (vitest.config.ts thresholds + package.json no-cambios + tsconfig.renderer.json no-cambios). Forward extensibility documentado en §12.2 — F4.x (catálogos) + F5.x (facturación) + F6.x (ingreso) + F7.x (salida) + F8.x (cobro+FE) + F9.x (suscripciones) + F10.x (arqueos completos completa placeholder) + F11.x (sync UI + Toast post-cierre) + F12.x (reportería) consumen `useSesionActiva` hook + `SesionRead.uuid` scoped queries + F3.2 pre-flight gate ya cubre /facturacion/* y /caja/arqueo*. Ready for `sdd-tasks`.

---

**End of design — HU-F3.3.**
