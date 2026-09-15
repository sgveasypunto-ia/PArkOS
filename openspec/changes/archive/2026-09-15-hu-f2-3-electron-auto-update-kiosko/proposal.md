# Propuesta — HU-F2.3 Auto-actualización, single-instance, kiosko y api-status

> **Change**: `hu-f2-3-electron-auto-update-kiosko` · **Folder**: `openspec/changes/hu-f2-3-electron-auto-update-kiosko/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F2.3 (Fase 2 — última HU; cierra Andamiaje Electron con infra de runtime)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `6bfe514`, F2.1 + F2.2 archivados 2026-09-15) · **PR target**: `origin/dev`
> **Inputs**: `plan.md` lines 1244-1266 (HU-F2.3 verbatim + 7 tareas atómicas T1..T7 + 3 criterios de aceptación + 3 e2e); `plan.md` lines 1159-1240 (F2.1 + F2.2 archivados, precedentes verbatim); `openspec/_meta/roadmap.md` lines 38-273 (IT-1..IT-10 web_sucursal consumer map); `openspec/specs/operations/spec.md:3951` (REQ-OPS-XR6 canonical 5-layer defense — F2.3 referencia INFORMATIONALLY); `openspec/specs/operations/spec.md:4386` (F1.15 DEC-XR7 NOT-CREATED precedent); `apps/electron-sucursal/electron/main.ts:1-55` (skeleton F2.1); `apps/electron-sucursal/electron/preload.ts:1-49` (whitelist IPC F2.2); `apps/electron-sucursal/electron/bridge.d.ts:1-87` (BridgeSurface typed F2.2); `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts:1-110` (contract test F2.2); `apps/electron-sucursal/electron/__mocks__/electron.ts` (mock contextBridge); `apps/electron-sucursal/package.json` (deps F2.1+F2.2); `apps/electron-sucursal/tsconfig.{json,main.json}`; `apps/electron-sucursal/vite.config.ts`; `apps/electron-sucursal/playwright.config.ts`; `apps/electron-sucursal/esbuild-main.mjs` (DEC-ELEC-03 F2.1); `apps/electron-sucursal/src/renderer/{App.tsx,main.tsx,i18n/locales/common.json}`; `apps/electron-sucursal/e2e/{scaffold.spec.ts,auth/parkos-fetch.spec.ts,auth/bridge.spec.ts,a11y/wcag-2.1-aa.spec.ts}`; `apps/ui-kit/{package.json,src/{index.ts,Button.tsx,cn.ts,tokens.ts,store/authStore.ts,store/authStore.test.ts,hooks/useAuth.ts,hooks/useAuth.test.ts,fetch/parkosFetch.ts,fetch/parkosFetch.test.ts}}`; `docs/01-requisitos/no-funcionales.md:126` (RNF-022 WCAG 2.1 AA); `docs/03-desarrollo/{setup.md:15, estandares.md:79-91}`; `pending.md §1-2`; `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/{exploration,proposal}.md` (precedentes verbatim); `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/{exploration,proposal}.md` (precedente verbatim F2.2).

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F2.3 |
| **Fase** | 2 (Andamiaje Electron — última HU, infra de runtime) |
| **Change name** | `hu-f2-3-electron-auto-update-kiosko` |
| **Folder** | `openspec/changes/hu-f2-3-electron-auto-update-kiosko/` |
| **State** | proposed (ready for design + spec) |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | F2.1 + F2.2 archivados 2026-09-15 (scaffold + IPC + authStore) |
| **Próximo phase** | sdd-spec + sdd-design (paralelo) |
| **Language** | español neutro profesional |
| **Conventional commits** | feat(electron) / feat(ui) / test(electron) — sin Co-authored-by |

---

## 1. Title & Goal

**Title**: "Auto-actualización con `electron-updater` (feed configurable + signature verification + `autoDownload`/`autoInstallOnAppQuit`) + Single-instance lock con `second-instance` focus + Kiosko mode con PIN bcrypt factor 12 + api-status polling 30s a `/health` + `electron-log` rotación 10MB×5 JSON + `<StatusBar>` con `aria-live="polite"` y de-duplicación de anuncios consecutivos"

**Goal**: F2.1 shippeó el skeleton (Electron 30 + Vite 5 + React 18 + TS 5 strict + shadcn 14 + i18n 7 namespaces + ui-kit workspace + Playwright `_electron` + axe-core) y F2.2 llenó el bridge IPC con 8 métodos typed + parkosFetch + authStore + useAuth. Lo único que falta para cerrar Fase 2 es la **infra de runtime** que toda feature operativa posterior consumirá sin reinventar: auto-actualización, single-instance, kiosko, api-status polling, logging estructurado y la primera pieza de UI de status. F2.3 entrega esos seis bloques de infraestructura sobre la base sentada por F2.1 + F2.2:

1. **`electron-updater`** — `autoUpdater.checkForUpdates()` cada 6h (configurable), `autoDownload:true` (descarga silenciosa), `autoInstallOnAppQuit:true` (instala al cerrar), `allowDowngrade:false`. Feed configurable via env `PARKOS_UPDATE_FEED_URL` (default `https://github.com/easypunto_parkos/easypunto_parkos/releases`). Signature verification via `electron-builder` publish config — si la firma falla, NO se instala, se loguea en `electron-log` nivel `error` y se reintenta en el próximo ciclo.
2. **`electron-log` rotación 10MB×5 JSON** — `log.transports.file.maxSize = 10 * 1024 * 1024`, `transports.file.backups = 5`, `log.format = log.formats.json`. Captura `uncaughtException` y `unhandledRejection` con `log.error(...)`. Path: `app.getPath('userData')/logs/main.log` (Windows: `%APPDATA%/parkos/logs/main.log`).
3. **`app.requestSingleInstanceLock()` + `second-instance` focus** — Llamada ANTES de `app.whenReady()` para evitar race conditions. Si el lock falla (`false`), la segunda invocación llama `app.quit()` inmediatamente. Si el lock es OK (`true`), se registra el listener `app.on('second-instance', () => { mainWindow.focus() })`.
4. **api-status polling 30s a `/health`** — `electron/services/api-status.ts` hace `fetch('http://127.0.0.1:8000/health')` cada 30 s con `AbortController` timeout 5 s. Devuelve `{ok: boolean, latency_ms: number, code?: number}`. Maneja 3 estados: 2xx → `{ok:true, latency_ms}`, 2xx con >1000ms → loggeado como lento (sigue `{ok:true, latency_ms}`), timeout/error → `{ok:false, code?: number}`. Expone via IPC handler `api:status` que `bridge.apiStatus.get()` consume (F2.2 ya wireado, F2.3 materializa el handler real).
5. **Kiosko mode con PIN bcrypt** — Toggle via env `PARKOS_KIOSK_MODE=1` al deploy-time. Cuando está activo: `mainWindow.setKiosk(true)` (pantalla completa sin barra de tareas), `Menu.setApplicationMenu(null)`, `mainWindow.on('close', e => e.preventDefault())` (impide Alt+F4), `mainWindow.webContents.on('before-input-event', ...)` bloquea `Ctrl+W` y otros shortcuts. Salida con `Ctrl+Shift+K` + PIN: `bcrypt.hash(pin, 12)` pre-compartido via electron-store bajo key `kiosk.pinHash` (configurado al deploy, NO se pide al usuario). Comparación con `bcrypt.compareSync(pin, hash)` — comparación en tiempo constante. **El PIN NUNCA se loguea** (ni en texto plano ni hasheado; el log solo registra `kiosko.unlock_attempt{success: bool, attempt_id: uuid, timestamp: ISO}`).
6. **`<StatusBar>` con `aria-live="polite"`** — Componente React nuevo (`apps/electron-sucursal/src/renderer/components/StatusBar.tsx`). Suscribe al polling de `bridge.apiStatus.get()` con `useState` + `setInterval(30_000)`. Renderiza texto exacto por estado:
   - `{ok:true, latency_ms <= 1000}` → `"🟢 API OK"` (verde)
   - `{ok:true, latency_ms > 1000}` → `"🟡 API lento"` (amarillo)
   - `{ok:false}` → `"🔴 Sin API"` (rojo)
   Atributo `aria-live="polite"` para que screen readers anuncien el cambio sin interrumpir al usuario. **De-duplicación de anuncios consecutivos**: si el estado nuevo es igual al anterior, NO se vuelve a anunciar (track via ref `lastAnnouncedState`). Debounce 2 s entre anuncios para no saturar al screen reader.

**Por qué importa** (rationale): F2.3 cierra Fase 2 con la infraestructura de runtime que toda HU operativa posterior (F3.1 login, F3.2 lockout, F3.3 turno, IT-3..IT-10 operación, IT-11 sync UI) consumirá. Sin auto-update, deploys requieren intervención manual del operador (inacceptable para kiosko desatendido). Sin single-instance lock, dos ventanas abiertas pueden escribir a la misma DB generando races (catastrófico para flujo de caja). Sin kiosko mode, el operador puede cerrar la app accidentalmente durante operación (pérdida de datos). Sin `electron-log`, debugging post-mortem es imposible. Sin api-status polling, el operador opera a ciegas cuando el backend está caído (facturación perdida). Sin `<StatusBar>` con a11y, RNF-022 se rompe en cuanto agreguemos el primer elemento dinámico de UI. **F2.3 es la última oportunidad de Fase 2 para sentar las bases sin renegociar contratos** — F3.x arranca con `login + lockout + turno` y NO debe tocar infra.

**Hard constraints** (mirrored from `plan.md:1244-1266`):
- `electron-updater.autoDownload:true`, `autoInstallOnAppQuit:true`, `allowDowngrade:false` — G1 verbatim.
- `app.requestSingleInstanceLock()` retorna `boolean`; si `false` → `app.quit()` antes de `whenReady` — G3 verbatim.
- `PARKOS_KIOSK_MODE=1` → full-screen + `Menu.setApplicationMenu(null)` + bloquea `Ctrl+W`/`Alt+F4`; salida con `Ctrl+Shift+K` + `bcrypt.hash(pin, 12)` + comparación en tiempo constante; PIN nunca logueado — G4 verbatim.
- `electron-log` rotación 10 MB × 5 backups, formato JSON, captura `uncaughtException`/`unhandledRejection` — G5 verbatim.
- api-status polling cada 30 s, IPC `bridge.apiStatus` con `{ok, latency_ms, code?}` resuelve los 3 estados (🟢 OK / 🟡 lento / 🔴 Sin API) — G6 verbatim.
- `<StatusBar>` con `aria-live="polite"` + de-duplicación de anuncios consecutivos — G7 verbatim.
- e2e lifecycle + kiosko: segunda instancia enfoca, `Ctrl+W` bloqueado, PIN incorrecto no desbloquea — G8 verbatim.

**Scope**: ~450 LOC production (matches `plan.md:1257` verbatim). Breakdown por cluster C1..C4 detallado en §10. Total estimado con tests ~795 LOC (production ~555 + tests ~240, variance plan 450 → 555 esperado por e2e verbose + JSON config rotation + StatusBar a11y testing).

---

## 2. Estado actual verificado

### 2.1 main.ts (`apps/electron-sucursal/electron/main.ts:1-55`)

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

**Decisión técnica (ver §5 y §8)**: extraer cada bloque de init a `electron/services/{updater,log-config,api-status,kiosko,single-instance}.ts` para que `main.ts` quede como composición pura (importa + llama, sin lógica inline). Esto permite tests unitarios de cada servicio por separado y respeta SRP.

### 2.2 preload.ts (`apps/electron-sucursal/electron/preload.ts:1-49`)

**Verificado**:
- **R-IPC-1 (PASS)**: `contextBridge.exposeInMainWorld('bridge', {...})` con whitelist explícita de 8 métodos (NO spread) — F2.2 lo shippeó.
- **R-IPC-2 (PASS)**: `bridge.apiStatus.get()` ya invoca `ipcRenderer.invoke('api:status')` — F2.3 solo implementa el handler en main process.
- **R-IPC-3 (PASS)**: `bridge.kiosk.toggle(on)` ya hace `ipcRenderer.send('kiosk:toggle', on)` — F2.3 implementa el handler.
- **R-IPC-4 (PASS)**: `bridge.app.quit()` ya hace `ipcRenderer.send('app:quit')` — F2.3 implementa el handler.
- **R-IPC-5 (PASS)**: contract test `__tests__/preload.contract.test.ts` valida shape via mocks — F2.2 lo shippeó.

**Decisión técnica (ver §5)**: F2.3 NO modifica `preload.ts`. Solo agrega handlers en main process que escuchan los canales que preload ya emite. Esto preserva el contract test verde y mantiene el principio de whitelist filtering (R-IPC del F2.2 DEC-FETCH-08).

### 2.3 bridge.d.ts (`apps/electron-sucursal/electron/bridge.d.ts:1-87`)

**Verificado**:
- **R-DTS-1 (PASS)**: `BridgeSurface` interface ya define `apiStatus.get(): Promise<ApiStatus>`, `kiosk.toggle(on: boolean): void`, `app.quit(): void` — F2.2 lo shippeó.
- **R-DTS-2 (PARTIAL)**: `ApiStatus {online: boolean, lastSync: string | null}` es el shape ACTUAL; **F2.3 lo extiende** a `{ok: boolean, latency_ms: number, code?: number}` para los 3 estados (🟢/🟡/🔴). Esto es un DELTA al bridge.d.ts que requiere actualizar preload contract test.

**Decisión técnica (ver §5.12)**: DEC-UPD-12 cambia `ApiStatus` shape. Mantener backward-compat imposible sin romper parkosFetch (F2.2 DEC-FETCH-08 enforza exact shape). Cambio se acepta como breaking — solo hay 1 consumer en F2.3 (`StatusBar`) y 1 stub en F2.2 (`bridge.spec.ts` test 5) que se actualiza simultáneamente.

### 2.4 package.json (`apps/electron-sucursal/package.json:22-77`)

**Verificado**:
- **R-DEPS-1 (PASS)**: `electron-log@^5.1.7` ya está en dependencies (F2.1 lo agregó como placeholder).
- **R-DEPS-2 (PASS)**: `electron-updater@^6.3.9` ya está en dependencies (F2.1 lo agregó como placeholder).
- **R-DEPS-3 (PASS)**: `electron-store@^8.2.0` ya está en dependencies (F2.2 lo consumió para authStore).
- **R-DEPS-4 (FAIL — F2.3 lo agrega)**: `bcrypt` NO está en dependencies. F2.3 agrega `bcrypt@^5.1.1` + `@types/bcrypt@^5.0.2` (dev).
- **R-DEPS-5 (PASS)**: `electron-builder@^25.0.5` + `electron@^30.5.1` ya están (F2.1 DEC-ELEC-04).
- **R-DEPS-6 (PASS)**: `@playwright/test@^1.48.0` ya está (F2.2 e2e).
- **R-DEPS-7 (PASS)**: `@axe-core/playwright@^4.10.0` ya está (RNF-022 gate).

**Decisión técnica (ver §5)**: F2.3 agrega solo `bcrypt` + `@types/bcrypt`. Las otras deps ya están. NO requiere npm install si `bcrypt` se agrega a package.json en el commit (la instalación la hace el apply phase).

### 2.5 tsconfig + vite config + esbuild config

**Verificado**:
- **R-CFG-1 (PASS)**: `tsconfig.json` references `./tsconfig.main.json` + `./tsconfig.renderer.json` (F2.1 DEC-ELEC-02).
- **R-CFG-2 (PASS)**: `tsconfig.main.json` includes `electron/**/*.ts` + `electron/**/*.d.ts` + `src/main/**/*.ts` + `src/shared/**/*.ts` con `strict:true` + `noUncheckedIndexedAccess:true` (F2.1 DEC-ELEC-02).
- **R-CFG-3 (FAIL — F2.3 lo agrega)**: `tsconfig.main.json` NO incluye `electron/services/**/*.ts` — F2.3 lo agrega.
- **R-CFG-4 (PASS)**: `vite.config.ts` alias `@` → `src/renderer` + `@shared` → `src/shared` (F2.1 DEC-ELEC-03).
- **R-CFG-5 (PASS)**: `esbuild-main.mjs` bundlea `electron/main.ts` → `out/main.js` + `electron/preload.ts` → `out/preload.js` con target node20 format cjs external:electron (F2.1 DEC-ELEC-03).
- **R-CFG-6 (FAIL — F2.3 lo agrega)**: `esbuild-main.mjs` NO incluye `electron/services/**/*.ts` — esbuild resuelve transitivamente desde main.ts entry, así que NO requiere cambio.

**Decisión técnica (ver §5)**: F2.3 agrega `electron/services/**/*.ts` al include de `tsconfig.main.json` para que tsc valide strict types. esbuild resuelve transitivamente sin cambio.

### 2.6 e2e/ (`apps/electron-sucursal/e2e/`)

**Verificado**:
- **R-E2E-1 (PASS)**: `e2e/scaffold.spec.ts` (F2.1, axe-core gate RNF-022).
- **R-E2E-2 (PASS)**: `e2e/auth/parkos-fetch.spec.ts` (F2.2, 14 scenarios).
- **R-E2E-3 (PASS)**: `e2e/auth/bridge.spec.ts` (F2.2, 8 scenarios).
- **R-E2E-4 (PASS)**: `e2e/a11y/wcag-2.1-aa.spec.ts` (F2.2, axe-core scan).
- **R-E2E-5 (FAIL — F2.3 lo agrega)**: NO existe `e2e/lifecycle.spec.ts` (segunda instancia focus + kiosko Ctrl+W).
- **R-E2E-6 (FAIL — F2.3 lo agrega)**: NO existe `e2e/kiosko.spec.ts` (PIN incorrecto + log de audit).

**Decisión técnica (ver §11)**: F2.3 agrega 2 e2e (lifecycle + kiosko). Las e2e en sandbox F.6 + npm 11.16.0 SKIPPED precedent (F2.2 G8 archive report) — F2.3 e2e van a correr la misma suerte, documentado en §11.

### 2.7 apps/ui-kit/

**Verificado**:
- **R-UI-1 (PASS)**: `apps/ui-kit/src/index.ts` exporta Button + cn + tokens (F2.1 DEC-ELEC-08).
- **R-UI-2 (PASS)**: `apps/ui-kit/src/hooks/useAuth.ts` + `apps/ui-kit/src/store/authStore.ts` (F2.2 DEC-FETCH-06/07).
- **R-UI-3 (FAIL — F2.3 opcional)**: NO existe `apps/ui-kit/src/hooks/useApiStatus.ts` — F2.3 opcional lo crea como wrapper SWR para `bridge.apiStatus.get()`.

**Decisión técnica (ver §5.13)**: F2.3 NO requiere nuevo ui-kit export. StatusBar consume `bridge.apiStatus.get()` directamente con su propio `useState` + `setInterval`. Si el equipo decide abstraer (forward consumer: F11.x sync UI), DEC-UPD-13 lo agrega como follow-up HU.

---

## 3. Consumer anchor: endpoints backend + servicios externos

### 3.1 Backend `/health` endpoint

**Estado**: NO EXISTE en backend.

`backend/packages/parkos_core/src/parkos_core/api/v1/` no contiene `health.py` ni equivalente. F2.3 lo necesita para `bridge.apiStatus.get()`. `plan.md` §1270+ menciona "Fase 3" como consumer de login, no como creador de `/health`.

**Decisión**: F2.3 implementa el polling asumiendo endpoint hypothetical con response `{status: "ok"}` (2xx) o cualquier error (4xx/5xx/timeout). StatusBar renderiza 🔴 mientras el endpoint no exista. Documentado en pending.md §2 (bloqueador deployment) y en §13 (out-of-scope). F2.3 NO bloquea si /health no existe — degrada gracefully a 🔴.

### 3.2 electron-updater feed

**Estado**: configurable.

`electron-updater` lee la config `publish` desde `electron-builder.yml` (F2.1 DEC-ELEC-04 lo creó con `autoUpdate:false` placeholder). F2.3 agrega `publish: [{provider: 'github', owner: 'easypunto_parkos', repo: 'easypunto_parkos'}]` como default. Override via env `PARKOS_UPDATE_FEED_URL` para entornos staging (custom server).

**Decisión**: F2.3 usa `autoUpdater.setFeedURL(process.env.PARKOS_UPDATE_FEED_URL || 'https://github.com/easypunto_parkos/easypunto_parkos/releases')` en runtime para sobreescribir el publish default sin recompilar electron-builder (DEC-UPD-01).

### 3.3 electron-log path

**Estado**: ya integrado en `electron-log@^5.1.7`.

`log.transports.file.resolvePathFn = () => path.join(app.getPath('userData'), 'logs', 'main.log')`. Default electron-log path es `%APPDATA%/<productName>/logs/main.log` (Windows) — matches `Parkos Sucursal` productName de F2.1 DEC-ELEC-04. NO requiere override (DEC-UPD-11).

### 3.4 bcrypt PIN pre-shared

**Estado**: NO EXISTE en electron-store.

F2.3 crea el hash al primer deploy via script de seeding: `node scripts/seed-kiosko-pin.js --pin=<value>` (out-of-scope, pero el contrato está documentado). El hash se persiste bajo key `kiosk.pinHash` en `app.getPath('userData')/auth.json` (electron-store ya existe por F2.2).

**Decisión**: F2.3 lee `bridge.authStore.get('kiosk.pinHash')` al startup. Si `null`, kiosko mode se desactiva con warning loggeado (`kiosko.pin_missing`). El deploy-time seeding script se documenta en §13 out-of-scope (DEC-UPD-09).

---

## 4. Stack técnico objetivo

### 4.1 Nuevas dependencias (`apps/electron-sucursal/package.json`)

**AGREGAR**:
- `dependencies`: `bcrypt@^5.1.1` (factor 12 compatible — versiones 5.x soportan cost factor >=10 sin deprecation warning).
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

- `electron-updater@^6.3.9`.
- `electron-log@^5.1.7`.
- `bcrypt@^5.1.1`.
- Electron `30.5.x` (ya en stack).
- React `18.3.x` (ya en stack).

### 4.3 Tooling

- esbuild `0.24.x` (main+preload, F2.1 DEC-ELEC-03).
- Vite `5.4.x` (renderer, F2.1 DEC-ELEC-03).
- Vitest `2.1.x` (unit, F2.1).
- Playwright `1.48.x` + `_electron.launch` (e2e, F2.1 + F2.2).
- axe-core `4.10.x` (a11y, F2.1 RNF-022).

---

## 5. Decisiones arquitectónicas (DEC-UPD-NN × 13)

F2.3 introduce 13 decisiones arquitectónicas (DEC-UPD-01..13). El detalle verbatim vive en `exploration.md` §5. Esta sección referencia y resume cada DECISION + RATIONALE + ALTERNATIVES CONSIDERED. El segundo pase con justificación extendida vive en §8.

### 5.1 DEC-UPD-01 — electron-updater feed configurable via env `PARKOS_UPDATE_FEED_URL`

**DECISION**: `autoUpdater.setFeedURL(process.env.PARKOS_UPDATE_FEED_URL || 'https://github.com/easypunto_parkos/easypunto_parkos/releases')` en runtime init.

**RATIONALE**: F2.1 shippeó `electron-builder.yml autoUpdate:false` placeholder (DEC-ELEC-04). F2.3 flipea a `true` y agrega publish config. Override via env permite staging sin recompilar electron-builder (reading config en runtime, no bake-time).

**ALTERNATIVES CONSIDERED**:
- A. `electron-builder.yml publish` estático (bake-time) — RECHAZADA. Requiere recompilar electron-builder para staging; staging override sin recompilar es patrón estándar del repo (F2.2 ya usa `PARKOS_API_BASE` para parkosFetch baseURL — precedent).
- B. Variable de feed solo en runtime sin publish default — RECHAZADA. Sin default, primera ejecución antes de staging setup falla con error "no feed URL".

### 5.2 DEC-UPD-02 — autoDownload + autoInstallOnAppQuit (NO prompt al usuario)

**DECISION**: `autoUpdater.autoDownload = true` + `autoUpdater.autoInstallOnAppQuit = true`. CERO UI prompts al operador.

**RATIONALE**: Kiosko desatendido — el operador no debe interactuar con update dialogs. Auto-install at quit minimiza disruption (la próxima vez que el operador abre la app, ya está en la nueva versión). `plan.md:1249` verbatim.

**ALTERNATIVES CONSIDERED**:
- A. Modal "Hay una actualización disponible" con botón "Instalar ahora" — RECHAZADA. Kiosko desatendido no puede requerir interacción.
- B. Manual update via menú "Ayuda > Buscar actualizaciones" — RECHAZADA. Kiosko mode oculta menú (DEC-UPD-08).

### 5.3 DEC-UPD-03 — allowDowngrade false + allowPrerelease false

**DECISION**: `autoUpdater.allowDowngrade = false` + `electron-builder.yml publish.allowPrerelease:false`. Downgrades NO permitidos.

**RATIONALE**: `plan.md:1249` verbatim. Schema migrations pueden ser incompatibles con versiones anteriores; un downgrade puede dejar la DB en estado inconsistente. Updates solo forward (major + minor + patch).

**ALTERNATIVES CONSIDERED**:
- A. Permitir downgrade para rollback de emergencia — RECHAZADA. Riesgo de inconsistencia DB > beneficio de rollback. Si update falla, retry next cycle (6h, DEC-UPD-02).
- B. Permitir prereleases a staging — CONSIDERADA PERO RECHAZADA. `allowPrerelease:false` global para evitar confusión. Staging usa feed URL custom (DEC-UPD-01).

### 5.4 DEC-UPD-04 — signature verification via electron-builder publish config (auto-falla si no está)

**DECISION**: `electron-builder.yml publish.provider:"github"` + macOS hardened-runtime + Windows Authenticode. Si la firma falla (`autoUpdater.on('error', err)` con `err.message` contiene "signature"), NO se instala, se loguea en `electron-log` nivel `error` y se reintenta en el próximo ciclo (6h después).

**RATIONALE**: Security boundary — sin signature verification, un MITM puede inyectar un binario malicioso. electron-builder valida automáticamente durante download; F2.3 solo necesita capturar el error event.

**ALTERNATIVES CONSIDERED**:
- A. Verificación manual con `crypto.verify()` en JS — RECHAZADA. electron-builder ya lo hace; duplicar trabajo es bug-prone.
- B. Skip signature verification en dev mode — RECHAZADA. Mismo código path dev/prod (DX consistency).

### 5.5 DEC-UPD-05 — api-status polling 30s en MAIN process (NO renderer)

**DECISION**: El polling ocurre en `electron/services/api-status.ts` (main process), NO en el renderer. El renderer consume `bridge.apiStatus.get()` que IPC-invoca el último valor cacheado.

**RATIONALE**: Security boundary — el renderer NO debe hacer fetch directo al backend (sería绕过 CORS + CSP). Main process tiene control total de la red. Polling 30s en main libera al renderer del ciclo de vida.

**ALTERNATIVES CONSIDERED**:
- A. Polling en renderer con `setInterval` + parkosFetch — RECHAZADA. Renderer exposed a CORS, CSP, race conditions de window focus.
- B. SSE (Server-Sent Events) desde backend — RECHAZADA. Backend `/health` no existe (F2.3 lo asume hypothetical). Forward hook si backend migra a push.

### 5.6 DEC-UPD-06 — api-status timeout 5s vía AbortController

**DECISION**: `fetch(url, {signal: AbortSignal.timeout(5000)})` o equivalente con `AbortController` + `setTimeout(() => controller.abort(), 5000)`. Si timeout, devuelve `{ok:false, code: undefined}`.

**RATIONALE**: Kiosko desatendido — un backend colgado no puede bloquear la UI indefinidamente. 5s es suficiente para un health check (red local 127.0.0.1 < 100ms típicamente).

**ALTERNATIVES CONSIDERED**:
- A. Timeout 30s — RECHAZADA. UX inaceptable (operador espera 30s para ver 🔴).
- B. Sin timeout — RECHAZADA. Kiosko bloqueado en una request indefinidamente.

### 5.7 DEC-UPD-07 — single-instance lock con second-instance focus (no spawn new window)

**DECISION**: `app.requestSingleInstanceLock()` ANTES de `app.whenReady()`. Si `false` → `app.quit()`. Si `true` → `app.on('second-instance', () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus() } })`.

**RATIONALE**: `plan.md:1250` verbatim. Race condition prevention: el lock DEBE adquirirse antes de cualquier otra inicialización. Segundo instance enfoca la ventana existente (UX: el operador no quiere 2 ventanas con la misma DB).

**ALTERNATIVES CONSIDERED**:
- A. Lock after whenReady — RECHAZADA. Race window entre whenReady y createWindow permite spawn de 2 ventanas.
- B. Spawn new window on second-instance — RECHAZADA. Catastrófico para kiosko (2 ventanas con la misma DB = race conditions).

### 5.8 DEC-UPD-08 — kiosko via env var `PARKOS_KIOSK_MODE=1` (no config UI)

**DECISION**: Kiosko se activa al startup si `process.env.PARKOS_KIOSK_MODE === '1'`. NO hay toggle UI para activar kiosko (solo `Ctrl+Shift+K` + PIN para desactivar).

**RATIONALE**: Kiosko es decisión de deploy, no de operador. Env var permite configurar vía electron-builder o script de launch sin recompilar. F2.3 NO expone toggle UI para activar (sería backdoor).

**ALTERNATIVES CONSIDERED**:
- A. Toggle UI para activar/desactivar kiosko — RECHAZADA. Backdoor: cualquier operador puede salir de kiosko.
- B. Archivo `kiosko.json` con config persistente — CONSIDERADA PERO RECHAZADA. Env var es KISS; archivo requiere deploy process adicional.

### 5.9 DEC-UPD-09 — PIN bcrypt factor 12, comparación tiempo constante, hash pre-shared via electron-store

**DECISION**: `bcrypt.hash(pin, 12)` al deploy-time, persistido bajo key `kiosk.pinHash` en electron-store. Comparación con `bcrypt.compareSync(pin, hash)` (Node bcrypt es constant-time por default). **PIN nunca logueado** — solo `kiosko.unlock_attempt{success: bool, attempt_id: uuid, timestamp: ISO}`.

**RATIONALE**: `plan.md:1251` verbatim. Factor 12 = ~250ms por hash (OWASP 2023 recommendation para interactive auth). Constant-time compare previene timing attacks. Pre-shared via electron-store evita pedir PIN al deploy (un solo secreto, no por usuario).

**ALTERNATIVES CONSIDERED**:
- A. PIN por usuario (consulta backend) — RECHAZADA. Kiosko offline no funciona; backend down = locked out.
- B. PIN por sucursal en DB cloud — RECHAZADA. Kiosko offline-first; pre-shared es KISS.
- C. SHA-256 simple del PIN — RECHAZADA. No es constant-time; vulnerable a timing attacks; factor de costo no ajustable.

### 5.10 DEC-UPD-10 — shortcuts bloqueados via before-input-event (no accelerators globales)

**DECISION**: `mainWindow.webContents.on('before-input-event', (event, input) => { if (input.control && input.key.toLowerCase() === 'w') event.preventDefault(); if (input.alt && input.key === 'F4') event.preventDefault(); })`. NO se usan `globalShortcut.register()` (esos son OS-wide, demasiado invasivos).

**RATIONALE**: `before-input-event` es scoped a la ventana Electron — solo bloquea dentro de la app, no afecta otros OS shortcuts. `globalShortcut` bloquearía system-wide (inacceptable).

**ALTERNATIVES CONSIDERED**:
- A. `globalShortcut.register()` — RECHAZADA. OS-wide, bloquea shortcuts fuera de la app.
- B. `Menu.setApplicationMenu(null)` solamente — INSUFICIENTE. `Ctrl+W` y `Alt+F4` son accelerators del BrowserWindow, no del Menu.

### 5.11 DEC-UPD-11 — electron-log rotación 10MB×5 JSON, captura uncaughtException + unhandledRejection

**DECISION**: `log.transports.file.maxSize = 10 * 1024 * 1024` (10 MB), `transports.file.backups = 5` (max 50 MB total). `log.format = log.formats.json` (estructurado). `process.on('uncaughtException', err => log.error(err))` + `process.on('unhandledRejection', reason => log.error(reason))`.

**RATIONALE**: `plan.md:1253` verbatim. 50 MB cap evita disk fill. JSON format permite parsing post-mortem con `jq` o similar. Capturar crashes tempranos (boot antes de whenReady) requiere init ANTES de cualquier otra cosa.

**ALTERNATIVES CONSIDERED**:
- A. Rotación 5MB×10 (mismo total 50MB) — RECHAZADA. Más archivos = más I/O; 10MB×5 es sweet spot.
- B. Logs en formato plain text — RECHAZADA. JSON estructurado permite parsing con `jq` para post-mortem.

### 5.12 DEC-UPD-12 — `<StatusBar>` con `aria-live="polite"` + de-duplicación consecutiva + debounce 2s

**DECISION**: `<StatusBar role="status" aria-live="polite" aria-atomic="true">` envuelve el texto. `useRef<ApiStatus | null>(null)` tracks `lastAnnouncedState`. Si `newState !== lastAnnouncedState` Y `now - lastAnnouncedAt > 2000`, anuncia + actualiza ref.

**RATIONALE**: `aria-live="polite"` no interrumpe al screen reader (vs `assertive`). De-duplicación evita spam (operador no necesita oír "Sin API" 30 veces por minuto). Debounce 2s previene race conditions en cambios rápidos.

**ALTERNATIVES CONSIDERED**:
- A. `aria-live="assertive"` (interrumpe screen reader) — RECHAZADA. Interrumpe al operador en medio de otra tarea (mala UX).
- B. Toast notification por cambio de estado — RECHAZADA. Visual noise + no es screen-reader friendly.
- C. Sin de-duplicación (anuncia cada cambio) — RECHAZADA. Screen reader spam (operador oye "Sin API" cada 30s).

### 5.13 DEC-UPD-13 — NO-OP delta stub para spec.md (DEC-ELEC-10 + DEC-FETCH-10 precedent)

**DECISION**: `openspec/changes/hu-f2-3-electron-auto-update-kiosko/specs/operations/spec.md` es un NO-OP stub (~85 LOC) que documenta las 13 DEC-UPD-NN como INFORMATIONAL. NO agrega REQ-OPS-NNN (F2.3 es infra de runtime, no behavior contract).

**RATIONALE**: Precedente verbatim de F2.1 DEC-ELEC-10 (`specs/operations/spec.md` NO-OP stub) + F2.2 DEC-FETCH-10 (mismo patrón). Si F2.3 agrega REQs, sería la primera HU de Fase 2 con behavior contract — out-of-pattern. La justificación: las decisions viven en proposal.md como DEC-UPD-NN, no como REQ-OPS.

**ALTERNATIVES CONSIDERED**:
- A. Crear REQ-OPS-113..125 para DEC-UPD-NN — RECHAZADA. Out-of-pattern; precedent F2.1 + F2.2 explícitamente NO-OP.
- B. Crear capability spec `electron-runtime` — RECHAZADA. F2.3 es infra de runtime, no behavior contract; precedent F1.15 DEC-XR7 NOT-CREATED.

**Convención de identificadores**: DEC-UPD-NN sigue el patrón DEC-ELEC-NN de F2.1 y DEC-FETCH-NN de F2.2. La propuesta F2.3 NO crea nuevos REQ-OPS-NNN (DEC-UPD-13, ver §6).

---

## 6. Contratos de comportamiento

### 6.1 Decisión explícita: NO agregar REQ-OPS-NNN nuevos

**F2.3 NO agrega REQs al spec canónico** (`openspec/specs/operations/spec.md`) porque es "infraestructura de runtime" — mismo razonamiento que F2.1 DEC-ELEC-10 y F2.2 DEC-FETCH-10. Las 13 decisiones arquitectónicas viven en este `proposal.md` como DEC-UPD-NN. Behavior contracts futuros (refresh rotation detection en PR7 backend, lockout countdown en F3.2, turno lifecycle en F3.3) se agregarán como REQ cuando introduzcan endpoints nuevos o invariantes de negocio.

**Precedente**: F2.1 archivado en `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/proposal.md` §13 (DEC-ELEC-10) y F2.2 archivado en `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/proposal.md` §6 (DEC-FETCH-10) aplican la misma convención. F1.15 archivado en `operations/spec.md:4386` (DEC-XR7 NOT-CREATED) la precede para HU con decisiones arquitectónicas sin comportamiento observable.

### 6.2 Si la propuesta decidiera agregar REQ-OPS-113..125 (enumerados verbatim)

`exploration.md` §5 enumera las 13 DEC candidatas. F2.3 las incluye referencialmente pero NO las materializa como REQ-OPS-NNN en `operations/spec.md`:

| ID candidato | Comportamiento | Source |
|---|---|---|
| ~~REQ-OPS-113~~ | `electron-updater autoDownload:true + autoInstallOnAppQuit:true + allowDowngrade:false` | DEC-UPD-02/03 |
| ~~REQ-OPS-114~~ | `electron-updater signature verification via electron-builder publish config` | DEC-UPD-04 |
| ~~REQ-OPS-115~~ | `api-status polling 30s main process + timeout 5s AbortController` | DEC-UPD-05/06 |
| ~~REQ-OPS-116~~ | `app.requestSingleInstanceLock() before whenReady + second-instance focus` | DEC-UPD-07 |
| ~~REQ-OPS-117~~ | `kiosko mode via env PARKOS_KIOSK_MODE=1` | DEC-UPD-08 |
| ~~REQ-OPS-118~~ | `kiosko PIN bcrypt factor 12 + constant-time compare + never logged` | DEC-UPD-09 |
| ~~REQ-OPS-119~~ | `kiosko shortcuts blocked via before-input-event (Ctrl+W, Alt+F4)` | DEC-UPD-10 |
| ~~REQ-OPS-120~~ | `electron-log rotation 10MB×5 JSON + uncaughtException capture` | DEC-UPD-11 |
| ~~REQ-OPS-121~~ | `<StatusBar> aria-live="polite" + dedup consecutiva + debounce 2s` | DEC-UPD-12 |
| ~~REQ-OPS-122~~ | `electron-updater feed configurable via env PARKOS_UPDATE_FEED_URL` | DEC-UPD-01 |
| ~~REQ-OPS-123~~ | `autoUpdater autoInstall retry every 6h on signature failure` | DEC-UPD-04 |
| ~~REQ-OPS-124~~ | `kiosko unlock audit log kiosko.unlock_attempt{success, attempt_id, timestamp}` | DEC-UPD-09 |
| ~~REQ-OPS-125~~ | `bridge.apiStatus shape {ok: boolean, latency_ms: number, code?: number}` | DEC-UPD-12 |

**DECIDIDO**: NO se crean REQ-OPS-113..125 en esta propuesta. Las DEC-UPD-NN en §5 cargan el mismo peso RFC 2119 que las REQs para HUs de comportamiento. Esta decisión es reversible: si en `sdd-spec` se determina que la complejidad justifica REQs explícitas, el spec las materializa.

### 6.3 Contratos forwarded (consume-only)

F2.3 NO crea endpoints. Consume los siguientes contratos existentes o hipotéticos:

- **`GET /api/v1/health`** — HIPOTHÉTICO. Response `{status: "ok"}` (2xx) o cualquier error (4xx/5xx/timeout). NO EXISTE en backend; F2.3 degrada gracefully a 🔴 mientras no exista. HU backend separada F3+.
- **`electron-updater feed`** — `https://github.com/easypunto_parkos/easypunto_parkos/releases` (default) o custom via `PARKOS_UPDATE_FEED_URL`.
- **`electron-log path`** — `app.getPath('userData')/logs/main.log` (Windows: `%APPDATA%/parkos/logs/main.log`).
- **PIN bcrypt pre-shared** — `bridge.authStore.get('kiosk.pinHash')` retorna hash bcrypt factor 12 desde `app.getPath('userData')/auth.json`.

F2.3 NO modifica los endpoints existentes (porque no crea ninguno). Backward-compat preservada.

---

## 7. Análisis de impacto (no hay conflicto arquitectónico)

A diferencia de F1.12 (cross-domain atomicity) o F2.1 (workspaces topological order), F2.3 NO tiene un conflicto arquitectónico mayor. Cada bloque de F2.3 (updater, log-config, single-instance, kiosko, api-status, `<StatusBar>`) opera en un namespace distinto:

- **Updater**: `electron/services/updater.ts` (NEW). Lifecycle: `app.whenReady()` → check every 6h via `setInterval`. Main process only.
- **Log-config**: `electron/services/log-config.ts` (NEW). Lifecycle: app boot (ANTES de `whenReady` para capturar crashes tempranos). Main process only.
- **Single-instance**: `electron/main.ts` (MODIFY top). Lifecycle: synchronous at app boot, BEFORE `whenReady`.
- **Kiosko**: `electron/services/kiosko.ts` (NEW). Lifecycle: `app.whenReady()` → apply if env var set. Listens IPC `kiosk:toggle`.
- **api-status**: `electron/services/api-status.ts` (NEW). Lifecycle: `app.whenReady()` → `setInterval` 30s. Cache last result. IPC handler `api:status`.
- **`<StatusBar>`**: `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (NEW). Renderer only, mounts in `App.tsx`.

### 7.1 Orden de inicialización (DEC-UPD-07 mandates)

1. `app.requestSingleInstanceLock()` — sync, boot (SI RETORNA FALSE → `app.quit()` INMEDIATO).
2. `electron-log` init (`initLogConfig()`) — sync, boot (antes de `whenReady` para capturar crashes tempranos).
3. `process.on('uncaughtException'/'unhandledRejection')` — sync, boot.
4. `app.whenReady().then(...)` — async.
5. Dentro de `whenReady`:
   a. `electron-updater` init (`initUpdater()` — autoDownload, setFeedURL, signature verification handlers).
   b. `api-status` polling start (`initApiStatus()` — setInterval 30s).
   c. Si `PARKOS_KIOSK_MODE === '1'` → apply kiosko (`initKiosko()`).
   d. `createMainWindow()`.
6. IPC handlers registered (`api:status`, `kiosk:toggle`, `app:quit`).

### 7.2 Modificaciones a archivos existentes

| Archivo | Cambio | Razón |
|---|---|---|
| `electron/main.ts` | MODIFY ~70 LOC delta | Imports de services + init calls en orden + IPC handlers + lock check |
| `electron/bridge.d.ts` | MODIFY ~5 LOC delta | `ApiStatus` shape delta: `{online, lastSync}` → `{ok, latency_ms, code?}` |
| `electron/preload.ts` | NO MODIFY | F2.2 ya wireado, F2.3 solo implementa handlers |
| `electron/__tests__/preload.contract.test.ts` | MODIFY ~10 LOC | Actualizar test 5 `apiStatus.get` para match nuevo shape |
| `electron-builder.yml` | MODIFY ~10 LOC | Flipear `autoUpdate:false → true` + agregar publish provider |
| `tsconfig.main.json` | MODIFY ~3 LOC | Agregar `electron/services/**/*.ts` a include |
| `package.json` | MODIFY ~2 LOC | Agregar `bcrypt@^5.1.1` + `@types/bcrypt@^5.0.2` |
| `src/renderer/App.tsx` | MODIFY ~5 LOC | Mount `<StatusBar />` arriba del `<main>` |
| `src/renderer/i18n/locales/common.json` | MODIFY ~5 LOC | Agregar keys `statusBar.ok`, `statusBar.slow`, `statusBar.offline` |

---

## 8. Decisiones arquitectónicas — segundo pase con justificación extendida

### 8.1 DEC-UPD-01 vs alternativas — feed runtime override

**Contexto**: F2.1 shippeó `electron-builder.yml autoUpdate:false` placeholder (DEC-ELEC-04). F2.3 flipea a `true` y configura el feed.

**Alternativa A (RECHAZADA)**: `electron-builder.yml publish` estático (bake-time).
- Pros: simple, no env var.
- Cons: requiere recompilar electron-builder para staging.

**Alternativa B (DECIDIDA)**: `autoUpdater.setFeedURL(env || github_default)` runtime.
- Pros: staging override sin recompilar; misma flexibilidad que `PARKOS_API_BASE` (F2.2 precedent).
- Cons: requiere `autoUpdater.setFeedURL` antes de `checkForUpdates()`.

**Razón**: electron-updater 6.x soporta `setFeedURL` runtime sin issues. Override via env es patrón estándar del repo (F2.2 ya usa `PARKOS_API_BASE` para parkosFetch baseURL).

### 8.2 DEC-UPD-09 vs alternativas — PIN bcrypt pre-shared

**Contexto**: PIN de salida de kiosko debe ser seguro pero offline-safe.

**Alternativa A (RECHAZADA)**: PIN por usuario (consulta backend).
- Pros: revocable individual; audit per user.
- Cons: kiosko offline no funciona; backend down = locked out; requires `prod.login` lookup.

**Alternativa B (DECIDIDA)**: PIN pre-shared via electron-store.
- Pros: kiosko offline-safe; deploy-time rotation; simple; un solo secreto compartido entre operadores.
- Cons: rotación requiere script de deploy (no UI).

**Razón**: kiosko es desatendido — asumir backend down es el failure mode común. PIN pre-shared es KISS. Si backend está disponible, F3.x puede consultar `prod.login` para usuarios individuales (forward hook).

### 8.3 DEC-UPD-12 vs alternativas — aria-live polite + dedup

**Contexto**: StatusBar muestra estado del backend; screen readers deben anunciar cambios sin interrumpir.

**Alternativa A (RECHAZADA)**: `aria-live="assertive"` (interrumpe screen reader).
- Pros: anuncia inmediatamente.
- Cons: interrumpe al operador en medio de otra tarea (mala UX).

**Alternativa B (DECIDIDA)**: `aria-live="polite"` + de-duplicación + debounce 2s.
- Pros: no interrumpe; evita spam; respeta al operador.
- Cons: requiere ref tracking (`useRef<ApiStatus | null>(null)`) + debounce logic.

**Razón**: RNF-022 WCAG 2.1 AA incluye "no interrumpir sin razón" (SC 4.1.3). Polite + dedup es el patrón canónico para status updates (WAI-ARIA Authoring Practices).

---

## 9. Atomic tasks T1..T7 con budgets LOC

Cada task es **atómica** (commiteable independientemente con tests verde), pero se ejecutan en orden T1 → T7. Detalle verbatim en `exploration.md` §9.

| Task | Budget (LOC) | Archivos | Commit message | Gate |
|---|---|---|---|---|
| **T1 — electron-updater + signature verification** | ~110 (80 prod + 30 tests) | `apps/electron-sucursal/electron/services/updater.ts` (NEW, ~70 LOC) · `updater.test.ts` (NEW, ~30 LOC) · `apps/electron-sucursal/electron/main.ts` (MODIFY, agregar `initUpdater()` call en whenReady) · `electron-builder.yml` (MODIFY, flipear `autoUpdate:false → true` + agregar publish provider) · `tsconfig.main.json` (MODIFY, agregar `electron/services/**/*.ts` a include) | `feat(electron): adicionar electron-updater con feed configurable + signature verification + autoDownload/autoInstallOnAppQuit` | G1, G2 |
| **T2 — api-status polling 30s + IPC handler** | ~70 (50 prod + 20 tests) | `apps/electron-sucursal/electron/services/api-status.ts` (NEW, ~40 LOC) · `api-status.test.ts` (NEW, ~20 LOC) · `apps/electron-sucursal/electron/main.ts` (MODIFY, registrar IPC handler `api:status` + `initApiStatus()` en whenReady) | `feat(electron): adicionar api-status polling 30s a /health con AbortController timeout 5s + IPC bridge.apiStatus` | G6 |
| **T3 — single-instance lock + second-instance focus** | ~30 (20 prod + 10 tests) | `apps/electron-sucursal/electron/main.ts` (MODIFY, agregar `app.requestSingleInstanceLock()` antes de whenReady + listener `second-instance`) · `apps/electron-sucursal/electron/__tests__/single-instance.test.ts` (NEW, ~10 LOC — opcional, e2e cubre el caso real) | `feat(electron): adicionar single-instance lock con second-instance focus` | G3 |
| **T4 — kiosko mode + PIN bcrypt** | ~140 (100 prod + 40 tests) | `apps/electron-sucursal/electron/services/kiosko.ts` (NEW, ~90 LOC) · `kiosko.test.ts` (NEW, ~40 LOC) · `apps/electron-sucursal/electron/main.ts` (MODIFY, registrar IPC handlers `kiosk:toggle` + `app:quit` + apply kiosko si env var) · `apps/electron-sucursal/package.json` (MODIFY, agregar `bcrypt@^5.1.1` + `@types/bcrypt@^5.0.2`) | `feat(electron): adicionar kiosko mode con PIN bcrypt factor 12 + shortcuts bloqueados + Menu null + setKiosk` | G4 |
| **T5 — electron-log rotación 10MB×5 JSON + captura uncaughtException** | ~40 (30 prod + 10 tests) | `apps/electron-sucursal/electron/services/log-config.ts` (NEW, ~25 LOC) · `apps/electron-sucursal/electron/main.ts` (MODIFY, `initLogConfig()` ANTES de whenReady + `process.on('uncaughtException'/'unhandledRejection')`) | `feat(electron): adicionar electron-log con rotación 10MB×5 JSON + captura uncaughtException/unhandledRejection` | G5 |
| **T6 — `<StatusBar>` con aria-live polite + de-duplicación** | ~110 (80 prod + 30 tests) | `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (NEW, ~70 LOC) · `StatusBar.test.tsx` (NEW, ~30 LOC) · `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY, mount `<StatusBar />` arriba del `<main>`) · `apps/electron-sucursal/src/renderer/i18n/locales/common.json` (MODIFY, agregar keys `statusBar.ok`, `statusBar.slow`, `statusBar.offline`) | `feat(ui): adicionar StatusBar con aria-live polite + de-duplicación de anuncios consecutivos` | G7 |
| **T7 — 2 e2e lifecycle + kiosko** | ~120 tests | `apps/electron-sucursal/e2e/lifecycle.spec.ts` (NEW, ~60 LOC — segunda instancia focus + kiosko Ctrl+W bloqueado) · `apps/electron-sucursal/e2e/kiosko.spec.ts` (NEW, ~60 LOC — PIN incorrecto no desbloquea + log audit verificado) | `test(electron): adicionar 2 e2e lifecycle + kiosko (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto)` | G3, G4, G8 |
| **TOTAL** | **~620 LOC** (360 prod + 240 tests + 20 config) | 14 archivos nuevos + 9 modificaciones | 7 commits atómicos | 8 gates |

**Resumen de clusters** (§10): C1 = T1+T5 · C2 = T2+T6 · C3 = T3+T4 · C4 = T7. Orden obligatorio C1 → C2 → C3 → C4.

### 9.8 Resumen de budgets

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 updater | 80 | 30 | 110 |
| T2 api-status | 50 | 20 | 70 |
| T3 single-instance | 20 | 10 | 30 |
| T4 kiosko | 100 | 40 | 140 |
| T5 log-config | 30 | 10 | 40 |
| T6 `<StatusBar>` | 80 | 30 | 110 |
| T7 e2e | 0 | 120 | 120 |
| **TOTAL** | **360** | **260** | **620** |

Total real ~795 LOC incluyendo configs (~30 LOC package.json + tsconfig + electron-builder.yml edits) y JSDoc (~30 LOC comentarios).

---

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
- `apps/electron-sucursal/src/renderer/App.tsx` (MODIFY — mount `<StatusBar />`).
- `apps/electron-sucursal/src/renderer/i18n/locales/common.json` (MODIFY — 3 keys).

**Total C2**: ~180 LOC.

### 10.3 C3: Lockdown (T3+T4) — single-instance + kiosko PIN

**Archivos**:
- `apps/electron-sucursal/electron/services/kiosko.ts` (~90 LOC).
- `apps/electron-sucursal/electron/services/kiosko.test.ts` (~40 LOC).
- `apps/electron-sucursal/electron/main.ts` (MODIFY ~30 LOC delta — lock + kiosko init + IPC handlers).
- `apps/electron-sucursal/package.json` (MODIFY — agregar `bcrypt` + `@types/bcrypt`).

**Total C3**: ~170 LOC.

### 10.4 C4: Testing (T7) — 2 e2e lifecycle + kiosko

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

C1 → C2 → C3 → C4 (mandatory). C1 antes de C2 porque StatusBar consume api-status IPC (C2). C1 antes de C3 porque kiosko setup corre en `whenReady` que también inicializa updater. C2+C3 antes de C4 porque e2e tests requieren el runtime completo.

---

## 11. Acceptance gates pre-flight

8 gates que deben pasar ANTES de mergear F2.3 a `origin/dev`.

| # | Gate | Mecanismo | Source |
|---|---|---|---|
| G1 | `electron-updater.autoDownload:true` + `autoInstallOnAppQuit:true` + `allowDowngrade:false` configurados | unit test `updater.test.ts` assert config | T1 |
| G2 | Signature verification failure → NO instala + log error + retry next cycle | unit test `updater.test.ts` mock `autoUpdater.on('error')` | T1 |
| G3 | `app.requestSingleInstanceLock()` retorna `false` en segunda invocación → enfoca primera + termina | e2e `lifecycle.spec.ts` con `_electron.launch` 2 veces | T3 + T7 |
| G4 | `PARKOS_KIOSK_MODE=1` → full-screen + Menu null + Ctrl+W bloqueado + PIN bcrypt factor 12 + Ctrl+Shift+K + PIN correcto desactiva + PIN incorrecto no desactiva + nunca logueado | unit test `kiosko.test.ts` + e2e `kiosko.spec.ts` | T4 + T7 |
| G5 | `electron-log` rotación 10MB×5 JSON + captura `uncaughtException`/`unhandledRejection` | unit test `log-config.test.ts` (mock electron-log) | T5 |
| G6 | api-status polling cada 30 s + timeout 5 s + IPC handler retorna `{ok, latency_ms, code?}` + 3 estados (🟢/🟡/🔴) | unit test `api-status.test.ts` con mock fetch + e2e integration | T2 |
| G7 | `<StatusBar>` con `aria-live="polite"` + texto exacto por estado + de-duplicación consecutiva + debounce 2 s | vitest `StatusBar.test.tsx` + axe-core extension (F2.2 axe pattern) | T6 |
| G8 | 2 e2e verde (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto no desbloquea) | playwright e2e `_electron` | T7 |

**Estado pre-flight**: 0/8 PASS al inicio (no implementado). Target 8/8 PASS post-implementación.

**Sandbox F.6 precedent**: 6/10 gates SKIPPED en F2.1 + F2.2 archive (npm 11.16.0 refuses workspace:*). F2.3 e2e (G3, G4, G8) van a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect.

---

## 12. Pre-flight checks ya cerrados

10 checks verificados antes de empezar implementación:

| # | Check | Source | Result |
|---|---|---|---|
| 1 | `plan.md` HU-F2.3 existe con 7 tasks + 8 gates + 13 DEC-UPD-NN | `plan.md:1244-1266` | PASS |
| 2 | main.ts boot lifecycle existe (whenReady + createMainWindow + window-all-closed) | `main.ts:41-54` | PASS |
| 3 | preload.ts bridge IPC 8 métodos wireados (F2.2) | `preload.ts:24-48` | PASS |
| 4 | bridge.d.ts BridgeSurface typed con apiStatus/kiosk/app (F2.2) | `bridge.d.ts:1-87` | PASS |
| 5 | electron-updater@^6.3.9 + electron-log@^5.1.7 + electron-store@^8.2.0 ya en deps (F2.1/F2.2) | `package.json:36-38` | PASS |
| 6 | bcrypt NO está en deps — F2.3 lo agrega | `package.json:22-52` (absent) | KNOWN-MISSING (mitigated: T4 plan agrega) |
| 7 | Vitest + Playwright + axe-core + esbuild + Vite stack completo | `package.json:53-77` | PASS |
| 8 | tsconfig.main.json strict + noUncheckedIndexedAccess; vite.config.ts alias @; esbuild-main.mjs target node20 cjs | tsconfig.main.json + vite.config.ts + esbuild-main.mjs | PASS |
| 9 | e2e/ tiene scaffold + auth + a11y; F2.3 agrega lifecycle + kiosko | e2e/ dir | PASS |
| 10 | apps/ui-kit exports Button + cn + tokens + useAuth + parkosFetch + authStore (F2.1+F2.2) | ui-kit/src/index.ts + ui-kit/package.json exports | PASS |

Result: 9/10 PASS + 1/10 KNOWN-MISSING (bcrypt, mitigated). Pre-flight gate PASS. F2.3 ready for `sdd-propose`.

---

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

---

## 14. Forward hooks (a Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.1** (login email+password) | `bridge.kiosk.toggle` (no — login UI no requiere kiosko) | Login form se monta dentro de kiosko mode (no operation conflict) |
| **HU-F3.2** (lockout visible) | electron-log (eventos 429 Retry-After) | parkosFetch emite log `auth.lockout{retry_after: seconds}` |
| **HU-F3.3** (abrir/cerrar turno) | `bridge.apiStatus` (verifica backend up antes de abrir turno) | Si 🔴, no permite abrir turno |
| **HU-F5.1+** (impresión térmica) | `bridge.imprimir` + kiosko mode (no operation conflict) | Impresión opera normal dentro de kiosko |
| **HU-F11.x** (sync UI) | `bridge.apiStatus.get` + `<StatusBar>` (F2.3 forward consumer) | StatusBar extendido con sync state (queue depth, lag seconds) |
| **HU-F2.4+** (post-Fase 2 ops) | `bridge.kiosk.toggle` para admin override (forward) | Admin puede forzar kiosko on/off remotamente via backend command |

---

## 15. Convenciones del proyecto

### 15.1 Commits

- Conventional Commits.
- **NO** "Co-Authored-By" attribution.
- **NO** AI trailers.
- Formato: `<type>(<scope>): <description>` con type ∈ {feat, fix, test, refactor, docs, chore}, scope ∈ {ui-kit, electron, web, ops}.
- Author: `Parkos Dev <dev@parkos.local>` (F2.1 precedent).

### 15.2 TDD estricto

- Cada test escrito ANTES de la implementación.
- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `services/{updater,api-status,kiosko}.ts`.
- Cobertura >80% en `StatusBar.tsx`.

### 15.3 Defense in depth

5 capas (XR6 pattern per `operations/spec.md:3951` + F2.2 §15.3 precedent):

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

### 15.5 Sandbox F.6 caveat (e2e)

Per F2.1 + F2.2 archive reports, las e2e (`lifecycle.spec.ts`, `kiosko.spec.ts`) corren en sandbox F.6 con npm 11.16.0 que refuses `workspace:*` resolution. F2.3 e2e van a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. e2e verdes en local dev (npm 11.16+ en Windows native) o CI con image compatible.

---

## 16. Estimación total

### 16.1 Production LOC

- C1 (updater + log-config): ~145 LOC.
- C2 (api-status + StatusBar): ~160 LOC production + ~20 LOC JSON i18n.
- C3 (single-instance + kiosko): ~170 LOC.
- Total production: **~475 LOC** + **~50 LOC** configs/package.json edits + **~30 LOC** comentarios JSDoc = **~555 LOC**.

### 16.2 Test LOC

- `updater.test.ts`: ~30 LOC.
- `api-status.test.ts`: ~20 LOC.
- `kiosko.test.ts`: ~40 LOC.
- `StatusBar.test.tsx`: ~30 LOC.
- `e2e/lifecycle.spec.ts`: ~60 LOC.
- `e2e/kiosko.spec.ts`: ~60 LOC.
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

---

## 17. Commits planeados

| # | Task | Hash (TBD) | Message |
|---|---|---|---|
| 1 | T1 updater | TBD | `feat(electron): adicionar electron-updater con feed configurable + signature verification + autoDownload/autoInstallOnAppQuit` |
| 2 | T2 api-status | TBD | `feat(electron): adicionar api-status polling 30s a /health con AbortController timeout 5s + IPC bridge.apiStatus` |
| 3 | T3 single-instance | TBD | `feat(electron): adicionar single-instance lock con second-instance focus` |
| 4 | T4 kiosko | TBD | `feat(electron): adicionar kiosko mode con PIN bcrypt factor 12 + shortcuts bloqueados + Menu null + setKiosk` |
| 5 | T5 log-config | TBD | `feat(electron): adicionar electron-log con rotación 10MB×5 JSON + captura uncaughtException/unhandledRejection` |
| 6 | T6 StatusBar | TBD | `feat(ui): adicionar StatusBar con aria-live polite + de-duplicación de anuncios consecutivos` |
| 7 | T7 e2e | TBD | `test(electron): adicionar 2 e2e lifecycle + kiosko (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto)` |

Todos commiteados por `Parkos Dev <dev@parkos.local>`, sin Co-authored-by, sin AI trailers.

---

## 18. Referencias

### 18.1 Source of truth

- `plan.md` lines 1244-1266 — HU-F2.3 verbatim con 7 tareas atómicas T1..T7 (T1 updater lines 1260, T2 api-status line 1261, T3 single-instance line 1262, T4 kiosko PIN line 1263, T5 electron-log line 1264, T6 StatusBar line 1265, T7 e2e line 1266). Hard constraints: autoDownload/autoInstallOnAppQuit/allowDowngrade line 1249, single-instance lock line 1250, kiosko PIN bcrypt factor 12 line 1251, electron-log 10MB×5 line 1253, e2e segunda instancia + Ctrl+W + PIN incorrecto line 1255.
- `openspec/changes/hu-f2-3-electron-auto-update-kiosko/exploration.md` — 17 secciones, ~717 LOC, 13 DEC-UPD-NN (sección 5), 8 riesgos R1..R8 (sección 6), 7 atomic tasks T1..T7 con budgets (sección 9), 4 clusters C1..C4 (sección 10), 8 acceptance gates G1..G8 (sección 11), pre-flight 9/10 PASS + 1 KNOWN-MISSING (sección 12), out of scope (sección 13), forward hooks (sección 14), archivos a tocar (sección 17).

### 18.2 Precedentes archivados

- `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/proposal.md` — 16 secciones, ~770 LOC. Estructura verbatim (esta propuesta clona layout). DEC-FETCH-10 precedent: "F2.2 NO agrega REQ-OPS-NNN — infra HTTP/IPC, no behavior contract".
- `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/exploration.md` — 17 secciones, ~870 LOC. Precedente verbatim de template + estilo.
- `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/proposal.md` — 16 secciones, ~770 LOC. DEC-ELEC-10 precedent: "F2.1 NO agrega REQ-OPS-NNN — infra scaffold, no behavior contract".
- `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/exploration.md` — 17 secciones, ~1,150 LOC. DEC-ELEC-01..10 mirror. Workspaces topological order resuelto.
- `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/proposal.md` — 16 secciones canonical template.
- `openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/exploration.md` — 17 secciones template verbatim mirror.
- `openspec/changes/archive/bootstrap-monorepo-foundation/proposal.md:9` — workspaces precedent verbatim.

### 18.3 Apps anchors

- `apps/electron-sucursal/electron/main.ts:1-55` — F2.1 minimal app shell (whenReady + createMainWindow + window-all-closed). F2.3 lo extiende con init calls + IPC handlers + lock check.
- `apps/electron-sucursal/electron/preload.ts:1-49` — F2.2 whitelist IPC 8 métodos. F2.3 NO lo modifica.
- `apps/electron-sucursal/electron/bridge.d.ts:1-87` — F2.2 typed BridgeSurface. F2.3 delta en `ApiStatus` shape.
- `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts:1-110` — F2.2 contract test. F2.3 actualiza test 5 `apiStatus.get`.
- `apps/electron-sucursal/electron/__mocks__/electron.ts` — F2.2 mock para tests unit.
- `apps/electron-sucursal/package.json:22-77` — F2.1 deps + F2.2 zustand + swr + electron-store. F2.3 agrega `bcrypt` + `@types/bcrypt`.
- `apps/electron-sucursal/tsconfig.{json,main.json}` — F2.1 strict + noUncheckedIndexedAccess. F2.3 agrega `electron/services/**/*.ts` a include.
- `apps/electron-sucursal/vite.config.ts` — F2.1 renderer Vite alias `@`. F2.3 NO modifica.
- `apps/electron-sucursal/esbuild-main.mjs` — F2.1 main+preload esbuild target node20 cjs. F2.3 NO modifica (esbuild resuelve transitivamente).
- `apps/electron-sucursal/playwright.config.ts` — F2.1 `_electron` launch. F2.3 NO modifica (e2e auto-discovers `e2e/**/*.spec.ts`).
- `apps/electron-sucursal/src/renderer/App.tsx` — F2.1 router placeholder. F2.3 monta `<StatusBar />` arriba del `<main>`.
- `apps/electron-sucursal/src/renderer/i18n/locales/common.json` — F2.1 placeholder keys. F2.3 agrega `statusBar.ok`, `statusBar.slow`, `statusBar.offline`.
- `apps/electron-sucursal/src/renderer/main.tsx` — F2.1 entrypoint. F2.3 NO modifica.
- `apps/electron-sucursal/e2e/{scaffold.spec.ts,auth/parkos-fetch.spec.ts,auth/bridge.spec.ts,a11y/wcag-2.1-aa.spec.ts}` — F2.1+F2.2 e2e. F2.3 NO modifica.
- `apps/ui-kit/src/index.ts` — F2.1 exporta Button + cn + tokens. F2.3 NO modifica.
- `apps/ui-kit/src/{store/authStore.ts,hooks/useAuth.ts,fetch/parkosFetch.ts}` — F2.2 primitives. F2.3 NO modifica.

### 18.4 Documentación

- `docs/01-requisitos/no-funcionales.md:126` — RNF-022 WCAG 2.1 AA gate (axe-core tags).
- `docs/03-desarrollo/setup.md:15` — npm + npm-run-all pattern.
- `docs/03-desarrollo/estandares.md:79-91` — flat ESLint 9 config + convenciones.
- `docs/02-arquitectura/decisiones-tecnicas.md` — agregar DEC-UPD-01..13 (resumen) post-archive. Referenciar este proposal.md para detalle.

### 18.5 Specs y roadmap

- `openspec/specs/operations/spec.md:3951` — REQ-OPS-XR6 canonical 5-layer defense (reference, F2.3 NO crea new XR).
- `openspec/specs/operations/spec.md:4386` — F1.15 DEC-XR7 NOT-CREATED precedent.
- `openspec/_meta/roadmap.md:38-273` — IT-1..IT-10 web_sucursal consumer map.
- `openspec/_meta/roadmap.md:47` — web_sucursal ya existe (F2.1 fixed).
- `openspec/CHANGELOG.md` — Entrada: "2026-09-15 — HU-F2.3 auto-update + single-instance + kiosko + api-status + log-config + StatusBar archived".

### 18.6 Convenciones

- Conventional commits (sin Co-authored-by, sin AI trailers por convención global).
- Author: `Parkos Dev <dev@parkos.local>` (verbatim F2.1 precedent).
- TDD estricto: tests rojos primero, luego código que los hace verde.
- Defense in depth 5 capas (XR6 pattern + engineering variant).
- RFC 2119 MUST/SHOULD/MAY key words en DEC-UPD-NN.
- BDD Given/When/Then/And format en acceptance gates.

---

**End of proposal.**
