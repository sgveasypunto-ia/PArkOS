# Tasks — HU-F2.3 Auto-actualización, single-instance y kiosko

> **Phase**: tasks (sdd-tasks) · **Status**: ready for sdd-apply
> **HU ID**: HU-F2.3 (Fase 2 — última HU; cierra Andamiaje Electron con infra de runtime)
> **Working dir**: `E:\easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `6bfe514`, F2.1 + F2.2 archivados 2026-09-15)
> **Cross-refs**: `exploration.md` §5-§17, `proposal.md` §5-§17, `design.md` §5-§15 + Appendix A + Appendix B
> **Prereq change**: `hu-f2-2-parkos-fetch-ipc-auth-store` archived 2026-09-15
> **Author**: Parkos Dev <dev@parkos.local> · **Language**: español neutro profesional

---

## §0. Metadata

| Campo | Valor |
|---|---|
| **Change** | `hu-f2-3-electron-auto-update-kiosko` |
| **HU** | F2.3 — Auto-actualización electron-updater + single-instance lock + kiosko mode PIN bcrypt + api-status polling 30s + electron-log rotación 10MB×5 JSON + `<StatusBar>` aria-live polite |
| **Owner** | Parkos Dev <dev@parkos.local> |
| **Working tree** | `E:\easypunto_parkos` |
| **Branch base** | `feat/fase-2-electron-scaffold` (F2.1 + F2.2 archivados) |
| **PR target** | `feat/fase-2-electron-scaffold` (intra-fase, Fase 2 cierra aquí) |
| **Total tasks** | 7 atomic (T1..T7) |
| **Total clusters** | 4 (C1 infra runtime + C2 status UI + C3 lockdown + C4 testing) |
| **Production LOC budget** | ~555 LOC (production 475 + configs 50 + JSDoc 30) |
| **Test LOC budget** | ~240 LOC (unit 130 + e2e 120) |
| **Total LOC budget** | ~795 LOC |
| **Atomic commits** | 7 (C1: T1,T5 + C2: T2,T6 + C3: T3,T4 + C4: T7) |
| **Review actor** | `sdd-verify` post-apply |
| **Archive actor** | orchestrator (post-verify PASS) |
| **Related artifacts** | `exploration.md` (17 secciones, 13 DEC-UPD-NN, 8 riesgos R1..R8) · `proposal.md` (16 secciones, 8 gates G1..G8) · `design.md` (15 secciones + 2 apéndices, 5 TS mockups + 5 configs delta) · `specs/operations/spec.md` (NO-OP stub DEC-UPD-13) |
| **Scope** | Cerrar Fase 2 — infra runtime consumida por F3.x login/lockout/turno, F5.1+ impresión térmica, F11.x sync UI. NO incluye backend `/health`, OS-level kiosk, code signing certificates, login UI ni lockout UI. |
| **Dependencies** | F2.1 archivado (Electron scaffold) · F2.2 archivado (bridge IPC + parkosFetch + authStore) · npm 11.16.0 local Windows + npm sandbox F.6 caveat documentado |

---

## §1. Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Total LOC production | ~555 |
| Total LOC tests | ~240 |
| Total LOC delta | ~795 |
| Atomic tasks | 7 (T1..T7) |
| Clusters | 4 (C1..C4) orden mandatory C1 → C2 → C3 → C4 |
| Acceptance gates | 8 (G1..G8) |
| DEC-UPD-NN ratificadas | 13 (DEC-UPD-01..13) |
| Files NEW | 12 (~545 LOC) |
| Files MODIFY | 8 (~104 LOC delta) |
| Conventional commits | feat(electron) × 5 + feat(ui) × 1 + test(electron) × 1 |
| Author commits | `Parkos Dev <dev@parkos.local>` (sin Co-authored-by, sin AI trailers) |
| Sandbox F.6 caveat | npm 11.16.0 refuses workspace:* → e2e G3+G4+G8 SKIPPED local; CI matrix required |

**Paralelización intra-cluster** (cross-ref design §11):
- T1, T5 (C1) ejecutan en paralelo (ambos corren ANTES de `whenReady` y dentro de `whenReady`, sin acoplamiento entre sí — T1 init en whenReady, T5 init en boot sync).
- T2 (C2) corre DESPUÉS de C1 porque `bridge.apiStatus.get()` IPC handler se registra en whenReady tras log-config (T5).
- T6 (C2) corre DESPUÉS de T2 porque StatusBar consume `bridge.apiStatus.get()` shape `{ok, latency_ms, code?}` materializado por T2.
- T3, T4 (C3) corren DESPUÉS de C1 + C2 porque single-instance lock corre en boot (T3) y kiosko apply corre en whenReady tras updater+api-status init (T1+T2).
- T7 (C4) corre ÚLTIMO porque e2e lifecycle + kiosko requiere el runtime completo con T1..T6 mergeados.

**Dependencias entre clusters** (estrictas, no negociables):

```
C1 (T1, T5)
  │
  ├─► C2 (T2, T6)
  │     │
  │     └─► C3 (T3, T4)
  │           │
  │           └─► C4 (T7)
```

---

## §2. Dependency graph + Cluster ordering

### §2.1 Diagrama ASCII

```
                    ┌─────────────────────────────────────────────┐
                    │ BOOT (sync, top-level, ANTES de whenReady) │
                    └─────────────────────────────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────────┐
              │                        │                            │
              ▼                        ▼                            ▼
   ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────────────────┐
   │ T5 log-config       │  │ T3 single-instance  │  │ uncaughtException +      │
   │ (init en boot)      │  │ (lock check boot)   │  │ unhandledRejection       │
   └─────────────────────┘  └─────────────────────┘  └──────────────────────────┘
              │                        │                            │
              └────────┬───────────────┘                            │
                       │                                            │
                       ▼                                            │
              ┌─────────────────────────────────────┐                │
              │ whenReady().then(() => ...)        │                │
              └─────────────────────────────────────┘                │
                       │                                            │
   ┌───────────────────┼────────────────────┐                       │
   │                   │                    │                       │
   ▼                   ▼                    ▼                       │
┌──────────┐   ┌───────────────┐   ┌──────────────────┐            │
│ T1       │   │ T2            │   │ createMainWindow │            │
│ updater  │   │ api-status    │   │ (F2.1 verbatim)  │            │
│ init     │   │ polling init  │   └──────────────────┘            │
└──────────┘   └───────────────┘            │                       │
   │                   │                    │                       │
   │                   ▼                    ▼                       │
   │          ┌────────────────────┐  ┌──────────────────┐         │
   │          │ IPC handler        │  │ T4 kiosko apply  │         │
   │          │ `api:status`       │  │ (if env var set) │         │
   │          │ registra `getApi`  │  └──────────────────┘         │
   │          └────────────────────┘                                │
   │                                                                │
   ├─────────────────────┬─────────────────────────┐                │
   ▼                     ▼                         ▼                │
┌─────────────┐  ┌─────────────────┐  ┌──────────────────┐         │
│ T6 StatusBar│  │ T4 kiosko init  │  │ IPC handlers     │         │
│ (renderer)  │  │ (unlock handler)│  │ (api/kiosk/app)  │         │
└─────────────┘  └─────────────────┘  └──────────────────┘         │
                                                                ────┘
```

### §2.2 Tabla de orden estricto

| Step | Cluster | Task | Cuándo | Acción | Razón orden |
|---|---|---|---|---|---|
| 1 | C1 | **T5** | sync boot | `initLogConfig(log, app)` | Captura crashes tempranos (DEC-UPD-11); ANTES de cualquier código que pueda fallar. |
| 2 | C3 | **T3** | sync boot | `app.requestSingleInstanceLock()` + second-instance listener | Atomic check (DEC-UPD-07); si false → `app.quit()`; previene race conditions. |
| 3 | C1 | **T1** | whenReady | `initUpdater(autoUpdater, env)` | Auto-update puede emitir eventos durante la vida; init temprano (DEC-UPD-01/02/03/04). |
| 4 | C2 | **T2** | whenReady | `initApiStatus(httpUrl, 30_000, 5_000)` | Polling independiente; IPC handler `api:status` se registra al final. |
| 5 | — | — | whenReady | `createMainWindow()` (F2.1 verbatim) | BrowserWindow necesita `whenReady`. |
| 6 | C3 | **T4** | whenReady | `applyKiosko(mainWindow, store, env)` + `initKiosko(mainWindow, store)` | Requiere mainWindow vivo (DEC-UPD-08/09/10). |
| 7 | C2 | **T6** | renderer mount | `<StatusBar />` en `App.tsx` | Consume `bridge.apiStatus.get()` shape materializado en T2. |
| 8 | C4 | **T7** | post-merge T1..T6 | e2e `lifecycle.spec.ts` + `kiosko.spec.ts` | Requiere runtime completo (T3 + T4 + T1 + T2 + T6). |

### §2.3 Justificación de orden

- **C1 antes que C2** porque el IPC handler `api:status` (T2) se registra dentro de `whenReady` que también ejecuta `initUpdater` (T1) + `initLogConfig` (T5 ya en boot). El log-config (T5) es pre-requisito de cualquier otro init para capturar fallos tempranos.
- **C1 antes que C3** porque `applyKiosko` (T4) corre en `whenReady` que también inicializa updater (T1); el single-instance lock (T3) corre ANTES de `whenReady` pero comparte el sync boot phase.
- **C2 antes que C3** parcialmente: `bridge.apiStatus.get()` (T2) es consumido por StatusBar (T6) que se monta en renderer; pero kiosko (T4) NO consume api-status directamente. La dependencia T2 → T6 es renderer-side; T4 es main-side. Por tanto T4 puede correr en paralelo con T6 una vez T2 esté listo.
- **C3 antes que C4** porque e2e `lifecycle.spec.ts` valida single-instance (T3) + kiosko Ctrl+W (T4), y e2e `kiosko.spec.ts` valida PIN incorrecto (T4).
- **Ningún task puede saltarse pasos** sin invalidar acceptance gates (cross-ref §8 G1..G8).

---

## §3. Cluster C1 — Infra runtime (T1+T5)

### §3.0 Pre-requisitos C1

- branch: `feat/fase-2-electron-scaffold` checked out.
- working tree: `clean` (`git status --short` retorna vacío).
- pre-flight local:
  - `git log --oneline -1` → debe ser `6bfe514` o posterior (F2.2 archivado).
  - F2.1 archivado en `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/`.
  - F2.2 archivado en `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/`.
  - `electron-updater@^6.3.9` + `electron-log@^5.1.7` presentes en `apps/electron-sucursal/package.json:36-38` (F2.1 los agregó como placeholder).

### §3.1 Task T1 — electron-updater + signature verification

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~110 LOC delta) |
| **Order** | 1 (primera de C1) |
| **Cluster** | C1 |
| **Pre-requisitos** | F2.1 + F2.2 archivados; `electron-updater@^6.3.9` ya en deps |
| **Acceptance gates** | G1 (config autoDownload/autoInstallOnAppQuit/allowDowngrade), G2 (signature failure retry) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/electron/services/updater.ts` (~70 LOC).
- NEW: `apps/electron-sucursal/electron/services/updater.test.ts` (~30 LOC).
- MODIFY: `apps/electron-sucursal/electron/main.ts` (+5 LOC — `import { initUpdater } from './services/updater'` + `initUpdater(autoUpdater, process.env)` en whenReady).
- MODIFY: `apps/electron-sucursal/electron-builder.yml` (+12 LOC delta — flipear `autoUpdate:false → true` + agregar publish provider github + mac hardenedRuntime + win certificate reference).
- MODIFY: `apps/electron-sucursal/tsconfig.main.json` (+1 include — agregar `electron/services/**/*.ts`).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~30 LOC):
   - Test U1: `setFeedURL` lee `env.PARKOS_UPDATE_FEED_URL` cuando está presente → `expect(autoUpdater.setFeedURL).toHaveBeenCalledWith(envValue)`.
   - Test U2: `setFeedURL` fallback GitHub default `https://github.com/easypunto_parkos/easypunto_parkos/releases` cuando env ausente.
   - Test U3: `autoDownload === true` + `autoInstallOnAppQuit === true` + `allowDowngrade === false` (DEC-UPD-02/03 verbatim).
   - Test U4: signature verification failure → mock `autoUpdater.on('error', ...)` con `err.message` conteniendo `"signature"` → assert `log.error` invocado + NO `install` action + retry next cycle (interval sigue activo).
   - Test U5: `setInterval(checkForUpdates, 6h)` configurado → `expect(vi.getTimerCount()).toBeGreaterThan(0)` post-init; `dispose()` limpia interval.

2. **GREEN** (implementación mínima, ~70 LOC):
   - Función `initUpdater(autoUpdater, env, checkIntervalMs = 6 * 60 * 60 * 1000): UpdaterHandle` con `dispose()`.
   - `resolveFeedUrl(env)` lee `env.PARKOS_UPDATE_FEED_URL` o default GitHub.
   - Config flags verbatim: `autoDownload = true`, `autoInstallOnAppQuit = true`, `allowDowngrade = false`.
   - Listeners: `update-available` (log info), `update-not-available` (log debug), `download-progress` (log debug), `update-downloaded` (log info), `error` (log error + signature detection).
   - `setInterval(checkForUpdates, checkIntervalMs)` + check inmediato.

3. **REFACTOR** (extract constants, JSDoc):
   - `DEFAULT_FEED = 'https://github.com/easypunto_parkos/easypunto_parkos/releases'` constante module-level.
   - `DEFAULT_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000` constante module-level.
   - JSDoc en cada función exportada con cross-ref DEC-UPD-01/02/03/04.
   - Tipos `UpdaterConfig` + `UpdaterHandle` exportados.

**Commit message**:

```
feat(electron): adicionar electron-updater con feed configurable + signature verification + autoDownload/autoInstallOnAppQuit
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm vitest run electron/services/updater.test.ts --coverage
```

**LOC budget**: ~110 (production 80 + tests 30).

---

### §3.2 Task T5 — electron-log rotación 10MB×5 JSON + uncaughtException

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~40 LOC delta) |
| **Order** | 2 (segunda de C1; T5 antes que T1 lógicamente porque log-config corre en boot antes de whenReady) |
| **Cluster** | C1 |
| **Pre-requisitos** | F2.1 archivado; `electron-log@^5.1.7` ya en deps |
| **Acceptance gates** | G5 |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/electron/services/log-config.ts` (~25 LOC).
- MODIFY: `apps/electron-sucursal/electron/main.ts` (+5 LOC — `import { initLogConfig } from './services/log-config'` + `initLogConfig(log, app)` ANTES de `app.whenReady()` + `process.on('uncaughtException')` + `process.on('unhandledRejection')`).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~10 LOC):
   - Test L1: `transports.file.maxSize === 10 * 1024 * 1024` (10 MB) — DEC-UPD-11 verbatim.
   - Test L2: `transports.file.backups === 5` — DEC-UPD-11 verbatim.
   - Test L3: `format === formats.json` — DEC-UPD-11 verbatim.
   - Test L4: `process.on('uncaughtException', ...)` registrado con spy en `process.on`.
   - Test L5: `process.on('unhandledRejection', ...)` registrado con spy en `process.on`.

2. **GREEN** (implementación mínima, ~25 LOC):
   - Función `initLogConfig(logImpl, app)` configura `transports.file.{maxSize, backups, resolvePathFn}` + `logImpl.format`.
   - `process.on('uncaughtException', err => logImpl.error('uncaughtException', err))`.
   - `process.on('unhandledRejection', reason => logImpl.error('unhandledRejection', reason))`.

3. **REFACTOR** (extract constants, JSDoc):
   - `MAX_SIZE_BYTES = 10 * 1024 * 1024` constante.
   - `MAX_BACKUPS = 5` constante.
   - Path `app.getPath('userData')/logs/main.log` documentado en JSDoc.
   - JSDoc cross-ref DEC-UPD-11.

**Commit message**:

```
feat(electron): adicionar electron-log con rotación 10MB×5 JSON + captura uncaughtException/unhandledRejection
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm tsc --noEmit -p tsconfig.main.json && pnpm vitest run electron/services/log-config.test.ts
```

**LOC budget**: ~40 (production 30 + tests 10).

---

### §3.3 C1 commits ledger

| Hash TBD | Task | +LOC | -LOC | Files | Commit message |
|---|---|---|---|---|---|
| TBD-1 | T1 updater | +110 | -20 | 5 | `feat(electron): adicionar electron-updater con feed configurable + signature verification + autoDownload/autoInstallOnAppQuit` |
| TBD-2 | T5 log-config | +40 | -10 | 2 | `feat(electron): adicionar electron-log con rotación 10MB×5 JSON + captura uncaughtException/unhandledRejection` |
| **TOTAL C1** | — | **+150** | **-30** | **7** | — |

---

## §4. Cluster C2 — Status UI (T2+T6)

### §4.0 Pre-requisitos C2

- T1 + T5 merged (C1 done).
- branch: `feat/fase-2-electron-scaffold` checked out.
- working tree: `clean`.
- pre-flight local:
  - `apps/electron-sucursal/electron/services/{updater.ts, log-config.ts}` existen (T1 + T5 commitados).

### §4.1 Task T2 — api-status polling 30s + IPC handler

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~70 LOC delta) |
| **Order** | 3 (primera de C2) |
| **Cluster** | C2 |
| **Pre-requisitos** | C1 done (T1 + T5 merged); `bridge.apiStatus.get()` ya wireado en preload.ts (F2.2) |
| **Acceptance gates** | G6 |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/electron/services/api-status.ts` (~40 LOC).
- NEW: `apps/electron-sucursal/electron/services/api-status.test.ts` (~20 LOC).
- MODIFY: `apps/electron-sucursal/electron/main.ts` (+8 LOC — `import { initApiStatus, getApiStatus } from './services/api-status'` + `initApiStatus(url, 30_000, 5_000)` en whenReady + `ipcMain.handle('api:status', () => getApiStatus())`).
- MODIFY: `apps/electron-sucursal/electron/bridge.d.ts` (+5 LOC — `ApiStatus` shape delta `{online, lastSync}` → `{ok, latency_ms, code?}` per DEC-UPD-12).
- MODIFY: `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` (+5 LOC — actualizar test 5 `apiStatus.get` para match nuevo shape).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~20 LOC):
   - Test A1: 2xx response → `{ok: true, latency_ms: <ms>, code: 200}` con `latency_ms > 1000` logueado como slow.
   - Test A2: 5xx response → `{ok: false, latency_ms: <ms>, code: 500}`.
   - Test A3: timeout 5s → `{ok: false, code: undefined, latency_ms: -1}` con `vi.useFakeTimers` advance 5001ms.
   - Test A4: cache `getApiStatus()` antes del primer ping retorna `{ok: false, latency_ms: -1, code: undefined}` (initial state).

2. **GREEN** (implementación mínima, ~40 LOC):
   - Función `initApiStatus(httpUrl, intervalMs = 30_000, timeoutMs = 5_000): ApiStatusHandle` con `dispose()`.
   - Función `getApiStatus(): ApiStatusValue` retorna `lastResult` module-level.
   - `ping(httpUrl, timeoutMs)` usa `fetch` con `AbortController` + `setTimeout(() => controller.abort(), timeoutMs)`.
   - Cache `lastResult` actualizado post-ping.
   - `setInterval(ping, intervalMs)` + ping inmediato.

3. **REFACTOR** (extract constants, JSDoc):
   - `DEFAULT_INTERVAL_MS = 30_000` constante.
   - `DEFAULT_TIMEOUT_MS = 5_000` constante.
   - `SLOW_THRESHOLD_MS = 1_000` constante.
   - JSDoc en `ApiStatusValue` interface con 3 estados (🟢/🟡/🔴).
   - Tipos `ApiStatusHandle` + `ApiStatusValue` exportados.

**Commit message**:

```
feat(electron): adicionar api-status polling 30s a /health con AbortController timeout 5s + IPC bridge.apiStatus
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm tsc --noEmit -p tsconfig.main.json && pnpm vitest run electron/services/api-status.test.ts --coverage
```

**LOC budget**: ~70 (production 50 + tests 20).

---

### §4.2 Task T6 — `<StatusBar>` con aria-live polite + de-duplicación + debounce 2s

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~110 LOC delta) |
| **Order** | 4 (segunda de C2; corre DESPUÉS de T2 porque consume `bridge.apiStatus.get()` shape materializado por T2) |
| **Cluster** | C2 |
| **Pre-requisitos** | T2 merged (bridge.d.ts `ApiStatus` shape delta aplicado) |
| **Acceptance gates** | G7 (aria-live polite + 3 textos exactos + dedup + debounce 2s) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/src/renderer/components/StatusBar.tsx` (~70 LOC).
- NEW: `apps/electron-sucursal/src/renderer/components/StatusBar.test.tsx` (~30 LOC).
- MODIFY: `apps/electron-sucursal/src/renderer/App.tsx` (+3 LOC — `import { StatusBar } from './components/StatusBar'` + `<StatusBar />` arriba del `<main>`).
- MODIFY: `apps/electron-sucursal/src/renderer/i18n/locales/common.json` (+5 LOC — 6 keys: `statusBar.ok`, `statusBar.slow`, `statusBar.offline`, `statusBar.ok.aria`, `statusBar.slow.aria`, `statusBar.offline.aria`).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~30 LOC):
   - Test S1: 3 textos exactos — `{ok:true, latency_ms <= 1000}` → `"🟢 API OK"` · `{ok:true, latency_ms > 1000}` → `"🟡 API lento"` · `{ok:false}` → `"🔴 Sin API"`.
   - Test S2: atributo `aria-live="polite"` + `aria-atomic="true"` presentes en DOM.
   - Test S3: de-duplicación — cambio consecutivo al mismo estado NO actualiza `lastAnnouncedState` (assert ref no cambia).
   - Test S4: debounce 2s — cambio a estado distinto dentro de 2s NO actualiza `lastAnnouncedAt`; tras 2s sí actualiza.

2. **GREEN** (implementación mínima, ~70 LOC):
   - Componente `StatusBar()` con `useState<StatusBarState>` + `useRef<ApiStatus>` + `useRef<number>` (lastAnnouncedAt).
   - `useEffect` con `setInterval(tick, 30_000)` + `tick()` inmediato.
   - `deriveDisplay(apiStatus)` mapea a `'ok' | 'slow' | 'offline'`.
   - `displayText(display, t)` retorna texto exacto con emoji.
   - Lógica de-duplicación: `shouldAnnounce = display !== prev.lastAnnouncedState && now - prev.lastAnnouncedAt > 2000`.
   - JSX: `<div role="status" aria-live="polite" aria-atomic="true" aria-label={...} data-testid="status-bar">`.

3. **REFACTOR** (extract helpers, JSDoc):
   - Helpers `deriveDisplay` + `displayText` + `displayAriaLabel` extraídos.
   - Constantes `POLL_INTERVAL_MS = 30_000` + `ANNOUNCE_DEBOUNCE_MS = 2_000` + `SLOW_THRESHOLD_MS = 1_000`.
   - JSDoc cross-ref DEC-UPD-12.

**Commit message**:

```
feat(ui): adicionar StatusBar con aria-live polite + de-duplicación de anuncios consecutivos
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm vitest run src/renderer/components/StatusBar.test.tsx --coverage && pnpm vitest run e2e/a11y/wcag-2.1-aa.spec.ts
```

**LOC budget**: ~110 (production 80 + tests 30).

---

### §4.3 C2 commits ledger

| Hash TBD | Task | +LOC | -LOC | Files | Commit message |
|---|---|---|---|---|---|
| TBD-3 | T2 api-status | +70 | -20 | 5 | `feat(electron): adicionar api-status polling 30s a /health con AbortController timeout 5s + IPC bridge.apiStatus` |
| TBD-4 | T6 StatusBar | +110 | -30 | 4 | `feat(ui): adicionar StatusBar con aria-live polite + de-duplicación de anuncios consecutivos` |
| **TOTAL C2** | — | **+180** | **-50** | **9** | — |

---

## §5. Cluster C3 — Lockdown (T3+T4)

### §5.0 Pre-requisitos C3

- C1 + C2 merged (T1 + T5 + T2 + T6 done).
- branch: `feat/fase-2-electron-scaffold` checked out.
- working tree: `clean`.
- pre-flight local:
  - `apps/electron-sucursal/electron/services/{updater.ts, log-config.ts, api-status.ts}` existen (T1+T5+T2 commitados).
  - `<StatusBar />` montado en `App.tsx` (T6 commitado).

### §5.1 Task T3 — single-instance lock + second-instance focus

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~30 LOC delta) |
| **Order** | 5 (primera de C3; corre ANTES de T4 porque T4 applyKiosko requiere mainWindow vivo) |
| **Cluster** | C3 |
| **Pre-requisitos** | C1 + C2 done; `app` import disponible |
| **Acceptance gates** | G3 (cubierto por e2e T7 `lifecycle.spec.ts` E1) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- MODIFY: `apps/electron-sucursal/electron/main.ts` (+20 LOC — `if (!app.requestSingleInstanceLock()) { app.quit(); }` ANTES de `whenReady` + `app.on('second-instance', ...)` listener).
- NEW (opcional): `apps/electron-sucursal/electron/__tests__/single-instance.test.ts` (~10 LOC — test stub que mockea `app.requestSingleInstanceLock` y verifica flujo; e2e T7 cubre el caso real end-to-end).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~10 LOC):
   - Test SI1: `app.requestSingleInstanceLock()` retorna `false` → `app.quit()` llamado (DEC-UPD-07 verbatim).
   - Test SI2: `app.on('second-instance', handler)` registrado con spy.
   - Test SI3: handler `second-instance` invoca `mainWindow.focus()` (cuando mainWindow existe y no está minimized).

2. **GREEN** (implementación mínima, ~20 LOC):
   - `if (!app.requestSingleInstanceLock()) { app.quit(); }` ANTES de cualquier init.
   - `app.on('second-instance', () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); } })`.

3. **REFACTOR** (extract helper, JSDoc):
   - Helper `focusExistingWindow(mainWindow)` extraído.
   - JSDoc cross-ref DEC-UPD-07.

**Commit message**:

```
feat(electron): adicionar single-instance lock con second-instance focus
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm tsc --noEmit -p tsconfig.main.json && pnpm vitest run electron/__tests__/single-instance.test.ts
```

**LOC budget**: ~30 (production 20 + tests 10).

---

### §5.2 Task T4 — kiosko mode + PIN bcrypt factor 12

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done |
| **Type** | feature |
| **Atomicidad** | sí (1 commit, ~140 LOC delta) |
| **Order** | 6 (segunda de C3; corre DESPUÉS de T3 porque kiosko apply corre en whenReady tras lock check) |
| **Cluster** | C3 |
| **Pre-requisitos** | T3 merged; `bcrypt` + `@types/bcrypt` agregados a package.json (commit T4 incluye esto) |
| **Acceptance gates** | G4 (cubierto por unit T4 + e2e T7 `kiosko.spec.ts`) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Files**:
- NEW: `apps/electron-sucursal/electron/services/kiosko.ts` (~90 LOC).
- NEW: `apps/electron-sucursal/electron/services/kiosko.test.ts` (~40 LOC).
- MODIFY: `apps/electron-sucursal/electron/main.ts` (+30 LOC — `import { applyKiosko, initKiosko, tryUnlockKiosko } from './services/kiosko'` + `if (process.env.PARKOS_KIOSK_MODE === '1') { applyKiosko(...); initKiosko(...); }` en whenReady + IPC handlers `kiosk:toggle` + `kiosk:unlock` + `app:quit`).
- MODIFY: `apps/electron-sucursal/package.json` (+2 deps — `bcrypt@^5.1.1` + `@types/bcrypt@^5.0.2`).

**TDD strict RED → GREEN → REFACTOR**:

1. **RED** (tests rojos primero, ~40 LOC):
   - Test K1: `applyKiosko` → `mainWindow.setKiosk(true)` + `Menu.setApplicationMenu(null)` + `mainWindow.on('close', preventDefault)` + `webContents.on('before-input-event', blockShortcuts)`.
   - Test K2: `blockShortcuts` bloquea `Ctrl+W` (input.control + key='w') + `Alt+F4` (input.alt + key='F4') vía `event.preventDefault()`.
   - Test K3: PIN correcto → `bcrypt.compareSync(pin, hash)` retorna `true` → reset counter + `unlock` event emitted.
   - Test K4: PIN incorrecto → `bcrypt.compareSync` retorna `false` → counter++ + `lockout` event cuando counter >= 3.
   - Test K5: 3 intentos fallidos → `{success: false, reason: 'lockout', lockoutSecondsRemaining: 300}` + NO unlock.
   - Test K6: `store.get('kiosk.pinHash') === null` → `{success: false, reason: 'invalid_pin', remainingAttempts: 0}` + warning log.
   - Test K7: PIN NUNCA logueado — spy `log.info/warn/error` y assert NINGUNA llamada contiene el PIN string (DEC-UPD-09 verbatim).

2. **GREEN** (implementación mínima, ~90 LOC):
   - Función `applyKiosko(mainWindow, store, env)` con 4 efectos: `setKiosk(true)`, `Menu null`, `close preventDefault`, `before-input-event` shortcuts blocker.
   - Función `initKiosko(mainWindow, store): KioskoHandle` registra `Ctrl+Shift+K` listener scoped (NO `globalShortcut` — DEC-UPD-10).
   - Función `tryUnlockKiosko(pin, store): KioskoUnlockResult` con 4 paths: pin null, lockout, pin correcto, pin incorrecto.
   - Función `isKioskoLocked(store): boolean` lee `kiosk.failedAttempts` counter.
   - `randomUUID()` para `attempt_id` en cada unlock attempt log.
   - `MAX_FAILED_ATTEMPTS = 3` + `LOCKOUT_SECONDS = 300` constantes.

3. **REFACTOR** (extract UnlockState machine, JSDoc):
   - Helper `emitAuditLog(success, reason, attemptId)` extraído (NUNCA incluye PIN).
   - Tipos `KioskoHandle` + `KioskoStoreShape` + `KioskoUnlockResult` exportados.
   - JSDoc cross-ref DEC-UPD-08/09/10.

**Commit message**:

```
feat(electron): adicionar kiosko mode con PIN bcrypt factor 12 + shortcuts bloqueados + Menu null + setKiosk
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm tsc --noEmit -p tsconfig.main.json && pnpm vitest run electron/services/kiosko.test.ts --coverage
```

**LOC budget**: ~140 (production 100 + tests 40).

---

### §5.3 C3 commits ledger

| Hash TBD | Task | +LOC | -LOC | Files | Commit message |
|---|---|---|---|---|---|
| TBD-5 | T3 single-instance | +30 | -10 | 1-2 | `feat(electron): adicionar single-instance lock con second-instance focus` |
| TBD-6 | T4 kiosko | +140 | -40 | 4 | `feat(electron): adicionar kiosko mode con PIN bcrypt factor 12 + shortcuts bloqueados + Menu null + setKiosk` |
| **TOTAL C3** | — | **+170** | **-50** | **5-6** | — |

---

## §6. Cluster C4 — Testing (T7)

### §6.0 Pre-requisitos C4

- C1 + C2 + C3 merged (T1+T2+T3+T4+T5+T6 done).
- branch: `feat/fase-2-electron-scaffold` checked out.
- working tree: `clean`.
- pre-flight local:
  - Todos los servicios en `apps/electron-sucursal/electron/services/{updater,log-config,api-status,kiosko}.ts` existen.
  - `<StatusBar />` montado.
  - IPC handlers `api:status`, `kiosk:toggle`, `kiosk:unlock`, `app:quit` registrados.
  - `bcrypt` instalado localmente (npm install en sandbox F.6 SKIPPED — documentado en §10).

### §6.1 Task T7 — 2 e2e lifecycle + kiosko

| Campo | Valor |
|---|---|
| **Status** | pending → ready → in_progress → done |
| **Type** | test |
| **Atomicidad** | sí (1 commit, ~120 LOC delta tests only) |
| **Order** | 7 (última de C4; corre DESPUÉS de T1..T6 mergeados) |
| **Cluster** | C4 |
| **Pre-requisitos** | C1+C2+C3 done; `apps/electron-sucursal/playwright.config.ts` auto-discovers `e2e/**/*.spec.ts` (F2.1) |
| **Acceptance gates** | G3, G4, G8 (cubierto por e2e `lifecycle.spec.ts` + `kiosko.spec.ts`) |
| **Commit author** | `Parkos Dev <dev@parkos.local>` |

**Sandbox F.6 caveat**: npm 11.16.0 en sandbox refuses `workspace:*` resolution. e2e G3+G4+G8 SKIPPED en este ambiente; CI matrix required. NO es project defect — precedent F2.1 + F2.2 verbatim.

**Files**:
- NEW: `apps/electron-sucursal/e2e/lifecycle.spec.ts` (~60 LOC — 3 escenarios E1+E2+E3).
- NEW: `apps/electron-sucursal/e2e/kiosko.spec.ts` (~60 LOC — 3 escenarios E4+E5+E6).

**E2E scenarios**:

**`lifecycle.spec.ts`** (3 escenarios per `plan.md:1255` verbatim):
- **E1**: segunda invocación enfoca primera + termina (`_electron.launch` 2 veces; segunda retorna `false` de `requestSingleInstanceLock` → `app.quit()` invocado; primera ventana recibe `second-instance` event → focus).
- **E2**: kiosko mode activo (`PARKOS_KIOSK_MODE=1`) → `Ctrl+W` no cierra ventana (`page.keyboard.press('Control+w')` + assert window still open).
- **E3**: kiosko mode activo → `Alt+F4` no cierra ventana (`page.keyboard.press('Alt+F4')` + assert window still open).

**`kiosko.spec.ts`** (3 escenarios per `plan.md:1255` + design §11.2):
- **E4**: PIN incorrecto no desactiva kiosko (`bridge.kiosk.toggle(true)` + IPC `kiosk:unlock` con PIN malo + assert kiosko still active).
- **E5**: 3 intentos fallidos → lockout 5 min (3 calls con PIN malo + assert 4to retorna `{reason: 'lockout', lockoutSecondsRemaining: 300}`).
- **E6**: Audit log `kiosko.unlock_attempt` emitido con `attempt_id` UUID + timestamp ISO + success boolean (PIN NUNCA en log — spy `electron-log` writes + assert NO call contiene PIN string).

**Commit message**:

```
test(electron): adicionar 2 e2e lifecycle + kiosko (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto)
```

**Verification command** (post-commit):

```bash
cd apps/electron-sucursal && pnpm playwright test e2e/lifecycle.spec.ts e2e/kiosko.spec.ts
```

**LOC budget**: ~120 tests.

---

### §6.2 C4 commits ledger

| Hash TBD | Task | +LOC | -LOC | Files | Commit message |
|---|---|---|---|---|---|
| TBD-7 | T7 e2e | +120 | 0 | 2 | `test(electron): adicionar 2 e2e lifecycle + kiosko (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto)` |
| **TOTAL C4** | — | **+120** | **0** | **2** | — |

---

## §7. Atomic commits ledger (consolidado)

| Hash TBD | Task | Cluster | Files | +LOC | -LOC | Commit message |
|---|---|---|---|---|---|---|
| TBD-1 | T1 updater | C1 | 5 | +110 | -20 | `feat(electron): adicionar electron-updater con feed configurable + signature verification + autoDownload/autoInstallOnAppQuit` |
| TBD-2 | T5 log-config | C1 | 2 | +40 | -10 | `feat(electron): adicionar electron-log con rotación 10MB×5 JSON + captura uncaughtException/unhandledRejection` |
| TBD-3 | T2 api-status | C2 | 5 | +70 | -20 | `feat(electron): adicionar api-status polling 30s a /health con AbortController timeout 5s + IPC bridge.apiStatus` |
| TBD-4 | T6 StatusBar | C2 | 4 | +110 | -30 | `feat(ui): adicionar StatusBar con aria-live polite + de-duplicación de anuncios consecutivos` |
| TBD-5 | T3 single-instance | C3 | 1-2 | +30 | -10 | `feat(electron): adicionar single-instance lock con second-instance focus` |
| TBD-6 | T4 kiosko | C3 | 4 | +140 | -40 | `feat(electron): adicionar kiosko mode con PIN bcrypt factor 12 + shortcuts bloqueados + Menu null + setKiosk` |
| TBD-7 | T7 e2e | C4 | 2 | +120 | 0 | `test(electron): adicionar 2 e2e lifecycle + kiosko (segunda instancia enfoca, Ctrl+W bloqueado, PIN incorrecto)` |
| **TOTAL** | **7 atomic** | **4 clusters** | **23-24** | **+620** | **-130** | — |

**Net LOC delta**: `+620 - 130 = +490 net LOC production + tests`.

---

## §8. Acceptance gates mapping

Cross-ref `proposal.md §11` + `design.md §11` + `plan.md:1244-1266` verbatim.

| Gate | Task | Mechanism | File | Verification command |
|---|---|---|---|---|
| **G1** | T1 | vitest unit | `updater.test.ts` | `pnpm vitest run electron/services/updater.test.ts --coverage` |
| **G2** | T1 | vitest unit (mock `autoUpdater.on('error')`) | `updater.test.ts` | idem G1 |
| **G3** | T3 + T7 | playwright e2e (`_electron.launch` 2 veces) | `lifecycle.spec.ts` | `pnpm playwright test e2e/lifecycle.spec.ts` |
| **G4** | T4 + T7 | vitest unit + playwright e2e | `kiosko.test.ts` + `kiosko.spec.ts` | `pnpm vitest run electron/services/kiosko.test.ts && pnpm playwright test e2e/kiosko.spec.ts` |
| **G5** | T5 | vitest unit (mock electron-log) | `log-config.test.ts` | `pnpm vitest run electron/services/log-config.test.ts` |
| **G6** | T2 | vitest unit (mock fetch) | `api-status.test.ts` | `pnpm vitest run electron/services/api-status.test.ts --coverage` |
| **G7** | T6 | vitest unit + axe-core | `StatusBar.test.tsx` + `e2e/a11y/wcag-2.1-aa.spec.ts` | `pnpm vitest run src/renderer/components/StatusBar.test.tsx && pnpm playwright test e2e/a11y/wcag-2.1-aa.spec.ts` |
| **G8** | T7 | playwright e2e | `lifecycle.spec.ts` + `kiosko.spec.ts` | `pnpm playwright test e2e/lifecycle.spec.ts e2e/kiosko.spec.ts` |

**Estado pre-flight target**: 0/8 PASS al inicio; **8/8 PASS** post-implementación en local dev (Windows native npm 11.16+) o CI matrix con image compatible.

**Sandbox F.6 caveat**: G3, G4, G8 SKIPPED en sandbox F.6 (npm 11.16.0 refuses workspace:*). G1, G2, G5, G6, G7 pueden ejecutar con mocks (sin necesidad de workspace resolution). Documentado en §10.

---

## §9. Verification contract (cross-ref `sdd-verify`)

`sdd-verify` debe validar los siguientes criterios antes de emitir PASS:

1. **7 atomic commits** en `feat/fase-2-electron-scaffold` con:
   - Author: `Parkos Dev <dev@parkos.local>` (verificado via `git log --format='%an <%ae>'`).
   - **SIN** `Co-authored-by` trailer (verificado via `git log --format='%(trailers)' --grep='Co-authored-by'` retorna vacío).
   - **SIN** AI trailers (no `Signed-off-by` automático, no `[AI]`, no `Generated by`).
   - Mensajes verbatim de §7 commits ledger.

2. **8/8 acceptance gates** evaluados:
   - G1, G2, G5, G6, G7 (unit + a11y) ejecutan localmente.
   - G3, G4, G8 (e2e) ejecutan solo en CI matrix (sandbox F.6 SKIPPED-env-blocked documentado).

3. **Coverage thresholds** (cross-ref design §11.5):
   - `electron/services/updater.ts` ≥80% lines.
   - `electron/services/api-status.ts` ≥80% lines.
   - `electron/services/kiosko.ts` ≥80% lines.
   - `electron/services/log-config.ts` ≥80% lines.
   - `src/renderer/components/StatusBar.tsx` ≥80% lines.
   - Verificado via `vitest --coverage` en CI matrix.

4. **TypeScript strict**:
   - `pnpm tsc --noEmit -p tsconfig.main.json` limpio en archivos nuevos.
   - `pnpm tsc --noEmit -p tsconfig.renderer.json` limpio en archivos nuevos.
   - **CERO** `any` introducido en código nuevo.

5. **Unit tests verde**:
   - `pnpm vitest --run` en archivos nuevos (`updater.test.ts`, `api-status.test.ts`, `kiosko.test.ts`, `log-config.test.ts`, `StatusBar.test.tsx`) verde.

6. **Canonical `openspec/specs/operations/spec.md` UNCHANGED**:
   - Byte count identical antes/después de F2.3 merge (DEC-UPD-13 NO-OP stub solo, archivo `openspec/changes/hu-f2-3-electron-auto-update-kiosko/specs/operations/spec.md` es nuevo, no modifica el canonical).

7. **`bridge.d.ts` `ApiStatus` shape delta**:
   - Actualizado simultáneamente en T2 (1 commit atómico).
   - `preload.contract.test.ts` test 5 actualizado para match nuevo shape.

8. **Defense in depth XR6 (5 capas)** preservado:
   - Layer 1 auth: F2.2 parkosFetch + F2.3 kiosko PIN bcrypt.
   - Layer 2 engineering: TS strict + noUncheckedIndexedAccess.
   - Layer 3 a11y: axe-core WCAG 2.1 AA + StatusBar `aria-live="polite"`.
   - Layer 4 contract: bridge.d.ts shape + Zod validation.
   - Layer 5 retry-budget: api-status 30s + updater 6h + kiosko lockout 3 attempts.

---

## §10. Sandbox F.6 + npm 11.16.0 caveat

Cross-ref `exploration.md §13` + `design.md §15.5` + precedent F2.1 + F2.2 archive reports.

**Documentación obligatoria**:

- `npm 11.16.0` en sandbox F.6 refuses `workspace:*` resolution (`apps/ui-kit` consume `apps/electron-sucursal` etc.). Esto bloquea `pnpm/npm install` con workspaces.
- e2e G3+G4+G8 (playwright `_electron.launch`) SKIPPED en este ambiente — `pnpm install` falla antes de poder ejecutar tests.
- **NO es project defect** — precedent verbatim F2.1 + F2.2 archive reports documentan misma limitation.
- e2e verdes en local dev (Windows native npm 11.16+) o CI con image compatible (ubuntu-latest, macos-latest).
- Unit tests G1, G2, G5, G6, G7 ejecutan con mocks (no requieren workspace resolution post-install) — estos sí corren localmente.

**Acciones en verify-report**:

- `verify-report.md` documenta D-env deviation: "e2e G3+G4+G8 SKIPPED en sandbox F.6 — CI matrix required para validar".
- `verify-report.md` lista los 5 unit gates PASS (G1, G2, G5, G6, G7) y los 3 e2e gates DEFERRED (G3, G4, G8) a CI.
- Status final del verify: `partial — CI matrix required para completar G3+G4+G8` (NO `fail`).

---

## §11. Forward hooks (a Fase 3+)

Cross-ref `proposal.md §14` + `design.md §14` + `exploration.md §14`.

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.1** (login email+password) | `bridge.kiosk.toggle` (consume sin operation conflict) | Login form se monta DENTRO de kiosko mode (no toggle UI para salir). |
| **HU-F3.2** (lockout visible) | electron-log (eventos 429 Retry-After) | parkosFetch emite log `auth.lockout{retry_after: seconds}`; F3.2 renderiza countdown UI. |
| **HU-F3.3** (abrir/cerrar turno) | `bridge.apiStatus` (verifica backend up antes de abrir turno) | Si 🔴, no permite abrir turno. |
| **HU-F5.1+** (impresión térmica) | `bridge.imprimir` + kiosko mode (no operation conflict) | Impresión opera normal dentro de kiosko. |
| **HU-F11.x** (sync UI) | `bridge.apiStatus.get` + `<StatusBar>` (F2.3 forward consumer) | StatusBar extendido con sync state (queue depth, lag seconds). |
| **HU-F2.4+** (post-Fase 2 ops) | `bridge.kiosk.toggle` para admin override (forward) | Admin puede forzar kiosko on/off remotamente via backend command. |
| **DEC-UPD-13 opcional** | `apps/ui-kit/src/hooks/useApiStatus.ts` (forward) | Wrapper SWR para `bridge.apiStatus.get()` si F11.x lo necesita como primitive. |

---

## §12. CHANGELOG

- (2026-09-15) **F2.3 tasks phase complete** — 7 atomic tasks T1..T7 across 4 clusters C1..C4 (orden C1 → C2 → C3 → C4 mandatory). ~795 LOC total (production 555 + tests 240). 8 acceptance gates G1..G8 mapeados a unit + e2e + a11y mechanisms. 13 DEC-UPD-NN ratificadas (cross-ref proposal §5 + exploration §5 + design §5). Sandbox F.6 caveat documentado (e2e G3+G4+G8 SKIPPED local, CI matrix required). Ready for `sdd-apply`.

---

## §13. End of tasks

Tasks artifact complete. Ready for `sdd-apply` to execute T1..T7 in 7 atomic commits across 4 clusters.
