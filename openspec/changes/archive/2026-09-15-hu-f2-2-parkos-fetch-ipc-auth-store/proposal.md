# Propuesta — HU-F2.2 Cliente HTTP parkosFetch + IPC bridge + authStore

> **Change**: `hu-f2-2-parkos-fetch-ipc-auth-store` · **Folder**: `openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F2.2 (Fase 2 — capa de infraestructura HTTP/IPC/authStore; transversal, primera HU con HTTP behavior contract)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `5bdf857`, F2.1 archivado 2026-09-15) · **PR target**: `origin/dev`
> **Inputs**: `plan.md` lines 1196-1240 (HU-F2.2 verbatim + 7 tareas atómicas T1..T7 + 14 escenarios e2e + 8 escenarios bridge); `plan.md` lines 1159-1194 (HU-F2.1 archivado, precedente de scaffold); `plan.md` lines 1242-1267 (HU-F2.3 updater+kiosko, forward consumer); `openspec/_meta/roadmap.md` lines 38-273 (IT-1..IT-10 web_sucursal consumer map); `openspec/specs/operations/spec.md` (XR6 at line 3951 + REQ-OPS-102..105 from F1.15 — pattern para REQ-OPS-106..112 si la propuesta decide agregar); `apps/web_admin/src/lib/fetch.ts:1-66` (parkosFetch existente, fuente de reutilización); `apps/electron-sucursal/electron/preload.ts:1-11` (contextBridge vacío, F2.2 lo expande); `apps/electron-sucursal/electron/bridge.d.ts` (no existe — F2.2 lo crea); `apps/ui-kit/{package.json,src/Button.tsx,src/cn.ts,src/tokens.ts}` (workspace package shipped F2.1, target de nueva ubicación de parkosFetch); `apps/package.json:5-8` (workspaces = ["ui-kit","web_admin","electron-sucursal"], F2.1 ya añadió electron-sucursal); `backend/.../api/v1/auth.py:148-583` (POST /auth/{login,refresh,logout,me} consumer anchors); `backend/.../schemas/auth.py:243-321` (LoginRequest, RefreshRequest, TokenPair, UserItem, SucursalItem, AuthMeResponse); `modelo_datos_er.mmd:558-573` (prod.login [L-S] — F2.2 NO touch); `docs/01-requisitos/no-funcionales.md:126` (RNF-022 WCAG 2.1 AA); `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/{exploration,proposal}.md` (17-section exploration template + 16-section proposal template — espejo verbatim); `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/{exploration,proposal}.md` (precedente REQ-OPS-102..105 + DEC-XR7 NOT-CREATED).

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F2.2 |
| **Fase** | 2 (Andamiaje Electron + Capa de Infraestructura HTTP/IPC/authStore) |
| **Change name** | `hu-f2-2-parkos-fetch-ipc-auth-store` |
| **Folder** | `openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/` |
| **State** | proposed (ready for design + spec) |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | F2.1 archivado 2026-09-15 (scaffold apps/electron-sucursal) |
| **Próximo phase** | sdd-spec + sdd-design (paralelo) |
| **Language** | español neutro profesional |
| **Conventional commits** | feat(ui-kit) / feat(electron) / test(electron) — sin Co-authored-by |

---

## 1. Resumen ejecutivo

F2.1 shippeó el esqueleto de `apps/electron-sucursal` (Electron 30 + Vite 5 + React 18 + TS 5 strict + 14 componentes shadcn/ui + i18n 7 namespaces + ui-kit workspace + Playwright _electron + axe-core) — pero sin cliente HTTP, sin superficie IPC tipada, ni store de autenticación. F2.2 entrega las **tres primitives de infraestructura transversal** sobre las cuales se construirá toda la Fase 3 y los IT-3..IT-10 sin reinventar reglas cross-cutting: (a) `parkosFetch` extendido en `apps/ui-kit/src/fetch/parkosFetch.ts` con retry 5xx + refresh-once 401 + Idempotency-Key SHA-256 + validación Zod opcional + timeout AbortController; (b) Bridge IPC tipado en `apps/electron-sucursal/electron/bridge.d.ts` con 8 métodos en 6 grupos (`imprimir`, `usb`, `kiosk`, `app`, `apiStatus`, `authStore`) materializado por `preload.ts` con whitelist explícita; (c) `authStore` Zustand con `persist` contra `electron-store` (path `app.getPath('userData')/auth.json`) + hook `useAuth()` SWR que hidrata desde `/auth/me` cada 5 minutos.

F2.2 desbloquea **11 HUs downstream** (F3.1 login UI, F3.2 lockout visible con countdown, F3.3 turno abrir/cerrar, IT-3 Ingreso vehículo, IT-4 Salida, IT-5 Facturación, IT-6 Caja, IT-7 Anulación, IT-8 Alertas, IT-9 Reimpresión térmica, IT-10 Clientes list) — todas consumirán `parkosFetch` + `useAuth()` + `bridge.*` sin negociar el contrato HTTP. Mal diseño en F2.2 se propaga a 11 HUs downstream; bien diseñado, Fase 3 es trabajo de UI puro sobre primitives estables.

Métricas objetivo: **~600 LOC production + ~370 LOC tests = ~970 LOC total**, distribuidos en **3 clusters atómicos** (C1: parkosFetch + bridge.d.ts + preload ~230 LOC; C2: authStore + useAuth ~130 LOC; C3: 22 e2e + axe-core + bridge contract ~190 LOC), ejecutados en **7 commits atómicos** (T1..T7) ordenados C1 → C2 → C3, validados por **8 acceptance gates** (G1..G8) con cobertura >90% en `parkosFetch.ts` y >80% en `authStore.ts` + `useAuth.ts`. Pre-flight 10/10 PASS verificado en `exploration.md` §12.

---

## 2. Contexto y motivación

**Title**: "Cliente HTTP único parkosFetch (retry 5xx + refresh-once 401 + Idempotency-Key + Zod validation) + Bridge IPC tipado (imprimir, usb, kiosk, app, apiStatus, authStore) + authStore Zustand con persist electron-store + useAuth() hook SWR"

**Goal**: F2.1 shippeó la skeleton (Electron 30 + Vite 5 + React 18 + TS 5 strict + shadcn 14 + i18n 7 namespaces + ui-kit workspace + Playwright _electron + axe-core) — pero sin HTTP client ni IPC surface ni store de auth. F2.2 entrega las tres primitives de infraestructura que toda feature subsecuente (F3.1 login, F3.2 lockout, F3.3 turno, IT-3..IT-10) consumirá sin reinventar reglas cross-cutting:

1. **parkosFetch extendido** — un único `fetch` wrapper para web_admin + electron-sucursal que centraliza: (a) `Authorization: Bearer <token>` injection desde authStore (NO localStorage crudo); (b) `X-Sucursal-Context` header (idéntico a F2.1 behaviour); (c) `Idempotency-Key: <sha256>` header en POST/PUT/DELETE mutacionales; (d) retry con backoff 300/600/1200ms limitado a respuestas 5xx + 408; (e) refresh-once en 401 con Mutex singleton; (f) timeout via AbortController; (g) Zod validation opcional en boundary via `parkosFetch<T>(url, schema)`.
2. **Bridge IPC tipado** — `apps/electron-sucursal/electron/bridge.d.ts` define el contrato typed entre main process y renderer; `preload.ts` lo materializa vía `contextBridge.exposeInMainWorld('bridge', {imprimir, usb.list, kiosk.toggle, app.quit, apiStatus.get, authStore.{get,set,delete}})`. Renderer importa tipos con triple-slash reference.
3. **authStore Zustand + persist electron-store** — Zustand store con `persist` middleware contra filesystem (`app.getPath('userData')/auth.json`); expone `useAuthStore()` selector + `useAuth()` SWR hook que hidrata desde `/auth/me`. `useAuth()` sincroniza store ↔ cache SWR ↔ backend.

**Por qué importa** (rationale): F2.2 es la última HU de Fase 2 con superficie HTTP. Cada HU de Fase 3 (login, lockout, turno, vehículo, factura, caja, anulación, alerta, reclamo, reimpresión, cliente) **consumirá** parkosFetch + bridge + authStore sin negociación. Mal diseño aquí se propaga a 11 HUs downstream (IT-3..IT-10 + F3.1/F3.2/F3.3). Bien diseñado, Fase 3 es trabajo de UI; mal diseñado, Fase 3 incluye reescritura de infra.

**Hard constraints** (mirrored from `plan.md:1198-1240`):
- `baseURL=http://127.0.0.1:8000/api/v1` (default; configurable por `PARKOS_API_BASE`).
- POST/PUT/DELETE/PATCH mutacionales llevan `Idempotency-Key` calculado como SHA-256(método+ruta+cuerpo) — **NO** uuid v4 (específico de `plan.md:1203`).
- 5xx + `NetworkError` reintenta hasta 3 veces con backoff 300/600/1200ms; 4xx NO retry (excepto 408).
- 401 → refresh único (`POST /auth/refresh`); un segundo 401 consecutivo limpia `authStore` y emite `authStore.cleared` event que el router intercepta para redirect a `/login?next=<path>`.
- `window.bridge` expone métodos typed en `electron/bridge.d.ts` y filtrados por whitelist en `preload.ts`.
- Cobertura de tests >90% en `parkosFetch.ts`; 14 escenarios MSW + 8 escenarios bridge contract.
- TDD estricto: cada test escrito ANTES de la implementación; tests rojos primero.
- Defense in depth: 5 capas (XR6 pattern de `operations/spec.md:3951`) — auth (HTTP) + a11y (axe-core) + engineering (TS strict + ESLint) + contract (vitest bridge) + retry-budget (timeout + refresh-once).

**Scope**: ~600 LOC production + ~370 LOC tests = ~970 LOC total. Plan 450 LOC matches: 450 ≈ 600 production logic - 150 LOC para shadcn-generated/reuse que no cuenta como authored. Breakdown por cluster C1..C3 detallado en §9.

---

## 3. Scope y fuera de scope

### 3.1 In Scope

- `apps/ui-kit/src/fetch/parkosFetch.ts` — wrapper fetch con retry/refresh/idempotency/Zod/timeout. ~120 LOC production + ~120 LOC tests.
- `apps/ui-kit/src/fetch/parkosFetch.test.ts` — 14 escenarios MSW con `vi.useFakeTimers()`.
- `apps/ui-kit/src/fetch/index.ts` — barrel export (~5 LOC).
- `apps/web_admin/src/lib/fetch.ts` — MODIFY a re-exporter desde `@parkos/ui-kit/fetch` (sin breaking change para `sucursal-context.ts`).
- `apps/electron-sucursal/electron/bridge.d.ts` — `BridgeSurface` interface con 8 métodos typed (~60 LOC).
- `apps/electron-sucursal/electron/preload.ts` — MODIFY 11 → ~50 LOC con whitelist explícita (no `...spread`).
- `apps/electron-sucursal/src/renderer/global.d.ts` — `/// <reference types="../../electron/bridge.d.ts" />`.
- `apps/ui-kit/src/store/authStore.ts` — Zustand store con persist electron-store (~80 LOC + 60 LOC tests).
- `apps/ui-kit/src/hooks/useAuth.ts` — SWR hook con refresh 5min + auto-clear en 401 (~50 LOC + 40 LOC tests).
- `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` — 14 escenarios e2e (~60 LOC).
- `apps/electron-sucursal/e2e/auth/bridge.spec.ts` — 8 escenarios e2e (~50 LOC).
- `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` — axe-core RNF-022 gate (~30 LOC).
- `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` — validación shape bridge (~50 LOC).
- `apps/ui-kit/package.json` — agregar `zustand`, `swr`, `zod` (dev), `msw`, `@testing-library/react`.
- `apps/electron-sucursal/tsconfig.main.json` — agregar `.d.ts` a `include`.
- Documentación: `apps/ui-kit/README.md`, `apps/electron-sucursal/README.md`, `docs/03-desarrollo/estandares.md`.

### 3.2 Out of Scope

- **Backend `/health` endpoint** — necesario para `bridge.apiStatus.get()`. F2.3 lo crea.
- **Generación automática de Zod schemas desde Pydantic** — vía `datamodel-code-generator`. Deferred a Fase 3.
- **Refresh-token rotation detection** — PR1b no rota; F2.2 trata refresh token como long-lived.
- **Multi-tab login UI** — kiosko single-tab por F2.3 lock.
- **2FA / WebAuthn** — futuro.
- **Login UI** — F3.1 (form + POST /auth/login + redirect).
- **Lockout + countdown UI** — F3.2 (429 Retry-After countdown visible).
- **Turno abrir/cerrar** — F3.3 (turno lifecycle + logout cleanup).
- **Auto-update** — F2.3 (electron-updater + signature).
- **Single-instance lock** — F2.3 (`app.requestSingleInstanceLock()`).
- **Kiosko mode PIN bcrypt** — F2.3 (factor ≥12, constant-time compare).
- **Logging (electron-log rotation)** — F2.3 (10MB×5 JSON).
- **Ingreso de vehículo / Salida / Facturación / Caja / Anulación / Alertas / Reclamo / Reimpresión / Clientes list** — IT-3..IT-10.
- **Handlers reales del main process** para `imprimir`/`usb.list`/`kiosk.toggle` — F2.3 los conecta vía `ipcMain.handle('print:ticket', ...)`.
- **Backend migrations / nuevas tablas / nuevos permisos** — F2.2 es consumer-only, no toca `prod.*`.

---

## 4. Decisiones arquitectónicas (DEC-FETCH-NN)

F2.2 introduce 8 decisiones arquitectónicas (DEC-FETCH-01..08). El detalle verbatim vive en `exploration.md` §7. Esta sección referencia y resume.

| # | Decisión | Rationale | Referencia |
|---|---|---|---|
| **DEC-FETCH-01** | Extraer parkosFetch a `@parkos/ui-kit/fetch` (DRY). `web_admin/src/lib/fetch.ts` se convierte en re-exporter. | web_admin y electron-sucursal comparten el mismo backend API. Sin extracción, dos copias divergen. F2.1 ya shippeó `@parkos/ui-kit` como workspace package (DEC-ELEC-08); F2.2 continúa la tendencia DRY. | exploration §7.1 |
| **DEC-FETCH-02** | Retry 5xx + 408 + NetworkError con backoff 300/600/1200ms (3 intentos). NO retry sobre 4xx excepto 408. | 5xx es transitorio (DB blip, restart del backend). 408 es timeout del server. 4xx es bug del cliente — retry no soluciona. `plan.md:1204` verbatim. | exploration §7.2 |
| **DEC-FETCH-03** | 401 refresh-once con Mutex singleton (`refreshPromise`). Al recibir 401, intenta `POST /auth/refresh` UNA vez; si refresh 200, reintenta la request original con el nuevo access token; si refresh 401, propaga el 401 + emite `authStore.clear()` + evento para redirect a `/login?next=<path>`. | Previene stampede de refreshes concurrentes (R1 HIGH). Singleton garantiza que 2+ requests con 401 disparan UN solo refresh; los demás esperan el resultado. | exploration §7.3 |
| **DEC-FETCH-04** | `Idempotency-Key: <sha256>` en POST/PUT/DELETE/PATCH mutacionales. SHA-256(method.toUpperCase() + "\|" + url + "\|" + JSON.stringify(body ?? null)). EXCEPCIÓN: `POST /auth/login` NO lleva Idempotency-Key (es idempotente por sí mismo — bcrypt determinístico + UNIQUE constraint en `prod.login`). | `plan.md:1203` verbatim. Determinismo > randomness: dos requests idénticos producen la MISMA key → backend puede dedupe retries sin doble-ejecutar. UUID v4 fue rechazado por no ser determinístico. | exploration §7.4 |
| **DEC-FETCH-05** | Zod validation en boundary via `parkosFetch<T>(url, init, schema?)`. Si se provee schema, valida la respuesta; si falla, lanza `ZodError`. | Defense in depth (XR6 layer 4 — contract). Auto-gen desde Pydantic DEFERRED a Fase 3 (forward hook). | exploration §7.5 |
| **DEC-FETCH-06** | `useAuthStore` (Zustand) usa `persist` middleware con `createJSONStorage(() => electronStoreAdapter)`. `electronStoreAdapter` envuelve `window.bridge.authStore.{get,set,delete}` que IPC-invoca `electron-store` en main process. Path: `app.getPath('userData')/auth.json`. `partialize` persiste solo `{accessToken, refreshToken, expiresAt}`. | electron-store es más robusto para kiosko que sobrevive: (a) DevTools reset; (b) OS-level storage clear; (c) profile corruption. F2.1 ya agregó electron-store como dep. localStorage es frágil en kiosko Electron (R-FETCH-4 FAIL). | exploration §7.6 |
| **DEC-FETCH-07** | `useAuth()` hook combina Zustand store (source-of-truth para tokens) con SWR cache (datos derivados de `/auth/me`). `refreshInterval: 5 * 60 * 1000` (5 min, `plan.md:1208` verbatim). `revalidateOnFocus:true`. `shouldRetryOnError:(err) => err?.status !== 401`. `onError` con `status===401` dispara `useAuthStore.getState().clear()`. | Zustand = tokens (small, sync, frequently updated). SWR = profile data (large, async, infrequently fetched). Separación de concerns. | exploration §7.7 |
| **DEC-FETCH-08** | Bridge IPC typed surface (8 métodos en 6 grupos) via `apps/electron-sucursal/electron/bridge.d.ts`. `preload.ts` materializa con `contextBridge.exposeInMainWorld('bridge', {...})` con whitelist explícita (NO spread). Renderer importa tipos via triple-slash reference en `src/renderer/global.d.ts`. Surface: `imprimir(payload)`, `usb.list()`, `kiosk.toggle(on)`, `app.quit()`, `apiStatus.get()`, `authStore.{get,set,delete}(key[,value])`. | Tipado end-to-end previene drift entre main y renderer. Si main cambia sin actualizar `bridge.d.ts`, `tsc --noEmit` falla en CI (G5 §10). Whitelist explícita previene leak de `ipcRenderer` raw. | exploration §7.7 |

**Convención de identificadores**: DEC-FETCH-NN sigue el patrón DEC-ELEC-NN de F2.1. La propuesta F2.2 NO crea nuevos REQ-OPS-NNN (DEC-ELEC-10 precedent de F2.1, ver §6).

---

## 5. Diseño de alto nivel

### 5.1 Capas

**Capa HTTP (apps/ui-kit/src/fetch/parkosFetch.ts)** — único wrapper `fetch` compartido por web_admin y electron-sucursal. Inyecta `Authorization: Bearer <token>` desde authStore (NO desde localStorage crudo), añade `X-Sucursal-Context` desde `getSucursalHeader()`, calcula `Idempotency-Key` SHA-256(método+ruta+cuerpo) para mutacionales, reintenta 5xx/408 con backoff 300/600/1200ms, ejecuta refresh-once en 401 con Mutex singleton, soporta timeout via AbortController, valida respuesta con Zod schema opcional. Expone función raw `parkosFetchRaw(input, init): Promise<Response>` y wrapper tipado `parkosFetch<T>(input, init, schema?): Promise<T>`.

**Capa Store (apps/ui-kit/src/store/authStore.ts)** — Zustand store con `persist` middleware. Estado: `{accessToken: string|null, refreshToken: string|null, expiresAt: string|null}`. Acciones: `setTokens(access, refresh, expiresIn)`, `clear()`. Persistencia: `createJSONStorage(() => electronStoreAdapter)` que IPC-invoca `window.bridge.authStore.{get,set,delete}` → main process `electron-store` → filesystem `app.getPath('userData')/auth.json`. `partialize` excluye campos derivados.

**Capa Hook (apps/ui-kit/src/hooks/useAuth.ts)** — SWR hook sobre `/auth/me`. Lee `accessToken` desde authStore (subscription). Si no hay token, retorna `isAuthenticated:false`. Si hay token, ejecuta `useSWR<AuthMeResponse>('/auth/me', parkosFetch, {refreshInterval:5*60*1000, revalidateOnFocus:true, shouldRetryOnError:(err)=>err?.status!==401, onError:401→authStore.clear()})`. Retorna `{user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated, isLoading, error, refresh}`.

**Capa IPC (apps/electron-sucursal/electron/{bridge.d.ts,preload.ts})** — Contrato typed entre main y renderer. `bridge.d.ts` define `BridgeSurface` interface + `PrintPayload`, `USBDevice`, `ApiStatus` types + `declare global { interface Window { bridge: BridgeSurface } }`. `preload.ts` materializa con whitelist explícita:
```typescript
contextBridge.exposeInMainWorld('bridge', {
  imprimir: (payload) => ipcRenderer.invoke('print:ticket', payload),
  usb: { list: () => ipcRenderer.invoke('usb:list') },
  kiosk: { toggle: (on) => ipcRenderer.send('kiosk:toggle', on) },
  app: { quit: () => ipcRenderer.send('app:quit') },
  apiStatus: { get: () => ipcRenderer.invoke('api:status') },
  authStore: {
    get: (key) => ipcRenderer.invoke('auth-store:get', key),
    set: (key, value) => ipcRenderer.invoke('auth-store:set', key, value),
    delete: (key) => ipcRenderer.invoke('auth-store:delete', key),
  },
});
```
Handlers `print:ticket`, `usb:list`, `kiosk:toggle`, `app:quit`, `api:status` NO se implementan en F2.2 — F2.3 los conecta al main real (HU-F2.3-T5).

### 5.2 Diagrama de flujo (ASCII)

```
┌─────────────────────┐                  ┌────────────────────────┐
│ Renderer (React)    │                  │ Main Process           │
│                     │                  │ (Electron)             │
│ ┌─────────────────┐ │  HTTP request    │                        │
│ │ parkosFetch<T>  │─┼─────────────────►│ http://127.0.0.1:8000  │
│ └────────┬────────┘ │                  │ /api/v1/auth/me        │
│          │          │                  │                        │
│          ▼          │                  └────────────────────────┘
│ ┌─────────────────┐ │
│ │ useAuthStore()  │ │  IPC invoke      ┌────────────────────────┐
│ │ (Zustand+persist)│─┼──authStore.get──►│ electron-store         │
│ │ accessToken     │ │                  │ app.getPath('userData')│
│ └────────┬────────┘ │                  │ /auth.json             │
│          │          │                  └────────────────────────┘
│          ▼          │
│ ┌─────────────────┐ │  IPC invoke      ┌────────────────────────┐
│ │ window.bridge   │─┼──usb.list()─────►│ usb handler            │
│ │   .imprimir     │ │                  │ (F2.3 stub/mocked)     │
│ │   .usb.list     │ │                  │                        │
│ │   .kiosk.toggle │ │                  └────────────────────────┘
│ │   .app.quit     │ │
│ │   .apiStatus.get│ │
│ │   .authStore.*  │ │
│ └─────────────────┘ │
│                     │
│ ┌─────────────────┐ │                  ┌────────────────────────┐
│ │ useAuth()       │ │  SWR             │                        │
│ │ useSWR('/auth/me')│──────────────────►│ GET /api/v1/auth/me    │
│ │ refreshInterval │ │                  │ Authorization:Bearer   │
│ │ 5 * 60 * 1000   │ │                  │                        │
│ └─────────────────┘ │                  └────────────────────────┘
└─────────────────────┘
```

### 5.3 Garantías

- **Determinismo Idempotency-Key**: SHA-256(método+ruta+cuerpo) garantiza misma key para retries idénticos. El backend puede dedupe sin doble-ejecutar.
- **Mutex refresh**: `refreshPromise` singleton evita stampede en 401 concurrentes. R1 mitigado.
- **Fail-open en 401 doble**: si refresh 401, `authStore.clear()` emite evento que el router intercepta para redirect a `/login?next=<path>` (F3.1 implementa el handler).
- **Whitelist explícita**: `preload.ts` declara cada método del `BridgeSurface` individualmente. `ipcRenderer` raw nunca se expone (contextIsolation=true por F2.1).
- **Persistencia robusta**: electron-store sobrevive DevTools reset, OS storage clear, profile corruption — preferible a localStorage para kiosko Electron.

---

## 6. Contratos de comportamiento

### 6.1 Decisión explícita: NO agregar REQ-OPS-NNN nuevos

**F2.2 NO agrega REQs al spec canónico** (`openspec/specs/operations/spec.md`) porque es "infraestructura HTTP" — mismo razonamiento que F2.1 DEC-ELEC-10. Las 8 decisiones arquitectónicas viven en este `proposal.md` como DEC-FETCH-NN. Behavior contracts futuros (refresh rotation detection en PR7 backend, kiosko PIN F2.3, etc.) se agregarán como REQ cuando introduzcan endpoints nuevos o invariantes de negocio.

**Precedente**: F2.1 archivado en `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/proposal.md` §6.10 (DEC-ELEC-10) y F1.15 archivado en `operations/spec.md:4386` (DEC-XR7 NOT-CREATED) aplican la misma convención.

### 6.2 Si la propuesta decidiera agregar REQ-OPS-106..112 (enumerados verbatim)

`exploration.md` §15.4 lista las 7 REQs candidatas. F2.2 las incluye referencialmente pero NO las materializa como REQ-OPS-NNN en `operations/spec.md`:

| ID candidato | Comportamiento | Source |
|---|---|---|
| ~~REQ-OPS-106~~ | `parkosFetch retries 5xx with backoff 300/600/1200ms` | exploration §15.4 |
| ~~REQ-OPS-107~~ | `parkosFetch triggers single 401 refresh via POST /auth/refresh` | exploration §15.4 |
| ~~REQ-OPS-108~~ | `parkosFetch emits Idempotency-Key SHA-256(method+path+body) on POST/PUT/DELETE` | exploration §15.4 |
| ~~REQ-OPS-109~~ | `parkosFetch validates response via Zod schema` | exploration §15.4 |
| ~~REQ-OPS-110~~ | `authStore persists access+refresh tokens via electron-store` | exploration §15.4 |
| ~~REQ-OPS-111~~ | `useAuth hook fetches /auth/me every 5 minutes via SWR` | exploration §15.4 |
| ~~REQ-OPS-112~~ | `bridge.imprimir invokes escpos-usb with PrintPayload` | exploration §15.4 (forward hook a F5.1) |

**DECIDIDO**: NO se crean REQ-OPS-106..112 en esta propuesta. Las DEC-FETCH-NN en §4 cargan el mismo peso RFC 2119 que las REQs para HUs de comportamiento. Esta decisión es reversible: si en `sdd-spec` se determina que la complejidad justifica REQs explícitas, el spec las materializa.

### 6.3 Contratos forwarded (consume-only)

F2.2 NO crea endpoints. Consume los 4 existentes:

- `POST /api/v1/auth/login` — `LoginRequest{email, password}` → `TokenPair{access_token, refresh_token, token_type, expires_in}`. 401 invalid_credentials, 429 account_locked con `Retry-After`. `auth.py:148-307`. **Idempotente por sí mismo — NO lleva Idempotency-Key**.
- `POST /api/v1/auth/refresh` — `RefreshRequest{refresh_token}` → `TokenPair` (mismo refresh_token, sin rotation en PR1b). 401 invalid_refresh_token. `auth.py:310-349`.
- `POST /api/v1/auth/logout` — 204 No Content. Cierra último `prod.login` row abierto. `auth.py:352-393`.
- `GET /api/v1/auth/me` — `AuthMeResponse{user, sucursal, sucursales_permitidas, permisos, expires_at}`. 404 not_found en cualquier JWT failure mode (antienumeration). `auth.py:419-583`.

F2.2 NO los modifica. Backward-compat preservada.

---

## 7. Decomposición atómica (T1..T7)

Cada task es **atómica** (commiteable independientemente con tests verdes). Ejecución en orden T1 → T7. Detalle verbatim en `exploration.md` §10.

| Task | Budget (LOC) | Archivos | Commit message | Gate |
|---|---|---|---|---|
| **T1 — parkosFetch en ui-kit** | ~240 (120 prod + 120 tests) | `apps/ui-kit/src/fetch/parkosFetch.ts` (NEW) · `parkosFetch.test.ts` (NEW) · `index.ts` (NEW) · `apps/ui-kit/package.json` (MODIFY) · `apps/web_admin/src/lib/fetch.ts` (MODIFY a re-export) | `feat(ui-kit): adicionar parkosFetch con retry 5xx, refresh-once 401, Idempotency-Key SHA-256, Zod validation, AbortController timeout` | G1, G2, G3, G4 |
| **T2 — bridge.d.ts typed surface** | ~60 | `apps/electron-sucursal/electron/bridge.d.ts` (NEW) · `apps/electron-sucursal/tsconfig.main.json` (MODIFY, agregar `.d.ts` a `include`) | `feat(electron): adicionar bridge IPC typed surface en bridge.d.ts con 8 métodos (imprimir, usb, kiosk, app, apiStatus, authStore)` | G5 |
| **T3 — preload.ts IPC wiring** | ~100 (50 prod + 50 tests) | `apps/electron-sucursal/electron/preload.ts` (MODIFY 11→~50 LOC) · `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` (NEW) | `feat(electron): wire bridge IPC handlers en preload con whitelist de 8 métodos` | G5, G8 |
| **T4 — authStore Zustand** | ~140 (80 prod + 60 tests) | `apps/ui-kit/src/store/authStore.ts` (NEW) · `authStore.test.ts` (NEW) · `apps/ui-kit/package.json` (MODIFY, agregar `zustand` dep) | `feat(ui-kit): adicionar authStore Zustand con persist electron-store y Mutex refresh-once` | G6 |
| **T5 — useAuth() SWR hook** | ~90 (50 prod + 40 tests) | `apps/ui-kit/src/hooks/useAuth.ts` (NEW) · `useAuth.test.ts` (NEW) | `feat(ui-kit): adicionar useAuth SWR hook con refresh 5min y auto-clear en 401` | G7 |
| **T6 — 22 e2e auth scenarios** | ~110 | `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` (NEW) · `apps/electron-sucursal/e2e/auth/bridge.spec.ts` (NEW) | `test(electron): adicionar 22 e2e auth scenarios via MSW (14 parkosFetch + 8 bridge)` | G8 |
| **T7 — axe-core WCAG 2.1 AA gate** | ~30 | `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (NEW) | `test(electron): adicionar axe-core WCAG 2.1 AA gate (RNF-022)` | RNF-022 |
| **TOTAL** | **~770 LOC** (360 prod + 410 tests) | 13 archivos nuevos + 5 modificaciones | 7 commits atómicos | 8 gates |

**Resumen de clusters** (§9): C1 = T1+T2+T3 · C2 = T4+T5 · C3 = T6+T7. Orden obligatorio C1 → C2 → C3.

---

## 8. Riesgos y mitigaciones

Tabla de 8 riesgos con severidad y mitigación. Detalle verbatim en `exploration.md` §8.

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | Race condition 401 refresh — 5 requests concurrentes con 401 disparan 5 refreshes paralelos | HIGH | DEC-FETCH-03: Mutex singleton en `refreshPromise`; solo UN refresh activo a la vez; los demás esperan |
| **R2** | electron-store stale key TTL — refresh token expirado persiste | MEDIUM | DEC-FETCH-06: `clear()` en logout handler + en doble-401 fallido; `partialize` solo persiste `{accessToken, refreshToken, expiresAt}`; expiración validada en cada read |
| **R3** | Idempotency-Key collisions en multi-tab | LOW (kiosko single-tab) | DEC-FETCH-04: SHA-256(method+path+body) garantiza uniqueness por contenido; kiosko Electron es single-tab por diseño (F2.3 single-instance lock) |
| **R4** | Bridge IPC type drift — main process cambia handler sin actualizar d.ts | MEDIUM | DEC-FETCH-08: `bridge.contract.test.ts` valida shape en CI; `tsc --noEmit` catches drift |
| **R5** | Zod schema drift backend/frontend | MEDIUM | DEC-FETCH-05: Zod validation en runtime catches drift en dev/test; auto-generación desde Pydantic DEFERRED a Fase 3 (forward hook) |
| **R6** | electron-store path differs across OS — Windows / Linux / macOS tienen diferentes `app.getPath('userData')` | LOW | electron-store normaliza; plan F2.1 ya verificó 3-target support |
| **R7** | SHA-256 async overhead — `crypto.subtle.digest` es async; impacta latency | LOW | Pre-computar key en build del request (no bloqueante) |
| **R8** | vitest fake timers + AbortController interaction | LOW | `vi.useFakeTimers({ shouldAdvanceTime: true })` para preservar timers reales durante AbortController |

**Riesgos identificados y cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

---

## 9. Plan de entrega (orden de ejecución)

### 9.1 Clusters

F2.2 se descompone en **3 clusters** (C1, C2, C3) con orden obligatorio **C1 → C2 → C3**.

**C1: parkosFetch + bridge typed surface + preload wiring (~350 LOC)**
- T1: parkosFetch.ts + tests + ui-kit fetch index + web_admin re-export (~240 LOC).
- T2: bridge.d.ts typed surface + tsconfig include (~60 LOC).
- T3: preload.ts whitelist + contract test (~100 LOC).

**C2: authStore Zustand + useAuth() SWR hook (~230 LOC)**
- T4: authStore.ts + tests + ui-kit package.json zustand (~140 LOC).
- T5: useAuth.ts + tests (~90 LOC).

**C3: 22 e2e auth scenarios + axe-core gate (~140 LOC)**
- T6: 14 parkos-fetch.spec.ts + 8 bridge.spec.ts e2e (~110 LOC).
- T7: axe-core WCAG 2.1 AA gate (~30 LOC).

### 9.2 Orden de ejecución

`C1 → C2 → C3` (mandatory). C1 antes de C2 porque useAuth() consume parkosFetch (C1). C2 antes de C3 porque e2e tests necesitan authStore para login flow.

### 9.3 Atomicidad

Cada task T1..T7 es **commiteable independientemente** con sus tests verdes. Los 7 commits siguen conventional commits (feat/test), sin Co-authored-by. Autor: Parkos Dev.

### 9.4 Verificación por cluster

- **C1 verde** cuando T1+T2+T3 completan: G1+G2+G3+G4 (parkosFetch MSW 14 scenarios) + G5 (bridge tsc clean) + parte de G8 (preload contract test).
- **C2 verde** cuando T4+T5 completan: G6 (authStore 8 tests) + G7 (useAuth 5 tests).
- **C3 verde** cuando T6+T7 completan: G8 completo (22 e2e verde) + RNF-022 axe-core 0 violaciones.

---

## 10. Acceptance gates (G1..G8)

8 gates deben pasar ANTES de mergear F2.2 a `origin/dev`. Mecanismo + source task referenciados verbatim desde `exploration.md` §11.

| # | Gate | Mecanismo | Source task | Estado pre-flight |
|---|---|---|---|---|
| **G1** | parkosFetch retries 5xx + 408 con backoff correcto | unit test MSW con `vi.useFakeTimers()` | T1 | 0/8 PASS inicial → target 8/8 |
| **G2** | parkosFetch emite 401 refresh-once y reintenta request original | unit test MSW con Mutex validation | T1 | 0/8 → 8/8 |
| **G3** | parkosFetch emite Idempotency-Key SHA-256 en POST mutacionales | unit test MSW con hash assertion | T1 | 0/8 → 8/8 |
| **G4** | parkosFetch valida respuesta con Zod schema y lanza ZodError | unit test MSW con schema inválido | T1 | 0/8 → 8/8 |
| **G5** | bridge IPC typed surface compilable sin `any` | `tsc --noEmit` clean | T2 + T3 | 0/8 → 8/8 |
| **G6** | authStore persiste + restaura desde electron-store | unit test con mock `bridge.authStore` | T4 | 0/8 → 8/8 |
| **G7** | useAuth() hidrata desde /auth/me con SWR cache + Zustand store | unit test con SWR config mock | T5 | 0/8 → 8/8 |
| **G8** | 22 e2e auth scenarios verde + axe-core 0 violaciones | playwright e2e + axe-core | T6 + T7 | 0/8 → 8/8 |

**Estado pre-flight**: 0/8 PASS al inicio (no implementado). Target 8/8 PASS post-implementación.

**Cross-gate**: `RNF-022 WCAG 2.1 AA` (axe-core scan contra appWindow.page() con tags `['wcag2a','wcag2aa','wcag21a','wcag21aa']`) pasa en T7.

---

## 11. Compatibilidad y migración

### 11.1 Compatibilidad web_admin

`apps/web_admin/src/lib/fetch.ts` (66 LOC) se convierte a **re-export transparente** desde `@parkos/ui-kit/fetch`:

```typescript
// apps/web_admin/src/lib/fetch.ts (post-T1)
export { parkosFetch, setAuthToken, getAuthToken } from '@parkos/ui-kit/fetch';
```

- **NO breaking change** para consumidores existentes (`sucursal-context.ts`, hooks de auth legacy, etc.) que importan `parkosFetch` desde `@/lib/fetch`.
- Las capabilities R-FETCH-1 (Bearer header) y R-FETCH-2 (X-Sucursal-Context) se preservan verbatim.
- Las capabilities R-FETCH-3 (retry/refresh/idempotency/Zod/timeout) y R-FETCH-4 (authStore-backed persistence) se AÑADEN — los consumers que antes NO tenían retry ahora lo tienen automáticamente.

### 11.2 Compatibilidad backend

- F2.2 NO toca `backend/.../api/v1/auth.py`. Consume los 4 endpoints existentes sin modificarlos.
- F2.2 NO toca `backend/.../schemas/auth.py`. Consume `LoginRequest`, `TokenPair`, `AuthMeResponse` shapes sin modificarlos.
- F2.2 NO toca `modelo_datos_er.mmd`. NO crea tablas, columnas, índices ni permisos.
- F2.2 NO toca `prod.login [L-S]` (immutability preservada).
- F2.2 NO crea Alembic migration. Head sigue en `0033_login_historic_index` (F1.15).

### 11.3 Compatibilidad electron-sucursal (F2.1)

- `apps/electron-sucursal/electron/preload.ts` crece de 11 LOC a ~50 LOC (whitelist explícita). NO breaking change — F2.1 ships `{}` placeholder, F2.2 lo expande.
- `apps/electron-sucursal/electron/main.ts` (F2.1 minimal) NO se modifica. Los handlers `print:ticket`, `usb:list`, etc. NO se implementan en F2.2 — F2.3 los conecta.
- `apps/electron-sucursal/tsconfig.main.json` agrega `bridge.d.ts` a `include` — sin impacto en otros targets.
- `apps/electron-sucursal/src/renderer/global.d.ts` (NEW, ~5 LOC) — triple-slash reference a `bridge.d.ts`.

### 11.4 Compatibilidad ui-kit (F2.1)

- `apps/ui-kit/package.json` agrega `dependencies: { "zustand": "^4.5.0" }`, `peerDependencies: { "swr": "^2.2.5" }`, `devDependencies: { "zod": "^3.23.0", "msw": "^2.4.0", "@testing-library/react": "^16.0.0" }`.
- `apps/ui-kit/src/index.ts` (F2.1) NO se modifica (Button + cn + tokens intactos).
- `apps/ui-kit/src/Button.tsx`, `cn.ts`, `tokens.ts` (F2.1) NO se tocan.

### 11.5 i18n

F2.2 NO agrega keys nuevos. Los namespaces `auth`, `errors` (F2.1) están listos para que F3.1 (login UI) los pueble.

---

## 12. Observabilidad y testing

### 12.1 Unit tests (Vitest + MSW + jsdom)

| Archivo | Escenarios | Cobertura target |
|---|---|---|
| `apps/ui-kit/src/fetch/parkosFetch.test.ts` | 14 escenarios MSW: bearer header, retry 5xx, retry 408, retry network error, NO retry 4xx (excepto 408), 401 refresh-once, 401 refresh-fail-clear, Mutex concurrency, Idempotency-Key SHA-256, X-Sucursal-Context, timeout AbortController, Zod schema pass, Zod schema fail (lanzar ZodError), backoff timing con `vi.useFakeTimers()` | **>90%** |
| `apps/ui-kit/src/store/authStore.test.ts` | 8 escenarios: initial state, setTokens persiste via electronStoreAdapter, getState restores from electron-store, clear() borra state, partialize excluye campos derivados, Mutex refresh dedupe, refresh fail limpia state, expiración validada en read | **>80%** |
| `apps/ui-kit/src/hooks/useAuth.test.ts` | 5 escenarios: sin accessToken retorna isAuthenticated:false, con accessToken hidrata /auth/me, refreshInterval 5*60*1000 verbatim, revalidateOnFocus true, 401 dispara useAuthStore.clear() | **>80%** |
| `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` | Validación shape: cada método de `BridgeSurface` está implementado en `preload.ts`; ningún `ipcRenderer` raw se expone; contextBridge.exposeInMainWorld recibe exactamente la whitelist | N/A (contract test) |

### 12.2 E2E tests (Playwright + _electron.launch + axe-core)

| Archivo | Escenarios | Mecanismo |
|---|---|---|
| `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` | 14 escenarios: `parkosFetch retries 5xx con backoff`, `parkosFetch refresh-once 401`, `parkosFetch emits Idempotency-Key SHA-256`, `parkosFetch Zod validation`, `parkosFetch timeout AbortController`, etc. (verbatim `plan.md:1214-1227`) | `_electron.launch({args:['.']})` + MSW handlers via Node |
| `apps/electron-sucursal/e2e/auth/bridge.spec.ts` | 8 escenarios: `bridge.imprimir con PrintPayload`, `bridge.usb.list retorna USBDevice[]`, `bridge.kiosk.toggle(on)`, `bridge.app.quit`, `bridge.apiStatus.get`, `bridge.authStore.get/set/delete roundtrip`, etc. (verbatim `plan.md:1229`) | `_electron.launch` + ipcMain.handle mock |
| `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` | axe-core scan con tags `['wcag2a','wcag2aa','wcag21a','wcag21aa']` — 0 violaciones | `@axe-core/playwright` |

**Total e2e**: 22 escenarios + 1 axe-core scan.

### 12.3 Coverage

| Archivo | Coverage target | Mecanismo |
|---|---|---|
| `parkosFetch.ts` | **>90%** | vitest --coverage + threshold en `vitest.config.ts` |
| `authStore.ts` | **>80%** | vitest --coverage |
| `useAuth.ts` | **>80%** | vitest --coverage |
| `bridge.d.ts` + `preload.ts` | N/A (declaration + contextBridge) | tsc --noEmit + contract test |

### 12.4 Mutation testing

- **NO este sprint** (deferred Fase 3).
- Forward hook: integrar `stryker-mutator` o `vitest-mutation` en `vitest.config.ts` para parkosFetch.ts post-Fase 3 estabilización.

### 12.5 Logging

- F2.2 NO agrega logging (F2.3 introduce electron-log rotation 10MB×5 JSON).
- Errores en parkosFetch se propagan como `ParkosHttpError` con `status` y `body` para que callers (F3.1+) decidan UX (toast, redirect, retry manual).

---

## 13. Rollback plan

### 13.1 Estrategia general

7 commits atómicos permiten **rollback granular** via `git revert <sha>` por task.

### 13.2 Escenarios de rollback

| Escenario | Acción | Reversibilidad |
|---|---|---|
| **T1 falla** | `git revert <T1-sha>` | `apps/web_admin/src/lib/fetch.ts` vuelve a su contenido original (no re-export); `apps/ui-kit/src/fetch/*` desaparece. web_admin sigue funcionando con `parkosFetch` legacy en su propio `lib/fetch.ts`. NO se elimina el archivo original, solo se convierte a re-exporter — `git revert` restaura el contenido anterior. |
| **T2/T3 fallan** | `git revert <T2-sha> <T3-sha>` | `bridge.d.ts` se elimina; `preload.ts` vuelve a `{ }` (F2.1 state). Bridge vacío es funcional (F2.1 vereds). Type safety se pierde — tsc --noEmit puede pasar porque `window.bridge` queda `unknown`, pero los consumers no se compilan hasta que T2+T3 regresen. |
| **T4/T5 fallan** | `git revert <T4-sha> <T5-sha>` | `authStore.ts` + `useAuth.ts` desaparecen. Callers (futuros F3.1+) caen en fallback a localStorage (F1.x/F2.1 behaviour). Sin pérdida de datos — `auth.json` en `app.getPath('userData')/` puede persistir, pero authStore ya no lo lee; cleanup manual en F2.3. |
| **T6/T7 fallan** | `git revert <T6-sha> <T7-sha>` | E2e tests se eliminan. CI gate G8 cae. Riesgo aceptable si unit tests (G1..G7) pasan — e2e solo se difiere, no es bloqueante. F2.1 axe-core en `scaffold.spec.ts` sigue verde. |
| **Fallo sistémico post-merge** | `git revert <merge-sha>` total | F2.2 se deshace completamente. F2.1 ya archivada — workspace topology intacta. |

### 13.3 Tests de rollback

Después de cada `git revert`, ejecutar:
```bash
npm run typecheck         # tsc -b en 3 tsconfigs
npm run test              # vitest unit
npm run test:e2e          # playwright e2e
npm run lint              # eslint --max-warnings 0
```

Si los 4 comandos pasan post-revert, el rollback es exitoso.

---

## 14. Documentación a actualizar

| Archivo | Cambio | Task |
|---|---|---|
| `apps/ui-kit/README.md` | Agregar sección **"HTTP client (parkosFetch)"** con capability matrix, ejemplos de uso, retry/refresh/idempotency/Zod. Agregar sección **"Auth (authStore + useAuth())"** con persist electron-store, SWR integration, `useAuth()` API. | T1+T4+T5 |
| `apps/electron-sucursal/README.md` | Agregar sección **"Bridge IPC"** referenciando `bridge.d.ts`. Listar 8 métodos en 6 grupos con signatures y forward consumers. | T2+T3 |
| `apps/web_admin/README.md` | Sin cambios (re-export transparente). Mencionar que `parkosFetch` ahora viene de `@parkos/ui-kit/fetch`. | T1 (mención) |
| `docs/03-desarrollo/estandares.md` | Agregar convención: **"Auth tokens en electron-store, NO localStorage"**. Justificación: kiosko Electron sobrevive DevTools reset + OS storage clear. | T4 |
| `docs/02-arquitectura/decisiones-tecnicas.md` | Agregar entradas DEC-FETCH-01..08 (resumen). Referenciar este proposal.md para detalle. | Post-F2.2 (archive) |
| `openspec/_meta/roadmap.md` | Marcar HU-F2.2 como completed tras archive. | Post-archive |
| `openspec/CHANGELOG.md` | Entrada: "2026-09-15 — HU-F2.2 parkosFetch + IPC bridge + authStore archived". | Post-archive |

**NO se actualiza**: `docs/01-requisitos/no-funcionales.md` (RNF-022 ya documentado), `docs/03-desarrollo/setup.md` (sin cambios), `docs/00-general/README.md` (sin cambios).

---

## 15. Checklist final (Definition of Done)

- [ ] **7 atomic commits** en `feat/fase-2-electron-scaffold` con author Parkos Dev, sin `Co-authored-by`.
- [ ] Conventional commits formato `<type>(<scope>): <description>` con type ∈ {feat, fix, test, refactor, docs, chore}, scope ∈ {ui-kit, electron, web}.
- [ ] **8/8 acceptance gates PASS** (G1..G8).
- [ ] `parkosFetch.ts` cobertura **>90%** (vitest --coverage threshold).
- [ ] `authStore.ts` cobertura **>80%**.
- [ ] `useAuth.ts` cobertura **>80%**.
- [ ] `tsc --noEmit` limpio en `ui-kit` + `web_admin` + `electron-sucursal` (main + renderer).
- [ ] Playwright e2e **22/22 verde** (14 parkos-fetch + 8 bridge).
- [ ] axe-core **0 violaciones WCAG 2.1 AA** (RNF-022).
- [ ] **0 regresiones** en F1/F2.1 vereds (ver §11 compatibility):
  - web_admin `sucursal-context.ts` sigue funcionando.
  - electron-sucursal smoke test sigue verde.
  - backend `/auth/*` endpoints no tocados.
- [ ] `apps/ui-kit/README.md`, `apps/electron-sucursal/README.md`, `docs/03-desarrollo/estandares.md` actualizados.
- [ ] `npm run lint --max-warnings 0` limpio en los 3 workspaces.
- [ ] `npm run build` produce `dist/renderer` + `out/main` + `out/preload.js` sin type errors.
- [ ] pre-commit hooks (eslint + prettier) pasan localmente.
- [ ] PR description incluye referencia a este proposal.md + exploration.md.

---

## 16. Referencias

### 16.1 Source of truth

- `plan.md` lines 1196-1240 — HU-F2.2 verbatim con 7 tareas atómicas T1..T7 (T1 parkosFetch lines 1212-1213, T2 bridge.d.ts line 1218, T3 preload line 1219, T4 authStore line 1220, T5 useAuth line 1221, T6 14 e2e auth scenarios lines 1224-1227, T7 8 bridge e2e line 1229). Hard constraints: baseURL line 1203, 5xx retry 300/600/1200ms line 1204, 401 refresh-once line 1205, bridge surface line 1206, useAuth SWR 5*60*1000 line 1208.
- `openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/exploration.md` — 17 secciones, ~870 LOC, 8 DEC-FETCH-NN (sección 7), 8 riesgos R1..R8 (sección 8), 7 atomic tasks T1..T7 con budgets (sección 10), 8 acceptance gates G1..G8 (sección 11), pre-flight 10/10 PASS (sección 12), out of scope (sección 13), forward hooks (sección 14), REQ-OPS-106..112 candidates (sección 15.4), archivos a tocar (sección 17).

### 16.2 Precedentes archivados

- `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/proposal.md` — 16 secciones, ~770 LOC. Estructura verbatim (esta propuesta clona layout). DEC-ELEC-10 precedent: "F2.1 NO agrega REQ-OPS-NNN — infra, no behavior contract".
- `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/exploration.md` — 17 secciones, ~1,150 LOC. DEC-ELEC-01..10 mirror. Workspaces topological order resuelto.
- `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/exploration.md` — 17 secciones template verbatim mirror.
- `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/proposal.md` — 16 secciones canonical template.
- `openspec/changes/archive/bootstrap-monorepo-foundation/proposal.md:9` — workspaces precedent verbatim.

### 16.3 Backend anchors

- `backend/.../api/v1/auth.py:148-307` — `POST /auth/login` (LoginRequest → TokenPair, parkos_session cookie httponly+secure+samesite=lax).
- `backend/.../api/v1/auth.py:310-349` — `POST /auth/refresh` (RefreshRequest → TokenPair, NO rotation en PR1b).
- `backend/.../api/v1/auth.py:352-393` — `POST /auth/logout` (cierra prod.login row).
- `backend/.../api/v1/auth.py:419-583` — `GET /auth/me` (AuthMeResponse, 404 not_found antienumeration).
- `backend/.../schemas/auth.py:243-321` — LoginRequest, RefreshRequest, TokenPair, UserItem, SucursalItem, AuthMeResponse Pydantic shapes.

### 16.4 Modelo de datos

- `modelo_datos_er.mmd:558-573` — `prod.login [L-S]` (inmutable, branch→cloud sync). F2.2 NO touch.
- `modelo_datos_er.mmd:7-50` — `prod.usuarios [V]`. F2.2 NO touch.
- `modelo_datos_er.mmd:270-289` — `prod.configuracion_seguridad [V]`. F2.2 NO touch.

### 16.5 Apps anchors

- `apps/web_admin/src/lib/fetch.ts:1-66` — parkosFetch existente (fuente de reutilización).
- `apps/web_admin/src/lib/sucursal-context.ts` — getSucursalHeader() (READ ONLY — F2.2 NO migration scope).
- `apps/electron-sucursal/electron/preload.ts:1-11` — contextBridge vacío (F2.2 lo expande).
- `apps/electron-sucursal/electron/bridge.d.ts` — NO existe (F2.2 T2 lo crea).
- `apps/ui-kit/src/{Button,cn,tokens}.{tsx,ts}` — workspace package shipped F2.1 (target de nueva ubicación).
- `apps/ui-kit/package.json` — F2.1 shipeado, F2.2 agrega deps.
- `apps/package.json:5-8` — workspaces = ["ui-kit","web_admin","electron-sucursal"] (F2.1 ya añadió electron-sucursal).

### 16.6 Documentación

- `docs/01-requisitos/no-funcionales.md:126` — RNF-022 WCAG 2.1 AA gate (axe-core tags).
- `docs/03-desarrollo/setup.md:15` — npm + npm-run-all pattern.
- `docs/03-desarrollo/estandares.md:79-91` — flat ESLint 9 config + convenciones.
- `docs/00-general/README.md:64-67` — apps/ui-kit scaffold state.
- `docs/00-general/roadmap.md:102` — apps/ui-kit scaffold state.
- `docs/02-arquitectura/decisiones-tecnicas.md` — agregar DEC-FETCH-01..08 post-archive.

### 16.7 Specs y roadmap

- `openspec/specs/operations/spec.md:3951` — REQ-OPS-XR6 canonical 5-layer defense (reference, F2.2 NO crea new XR).
- `openspec/specs/operations/spec.md:4386` — F1.15 DEC-XR7 NOT-CREATED precedent.
- `openspec/specs/operations/spec.md:32` — REQ-OPS-002 coverage ≥80% sync modules (NO aplicable a F2.2).
- `openspec/_meta/iteration-plan.md:152` — IT-3.9 web_sucursal IngresoForm (F2.2 consumer).
- `openspec/_meta/roadmap.md:38-273` — IT-1..IT-10 web_sucursal consumer map.
- `openspec/_meta/roadmap.md:47` — web_sucursal no existe (F2.1 ya fixed).

### 16.8 Convenciones

- Conventional commits (sin Co-authored-by por convención global).
- TDD estricto: tests rojos primero, luego código que los hace verde.
- Defense in depth 5 capas (XR6 pattern + engineering variant).
- RFC 2119 MUST/SHOULD/MAY key words en DEC-FETCH-NN.
- BDD Given/When/Then/And format en acceptance gates.

---

**End of proposal.**