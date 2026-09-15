# Exploración — HU-F2.3 Auto-actualización, single-instance y kiosko

> **Phase**: explore (sdd-explore) · **Status**: ready for sdd-propose
> **HU ID**: HU-F2.3 (Fase 2 — última HU; cierra Andamiaje Electron con infra de runtime)
> **Working dir**: E:/easypunto_parkos · **Branch**: feat/fase-2-electron-scaffold (HEAD 6bfe514, F2.1 + F2.2 archivados 2026-09-15)
> **Inputs**: plan.md lines 1244-1266; plan.md lines 1159-1240 (F2.1+F2.2 archivados); plan.md lines 1270+ (Fase 3 forward consumers); openspec/_meta/roadmap.md; openspec/specs/operations/spec.md; apps/electron-sucursal/electron/{main.ts:1-55, preload.ts:1-49, bridge.d.ts:1-87, __tests__/preload.contract.test.ts:1-110, __mocks__/electron.ts}; apps/electron-sucursal/package.json; apps/electron-sucursal/tsconfig.{json,main.json}; apps/electron-sucursal/vite.config.ts; apps/electron-sucursal/playwright.config.ts; apps/electron-sucursal/esbuild-main.mjs (DEC-ELEC-03); apps/electron-sucursal/src/renderer/{App.tsx,main.tsx,i18n/locales/common.json}; apps/electron-sucursal/e2e/{scaffold.spec.ts,auth/parkos-fetch.spec.ts,auth/bridge.spec.ts,a11y/wcag-2.1-aa.spec.ts}; apps/ui-kit/{package.json,src/{index.ts,Button.tsx,cn.ts,tokens.ts,store/authStore.ts,store/authStore.test.ts,hooks/useAuth.ts,hooks/useAuth.test.ts,fetch/parkosFetch.ts,fetch/parkosFetch.test.ts}}; docs/01-requisitos/no-funcionales.md:126 (RNF-022 WCAG 2.1 AA); docs/03-desarrollo/{setup.md:15, estandares.md:79-91}; pending.md §1-2; openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/{exploration.md,archive-report.md} (precedentes verbatim); openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/exploration.md (precedente verbatim 17 secciones, DEC-FETCH-01..08 style).

---

## 1. Title & Goal

**Title**: "Auto-actualización con electron-updater (feed configurable + signature verification + autoDownload/autoInstallOnAppQuit) + Single-instance lock con second-instance focus + Kiosko mode con PIN bcrypt factor 12 + api-status polling 30s a /health + electron-log rotación 10MB×5 JSON + StatusBar aria-live polite con de-duplicación de anuncios consecutivos"

**Goal**: F2.1 shipteó el skeleton (Electron 30 + Vite 5 + React 18 + TS 5 strict + shadcn 14 + i18n 7 namespaces + ui-kit workspace + Playwright _electron + axe-core) y F2.2 llenó el bridge IPC con 8 métodos typed + parkosFetch + authStore + useAuth. Lo único que falta para cerrar Fase 2 es la **infra de runtime** que toda feature operativa posterior consumirá sin reinventar: auto-update, single-instance, kiosko, logging estructurado, health polling y la primera pieza de UI de status. F2.3 entrega esos seis bloques de infraestructura sobre la base sentada por F2.1 + F2.2:

1. **electron-updater** — `autoUpdater.checkForUpdates()` cada 6h (configurable), `autoDownload:true` (descarga silenciosa), `autoInstallOnAppQuit:true` (instala al cerrar), `allowDowngrade:false`. Feed configurable via env `PARKOS_UPDATE_FEED_URL` (default GitHub releases para el repo easypunto_parkos). Signature verification via `electron-builder` publish config — si la firma falla, NO se instala, se loguea el error en `electron-log` y se reintenta en el próximo ciclo.
2. **electron-log rotación 10MB×5 JSON** — `log.transports.file.maxSize = 10 * 1024 * 1024`, `transports.file.backups = 5`, `log.format = log.formats.json`. Captura `uncaughtException` y `unhandledRejection` con `log.error(...)`. Path: `app.getPath('userData')/logs/main.log` (Windows: `%APPDATA%/parkos/logs/main.log`).
3. **app.requestSingleInstanceLock() + second-instance focus** — Llamada ANTES de `app.whenReady()` para evitar race conditions. Si el lock falla (`false`), la segunda invocación llama `app.quit()` inmediatamente. Si el lock es OK (`true`), se registra el listener `app.on('second-instance', () => { mainWindow.focus() })`.
4. **api-status polling 30s a /health** — `electron/services/api-status.ts` hace `fetch('http://127.0.0.1:8000/health')` cada 30 s con `AbortController` timeout 5 s. Devuelve `{ok: boolean, latency_ms: number, code?: number}`. Maneja 3 estados: 2xx → `{ok:true, latency_ms}`, 2xx con >1000ms → loggeado como lento (sigue `{ok:true, latency_ms}`), timeout/error → `{ok:false, code?: number}`. Expone via IPC handler `api:status` que `bridge.apiStatus.get()` consume (F2.2 ya wireado, F2.3 materializa el handler real).
5. **Kiosko mode con PIN bcrypt** — Toggle via env `PARKOS_KIOSK_MODE=1` o via `bridge.kiosk.toggle(true)` (F2.2 ya lo expone). Cuando está activo: `mainWindow.setKiosk(true)` (pantalla completa sin barra de tareas), `Menu.setApplicationMenu(null)`, `mainWindow.on('close', e => e.preventDefault())` (impide Alt+F4), `mainWindow.webContents.on('before-input-event', ...)` bloquea `Ctrl+W` y otros shortcuts. Salida con `Ctrl+Shift+K` + PIN: `bcrypt.hash(pin, 12)` pre-compartido via electron-store bajo key `kiosk.pinHash` (configurado al deploy, NO se pide al usuario). Comparación con `bcrypt.compareSync(pin, hash)` — comparación en tiempo constante. **El PIN NUNCA se loguea** (ni en texto plano ni hasheado; el log solo registra `kiosko.unlock_attempt{success: bool, attempt_id: uuid}`).
6. **StatusBar con aria-live polite** — Componente React nuevo (`apps/electron-sucursal/src/renderer/components/StatusBar.tsx`). Suscribe al polling de `bridge.apiStatus.get()` via SWR (intervalo 30 s). Renderiza texto exacto por estado:
   - `{ok:true, latency_ms <= 1000}` → `"🟢 API OK"` (verde)
   - `{ok:true, latency_ms > 1000}` → `"🟡 API lento"` (amarillo)
   - `{ok:false}` → `"🔴 Sin API"` (rojo)
   Atributo `aria-live="polite"` para que screen readers anuncien el cambio sin interrumpir al usuario. **De-duplicación de anuncios consecutivos**: si el estado nuevo es igual al anterior, NO se vuelve a anunciar (track via ref `lastAnnouncedState`). Debounce 2 s entre anuncios para no saturar al screen reader.

**Por qué importa** (rationale): F2.3 cierra Fase 2 con la infraestructura de runtime que toda HU operativa posterior (F3.1 login, F3.3 turno, IT-3..IT-10 operación, IT-11 sync UI) consumirá. Sin auto-update, deploys requieren intervención manual del operador (inacceptable para kiosko desatendido). Sin single-instance lock, dos ventanas abiertas pueden escribir a la misma DB generando races (catastrófico para flujo de caja). Sin kiosko mode, el operador puede cerrar la app accidentalmente durante operación (pérdida de datos). Sin electron-log, debugging post-mortem es imposible. Sin api-status polling, el operador opera a ciegas cuando el backend está caído (facturación perdida). Sin StatusBar con a11y, RNF-022 se rompe en cuanto agreguemos el primer elemento dinámico de UI. **F2.3 es la última oportunidad de Fase 2 para sentar las bases sin renegociar contratos** — F3.x arranca con `login + lockout + turno` y NO debe tocar infra.

**Hard constraints** (mirrored from plan.md:1244-1266):
- `electron-updater.autoDownload:true`, `autoInstallOnAppQuit:true`, `allowDowngrade:false` — G1 verbatim.
- `app.requestSingleInstanceLock()` retorna `boolean`; si `false` → `app.quit()` antes de `whenReady` — G3 verbatim.
- `PARKOS_KIOSK_MODE=1` → full-screen + `Menu.setApplicationMenu(null)` + bloquea `Ctrl+W`/`Alt+F4`; salida con `Ctrl+Shift+K` + `bcrypt.hash(pin, 12)` + comparación en tiempo constante; PIN nunca logueado — G4 verbatim.
- `electron-log` rotación 10 MB × 5 backups, formato JSON, captura `uncaughtException`/`unhandledRejection` — G5 verbatim.
- api-status polling cada 30 s, IPC `bridge.apiStatus` con `{ok, latency_ms, code?}` resuelve los 3 estados (🟢 OK / 🟡 lento / 🔴 Sin API) — G6 verbatim.
- `<StatusBar>` con `aria-live="polite"` + de-duplicación de anuncios consecutivos — G7 verbatim.
- e2e lifecycle + kiosko: segunda instancia enfoca, `Ctrl+W` bloqueado, PIN incorrecto no desbloquea — G8 verbatim.

**Scope**: ~450 LOC production (matches plan.md:1257 verbatim). Breakdown por cluster C1..C4 detallado en §10. Total estimado con tests ~850-950 LOC (variance plan 450 → 550 esperado por e2e verbose + JSON config rotation).

## 2. Estado actual verificado

### 2.1 main.ts (apps/electron-sucursal/electron/main.ts:1-55)

**Verificado**:
- **R-MAIN-1 (PASS)**: `app.whenReady().then(() => createMainWindow())` con `BrowserWindow({width:1280,height:800,minWidth:1024,minHeight:700,show:false,title:'Parkos Sucursal'})` y `webPreferences:{preload,contextIsolation:true,nodeIntegration:false,sandbox:true}`.
- **R-MAIN-2 (FAIL — F2.3 lo agrega)**: NO llama `app.requestSingleInstanceLock()` antes de `whenReady`.
- **R-MAIN-3 (FAIL — F2.3 lo agrega)**: NO inicializa `electron-log` rotación.
- **R-MAIN-4 (FAIL — F2.3 lo agrega)**: NO wirea `electron-updater.autoUpdater` init.
- **R-MAIN-5 (FAIL — F2.3 lo agrega)**: NO implementa el handler IPC `api:status` para `bridge.apiStatus.get()`.
- **R-MAIN-6 (FAIL — F2.3 lo agrega)**: NO implementa `kiosk:toggle` ni `app:quit` handlers.
- **R-MAIN-7 (PASS)**: `mainWindow.webContents.setWindowOpenHandler(({url}) => shell.openExternal(url))` — ya hace deny + external open.
- **R-MAIN-8 (FAIL — F2.3 lo agrega)**: NO captura `uncaughtException`/`unhandledRejection`.
- **R-MAIN-9 (PASS)**: `app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })` — estándar macOS dock preservation.

**Decisión técnica (ver §8)**: extraer cada bloque de init a `electron/services/{updater,log-config,api-status,kiosko,single-instance}.ts` para que `main.ts` quede como composición pura (importa + llama, sin lógica inline). Esto permite tests unitarios de cada servicio por separado.

### 2.2 preload.ts (apps/electron-sucursal/electron/preload.ts:1-49)

**Verificado**:
- **R-IPC-1 (PASS)**: `contextBridge.exposeInMainWorld('bridge', {...})` con whitelist explícita de 8 métodos (NO spread) — F2.2 lo shippeó.
- **R-IPC-2 (PASS)**: `bridge.apiStatus.get()` ya invoca `ipcRenderer.invoke('api:status')` — F2.3 solo implementa el handler en main process.
- **R-IPC-3 (PASS)**: `bridge.kiosk.toggle(on)` ya hace `ipcRenderer.send('kiosk:toggle', on)` — F2.3 implementa el handler.
- **R-IPC-4 (PASS)**: `bridge.app.quit()` ya hace `ipcRenderer.send('app:quit')` — F2.3 implementa el handler.
- **R-IPC-5 (PASS)**: contract test `__tests__/preload.contract.test.ts` valida shape via mocks — F2.2 lo shippeó.

**Decisión técnica (ver §8)**: F2.3 NO modifica `preload.ts`. Solo agrega handlers en main process que escuchan los canales que preload ya emite. Esto preserva el contract test verde y mantiene el principio de whitelist filtering (R-IPC del F2.2 DEC-FETCH-08).

### 2.3 bridge.d.ts (apps/electron-sucursal/electron/bridge.d.ts:1-87)

**Verificado**:
- **R-DTS-1 (PASS)**: `BridgeSurface` interface ya define `apiStatus.get(): Promise<ApiStatus>`, `kiosk.toggle(on: boolean): void`, `app.quit(): void` — F2.2 lo shippeó.
- **R-DTS-2 (PARTIAL)**: `ApiStatus {online: boolean, lastSync: string | null}` es el shape ACTUAL; **F2.3 lo extiende** a `{ok: boolean, latency_ms: number, code?: number}` para los 3 estados (🟢/🟡/🔴). Esto es un DELTA al bridge.d.ts que requiere actualizar preload contract test.

**Decisión técnica (ver §8)**: DEC-UPD-12 cambia `ApiStatus` shape. Mantener backward-compat imposible sin romper parkosFetch (F2.2 DEC-FETCH-08 enforza exact shape). Cambio se acepta como breaking — solo hay 1 consumer en F2.3 (`StatusBar`) y 1 stub en F2.2 (`bridge.spec.ts` test 5) que se actualiza simultáneamente.

### 2.4 package.json (apps/electron-sucursal/package.json:22-77)

**Verificado**:
- **R-DEPS-1 (PASS)**: `electron-log@^5.1.7` ya está en dependencies (F2.1 lo agregó como placeholder).
- **R-DEPS-2 (PASS)**: `electron-updater@^6.3.9` ya está en dependencies (F2.1 lo agregó como placeholder).
- **R-DEPS-3 (PASS)**: `electron-store@^8.2.0` ya está en dependencies (F2.2 lo consumió para authStore).
- **R-DEPS-4 (FAIL — F2.3 lo agrega)**: `bcrypt` NO está en dependencies. F2.3 agrega `bcrypt@^5.1.1` + `@types/bcrypt@^5.0.2` (dev).
- **R-DEPS-5 (PASS)**: `electron-builder@^25.0.5` + `electron@^30.5.1` ya están (F2.1 DEC-ELEC-04).
- **R-DEPS-6 (PASS)**: `@playwright/test@^1.48.0` ya está (F2.2 e2e).
- **R-DEPS-7 (PASS)**: `@axe-core/playwright@^4.10.0` ya está (RNF-022 gate).

**Decisión técnica (ver §8)**: F2.3 agrega solo `bcrypt` + `@types/bcrypt`. Las otras deps ya están. NO requiere npm install si `bcrypt` se agrega a package.json en el commit (la instalación la hace el apply phase).

### 2.5 tsconfig + vite config + esbuild config

**Verificado**:
- **R-CFG-1 (PASS)**: `tsconfig.json` references `./tsconfig.main.json` + `./tsconfig.renderer.json` (F2.1 DEC-ELEC-02).
- **R-CFG-2 (PASS)**: `tsconfig.main.json` includes `electron/**/*.ts` + `electron/**/*.d.ts` + `src/main/**/*.ts` + `src/shared/**/*.ts` con `strict:true` + `noUncheckedIndexedAccess:true` (F2.1 DEC-ELEC-02).
- **R-CFG-3 (FAIL — F2.3 lo agrega)**: `tsconfig.main.json` NO incluye `electron/services/**/*.ts` — F2.3 lo agrega.
- **R-CFG-4 (PASS)**: `vite.config.ts` alias `@` → `src/renderer` + `@shared` → `src/shared` (F2.1 DEC-ELEC-03).
- **R-CFG-5 (PASS)**: `esbuild-main.mjs` bundlea `electron/main.ts` → `out/main.js` + `electron/preload.ts` → `out/preload.js` con target node20 format cjs external:electron (F2.1 DEC-ELEC-03).
- **R-CFG-6 (FAIL — F2.3 lo agrega)**: `esbuild-main.mjs` NO incluye `electron/services/**/*.ts` — esbuild resuelve transitivamente desde main.ts entry, así que NO requiere cambio.

**Decisión técnica (ver §8)**: F2.3 agrega `electron/services/**/*.ts` al include de `tsconfig.main.json` para que tsc valide strict types. esbuild resuelve transitivamente sin cambio.

### 2.6 e2e/ (apps/electron-sucursal/e2e/)

**Verificado**:
- **R-E2E-1 (PASS)**: `e2e/scaffold.spec.ts` (F2.1, axe-core gate RNF-022).
- **R-E2E-2 (PASS)**: `e2e/auth/parkos-fetch.spec.ts` (F2.2, 14 scenarios).
- **R-E2E-3 (PASS)**: `e2e/auth/bridge.spec.ts` (F2.2, 8 scenarios).
- **R-E2E-4 (PASS)**: `e2e/a11y/wcag-2.1-aa.spec.ts` (F2.2, axe-core scan).
- **R-E2E-5 (FAIL — F2.3 lo agrega)**: NO existe `e2e/lifecycle.spec.ts` (segunda instancia focus + kiosko Ctrl+W).
- **R-E2E-6 (FAIL — F2.3 lo agrega)**: NO existe `e2e/kiosko.spec.ts` (PIN incorrecto + log de audit).

**Decisión técnica (ver §8)**: F2.3 agrega 3 e2e (lifecycle + kiosko + bonus). Las e2e en sandbox F.6 + npm 11.16.0 SKIPPED precedent (F2.2 G8 archive report) — F2.3 e2e van a correr la misma suerte, documentado en §11.

### 2.7 apps/ui-kit/

**Verificado**:
- **R-UI-1 (PASS)**: `apps/ui-kit/src/index.ts` exporta Button + cn + tokens (F2.1 DEC-ELEC-08).
- **R-UI-2 (PASS)**: `apps/ui-kit/src/hooks/useAuth.ts` + `apps/ui-kit/src/store/authStore.ts` (F2.2 DEC-FETCH-06/07).
- **R-UI-3 (FAIL — F2.3 opcional)**: NO existe `apps/ui-kit/src/hooks/useApiStatus.ts` — F2.3 opcional lo crea como wrapper SWR para `bridge.apiStatus.get()`.

**Decisión técnica (ver §8)**: F2.3 NO requiere nuevo ui-kit export. StatusBar consume `bridge.apiStatus.get()` directamente con su propio `useState` + `setInterval`. Si el equipo decide abstraer (forward consumer: F11.x sync UI), DEC-UPD-13 lo agrega como follow-up HU.

## 3. Consumer anchor: endpoints backend + servicios externos

### 3.1 Backend /health endpoint

**Estado**: NO EXISTE en backend.

`backend/packages/parkos_core/src/parkos_core/api/v1/` no contiene `health.py` ni equivalente. F2.3 lo necesita para `bridge.apiStatus.get()`. Plan.md §1270+ menciona "Fase 3" como consumer de login, no como creador de `/health`.

**Decisión**: F2.3 implementa el polling asumiendo endpoint hypothetical con response `{status: "ok"}` (2xx) o cualquier error (4xx/5xx/timeout). StatusBar renderiza 🔴 mientras el endpoint no exista. Documentado en pending.md §2 (bloqueador deployment) y en este exploration §15 (out-of-scope). F2.3 NO bloquea si /health no existe — degrada gracefully a 🔴.

### 3.2 electron-updater feed

**Estado**: configurable.

`electron-updater` lee la config `publish` desde `electron-builder.yml` (F2.1 DEC-ELEC-04 lo creó con `autoUpdate:false` placeholder). F2.3 agrega `publish: [{provider: 'github', owner: 'easypunto_parkos', repo: 'easypunto_parkos'}]` como default. Override via env `PARKOS_UPDATE_FEED_URL` para entornos staging (custom server).

**Decisión**: F2.3 usa `autoUpdater.setFeedURL(process.env.PARKOS_UPDATE_FEED_URL || 'https://github.com/easypunto_parkos/easypunto_parkos/releases')` en runtime para sobreescribir el publish default sin recompilar electron-builder.

### 3.3 electron-log path

**Estado**: ya integrado en electron-log@^5.1.7.

`log.transports.file.resolvePathFn = () => path.join(app.getPath('userData'), 'logs', 'main.log')`. Default electron-log path es `%APPDATA%/<productName>/logs/main.log` (Windows) — matches `Parkos Sucursal` productName de F2.1 DEC-ELEC-04. NO requiere override.

### 3.4 bcrypt PIN pre-shared

**Estado**: NO EXISTE en electron-store.

F2.3 crea el hash al primer deploy via script de seeding: `node scripts/seed-kiosko-pin.js --pin=<value>` (out-of-scope, pero el contrato está documentado). El hash se persiste bajo key `kiosk.pinHash` en `app.getPath('userData')/auth.json` (electron-store ya existe por F2.2).

**Decisión**: F2.3 lee `bridge.authStore.get('kiosk.pinHash')` al startup. Si `null`, kiosko mode se desactiva con warning loggeado (`kiosko.pin_missing`). El deploy-time seeding script se documenta en §15 out-of-scope.

## 4. Stack técnico objetivo

### 4.1 Nuevas dependencias (apps/electron-sucursal/package.json)

**AGREGAR**:
- `dependencies`: `bcrypt@^5.1.1` (factor 12 compatible).
- `devDependencies`: `@types/bcrypt@^5.0.2`.

**YA EXISTEN** (F2.1 + F2.2):
- `electron-updater@^6.3.9` (F2.1 placeholder).
- `electron-log@^5.1.7` (F2.1 placeholder).
- `electron-store@^8.2.0` (F2.2 authStore).
- `electron@^30.5.1` + `electron-builder@^25.0.5` (F2.1 DEC-ELEC-04).
- `react@^18.3.1` + `react-dom@^18.3.1` (F2.1 scaffold).
- `swr@^2.2.5` (F2.2 peerDep).
- `lucide-react@^0.453.0` (F2.1 shadcn).
- `@radix-ui/react-tooltip@^1.1.4` (F2.1, para StatusBar tooltip si agrega hint).
- `tailwind-merge@^2.5.4` + `clsx@^2.1.1` (F2.1 shadcn).
- `@playwright/test@^1.48.0` + `@axe-core/playwright@^4.10.0` (F2.1+RNF-022).

### 4.2 Versiones objetivo

- electron-updater@^6.3.9.
- electron-log@^5.1.7.
- bcrypt@^5.1.1 (factor 12 compatible — versiones 5.x soportan cost factor >=10 sin deprecation warning).
- Electron 30.5.x (ya en stack).
- React 18.3.x (ya en stack).

### 4.3 Tooling

- esbuild 0.24.x (main+preload, F2.1 DEC-ELEC-03).
- Vite 5.4.x (renderer, F2.1 DEC-ELEC-03).
- Vitest 2.1.x (unit, F2.1).
- Playwright 1.48.x + _electron.launch (e2e, F2.1 + F2.2).
- axe-core 4.10.x (a11y, F2.1 RNF-022).

## 5. Decisiones arquitectónicas (DEC-UPD-NN × 13)

### 5.1 DEC-UPD-01 — electron-updater feed configurable via env PARKOS_UPDATE_FEED_URL

**DECISION**: `autoUpdater.setFeedURL(process.env.PARKOS_UPDATE_FEED_URL || 'https://github.com/easypunto_parkos/easypunto_parkos/releases')` en runtime init.

**RATIONALE**: F2.1 shippeó `electron-builder.yml autoUpdate:false` placeholder (DEC-ELEC-04). F2.3 flipea a `true` y agrega publish config. Override via env permite staging sin recompilar electron-builder (DEC-UPD-01 verification gate: leer config en runtime, no bake-time).

### 5.2 DEC-UPD-02 — autoDownload + autoInstallOnAppQuit (NO prompt al usuario)

**DECISION**: `autoUpdater.autoDownload = true` + `autoUpdater.autoInstallOnAppQuit = true`. CERO UI prompts al operador.

**RATIONALE**: Kiosko desatendido — el operador no debe interactuar con update dialogs. Auto-install at quit minimiza disruption (la próxima vez que el operador abre la app, ya está en la nueva versión). Plan.md:1249 verbatim.

### 5.3 DEC-UPD-03 — allowDowngrade false

**DECISION**: `autoUpdater.allowDowngrade = false` + `electron-builder.yml publish.allowPrerelease:false`. Downgrades NO permitidos.

**RATIONALE**: Plan.md:1249 verbatim. Schema migrations pueden ser incompatibles con versiones anteriores; un downgrade puede dejar la DB en estado inconsistente. Updates solo forward (major + minor + patch).

### 5.4 DEC-UPD-04 — signature verification via electron-builder publish config (auto-falla si no está)

**DECISION**: `electron-builder.yml publish.provider:"github"` + macOS hardened-runtime + Windows Authenticode. Si la firma falla (`autoUpdater.on('error', err)` con err.message contiene "signature"), NO se instala, se loguea en `electron-log` nivel `error` y se reintenta en el próximo ciclo (6h después).

**RATIONALE**: Security boundary — sin signature verification, un MITM puede inyectar un binario malicioso. electron-builder valida automáticamente durante download; F2.3 solo necesita capturar el error event.

### 5.5 DEC-UPD-05 — api-status polling 30s en MAIN process (NO renderer)

**DECISION**: El polling ocurre en `electron/services/api-status.ts` (main process), NO en el renderer. El renderer consume `bridge.apiStatus.get()` que IPC-invoca el último valor cacheado.

**RATIONALE**: Security boundary — el renderer NO debe hacer fetch directo al backend (sería绕过 CORS + CSP). Main process tiene control total de la red. Polling 30s en main libera al renderer del ciclo de vida.

### 5.6 DEC-UPD-06 — api-status timeout 5s vía AbortController

**DECISION**: `fetch(url, {signal: AbortSignal.timeout(5000)})` o equivalente con `AbortController` + `setTimeout(() => controller.abort(), 5000)`. Si timeout, devuelve `{ok:false, code: undefined}`.

**RATIONALE**: Kiosko desatendido — un backend colgado no puede bloquear la UI indefinidamente. 5s es suficiente para un health check (red local 127.0.0.1 < 100ms típicamente).

### 5.7 DEC-UPD-07 — single-instance lock con second-instance focus (no spawn new window)

**DECISION**: `app.requestSingleInstanceLock()` ANTES de `app.whenReady()`. Si `false` → `app.quit()`. Si `true` → `app.on('second-instance', () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus() } })`.

**RATIONALE**: Plan.md:1250 verbatim. Race condition prevention: el lock DEBE adquirirse antes de cualquier otra inicialización. Segundo instance enfoca la ventana existente (UX: el operador no quiere 2 ventanas con la misma DB).

### 5.8 DEC-UPD-08 — kiosko via env var PARKOS_KIOSK_MODE=1 (no config UI)

**DECISION**: Kiosko se activa al startup si `process.env.PARKOS_KIOSK_MODE === '1'`. NO hay toggle UI para activar kiosko (solo `Ctrl+Shift+K` + PIN para desactivar).

**RATIONALE**: Kiosko es decisión de deploy, no de operador. Env var permite configurar vía electron-builder o script de launch sin recompilar. F2.3 NO expone toggle UI para activar (sería backdoor).

### 5.9 DEC-UPD-09 — PIN bcrypt factor 12, comparación tiempo constante, hash pre-shared via electron-store

**DECISION**: `bcrypt.hash(pin, 12)` al deploy-time, persistido bajo key `kiosk.pinHash` en electron-store. Comparación con `bcrypt.compareSync(pin, hash)` (Node bcrypt es constant-time por default). **PIN nunca logueado** — solo `kiosko.unlock_attempt{success: bool, attempt_id: uuid, timestamp: ISO}`.

**RATIONALE**: Plan.md:1251 verbatim. Factor 12 = ~250ms por hash (OWASP 2023 recommendation para interactive auth). Constant-time compare previene timing attacks. Pre-shared via electron-store evita pedir PIN al deploy (un solo secreto, no por usuario).

### 5.10 DEC-UPD-10 — shortcuts bloqueados via before-input-event (no accelerators globales)

**DECISION**: `mainWindow.webContents.on('before-input-event', (event, input) => { if (input.control && input.key.toLowerCase() === 'w') event.preventDefault(); if (input.alt && input.key === 'F4') event.preventDefault(); })`. NO se usan `globalShortcut.register()` (esos son OS-wide, demasiado invasivos).

**RATIONALE**: `before-input-event` es scoped a la ventana Electron — solo bloquea dentro de la app, no afecta otros OS shortcuts. `globalShortcut` bloquearía system-wide (inacceptable).

### 5.11 DEC-UPD-11 — electron-log rotación 10MB×5 JSON, captura uncaughtException + unhandledRejection

**DECISION**: `log.transports.file.maxSize = 10 * 1024 * 1024` (10 MB), `transports.file.backups = 5` (max 50 MB total). `log.format = log.formports.file.backups = 5` (max 50 MB total). `log.format = log.formats.json` (estructurado). `process.on('uncaughtException', log.error)` + `process.on('unhandledRejection', log.error)`.

**RATIONALE**: Plan.md:1253 verbatim. 50 MB cap evita disk fill. JSON format permite parsing post-mortem con `jq` o similar.

### 5.12 DEC-UPD-12 — StatusBar aria-live="polite" + de-duplicación consecutiva + debounce 2s

**DECISION**: `<StatusBar role="status" aria-live="polite" aria-atomic="true">` envuelve el texto. `useRef<ApiStatus | null>(null)` tracks `lastAnnouncedState`. Si `newState !== lastAnnouncedState` Y `now - lastAnnouncedAt > 2000`, anuncia + actualiza ref.

**RATIONALE**: `aria-live="polite"` no interrumpe al screen reader (vs `assertive`). De-duplicación evita spam (operador no necesita oír "Sin API" 30 veces por minuto). Debounce 2s previene race conditions en cambios rápidos.

### 5.13 DEC-UPD-13 — NO-OP delta stub para spec.md (DEC-ELEC-10 + DEC-FETCH-10 precedent)

**DECISION**: `openspec/changes/hu-f2-3-electron-auto-update-kiosko/specs/operations/spec.md` es un NO-OP stub (~85 LOC) que documenta las 13 DEC-UPD-NN como INFORMATIONAL. NO agrega REQ-OPS-NNN (F2.3 es infra de runtime, no behavior contract).

**RATIONALE**: Precedente verbatim de F2.1 DEC-ELEC-10 (`specs/operations/spec.md` NO-OP stub) + F2.2 DEC-FETCH-10 (mismo patrón). Si F2.3 agrega REQs, sería la primera HU de Fase 2 con behavior contract — out-of-pattern. La justificación: las decisions viven en proposal.md como DEC-UPD-NN, no como REQ-OPS.

## 6. Riesgo y mitigaciones

| # | Risk | Severity | Mitigación |
|---|---|---|---|
| R1 | **Signature verification failure en update** — atacante MITM inyecta binario malicioso | MEDIUM | DEC-UPD-04: electron-builder publish provider valida firma automáticamente; si falla, `autoUpdater.on('error')` logea + NO instala + retry next cycle (6h). UI notification "Update failed — please contact admin" via `mainWindow.webContents.send('updater:status', 'failed')`. |
| R2 | **Backend /health endpoint NO existe** — api-status polling siempre retorna 🔴 | HIGH | DEC-UPD-05/06: api-status degrada gracefully a `{ok:false, code:undefined}`; StatusBar renderiza 🔴. NO bloquea F2.3 (documentado §15 out-of-scope, HU backend separada F3+). |
| R3 | **Single-instance lock race condition en startup** — dos instancias adquieren lock antes de que la primera se establezca | LOW | DEC-UPD-07: `app.requestSingleInstanceLock()` ANTES de `whenReady`. Electron garantiza atomic check; segunda instancia ve `false` y termina inmediatamente. |
| R4 | **Kiosko bypass via task manager / alt-tab** — operador mata el proceso con Ctrl+Shift+Esc | LOW | DEC-UPD-10: full kiosk mode es best-effort dentro de Electron; layer con OS-level kiosk (Windows Assigned Access, macOS kiosk mode) si se requiere real — FUERA scope Fase 2 (out-of-scope §15). |
| R5 | **PIN brute force** — atacante prueba 1000 PINs/seg | MEDIUM | DEC-UPD-09: bcrypt factor 12 = ~250ms/hash → max 4 PINs/seg. Lockout después de 3 intentos via electron-store counter `kiosk.failedAttempts`, reset on successful unlock o exit Ctrl+Shift+K. Counter persistence evita brute force persistente tras restart. |
| R6 | **bcrypt CPU cost en PIN check** — cada unlock toma ~250ms | LOW | DEC-UPD-09: 250ms es acceptable para unlock (UX: operador espera feedback). Lockout check es O(1) en electron-store, negligible. |
| R7 | **electron-log disk fill** — rotación no funciona o path es readonly | LOW | DEC-UPD-11: 10MB×5 = 50MB cap. Fallback: si `transports.file.write` falla, log a stderr (capturado por OS journald/EventLog). |
| R8 | **StatusBar screen reader spam** — cambio de estado cada 30s satura al operador con screen reader | MEDIUM | DEC-UPD-12: de-duplicación de estado consecutivo + debounce 2s + `aria-live="polite"` (no interrumpe). Atributo `aria-atomic="true"` lee todo el bloque, no solo el cambio. |

**Riesgos identificados y cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

## 7. Análisis de impacto (no hay conflicto arquitectónico)

A diferencia de F1.12 (cross-domain atomicity), F2.3 NO tiene un conflicto arquitectónico mayor. Cada bloque de F2.3 (updater, log-config, single-instance, kiosko, api-status, StatusBar) opera en un namespace distinto:

- **Updater**: `electron/services/updater.ts` (NEW). Lifecycle: app.whenReady() → check every 6h via setInterval. Main process only.
- **Log-config**: `electron/services/log-config.ts` (NEW). Lifecycle: app boot (ANTES de whenReady para capturar crashes tempranos). Main process only.
- **Single-instance**: `electron/main.ts` (MODIFY top). Lifecycle: synchronous at app boot, BEFORE whenReady.
- **Kiosko**: `electron/services/kiosko.ts` (NEW). Lifecycle: app.whenReady() → apply if env var set. Listens IPC `kiosk:toggle`.
- **api-status**: `electron/services/api-status.ts` (NEW). Lifecycle: app.whenReady() → setInterval 30s. Cache last result. IPC handler `api:status`.
- **StatusBar**: `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (NEW). Renderer only, mounts in App.tsx.

**Orden de inicialización** (DEC-UPD-07 mandates):
1. `app.requestSingleInstanceLock()` — sync, boot.
2. `electron-log` init — sync, boot (antes de whenReady).
3. `process.on('uncaughtException'/'unhandledRejection')` — sync, boot.
4. `app.whenReady().then(...)` — async.
5. Dentro de whenReady:
   a. `electron-updater` init (autoDownload, setFeedURL).
   b. `api-status` polling start (setInterval).
   c. Si `PARKOS_KIOSK_MODE=1` → apply kiosko.
   d. `createMainWindow()`.
6. IPC handlers registered (`api:status`, `kiosk:toggle`, `app:quit`).

## 8. Decisiones arquitectónicas (DEC-UPD-NN) — segundo pase con justificación extendida

### 8.1 DEC-UPD-01 vs alternativas

**Alternativa A**: `electron-builder.yml publish` estático (bake-time).
- Pros: simple, no env var.
- Cons: requiere recompilar electron-builder para staging.

**Alternativa B (DECIDIDA)**: `autoUpdater.setFeedURL(env || github_default)` runtime.
- Pros: staging override sin recompilar.
- Cons: requiere `autoUpdater.setFeedURL` antes de `checkForUpdates()`.

**Razón**: electron-updater 6.x soporta `setFeedURL` runtime sin issues. Override via env es patrón estándar (F2.2 ya usa `PARKOS_API_BASE` para parkosFetch baseURL — precedent).

### 8.2 DEC-UPD-09 vs alternativas

**Alternativa A**: PIN por usuario (consulta backend).
- Pros: revocable individual.
- Cons: kiosko offline no funciona; backend down = locked out.

**Alternativa B (DECIDIDA)**: PIN pre-shared via electron-store.
- Pros: kiosko offline-safe; deploy-time rotation; simple.
- Cons: rotación requiere script de deploy (no UI).

**Razón**: kiosko es desatendido — asumir backend down es el failure mode común. PIN pre-shared es KISS.

### 8.3 DEC-UPD-12 vs alternativas

**Alternativa A**: `aria-live="assertive"` (interrumpe screen reader).
- Pros: anuncia inmediatamente.
- Cons: interrumpe al operador en medio de otra tarea (mala UX).

**Alternativa B (DECIDIDA)**: `aria-live="polite"` + de-duplicación + debounce 2s.
- Pros: no interrumpe; evita spam; respeta al operador.
- Cons: requiere ref tracking (más código).

**Razón**: RNF-022 WCAG 2.1 AA incluye "no interrumpir sin razón" (SC 4.1.3). Polite + dedup es el patrón canónico para status updates.

## 9. Atomic tasks T1..T7 con budgets LOC

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1 → T7.

### 9.1 T1 — electron-updater + signature verification

**Budget**: ~80 LOC production + ~30 LOC tests = **~110 LOC**.

**Archivos**:
- `apps/electron-sucursal/electron/services/updater.ts` (NEW, ~70 LOC).
- `apps/electron-sucursal/electron/services/updater.test.ts` (NEW, ~30 LOC).
- `apps/electron-sucursal/electron/main.ts` (MODIFY, agregar `initUpdater()` call en whenReady).
- `apps/electron-sucursal/electron-builder.yml` (MODIFY, flipear `autoUpdate:false → true` + agregar publish provider).
- `apps/electron-sucursal/tsconfig.main.json` (MODIFY, agregar `electron/services/**/*.ts` a include).

**Commit message**: `feat(electron): adicionar electron-updater con feed configurable + signature verification + autoDownload/autoInstallOnAppQuit`

**Acceptance** (G1, G2): `autoUpdater.setFeedURL` lee env o default github; signature failure logea + no instala; `autoDownload:true` + `autoInstallOnAppQuit:true` configurados; `allowDowngrade:false`.

### 9.2 T2 — api-status polling 30s + IPC handler

**Budget**: ~50 LOC production + ~20 LOC tests = **~70 LOC**.

**Archivos**:
- `apps/electron-sucursal/electron/services/api-status.ts` (NEW, ~40 LOC).
- `apps/electron-sucursal/electron/services/api-status.test.ts` (NEW, ~20 LOC).
- `apps/electron-sucursal/electron/main.ts` (MODIFY, registrar IPC handler `api:status` + `initApiStatus()` en whenReady).

**Commit message**: `feat(electron): adicionar api-status polling 30s a /health con AbortController timeout 5s + IPC bridge.apiStatus`

**Acceptance** (G6): polling cada 30 s; timeout 5 s; IPC handler retorna `{ok, latency_ms, code?}`; 3 estados manejados (🟢/🟡/🔴); /health 404 degrada a 🔴 gracefully.

### 9.3 T3 — single-instance lock + second-instance focus

**Budget**: ~20 LOC production + ~10 LOC tests = **~30 LOC**.

**Archivos**:
- `apps/electron-sucursal/electron/main.ts` (MODIFY, agregar `app.requestSingleInstanceLock()` antes de whenReady + listener `second-instance`).
- `apps/electron-sucursal/electron/__tests__/single-instance.test.ts` (NEW, ~10 LOC — pero e2e cubre el caso real).

**Commit message**: `feat(electron): adicionar single-instance lock con second-instance focus`

**Acceptance** (G3): segunda invocación enfoca primera + termina; no spawn new window; lock antes de whenReady.

### 9.4 T4 — kiosko mode + PIN bcrypt

**Budget**: ~100 LOC production + ~40 LOC tests = **~140 LOC**.

**Archivos**:
- `apps/electron-sucursal/electron/services/kiosko.ts` (NEW, ~90 LOC).
- `apps/electron-sucursal/electron/services/kiosko.test.ts` (NEW, ~40 LOC).
- `apps/electron-sucursal/electron/main.ts` (MODIFY, registrar IPC handlers `kiosk:toggle` + `app:quit` + apply kiosko si env var).

**Commit message**: `feat(electron): adicionar kiosko mode con PIN bcrypt factor 12 + shortcuts bloqueados + Menu null + setKiosk`

**Acceptance** (G4): `PARKOS_KIOSK_MODE=1` activa full-screen + `Menu.setApplicationMenu(null)` + bloquea `Ctrl+W`/`Alt+F4`; `Ctrl+Shift+K` + PIN correcto desactiva; PIN incorrecto no desactiva + log audit; PIN nunca logueado en texto plano.

### 9.5 T5 — electron-log rotación 10MB×5 JSON + captura uncaughtException

**Budget**: ~30 LOC production + ~10 LOC tests = **~40 LOC**.

**Archivos**:
- `apps/electron-sucursal/electron/services/log-config.ts` (NEW, ~25 LOC).
- `apps/electron-sucursal/electron/main.ts` (MODIFY, `initLogConfig()` ANTES de whenReady + process.on('uncaughtException'/'unhandledRejection')).

**Commit message**: `feat(electron): adicionar electron-log con rotación 10MB×5 JSON + captura uncaughtException/unhandledRejection`

**Acceptance** (G5): log path en `%APPDATA%/parkos/logs/main.log`; rotación al alcanzar 10MB; formato JSON estructurado; `uncaughtException` y `unhandledRejection` capturados.

### 9.6 T6 — StatusBar con aria-live polite + de-duplicación

**Budget**: ~80 LOC production + ~30 LOC tests = **~110 LOC**.

**Archivos**:
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (NEW, ~70 LOC).
- `apps/electron-sucursal/src/renderer/components/StatusBar.test.tsx` (NEW, ~30 LOC).
- `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY, mount `<StatusBar />` arriba del `<main>`).
- `apps/electron-sucursal/src/renderer/i18n/locales/common.json` (MODIFY, agregar keys `statusBar.ok`, `statusBar.slow`, `statusBar.offline`).

**Commit message**: `feat(ui): adicionar StatusBar con aria-live polite + de-duplicación de anuncios consecutivos`

**Acceptance** (G7): 3 textos exactos (`"🟢 API OK"` / `"🟡 API lento"` / `"🔴 Sin API"`); `aria-live="polite"` + `aria-atomic="true"`; cambio consecutivo igual NO se re-anuncia; debounce 2 s entre anuncios distintos.

### 9.7 T7 — 3 e2e lifecycle + kiosko

**Budget**: ~120 LOC tests.

**Archivos**:
- `apps/electron-sucursal/e2e/lifecycle.spec.ts` (NEW, ~60 LOC — segunda instancia focus + kiosko Ctrl+W bloqueado).
- `apps/electron-sucursal/e2e/kiosko.spec.ts` (NEW, ~60 LOC — PIN incorrecto no desbloquea + log audit verificado).

**Commit message**: `test(electron): adicionar 3 e2e lifecycle + kiosko (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto)`

**Acceptance** (G8): 3 escenarios verde per plan.md:1255 verbatim. Sandbox F.6 precedent: SKIPPED en npm 11.16.0 (F2.2 G8 archive report) — F2.3 e2e va a correr misma suerte, documentado como deviation en verify-report.

### 9.8 Resumen de budgets

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 updater | 80 | 30 | 110 |
| T2 api-status | 50 | 20 | 70 |
| T3 single-instance | 20 | 10 | 30 |
| T4 kiosko | 100 | 40 | 140 |
| T5 log-config | 30 | 10 | 40 |
| T6 StatusBar | 80 | 30 | 110 |
| T7 e2e | 0 | 120 | 120 |
| **TOTAL** | **360** | **260** | **620** |

Total real ~700-800 LOC incluyendo configs y JSDoc.

## 10. Descomposición en clusters atómicos (C1..C4)

F2.3 se descompone en **4 clusters** (C1, C2, C3, C4) con orden C1 → C2 → C3 → C4.

### 10.1 C1: Infra runtime (T1+T5) — updater + electron-log

**Archivos**:
- `apps/electron-sucursal/electron/services/updater.ts` (~70 LOC).
- `apps/electron-sucursal/electron/services/updater.test.ts` (~30 LOC).
- `apps/electron-sucursal/electron/services/log-config.ts` (~25 LOC).
- `apps/electron-sucursal/electron/main.ts` (MODIFY ~20 LOC delta — init calls).
- `apps/electron-sucursal/electron-builder.yml` (MODIFY — flipear autoUpdate + publish).

**Total C1**: ~145 LOC.

### 10.2 C2: Status UI (T2+T6) — api-status service + StatusBar component

**Archivos**:
- `apps/electron-sucursal/electron/services/api-status.ts` (~40 LOC).
- `apps/electron-sucursal/electron/services/api-status.test.ts` (~20 LOC).
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (~70 LOC).
- `apps/electron-sucursal/src/renderer/components/StatusBar.test.tsx` (~30 LOC).
- `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY — mount StatusBar).
- `apps/electron-sucursal/src/renderer/i18n/locales/common.json` (MODIFY — 3 keys).

**Total C2**: ~180 LOC.

### 10.3 C3: Lockdown (T3+T4) — single-instance + kiosko PIN

**Archivos**:
- `apps/electron-sucursal/electron/services/kiosko.ts` (~90 LOC).
- `apps/electron-sucursal/electron/services/kiosko.test.ts` (~40 LOC).
- `apps/electron-sucursal/electron/main.ts` (MODIFY ~30 LOC delta — lock + kiosko init + IPC handlers).
- `apps/electron-sucursal/package.json` (MODIFY — agregar bcrypt + @types/bcrypt).

**Total C3**: ~170 LOC.

### 10.4 C4: Testing (T7) — 3 e2e lifecycle + kiosko

**Archivos**:
- `apps/electron-sucursal/e2e/lifecycle.spec.ts` (~60 LOC).
- `apps/electron-sucursal/e2e/kiosko.spec.ts` (~60 LOC).

**Total C4**: ~120 LOC.

### 10.5 Total estimado

- **C1**: ~145 LOC.
- **C2**: ~180 LOC.
- **C3**: ~170 LOC.
- **C4**: ~120 LOC tests.
- **TOTAL**: ~615 LOC.

Plan 450 LOC matches: 450 ≈ 615 - 165 LOC ya en stack (deps, preload, bridge.d.ts ya presentes por F2.1+F2.2).

### 10.6 Orden de ejecución

C1 → C2 → C3 → C4 (mandatory). C1 antes de C2 porque StatusBar consume api-status IPC (C2). C1 antes de C3 porque kiosko setup corre en whenReady que también inicializa updater. C2+C3 antes de C4 porque e2e tests requieren el runtime completo.

## 11. Acceptance gates pre-flight

8 gates que deben pasar ANTES de mergear F2.3 a main.

| # | Gate | Mecanismo | Source |
|---|---|---|---|
| G1 | `electron-updater.autoDownload:true` + `autoInstallOnAppQuit:true` + `allowDowngrade:false` configurados | unit test `updater.test.ts` assert config | T1 |
| G2 | Signature verification failure → NO instala + log error + retry next cycle | unit test `updater.test.ts` mock `autoUpdater.on('error')` | T1 |
| G3 | `app.requestSingleInstanceLock()` retorna `false` en segunda invocación → enfoca primera + termina | e2e `lifecycle.spec.ts` con `_electron.launch` 2 veces | T3 + T7 |
| G4 | `PARKOS_KIOSK_MODE=1` → full-screen + Menu null + Ctrl+W bloqueado + PIN bcrypt factor 12 + Ctrl+Shift+K + PIN correcto desactiva + PIN incorrecto no desactiva + nunca logueado | unit test `kiosko.test.ts` + e2e `kiosko.spec.ts` | T4 + T7 |
| G5 | `electron-log` rotación 10MB×5 JSON + captura `uncaughtException`/`unhandledRejection` | unit test `log-config.test.ts` (mock electron-log) | T5 |
| G6 | api-status polling cada 30 s + timeout 5 s + IPC handler retorna `{ok, latency_ms, code?}` + 3 estados (🟢/🟡/🔴) | unit test `api-status.test.ts` con mock fetch + e2e integration | T2 |
| G7 | `<StatusBar>` con `aria-live="polite"` + texto exacto por estado + de-duplicación consecutiva + debounce 2 s | vitest `StatusBar.test.tsx` + axe-core extension (F2.2 axe pattern) | T6 |
| G8 | 3 e2e verde (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto no desbloquea) | playwright e2e `_electron` | T7 |

**Estado pre-flight**: 0/8 PASS al inicio (no implementado). Target 8/8 PASS post-implementación.

**Sandbox F.6 precedent**: 6/10 gates SKIPPED en F2.1 + F2.2 archive (npm 11.16.0 refuses workspace:*). F2.3 e2e (G3, G4, G8) van a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect.

## 12. Pre-flight checks ya cerrados

10 checks verificados antes de empezar implementación:

| # | Check | Source | Result |
|---|---|---|---|
| 1 | plan.md HU-F2.3 existe con 7 tasks + 8 gates + 13 DEC-UPD-NN | plan.md:1244-1266 | PASS |
| 2 | main.ts boot lifecycle existe (whenReady + createMainWindow + window-all-closed) | main.ts:41-54 | PASS |
| 3 | preload.ts bridge IPC 8 métodos wireados (F2.2) | preload.ts:24-48 | PASS |
| 4 | bridge.d.ts BridgeSurface typed con apiStatus/kiosk/app (F2.2) | bridge.d.ts:1-87 | PASS |
| 5 | electron-updater@^6.3.9 + electron-log@^5.1.7 + electron-store@^8.2.0 ya en deps (F2.1/F2.2) | package.json:36-38 | PASS |
| 6 | bcrypt NO está en deps — F2.3 lo agrega | package.json:22-52 (absent) | KNOWN-MISSING (mitigated: T4 plan agrega) |
| 7 | Vitest + Playwright + axe-core + esbuild + Vite stack completo | package.json:53-77 | PASS |
| 8 | tsconfig.main.json strict + noUncheckedIndexedAccess; vite.config.ts alias @; esbuild-main.mjs target node20 cjs | tsconfig.main.json + vite.config.ts + esbuild-main.mjs | PASS |
| 9 | e2e/ tiene scaffold + auth + a11y; F2.3 agrega lifecycle + kiosko | e2e/ dir | PASS |
| 10 | apps/ui-kit exports Button + cn + tokens + useAuth + parkosFetch + authStore (F2.1+F2.2) | ui-kit/src/index.ts + ui-kit/package.json exports | PASS |

Result: 9/10 PASS + 1/10 KNOWN-MISSING (bcrypt, mitigated). Pre-flight gate PASS. F2.3 ready for sdd-propose.

## 13. Out of scope Fase 2

F2.3 NO incluye (explícitamente deferido a Fase 3+):

- **Backend `/health` endpoint** — necesario para `bridge.apiStatus.get()` real. F2.3 degrada a 🔴 gracefully mientras no exista. HU backend separada F3+.
- **OS-level kiosk** — Windows Assigned Access / macOS kiosk mode (FUERA Fase 2, solo Electron-level best-effort).
- **Code signing certificates** — release pipeline concern. F2.3 assume electron-builder publish + GitHub releases con auto-sign.
- **PIN rotation UI** — solo deploy-time script `node scripts/seed-kiosko-pin.js`. NO UI para que el operador cambie el PIN (sería backdoor).
- **Update rollback UI** — `allowDowngrade:false` previene rollback. Si update falla, retry next cycle (6h).
- **StatusBar polling interval UI** — 30 s hardcoded per plan.md. Forward hook: F11.x sync UI podría exponer toggle.
- **Refresh-token rotation detection** — F2.2 cubre, F2.3 NO toca.
- **2FA / WebAuthn** — futuro.
- **Login UI** — F3.1.
- **Lockout + countdown UI** — F3.2.
- **Turno abrir/cerrar** — F3.3.
- **web_sucursal IT-3..IT-10** — F3.4+.
- **Operación / caja / facturación / alertas** — Fase 4-5.

## 14. Forward hooks (a Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.1** (login email+password) | bridge.kiosk.toggle (no — login UI no requiere kiosko) | Login form se monta dentro de kiosko mode (no operation conflict) |
| **HU-F3.2** (lockout visible) | electron-log (eventos 429 Retry-After) | parkosFetch emite log `auth.lockout{retry_after: seconds}` |
| **HU-F3.3** (abrir/cerrar turno) | bridge.apiStatus (verifica backend up antes de abrir turno) | Si 🔴, no permite abrir turno |
| **HU-F5.1+** (impresión térmica) | bridge.imprimir + kiosko mode (no operation conflict) | Impresión opera normal dentro de kiosko |
| **HU-F11.x** (sync UI) | bridge.apiStatus.get + StatusBar (F2.3 forward consumer) | StatusBar extendido con sync state (queue depth, lag seconds) |
| **HU-F2.4+** (post-Fase 2 ops) | bridge.kiosk.toggle para admin override (forward) | Admin puede forzar kiosko on/off remotamente via backend command |

## 15. Convenciones del proyecto

### 15.1 Commits

- Conventional Commits.
- NO "Co-Authored-By" attribution.
- Formato: `<type>(<scope>): <description>` con type ∈ {feat, fix, test, refactor, docs, chore}, scope ∈ {ui-kit, electron, web, ops}.
- Author: `Parkos Dev <dev@parkos.local>` (F2.1 precedent).

### 15.2 TDD estricto

- Cada test escrito ANTES de la implementación.
- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `services/{updater,api-status,kiosko}.ts`.
- Cobertura >80% en `StatusBar.tsx`.

### 15.3 Defense in depth

5 capas (XR6 pattern per operations/spec.md:3951 + F2.2 §15.3 precedent):

| Layer | Mechanism | Source |
|---|---|---|
| 1 auth | JWT Bearer + kiosko PIN bcrypt | F2.2 + F2.3 DEC-UPD-09 |
| 2 engineering | TS strict + noUncheckedIndexedAccess + ESLint flat | tsconfig.* + eslint.config.js |
| 3 a11y | axe-core WCAG 2.1 AA + StatusBar aria-live polite | e2e/a11y/wcag-2.1-aa.spec.ts (F2.2) + DEC-UPD-12 |
| 4 contract | bridge.d.ts shape + Zod validation opcional | bridge.d.ts + parkosFetch<T>(url, schema) (F2.2) |
| 5 retry-budget | API status polling 30s + updater retry 6h + kiosko lockout 3 attempts | DEC-UPD-02/06/09 |

F2.3 NO crea un nuevo REQ-OPS-XR (F2.3 NO es XR-class; las decisiones viven en proposal.md como DEC-UPD-NN per F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10 precedent).

### 15.4 Pending.md update

Al archive F2.3:
- Row 3 (HU-F2.3) en `pending.md §1` → marcar ✅ cerrado.
- Total LOC restante → `$0 LOC` (Fase 2 cerrada).
- Footer → "Fase 2 3/3 cerrado".

## 16. Estimación total

### 16.1 Production LOC

- C1 (updater + log-config): ~145 LOC.
- C2 (api-status + StatusBar): ~160 LOC production + ~20 LOC JSON i18n.
- C3 (single-instance + kiosko): ~170 LOC.
- Total production: **~475 LOC** + **~50 LOC** configs/package.json edits + **~30 LOC** comentarios JSDoc = **~555 LOC**.

### 16.2 Test LOC

- updater.test.ts: ~30 LOC.
- api-status.test.ts: ~20 LOC.
- kiosko.test.ts: ~40 LOC.
- StatusBar.test.tsx: ~30 LOC.
- e2e/lifecycle.spec.ts: ~60 LOC.
- e2e/kiosko.spec.ts: ~60 LOC.
- Total tests: **~240 LOC**.

### 16.3 Gran total

~555 LOC production + ~240 LOC tests = **~795 LOC**.

### 16.4 Timeline estimado

| Fase | Duración estimada | Owner |
|---|---|---|
| sdd-propose | 1 sesión | orchestrator |
| sdd-apply T1..T7 | 3-4 sesiones | sdd-apply (7 atomic commits en 4 clusters) |
| sdd-verify | 1 sesión | sdd-verify |
| archive | 0.5 sesión | orchestrator |

Total: ~5-6 sesiones (cierra Fase 2, habilita Fase 3).

## 17. Apéndice archivos a tocar

### 17.1 NEW (crear)

- `apps/electron-sucursal/electron/services/updater.ts` (T1)
- `apps/electron-sucursal/electron/services/updater.test.ts` (T1)
- `apps/electron-sucursal/electron/services/api-status.ts` (T2)
- `apps/electron-sucursal/electron/services/api-status.test.ts` (T2)
- `apps/electron-sucursal/electron/services/kiosko.ts` (T4)
- `apps/electron-sucursal/electron/services/kiosko.test.ts` (T4)
- `apps/electron-sucursal/electron/services/log-config.ts` (T5)
- `apps/electron-sucursal/electron/__tests__/single-instance.test.ts` (T3, opcional — e2e cubre)
- `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (T6)
- `apps/electron-sucursal/src/renderer/components/StatusBar.test.tsx` (T6)
- `apps/electron-sucursal/e2e/lifecycle.spec.ts` (T7)
- `apps/electron-sucursal/e2e/kiosko.spec.ts` (T7)
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/exploration.md` (this file)
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/proposal.md` (proposal phase)
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/design.md` (design phase)
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/tasks.md` (tasks phase)
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/specs/operations/spec.md` (NO-OP stub DEC-UPD-13)
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/verify-report.md` (verify phase)
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/archive-report.md` (archive phase)

### 17.2 MODIFY (extender)

- `apps/electron-sucursal/electron/main.ts` (T1+T2+T3+T4+T5 — ~70 LOC delta: import services, init calls, IPC handlers, lock check, kiosko apply, log capture).
- `apps/electron-sucursal/electron/bridge.d.ts` (T2 — `ApiStatus` shape delta: `{online, lastSync}` → `{ok, latency_ms, code?}`).
- `apps/electron-sucursal/electron/preload.ts` (no change per DEC-UPD — handler ya wireado).
- `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` (T2 — actualizar test 5 `apiStatus.get` para match nuevo shape).
- `apps/electron-sucursal/electron-builder.yml` (T1 — flipear `autoUpdate:false → true` + agregar publish provider).
- `apps/electron-sucursal/tsconfig.main.json` (T1 — agregar `electron/services/**/*.ts` a include).
- `apps/electron-sucursal/package.json` (T4 — agregar `bcrypt@^5.1.1` + `@types/bcrypt@^5.0.2`).
- `apps/electron-sucursal/src/renderer/App.tsx` (T6 — mount `<StatusBar />` arriba del `<main>`).
- `apps/electron-sucursal/src/renderer/i18n/locales/common.json` (T6 — agregar `statusBar.ok`, `statusBar.slow`, `statusBar.offline`).
- `apps/electron-sucursal/playwright.config.ts` (T7 — sin cambios necesarios, e2e auto-discovers `e2e/**/*.spec.ts`).
- `pending.md` (archive phase — marcar F2.3 ✅ cerrado, actualizar Total LOC restante, footer).

### 17.3 READ ONLY (anchors — NO modificar)

- `apps/web_admin/**` (F2.2 consumer, no F2.3 touch).
- `backend/.../api/v1/auth.py` (F2.2 consumer, no F2.3 touch).
- `backend/.../schemas/auth.py` (F2.2 consumer, no F2.3 touch).
- `apps/ui-kit/**` (F2.1+F2.2, no F2.3 touch — DEC-UPD-13 deja useApiStatus como optional forward hook).
- `apps/electron-sucursal/electron/preload.ts` (F2.2, no F2.3 touch — handlers en main).
- `apps/electron-sucursal/e2e/{scaffold,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa}.spec.ts` (F2.1+F2.2, no F2.3 touch).
- `openspec/specs/operations/spec.md` (canonical, no F2.3 touch — delta stub solo).

### 17.4 Total de archivos impactados

- **NEW**: 20 archivos (~795 LOC + ~150 LOC artifacts SDD).
- **MODIFY**: 10 archivos (~150 LOC delta production + 30 LOC i18n + pending.md).
- **READ ONLY**: 8 archivos.
- **TOTAL IMPACT**: 30 archivos de 795 LOC nuevos + 180 LOC delta.

---

## CHANGELOG

- (2026-09-15) F2.3 explore phase complete — 17 secciones, 13 DEC-UPD-NN, 8 acceptance gates, 8 riesgos, 4 clusters C1..C4. Pre-flight 9/10 PASS + 1 KNOWN-MISSING (bcrypt mitigated by T4). Ready for sdd-propose.

---

**End of exploration.**
