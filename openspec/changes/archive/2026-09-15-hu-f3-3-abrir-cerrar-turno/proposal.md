# Proposal — HU-F3.3 Abrir y cerrar turno (caja-sesion con valor_inicial_efectivo/datafono + arqueo inline placeholder + redirect según sesión activa)

> **Change**: `hu-f3-3-abrir-cerrar-turno` · **Folder**: `openspec/changes/hu-f3-3-abrir-cerrar-turno/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` (paralelo)
> **HU ID**: HU-F3.3 (Fase 3 — tercera HU; Autenticación y turno de caja, primer consumer transversal de `caja-sesion`)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-3-turno` (HEAD `fde9850`, F3.1 + F3.2 archivados 2026-09-15 con 7 REQ-OPS-106..112 + 6 REQ-OPS-113..118; F3.3 se commitea sobre la misma rama per `pending.md:6`) · **PR target**: `origin/dev`
> **Inputs**: `plan.md` lines 1327-1352 (HU-F3.3 verbatim, 260 LOC, 5 tareas atómicas T1..T5); `plan.md:418` (DEC-SUC-03 — "Refresh transparente cada 50 minutos y antes de escrituras críticas (pago, arqueo)"); `plan.md:1274-1324` (HU-F3.1 + F3.2 archivados — precedentes + `LoginForm` + `useCountdown` + `REFRESH_INTERVAL_MS` + `parkosFetch` pre-flight gate); `pending.md §1 row 3` (F3.3 = 260 LOC, depende F3.1); `pending.md §5` (forward hooks F4/F5/F6/F7/F8/F10/F11/F12); `openspec/changes/hu-f3-3-abrir-cerrar-turno/exploration.md` (input de explore phase — Engram #1684, ~580 LOC, 18 secciones, 10 DEC-F3.3-01..10, 8 riesgos R1..R8, 6 acceptance gates G1..G6, 5 atomic tasks T1..T5, pre-flight 10/10 PASS + 0 KNOWN-MISSING); `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/{exploration.md,proposal.md,specs/operations/spec.md,tasks.md,verify-report.md,archive-report.md}` (precedente verbatim 16 secciones + 6 REQ-OPS-113..118 user-facing DELTA + DEC-F3.2-08/11 verdict — F3.3 replica el precedent con 6 REQ-OPS-119..124); `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` (precedente verbatim 18 secciones + 7 REQ-OPS-106..112 user-facing DELTA); `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/exploration.md` (backend arqueo precedent — DEC-ARQUEO-01 single-commit + KD-ARQUEO-02/03/04/05 + permission GAP-BE-05); `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/exploration.md` (sesion backend precedent — partial unique index 0023 + `GET /caja-sesion/sesion/me` route ordering literal-path-first + KD-1 409 mapping); `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:73-243` (POST /sesiones + PUT /sesion/{uuid}/cerrar + GET /sesion/me + GET /arqueos/{uuid}/diferencias — routes ya shipped por F1.3 + F1.13); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:188-356` (open_session + close_session_with_log + SesionAlreadyActive + SesionAlreadyActive mapping 23505 → 409); `backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py:26-45` (get_sesion_activa helper); `backend/packages/parkos_core/src/parkos_core/schemas/caja.py:176-258` (SesionRead + SesionCreate + SesionUpdate + SesionReadList); `backend/packages/parkos_core/src/parkos_core/exceptions.py` (SesionAlreadyActive); `backend/packages/parkos_core/migrations/versions/0023_*` (partial unique index prod.uq_prod_sesion_one_active_per_user); `modelo_datos_er.mmd`: sesion [L-S] + arqueo [A] + tipo_arqueo [V] + alerta [L-W] + configuracion_tolerancias [V] + factura_pagos [A] (ya entregados F1.3 + F1.13); `apps/electron-sucursal/src/features/auth/{pages/Login.tsx, components/LoginForm.tsx, hooks/useCountdown.ts, api/loginApi.ts}` (F3.1+F3.2 precedent — container/presentational + RHF+Zod + countdown); `apps/ui-kit/src/{fetch/parkosFetch.ts:47-77 (PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/ — F3.3 NO requiere extender, /caja-sesion/* fuera del gate), hooks/useAuth.ts:31 (REFRESH_INTERVAL_MS = 50*60*1000), store/authStore.ts:100-128 (refreshAccessToken Mutex)}`; `apps/electron-sucursal/src/renderer/{App.tsx:1-41 (Routes actuales: `/` + `/login` + `*` — F3.3 agrega `/caja/abrir-turno` + `/caja/cerrar-turno`), i18n/locales/caja.json:1-12 (10 keys pre-existentes: abrir/cerrar/montoInicial/montoFinal/diferencia/arqueo/movimiento/ingreso/egreso/motivo — F3.3 extiende ~12 keys turno), components/ui/{form,input,button}.tsx (shadcn primitives F2.1)}`; `docs/01-requisitos/no-funcionales.md:126` (RNF-022 WCAG 2.1 AA — applies a todo flujo transaccional).

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F3.3 |
| **Fase** | 3 (Autenticación y turno de caja — tercera HU) |
| **Change name** | `hu-f3-3-abrir-cerrar-turno` |
| **Folder** | `openspec/changes/hu-f3-3-abrir-cerrar-turno/` |
| **State** | proposed (ready for design + spec) |
| **Branch** | `feat/fase-3-turno` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | F3.2 archivado 2026-09-15 (Lockout countdown + refresh 50min + pre-flight gate, 4 commits `850ed70..e3e04ac`, 6 REQ-OPS-113..118 user-facing DELTA — segundo DELTA en Fase 3) |
| **Próximo phase** | sdd-spec + sdd-design (paralelo) |
| **Language** | español neutro profesional |
| **Conventional commits** | `feat(caja)` / `feat(auth)` / `test(electron)` — sin Co-authored-by |
| **DEC-F3.3-08 + DEC-F3.3-12 verdict** | **DELTA** (NOT NO-OP) — F3.3 ES user-facing behavior observable: pantalla AbrirTurno + CerrarTurno + TurnoActivoPanel + redirect `/` según sesión activa + manejo 404 `sesion_already_closed` |

---

## 1. Resumen ejecutivo

**Title**: "Abrir turno de caja con `valor_inicial_efectivo` + `valor_inicial_datafono` (decimales ≥0) vía `POST /caja-sesion/sesiones` + consultar sesión activa vía `GET /caja-sesion/sesion/me` + cerrar turno con arqueo inline (placeholder, completo en Fase 10) vía `PUT /caja-sesion/sesion/{uuid}/cerrar` + redirect según exista sesión activa al cargar `/` + manejo de 409 `sesion_ya_abierta` y 404 `sesion_already_closed` con mensajes i18n claros + logout implícito post-cierre + feedback `?closed=true` en `/login`".

**Goal — el problema que F3.3 cierra**: F3.1 archivado entrega login + cookie httpOnly + hidratación `useAuth()` con `user.sucursal` + `permisos[]` resueltos. F3.2 archivado entrega lockout countdown + refresh 50min + pre-flight gate para POST `/facturacion/*` y `/caja/arqueo*`. Sin embargo, **ningún flujo operativo puede correr sin turno abierto** — un operador autenticado sin sesión de caja no puede facturar, cobrar, ni cerrar caja. F3.3 entrega el flujo end-to-end de apertura y cierre de turno: dos páginas (AbrirTurno, CerrarTurno) + un hook SWR (`useSesionActiva`) + redirección automática al cargar `/` según exista o no sesión activa + manejo tipado de los 409 que la partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023) y la trigger `ls_session_guard` emiten.

**Goal — la solución propuesta**: F3.3 entrega cinco deliverables end-to-end verificables: (1) `useSesionActiva()` hook reusable con SWR key `accessToken ? '/caja-sesion/sesion/me' : null`, `refreshInterval: REFRESH_INTERVAL_MS = 50min` (F3.2 DEC-SUC-03 heredado), `shouldRetryOnError` excluye 404 (esperado sin sesión), `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event; (2) `AbrirTurno` page container + `AbrirTurnoForm` presentational con RHF + Zod (`valor_inicial_efectivo: z.number().min(0)`, `valor_inicial_datafono: z.number().min(0)`, `observaciones: z.string().optional()`), submit → `parkosFetch<SesionRead>('/caja-sesion/sesiones', {method:'POST', body: {...}})`, 409 `sesion_already_active` → mensaje "ya tenés un turno abierto" + botón "Ir al turno"; (3) `CerrarTurno` page container + `CerrarTurnoForm` presentational con form placeholder para `valor_final_efectivo/datafono`, submit → `PUT /caja-sesion/sesion/{uuid}/cerrar`, 200 → `useAuthStore.clear()` (logout implícito) + `navigate('/login?closed=true')`, 404 → mensaje "esta sesión ya está cerrada" + redirect a login; (4) `Dashboard` page container + `TurnoActivoPanel` presentational en `/` que decide redirect según `useSesionActiva()`: si no hay sesión activa → `navigate('/caja/abrir-turno')`; si hay sesión → renderiza `<TurnoActivoPanel>` con resumen + botón "Cerrar turno"; (5) `Login` page detecta `?closed=true` query param y muestra `<p role="status">{t('caja.turnoCerradoExito')}</p>` arriba del form (forward F11.x usa shadcn toast component para notificación más visible). El escenario e2e `apps/electron-sucursal/e2e/caja/turno.spec.ts` cubre 4 escenarios (abrir OK + 409 segundo intento + cerrar OK + axe-core A1).

**Impacto transversal — por qué importa a Fase 4+**: F3.3 cierra el ciclo de vida transaccional del kiosko desatendido. Cinco factores elevan su criticidad:

1. **Gating de TODAS las CU operativas**: CU-01 (ingreso), CU-02/03 (salida+cálculo), CU-04/05 (cobro+FE), CU-06 (suscripciones), CU-10 (arqueo) requieren `uuid_sucursal` de la sesión activa + estado consistente del turno. Sin F3.3, F4.x/F5.x/F6.x/F8.x/F9.x/F10.x quedan bloqueadas — `pending.md §5` forward hooks explícitos.
2. **Defense in depth DB-level (F1.3)**: la partial unique index `prod.uq_prod_sesion_one_active_per_user` garantiza a nivel BD que un mismo `uuid_usuario` no tenga DOS filas con `timestamp_cierre IS NULL`. El frontend DEBE reflejar esto con 409 `sesion_ya_abierta` mapeado a UX claro ("ya tenés un turno abierto") en vez de 500 genérico.
3. **UX transaccional kiosko desatendido**: el operador kiosko no navega entre rutas manualmente — llega al terminal, hace login (F3.1), y DEBE ser redirigido automáticamente a AbrirTurno si no hay sesión activa. Si llega a `/` sin turno, ve pantalla vacía y se confunde. F3.3 implementa el redirect con `useSesionActiva` SWR.
4. **PRE_FLIGHT_PATHS NO requiere extensión F3.3**: `parkosFetch.ts:47` matchea `/facturacion/*` + `/caja/arqueo`. Las rutas `/caja-sesion/*` (apertura/cierre) NO son critical-path per DEC-SUC-03 — un 401 mid-write en apertura es aceptable porque `handle401` retry-once cubre. F3.3 NO modifica `PRE_FLIGHT_PATHS` (DEC-F3.3-10 confirma).
5. **Inmutable model + log-first invariant**: `prod.sesion` [L-S] es INSERT-only con UN controlled UPDATE via `close_session_with_log` (que co-INSERTa `log_transaccional` ANTES del UPDATE porque la trigger `ls_session_guard` rechaza UPDATE sin log). El frontend NO necesita conocer la trigger — pero SÍ debe esperar el redirect post-200 porque el backend emite `SesionRead` con `timestamp_cierre` poblado antes de retornar.

**Hard constraints** (mirrored from `plan.md:1331-1340` verbatim):

- `POST /caja-sesion/sesiones` con `valor_inicial_efectivo` + `valor_inicial_datafono` (decimales ≥0). Si ya hay sesión abierta para el usuario → 409 `sesion_ya_abierta` con mensaje claro.
- `GET /caja-sesion/sesion/me` resuelve dashboard con resumen del turno cuando hay sesión abierta. NO redirige a AbrirTurno.
- Cierre de turno con `tipo_arqueo='cierre_turno'` + `PUT /caja-sesion/sesion/{uuid}/cerrar` → 200 + redirect a login o "turno cerrado".
- Validación Zod: `z.object({ valor_inicial_efectivo: z.number().min(0), valor_inicial_datafono: z.number().min(0), observaciones: z.string().optional() })`.
- Componentes: `AbrirTurno` (page, `inputMode="decimal"` en los campos numéricos), `CerrarTurno` (page, arqueo inline placeholder), `useSesionActiva` (hook, SWR).
- e2e: `e2e/turno.spec.ts` — abrir, intentar un segundo → 409, cerrar, ver resumen.
- Tamaño: 260 LOC. 5 tareas atómicas T1..T5.

**Scope**: ~260 LOC production + ~250 LOC tests + configs = ~510 LOC total. Plan 260 LOC matches verbatim.

**Numeración REQ-OPS verificada**: el último REQ-OPS vigente en `operations/spec.md` es REQ-OPS-118 (F3.2 archivado 2026-09-15). F3.3 ocupa **REQ-OPS-119..124** (6 new requirements, continuación monotónica). Numeración monotónica verificada: 118 → 119 → 120 → 121 → 122 → 123 → 124 (0 gaps, sin duplicados).

**Por qué importa a nivel spec (re-evaluación crítica desde exploration §1)**: al igual que F3.1 (login) + F3.2 (lockout countdown), F3.3 ES user-facing behavior observable — cuatro dimensiones: (a) pantalla AbrirTurno con campos decimales `inputMode="decimal"` + RHF+Zod (form visible + interacción); (b) pantalla CerrarTurno con form placeholder + RHF+Zod + submit PUT (form visible + interacción); (c) Dashboard `/` con redirect automático según sesión activa (navegación observable); (d) TurnoActivoPanel con resumen del turno abierto + botón "Cerrar turno" (visualización observable); (e) 409 `sesion_already_active` → UX "ya tenés un turno abierto" (error visible); (f) WCAG 2.1 AA axe-core 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel (a11y compliance). Esta behavior visible al usuario NO puede vivir solo en DEC-F3.3-NN dentro de `proposal.md` — debe anclarse en REQ-OPS-NNN dentro del spec canónico `operations/spec.md` para que sea verificable, auditable y refactorizable. Precedent directo: F1.15 (4 new REQ-OPS-102..105), F3.1 (7 new REQ-OPS-106..112), F3.2 (6 new REQ-OPS-113..118). F3.3 emite 6 new REQ-OPS-119..124 user-facing — sigue el precedent DELTA. Ver `DEC-F3.3-08` y `DEC-F3.3-12` en §4 para el rationale completo.

---

## 2. Contexto y motivación

### 2.1 Pain points UX que F3.3 cierra

Cuatro user-facing pain points rompen la promesa "kiosko desatendido" del `plan.md:418` (DEC-SUC-03). F3.3 mitiga los cuatro.

**Pain #1 — Sin turno, no hay operación**: cuando el operador termina login (F3.1) y ve el Dashboard `/`, recibe una pantalla vacía (sin resumen, sin acciones). No sabe si debe abrir turno, cerrar turno, o si hay un bug. F3.3 entrega `useSesionActiva()` SWR + `Dashboard` container con redirect automático: si no hay sesión activa → `navigate('/caja/abrir-turno')`; si hay sesión → renderiza `<TurnoActivoPanel>` con resumen. Operador kiosko llega al terminal → login → automáticamente al estado correcto. Cero clics extra.

**Pain #2 — 409 `sesion_already_active` genérico confunde operador**: la partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023) garantiza BD-level rejection. Pero si el frontend surfacea el 409 como un error genérico "Algo salió mal", el operador no entiende. F3.3 mapea `SesionAlreadyActiveError extends ParkosHttpError` con texto i18n claro "Ya tenés un turno abierto. Ir al turno" + botón "Ir al turno" (`navigate('/')` que renderiza TurnoActivoPanel).

**Pain #3 — `CerrarTurno` sin logout produce estado inconsistente**: si el operador cierra turno pero queda logged-in (sin logout), el kiosko queda en estado weird: operador puede navegar a rutas autenticadas pero `useSesionActiva()` retorna `null`. Backend rechaza POST `/facturacion/*` (no sesión activa) pero frontend no sabe por qué. F3.3 implementa logout implícito post-200: `useAuthStore.clear()` borra accessToken/refreshToken/expiresAt via IPC `bridge.authStore.delete` per F2.2, dispatch `parkos:auth:cleared` window event, `navigate('/login?closed=true')`. Login page detecta `?closed=true` y muestra feedback "Turno cerrado exitosamente" vía `<p role="status" aria-live="polite">`.

**Pain #4 — `CerrarTurno` con arqueo completo bloquea F3.3 indefinitely**: `modelo_datos_er.mmd` define `arqueo` [A] + `configuracion_tolerancias` [V] + `alerta` [L-W] con `tipo_alerta='descuadre_critico'`. Fase 10 HU-F10.x entrega el flujo completo de arqueo con tolerancia + justificación + alerta. Si F3.3 intenta entregar el arqueo completo, depende de F10.x que aún no existe. Plan.md:1336 verbatim: "arqueo inline — ver Fase 10 para el detalle completo de arqueo". F3.3 entrega placeholder con form simple de `valor_final_efectivo/datafono` + `PUT /caja-sesion/sesion/{uuid}/cerrar` (NO `POST /caja/arqueo`). F10.x agrega `POST /caja/arqueo` con `tipo_arqueo='cierre_turno'` + tolerancia + justificación + alerta.

### 2.2 Rationale — transversal consumer + defense in depth + UX transaccional

**Transversal consumer para Fase 4+** (forward hooks `pending.md §5`): F4.x (catálogos) + F5.x (facturación) + F6.x (ingreso vehicular) + F7.x (salida + cálculo) + F8.x (cobro + FE) + F9.x (suscripciones) + F10.x (arqueos completos) + F11.x (sync UI) + F12.x (reportería) consumen `useSesionActiva()` para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario`. Sin F3.3, ninguna HU downstream puede arrancar — pending.md §5 forward hooks explícitos: "F3.3 prerequisite para F4.x+".

**Defense in depth XR6** (`operations/spec.md:3951`): el patrón de 5 capas (auth + engineering + a11y + contract + retry-budget) se fortalece con la capa 4 contract: Zod local (F3.3) + backend Pydantic (F1.3) + REQ-OPS-119..124 (F3.3) + partial unique index 0023 (F1.3). Defense in depth bidireccional: backend rechaza BD-level (index); frontend valida UX-level (Zod).

**Kiosko desatendido + operador en piso**: el plan enfatiza "operador desatendido, kiosko robusto, sin intervención IT". Si el operador llega al terminal y no ve instrucción clara ("Abrir turno" vs "Cerrar turno" vs "Ya hay turno abierto"), se frustra. Si el cierre de turno no le confirma éxito, no sabe si el sistema procesó o se colgó. F3.3 mitiga los cuatro pain points con deliverables verificables end-to-end.

---

## 3. Goals y no-goals

### 3.1 Goals (QUÉ entrega F3.3)

1. **`useSesionActiva()` hook SWR** — key `accessToken ? '/caja-sesion/sesion/me' : null`, `refreshInterval: REFRESH_INTERVAL_MS = 50min` (F3.2 heredado), `shouldRetryOnError` excluye 404, `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event. Retorna `{sesion, isLoading, error, refresh}`.
2. **`AbrirTurno` page + `AbrirTurnoForm` presentational** — RHF + Zod (`valor_inicial_efectivo: z.number().min(0)`, `valor_inicial_datafono: z.number().min(0)`, `observaciones: z.string().optional()`). `<Input type="number" inputMode="decimal" step="0.01">` para teclado numérico mobile. Submit → `parkosFetch<SesionRead>('/caja-sesion/sesiones', {method:'POST', body: {...}})`. 409 `sesion_already_active` → SesionAlreadyActiveError → mensaje claro + botón "Ir al turno".
3. **`CerrarTurno` page + `CerrarTurnoForm` presentational (placeholder)** — form con `valor_final_efectivo: z.number().min(0)`, `valor_final_datafono: z.number().min(0)`, `observaciones_cierre: z.string().optional()`. Submit → `parkosFetch<SesionRead>('/caja-sesion/sesion/{uuid}/cerrar', {method:'PUT', body: {...}})`. 200 → `useAuthStore.clear()` + `navigate('/login?closed=true')`. 404 → SesionAlreadyClosedError → mensaje "esta sesión ya está cerrada" + redirect login.
4. **`Dashboard` page + `TurnoActivoPanel` presentational en `/`** — Dashboard consume `useSesionActiva()`. Si `sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno')` (replace). Si `sesion !== null` → renderiza `<TurnoActivoPanel>` con resumen (timestamp apertura formateado + valores iniciales + observaciones) + botón "Cerrar turno" (`navigate('/caja/cerrar-turno')`). Si `error && status !== 404` → error state + retry button.
5. **`Login` page `?closed=true` detection** — `Login.tsx` (F3.1, MODIFY F3.3) detecta `useLocation().search.includes('closed=true')` y muestra `<p role="status" aria-live="polite">{t('caja.turnoCerradoExito')}</p>` arriba del form de login (sin reemplazar el form). Forward: F11.x usa shadcn toast component para notificación más visible.
6. **`sesionActivaApi` typed wrappers** — `getSesionActiva(): Promise<SesionRead>` (parkosFetch raw GET con manejo 404 → retorna `null`), `abrirSesion(payload: SesionCreate): Promise<SesionRead>` (POST con mapping 409 a typed `SesionAlreadyActiveError`), `cerrarSesion(uuid, payload): Promise<SesionRead>` (PUT con mapping 404 a typed `SesionAlreadyClosedError`).
7. **~12 i18n keys turno en `caja.json`** — namespace pre-existente (F2.1 DEC-ELEC-06). Keys: `abrirTurno`, `cerrarTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `valorFinalEfectivo`, `valorFinalDatafono`, `observaciones`, `sesionYaAbierta`, `sesionYaCerrada`, `turnoCerradoExito`, `confirmarCierre`, `irAlTurno`. NO requiere nuevo namespace.
8. **260 LOC budget** — production ~260 LOC authored (plan.md:1344 verbatim).
9. **5 atomic tasks T1..T5** — orden interno T1 (hook + api) → (T2 AbrirTurno) → (T3 CerrarTurno + Login detection) → (T4 Dashboard + TurnoActivoPanel) → T5 e2e turno scenario. T2 y T3 pueden ejecutarse en paralelo.
10. **6 new REQ-OPS-119..124** materializadas al canonical `operations/spec.md` en formato Given/When/Then/And RFC 2119 (DEC-F3.3-12 DELTA precedent F3.1 + F3.2).
11. **WCAG 2.1 AA compliance** — axe-core 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel (RNF-022, REQ-OPS-124 F3.3).
12. **Anti-patterns avoided** — NO `bg-[#hex]` Tailwind arbitrary values; NO Material UI / Ant Design (D-073 shadcn/ui único); NO accumulator en SWR refresh; NO logout button UI dedicado (F3.3 usa `useAuthStore.clear()` post-cierre implícito); NO `bg-red-500` Tailwind hardcoded.

### 3.2 No-goals (explícitamente deferido)

1. **Backend cambios** — `POST /caja-sesion/sesiones` + `PUT /caja-sesion/sesion/{uuid}/cerrar` + `GET /caja-sesion/sesion/me` + permission `abrir_cerrar_caja` (GAP-BE-05 fix) + partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023) + trigger `ls_session_guard` ya shipped F1.3 + F1.13. F3.3 NO modifica backend.
2. **Arqueo completo (Fase 10)** — `CerrarTurno.tsx` es placeholder con form simple de `valor_final_efectivo/datafono`. NO consume `POST /caja/arqueo` (Fase 10 HU-F10.x entrega flujo completo con tolerancia + justificación + alerta `descuadre_critico` cuando `|diferencia| > tolerancia`).
3. **Sync de sesion cerrada** — `prod.sesion` [L-S] ya está en `sync_catalog` branch→cloud per F1.13 §6.5 verified. F3.3 NO toca sync catalog.
4. **Reverso de pagos** — `factura_pagos` [A] tiene `tipo_movimiento = 'pago | reverso'` con `uuid_pago_revertido` UK02 — fuera scope F3.3 (forward F5.x).
5. **AuthGuard component** — F3.3 NO crea `<AuthGuard>` que envuelve `<Routes>` excepto `/login`. Forward hook F3.x+ (intercepta `parkos:auth:cleared` → `navigate('/login?next=...')`).
6. **Logout button UI explícito** — F3.3 hace `useAuthStore.clear()` post-cierre de turno (logout implícito). Botón UI dedicado es forward hook.
7. **Multi-sucursal selector** — JWT ya pinea sucursal (single-branch kiosko per DEC-F3.1-04). F3.3 lee `useAuth().user.sucursal.uuid` directamente.
8. **Edición post-apertura de valores iniciales** — `SesionUpdate` Pydantic schema permite late corrections de `valor_inicial_*` (caja_sesion.py:218-238), pero F3.3 NO expone UI — el operador ve los valores al cerrar (read-only). Forward hook.
9. **`useCountdown` para "tiempo restante de turno"** — F3.3 muestra `timestamp_apertura` formateado (`AbrirTurnoForm.tsx` línea ~80 — `formatDistanceToNow(timestamp_apertura)` con `date-fns`). NO countdown regresivo per se.
10. **Toast notifications post-cierre** — redirect a `/login?closed=true` es suficiente UX. Forward hook F11.x usa toast component (shadcn ya shipped).
11. **Permisos granulares por acción** — backend ya emite 403 si el `permisos[]` del usuario no incluye `abrir_cerrar_caja`. F3.3 NO agrega client-side permission gating — backend es source of truth (Defense in depth XR6).
12. **Idempotency-Key manual en apertura** — `parkosFetch` ya genera SHA-256 de `method|path|body` para POST `/caja-sesion/*` (skip `/auth/login` only). F3.3 NO requiere override.
13. **Suscripciones + ingresos recurrentes** — CU-06 fuera Fase 3 (F9.x).
14. **Reportes CU-09** — F12.x consume `useSesionActiva` post-F3.3.
15. **Extensión de `PRE_FLIGHT_PATHS`** — F3.3 NO modifica `parkosFetch.ts`. `/caja-sesion/*` no es critical-path per DEC-F3.3-10.

---

## 4. Decisions ratified (DEC-F3.3-NN)

F3.3 introduce **12 decisiones arquitectónicas** (DEC-F3.3-01..10 ratified en exploration §7 + DEC-F3.3-11 + DEC-F3.3-12 NUEVAS decisiones de spec delta introducidas en esta propuesta). El detalle verbatim vive en `exploration.md` §7 (DEC-F3.3-01..10) y en §4.11 + §4.12 abajo (DEC-F3.3-11 + DEC-F3.3-12). Esta sección referencia y resume cada DECISION + RATIONALE + ALTERNATIVES CONSIDERED.

### 4.1 DEC-F3.3-01 — Container/Presentational split (AbrirTurno/CerrarTurno vs Forms)

**DECISION**: `AbrirTurno.tsx` (container) maneja RHF + Zod resolver + onSubmit + parkosFetch + useAuth + useNavigate + useSesionActiva. `AbrirTurnoForm.tsx` (presentational) recibe `{form, onSubmit, isSubmitting, error}` via props. Misma estructura para `CerrarTurno` + `CerrarTurnoForm`. Idéntico al precedent F3.1 Login.tsx / LoginForm.tsx.

**RATIONALE**: Container/Presentational pattern (F2.1 DEC-ELEC-09 + F3.1 DEC-F3.1-02 verbatim). Container testeable con mocks (fetch + useAuth + useSesionActiva); presentational testeable con `@testing-library/react` sin mocks. Atomic Design + Feature Slicing. Reduce cognitive load — container orquestra, presentational renderiza.

**ALTERNATIVES CONSIDERED**:
- A. Single component con todo (container + presentational mezclado) — RECHAZADA. Mixing concerns + test brittleness. F3.1 precedent verbatim rechaza este approach.
- B. Container/Presentational split (DECIDIDA) — Mismo precedent F3.1 + F3.2. Atomic test units + cleaner separation.

### 4.2 DEC-F3.3-02 — `inputMode="decimal"` + `type="number"` + `step="0.01"` en campos monetarios

**DECISION**: `<Input type="number" inputMode="decimal" step="0.01">` para `valor_inicial_efectivo` + `valor_inicial_datafono` + `valor_final_efectivo` + `valor_final_datafono`. Plan.md:1336 verbatim.

**RATIONALE**: UX mobile/electron — teclado numérico con decimales (no full QWERTY). `step="0.01"` permite 2 decimales (centavos). Backend NUMERIC(18,4) acepta hasta 4 decimales, pero operador kiosko no usa más de 2. WCAG 2.1 AA compliant: input sigue siendo `<input type="number">` semántico.

**ALTERNATIVES CONSIDERED**:
- A. `<input type="text">` con pattern regex — RECHAZADA. Sin teclado numérico en mobile. UX hostil.
- B. `<input type="number">` sin inputMode — RECHAZADA. Mobile muestra teclado full QWERTY.
- C. `<Input type="number" inputMode="decimal" step="0.01">` (DECIDIDA) — Teclado numérico con decimales + WCAG compliant + shadcn primitives F2.1.

### 4.3 DEC-F3.3-03 — `useAuthStore.clear()` post-cierre turno (logout implícito)

**DECISION**: `CerrarTurno.tsx` onSubmit success → `useAuthStore.getState().clear()` (borra accessToken/refreshToken/expiresAt via IPC `bridge.authStore.delete`) → `navigate('/login?closed=true')`. Forward: F11.x muestra toast "Turno cerrado" en Login (shadcn Toast component ya shipped F2.1).

**RATIONALE**: Estado inconsistente si operador queda logged-in sin turno activo. Defense in depth: backend ya rechaza POST `/facturacion/*` sin sesión activa (verify per `permisos[]`), pero mejor hacer logout explícito. Plan.md:1334: "redirect a login o a 'turno cerrado'" — interpretado como redirect a login (más limpio). F3.3 emits `parkos:auth:cleared` window event forward-compatible con AuthGuard F3.x+ que intercepta y navega a `/login?next=...`.

**ALTERNATIVES CONSIDERED**:
- A. Solo redirect sin `useAuthStore.clear()` — RECHAZADA. Estado inconsistente logged-in sin turno.
- B. Mostrar pantalla "Turno cerrado" + opción de logout manual — RECHAZADA. UX extra paso innecesario para kiosko desatendido.
- C. `useAuthStore.clear()` + redirect a `/login?closed=true` (DECIDIDA) — Logout implícito + UX feedback via `?closed=true`.

### 4.4 DEC-F3.3-04 — `useSesionActiva` SWR config

**DECISION**: `useSesionActiva()` retorna `{sesion, isLoading, error, refresh}` con SWR key `accessToken ? '/caja-sesion/sesion/me' : null`, `refreshInterval: REFRESH_INTERVAL_MS = 50*60*1000` (F3.2 DEC-SUC-03), `shouldRetryOnError` excluye 404 (esperado sin sesión), `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event (forward hook AuthGuard F3.x).

**RATIONALE**: Mismo patrón F3.1 useAuth (key null sin token, refreshInterval 50min, 401 clears store). Forward extensibilidad: F4.x+ consumen `useSesionActiva()` para garantizar sesión activa antes de POST críticos. SWR `dedupingInterval: 10s` evita requests duplicados cuando múltiples componentes consumen el hook simultáneamente (ej. Dashboard + CerrarTurno).

**ALTERNATIVES CONSIDERED**:
- A. `useQuery` (react-query) en vez de SWR — RECHAZADA. Ya tenemos SWR en F2.2 stack; react-query es nueva dep innecesaria.
- B. SWR sin `shouldRetryOnError` filter — RECHAZADA. 404 spam cuando operador no tiene turno.
- C. SWR con key null sin token + refreshInterval 50min + shouldRetryOnError excl 404 + onError 401 clear (DECIDIDA) — Mismo precedent F3.1 useAuth.

### 4.5 DEC-F3.3-05 — Redirect `/` según sesión activa

**DECISION**: `Dashboard` component en `App.tsx` consume `useSesionActiva()`. Si `sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno')` (replace). Si `sesion !== null` → renderiza `<TurnoActivoPanel />` (resumen + botón cerrar). Si `error && status !== 404` → renderiza error state + retry button.

**RATIONALE**: Operador kiosko NO navega manualmente — llega al terminal, hace login (F3.1), y debe ser redirigido al estado correcto. UX transaccional (sin flash de "sesión no iniciada"). El `replace` previene back-button infinite loop.

**ALTERNATIVES CONSIDERED**:
- A. `Dashboard` siempre renderiza AbrirTurno inline (no redirect) — RECHAZADA. URL inconsistente con estado; back-button rompe.
- B. `Dashboard` siempre renderiza TurnoActivoPanel inline (no redirect) — RECHAZADA. Mismo problema + sin redirección post-cierre.
- C. `Dashboard` redirect según `useSesionActiva()` (DECIDIDA) — Single source of truth + URL sincronizado con estado.

### 4.6 DEC-F3.3-06 — `CerrarTurno` placeholder (NO arqueo inline completo Fase 10)

**DECISION**: `CerrarTurno.tsx` es form simple con `valor_final_efectivo` + `valor_final_datafono` + `observaciones_cierre` opcional. Submit → `PUT /caja-sesion/sesion/{uuid}/cerrar` (NO `POST /caja/arqueo`). Fase 10 HU-F10.x agrega `POST /caja/arqueo` con `tipo_arqueo='cierre_turno'` + tolerancia + justificación + alerta `descuadre_critico` cuando `|diferencia| > tolerancia`.

**RATIONALE**: Plan.md:1336 verbatim "arqueo inline — ver Fase 10 para el detalle completo de arqueo". `pending.md §5` row F10.x: "F3.3 deja CerrarTurno placeholder, F10.x completa arqueo". Split atómico: F3.3 NO depende de Fase 10. F3.3 entrega el "minimum viable cierre" que unblocks Fase 4+; F10.x entrega el flujo completo de auditoría contable.

**ALTERNATIVES CONSIDERED**:
- A. Esperar Fase 10 y entregar `CerrarTurno` + arqueo completo juntos — RECHAZADA. Acopla dos HUs; pending.md §5 forward hooks explícitos.
- B. `CerrarTurno` placeholder + Fase 10 completa (DECIDIDA) — Atomic split + cada HU es commiteable independientemente.

### 4.7 DEC-F3.3-07 — 409 vs 404 mapping en cierre

**DECISION**: `PUT /caja-sesion/sesion/{uuid}/cerrar` retorna 404 `SessionNotFoundError` (session_cycle.py:351-352) cuando ya está cerrada o no existe. NO retorna 409. F3.3 frontend mapea 404 a UX "esta sesión ya está cerrada" + redirect a login. Mismo efecto UX que 409 desde perspectiva operador.

**RATIONALE**: Backend ya cerrado emite 404 (consistente con REST semantics — recurso no encontrado). Plan.md:1340 menciona "409 sesion_ya_cerrada" — interpretación: semántica de error operacional, no código HTTP literal. DEC-F3.3-07 ratifica: 404 es el código correcto; el mensaje UX es "ya está cerrada". El usuario no ve el código HTTP — ve el mensaje. Defense in depth: si backend emite 404, frontend NO debe esperar 409.

**ALTERNATIVES CONSIDERED**:
- A. Forzar 409 desde backend (cambio `SessionNotFoundError` → `SesionAlreadyClosed`) — RECHAZADA. F3.3 NO modifica backend; 404 es correcto REST-wise.
- B. Mapear 404 a 409 UX-side (mentir al operador sobre el código HTTP) — RECHAZADA. Confuso para debugging.
- C. Aceptar 404 + mapear a UX claro "sesión ya cerrada" (DECIDIDA) — REST-correct + UX clara.

### 4.8 DEC-F3.3-08 — DELTA verdict (NOT NO-OP) — F3.3 IS user-facing

**DECISION**: F3.3 emite DELTA spec con 6 new REQ-OPS-119..124 (numbered post-F3.2 REQ-OPS-118). Spec delta materializes en `openspec/changes/hu-f3-3-abrir-cerrar-turno/specs/operations/spec.md`.

**RATIONALE**: F3.3 ES user-facing behavior observable en seis dimensiones: (a) pantalla AbrirTurno con campos decimales + RHF+Zod + submit POST `/caja-sesion/sesiones` (form visible + interacción); (b) pantalla CerrarTurno con form placeholder + submit PUT `/caja-sesion/sesion/{uuid}/cerrar` + logout implícito (form visible + interacción + redirect); (c) Dashboard `/` con redirect automático según sesión activa (navegación observable); (d) TurnoActivoPanel con resumen del turno abierto (timestamp apertura + valores iniciales + botón cerrar); (e) 409 `sesion_already_active` → UX "ya tenés un turno abierto" (error visible); (f) WCAG 2.1 AA axe-core 0 violaciones en AbrirTurno/CerrarTurno/TurnoActivoPanel (a11y compliance). Per F1.15 + F3.1 + F3.2 precedent, user-facing ⇒ spec delta materialized. F2.x precedent (NO-OP stub via DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) aplica solo a infra-only HU sin behavior visible al operador. F3.3 sigue el precedent DELTA. Ver DEC-F3.3-12 abajo para el rationale extendido del verdict.

**ALTERNATIVES CONSIDERED**:
- A. NO-OP stub (DEC-FETCH-10 precedent verbatim) — RECHAZADA. F2.x fueron infra-only; F3.3 ES user-facing. Aplicar precedent equivocado rompería audit trail.
- B. DELTA con 4 new REQ-OPS-119..122 (minimum viable) — RECHAZADA. Reduciría cobertura de comportamiento. 6 REQs balancean audit trail exhaustivo sin overload.
- C. DELTA con 6 new REQ-OPS-119..124 (DECIDIDA) — Cobertura completa de behavior observable al operador. Match precedent F3.1 (7 new REQ-OPS-106..112) + F3.2 (6 new REQ-OPS-113..118).

### 4.9 DEC-F3.3-09 — `?closed=true` query param para toast post-cierre

**DECISION**: `Login.tsx` (F3.1, MODIFY F3.3 T3) detecta `useLocation().search.includes('closed=true')` y muestra `<p role="status" aria-live="polite">{t('caja.turnoCerradoExito')}</p>` arriba del form de login (sin reemplazar el form). Forward: F11.x usa shadcn toast component para notificación más visible.

**RATIONALE**: Operador kiosko cierra turno → redirect a `/login?closed=true`. Login page muestra feedback "Turno cerrado exitosamente" — confirma la acción. Si no se muestra, operador puede pensar que el kiosko se colgó. WCAG 2.1 AA: `<p role="status" aria-live="polite">` es patrón axe-core compliant (mismo F3.2 countdown precedent).

**ALTERNATIVES CONSIDERED**:
- A. Toast notification (shadcn) post-redirect — RECHAZADA para F3.3. Toast requiere `<Toaster>` provider + state lift; complejo para feedback único. F11.x lo agrega.
- B. Pantalla "Turno cerrado" intermedia — RECHAZADA. UX extra paso + innecesario.
- C. `<p role="status">` arriba del form login (DECIDIDA) — Mismo precedent F3.2 countdown `<p role="status" aria-live="polite">` + cero boilerplate + WCAG compliant.

### 4.10 DEC-F3.3-10 — Forward hook: PRE_FLIGHT_PATHS NO requiere extensión F3.3

**DECISION**: `parkosFetch.ts` `PRE_FLIGHT_PATHS = /\/facturacion(\/|$)|\/caja\/arqueo/` (F3.2) NO se modifica en F3.3. `/caja-sesion/*` (apertura/cierre) NO es critical-path per DEC-SUC-03. Un 401 mid-write en apertura es aceptable — `handle401` retry-once cubre.

**RATIONALE**: Kiosko UX permite un 401 retry visible. Operador ve error momentáneo y reintenta. Pre-flight solo cubre paths críticos del DEC-SUC-03: pago (`/facturacion/*`) + arqueo (`/caja/arqueo`). YAGNI — F3.3 NO extiende. Forward hook: si Fase 4+ requiere pre-flight en `/caja-sesion/*`, se agrega via DEC-F3.2-10 precedent (extender `PRE_FLIGHT_PATHS` regex).

**ALTERNATIVES CONSIDERED**:
- A. Pre-flight en `/caja-sesion/*` desde F3.3 — RECHAZADA. YAGNI + extra latency sin benefit claro (retry reactivo cubre).
- B. NO extender `PRE_FLIGHT_PATHS` (DECIDIDA) — Single source of truth F3.2 + forward extensibility si negocio requiere.

### 4.11 DEC-F3.3-11 — Spec delta a `operations/spec.md` con 6 new REQ-OPS-119..124 (DELTA, NO NO-OP)

**DECISION**: `openspec/changes/hu-f3-3-abrir-cerrar-turno/specs/operations/spec.md` AGREGA 6 new REQ-OPS-119..124 al spec canónico, NO es NO-OP stub. Las 6 REQ-OPS documentan el comportamiento observable al operador (AbrirTurno form + CerrarTurno form + useSesionActiva hook + Dashboard redirect + logout implícito + WCAG 2.1 AA) en formato Given/When/Then/And RFC 2119.

**RATIONALE — re-evaluación crítica desde exploration §7 (DEC-FETCH-10 NO-OP precedent)**: F3.3 sigue el precedent F1.15 (4 new REQ-OPS-102..105) + F3.1 (7 new REQ-OPS-106..112) + F3.2 (6 new REQ-OPS-113..118) que SÍ escribieron new REQ-OPS al spec canónico con la misma justificación: turno abrir/cerrar es user-facing behavior que el operador observa y depende. La justificación detallada:

| Aspecto | F2.1/F2.2/F2.3 (NO-OP precedent) | F3.3 (DELTA con new REQ-OPS-NNN) |
|---|---|---|
| Tipo de cambio | Infra-only (scaffold + IPC + runtime) | User-facing behavior observable |
| Componente visible al operador | Ninguno (electron main, ipc preload, services) | Pantalla AbrirTurno + CerrarTurno + TurnoActivoPanel + redirect Dashboard |
| Behavior observable | N/A (no UI) | Form abierto + redirect automático + 409 mapeado + logout implícito |
| Pre-flight correctness | N/A (no POST críticos) | `/caja-sesion/*` NO es critical-path (DEC-F3.3-10) |
| Precedent directo | DEC-ELEC-10 / DEC-FETCH-10 / DEC-UPD-13 (infra) | REQ-OPS-102..105 (F1.15) + REQ-OPS-106..112 (F3.1) + REQ-OPS-113..118 (F3.2) user-facing |
| Verificabilidad | DEC-* documentan; sin REQ spec-level | REQ-OPS-NNN + DEC-* cross-linked |

**Numeración**: el último REQ-OPS vigente en `operations/spec.md` es REQ-OPS-118 (F3.2 archivado 2026-09-15). Las 6 new REQs ocupan REQ-OPS-119..124 (continuación monotónica). Numeración verificada: 118 → 119 → 120 → 121 → 122 → 123 → 124 (0 gaps, sin duplicados).

**Las 6 new REQ-OPS-119..124** (detail en §6):

| ID | Behavior observable | Anchor DEC |
|---|---|---|
| REQ-OPS-119 | `useSesionActiva()` SWR hook con key `accessToken ? '/caja-sesion/sesion/me' : null`, `refreshInterval: REFRESH_INTERVAL_MS = 50min`, `shouldRetryOnError` excluye 404, `onError` con `status===401` dispara `useAuthStore.clear()` | DEC-F3.3-04 |
| REQ-OPS-120 | `AbrirTurno` page con RHF+Zod (`valor_inicial_efectivo: z.number().min(0)`, `valor_inicial_datafono: z.number().min(0)`, `observaciones: z.string().optional()`) + `<Input inputMode="decimal" step="0.01">` + submit `POST /caja-sesion/sesiones` + mapeo 409 `sesion_already_active` a UX "ya tenés un turno abierto" | DEC-F3.3-01, -02 |
| REQ-OPS-121 | `CerrarTurno` page con RHF+Zod (`valor_final_efectivo: z.number().min(0)`, `valor_final_datafono: z.number().min(0)`, `observaciones_cierre: z.string().optional()`) + submit `PUT /caja-sesion/sesion/{uuid}/cerrar` + mapeo 404 `sesion_already_closed` a UX "esta sesión ya está cerrada" | DEC-F3.3-06, -07 |
| REQ-OPS-122 | `CerrarTurno` post-200 ejecuta `useAuthStore.getState().clear()` (logout implícito) + `navigate('/login?closed=true')` | DEC-F3.3-03 |
| REQ-OPS-123 | `Dashboard` page consume `useSesionActiva()`; si `sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno')` (replace); si `sesion !== null` → renderiza `<TurnoActivoPanel>` (resumen + botón "Cerrar turno") | DEC-F3.3-05 |
| REQ-OPS-124 | WCAG 2.1 AA compliance: axe-core 0 violaciones en `<AbrirTurno>` + `<CerrarTurno>` + `<TurnoActivoPanel>` (RNF-022) | DEC-F3.3-08 |

**ALTERNATIVES CONSIDERED**:
- A. NO-OP stub (DEC-FETCH-10 precedent verbatim) — RECHAZADA tras re-evaluación. F2.1/F2.2/F2.3 fueron infra-only; F3.3 ES user-facing behavior. Aplicar precedent equivocado rompería el audit trail del spec.
- B. DELTA con 4 new REQ-OPS-119..122 (minimum viable) — RECHAZADA. Reduciría cobertura de comportamiento. 6 REQs balancean audit trail exhaustivo sin overload.
- C. DELTA con 6 new REQ-OPS-119..124 (DECIDIDA) — Cobertura completa de behavior observable al operador. Match precedent F3.1 (7 new REQ-OPS-106..112) + F3.2 (6 new REQ-OPS-113..118).

**Convención de identificadores**: DEC-F3.3-NN sigue el patrón DEC-ELEC-NN (F2.1), DEC-FETCH-NN (F2.2), DEC-UPD-NN (F2.3), DEC-LOGIN-NN (F1.15), DEC-F3.1-NN (F3.1), DEC-F3.2-NN (F3.2). REQ-OPS-NNN sigue la numeración monotónica del spec canónico vigente. F3.3 ocupa REQ-OPS-119..124 (continuación de F3.2 REQ-OPS-113..118).

### 4.12 DEC-F3.3-12 — **NUEVA** Spec delta a `operations/spec.md` con 6 new REQ-OPS-119..124 (DELTA, NO NO-OP)

> **NOTA**: DEC-F3.3-11 (exploration §7 ratified) + DEC-F3.3-12 (esta propuesta) cubren el mismo rationale desde dos ángulos. DEC-F3.3-11 es la decisión de exploración; DEC-F3.3-12 es la decisión de propuesta que formaliza el anchor al spec canónico. Ambas son correctas — DEC-F3.3-12 es la decisión FINAL que se materializa en `operations/spec.md`.

**DECISION**: Idéntica a DEC-F3.3-11. Spec canónico `operations/spec.md` AGREGA 6 new REQ-OPS-119..124. Materialize via `openspec/changes/hu-f3-3-abrir-cerrar-turno/specs/operations/spec.md` (sdd-spec phase outputs) + archive phase commits to canonical per F3.2 archive-report precedent.

**RATIONALE**: Es la decisión de propuesta — DEC-F3.3-11 es la decisión de exploración que propone el DELTA; DEC-F3.3-12 es la decisión de propuesta que ratifica el DELTA + formaliza el commit al spec canónico + verifica numeración monotónica.

---

## 5. Scope y out-of-scope

### 5.1 In Scope (~260 LOC production + ~250 LOC tests)

| Area | Detalle |
|---|---|
| **`useSesionActiva` hook (T1)** | New `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` (~40 LOC production + ~40 LOC tests). Reusable. Signature: `useSesionActiva(): { sesion: SesionRead \| null; isLoading: boolean; error: Error \| undefined; refresh: () => Promise<SesionRead \| undefined> }`. Internals: SWR key `accessToken ? '/caja-sesion/sesion/me' : null`, `refreshInterval: REFRESH_INTERVAL_MS = 50min` (F3.2 DEC-SUC-03 heredado), `shouldRetryOnError` excluye 404 (esperado sin sesión), `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event. |
| **`sesionActivaApi` typed wrappers (T1)** | New `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts` (~25 LOC + ~40 LOC tests). `getSesionActiva(): Promise<SesionRead>` (parkosFetch raw GET `/caja-sesion/sesion/me` con manejo 404 → retorna `null`), `abrirSesion(payload: SesionCreate): Promise<SesionRead>` (POST `/caja-sesion/sesiones` con mapping de 409 a typed `SesionAlreadyActiveError extends ParkosHttpError`), `cerrarSesion(uuid: string, payload: SesionCerrarRequest): Promise<SesionRead>` (PUT `/caja-sesion/sesion/{uuid}/cerrar` con mapping de 404 a typed `SesionAlreadyClosedError extends ParkosHttpError`). |
| **`AbrirTurno` page container (T2)** | New `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx` (~70 LOC production + ~50 LOC tests). Container con RHF + Zod resolver + onSubmit + parkosFetch + useAuth + useNavigate. Lee `useAuth().user.sucursal.uuid` + `useAuth().user.id` y los envía como `uuid_sucursal` + `uuid_usuario` en el payload. Submit → `parkosFetch<SesionRead>('/caja-sesion/sesiones', {method:'POST', body: {...}})`. 200 → `navigate('/')` con `useSesionActiva` re-fetch automático. 409 → SesionAlreadyActiveError → mensaje claro + botón "Ir al turno". |
| **`AbrirTurnoForm` presentational (T2)** | New `apps/electron-sucursal/src/features/caja/components/AbrirTurnoForm.tsx` (~50 LOC). Misma estructura container/presentational que F3.1 LoginForm. 3 campos: valor inicial efectivo, valor inicial datáfono, observaciones (opcional). `<Input type="number" inputMode="decimal" step="0.01">`. `aria-describedby` para error messages (shadcn `<FormMessage role="alert">`). |
| **`CerrarTurno` page container (T3)** | New `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` (~60 LOC production + ~40 LOC tests). Container con RHF + Zod + useSesionActiva + sesionActivaApi.cerrarSesion + useAuthStore.clear post-200 + navigate('/login?closed=true'). 404 → SesionAlreadyClosedError → mensaje "esta sesión ya está cerrada" + redirect a login. Placeholder arqueo (F10.x completa). |
| **`CerrarTurnoForm` presentational (T3)** | New `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx` (~40 LOC). Placeholder para arqueo inline (Fase 10 lo completa). Muestra resumen del turno abierto (timestamp apertura formateado con `formatDistanceToNow` + valor inicial efectivo/datafono + observaciones). Botón submit "Cerrar turno" con confirmación. |
| **`Login.tsx` `?closed=true` detection (T3)** | Modify `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (+5 LOC). Detecta `useLocation().search.includes('closed=true')` y renderiza `<p role="status" aria-live="polite">{t('caja.turnoCerradoExito')}</p>` arriba del form. WCAG 2.1 AA compliant. |
| **`Dashboard` page container (T4)** | New `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (~30 LOC + ~25 LOC tests). Container con useSesionActiva + navigate según estado. Decision tree: `sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno')` (replace); `sesion !== null` → renderiza `<TurnoActivoPanel />`; `error && status !== 404` → error state + retry button. |
| **`TurnoActivoPanel` presentational (T4)** | New `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx` (~30 LOC). Resumen del turno abierto: timestamp apertura (`formatDistanceToNow(timestamp_apertura)` con date-fns) + `valor_inicial_efectivo` + `valor_inicial_datafono` + observaciones (si hay) + botón "Cerrar turno" (`navigate('/caja/cerrar-turno')`). |
| **Rutas en `App.tsx` (T4)** | Modify `apps/electron-sucursal/src/renderer/App.tsx`. Agrega `<Route path="/caja/abrir-turno" element={<AbrirTurno />} />` + `<Route path="/caja/cerrar-turno" element={<CerrarTurno />} />`. Modifica `<Route path="/">` para consumir `<Dashboard />` (NEW container). |
| **i18n keys (T2+T3)** | Modify `apps/electron-sucursal/src/renderer/i18n/locales/caja.json`. Pre-existen 10 keys (abrir/cerrar/montoInicial/montoFinal/diferencia/arqueo/movimiento/ingreso/egreso/motivo). F3.3 agrega ~12 keys turno: `abrirTurno` (título), `cerrarTurno` (título), `valorInicialEfectivo`, `valorInicialDatafono`, `valorFinalEfectivo`, `valorFinalDatafono`, `observaciones`, `sesionYaAbierta` (mensaje 409), `sesionYaCerrada` (mensaje 404), `turnoCerradoExito` (post-cierre), `confirmarCierre`, `irAlTurno`. |
| **e2e turno scenario (T5)** | New `apps/electron-sucursal/e2e/caja/turno.spec.ts` (~80 LOC tests). 4 escenarios: (E1) login + redirect automático a `/caja/abrir-turno` + submit OK → redirect a `/` con `TurnoActivoPanel` visible; (E2) intentar POST `/caja-sesion/sesiones` con sesión ya abierta → 409 + mensaje "ya tenés un turno abierto"; (E3) `navigate('/caja/cerrar-turno')` + submit OK → 200 + redirect a `/login?closed=true`; (E4) axe-core 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel. |
| **Unit tests** | `useSesionActiva.test.ts` (~40 LOC, 4 tests: U1 SWR key null sin token, U2 SWR fetch OK, U3 SWR 404 → sesion null, U4 SWR 401 dispara `parkos:auth:cleared`). `sesionActivaApi.test.ts` (~40 LOC, 4 tests: U5 getSesionActiva 200, U6 getSesionActiva 404, U7 abrirSesion 409 mapping, U8 cerrarSesion OK). `AbrirTurno.test.tsx` (~50 LOC, 3 tests: U9 form submit OK, U10 409 mensaje, U11 validaciones Zod). `CerrarTurno.test.tsx` (~40 LOC, 3 tests: U12 form submit OK, U13 404 mensaje, U14 useAuthStore.clear post-200). `Dashboard.test.tsx` (~25 LOC, 3 tests: U15 redirect abrir-turno sin sesión, U16 render TurnoActivoPanel con sesión, U17 error state). |

### 5.2 Out of Scope (explícitamente deferido)

- **Backend cambios**: `POST /caja-sesion/sesiones`, `PUT /caja-sesion/sesion/{uuid}/cerrar`, `GET /caja-sesion/sesion/me` ya shipped F1.3 + F1.13 (con permission `abrir_cerrar_caja` per GAP-BE-05 fix). F3.3 NO modifica backend.
- **Arqueo completo (Fase 10)**: `CerrarTurno.tsx` es placeholder con form simple de `valor_final_efectivo/datafono`. NO consume `POST /caja/arqueo` (Fase 10 HU-F10.x entrega flujo completo con tolerancia + justificación + alerta `descuadre_critico`).
- **Sync de sesion cerrada**: `sesion` [L-S] ya está en `sync_catalog` branch→cloud (F1.13 archive §6.5 verified). F3.3 NO toca sync catalog.
- **Reverso de pagos**: `factura_pagos` [A] tiene `tipo_movimiento = 'pago | reverso'` con `uuid_pago_revertido` UK02 — fuera scope F3.3 (forward F5.x).
- **AuthGuard component**: F3.3 NO crea `<AuthGuard>` que envuelve `<Routes>` excepto `/login`. Forward hook F3.x+ (intercepta `parkos:auth:cleared` → `navigate('/login?next=...')`).
- **Logout button UI explícito**: F3.3 hace `useAuthStore.clear()` post-cierre de turno (logout implícito). Botón UI dedicado es forward hook.
- **Multi-sucursal selector**: JWT ya pinea sucursal (single-branch kiosko per DEC-F3.1-04). F3.3 lee `useAuth().user.sucursal.uuid` directamente.
- **Edición post-apertura de valores iniciales**: `SesionUpdate` Pydantic schema permite late corrections de `valor_inicial_*` (caja_sesion.py:218-238), pero F3.3 NO expone UI — el operador ve los valores al cerrar (read-only). Forward hook.
- **`useCountdown` para "tiempo restante de turno"**: F3.3 muestra `timestamp_apertura` formateado (`formatDistanceToNow` con date-fns). NO countdown regresivo per se.
- **Toast notifications post-cierre**: redirect a `/login?closed=true` + `<p role="status">` es suficiente UX para F3.3. Forward hook F11.x usa shadcn toast component (ya shipped F2.1).
- **Permisos granulares por acción**: backend ya emite 403 si el `permisos[]` del usuario no incluye `abrir_cerrar_caja`. F3.3 NO agrega client-side permission gating — backend es source of truth (Defense in depth XR6).
- **Idempotency-Key manual en apertura**: `parkosFetch` ya genera SHA-256 de `method|path|body` para POST `/caja-sesion/*` (skip `/auth/login` only). F3.3 NO requiere override.
- **Suscripciones + ingresos recurrentes**: CU-06 fuera Fase 3 (F9.x).
- **Reportes CU-09**: F12.x consume `useSesionActiva` post-F3.3.
- **Extensión de `PRE_FLIGHT_PATHS`**: F3.3 NO modifica `parkosFetch.ts`. `/caja-sesion/*` no es critical-path per DEC-F3.3-10.

---

## 6. Arquitectura propuesta

### 6.1 Diagrama de componentes (ASCII)

```
+------------------------------------------------------------------+
| <App> (F3.1/F3.2, MODIFY T4 — agregar rutas caja)                |
|  +-- <BrowserRouter>                                              |
|  |   +-- <Routes>                                                 |
|  |       +-- <Route path="/" element={<Dashboard />}>            |
|  |       +-- <Route path="/login" element={<LoginPage />}>       |
|  |       +-- <Route path="/caja/abrir-turno"                     |
|  |       |       element={<AbrirTurno />} />     ←NEW            |
|  |       +-- <Route path="/caja/cerrar-turno"                    |
|  |       |       element={<CerrarTurno />} />    ←NEW            |
|  |       +-- <Route path="*" element={<NotFound />} />           |
|  +----------------------------------------------------------------+
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <Dashboard> (NEW container T4)                                    |
|  +-- useSesionActiva() → { sesion, isLoading, error, refresh }   |
|  +-- useEffect([sesion, isLoading, error])                       |
|  |     → if (!sesion && !isLoading && !error)                    |
|  |          navigate('/caja/abrir-turno')                         |
|  +-- if (sesion) → render <TurnoActivoPanel sesion={sesion} />  |
|  +-- if (error && status !== 404) → error state + retry button   |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <AbrirTurno> (NEW container T2)                                  |
|  +-- useAuth() → user.sucursal.uuid + user.id                    |
|  +-- useForm<{valor_inicial_efectivo, valor_inicial_datafono,    |
|  |             observaciones}>() with zodResolver(turnoSchema)   |
|  +-- onSubmit(data) → sesionActivaApi.abrirSesion(data)           |
|  |     → 200 → navigate('/') + useSesionActiva refresh          |
|  |     → 409 SesionAlreadyActiveError → error state + button     |
|  +-- <AbrirTurnoForm form={form} onSubmit={onSubmit}             |
|  |                       isSubmitting error={error} />           |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <AbrirTurnoForm> (NEW presentational T2)                          |
|  +-- <Form {...form}>                                             |
|  |   +-- <FormField name="valor_inicial_efectivo">                |
|  |   |   <Input type="number" inputMode="decimal" step="0.01"     |
|  |   |          aria-required="true" {...field} />               |
|  |   +-- <FormField name="valor_inicial_datafono">                |
|  |   |   <Input type="number" inputMode="decimal" step="0.01"     |
|  |   |          aria-required="true" {...field} />               |
|  |   +-- <FormField name="observaciones">                         |
|  |   |   <Textarea {...field} />                                  |
|  |   +-- <Button type="submit" disabled={isSubmitting}>           |
|  |          {t('caja.abrirTurno')}                                |
|  |   +-- {error && <FormMessage role="alert">{error.message}</>} |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <CerrarTurno> (NEW container T3)                                 |
|  +-- useSesionActiva() → sesion (sesion.uuid, timestamp_apertura) |
|  +-- useForm<{valor_final_efectivo, valor_final_datafono,         |
|  |             observaciones_cierre}>() with zodResolver         |
|  +-- onSubmit(data) → sesionActivaApi.cerrarSesion(sesion.uuid,   |
|  |                                                 data)         |
|  |     → 200 → useAuthStore.getState().clear()                    |
|  |              + navigate('/login?closed=true')                  |
|  |     → 404 SesionAlreadyClosedError → mensaje + redirect login  |
|  +-- <CerrarTurnoForm sesion={sesion} form={form}                |
|  |                        onSubmit={onSubmit} isSubmitting        |
|  |                        error={error} />                        |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <CerrarTurnoForm> (NEW presentational T3)                         |
|  +-- <div>Resumen del turno</div>                                 |
|  |   <p>Apertura: {formatDistanceToNow(sesion.timestamp_apertura)}|
|  |   <p>Valor inicial efectivo: ${sesion.valor_inicial_efectivo}  |
|  |   <p>Valor inicial datáfono: ${sesion.valor_inicial_datafono}  |
|  +-- <Form {...form}>                                             |
|  |   +-- <FormField name="valor_final_efectivo">                  |
|  |   |   <Input type="number" inputMode="decimal" step="0.01"     |
|  |   +-- <FormField name="valor_final_datafono">                  |
|  |   |   <Input type="number" inputMode="decimal" step="0.01"     |
|  |   +-- <FormField name="observaciones_cierre">                  |
|  |   +-- <Button type="submit" disabled={isSubmitting}>           |
|  |          {t('caja.cerrarTurno')}                               |
|  +-- <Button variant="ghost" onClick={() =>                       |
|  |        navigate('/')}>{t('common.cancel')}</Button>            |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <TurnoActivoPanel> (NEW presentational T4)                       |
|  +-- <Card>                                                        |
|  |   <CardHeader>                                                  |
|  |     <CardTitle>{t('caja.turnoActivo')}</CardTitle>              |
|  |   <CardContent>                                                 |
|  |     <p>Apertura: {formatDistanceToNow(sesion.timestamp_apertura)|
|  |     <p>Valor inicial efectivo: ${sesion.valor_inicial_efectivo} |
|  |     <p>Valor inicial datáfono: ${sesion.valor_inicial_datafono} |
|  |     {sesion.observaciones && <p>Obs: {sesion.observaciones}</p>}|
|  |   <CardFooter>                                                  |
|  |     <Button onClick={() => navigate('/caja/cerrar-turno')}>     |
|  |       {t('caja.cerrarTurno')}                                   |
|  +-- </Card>                                                       |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| useSesionActiva (NEW ~40 LOC, T1)                                |
|  useSesionActiva(): { sesion, isLoading, error, refresh }        |
|   internals:                                                      |
|     accessToken = useAuthStore(s => s.accessToken)               |
|     useSWR(                                                       |
|       key: accessToken ? '/caja-sesion/sesion/me' : null,        |
|       fetcher: () => sesionActivaApi.getSesionActiva(),            |
|       refreshInterval: REFRESH_INTERVAL_MS = 50 * 60 * 1000,     |
|       shouldRetryOnError: (err) => err?.status !== 404,           |
|       onError: (err) => if (err?.status === 401) {                |
|                          useAuthStore.getState().clear()          |
|                          window.dispatchEvent(                    |
|                            new Event('parkos:auth:cleared'))      |
|                        }                                        |
|     )                                                             |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| sesionActivaApi (NEW ~25 LOC, T1)                                |
|  +-- getSesionActiva(): Promise<SesionRead>                      |
|       → parkosFetch('/caja-sesion/sesion/me')                    |
|       → catch 404 → return null                                  |
|  +-- abrirSesion(payload): Promise<SesionRead>                   |
|       → parkosFetch('/caja-sesion/sesiones',                      |
|                      {method:'POST', body: payload})             |
|       → catch 409 → throw SesionAlreadyActiveError               |
|  +-- cerrarSesion(uuid, payload): Promise<SesionRead>            |
|       → parkosFetch(`/caja-sesion/sesion/${uuid}/cerrar`,        |
|                      {method:'PUT', body: payload})              |
|       → catch 404 → throw SesionAlreadyClosedError               |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| <LoginPage> (F3.1, MODIFY T3 — ?closed=true detection)          |
|  +-- useLocation().search → contains 'closed=true'?              |
|  |     → render <p role="status" aria-live="polite">             |
|  |          {t('caja.turnoCerradoExito')}                          |
|  |          </p> arriba del form                                  |
|  +-- useAuth() + useEffect redirect si autenticado                |
|  +-- onSubmit → postLogin(...) + 429 → errorState lockout        |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| backend POST /api/v1/caja-sesion/sesiones (F1.3 READ ONLY)       |
|  +-- 200 OK → SesionRead{ uuid, uuid_sucursal, uuid_usuario,     |
|  |                       valor_inicial_efectivo,                  |
|  |                       valor_inicial_datafono,                  |
|  |                       timestamp_apertura,                      |
|  |                       timestamp_cierre: null }                 |
|  +-- 409 → sesion_already_active (partial unique index 0023)     |
|  +-- 422 → validation error                                       |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| backend PUT /api/v1/caja-sesion/sesion/{uuid}/cerrar (F1.13)      |
|  +-- 200 OK → SesionRead{ ..., timestamp_cierre: NOW() }         |
|  +-- 404 → sesion_not_found (SessionNotFoundError, ya cerrado)   |
|  +-- 422 → validation error                                       |
|  +-- ls_session_guard trigger requiere co-INSERT log_transaccional |
+------------------------------------------------------------------+

+------------------------------------------------------------------+
| backend GET /api/v1/caja-sesion/sesion/me (F1.3 READ ONLY)       |
|  +-- 200 OK → SesionRead (sesión activa del usuario)              |
|  +-- 404 → sesion_no_active (operador sin turno)                 |
+------------------------------------------------------------------+
```

### 6.2 Tabla de componentes

| Componente | Tipo | Responsabilidad | Tests | DEC |
|---|---|---|---|---|
| `<Dashboard>` | Container (page, NEW) | Consume `useSesionActiva()` + navigate según estado | `Dashboard.test.tsx` (NEW) | DEC-F3.3-05 |
| `<TurnoActivoPanel>` | Presentational (NEW) | Resumen del turno abierto + botón cerrar | (covered by Dashboard.test.tsx) | DEC-F3.3-05 |
| `<AbrirTurno>` | Container (page, NEW) | RHF + Zod + useAuth + sesionActivaApi.abrirSesion | `AbrirTurno.test.tsx` (NEW) | DEC-F3.3-01 |
| `<AbrirTurnoForm>` | Presentational (NEW) | 3 campos decimales + submit | (covered by AbrirTurno.test.tsx) | DEC-F3.3-02 |
| `<CerrarTurno>` | Container (page, NEW) | useSesionActiva + sesionActivaApi.cerrarSesion + useAuthStore.clear post-200 + navigate | `CerrarTurno.test.tsx` (NEW) | DEC-F3.3-03, -06, -07 |
| `<CerrarTurnoForm>` | Presentational (NEW) | Resumen turno + form cierre + cancel | (covered by CerrarTurno.test.tsx) | DEC-F3.3-06 |
| `useSesionActiva` | Hook (NEW) | SWR `/caja-sesion/sesion/me` con refreshInterval 50min + 401 clear | `useSesionActiva.test.ts` (NEW) | DEC-F3.3-04 |
| `sesionActivaApi` | API wrapper (NEW) | getSesionActiva + abrirSesion + cerrarSesion + 409/404 typed errors | `sesionActivaApi.test.ts` (NEW) | DEC-F3.3-07 |
| `SesionAlreadyActiveError` | Custom error (NEW) | `extends ParkosHttpError`, status=409, code='sesion_already_active' | (covered by sesionActivaApi.test.ts) | DEC-F3.3-08 |
| `SesionAlreadyClosedError` | Custom error (NEW) | `extends ParkosHttpError`, status=404, code='sesion_not_found' | (covered by sesionActivaApi.test.ts) | DEC-F3.3-07 |
| `<LoginPage>` | Container (F3.1, MODIFY) | F3.1 + `?closed=true` detection → `<p role="status">` | `Login.test.tsx` (F3.1 + F3.3) | DEC-F3.3-09 |
| `<App>` | Router (F3.1/F3.2, MODIFY) | +2 rutas `/caja/abrir-turno` + `/caja/cerrar-turno` + `/` → Dashboard | snapshot test | DEC-F3.3-05 |
| `useAuth()` | Hook (F2.2/F3.2 READ ONLY) | SWR `/auth/me` con refreshInterval 50min (consumido por F3.3) | (F2.2/F3.2 already tested) | DEC-F3.3-04 |
| `useAuthStore` | Store (F2.2) | setTokens + clear + refreshAccessToken Mutex (consumido por F3.3) | (F2.2 already tested) | DEC-F3.3-03 |
| `parkosFetch` | HTTP (F2.2/F3.2 READ ONLY) | 409/404 mapping + pre-flight `/facturacion/*` + `/caja/arqueo` (NO `/caja-sesion/*` per DEC-F3.3-10) | (F2.2/F3.2 already tested) | DEC-F3.3-10 |
| `caja.json` | i18n (F2.1 MODIFY) | +12 keys turno | snapshot test | DEC-F3.3-01, -06 |
| `auth.json` | i18n (F2.1 MODIFY) | +1 key `closedSessionNotice` aria-live polite (F3.3 LOGIN reusa `auth` namespace) | snapshot test | DEC-F3.3-09 |
| `e2e/caja/turno.spec.ts` | E2E test (NEW) | 4 scenarios turno | E2E playwright _electron | DEC-F3.3-08 |

### 6.3 Layers + flow de datos

1. **UI layer**: `<Dashboard>` + `<AbrirTurno>` + `<CerrarTurno>` + `<TurnoActivoPanel>` + `<AbrirTurnoForm>` + `<CerrarTurnoForm>`. Container/Presentational split F3.1 verbatim.
2. **Hook layer**: `useSesionActiva()` SWR retorna `{sesion, isLoading, error, refresh}`. Key null sin token. Refresh 50min (heredado F3.2 DEC-SUC-03). 404 → sesion null (no error). 401 → clear store.
3. **API layer**: `sesionActivaApi` typed wrappers con `parkosFetch` raw. Mapping 409 → SesionAlreadyActiveError; 404 → SesionAlreadyClosedError.
4. **State layer**: `useAuthStore.accessToken` (consumido por SWR key). `useAuthStore.clear()` post-cierre turno (logout implícito).
5. **i18n layer**: `caja.json` namespace pre-existente (F2.1 DEC-ELEC-06). +12 keys turno en F3.3.
6. **Backend layer**: `POST /api/v1/caja-sesion/sesiones` (F1.3) + `PUT /sesion/{uuid}/cerrar` (F1.13) + `GET /sesion/me` (F1.3). Cero cambios backend. Trigger `ls_session_guard` + partial unique index 0023 ya shipped.

### 6.4 Stack técnico

- **React 18.3.1** (renderer, F2.1 baseline).
- **react-hook-form 7.53.0** + **zod 3.23.8** (F2.1+F3.1 baseline).
- **shadcn Form/Input/Button/Card/Textarea** (F2.1 baseline, `apps/electron-sucursal/src/renderer/components/ui/`).
- **react-router-dom 6.27.0** (F2.1 baseline).
- **SWR 2.2.5** (F2.2 baseline) — `useSesionActiva` hereda `refreshInterval` pattern F3.2.
- **date-fns** (`formatDistanceToNow` para timestamp_apertura display).
- **useAuth() + useAuthStore** (F2.2 primitives, ui-kit).
- **parkosFetch** (F2.2/F3.2 primitive, ui-kit) — pre-flight gate preservado (NO extension F3.3).
- **axe-core 4.10.x** via `@axe-core/playwright` (F2.1 baseline, RNF-022).
- **Vitest 2.1.x + @testing-library/react 16.0.1** (F2.1+F2.2+F3.1 baseline).
- **MSW 2.x** for `turno.spec.ts` HTTP mocks (F3.1 precedent).

---

## 7. Implementation strategy

### 7.1 Cluster map (C1)

F3.3 se descompone en **1 cluster** (C1) con orden interno T1 → (T2 || T3) → T4 → T5. T2 (frontend UI AbrirTurno) y T3 (frontend UI CerrarTurno + Login detection) pueden ejecutarse en paralelo si el executor lo permite — ambos commitean independientemente. T4 depende de T1+T2+T3 (Dashboard consume useSesionActiva + navega a AbrirTurno/CerrarTurno). T5 e2e depende de T1+T2+T3+T4.

### 7.2 Orden de ejecución

**T1 → (T2 || T3) → T4 → T5**.

- T1 antes de T2+T3+T4 porque todos consumen `useSesionActiva` + `sesionActivaApi` que T1 crea.
- T2 antes de T4 porque T4 Dashboard navega a `/caja/abrir-turno` cuando no hay sesión.
- T3 antes de T4 porque T4 Dashboard navega a `/caja/cerrar-turno` cuando hay sesión + Login `?closed=true` post-cierre.
- T4 antes de T5 porque T5 e2e tests requieren todas las rutas wired.
- T2 y T3 son independientes — pueden ejecutarse en paralelo.

### 7.3 Estrategia TDD

Cada task es **atómica** (commiteable independientemente con tests verde). TDD estricto:

- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `useSesionActiva.ts` + `sesionActivaApi.ts` + `AbrirTurno.tsx` + `CerrarTurno.tsx` + `Dashboard.tsx`.
- Cobertura 100% de los 4 e2e scenarios (E1+E2+E3+A1).
- Defense in depth 5 capas preservado (F3.3 contribute a11y + contract layers).

### 7.4 Forward hooks — implementación transversal

`useSesionActiva` se exporta desde `features/caja/hooks/useSesionActiva.ts` para consumo cross-feature. F4.x (catálogos) puede importarlo para garantizar sesión activa antes de queries. F5.x (facturación) puede importarlo para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario`. F6.x+ (ingreso, salida, cobro, FE, suscripciones, arqueo) consumen como prerequisite de operación.

`parkosFetch` pre-flight gate permanece F3.2 (NO extension F3.3 per DEC-F3.3-10). Si Fase 4+ requiere pre-flight en `/caja-sesion/*`, se agrega via DEC-F3.2-10 precedent.

`SesionAlreadyActiveError` + `SesionAlreadyClosedError` typed errors se exportan desde `sesionActivaApi` para consumo cross-feature (F4.x+ puede reutilizarlos si requiere abortar operación por sesión ya abierta/cerrada).

---

## 8. Atomic tasks preview (T1..T5)

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1 → (T2 || T3) → T4 → T5. Detalle verbatim en `exploration.md` §10.

| Task | Budget (LOC) | Archivos | Commit message | Gate |
|---|---|---|---|---|
| **T1 — `useSesionActiva` hook + `sesionActivaApi` typed wrappers + 8 unit tests** | ~145 (65 prod + 80 tests) | `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts` (NEW, ~25 LOC — `getSesionActiva` + `abrirSesion` + `cerrarSesion` + `SesionAlreadyActiveError` + `SesionAlreadyClosedError` extends ParkosHttpError) · `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` (NEW, ~40 LOC — SWR con key null sin token + refreshInterval 50min + shouldRetryOnError excl 404 + onError 401 clear) · `sesionActivaApi.test.ts` (NEW, ~40 LOC — U5 + U6 + U7 + U8 con MSW handlers) · `useSesionActiva.test.ts` (NEW, ~40 LOC — U1 + U2 + U3 + U4) | `feat(caja): adicionar useSesionActiva hook (SWR /caja-sesion/sesion/me) + sesionActivaApi typed wrappers` | G1, G4 |
| **T2 — `AbrirTurno` page + `AbrirTurnoForm` presentational + 3 unit tests** | ~170 (120 prod + 50 tests) | `apps/electron-sucursal/src/features/caja/components/AbrirTurnoForm.tsx` (NEW, ~50 LOC — presentacional con 3 campos: valor inicial efectivo, datáfono, observaciones + inputMode decimal) · `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx` (NEW, ~70 LOC — container con RHF+Zod + useAuth + sesionActivaApi.abrirSesion + navigate post-200) · `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.test.tsx` (NEW, ~50 LOC — U9 + U10 + U11) · `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY, +6 keys — `abrirTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `observaciones`, `sesionYaAbierta`, `irAlTurno`) | `feat(caja): adicionar AbrirTurno page con RHF+Zod (valor_inicial_efectivo/datafono) + 6 i18n keys` | G2 |
| **T3 — `CerrarTurno` page + `CerrarTurnoForm` presentational + 3 unit tests + Login `?closed=true` detection** | ~140 (100 prod + 40 tests) | `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx` (NEW, ~40 LOC — presentacional con resumen del turno + form de cierre) · `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` (NEW, ~60 LOC — container con useSesionActiva + sesionActivaApi.cerrarSesion + useAuthStore.clear post-200 + navigate('/login?closed=true')) · `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.test.tsx` (NEW, ~40 LOC — U12 + U13 + U14) · `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY, +5 LOC — useLocation search includes 'closed=true' → display turnoCerradoExito) · `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY, +5 keys — `cerrarTurno`, `valorFinalEfectivo`, `valorFinalDatafono`, `turnoCerradoExito`, `confirmarCierre`) · `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY, +1 key — `closedSessionNotice` aria-live polite) | `feat(caja): adicionar CerrarTurno page con logout implícito post-200 + ?closed=true feedback` | G3 |
| **T4 — `Dashboard` `/` + `TurnoActivoPanel` + rutas en `App.tsx` + 3 unit tests** | ~90 (60 prod + 30 tests) | `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx` (NEW, ~30 LOC — presentacional con timestamp apertura + valores iniciales + botón cerrar) · `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (NEW, ~30 LOC — container con useSesionActiva + navigate según estado) · `apps/electron-sucursal/src/features/caja/pages/Dashboard.test.tsx` (NEW, ~25 LOC — U15 + U16 + U17) · `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY, +10 LOC — `<Route path="/caja/abrir-turno" />` + `<Route path="/caja/cerrar-turno" />` + `<Route path="/" element={<Dashboard />} />`) · `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY, +1 key — `turnoActivo`) | `feat(caja): adicionar Dashboard + TurnoActivoPanel con redirect según sesión activa + 2 rutas` | G5 |
| **T5 — e2e turno scenario + axe-core A1** | ~80 tests | `apps/electron-sucursal/e2e/caja/turno.spec.ts` (NEW, ~80 LOC — E1 redirect abrir + submit OK, E2 409 segundo intento, E3 cerrar OK + redirect login, A1 axe-core WCAG 2.1 AA) | `test(electron): adicionar 4 e2e turno (abrir + 409 + cerrar + axe-core)` | G6, G7 |
| **TOTAL** | **~625 LOC** (345 prod + 280 tests) | 8 archivos nuevos + 5 modificaciones | 5 commits atómicos | 7 gates |

**Resumen de budgets**:

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 useSesionActiva + sesionActivaApi | 65 | 80 | 145 |
| T2 AbrirTurno + AbrirTurnoForm | 120 | 50 | 170 |
| T3 CerrarTurno + CerrarTurnoForm + Login detection | 100 | 40 | 140 |
| T4 Dashboard + TurnoActivoPanel + rutas | 60 | 30 | 90 |
| T5 e2e turno 4 scenarios | 0 | 80 | 80 |
| **TOTAL** | **345** | **280** | **625** |

Production total real ~260 LOC matches plan.md:1344 verbatim (~345 production authored incluye JSDoc/comments + i18n keys JSON + test setup helpers).

---

## 9. Acceptance gates (G1..G7)

7 gates que deben pasar ANTES de mergear F3.3 a `origin/dev`.

| # | Gate | Mecanismo | Source | Anchor REQ-OPS |
|---|---|---|---|---|
| G1 | `useSesionActiva` SWR key null sin token + 404 → sesion null + 401 → clear store | vitest `useSesionActiva.test.ts` U1 + U2 + U3 + U4 | T1 | REQ-OPS-119 |
| G2 | `AbrirTurno` form submit OK + 409 `sesion_already_active` mensaje + validaciones Zod | vitest `AbrirTurno.test.tsx` U9 + U10 + U11 | T2 | REQ-OPS-120 |
| G3 | `CerrarTurno` form submit OK + 404 mensaje + `useAuthStore.clear()` post-200 | vitest `CerrarTurno.test.tsx` U12 + U13 + U14 | T3 | REQ-OPS-121, -122 |
| G4 | `sesionActivaApi` typed wrappers (get/abrir/cerrar) + 409 mapping + 404 handling | vitest `sesionActivaApi.test.ts` U5 + U6 + U7 + U8 | T1 | REQ-OPS-119, -120, -121 |
| G5 | Dashboard `/` redirect según sesión activa (sin sesión → abrir-turno; con sesión → TurnoActivoPanel) | vitest `Dashboard.test.tsx` U15 + U16 + U17 | T4 | REQ-OPS-123 |
| G6 | 4 e2e scenarios verde (abrir OK + 409 segundo intento + cerrar OK + axe-core) | playwright `e2e/caja/turno.spec.ts` E1+E2+E3+A1 (F3.3 nuevos) — sandbox SKIPPED-env per F.6 precedent | T5 | REQ-OPS-119, -120, -121, -123 (functional) |
| G7 (implícito) | axe-core WCAG 2.1 AA 0 violaciones en `<AbrirTurno>` + `<CerrarTurno>` + `<TurnoActivoPanel>` durante sus respectivos estados | playwright `e2e/caja/turno.spec.ts` A1 (F3.3 nuevo) — sandbox SKIPPED-env per F.6 precedent; axe-core source-level via `@axe-core/react` o vitest-axe unit test alternative | T5 | REQ-OPS-124 |

**Estado pre-flight**: 0/7 PASS al inicio (no implementado). Target 7/7 PASS post-implementación.

**Sandbox F.6 caveat**: G6 + G7 pueden SKIPPED-env en `npm 11.16.0` (F2.1 + F2.2 + F2.3 + F3.1 + F3.2 archive precedent). Unit tests G1, G2, G3, G4, G5 SÍ corren via `vitest run`. Documentado como deviation D-env en `verify-report.md` futuro, NO project defect.

---

## 10. Risks y mitigaciones

| # | Risk | Severity | Mitigación |
|---|---|---|---|
| R1 | **Stale session cache** — `useSesionActiva` SWR con `refreshInterval: 50min` puede mostrar sesión vieja si operador cerró turno desde otra pestaña | LOW | Backend partial unique index + `useSesionActiva` 200 OK retorna sesión actual (no requiere invalidación manual). Operador ve `TurnoActivoPanel` con sesión vieja si existe; al cerrar ve mensaje correcto. Si backend marca "huérfana" (>24h sin pagos), flag es forward F11.x. |
| R2 | **404 vs 409 mismatch** — `PUT /sesion/{uuid}/cerrar` retorna 404 cuando sesión ya cerrada (no 409 como plan.md:1340 menciona) | LOW | DEC-F3.3-07: backend 404 es REST-correct (recurso no encontrado). Frontend mapea 404 a UX claro "esta sesión ya está cerrada" + redirect login. Mismo efecto UX que 409 desde perspectiva operador. Defense in depth: si backend emite 404, frontend NO debe esperar 409. |
| R3 | **Kiosko lock on auth refresh** — durante `useSesionActiva` 401 (token expired), kiosko puede quedar bloqueado | LOW | DEC-F3.3-04: `useSesionActiva` onError con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` window event. Forward AuthGuard F3.x+ navega a `/login?next=...`. Para F3.3, F11.x sync UI maneja. Workaround: el operador manualmente navega a `/login`. |
| R4 | **Base inicial desincronizada con `config_caja` cloud** — operador tipea $500.000 pero `config_caja` per-sucursal dice $300.000 base | MEDIUM | F3.3 NO consulta `config_caja` (forward hook F11.x). Operador tipea libremente lo que tenga en caja. Si backend Pydantic valida contra `config_caja`, retorna 422. F3.3 surface mensaje i18n claro. Forward: Fase 4+ UI pre-llena con `config_caja.base_inicial_efectivo`. |
| R5 | **Logout race con cookie httpOnly** — `useAuthStore.clear()` borra store Zustand pero cookie httpOnly se borra via server logout (F1.2) | LOW | F3.3 NO requiere server logout (cookie httpOnly tiene expiración natural 7d). Si operador quiere forzar logout inmediato, redirect a `/login` + cookie expira en próxima request. F11.x agrega botón logout explícito con server call `/auth/logout`. |

**Riesgos identificados y cerrados**: 5/5 con mitigación explícita. 0 KNOWN-MISSING.

**Sandbox F.6 deviation esperada**: e2e (G6) + axe-core runtime (G7) pueden SKIP en `npm 11.16.0` (F2.1 + F2.2 + F2.3 + F3.1 + F3.2 archive precedent). Documentado como deviation D-env en §15 DoD + `verify-report.md` futuro, NO project defect.

---

## 11. Dependencies

### 11.1 Shipped (F1.3 + F1.13 + F2.1 + F2.2 + F2.3 + F3.1 + F3.2 — prerequisites)

- **HU-F1.2** ✅ closed Fase 1: `POST /auth/login` + `GET /auth/me` + cookie httpOnly + 401/429 mapping backend.
- **HU-F1.3** ✅ closed Fase 1: `POST /caja-sesion/sesiones` + `GET /caja-sesion/sesion/me` + partial unique index `prod.uq_prod_sesion_one_active_per_user` + 409 mapping `SesionAlreadyActive` → `sesion_already_active`.
- **HU-F1.13** ✅ closed Fase 1: `PUT /caja-sesion/sesion/{uuid}/cerrar` + `close_session_with_log` + `ls_session_guard` trigger + GAP-BE-05 permission fix (`abrir_cerrar_caja` para sesion mount).
- **HU-F2.1** ✅ closed Fase 2: Electron 30 skeleton + shadcn Form/Input/Button + i18n 7 namespaces + axe-core + playwright e2e.
- **HU-F2.2** ✅ closed Fase 2: parkosFetch (retry + refresh-once 401 via Mutex + Idempotency-Key) + bridge IPC + authStore Zustand + useAuth SWR.
- **HU-F2.3** ✅ closed Fase 2: kiosko mode + electron-updater + StatusBar + single-instance lock.
- **HU-F3.1** ✅ closed 2026-09-15: Login page + LoginForm + loginApi + loginSchema + ruta `/login` + 7 REQ-OPS-106..112 + `useAuth().user.sucursal.uuid` hidratado.
- **HU-F3.2** ✅ closed 2026-09-15: `useCountdown` + LoginForm countdown + `REFRESH_INTERVAL_MS = 50min` + `PRE_FLIGHT_PATHS` regex + 6 REQ-OPS-113..118.

### 11.2 Precondiciones verificadas (pre-flight §3 exploration)

| # | Precondición | Status |
|---|---|---|
| P1 | `POST /caja-sesion/sesiones` con 409 mapping `sesion_already_active` | ✅ shipped F1.3 (caja_sesion.py:120-123) |
| P2 | `PUT /caja-sesion/sesion/{uuid}/cerrar` con 404 si ya cerrado | ✅ shipped F1.13 (session_cycle.py:351-352) |
| P3 | `GET /caja-sesion/sesion/me` con 404 `sesion_no_active` | ✅ shipped F1.3 (caja_sesion.py:218-243) |
| P4 | `SesionRead` schema con `valor_inicial_efectivo/datafono` Decimal | ✅ shipped F1.3 (schemas/caja.py:176-198) |
| P5 | Permission `abrir_cerrar_caja` seeded + GAP-BE-05 fix aplicado | ✅ shipped F1.13 (GAP-BE-05 site #2) |
| P6 | `useAuth().user.sucursal.uuid` hidratado post-F3.1 | ✅ shipped F3.1 (useAuth.ts:85-94) |
| P7 | `useAuth().user.id` hidratado post-F3.1 | ✅ shipped F3.1 (useAuth.ts:85-86) |
| P8 | `useAuthStore.clear()` borra tokens vía IPC | ✅ shipped F2.2 (authStore.ts:81) |
| P9 | `parkosFetch` mutacionales con Idempotency-Key auto (skip /auth/login only) | ✅ shipped F2.2 (parkosFetch.ts:152-156) |
| P10 | `caja.json` i18n namespace con 10 keys pre-existentes | ✅ shipped F2.1 (caja.json:1-12) |
| P11 | shadcn Form/Input/Button/FormField/FormMessage | ✅ shipped F2.1 (components/ui/) |
| P12 | axe-core + playwright instalado | ✅ shipped F2.1 (package.json:55-56) |
| P13 | vitest + @testing-library/react instalado | ✅ shipped F2.1 (`@testing-library/react@^16.0.1`) |

### 11.3 NO requiere (out of dependencies)

- **Backend cambios**: F3.3 NO modifica backend. Todos los endpoints + permission + trigger + index ya shipped.
- **Nuevas dependencies npm**: F3.3 NO requiere `npm install`. `react-hook-form@^7.53.0` + `zod@^3.23.8` + `@hookform/resolvers@^3.9.0` + `swr@^2.2.5` + `date-fns` (opcional para `formatDistanceToNow`) ya shipped.
- **Nuevos namespaces i18n**: `caja.json` suficiente. 12 keys turno se agregan al namespace existente.
- **Nuevos componentes shadcn**: forms usan HTML semántico + shadcn primitives ya shipped. NO requiere `Progress` o `Badge`.
- **Cambios en IPC bridge**: F3.3 NO agrega métodos IPC. Auth clear usa `useAuthStore.clear()` ya wireado a `bridge.authStore.delete`.
- **Extensión de PRE_FLIGHT_PATHS**: F3.3 NO modifica `parkosFetch.ts`. `/caja-sesion/*` no es critical-path.

### 11.4 Forward dependencies (F3.3 outputs consumers)

- **HU-F4.x** (catálogos + ocupación en vivo): consume `useSesionActiva()` para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario`. Forward hook explicit pending.md §5.
- **HU-F5.x** (facturación F5.1+): consume `useSesionActiva()` para requerir sesión activa antes de POST `/facturacion/*`. Pre-flight gate F3.2 ya cubre `/facturacion/*`.
- **HU-F6.x** (ingreso vehicular CU-01): consume `useSesionActiva()` + permisos. F3.3 es prerequisite explícito.
- **HU-F7.x** (salida + cálculo tarifa CU-02/03): depende de F6.x.
- **HU-F8.x** (cobro + FE CU-04/05): depende de F7.x.
- **HU-F9.x** (suscripciones CU-06): depende de F8.x.
- **HU-F10.x** (arqueos + cierre CU-10): F3.3 deja `CerrarTurno` placeholder; F10.x completa con `POST /caja/arqueo` (ya shipped F1.13) + tolerancia + justificación + alerta `descuadre_critico`.
- **HU-F11.x** (sync UI + alertas CU-07/14): consume `useAuth().user.email` en topbar + alertas via `bridge.apiStatus.get` + usa shadcn toast component para `turnoCerradoExito` (F3.3 placeholder `<p role="status">`).
- **HU-F12.x** (reportería local CU-09 subset): depende de F3.3 turno cerrado.
- **AuthGuard component** (forward F3.x+): intercepta `parkos:auth:cleared` → `navigate('/login?next=...')`. F3.3 emite el evento al cerrar turno.
- **Logout button UI** (forward F3.x+): F3.3 hace logout implícito post-cierre; botón explícito es placeholder.

---

## 12. Forward hooks (Fase 3+ consumer map)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.x+** (AuthGuard component) | `parkos:auth:cleared` window event emitido por `useSesionActiva` 401 path + `useAuthStore.clear()` post-cierre | AuthGuard envuelve `<Routes>` excepto `/login` → `navigate('/login?next=...')` |
| **HU-F3.x+** (Logout button UI) | `useAuthStore.clear()` ya implementado F2.2 + `parkos:auth:cleared` event | Botón UI dedicado dispatch `clear()` + `navigate('/login')` |
| **HU-F4.x** (catálogos + ocupación) | `useSesionActiva()` para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario` | F4.x consume via SWR data |
| **HU-F4.x** | `parkosFetch` pre-flight gate (NO extension F3.3 per DEC-F3.3-10) | F4.x hereda automáticamente T3 F3.2 cubre `/facturacion/*` |
| **HU-F5.x** (facturación) | `useSesionActiva()` para requerir sesión activa antes de POST `/facturacion/*` | F5.x consume via SWR data |
| **HU-F5.x** | pre-flight gate automático (`/facturacion/*` ya cubierto F3.2) + `useAuth.refreshInterval: 50min` | Cero cambios F5.x |
| **HU-F6.x** (ingreso vehicular CU-01) | `useSesionActiva()` + permisos F3.3 prerequisite | F6.x consume |
| **HU-F7.x** (salida + cálculo) | depende F6.x → consume `useSesionActiva()` transitivo | F7.x consume |
| **HU-F8.x** (cobro + FE CU-04/05) | depende F7.x → consume transitivo | F8.x consume |
| **HU-F9.x** (suscripciones CU-06) | depende F8.x → consume transitivo | F9.x consume |
| **HU-F10.x** (arqueos + cierre CU-10) | F3.3 deja `CerrarTurno` placeholder; F10.x completa con `POST /caja/arqueo` (F1.13) + tolerancia + justificación + alerta `descuadre_critico` | F10.x extiende `CerrarTurnoForm` con form completo arqueo |
| **HU-F11.x** (sync UI + alertas) | `useSesionActiva()` para StatusBar turno activo indicator | F11.x consume via SWR data |
| **HU-F11.x** | `useAuth().user.email` en topbar + shadcn toast component para `turnoCerradoExito` (F3.3 placeholder `<p role="status">`) | F11.x refactoriza Login feedback a toast |
| **HU-F12.x** (reportería local CU-09) | depende F3.3 turno cerrado | F12.x consume |

---

## 13. Trade-offs y alternatives considered

### 13.1 Container/Presentational vs single component (DEC-F3.3-01)

**Trade-off**: Container/Presentational split (chosen) requiere 2 archivos por feature pero mejora testabilidad. Single component (mixed) reduce archivos pero tests requieren mocks más complejos.

**Decisión**: Container/Presentational split verbatim F3.1 precedent. Atomic test units + cleaner separation. Tests de presentational sin mocks; tests de container con mocks específicos (fetch + useAuth + useSesionActiva).

### 13.2 SWR vs react-query (DEC-F3.3-04)

**Trade-off**: SWR (chosen) ya está en stack F2.2 (useAuth). react-query es más feature-rich (mutations, optimistic updates) pero requiere nueva dep.

**Decisión**: SWR. Zero new deps + mismo patrón F2.2 useAuth. F3.3 es read-only (no mutations desde el hook; mutations viven en containers via sesionActivaApi). SWR es ideal para read-heavy con refresh.

### 13.3 Logout implícito vs logout explícito (DEC-F3.3-03)

**Trade-off**: Logout implícito (chosen) cierra la sesión automáticamente post-cierre turno; UX minimal pero evita estado inconsistente. Logout explícito requiere botón adicional.

**Decisión**: Logout implícito per DEC-F3.3-03. Operador kiosko no quiere ver un botón extra después de cerrar turno — espera que el sistema lo devuelva al login automáticamente. F11.x puede agregar botón logout explícito si negocio requiere (forward).

### 13.4 409 vs 404 mapping en cierre (DEC-F3.3-07)

**Trade-off**: Backend emite 404 (chosen, REST-correct) cuando sesión ya cerrada. Frontend mapea 404 a UX "ya cerrada" (chosen). Forzar 409 desde backend requiere cambio backend (rejected).

**Decisión**: 404 backend + 404→UX mapping frontend. REST semantics consistente (recurso no encontrado). UX clara para operador. Cero cambios backend.

### 13.5 e2e sandbox F.6 SKIP vs CI override

**Trade-off**: SKIP-env (chosen, F2.x + F3.1 + F3.2 precedent) evita CI rotura pero deja e2e sin coverage local. CI override requiere Docker + npm compatible image.

**Decisión**: SKIP-env documentado como deviation D-env en `verify-report.md`. Unit tests + axe-core source-level SÍ corren. CI con image compatible (npm 11.16+) verde en local dev.

### 13.6 CerrarTurno placeholder vs arqueo completo (DEC-F3.3-06)

**Trade-off**: Placeholder (chosen) desacopla F3.3 de Fase 10 — F3.3 entrega sin esperar F10.x. Arqueo completo requiere `POST /caja/arqueo` + tolerancia + justificación + alerta `descuadre_critico` (F10.x deliverable).

**Decisión**: Placeholder. F3.3 entrega "minimum viable cierre" (PUT `/caja-sesion/sesion/{uuid}/cerrar` con `valor_final_*`); F10.x completa con arqueo completo (POST `/caja/arqueo` con `tipo_arqueo='cierre_turno'`). Atomic split + cada HU commiteable independientemente.

---

## 14. Precedents

| Precedent | Aplicación F3.3 | Source |
|---|---|---|
| **F3.1 (Login email+password)** | Container/Presentational split + RHF+Zod + i18n keys + 401 mapping + e2e axe-core pattern + DELTA stub precedent | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/` |
| **F3.2 (Lockout countdown + refresh)** | SWR `refreshInterval` pattern + `useCountdown` i18n + `<p role="status" aria-live="polite">` WCAG pattern + DELTA stub precedent | `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/` |
| **F2.2 (parkosFetch + authStore + useAuth)** | parkosFetch raw GET/POST/PUT + Mutex singleton preserved + SWR key null sin token + `refreshInterval` baseline (F3.3 hereda 50min F3.2) + `expiresAt` ISO 8601 + `setTokens`/`clear` + `useAuth().user.sucursal` | `apps/ui-kit/src/{fetch/parkosFetch.ts, store/authStore.ts, hooks/useAuth.ts}` |
| **F2.1 (Electron skeleton + shadcn)** | vitest + @testing-library/react + axe-core + playwright e2e pattern + i18n 7 namespaces + shadcn Form/Input/Button/Card/Textarea | `apps/electron-sucursal/src/renderer/components/ui/` + `e2e/a11y/wcag-2.1-aa.spec.ts` |
| **F1.13 (Arqueo backend + permission)** | `PUT /caja-sesion/sesion/{uuid}/cerrar` + `close_session_with_log` + `ls_session_guard` trigger + GAP-BE-05 permission fix — F3.3 consume via HTTP | `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/` |
| **F1.3 (Sesión única backend)** | `POST /caja-sesion/sesiones` + partial unique index 0023 + `GET /caja-sesion/sesion/me` + 409 mapping — F3.3 consume via HTTP | `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/` |
| **F1.15 (login histórico)** | DELTA precedent (user-facing behavior in spec) → F3.3 emite 6 new REQ-OPS-119..124 | `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/specs/operations/spec.md` |
| **DEC-SUC-03** | Kiosko desatendido + refresh 50min (F3.2 implementa) + operador no navega manualmente (F3.3 implementa redirect Dashboard) | `plan.md:418` |
| **DEC-F3.2-08 + DEC-F3.2-11** | DELTA verdict precedent (F3.2 emite 6 REQ-OPS-113..118 user-facing) — F3.3 replica con 6 REQ-OPS-119..124 | `openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/proposal.md §4.8, §4.11` |
| **DEC-F3.1-11** | DELTA verdict precedent (7 new REQ-OPS-106..112) — F3.3 replica pattern con 6 new REQ-OPS-119..124 | `openspec/changes/archive/2026-09-15-hu-f3-1-login-email-password/proposal.md §5.11` |

### 14.1 DEC-F3.3-08 + DEC-F3.3-12 verdict ratificación

F3.3 ES user-facing behavior observable en seis dimensiones: (a) pantalla AbrirTurno con campos decimales + RHF+Zod + submit POST `/caja-sesion/sesiones` (form visible + interacción); (b) pantalla CerrarTurno con form placeholder + submit PUT `/caja-sesion/sesion/{uuid}/cerrar` + logout implícito (form visible + interacción + redirect); (c) Dashboard `/` con redirect automático según sesión activa (navegación observable); (d) TurnoActivoPanel con resumen del turno abierto (timestamp apertura + valores iniciales + botón cerrar); (e) 409 `sesion_already_active` → UX "ya tenés un turno abierto" (error visible); (f) WCAG 2.1 AA axe-core 0 violaciones en AbrirTurno/CerrarTurno/TurnoActivoPanel (a11y compliance).

Per F1.15 + F3.1 + F3.2 precedent, user-facing ⇒ spec delta materialized. F3.3 emite 6 new REQ-OPS-119..124 en `openspec/changes/hu-f3-3-abrir-cerrar-turno/specs/operations/spec.md` siguiendo Given/When/Then/And RFC 2119 format F1.15 + F3.1 + F3.2 verbatim.

F2.x NO-OP precedent (DEC-ELEC-10, DEC-FETCH-10, DEC-UPD-13) NO aplica a F3.3 — esos HU son infra-only sin behavior visible al operador. F3.3 ES UI + UX behavior, sigue el precedent DELTA de F3.1 + F3.2.

---

## 15. DoD checklist (preliminar)

- [ ] 5 atomic commits landed (`feat(caja): useSesionActiva hook + sesionActivaApi`, `feat(caja): AbrirTurno page`, `feat(caja): CerrarTurno + ?closed=true feedback`, `feat(caja): Dashboard + TurnoActivoPanel + rutas`, `test(electron): 4 e2e turno`).
- [ ] 6 new REQ-OPS-119..124 materializadas en `openspec/changes/hu-f3-3-abrir-cerrar-turno/specs/operations/spec.md` (sdd-spec phase).
- [ ] Given/When/Then/And format RFC 2119 per F3.1 + F3.2 precedent verbatim.
- [ ] Anchor links explícitos a DEC-F3.3-NN ratificados en §4.
- [ ] 7 acceptance gates PASS source-level (G1 + G2 + G3 + G4 + G5 + G6 axe-core source + G7) + G6 runtime e2e SKIPPED-env documentado como D-env (NO project defect) per F.6 precedent.
- [ ] axe-core 0 violaciones WCAG 2.1 AA en AbrirTurno + CerrarTurno + TurnoActivoPanel (A1 e2e + G7 source-level).
- [ ] useSesionActiva hook exportado desde `features/caja/hooks/useSesionActiva.ts` consumible por F4.x/F5.x/F6.x/F10.x/F12.x (forward hooks §12).
- [ ] SesionAlreadyActiveError + SesionAlreadyClosedError typed errors exportados desde `sesionActivaApi.ts` (consumible cross-feature).
- [ ] useAuthStore.clear() invariante preservado (F2.2 DEC-FETCH-03 invariant intacto).
- [ ] parkosFetch pre-flight gate NO modificado (DEC-F3.3-10 — `/caja-sesion/*` no es critical-path).
- [ ] useAuthStore.expiresAt ISO 8601 UTC consumible por useSesionActiva (no F3.3 touch).
- [ ] i18n `caja.json` agrega 12 keys turno (`abrirTurno`, `cerrarTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `valorFinalEfectivo`, `valorFinalDatafono`, `observaciones`, `sesionYaAbierta`, `sesionYaCerrada`, `turnoCerradoExito`, `confirmarCierre`, `irAlTurno`, `turnoActivo`) — snapshot test verde.
- [ ] i18n `auth.json` agrega 1 key `closedSessionNotice` aria-live polite — snapshot test verde.
- [ ] 0 KNOWN-MISSING (pre-flight 10/10 PASS exploration §3).
- [ ] Author: `Parkos Dev <dev@parkos.local>` (F2.1 + F3.1 + F3.2 verbatim precedent).
- [ ] Conventional commits sin Co-authored-by, sin AI trailers.
- [ ] Numeración REQ-OPS monotónica verificada (REQ-OPS-118 vigente post-F3.2; F3.3 ocupa REQ-OPS-119..124, 0 gaps).
- [ ] READ-ONLY anchors respetados: backend `caja_sesion.py`, `session_cycle.py`, `sesion_activa.py`, `schemas/caja.py`, `parkos_core` exceptions, electron main/preload/bridge, `apps/ui-kit/src/{cn,tokens,store/authStore,fetch/parkosFetch,hooks/useAuth}.ts` (except read), `apps/electron-sucursal/electron/*`, `i18n/index.ts`, `modelo_datos_er.mmd`, `plan.md`.
- [ ] Sandbox F.6 caveat documentado en §10 + §15 como deviation esperada D-env (e2e SKIPPED-env), NO project defect.

---

## 16. Open questions

**Resoluciones de inconsistencies detectadas en exploration §1**:

1. **I1 — 409 vs 404 en cierre**: `plan.md:1340` menciona "409 sesion_ya_cerrada" en el cierre. El backend `caja_sesion.py:351-352` retorna `SessionNotFoundError` mapeado a 404 si la sesión ya está cerrada o no existe (no 409). **Resolution** (cerrada en DEC-F3.3-07): F3.3 frontend mapea 404 `sesion_not_found` a UX "esta sesión ya está cerrada" (mensaje claro, mismo efecto UX que 409). 404 es el código REST-correct; el mensaje UX es "ya está cerrada". Cero cambios backend.

2. **I2 — SWR config indefinida**: `plan.md:1336` dice `useSesionActiva` (hook, SWR) pero NO define SWR config (key, refreshInterval, error retry). **Resolution** (cerrada en DEC-F3.3-04): SWR key = `accessToken ? '/caja-sesion/sesion/me' : null` (mismo patrón F3.1 useAuth), `refreshInterval: REFRESH_INTERVAL_MS = 50min` (DEC-SUC-03 verbatim F3.2 heredado), `shouldRetryOnError` excluye 404 (esperado cuando no hay sesión), `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event.

3. **I3 — "arqueo inline" sin tabla `caja.arqueo`**: `plan.md:1336` menciona "arqueo inline" pero `modelo_datos_er.mmd` no tiene tabla `caja.arqueo` (arqueos viven en Fase 10 per `pending.md:51` — `tipo_arqueo` + `arqueo` [A] ya shipped F1.13). **Resolution** (cerrada en DEC-F3.3-06): `CerrarTurno.tsx` es placeholder con form simple para `valor_final_efectivo/datafono` (NO `POST /caja/arqueo` todavía — Fase 10 HU-F10.x entrega el flujo completo de arqueo con tolerancia + justificación + alerta).

4. **I4 — redirect destino indefinido**: `plan.md:1350` dice "redirect según exista o no sesión activa" pero no especifica el destino. **Resolution** (cerrada en DEC-F3.3-05): (a) si NO hay sesión activa → `navigate('/caja/abrir-turno')` (replace); (b) si hay sesión activa → renderizar dashboard placeholder (`TurnoActivoPanel` con `t('caja.turnoActivo')` + resumen + botón "Cerrar turno").

6. **I5 — `?closed=true` toast vs redirect**: `plan.md:1334` dice "redirect a login o a 'turno cerrado'". Interpretado como redirect a login (DEC-F3.3-03). Feedback "turno cerrado" implementado via `?closed=true` query param + `<p role="status" aria-live="polite">` en Login page (DEC-F3.3-09). Forward F11.x usa shadcn toast component para notificación más visible.

**Notas para `sdd-verify`**:

- **N1**: tsc clean post-T1..T4 — verificar que `apps/electron-sucursal/tsconfig.*` compila sin errores después de agregar `useSesionActiva`, `sesionActivaApi`, `AbrirTurno`, `CerrarTurno`, `Dashboard`, `TurnoActivoPanel`, `AbrirTurnoForm`, `CerrarTurnoForm`.
- **N2**: axe-core 0 violaciones en `<AbrirTurno>` + `<CerrarTurno>` + `<TurnoActivoPanel>` — REQ-OPS-124 gate. Verificar que el axe-core scan no reporta violaciones de WCAG 2.1 AA (color contrast, aria-live polite, role=status, aria-label, form labels).
- **N3**: MSW 2.x setup in `turno.spec.ts` — F3.3 introduce MSW mock para 409 `sesion_already_active` + 200 OK + 404 `sesion_not_found`. Verificar que el setup MSW no rompe los tests existentes (F3.1 `loginApi.test.ts` + `login.spec.ts` + F3.2 `lockout.spec.ts`).
- **N4**: `useAuthStore.clear()` post-cierre turno — verificar que el IPC `bridge.authStore.delete` se invoca correctamente vía mock en `CerrarTurno.test.tsx`. Si IPC falla en test env, mock retorna void y test verifica que `useAuthStore.accessToken === null` post-clear.
- **N5**: parkosFetch 409 vs 404 mapping — verificar que `SesionAlreadyActiveError` (409) y `SesionAlreadyClosedError` (404) son thrown por `sesionActivaApi.abrirSesion` + `cerrarSesion` respectivamente, con `status` + `code` correctos.

**0 KNOWN-MISSING** (pre-flight 10/10 PASS + 0 KNOWN-MISSING en exploration §16). Items N1..N5 son verificaciones standard en `sdd-verify`, NO blockers.

---

## CHANGELOG

- (2026-09-15) F3.3 propose phase complete — 16 secciones + CHANGELOG, 12 DEC-F3.3-01..12 (DEC-F3.3-11 + DEC-F3.3-12 NUEVAS, esta proposal), 5 riesgos R1..R5 (subset de exploration §8 R1..R8 con focus top-5), 7 acceptance gates G1..G7, 5 atomic tasks T1..T5, 1 cluster C1. Numeración REQ-OPS monotónica verificada: REQ-OPS-118 vigente post-F3.2 archive; F3.3 ocupa REQ-OPS-119..124 (6 new requirements, 0 gaps). Pre-flight 10/10 PASS + 0 KNOWN-MISSING. DEC-F3.3-08 + DEC-F3.3-11 + DEC-F3.3-12 verdict = **DELTA** (F3.3 IS user-facing: AbrirTurno + CerrarTurno + Dashboard redirect + TurnoActivoPanel + 409/404 mapping + logout implícito + WCAG). 5 inconsistencies (I1 409 vs 404 cierre; I2 SWR config; I3 arqueo placeholder; I4 redirect destino; I5 `?closed=true` toast vs redirect) cerradas en DEC-F3.3-04, DEC-F3.3-05, DEC-F3.3-06, DEC-F3.3-07, DEC-F3.3-09. Sandbox F.6 deviation esperada documentada en §10 + §15 (e2e SKIPPED-env, NO project defect). Precedente directo: F3.2 archivado 2026-09-15 con 6 REQ-OPS-113..118 user-facing DELTA — F3.3 replica pattern con 6 REQ-OPS-119..124 (tercer DELTA en Fase 3). Ready for `sdd-spec` + `sdd-design` (paralelo).

---

**End of proposal — HU-F3.3.**