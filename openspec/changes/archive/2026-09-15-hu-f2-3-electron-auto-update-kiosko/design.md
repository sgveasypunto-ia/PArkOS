# Diseño técnico — HU-F2.3 Auto-actualización, single-instance y kiosko

> **Change**: `hu-f2-3-electron-auto-update-kiosko` · **Folder**: `openspec/changes/hu-f2-3-electron-auto-update-kiosko/`
> **Phase**: design (sdd-design) · **Status**: ready for `sdd-tasks`
> **HU ID**: HU-F2.3 (Fase 2 — última HU; cierra Andamiaje Electron con infra de runtime)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `6bfe514`, F2.1 + F2.2 archivados 2026-09-15)
> **Inputs**: `proposal.md` (16 secciones, 13 DEC-UPD-NN, 8 acceptance gates, 4 clusters C1..C4, 7 tasks T1..T7, ~810 LOC), `exploration.md` (17 secciones, 13 DEC-UPD-NN, 8 riesgos R1..R8, 7 tasks T1..T7, ~715 LOC), `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/design.md` (16 secciones + 2 apéndices, ~1658 LOC — layout canónico clonado verbatim), `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/design.md` (precedente scaffold).
> **Language**: español neutro profesional · **Conventional commits**: feat(electron) / feat(ui) / test(electron) — sin Co-authored-by.

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F2.3 |
| **Fase** | 2 (Andamiaje Electron — última HU, infra de runtime) |
| **Change name** | `hu-f2-3-electron-auto-update-kiosko` |
| **Folder** | `openspec/changes/hu-f2-3-electron-auto-update-kiosko/` |
| **State** | design ready |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | sdd-propose (proposal.md) + sdd-explore (exploration.md) |
| **Próximo phase** | sdd-tasks (tras sdd-spec también listo) |
| **Language** | español neutro profesional |
| **Conventional commits** | feat(electron) / feat(ui) / test(electron) — sin Co-authored-by |
| **LOC target** | ~475 producción + ~240 tests + ~80 configs = **~795 LOC total** |

---

## 1. Visión general y objetivos

### 1.1 Objetivo primario

Definir la arquitectura técnica HOW de los seis bloques de infraestructura de runtime que F2.3 entrega sobre la base sentada por F2.1 (scaffold Electron 30 + Vite 5 + React 18 + TS 5 strict + Playwright `_electron` + axe-core) y F2.2 (bridge IPC 8 métodos typed + parkosFetch + authStore + useAuth):

1. **`electron-updater`** — wrapper `initUpdater(autoUpdater, env)` con `setFeedURL(env||default_github)`, `autoDownload:true`, `autoInstallOnAppQuit:true`, `allowDowngrade:false`. Listeners para `update-available`/`update-not-available`/`download-progress`/`update-downloaded`/`error`. Ubicado en `apps/electron-sucursal/electron/services/updater.ts`.
2. **`electron-log`** — wrapper `initLogConfig(log, app)` con `transports.file.maxSize = 10 * 1024 * 1024`, `transports.file.backups = 5`, `log.format = log.formats.json`. Captura `uncaughtException`/`unhandledRejection` con `log.error(...)`. Ubicado en `apps/electron-sucursal/electron/services/log-config.ts`.
3. **Single-instance lock** — `app.requestSingleInstanceLock()` antes de `whenReady`. Si retorna `false` → `app.quit()` inmediato. Si retorna `true` → registrar `app.on('second-instance', focusExisting)`.
4. **api-status polling 30s** — wrapper `initApiStatus(httpUrl, intervalMs, timeoutMs)` con `fetch` + `AbortController` timeout 5s + cache `lastResult`. IPC handler `api:status` que retorna `{ok, latency_ms, code?}`. Ubicado en `apps/electron-sucursal/electron/services/api-status.ts`.
5. **Kiosko mode con PIN bcrypt** — wrapper `initKiosko(mainWindow, electronStore, env)` con `setKiosk(true)`, `Menu.setApplicationMenu(null)`, `before-input-event` (bloquea `Ctrl+W`/`Alt+F4`), `Ctrl+Shift+K` unlock handler con `bcrypt.compareSync(pin, hash)` (factor 12, constant-time). Ubicado en `apps/electron-sucursal/electron/services/kiosko.ts`.
6. **`<StatusBar>` con a11y** — componente React con `aria-live="polite"`, de-duplicación de anuncios consecutivos via `useRef`, debounce 2s. Renderiza 🟢/🟡/🔴 según `ApiStatus`. Ubicado en `apps/electron-sucursal/src/renderer/components/StatusBar.tsx`.

Estos seis bloques desbloquean **12+ HUs downstream** (F3.1 login email+password, F3.2 lockout visible, F3.3 turno, F5.1+ impresión térmica, F11.x sync UI, F2.4+ admin override, IT-3..IT-10 operación) que consumirán la infra sin renegociar el contrato de runtime.

### 1.2 Objetivos secundarios

- **Defense in depth XR6** (cross-ref `operations/spec.md:3951` + F2.2 §15.3): las 5 capas existentes se fortalecen con la capa 5 retry-budget (`api-status` polling 30s + updater retry 6h + kiosko lockout 3 intentos). F2.3 NO crea nuevo REQ-OPS-XR — las decisiones viven como DEC-UPD-NN per F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10 precedent.
- **Kiosko desatendido safe**: auto-update silencioso + single-instance + PIN unlock + full-screen bloqueado. El operador no interactúa con update dialogs ni puede cerrar accidentalmente.
- **Logs estructurados**: rotación 10MB×5 JSON + captura de crashes tempranos. `electron-log` activo desde ANTES de `whenReady` para no perder crashes de boot.
- **api-status sin polling en renderer**: el polling ocurre en main process (security boundary — renderer NO hace fetch directo). El renderer consume `bridge.apiStatus.get()` que retorna el último valor cacheado.
- **a11y WCAG 2.1 AA** (RNF-022): `aria-live="polite"` + dedup + debounce 2s evita interrumpir al operador con screen reader.
- **Cobertura >80%** en `services/{updater,api-status,kiosko}.ts` y `StatusBar.tsx` (vitest --coverage threshold).
- **TDD estricto**: cada test escrito ANTES de la implementación; 8 acceptance gates (G1..G8) deben pasar antes de merge.

### 1.3 No-objetivos (cross-ref proposal §13 / exploration §13)

- Backend `/health` endpoint — F2.3 degrada a 🔴 gracefully mientras no exista. HU backend separada F3+.
- OS-level kiosk (Windows Assigned Access, macOS kiosk mode) — solo Electron-level best-effort.
- Code signing certificates — release pipeline concern, F2.3 asume electron-builder publish + GitHub releases con auto-sign.
- PIN rotation UI — solo deploy-time script `node scripts/seed-kiosko-pin.js`. NO UI (sería backdoor).
- Update rollback UI — `allowDowngrade:false`. Si update falla, retry next cycle (6h).
- StatusBar polling interval UI — 30s hardcoded per `plan.md:1244`.
- Login UI (F3.1), Lockout UI (F3.2), Turno (F3.3) — F2.3 entrega infra; F3.x entrega UI.
- 2FA / WebAuthn — futuro.

---

## 2. Estado actual verificado (AS-IS)

### 2.1 main.ts — `apps/electron-sucursal/electron/main.ts:1-55`

```typescript
// F2.1 baseline (F2.3 lo extiende, no reemplaza)
import { app, BrowserWindow, shell } from 'electron';
import path from 'node:path';

const isDev = !app.isPackaged;
let mainWindow: BrowserWindow | null = null;

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    title: 'Parkos Sucursal',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

app.whenReady().then(() => createMainWindow());
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
});
```

**Gaps identificados (cross-ref exploration §2.1 R-MAIN-2..6,8)**:

| ID | Gap | F2.3 fix |
|---|---|---|
| R-MAIN-2 | NO llama `app.requestSingleInstanceLock()` | T3 (DEC-UPD-07) |
| R-MAIN-3 | NO inicializa `electron-log` rotación | T5 (DEC-UPD-11) |
| R-MAIN-4 | NO wirea `electron-updater.autoUpdater` init | T1 (DEC-UPD-01/02/03/04) |
| R-MAIN-5 | NO handler IPC `api:status` | T2 (DEC-UPD-05/06) |
| R-MAIN-6 | NO handlers `kiosk:toggle` / `app:quit` | T4 (DEC-UPD-08/09/10) |
| R-MAIN-8 | NO captura `uncaughtException`/`unhandledRejection` | T5 (DEC-UPD-11) |

### 2.2 preload.ts — `apps/electron-sucursal/electron/preload.ts:1-49`

F2.2 shippeó whitelist de 8 métodos en 6 grupos. F2.3 **NO modifica preload.ts** — el contrato IPC ya está wireado, solo se implementan los handlers en main process.

```typescript
// F2.2 verbatim (F2.3 NO toca)
contextBridge.exposeInMainWorld('bridge', {
  apiStatus: { get: () => ipcRenderer.invoke('api:status') },
  kiosk: { toggle: (on) => ipcRenderer.send('kiosk:toggle', on) },
  app: { quit: () => ipcRenderer.send('app:quit') },
  // ... authStore.get/set/delete, imprimir, usb.list
});
```

### 2.3 bridge.d.ts — `apps/electron-sucursal/electron/bridge.d.ts:1-87`

**DELTA F2.3** (DEC-UPD-12, exploration §2.3 R-DTS-2):

```typescript
// F2.2 shape (ACTUAL)
export interface ApiStatus {
  online: boolean;
  lastSync: string | null;
}

// F2.3 shape (NUEVO — reemplazo breaking, actualizar preload contract test)
export interface ApiStatus {
  ok: boolean;
  latency_ms: number;
  code?: number;
}
```

**Justificación del delta**: el shape F2.2 `{online, lastSync}` no captura los 3 estados que el StatusBar debe renderizar (🟢 OK / 🟡 lento / 🔴 Sin API). F2.3 introduce `{ok, latency_ms, code?}` que mapea 1:1 a los 3 estados.

### 2.4 package.json — `apps/electron-sucursal/package.json:22-77`

**Deps ya presentes** (F2.1 + F2.2): `electron-updater@^6.3.9`, `electron-log@^5.1.7`, `electron-store@^8.2.0`, `electron@^30.5.1`, `electron-builder@^25.0.5`, `@playwright/test@^1.48.0`, `@axe-core/playwright@^4.10.0`.

**Agregar en F2.3** (T4 DEC-UPD-09):

```json
{
  "dependencies": {
    "bcrypt": "^5.1.1"
  },
  "devDependencies": {
    "@types/bcrypt": "^5.0.2"
  }
}
```

### 2.5 tsconfig + esbuild config

- `tsconfig.main.json` (F2.1): `strict:true` + `noUncheckedIndexedAccess:true` + include `electron/**/*.ts` + `electron/**/*.d.ts` + `src/main/**/*.ts` + `src/shared/**/*.ts`. **DELTA F2.3**: agregar `electron/services/**/*.ts` al include.
- `esbuild-main.mjs` (F2.1 DEC-ELEC-03): bundlea `electron/main.ts` → `out/main.js` + `electron/preload.ts` → `out/preload.js`. esbuild resuelve transitivamente desde `main.ts` entry, así que **NO requiere cambio** para incluir `electron/services/**/*.ts`.

### 2.6 e2e/ — `apps/electron-sucursal/e2e/`

**Existente** (F2.1+F2.2): `scaffold.spec.ts`, `auth/parkos-fetch.spec.ts`, `auth/bridge.spec.ts`, `a11y/wcag-2.1-aa.spec.ts`.

**Agregar en F2.3** (T7): `lifecycle.spec.ts` (segunda instancia focus + kiosko Ctrl+W bloqueado), `kiosko.spec.ts` (PIN incorrecto no desbloquea + log audit verificado).

### 2.7 apps/ui-kit/

F2.1 exporta `Button + cn + tokens`. F2.2 exporta `authStore + useAuth + parkosFetch`. F2.3 **NO agrega nuevos exports a ui-kit** (DEC-UPD-13 opcional forward hook para `useApiStatus` queda como follow-up HU).

---

## 3. Estado objetivo (TO-BE)

### 3.1 main.ts (target)

```typescript
// F2.3 target (cross-ref exploration §7.1)
import { app, BrowserWindow, shell, ipcMain, Menu } from 'electron';
import { autoUpdater } from 'electron-updater';
import log from 'electron-log';
import Store from 'electron-store';
import path from 'node:path';
import { initUpdater } from './services/updater';
import { initLogConfig } from './services/log-config';
import { initApiStatus, getApiStatus } from './services/api-status';
import { initKiosko, applyKiosko, isKioskoLocked, tryUnlockKiosko } from './services/kiosko';

const isDev = !app.isPackaged;
let mainWindow: BrowserWindow | null = null;
const store = new Store({ name: 'auth' });

// (1) SINGLE-INSTANCE LOCK — ANTES de todo (DEC-UPD-07)
if (!app.requestSingleInstanceLock()) {
  app.quit();
}

// (2) ELECTRON-LOG INIT — antes de whenReady (DEC-UPD-11)
initLogConfig(log, app);
process.on('uncaughtException', (err) => log.error('uncaughtException', err));
process.on('unhandledRejection', (reason) => log.error('unhandledRejection', reason));

// (3) SECOND-INSTANCE LISTENER — registra la ventana a enfocar (DEC-UPD-07)
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

// (4) WHEN READY — composition (DEC-UPD-07 mandates order)
app.whenReady().then(() => {
  initUpdater(autoUpdater, process.env);
  initApiStatus(process.env.PARKOS_API_BASE ?? 'http://127.0.0.1:8000', 30_000, 5_000);

  mainWindow = createMainWindow();

  if (process.env.PARKOS_KIOSK_MODE === '1') {
    applyKiosko(mainWindow, store, process.env);
    initKiosko(mainWindow, store);
  }

  registerIpcHandlers(store);
});

// (5) IPC HANDLERS — registro único al final
function registerIpcHandlers(store: Store): void {
  ipcMain.handle('api:status', () => getApiStatus());
  ipcMain.on('kiosk:toggle', (_e, on: boolean) => {
    if (!mainWindow) return;
    if (on) applyKiosko(mainWindow, store, process.env);
    else mainWindow.setKiosk(false);
  });
  ipcMain.on('app:quit', () => app.quit());
}

// createMainWindow (F2.1 verbatim + return BrowserWindow para kiosko apply)
function createMainWindow(): BrowserWindow { /* ... F2.1 ... */ }

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
```

### 3.2 Seis bloques de infra (resumen)

| # | Bloque | Archivo | Lifecycle | Comandos IPC |
|---|---|---|---|---|
| 1 | electron-updater | `electron/services/updater.ts` | `whenReady` → check + 6h interval | `updater:status` (push a renderer, F11.x) |
| 2 | electron-log | `electron/services/log-config.ts` | boot (antes de `whenReady`) | — |
| 3 | single-instance | `main.ts` (top) | sync, boot | — |
| 4 | api-status | `electron/services/api-status.ts` | `whenReady` → setInterval 30s | `api:status` (invoke) |
| 5 | kiosko | `electron/services/kiosko.ts` | `whenReady` → apply si env var | `kiosk:toggle`, `app:quit` (send) |
| 6 | `<StatusBar>` | `src/renderer/components/StatusBar.tsx` | mount en `App.tsx` arriba del `<main>` | — (consume `bridge.apiStatus.get()`) |

---

## 4. Arquitectura de alto nivel

### 4.1 Vista de capas (ASCII)

```
┌────────────────────────────────── Renderer (React 18, Vite 5) ──────────────────────────────────┐
│                                                                                                  │
│   ┌────────────────────┐  IPC invoke  ┌────────────────────┐                                     │
│   │  <StatusBar />     │─────────────►│ bridge.apiStatus   │                                     │
│   │  (aria-live polite)│              │   .get()           │                                     │
│   │  useState +        │              └────────────────────┘                                     │
│   │  setInterval(30s)  │                                                                          │
│   │  dedup + debounce  │  IPC send     ┌────────────────────┐                                     │
│   │                    │───────────────►│ bridge.kiosk       │                                     │
│   │  useRef<ApiStatus> │              │   .toggle(on)      │                                     │
│   │  useRef<number>    │              │ bridge.app         │                                     │
│   │    lastAnnouncedAt │              │   .quit()          │                                     │
│   └────────────────────┘              └────────────────────┘                                     │
│                                                                                                  │
└──────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                           │ contextBridge.exposeInMainWorld('bridge', ...)
                                           ▼
┌─────────────────────────── Main Process (Electron 30 + electron-updater + electron-log) ─────────┐
│                                                                                                  │
│   BOOT SEQUENCE (synchronous, before whenReady):                                                 │
│   ┌────────────────────────────────────────────────────────────────────────────────────────┐    │
│   │ (1) app.requestSingleInstanceLock()  ──► false? app.quit() | true? continue             │    │
│   │ (2) initLogConfig()                  ──► log.transports.file.maxSize=10MB, backups=5    │    │
│   │ (3) process.on('uncaughtException')  ──► log.error(...)                                  │    │
│   │     process.on('unhandledRejection') ──► log.error(...)                                  │    │
│   └────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                                  │
│   WHEN READY (async):                                                                             │
│   ┌────────────────────────────────────────────────────────────────────────────────────────┐    │
│   │ (4) initUpdater(autoUpdater, env)         ──► setFeedURL, autoDownload, listeners       │    │
│   │ (5) initApiStatus(url, 30_000, 5_000)     ──► setInterval(30s) → fetch /health           │    │
│   │ (6) if env PARKOS_KIOSK_MODE === '1':                                                  │    │
│   │         applyKiosko(mainWindow, store)    ──► setKiosk(true), Menu null, Ctrl+W bloqueado│    │
│   │         initKiosko(mainWindow, store)      ──► Ctrl+Shift+K unlock handler               │    │
│   │ (7) createMainWindow()                    ──► BrowserWindow + webPreferences preload    │    │
│   └────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                                  │
│   IPC HANDLERS (final):                                                                          │
│   ipcMain.handle('api:status',  () => getApiStatus())                                            │
│   ipcMain.on('kiosk:toggle',   (_e, on) => on ? applyKiosko(...) : mainWindow.setKiosk(false))  │
│   ipcMain.on('app:quit',       () => app.quit())                                                 │
│                                                                                                  │
│   SECOND-INSTANCE LISTENER:                                                                      │
│   app.on('second-instance', () => { if (mainWindow) mainWindow.focus() })                       │
│                                                                                                  │
└──────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                           │ HTTPS (solo main process — renderer NO hace fetch directo)
                                           ▼
                          ┌──────────────────────────────┐
                          │ Backend FastAPI (F3+)        │
                          │ http://127.0.0.1:8000/health  │ ◄── STATUSBAR consumer
                          │ {status: "ok"} (hipotético)   │
                          └──────────────────────────────┘
                          ┌──────────────────────────────┐
                          │ GitHub Releases               │ ◄── UPDATER feed
                          │ (default) o PARKOS_UPDATE_    │     (configurable via env)
                          │ FEED_URL staging custom       │
                          └──────────────────────────────┘
                          ┌──────────────────────────────┐
                          │ electron-store (userData)     │
                          │ auth.json                     │ ◄── KIOSKO PIN hash
                          │ key: 'kiosk.pinHash'          │     bcrypt factor 12
                          └──────────────────────────────┘
                          ┌──────────────────────────────┐
                          │ electron-log (userData)       │ ◄── LOGGING rotación
                          │ logs/main.log + backups       │     10MB × 5 JSON
                          │ %APPDATA%/parkos/             │
                          └──────────────────────────────┘
```

### 4.2 Principios arquitectónicos

1. **SRP en main.ts**: `main.ts` es composición pura (imports + init calls + IPC handlers). Cada bloque de infra vive en `electron/services/{name}.ts`.
2. **Decorator pattern para init wrappers**: `initXxx(service, env)` retorna cleanup handle. Main.ts llama `initXxx` sin lógica inline.
3. **Renderer sin fetch directo**: el renderer consume IPC `bridge.apiStatus.get()` (cache main). UN solo origen de verdad para el network polling.
4. **Pre-shared secrets en electron-store**: PIN hash persistente con deploy-time seeding script (out-of-scope F2.3, documentado en §13).
5. **Boot order riguroso**: lock check + log init + crash handlers ANTES de `whenReady`. Esto captura crashes tempranos y previene race conditions.

---

## 5. Decisiones arquitectónicas (DEC-UPD-NN × 13)

Cross-ref `proposal.md` §5 + `exploration.md` §5. Tabla resumen con anclas a las justificaciones extendidas (exploration §8).

| ID | Title | Choice | Rationale | Alternativas rechazadas | Anchor |
|---|---|---|---|---|---|
| **DEC-UPD-01** | electron-updater feed configurable via env | `autoUpdater.setFeedURL(env || github_default)` runtime | Override staging sin recompilar; patrón `PARKOS_API_BASE` precedent | (a) publish estático en electron-builder.yml — RECHAZADA (recompila); (b) sin default — RECHAZADA (falla en primer run) | proposal §5.1, exploration §5.1/8.1 |
| **DEC-UPD-02** | autoDownload + autoInstallOnAppQuit (NO prompt) | `autoDownload:true` + `autoInstallOnAppQuit:true` | Kiosko desatendido — operador NO interactúa con dialogs | (a) modal "actualización disponible" — RECHAZADA; (b) menú buscar updates — RECHAZADA (kiosko oculta menú) | proposal §5.2 |
| **DEC-UPD-03** | allowDowngrade false + allowPrerelease false | `allowDowngrade:false` + `publish.allowPrerelease:false` | Schema migrations incompatibles con versiones anteriores | (a) permitir downgrade rollback — RECHAZADA (DB inconsistente); (b) prereleases staging — RECHAZADA (staging usa feed custom) | proposal §5.3 |
| **DEC-UPD-04** | Signature verification via electron-builder | `publish.provider:"github"` + macOS hardened + Windows Authenticode | Security boundary — MITM protection; electron-builder ya valida | (a) `crypto.verify()` manual — RECHAZADA (electron-builder ya lo hace); (b) skip dev — RECHAZADA (DX consistency) | proposal §5.4 |
| **DEC-UPD-05** | api-status polling 30s en main process | `services/api-status.ts` polling; renderer consume `bridge.apiStatus.get()` | Security boundary — renderer NO hace fetch directo (CORS+CSP) | (a) polling en renderer — RECHAZADA; (b) SSE backend — RECHAZADA (/health no existe) | proposal §5.5 |
| **DEC-UPD-06** | api-status timeout 5s vía AbortController | `fetch(url, {signal: AbortSignal.timeout(5000)})` | Kiosko desatendido — backend colgado no bloquea UI | (a) timeout 30s — RECHAZADA (UX inaceptable); (b) sin timeout — RECHAZADA (kiosko bloqueado) | proposal §5.6 |
| **DEC-UPD-07** | single-instance lock + second-instance focus | `requestSingleInstanceLock()` ANTES de `whenReady`; si false → quit; si true → listener focus | Race condition prevention; kiosko single-window por diseño | (a) lock after whenReady — RECHAZADA (race window); (b) spawn new window — RECHAZADA (race DB) | proposal §5.7, exploration §7.1 |
| **DEC-UPD-08** | kiosko via env `PARKOS_KIOSK_MODE=1` (no UI toggle) | Env var activate; no toggle UI (solo `Ctrl+Shift+K`+PIN para desactivar) | Kiosko es decisión de deploy, no operador; env var configurable sin recompilar | (a) toggle UI — RECHAZADA (backdoor); (b) archivo kiosko.json — RECHAZADA (env var KISS) | proposal §5.8 |
| **DEC-UPD-09** | PIN bcrypt factor 12 + constant-time compare | `bcrypt.hash(pin, 12)` pre-shared via electron-store; `bcrypt.compareSync`; PIN nunca logueado | Factor 12 OWASP 2023; constant-time previene timing attacks; offline-safe | (a) PIN por usuario backend — RECHAZADA (offline fails); (b) PIN por sucursal DB — RECHAZADA; (c) SHA-256 — RECHAZADA (no constant-time) | proposal §5.9, exploration §8.2 |
| **DEC-UPD-10** | Shortcuts bloqueados via `before-input-event` | `webContents.on('before-input-event')` bloquea `Ctrl+W` + `Alt+F4`; NO `globalShortcut` | Scoped a ventana Electron; `globalShortcut` OS-wide inacceptable | (a) `globalShortcut.register` — RECHAZADA (OS-wide); (b) `Menu null` solo — INSUFICIENTE | proposal §5.10 |
| **DEC-UPD-11** | electron-log rotación 10MB×5 JSON + captura crashes | `maxSize:10MB` + `backups:5` + `format:JSON` + `process.on('uncaughtException')` | Plan.md:1253 verbatim; 50MB cap evita disk fill; JSON parseable con `jq` | (a) rotación 5MB×10 — RECHAZADA (más I/O); (b) plain text — RECHAZADA (no parseable) | proposal §5.11 |
| **DEC-UPD-12** | `<StatusBar>` aria-live polite + dedup + debounce 2s | `aria-live="polite"` + `aria-atomic="true"` + `useRef` lastAnnounced + debounce 2000ms | RNF-022 WCAG 2.1 AA; polite no interrumpe; dedup evita spam | (a) `aria-live="assertive"` — RECHAZADA (interrumpe); (b) toast — RECHAZADA (no a11y); (c) sin dedup — RECHAZADA (spam) | proposal §5.12, exploration §8.3 |
| **DEC-UPD-13** | NO-OP delta stub para spec.md | `specs/operations/spec.md` ~85 LOC stub INFORMATIONAL; NO nuevos REQ-OPS-NNN | Precedente verbatim F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10; F2.3 es infra de runtime, no behavior contract | (a) REQ-OPS-113..125 — RECHAZADA (out-of-pattern); (b) capability `electron-runtime` — RECHAZADA (F1.15 DEC-XR7 NOT-CREATED) | proposal §5.13 |

---

## 6. Componentes y contratos (TS interfaces)

### 6.1 `ApiStatus` shape delta (bridge.d.ts)

```typescript
// apps/electron-sucursal/electron/bridge.d.ts (F2.3 MODIFY — DEC-UPD-12)

/**
 * Estado del backend health check (F2.3 delta).
 * - `ok:true, latency_ms <= 1000` → 🟢 API OK
 * - `ok:true, latency_ms > 1000`  → 🟡 API lento
 * - `ok:false`                    → 🔴 Sin API
 */
export interface ApiStatus {
  /** true si el backend respondió 2xx (independiente del latency). */
  ok: boolean;
  /** Latencia del ping en milisegundos. `-1` si no hay medición (cache inicial). */
  latency_ms: number;
  /** HTTP status code si la respuesta fue HTTP (4xx/5xx). Undefined para timeout/network error. */
  code?: number;
}
```

### 6.2 `UpdaterStatus` event payload (push a renderer, F11.x consumer)

```typescript
// apps/electron-sucursal/electron/services/updater.ts (F2.3 NEW — DEC-UPD-04)

/**
 * Estado del auto-updater emitido via webContents.send('updater:status', payload).
 * F11.x sync UI consume (F2.3 NO renderiza UI; solo emite evento).
 */
export type UpdaterStatus =
  | { kind: 'checking' }
  | { kind: 'available'; version: string }
  | { kind: 'not-available'; currentVersion: string }
  | { kind: 'downloading'; percent: number; transferred: number; total: number }
  | { kind: 'downloaded'; version: string }
  | { kind: 'failed'; reason: string; signature?: boolean };
```

### 6.3 `KioskoState` env + electron-store shape

```typescript
// apps/electron-sucursal/electron/services/kiosko.ts (F2.3 NEW — DEC-UPD-08/09)

/**
 * Activación de kiosko via env var (deploy-time).
 * True iff `process.env.PARKOS_KIOSK_MODE === '1'`.
 */
export type KioskoEnvActivation = boolean;

/**
 * Estado del kiosko almacenado en electron-store bajo keys prefijadas 'kiosk.'.
 * - 'kiosk.pinHash'      → string (bcrypt hash $2b$12$...)
 * - 'kiosk.failedAttempts' → number (counter; reset on successful unlock)
 */
export interface KioskoStoreShape {
  pinHash: string | null;
  failedAttempts: number;
}

/**
 * Resultado de un intento de unlock Ctrl+Shift+K + PIN.
 */
export type KioskoUnlockResult =
  | { success: true; attemptId: string }
  | { success: false; reason: 'invalid_pin' | 'lockout'; remainingAttempts?: number; lockoutSecondsRemaining?: number };
```

### 6.4 `LogEntry` JSON format (electron-log rotation)

```typescript
// apps/electron-sucursal/electron/services/log-config.ts (F2.3 NEW — DEC-UPD-11)

/**
 * Formato de cada línea del log rotado (JSON estructurado).
 * Path: app.getPath('userData')/logs/main.log (Windows: %APPDATA%/parkos/logs/main.log).
 */
export interface LogEntry {
  /** ISO 8601 UTC timestamp. */
  timestamp: string;
  /** Log level: 'error' | 'warn' | 'info' | 'verbose' | 'debug' | 'silly'. */
  level: 'error' | 'warn' | 'info' | 'verbose' | 'debug' | 'silly';
  /** Mensaje libre. */
  message: string;
  /** Scope opcional ('updater', 'api-status', 'kiosko', 'uncaughtException', etc.). */
  scope?: string;
  /** Error stack si aplica. */
  stack?: string;
  /** Metadata arbitraria (request URL, HTTP status, attempt_id). */
  meta?: Record<string, unknown>;
}
```

### 6.5 `StatusBarState` (renderer)

```typescript
// apps/electron-sucursal/src/renderer/components/StatusBar.tsx (F2.3 NEW — DEC-UPD-12)

import type { ApiStatus } from '../../../electron/bridge';

export type StatusBarDisplay = 'ok' | 'slow' | 'offline';

export interface StatusBarState {
  /** Estado actual del backend (último valor cacheado por `bridge.apiStatus.get()`). */
  apiStatus: ApiStatus | null;
  /** Display derivado para renderizar texto + emoji. */
  display: StatusBarDisplay;
  /** Último estado anunciado (para de-duplicación). */
  lastAnnouncedState: StatusBarDisplay | null;
  /** Timestamp del último anuncio (ms epoch) — debounce 2s. */
  lastAnnouncedAt: number;
}
```

### 6.6 Tipos auxiliares

```typescript
// apps/electron-sucursal/electron/services/updater.ts (DEC-UPD-04)
export interface UpdaterConfig {
  feedUrl: string;
  autoDownload: true;
  autoInstallOnAppQuit: true;
  allowDowngrade: false;
  checkIntervalMs: number;          // 6h default
}

// apps/electron-sucursal/electron/services/api-status.ts (DEC-UPD-05/06)
export interface ApiStatusConfig {
  httpUrl: string;                  // 'http://127.0.0.1:8000/health'
  intervalMs: number;               // 30_000
  timeoutMs: number;                // 5_000
}

// apps/electron-sucursal/electron/services/kiosko.ts (DEC-UPD-08/09)
export interface KioskoConfig {
  pinHashKey: 'kiosk.pinHash';
  failedAttemptsKey: 'kiosk.failedAttempts';
  maxFailedAttempts: number;        // 3
  lockoutSeconds: number;           // 300 (5 min)
  unlockShortcut: 'Ctrl+Shift+K';
}
```

---

## 7. Servicios main process (services/*.ts)

Descripción del contrato de cada servicio. Mockups TS completos viven en Appendix A.

### 7.1 `electron/services/updater.ts` (~70 LOC target)

**Función exportada**: `initUpdater(autoUpdater: Electron.AutoUpdater, env: NodeJS.ProcessEnv): UpdaterHandle`.

**Responsabilidades** (DEC-UPD-01/02/03/04):

1. Lee `env.PARKOS_UPDATE_FEED_URL` o usa default GitHub releases. Llama `autoUpdater.setFeedURL(feedUrl)`.
2. Configura flags: `autoUpdater.autoDownload = true`, `autoUpdater.autoInstallOnAppQuit = true`, `autoUpdater.allowDowngrade = false`.
3. Registra listeners: `update-available` (log info + emit `updater:status`), `update-not-available` (log debug), `download-progress` (log debug), `update-downloaded` (log info + emit `updater:status`), `error` (log error + si signature → emit `updater:status` failed).
4. `setInterval(() => autoUpdater.checkForUpdates(), 6 * 60 * 60 * 1000)` (6h).
5. `autoUpdater.checkForUpdates()` inmediato al init.

**Retorna**: `UpdaterHandle` con `dispose()` que limpia el interval.

### 7.2 `electron/services/log-config.ts` (~25 LOC target)

**Función exportada**: `initLogConfig(log: typeof import('electron-log').default, app: Electron.App): void`.

**Responsabilidades** (DEC-UPD-11):

1. `log.transports.file.maxSize = 10 * 1024 * 1024` (10 MB).
2. `log.transports.file.backups = 5`.
3. `log.transports.file.resolvePathFn = () => path.join(app.getPath('userData'), 'logs', 'main.log')`.
4. `log.format = log.formats.json`.

### 7.3 `electron/services/api-status.ts` (~40 LOC target)

**Funciones exportadas**:

- `initApiStatus(httpUrl: string, intervalMs?: number, timeoutMs?: number): ApiStatusHandle`.
- `getApiStatus(): ApiStatus`.

**Responsabilidades** (DEC-UPD-05/06):

1. `setInterval(() => void ping(httpUrl, timeoutMs), intervalMs)`.
2. `ping` usa `fetch` con `AbortSignal.timeout(timeoutMs)`. Mide `Date.now()` antes y después → `latency_ms`.
3. Maneja 3 outcomes:
   - 2xx → `{ok: true, latency_ms: <ms>, code: <status>}`.
   - 4xx/5xx → `{ok: false, code: <status>, latency_ms: <ms>}`.
   - timeout/network error → `{ok: false, code: undefined, latency_ms: -1}`.
4. Cachea `lastResult` en variable módulo-level. `getApiStatus()` retorna el último cache.
5. Primer `getApiStatus()` antes del primer ping retorna `{ok: false, code: undefined, latency_ms: -1}`.

### 7.4 `electron/services/kiosko.ts` (~90 LOC target)

**Funciones exportadas**:

- `applyKiosko(mainWindow: BrowserWindow, store: Store, env: NodeJS.ProcessEnv): void`.
- `initKiosko(mainWindow: BrowserWindow, store: Store): KioskoHandle`.
- `tryUnlockKiosko(pin: string, store: Store): KioskoUnlockResult`.
- `isKioskoLocked(store: Store): boolean`.

**Responsabilidades** (DEC-UPD-08/09/10):

1. `applyKiosko`:
   - `mainWindow.setKiosk(true)`.
   - `Menu.setApplicationMenu(null)`.
   - `mainWindow.on('close', e => e.preventDefault())`.
   - `mainWindow.webContents.on('before-input-event', blockShortcuts)`.
2. `initKiosko`: registra `globalShortcut.register('CommandOrControl+Shift+K', promptUnlock)` O `mainWindow.webContents.on('before-input-event', detectUnlock)` + IPC `kiosk:unlock`.
3. `tryUnlockKiosko`:
   - Lee `store.get('kiosk.pinHash')`. Si `null` → `{success: false, reason: 'invalid_pin'}` + warning log.
   - Lee `store.get('kiosk.failedAttempts')` (default 0). Si `>= 3` → `{success: false, reason: 'lockout'}` + remaining lockout time.
   - `bcrypt.compareSync(pin, hash)`. Si `true` → reset counter + emit audit log `kiosko.unlock_attempt{success: true, attempt_id, timestamp}`.
   - Si `false` → `store.set('kiosk.failedAttempts', n + 1)` + emit audit log `kiosko.unlock_attempt{success: false, attempt_id, timestamp}`.
4. **PIN nunca logueado**. Solo `attempt_id` (uuid v4) + `timestamp` (ISO 8601) + `success` boolean.

---

## 8. IPC bridge integration

Cross-ref `exploration.md` §2.2 + `bridge.d.ts:1-87` F2.2 verbatim. Tabla completa de canales IPC con handlers F2.3.

| Channel | Dirección | Bridge method | F2.2 handler | F2.3 handler real | Gate |
|---|---|---|---|---|---|
| `auth-store:get` | renderer → main (invoke) | `bridge.authStore.get(key)` | `electron-store.get(key)` | (intacto, F2.2) | — |
| `auth-store:set` | renderer → main (invoke) | `bridge.authStore.set(key, value)` | `electron-store.set(key, value)` | (intacto, F2.2) | — |
| `auth-store:delete` | renderer → main (invoke) | `bridge.authStore.delete(key)` | `electron-store.delete(key)` | (intacto, F2.2) | — |
| `print:ticket` | renderer → main (invoke) | `bridge.imprimir(payload)` | STUB (F2.3 deferred) | FUERA scope F2.3 (F5.1+) | — |
| `usb:list` | renderer → main (invoke) | `bridge.usb.list()` | STUB (F2.3 deferred) | FUERA scope F2.3 (F5.1+) | — |
| `kiosk:toggle` | renderer → main (send) | `bridge.kiosk.toggle(on)` | STUB | `on ? applyKiosko(...) : mainWindow.setKiosk(false)` | G4 |
| `app:quit` | renderer → main (send) | `bridge.app.quit()` | STUB | `app.quit()` | — |
| `api:status` | renderer → main (invoke) | `bridge.apiStatus.get()` | STUB | `getApiStatus()` (cache `api-status` service) | G6 |
| `updater:status` (NEW F2.3) | main → renderer (send) | (consumidor F11.x) | NO existe | `webContents.send('updater:status', UpdaterStatus)` | G2 |

**Convención de nombres** (cross-ref F2.2 §6.4): `<group>:<method>` con `:` separador. Permite `grep -r 'kiosk:' electron/` para listar handlers + invokes cruzados.

**Channel nuevo F2.3**: `updater:status` es push-only (main → renderer). F2.3 NO renderiza UI para este canal; el handler emite y F11.x lo consume (forward hook).

---

## 9. Renderer: StatusBar component

Cross-ref `exploration.md` §9.6 T6 + `proposal.md` §1.6 + DEC-UPD-12.

### 9.1 Mockup del componente

```typescript
// apps/electron-sucursal/src/renderer/components/StatusBar.tsx (~70 LOC target)

import { useEffect, useRef, useState } from 'react';
import type { ApiStatus } from '../../../electron/bridge';
import type { StatusBarDisplay, StatusBarState } from './StatusBar.types';

const POLL_INTERVAL_MS = 30_000;
const ANNOUNCE_DEBOUNCE_MS = 2_000;
const SLOW_THRESHOLD_MS = 1_000;

function deriveDisplay(status: ApiStatus | null): StatusBarDisplay {
  if (status === null) return 'offline';
  if (!status.ok) return 'offline';
  if (status.latency_ms > SLOW_THRESHOLD_MS) return 'slow';
  return 'ok';
}

function displayText(display: StatusBarDisplay, t: (key: string) => string): string {
  switch (display) {
    case 'ok':      return `🟢 ${t('statusBar.ok')}`;
    case 'slow':    return `🟡 ${t('statusBar.slow')}`;
    case 'offline': return `🔴 ${t('statusBar.offline')}`;
  }
}

function displayAriaLabel(display: StatusBarDisplay, t: (key: string) => string): string {
  switch (display) {
    case 'ok':      return t('statusBar.ok.aria');
    case 'slow':    return t('statusBar.slow.aria');
    case 'offline': return t('statusBar.offline.aria');
  }
}

export function StatusBar(): JSX.Element {
  const [state, setState] = useState<StatusBarState>({
    apiStatus: null,
    display: 'offline',
    lastAnnouncedState: null,
    lastAnnouncedAt: 0,
  });

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    const tick = async (): Promise<void> => {
      const apiStatus = await window.bridge.apiStatus.get();
      if (cancelled) return;
      const display = deriveDisplay(apiStatus);
      const now = Date.now();

      setState((prev) => {
        const shouldAnnounce =
          display !== prev.lastAnnouncedState &&
          now - prev.lastAnnouncedAt > ANNOUNCE_DEBOUNCE_MS;

        return {
          apiStatus,
          display,
          lastAnnouncedState: shouldAnnounce ? display : prev.lastAnnouncedState,
          lastAnnouncedAt: shouldAnnounce ? now : prev.lastAnnouncedAt,
        };
      });
    };

    void tick();
    pollTimerRef.current = setInterval(() => void tick(), POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (pollTimerRef.current !== null) clearInterval(pollTimerRef.current);
    };
  }, []);

  const { display } = state;
  const useT = (key: string): string => {
    // F2.1 i18n helper — wrap real `useTranslation` from `react-i18next` (F2.1 ships `t()`).
    return key;
  };

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={displayAriaLabel(display, useT)}
      data-testid="status-bar"
      data-status={display}
      className="status-bar"
    >
      {displayText(display, useT)}
    </div>
  );
}
```

### 9.2 i18n keys (common.json delta)

```json
{
  "statusBar": {
    "ok": "API OK",
    "slow": "API lento",
    "offline": "Sin API",
    "ok.aria": "Conexión con el backend estable",
    "slow.aria": "Conexión con el backend lenta",
    "offline.aria": "Sin conexión con el backend"
  }
}
```

### 9.3 App.tsx mount delta

```typescript
// apps/electron-sucursal/src/renderer/App.tsx (F2.3 MODIFY)

import { StatusBar } from './components/StatusBar';

export default function App(): JSX.Element {
  return (
    <div className="app-root">
      <StatusBar />            {/* F2.3 NEW — mount arriba del <main> */}
      <main>{/* router placeholder F2.1 */}</main>
    </div>
  );
}
```

---

## 10. Orden de inicialización (boot sequence)

Cross-ref `proposal.md` §7.1 + `exploration.md` §7.1.

### 10.1 Diagrama de flujo

```
app boot (sync, top-level)
│
├── (1) app.requestSingleInstanceLock()
│       │
│       ├── false ──► app.quit()  ◄── segunda invocación termina
│       │
│       └── true ──► continue
│
├── (2) initLogConfig(log, app)
│       └── log.transports.file.{maxSize,backups}, log.format = JSON
│
├── (3) process.on('uncaughtException',  err => log.error(err))
│     process.on('unhandledRejection', reason => log.error(reason))
│
├── (4) app.on('second-instance', focusExisting)
│       └── (a) mainWindow.restore() si minimized
│           (b) mainWindow.focus()
│
└── (5) app.whenReady().then(() => { ... })
        │
        ├── (5a) initUpdater(autoUpdater, process.env)
        │       ├── autoUpdater.setFeedURL(env.PARKOS_UPDATE_FEED_URL || github_default)
        │       ├── autoUpdater.autoDownload = true
        │       ├── autoUpdater.autoInstallOnAppQuit = true
        │       ├── autoUpdater.allowDowngrade = false
        │       ├── listeners: update-available / not-available / download-progress / downloaded / error
        │       ├── setInterval(checkForUpdates, 6h)
        │       └── checkForUpdates() inmediato
        │
        ├── (5b) initApiStatus(httpUrl, 30_000, 5_000)
        │       └── setInterval(ping, 30_000)
        │
        ├── (5c) mainWindow = createMainWindow()
        │
        ├── (5d) if (process.env.PARKOS_KIOSK_MODE === '1'):
        │           ├── applyKiosko(mainWindow, store, env)
        │           │   ├── mainWindow.setKiosk(true)
        │           │   ├── Menu.setApplicationMenu(null)
        │           │   ├── mainWindow.on('close', e => e.preventDefault())
        │           │   └── mainWindow.webContents.on('before-input-event', blockShortcuts)
        │           └── initKiosko(mainWindow, store)
        │               └── Ctrl+Shift+K listener → IPC `kiosk:unlock`
        │
        └── (5e) registerIpcHandlers(store)
                ├── ipcMain.handle('api:status',  () => getApiStatus())
                ├── ipcMain.on('kiosk:toggle',   (_e, on) => ...)
                └── ipcMain.on('app:quit',       () => app.quit())
```

### 10.2 Tabla de orden estricto

| Step | Cuándo | Acción | Por qué este orden |
|---|---|---|---|
| 1 | sync boot | `requestSingleInstanceLock()` | Atomic check antes de cualquier init (DEC-UPD-07). |
| 2 | sync boot | `initLogConfig()` | Log path ANTES de cualquier código que pueda fallar (DEC-UPD-11). |
| 3 | sync boot | `uncaughtException` / `unhandledRejection` | Crash handlers listos antes de cualquier async (DEC-UPD-11). |
| 4 | sync boot | `app.on('second-instance')` | Listener registrado antes de que otra instancia intente focus (DEC-UPD-07). |
| 5a | whenReady | `initUpdater()` | Auto-update puede emitir eventos durante la vida de la app; init temprano (DEC-UPD-01). |
| 5b | whenReady | `initApiStatus()` | Polling independiente; puede correr antes/después de mainWindow sin acoplamiento (DEC-UPD-05). |
| 5c | whenReady | `createMainWindow()` | BrowserWindow necesita `whenReady` resuelto. |
| 5d | whenReady | `applyKiosko()` + `initKiosko()` | Requiere mainWindow vivo. |
| 5e | whenReady | `registerIpcHandlers()` | Handlers registrados al final para que `mainWindow` global ref esté asignada. |

### 10.3 Justificación de orden

- **(1) antes que (2)** porque si lock falla, NO queremos haber tocado el filesystem del userData.
- **(2) antes que (3)** porque si uncaughtException ocurre durante boot, necesitamos un logger configurado.
- **(3) antes que (5)** porque las exceptions en `whenReady().then(...)` deben loguearse, no crashear silenciosamente.
- **(4) puede ir antes o después de (5)**: lo ubicamos antes por simplicidad (listener activo desde el inicio).
- **(5a) antes que (5c)** porque updater puede emitir `update-downloaded` que requiere `mainWindow.webContents.send`. Sin mainWindow, el evento se pierde (acceptable — F2.3 no lo renderiza).
- **(5b) independiente** — polling no necesita mainWindow.
- **(5c) antes que (5d)** porque `applyKiosko` necesita mainWindow asignado.
- **(5e) último** — handlers usan `mainWindow` global, debe estar asignado.

---

## 11. Estrategia de testing

Cross-ref `proposal.md` §11 G1..G8 + `exploration.md` §11.

### 11.1 Vitest unit (mockeando electron, electron-log, electron-store)

**`apps/electron-sucursal/electron/services/updater.test.ts`** (~30 LOC, 5 escenarios):

| # | Escenario | Aserción clave |
|---|---|---|
| U1 | `setFeedURL` lee env si presente | `expect(autoUpdater.setFeedURL).toHaveBeenCalledWith(env.PARKOS_UPDATE_FEED_URL)` |
| U2 | `setFeedURL` fallback github default | sin env → `https://github.com/easypunto_parkos/easypunto_parkos/releases` |
| U3 | `autoDownload:true` + `autoInstallOnAppQuit:true` + `allowDowngrade:false` | assert properties |
| U4 | Signature verification failure → `error` event → log error + NO install | mock `autoUpdater.checkForUpdates` reject con signature error |
| U5 | setInterval 6h configurado | `expect(vi.getTimerCount()).toBeGreaterThan(0)` post-init |

**`apps/electron-sucursal/electron/services/api-status.test.ts`** (~20 LOC, 4 escenarios):

| # | Escenario | Aserción clave |
|---|---|---|
| U6 | 2xx → `{ok:true, latency_ms:N}` | mock fetch resolve 200 |
| U7 | 5xx → `{ok:false, code:500, latency_ms:N}` | mock fetch resolve 500 |
| U8 | timeout 5s → `{ok:false, code:undefined, latency_ms:-1}` | `vi.useFakeTimers` advance 5001ms |
| U9 | cache: `getApiStatus()` antes del primer ping retorna `{ok:false, latency_ms:-1}` | assert shape |

**`apps/electron-sucursal/electron/services/kiosko.test.ts`** (~40 LOC, 7 escenarios):

| # | Escenario | Aserción clave |
|---|---|---|
| U10 | `applyKiosko` → `setKiosk(true)` + `Menu.setApplicationMenu(null)` | mock BrowserWindow + Menu |
| U11 | `applyKiosko` registra `before-input-event` listener | spy `webContents.on` |
| U12 | PIN correcto → unlock + reset counter | mock store + bcrypt |
| U13 | PIN incorrecto → NO unlock + counter++ | mock bcrypt.compareSync → false |
| U14 | 3 intentos fallidos → lockout | 3 calls con PIN malo → 4to retorna `{reason:'lockout'}` |
| U15 | PIN hash null (electron-store vacío) → `{success:false, reason:'invalid_pin'}` + warning log | mock store.get returns null |
| U16 | PIN nunca logueado | spy `log.info/warn/error` — ninguna llamada contiene el PIN string |

### 11.2 Playwright e2e (`_electron.launch`)

**`apps/electron-sucursal/e2e/lifecycle.spec.ts`** (~60 LOC, 3 escenarios):

| # | Escenario |
|---|---|
| E1 | segunda invocación enfoca primera + termina (`app.requestSingleInstanceLock` retorna false en segunda) |
| E2 | kiosko mode activo → `Ctrl+W` no cierra ventana |
| E3 | kiosko mode activo → `Alt+F4` no cierra ventana |

**`apps/electron-sucursal/e2e/kiosko.spec.ts`** (~60 LOC, 3 escenarios):

| # | Escenario |
|---|---|
| E4 | PIN incorrecto no desactiva kiosko |
| E5 | 3 intentos fallidos → lockout 5 min |
| E6 | Audit log `kiosko.unlock_attempt` emitido con `attempt_id` UUID + timestamp ISO + success boolean (PIN NUNCA en log) |

### 11.3 A11y axe-core (RNF-022)

**`apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts`** (F2.2 ya incluye; F2.3 +1 caso para StatusBar):

| # | Escenario |
|---|---|
| A1 | `<StatusBar>` con `aria-live="polite"` + `aria-atomic="true"` → axe-core 0 violaciones |

### 11.4 Sandbox F.6 caveat

Precedente verbatim F2.1 + F2.2 archive reports: e2e en sandbox F.6 con npm 11.16.0 que refuses `workspace:*` resolution. Las e2e F2.3 (E1..E6) van a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. e2e verdes en local dev (npm 11.16+ Windows native) o CI con image compatible.

### 11.5 Cobertura thresholds

```typescript
// apps/electron-sucursal/vitest.config.ts (extracto)
coverage: {
  provider: 'v8',
  thresholds: {
    'electron/services/updater.ts':   { lines: 80, functions: 80, branches: 75 },
    'electron/services/api-status.ts':{ lines: 80, functions: 80, branches: 75 },
    'electron/services/kiosko.ts':    { lines: 80, functions: 80, branches: 75 },
    'src/renderer/components/StatusBar.tsx': { lines: 80, functions: 80, branches: 75 },
  },
},
```

---

## 12. Configuración y tooling

Cross-ref `exploration.md` §17.2 + `proposal.md` §4.1.

### 12.1 `apps/electron-sucursal/package.json` delta (T4)

```diff
   "dependencies": {
+    "bcrypt": "^5.1.1",
     "electron": "^30.5.1",
     "electron-log": "^5.1.7",
     "electron-store": "^8.2.0",
     "electron-updater": "^6.3.9"
   },
   "devDependencies": {
+    "@types/bcrypt": "^5.0.2",
     "@playwright/test": "^1.48.0",
     "@axe-core/playwright": "^4.10.0"
   }
```

### 12.2 `apps/electron-sucursal/tsconfig.main.json` delta (T1)

```diff
   "include": [
     "electron/**/*.ts",
+    "electron/services/**/*.ts",
     "electron/**/*.d.ts",
     "src/main/**/*.ts",
     "src/shared/**/*.ts"
   ]
```

### 12.3 `apps/electron-sucursal/electron-builder.yml` delta (T1)

```diff
 appId: com.parkos.sucursal
 productName: Parkos Sucursal
-autoUpdate: false
+autoUpdate: true
 directories:
   output: dist
   buildResources: build
+publish:
+  - provider: github
+    owner: easypunto_parkos
+    repo: easypunto_parkos
+    releaseType: release
+    allowPrerelease: false
+mac:
+  hardenedRuntime: true
+  gatekeeperAssess: false
+win:
+  # Windows Authenticode via electron-builder auto-sign
+  # certificate file: process.env.WINDOWS_CERT_FILE (build pipeline concern)
```

### 12.4 Tooling sin cambios

- `esbuild-main.mjs` (F2.1 DEC-ELEC-03) — esbuild resuelve transitivamente `electron/services/**/*.ts` desde `main.ts` entry. NO requiere cambio.
- `vite.config.ts` (F2.1) — renderer Vite. NO requiere cambio.
- `playwright.config.ts` (F2.1) — auto-discovers `e2e/**/*.spec.ts`. NO requiere cambio.
- `apps/electron-sucursal/playwright.config.ts` — idem.

---

## 13. Riesgos y mitigaciones (R1..R8)

Cross-ref `exploration.md` §6 + `proposal.md` §5.

| # | Riesgo | Severidad | Mitigación | Test |
|---|---|---|---|---|
| **R1** | Signature verification failure en update (MITM) | MEDIUM | DEC-UPD-04: electron-builder publish valida firma automáticamente; `autoUpdater.on('error')` logea + NO instala + retry next cycle (6h). | U4 |
| **R2** | Backend `/health` NO existe → 🔴 permanente | HIGH | DEC-UPD-05/06: api-status degrada gracefully a `{ok:false, code:undefined}`; StatusBar 🔴. NO bloquea F2.3 (HU backend separada F3+). | U9 |
| **R3** | Single-instance lock race en startup | LOW | DEC-UPD-07: lock ANTES de whenReady; segunda instancia ve false y termina. | E1 |
| **R4** | Kiosko bypass via task manager / alt-tab | LOW | DEC-UPD-10: Electron-level best-effort; OS-level kiosk (Windows Assigned Access) FUERA scope Fase 2 (proposal §13 out-of-scope). | E2, E3 |
| **R5** | PIN brute force (1000 PINs/seg) | MEDIUM | DEC-UPD-09: bcrypt factor 12 = ~250ms/hash → max 4 PINs/seg. Lockout 3 intentos via electron-store counter (persiste tras restart). | U14, E5 |
| **R6** | bcrypt CPU cost (~250ms por unlock) | LOW | DEC-UPD-09: 250ms aceptable para unlock (UX: operador espera feedback). Lockout check O(1). | (perf manual) |
| **R7** | electron-log disk fill (rotación falla) | LOW | DEC-UPD-11: 50MB cap. Fallback: si `transports.file.write` falla, log a stderr (capturado por OS journald/EventLog). | (manual) |
| **R8** | StatusBar screen reader spam | MEDIUM | DEC-UPD-12: dedup consecutiva + debounce 2s + `aria-live="polite"` + `aria-atomic="true"`. | A1 + axe-core |

**Riesgos cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

---

## 14. Forward hooks (a Fase 3+)

Cross-ref `proposal.md` §14 + `exploration.md` §14.

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.1** (login email+password) | bridge.kiosk.toggle (no — login UI no requiere kiosko) | Login form se monta dentro de kiosko mode (no operation conflict). |
| **HU-F3.2** (lockout visible) | electron-log (eventos 429 Retry-After) | parkosFetch emite log `auth.lockout{retry_after: seconds}`; F3.2 renderiza countdown. |
| **HU-F3.3** (abrir/cerrar turno) | `bridge.apiStatus` (verifica backend up antes de abrir turno) | Si 🔴, no permite abrir turno. |
| **HU-F5.1+** (impresión térmica) | `bridge.imprimir` + kiosko mode (no operation conflict) | Impresión opera normal dentro de kiosko. |
| **HU-F11.x** (sync UI) | `bridge.apiStatus.get` + `<StatusBar>` (F2.3 forward consumer) | StatusBar extendido con sync state (queue depth, lag seconds). |
| **HU-F2.4+** (post-Fase 2 ops) | `bridge.kiosk.toggle` para admin override (forward) | Admin puede forzar kiosko on/off remotamente via backend command. |
| **DEC-UPD-13 opcional** | `apps/ui-kit/src/hooks/useApiStatus.ts` (forward) | Wrapper SWR para `bridge.apiStatus.get()` si F11.x lo necesita como primitive. |

---

## 15. Convenciones del proyecto

Cross-ref `proposal.md` §15 + `exploration.md` §15 + F2.1/F2.2 precedents.

### 15.1 Commits

- Conventional Commits.
- **NO** "Co-Authored-By" attribution. **NO** AI trailers.
- Formato: `<type>(<scope>): <description>` con type ∈ {feat, fix, test, refactor, docs, chore}, scope ∈ {ui-kit, electron, web, ops}.
- Author: `Parkos Dev <dev@parkos.local>` (verbatim F2.1 precedent).
- Mensajes T1..T7 detallados en `proposal.md` §17.

### 15.2 TDD estricto

- Cada test escrito ANTES de la implementación.
- Tests rojos primero, luego código que los hace verde.
- Cobertura >80% exigida en `services/{updater,api-status,kiosko}.ts` y `StatusBar.tsx`.

### 15.3 Defense in depth (5 capas)

| Layer | Mechanism | Source |
|---|---|---|
| 1 auth | JWT Bearer (F2.2) + kiosko PIN bcrypt (F2.3 DEC-UPD-09) | `useAuth.ts` + `kiosko.ts` |
| 2 engineering | TS strict + `noUncheckedIndexedAccess` + ESLint flat | tsconfig.* + eslint.config.js |
| 3 a11y | axe-core WCAG 2.1 AA + StatusBar `aria-live="polite"` | e2e/a11y/wcag-2.1-aa.spec.ts (F2.2) + DEC-UPD-12 |
| 4 contract | bridge.d.ts shape + Zod validation | bridge.d.ts + parkosFetch<T>(url, schema) (F2.2) |
| 5 retry-budget | API status polling 30s + updater retry 6h + kiosko lockout 3 attempts | DEC-UPD-02/06/09 |

F2.3 **NO crea un nuevo REQ-OPS-XR** — las decisiones viven en proposal.md como DEC-UPD-NN per F2.1 DEC-ELEC-10 + F2.2 DEC-FETCH-10 precedent.

### 15.4 Pending.md update (archive phase)

- Row 3 (HU-F2.3) en `pending.md §1` → marcar ✅ cerrado.
- Total LOC restante → `$0 LOC` (Fase 2 cerrada).
- Footer → "Fase 2 3/3 cerrado".

### 15.5 Sandbox F.6 caveat (e2e)

Per F2.1 + F2.2 archive reports, las e2e (`lifecycle.spec.ts`, `kiosko.spec.ts`) corren en sandbox F.6 con npm 11.16.0 que refuses `workspace:*` resolution. F2.3 e2e van a SKIP en el mismo sandbox — documentado como deviation D-env en verify-report, NO project defect. e2e verdes en local dev (npm 11.16+ Windows native) o CI con image compatible.

---

## Appendix A: TS mockups completos (~500 LOC)

### A.1 `electron/services/updater.ts` (~70 LOC target)

```typescript
// apps/electron-sucursal/electron/services/updater.ts

import type { App } from 'electron';
import log from 'electron-log';

export interface UpdaterHandle {
  dispose(): void;
}

export interface UpdaterConfig {
  feedUrl: string;
  autoDownload: true;
  autoInstallOnAppQuit: true;
  allowDowngrade: false;
  checkIntervalMs: number;
}

const DEFAULT_FEED = 'https://github.com/easypunto_parkos/easypunto_parkos/releases';
const DEFAULT_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

function resolveFeedUrl(env: NodeJS.ProcessEnv): string {
  const fromEnv = env['PARKOS_UPDATE_FEED_URL'];
  return typeof fromEnv === 'string' && fromEnv.length > 0 ? fromEnv : DEFAULT_FEED;
}

export function initUpdater(
  autoUpdater: {
    setFeedURL: (url: string) => void;
    autoDownload: boolean;
    autoInstallOnAppQuit: boolean;
    allowDowngrade: boolean;
    checkForUpdates: () => Promise<unknown>;
    on: (event: string, listener: (...args: unknown[]) => void) => void;
  },
  env: NodeJS.ProcessEnv,
  checkIntervalMs: number = DEFAULT_CHECK_INTERVAL_MS,
): UpdaterHandle {
  const feedUrl = resolveFeedUrl(env);
  autoUpdater.setFeedURL(feedUrl);
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowDowngrade = false;

  log.info('updater.init', { feedUrl, checkIntervalMs });

  autoUpdater.on('update-available', (info: unknown) => {
    log.info('updater.update-available', { info });
  });
  autoUpdater.on('update-not-available', (info: unknown) => {
    log.debug('updater.update-not-available', { info });
  });
  autoUpdater.on('download-progress', (progress: unknown) => {
    log.debug('updater.download-progress', { progress });
  });
  autoUpdater.on('update-downloaded', (info: unknown) => {
    log.info('updater.update-downloaded', { info });
  });
  autoUpdater.on('error', (err: unknown) => {
    const message = err instanceof Error ? err.message : String(err);
    const isSignature = /signature/i.test(message);
    log.error('updater.error', { message, signature: isSignature });
    // Retry next cycle (interval) — DO NOT install
  });

  // Initial check + recurring every 6h
  void autoUpdater.checkForUpdates();
  const intervalId = setInterval(() => {
    void autoUpdater.checkForUpdates();
  }, checkIntervalMs);

  return {
    dispose(): void {
      clearInterval(intervalId);
    },
  };
}
```

### A.2 `electron/services/log-config.ts` (~25 LOC target)

```typescript
// apps/electron-sucursal/electron/services/log-config.ts

import type { App } from 'electron';
import path from 'node:path';
import log from 'electron-log';

const MAX_SIZE_BYTES = 10 * 1024 * 1024;
const MAX_BACKUPS = 5;

export function initLogConfig(logImpl: typeof log, app: App): void {
  logImpl.transports.file.maxSize = MAX_SIZE_BYTES;
  logImpl.transports.file.backups = MAX_BACKUPS;
  logImpl.transports.file.resolvePathFn = (): string =>
    path.join(app.getPath('userData'), 'logs', 'main.log');
  logImpl.format = logImpl.formats.json;

  process.on('uncaughtException', (err) => {
    logImpl.error('uncaughtException', err);
  });
  process.on('unhandledRejection', (reason) => {
    logImpl.error('unhandledRejection', reason);
  });

  logImpl.info('log-config.init', {
    path: path.join(app.getPath('userData'), 'logs', 'main.log'),
    maxSizeBytes: MAX_SIZE_BYTES,
    maxBackups: MAX_BACKUPS,
  });
}
```

### A.3 `electron/services/api-status.ts` (~40 LOC target)

```typescript
// apps/electron-sucursal/electron/services/api-status.ts

import log from 'electron-log';

export interface ApiStatusHandle {
  dispose(): void;
}

const DEFAULT_INTERVAL_MS = 30_000;
const DEFAULT_TIMEOUT_MS = 5_000;
const SLOW_THRESHOLD_MS = 1_000;

let lastResult: ApiStatusValue = { ok: false, latency_ms: -1, code: undefined };

export interface ApiStatusValue {
  ok: boolean;
  latency_ms: number;
  code?: number;
}

async function ping(httpUrl: string, timeoutMs: number): Promise<ApiStatusValue> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = Date.now();

  try {
    const res = await fetch(httpUrl, { signal: controller.signal });
    const latency_ms = Date.now() - startedAt;
    if (res.ok) {
      if (latency_ms > SLOW_THRESHOLD_MS) {
        log.warn('api-status.slow', { latency_ms, code: res.status });
      }
      return { ok: true, latency_ms, code: res.status };
    }
    return { ok: false, latency_ms, code: res.status };
  } catch (err) {
    const latency_ms = Date.now() - startedAt;
    log.warn('api-status.error', { err: err instanceof Error ? err.message : String(err) });
    return { ok: false, latency_ms: latency_ms >= timeoutMs ? -1 : latency_ms, code: undefined };
  } finally {
    clearTimeout(timeoutId);
  }
}

export function initApiStatus(
  httpUrl: string,
  intervalMs: number = DEFAULT_INTERVAL_MS,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): ApiStatusHandle {
  const tick = async (): Promise<void> => {
    const result = await ping(httpUrl, timeoutMs);
    lastResult = result;
  };

  void tick();
  const intervalId = setInterval(() => {
    void tick();
  }, intervalMs);

  log.info('api-status.init', { httpUrl, intervalMs, timeoutMs });

  return {
    dispose(): void {
      clearInterval(intervalId);
    },
  };
}

export function getApiStatus(): ApiStatusValue {
  return lastResult;
}
```

### A.4 `electron/services/kiosko.ts` (~90 LOC target)

```typescript
// apps/electron-sucursal/electron/services/kiosko.ts

import { randomUUID } from 'node:crypto';
import { BrowserWindow, Menu } from 'electron';
import bcrypt from 'bcrypt';
import log from 'electron-log';

export interface KioskoHandle {
  dispose(): void;
}

export interface KioskoStoreShape {
  get(key: 'kiosk.pinHash'): string | null;
  get(key: 'kiosk.failedAttempts'): number | null;
  set(key: 'kiosk.pinHash', value: string): void;
  set(key: 'kiosk.failedAttempts', value: number): void;
}

export type KioskoUnlockResult =
  | { success: true; attemptId: string }
  | { success: false; reason: 'invalid_pin'; remainingAttempts: number }
  | { success: false; reason: 'lockout'; lockoutSecondsRemaining: number };

const MAX_FAILED_ATTEMPTS = 3;
const LOCKOUT_SECONDS = 300;

function blockShortcuts(event: Electron.Event, input: Electron.Input): void {
  if (input.control && input.key.toLowerCase() === 'w') {
    event.preventDefault();
  }
  if (input.alt && input.key === 'F4') {
    event.preventDefault();
  }
}

export function applyKiosko(
  mainWindow: BrowserWindow,
  _store: KioskoStoreShape,
  _env: NodeJS.ProcessEnv,
): void {
  mainWindow.setKiosk(true);
  Menu.setApplicationMenu(null);
  mainWindow.on('close', (e) => e.preventDefault());
  mainWindow.webContents.on('before-input-event', blockShortcuts);
  log.info('kiosko.applied');
}

export function initKiosko(
  mainWindow: BrowserWindow,
  store: KioskoStoreShape,
): KioskoHandle {
  // Ctrl+Shift+K listener scoped to mainWindow (NOT globalShortcut — DEC-UPD-10)
  const onBeforeInput = (event: Electron.Event, input: Electron.Input): void => {
    if (input.control && input.shift && input.key.toLowerCase() === 'k') {
      event.preventDefault();
      const pin = promptForPin(mainWindow); // simple window.prompt — see note below
      if (pin === null) return;
      const result = tryUnlockKiosko(pin, store);
      if (result.success) {
        mainWindow.setKiosk(false);
        Menu.setApplicationMenu(null);
      }
    }
  };
  mainWindow.webContents.on('before-input-event', onBeforeInput);

  return {
    dispose(): void {
      mainWindow.webContents.off('before-input-event', onBeforeInput);
    },
  };
}

// NOTE: `promptForPin` is a placeholder for F2.3 prototype. Production implementation
// should open a secure IPC-driven modal (F3.x consumer) — see forward hook.
function promptForPin(_mainWindow: BrowserWindow): string | null {
  // Minimal stub: Electron has no window.prompt. For sandbox validation, F2.3 e2e
  // uses IPC channel 'kiosk:unlock' with payload {pin: string} sent from a test-only
  // renderer route. F3.x will replace with proper modal UI.
  return null;
}

export function tryUnlockKiosko(pin: string, store: KioskoStoreShape): KioskoUnlockResult {
  const attemptId = randomUUID();
  const timestamp = new Date().toISOString();
  const pinHash = store.get('kiosk.pinHash');

  if (pinHash === null) {
    log.warn('kiosko.unlock_attempt', { attemptId, timestamp, success: false, reason: 'pin_missing' });
    return { success: false, reason: 'invalid_pin', remainingAttempts: 0 };
  }

  const failedAttempts = store.get('kiosk.failedAttempts') ?? 0;
  if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
    log.warn('kiosko.unlock_attempt', { attemptId, timestamp, success: false, reason: 'lockout' });
    return { success: false, reason: 'lockout', lockoutSecondsRemaining: LOCKOUT_SECONDS };
  }

  const isValid = bcrypt.compareSync(pin, pinHash);

  if (isValid) {
    store.set('kiosk.failedAttempts', 0);
    log.info('kiosko.unlock_attempt', { attemptId, timestamp, success: true });
    return { success: true, attemptId };
  }

  const next = failedAttempts + 1;
  store.set('kiosk.failedAttempts', next);
  log.warn('kiosko.unlock_attempt', { attemptId, timestamp, success: false, reason: 'invalid_pin' });

  if (next >= MAX_FAILED_ATTEMPTS) {
    return { success: false, reason: 'lockout', lockoutSecondsRemaining: LOCKOUT_SECONDS };
  }
  return { success: false, reason: 'invalid_pin', remainingAttempts: MAX_FAILED_ATTEMPTS - next };
}

export function isKioskoLocked(store: KioskoStoreShape): boolean {
  const failed = store.get('kiosk.failedAttempts') ?? 0;
  return failed >= MAX_FAILED_ATTEMPTS;
}
```

### A.5 `electron/main.ts` delta (~70 LOC target)

```typescript
// apps/electron-sucursal/electron/main.ts (F2.3 MODIFY)

import { app, BrowserWindow, ipcMain, Menu, shell } from 'electron';
import { autoUpdater } from 'electron-updater';
import log from 'electron-log';
import Store from 'electron-store';
import path from 'node:path';
import { initUpdater } from './services/updater';
import { initLogConfig } from './services/log-config';
import { initApiStatus, getApiStatus } from './services/api-status';
import {
  applyKiosko,
  initKiosko,
  tryUnlockKiosko,
  type KioskoStoreShape,
} from './services/kiosko';

const isDev = !app.isPackaged;
let mainWindow: BrowserWindow | null = null;

const store = new Store({ name: 'auth' }) as unknown as KioskoStoreShape;

// (1) SINGLE-INSTANCE LOCK — before any other init (DEC-UPD-07)
if (!app.requestSingleInstanceLock()) {
  app.quit();
}

// (2) LOG CONFIG — before whenReady (DEC-UPD-11)
initLogConfig(log, app);

// (3) SECOND-INSTANCE LISTENER — register early (DEC-UPD-07)
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

// (4) WHEN READY — composition (DEC-UPD-07 mandates order)
app.whenReady().then(() => {
  initUpdater(autoUpdater, process.env);
  initApiStatus(process.env['PARKOS_API_BASE'] ?? 'http://127.0.0.1:8000/health');

  mainWindow = createMainWindow();

  if (process.env['PARKOS_KIOSK_MODE'] === '1') {
    applyKiosko(mainWindow, store, process.env);
    initKiosko(mainWindow, store);
  }

  registerIpcHandlers(store);
});

function registerIpcHandlers(kioskoStore: KioskoStoreShape): void {
  ipcMain.handle('api:status', () => getApiStatus());
  ipcMain.on('kiosk:toggle', (_e, on: boolean) => {
    if (!mainWindow) return;
    if (on) applyKiosko(mainWindow, kioskoStore, process.env);
    else {
      mainWindow.setKiosk(false);
      Menu.setApplicationMenu(null);
    }
  });
  ipcMain.handle('kiosk:unlock', (_e, pin: string) => tryUnlockKiosko(pin, kioskoStore));
  ipcMain.on('app:quit', () => app.quit());
}

function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    title: 'Parkos Sucursal',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.once('ready-to-show', () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  if (isDev) {
    void win.loadURL('http://localhost:5173');
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    void win.loadFile(path.join(__dirname, '../dist/index.html'));
  }
  return win;
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && app.isReady()) {
    mainWindow = createMainWindow();
  }
});
```

### A.6 `electron/bridge.d.ts` delta (ApiStatus shape)

```diff
-/** Estado del backend health check. */
-export interface ApiStatus {
-  online: boolean;
-  lastSync: string | null;
-}
+/**
+ * Estado del backend health check (F2.3 delta — DEC-UPD-12).
+ * - ok:true, latency_ms <= 1000 → 🟢 API OK
+ * - ok:true, latency_ms >  1000 → 🟡 API lento
+ * - ok:false                     → 🔴 Sin API
+ */
+export interface ApiStatus {
+  ok: boolean;
+  latency_ms: number;
+  code?: number;
+}
```

### A.7 `electron/preload.ts` — sin cambios (F2.2 verbatim)

```typescript
// apps/electron-sucursal/electron/preload.ts (F2.2 verbatim — F2.3 NO modifica)

import { contextBridge, ipcRenderer } from 'electron';

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

### A.8 `electron/__tests__/preload.contract.test.ts` delta

```diff
   it('bridge.apiStatus.get retorna ApiStatus', async () => {
     const status = await bridge.apiStatus.get();
-    expect(status).toMatchObject({ online: expect.any(Boolean) });
+    expect(status).toMatchObject({
+      ok: expect.any(Boolean),
+      latency_ms: expect.any(Number),
+    });
+    expect(typeof status.code === 'undefined' || typeof status.code === 'number').toBe(true);
   });
```

---

## Appendix B: Configuraciones y archivos delta

### B.1 NEW (10 archivos de producción)

| Path | Task | LOC target |
|---|---|---|
| `apps/electron-sucursal/electron/services/updater.ts` | T1 | 70 |
| `apps/electron-sucursal/electron/services/updater.test.ts` | T1 | 30 |
| `apps/electron-sucursal/electron/services/api-status.ts` | T2 | 40 |
| `apps/electron-sucursal/electron/services/api-status.test.ts` | T2 | 20 |
| `apps/electron-sucursal/electron/services/kiosko.ts` | T4 | 90 |
| `apps/electron-sucursal/electron/services/kiosko.test.ts` | T4 | 40 |
| `apps/electron-sucursal/electron/services/log-config.ts` | T5 | 25 |
| `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` | T6 | 70 |
| `apps/electron-sucursal/src/renderer/components/StatusBar.test.tsx` | T6 | 30 |
| `apps/electron-sucursal/electron/__tests__/single-instance.test.ts` | T3 | 10 |
| `apps/electron-sucursal/e2e/lifecycle.spec.ts` | T7 | 60 |
| `apps/electron-sucursal/e2e/kiosko.spec.ts` | T7 | 60 |
| **TOTAL** | T1..T7 | **~545 LOC** |

### B.2 MODIFY (8 archivos de producción + configs)

| Path | Task | Delta LOC |
|---|---|---|
| `apps/electron-sucursal/electron/main.ts` | T1+T2+T3+T4+T5 | ~70 LOC delta |
| `apps/electron-sucursal/electron/bridge.d.ts` | T2 (DEC-UPD-12) | ~5 LOC delta |
| `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` | T2 | ~5 LOC delta |
| `apps/electron-sucursal/electron-builder.yml` | T1 | ~12 LOC delta |
| `apps/electron-sucursal/tsconfig.main.json` | T1 | +1 include |
| `apps/electron-sucursal/package.json` | T4 | +2 deps |
| `apps/electron-sucursal/src/renderer/App.tsx` | T6 | +3 LOC mount |
| `apps/electron-sucursal/src/renderer/i18n/locales/common.json` | T6 | +6 keys |
| **TOTAL** | T1..T7 | **~104 LOC delta** |

### B.3 Configuraciones (verbatim diffs)

#### B.3.1 `electron-builder.yml`

```diff
 appId: com.parkos.sucursal
 productName: Parkos Sucursal
-autoUpdate: false
+autoUpdate: true
 directories:
   output: dist
   buildResources: build
+publish:
+  - provider: github
+    owner: easypunto_parkos
+    repo: easypunto_parkos
+    releaseType: release
+    allowPrerelease: false
+mac:
+  hardenedRuntime: true
+  gatekeeperAssess: false
+win:
+  # Windows Authenticode via electron-builder auto-sign
+  # certificate file: process.env.WINDOWS_CERT_FILE (build pipeline concern)
```

#### B.3.2 `package.json`

```diff
   "dependencies": {
+    "bcrypt": "^5.1.1",
     "electron": "^30.5.1",
     "electron-log": "^5.1.7",
     "electron-store": "^8.2.0",
     "electron-updater": "^6.3.9"
   },
   "devDependencies": {
+    "@types/bcrypt": "^5.0.2",
     "@playwright/test": "^1.48.0",
     "@axe-core/playwright": "^4.10.0"
   }
```

#### B.3.3 `tsconfig.main.json`

```diff
   "include": [
     "electron/**/*.ts",
+    "electron/services/**/*.ts",
     "electron/**/*.d.ts",
     "src/main/**/*.ts",
     "src/shared/**/*.ts"
   ]
```

#### B.3.4 `i18n/locales/common.json`

```diff
 {
   "common": {
     "loading": "Cargando...",
     "error": "Error"
+  },
+  "statusBar": {
+    "ok": "API OK",
+    "slow": "API lento",
+    "offline": "Sin API",
+    "ok.aria": "Conexión con el backend estable",
+    "slow.aria": "Conexión con el backend lenta",
+    "offline.aria": "Sin conexión con el backend"
   }
 }
```

#### B.3.5 `App.tsx`

```diff
+import { StatusBar } from './components/StatusBar';
+
 export default function App(): JSX.Element {
   return (
     <div className="app-root">
+      <StatusBar />
       <main>{/* router placeholder F2.1 */}</main>
     </div>
   );
 }
```

### B.4 READ ONLY (anchors — NO modificar)

- `apps/web_admin/**` (F2.2 consumer, no F2.3 touch).
- `backend/.../api/v1/auth.py` (F2.2 consumer, no F2.3 touch).
- `apps/ui-kit/**` (F2.1+F2.2, no F2.3 touch — DEC-UPD-13 deja `useApiStatus` como optional forward hook).
- `apps/electron-sucursal/electron/preload.ts` (F2.2 verbatim, no F2.3 touch — handlers en main).
- `apps/electron-sucursal/e2e/{scaffold,auth/parkos-fetch,auth/bridge,a11y/wcag-2.1-aa}.spec.ts` (F2.1+F2.2, no F2.3 touch).
- `openspec/specs/operations/spec.md` (canonical, no F2.3 touch — DEC-UPD-13 stub INFORMATIONAL solo).
- `apps/electron-sucursal/esbuild-main.mjs` (F2.1 DEC-ELEC-03, esbuild resuelve transitivamente).

### B.5 Total de impacto

- **NEW**: 12 archivos de producción (~545 LOC) + 6 artefactos SDD (exploration + proposal + design + spec stub + tasks + archive-report + verify-report, ~2000 LOC).
- **MODIFY**: 8 archivos (~104 LOC delta).
- **READ ONLY**: 7 archivos.
- **TOTAL IMPACT**: 27 archivos de 545 LOC nuevos + 104 LOC delta + 2000 LOC artifacts.

---

## CHANGELOG

- (2026-09-15) F2.3 design phase complete — 15 secciones + 2 apéndices verbatim, ~790 LOC total. 13 DEC-UPD-NN documentados (cross-ref proposal §5 + exploration §5). 8 acceptance gates G1..G8 mapeados a tests (cross-ref proposal §11). Boot sequence riguroso (lock → log → crash handlers → whenReady → updater → api-status → kiosko → createWindow → IPC handlers). TS mockups válidos strict + noUncheckedIndexedAccess + no `any`. 6 TS interfaces en §6 + 5 TS mockups en Appendix A (updater + log-config + api-status + kiosko + main.ts delta) + 1 bridge.d.ts delta + 1 preload sin cambios + 1 contract test delta. 5 configs delta en Appendix B.3. Ready for sdd-tasks.

---

**End of design.**
