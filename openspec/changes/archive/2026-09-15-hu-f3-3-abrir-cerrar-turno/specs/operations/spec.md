# Delta Spec — HU-F3.3 Abrir y cerrar turno (caja-sesion con valor_inicial_efectivo/datafono + arqueo inline placeholder + redirect según sesión activa)

> **Phase**: spec (sdd-spec) · **Status**: ready for sdd-design (parallel) + sdd-tasks
> **HU ID**: HU-F3.3 (Fase 3 — tercera HU; Autenticación y turno de caja, primer consumer transversal de `caja-sesion`)
> **Change**: `hu-f3-3-abrir-cerrar-turno`
> **Spec canonical**: `openspec/specs/operations/spec.md` (v: post-F3.2, 118 REQ-OPS-001..118)
> **Delta type**: MATERIALIZED con 6 new REQ-OPS-119..124 (user-facing behavior per F1.15 + F3.1 + F3.2 precedent)
> **DEC-F3.3-08 + DEC-F3.3-11 + DEC-F3.3-12 verdict**: DELTA stub (NOT NO-OP) — F3.3 IS user-facing behavior observable (AbrirTurno form + CerrarTurno form + useSesionActiva SWR + TurnoActivoPanel + Dashboard redirect + 409/404 UX mapping + logout implícito post-200 + ?closed=true feedback + WCAG 2.1 AA compliance).

---

## 0. Metadata

- **HU**: HU-F3.3
- **Fase**: 3 (Autenticación y turno de caja — tercera HU; gating transversal para F4.x+)
- **Spec delta type**: MATERIALIZED DELTA (NOT NO-OP stub)
- **New REQ-OPS**: 6 (REQ-OPS-119..124)
- **Author**: Parkos Dev <dev@parkos.local>
- **Date**: 2026-09-15
- **Branch**: `feat/fase-3-turno` (HEAD `fde9850`, F3.1 archivado 2026-09-15 con 7 REQ-OPS-106..112; F3.2 archivado 2026-09-15 con 6 REQ-OPS-113..118; F3.3 commitea sobre la misma rama per `pending.md:6`)
- **PR target**: `origin/dev`
- **Precedente directo**: F3.2 (Lockout countdown + refresh 50min + pre-flight gate) archivado 2026-09-15 con 6 new REQ-OPS-113..118 user-facing (`openspec/changes/archive/2026-09-15-hu-f3-2-lockout-refresh-pre-flight/specs/operations/spec.md`). Precedente histórico: F3.1 (Login email+password) archivado 2026-09-15 con 7 new REQ-OPS-106..112 + F1.15 (login histórico) archivado 2026-09-15 con 4 new REQ-OPS-102..105.
- **Spec canonical vigente**: 118 REQ-OPS (REQ-OPS-001..118) + 6 XR (REQ-OPS-XR1..XR6) post-F3.2 archive.
- **Numeración monotónica verificada**: 118 → 119 → 120 → 121 → 122 → 123 → 124 (0 gaps, sin duplicados). Materialization al canonical `operations/spec.md` ocurre en `sdd-archive` phase, NO en spec phase.

---

## 1. Contexto y motivación

Esta delta cierra el **gap UX crítico** que F3.1 + F3.2 archivados 2026-09-15 dejaron abiertos en el ciclo de vida transaccional del operador kiosko: aunque el login funciona y el refresh del `access_token` está blindado, **ningún flujo operativo puede correr sin turno abierto** — un operador autenticado sin sesión de caja no puede facturar, cobrar, ni cerrar caja. F3.3 entrega el flujo end-to-end de apertura y cierre de turno, anclando el comportamiento observable al operador en 6 new REQ-OPS-119..124 dentro del spec canónico.

A diferencia de F2.1/F2.2/F2.3 (infra-only con NO-OP stub per `DEC-ELEC-10`, `DEC-FETCH-10`, `DEC-UPD-13`), F3.3 ES user-facing behavior observable en seis dimensiones: (a) pantalla AbrirTurno con campos decimales `inputMode="decimal"` + RHF+Zod + submit POST `/caja-sesion/sesiones` (form visible + interacción); (b) pantalla CerrarTurno con form placeholder + RHF+Zod + submit PUT `/caja-sesion/sesion/{uuid}/cerrar` + logout implícito post-200 (form visible + interacción + redirect); (c) Dashboard `/` con redirect automático según sesión activa (navegación observable); (d) TurnoActivoPanel con resumen del turno abierto (timestamp apertura + valores iniciales + botón cerrar); (e) 409 `sesion_already_active` mapeado a UX "ya tenés un turno abierto" + 404 `sesion_already_closed` mapeado a "esta sesión ya está cerrada" (errores visibles); (f) WCAG 2.1 AA axe-core 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel + feedback `?closed=true` post-cierre (a11y compliance). Esta behavior visible al usuario no puede vivir solo en `DEC-F3.3-NN` dentro de `proposal.md` — debe anclarse en `REQ-OPS-NNN` dentro del spec canónico `operations/spec.md`.

`DEC-F3.3-08 + DEC-F3.3-11 + DEC-F3.3-12` (introducidos en `proposal.md §4.8 + §4.11 + §4.12`) **rompen** el precedent NO-OP de F2.x y adoptan precedent F1.15 + F3.1 + F3.2. Las 6 new REQ-OPS-119..124 documentan el comportamiento observable al operador en formato Given/When/Then/And RFC 2119, con anchor links explícitos a `DEC-F3.3-NN` ratificados en `proposal.md §4`. Las decisiones técnicas viven en `proposal.md` (qué hace cada componente, layout, archivos), las requirements viven en este spec (qué comportamiento debe ser verdadero post-cambio).

Adicionalmente, F3.3 entrega **`useSesionActiva`** como segundo hook genuinely reusable del feature `caja` — se exporta desde `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` para forward consumption F4.x (catálogos), F5.x (facturación), F6.x+ (ingreso/salida/cobro/FE/suscripciones), F10.x (arqueos completos), F12.x (reportería local). El pattern SWR con `refreshInterval: REFRESH_INTERVAL_MS = 50min` (DEC-SUC-03 heredado de F3.2 REQ-OPS-117) + `shouldRetryOnError` excl 404 + `onError` con `status===401` dispara `useAuthStore.clear()` es **idéntico** al precedent F3.1 `useAuth` (F2.2 baseline) y F3.2 useCountdown. Defense in depth XR6 contribution: F3.3 suma las capas contract (Zod + 409/404 typed errors) + a11y (WCAG axe-core) sobre la base sentada por F1.3 (partial unique index `prod.uq_prod_sesion_one_active_per_user` migration 0023) + F1.13 (`ls_session_guard` trigger + `close_session_with_log`).

---

## 2. Goals y no-goals

### 2.1 Goals in-scope (6 new REQ-OPS)

| REQ-OPS | Comportamiento observable al operador |
|---|---|
| **REQ-OPS-119** | `AbrirTurno` flow: POST `/caja-sesion/sesiones` con `valor_inicial_efectivo` + `valor_inicial_datafono` (decimales ≥0) + `observaciones` opcional; 200 OK → SesionRead; 409 `sesion_already_active` → UX "ya tenés un turno abierto" + botón "Ir al turno"; Zod local validation |
| **REQ-OPS-120** | `useSesionActiva` SWR hook: key `accessToken ? '/caja-sesion/sesion/me' : null` + `refreshInterval: REFRESH_INTERVAL_MS = 50min` + `shouldRetryOnError` excl 404 + `onError` con `status===401` dispara `useAuthStore.clear()` + `parkos:auth:cleared` event |
| **REQ-OPS-121** | `TurnoActivoPanel` organism: renderiza uuid + timestamp_apertura (`formatDistanceToNow`) + `valor_inicial_efectivo` + `valor_inicial_datafono` + observaciones (si hay) + botón "Cerrar turno" → `/caja/cerrar-turno` |
| **REQ-OPS-122** | `CerrarTurno` flow: PUT `/caja-sesion/sesion/{uuid}/cerrar` con `valor_final_efectivo` + `valor_final_datafono` + `observaciones_cierre` opcional; 200 OK → `useAuthStore.clear()` (logout implícito) + `navigate('/login?closed=true')`; 404 `sesion_not_found` → UX "esta sesión ya está cerrada" + redirect login |
| **REQ-OPS-123** | `Dashboard` `/` redirect rule: consume `useSesionActiva()`; `sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno')` (replace); `sesion !== null` → render `<TurnoActivoPanel>`; `error && status !== 404` → error state + retry |
| **REQ-OPS-124** | `Login` page `?closed=true` detection: detecta `useLocation().search.includes('closed=true')` → render `<p role="status" aria-live="polite">{t('caja.turnoCerradoExito')}</p>` arriba del form (sin reemplazar el form); WCAG 2.1 AA compliance: axe-core 0 violaciones en `<AbrirTurno>` + `<CerrarTurno>` + `<TurnoActivoPanel>` + feedback post-cierre (RNF-022, extiende REQ-OPS-112 F3.1 + REQ-OPS-118 F3.2 precedent) |

### 2.2 Out of scope (deferred a Fase 3+)

- **Backend cambios** — `POST /caja-sesion/sesiones` + `PUT /caja-sesion/sesion/{uuid}/cerrar` + `GET /caja-sesion/sesion/me` + permission `abrir_cerrar_caja` (GAP-BE-05 fix site #2) + partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023) + trigger `ls_session_guard` ya shipped F1.3 + F1.13. F3.3 NO modifica backend (DEC-F3.3-07).
- **Arqueo completo (Fase 10)** — `CerrarTurno.tsx` es placeholder con form simple `valor_final_efectivo/datafono`. NO consume `POST /caja/arqueo` (Fase 10 HU-F10.x entrega flujo completo con tolerancia + justificación + alerta `descuadre_critico`) per DEC-F3.3-06.
- **Sync de sesion cerrada** — `prod.sesion` [L-S] ya está en `sync_catalog` branch→cloud per F1.13 §6.5 verified. F3.3 NO toca sync catalog.
- **Reverso de pagos** — `factura_pagos` [A] con `tipo_movimiento = 'pago | reverso'` — fuera scope F3.3 (forward F5.x).
- **AuthGuard component** — F3.3 NO crea `<AuthGuard>` que envuelve `<Routes>` excepto `/login`. Forward hook F3.x+ intercepta `parkos:auth:cleared` → `navigate('/login?next=...')`.
- **Logout button UI explícito** — F3.3 hace `useAuthStore.clear()` post-cierre de turno (logout implícito per DEC-F3.3-03). Botón UI dedicado es forward hook.
- **Multi-sucursal selector** — JWT ya pinea sucursal (single-branch kiosko per DEC-F3.1-04). F3.3 lee `useAuth().user.sucursal.uuid` directamente.
- **Edición post-apertura de valores iniciales** — `SesionUpdate` Pydantic schema permite late corrections (caja_sesion.py:218-238), pero F3.3 NO expone UI — read-only en CerrarTurno y TurnoActivoPanel.
- **`useCountdown` para "tiempo restante de turno"** — F3.3 muestra `timestamp_apertura` formateado (`formatDistanceToNow` con date-fns). NO countdown regresivo.
- **Toast notifications post-cierre** — `?closed=true` + `<p role="status">` es suficiente UX para F3.3. Forward F11.x usa shadcn Toast component.
- **Permisos granulares por acción** — backend ya emite 403 si `permisos[]` no incluye `abrir_cerrar_caja`. F3.3 NO agrega client-side permission gating (Defense in depth XR6 — backend source of truth).
- **Idempotency-Key manual en apertura** — `parkosFetch` ya genera SHA-256 de `method|path|body` para POST `/caja-sesion/*` (skip `/auth/login` only). F3.3 NO requiere override.
- **Suscripciones + ingresos recurrentes** — CU-06 fuera Fase 3 (F9.x).
- **Reportes CU-09** — F12.x consume `useSesionActiva` post-F3.3.
- **Extensión de `PRE_FLIGHT_PATHS`** — F3.3 NO modifica `parkosFetch.ts`. `/caja-sesion/*` no es critical-path per DEC-F3.3-10 + DEC-SUC-03.
- **A11y biblioteca externa** — axe-core via `@axe-core/playwright` F2.1 baseline. NO nueva dep.

---

## 3. Requirements (REQ-OPS-119..124)

### REQ-OPS-119 — `AbrirTurno` flow con POST `/caja-sesion/sesiones` + 409 `sesion_already_active` (DEC-F3.3-01 + DEC-F3.3-02 + DEC-F3.3-08)

**Source**: HU-F3.3 (`plan.md:1327-1352` + `DEC-F3.3-01` container/presentational + `DEC-F3.3-02` inputMode decimal + `DEC-F3.3-08` DELTA verdict + plan.md:1338 Zod schema verbatim) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<AbrirTurno>` (page container) MUST invocar `sesionActivaApi.abrirSesion(payload)` que ejecuta `parkosFetch<SesionRead>('/caja-sesion/sesiones', { method: 'POST', body: payload, idempotencyKey: auto })` cuando el operador submitea el form. El payload MUST contener `uuid_sucursal` (leído de `useAuth().user.sucursal.uuid`) + `uuid_usuario` (leído de `useAuth().user.id`) + `valor_inicial_efectivo: number ≥0` + `valor_inicial_datafono: number ≥0` + `observaciones: string` opcional. La validación local Zod MUST aplicar `z.object({ valor_inicial_efectivo: z.number().min(0), valor_inicial_datafono: z.number().min(0), observaciones: z.string().optional() })` (plan.md:1338 verbatim). Los `<Input>` MUST renderizarse con `type="number" inputMode="decimal" step="0.01"` (DEC-F3.3-02 — teclado numérico mobile + WCAG compliance). El submit MUST invocar `useForm` con `zodResolver(turnoSchema)` antes del `parkosFetch` (defense in depth — Zod local + backend Pydantic validan ambos lados). Ante respuesta `200 OK` con `SesionRead` válido, el componente MUST ejecutar `navigate('/')` (replace) — `useSesionActiva()` re-fetcha automáticamente por SWR key change. Ante respuesta `409 Conflict` con body `{"error": "sesion_already_active"}` (proveniente de `partial unique index prod.uq_prod_sesion_one_active_per_user` migration 0023 — KD-3 BD-only, sin pre-check), `sesionActivaApi.abrirSesion` MUST rechazar con `SesionAlreadyActiveError extends ParkosHttpError` (status=409, code='sesion_already_active') y `<AbrirTurno>` MUST renderizar `<FormMessage role="alert">{t('caja.sesionYaAbierta')}</FormMessage>` + un `<Button onClick={() => navigate('/')}>{t('caja.irAlTurno')}</Button>` (UX clara, no error genérico).

**Rationale**: La partial unique index garantiza BD-level que un mismo `uuid_usuario` no tenga DOS filas con `timestamp_cierre IS NULL`. Sin el mapping 409→UX claro, el operador kiosko no entiende por qué "Algo salió mal" cuando intenta abrir un segundo turno. Defense in depth bidireccional: backend rechaza BD-level; frontend valida UX-level. El `inputMode="decimal"` es crítico para kiosko mobile — sin él, el operador ve teclado QWERTY completo en mobile/electron (DEC-F3.3-02).

**Source**: `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.tsx` (NEW T2 ~70 LOC); `apps/electron-sucursal/src/features/caja/components/AbrirTurnoForm.tsx` (NEW T2 ~50 LOC presentational); `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts` (NEW T1 ~25 LOC — `abrirSesion` + `SesionAlreadyActiveError`); `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY T2 +6 keys: `abrirTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `observaciones`, `sesionYaAbierta`, `irAlTurno`); `apps/electron-sucursal/src/features/caja/pages/AbrirTurno.test.tsx` (NEW T2 ~50 LOC — U9 submit OK + U10 409 mensaje + U11 validaciones Zod); `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:73-243` (READ ONLY — endpoint ya shipped F1.3); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:188-356` (READ ONLY — `open_session` + `SesionAlreadyActive` mapping 23505 → 409).

#### Scenario 1: AbrirTurno happy path — 200 OK → SesionRead + redirect `/`
- **Given** el operador autenticado con `useAuth().user.sucursal.uuid = :s` y `useAuth().user.id = :u`
- **And** el form completo con `valor_inicial_efectivo = 50000`, `valor_inicial_datafono = 0`, `observaciones = 'Apertura turno mañana'`
- **And** MSW mockea `POST /caja-sesion/sesiones` retornando `200 OK` con `SesionRead{uuid: 'new-uuid', uuid_sucursal: ':s', uuid_usuario: ':u', valor_inicial_efectivo: 50000, valor_inicial_datafono: 0, timestamp_apertura: NOW(), timestamp_cierre: null}`
- **When** el operador hace click en "Abrir turno" (submit form)
- **Then** Zod validation MUST pasar (los 3 campos cumplen schema)
- **And** `parkosFetch` MUST enviar `POST /caja-sesion/sesiones` con `Authorization: Bearer <accessToken>` + body JSON con los 3 campos
- **And** el componente MUST ejecutar `navigate('/')` (replace)
- **And** `useSesionActiva()` MUST re-fetchar (SWR detecta key change → nueva sesión activa retornada)
- **And** `<Dashboard>` MUST renderizar `<TurnoActivoPanel>` con los valores enviados.

#### Scenario 2: 409 `sesion_already_active` → UX "ya tenés un turno abierto" + botón "Ir al turno"
- **Given** el operador intenta abrir un segundo turno mientras tiene sesión activa
- **And** MSW mockea `POST /caja-sesion/sesiones` retornando `409 Conflict` con body `{"error": "sesion_already_active"}` (proveniente de partial unique index 0023)
- **When** el operador submitea el form
- **Then** `sesionActivaApi.abrirSesion` MUST rechazar con `SesionAlreadyActiveError(status=409, code='sesion_already_active')`
- **And** `<AbrirTurno>` MUST renderizar `<FormMessage role="alert">{t('caja.sesionYaAbierta')}</FormMessage>` (mensaje "Ya tenés un turno abierto")
- **And** MUST renderizar `<Button onClick={() => navigate('/')}>{t('caja.irAlTurno')}</Button>` ("Ir al turno")
- **And** el operador MUST ver el mensaje i18n claro, NO "Algo salió mal" genérico.

#### Scenario 3: Validación Zod local rechaza `valor_inicial_efectivo < 0` antes del POST
- **Given** el operador tipea `valor_inicial_efectivo = -100` en el `<Input type="number">`
- **When** el operador hace blur del campo o intenta submit
- **Then** Zod resolver MUST retornar error de validación (`min(0)` violated)
- **And** `<FormMessage>` MUST mostrar mensaje inline de error (no se envía POST al backend)
- **And** el `parkosFetch` MUST NO invocarse (defense in depth — Zod local previene request inválido)
- **And** MSW MUST NO recibir el POST (test verifica que el handler `sesion-create` no fue llamado).

---

### REQ-OPS-120 — `useSesionActiva()` SWR hook con refresh 50min + 404 null + 401 clear (DEC-F3.3-04 + DEC-SUC-03 + F3.2 REQ-OPS-117 precedent)

**Source**: HU-F3.3 (`plan.md:1336` + `DEC-F3.3-04` SWR config + `DEC-SUC-03` 50min verbatim + F3.2 REQ-OPS-117 refresh precedent) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El hook `useSesionActiva(): { sesion: SesionRead | null; isLoading: boolean; error: Error | undefined; refresh: () => Promise<SesionRead | undefined> }` MUST consumir `useAuthStore(s => s.accessToken)` y MUST configurar `useSWR` con: (1) `key: accessToken ? '/caja-sesion/sesion/me' : null` (key null sin token, idéntico pattern F3.1 useAuth); (2) `fetcher: () => sesionActivaApi.getSesionActiva()`; (3) `refreshInterval: REFRESH_INTERVAL_MS` donde `REFRESH_INTERVAL_MS = 50 * 60 * 1000` constante exportada desde el módulo (DEC-SUC-03 verbatim heredado F3.2 — `ACCESS_TOKEN_TTL (3600s) - REFRESH_INTERVAL_MS (3000s) = 600s = 10min` safety margin); (4) `dedupingInterval: 10 * 1000` (evita refetch simultáneo cuando múltiples componentes consumen el hook — Dashboard + CerrarTurno consumen en paralelo); (5) `shouldRetryOnError: (err) => err?.status !== 404` (404 es estado esperado cuando operador sin sesión activa — NO retry spam); (6) `onError: (err) => { if (err?.status === 401) { useAuthStore.getState().clear() /* borra tokens vía IPC bridge.authStore.delete */; window.dispatchEvent(new Event('parkos:auth:cleared')) /* forward hook AuthGuard F3.x+ */ } }` (401 dispara logout defensivo, idéntico pattern F3.1 useAuth). El fetcher MUST invocar `sesionActivaApi.getSesionActiva()` que internamente ejecuta `parkosFetch('/caja-sesion/sesion/me')` con manejo 404 → retorna `null` (NO lanza error — operador sin sesión es estado válido). El hook MUST retornar `{ sesion: data ?? null, isLoading, error: error?.status === 404 ? undefined : error, refresh: mutate }` — `error` se omite cuando es 404 para no contaminar consumers (Dashboard no muestra error cuando operador sin sesión, simplemente muestra redirect).

**Rationale**: Mismo pattern F3.1 useAuth (F2.2 baseline) + F3.2 REQ-OPS-117 50min refresh. SWR `dedupingInterval: 10s` evita refetch simultáneo cuando múltiples componentes (Dashboard + CerrarTurno + TurnoActivoPanel en el futuro F11.x) consumen el hook en paralelo. Forward extensibilidad: F4.x+ consumen `useSesionActiva()` para garantizar sesión activa antes de POST críticos (ya cubiertos por pre-flight gate F3.2 para `/facturacion/*` + `/caja/arqueo` per DEC-F3.3-10).

**Source**: `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` (NEW T1 ~40 LOC); `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.test.ts` (NEW T1 ~40 LOC — U1 SWR key null sin token + U2 SWR fetch OK + U3 SWR 404 → sesion null + U4 SWR 401 dispara `parkos:auth:cleared`); `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts` (NEW T1 ~25 LOC — `getSesionActiva` con manejo 404 → null); `apps/ui-kit/src/store/authStore.ts:71-128` (F2.2 READ ONLY — `setTokens` + `clear` + `refreshAccessToken` Mutex); `apps/ui-kit/src/hooks/useAuth.ts:60` (F2.2/F3.2 — `refreshInterval: REFRESH_INTERVAL_MS = 50min` precedent); `apps/ui-kit/src/fetch/parkosFetch.ts` (F2.2/F3.2 READ ONLY — `Idempotency-Key` auto + 401 retry-once via Mutex); `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:218-243` (READ ONLY — `GET /sesion/me` retorna 404 si sin sesión activa).

#### Scenario 1: SWR key null sin token — hook retorna sesion null sin fetch
- **Given** el operador no está autenticado (`useAuthStore.accessToken === null`)
- **When** un componente invoca `useSesionActiva()`
- **Then** la SWR key MUST ser `null` (string vacío convertido a null por la expresión ternaria)
- **And** SWR MUST NO ejecutar el fetcher (key null skip)
- **And** el hook MUST retornar `{ sesion: null, isLoading: false, error: undefined, refresh: <fn> }`
- **And** ningún `parkosFetch('/caja-sesion/sesion/me')` MUST ejecutarse (verificable con MSW handler spy — no calls).

#### Scenario 2: SWR fetch OK con sesión activa — hook retorna sesion poblada
- **Given** el operador está autenticado (`useAuthStore.accessToken !== null`)
- **And** MSW mockea `GET /caja-sesion/sesion/me` retornando `200 OK` con `SesionRead{uuid: 'active-uuid', valor_inicial_efectivo: 50000, timestamp_apertura: '2026-09-15T08:00:00Z', ...}`
- **When** un componente invoca `useSesionActiva()` por primera vez
- **Then** SWR MUST ejecutar `parkosFetch('/caja-sesion/sesion/me')` con la SWR key `/caja-sesion/sesion/me`
- **And** el hook MUST retornar `{ sesion: { uuid: 'active-uuid', ... }, isLoading: false, error: undefined, refresh: <fn> }`.

#### Scenario 3: SWR fetch 404 — hook retorna sesion null sin error (operador sin turno es estado válido)
- **Given** el operador autenticado pero sin sesión activa
- **And** MSW mockea `GET /caja-sesion/sesion/me` retornando `404 Not Found` con body `{"error": "sesion_no_active"}`
- **When** un componente invoca `useSesionActiva()`
- **Then** `sesionActivaApi.getSesionActiva()` MUST capturar el 404 y retornar `null` (NO lanza error)
- **And** SWR MUST NO reintentar (`shouldRetryOnError: err?.status !== 404`)
- **And** el hook MUST retornar `{ sesion: null, isLoading: false, error: undefined, refresh: <fn> }`
- **And** `<Dashboard>` MUST leer `sesion === null` y ejecutar `navigate('/caja/abrir-turno')` per REQ-OPS-123.

#### Scenario 4: SWR 401 onError → `useAuthStore.clear()` + `parkos:auth:cleared` window event
- **Given** el operador autenticado pero con token expirado (backend responde 401 a `GET /sesion/me`)
- **And** MSW mockea `GET /caja-sesion/sesion/me` retornando `401 Unauthorized`
- **When** un componente invoca `useSesionActiva()` y SWR ejecuta el fetcher
- **Then** `onError` MUST capturar el error con `status === 401`
- **And** MUST invocar `useAuthStore.getState().clear()` (borra accessToken/refreshToken/expiresAt vía IPC `bridge.authStore.delete` per F2.2)
- **And** MUST despachar `new Event('parkos:auth:cleared')` en `window` (forward hook para AuthGuard F3.x+ que intercepta y navega a `/login?next=...'`)
- **And** el hook MUST retornar `{ sesion: null, isLoading: false, error: <error401>, refresh: <fn> }`.

#### Scenario 5: refreshInterval 50min alinea con ACCESS_TOKEN_TTL = 3600s (DEC-SUC-03 verbatim)
- **Given** `REFRESH_INTERVAL_MS` exportado desde `useSesionActiva.ts`
- **When** `useSesionActiva.test.ts` ejecuta `expect(REFRESH_INTERVAL_MS).toBe(50 * 60 * 1000)`
- **Then** el assertion MUST pasar (3_000_000ms exact, F3.2 precedent REQ-OPS-117 Scenario 2)
- **And** el test MUST verificar safety margin 10min — si SWR refresh scheduled at T+50min falla, el operador tiene hasta T+60min antes de 401 forzado (TTL expiration).

---

### REQ-OPS-121 — `TurnoActivoPanel` organism con uuid + timestamp + valores iniciales + botón cerrar (DEC-F3.3-05)

**Source**: HU-F3.3 (`plan.md:1336` + `DEC-F3.3-05` Dashboard/TurnoActivoPanel layout + `plan.md:1338` Zod + DEC-F3.3-02 inputMode decimal) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El componente presentational `<TurnoActivoPanel sesion={...} onCerrarClick={...}>` MUST renderizar un `<Card>` de shadcn con: (1) `<CardTitle>{t('caja.turnoActivo')}</CardTitle>` (título i18n); (2) `<CardContent>` con `<p><strong>UUID:</strong> {sesion.uuid}</p>` (identificador visible al operador — copyable via click + tooltip, útil para soporte), `<p><strong>Apertura:</strong> {formatDistanceToNow(sesion.timestamp_apertura, { locale: es, addSuffix: true })}</p>` (formato relativo con `date-fns` para kiosko UX legible — "hace 2 horas" en vez de timestamp ISO crudo), `<p><strong>Valor inicial efectivo:</strong> {formatCOP(sesion.valor_inicial_efectivo)}</p>` (formato moneda colombiana con separador de miles), `<p><strong>Valor inicial datáfono:</strong> {formatCOP(sesion.valor_inicial_datafono)}</p>`, y opcionalmente `<p><strong>Observaciones:</strong> {sesion.observaciones}</p>` solo si `sesion.observaciones` es truthy; (3) `<CardFooter>` con `<Button variant="default" onClick={onCerrarClick}>{t('caja.cerrarTurno')}</Button>` (botón primario "Cerrar turno" — wired al callback que ejecuta `navigate('/caja/cerrar-turno')` desde `<Dashboard>` container). El componente MUST ser puramente presentational — NO consume `useSesionActiva`, NO invoca `parkosFetch`, NO maneja estado interno más allá de props (idéntico pattern F3.1 `LoginForm` container/presentational split DEC-F3.1-02). El `formatCOP` helper MUST usar `Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 })` (formato local colombiano — sin decimales para efectivo/datáfono kiosko, aunque DB persiste NUMERIC(18,4) per `modelo_datos_er.mmd`). El componente MUST ser accesible WCAG 2.1 AA: `<Card>` con `role="region"` implícito vía shadcn semantics, headings semánticos (`<CardTitle>` → `<h3>`), contraste de color ≥4.5:1 via CSS tokens F2.1 baseline, foco visible al tab del `<Button>`.

**Rationale**: El operador kiosko llega al terminal, hace login (F3.1), ve `<Dashboard>` que renderiza `<TurnoActivoPanel>` con el resumen de su turno abierto. Sin este resumen legible, el operador no sabe cuánto tiempo lleva de turno ni cuánto efectivo declaró al abrir. F3.3 entrega la información mínima legible para que el operador se ubique y decida si cierra turno. Container/Presentational split mantiene testeabilidad (DEC-F3.1-02 verbatim) — presentational testeable con `@testing-library/react` sin mocks; container (Dashboard) testea orquestación.

**Source**: `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx` (NEW T4 ~30 LOC); `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (NEW T4 ~30 LOC container que renderiza `<TurnoActivoPanel>`); `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.test.tsx` (NEW T4 ~25 LOC — snapshot test + render tests); `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY T4 +1 key `turnoActivo`); `date-fns` (F3.3 introduce dep opcional — ya shipped F2.1 baseline per package.json); `apps/electron-sucursal/src/renderer/components/ui/Card.tsx` (F2.1 shadcn primitives — Card + CardHeader + CardTitle + CardContent + CardFooter READ ONLY).

#### Scenario 1: TurnoActivoPanel renderiza uuid + timestamp + valores iniciales
- **Given** el operador tiene sesión activa con `sesion = { uuid: 'sess-uuid-123', timestamp_apertura: '2026-09-15T08:00:00Z', valor_inicial_efectivo: 50000, valor_inicial_datafono: 0, observaciones: 'Apertura turno mañana' }`
- **When** `<Dashboard>` renderiza `<TurnoActivoPanel sesion={sesion} onCerrarClick={jest.fn()} />`
- **Then** el componente MUST renderizar `<CardTitle>Turno activo</CardTitle>`
- **And** MUST renderizar `<p>UUID: sess-uuid-123</p>`
- **And** MUST renderizar `<p>Apertura: hace 2 horas</p>` (formato `formatDistanceToNow` con `addSuffix: true` y `locale: es` desde `date-fns/locale/es`)
- **And** MUST renderizar `<p>Valor inicial efectivo: $ 50.000</p>` (formato `Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP' })`)
- **And** MUST renderizar `<p>Valor inicial datáfono: $ 0</p>`
- **And** MUST renderizar `<p>Observaciones: Apertura turno mañana</p>` (porque `sesion.observaciones` es truthy).

#### Scenario 2: TurnoActivoPanel OMITE bloque Observaciones cuando observaciones es null/empty
- **Given** sesión activa con `observaciones = null` o `observaciones = ''`
- **When** `<Dashboard>` renderiza `<TurnoActivoPanel sesion={sesion} onCerrarClick={jest.fn()} />`
- **Then** el componente MUST NO renderizar el bloque `<p>Observaciones: ...</p>` (operador sin notas no ve línea vacía).

#### Scenario 3: Botón "Cerrar turno" invoca callback onCerrarClick (wired al navigate)
- **Given** `<Dashboard>` renderiza `<TurnoActivoPanel onCerrarClick={() => navigate('/caja/cerrar-turno')} />`
- **When** el operador hace click en el `<Button>Cerrar turno</Button>`
- **Then** el callback `onCerrarClick` MUST invocarse exactamente una vez
- **And** `<Dashboard>` MUST ejecutar `navigate('/caja/cerrar-turno')` que monta `<CerrarTurno>` (REQ-OPS-122).

---

### REQ-OPS-122 — `CerrarTurno` flow con PUT `/sesion/{uuid}/cerrar` + logout implícito + 404→"ya cerrada" UX (DEC-F3.3-03 + DEC-F3.3-06 + DEC-F3.3-07)

**Source**: HU-F3.3 (`plan.md:1336` + `DEC-F3.3-03` logout implícito + `DEC-F3.3-06` placeholder arqueo + `DEC-F3.3-07` 404 mapping + `plan.md:1340` errores verbatim) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<CerrarTurno>` (page container) MUST invocar `sesionActivaApi.cerrarSesion(sesion.uuid, payload)` que ejecuta `parkosFetch<SesionRead>('/caja-sesion/sesion/{uuid}/cerrar', { method: 'PUT', body: payload, idempotencyKey: auto })` cuando el operador submitea el form con confirmación. El payload MUST contener `valor_final_efectivo: number ≥0` + `valor_final_datafono: number ≥0` + `observaciones_cierre: string` opcional. La validación local Zod MUST aplicar `z.object({ valor_final_efectivo: z.number().min(0), valor_final_datafono: z.number().min(0), observaciones_cierre: z.string().optional() })` (mismo shape que apertura, sin `uuid_sucursal`/`uuid_usuario` — el uuid viene del path param). El componente MUST leer el `uuid` de la sesión activa vía `useSesionActiva()` (REQ-OPS-120). El `<CerrarTurnoForm>` (presentational) MUST mostrar resumen del turno arriba del form (uuid + timestamp apertura formateado con `formatDistanceToNow` + valores iniciales via `formatCOP` — mismo helper que REQ-OPS-121) + un botón "Confirmar cierre" + un botón "Cancelar" (`variant="ghost"` → `navigate('/')`). Ante respuesta `200 OK` con `SesionRead` válido (con `timestamp_cierre` poblado por backend), el componente MUST ejecutar **atómicamente**: (1) `useAuthStore.getState().clear()` (borra accessToken/refreshToken/expiresAt vía IPC `bridge.authStore.delete` per F2.2 — logout implícito post-cierre DEC-F3.3-03); (2) `window.dispatchEvent(new Event('parkos:auth:cleared'))` (forward hook AuthGuard F3.x+); (3) `navigate('/login?closed=true', { replace: true })` (redirect a Login con query param para feedback). Ante respuesta `404 Not Found` con body `{"error": "sesion_not_found"}` (proveniente de `SessionNotFoundError` en `session_cycle.py:351-352` cuando sesión ya cerrada o no existe — REST semantics, NO 409 per DEC-F3.3-07), `sesionActivaApi.cerrarSesion` MUST rechazar con `SesionAlreadyClosedError extends ParkosHttpError` (status=404, code='sesion_not_found') y `<CerrarTurno>` MUST renderizar `<FormMessage role="alert">{t('caja.sesionYaCerrada')}</FormMessage>` ("Esta sesión ya está cerrada") + ejecutar `navigate('/login')` (redirect login, mismo efecto UX que 409 desde perspectiva operador — DEC-F3.3-07 resuelve inconsistencia plan.md:1340 vs backend real).

**Rationale**: Logout implícito post-200 cierra el ciclo de vida del operador kiosko — sin él, el operador queda logged-in sin turno activo (estado inconsistente donde backend rechaza POST `/facturacion/*` por `permisos[]` insuficiente). DEC-F3.3-03 ratifica: redirección directa a `/login?closed=true` es UX limpia para kiosko desatendido. El 404 mapping (DEC-F3.3-07) resuelve la inconsistencia plan.md:1340 ("409 sesion_ya_cerrada") vs backend real (`SessionNotFoundError` → 404 per REST semantics): UX mensaje "ya está cerrada" es idéntico desde perspectiva operador, sin cambios backend.

**Source**: `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` (NEW T3 ~60 LOC); `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx` (NEW T3 ~40 LOC presentational); `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts` (MODIFY T1 ~25 LOC — `cerrarSesion` + `SesionAlreadyClosedError`); `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.test.tsx` (NEW T3 ~40 LOC — U12 form submit OK + U13 404 mensaje + U14 useAuthStore.clear post-200); `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY T3 +5 keys: `cerrarTurno`, `valorFinalEfectivo`, `valorFinalDatafono`, `turnoCerradoExito`, `confirmarCierre`); `apps/ui-kit/src/store/authStore.ts:81` (F2.2 READ ONLY — `clear()` borra tokens vía IPC); `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py:213-217` (READ ONLY — `PUT /sesion/{uuid}/cerrar` endpoint ya shipped F1.13); `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py:188-356` (READ ONLY — `close_session_with_log` + `SessionNotFoundError:351-352`).

#### Scenario 1: CerrarTurno happy path — 200 OK + logout implícito + redirect `/login?closed=true`
- **Given** el operador con sesión activa `sesion.uuid = 'sess-uuid-123'`
- **And** form completo con `valor_final_efectivo = 75000`, `valor_final_datafono = 25000`, `observaciones_cierre = 'Cierre turno tarde'`
- **And** MSW mockea `PUT /caja-sesion/sesion/sess-uuid-123/cerrar` retornando `200 OK` con `SesionRead{ uuid: 'sess-uuid-123', timestamp_cierre: NOW(), ... }`
- **When** el operador hace click en "Confirmar cierre" (submit form)
- **Then** Zod validation MUST pasar
- **And** `parkosFetch` MUST enviar `PUT /caja-sesion/sesion/sess-uuid-123/cerrar` con body JSON
- **And** post-200, `<CerrarTurno>` MUST invocar `useAuthStore.getState().clear()` (verificable con spy en `authStore.clear`)
- **And** MUST despachar `new Event('parkos:auth:cleared')` en `window`
- **And** MUST ejecutar `navigate('/login?closed=true', { replace: true })`
- **And** la siguiente invocación de `useSesionActiva()` MUST retornar `sesion: null` (key null sin token per REQ-OPS-120 Scenario 1).

#### Scenario 2: 404 `sesion_not_found` → UX "esta sesión ya está cerrada" + redirect login
- **Given** el operador intenta cerrar una sesión que ya está cerrada (race condition: cerró desde otra pestaña)
- **And** MSW mockea `PUT /caja-sesion/sesion/sess-uuid-123/cerrar` retornando `404 Not Found` con body `{"error": "sesion_not_found"}` (proveniente de `SessionNotFoundError` per backend)
- **When** el operador submitea el form
- **Then** `sesionActivaApi.cerrarSesion` MUST rechazar con `SesionAlreadyClosedError(status=404, code='sesion_not_found')`
- **And** `<CerrarTurno>` MUST renderizar `<FormMessage role="alert">{t('caja.sesionYaCerrada')}</FormMessage>` ("Esta sesión ya está cerrada")
- **And** MUST ejecutar `navigate('/login')` (redirect login, sin `?closed=true` porque no fue cierre exitoso del operador actual).

#### Scenario 3: Validación Zod local rechaza `valor_final_efectivo < 0` antes del PUT
- **Given** el operador tipea `valor_final_efectivo = -50` en el `<Input type="number">`
- **When** el operador intenta submit
- **Then** Zod resolver MUST retornar error de validación (`min(0)` violated)
- **And** `<FormMessage>` MUST mostrar mensaje inline de error
- **And** el `parkosFetch` MUST NO invocarse (defense in depth)
- **And** MSW MUST NO recibir el PUT (test verifica que el handler `sesion-cerrar` no fue llamado).

#### Scenario 4: Botón "Cancelar" → navigate('/') sin invocar cerrarSesion
- **Given** `<CerrarTurnoForm>` muestra el botón "Cancelar" (`variant="ghost"`)
- **When** el operador hace click en "Cancelar"
- **Then** el componente MUST ejecutar `navigate('/')` (vuelve al Dashboard sin cerrar sesión)
- **And** `parkosFetch` MUST NO invocarse (PUT NO viaja)
- **And** `useAuthStore` MUST NO limpiarse (operador sigue autenticado).

---

### REQ-OPS-123 — `Dashboard` `/` redirect rule según sesión activa (DEC-F3.3-05)

**Source**: HU-F3.3 (`plan.md:1350` + `DEC-F3.3-05` Dashboard redirect + `plan.md:1333` `/` resuelve dashboard con resumen del turno) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<Dashboard>` (page container en ruta `/`) MUST consumir `useSesionActiva()` (REQ-OPS-120) y MUST aplicar la siguiente decision tree atómica en cada render: (1) **`sesion === null && !isLoading && !error` → `navigate('/caja/abrir-turno', { replace: true })`** (operador autenticado sin sesión activa → redirige a pantalla de apertura; `replace` previene back-button infinite loop — operador no vuelve al dashboard presionando back); (2) **`sesion !== null` → render `<TurnoActivoPanel sesion={sesion} onCerrarClick={() => navigate('/caja/cerrar-turno')} />`** (operador con sesión activa ve resumen + botón cerrar); (3) **`isLoading === true` → render `<Skeleton>` o `<p>...</p>` neutral** (estado de carga mientras SWR fetcha; evita flash de "sesión no iniciada" durante refetch de 50min); (4) **`error !== undefined && error?.status !== 404`** → render error state con `<Button onClick={() => refresh()}>{t('common.retry')}</Button>` (errores distintos a 404 — operador puede reintentar manualmente). El `useEffect` que ejecuta el redirect MUST tener deps `[sesion, isLoading, error]` para evitar loops infinitos. La ruta `/` MUST ser registrada en `App.tsx` como `<Route path="/" element={<Dashboard />} />` (replace la ruta placeholder F3.1 que retornaba `<Navigate to="/login" />`). El componente MUST NO consumir `useAuth()` directamente para verificar autenticación — eso es responsabilidad de un futuro `<AuthGuard>` (forward hook F3.x+). El componente MUST NO mostrar contenido mientras ejecuta el redirect (NO flash de "Sesión no iniciada" antes de navegar).

**Rationale**: El operador kiosko NO navega manualmente — llega al terminal, hace login (F3.1), y debe ser redirigido al estado correcto. UX transaccional sin flash de pantalla vacía. El `replace: true` previene back-button infinite loop (operador presiona back después del redirect → vuelve al login, no al dashboard vacío que redirige otra vez). El decision tree exhaustivo cubre los 4 estados posibles de `useSesionActiva()` — sin ambigüedad.

**Source**: `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` (NEW T4 ~30 LOC); `apps/electron-sucursal/src/features/caja/components/TurnoActivoPanel.tsx` (NEW T4 ~30 LOC — REQ-OPS-121); `apps/electron-sucursal/src/features/caja/pages/Dashboard.test.tsx` (NEW T4 ~25 LOC — U15 redirect abrir-turno sin sesión + U16 render TurnoActivoPanel con sesión + U17 error state con retry); `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY T4 +10 LOC — registra ruta `/` → `<Dashboard>` + `/caja/abrir-turno` + `/caja/cerrar-turno`); `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY T4 +1 key `turnoActivo`); `react-router-dom@6.27.0` (F2.1 baseline — `navigate` + `replace` READ ONLY).

#### Scenario 1: Operador autenticado sin sesión activa → redirect `/caja/abrir-turno` (replace)
- **Given** el operador está autenticado (`useAuthStore.accessToken !== null`) pero sin sesión activa
- **And** MSW mockea `GET /caja-sesion/sesion/me` retornando `404 Not Found` (operador sin turno)
- **When** el operador navega a `/` (o es redirigido post-login)
- **Then** `<Dashboard>` MUST ejecutar `navigate('/caja/abrir-turno', { replace: true })` en el primer render donde `sesion === null && !isLoading && !error`
- **And** `<AbrirTurno>` MUST montar (REQ-OPS-119)
- **And** el operador MUST NO ver flash de dashboard vacío — el redirect es síncrono post-resolución SWR.

#### Scenario 2: Operador con sesión activa → render `<TurnoActivoPanel>` con resumen + botón cerrar
- **Given** el operador con sesión activa `sesion = { uuid: 'sess-uuid-123', ... }`
- **And** MSW mockea `GET /caja-sesion/sesion/me` retornando `200 OK` con SesionRead
- **When** el operador navega a `/`
- **Then** `<Dashboard>` MUST renderizar `<TurnoActivoPanel sesion={sesion} onCerrarClick={...} />` per REQ-OPS-121
- **And** el operador MUST NO ser redirigido a `/caja/abrir-turno`
- **And** el botón "Cerrar turno" MUST ejecutar `navigate('/caja/cerrar-turno')` que monta `<CerrarTurno>` per REQ-OPS-122.

#### Scenario 3: SWR isLoading → render Skeleton (sin redirect)
- **Given** el operador navega a `/` con SWR fetching (estado inicial `isLoading === true`)
- **When** `<Dashboard>` renderiza por primera vez
- **Then** MUST renderizar `<Skeleton>` o `<p>{t('common.loading')}</p>` neutral
- **And** MUST NO ejecutar redirect (todavía no se sabe si hay sesión o no).

#### Scenario 4: Error distinto a 404 → error state + botón retry
- **Given** `GET /caja-sesion/sesion/me` retorna `500 Internal Server Error` (backend caído)
- **When** SWR ejecuta el fetcher
- **Then** `<Dashboard>` MUST renderizar `<Alert variant="destructive">{t('errors.networkError')}</Alert>`
- **And** MUST renderizar `<Button onClick={() => refresh()}>{t('common.retry')}</Button>`
- **And** MUST NO ejecutar redirect (error !== undefined, status !== 404).

---

### REQ-OPS-124 — `Login` `?closed=true` detection + WCAG 2.1 AA compliance en AbrirTurno + CerrarTurno + TurnoActivoPanel (DEC-F3.3-09 + DEC-F3.3-08 + RNF-022)

**Source**: HU-F3.3 (`plan.md:1334` + `DEC-F3.3-09` `?closed=true` query param + `DEC-F3.3-08` DELTA verdict + RNF-022 WCAG 2.1 AA + REQ-OPS-112 F3.1 precedent + REQ-OPS-118 F3.2 precedent) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
El componente `<Login>` (F3.1, MODIFY T3) MUST detectar `useLocation().search.includes('closed=true')` y MUST renderizar `<p role="status" aria-live="polite" data-testid="turno-cerrado-exito">{t('caja.turnoCerradoExito')}</p>` **arriba del form de login** (sin reemplazar el form, sin alterar la lógica de autenticación F3.1). El `<p>` MUST usar `role="status"` + `aria-live="polite"` (WCAG 2.1 AA — patrón idéntico a F3.2 REQ-OPS-118 countdown precedent, screen reader anuncia el cambio sin interrumpir). El i18n key `turnoCerradoExito` MUST agregarse a `caja.json` (español neutro: "Turno cerrado exitosamente"). El `<Login>` MUST NO alterar el comportamiento de submit (F3.1 REQ-OPS-106..112 intacto). F3.3 MUST extender WCAG 2.1 AA compliance al state post-cierre: el scan `axe-core` vía `@axe-core/playwright` MUST retornar 0 violaciones de WCAG 2.1 AA en `<AbrirTurno>` (estado normal + estado 409) + `<CerrarTurno>` (estado normal + estado 404) + `<TurnoActivoPanel>` (estado con/sin observaciones) + el feedback `?closed=true` en `<Login>`. Cobertura mandatory incluye: (1) `<p role="status" aria-live="polite">` con `aria-label` descriptivo si aplica; (2) `<Input>` numéricos con `<label>` asociado vía `<FormField>` shadcn; (3) `<FormMessage role="alert">` para errores (no duplicar `role=status`); (4) contraste de color ≥4.5:1 entre foreground/background (CSS tokens F2.1 baseline); (5) tab order secuencial preservado (foco pasa por inputs + submit en orden lógico); (6) NO errores de axe-core sobre `aria-live="polite"` mal usado (`<p>` con contenido textual). El e2e test `apps/electron-sucursal/e2e/caja/turno.spec.ts::A1` MUST incluir `test_axe_core_turno` que ejecuta `new AxeBuilder({page}).analyze()` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa` post-render de cada componente (4 escenarios: abrir normal, abrir 409, cerrar normal, cerrar 404).

**Rationale**: Operador kiosko cierra turno → redirect a `/login?closed=true` (REQ-OPS-122) → Login page muestra feedback "Turno cerrado exitosamente" — confirma la acción. Sin feedback, operador puede pensar que el kiosko se colgó. WCAG 2.1 AA compliance extiende F3.1 REQ-OPS-112 (LoginForm normal) + F3.2 REQ-OPS-118 (LoginForm lockout state) a F3.3 — AbrirTurno + CerrarTurno + TurnoActivoPanel + post-cierre feedback. Si axe-core reporta violaciones, el kiosko desatendido pierde la cobertura a11y que el operador en piso necesita (RNF-022).

**Source**: `apps/electron-sucursal/src/features/auth/pages/Login.tsx` (MODIFY T3 +5 LOC — detecta `?closed=true` y renderiza `<p role="status">`); `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` (MODIFY T3 +1 key `turnoCerradoExito`); `apps/electron-sucursal/src/renderer/i18n/locales/auth.json` (MODIFY T3 +1 key `closedSessionNotice` aria-live polite — alias opcional F3.3 mantiene namespace caja por consistencia con `turnoCerradoExito`); `apps/electron-sucursal/e2e/caja/turno.spec.ts` (NEW T5 ~80 LOC — E1 abrir OK + E2 409 segundo intento + E3 cerrar OK + A1 axe-core WCAG 2.1 AA 4 estados); `docs/01-requisitos/no-funcionales.md:126` (RNF-022 anchor WCAG 2.1 AA); `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (F2.1 axe-core pattern precedent — F3.3 replica); REQ-OPS-112 F3.1 + REQ-OPS-118 F3.2 (WCAG patterns precedente verbatim).

#### Scenario 1: Login detecta `?closed=true` → render `<p role="status" aria-live="polite">` arriba del form
- **Given** el operador es redirigido a `/login?closed=true` post-cierre de turno (REQ-OPS-122 Scenario 1)
- **When** `<Login>` monta
- **Then** `useLocation().search.includes('closed=true')` MUST retornar `true`
- **And** MUST renderizar `<p role="status" aria-live="polite" data-testid="turno-cerrado-exito">{t('caja.turnoCerradoExito')}</p>` **arriba del form** (verificable con `getByTestId('turno-cerrado-exito')` seguido de `getByRole('form')` — orden DOM)
- **And** el form de login MUST quedar intacto (no se reemplaza, no se altera su lógica de submit F3.1).

#### Scenario 2: axe-core scan post-render del feedback `?closed=true` — 0 violaciones
- **Given** el operador navega a `/login?closed=true` (post-cierre)
- **When** `e2e/caja/turno.spec.ts::A1` ejecuta `new AxeBuilder({page}).analyze()` con tags `wcag2a, wcag2aa, wcag21a, wcag21aa`
- **Then** el array `result.violations` MUST estar vacío (length === 0)
- **And** el `<p role="status" aria-live="polite">` MUST contener contenido textual (axe-core rechaza `aria-live` regions vacías)
- **And** el test MUST pasar verde (no skip en CI).

#### Scenario 3: axe-core scan en `<AbrirTurno>` estado normal — 0 violaciones
- **Given** el operador navega a `/caja/abrir-turno`
- **When** axe-core scan ejecuta sobre el page completo
- **Then** el array `result.violations` MUST estar vacío
- **And** los `<Input type="number" inputMode="decimal" step="0.01">` MUST tener `<label>` asociado vía shadcn `<FormField>`
- **And** el contraste de color MUST ser ≥4.5:1 (CSS tokens F2.1).

#### Scenario 4: axe-core scan en `<AbrirTurno>` con error 409 visible — 0 violaciones
- **Given** el operador submitea AbrirTurno y recibe 409 (sesión ya activa)
- **When** `<AbrirTurno>` renderiza `<FormMessage role="alert">{t('caja.sesionYaAbierta')}</FormMessage>` + botón "Ir al turno"
- **And** axe-core scan ejecuta
- **Then** el array `result.violations` MUST estar vacío
- **And** el `<FormMessage>` con `role="alert"` MUST coexistir sin violar axe-core (NO duplica `role=status` — R6 risk F3.2 verbatim).

#### Scenario 5: axe-core scan en `<CerrarTurno>` + `<TurnoActivoPanel>` — 0 violaciones
- **Given** el operador navega a `/caja/cerrar-turno` (con sesión activa) y también navega a `/` con sesión activa
- **When** axe-core scan ejecuta en ambos pages
- **Then** ambos scans MUST retornar `result.violations.length === 0`
- **And** el `<TurnoActivoPanel>` MUST tener headings semánticos (`<CardTitle>` → `<h3>`)
- **And** el `<CerrarTurnoForm>` MUST tener `<label>` en cada `<Input>` (RNF-022 compliance).

---

## 4. Cross-reference table + acceptance scenarios

### 4.1 Cross-reference table

| REQ-OPS | DEC-F3.3 anchor | plan.md line | Precedent directo |
|---|---|---|---|
| REQ-OPS-119 | DEC-F3.3-01, DEC-F3.3-02 | 1327-1352 (HU-F3.3 verbatim) + 1338 (Zod schema) | F3.1 REQ-OPS-106..108 (RHF+Zod + 409 error mapping pattern) + F1.3 (partial unique index 0023 BD-level) |
| REQ-OPS-120 | DEC-F3.3-04 + DEC-SUC-03 | 1336 + 418 (50min verbatim) | F3.1 REQ-OPS-110 (`useAuth` SWR pattern) + F3.2 REQ-OPS-117 (`refreshInterval: 50min`) + F2.2 baseline `authStore` |
| REQ-OPS-121 | DEC-F3.3-05 | 1336 + 1350 (Dashboard redirect) | F3.1 REQ-OPS-106 (container/presentational split) + F1.13 (SesionRead schema) + shadcn Card primitives F2.1 |
| REQ-OPS-122 | DEC-F3.3-03, DEC-F3.3-06, DEC-F3.3-07 | 1334 (`PUT /caja-sesion/sesion/{uuid}/cerrar`) + 1340 (`409 sesion_ya_cerrada`) + 1344 (260 LOC) | F1.13 (`SessionNotFoundError` 404 backend) + F2.2 (`useAuthStore.clear()`) + F3.2 (Mutex preserved) |
| REQ-OPS-123 | DEC-F3.3-05 | 1350 (redirect según exista o no sesión activa) + 1333 (`/` resuelve dashboard con resumen del turno) | F3.1 REQ-OPS-111 (redirect post-login transaccional pattern) + F3.2 (SWR refresh consume) |
| REQ-OPS-124 | DEC-F3.3-09 + DEC-F3.3-08 + RNF-022 | 1334 (redirect a login o "turno cerrado") + 1342 (axe-core WCAG) | F3.1 REQ-OPS-112 (axe-core LoginForm precedent) + F3.2 REQ-OPS-118 (axe-core lockout state extension) + RNF-022 (no-funcionales.md:126) |

**Nota**: F3.3 NO crea un nuevo REQ-OPS-XR (cross-cutting requirement). Las 6 new REQ-OPS-119..124 son SPECIFIC al flujo de turno. REQ-OPS-XR6 de F1.13 (5-layer defense in depth) sigue siendo el canonical cross-cutting contract; F3.3 contribuye a las capas contract (Zod + 409/404 typed errors) + a11y (WCAG axe-core) sin formalizar un XR7 (precedent F1.15 `DEC-XR7 NOT-CREATED` en `operations/spec.md:4386` + F3.1 NO crea XR en spec + F3.2 NO crea XR en spec).

### 4.2 Acceptance scenarios for sdd-verify

| # | Criterion | Test source | Type |
|---|---|---|---|
| AC-1 | `useSesionActiva()` SWR con key null sin token + refreshInterval 50min + 404 null + 401 clear (REQ-OPS-120) | `useSesionActiva.test.ts` (T1, ~40 LOC, 4 tests: U1 SWR key null sin token, U2 SWR fetch OK, U3 SWR 404 → sesion null, U4 SWR 401 dispara `parkos:auth:cleared`) | Unit (vitest + MSW) |
| AC-2 | `AbrirTurno` form submit OK + 409 `sesion_already_active` mensaje + validaciones Zod (REQ-OPS-119) | `AbrirTurno.test.tsx` (T2, ~50 LOC, 3 tests: U9 form submit OK, U10 409 mensaje, U11 validaciones Zod) | Unit (vitest + @testing-library/react + MSW) |
| AC-3 | `CerrarTurno` form submit OK + 404 `sesion_not_found` mensaje + `useAuthStore.clear()` post-200 (REQ-OPS-122) | `CerrarTurno.test.tsx` (T3, ~40 LOC, 3 tests: U12 form submit OK, U13 404 mensaje, U14 useAuthStore.clear post-200) | Unit (vitest + @testing-library/react + MSW) |
| AC-4 | `sesionActivaApi` typed wrappers (`getSesionActiva` 404→null + `abrirSesion` 409 mapping + `cerrarSesion` 404 mapping) (REQ-OPS-119, REQ-OPS-120, REQ-OPS-122) | `sesionActivaApi.test.ts` (T1, ~40 LOC, 4 tests: U5 getSesionActiva 200, U6 getSesionActiva 404, U7 abrirSesion 409 mapping, U8 cerrarSesion OK) | Unit (vitest + MSW) |
| AC-5 | `TurnoActivoPanel` renderiza uuid + timestamp + valores iniciales + botón cerrar (REQ-OPS-121) | `TurnoActivoPanel.test.tsx` (T4, ~25 LOC, snapshot test + render tests) | Unit (vitest + @testing-library/react) |
| AC-6 | `Dashboard` `/` redirect según sesión activa (sin sesión → `/caja/abrir-turno` replace; con sesión → `<TurnoActivoPanel>`) (REQ-OPS-123) | `Dashboard.test.tsx` (T4, ~25 LOC, 3 tests: U15 redirect abrir-turno sin sesión, U16 render TurnoActivoPanel con sesión, U17 error state con retry) | Unit (vitest + @testing-library/react + MSW) |
| AC-7 | `Login` page detecta `?closed=true` → render `<p role="status" aria-live="polite">` arriba del form (REQ-OPS-124) | `Login.test.tsx` (T3 MODIFY, ~15 LOC, 1 test: ?closed=true detection + render orden DOM) | Unit (vitest + @testing-library/react) |
| AC-8 | 4 e2e scenarios verde (abrir OK + 409 segundo intento + cerrar OK + axe-core) (REQ-OPS-119, REQ-OPS-120, REQ-OPS-122, REQ-OPS-123, REQ-OPS-124) | `e2e/caja/turno.spec.ts` (T5, ~80 LOC — E1 redirect abrir + submit OK, E2 409 segundo intento, E3 cerrar OK + redirect login, A1 axe-core WCAG 2.1 AA 4 estados) | E2E (playwright _electron + axe-core) |
| AC-9 | axe-core 0 violaciones WCAG 2.1 AA en `<AbrirTurno>` (estado normal + estado 409) + `<CerrarTurno>` (estado normal + estado 404) + `<TurnoActivoPanel>` + feedback `?closed=true` (REQ-OPS-124) | `e2e/caja/turno.spec.ts::A1` (T5, embedded axe-core scan — sandbox SKIPPED-env per F.6 precedent; axe-core source-level via `@axe-core/react` o vitest-axe unit test alternative) | E2E (playwright _electron + axe-core) + Unit (vitest + vitest-axe) |
| AC-10 | (transversal) i18n `caja.json` agrega 12 keys turno (`abrirTurno`, `cerrarTurno`, `valorInicialEfectivo`, `valorInicialDatafono`, `valorFinalEfectivo`, `valorFinalDatafono`, `observaciones`, `sesionYaAbierta`, `sesionYaCerrada`, `turnoCerradoExito`, `confirmarCierre`, `irAlTurno`, `turnoActivo`) — snapshot test verde | snapshot test del JSON (T2+T3+T4) | Unit (vitest snapshot) |
| AC-11 | (transversal) i18n `auth.json` agrega 1 key `closedSessionNotice` aria-live polite — snapshot test verde | snapshot test del JSON (T3) | Unit (vitest snapshot) |

**Sandbox F.6 caveat**: AC-8 + AC-9 pueden SKIP en sandbox F.6 (npm 11.16.0 refuses `workspace:*` resolution — F2.1 + F2.2 + F2.3 + F3.1 + F3.2 archive precedent). Unit tests AC-1..AC-7 + AC-10..AC-11 + AC-9 axe-core source-level SÍ corren. Documentado como deviation D-env en `verify-report.md` futuro, NO project defect.

---

## 5. Out of scope (deferred a Fase 3+)

F3.3 NO incluye (explícitamente deferido):

- **Backend cambios** — `POST /caja-sesion/sesiones` (F1.3) + `PUT /sesion/{uuid}/cerrar` (F1.13) + `GET /sesion/me` (F1.3) + permission `abrir_cerrar_caja` (GAP-BE-05 site #2) + partial unique index 0023 + trigger `ls_session_guard` ya shipped. F3.3 NO modifica backend.
- **Arqueo completo (Fase 10)** — `CerrarTurno.tsx` es placeholder. F10.x HU entrega `POST /caja/arqueo` con `tipo_arqueo='cierre_turno'` + tolerancia + justificación + alerta `descuadre_critico` (DEC-F3.3-06).
- **Sync de sesion cerrada** — `prod.sesion` [L-S] ya en `sync_catalog` branch→cloud. F3.3 NO toca sync catalog.
- **Reverso de pagos** — `factura_pagos` [A] con `tipo_movimiento = 'pago | reverso'` — fuera scope F3.3 (forward F5.x).
- **AuthGuard component** — F3.3 NO crea `<AuthGuard>` que envuelve `<Routes>` excepto `/login`. Forward hook F3.x+ intercepta `parkos:auth:cleared` → `navigate('/login?next=...')`.
- **Logout button UI explícito** — F3.3 hace logout implícito post-cierre (DEC-F3.3-03). Botón UI dedicado es forward hook.
- **Multi-sucursal selector** — JWT ya pinea sucursal (DEC-F3.1-04 single-branch kiosko). F3.3 lee `useAuth().user.sucursal.uuid` directamente.
- **Edición post-apertura de valores iniciales** — `SesionUpdate` Pydantic schema permite late corrections (caja_sesion.py:218-238), pero F3.3 NO expone UI — read-only en CerrarTurno + TurnoActivoPanel.
- **`useCountdown` para "tiempo restante de turno"** — F3.3 muestra `timestamp_apertura` formateado (`formatDistanceToNow` con date-fns). NO countdown regresivo.
- **Toast notifications post-cierre** — `?closed=true` + `<p role="status">` es suficiente UX para F3.3. Forward F11.x usa shadcn Toast component.
- **Permisos granulares por acción** — backend ya emite 403 si `permisos[]` no incluye `abrir_cerrar_caja`. F3.3 NO agrega client-side permission gating (Defense in depth XR6 — backend source of truth).
- **Idempotency-Key manual en apertura** — `parkosFetch` ya genera SHA-256 de `method|path|body` para POST `/caja-sesion/*` (skip `/auth/login` only). F3.3 NO requiere override.
- **Suscripciones + ingresos recurrentes** — CU-06 fuera Fase 3 (F9.x).
- **Reportes CU-09** — F12.x consume `useSesionActiva` post-F3.3.
- **Extensión de `PRE_FLIGHT_PATHS`** — F3.3 NO modifica `parkosFetch.ts`. `/caja-sesion/*` no es critical-path per DEC-F3.3-10.
- **A11y biblioteca externa nueva** — axe-core via `@axe-core/playwright` F2.1 baseline. NO nueva dep.
- **Fechas relativas con i18n plurals** — `formatDistanceToNow` con `locale: es` suficiente. NO requiere `i18next-plural` plugin.
- **Configuración `REFRESH_INTERVAL_MS` via env** — hardcoded 50min per DEC-SUC-03. Env var `PARKOS_REFRESH_INTERVAL_MS` es forward hook F3.x.
- **Per-sucursal override de tasa de refresco** — kiosko single-branch kiosko, rate global es suficiente.
- **Edición tardía de `valor_inicial_*` post-apertura** — `SesionUpdate` schema permite (forward hook), pero F3.3 NO expone UI.

---

## 6. Dependencies + forward hooks

### 6.1 Shipped prerequisites (F1.3 + F1.13 + F2.1 + F2.2 + F2.3 + F3.1 + F3.2)

- **HU-F1.3** ✅ closed Fase 1: `POST /caja-sesion/sesiones` + `GET /caja-sesion/sesion/me` + partial unique index `prod.uq_prod_sesion_one_active_per_user` (migration 0023) + 409 mapping `SesionAlreadyActive` → `sesion_already_active`.
- **HU-F1.13** ✅ closed Fase 1: `PUT /caja-sesion/sesion/{uuid}/cerrar` + `close_session_with_log` + `ls_session_guard` trigger + GAP-BE-05 permission fix (`abrir_cerrar_caja` para sesion mount, site #2).
- **HU-F2.1** ✅ closed Fase 2: Electron 30 skeleton + shadcn Form/Input/Button/Card + i18n 7 namespaces + axe-core + playwright e2e.
- **HU-F2.2** ✅ closed Fase 2: `parkosFetch` (retry + refresh-once 401 via Mutex + Idempotency-Key) + bridge IPC + `authStore` Zustand + `useAuth` SWR.
- **HU-F2.3** ✅ closed Fase 2: kiosko mode + electron-updater + StatusBar + single-instance lock.
- **HU-F3.1** ✅ closed 2026-09-15: Login page + LoginForm + loginApi + loginSchema + ruta `/login` + 7 REQ-OPS-106..112 + `useAuth().user.sucursal.uuid` hidratado.
- **HU-F3.2** ✅ closed 2026-09-15: `useCountdown` + LoginForm countdown + `REFRESH_INTERVAL_MS = 50min` + `PRE_FLIGHT_PATHS` regex + 6 REQ-OPS-113..118.

### 6.2 Forward hooks (Fase 3+ consumer map)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.x+** (AuthGuard component) | `parkos:auth:cleared` window event emitido por `useSesionActiva` 401 path + `useAuthStore.clear()` post-cierre | AuthGuard envuelve `<Routes>` excepto `/login` → `navigate('/login?next=...')` |
| **HU-F3.x+** (Logout button UI) | `useAuthStore.clear()` ya implementado F2.2 + `parkos:auth:cleared` event | Botón UI dedicado dispatch `clear()` + `navigate('/login')` |
| **HU-F4.x** (catálogos + ocupación en vivo) | `useSesionActiva()` para scoped queries per `sesion.uuid_sucursal` + `sesion.uuid_usuario` | F4.x consume via SWR data — refresh 50min aplica transparentemente |
| **HU-F4.x** | `parkosFetch` pre-flight gate (NO extension F3.3 per DEC-F3.3-10) | F4.x hereda automáticamente T3 F3.2 cubre `/facturacion/*` |
| **HU-F5.x** (facturación) | `useSesionActiva()` para requerir sesión activa antes de POST `/facturacion/*` | F5.x consume via SWR data |
| **HU-F5.x** | pre-flight gate automático (`/facturacion/*` ya cubierto F3.2) + `useAuth.refreshInterval: 50min` | Cero cambios F5.x |
| **HU-F6.x** (ingreso vehicular CU-01) | `useSesionActiva()` + permisos F3.3 prerequisite | F6.x consume |
| **HU-F7.x** (salida + cálculo tarifa CU-02/03) | depende F6.x → consume `useSesionActiva()` transitivo | F7.x consume |
| **HU-F8.x** (cobro + FE CU-04/05) | depende F7.x → consume transitivo | F8.x consume |
| **HU-F9.x** (suscripciones CU-06) | depende F8.x → consume transitivo | F9.x consume |
| **HU-F10.x** (arqueos + cierre CU-10) | F3.3 deja `CerrarTurno` placeholder; F10.x completa con `POST /caja/arqueo` (F1.13) + tolerancia + justificación + alerta `descuadre_critico` | F10.x extiende `CerrarTurnoForm` con form completo arqueo |
| **HU-F11.x** (sync UI + alertas CU-07/14) | `useSesionActiva()` para StatusBar turno activo indicator | F11.x consume via SWR data |
| **HU-F11.x** | `useAuth().user.email` en topbar + shadcn toast component para `turnoCerradoExito` (F3.3 placeholder `<p role="status">`) | F11.x refactoriza Login feedback a toast |
| **HU-F12.x** (reportería local CU-09) | depende F3.3 turno cerrado | F12.x consume |

---

## 7. DoD checklist

- [ ] 6 REQ-OPS-119..124 materializadas en `openspec/changes/hu-f3-3-abrir-cerrar-turno/specs/operations/spec.md` (este archivo)
- [ ] Given/When/Then/And format RFC 2119 per F3.1 + F3.2 precedent verbatim
- [ ] Anchor links explícitos a `DEC-F3.3-NN` ratificados en `proposal.md §4` + `exploration.md §7`
- [ ] Cross-reference table completa (§4.1) — 6 rows con precedent column
- [ ] Acceptance criteria verificables para `sdd-verify` (§4.2) — 11 criterios
- [ ] Forward hooks documentados para F3.x+, F4.x, F5.x, F6.x, F7.x, F8.x, F9.x, F10.x, F11.x, F12.x (§6.2) — 13 hooks
- [ ] Out of scope verbatim de `proposal.md §3.2 + §5.2` (§5)
- [ ] NO-OP stub NO aplicado — DELTA stub con 6 new REQ-OPS confirmado (per `DEC-F3.3-08` + `DEC-F3.3-11` + `DEC-F3.3-12`)
- [ ] Numeración monotónica verificada (REQ-OPS-118 vigente post-F3.2; F3.3 ocupa REQ-OPS-119..124)
- [ ] Spanish neutro profesional per F3.1 + F3.2 precedent + global contract
- [ ] Author: `Parkos Dev <dev@parkos.local>` (F2.1 + F3.1 + F3.2 verbatim precedent)
- [ ] No "Co-authored-by" attribution per `CLAUDE.md` global rules
- [ ] RFC 2119 MUST/SHOULD/MAY keywords consistentes en las 6 REQ-OPS

---

## CHANGELOG

- **(2026-09-15)** F3.3 spec delta complete — 6 REQ-OPS-119..124 materializadas en Given/When/Then/And format RFC 2119. DELTA stub (NOT NO-OP) per critical re-evaluación en `proposal.md §4.8 + §4.11 + §4.12` (DEC-F3.3-08 + DEC-F3.3-11 + DEC-F3.3-12). F3.3 ES user-facing behavior observable: AbrirTurno form con campos decimales + RHF+Zod + 409 `sesion_already_active` UX claro (REQ-OPS-119) + `useSesionActiva` SWR con refreshInterval 50min + 401 clear (REQ-OPS-120) + `TurnoActivoPanel` con resumen legible del turno (REQ-OPS-121) + `CerrarTurno` con logout implícito post-200 + 404 `sesion_not_found` mapeado a UX "ya está cerrada" (REQ-OPS-122) + `Dashboard` `/` redirect según sesión activa con `replace: true` (REQ-OPS-123) + `Login` `?closed=true` detection + WCAG 2.1 AA axe-core 0 violaciones en AbrirTurno + CerrarTurno + TurnoActivoPanel + post-cierre feedback (REQ-OPS-124). Precedente directo: F3.2 archivado 2026-09-15 con 6 new REQ-OPS-113..118 + F3.1 archivado 2026-09-15 con 7 new REQ-OPS-106..112 + F1.15 archivado 2026-09-15 con 4 new REQ-OPS-102..105. Numeración monotónica: REQ-OPS-118 vigente post-F3.2; F3.3 ocupa REQ-OPS-119..124 (continuación, 0 gaps). Ready for `sdd-design` (parallel) + `sdd-tasks`.

---

**End of delta spec — HU-F3.3.**
