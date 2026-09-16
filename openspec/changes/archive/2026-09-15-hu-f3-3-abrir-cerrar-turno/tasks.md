# Tasks — HU-F3.3 Abrir y cerrar turno (caja-sesion con valor_inicial_efectivo/datafono + arqueo inline placeholder + redirect según sesión activa)

> **Phase**: tasks (sdd-tasks) · **Status**: ready for sdd-apply
> **HU ID**: HU-F3.3 (Fase 3 — tercera HU; Autenticación y turno de caja, primer consumer transversal de `caja-sesion`)
> **Working dir**: `E:\easypunto_parkos` · **Branch**: `feat/fase-3-turno` (HEAD `fde9850`, F3.1 archivado 2026-09-15 + F3.2 archivado 2026-09-15)
> **PR target**: `origin/dev`
> **Cross-refs**: `exploration.md` (Engram #1684, ~580 LOC, 10 DEC-F3.3-01..10, 8 riesgos R1..R8) · `proposal.md` (12 DEC-F3.3-01..12 ratified, DEC-F3.3-08 + DEC-F3.3-12 verdict DELTA, 6 new REQ-OPS-119..124 user-facing) · `specs/operations/spec.md` (DELTA con 6 new REQ-OPS-119..124 en formato Given/When/Then/And RFC 2119) · `design.md` (13 secciones + 2 apéndices, 8 TS mockups + 3 configs delta)
> **Prereq change**: `hu-f3-2-lockout-refresh-pre-flight` archived 2026-09-15 (HEAD `fde9850`)
> **Author**: Parkos Dev <dev@parkos.local> · **Language**: español neutro profesional · **Conventional commits**: `feat(caja)` / `feat(auth)` / `test(electron)` — sin Co-authored-by AI

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **Change** | `hu-f3-3-abrir-cerrar-turno` |
| **HU** | F3.3 — Abrir turno con `valor_inicial_efectivo` + `valor_inicial_datafono` (decimales ≥0) vía `POST /caja-sesion/sesiones` + consultar sesión activa vía `GET /caja-sesion/sesion/me` + cerrar turno con arqueo inline placeholder (completo en Fase 10) vía `PUT /caja-sesion/sesion/{uuid}/cerrar` + redirect según exista sesión activa al cargar `/` + manejo tipado de 409 `sesion_already_active` (DEC-F3.3-07) y 404 `sesion_not_found` con mensajes i18n claros + logout implícito post-cierre + feedback `?closed=true` en `/login` + WCAG 2.1 AA axe-core compliance. |
| **Owner** | Parkos Dev <dev@parkos.local> |
| **Working tree** | `E:\easypunto_parkos` |
| **Branch base** | `feat/fase-3-turno` (F2.1 + F2.2 + F2.3 + F3.1 + F3.2 archivados) |
| **PR target** | `origin/dev` |
| **Total tasks** | 5 atomic (T1..T5) |
| **Total clusters** | 1 (C1 — turno end-to-end) |
| **Production LOC budget** | ~320 LOC (T1 80 + T2 100 + T3 100 + T4 40) |
| **Test LOC budget** | ~250 LOC unit (T1 60 + T2 80 + T3 60 + T4 50) + ~80 LOC e2e (T5) |
| **Total LOC budget** | ~650 LOC (production + unit + e2e) — debajo del budget 800 per `config.yaml rules.tasks` |
| **Atomic commits** | 5 (C1: T1, T2, T3, T4, T5) |
| **Review actor** | `sdd-verify` post-apply |
| **Archive actor** | orchestrator (post-verify PASS) |
| **Related artifacts** | `exploration.md` (18 secciones, 10 DEC-F3.3-01..10, 8 riesgos R1..R8) · `proposal.md` (16 secciones, 12 DEC-F3.3-01..12 ratified) · `specs/operations/spec.md` (DELTA con 6 new REQ-OPS-119..124) · `design.md` (13 secciones + 2 apéndices, 8 TS mockups + 3 configs delta) |
| **Scope** | Hardening UX kiosko desatendido: `useSesionActiva()` SWR hook reusable (segundo hook genuinely reusable del feature `caja` — forward F4.x/F5.x/F6.x/F7.x/F8.x/F9.x/F10.x/F11.x/F12.x) + `sesionActivaApi` typed wrappers + `AbrirTurno` page+form (RHF+Zod + inputMode=decimal + 409 UX) + `CerrarTurno` page+form placeholder (RHF+Zod + 404 UX + logout implícito) + `Login` MODIFY `?closed=true` detection + `Dashboard` page redirect rule + `TurnoActivoPanel` organism + 3 rutas en `App.tsx` + 12 i18n keys turno en `caja.json` + axe-core WCAG 2.1 AA compliance. NO incluye backend cambios (HU-F1.3 + HU-F1.13 shipped — partial unique index 0023 + `close_session_with_log` + permission `abrir_cerrar_caja`), arqueo completo (Fase 10 HU-F10.x con tolerancia + justificación + alerta `descuadre_critico`), AuthGuard (F3.x+), logout button UI dedicado (F3.x+), multi-sucursal selector (single-branch kiosko per DEC-F3.1-04), toast notifications post-cierre (F11.x usa shadcn Toast). |
| **Dependencies** | F2.1 archivado (Electron scaffold + shadcn Form/Input/Button/Card + i18n namespaces) · F2.2 archivado (parkosFetch + authStore + useAuth + Mutex `refreshAccessToken`) · F2.3 archivado (kiosko mode + StatusBar) · F3.1 archivado (Login + LoginForm + loginApi + ruta `/login`) · F3.2 archivado (useCountdown + 50min refresh + pre-flight gate + `REFRESH_INTERVAL_MS`) · HU-F1.3 shipped Fase 1 (backend `POST /caja-sesion/sesiones` + 409 `sesion_already_active` + partial unique index 0023) · HU-F1.13 shipped Fase 1 (backend `PUT /caja-sesion/sesion/{uuid}/cerrar` + `close_session_with_log` + 404 `sesion_not_found` + permission `abrir_cerrar_caja` per GAP-BE-05) · npm 11.16.0 local Windows + npm sandbox F.6 caveat documentado |

---

## 1. Atomic task cluster (C1 único end-to-end)

F3.3 entrega 5 atomic tasks en orden mandatory con paralelismo donde aplica, organizados en **un solo cluster C1** que cierra el ciclo de vida transaccional del operador kiosko:

```
T1 — useSesionActiva SWR hook + sesionActivaApi typed wrappers + 8 unit tests (U1..U8)
   ↓ (T1 provee hook reusable + API typed)
(T2 || T3 || T4) — AbrirTurno page+form (T2) || CerrarTurno page+form + Login MODIFY (T3) || Dashboard+TurnoActivoPanel+App.tsx (T4)
   ↓ (T2+T3+T4 proveen UI completa + Login detection + rutas)
T5 — e2e turno.spec.ts (E1+E2+E3+A1) + Login U18 test
   ↓ (T5 provee e2e green gate + Login feedback verification)
archive — mover change folder a archive/, update pending.md §1 row F3.3 → ✅
```

**Justificación del single-cluster C1**: la atomicidad del feature (apertura turno + cierre turno + redirect automático + logout implícito + feedback post-cierre + WCAG axe-core) requiere que los 5 tasks se commiteen en orden sin pasos intermedios. Plan.md:1344 verbatim: "260 LOC. 5 tareas atómicas T1..T5". F3.3 NO es divisible en features independientes — un solo cambio funcional que cierra el gating transversal para F4.x+.

**Paralelización intra-cluster**:
- T2, T3, T4 son **parcialmente independientes** (todos consumen T1) — pueden ejecutarse en paralelo si el executor lo permite.
- Recomendación secuencial por dependencia + reduce merge conflicts: **T1 → T4 (Dashboard wire App.tsx) → T2 (AbrirTurno independiente) → T3 (CerrarTurno + Login MODIFY) → T5**.

### §1.1 Dependency graph (ASCII)

```
              ┌──────────────────────────────────────────────────────────┐
              │ HOOK REUSABLE (NEW — DEC-F3.3-04)                       │
              │ apps/electron-sucursal/src/features/caja/hooks/         │
              │ + api/                                                  │
              └──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ T1 useSesionActiva.ts + sesionActivaApi.ts + format.ts  │
              │ ~80 LOC prod + ~60 LOC tests = ~140 LOC                 │
              │ SWR key null + refresh 50min + dedupingInterval 10s     │
              │ + shouldRetryOnError 404 + onError 401 clear            │
              └──────────────────────────────────────────────────────────┘
                                          │
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
    ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
    │ T2 AbrirTurno        │ │ T3 CerrarTurno       │ │ T4 Dashboard +       │
    │ page+form            │ │ page+form + Login    │ │ TurnoActivoPanel +   │
    │ RHF+Zod + 409 UX     │ │ MODIFY ?closed=true  │ │ App.tsx 3 rutas      │
    │ ~100 LOC + ~80 tests │ │ ~65 LOC + ~50 tests  │ │ ~40 LOC + ~50 tests  │
    │ = ~180 LOC           │ │ = ~115 LOC           │ │ = ~90 LOC            │
    └──────────────────────┘ └──────────────────────┘ └──────────────────────┘
                  │                       │                       │
                  └───────────────────────┼───────────────────────┘
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ T5 e2e/caja/turno.spec.ts (E1+E2+E3+A1 axe-core)        │
              │ + Login U18 test consolidates                            │
              │ ~80 LOC e2e SKIPPED-env per Sandbox F.6                  │
              └──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
              ┌──────────────────────────────────────────────────────────┐
              │ archive — mover change folder, update pending.md §1 F3.3│
              └──────────────────────────────────────────────────────────┘
```

### §1.2 Tabla de orden estricto

| Step | Cluster | Task | Cuándo | Acción | Razón orden |
|---|---|---|---|---|---|
| 1 | C1 | **T1** | primera | NEW `useSesionActiva.ts` + `useSesionActiva.test.ts` + `sesionActivaApi.ts` + `sesionActivaApi.test.ts` + `lib/format.ts` (~140 LOC) | DEC-F3.3-04: hook SWR reusable con key null + 50min refresh. T2+T3+T4 consumen el hook. |
| 2 | C1 | **T2** | después T1 (paralelo T3+T4) | NEW `turnoSchema.ts` + `AbrirTurnoForm.tsx` + `AbrirTurno.tsx` + `AbrirTurno.test.tsx` + MODIFY `caja.json` (+6 keys) + MODIFY `vitest.config.ts` (~180 LOC) | DEC-F3.3-01/02: container/presentational + inputMode=decimal + Zod schema. Consume hook T1 + api T1. |
| 3 | C1 | **T3** | después T1 (paralelo T2+T4) | NEW `CerrarTurnoForm.tsx` + `CerrarTurno.tsx` + `CerrarTurno.test.tsx` + MODIFY `Login.tsx` (+5 LOC) + MODIFY `Login.test.tsx` (+10 LOC) + MODIFY `caja.json` (+5 keys) (~115 LOC) | DEC-F3.3-03/06/07: logout implícito post-200 + placeholder arqueo + 404 UX + `?closed=true` detection. Consume hook T1 + api T1. |
| 4 | C1 | **T4** | después T1 (paralelo T2+T3) | NEW `TurnoActivoPanel.tsx` + `TurnoActivoPanel.test.tsx` + `Dashboard.tsx` + `Dashboard.test.tsx` + MODIFY `App.tsx` (+10 LOC) + MODIFY `caja.json` (+1 key) (~90 LOC) | DEC-F3.3-05: Dashboard redirect + TurnoActivoPanel organism + 3 rutas. Consume hook T1. |
| 5 | C1 | **T5** | después T2+T3+T4 | NEW `e2e/caja/turno.spec.ts` (~80 LOC — E1+E2+E3+A1) | e2e requiere AbrirTurno (T2) + CerrarTurno (T3) + Dashboard (T4) + Login ?closed=true (T3) para validar flujo end-to-end. Sandbox F.6 SKIPPED-env (deviation D-env documentada). |

### §1.3 Justificación de orden

- **T1 antes que T2, T3, T4**: los 3 consumers de UI (T2+T3+T4) requieren el hook `useSesionActiva()` + `sesionActivaApi` typed wrappers exportables. Sin T1, T2/T3/T4 tests fallan al no existir el hook ni los wrappers.
- **T2, T3, T4 paralelos** — tocan archivos disjuntos:
  - T2: `features/caja/api/schemas/turnoSchema.ts` + `features/caja/components/AbrirTurnoForm.tsx` + `features/caja/pages/AbrirTurno.tsx` + `caja.json` (+6 keys).
  - T3: `features/caja/components/CerrarTurnoForm.tsx` + `features/caja/pages/CerrarTurno.tsx` + `features/auth/pages/Login.tsx` + `caja.json` (+5 keys).
  - T4: `features/caja/components/TurnoActivoPanel.tsx` + `features/caja/pages/Dashboard.tsx` + `renderer/App.tsx` + `caja.json` (+1 key).
  - Única colisión: `caja.json` MODIFY (T2+T3+T4 agregan keys distintas). Resolución: cada commit agrega su delta; merge trivial (sin overlaps en keys).
- **T2+T3+T4 antes que T5**: T5 e2e valida flujo end-to-end (login → AbrirTurno → CerrarTurno → Login ?closed=true feedback). Sin T2/T3/T4 mergeados, T5 e2e tests no compilan.
- **Single cluster C1 end-to-end**: la atomicidad del feature (apertura turno + cierre turno + redirect automático + logout implícito + feedback post-cierre + WCAG axe-core) requiere que los 5 tasks se commiteen en orden sin pasos intermedios. Plan.md:1344 verbatim: "260 LOC. 5 tareas atómicas T1..T5".

**Precedente inmediato**: F3.2 archivado (`archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/tasks.md`) — 4 atomic tasks T1..T4 con single-cluster C1 end-to-end. F3.3 extiende a 5 tasks (T1..T5) porque Login MODIFY + Dashboard wire App.tsx + e2e scenario son unidades atómicas independientes que merecen su propio commit (work-unit-commits skill: "Tell a story — a reviewer should understand why each commit exists from its diff and message").

---

## 2. Atomic task inventory

### T1 — `useSesionActiva` SWR hook + `sesionActivaApi` typed wrappers (~80 prod + ~60 tests = ~140 LOC)

**Descripción**: Entrega el hook SWR reusable para consultar sesión activa del operador autenticado (segundo hook genuinely reusable del feature `caja` — primer consumer F3.3, forward consumers F4.x+) + los wrappers typed para abrir/cerrar turno con manejo explícito de 404/409. `useSesionActiva(): { sesion, isLoading, error, refresh }` configura SWR con `key: accessToken ? '/caja-sesion/sesion/me' : null` (gate null sin token idéntico F3.1 useAuth), `refreshInterval: REFRESH_INTERVAL_MS = 50min` (F3.2 DEC-SUC-03 heredado verbatim), `dedupingInterval: 10s` (evita refetch simultáneo Dashboard + CerrarTurno), `shouldRetryOnError: (err) => err?.status !== 404` (operador sin turno NO es error — estado válido), `onError` con `status===401` dispara `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` (F2.2 invariant preserved + forward hook AuthGuard F3.x+). `sesionActivaApi` exporta `getSesionActiva()` (404 → null, NO lanza error), `abrirSesion()` (409 → typed `SesionAlreadyActiveError extends ParkosHttpError`), `cerrarSesion()` (404 → typed `SesionAlreadyClosedError`). Types `SesionRead`, `SesionCreate`, `SesionCerrarRequest` derivados de backend Pydantic schemas F1.3 + F1.13 READ ONLY.

**Archivos a crear**:
- `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts` (~25 LOC — `getSesionActiva` + `abrirSesion` + `cerrarSesion` + `SesionAlreadyActiveError` + `SesionAlreadyClosedError` + types `SesionRead`/`SesionCreate`/`SesionCerrarRequest`).
- `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.test.ts` (~40 LOC — U5 getSesionActiva 200, U6 getSesionActiva 404→null, U7 abrirSesion 409 mapping, U8 cerrarSesion 200).
- `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` (~40 LOC — SWR config + `REFRESH_INTERVAL_MS` import + `useAuthStore` selector + onError 401 clear + dispatchEvent).
- `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.test.ts` (~40 LOC — U1 SWR key null sin token, U2 SWR fetch OK, U3 SWR 404→sesion null, U4 SWR 401 dispara `parkos:auth:cleared`).
- `apps/electron-sucursal/src/features/caja/lib/format.ts` (~10 LOC — `formatCOP` helper con `Intl.NumberFormat('es-CO', currency: 'COP', minimumFractionDigits: 0)` + re-export `formatDistanceToNow` + `es` de `date-fns`).

**Archivos a modificar**: (ninguno — T1 es additive puro, consume primitives F2.2+F3.2 READ ONLY).

**Criterio de done**:
- U1..U4 verde en `pnpm vitest run src/features/caja/hooks/useSesionActiva.test.ts --coverage` (≥90% lines, ≥90% functions, ≥85% branches).
- U5..U8 verde en `pnpm vitest run src/features/caja/api/sesionActivaApi.test.ts --coverage` (≥85% lines, ≥85% functions, ≥80% branches).
- `pnpm tsc --noEmit -p tsconfig.renderer.json` clean (zero TS errors en archivos nuevos).
- Coverage thresholds agregados a `apps/electron-sucursal/vitest.config.ts` (cross-ref design §B.1).
- Working tree clean (`git status --short` vacío) post-commit.

**Commit hash esperado**: TBD (sdd-apply will populate) — mensaje: `feat(caja): adicionar useSesionActiva SWR hook + sesionActivaApi typed wrappers (T1)`.

---

### T2 — `AbrirTurno` page + `AbrirTurnoForm` presentational (~100 prod + ~80 tests = ~180 LOC)

**Descripción**: Entrega el formulario de apertura de turno con 3 campos decimales (valor inicial efectivo + valor inicial datáfono + observaciones opcionales). Container `<AbrirTurno>` orquesta RHF + Zod resolver + `useAuth().user.sucursal.uuid` + `useAuth().user.id` + `sesionActivaApi.abrirSesion(payload)` + `useNavigate` + manejo del 409. `<AbrirTurnoForm>` presentational recibe `{form, onSubmit, isSubmitting, error}` via props (F3.1 DEC-F3.1-02 container/presentational split verbatim). Zod schema verbatim plan.md:1338: `z.object({ valor_inicial_efectivo: z.number().min(0), valor_inicial_datafono: z.number().min(0), observaciones: z.string().optional() })`. `<Input type="number" inputMode="decimal" step="0.01">` DEC-F3.3-02 — teclado numérico mobile/electron + WCAG compliant. Submit 200 → `navigate('/')` (replace) + SWR re-fetch automático. Submit 409 → `SesionAlreadyActiveError` → `<FormMessage role="alert">{t('caja.sesionYaAbierta')}</FormMessage>` + `<Button onClick={() => navigate('/')}>{t('caja.irAlTurno')}</Button>`. Validación Zod rechaza `valor_inicial_efectivo < 0` ANTES del POST (defense in depth — no se envía request inválido). También agrega 6 i18n keys a `caja.json`: `abrirTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `observaciones`, `sesionYaAbierta`, `irAlTurno`.

**Archivos a crear**:
- `apps/electron-sucursal/src/features/caja/api/schemas/turnoSchema.ts` (~10 LOC — `abrirTurnoSchema` + `cerrarTurnoSchema` + types `AbrirTurnoInput`/`CerrarTurnoInput`).
- `apps/electron-sucursal/src/features/caja/components/AbrirTurnoForm.tsx` (~50 LOC presentational — `<Form>` wrap + 3 `<FormField>` con `<Input type="number" inputMode="decimal" step="0.01">` + FormMessage + submit Button con `aria-disabled`).
- `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx` (~70 LOC container — RHF + Zod + `useAuth` + `sesionActivaApi.abrirSesion` + error state + `useNavigate`).
- `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.test.tsx` (~50 LOC — U9 submit OK + U10 409 mensaje + U11 validaciones Zod).

**Archivos a modificar**:
- `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (+6 keys — `abrirTurno` + `valorInicialEfectivo` + `valorInicialDatafono` + `observaciones` + `sesionYaAbierta` + `irAlTurno`).
- `apps/electron-sucursal/vitest.config.ts` (+threshold `AbrirTurno.tsx` ≥80% lines).

**Criterio de done**:
- U9..U11 verde en `pnpm vitest run src/features/caja/pages/AbrirTurno.test.tsx --coverage` (≥80% lines, ≥80% functions, ≥75% branches).
- `pnpm tsc --noEmit -p tsconfig.renderer.json` clean.
- `caja.json` snapshot estable con +6 keys (sin regresión de las 10 pre-existentes F2.1).
- `<AbrirTurnoForm>` axe-core 0 violaciones (vitest-axe) — REQ-OPS-124 S3.
- Working tree clean post-commit.

**Commit hash esperado**: TBD (sdd-apply will populate) — mensaje: `feat(caja): adicionar AbrirTurno page+form con RHF+Zod+inputMode decimal (T2)`.

---

### T3 — `CerrarTurno` page + `CerrarTurnoForm` placeholder + `Login` `?closed=true` detection (~60 prod + ~70 tests = ~130 LOC)

**Descripción**: Entrega el formulario placeholder de cierre de turno con 3 campos decimales (valor final efectivo + valor final datáfono + observaciones_cierre opcionales) + el logout implícito post-200 (DEC-F3.3-03) + el feedback `?closed=true` en Login. Container `<CerrarTurno>` lee `sesion.uuid` via `useSesionActiva()` (T1 hook) + RHF+Zod (`cerrarTurnoSchema`) + `sesionActivaApi.cerrarSesion(uuid, payload)`. Submit 200 → **atómico**: `useAuthStore.getState().clear()` (borra accessToken/refreshToken/expiresAt vía IPC `bridge.authStore.delete` per F2.2) + `window.dispatchEvent(new Event('parkos:auth:cleared'))` (forward hook AuthGuard F3.x+) + `navigate('/login?closed=true', { replace: true })`. Submit 404 → `SesionAlreadyClosedError` → `<FormMessage role="alert">{t('caja.sesionYaCerrada')}</FormMessage>` + `navigate('/login')` (sin `?closed=true`). Cancel button → `navigate('/')` sin invocar cerrarSesion. `<CerrarTurnoForm>` presentational lee `sesion` via props (NO consume SWR) + renderiza resumen del turno arriba del form (uuid + timestamp apertura formateado con `formatDistanceToNow` + valores iniciales via `formatCOP`) + botones "Confirmar cierre" + "Cancelar" (`variant="ghost"` → navigate('/')). Adicionalmente MODIFICAR `<Login>` (F3.1, +5 LOC): detecta `useLocation().search.includes('closed=true')` y renderiza `<p role="status" aria-live="polite" data-testid="turno-cerrado-exito">{t('caja.turnoCerradoExito')}</p>` arriba del form (sin reemplazar, F3.1+F3.2 intactos). 5 i18n keys a `caja.json`: `cerrarTurno`, `valorFinalEfectivo`, `valorFinalDatafono`, `turnoCerradoExito`, `confirmarCierre`.

**Archivos a crear**:
- `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx` (~40 LOC presentational — `<Form>` wrap + 3 `<FormField>` numéricos + FormMessage + Cancel button `variant="ghost"` + submit Button).
- `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` (~60 LOC container — `useSesionActiva` + RHF+Zod + `sesionActivaApi.cerrarSesion` + `useAuthStore.clear()` + dispatchEvent + navigate).
- `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.test.tsx` (~40 LOC — U12 submit OK + U13 404 mensaje + U14 useAuthStore.clear post-200).

**Archivos a modificar**:
- `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (+5 LOC — `import { useLocation }` + `const location = useLocation()` + `const showClosedNotice = location.search.includes('closed=true')` + render condicional `<p role="status" aria-live="polite" data-testid="turno-cerrado-exito">{t('caja.turnoCerradoExito')}</p>` arriba del form).
- `apps/electron-sucursal/src/features/auth/pages/Login.test.tsx` (+10 LOC — U18 Login mount con `?closed=true` → `<p data-testid="turno-cerrado-exito">` visible).
- `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (+5 keys — `cerrarTurno` + `valorFinalEfectivo` + `valorFinalDatafono` + `turnoCerradoExito` + `confirmarCierre`).
- `apps/electron-sucursal/vitest.config.ts` (+threshold `CerrarTurno.tsx` ≥80% lines).

**Criterio de done**:
- U12..U14 verde en `pnpm vitest run src/features/caja/pages/CerrarTurno.test.tsx --coverage` (≥80% lines, ≥80% functions, ≥75% branches).
- U18 verde en `pnpm vitest run src/features/auth/pages/Login.test.tsx --coverage` (no regresión F3.1+F3.2 tests pre-existentes).
- `pnpm tsc --noEmit -p tsconfig.renderer.json` clean.
- `useAuthStore.clear()` spy called exactly once post-200 (verificable en U12 con `spyOn(useAuthStore.getState(), 'clear')`).
- `<CerrarTurnoForm>` + Login `?closed=true` axe-core 0 violaciones — REQ-OPS-124 S5 + S2.

**Commit hash esperado**: TBD (sdd-apply will populate) — mensaje: `feat(caja,feat(auth)): adicionar CerrarTurno page+form + Login ?closed=true detection (T3)`.

---

### T4 — `Dashboard` page + `TurnoActivoPanel` organism + rutas en `App.tsx` (~40 prod + ~50 tests = ~90 LOC)

**Descripción**: Entrega el redirect automático al cargar `/` según exista o no sesión activa + el panel legible del turno abierto + las 3 rutas en `App.tsx`. `<Dashboard>` container consume `useSesionActiva()` (T1 hook) + decide atómicamente via `useEffect([sesion, isLoading, error])`: (a) `sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno', { replace: true })` (replace previene back-button infinite loop); (b) `sesion !== null` → renderiza `<TurnoActivoPanel sesion onCerrarClick={() => navigate('/caja/cerrar-turno')} />`; (c) `isLoading === true` → render `<Skeleton>` neutral; (d) `error && status !== 404` → `<Alert variant="destructive">` + retry button. `<TurnoActivoPanel>` organism puramente presentational (NO consume SWR, NO invoca parkosFetch, NO state interno más allá de props) — renderiza `<Card>` shadcn con `<CardTitle>{t('caja.turnoActivo')}</CardTitle>` + `<CardContent>` con `<p>UUID: {sesion.uuid}</p>` (copyable via tooltip) + `<p>Apertura: {formatDistanceToNow(timestamp_apertura, { locale: es, addSuffix: true })}</p>` ("hace 2 horas") + `<p>Valor inicial efectivo: {formatCOP(...)}</p>` + `<p>Valor inicial datáfono: {formatCOP(...)}</p>` + opcional `<p>Observaciones: ...</p>` si truthy + `<CardFooter>` con `<Button onClick={onCerrarClick}>{t('caja.cerrarTurno')}</Button>`. Modificar `App.tsx` para registrar 3 rutas (`/`, `/caja/abrir-turno`, `/caja/cerrar-turno`) — `<Route path="/" element={null} />` (F3.1+F3.2 placeholder) se reemplaza por `<Route path="/" element={<Dashboard />} />`. 1 i18n key a `caja.json`: `turnoActivo`.

**Archivos a crear**:
- `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx` (~30 LOC organism — `<Card>` shadcn + `<CardHeader>`/`<CardTitle>` + `<CardContent>` con 5 `<p>` + `<CardFooter>` con submit Button).
- `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.test.tsx` (~25 LOC — U-T1 render uuid + timestamp + valores + botón, U-T2 omite bloque Observaciones cuando null, U-T3 click button invoca onCerrarClick).
- `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (~30 LOC container — `useSesionActiva` + `useNavigate` + `useEffect` redirect + `Skeleton` durante `isLoading` + error state + render `<TurnoActivoPanel>` condicional).
- `apps/electron-sucursal/src/features/caja/pages/Dashboard.test.tsx` (~25 LOC — U15 redirect abrir-turno sin sesión, U16 render TurnoActivoPanel con sesión, U17 error state con retry).

**Archivos a modificar**:
- `apps/electron-sucursal/src/renderer/App.tsx` (+10 LOC — `import { Dashboard }` + `import { AbrirTurno }` + `import { CerrarTurno }` + 3 `<Route>` nuevos + reemplazo de `<Route path="/" element={null} />`).
- `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (+1 key — `turnoActivo`).
- `apps/electron-sucursal/vitest.config.ts` (+threshold `Dashboard.tsx` ≥80% + `TurnoActivoPanel.tsx` ≥80% lines).

**Criterio de done**:
- U15..U17 + U-T1..U-T3 verde en `pnpm vitest run src/features/caja/pages/Dashboard.test.tsx src/features/caja/components/TurnoActivoPanel.test.tsx --coverage` (≥80% lines, ≥80% functions, ≥75% branches cada uno).
- `pnpm tsc --noEmit -p tsconfig.renderer.json` clean.
- `App.tsx` mantiene F3.1+F3.2 routes intactas (`/login`, `*` NotFound) — sin regresión.
- `<TurnoActivoPanel>` axe-core 0 violaciones (vitest-axe) — REQ-OPS-124 S5.
- Working tree clean post-commit.

**Commit hash esperado**: TBD (sdd-apply will populate) — mensaje: `feat(caja): adicionar Dashboard redirect + TurnoActivoPanel + 3 rutas en App.tsx (T4)`.

---

### T5 — e2e `turno.spec.ts` + Login U18 (~80 e2e SKIPPED-env + ~10 tests unit = ~90 LOC)

**Descripción**: Entrega los escenarios e2e completos del flujo abrir → 409 → cerrar → feedback post-cierre + axe-core A1 test para WCAG 2.1 AA compliance. **SKIPPED-env per Sandbox F.6** — npm 11.16.0 refuses `workspace:*` resolution (precedent F2.1+F2.2+F2.3+F3.1+F3.2 archive verbatim). Unit tests (vitest sobre T1 hook + T1 api + T2 page + T3 page + T4 page mockeando SWR + parkosFetch) cubren el camino crítico. Verify-report documenta D-env deviation. Escenarios: E1 login → redirect automático a `/caja/abrir-turno` → submit OK → redirect a `/` con `TurnoActivoPanel` visible + timestamp "hace 0 minutos"; E2 setup sesión activa + submit → 409 + mensaje "ya tenés un turno abierto" + botón "Ir al turno"; E3 setup sesión activa + submit OK → redirect a `/login?closed=true` con `<p role="status">` visible; A1 axe-core 0 violaciones en AbrirTurno normal + AbrirTurno 409 + CerrarTurno normal + Login `?closed=true` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa`. Adicionalmente T5 también incluye el U18 Login test (que podría commitearse en T3 — pero se consolida aquí para evitar cross-feature file splits, work-unit-commits skill: "Keep tests with code, keep docs with the user-visible change"). Sin embargo, si el executor lo prefiere, U18 puede commit-earse en T3 atomically con Login MODIFY (work-unit flexibility per work-unit-commits skill).

**Archivos a crear**:
- `apps/electron-sucursal/e2e/caja/turno.spec.ts` (~80 LOC — E1 + E2 + E3 + A1 con `_electron.launch` per F2.1 baseline + `page.route` mocks para POST `/caja-sesion/*` + axe-core via `@axe-core/playwright`).

**Archivos a modificar**: (ninguno — T5 es additive puro e2e. U18 Login test consolidates in T3 per above).

**Criterio de done**:
- T5 e2e **SKIPPED-env** documentado en `verify-report.md` (D-env deviation) — sandbox F.6 npm 11.16.0 refuses workspace:*.
- Working tree clean post-commit.
- Conventional commit `test(electron): adicionar 4 e2e turno (abrir OK + 409 + cerrar OK + axe-core) (T5)`.
- Si executor decide consolidar U18 en T3, NO se duplica acá — único commit atómico por work unit.

**Commit hash esperado**: TBD (sdd-apply will populate) — mensaje: `test(electron): adicionar 4 e2e turno (abrir OK + 409 segundo intento + cerrar OK + axe-core A1) (T5)`.

---

## 3. Acceptance gates (G1..G7)

Cross-ref `proposal.md §6` + `design.md §13` + `exploration.md §9` + `spec.md §5` verbatim. Mapeo de gates a tests verificables:

| Gate | Task | Mechanism | File | Verification command |
|---|---|---|---|---|
| **G1** | T1 | vitest unit (`useSesionActiva` SWR con key null sin token + refreshInterval 50min + 404 null + 401 clear) + `sesionActivaApi` typed wrappers (200/404/409 mapping) | `useSesionActiva.test.ts` U1..U4 + `sesionActivaApi.test.ts` U5..U8 | `pnpm vitest run src/features/caja/hooks/useSesionActiva.test.ts src/features/caja/api/sesionActivaApi.test.ts --coverage` |
| **G2** | T2 | vitest unit (`AbrirTurno` form submit OK + 409 `sesion_already_active` UX + validaciones Zod) | `AbrirTurno.test.tsx` U9..U11 | `pnpm vitest run src/features/caja/pages/AbrirTurno.test.tsx --coverage` |
| **G3** | T3 | vitest unit (`CerrarTurno` form submit OK + 404 `sesion_not_found` UX + `useAuthStore.clear()` post-200) | `CerrarTurno.test.tsx` U12..U14 | `pnpm vitest run src/features/caja/pages/CerrarTurno.test.tsx --coverage` |
| **G4** | T4 | vitest unit (`Dashboard` redirect rule + `TurnoActivoPanel` organism + App.tsx routes) | `Dashboard.test.tsx` U15..U17 + `TurnoActivoPanel.test.tsx` U-T1..U-T3 | `pnpm vitest run src/features/caja/pages/Dashboard.test.tsx src/features/caja/components/TurnoActivoPanel.test.tsx --coverage` |
| **G5** | T1 (hook SWR) | **Hard requirement** — `useSesionActiva()` SWR key MUST ser `null` cuando `useAuthStore.accessToken === null` (GATE NO — NO 401 noise on cold boot antes de login) | `useSesionActiva.test.ts` U1 | `pnpm vitest run src/features/caja/hooks/useSesionActiva.test.ts` |
| **G6** | T3 (Login MODIFY) | **Hard requirement** — `?closed=true` feedback MUST renderizarse con `role="status"` + `aria-live="polite"` (WCAG 2.1 AA axe-core compliant, patrón F3.2 REQ-OPS-118 verbatim) | `Login.test.tsx` U18 + axe-core unit | `pnpm vitest run src/features/auth/pages/Login.test.tsx --coverage` + axe-core scan |
| **G7** | T2 + T3 + T4 (axe-core WCAG 2.1 AA) | **Hard requirement** — axe-core 0 violaciones en `<AbrirTurno>` (estado normal + 409) + `<CerrarTurno>` (estado normal + 404) + `<TurnoActivoPanel>` (con/sin observaciones) + Login (`?closed=true` state) — REQ-OPS-124 RNF-022 + REQ-OPS-112 F3.1 + REQ-OPS-118 F3.2 precedent | `AbrirTurno.test.tsx` (vitest-axe) + `CerrarTurno.test.tsx` (vitest-axe) + `TurnoActivoPanel.test.tsx` (vitest-axe) + `Login.test.tsx` (vitest-axe) + e2e A1 (playwright axe-core) | `pnpm vitest run <all 4 files> && pnpm playwright test e2e/caja/turno.spec.ts` |

**Estado pre-flight target**: 0/7 PASS al inicio; **7/7 PASS** post-implementación en local dev (Windows native npm 11.16+) o CI matrix con image compatible.

**Sandbox F.6 caveat**: e2e G7-A1 SKIPPED en sandbox F.6 (npm 11.16.0 refuses workspace:*). Vitest-axe unit tests G7 corren localmente con mocks (no requieren workspace resolution post-install) — estos sí corren localmente. Documentado en §6 DoD.

---

## 4. Review Workload Forecast

**LOC budget breakdown** (suma de T1..T5 per task specs):

| Task | Prod LOC | Unit tests LOC | E2E LOC | Total |
|---|---|---|---|---|
| T1 (`useSesionActiva` + `sesionActivaApi` + `format.ts`) | ~80 | ~60 | 0 | ~140 |
| T2 (`AbrirTurno` + `AbrirTurnoForm` + `turnoSchema`) | ~100 | ~80 | 0 | ~180 |
| T3 (`CerrarTurno` + `CerrarTurnoForm` + Login MODIFY) | ~60 + Login +5 = ~65 | CerrarTurno 40 + Login 10 = ~50 | 0 | ~115 (ajustado del estimado 130; Login +5 prod ya consolidado en T3) |
| T4 (`Dashboard` + `TurnoActivoPanel` + App.tsx) | ~40 | ~50 | 0 | ~90 |
| T5 (e2e + axe-core A1) | 0 | 0 | ~80 | ~80 |
| **TOTAL** | **~285** | **~240** | **~80** | **~605** |

**Verdict**: **~605 LOC total** (production 285 + unit 240 + e2e 80 + Login U18 unit ~10 + i18n keys + coverage thresholds configs ~30 LOC delta) ≈ **~650 LOC delta total**. **DEBAJO del budget 800 LOC per `config.yaml rules.tasks`**.

**Comparación con presupuesto plan.md**: plan.md:1344 verbatim "260 LOC" — F3.3 sobreexcede ese presupuesto en ~2.5x porque incluye tests + e2e + 3 archivos MODIFY. Sin embargo, `config.yaml rules.tasks` establece budget 800 LOC por HU/change (cross-ref `pending.md §4`), y **F3.3 está cómodamente debajo**.

**¿Split required?**: **NO**. ~650 LOC está bien dentro del budget 800. Cero necesidad de chained PR slice per `work-unit-commits` skill ("Low risk: keep work-unit commits inside one PR"). Single PR con 5 atomic commits T1..T5 es la estrategia óptima.

**Nota sobre cálculo del user**: el prompt inicial mencionó "~860 LOC (slightly over 800 budget)" pero la suma aritmética de los LOC per-task T1..T5 da ~605-650 LOC. La diferencia se debe a que el user probablemente incluyó configs (vitest coverage thresholds), i18n keys delta, y cabeceras/imports que no son LOC "authored" per se. Usé el número honesto (~650 LOC) en este tasks.md para no inflar el budget artificialmente. **Si el apply phase ejecuta `git diff --stat` y observa >800 LOC, debe revisar si hay overhead no-planeado (probablemente `format.ts` o `turnoSchema.ts` que son shared utilities, no core feature LOC)**.

---

## 5. Delivery strategy alignment

Cross-ref `work-unit-commits` skill + `sdd-apply` SDD workflow + `plan.md:1319` + precedent F3.2 archivado verbatim.

**Delivery strategy**: **Single PR con 5 atomic commits** (chained PR slice NO requerida — dentro del budget 800 LOC).

**Work-unit commit strategy** (per work-unit-commits skill "Tell a story"):

1. **Commit T1** (`feat(caja)`) — `useSesionActiva` SWR hook + `sesionActivaApi` typed wrappers + 8 unit tests. **Work unit**: hook SWR reusable + API typed. Reviewable standalone. Rollback: `git revert <T1-commit>` elimina hook — F3.3 entero bloqueado (sin hook, T2-T5 no funcionan).
2. **Commit T2** (`feat(caja)`) — `AbrirTurno` page + `AbrirTurnoForm` presentational + 3 unit tests + 6 i18n keys. **Work unit**: pantalla de apertura + 409 UX + Zod validations. Reviewable standalone. Rollback: `git revert <T2-commit>` — operador no puede abrir turno (regresión a F3.2 pre-F3.3 behavior — T1 hook queda huérfano pero no rompe login).
3. **Commit T3** (`feat(caja)` + `feat(auth)`) — `CerrarTurno` page + `CerrarTurnoForm` placeholder + Login `?closed=true` MODIFY + 3 unit tests + 5 i18n keys. **Work unit**: pantalla de cierre + logout implícito + feedback post-cierre. Rollback: `git revert <T3-commit>` — operador no puede cerrar turno limpiamente (queda logged-in sin sesión activa — regresión temporal).
4. **Commit T4** (`feat(caja)`) — `Dashboard` page + `TurnoActivoPanel` organism + `App.tsx` MODIFY + 6 unit tests + 1 i18n key. **Work unit**: redirect automático `/` según sesión activa + rutas. Rollback: `git revert <T4-commit>` — operador kiosko ve pantalla vacía en `/` (regresión a pre-F3.3 F3.1+F3.2 behavior).
5. **Commit T5** (`test(electron)`) — e2e `turno.spec.ts` (4 scenarios + axe-core A1). **Work unit**: tests e2e end-to-end del flujo. Rollback: `git revert <T5-commit>` — e2e tests removed pero unit tests siguen verdes (defensa en profundidad sin e2e sandbox F.6 caveat).

**Conventional commits** (per F2.1 + F3.1 + F3.2 precedent):

| Commit | Type | Scope | Mensaje |
|---|---|---|---|
| T1 | `feat` | `caja` | `feat(caja): adicionar useSesionActiva SWR hook + sesionActivaApi typed wrappers (T1)` |
| T2 | `feat` | `caja` | `feat(caja): adicionar AbrirTurno page+form con RHF+Zod+inputMode decimal (T2)` |
| T3 | `feat` | `caja,auth` | `feat(caja,auth): adicionar CerrarTurno page+form + Login ?closed=true detection (T3)` |
| T4 | `feat` | `caja` | `feat(caja): adicionar Dashboard redirect + TurnoActivoPanel + 3 rutas en App.tsx (T4)` |
| T5 | `test` | `electron` | `test(electron): adicionar 4 e2e turno (abrir OK + 409 segundo intento + cerrar OK + axe-core A1) (T5)` |

**NO** `Co-authored-by` trailer (F2.1 canon — `git log --format='%(trailers)' --grep='Co-authored-by'` debe retornar vacío post-apply). **NO** AI attribution (per persona rules + canon de la organización).

**PR target**: `origin/dev` per `AGENTS.md` gitflow authorization model. PRs mergean a `dev` (nunca directo a `main`); cada rama certificada se mergea a `dev`, y de `dev` a `main` solo via release branch con certificación.

**Author identity** (per `AGENTS.md` §Git identity for sub-agent work): sub-agent runs set `user.name=gentle-ai-sub-agent, user.email=sub-agent@local`. Para evitar `Co-authored-by: gentle-ai-sub-agent <sub-agent@local>` trailer automático en squash merge, set neutral identity BEFORE merging: `git config user.name "Parkos Dev"` + `git config user.email "dev@parkos.local"`.

---

## 6. DoD checklist

Cross-ref `proposal.md §16.4` + `design.md §11.5` + `exploration.md §13` + F3.2 precedent verbatim.

- [ ] **5 atomic commits T1..T5** con author `Parkos Dev <dev@parkos.local>` (verificado via `git log --format='%an <%ae>'`).
- [ ] **NO Co-authored-by, NO AI trailers** en los 5 commits (verificado via `git log --format='%(trailers)'`).
- [ ] **Conventional commits** neutrales español: `feat(caja)` × 3 + `feat(caja,auth)` × 1 + `test(electron)` × 1.
- [ ] **`pnpm vitest --run` verde** en archivos nuevos: `useSesionActiva.test.ts` + `sesionActivaApi.test.ts` + `AbrirTurno.test.tsx` + `CerrarTurno.test.tsx` + `Dashboard.test.tsx` + `TurnoActivoPanel.test.tsx` + `Login.test.tsx` (U18).
- [ ] **`pnpm tsc --noEmit -p tsconfig.renderer.json` clean** en archivos nuevos (zero TS errors).
- [ ] **axe-core 0 violaciones WCAG 2.1 AA** en `<AbrirTurno>` + `<CerrarTurno>` + `<TurnoActivoPanel>` + Login `?closed=true` state (G7 REQ-OPS-124 RNF-022 — vitest `vitest-axe` matcher).
- [ ] **e2e T5 SKIPPED-env** documentado (verify-report.md D-env — sandbox F.6 npm 11.16.0 refuses workspace:*).
- [ ] **No regresiones en suite Fase 2 + F3.1 + F3.2** (F2.1+F2.2+F2.3+F3.1+F3.2 e2e siguen verdes post-merge F3.3).
- [ ] **Coverage thresholds** cumplidos: `useSesionActiva.ts` ≥90% + `sesionActivaApi.ts` ≥85% + `AbrirTurno.tsx` ≥80% + `CerrarTurno.tsx` ≥80% + `Dashboard.tsx` ≥80% + `TurnoActivoPanel.tsx` ≥80% (vitest --coverage).
- [ ] **CERO `any`** introducido en código nuevo (TS strict + lint).
- [ ] **Working tree clean post-apply** (`git status --short` retorna vacío post-archive).
- [ ] **`caja.json` snapshot estable** con +12 keys turno (`abrirTurno` + `cerrarTurno` + `valorInicialEfectivo` + `valorInicialDatafono` + `valorFinalEfectivo` + `valorFinalDatafono` + `observaciones` + `sesionYaAbierta` + `sesionYaCerrada` + `turnoCerradoExito` + `confirmarCierre` + `irAlTurno` + `turnoActivo`) — snapshot test verde, sin regresión de las 10 keys pre-existentes F2.1.
- [ ] **`pending.md` §1 row F3.3 → ✅ cerrado** (archive phase post-verify).
- [ ] **`openspec/specs/operations/spec.md` REQ-OPS-119..124 mergeados** (post-archive byte count incrementado, numeración monotónica verificada 118 → 119..124).
- [ ] **i18n namespaces consistentes** — 0 nuevos namespaces; todas las keys viven en `caja.json` (F2.1 DEC-ELEC-06 verbatim — un namespace por bounded context).

---

## 7. Forward hooks (qué consumer Fase 4+ va a leer)

Cross-ref `proposal.md §14` + `design.md §15.2` + `exploration.md §6.4` verbatim.

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.x** (AuthGuard component) | `<AuthGuard>` intercepta `parkos:auth:cleared` window event → `navigate('/login?next=...')` | F3.3 dispatch event verbatim en T3 (`CerrarTurno.handleSuccess` post-200) |
| **HU-F3.x** (Logout button UI) | Botón dedicado invoca `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` + `navigate('/login')` | F3.3 pattern reusable — copy verbatim de T3 `handleSuccess` |
| **HU-F4.x** (catálogos + ocupación) | `useSesionActiva()` para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario` | F3.3 export hook desde `features/caja/hooks/useSesionActiva.ts` (T1) |
| **HU-F5.x** (facturación) | `useSesionActiva()` + pre-flight gate automático (`/facturacion/*` ya cubierto F3.2 — NO extension F3.3 per DEC-F3.3-10) | F3.3 hook reusable; F3.2 pre-flight inherit |
| **HU-F6.x** (ingreso vehicular) | `useSesionActiva()` + `sesion.uuid` para FK en `ingreso` | F3.3 hook + `SesionRead.uuid` (T1 typed wrappers) |
| **HU-F7.x** (salida + cálculo) | `useSesionActiva()` para validar sesión activa pre-cálculo | F3.3 hook |
| **HU-F8.x** (cobro + FE) | `useSesionActiva()` + pre-flight gate (ya cubierto F3.2) | F3.3 hook + F3.2 pre-flight |
| **HU-F9.x** (suscripciones) | `useSesionActiva()` para suscripciones recurrentes | F3.3 hook |
| **HU-F10.x** (arqueos completos) | `CerrarTurno` placeholder → flujo completo con `POST /caja/arqueo` + tolerancia + justificación + alerta `descuadre_critico` | F3.3 marca placeholder (T3), F10.x completa |
| **HU-F11.x** (sync UI + alertas) | `useSesionActiva()` para alertas per-turno + shadcn Toast component para post-cierre (F3.3 usa `<p role="status">` simple, F11.x lo upgrade a Toast) | F3.3 hook + forward Toast post-cierre feedback |
| **HU-F12.x** (reportería) | `useSesionActiva()` + queries a `prod.sesion_v_resumen` view | F3.3 hook |
| **PR7 backend** (refresh-token rotation) | `useAuthStore.clear()` post-cierre + `parkos:auth:cleared` event → backend detects `jti` reuse y revoca cadena | F3.3 emite el evento; PR7 backend integra detection |

**Gating transversal confirmado**: F3.3 es prerequisite para **F4.x, F5.x, F6.x, F7.x, F8.x, F9.x, F10.x, F11.x, F12.x**. Sin F3.3, ninguna HU downstream puede arrancar — `pending.md §5` forward hooks explícitos: "F3.3 prerequisite para F4.x+". Hook `useSesionActiva()` es el single source of truth para "existe sesión activa?" a través de toda la Fase 4+.

---

## CHANGELOG

- (2026-09-15) **F3.3 tasks phase complete** — 5 atomic tasks T1..T5 across 1 cluster C1 (turno end-to-end, orden interno T1 → (T2 || T3 || T4) → T5). ~650 LOC total (production 285 + unit tests 240 + e2e 80 + i18n keys + coverage configs ≈ 30 LOC delta). 7 acceptance gates G1..G7 (G1 hook+api U1..U8, G2 AbrirTurno U9..U11, G3 CerrarTurno U12..U14, G4 Dashboard+TurnoActivoPanel U15..U17+U-T1..U-T3, G5 SWR key null hard requirement, G6 `?closed=true` aria-live polite hard requirement, G7 axe-core WCAG 2.1 AA 0 violaciones hard requirement). 12 DEC-F3.3-01..12 ratified (cross-ref proposal §4 + exploration §7 + design §5). 6 new REQ-OPS-119..124 user-facing (DEC-F3.3-11 + DEC-F3.3-12 DELTA verdict — F3.3 ES user-facing precedent F1.15 + F3.1 + F3.2 verbatim). T1 entrega `useSesionActiva` segundo hook genuinely reusable del feature `caja` (forward F4.x+). T2 entrega AbrirTurno form + 409 UX + Zod validations. T3 entrega CerrarTurno placeholder + logout implícito post-200 + Login `?closed=true` detection. T4 entrega Dashboard redirect + TurnoActivoPanel + 3 rutas en App.tsx. T5 entrega e2e turno scenario + axe-core A1 (SKIPPED-env per F2.1+F3.1+F3.2 precedent — sandbox F.6 npm 11.16.0 refuses workspace:*). Single-PR strategy (NO chained slice needed — ~650 LOC debajo del budget 800 per `config.yaml rules.tasks`). Sandbox F.6 caveat documentado (e2e G7-A1 SKIPPED local, CI matrix required). Plan 260 LOC production matches verbatim + tests overhead. Ready for `sdd-apply`.

---

**End of tasks — HU-F3.3.**